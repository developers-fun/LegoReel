"""Procedural meshes: beveled boxes, rounded-square prisms (the head) and cylinders.

Each mesh is (vertices, normals, triangles) in the shape's local frame, centred on the origin.
Normals are per vertex so the rasterizer can shade a bevel smoothly (Gouraud). Everything is
generated here in code; nothing is loaded from any outside asset.
"""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

_AXES = ((1, 2), (0, 2), (0, 1))   # for an axis a, the two other axes (u, v)


@lru_cache(maxsize=1024)
def box_mesh(size, bevel):
    """Box with chamfered edges. 24 vertices, 12 triangles when bevel is 0, else 44."""
    h = [s / 2.0 for s in size]
    b = float(min(bevel, 0.45 * min(size)))
    V, N, vid = [], [], {}
    for a in range(3):
        u, v = _AXES[a]
        for s in (-1, 1):
            for su in (-1, 1):
                for sv in (-1, 1):
                    p = [0.0, 0.0, 0.0]
                    p[a] = s * h[a]
                    p[u] = su * (h[u] - b)
                    p[v] = sv * (h[v] - b)
                    n = [0.0, 0.0, 0.0]
                    n[a] = float(s)
                    vid[(a, s, su, sv)] = len(V)
                    V.append(p)
                    N.append(n)
    F = []

    def corner_vertex(a, s, signs):
        u, v = _AXES[a]
        return vid[(a, s, signs[u], signs[v])]

    for a in range(3):
        for s in (-1, 1):
            q = [vid[(a, s, -1, -1)], vid[(a, s, 1, -1)], vid[(a, s, 1, 1)], vid[(a, s, -1, 1)]]
            F += [(q[0], q[1], q[2]), (q[0], q[2], q[3])]
    if b > 1e-6:
        # edge strips: one per pair of axes and sign pair, running along the third axis
        for a in range(3):
            for c in range(a + 1, 3):
                e = 3 - a - c  # axis the edge runs along
                for sa in (-1, 1):
                    for sc in (-1, 1):
                        quad = []
                        for se in (-1, 1):
                            signs = [0, 0, 0]
                            signs[a], signs[c], signs[e] = sa, sc, se
                            quad.append((corner_vertex(a, sa, signs), corner_vertex(c, sc, signs)))
                        (a0, c0), (a1, c1) = quad
                        F += [(a0, c0, c1), (a0, c1, a1)]
        # corner triangles
        for sx in (-1, 1):
            for sy in (-1, 1):
                for sz in (-1, 1):
                    signs = [sx, sy, sz]
                    F.append(tuple(corner_vertex(a, signs[a], signs) for a in range(3)))
    return (np.array(V, dtype=np.float64), np.array(N, dtype=np.float64), np.array(F, dtype=np.int64))


@lru_cache(maxsize=256)
def prism_mesh(size, exponent, corner, segs=28, steps=3):
    """Vertical prism whose cross-section is a superellipse (exponent 2 = round, 4 = soft square),
    with rounded top and bottom edges of radius `corner`. size = (w, h, d)."""
    a, hh, bb = size[0] / 2.0, size[1] / 2.0, size[2] / 2.0
    c = float(min(corner, 0.9 * min(a, bb), 0.9 * hh))
    e = float(exponent)
    th = np.linspace(0.0, 2 * math.pi, segs, endpoint=False)
    ct, st = np.cos(th), np.sin(th)
    ex = 2.0 / e
    px = np.sign(ct) * np.abs(ct) ** ex
    pz = np.sign(st) * np.abs(st) ** ex
    # outward horizontal normal of the superellipse |x/a|^e + |z/b|^e = 1
    nx = np.sign(px) * np.abs(px) ** (e - 1.0) / max(a, 1e-9)
    nz = np.sign(pz) * np.abs(pz) ** (e - 1.0) / max(bb, 1e-9)
    nl = np.hypot(nx, nz)
    nx, nz = nx / nl, nz / nl

    # profile rings from the bottom edge up: (radius scale, y, horizontal-normal weight, vertical normal)
    prof = []
    for k in range(steps + 1):                       # bottom corner: phi from -90 to 0 degrees
        phi = -math.pi / 2 + (math.pi / 2) * k / steps
        prof.append((((min(a, bb) - c) + c * math.cos(phi)) / min(a, bb), -hh + c + c * math.sin(phi),
                     math.cos(phi), math.sin(phi)))
    for k in range(steps + 1):                       # top corner: phi from 0 to 90 degrees
        phi = (math.pi / 2) * k / steps
        prof.append((((min(a, bb) - c) + c * math.cos(phi)) / min(a, bb), hh - c + c * math.sin(phi),
                     math.cos(phi), math.sin(phi)))
    V, N = [], []
    for rs, y, wh, wv in prof:
        for i in range(segs):
            V.append([a * px[i] * rs, y, bb * pz[i] * rs])
            N.append([wh * nx[i], wv, wh * nz[i]])
    F = []
    R = len(prof)
    for r in range(R - 1):
        for i in range(segs):
            j = (i + 1) % segs
            p0, p1, p2, p3 = r * segs + i, r * segs + j, (r + 1) * segs + j, (r + 1) * segs + i
            F += [(p0, p1, p2), (p0, p2, p3)]
    # caps
    bot = len(V)
    V.append([0.0, -hh, 0.0]); N.append([0.0, -1.0, 0.0])
    top = len(V)
    V.append([0.0, hh, 0.0]); N.append([0.0, 1.0, 0.0])
    for i in range(segs):
        j = (i + 1) % segs
        F.append((bot, j, i))
        F.append((top, (R - 1) * segs + i, (R - 1) * segs + j))
    return (np.array(V, dtype=np.float64), np.array(N, dtype=np.float64), np.array(F, dtype=np.int64))


