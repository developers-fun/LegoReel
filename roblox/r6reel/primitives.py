"""Scenery meshes. Every function returns an r6reel.mesh.Mesh.

Conventions
- Y-up, right-handed, units are studs. Shapes are centred on the origin unless noted.
- Triangles are counter-clockwise seen from outside. Normals are unit length.
- Boxes, wedges and prisms get one normal per face. Cylinder and cone sides and the sphere get smooth normals.
- UVs run 0..1 across each face (plane() repeats them uv_tile times).
- Results are cached with an unbounded lru_cache: the same arguments return the same Mesh object, so
  the renderer can cache GPU buffers by identity. Never mutate a returned Mesh; use Mesh.transformed().

Wedge orientation (Roblox WedgePart): a right triangular prism. size = (width X, height Y, depth Z).
The sloped face faces up and toward -Z (forward). The low edge is at z=-depth/2, y=-height/2;
the high edge is at z=+depth/2, y=+height/2. The vertical back face is at z=+depth/2 and the bottom at y=-height/2.

prism(profile, length, axis) extrudes a convex 2D profile. Profile (p, q) maps to the two axes after the
extrusion axis in cyclic order: axis "z" -> (x, y), "x" -> (y, z), "y" -> (z, x). The extrusion is centred.
"""
from __future__ import annotations

import functools
import math

import numpy as np

from r6reel.mesh import Mesh

_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


class _Builder:
    """Collects vertices and triangles. Each triangle is wound to agree with a wanted normal."""

    def __init__(self):
        self.pos, self.nrm, self.uv, self.idx = [], [], [], []

    def vert(self, p, n, uv) -> int:
        self.pos.append(np.asarray(p, float))
        self.nrm.append(np.asarray(n, float))
        self.uv.append(uv)
        return len(self.pos) - 1

    def tri(self, a, b, c, want=None):
        pa, pb, pc = self.pos[a], self.pos[b], self.pos[c]
        cr = np.cross(pb - pa, pc - pa)
        if np.linalg.norm(cr) < 1e-12:      # degenerate (e.g. sphere poles): skip
            return
        want = np.asarray(want, float) if want is not None else self.nrm[a] + self.nrm[b] + self.nrm[c]
        if np.dot(cr, want) < 0:
            b, c = c, b
        self.idx.append((a, b, c))

    def mesh(self) -> Mesh:
        return Mesh(np.array(self.pos), np.array(self.nrm), np.array(self.uv),
                    np.array(self.idx, dtype=np.uint32).reshape(-1, 3))


def _tup3(v) -> tuple:
    vals = tuple(float(x) for x in v)
    if len(vals) != 3:
        raise ValueError(f"expected 3 values, got {v!r}")
    return vals


def _flat_faces(bld: _Builder, faces, interior):
    """Add convex planar polygons (lists of 3D points). Each face gets its own vertices and a flat normal.

    The normal comes from the polygon's own vertex order (Newell sum) and is flipped to point away from
    `interior`, so winding is correct for any convex solid without hand-checking each face.
    """
    for pts in faces:
        pts = [np.asarray(p, float) for p in pts]
        n = np.zeros(3)
        for i in range(len(pts)):
            n += np.cross(pts[i], pts[(i + 1) % len(pts)])
        n /= np.linalg.norm(n)
        if np.dot(n, np.mean(pts, axis=0) - interior) < 0:
            pts = pts[::-1]
            n = -n
        u = pts[1] - pts[0]
        u = u / np.linalg.norm(u)
        v = np.cross(n, u)
        uvs = np.array([[np.dot(p - pts[0], u), np.dot(p - pts[0], v)] for p in pts])
        uvs -= uvs.min(axis=0)
        span = uvs.max(axis=0)
        span[span < 1e-9] = 1.0
        uvs /= span
        base = [bld.vert(p, n, uv) for p, uv in zip(pts, uvs)]
        for k in range(1, len(pts) - 1):
            bld.tri(base[0], base[k], base[k + 1], want=n)


def _box_faces(h):
    faces = []
    for axis in range(3):
        a, b = (axis + 1) % 3, (axis + 2) % 3
        for s in (-1.0, 1.0):
            corners = []
            for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                p = np.zeros(3)
                p[axis] = s * h[axis]
                p[a] = sa * h[a]
                p[b] = sb * h[b]
                corners.append(p)
            faces.append(corners)
    return faces


@functools.lru_cache(maxsize=None)
def _box(size, bevel):
    if bevel > 0:
        return _rounded_cube(size, bevel, 2)
    bld = _Builder()
    _flat_faces(bld, _box_faces(np.asarray(size, float) / 2), np.zeros(3))
    return bld.mesh()


