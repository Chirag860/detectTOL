"""Write small synthetic STEP assemblies of boxes with known dimensions.

Used by the tests and as known-by-construction input for later phases.
Geometry only: no PMI is written (writing PMI created through the Python
binding crashes OCCT 8.0.1, see docs/reports/phase-5.md).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCC.Core.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.STEPCAFControl import STEPCAFControl_Writer
from OCC.Core.STEPControl import STEPControl_AsIs
from OCC.Core.TDataStd import TDataStd_Name
from OCC.Core.TDocStd import TDocStd_Document
from OCC.Core.TopLoc import TopLoc_Location
from OCC.Core.XCAFDoc import XCAFDoc_DocumentTool

from detecttol.cad._occt import silence_occt


@dataclass(frozen=True)
class BoxPart:
    """An axis-aligned box part and its placement.

    Attributes:
        name: part name (unique within the assembly).
        size: ``(dx, dy, dz)`` [mm]; the box spans ``[0, dx] x [0, dy] x [0, dz]``
            in its own frame.
        origin: translation of the part in the assembly [mm].
        rotation_z_deg: rotation about the assembly z axis through the part's
            own origin, applied before the translation [degrees].
        slot: optional ``(x0, x1, z0, z1)`` [mm, part frame]: a rectangular slot
            cut through the whole y extent, leaving a floor at ``z0`` (normal +z)
            and a ceiling at ``z1`` (normal -z).
        cylinder_radius: if given, the part is instead a cylinder of this
            radius and height ``size[2]`` standing on z = 0 with its axis at
            ``(radius, radius)`` in the part frame (``size[0]``/``size[1]`` unused).
    """

    name: str
    size: tuple[float, float, float]
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_z_deg: float = 0.0
    slot: tuple[float, float, float, float] | None = None
    cylinder_radius: float | None = None


def write_box_assembly(
    path: str | Path, parts: Sequence[BoxPart], assembly_name: str = "ASSEMBLY"
) -> None:
    """Write an assembly of boxes to a STEP file (AP214/AP242 as OCCT defaults).

    Raises:
        ValueError: no parts, duplicate names or a non-positive size.
        OSError: the file could not be written.
    """
    if not parts:
        raise ValueError("at least one part is required")
    names = [p.name for p in parts]
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate part names in {names}")
    silence_occt()
    document = TDocStd_Document("detecttol-synthetic")
    shape_tool = XCAFDoc_DocumentTool.ShapeTool(document.Main())
    assembly = shape_tool.NewShape()
    TDataStd_Name.Set(assembly, assembly_name)
    for part in parts:
        dx, dy, dz = part.size
        if min(dx, dy, dz) <= 0:
            raise ValueError(f"part '{part.name}': sizes must be > 0")
        if part.cylinder_radius is not None:
            r = part.cylinder_radius
            axis = gp_Ax2(gp_Pnt(r, r, 0.0), gp_Dir(0.0, 0.0, 1.0))
            box = BRepPrimAPI_MakeCylinder(axis, r, dz).Shape()
        else:
            box = BRepPrimAPI_MakeBox(gp_Pnt(0.0, 0.0, 0.0), dx, dy, dz).Shape()
        if part.slot is not None:
            x0, x1, z0, z1 = part.slot
            if not (0.0 <= x0 < x1 <= dx and 0.0 < z0 < z1 < dz):
                raise ValueError(f"part '{part.name}': slot must lie inside the box")
            cutter = BRepPrimAPI_MakeBox(gp_Pnt(x0, -1.0, z0), gp_Pnt(x1, dy + 1.0, z1)).Shape()
            box = BRepAlgoAPI_Cut(box, cutter).Shape()
        label = shape_tool.AddShape(box, False)
        TDataStd_Name.Set(label, part.name)
        rotation = gp_Trsf()
        rotation.SetRotation(
            gp_Ax1(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(0.0, 0.0, 1.0)),
            math.radians(part.rotation_z_deg),
        )
        translation = gp_Trsf()
        translation.SetTranslation(gp_Vec(*part.origin))
        component = shape_tool.AddComponent(
            assembly, label, TopLoc_Location(translation.Multiplied(rotation))
        )
        TDataStd_Name.Set(component, part.name)
    shape_tool.UpdateAssemblies()

    writer = STEPCAFControl_Writer()
    writer.SetNameMode(True)
    if not writer.Transfer(document, STEPControl_AsIs):
        raise OSError(f"could not transfer the assembly for {path}")
    if writer.Write(str(path)) != IFSelect_RetDone:
        raise OSError(f"could not write STEP file {path}")