def _subdivide(V, N, F, passes):
    """Split every triangle into four, `passes` times. More vertices let per-vertex lighting
    (including the plastic highlight) show up in the middle of a flat face."""
    for _ in range(passes):
        V, N = list(map(list, V)), list(map(list, N))
        cache, out = {}, []

        def mid(a, b):
            k = (a, b) if a < b else (b, a)
            if k not in cache:
                v = [(V[a][i] + V[b][i]) / 2.0 for i in range(3)]
                n = [(N[a][i] + N[b][i]) for i in range(3)]
                ln = math.sqrt(sum(c * c for c in n)) or 1.0
                cache[k] = len(V)
                V.append(v)
                N.append([c / ln for c in n])
            return cache[k]
        for a, b, c in F:
            ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
            out += [(a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)]
        F = out
    return np.array(V, dtype=np.float64), np.array(N, dtype=np.float64), np.array(F, dtype=np.int64)


def _taper(V, height, bottom, top):
    t = V[:, 1] / max(height, 1e-9) + 0.5
    sx = bottom[0] + (top[0] - bottom[0]) * t
    sz = bottom[1] + (top[1] - bottom[1]) * t
    V = V.copy()
    V[:, 0] *= sx
    V[:, 2] *= sz
    return V


@lru_cache(maxsize=64)
def sphere_mesh(size, segs=18, rings=10):
    V, N, F = [], [], []
    for r in range(rings + 1):
        phi = math.pi * r / rings
        for i in range(segs):
            th = 2 * math.pi * i / segs
            n = (math.sin(phi) * math.cos(th), math.cos(phi), math.sin(phi) * math.sin(th))
            V.append([n[0] * size[0] / 2, n[1] * size[1] / 2, n[2] * size[2] / 2])
            N.append(list(n))
    for r in range(rings):
        for i in range(segs):
            j = (i + 1) % segs
            a, b, c, d = r * segs + i, r * segs + j, (r + 1) * segs + j, (r + 1) * segs + i
            F += [(a, b, c), (a, c, d)]
    return np.array(V), np.array(N), np.array(F, dtype=np.int64)


_OBJ_CACHE = {}


def obj_mesh(path, scale=1.0):
    """Load a Wavefront .obj (v, vn, f lines; quads and polygons are fanned into triangles).
    Normals come from the file, or are smoothed from the faces when the file has none."""
    import os
    key = (str(path), os.path.getmtime(path), float(scale))
    if key in _OBJ_CACHE:
        return _OBJ_CACHE[key]
    verts, norms, faces = [], [], []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            t = line.split()
            if not t:
                continue
            if t[0] == "v":
                verts.append([float(x) for x in t[1:4]])
            elif t[0] == "vn":
                norms.append([float(x) for x in t[1:4]])
            elif t[0] == "f":
                ids = []
                for tok in t[1:]:
                    p = tok.split("/")
                    vi = int(p[0])
                    ni = int(p[2]) if len(p) > 2 and p[2] else 0
                    ids.append((vi - 1 if vi > 0 else len(verts) + vi, ni - 1 if ni > 0 else (len(norms) + ni if ni < 0 else -1)))
                for k in range(1, len(ids) - 1):
                    faces.append((ids[0], ids[k], ids[k + 1]))
    if not verts or not faces:
        raise ValueError(f"{path}: no vertices or faces found")
    if len(faces) > 6000:
        raise ValueError(f"{path}: {len(faces)} triangles is too many for a part (limit 6000); decimate it first")
    V, N, F = [], [], []
    use_file_normals = bool(norms) and all(n >= 0 for f in faces for _, n in f)
    for f in faces:
        base = len(V)
        for vi, ni in f:
            V.append(verts[vi])
            N.append(norms[ni] if use_file_normals else [0, 0, 0])
        F.append((base, base + 1, base + 2))
    V, N, F = np.array(V) * float(scale), np.array(N, dtype=np.float64), np.array(F, dtype=np.int64)
    if not use_file_normals:                         # smooth by position, so curved parts look round
        fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
        keyed = {}
        for fi, tri in enumerate(F):
            for vi in tri:
                keyed.setdefault(tuple(np.round(V[vi], 4)), []).append(fi)
        for vi in range(len(V)):
            fs = keyed[tuple(np.round(V[vi], 4))]
            N[vi] = fn[fs].sum(axis=0)
    ln = np.linalg.norm(N, axis=1, keepdims=True)
    N = N / np.maximum(ln, 1e-12)
    _OBJ_CACHE[key] = (V, N, F)
    return _OBJ_CACHE[key]


