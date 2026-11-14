# ruff: noqa
# Step 1 feasibility spike (docs/reports/phase-app-1.md). Not product code; needs SOLIDWORKS + pywin32.
"""Small helpers around the SolidWorks COM API (throwaway test-file builder)."""

from __future__ import annotations

import pythoncom
import win32com.client
from win32com.client import VARIANT

MM = 0.001  # SolidWorks API lengths are metres

SW_DOC_PART, SW_DOC_ASSEMBLY, SW_DOC_DRAWING = 1, 2, 3
PREF_TEMPLATE = {SW_DOC_PART: 8, SW_DOC_ASSEMBLY: 9, SW_DOC_DRAWING: 10}
SW_UNIT_SYSTEM, SW_UNIT_MMGS = 263, 5
SW_TOL_BILAT = 2


def byref_long() -> VARIANT:
    return VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)


def byref_double() -> VARIANT:
    return VARIANT(pythoncom.VT_BYREF | pythoncom.VT_R8, 0.0)


def nothing() -> None:
    """Empty object argument (typed wrappers accept None)."""
    return None


SLDWORKS_TLB = ("{83A33D31-27C5-11CE-BFD4-00400513BB57}", 0, 34, 0)
DIMXPERT_TLB = ("{582D0D5B-FF58-42CD-8968-A8A001A52454}", 0, 34, 0)

_sw_mod = None
_dx_mod = None


def _modules():
    global _sw_mod, _dx_mod
    if _sw_mod is None:
        from win32com.client import gencache

        _sw_mod = gencache.EnsureModule(*SLDWORKS_TLB)
        _dx_mod = gencache.EnsureModule(*DIMXPERT_TLB)
    return _sw_mod, _dx_mod


def typed(obj, interface: str):
    """Early-bound wrapper of ``obj`` as SolidWorks / DimXpert ``interface``."""
    sw_mod, dx_mod = _modules()
    for mod in (dx_mod, sw_mod):
        cls = getattr(mod, interface, None)
        if cls is not None:
            return cls(obj._oleobj_ if hasattr(obj, "_oleobj_") else obj)
    raise KeyError(interface)


def connect(visible: bool = False):
    _modules()
    sw = typed(win32com.client.Dispatch("SldWorks.Application"), "ISldWorks")
    sw.Visible = visible
    return sw


def dimxpert_part(doc):
    config = doc.ConfigurationManager.ActiveConfiguration.Name
    manager = typed(doc.Extension.DimXpertManager(config, True), "IDimXpertManager")
    return typed(manager.DimXpertPart, "IDimXpertPart")


def new_doc(sw, kind: int):
    template = sw.GetUserPreferenceStringValue(PREF_TEMPLATE[kind])
    if not template:
        raise RuntimeError(f"no default template for document type {kind}")
    raw = sw.NewDocument(template, 0, 0, 0)
    if raw is None:
        raise RuntimeError(f"NewDocument failed for template {template}")
    doc = typed(raw, "IModelDoc2")
    typed(doc.Extension, "IModelDocExtension").SetUserPreferenceInteger(SW_UNIT_SYSTEM, 0, SW_UNIT_MMGS)
    return doc


def save_as(doc, path: str) -> None:
    result = doc.Extension.SaveAs3(path, 0, 1, None, None, 0, 0)  # 1 = silent; returns (ok, err, warn)
    ok, err, warn = result if isinstance(result, tuple) else (result, 0, 0)
    if not ok:
        raise RuntimeError(f"SaveAs3 {path} failed: errors={err} warnings={warn}")


def math_point(sw, x_mm: float, y_mm: float, z_mm: float):
    util = typed(sw.GetMathUtility(), "IMathUtility")
    return util.CreatePoint([x_mm * MM, y_mm * MM, z_mm * MM])


def extrude_blind(doc, depth_mm: float):
    fm = doc.FeatureManager
    feat = fm.FeatureExtrusion3(
        True, False, False, 0, 0, depth_mm * MM, 0.0, False, False, False, False,
        0.0, 0.0, False, False, False, False, True, True, True, 0, 0.0, False,
    )
    if feat is None:
        raise RuntimeError("FeatureExtrusion3 returned None")
    return feat


def select_point(doc, kind: str, x: float, y: float, z: float, append: bool) -> bool:
    """Select an entity of ``kind`` (e.g. FACE) at a point given in mm."""
    return bool(doc.Extension.SelectByID2("", kind, x * MM, y * MM, z * MM, append, 0, nothing(), 0))
