"""Stick figure rig: 2-bone IK arms and legs, thick outlined limbs with edge shading, a pickaxe prop.

A pose is a dict of reference-space points:
  head (x, y)      centre of the head circle
  neck (x, y)      base of the head / top of the torso
  hip  (x, y)
  hands [(x, y), (x, y)]      first = near hand (drawn on top)
  feet  [(x, y), (x, y)]      first = near foot
  eb [sign, sign]  elbow bend side (+1/-1); kb [sign, sign] knee bend side
  pick None or angle in degrees (handle direction from the grip, 0 = right, -90 = up)
  pick_len handle length beyond the grip
"""
import math
import numpy as np
from PIL import Image, ImageDraw, ImageChops, ImageFilter
from .engine import S, lerp, hexc

OUTLINE = (52, 46, 52, 255)
FILL = (247, 247, 252, 255)
SHADE = (176, 182, 208, 255)

UPPER_ARM, FORE_ARM = 33.0, 37.0
THIGH, SHIN = 43.0, 43.0
LIMB_ARM, LIMB_LEG, LIMB_TORSO, HEAD_R = 15.0, 19.0, 21.0, 17.0


def ik2(root, target, l1, l2, side):
    """elbow/knee position for a 2-bone chain root->target; side = +1/-1 picks the bend direction."""
    rx, ry = root
    tx, ty = target
    dx, dy = tx - rx, ty - ry
    d = max(math.hypot(dx, dy), 1e-3)
    if d > (l1 + l2) * 0.999:                      # cartoon stretch: lengthen both bones to reach
        f = d / ((l1 + l2) * 0.999)
        l1, l2 = l1 * f, l2 * f
    a = (l1 * l1 - l2 * l2 + d * d) / (2 * d)
    h2 = max(l1 * l1 - a * a, 0.0)
    h = math.sqrt(h2)
    ux, uy = dx / math.hypot(dx, dy), dy / math.hypot(dx, dy)
    px, py = rx + ux * a, ry + uy * a
    return (px - uy * h * side, py + ux * h * side)


def lerp_pose(a, b, u):
    out = {}
    for k in ("head", "neck", "hip"):
        out[k] = (lerp(a[k][0], b[k][0], u), lerp(a[k][1], b[k][1], u))
    out["hands"] = [(lerp(a["hands"][i][0], b["hands"][i][0], u), lerp(a["hands"][i][1], b["hands"][i][1], u)) for i in range(2)]
    out["feet"] = [(lerp(a["feet"][i][0], b["feet"][i][0], u), lerp(a["feet"][i][1], b["feet"][i][1], u)) for i in range(2)]
    out["eb"] = a.get("eb", [1, 1])
    out["kb"] = a.get("kb", [1, -1])
    pa, pb = a.get("pick"), b.get("pick")
    if pa is None or pb is None:
        out["pick"] = pa if u < 0.5 else pb
    else:
        d = (pb - pa + 180) % 360 - 180          # shortest way round
        out["pick"] = pa + d * u
    out["pick_len"] = lerp(a.get("pick_len", 58), b.get("pick_len", 58), u)
    out["tint"] = a.get("tint")
    return out


def shift(pose, dx, dy):
    q = dict(pose)
    for k in ("head", "neck", "hip"):
        q[k] = (pose[k][0] + dx, pose[k][1] + dy)
    q["hands"] = [(h[0] + dx, h[1] + dy) for h in pose["hands"]]
    q["feet"] = [(h[0] + dx, h[1] + dy) for h in pose["feet"]]
    return q


def _capsule_mask(size, pts, width, S_, off):
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    P = [((x - off[0]) * S_, (y - off[1]) * S_) for x, y in pts]
    w = max(1, int(round(width * S_)))
    d.line(P, fill=255, width=w, joint="curve")
    r = w / 2
    for p in (P[0], P[-1]):
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=255)
    return m


def _circle_mask(size, c, r, S_, off):
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    x, y = (c[0] - off[0]) * S_, (c[1] - off[1]) * S_
    d.ellipse([x - r * S_, y - r * S_, x + r * S_, y + r * S_], fill=255)
    return m


def _paint_part(patch, mask, ow, S_, fill=FILL, shade=SHADE, tint=None):
    """outline + fill + lower-right edge shading for one body part."""
    k = max(3, int(round(ow * S_)) * 2 + 1)
    om = mask.filter(ImageFilter.MaxFilter(k))
    patch.paste(Image.new("RGBA", patch.size, OUTLINE), (0, 0), om)
    f = fill
    if tint:
        f = tuple(int(c * t) for c, t in zip(fill[:3], tint)) + (255,)
    patch.paste(Image.new("RGBA", patch.size, f), (0, 0), mask)
    # shading = mask minus mask moved up-left; then soften
    sh = ImageChops.subtract(mask, ImageChops.offset(mask, -int(3 * S_), -int(3 * S_)))
    sh = sh.filter(ImageFilter.GaussianBlur(1.2 * S_))
    sh = ImageChops.multiply(sh, mask)
    sc = shade
    if tint:
        sc = tuple(int(c * t) for c, t in zip(shade[:3], tint)) + (255,)
    patch.paste(Image.new("RGBA", patch.size, sc), (0, 0), sh.point(lambda v: int(v * 0.85)))


def pick_geometry(grip, ang, plen):
    dx, dy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    nx, ny = -dy, dx
    end = (grip[0] + dx * plen, grip[1] + dy * plen)
    back = (grip[0] - dx * 14, grip[1] - dy * 14)

    def L(u, v):
        return (end[0] + dx * u + nx * v, end[1] + dy * u + ny * v)

    return back, end, L


