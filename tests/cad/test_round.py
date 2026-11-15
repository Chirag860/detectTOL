"""Round features: grouping half faces, fit check, pin float, position in a chain.

Golden values are derived by hand in each docstring.

Synthetic pin assembly (``pin_model``), all lengths mm:
  Plate_1 60 x 20 x 10 at z = 0..10, hole dia 6.2 at (30, 10);
  Plate_2 the same at z = 10..20;
  Pin dia 6, z = 0..20, axis at (30, 10).
Requirement: Plate_1's x = 0 face (datum B) -> Plate_2's x = 0 face, along +x; nominal 0.
Tolerances: holes dia 6.2 +/-0.05, pin dia 6 +0/-0.02, positions dia 0.1 to B.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("OCC", reason="pythonocc-core is not installed")

from detecttol.cad.cad_stack import CadInput, CadStackError, build_cad_stack, build_fit_check
from detecttol.cad.chain import ChainError, build_chain, find_coaxial_contacts
from detecttol.cad.pmi import FaceRef
from detecttol.cad.round import (
    ResolvedDiameter,
    ResolvedPosition,
    RoundFeatureError,
    classify_fit,
    find_round,
    fit_stack,
    float_contributor,
    position_dimension,
    round_features,
)
from detecttol.cad.step_reader import StepModel, read_step
from detecttol.cad.synthetic import BoxPart, write_box_assembly
from detecttol.core.analyze import analyze
from detecttol.gdt.models import DatumReferenceFrame, Position
from tests.conftest import EXAMPLES

EXACT = {"rel": 1e-12, "abs": 1e-12}
FITS = EXAMPLES / "solidworks" / "fits"


def dia(
    cid: str, part: str, face: int, nominal: float, upper: float, lower: float, internal: bool
) -> ResolvedDiameter:
    return ResolvedDiameter(cid, part, face, nominal, upper, lower, internal)


@pytest.fixture(scope="module")
def pin_model(tmp_path_factory: pytest.TempPathFactory) -> StepModel:
    path = tmp_path_factory.mktemp("pin") / "pin.step"
    write_box_assembly(
        path,
        [
            BoxPart("Plate_1", (60, 20, 10), holes=((30, 10, 6.2),)),
            BoxPart("Plate_2", (60, 20, 10), origin=(0, 0, 10), holes=((30, 10, 6.2),)),
            BoxPart("Pin", (6, 6, 20), origin=(27, 7, 0), cylinder_radius=3.0),
        ],
    )
    return read_step(path)


def _face(model: StepModel, part: str, normal: tuple[float, float, float]) -> int:
    (index,) = [f.index for f in model.part(part).faces if f.normal == normal]
    return index


def _pin_inputs(model: StepModel, condition: str = "RFS") -> dict:  # type: ignore[type-arg]
    holes = {p: round_features(model.part(p))[0] for p in ("Plate_1", "Plate_2")}
    pin = round_features(model.part("Pin"))[0]
    b = {p: _face(model, p, (-1.0, 0.0, 0.0)) for p in holes}
    return {
        "b": b,
        "diameters": [dia(f"{p}:D", p, holes[p].face, 6.2, 0.05, -0.05, True) for p in holes]
        + [dia("Pin:D", "Pin", pin.face, 6.0, 0.0, -0.02, False)],
        "positions": [
            ResolvedPosition(
                f"{p}:Pos",
                p,
                holes[p].face,
                0.1,
                condition,  # type: ignore[arg-type]
                (FaceRef(p, b[p]),),
            )
            for p in holes
        ],
    }


# --------------------------------------------------------------------------- #
# geometry
# --------------------------------------------------------------------------- #


def test_holes_and_pins_are_recognised(pin_model: StepModel) -> None:
    (h1,) = round_features(pin_model.part("Plate_1"))
    (pin,) = round_features(pin_model.part("Pin"))
    assert (h1.internal, h1.radius) == (True, pytest.approx(3.1, **EXACT))
    assert (pin.internal, pin.radius) == (False, pytest.approx(3.0, **EXACT))
    assert h1.axis_point[:2] == pytest.approx((30.0, 10.0), **EXACT)
    assert abs(h1.axis[2]) == pytest.approx(1.0, **EXACT)


def test_solidworks_half_faces_are_grouped() -> None:
    """SolidWorks' STEP export splits each cylinder into two half faces (phase-dia-1)."""
    model = read_step(FITS / "Pin_Test_geometry_AP214.step")
    for part, internal, diameter in (
        ("Plate_1", True, 6.2),
        ("Plate_2", True, 6.2),
        ("Pin", False, 6.0),
    ):
        (feature,) = round_features(model.part(part))
        assert len(feature.faces) == 2
        assert (feature.internal, feature.diameter) == (internal, pytest.approx(diameter, abs=1e-9))
        assert find_round(model, FaceRef(part, feature.faces[1])) == feature
    contacts = find_coaxial_contacts(model)
    assert sorted(
        (model.parts[c.part_hole].name, model.parts[c.part_pin].name) for c in contacts
    ) == [("Plate_1", "Pin"), ("Plate_2", "Pin")]


