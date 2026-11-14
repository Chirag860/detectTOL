"""Tolerances read from SolidWorks files through the installed SolidWorks (COM API).

detectTOL never parses SolidWorks' file format. It asks a locally installed,
licensed SolidWorks (Windows, ``pywin32``) to open the assembly **read-only**,
reads what the engineer put there, and writes a STEP geometry copy into a temporary
folder for detectTOL's own geometry code. The user's files are never modified or
saved.

- :mod:`detecttol.solidworks.model`: plain records of what was read (no COM, no OCCT).
- :mod:`detecttol.solidworks.reader`: the COM reader (``read_solidworks``).
- :mod:`detecttol.solidworks.resolve`: records -> faces of the STEP geometry ->
  :class:`detecttol.cad.annotations.ResolvedDimension` (needs pythonocc).

Read today: DimXpert *Width* and *DistanceBetween* dimensions (+/- tolerance or an
ISO fit code), DimXpert flatness, and linear drawing dimensions between two
edges with a bilateral or symmetric tolerance. See docs/ASSUMPTIONS.md A33-A36 and
docs/reports/phase-app-2.md.
"""
