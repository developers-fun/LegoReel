"""stickreel engine: small 2D vector animation helpers on top of Pillow + numpy.

Everything is authored in "reference space" (576 x 1024, the size of the TikTok reference) and drawn through a
Cam that maps reference space to the render canvas. Render canvas = REF * S pixels (S=2 -> 1152x2048), and the
final frame is resized to 1080x1920 (or 576x1024 for side-by-side checks).
"""
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageChops, ImageFont

REF_W, REF_H = 576, 1024
S = 2.0


class Cam:
    """zoom z about the reference point (cx, cy), which lands at (tx, ty) in reference space of the output."""

    def __init__(self, z=1.0, cx=288.0, cy=512.0, tx=288.0, ty=512.0):
        self.z, self.cx, self.cy, self.tx, self.ty = z, cx, cy, tx, ty

    def p(self, x, y):
        return ((self.tx + (x - self.cx) * self.z) * S, (self.ty + (y - self.cy) * self.z) * S)

    def k(self, w):
        return w * self.z * S


def lerp(a, b, u):
    return a + (b - a) * u


def smooth(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def ease_out(u):
    u = min(1.0, max(0.0, u))
    return 1 - (1 - u) ** 3


def ease_in(u):
    u = min(1.0, max(0.0, u))
    return u ** 3


def hexc(h, a=255):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


def new_canvas():
    return Image.new("RGBA", (int(REF_W * S), int(REF_H * S)), (0, 0, 0, 255))


def vgrad(img, y0, y1, stops, cam, x0=0, x1=REF_W):
    """vertical gradient over reference y0..y1 using stops [(pos 0..1, '#hex'), ...]."""
    ax, ay = cam.p(x0, y0)
    bx, by = cam.p(x1, y1)
    ay, by = int(round(ay)), int(round(by))
    ax, bx = int(round(ax)), int(round(bx))
    H = max(1, by - ay)
    W = max(1, bx - ax)
    pos = np.array([s[0] for s in stops])
    cols = np.array([hexc(s[1])[:3] for s in stops], dtype=np.float32)
    t = np.linspace(0, 1, H)
    col = np.stack([np.interp(t, pos, cols[:, i]) for i in range(3)], axis=1)
    arr = np.repeat(col[:, None, :], W, axis=1).astype(np.uint8)
    layer = Image.fromarray(arr, "RGB")
    # clip to canvas
    full = img.size
    px, py = ax, ay
    img.paste(layer, (px, py))


def _translucent(*cols):
    return any(c is not None and len(c) == 4 and c[3] < 255 for c in cols)


def _over(img, draw_fn):
    """run draw_fn(ImageDraw) on a transparent layer and alpha-composite it, so translucent colours blend
    (ImageDraw on an RGBA image replaces pixels instead of blending)."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(layer, "RGBA"))
    img.alpha_composite(layer)


def poly(img, pts, cam, fill=None, outline=None, width=1.0, join=True):
    if _translucent(fill, outline):
        return _over(img, lambda d: _poly_d(d, pts, cam, fill, outline, width, join))
    return _poly_d(ImageDraw.Draw(img, "RGBA"), pts, cam, fill, outline, width, join)


def _poly_d(d, pts, cam, fill, outline, width, join):
    P = [cam.p(*q) for q in pts]
    if fill is not None:
        d.polygon(P, fill=fill)
    if outline is not None:
        w = max(1, int(round(cam.k(width))))
        d.line(P + ([P[0]] if join else []), fill=outline, width=w, joint="curve")


def circle(img, c, r, cam, fill=None, outline=None, width=1.0):
    if _translucent(fill, outline):
        return _over(img, lambda d: _circle_d(d, c, r, cam, fill, outline, width))
    return _circle_d(ImageDraw.Draw(img, "RGBA"), c, r, cam, fill, outline, width)


def _circle_d(d, c, r, cam, fill, outline, width):
    x, y = cam.p(*c)
    R = cam.k(r)
    d.ellipse([x - R, y - R, x + R, y + R], fill=fill, outline=outline, width=max(1, int(round(cam.k(width)))) if outline else 0)


def ellipse(img, c, rx, ry, cam, fill=None, outline=None, width=1.0, rot=0.0):
    if _translucent(fill, outline) and abs(rot) < 1e-6:
        return _over(img, lambda d: _ellipse_d(d, c, rx, ry, cam, fill, outline, width))
    if abs(rot) < 1e-6:
        return _ellipse_d(ImageDraw.Draw(img, "RGBA"), c, rx, ry, cam, fill, outline, width)
    if False:
        d = None
        pass
    else:
        pts = []
        for i in range(24):
            th = i / 24 * 2 * math.pi
            ex, ey = rx * math.cos(th), ry * math.sin(th)
            pts.append((c[0] + ex * math.cos(rot) - ey * math.sin(rot), c[1] + ex * math.sin(rot) + ey * math.cos(rot)))
        poly(img, pts, cam, fill, outline, width)


def _ellipse_d(d, c, rx, ry, cam, fill, outline, width):
    x, y = cam.p(*c)
    a, b = cam.k(rx), cam.k(ry)
    d.ellipse([x - a, y - b, x + a, y + b], fill=fill, outline=outline,
              width=max(1, int(round(cam.k(width)))) if outline else 0)


def line(img, a, b, cam, color, width, cap=True):
    if _translucent(color):
        return _over(img, lambda d: _line_d(d, a, b, cam, color, width, cap))
    return _line_d(ImageDraw.Draw(img, "RGBA"), a, b, cam, color, width, cap)


def _line_d(d, a, b, cam, color, width, cap):
    pa, pb = cam.p(*a), cam.p(*b)
    w = max(1, int(round(cam.k(width))))
    d.line([pa, pb], fill=color, width=w)
    if cap:
        r = w / 2
        for p in (pa, pb):
            d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=color)


def glow(img, c, r, cam, color=(255, 240, 200), strength=1.0, power=2.0):
    """additive radial glow, radius r (ref px)."""
    x, y = cam.p(*c)
    R = cam.k(r)
    x0, y0 = int(max(0, x - R)), int(max(0, y - R))
    x1, y1 = int(min(img.size[0], x + R + 1)), int(min(img.size[1], y + R + 1))
    if x1 <= x0 or y1 <= y0:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1]
    d = np.sqrt((xx - x) ** 2 + (yy - y) ** 2) / max(R, 1e-6)
    a = np.clip(1 - d, 0, 1) ** power * strength
    reg = np.asarray(img.crop((x0, y0, x1, y1)).convert("RGB")).astype(np.float32)
    col = np.array(color, dtype=np.float32)
    reg = reg + a[..., None] * col[None, None, :]
    out = Image.fromarray(np.clip(reg, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    img.paste(out, (x0, y0))


def star(img, c, r, cam, color=(255, 255, 255, 230), thin=0.18):
    x, y = c
    pts = []
    for i in range(8):
        a = i * math.pi / 4
        rr = r if i % 2 == 0 else r * thin
        pts.append((x + rr * math.cos(a - math.pi / 2), y + rr * math.sin(a - math.pi / 2)))
    poly(img, pts, cam, fill=color)


def tint(img, color, alpha):
    """overlay a flat colour on the whole frame (alpha 0..1)."""
    ov = Image.new("RGBA", img.size, (*color[:3], int(255 * alpha)))
    img.alpha_composite(ov)


import os as _os
FONT_BOLD = _os.path.join(_os.path.dirname(__file__), "..", "..", "fonts", "Poppins-Bold.ttf")


def font(size, weight=800):
    f = ImageFont.truetype(FONT_BOLD, int(max(6, size)))
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass
    return f


def text(img, s, c, size, cam, fill=(255, 255, 255, 255), outline=(40, 25, 10, 255), ow=2.0, track=0.0,
         weight=800, grad=None, shadow=None, width=None, alpha=1.0, align="center"):
    """centered text at ref point c with letter spacing `track` (ref px). grad = (top_hex, bottom_hex).
    width = target total width in ref px (solves the letter spacing). alpha fades the whole text."""
    f = font(cam.k(size), weight)
    d = ImageDraw.Draw(img, "RGBA")
    widths = [d.textlength(ch, font=f) for ch in s]
    if width is not None:
        track = (cam.k(width) - sum(widths)) / max(1, len(s) - 1) / cam.k(1.0)
    tr = cam.k(track)
    total = sum(widths) + tr * (len(s) - 1)
    x, y = cam.p(*c)
    if align != "left":
        x -= total / 2
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    mask = Image.new("L", img.size, 0)
    md = ImageDraw.Draw(mask)
    cx = x
    for ch, w in zip(s, widths):
        md.text((cx, y), ch, font=f, anchor="lm", fill=255)
        cx += w + tr
    if alpha < 1.0:
        mask = mask.point(lambda v: int(v * alpha))
    if shadow:
        sh = mask.filter(ImageFilter.GaussianBlur(cam.k(2)))
        img.paste(Image.new("RGBA", img.size, shadow), (int(cam.k(1)), int(cam.k(2))), sh)
    if outline and ow > 0:
        o = mask.filter(ImageFilter.MaxFilter(max(3, int(cam.k(ow)) * 2 + 1)))
        img.paste(Image.new("RGBA", img.size, outline), (0, 0), o)
    if grad:
        top, bot = hexc(grad[0]), hexc(grad[1])
        H = img.size[1]
        t = np.clip((np.arange(H) - (y - cam.k(size) * 0.5)) / max(1, cam.k(size)), 0, 1)
        col = np.stack([np.interp(t, [0, 1], [top[i], bot[i]]) for i in range(3)], axis=1).astype(np.uint8)
        arr = np.repeat(col[:, None, :], img.size[0], axis=1)
        gl = Image.fromarray(arr, "RGB").convert("RGBA")
        img.paste(gl, (0, 0), mask)
    else:
        img.paste(Image.new("RGBA", img.size, fill), (0, 0), mask)
