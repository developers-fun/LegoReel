"""R6 rig: exact Roblox sizes, Motor6D joints, forward kinematics, part meshes.

Conventions (see docs/SPEC.md): Y-up, right-handed, character faces -Z, studs.
Joint rotation: R = Rx * Ry * Rz (CFrame.Angles).  Useful signs (right-handed):
  shoulder/hip rx>0 swings the limb FORWARD (-Z); rz>0 swings the RIGHT limb outward (+X)
  neck rx>0 looks UP, ry>0 looks to the character's LEFT; root rx>0 leans BACK.
Pose root "pos" is an OFFSET of the torso from the standing rest position (0, 3, 0)
in the character frame; root_cf is the character frame (origin on the floor).
"""
from __future__ import annotations
import math
from functools import lru_cache
import numpy as np
from .mesh import Mesh

PARTS = ["Head", "Torso", "Left Arm", "Right Arm", "Left Leg", "Right Leg"]
JOINTS = ["Neck", "Right Shoulder", "Left Shoulder", "Right Hip", "Left Hip"]
PART_SIZE = {"Head": (2, 1, 1), "Torso": (2, 2, 1), "Left Arm": (1, 2, 1), "Right Arm": (1, 2, 1),
             "Left Leg": (1, 2, 1), "Right Leg": (1, 2, 1)}
HEAD_VISUAL = (1.25, 1.2, 1.25)          # rendered extent of the rounded head mesh
VISUAL_SIZE = dict(PART_SIZE, Head=HEAD_VISUAL)
STAND_TORSO_Y = 3.0
V_UP = True   # UV convention: v=1 is the TOP row of the image (OpenGL style, renderer flips on upload)
TEMPLATE_W, TEMPLATE_H = 585, 559

JOINT_DEF = {
    "Neck": ("Torso", "Head", (0, 1, 0), (0, -0.5, 0)),
    "Right Shoulder": ("Torso", "Right Arm", (1, 0.5, 0), (-0.5, 0.5, 0)),
    "Left Shoulder": ("Torso", "Left Arm", (-1, 0.5, 0), (0.5, 0.5, 0)),
    "Right Hip": ("Torso", "Right Leg", (1, -1, 0), (0.5, 1, 0)),
    "Left Hip": ("Torso", "Left Leg", (-1, -1, 0), (-0.5, 1, 0)),
}


def translate(x=0.0, y=0.0, z=0.0):
    m = np.eye(4)
    if hasattr(x, "__len__"):
        x, y, z = x
    m[:3, 3] = (x, y, z)
    return m


def euler_to_matrix(rx=0.0, ry=0.0, rz=0.0, degrees=True):
    """4x4 rotation R = Rx*Ry*Rz (CFrame.Angles order)."""
    if hasattr(rx, "__len__"):
        rx, ry, rz = rx
    if degrees:
        rx, ry, rz = math.radians(rx), math.radians(ry), math.radians(rz)
    ca, sa, cb, sb, cc, sc = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    m = np.eye(4)
    m[:3, :3] = [[cb * cc, -cb * sc, sb],
                 [ca * sc + sa * sb * cc, ca * cc - sa * sb * sc, -sa * cb],
                 [sa * sc - ca * sb * cc, sa * cc + ca * sb * sc, ca * cb]]
    return m


def matrix_to_euler(m, degrees=True):
    """Inverse of euler_to_matrix (R = Rx*Ry*Rz)."""
    r = np.asarray(m)[:3, :3]
    b = math.asin(max(-1.0, min(1.0, r[0, 2])))
    if abs(r[0, 2]) < 0.999999:
        a = math.atan2(-r[1, 2], r[2, 2])
        c = math.atan2(-r[0, 1], r[0, 0])
    else:
        a = math.atan2(r[2, 1], r[1, 1])
        c = 0.0
    out = (a, b, c)
    return tuple(math.degrees(v) for v in out) if degrees else out


def cframe(pos=(0, 0, 0), rot_deg=(0, 0, 0)):
    """4x4 from position and euler degrees (Rx*Ry*Rz)."""
    m = euler_to_matrix(*rot_deg)
    m[:3, 3] = pos
    return m


def yaw_matrix(deg):
    return euler_to_matrix(0, deg, 0)


_JB = {k: (translate(*v[2]), np.linalg.inv(translate(*v[3]))) for k, v in JOINT_DEF.items()}