def test_axial_ranges_of_bore_and_shaft() -> None:
    """Bore and shaft share axis and radius but stay two features (one per part), each
    with its own length along the axis: 20 (housing) and 40 (shaft)."""
    model = read_step(FITS / "Fit_Test_geometry_AP214.step")
    (bore,) = round_features(model.part("Housing"))
    (shaft,) = round_features(model.part("Shaft"))
    assert bore.axial_range[1] - bore.axial_range[0] == pytest.approx(20.0, abs=1e-9)
    assert shaft.axial_range[1] - shaft.axial_range[0] == pytest.approx(40.0, abs=1e-9)


def test_find_round_refuses_a_plane(pin_model: StepModel) -> None:
    with pytest.raises(RoundFeatureError, match="not a cylindrical face"):
        find_round(pin_model, FaceRef("Plate_1", _face(pin_model, "Plate_1", (-1.0, 0.0, 0.0))))


# --------------------------------------------------------------------------- #
# fit check
# --------------------------------------------------------------------------- #


def test_fit_h7_g6_dia_20() -> None:
    """H7: 20 +0.021/0, g6: 20 -0.007/-0.020 (IS 919 / ISO 286, as entered here).

    Clearance limits: 20.000 - 19.993 = 0.007 and 20.021 - 19.980 = 0.041 -> clearance fit.
    Mean 20.0105 - 19.9865 = 0.024; sigma = sqrt(0.0035^2 + 0.0065^2/9) = 0.0041164... .
    """
    hole = dia("H", "Housing", 0, 20.0, 0.021, 0.0, True)
    shaft = dia("S", "Shaft", 0, 20.0, -0.007, -0.020, False)
    limits = classify_fit(hole, shaft)
    assert (limits.kind, limits.min_clearance, limits.max_clearance) == (
        "clearance",
        pytest.approx(0.007, **EXACT),
        pytest.approx(0.041, **EXACT),
    )
    result = analyze(fit_stack(hole, shaft))
    assert result.worst_case.lower == pytest.approx(0.007, abs=1e-12)
    assert result.worst_case.upper == pytest.approx(0.041, abs=1e-12)
    assert result.rss.sigma == pytest.approx(math.sqrt(0.0035**2 + (0.0065 / 3) ** 2), rel=1e-12)


@pytest.mark.parametrize(
    ("shaft", "kind", "lo", "hi"),
    [
        # H7 25: [25.000, 25.021]; k6 25: [25.002, 25.015] -> -0.015 .. 0.019
        ((0.015, 0.002), "transition", -0.015, 0.019),
        # s6 25: [25.035, 25.048] -> -0.048 .. -0.014
        ((0.048, 0.035), "interference", -0.048, -0.014),
    ],
)
def test_fit_kinds(shaft: tuple[float, float], kind: str, lo: float, hi: float) -> None:
    hole = dia("H", "A", 0, 25.0, 0.021, 0.0, True)
    limits = classify_fit(hole, dia("S", "B", 0, 25.0, shaft[0], shaft[1], False))
    assert (limits.kind, limits.min_clearance, limits.max_clearance) == (
        kind,
        pytest.approx(lo, **EXACT),
        pytest.approx(hi, **EXACT),
    )


def test_fit_stack_refuses_swapped_features() -> None:
    hole = dia("H", "A", 0, 20.0, 0.021, 0.0, True)
    shaft = dia("S", "B", 0, 20.0, -0.007, -0.02, False)
    with pytest.raises(RoundFeatureError, match="not a hole"):
        fit_stack(shaft, shaft)
    with pytest.raises(RoundFeatureError, match="not a pin"):
        fit_stack(hole, hole)


