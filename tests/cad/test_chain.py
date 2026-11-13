"""Phase 6: stacks built from STEP assemblies whose answer is known by construction."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml
from typer.testing import CliRunner

pytest.importorskip("OCC", reason="pythonocc-core is not installed")

from detecttol import analyze
from detecttol.cad.chain import find_contacts
from detecttol.cad.step_reader import read_step
from detecttol.cad.step_stack import build_step_stack, is_step_stack, load_step_stack
from detecttol.cad.synthetic import BoxPart, write_box_assembly
from detecttol.cli.main import app
from detecttol.io import StackInputError, load_stack
from detecttol.report import load_committed_schema
from tests.conftest import EXAMPLES

runner = CliRunner()
STEP_EXAMPLES = EXAMPLES / "step"
SEVEN_SF = {"rel": 1e-6}


def sel(part: str, face: int, centroid: list[float], normal: list[float]) -> dict[str, Any]:
    return {"part": part, "face": face, "centroid": centroid, "normal": normal}


def dim(did: str, a: dict[str, Any], b: dict[str, Any], tol: float) -> dict[str, Any]:
    return {"id": did, "kind": "dimension", "from": a, "to": b, "upper_tol": tol, "lower_tol": -tol}


UP, DOWN = [0, 0, 1], [0, 0, -1]


def towers(tmp_path: Path, *, lid: bool = False, gap: float = 0.0) -> tuple[Path, dict[str, Any]]:
    """BASE 100x30x10 with TOWER_A (25 high) and TOWER_B (25.5, or 25 with a lid).

    ``gap`` lifts tower B off the base by that amount.
    """
    height_b = 25.0 if lid else 25.5
    parts = [
        BoxPart("BASE", (100.0, 30.0, 10.0)),
        BoxPart("TOWER_A", (20.0, 30.0, 25.0), origin=(10.0, 0.0, 10.0)),
        BoxPart("TOWER_B", (20.0, 30.0, height_b), origin=(60.0, 0.0, 10.0 + gap)),
    ]
    if lid:
        parts.append(BoxPart("LID", (100.0, 30.0, 5.0), origin=(0.0, 0.0, 35.0)))
    write_box_assembly(tmp_path / "towers.step", parts)
    top_b = 10.0 + gap + height_b
    doc = {
        "schema_version": 3,
        "units": "mm",
        "name": "towers",
        "step_file": "towers.step",
        "requirement": {
            "description": "height of tower B above tower A",
            "from": sel("TOWER_A", 5, [20.0, 15.0, 35.0], UP),
            "to": sel("TOWER_B", 5, [70.0, 15.0, top_b], UP),
            "lsl": 0.4,
            "usl": 0.6,
        },
        "annotations": [
            dim(
                "tower_a_height",
                sel("TOWER_A", 4, [20.0, 15.0, 10.0], DOWN),
                sel("TOWER_A", 5, [20.0, 15.0, 35.0], UP),
                0.05,
            ),
            dim(
                "tower_b_height",
                sel("TOWER_B", 4, [70.0, 15.0, 10.0 + gap], DOWN),
                sel("TOWER_B", 5, [70.0, 15.0, top_b], UP),
                0.05,
            ),
        ],
    }
    return tmp_path, doc


def errors(doc: dict[str, Any], base: Path) -> list[str]:
    with pytest.raises(StackInputError) as info:
        build_step_stack(doc, base)
    return info.value.errors


# ------------------------------------------------------------------ golden case A


def test_golden_case_a_from_step_is_identical_to_the_yaml_version() -> None:
    """root.md Phase 6: "Golden case A rebuilt as an actual STEP assembly must give
    identical results to the YAML version."

    Housing with a slot (floor z = 10, ceiling z = 60: depth 50) and three plates of
    16.6. Chain from the top of PLATE_3 to the slot ceiling along +z:
        PLATE_3 top -> bottom (-16.6), PLATE_2 (-16.6), PLATE_1 (-16.6),
        HOUSING floor -> ceiling (+50)
    i.e. exactly the contributors of the YAML file (+1, -1, -1, -1), nominal 0.2.
    The whole result, Monte Carlo included, must equal the YAML result; only the
    description differs (it records the chain).
    """
    built = load_step_stack(STEP_EXAMPLES / "plate_stack.yaml")
    assert built.chain.path == ("PLATE_3", "PLATE_2", "PLATE_1", "HOUSING")
    assert built.chain.nominal == pytest.approx(0.2, abs=1e-9)
    assert built.chain.direction == pytest.approx((0.0, 0.0, 1.0), abs=1e-12)
    assert [(c.id, c.nominal, c.sensitivity) for c in built.stack.contributors] == [
        ("slot_depth", 50.0, 1.0),
        ("plate_1", 16.6, -1.0),
        ("plate_2", 16.6, -1.0),
        ("plate_3", 16.6, -1.0),
    ]
    assert [(link.part, link.signed_length) for link in built.chain.links] == [
        ("HOUSING", 50.0),
        ("PLATE_1", -16.6),
        ("PLATE_2", -16.6),
        ("PLATE_3", -16.6),
    ]
    from_step = analyze(built.stack)
    from_yaml = analyze(load_stack(EXAMPLES / "golden_case_a.yaml"))
    assert "from STEP: chain PLATE_3 -> PLATE_2 -> PLATE_1 -> HOUSING" in from_step.description
    assert from_step.model_copy(update={"description": from_yaml.description}) == from_yaml
    assert from_step.rss is not None
    assert from_step.rss.p_fail == pytest.approx(2.872356e-6, **SEVEN_SF)


def test_contacts_of_the_plate_stack() -> None:
    """Contacts by construction: slot floor / PLATE_1, PLATE_1 / PLATE_2,
    PLATE_2 / PLATE_3 (normal +-z), and each plate against both slot walls
    (normal +-x): 3 + 6 = 9 planar contacts, no non-planar one. PLATE_3 does not
    touch the ceiling (gap 0.2)."""
    model = read_step(STEP_EXAMPLES / "plate_stack.step")
    contacts, unsupported = find_contacts(model)
    names = [p.name for p in model.parts]
    vertical = sorted(
        (names[c.part_a], names[c.part_b]) for c in contacts if abs(c.normal[2]) > 0.5
    )
    assert vertical == [("HOUSING", "PLATE_1"), ("PLATE_1", "PLATE_2"), ("PLATE_2", "PLATE_3")]
    assert len(contacts) == 9 and unsupported == []


# ------------------------------------------------------------------ other assemblies


def test_stacked_blocks_height() -> None:
    """Base 10 +/-0.1 and plate 16.6 +/-0.05, measured upwards from the base bottom.

    mean = 26.6;  W = 0.15 -> [26.45, 26.75];  sigma = sqrt(0.0125)/3 = 0.03726780
    Both sensitivities +1. LSL 26.4 / USL 26.8 -> Cpk = 0.2/0.1118034 = 1.788854.
    """
    built = load_step_stack(STEP_EXAMPLES / "stacked_blocks.yaml")
    assert built.chain.path == ("BASE", "PLATE")
    r = analyze(built.stack)
    assert r.worst_case is not None and r.rss is not None
    assert r.mean == pytest.approx(26.6, abs=1e-9)
    assert r.worst_case.half_range == pytest.approx(0.15, abs=1e-12)
    assert r.rss.sigma == pytest.approx(0.03726780, **SEVEN_SF)
    assert r.rss.cpk == pytest.approx(1.788854, **SEVEN_SF)
    assert [c.sensitivity for c in r.contributors] == [1.0, 1.0]


def test_step_height_between_two_towers(tmp_path: Path) -> None:
    """Tower B (25.5) minus tower A (25) on a common base.

    Chain: down tower A (-25), through the base without a dimension (in and out
    by the same face), up tower B (+25.5).
    mean = 0.5;  W = 0.1 -> [0.4, 0.6] (lands on both limits: meets the spec);
    sigma = sqrt(2 * 0.05^2)/3 = 0.02357023;  Cpk = 0.1/0.07071068 = 1.414214.
    """
    base, doc = towers(tmp_path)
    built = build_step_stack(doc, base)
    assert built.chain.path == ("TOWER_A", "BASE", "TOWER_B")
    assert [(c.id, c.nominal, c.sensitivity) for c in built.stack.contributors] == [
        ("tower_a_height", 25.0, -1.0),
        ("tower_b_height", 25.5, 1.0),
    ]
    r = analyze(built.stack)
    assert r.worst_case is not None and r.rss is not None
    assert r.mean == pytest.approx(0.5, abs=1e-9)
    assert r.worst_case.half_range == pytest.approx(0.1, abs=1e-12)
    assert r.worst_case.meets_spec is True
    assert r.rss.sigma == pytest.approx(0.02357023, **SEVEN_SF)
    assert r.rss.cpk == pytest.approx(1.414214, **SEVEN_SF)
    # The committed example is the same assembly and gives the same stack.
    example = load_step_stack(STEP_EXAMPLES / "step_height.yaml")
    assert example.stack.contributors == built.stack.contributors


def test_reversed_requirement_changes_the_sign(tmp_path: Path) -> None:
    """Swapping from/to gives Y = -0.5 with every sensitivity flipped."""
    base, doc = towers(tmp_path)
    req = doc["requirement"]
    req["from"], req["to"] = req["to"], req["from"]
    req["lsl"], req["usl"] = -0.6, -0.4
    built = build_step_stack(doc, base)
    assert built.chain.nominal == pytest.approx(-0.5, abs=1e-9)
    assert [c.sensitivity for c in built.stack.contributors] == [1.0, -1.0]
    assert analyze(built.stack).mean == pytest.approx(-0.5, abs=1e-9)


# ------------------------------------------------------------------ reported problems


def test_no_path_is_reported(tmp_path: Path) -> None:
    """Tower B floats 1 mm above the base: no contact, so no chain."""
    base, doc = towers(tmp_path, gap=1.0)
    (msg,) = errors(doc, base)
    assert msg.startswith("chain: no path of planar contacts from 'TOWER_A' to 'TOWER_B'")
    assert "'TOWER_A' touches ['BASE']" in msg


def test_contact_tolerance_is_a_parameter(tmp_path: Path) -> None:
    """A 1e-4 mm gap is no contact at the default 1e-6 mm but is one at 1e-3 mm.
    The annotation fingerprints still match (they allow 1e-6 mm on the centroid
    only because the selectors here carry the lifted coordinates)."""
    base, doc = towers(tmp_path, gap=1e-4)
    assert errors(doc, base)[0].startswith("chain: no path")
    doc["contact_tolerance"] = 1e-3
    built = build_step_stack(doc, base)
    assert built.chain.path == ("TOWER_A", "BASE", "TOWER_B")
    assert built.chain.nominal == pytest.approx(0.5001, abs=1e-9)


def test_multiple_paths_are_listed_not_chosen(tmp_path: Path) -> None:
    """A lid resting on two towers of equal height: from the base bottom to the lid
    top there are two chains (via tower A and via tower B). The tool must list
    them and refuse to pick one."""
    base, doc = towers(tmp_path, lid=True)
    doc["requirement"] = {
        "from": sel("BASE", 4, [50.0, 15.0, 0.0], DOWN),
        "to": sel("LID", 5, [50.0, 15.0, 40.0], UP),
        "direction": [0, 0, 1],
        "usl": 40.5,
    }
    (msg,) = errors(doc, base)
    assert msg.startswith("chain: 2 possible paths from 'BASE' to 'LID'")
    assert "TOWER_A" in msg and "TOWER_B" in msg and "over-constrained" in msg


def test_non_planar_contacts_are_reported(tmp_path: Path) -> None:
    """A cylindrical post (r = 5, h = 20) stands on a base and touches a wall
    tangentially. Post bottom / base top is a planar contact and is used; the
    cylinder's side against the wall is non-planar: reported, not used.
    Height base (10) + post (20) = 30."""
    write_box_assembly(
        tmp_path / "post.step",
        [
            BoxPart("BASE", (60.0, 30.0, 10.0)),
            BoxPart("POST", (10.0, 10.0, 20.0), origin=(10.0, 10.0, 10.0), cylinder_radius=5.0),
            BoxPart("WALL", (10.0, 30.0, 20.0), origin=(20.0, 0.0, 10.0)),
        ],
    )
    model = read_step(tmp_path / "post.step")
    post = model.part("POST")
    top = next(f for f in post.faces if f.normal and f.normal[2] > 0.5)
    bottom = next(f for f in post.faces if f.normal and f.normal[2] < -0.5)
    _contacts, unsupported = find_contacts(model)
    assert any("POST" in u and "cylinder" in u and "WALL" in u for u in unsupported)
    doc = {
        "schema_version": 3,
        "units": "mm",
        "name": "post",
        "step_file": "post.step",
        "requirement": {
            "from": sel("BASE", 4, [30.0, 15.0, 0.0], DOWN),
            "to": sel("POST", top.index, list(top.centroid), UP),
            "direction": [0, 0, 1],
            "usl": 30.3,
        },
        "annotations": [
            dim(
                "base",
                sel("BASE", 4, [30.0, 15.0, 0.0], DOWN),
                sel("BASE", 5, [30.0, 15.0, 10.0], UP),
                0.1,
            ),
            dim(
                "post",
                sel("POST", bottom.index, list(bottom.centroid), DOWN),
                sel("POST", top.index, list(top.centroid), UP),
                0.1,
            ),
        ],
    }
    built = build_step_stack(doc, tmp_path)
    assert built.chain.path == ("BASE", "POST")
    assert built.chain.nominal == pytest.approx(30.0, abs=1e-9)
    assert built.chain.unsupported_contacts
    assert "non-planar contact(s) ignored" in built.stack.requirement.description


def test_missing_tolerance_names_the_dimension(tmp_path: Path) -> None:
    base, doc = towers(tmp_path)
    del doc["annotations"][1]
    (msg,) = errors(doc, base)
    assert msg.startswith("chain: no tolerance for the dimension of 'TOWER_B' between faces")
    assert "nominal 25.5 mm" in msg


@pytest.mark.parametrize(
    ("mutate", "prefix"),
    [
        (
            lambda d: d["requirement"].update(to=sel("TOWER_B", 1, [80.0, 15.0, 22.75], [1, 0, 0])),
            "chain: requirement.to: the face is not perpendicular",
        ),
        (lambda d: d["requirement"].update(direction=[0, 0, 0]), "chain: direction:"),
        (
            lambda d: d["requirement"].update(to=d["requirement"]["from"]),
            "chain: the two faces are in the same plane",
        ),
        (lambda d: d["requirement"]["to"].update(part="TOWER_C"), "requirement.to.part:"),
        (
            lambda d: d["requirement"]["to"].update(centroid=[70.0, 15.0, 36.0]),
            "requirement.to.centroid:",
        ),
        (lambda d: d["annotations"][0]["from"].update(face=99), "annotations[0].from.face:"),
        (lambda d: d["requirement"].update(lsl=None, usl=None), "requirement:"),
        (lambda d: d.update(step_file="missing.step"), "step_file:"),
        (lambda d: d.update(units="inch"), "units:"),
        (lambda d: d.update(schema_version=1), "schema_version:"),
        (lambda d: d.update(contact_tolerance=0), "contact_tolerance:"),
        (lambda d: d.update(annotations=[]), "annotations:"),
        (lambda d: d["requirement"].pop("from"), "requirement.from:"),
    ],
)
def test_bad_input_names_the_field(tmp_path: Path, mutate: Any, prefix: str) -> None:
    base, doc = towers(tmp_path)
    doc = copy.deepcopy(doc)
    mutate(doc)
    msgs = errors(doc, base)
    assert any(m.startswith(prefix) for m in msgs), msgs


def test_file_level_errors(tmp_path: Path) -> None:
    assert is_step_stack({"step_file": "x"}) and not is_step_stack({"contributors": []})
    with pytest.raises(StackInputError, match="file not found"):
        load_step_stack(tmp_path / "missing.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("a: [1\n", encoding="utf-8")
    with pytest.raises(StackInputError, match="not valid YAML"):
        load_step_stack(bad)
    with pytest.raises(StackInputError, match="mapping"):
        build_step_stack([1], tmp_path)


# ------------------------------------------------------------------ CLI, end to end


@pytest.mark.parametrize(
    ("example", "mean"),
    [("plate_stack", 0.2), ("stacked_blocks", 26.6), ("step_height", 0.5)],
)
def test_cli_step_to_report_end_to_end(example: str, mean: float, tmp_path: Path) -> None:
    """root.md Phase 6 gate: STEP -> report for three synthetic assemblies."""
    path = str(STEP_EXAMPLES / f"{example}.yaml")
    js = runner.invoke(app, ["analyze", path, "--format", "json"])
    assert js.exit_code == 0, js.output
    document = json.loads(js.stdout)
    jsonschema.validate(document, load_committed_schema(1), cls=jsonschema.Draft202012Validator)
    assert document["result"]["mean"] == pytest.approx(mean, abs=1e-9)
    assert "from STEP: chain" in document["result"]["description"]
    for fmt in ("md", "html"):
        out = runner.invoke(app, ["analyze", path, "--format", fmt, "--out", str(tmp_path)])
        assert out.exit_code == 0, out.output
    assert len(list(tmp_path.glob("*.html"))) == 1 and len(list(tmp_path.glob("*.png"))) == 1


def test_cli_reports_chain_errors(tmp_path: Path) -> None:
    base, doc = towers(tmp_path, gap=1.0)
    path = base / "towers.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    result = runner.invoke(app, ["analyze", str(path)])
    assert result.exit_code == 2
    assert "error: chain: no path of planar contacts" in result.stderr