def _joint_rot(pose, name):
    v = pose.get(name)
    return euler_to_matrix(*v) if v is not None else np.eye(4)


def part_models(pose: dict, root_cf=None) -> dict:
    """Forward kinematics: part name -> world 4x4 at the part center."""
    root_cf = np.eye(4) if root_cf is None else np.asarray(root_cf, float)
    r = pose.get("root") or {}
    pos = r.get("pos")
    rot = r.get("rot")
    off = tuple(pos) if pos is not None else (0.0, 0.0, 0.0)
    torso = root_cf @ translate(off[0], STAND_TORSO_Y + off[1], off[2])
    if rot is not None:
        torso = torso @ euler_to_matrix(*rot)
    out = {"Torso": torso}
    for j, (_, child, _, _) in JOINT_DEF.items():
        c0, c1i = _JB[j]
        out[child] = torso @ c0 @ _joint_rot(pose, j) @ c1i
    return out


_CORNERS = {}


def _corners(part):
    if part not in _CORNERS:
        h = np.array(VISUAL_SIZE[part]) / 2
        _CORNERS[part] = np.array([[sx * h[0], sy * h[1], sz * h[2], 1] for sx in (-1, 1)
                                   for sy in (-1, 1) for sz in (-1, 1)])
    return _CORNERS[part]


def lowest_y(pose, root_cf=None) -> float:
    ms = part_models(pose, root_cf)
    return min(float((_corners(p) @ ms[p].T)[:, 1].min()) for p in PARTS)


def ground_lift(pose) -> float:
    """How far the pose must be lifted (>=0) so no part goes below the floor (y=0)."""
    return max(0.0, -lowest_y(pose))


def with_root_offset(pose, dy=0.0):
    r = dict(pose.get("root") or {})
    p = r.get("pos") or (0.0, 0.0, 0.0)
    r["pos"] = (p[0], p[1] + dy, p[2])
    r.setdefault("rot", (0.0, 0.0, 0.0))
    out = dict(pose)
    out["root"] = r
    return out


# ---------------------------------------------------------------- geometry helpers
def _fix_winding(pos, nrm, idx):
    idx = np.asarray(idx, np.int64).reshape(-1, 3).copy()
    p0, p1, p2 = pos[idx[:, 0]], pos[idx[:, 1]], pos[idx[:, 2]]
    fn = np.cross(p1 - p0, p2 - p0)
    vn = nrm[idx[:, 0]] + nrm[idx[:, 1]] + nrm[idx[:, 2]]
    bad = (fn * vn).sum(1) < 0
    idx[bad] = idx[bad][:, [0, 2, 1]]
    return idx


_FACES = [  # name, normal, u axis, v axis (a x b = n, so winding is CCW from outside)
    ("right", (1, 0, 0), (0, 0, -1), (0, 1, 0)),
    ("left", (-1, 0, 0), (0, 0, 1), (0, 1, 0)),
    ("top", (0, 1, 0), (1, 0, 0), (0, 0, -1)),
    ("bottom", (0, -1, 0), (-1, 0, 0), (0, 0, -1)),
    ("back", (0, 0, 1), (1, 0, 0), (0, 1, 0)),
    ("front", (0, 0, -1), (-1, 0, 0), (0, 1, 0)),
]


def _samples(h, rlo, rhi, k):
    t = np.linspace(0, 1, k + 1)
    lo = [-h] if rlo <= 1e-9 else -h + rlo * t
    hi = [h] if rhi <= 1e-9 else h - rhi * t[::-1]
    return np.unique(np.round(np.concatenate([lo, hi]), 9))