# --------------------------------------------------------------------------- #
# pin float and position
# --------------------------------------------------------------------------- #


def test_float_is_half_the_largest_clearance() -> None:
    """(6.25 - 5.98)/2 = 0.135, uniform (A39)."""
    c = float_contributor(
        dia("H", "P", 0, 6.2, 0.05, -0.05, True), dia("p", "Q", 0, 6.0, 0.0, -0.02, False)
    )
    assert (c.nominal, c.upper_tol, c.lower_tol, c.distribution) == (
        0.0,
        pytest.approx(0.135, **EXACT),
        pytest.approx(-0.135, **EXACT),
        "uniform",
    )


def test_float_refuses_a_pin_that_never_fits() -> None:
    with pytest.raises(RoundFeatureError, match="never fits"):
        float_contributor(
            dia("H", "P", 0, 6.0, 0.0, -0.01, True), dia("p", "Q", 0, 6.0, 0.03, 0.02, False)
        )


def test_position_dimension_matches_the_gdt_position() -> None:
    """RFS: +/- T/2 = 0.05. MMC on a dia 6.2 +/-0.05 hole: +/- (0.1 + 0.1)/2 = 0.1, with the
    sigma of Position.bonus_sigma (same numbers as detecttol.gdt)."""
    datum = FaceRef("P", 3)
    hole = dia("P:D", "P", 0, 6.2, 0.05, -0.05, True)
    rfs = position_dimension(
        ResolvedPosition("P:Pos", "P", 0, 0.1, "RFS", (datum,)), datum, 30.0, (1, 0, 0), None
    )
    assert (rfs.nominal, rfs.upper_tol, rfs.lower_tol, rfs.cp) == (30.0, 0.05, -0.05, 1.0)
    mmc = position_dimension(
        ResolvedPosition("P:Pos", "P", 0, 0.1, "MMC", (datum,)), datum, -30.0, (-1, 0, 0), hole
    )
    ref = Position(
        id="x",
        tolerance=0.1,
        datums=DatumReferenceFrame(primary="A"),
        material_condition="MMC",
        feature="hole",
        size_contributor="P:D",
    ).to_contributor(hole.to_contributor(0.0))
    assert (mmc.nominal, mmc.upper_tol, mmc.lower_tol) == (
        30.0,
        pytest.approx(0.1, **EXACT),
        pytest.approx(-0.1, **EXACT),
    )
    assert mmc.cp == pytest.approx(ref.cp, **EXACT)
    with pytest.raises(RoundFeatureError, match="needs the hole's toleranced diameter"):
        position_dimension(
            ResolvedPosition("P:Pos", "P", 0, 0.1, "MMC", (datum,)), datum, 30.0, (1, 0, 0), None
        )


# --------------------------------------------------------------------------- #
# pin in holes inside a chain
# --------------------------------------------------------------------------- #


def test_pin_chain_rfs(pin_model: StepModel) -> None:
    """B1 -> hole 1 axis: +30 (+/-0.05); float pin in hole 1 (+/-0.135); float in hole 2;
    hole 2 axis -> B2: -30 (+/-0.05). Y = 0, worst case +/-(0.05 + 0.135 + 0.135 + 0.05)
    = +/-0.37; sigma = sqrt(2 (0.05/3)^2 + 2 (0.135/sqrt 3)^2) = 0.1127188..."""
    inp = _pin_inputs(pin_model)
    chain = build_chain(
        pin_model,
        FaceRef("Plate_1", inp["b"]["Plate_1"]),
        FaceRef("Plate_2", inp["b"]["Plate_2"]),
        [],
        direction=(1.0, 0.0, 0.0),
        diameters=inp["diameters"],
        positions=inp["positions"],
    )
    assert chain.path == ("Plate_1", "Pin", "Plate_2")
    assert chain.nominal == 0.0
    got = {
        link.contributor.id: (
            link.contributor.nominal * link.contributor.sensitivity,
            link.contributor.upper_tol,
        )
        for link in chain.links
    }
    assert got == {
        "Plate_1:Pos": (30.0, 0.05),
        "Plate_2:Pos": (-30.0, 0.05),
        "float Pin:D in Plate_1:D": (0.0, pytest.approx(0.135, **EXACT)),
        "float Pin:D in Plate_2:D": (0.0, pytest.approx(0.135, **EXACT)),
    }
    cad = CadInput(
        pin_model, (), (), (), "synthetic", tuple(inp["diameters"]), tuple(inp["positions"])
    )
    built = build_cad_stack(
        cad,
        FaceRef("Plate_1", inp["b"]["Plate_1"]),
        FaceRef("Plate_2", inp["b"]["Plate_2"]),
        lsl=-0.5,
        usl=0.5,
    )
    result = built.analyze()
    assert (result.worst_case.lower, result.worst_case.upper) == (
        pytest.approx(-0.37, abs=1e-12),
        pytest.approx(0.37, abs=1e-12),
    )
    sigma = math.sqrt(2 * (0.05 / 3) ** 2 + 2 * (0.135 / math.sqrt(3)) ** 2)
    assert result.rss.sigma == pytest.approx(sigma, rel=1e-12)


