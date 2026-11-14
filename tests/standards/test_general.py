"""IS 2102 (Part 1):1993 = ISO 2768-1:1989, Table 1 (linear dimensions).

Expected values are read from the standard's Table 1 (BIS scan, text layer):

    class        0.5-3  >3-6  >6-30  >30-120  >120-400  >400-1000  >1000-2000  >2000-4000
    f fine       0.05   0.05  0.1    0.15     0.2       0.3        0.5         -
    m medium     0.1    0.1   0.2    0.3      0.5       0.8        1.2         2
    c coarse     0.2    0.3   0.5    0.8      1.2       2          3           4
    v v. coarse  -      0.5   1      1.5      2.5       4          6           8
"""

from __future__ import annotations

import pytest

from detecttol.standards.general import (
    GeneralToleranceError,
    describe,
    general_deviation,
    range_text,
)


@pytest.mark.parametrize(
    ("size", "cls", "expected"),
    [
        (0.5, "f", 0.05),  # first range starts at 0.5 inclusive
        (3.0, "c", 0.2),  # 3 is still in "0.5 up to 3"
        (3.0001, "c", 0.3),  # over 3
        (25.0, "m", 0.2),
        (30.0, "m", 0.2),
        (100.0, "m", 0.3),
        (120.0, "f", 0.15),
        (250.0, "c", 1.2),
        (1000.0, "v", 4.0),
        (1500.0, "f", 0.5),
        (4000.0, "m", 2.0),
        (2500.0, "v", 8.0),
    ],
)
def test_table_values(size: float, cls: str, expected: float) -> None:
    assert general_deviation(size, cls) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("size", "cls", "message"),
    [
        (0.4, "m", "below 0.5 mm"),
        (4000.5, "m", "above 4000 mm"),
        (2.0, "v", "gives no value"),
        (3000.0, "f", "gives no value"),
        (10.0, "x", "unknown general tolerance class"),
    ],
)
def test_refused(size: float, cls: str, message: str) -> None:
    with pytest.raises(GeneralToleranceError, match=message):
        general_deviation(size, cls)  # type: ignore[arg-type]


def test_source_text() -> None:
    assert range_text(2.0) == "0.5 up to 3 mm"
    assert range_text(25.0) == "over 6 up to 30 mm"
    assert describe(25.0, "m") == "IS 2102-m / ISO 2768-m (over 6 up to 30 mm): +/-0.2"