def _rounded_cube(size, r, seg) -> Mesh:
    """Box with rounded edges and corners. Each face is a grid; points are pushed onto a sphere of
    radius r around the inner box (clamp trick), so the mesh is watertight and normals are smooth."""
    h = np.asarray(size, float) / 2
    if np.any(r >= h):
        raise ValueError(f"radius {r} must be smaller than half of every size {tuple(h)}")
    inner = h - r
    coords = [np.concatenate([np.linspace(-h[k], -inner[k], seg + 1),
                              np.linspace(inner[k], h[k], seg + 1)]) for k in range(3)]
    bld = _Builder()
    for axis in range(3):
        ua, ub = (axis + 1) % 3, (axis + 2) % 3
        for s in (-1.0, 1.0):
            ga, gb = coords[ua], coords[ub]
            ids = np.empty((len(ga), len(gb)), dtype=int)
            for i, x in enumerate(ga):
                for j, y in enumerate(gb):
                    p = np.zeros(3)
                    p[axis], p[ua], p[ub] = s * h[axis], x, y
                    c = np.clip(p, -inner, inner)
                    d = p - c
                    n = d / np.linalg.norm(d)
                    uv = ((p[ua] + h[ua]) / (2 * h[ua]), (p[ub] + h[ub]) / (2 * h[ub]))
                    ids[i, j] = bld.vert(c + r * n, n, uv)
            for i in range(len(ga) - 1):
                for j in range(len(gb) - 1):
                    v00, v10 = ids[i, j], ids[i + 1, j]
                    v11, v01 = ids[i + 1, j + 1], ids[i, j + 1]
                    bld.tri(v00, v10, v11)
                    bld.tri(v00, v11, v01)
    return bld.mesh()


@functools.lru_cache(maxsize=None)
def _rounded_box(size, radius, segments):
    if radius <= 0:
        return _box(size, 0.0)
    return _rounded_cube(size, radius, segments)


def box(size=(1, 1, 1), bevel=0.0) -> Mesh:
    """Axis-aligned box with full extents `size`. bevel > 0 rounds the edges (radius in studs)."""
    return _box(_tup3(size), float(bevel))


def rounded_box(size, radius, segments=3) -> Mesh:
    """Box with corners rounded to `radius`; `segments` is the number of steps per rounded edge."""
    return _rounded_box(_tup3(size), float(radius), int(segments))


@functools.lru_cache(maxsize=None)
def _prism(profile, length, axis):
    ext = _AXIS_INDEX[axis]
    pa, qa = (ext + 1) % 3, (ext + 2) % 3

    def to3(p, q, t):
        v = np.zeros(3)
        v[ext], v[pa], v[qa] = t, p, q
        return v

    n = len(profile)
    bottom = [to3(p, q, -length / 2) for p, q in profile]
    top = [to3(p, q, length / 2) for p, q in profile]
    faces = [bottom, top]
    for i in range(n):
        j = (i + 1) % n
        faces.append([bottom[i], bottom[j], top[j], top[i]])
    interior = np.mean(bottom + top, axis=0)
    bld = _Builder()
    _flat_faces(bld, faces, interior)
    return bld.mesh()


def prism(profile, length, axis="z") -> Mesh:
    """Convex polygon extruded `length` along `axis`. profile: list of (p, q) points (any order)."""
    if axis not in _AXIS_INDEX:
        raise ValueError(f"axis must be x, y or z, got {axis!r}")
    prof = tuple((float(p), float(q)) for p, q in profile)
    return _prism(prof, float(length), axis)


def wedge(size=(1, 1, 1)) -> Mesh:
    """Roblox-style WedgePart. See the module docstring for orientation."""
    w, h, d = _tup3(size)
    return _prism(((-h / 2, -d / 2), (-h / 2, d / 2), (h / 2, d / 2)), w, "x")


def _disc(bld: _Builder, y, normal, radius, segments):
    c = bld.vert((0.0, y, 0.0), normal, (0.5, 0.5))
    ring = []
    for j in range(segments):
        t = 2 * math.pi * j / segments
        ring.append(bld.vert((radius * math.cos(t), y, radius * math.sin(t)), normal,
                             (0.5 + 0.5 * math.cos(t), 0.5 + 0.5 * math.sin(t))))
    for j in range(segments):
        bld.tri(c, ring[j], ring[(j + 1) % segments], want=normal)


def _axis_matrix(axis) -> np.ndarray:
    m = np.eye(4)
    if axis == "x":      # Rz(-90): local +Y -> +X
        m[:3, :3] = [[0, 1, 0], [-1, 0, 0], [0, 0, 1]]
    elif axis == "z":    # Rx(+90): local +Y -> +Z
        m[:3, :3] = [[1, 0, 0], [0, 0, -1], [0, 1, 0]]
    elif axis != "y":
        raise ValueError(f"axis must be x, y or z, got {axis!r}")
    return m