def test_pin_chain_mmc_bonus(pin_model: StepModel) -> None:
    """At MMC each position may grow by the hole's size range 0.1: +/-0.1 each, so the
    worst case is +/-(0.1 + 0.135 + 0.135 + 0.1) = +/-0.47."""
    inp = _pin_inputs(pin_model, "MMC")
    cad = CadInput(
        pin_model, (), (), (), "synthetic", tuple(inp["diameters"]), tuple(inp["positions"])
    )
    built = build_cad_stack(
        cad,
        FaceRef("Plate_1", inp["b"]["Plate_1"]),
        FaceRef("Plate_2", inp["b"]["Plate_2"]),
        lsl=-0.5,
        usl=0.5,
    )
    result = built.analyze()
    assert result.worst_case.upper == pytest.approx(0.47, abs=1e-12)


def test_missing_pin_diameter_is_named_or_filled(pin_model: StepModel) -> None:
    """Without the pin's diameter: refused (names the pin); with general class m a dia 6
    gets +/-0.1 (IS 2102-m, over 3 up to 6), so the float is (6.25 - 5.9)/2 = 0.175."""
    inp = _pin_inputs(pin_model)
    dias = tuple(d for d in inp["diameters"] if d.part != "Pin")
    cad = CadInput(pin_model, (), (), (), "synthetic", dias, tuple(inp["positions"]))
    a, b = FaceRef("Plate_1", inp["b"]["Plate_1"]), FaceRef("Plate_2", inp["b"]["Plate_2"])
    with pytest.raises(CadStackError, match=r"diameter of Pin:\d+ \(pin dia 6\)"):
        build_cad_stack(cad, a, b, lsl=-1.0, usl=1.0)
    built = build_cad_stack(cad, a, b, lsl=-1.0, usl=1.0, general_class="m")
    floats = [
        link.contributor.upper_tol
        for link in built.chain.links
        if link.contributor.id.startswith("float")
    ]
    assert floats == [pytest.approx(0.175, **EXACT)] * 2
    placeholder = build_cad_stack(cad, a, b, lsl=-1.0, usl=1.0, placeholder_missing=True)
    (missing,) = placeholder.needs_value
    assert (missing.part, missing.from_face == missing.to_face, missing.nominal) == (
        "Pin",
        True,
        6.0,
    )


def test_pin_along_the_axis_carries_nothing(pin_model: StepModel) -> None:
    """Along z the pin can slide: the coaxial contact does not carry the stack, and the
    plates touch each other directly (Plate_1 top on Plate_2 bottom)."""
    top = _face(pin_model, "Plate_1", (0.0, 0.0, 1.0))
    p2_top = _face(pin_model, "Plate_2", (0.0, 0.0, 1.0))
    with pytest.raises(ChainError, match="no tolerance"):
        build_chain(pin_model, FaceRef("Plate_1", top), FaceRef("Plate_2", p2_top), [])