@lru_cache(maxsize=64)
def decal_head_mesh(radius, height, arc_deg, cols=16):
    """A strip that hugs the front of a round head, with UVs for a printed face. u runs left to right
    as the viewer sees it, v runs top to bottom."""
    V, N, UV, F = [], [], [], []
    for r, y in ((0, height / 2.0), (1, -height / 2.0)):
        for i in range(cols + 1):
            th = math.radians(arc_deg) * (i / cols - 0.5)
            V.append([radius * math.sin(th), y, radius * math.cos(th)])
            N.append([math.sin(th), 0.0, math.cos(th)])
            UV.append([i / cols, float(r)])
    for i in range(cols):
        a, b, c, d = i, i + 1, cols + 1 + i + 1, cols + 1 + i
        F += [(a, b, c), (a, c, d)]
    return np.array(V), np.array(N), np.array(F, dtype=np.int64), np.array(UV)


@lru_cache(maxsize=64)
def decal_quad_mesh(w, h):
    V = [[-w / 2, h / 2, 0], [w / 2, h / 2, 0], [w / 2, -h / 2, 0], [-w / 2, -h / 2, 0]]
    N = [[0, 0, 1]] * 4
    UV = [[0, 0], [1, 0], [1, 1], [0, 1]]
    return np.array(V, float), np.array(N, float), np.array([(0, 1, 2), (0, 2, 3)], dtype=np.int64), np.array(UV, float)


def get_mesh(shape, size, bevel, extra=None):
    """extra (a dict or None) can hold: top, bottom ([sx, sz] width ratios at each end), subdiv (int),
    file and scale (for shape 'obj')."""
    extra = extra or {}
    size = tuple(round(float(s), 5) for s in size)
    key = (shape, size, round(float(bevel or 0), 5), tuple(extra.get("top", (1, 1))), tuple(extra.get("bottom", (1, 1))),
           int(extra.get("subdiv", 0)), extra.get("file"), extra.get("scale", 1.0))
    return _get_mesh_cached(key)


def get_colors(shape, extra=None):
    """Per-vertex colours (n,3 in 0..1, -1 where the piece's own colour shows) for LDraw meshes, else None."""
    if shape != "ldraw":
        return None
    from . import ldraw
    return ldraw.load_mesh((extra or {}).get("file"), 1.0)[3]


@lru_cache(maxsize=2048)
def _get_mesh_cached(key):
    shape, size, bevel, top, bottom, subdiv, file, scale = key
    if shape == "box":
        V, N, F = box_mesh(size, bevel if size and min(size) > 0.09 else 0.0)
    elif shape == "head":
        V, N, F = prism_mesh(size, 4.0, round(min(0.22, 0.2 * size[1]), 4))
    elif shape == "cylinder":
        V, N, F = prism_mesh(size, 2.0, round(float(min(bevel, 0.3 * min(size))), 4), 32, 2)
    elif shape == "stud":       # a low round stud for floors and plates: fewer sides than a prop cylinder
        V, N, F = prism_mesh(size, 2.0, round(float(min(bevel, 0.3 * min(size))), 4), 16, 1)
    elif shape == "sphere":
        V, N, F = sphere_mesh(size)
    elif shape == "obj":
        V, N, F = obj_mesh(file, scale)
    elif shape == "ldraw":
        from . import ldraw
        V, N, F, _C = ldraw.load_mesh(file, 1.0)
    else:
        raise ValueError(f"unknown shape '{shape}'")
    if shape not in ("obj", "ldraw") and (tuple(top) != (1, 1) or tuple(bottom) != (1, 1)):
        V = _taper(V, size[1], bottom, top)
    if subdiv:
        V, N, F = _subdivide(V, N, F, subdiv)
    return V, N, F