@functools.lru_cache(maxsize=None)
def _cylinder(radius, height, segments, axis):
    bld = _Builder()
    h2 = height / 2
    for j in range(segments):
        t0 = 2 * math.pi * j / segments
        t1 = 2 * math.pi * (j + 1) / segments
        n0 = np.array([math.cos(t0), 0.0, math.sin(t0)])
        n1 = np.array([math.cos(t1), 0.0, math.sin(t1)])
        want = n0 + n1
        b0 = bld.vert(n0 * radius + (0, -h2, 0), n0, (j / segments, 0.0))
        b1 = bld.vert(n1 * radius + (0, -h2, 0), n1, ((j + 1) / segments, 0.0))
        u0 = bld.vert(n0 * radius + (0, h2, 0), n0, (j / segments, 1.0))
        u1 = bld.vert(n1 * radius + (0, h2, 0), n1, ((j + 1) / segments, 1.0))
        bld.tri(b0, b1, u1, want)
        bld.tri(b0, u1, u0, want)
    _disc(bld, h2, np.array([0.0, 1.0, 0.0]), radius, segments)
    _disc(bld, -h2, np.array([0.0, -1.0, 0.0]), radius, segments)
    return bld.mesh().transformed(_axis_matrix(axis))


def cylinder(radius=0.5, height=1.0, segments=24, axis="y") -> Mesh:
    """Cylinder along `axis` (x, y or z), centred on the origin, smooth sides, flat caps."""
    return _cylinder(float(radius), float(height), int(segments), str(axis).lower())


@functools.lru_cache(maxsize=None)
def _sphere(radius, segments):
    rings = max(2, segments // 2)
    bld = _Builder()
    grid = np.empty((rings + 1, segments + 1), dtype=int)
    for i in range(rings + 1):
        phi = math.pi * i / rings
        for j in range(segments + 1):
            th = 2 * math.pi * j / segments
            n = np.array([math.sin(phi) * math.cos(th), math.cos(phi), math.sin(phi) * math.sin(th)])
            grid[i, j] = bld.vert(radius * n, n, (j / segments, i / rings))
    for i in range(rings):
        for j in range(segments):
            a, b = grid[i, j], grid[i + 1, j]
            c, d = grid[i + 1, j + 1], grid[i, j + 1]
            bld.tri(a, b, c)
            bld.tri(a, c, d)
    return bld.mesh()


def sphere(radius=0.5, segments=24) -> Mesh:
    """UV sphere centred on the origin with smooth normals."""
    return _sphere(float(radius), int(segments))


@functools.lru_cache(maxsize=None)
def _cone(radius, height, segments):
    bld = _Builder()
    h2 = height / 2

    def side_normal(t):
        v = np.array([height * math.cos(t), radius, height * math.sin(t)])
        return v / np.linalg.norm(v)

    apex = (0.0, h2, 0.0)
    for j in range(segments):
        t0 = 2 * math.pi * j / segments
        t1 = 2 * math.pi * (j + 1) / segments
        tm = (t0 + t1) / 2
        n0, n1, nm = side_normal(t0), side_normal(t1), side_normal(tm)
        b0 = bld.vert((radius * math.cos(t0), -h2, radius * math.sin(t0)), n0, (j / segments, 0.0))
        b1 = bld.vert((radius * math.cos(t1), -h2, radius * math.sin(t1)), n1, ((j + 1) / segments, 0.0))
        ap = bld.vert(apex, nm, ((j + 0.5) / segments, 1.0))
        bld.tri(b0, b1, ap, want=nm)
    _disc(bld, -h2, np.array([0.0, -1.0, 0.0]), radius, segments)
    return bld.mesh()


def cone(radius=0.5, height=1.0, segments=24) -> Mesh:
    """Cone with its base on y=-height/2 and its apex on y=+height/2."""
    return _cone(float(radius), float(height), int(segments))


@functools.lru_cache(maxsize=None)
def _plane(sx, sz, ux, uz):
    bld = _Builder()
    hx, hz = sx / 2, sz / 2
    corners = [(-hx, -hz, 0.0, 0.0), (hx, -hz, ux, 0.0), (hx, hz, ux, uz), (-hx, hz, 0.0, uz)]
    ids = [bld.vert((x, 0.0, z), (0.0, 1.0, 0.0), (u, v)) for x, z, u, v in corners]
    up = (0.0, 1.0, 0.0)
    bld.tri(ids[0], ids[1], ids[2], want=up)
    bld.tri(ids[0], ids[2], ids[3], want=up)
    return bld.mesh()


def plane(size=(1, 1), uv_tile=(1, 1)) -> Mesh:
    """Flat quad in the XZ plane, normal +Y, centred on the origin. uv_tile repeats the texture."""
    return _plane(float(size[0]), float(size[1]), float(uv_tile[0]), float(uv_tile[1]))
