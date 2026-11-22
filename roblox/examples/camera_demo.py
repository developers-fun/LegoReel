"""Print a table of shot presets and write out/camera_shots.png (contact sheet).

Draws an R6 stick/box figure (and a second one for over_shoulder / two_shot) through each
preset camera with a tiny software perspective renderer (PIL only, no GL needed).
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from r6reel import camera as C  # noqa: E402

W, H = 270, 480
NEAR = 0.15


def box_faces(center, size, color):
    cx, cy, cz = center
    sx, sy, sz = (s / 2 for s in size)
    v = np.array([[x, y, z] for x in (-sx, sx) for y in (-sy, sy) for z in (-sz, sz)]) + [cx, cy, cz]
    idx = {(a, b, c): i for i, (a, b, c) in enumerate((a, b, c) for a in (0, 1) for b in (0, 1) for c in (0, 1))}
    faces = []
    for axis, sign, n in ((0, 0, (-1, 0, 0)), (0, 1, (1, 0, 0)), (1, 0, (0, -1, 0)), (1, 1, (0, 1, 0)),
                          (2, 0, (0, 0, -1)), (2, 1, (0, 0, 1))):
        quad = []
        for p, q in ((0, 0), (1, 0), (1, 1), (0, 1)):
            key = [0, 0, 0]
            key[axis] = sign
            o = [a for a in range(3) if a != axis]
            key[o[0]], key[o[1]] = p, q
            quad.append(v[idx[tuple(key)]])
        faces.append((np.array(quad), np.array(n, float), color))
    return faces


def figure(pos, facing_deg, tint=0):
    """R6: legs 1x2x1, torso 2x2x1, arms 1x2x1, head 1.25 cube.  Front (face) points to -Z at 0."""
    parts = [((-0.5, 1, 0), (1, 2, 1), (60, 160, 70)), ((0.5, 1, 0), (1, 2, 1), (60, 160, 70)),
             ((0, 3, 0), (2, 2, 1), (40, 90, 220) if not tint else (220, 70, 60)),
             ((-1.5, 3, 0), (1, 2, 1), (245, 205, 48)), ((1.5, 3, 0), (1, 2, 1), (245, 205, 48)),
             ((0, 4.62, 0), (1.25, 1.25, 1.25), (245, 205, 48)),
             ((-0.3, 4.75, -0.65), (0.2, 0.3, 0.06), (20, 20, 20)), ((0.3, 4.75, -0.65), (0.2, 0.3, 0.06), (20, 20, 20)),
             ((0, 4.3, -0.65), (0.5, 0.1, 0.06), (20, 20, 20))]
    out = []
    for c, s, col in parts:
        for quad, n, colr in box_faces(c, s, col):
            q = np.array([C.rot_y(p, facing_deg) + pos for p in quad])
            out.append((q, C.rot_y(n, facing_deg), colr))
    return out


def clip_near(poly_cam):
    """Sutherland-Hodgman against depth >= NEAR (poly in camera depth coordinates; returns list)."""
    out = []
    n = len(poly_cam)
    for i in range(n):
        a, b = poly_cam[i], poly_cam[(i + 1) % n]
        ina, inb = a[2] >= NEAR, b[2] >= NEAR
        if ina:
            out.append(a)
        if ina != inb:
            k = (NEAR - a[2]) / (b[2] - a[2])
            out.append(a + (b - a) * k)
    return out


def draw_scene(cs, figures, size=(W, H)):
    w, h = size
    img = Image.new("RGB", size, (150, 200, 245))
    d = ImageDraw.Draw(img)
    r, u, f = C._basis(np.array(cs.eye), np.array(cs.target), np.array(cs.up), cs.roll)
    th = math.tan(math.radians(cs.fov_y) / 2)
    eye = np.array(cs.eye)

    def to_screen(p3):                       # p3 = (right, up, depth) camera coords
        return ((p3[0] / (p3[2] * th * (w / h)) * 0.5 + 0.5) * w, (0.5 - p3[1] / (p3[2] * th) * 0.5) * h)

    def cam_coords(p):
        q = np.asarray(p) - eye
        return np.array([q @ r, q @ u, q @ f])

    # ground: horizon sky + green plane drawn as big quad, then grid
    ground = [(-200, 0, -200), (200, 0, -200), (200, 0, 200), (-200, 0, 200)]
    poly = clip_near([cam_coords(p) for p in ground])
    if len(poly) >= 3:
        d.polygon([to_screen(p) for p in poly], fill=(120, 190, 100))
    for g in range(-40, 41, 2):
        for a, b in (((g, 0, -40), (g, 0, 40)), ((-40, 0, g), (40, 0, g))):
            ca, cb = cam_coords(a), cam_coords(b)
            if ca[2] < NEAR and cb[2] < NEAR:
                continue
            if ca[2] < NEAR:
                ca = ca + (cb - ca) * ((NEAR - ca[2]) / (cb[2] - ca[2]))
            if cb[2] < NEAR:
                cb = cb + (ca - cb) * ((NEAR - cb[2]) / (ca[2] - cb[2]))
            d.line([to_screen(ca), to_screen(cb)], fill=(95, 165, 85), width=1)
    faces = []
    for fig in figures:
        faces.extend(fig)
    faces.sort(key=lambda q: -np.linalg.norm(q[0].mean(axis=0) - eye))
    light = -f * 0.7 + u * 0.55 + r * 0.25; light /= np.linalg.norm(light)   # headlight
    for quad, n, col in faces:
        if n @ (quad.mean(axis=0) - eye) > 0:      # back face
            continue
        poly = clip_near([cam_coords(p) for p in quad])
        if len(poly) < 3:
            continue
        shade = 0.55 + 0.45 * max(0.0, float(n @ light))
        d.polygon([to_screen(p) for p in poly], fill=tuple(int(c * shade) for c in col), outline=(15, 15, 15))
    return img


def main():
    rows = []
    sheet_cols, cell_w, cell_h = 4, W, H + 22
    kinds = list(C.SHOT_KINDS)
    nrows = math.ceil(len(kinds) / sheet_cols)
    sheet = Image.new("RGB", (sheet_cols * cell_w, nrows * cell_h), (24, 24, 28))
    sd = ImageDraw.Draw(sheet)
    print(f"{'kind':16s} {'fov':>5s} {'fill':>5s} {'dist':>6s}  eye -> target")
    for i, kind in enumerate(kinds):
        sub = np.array([0.0, 0.0, 0.0])
        kw = {}
        figs = [figure(sub, 0.0)]
        if kind == "over_shoulder":
            other = sub + C.forward_vec(0) * 3.2
            kw["other_pos"] = other
            figs.append(figure(other, 180.0, tint=1))       # listener faces the speaker
        elif kind == "two_shot":
            other = sub + C.right_vec(0) * 3.5
            kw["other_pos"] = other
            figs.append(figure(other, 90.0, tint=1))         # turned toward the speaker (+X side -> faces -X)
            figs[0] = figure(sub, -90.0)                     # speaker turned toward partner
        elif kind == "pov":
            other = sub + C.forward_vec(0) * 7.0
            kw["other_pos"] = other
            figs = [figure(other, 180.0, tint=1)]             # someone standing in front of the POV avatar
        cam = C.shot(kind, sub, subject_height=5, facing_deg=0, **kw)
        # slow push + drift on top, to prove moves compose with presets
        cam.push_in(0, 4, 0.08).drift(0, None, 0.1)
        cs = cam.state(0.0)
        info = cam.info
        print(f"{kind:16s} {cs.fov_y:5.0f} {info['fill']:5.2f} {info.get('distance', 0):6.2f}  "
              f"({cs.eye[0]:6.2f},{cs.eye[1]:6.2f},{cs.eye[2]:6.2f}) -> ({cs.target[0]:5.2f},{cs.target[1]:5.2f},{cs.target[2]:5.2f})")
        img = draw_scene(cs, figs)
        x, y = (i % sheet_cols) * cell_w, (i // sheet_cols) * cell_h
        sheet.paste(img, (x, y + 22))
        sd.text((x + 6, y + 5), f"{kind}  fov {cs.fov_y:.0f}", fill=(255, 255, 255))
    os.makedirs("out", exist_ok=True)
    sheet.save("out/camera_shots.png")
    print("wrote out/camera_shots.png", sheet.size)


if __name__ == "__main__":
    main()
