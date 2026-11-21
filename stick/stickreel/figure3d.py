"""Draws the solved figure: thick outlined capsules sorted by depth (so it works from the front, side and back),
a doodled face that wraps around the head, and a hook where held items are drawn between body parts."""
import math
from PIL import Image, ImageDraw, ImageChops, ImageFilter

from .engine import S
from .faces import FACES, INK, talk_mouth
from .track import parse_color

OUTLINE = (52, 46, 52, 255)
FILL = (247, 247, 252, 255)
SHADE = (176, 182, 208, 255)
LIMB_ARM, LIMB_LEG, LIMB_TORSO, HEAD_R = 15.0, 19.0, 21.0, 17.0


def _mul(c, tint):
    return tuple(int(v * t) for v, t in zip(c[:3], tint)) + (255,)


def _hex(c, a=None):
    r = parse_color(c)
    return r if a is None else r[:3] + (a,)


def draw_figure(img, pose, cam, face=None, talk_open=None, faces=None, item_hooks=None):
    """pose from skeleton.solve. item_hooks = {"arm_r": fn(img), ...} drawn just before that arm (so the hand wraps it)."""
    from .engine import S as _S
    tint = pose.get("tint")
    tint = tuple(tint) if tint is not None else None
    pts = [pose["head"], pose["neck"], pose["hip"]] + pose["hands"] + pose["feet"] + pose["elbows"] + pose["knees"]
    cp = [cam.p(*q) for q in pts]
    pad = cam.k(60)
    x0, y0 = int(max(0, min(q[0] for q in cp) - pad)), int(max(0, min(q[1] for q in cp) - pad))
    x1, y1 = int(min(img.size[0], max(q[0] for q in cp) + pad)), int(min(img.size[1], max(q[1] for q in cp) + pad))
    if x1 <= x0 or y1 <= y0:
        return
    size = (x1 - x0, y1 - y0)
    patch = Image.new("RGBA", size, (0, 0, 0, 0))
    k = cam.z * _S

    def T(p):
        q = cam.p(*p)
        return (q[0] - x0, q[1] - y0)

    def cap(points, width):
        m = Image.new("L", size, 0)
        d = ImageDraw.Draw(m)
        P = [T(p) for p in points]
        w = max(1, int(round(width * k)))
        d.line(P, fill=255, width=w, joint="curve")
        r = w / 2
        for p in (P[0], P[-1]):
            d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=255)
        return m

    def circ(c, r):
        m = Image.new("L", size, 0)
        x, y = T(c)
        ImageDraw.Draw(m).ellipse([x - r * k, y - r * k, x + r * k, y + r * k], fill=255)
        return m

    def paint(mask, ow=2.4):
        kk = max(3, int(round(ow * k)) * 2 + 1)
        patch.paste(Image.new("RGBA", size, OUTLINE), (0, 0), mask.filter(ImageFilter.MaxFilter(kk)))
        patch.paste(Image.new("RGBA", size, _mul(FILL, tint) if tint else FILL), (0, 0), mask)
        off = max(1, int(3 * k))
        sh = ImageChops.subtract(mask, ImageChops.offset(mask, -off, -off)).filter(ImageFilter.GaussianBlur(1.2 * k))
        sh = ImageChops.multiply(sh, mask)
        patch.paste(Image.new("RGBA", size, _mul(SHADE, tint) if tint else SHADE), (0, 0), sh.point(lambda v: int(v * 0.85)))

    dep = pose["depth"]
    parts = [
        (dep["leg_r"], 0, "leg_r", lambda: paint(cap([pose["hip"], pose["knees"][0], pose["feet"][0]], LIMB_LEG))),
        (dep["leg_l"], 1, "leg_l", lambda: paint(cap([pose["hip"], pose["knees"][1], pose["feet"][1]], LIMB_LEG))),
        (dep["torso"], 2, "torso", lambda: paint(cap([pose["neck"], pose["hip"]], LIMB_TORSO))),
        (dep["head"] - 0.05, 3, "head", None),
        (dep["arm_r"], 4, "arm_r", lambda: paint(cap([pose["shoulders"][0], pose["elbows"][0], pose["hands"][0]], LIMB_ARM))),
        (dep["arm_l"], 5, "arm_l", lambda: paint(cap([pose["shoulders"][1], pose["elbows"][1], pose["hands"][1]], LIMB_ARM))),
    ]
    parts.sort(key=lambda a: (-a[0], a[1]))             # far first
    hooks = item_hooks or {}
    for _, _, name, fn in parts:
        if name in hooks:                                # items go behind the hand that holds them
            img.alpha_composite(patch, (x0, y0))
            patch.paste((0, 0, 0, 0), (0, 0, size[0], size[1]))
            hooks[name](img)
        if name == "head":
            paint(circ(pose["head"], HEAD_R))
            if face is not None:
                _draw_face(patch, pose, face, talk_open, T, k, faces or FACES)
        else:
            fn()
    img.alpha_composite(patch, (x0, y0))