def draw_pick(img, grip, ang, plen, cam, hot=0.0):
    from .engine import line, poly
    back, end, L = pick_geometry(grip, ang, plen)
    line(img, back, end, cam, (60, 36, 20, 255), 6.5)
    line(img, back, end, cam, (206, 128, 66, 255), 3.6)
    line(img, (back[0] - 0.5, back[1] - 0.5), (end[0] - 0.5, end[1] - 0.5), cam, (240, 176, 110, 160), 1.1)

    def bez(p0, c, p1, n=14):
        out = []
        for i in range(n + 1):
            t = i / n
            out.append(((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * c[0] + t * t * p1[0],
                        (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * c[1] + t * t * p1[1]))
        return out

    t1, t2 = L(-16, -46), L(-16, 46)
    outer = bez(t1, L(40, 0), t2)
    inner = bez(t2, L(12, 0), t1)
    shape = outer + inner
    poly(img, shape, cam, fill=(206, 212, 224, 255), outline=(48, 50, 60, 255), width=2.0)
    # lighter highlight along the outer edge
    hi = bez(L(-8, -38), L(30, -2), L(-2, 22), 10)
    for a, b in zip(hi[:-1], hi[1:]):
        line(img, a, b, cam, (250, 252, 255, 210), 1.8, cap=False)
    # metal block where the handle enters
    blk = [L(-6, -7), L(7, -7), L(7, 7), L(-6, 7)]
    poly(img, blk, cam, fill=(108, 112, 122, 255), outline=(40, 40, 48, 255), width=1.6)
    return L(20, 0)


def draw_figure(img, pose, cam, tint=None):
    """draw one stick figure (and its pick) onto img."""
    pts = [pose["head"], pose["neck"], pose["hip"]] + list(pose["hands"]) + list(pose["feet"])
    if pose.get("pick") is not None:
        g = ((pose["hands"][0][0] + pose["hands"][1][0]) / 2, (pose["hands"][0][1] + pose["hands"][1][1]) / 2)
        _, e, _ = pick_geometry(g, pose["pick"], pose.get("pick_len", 58))
        pts.append(e)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    pad = 70
    # work in canvas pixel space of the camera
    cpts = [cam.p(x, y) for x, y in pts]
    cx0 = int(max(0, min(p[0] for p in cpts) - cam.k(pad)))
    cy0 = int(max(0, min(p[1] for p in cpts) - cam.k(pad)))
    cx1 = int(min(img.size[0], max(p[0] for p in cpts) + cam.k(pad)))
    cy1 = int(min(img.size[1], max(p[1] for p in cpts) + cam.k(pad)))
    if cx1 <= cx0 or cy1 <= cy0:
        return
    size = (cx1 - cx0, cy1 - cy0)
    patch = Image.new("RGBA", size, (0, 0, 0, 0))

    k = cam.z * S

    def T(p):
        q = cam.p(*p)
        return (q[0] - cx0, q[1] - cy0)

    def cap(pts_, width):
        m = Image.new("L", size, 0)
        d = ImageDraw.Draw(m)
        P = [T(p) for p in pts_]
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
        # the helper uses S as pixel scale; here pixel scale is k
        kk = max(3, int(round(ow * k)) * 2 + 1)
        om = mask.filter(ImageFilter.MaxFilter(kk))
        patch.paste(Image.new("RGBA", size, OUTLINE), (0, 0), om)
        f = FILL if tint is None else tuple(int(c * t) for c, t in zip(FILL[:3], tint)) + (255,)
        patch.paste(Image.new("RGBA", size, f), (0, 0), mask)
        off = max(1, int(3 * k))
        sh = ImageChops.subtract(mask, ImageChops.offset(mask, -off, -off)).filter(ImageFilter.GaussianBlur(1.2 * k))
        sh = ImageChops.multiply(sh, mask)
        sc = SHADE if tint is None else tuple(int(c * t) for c, t in zip(SHADE[:3], tint)) + (255,)
        patch.paste(Image.new("RGBA", size, sc), (0, 0), sh.point(lambda v: int(v * 0.85)))

    neck, hip, head = pose["neck"], pose["hip"], pose["head"]
    eb = pose.get("eb", [1, 1])
    kb = pose.get("kb", [1, -1])
    sh_pt = (neck[0], neck[1] + 8)
    legs = []
    for i in (1, 0):                       # far leg first
        f = pose["feet"][i]
        knee = ik2(hip, f, THIGH, SHIN, kb[i])
        legs.append([hip, knee, f])
    paint(cap(legs[0], LIMB_LEG))
    paint(cap([neck, hip], LIMB_TORSO))
    paint(cap(legs[1], LIMB_LEG))
    paint(circ(head, HEAD_R))
    arms = []
    for i in (1, 0):
        h = pose["hands"][i]
        el = ik2(sh_pt, h, UPPER_ARM, FORE_ARM, eb[i])
        arms.append([sh_pt, el, h])
    img.alpha_composite(patch, (cx0, cy0)) if False else None
    # arms are drawn after the pick handle so the hands wrap over it; pick drawn between body and arms
    base = img
    base.alpha_composite(patch, (cx0, cy0))
    patch.paste((0, 0, 0, 0), (0, 0, size[0], size[1]))
    if pose.get("pick") is not None:
        g = ((pose["hands"][0][0] + pose["hands"][1][0]) / 2, (pose["hands"][0][1] + pose["hands"][1][1]) / 2)
        draw_pick(base, g, pose["pick"], pose.get("pick_len", 58), cam)
    for a in arms:
        paint(cap(a, LIMB_ARM))
    base.alpha_composite(patch, (cx0, cy0))
