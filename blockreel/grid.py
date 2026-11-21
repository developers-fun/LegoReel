"""Stud-grid snapping: sizes become whole studs (a 4x6 slab, not 3.7 x 5.9) and everything sits on the ground lattice.

The ground lattice has pitch `ground.tile` (1.164 world units = one stud). Stud centres are at (i + 0.5) * pitch, so
cell edges are at whole multiples of the pitch. A prop N studs wide is on the grid when its edges are on those lines,
i.e. its centre is at (k + N/2) * pitch. Heights come in plates (1 plate = 0.4 stud pitch, 1 brick = 3 plates).

Scene.meta.grid (all keys optional):
    {"enabled": true, "props": true, "characters": true, "zones": true, "rotation": true}
A single prop opts out with "grid": false.
"""
from __future__ import annotations

import math

import numpy as np

PLATE = 0.4              # plate height as a fraction of the stud pitch
FIT_RANGE = (0.6, 1.6)   # a set piece is never rescaled outside this range to reach a whole-stud footprint

DEFAULT_GRID = {"enabled": True, "props": True, "characters": True, "zones": True, "rotation": True}


def studs(n_world, pitch):
    """World length -> whole studs (at least 1)."""
    return max(1, int(round(n_world / pitch)))


def snap_edge_centre(c, n, pitch):
    """Centre coordinate for a footprint of n studs so both edges sit on lattice lines."""
    return (round(c / pitch - n / 2.0) + n / 2.0) * pitch


def snap_rotation(deg):
    """Nearest multiple of 90 degrees, in (-180, 180]."""
    r = round(deg / 90.0) * 90.0
    r = (r + 180.0) % 360.0 - 180.0
    return 180.0 if r == -180.0 else r


def snap_character_xz(x, z, pitch):
    """A minifig is 2 studs wide and 1 deep: x on a lattice line, z on a stud centre."""
    return round(x / pitch) * pitch, (round(z / pitch - 0.5) + 0.5) * pitch


def snap_height(bottom, height, pitch):
    """Height in whole plates (>= 1) and a bottom edge on a plate boundary."""
    plate = PLATE * pitch
    plates = max(1, int(round(height / plate)))
    b = round(bottom / plate) * plate
    return plates, plates * plate, b


def _swap(rot):
    return int(round(rot / 90.0)) % 2 == 1


def snap_box(position, size, rotation_y, pitch, snap_rot=True):
    """Return (position, size, rotation_y, info) for a box or cylinder prop snapped to the grid."""
    rot = snap_rotation(rotation_y) if snap_rot else rotation_y
    sx, sy, sz = (float(v) for v in size)
    nx, nz = studs(sx, pitch), studs(sz, pitch)
    plates, h, bottom = snap_height(position[1] - sy / 2.0, sy, pitch)
    wx, wz = (nz, nx) if _swap(rot) else (nx, nz)         # footprint in world axes
    cx = snap_edge_centre(position[0], wx, pitch)
    cz = snap_edge_centre(position[2], wz, pitch)
    info = {"studs": (nx, nz), "plates": plates, "world_studs": (wx, wz), "rotation": rot}
    return np.array([cx, bottom + h / 2.0, cz]), (nx * pitch, h, nz * pitch), rot, info


def piece_extent(pieces):
    """Local xz bounding box (xmin, xmax, zmin, zmax) and ymin of a set's pieces, or None if it cannot be known."""
    xs, zs, ys = [], [], []
    for pc in pieces:
        if "size" not in pc or "pos" not in pc:
            return None
        sx, sy, sz = pc["size"]
        px, py, pz = pc["pos"]
        if pc.get("rot") and any(abs(v) > 1e-9 for v in pc["rot"]):
            r = math.sqrt(sx * sx + sy * sy + sz * sz) / 2.0     # tilted: use a bounding sphere, never too small
            sx = sy = sz = 2 * r
        xs += [px - sx / 2, px + sx / 2]
        zs += [pz - sz / 2, pz + sz / 2]
        ys.append(py - sy / 2)
    if not xs:
        return None
    return min(xs), max(xs), min(zs), max(zs), min(ys)


def snap_template(position, rotation_y, scale, extent, pitch, snap_rot=True):
    """Snap a set piece (prefab). The scale is nudged so the larger footprint side is a whole number of studs, then the
    footprint's edges are put on lattice lines. Returns (position, rotation_y, scale, info)."""
    rot = snap_rotation(rotation_y) if snap_rot else rotation_y
    if extent is None:
        x, z = snap_character_xz(position[0], position[2], pitch)
        return np.array([x, position[1], z]), rot, scale, {"note": "footprint unknown, position snapped only"}
    x0, x1, z0, z1, _ymin = extent
    wx, wz = (x1 - x0) * scale, (z1 - z0) * scale
    if _swap(rot):
        wx, wz = wz, wx
    big = max(wx, wz)
    n_big = studs(big, pitch)
    s = scale * (n_big * pitch) / big
    clamped = False
    lo, hi = scale * FIT_RANGE[0], scale * FIT_RANGE[1]
    if not lo <= s <= hi:
        s, clamped = min(max(s, lo), hi), True
    wx, wz = (x1 - x0) * s, (z1 - z0) * s
    if _swap(rot):
        wx, wz = wz, wx
    nx, nz = max(1, int(math.ceil(wx / pitch - 1e-6))), max(1, int(math.ceil(wz / pitch - 1e-6)))   # cells it occupies
    # local footprint centre, rotated and scaled, is where the prop's origin sits relative to its footprint centre
    lcx, lcz = (x0 + x1) / 2.0 * s, (z0 + z1) / 2.0 * s
    a = math.radians(rot)
    ox, oz = lcx * math.cos(a) + lcz * math.sin(a), -lcx * math.sin(a) + lcz * math.cos(a)
    fcx = snap_edge_centre(position[0] + ox, nx, pitch)
    fcz = snap_edge_centre(position[2] + oz, nz, pitch)
    info = {"studs": (nx, nz), "footprint_world": (wx, wz), "scale": s, "clamped": clamped, "rotation": rot}
    return np.array([fcx - ox, position[1], fcz - oz]), rot, s, info


def snap_zone_rect(rect, pitch):
    """Ground zone rect [x0, z0, x1, z1] with every edge on a lattice line (at least one cell wide)."""
    x0, z0, x1, z1 = (round(v / pitch) * pitch for v in rect)
    if x1 <= x0:
        x1 = x0 + pitch
    if z1 <= z0:
        z1 = z0 + pitch
    return [x0, z0, x1, z1]


def on_lattice(value, pitch, offset=0.0, tol=1e-6):
    """Is value on a lattice line (offset 0) or a stud centre (offset 0.5)?"""
    k = value / pitch - offset
    return abs(k - round(k)) * pitch < tol + 1e-9
