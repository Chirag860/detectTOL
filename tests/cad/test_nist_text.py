"""PMI counts of all NIST AP242 files, from the file text (no pythonocc needed).

root.md, Phase 5: "the number of PMI items read matches the documented counts
for the test models". NIST's expected-PMI tables are built into its STEP File
Analyzer and are not published as a separate table, so the reference here is
the file itself: two independent implementations - the tokenising parser
``parse_pmi_text`` that the reader uses, and the regular-expression counter
``count_pmi_entities`` - must agree on every file, item for item.

The table of expected counts below was produced by the counter and then checked
by hand for CTC-01 (8 valued dimensions, 6 geometric tolerances, datums A B C;
entity ids in tests/cad/test_nist.py).
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from detecttol.cad.step_pmi_text import KIND_OF_ENTITY, read_pmi_text
from detecttol.cad.step_text import count_pmi_entities

#: file -> (geometric tolerances, dimensions with a value, MMC, LMC, datum letters)
EXPECTED = {
    "nist_ctc_01_asme1_ap242-e1.stp": (6, 8, 0, 0, "ABC"),
    "nist_ctc_02_asme1_ap242-e2.stp": (22, 7, 1, 3, "ABCDEFGHJK"),
    "nist_ctc_03_asme1_ap242-e2.stp": (13, 9, 2, 0, "ABCDEF"),
    "nist_ctc_04_asme1_ap242-e1.stp": (7, 10, 0, 0, "ABCDEFGH"),
    "nist_ctc_05_asme1_ap242-e1.stp": (10, 6, 0, 0, "ABCD"),
    "nist_ftc_06_asme1_ap242-e2.stp": (28, 24, 4, 0, "ABCDEFGHJK"),
    "nist_ftc_07_asme1_ap242-e2.stp": (27, 17, 4, 0, "ABCDE"),
    "nist_ftc_08_asme1_ap242-e1-tg.stp": (0, 0, 0, 0, ""),
    "nist_ftc_08_asme1_ap242-e2.stp": (33, 10, 13, 0, "ABCDEFGHJKL"),
    "nist_ftc_09_asme1_ap242-e1.stp": (31, 22, 6, 0, "ABCDEFGH"),
    "nist_ftc_10_asme1_ap242-e2.stp": (40, 26, 2, 1, "ABCDEFGHJKL"),
    "nist_ftc_11_asme1_ap242-e2.stp": (4, 6, 0, 0, "AB"),
    "nist_stc_06_asme1_ap242-e3.stp": (25, 17, 3, 0, "ABCDEF"),
    "nist_stc_07_asme1_ap242-e3.stp": (22, 45, 3, 0, "ABCDE"),
    "nist_stc_08_asme1_ap242-e3.stp": (30, 7, 9, 0, "ABCDEGHJ"),
    "nist_stc_09_asme1_ap242-e3.stp": (27, 22, 5, 0, "ABCDEFGH"),
    "nist_stc_10_asme1_ap242-e2.stp": (37, 27, 2, 1, "ABCDEFGHJ"),
}
ENTITY_OF_KIND = {kind: entity for entity, kind in KIND_OF_ENTITY.items()}


def test_all_seventeen_files_are_covered(nist_dir: Path) -> None:
    present = sorted(p.name for p in nist_dir.glob("*ap242*.stp"))
    assert present == sorted(EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_pmi_item_counts_match_the_file(name: str, nist_dir: Path) -> None:
    """Parser, counter and the recorded table agree: number of geometric
    tolerances (in total and per type), valued dimensions, MMC and LMC modifiers,
    and the set of datum letters. 362 tolerances and 263 dimensions in all."""
    path = nist_dir / name
    pmi, counts = read_pmi_text(path), count_pmi_entities(path)
    tolerances, dimensions, mmc, lmc, datums = EXPECTED[name]

    assert len(pmi.geometric_tolerances) == counts.geometric_tolerances == tolerances
    assert len(pmi.dimensions) == counts.dimensions_with_value == dimensions
    modifiers = Counter(g.material_modifier for g in pmi.geometric_tolerances)
    assert (modifiers["M"], modifiers["L"]) == (counts.mmc_modifiers, counts.lmc_modifiers)
    assert (modifiers["M"], modifiers["L"]) == (mmc, lmc)
    assert "".join(pmi.datum_names) == "".join(sorted(set(counts.datum_names))) == datums

    per_type = Counter(ENTITY_OF_KIND[g.kind] for g in pmi.geometric_tolerances)
    for entity, count in per_type.items():
        assert count == counts.geometric_tolerance_types[entity], entity
    for g in pmi.geometric_tolerances:
        assert g.kind in ENTITY_OF_KIND
        # A zero tolerance is legitimate only with a material modifier
        # ("zero positional tolerance at MMC/LMC": FTC-10 and STC-10 have one at LMC).
        assert g.value > 0.0 or (g.value == 0.0 and g.material_modifier in ("M", "L"))
        assert all(d for d in g.datums)
    for d in pmi.dimensions:
        assert d.value == d.value and d.unit in ("mm", "rad")
        assert d.tolerance_form in ("plus_minus", "range", "class", "none")
        if d.upper_tol is not None and d.lower_tol is not None:
            assert d.upper_tol >= d.lower_tol


def test_totals() -> None:
    """Sum of the table: 362 geometric tolerances, 263 valued dimensions."""
    assert sum(v[0] for v in EXPECTED.values()) == 362
    assert sum(v[1] for v in EXPECTED.values()) == 263
