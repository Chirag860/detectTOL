"""The detectTOL page (NiceGUI). Display and clicks only; logic in :mod:`detecttol.app.state`."""

from __future__ import annotations

import base64
import itertools
import os
from pathlib import Path
from typing import Any

from fastapi import Response
from nicegui import app, run, ui

from detecttol.app.state import CAD_SUFFIXES, AppState, verdict
from detecttol.cad.cad_stack import CadStackError

_MESHES: dict[str, dict[int, bytes]] = {}  # token -> mesh number -> STL bytes
_TOKENS = itertools.count(1)

PALETTE = ["#4c78a8", "#59a14f", "#b07aa1", "#9c755f", "#76b7b2", "#edc948", "#ff9da7", "#bab0ac"]
COLOR_OTHER = "#d5d8dc"
COLOR_FROM, COLOR_TO, COLOR_CHAIN = "#1f6feb", "#e8590c", "#2f9e44"
LEVEL_COLOR = {"ok": "positive", "risk": "warning", "fail": "negative"}
STANDARDS = {"is": "IS (Indian Standards)", "iso": "ISO GPS", "asme": "ASME Y14.5"}
GENERAL = {
    "": "none (ask me)",
    "f": "f (fine)",
    "m": "m (medium)",
    "c": "c (coarse)",
    "v": "v (very coarse)",
}


@app.get("/dtol-mesh/{token}/{number}.stl")
def _mesh(token: str, number: int) -> Response:
    data = _MESHES.get(token, {}).get(number)
    if data is None:
        return Response(status_code=404)
    return Response(content=data, media_type="model/stl")


def _start_folder() -> Path:
    desktop = Path.home() / "Desktop"
    return desktop if desktop.is_dir() else Path.home()