def rounded_box(size, radius=0.0, seg=3, uv_fn=None, center=(0, 0, 0)) -> Mesh:
    """Box with corner radii. radius: scalar | (rx,ry,rz) | 6-tuple (-x,+x,-y,+y,-z,+z).
    Flat faces stay flat, normals are smooth across bevels, bevel UVs extend the adjacent face's UV
    (uv_fn(face, u, v, pos)->(U,V); default 0..1 per face)."""
    half = np.array(size, float) / 2
    rad = np.atleast_1d(np.asarray(radius, float))
    if rad.size == 1: rad = np.repeat(rad, 6)
    elif rad.size == 3: rad = np.repeat(rad, 2)
    rlo = np.minimum(rad[0::2], half * 0.999); rhi = np.minimum(rad[1::2], half * 0.999)
    # keep lo/hi bevels from overlapping
    over = rlo + rhi > 2 * half * 0.999
    rlo = np.where(over, half * 0.999, rlo); rhi = np.where(over, half * 0.999, rhi)
    smooth = max(rlo.max(), rhi.max()) > 1e-9
    pos_l, nrm_l, uv_l, idx_l = [], [], [], []
    off = 0
    for fname, n, a, b in _FACES:
        n, a, b = np.array(n, float), np.array(a, float), np.array(b, float)
        ia, ib, inn = int(np.argmax(abs(a))), int(np.argmax(abs(b))), int(np.argmax(abs(n)))
        ha, hb = half[ia], half[ib]
        sa, sb = _samples(ha, rlo[ia], rhi[ia], seg), _samples(hb, rlo[ib], rhi[ib], seg)
        A, B = np.meshgrid(sa, sb, indexing="ij")
        P = (n * half[inn])[None, None, :] + A[..., None] * a + B[..., None] * b
        P = P.reshape(-1, 3)
        # u/v along the face direction (a/b may point to -axis)
        U = ((A * (a[ia]) / ha + 1) / 2).reshape(-1) if False else ((A / ha + 1) / 2).reshape(-1)
        V = ((B / hb + 1) / 2).reshape(-1)
        if smooth:
            inner = np.clip(P, -(half - rlo), half - rhi)
            dlt = P - inner
            rr = np.where(dlt >= 0, np.maximum(rhi, 1e-6), np.maximum(rlo, 1e-6))
            d = dlt / rr
            ln = np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-12)
            u = d / ln
            pos = inner + u * rr
            nr = u / rr
            nr /= np.maximum(np.linalg.norm(nr, axis=1, keepdims=True), 1e-12)
        else:
            pos, nr = P, np.tile(n, (len(P), 1))
        if uv_fn is None:
            uv = np.c_[U, V]
        else:
            uu, vv = uv_fn(fname, U, V, pos)
            uv = np.c_[uu, vv]
        na, nb = len(sa), len(sb)
        ii, jj = np.meshgrid(np.arange(na - 1), np.arange(nb - 1), indexing="ij")
        v00 = (ii * nb + jj).ravel() + off
        v10 = ((ii + 1) * nb + jj).ravel() + off
        v11 = ((ii + 1) * nb + jj + 1).ravel() + off
        v01 = (ii * nb + jj + 1).ravel() + off
        idx_l += [np.c_[v00, v10, v11], np.c_[v00, v11, v01]]
        pos_l.append(pos + np.asarray(center)); nrm_l.append(nr); uv_l.append(uv)
        off += len(P)
    return Mesh(np.concatenate(pos_l), np.concatenate(nrm_l), np.concatenate(uv_l), np.concatenate(idx_l))


_BUILD_STYLE = ["smooth"]


def box_mesh(size=(1, 1, 1), center=(0, 0, 0), radius=None, seg=2) -> Mesh:
    """radius=None -> small automatic bevel in 'smooth' style, razor edges in 'classic'."""
    if radius is None:
        if _BUILD_STYLE[0] == "smooth":
            return rounded_box(size, min(0.035, 0.25 * min(size)), 1, None, center)
        radius = 0.0
    return rounded_box(size, radius, seg, None, center)


def sphere_mesh(radii=(0.5, 0.5, 0.5), seg=14, center=(0, 0, 0)) -> Mesh:
    if np.isscalar(radii):
        radii = (radii,) * 3
    rad = np.array(radii, float)
    nlat, nlon = seg, seg * 2
    la = np.linspace(0, math.pi, nlat + 1)
    lo = np.linspace(0, 2 * math.pi, nlon + 1)
    LA, LO = np.meshgrid(la, lo, indexing="ij")
    u = np.stack([np.sin(LA) * np.cos(LO), np.cos(LA), np.sin(LA) * np.sin(LO)], -1).reshape(-1, 3)
    pos = u * rad + np.asarray(center)
    nr = u / rad
    nr /= np.linalg.norm(nr, axis=1, keepdims=True)
    uv = np.stack([LO / (2 * math.pi), 1 - LA / math.pi], -1).reshape(-1, 2)
    ii, jj = np.meshgrid(np.arange(nlat), np.arange(nlon), indexing="ij")
    a = (ii * (nlon + 1) + jj).ravel()
    idx = np.concatenate([np.c_[a, a + nlon + 1, a + nlon + 2], np.c_[a, a + nlon + 2, a + 1]])
    return Mesh(pos, nr, uv, _fix_winding(pos, nr, idx))


