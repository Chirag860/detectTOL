"""Triangle meshes of every face of a STEP model, for the app's 3D view.

Faces are meshed with OCCT (``BRepMesh_IncrementalMesh``) in assembly coordinates
[mm] and keep the part name and face index of :func:`detecttol.cad.step_reader.read_step`,
so a clicked face is exactly the ``PART:FACE`` selector the stack builder uses.
Display only: no stack value is ever computed from a mesh.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from OCC.Core.BRep import BRep_Tool
from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
from OCC.Core.TopAbs import TopAbs_REVERSED
from OCC.Core.TopLoc import TopLoc_Location

from detecttol.cad.step_reader import placed_part_faces

Vec3 = tuple[float, float, float]


@dataclass(frozen=True)
class FaceMesh:
    """One face as triangles.

    Attributes:
        part: part name.
        index: face index within the part (as in ``detecttol faces``).
        vertices: corner points [mm].
        triangles: vertex indices, counter-clockwise seen from outside the part.
    """

    part: str
    index: int
    vertices: tuple[Vec3, ...]
    triangles: tuple[tuple[int, int, int], ...]

    @property
    def key(self) -> str:
        return f"{self.part}:{self.index}"


def mesh_model(
    path: str | Path, *, linear_deflection: float = 0.05, angular_deflection: float = 0.3
) -> list[FaceMesh]:
    """Mesh every face of a STEP file.

    Args:
        path: STEP file.
        linear_deflection: maximum chord error relative to the part size (OCCT
            relative mode).
        angular_deflection: maximum angle between neighbouring facets [rad].
    """
    out: list[FaceMesh] = []
    for part, faces in placed_part_faces(path):
        for face in faces:
            BRepMesh_IncrementalMesh(face, linear_deflection, True, angular_deflection, True)
        for index, face in enumerate(faces):
            loc = TopLoc_Location()
            tri = BRep_Tool.Triangulation(face, loc)
            if tri is None:
                continue
            trsf = loc.Transformation()
            vertices = []
            for i in range(1, tri.NbNodes() + 1):
                p = tri.Node(i).Transformed(trsf)
                vertices.append((p.X(), p.Y(), p.Z()))
            reverse = face.Orientation() == TopAbs_REVERSED
            triangles = []
            for i in range(1, tri.NbTriangles() + 1):
                a, b, c = tri.Triangle(i).Get()
                triangles.append((a - 1, c - 1, b - 1) if reverse else (a - 1, b - 1, c - 1))
            out.append(FaceMesh(part, index, tuple(vertices), tuple(triangles)))
    return out


def to_stl(mesh: FaceMesh) -> bytes:
    """Binary STL of one face (normals left to the viewer)."""
    data = bytearray(80)  # header
    data += struct.pack("<I", len(mesh.triangles))
    for a, b, c in mesh.triangles:
        data += struct.pack("<3f", 0.0, 0.0, 0.0)
        for v in (mesh.vertices[a], mesh.vertices[b], mesh.vertices[c]):
            data += struct.pack("<3f", *v)
        data += b"\x00\x00"
    return bytes(data)


def bounds(meshes: list[FaceMesh]) -> tuple[Vec3, Vec3]:
    """Axis-aligned box around all meshes [mm]."""
    pts = [v for m in meshes for v in m.vertices]
    if not pts:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    lo = (min(p[0] for p in pts), min(p[1] for p in pts), min(p[2] for p in pts))
    hi = (max(p[0] for p in pts), max(p[1] for p in pts), max(p[2] for p in pts))
    return lo, hi
