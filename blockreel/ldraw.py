"""Reads parts from the LDraw open parts library (https://www.ldraw.org, CC BY 4.0) and turns them into
triangle meshes the rasterizer can draw.

A mesh is (V, N, F, C): vertices (n,3), vertex normals (n,3), triangles (m,3) and per-vertex colour (n,3)
in 0..1 linear-ish sRGB, or -1 where the polygon takes the colour of the piece ("inherit", LDraw colour 16).
Units: LDraw units (20 per stud of the real brick) are scaled by the caller. Axes are converted to ours
(y up, front towards +z).

Only the subset of the library that the project needs is kept in `ldraw/` (see tools/ldraw_bundle.py).
This module follows the LDraw file format: type 1 sub-file lines, type 3 and 4 polygons, BFC winding
(CCW/CW, INVERTNEXT, mirrored transforms), colour 16 (inherit) and 24 (edge colour, ignored).
"""
import math
import os
import re
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent / "ldraw"
_SEARCH = ("parts", "p", "parts/s", "p/48", "p/8", "models")


def library_root():
    env = os.environ.get("LDRAW_DIR")
    return Path(env) if env else ROOT


@lru_cache(maxsize=1)
def colours():
    """LDraw colour code -> (r, g, b) floats 0..1, from LDConfig.ldr."""
    table = {}
    cfg = library_root() / "LDConfig.ldr"
    if cfg.exists():
        for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.search(r"!COLOUR\s+\S+\s+CODE\s+(\d+)\s+VALUE\s+#([0-9A-Fa-f]{6})", line)
            if m:
                v = int(m.group(2), 16)
                table[int(m.group(1))] = ((v >> 16 & 255) / 255.0, (v >> 8 & 255) / 255.0, (v & 255) / 255.0)
    return table


def _find(name):
    rel = name.replace("\\", "/").lower().strip()
    root = library_root()
    for d in _SEARCH:
        p = root / d / rel
        if p.exists():
            return p
    p = root / rel
    return p if p.exists() else None


def _colour_of(code):
    code = int(code, 0) if isinstance(code, str) else int(code)
    if code in (16, 24):
        return None
    if code >= 0x2000000:                              # direct colour 0x2RRGGBB
        v = code & 0xFFFFFF
        return ((v >> 16 & 255) / 255.0, (v >> 8 & 255) / 255.0, (v & 255) / 255.0)
    return colours().get(code, (0.5, 0.5, 0.5))


_EMPTY = (np.zeros((0, 3, 3)), np.zeros((0, 3)))


@lru_cache(maxsize=4096)
def _file_tris(name):
    """Triangles of one file in its own frame: ((n,3,3) vertices, (n,3) colours with -1 for inherit)."""
    path = _find(name)
    if path is None:
        return _EMPTY
    tris, cols = [], []
    cw = False
    invert_next = False
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        t = raw.split()
        if not t:
            continue
        k = t[0]
        if k == "0":
            if len(t) > 1 and t[1] == "BFC":
                if "CW" in t[2:] and "CCW" not in t[2:]:
                    cw = True
                elif "CCW" in t[2:]:
                    cw = False
                if "INVERTNEXT" in t[2:]:
                    invert_next = True
            continue
        if k == "1" and len(t) >= 15:
            col = _colour_of(t[1])
            x, y, z, a, b, c, d, e, f, g, h, i = [float(v) for v in t[2:14]]
            M = np.array([[a, b, c], [d, e, f], [g, h, i]])
            T = np.array([x, y, z])
            sub_t, sub_c = _file_tris(" ".join(t[14:]))
            if len(sub_t) == 0:
                invert_next = False
                continue
            nt = sub_t @ M.T + T
            flip = (np.linalg.det(M) < 0) != invert_next
            if flip:
                nt = nt[:, ::-1, :]
            nc = sub_c.copy()
            if col is not None:
                nc[(nc[:, 0] < 0)] = col
            tris.append(nt)
            cols.append(nc)
            invert_next = False
        elif k in ("3", "4"):
            n = 3 if k == "3" else 4
            if len(t) < 2 + n * 3 + 1 - 1:
                continue
            pts = np.array([float(v) for v in t[2:2 + n * 3]]).reshape(n, 3)
            col = _colour_of(t[1])
            order = pts[::-1] if cw != invert_next else pts
            invert_next = False
            fan = [(0, i, i + 1) for i in range(1, n - 1)]
            for f in fan:
                tris.append(order[list(f)][None])
                cols.append(np.tile(np.array(col if col is not None else (-1.0, -1.0, -1.0)), (1, 1)))
        elif k in ("2", "5"):
            invert_next = False
    if not tris:
        return _EMPTY
    return np.concatenate(tris), np.concatenate(cols)