def _draw_face(patch, pose, face, talk_open, T, k, faces):
    spec = faces.get(face) or FACES.get(face)
    if spec is None:
        return
    d = ImageDraw.Draw(patch, "RGBA")
    R = HEAD_R * k * 0.94
    cx, cy = T(pose["head"])
    yaw = pose["yaw"]
    tilt = math.radians(pose["head_tilt"]) * (1 if math.cos(math.radians(yaw)) >= 0 else -1)
    ct, st = math.cos(tilt), math.sin(tilt)
    off = math.radians(90 - yaw) * 0.8              # <1: the face sits a little toward the camera so profiles still show it

    def proj(u, v):
        phi = math.asin(max(-1.0, min(1.0, u * 0.95)))
        lam = phi + off
        lam = (lam + math.pi) % (2 * math.pi) - math.pi
        vis = math.cos(lam)
        x, y = R * math.sin(lam), v * R
        return (cx + x * ct - y * st, cy + x * st + y * ct), vis

    mouth = spec.get("mouth", [])
    if talk_open is not None:
        mouth = talk_mouth(talk_open)
    for prim in list(spec.get("parts", [])) + list(mouth):
        kind = prim[0]
        if kind == "dot":
            _, u, v, rx, ry = prim
            _poly(d, proj, [(u + rx * math.cos(a), v + ry * math.sin(a)) for a in _ang(12)], (u, v), INK_C, None, 0)
        elif kind == "ellipse":
            _, u, v, rx, ry, fill, stroke = prim
            _poly(d, proj, [(u + rx * math.cos(a), v + ry * math.sin(a)) for a in _ang(14)], (u, v),
                  _hex(fill) if fill else None, _hex(stroke) if stroke else None, max(1, int(0.05 * R)))
        elif kind == "fill":
            pts = prim[1]
            col = _hex(prim[2]) if len(prim) > 2 and prim[2] else INK_C
            c = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
            _poly(d, proj, pts, c, col, None, 0)
        elif kind == "line":
            pts, w = prim[1], prim[2]
            col = _hex(prim[3]) if len(prim) > 3 and prim[3] else INK_C
            P = []
            for u, v in pts:
                q, vis = proj(u, v)
                if vis > 0.02:
                    P.append(q)
            if len(P) >= 2:
                wd = max(1, int(w * R))
                d.line(P, fill=col, width=wd, joint="curve")
                for q in (P[0], P[-1]):
                    d.ellipse([q[0] - wd / 2, q[1] - wd / 2, q[0] + wd / 2, q[1] + wd / 2], fill=col)


INK_C = _hex(INK)


def _ang(n):
    return [2 * math.pi * i / n for i in range(n)]


def _poly(d, proj, pts, centre, fill, stroke, sw):
    _, vis = proj(*centre)
    if vis <= 0.02:
        return
    P = [proj(u, v)[0] for u, v in pts]
    d.polygon(P, fill=fill, outline=stroke)
    if stroke and sw > 1:
        d.line(P + [P[0]], fill=stroke, width=sw)
