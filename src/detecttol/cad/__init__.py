"""STEP AP242 / OCCT access (spec Phase 5).

Importing the sub-modules needs ``pythonocc-core`` (conda-forge). This package
initialiser imports nothing, so ``import detecttol`` works without it.

- :mod:`detecttol.cad.step_reader` - assembly, faces and semantic PMI.
- :mod:`detecttol.cad.step_text`   - OCCT-free PMI entity count (cross-check).
- :mod:`detecttol.cad.mapping`     - PMI -> contributor / GD&T models.
- :mod:`detecttol.cad.annotations` - YAML annotation fallback.
- :mod:`detecttol.cad.synthetic`   - synthetic box assemblies for tests.
"""