def cylinder_mesh(radius=0.5, height=1.0, seg=20, axis="y", center=(0, 0, 0),
                  radius_top=None, cap=True) -> Mesh:
    rt = radius if radius_top is None else radius_top
    th = np.linspace(0, 2 * math.pi, seg + 1)
    c, s = np.cos(th), np.sin(th)
    h2 = height / 2
    bot = np.c_[radius * c, np.full_like(c, -h2), radius * s]
    top = np.c_[rt * c, np.full_like(c, h2), rt * s]
    slope = (radius - rt) / max(height, 1e-9)
    nside = np.c_[c, np.full_like(c, slope), s]
    nside /= np.linalg.norm(nside, axis=1, keepdims=True)
    pos = [bot, top]; nrm = [nside, nside]
    uv = [np.c_[th / (2 * math.pi), np.zeros_like(c)], np.c_[th / (2 * math.pi), np.ones_like(c)]]
    k = np.arange(seg)
    idx = [np.c_[k, k + seg + 1, k + seg + 2], np.c_[k, k + seg + 2, k + 1]]
    base = 2 * (seg + 1)
    if cap:
        for y, rr, ny in ((-h2, radius, -1.0), (h2, rt, 1.0)):
            ring = np.c_[rr * c, np.full_like(c, y), rr * s]
            cen = np.array([[0, y, 0]])
            pos += [cen, ring]
            nrm += [np.tile([0, ny, 0], (seg + 2, 1))]
            uv += [np.full((1, 2), 0.5), np.c_[0.5 + 0.5 * c, 0.5 + 0.5 * s]]
            kk = np.arange(seg)
            idx.append(np.c_[np.full(seg, base), base + 1 + kk, base + 2 + kk])
            base += seg + 2
    pos = np.concatenate(pos); nrm = np.concatenate(nrm)
    idx = _fix_winding(pos, nrm, np.concatenate(idx))
    perm = {"y": [0, 1, 2], "x": [1, 0, 2], "z": [0, 2, 1]}[axis]
    pos = pos[:, perm]; nrm = nrm[:, perm]
    return Mesh(pos + np.asarray(center), nrm, np.concatenate(uv), _fix_winding(pos, nrm, idx))


def cone_mesh(radius=0.5, height=1.0, seg=12, center=(0, 0, 0)) -> Mesh:
    return cylinder_mesh(radius, height, seg, "y", center, radius_top=0.0, cap=True)


def arc_mesh(radius, thickness, depth, a0=0.0, a1=180.0, seg=24, center=(0, 0, 0)) -> Mesh:
    """Rectangular-section band swept in the XY plane (angle from +X, CCW), depth along Z."""
    th = np.radians(np.linspace(a0, a1, seg + 1))
    ro, ri = radius + thickness / 2, radius - thickness / 2
    z0, z1 = -depth / 2, depth / 2
    ring = []  # 4 corners per station: outer-front, outer-back, inner-back, inner-front
    for t in th:
        c, s = math.cos(t), math.sin(t)
        ring.append([(ro * c, ro * s, z0), (ro * c, ro * s, z1), (ri * c, ri * s, z1), (ri * c, ri * s, z0)])
    ring = np.array(ring)
    pos, idx = [], []
    for e in range(4):  # one quad strip per edge with its own flat-ish normals
        a, b = ring[:, e], ring[:, (e + 1) % 4]
        base = sum(len(p) for p in pos)
        pos += [a, b]
        n = len(th)
        k = np.arange(n - 1)
        idx += [np.c_[k, k + n, k + n + 1] + base, np.c_[k, k + n + 1, k + 1] + base]
    pos = np.concatenate(pos)
    cen = np.array([center[0], center[1], 0.0])
    nr = pos - np.array([0, 0, 0])
    nr = nr / np.maximum(np.linalg.norm(nr, axis=1, keepdims=True), 1e-9)
    idx = np.concatenate(idx)
    # approximate normals: outward from section center for shading
    sec = np.zeros_like(pos)
    for e in range(2 * 4):
        pass
    cen_s = np.array([[radius * math.cos(t), radius * math.sin(t), 0.0] for t in th])
    nr = np.concatenate([pos[i * len(th):(i + 1) * len(th)] - cen_s for i in range(8)])
    nr /= np.maximum(np.linalg.norm(nr, axis=1, keepdims=True), 1e-9)
    idx = _fix_winding(pos, nr, idx)
    return Mesh(pos + np.asarray(center), nr, np.zeros((len(pos), 2)), idx)