def _smooth_normals(V, F, angle_deg=38.0):
    """Per-corner normals: average the faces that meet at a position, but only those within `angle_deg`
    of this face, so curved parts look round and box corners stay sharp."""
    n = len(F)
    P = V[F]                                            # (n,3,3)
    fn = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    area = np.linalg.norm(fn, axis=1, keepdims=True)
    fnu = fn / np.maximum(area, 1e-12)
    N = np.repeat(fnu[:, None, :], 3, axis=1)           # start flat
    key = np.round(P.reshape(-1, 3), 3)
    uniq, inv = np.unique(key, axis=0, return_inverse=True)
    inv = inv.reshape(-1)
    order = np.argsort(inv, kind="stable")
    sorted_inv = inv[order]
    bounds = np.flatnonzero(np.diff(sorted_inv)) + 1
    groups = np.split(order, bounds)
    cos_lim = math.cos(math.radians(angle_deg))
    w = np.maximum(area[:, 0], 1e-9)
    for g in groups:
        if len(g) < 2:
            continue
        faces = g // 3
        dirs = fnu[faces]
        sim = dirs @ dirs.T                              # (k,k)
        wts = (sim >= cos_lim) * w[faces][None, :]
        acc = wts @ dirs
        for gi, corner in enumerate(g):
            N[corner // 3, corner % 3] = acc[gi]
    ln = np.linalg.norm(N, axis=2, keepdims=True)
    return N / np.maximum(ln, 1e-12)


@lru_cache(maxsize=1024)
def load_mesh(name, scale=1.0):
    """Mesh of an LDraw part (e.g. '3626bp01'). Axes: LDraw is y-down with the minifigure facing -z, so we
    rotate 180 degrees about x to get y-up facing +z. `scale` multiplies LDraw units."""
    tris, cols = _file_tris(name if name.endswith(".dat") else name + ".dat")
    if len(tris) == 0:
        raise ValueError(f"LDraw part '{name}' not found or empty (library at {library_root()})")
    tris = tris.copy()
    tris[:, :, 1] *= -1.0
    tris[:, :, 2] *= -1.0
    tris *= float(scale)
    V = tris.reshape(-1, 3)
    F = np.arange(len(V), dtype=np.int64).reshape(-1, 3)
    C = np.repeat(cols, 3, axis=0) if cols.ndim == 2 and len(cols) == len(tris) else np.repeat(cols.reshape(-1, 3), 3, axis=0)
    # drop zero-area triangles
    P = V[F]
    ok = np.linalg.norm(np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]), axis=1) > 1e-9
    F = F[ok]
    N = _smooth_normals(V, F)                           # (m,3,3) per corner
    # rebuild as flat arrays indexed by F so downstream code stays (V, N, F)
    Vn = V[F].reshape(-1, 3)
    Nn = N.reshape(-1, 3)
    Cn = C[F].reshape(-1, 3)
    Fn = np.arange(len(Vn), dtype=np.int64).reshape(-1, 3)
    return Vn, Nn, Fn, Cn


def part_title(name):
    p = _find(name if name.endswith(".dat") else name + ".dat")
    if not p:
        return ""
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines()[:3]:
        if line.startswith("0 ") and not line.startswith("0 Name"):
            return line[2:].strip()
    return ""


def bounds(name, scale=1.0):
    V = load_mesh(name, scale)[0]
    return V.min(axis=0), V.max(axis=0)
