"""The detectTOL app: a local browser page for engineers (``detecttol app``).

- :mod:`detecttol.app.state`: everything the page does, as plain Python (tested
  without a browser). No stack maths here: it calls :mod:`detecttol.cad.cad_stack`.
- :mod:`detecttol.app.ui`: the NiceGUI page (needs ``nicegui``).

Runs on the engineer's PC only (``127.0.0.1``); nothing is uploaded.
"""