@ui.page("/")
def page() -> None:
    state = AppState()
    view: dict[str, Any] = {"objects": {}, "token": None, "folder": _start_folder()}

    ui.page_title("detectTOL")
    with ui.header().classes("items-center justify-between"):
        ui.label("detectTOL — tolerance stack from your CAD model").classes("text-lg font-medium")
        ui.label("runs on this PC only").classes("text-xs opacity-80")

    with ui.row().classes("w-full items-start gap-4 p-2"):
        # ---------------- left: file, requirement --------------------------------------
        with ui.column().classes("w-96 shrink-0 gap-3"):
            with ui.card().classes("w-full"):
                ui.label("1. Open a model").classes("font-medium")
                folder_input = ui.input("Folder", value=str(view["folder"])).classes("w-full")
                browser = ui.column().classes("w-full gap-0 max-h-64 overflow-auto")
                drawing_box = ui.column().classes("w-full gap-0")
                status = ui.label("").classes("text-sm")

            with ui.card().classes("w-full"):
                ui.label("2. Choose the requirement").classes("font-medium")
                ui.label(
                    "Click a face in the 3D view for face 1, then for face 2 — or pick them from the lists."
                ).classes("text-sm")
                faces_label = ui.markdown("")
                from_in = ui.select({}, label="Face 1", with_input=True).classes("w-full")
                to_in = ui.select({}, label="Face 2", with_input=True).classes("w-full")
                with ui.row().classes("w-full"):
                    lsl_in = ui.number("Lower limit (mm)", value=0.0, format="%.4g").classes("w-36")
                    usl_in = ui.number("Upper limit (mm)", value=None, format="%.4g").classes(
                        "w-36"
                    )
                std_in = ui.select(STANDARDS, value="is", label="Drawing standard").classes(
                    "w-full"
                )
                gen_in = ui.select(
                    GENERAL, value="m", label="General tolerance for untoleranced dimensions"
                ).classes("w-full")
                with ui.row():
                    ui.button("Swap faces", on_click=lambda: swap()).props("flat dense")
                    ui.button("Save project", on_click=lambda: save_project()).props("flat dense")

        # ---------------- right: 3D, table, result -------------------------------------
        with ui.column().classes("grow gap-3 min-w-0"):
            scene_box = ui.card().classes("w-full")
            with scene_box:
                ui.label("3D view — drag to rotate, scroll to zoom, click a face").classes(
                    "text-sm"
                )
                scene = ui.scene(width=720, height=420, grid=False, on_click=lambda e: on_click(e))
            table_box = ui.card().classes("w-full")
            result_box = ui.card().classes("w-full")

    # ---------------- behaviour -----------------------------------------------------------

    def show_folder() -> None:
        folder = Path(folder_input.value or ".")
        browser.clear()
        if not folder.is_dir():
            with browser:
                ui.label("folder not found").classes("text-negative text-sm")
            return
        view["folder"] = folder
        entries = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        with browser:
            if folder.parent != folder:
                ui.button(".. (up)", on_click=lambda: goto(folder.parent)).props(
                    "flat dense no-caps align=left"
                )
            for p in entries:
                if p.name.startswith((".", "~$")):
                    continue
                if p.is_dir():
                    ui.button(f"📁 {p.name}", on_click=lambda p=p: goto(p)).props(
                        "flat dense no-caps align=left"
                    )
                elif p.suffix.lower() in (*CAD_SUFFIXES, ".dtol"):
                    ui.button(f"📄 {p.name}", on_click=lambda p=p: choose(p)).props(
                        "flat dense no-caps align=left color=primary"
                    )
        drawing_box.clear()
        drawings = [p for p in entries if p.suffix.lower() == ".slddrw"]
        if drawings:
            with drawing_box:
                ui.label("Drawings to read too (optional):").classes("text-sm mt-2")
                view["drawing_checks"] = {d: ui.checkbox(d.name, value=False) for d in drawings}
        else:
            view["drawing_checks"] = {}

    def goto(folder: Path) -> None:
        folder_input.value = str(folder)
        show_folder()

    async def choose(path: Path) -> None:
        nonlocal state
        drawings = [d for d, box in view.get("drawing_checks", {}).items() if box.value]
        status.text = (
            f"Reading {path.name} through SolidWorks (about 20 s)…"
            if path.suffix.lower() == ".sldasm"
            else f"Reading {path.name}…"
        )
        spinner = ui.notification(status.text, spinner=True, timeout=None)
        try:
            if path.suffix.lower() == ".dtol":
                state = await run.io_bound(AppState.load, path)
            else:
                await run.io_bound(state.open, path, drawings)
            from detecttol.cad.mesh import bounds, mesh_model, to_stl

            assert state.cad is not None
            meshes = await run.io_bound(mesh_model, state.cad.model.path)
        except (CadStackError, OSError, ValueError, RuntimeError) as exc:
            status.text = f"Could not open {path.name}: {exc}"
            status.classes(replace="text-sm text-negative")
            spinner.dismiss()
            return
        spinner.dismiss()
        status.classes(replace="text-sm")
        status.text = f"{path.name}: {state.summary()}"
        for note in state.cad.notes:
            ui.notify(note, type="info", timeout=8000)
        token = str(next(_TOKENS))
        _MESHES.clear()
        _MESHES[token] = {i: to_stl(m) for i, m in enumerate(meshes)}
        view["token"] = token
        parts = sorted({m.part for m in meshes})
        part_color = {p: PALETTE[i % len(PALETTE)] for i, p in enumerate(parts)}
        view["part_color"] = part_color
        scene.clear()
        objects: dict[str, Any] = {}
        with scene:
            for i, m in enumerate(meshes):
                objects[m.key] = (
                    scene.stl(f"/dtol-mesh/{token}/{i}.stl")
                    .with_name(m.key)
                    .material(part_color[m.part])
                )
        view["objects"] = objects
        lo, hi = bounds(meshes)
        centre = [(a + b) / 2 for a, b in zip(lo, hi, strict=True)]
        size = max(b - a for a, b in zip(lo, hi, strict=True)) or 1.0
        scene.move_camera(
            x=centre[0] + 0.3 * size, y=centre[1] + 0.7 * size, z=centre[2] + 0.6 * size,
            look_at_x=centre[0], look_at_y=centre[1], look_at_z=centre[2], duration=0,
        )  # fmt: skip
        view["face_options"] = face_options()
        from_in.set_options(dict(view["face_options"]), value=None)
        to_in.set_options(dict(view["face_options"]), value=None)
        lsl_in.value, usl_in.value = state.lsl, state.usl
        std_in.value, gen_in.value = state.standard, state.general_class or ""
        redraw()

    def face_options() -> dict[str, str]:
        assert state.cad is not None
        found: dict[tuple[str, int], list[str]] = {}
        for d in state.cad.dimensions:
            for ref in (d.from_face, d.to_face):
                found.setdefault((ref.part, ref.face_index), []).append(
                    f"{d.nominal:g} {d.upper_tol:+g}/{d.lower_tol:+g}"
                )
        options = {}
        for part in state.cad.model.parts:
            for f in part.faces:
                if f.normal is None:
                    continue
                axis = max(range(3), key=lambda k: abs(f.normal[k]))  # type: ignore[index]
                sign = "+" if f.normal[axis] > 0 else "-"  # type: ignore[index]
                at = f"{'xyz'[axis]} = {f.centroid[axis]:.4g}"
                tol = (
                    f"  [{'; '.join(found[(part.name, f.index)])}]"
                    if (part.name, f.index) in found
                    else ""
                )
                options[f"{part.name}:{f.index}"] = (
                    f"{part.name}:{f.index}  faces {sign}{'XYZ'[axis]} at {at}{tol}"
                )
        return options

    def on_select(which: str, key: str | None) -> None:
        if not key or state.cad is None:
            return
        current = state.face_from if which == "from" else state.face_to
        if current is not None and f"{current.part}:{current.face_index}" == key:
            return  # the list was only updated to show a 3D pick
        state.picking = "from" if which == "from" else "to"
        state.pick(key)
        redraw()

    from_in.on_value_change(lambda e: on_select("from", e.value))
    to_in.on_value_change(lambda e: on_select("to", e.value))

    def on_click(e: Any) -> None:
        if state.cad is None:
            return
        hit = next((h for h in e.hits if h.object_name in view["objects"]), None)
        if hit is None:
            return
        state.pick(hit.object_name)
        redraw()

    def swap() -> None:
        state.face_from, state.face_to = state.face_to, state.face_from
        state.result = None
        state.refresh()
        redraw()

    def on_requirement() -> None:
        state.lsl = None if lsl_in.value is None else float(lsl_in.value)
        state.usl = None if usl_in.value is None else float(usl_in.value)
        state.standard = std_in.value or "is"
        state.general_class = gen_in.value or None
        state.result = None
        state.refresh()
        redraw()

    for element in (lsl_in, usl_in, std_in, gen_in):
        element.on_value_change(lambda _e: on_requirement())

    def short_source(row: Any) -> str:
        if row.kind == "table":
            return (
                row.source.split(" (")[0].split(":")[0]
                + " (general tolerance; edit if the drawing differs)"
            )
        if row.kind == "cad":
            return row.source.replace("SolidWorks ", "").split(" (")[0]
        return row.source

    def save_project() -> None:
        if state.cad_file is None:
            ui.notify("Open a model first", type="warning")
            return
        target = state.cad_file.with_suffix(".dtol")
        state.save(target)
        ui.notify(f"Saved {target}", type="positive")

    def colour_faces() -> None:
        chain_parts = list(state.built.chain.path) if state.built else []
        for key, obj in view["objects"].items():
            part = key.rpartition(":")[0]
            if chain_parts:
                colour = (
                    PALETTE[chain_parts.index(part) % len(PALETTE)]
                    if part in chain_parts
                    else COLOR_OTHER
                )
            else:
                colour = view["part_color"][part]
            obj.material(colour)
        for ref, colour in ((state.face_from, COLOR_FROM), (state.face_to, COLOR_TO)):
            if ref is not None and f"{ref.part}:{ref.face_index}" in view["objects"]:
                view["objects"][f"{ref.part}:{ref.face_index}"].material(colour)

    def redraw() -> None:
        target = "face 1" if state.picking == "from" else "face 2"
        for box, ref in ((from_in, state.face_from), (to_in, state.face_to)):
            key = f"{ref.part}:{ref.face_index}" if ref else None
            if box.value != key and (key is None or key in box.options):
                box.set_value(key)
        faces_label.content = (
            f"**Face 1** (blue): {state.face_label(state.face_from)}  \n"
            f"**Face 2** (orange): {state.face_label(state.face_to)}  \n"
            f"_next click sets {target}_"
        )
        if view["objects"]:
            colour_faces()
        draw_table()
        draw_result()

    def draw_table() -> None:
        table_box.clear()
        with table_box:
            ui.label("3. The chain").classes("font-medium")
            if state.error:
                ui.label(state.error).classes("text-negative text-sm")
                return
            if state.built is None:
                ui.label("Choose two faces to see the chain.").classes("text-sm")
                return
            ui.label(
                " → ".join(state.built.chain.path)
                + f"   (nominal {state.built.chain.nominal:g} mm)"
            ).classes("text-sm")
            for note in state.built.notes:
                ui.label("ℹ " + note).classes("text-xs text-info")
            with ui.grid(columns=7).classes("w-full gap-x-3 gap-y-1 items-center text-sm"):
                for head in (
                    "Part",
                    "Faces",
                    "Nominal",
                    "Upper",
                    "Lower",
                    "Sign",
                    "Tolerance from",
                ):
                    ui.label(head).classes("font-medium")
                for row in state.rows():
                    bg = {
                        "missing": "bg-yellow-2",
                        "user": "bg-blue-1",
                        "table": "bg-yellow-1",
                    }.get(row.kind, "")
                    ui.label(row.part).classes(bg)
                    ui.label(row.faces)
                    ui.label(f"{row.nominal:g}")
                    if row.key is not None:
                        up = (
                            ui.number(
                                value=row.upper if row.kind != "missing" else None, format="%.4g"
                            )
                            .props("dense")
                            .classes("w-24 " + bg)
                        )
                        low = (
                            ui.number(
                                value=row.lower if row.kind != "missing" else None, format="%.4g"
                            )
                            .props("dense")
                            .classes("w-24 " + bg)
                        )

                        def commit(_e: Any, key=row.key, up=up, low=low) -> None:
                            if up.value is None or low.value is None:
                                return
                            state.set_override(key, float(up.value), float(low.value))
                            redraw()

                        up.on("blur", commit)
                        low.on("blur", commit)
                    else:
                        ui.label(f"{row.upper:+g}")
                        ui.label(f"{row.lower:+g}")
                    ui.label(f"{row.sensitivity:+g}" if row.kind != "gdt" else "±")
                    ui.label(short_source(row)).classes("text-xs").tooltip(row.source)
            missing = len(state.built.needs_value)
            with ui.row().classes("items-center mt-2"):
                ui.button("Analyse", on_click=lambda: analyse()).props(
                    "color=primary" + (" disable" if missing else "")
                )
                if missing:
                    ui.label(
                        f"Enter upper and lower for {missing} yellow row(s) first (or pick a general tolerance class)."
                    ).classes("text-sm text-warning")

    async def analyse() -> None:
        try:
            await run.io_bound(state.analyze)
        except CadStackError as exc:
            ui.notify(str(exc), type="negative")
            return
        draw_result()

    def draw_result() -> None:
        result_box.clear()
        if state.result is None:
            result_box.set_visibility(False)
            return
        result_box.set_visibility(True)
        r = state.result
        v = verdict(r)
        with result_box:
            ui.label("4. Result").classes("font-medium")
            ui.label(v.headline).classes(f"text-lg text-{LEVEL_COLOR[v.level]} font-medium")
            for line in v.details:
                ui.label(line).classes("text-sm")
            with ui.row().classes("w-full items-start"):
                with ui.column():
                    ui.label("Biggest contributors (worst case %)").classes("text-sm font-medium")
                    for c in sorted(r.contributors, key=lambda c: -(c.wc_contribution_pct or 0))[
                        :8
                    ]:
                        pct = c.wc_contribution_pct or 0.0
                        with ui.row().classes("items-center no-wrap"):
                            ui.label(c.id).classes("text-xs w-40")
                            ui.linear_progress(value=pct / 100, show_value=False).classes("w-40")
                            ui.label(f"{pct:.1f} %").classes("text-xs")
                from detecttol.report import render_histogram_png

                png = render_histogram_png(r)
                if png:
                    ui.image("data:image/png;base64," + base64.b64encode(png).decode()).classes(
                        "w-96"
                    )
            for w in r.warnings:
                ui.label(f"{w.code}: {w.message}").classes("text-xs opacity-80")
            ui.button(
                "Download report (HTML)",
                on_click=lambda: ui.download.content(
                    state.report_html(),
                    f"{state.cad_file.stem if state.cad_file else 'stack'}_report.html",
                ),
            ).props("outline")

    folder_input.on("keydown.enter", lambda _e: show_folder())
    ui.button("Show folder", on_click=show_folder).props("flat dense").move(
        target_container=folder_input.parent_slot.parent
    )
    show_folder()
    redraw()


def main(host: str = "127.0.0.1", port: int = 8765, show: bool = True) -> None:
    """Start the app (blocks). Local only by default."""
    os.environ.setdefault("MPLBACKEND", "Agg")
    ui.run(
        host=host, port=port, title="detectTOL", show=show, reload=False, show_welcome_message=True
    )