def test_fit_check_from_cad_input() -> None:
    model = read_step(FITS / "Fit_Test_geometry_AP214.step")
    (bore,) = round_features(model.part("Housing"))
    (shaft,) = round_features(model.part("Shaft"))
    cad = CadInput(
        model,
        (),
        (),
        (),
        "test",
        (
            dia("Housing:D", "Housing", bore.face, 20.0, 0.021, 0.0, True),
            dia("Shaft:D", "Shaft", shaft.face, 20.0, -0.007, -0.020, False),
        ),
    )
    check = build_fit_check(cad, FaceRef("Housing", bore.faces[1]), FaceRef("Shaft", shaft.face))
    assert (check.limits.kind, check.limits.min_clearance) == (
        "clearance",
        pytest.approx(0.007, **EXACT),
    )
    with pytest.raises(CadStackError, match="is not a hole"):
        build_fit_check(cad, FaceRef("Shaft", shaft.face), FaceRef("Shaft", shaft.face))
    bare = CadInput(model, (), (), (), "test")
    with pytest.raises(CadStackError, match="no tolerance for the diameter"):
        build_fit_check(bare, FaceRef("Housing", bore.face), FaceRef("Shaft", shaft.face))
    general = build_fit_check(
        bare, FaceRef("Housing", bore.face), FaceRef("Shaft", shaft.face), general_class="m"
    )
    # IS 2102-m over 6 up to 30: +/-0.2 -> clearance -0.4 .. 0.4: transition
    assert (general.limits.kind, general.limits.max_clearance) == (
        "transition",
        pytest.approx(0.4, **EXACT),
    )


