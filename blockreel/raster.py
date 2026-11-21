"""Software rasterizer: z-buffered Gouraud-shaded meshes over a sky and a ray-cast ground.

Pure numpy and Pillow. No GPU, no OpenGL. Slower than a GPU renderer, but it runs the same
on any PC with Python. Lighting is computed per vertex in linear colour: a warm sun, a sky/
ground hemisphere ambient, a soft fill from the camera side, and a little ambient occlusion
near the ground. The ground receives a projected, blurred sun shadow from every character
and prop, plus a small contact shadow under each character.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image

from . import meshes

EPS = 1e-7
NEAR = 0.05

try:
    _BILINEAR = Image.Resampling.BILINEAR
except AttributeError:  # Pillow < 9.1
    _BILINEAR = Image.BILINEAR


class Framebuffer:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.color = np.zeros((h, w, 3), dtype=np.uint8)
        self.depth = np.full((h, w), np.inf, dtype=np.float32)


# ---- lighting -----------------------------------------------------------------

def _smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


class Lighting:
    """Per-vertex lighting. All colours are 0-255 on the way in and out, linear inside."""

    def __init__(self, light, ground_y, fog_color, fog_distance):
        d = np.array(light["direction"], dtype=np.float64)
        self.sun_dir = d / np.linalg.norm(d)
        self.sun_col = np.array(light["sun_color"], dtype=np.float64) / 255.0
        self.sun_k = float(light["sun_strength"])
        self.sky_col = (np.array(light["sky_color"], dtype=np.float64) / 255.0) ** 2.2
        self.gnd_col = (np.array(light["ground_color"], dtype=np.float64) / 255.0) ** 2.2
        self.amb_k = float(light["ambient"])
        self.fill_k = float(light["fill_strength"])
        self.ao_k = float(light["ao"])
        self.spec_pow = float(light.get("spec_power", 36.0))
        self.ground_y = float(ground_y)
        self.fog_col = np.array(fog_color, dtype=np.float64)
        self.fog_d = max(float(fog_distance), 1e-3)

    def fill_dir_for(self, cam):
        f = -cam.fwd + 0.35 * cam.up
        return f / np.linalg.norm(f)

    def shade(self, normals, base, height, depth, fill_dir, view=None, spec=0.0):
        """normals (n,3) unit, base (3,) 0-255, height above ground (n,), depth (n,) -> (n,3) 0-255."""
        lin = (np.asarray(base, dtype=np.float64) / 255.0) ** 2.2
        if lin.ndim == 1:
            lin = lin[None, :]
        w = (normals[:, 1] * 0.5 + 0.5)[:, None]
        hemi = self.gnd_col[None, :] * (1.0 - w) + self.sky_col[None, :] * w
        sun = np.maximum(0.0, normals @ self.sun_dir)[:, None] * self.sun_col[None, :] * self.sun_k
        fill = np.maximum(0.0, normals @ fill_dir)[:, None] * self.fill_k
        ao = 1.0 - self.ao_k * (1.0 - _smooth(height / 1.6))
        light = (self.amb_k * hemi + sun + fill) * ao[:, None]
        out = lin * light
        if spec > 0 and view is not None:        # plastic highlight (Blinn-Phong) plus a faint rim
            hv = self.sun_dir[None, :] + view
            hv /= np.maximum(np.linalg.norm(hv, axis=1, keepdims=True), 1e-9)
            sp = np.maximum(0.0, np.einsum("ij,ij->i", normals, hv)) ** self.spec_pow
            rim = (1.0 - np.clip(np.einsum("ij,ij->i", normals, view), 0.0, 1.0)) ** 3 * 0.10
            out = out + (sp * spec * self.sun_k)[:, None] * self.sun_col[None, :] + (rim * spec)[:, None] * self.sky_col[None, :]
        out = np.where(out < 0.8, out, 0.8 + 0.2 * np.tanh((out - 0.8) / 0.2))   # soft highlight roll-off
        srgb = np.clip(out, 0.0, 1.0) ** (1.0 / 2.2) * 255.0
        fog = (np.clip(depth / self.fog_d, 0.0, 1.0) ** 1.5)[:, None]
        return srgb * (1.0 - fog) + self.fog_col[None, :] * fog


# ---- sky ----------------------------------------------------------------------

def fill_sky(fb, cam, top, bottom, sun_dir, glow, clouds=None):
    """Sky gradient by elevation angle, with a soft sun glow. Built at 1/8 size, then enlarged."""
    sw, sh = max(8, fb.w // 8), max(8, fb.h // 8)
    tanf = math.tan(math.radians(cam.fov) / 2.0)
    aspect = fb.w / fb.h
    xs = ((2.0 * (np.arange(sw) + 0.5) / sw) - 1.0) * tanf * aspect
    ys = (1.0 - (2.0 * (np.arange(sh) + 0.5) / sh)) * tanf
    d = (cam.up[None, None, :] * ys[:, None, None] + cam.right[None, None, :] * xs[None, :, None]
         + cam.fwd[None, None, :])
    d /= np.linalg.norm(d, axis=2, keepdims=True)
    elev = np.arcsin(np.clip(d[:, :, 1], -1.0, 1.0))
    t = np.clip(elev / 0.95, 0.0, 1.0) ** 0.65
    t = t[:, :, None]
    col = np.array(bottom, np.float32)[None, None, :] * (1 - t) + np.array(top, np.float32)[None, None, :] * t
    if glow > 0:
        c = np.clip(d @ sun_dir, 0.0, 1.0)
        g = (c ** 600) * 1.0 + (c ** 24) * 0.35 + (c ** 6) * 0.10
        col = col + (g * glow * 255.0)[:, :, None] * np.array([1.0, 0.95, 0.82], np.float32)[None, None, :]
    if clouds and clouds.get("coverage", 0) > 0:
        # clouds live on a flat layer overhead: project each view ray onto it, then sample fractal noise
        up = np.clip(d[:, :, 1], 0.0, 1.0)
        k = 1.0 / (up + 0.22)
        u = d[:, :, 0] * k * clouds.get("scale", 1.0) + 3.1
        v = d[:, :, 2] * k * clouds.get("scale", 1.0) + 7.7
        n = _fbm(u, v)
        cov = float(clouds["coverage"])
        a = np.clip((n - (1.0 - cov)) / 0.22, 0.0, 1.0)
        a = a * a * (3.0 - 2.0 * a)
        a *= np.clip((elev - 0.015) / 0.12, 0.0, 1.0)            # fade into the horizon haze
        ccol = np.array(clouds.get("color", (255, 255, 255)), np.float32)
        shade = (1.0 - 0.10 * np.clip((n - (1.0 - cov)) / 0.5, 0.0, 1.0))[:, :, None]
        col = col * (1 - a[:, :, None] * clouds.get("opacity", 0.9)) + ccol[None, None, :] * shade * (a[:, :, None] * clouds.get("opacity", 0.9))
    small = Image.fromarray(np.clip(col, 0, 255).astype(np.uint8))
    fb.color[:] = np.asarray(small.resize((fb.w, fb.h), _BILINEAR))


_NOISE = np.random.default_rng(7).random((64, 64)).astype(np.float32)


def _value_noise(u, v):
    iu, iv = np.floor(u), np.floor(v)
    fu, fv = u - iu, v - iv
    fu, fv = fu * fu * (3 - 2 * fu), fv * fv * (3 - 2 * fv)
    i0, j0 = iu.astype(np.int64) & 63, iv.astype(np.int64) & 63
    i1, j1 = (i0 + 1) & 63, (j0 + 1) & 63
    a, b = _NOISE[j0, i0], _NOISE[j0, i1]
    c, d = _NOISE[j1, i0], _NOISE[j1, i1]
    return (a * (1 - fu) + b * fu) * (1 - fv) + (c * (1 - fu) + d * fu) * fv


def _fbm(u, v):
    out = np.zeros_like(u, dtype=np.float32)
    amp, tot = 0.55, 0.0
    for o in range(4):
        out += amp * _value_noise(u * (1.7 ** o) * 1.3, v * (1.7 ** o) * 1.3)
        tot += amp
        amp *= 0.5
    return out / tot


# ---- ground -------------------------------------------------------------------

def _pattern(px, pz, tv, c0, c1, tile, var, linec, line_half, line_k, px_foot, studs=0.0):
    fx, fz = px / tile, pz / tile
    ix, iz = np.floor(fx), np.floor(fz)
    parity = (ix.astype(np.int64) + iz.astype(np.int64)) & 1
    col = np.where(parity[:, None] == 0, c0[None, :], c1[None, :]).astype(np.float32)
    if var > 0:   # each tile gets its own slight brightness, fixed by its position
        hsh = ((ix.astype(np.int64) * 73856093) ^ (iz.astype(np.int64) * 19349663)) & 1023
        col *= (1.0 + (hsh.astype(np.float32) / 1023.0 - 0.5) * 2.0 * var)[:, None]
    if line_k > 0:   # thin grid line on tile borders, anti-aliased by the pixel footprint
        edge = np.minimum(np.minimum(fx - ix, 1.0 - (fx - ix)), np.minimum(fz - iz, 1.0 - (fz - iz))) * tile
        fp = np.maximum(tv * px_foot, 1e-4)
        cover = np.clip((line_half - edge) / fp + 0.5, 0.0, 1.0) * line_k
        col = col * (1.0 - cover[:, None]) + np.asarray(linec, np.float32)[None, :] * cover[:, None]
    if studs > 0:     # a round stud in the middle of each tile: lighter top, darker rim on the side away from the sun
        cx, cz = fx - ix - 0.5, fz - iz - 0.5
        r = np.hypot(cx, cz)
        fp = np.maximum(tv * px_foot, 1e-4) / tile
        top = np.clip((studs - r) / fp + 0.5, 0.0, 1.0)
        rim = np.clip((studs + 0.07 - r) / fp + 0.5, 0.0, 1.0) * (1.0 - top)
        away = np.clip(0.5 + 0.5 * (cx * 0.6 + cz * -0.8) / np.maximum(r, 1e-3), 0.0, 1.0)
        col = col * (1.0 + 0.10 * top)[:, None] * (1.0 - 0.28 * rim * away)[:, None]
    return col


def draw_ground(fb, cam, ground, contact, shadow):
    """Ray-cast the ground plane per pixel, in row chunks to keep memory low.

    contact: list of (x, z, radius, strength) soft dark discs under characters.
    shadow:  None or dict(tex float32 (h, w) in 0..1, minx, minz, res, strength, tint).
    """
    gy = ground["y"]
    h0 = cam.position[1] - gy
    if h0 <= 1e-6:
        return  # camera at or below the ground plane: skip it
    W, H = fb.w, fb.h
    tanf = math.tan(math.radians(cam.fov) / 2.0)
    aspect = W / H
    xs = ((2.0 * (np.arange(W, dtype=np.float32) + 0.5) / W) - 1.0) * tanf * aspect
    r, u, f = (cam.right.astype(np.float32), cam.up.astype(np.float32), cam.fwd.astype(np.float32))
    c0 = np.array(ground["colors"][0], np.float32)
    c1 = np.array(ground["colors"][1], np.float32)
    fogc = np.array(ground["fog_color"], np.float32)
    linec = np.array(ground["line_color"], np.float32)
    tile = ground["tile"]
    fog_d = max(ground["fog_distance"], 1e-3)
    far = ground["far"]
    var = ground["variation"]
    line_half = ground["line_width"] * 0.5
    line_k = ground["line_strength"]
    px_foot = 2.0 * tanf / H            # world size of one pixel per unit distance
    cx, cz = float(cam.position[0]), float(cam.position[2])

    chunk = 256
    for y0 in range(0, H, chunk):
        y1 = min(H, y0 + chunk)
        ys = (1.0 - (2.0 * (np.arange(y0, y1, dtype=np.float32) + 0.5) / H)) * tanf
        dy = u[1] * ys[:, None] + r[1] * xs[None, :] + f[1]
        valid = dy < -1e-6
        if not valid.any():
            continue
        t = np.full(dy.shape, np.inf, dtype=np.float32)
        np.divide(np.float32(-h0), dy, out=t, where=valid)
        valid &= t < far
        if not valid.any():
            continue
        dx = u[0] * ys[:, None] + r[0] * xs[None, :] + f[0]
        dz = u[2] * ys[:, None] + r[2] * xs[None, :] + f[2]
        tv = t[valid]
        px = cx + tv * dx[valid]
        pz = cz + tv * dz[valid]

        col = _pattern(px, pz, tv, c0, c1, tile, var, linec, line_half, line_k, px_foot, ground.get("studs", 0.0))
        for zn in ground.get("zones", ()):     # painted areas: a different floor inside a rectangle
            x0, z0, x1, z1 = zn["rect"]
            inz = (px >= x0) & (px < x1) & (pz >= z0) & (pz < z1)
            if inz.any():
                col[inz] = _pattern(px[inz], pz[inz], tv[inz], np.array(zn["colors"][0], np.float32),
                                    np.array(zn["colors"][1], np.float32), zn["tile"], zn["variation"],
                                    zn["line_color"], zn["line_width"] * 0.5, zn["line_strength"], px_foot, zn.get("studs", 0.0))

        for sx, sz, rad, strength in contact:
            d2 = (px - sx) ** 2 + (pz - sz) ** 2
            s = np.clip(1.0 - d2 / (rad * rad), 0.0, 1.0)
            col *= (1.0 - strength * s * s * (3.0 - 2.0 * s))[:, None]

        if shadow is not None:
            tex = shadow["tex"]
            ui = ((px - shadow["minx"]) * shadow["res"]).astype(np.int32)
            vi = ((pz - shadow["minz"]) * shadow["res"]).astype(np.int32)
            inside = (ui >= 0) & (vi >= 0) & (ui < tex.shape[1]) & (vi < tex.shape[0])
            if inside.any():
                s = np.zeros_like(tv)
                s[inside] = tex[vi[inside], ui[inside]]
                col *= (1.0 - shadow["strength"] * s[:, None] * shadow["tint"][None, :])

        fog = np.clip(tv / fog_d, 0.0, 1.0) ** 1.5
        col = col * (1.0 - fog[:, None]) + fogc[None, :] * fog[:, None]

        sub_color = fb.color[y0:y1]
        sub_depth = fb.depth[y0:y1]
        sub_color[valid] = np.clip(col, 0, 255).astype(np.uint8)
        sub_depth[valid] = tv


# ---- triangles ------------------------------------------------------------------

def fill_tri(fb, xs, ys, zs, cols):
    """Fill one triangle with perspective-correct colour interpolation.

    xs, ys: screen coordinates (3 floats each), zs: camera depth (3), cols: three (3,) arrays
    of 0-255 colours, or one (3,) array for a flat colour.
    """
    x0, x1, x2 = xs
    y0, y1, y2 = ys
    z0, z1, z2 = zs
    minx = max(int(math.floor(min(x0, x1, x2))), 0)
    maxx = min(int(math.ceil(max(x0, x1, x2))), fb.w - 1)
    miny = max(int(math.floor(min(y0, y1, y2))), 0)
    maxy = min(int(math.ceil(max(y0, y1, y2))), fb.h - 1)
    if minx > maxx or miny > maxy:
        return
    area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
    if abs(area) < 1e-12:
        return
    X = (np.arange(minx, maxx + 1, dtype=np.float64) + 0.5)[None, :]
    Y = (np.arange(miny, maxy + 1, dtype=np.float64) + 0.5)[:, None]
    w0 = ((x1 - X) * (y2 - Y) - (x2 - X) * (y1 - Y)) / area
    w1 = ((x2 - X) * (y0 - Y) - (x0 - X) * (y2 - Y)) / area
    w2 = 1.0 - w0 - w1
    inside = (w0 >= -EPS) & (w1 >= -EPS) & (w2 >= -EPS)
    if not inside.any():
        return
    a0, a1, a2 = w0 / z0, w1 / z1, w2 / z2
    inv = a0 + a1 + a2
    inside &= inv > 0
    with np.errstate(divide="ignore", invalid="ignore"):
        z = (1.0 / inv).astype(np.float32)
    sub_depth = fb.depth[miny:maxy + 1, minx:maxx + 1]
    mask = inside & (z < sub_depth)
    if not mask.any():
        return
    sub_depth[mask] = z[mask]
    out = fb.color[miny:maxy + 1, minx:maxx + 1]
    if len(cols) == 3 and not isinstance(cols[0], (int, float, np.floating, np.integer)):
        c0, c1, c2 = cols
        im = inv[mask]
        col = (a0[mask][:, None] * c0 + a1[mask][:, None] * c1 + a2[mask][:, None] * c2) / im[:, None]
        out[mask] = np.clip(col, 0.0, 255.0).astype(np.uint8)
    else:
        out[mask] = np.clip(cols, 0, 255).astype(np.uint8)


def _clip_near_attr(poly):
    """Clip a polygon of rows (x, y, z, r, g, b) in camera space against the near plane."""
    out = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        ina, inb = a[2] >= NEAR, b[2] >= NEAR
        if ina:
            out.append(a)
        if ina != inb:
            u = (NEAR - a[2]) / (b[2] - a[2])
            out.append(a + (b - a) * u)
    return out


_TEX = {}


def load_texture(path):
    """RGBA float array (h, w, 4), 0-255, cached."""
    import os
    key = (str(path), os.path.getmtime(path))
    if key not in _TEX:
        _TEX[key] = np.asarray(Image.open(path).convert("RGBA"), dtype=np.float32)
    return _TEX[key]


def fill_tri_tex(fb, xs, ys, zs, cols, uvs, tex):
    """Textured triangle: perspective-correct uv, bilinear sampling, alpha-blended over what is already there.
    Pixels with alpha above 0.5 also write depth, so later parts in front still cover the print."""
    x0, x1, x2 = xs
    y0, y1, y2 = ys
    z0, z1, z2 = zs
    minx = max(int(math.floor(min(x0, x1, x2))), 0)
    maxx = min(int(math.ceil(max(x0, x1, x2))), fb.w - 1)
    miny = max(int(math.floor(min(y0, y1, y2))), 0)
    maxy = min(int(math.ceil(max(y0, y1, y2))), fb.h - 1)
    if minx > maxx or miny > maxy:
        return
    area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
    if abs(area) < 1e-12:
        return
    X = (np.arange(minx, maxx + 1, dtype=np.float64) + 0.5)[None, :]
    Y = (np.arange(miny, maxy + 1, dtype=np.float64) + 0.5)[:, None]
    w0 = ((x1 - X) * (y2 - Y) - (x2 - X) * (y1 - Y)) / area
    w1 = ((x2 - X) * (y0 - Y) - (x0 - X) * (y2 - Y)) / area
    w2 = 1.0 - w0 - w1
    inside = (w0 >= -EPS) & (w1 >= -EPS) & (w2 >= -EPS)
    if not inside.any():
        return
    a0, a1, a2 = w0 / z0, w1 / z1, w2 / z2
    inv = a0 + a1 + a2
    inside &= inv > 0
    with np.errstate(divide="ignore", invalid="ignore"):
        z = (1.0 / inv).astype(np.float32)
    sub_depth = fb.depth[miny:maxy + 1, minx:maxx + 1]
    mask = inside & (z <= sub_depth * 1.0005)
    if not mask.any():
        return
    im = inv[mask]
    u = (a0[mask] * uvs[0][0] + a1[mask] * uvs[1][0] + a2[mask] * uvs[2][0]) / im
    v = (a0[mask] * uvs[0][1] + a1[mask] * uvs[1][1] + a2[mask] * uvs[2][1]) / im
    th, tw = tex.shape[:2]
    fx = np.clip(u * tw - 0.5, 0, tw - 1.001)
    fy = np.clip(v * th - 0.5, 0, th - 1.001)
    ix, iy = fx.astype(np.int32), fy.astype(np.int32)
    dx, dy = (fx - ix)[:, None], (fy - iy)[:, None]
    t = (tex[iy, ix] * (1 - dx) * (1 - dy) + tex[iy, ix + 1] * dx * (1 - dy)
         + tex[iy + 1, ix] * (1 - dx) * dy + tex[iy + 1, ix + 1] * dx * dy)
    lit = (a0[mask][:, None] * cols[0] + a1[mask][:, None] * cols[1] + a2[mask][:, None] * cols[2]) / im[:, None] / 255.0
    alpha = t[:, 3:4] / 255.0
    out = fb.color[miny:maxy + 1, minx:maxx + 1]
    old = out[mask].astype(np.float32)
    new = np.clip(t[:, :3] * lit, 0, 255) * alpha + old * (1 - alpha)
    out[mask] = new.astype(np.uint8)
    zz = sub_depth[mask]
    sub_depth[mask] = np.where(alpha[:, 0] > 0.5, z[mask], zz)


def _draw_decal(fb, cam, item, lighting, fill_dir):
    ex = item.extra
    if ex["kind"] == "head":
        V, N, F, UV = meshes.decal_head_mesh(round(ex["radius"], 4), round(ex["height"], 4), round(ex["arc"], 3))
    else:
        V, N, F, UV = meshes.decal_quad_mesh(round(ex["w"], 4), round(ex["h"], 4))
    tex = load_texture(ex["image"])
    M = item.model
    R, t = M[:3, :3], M[:3, 3]
    Wv, Nw = V @ R.T + t, N @ R.T
    Nw /= np.maximum(np.linalg.norm(Nw, axis=1, keepdims=True), 1e-12)
    basis = np.stack([cam.right, cam.up, cam.fwd])
    pc = (Wv - cam.position) @ basis.T
    if (pc[:, 2] < NEAR).any():
        return
    view = cam.position - Wv
    view /= np.maximum(np.linalg.norm(view, axis=1, keepdims=True), 1e-9)
    cols = lighting.shade(Nw, (255, 255, 255), Wv[:, 1] - lighting.ground_y, pc[:, 2], fill_dir, view, 0.0)
    tanf = math.tan(math.radians(cam.fov) / 2.0)
    aspect = fb.w / fb.h
    z = pc[:, 2]
    sx = (pc[:, 0] / z / (tanf * aspect) * 0.5 + 0.5) * fb.w
    sy = (0.5 - (pc[:, 1] / z / tanf) * 0.5) * fb.h
    tri_n = Nw[F].sum(axis=1)
    cen = Wv[F].mean(axis=1)
    facing = np.einsum("ij,ij->i", tri_n, cam.position - cen) > 0
    for i in np.nonzero(facing)[0]:
        a, b, c = F[i]
        fill_tri_tex(fb, (sx[a], sx[b], sx[c]), (sy[a], sy[b], sy[c]), (z[a], z[b], z[c]),
                     (cols[a], cols[b], cols[c]), (UV[a], UV[b], UV[c]), tex)


def draw_item(fb, cam, item, lighting, fill_dir, default_bevel):
    """Draw one shape. Back-facing triangles are skipped; the rest are lit per vertex."""
    ex = item.extra or {}
    if item.shape == "decal":
        return _draw_decal(fb, cam, item, lighting, fill_dir)
    bevel = default_bevel if item.bevel is None else item.bevel
    V, N, F = meshes.get_mesh(item.shape, item.size, bevel, ex)
    M = item.model
    R, t = M[:3, :3], M[:3, 3]
    Wv = V @ R.T + t
    Nw = N @ R.T
    Nw /= np.maximum(np.linalg.norm(Nw, axis=1, keepdims=True), 1e-12)

    basis = np.stack([cam.right, cam.up, cam.fwd])
    pc = (Wv - cam.position) @ basis.T            # x right, y up, z depth
    if (pc[:, 2] < NEAR).all():
        return
    spec = float(ex.get("spec", 0.0))
    view = None
    if spec > 0:
        view = cam.position - Wv
        view /= np.maximum(np.linalg.norm(view, axis=1, keepdims=True), 1e-9)
    base = item.color
    explicit = None
    if item.shape == "ldraw":                        # printed or multi-colour parts: colour per vertex
        C = meshes.get_colors(item.shape, ex)
        own = C[:, 0] < 0
        base = np.where(own[:, None], np.asarray(item.color, dtype=np.float64)[None, :], C * 255.0)
        explicit = ~own
    cols = lighting.shade(Nw, base, Wv[:, 1] - lighting.ground_y, np.maximum(pc[:, 2], 0.0), fill_dir, view, spec)

    tri_n = Nw[F].sum(axis=1)
    cen = Wv[F].mean(axis=1)
    facing = np.einsum("ij,ij->i", tri_n, cam.position - cen) > 0
    if not facing.any():
        return

    tanf = math.tan(math.radians(cam.fov) / 2.0)
    aspect = fb.w / fb.h
    z = np.maximum(pc[:, 2], NEAR)
    sx = (pc[:, 0] / z / (tanf * aspect) * 0.5 + 0.5) * fb.w
    sy = (0.5 - (pc[:, 1] / z / tanf) * 0.5) * fb.h
    ok = pc[:, 2] >= NEAR
    all_ok = ok[F].all(axis=1)

    fx, fy = sx[F], sy[F]
    on = (fx.max(axis=1) >= 0) & (fx.min(axis=1) <= fb.w) & (fy.max(axis=1) >= 0) & (fy.min(axis=1) <= fb.h)
    simple = facing & all_ok & on
    zb = z if explicit is None else np.where(explicit, z * 0.9975, z)      # prints sit just in front of the surface
    for i in np.nonzero(simple)[0]:
        a, b, c = F[i]
        fill_tri(fb, (sx[a], sx[b], sx[c]), (sy[a], sy[b], sy[c]), (zb[a], zb[b], zb[c]),
                 (cols[a], cols[b], cols[c]))

    for i in np.nonzero(facing & ~all_ok)[0]:      # triangles crossing the near plane
        idx = F[i]
        poly = [np.concatenate([pc[j], cols[j]]) for j in idx]
        poly = _clip_near_attr(poly)
        if len(poly) < 3:
            continue
        pts = []
        for p in poly:
            pts.append(((p[0] / p[2] / (tanf * aspect) * 0.5 + 0.5) * fb.w,
                        (0.5 - (p[1] / p[2] / tanf) * 0.5) * fb.h, p[2], p[3:6]))
        for k in range(1, len(pts) - 1):
            a, b, c = pts[0], pts[k], pts[k + 1]
            fill_tri(fb, (a[0], b[0], c[0]), (a[1], b[1], c[1]), (a[2], b[2], c[2]), (a[3], b[3], c[3]))


# ---- shadows ----------------------------------------------------------------------

def _hull(points):
    pts = sorted(set((round(float(x), 5), round(float(y), 5)) for x, y in points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


_UNIT_CORNERS = np.array([[sx, sy, sz] for sx in (-.5, .5) for sy in (-.5, .5) for sz in (-.5, .5)], dtype=np.float64)


def build_shadow(items, cam, light_dir, ground_y, cfg):
    """Project every nearby item along the sun direction onto the ground and return a
    blurred coverage texture, or None when nothing casts a shadow into view."""
    from PIL import ImageDraw, ImageFilter
    if not cfg["enabled"] or light_dir[1] < 0.15:
        return None
    L = light_dir
    polys = []
    for it in items:
        if not it.casts:
            continue
        size = np.array(it.size, dtype=np.float64)
        pts = (_UNIT_CORNERS * size) @ it.model[:3, :3].T + it.model[:3, 3]
        c = pts.mean(axis=0)
        v = c - cam.position
        if np.linalg.norm(v) > cfg["range"] or float(v @ cam.fwd) < -4.0:
            continue
        if pts[:, 1].min() > 14.0:
            continue
        h = pts[:, 1] - ground_y
        proj = pts - L[None, :] * (h / L[1])[:, None]
        polys.append(_hull(np.stack([proj[:, 0], proj[:, 2]], axis=1)))
    polys = [p for p in polys if len(p) >= 3]
    if not polys:
        return None
    allp = np.array([q for p in polys for q in p])
    pad = 1.2
    minx, minz = allp[:, 0].min() - pad, allp[:, 1].min() - pad
    maxx, maxz = allp[:, 0].max() + pad, allp[:, 1].max() + pad
    ext = max(maxx - minx, maxz - minz)
    res = float(np.clip(900.0 / ext, 6.0, 48.0))
    w, h = int(math.ceil((maxx - minx) * res)), int(math.ceil((maxz - minz) * res))
    if w < 2 or h < 2 or w * h > 2.5e6:
        return None
    img = Image.new("L", (w, h), 0)
    dr = ImageDraw.Draw(img)
    for p in polys:
        dr.polygon([((x - minx) * res, (z - minz) * res) for x, z in p], fill=255)
    blur = max(0.6, cfg["softness"] * res)
    img = img.filter(ImageFilter.GaussianBlur(blur))
    tex = np.asarray(img, dtype=np.float32) / 255.0
    tex = np.minimum(1.0, tex * 1.35)   # the blur thins the core; bring it back up
    return {"tex": tex, "minx": float(minx), "minz": float(minz), "res": res,
            "strength": float(cfg["strength"]), "tint": np.array(cfg["tint"], np.float32)}
