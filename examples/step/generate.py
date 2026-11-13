"""Regenerate the synthetic STEP assemblies of this folder.

Run inside the conda environment:  python examples/step/generate.py

The geometry is known by construction, so the stacks built from these files
have hand-checkable answers (see the YAML files beside them).
"""

from __future__ import annotations

from pathlib import Path

from detecttol.cad.synthetic import BoxPart, write_box_assembly

HERE = Path(__file__).parent

ASSEMBLIES = {
    # Golden case A of root.md: slot depth 50, three plates of 16.6.
    "plate_stack.step": [
        BoxPart("HOUSING", (60.0, 30.0, 70.0), slot=(5.0, 55.0, 10.0, 60.0)),
        BoxPart("PLATE_1", (50.0, 30.0, 16.6), origin=(5.0, 0.0, 10.0)),
        BoxPart("PLATE_2", (50.0, 30.0, 16.6), origin=(5.0, 0.0, 26.6)),
        BoxPart("PLATE_3", (50.0, 30.0, 16.6), origin=(5.0, 0.0, 43.2)),
    ],
    # A plate on a base: overall height 26.6.
    "stacked_blocks.step": [
        BoxPart("BASE", (50.0, 30.0, 10.0)),
        BoxPart("PLATE", (50.0, 30.0, 16.6), origin=(0.0, 0.0, 10.0)),
    ],
    # Two towers on one base: height difference 0.5.
    "step_height.step": [
        BoxPart("BASE", (100.0, 30.0, 10.0)),
        BoxPart("TOWER_A", (20.0, 30.0, 25.0), origin=(10.0, 0.0, 10.0)),
        BoxPart("TOWER_B", (20.0, 30.0, 25.5), origin=(60.0, 0.0, 10.0)),
    ],
}


def main() -> None:
    for name, parts in ASSEMBLIES.items():
        write_box_assembly(HERE / name, parts)


if __name__ == "__main__":
    main()