def test_cli_faces_lists_round_features_and_fit_cad(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Housing 40 x 40 x 20 with a dia 20 bore at (20, 20); shaft dia 20 in it. Without CAD
    tolerances, --general m gives both +/-0.2 (IS 2102-m, over 6 up to 30): clearance
    -0.4 .. 0.4, a transition fit."""
    from typer.testing import CliRunner

    from detecttol.cli.main import app

    path = tmp_path / "fit.step"
    write_box_assembly(
        path,
        [
            BoxPart("Housing", (40, 40, 20), holes=((20, 20, 20),)),
            BoxPart("Shaft", (20, 20, 40), origin=(10, 10, 0), cylinder_radius=10.0),
        ],
    )
    runner = CliRunner()
    listed = runner.invoke(app, ["faces", str(path)])
    assert listed.exit_code == 0, listed.output
    assert "round:" in listed.output
    assert (
        'part: "Housing", face: ' in listed.output and "kind: hole, diameter: 20" in listed.output
    )
    model = read_step(path)
    (bore,) = round_features(model.part("Housing"))
    (shaft,) = round_features(model.part("Shaft"))
    args = [
        "fit-cad",
        str(path),
        "--hole",
        f"Housing:{bore.face}",
        "--shaft",
        f"Shaft:{shaft.face}",
    ]
    refused = runner.invoke(app, args)
    assert refused.exit_code == 2 and "no tolerance for the diameter" in refused.output
    out = runner.invoke(app, [*args, "--general", "m", "--samples", "2000"])
    assert out.exit_code == 0, out.output
    assert "fit: transition fit; clearance from -0.4 to 0.4 mm" in out.output
    assert "Range: [-0.4, 0.4]" in out.output


# --------------------------------------------------------------------------- #
# reviewer findings (2026-11-14)
# --------------------------------------------------------------------------- #


def test_half_faces_out_of_order_are_merged() -> None:
    """Three faces of one bore listed as z 0-10, 20-30, 10-20 form one feature."""
    from detecttol.cad.step_reader import CylinderInfo, FaceInfo, PartInstance

    def face(i: int, z0: float, z1: float) -> FaceInfo:
        c = CylinderInfo((5.0, 5.0, 0.0), (0.0, 0.0, 1.0), 2.0, True)
        return FaceInfo(i, "cylinder", 1.0, (5.0, 5.0, (z0 + z1) / 2), None,
                        (3.0, 3.0, z0), (7.0, 7.0, z1), c)  # fmt: skip

    part = PartInstance(
        "P", "P", ("P",), (0.0, 0.0, 0.0), ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
        (face(0, 0, 10), face(1, 20, 30), face(2, 10, 20)),
    )  # fmt: skip
    (feature,) = round_features(part)
    assert feature.faces == (0, 1, 2)
    assert feature.axial_range == (0.0, 30.0)
    split = PartInstance(part.name, part.instance_name, part.path, part.translation,
                         part.rotation, (face(0, 0, 10), face(1, 20, 30)))  # fmt: skip
    assert [f.faces for f in round_features(split)] == [(0,), (1,)]


def test_a_loose_rod_does_not_locate(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A dia 3 rod through a dia 20 hole is coaxial but far too loose to locate (A42)."""
    path = tmp_path / "loose.step"
    write_box_assembly(path, [
        BoxPart("Plate", (40, 40, 10), holes=((20, 20, 20),)),
        BoxPart("Rod", (3, 3, 30), origin=(18.5, 18.5, -10), cylinder_radius=1.5),
    ])  # fmt: skip
    assert find_coaxial_contacts(read_step(path)) == []


def test_positions_off_the_path_are_ignored(pin_model: StepModel) -> None:
    """A stack inside Plate_1 (datum B -> its x = 60 face) must not need Plate_2's MMC
    position (no diameters given at all) nor fill any diameter."""
    inp = _pin_inputs(pin_model, "MMC")
    cad = CadInput(pin_model, (), (), (), "synthetic", (), tuple(inp["positions"][1:]))
    far = _face(pin_model, "Plate_1", (1.0, 0.0, 0.0))
    built = build_cad_stack(cad, FaceRef("Plate_1", inp["b"]["Plate_1"]), FaceRef("Plate_1", far),
                            lsl=59.0, usl=61.0, general_class="m")  # fmt: skip
    assert built.chain.filled_diameters == ()
    (link,) = built.chain.links
    assert link.contributor.id.startswith("Plate_1:general_")
    assert link.contributor.nominal == pytest.approx(60.0, **EXACT)


def test_a_position_without_a_datum_across_the_stack_is_noted(pin_model: StepModel) -> None:
    """Plate_1's position refers only to datum A (z = 0): it cannot locate the hole along
    x, so the datum -> axis link falls back to the general class and a note says why."""
    inp = _pin_inputs(pin_model)
    a1 = _face(pin_model, "Plate_1", (0.0, 0.0, -1.0))
    p1 = ResolvedPosition("Plate_1:Pos", "Plate_1", inp["positions"][0].face, 0.1, "RFS",
                          (FaceRef("Plate_1", a1),))  # fmt: skip
    cad = CadInput(pin_model, (), (), (), "synthetic", tuple(inp["diameters"]),
                   (p1, inp["positions"][1]))  # fmt: skip
    built = build_cad_stack(cad, FaceRef("Plate_1", inp["b"]["Plate_1"]),
                            FaceRef("Plate_2", inp["b"]["Plate_2"]), lsl=-1.0, usl=1.0,
                            general_class="m")  # fmt: skip
    assert any("Plate_1:Pos: no datum plane" in n for n in built.notes)


def test_pin_in_two_bores_of_one_part_is_one_contact(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Fork 60 x 20 x 30 with a slot z 10..20 across it, so its dia 6.2 hole at (30, 10)
    is two coaxial bores; a 60 x 20 x 10 tongue with the same hole sits in the slot; a
    dia 6 pin goes through all three. Fork datum (x = 0) -> Tongue x = 0: one path, the
    fork's two equal bores give one float, with a note."""
    path = tmp_path / "clevis.step"
    write_box_assembly(path, [
        BoxPart("Fork", (60, 20, 30), slot=(0.0, 60.0, 10.0, 20.0), holes=((30, 10, 6.2),)),
        BoxPart("Tongue", (60, 20, 10), origin=(0, 0, 10), holes=((30, 10, 6.2),)),
        BoxPart("Pin", (6, 6, 30), origin=(27, 7, 0), cylinder_radius=3.0),
    ])  # fmt: skip
    model = read_step(path)
    assert len(round_features(model.part("Fork"))) == 2
    (fork_b,) = [
        f.index
        for f in model.part("Fork").faces
        if f.normal == (-1.0, 0.0, 0.0) and f.centroid[2] < 10.0
    ]  # lower prong
    tongue_b = _face(model, "Tongue", (-1.0, 0.0, 0.0))
    bores = round_features(model.part("Fork"))
    (tongue_hole,) = round_features(model.part("Tongue"))
    positions = (
        ResolvedPosition("Fork:Pos", "Fork", bores[0].face, 0.1, "RFS", (FaceRef("Fork", fork_b),)),
        ResolvedPosition("Tongue:Pos", "Tongue", tongue_hole.face, 0.1, "RFS",
                         (FaceRef("Tongue", tongue_b),)),
    )  # fmt: skip
    cad = CadInput(model, (), (), (), "synthetic", (), positions)
    built = build_cad_stack(cad, FaceRef("Fork", fork_b), FaceRef("Tongue", tongue_b),
                            lsl=-1.0, usl=1.0, general_class="m")  # fmt: skip
    assert built.chain.path == ("Fork", "Pin", "Tongue")
    assert any("sits in 2 coaxial holes of Fork" in n for n in built.notes)