# ---------------------------------------------------------------- classic clothing template (585x559)
_RA = {"left": (19, 355, 64, 128), "back": (85, 355, 64, 128), "right": (151, 355, 64, 128),
       "front": (217, 355, 64, 128), "top": (217, 289, 64, 64), "bottom": (217, 485, 64, 64)}
_LA = {"front": (308, 355, 64, 128), "left": (374, 355, 64, 128), "back": (440, 355, 64, 128),
       "right": (506, 355, 64, 128), "top": (308, 289, 64, 64), "bottom": (308, 485, 64, 64)}
TEMPLATE_RECTS = {
    "Torso": {"top": (231, 8, 128, 64), "bottom": (231, 204, 128, 64), "front": (231, 74, 128, 128),
              "back": (427, 74, 128, 128), "right": (165, 74, 64, 128), "left": (361, 74, 64, 128)},
    "Right Arm": _RA, "Left Arm": _LA, "Right Leg": _RA, "Left Leg": _LA,
}


def _vconv(v_up):
    return v_up if V_UP else 1.0 - v_up


def template_uv(part, face, u, v):
    x, y, w, h = TEMPLATE_RECTS[part][face]
    px = x + u * w
    py = y + (1.0 - v) * h
    return px / TEMPLATE_W, _vconv(1.0 - py / TEMPLATE_H)


_EDGE_STYLE = ["smooth"]
_MESH_CACHE: dict = {}
STYLES = ("smooth", "classic")


def set_edge_style(style: str):
    """'smooth' (default: rounded shoulders/feet/torso, smooth normals) or 'classic' (crisp blocks)."""
    if style not in STYLES:
        raise ValueError(f"edge style must be one of {STYLES}")
    _EDGE_STYLE[0] = style
    _MESH_CACHE.clear()


def get_edge_style() -> str:
    return _EDGE_STYLE[0]


# (radius spec, bevel segments) per part and style; 6-tuples are (-x,+x,-y,+y,-z,+z)
_RADII = {
    "classic": {"Head": ((0.30, 0.42, 0.36), 4), "Torso": (0.06, 2), "arm": (0.05, 2), "leg": (0.05, 2)},
    "smooth": {"Head": ((0.36, 0.46, 0.42), 5),
               "Torso": ((0.2, 0.2, 0.2, 0.2, 0.2, 0.2), 4),
               "arm": ((0.2, 0.2, 0.26, 0.46, 0.2, 0.2), 3),     # soft hand end (-y), shoulder cap (+y)
               "leg": ((0.17, 0.17, 0.3, 0.2, 0.17, 0.17), 3)},  # soft toe/heel end (-y), rounded hip (+y)
}


def _build_part(name, style):
    W, H, D = HEAD_VISUAL
    r = _RADII[style]
    if name == "Head":
        def uv(face, u, v, pos):
            if face == "front":
                du = 0.5 - pos[:, 0] / W
                dv = 0.5 + pos[:, 1] / H
                return np.clip(du, 0, 1) * 0.5, _vconv(np.clip(dv, 0, 1))
            return np.full(len(u), 0.75), np.full(len(u), 0.5)
        return rounded_box(HEAD_VISUAL, r["Head"][0], r["Head"][1], uv)
    key = "Torso" if name == "Torso" else ("arm" if "Arm" in name else "leg")
    return rounded_box(PART_SIZE[name], r[key][0], r[key][1], lambda f, u, v, p: template_uv(name, f, u, v))


def part_mesh(name: str, style: str = None) -> Mesh:
    """Cached local-space mesh centered on the part. Head UV: left half of a 2:1 atlas is the face decal
    (planar front projection), right half plain skin. Others use the 585x559 template (bevel UVs extend
    the adjacent face's UV)."""
    style = style or _EDGE_STYLE[0]
    k = (name, style)
    if k not in _MESH_CACHE:
        _MESH_CACHE[k] = _build_part(name, style)
    return _MESH_CACHE[k]
