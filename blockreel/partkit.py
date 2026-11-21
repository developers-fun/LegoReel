"""Drawing helpers for making part images (faces and torso prints) with Pillow.

Everything draws at 4x size and shrinks, so edges are smooth. Colours are hex strings.
Faces: FaceCanvas (320x256, transparent; the head colour shows through).
Torso prints: TorsoCanvas (256x240, transparent; the torso colour shows through).
Coordinates are fractions of the canvas: x 0 (left) to 1 (right), y 0 (top) to 1 (bottom).
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SS = 4
INK = "#1b1b1f"


class _Canvas:
    W, H = 320, 256

    def __init__(self):
        self.w, self.h = self.W * SS, self.H * SS
        self.im = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    def px(self, x, y):
        return x * self.w, y * self.h

    def circle(self, x, y, r, fill, outline=None, width=0):
        cx, cy = self.px(x, y)
        rr = r * self.w
        self.d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=fill, outline=outline, width=int(width * self.w))

    def ellipse(self, x, y, rx, ry, fill, outline=None, width=0):
        cx, cy = self.px(x, y)
        self.d.ellipse([cx - rx * self.w, cy - ry * self.h, cx + rx * self.w, cy + ry * self.h], fill=fill,
                       outline=outline, width=int(width * self.w))

    def rect(self, x0, y0, x1, y1, fill, radius=0.0):
        a, b = self.px(x0, y0), self.px(x1, y1)
        if radius > 0:
            self.d.rounded_rectangle([a, b], radius=radius * self.w, fill=fill)
        else:
            self.d.rectangle([a, b], fill=fill)

    def line(self, pts, color, width=0.012):
        self.d.line([self.px(*p) for p in pts], fill=color, width=max(1, int(width * self.w)), joint="curve")
        for p in (pts[0], pts[-1]):                       # round caps
            self.circle(p[0], p[1], width / 2, color)

    def polygon(self, pts, fill):
        self.d.polygon([self.px(*p) for p in pts], fill=fill)

    def arc_points(self, cx, cy, rx, ry, a0, a1, n=24):
        return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
                 cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]

    def text(self, x, y, s, size, color, font=None):
        f = ImageFont.truetype(font, int(size * self.h)) if font else ImageFont.load_default(int(size * self.h))
        self.d.text(self.px(x, y), s, font=f, fill=color, anchor="mm")

    def save(self, path):
        out = self.im.resize((self.W, self.H), Image.LANCZOS)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        out.save(path)
        return path


class FaceCanvas(_Canvas):
    """320x256 face print. The eyes sit at about y 0.42 and the mouth at about y 0.70."""
    W, H = 320, 256

    # -- eyes (cx is the distance of each eye from the centre line; both eyes are drawn)
    def eyes_dots(self, cx=0.17, y=0.42, r=0.034, color=INK, highlight=True):
        for s in (-1, 1):
            self.circle(0.5 + s * cx, y, r, color)
            if highlight:
                self.circle(0.5 + s * cx + r * 0.35, y - r * 0.4, r * 0.32, "#ffffff")

    def eyes_big(self, cx=0.17, y=0.42, r=0.05, color=INK, white="#ffffff"):
        for s in (-1, 1):
            self.circle(0.5 + s * cx, y, r, white, outline=INK, width=0.004)
            self.circle(0.5 + s * cx, y + r * 0.1, r * 0.55, color)
            self.circle(0.5 + s * cx + r * 0.2, y - r * 0.2, r * 0.2, "#ffffff")

    def eyes_oval(self, cx=0.17, y=0.42, rx=0.026, ry=0.05, color=INK):
        for s in (-1, 1):
            self.ellipse(0.5 + s * cx, y, rx, ry / 1.25, color)
            self.circle(0.5 + s * cx + rx * 0.3, y - ry * 0.35, rx * 0.35, "#ffffff")

    def eyes_happy(self, cx=0.17, y=0.44, w=0.05, color=INK, width=0.014):
        for s in (-1, 1):
            self.line(self.arc_points(0.5 + s * cx, y, w, w * 1.1, 200, 340), color, width)

    def eyes_closed(self, cx=0.17, y=0.44, w=0.05, color=INK, width=0.013):
        for s in (-1, 1):
            self.line(self.arc_points(0.5 + s * cx, y - 0.02, w, w * 0.9, 20, 160), color, width)

    def eyes_wink(self, cx=0.17, y=0.43, r=0.034, color=INK):
        self.circle(0.5 - cx, y, r, color)
        self.circle(0.5 - cx + r * 0.35, y - r * 0.4, r * 0.32, "#ffffff")
        self.line(self.arc_points(0.5 + cx, y, 0.05, 0.05, 200, 340), color, 0.013)

    def eyes_x(self, cx=0.17, y=0.43, w=0.04, color=INK):
        for s in (-1, 1):
            x = 0.5 + s * cx
            self.line([(x - w, y - w * 1.25), (x + w, y + w * 1.25)], color, 0.013)
            self.line([(x - w, y + w * 1.25), (x + w, y - w * 1.25)], color, 0.013)

    def eyes_sleepy(self, cx=0.17, y=0.45, w=0.05, color=INK):
        for s in (-1, 1):
            self.line([(0.5 + s * cx - w, y), (0.5 + s * cx + w, y)], color, 0.013)

    def eyes_stars(self, cx=0.17, y=0.42, r=0.05, color="#ffcf33"):
        for s in (-1, 1):
            x = 0.5 + s * cx
            pts = []
            for i in range(10):
                rr = r if i % 2 == 0 else r * 0.45
                a = math.radians(-90 + i * 36)
                pts.append((x + rr * math.cos(a), y + rr * 1.25 * math.sin(a)))
            self.polygon(pts, color)

    def eyes_hearts(self, cx=0.17, y=0.42, r=0.045, color="#ff4d6d"):
        for s in (-1, 1):
            x = 0.5 + s * cx
            self.circle(x - r * 0.5, y - r * 0.3, r * 0.55, color)
            self.circle(x + r * 0.5, y - r * 0.3, r * 0.55, color)
            self.polygon([(x - r * 1.03, y - r * 0.1), (x + r * 1.03, y - r * 0.1), (x, y + r * 1.15)], color)

    # -- brows
    def brows(self, style="flat", cx=0.17, y=0.30, w=0.065, color="#3a2a20", width=0.014):
        """style: flat, raised, angry (inner ends low), sad or worried (inner ends high)."""
        dy = {"flat": 0.0, "raised": 0.0, "angry": 0.03, "sad": -0.03, "worried": -0.03}[style]
        yy = y - (0.035 if style == "raised" else 0.0)
        for s in (-1, 1):
            x = 0.5 + s * cx
            self.line([(x - s * w, yy + dy), (x + s * w, yy - dy)], color, width)

    # -- mouths
    def mouth_smile(self, y=0.66, w=0.12, depth=0.07, color=INK, width=0.014):
        self.line(self.arc_points(0.5, y - depth, w, depth * 1.6, 20, 160), color, width)

    def mouth_grin(self, y=0.64, w=0.13, depth=0.10, teeth=True):
        pts = self.arc_points(0.5, y - 0.02, w, depth, 10, 170)
        self.polygon(pts + [(0.5 - w * 0.98, y - 0.005 - 0.0), (0.5 + w * 0.98, y - 0.005)][::-1] if False else pts, INK)
        if teeth:
            top = self.arc_points(0.5, y - 0.02, w * 0.92, depth * 0.55, 12, 168)
            self.polygon(top + [(top[-1][0], y - 0.02 + 0.001), (top[0][0], y - 0.02 + 0.001)], "#ffffff")

    def mouth_open(self, y=0.70, rx=0.05, ry=0.06, tongue=True):
        self.ellipse(0.5, y, rx, ry, INK)
        if tongue:
            self.ellipse(0.5, y + ry * 0.45, rx * 0.65, ry * 0.45, "#f26d7d")

    def mouth_flat(self, y=0.70, w=0.08, color=INK, width=0.013):
        self.line([(0.5 - w, y), (0.5 + w, y)], color, width)

    def mouth_frown(self, y=0.74, w=0.09, depth=0.05, color=INK, width=0.014):
        self.line(self.arc_points(0.5, y + depth, w, depth * 1.6, 200, 340), color, width)

    def mouth_smirk(self, y=0.68, w=0.10, color=INK, width=0.014):
        self.line([(0.5 - w, y + 0.01), (0.5 + w * 0.2, y + 0.015), (0.5 + w, y - 0.03)], color, width)

    def mouth_tongue(self, y=0.66, w=0.11, depth=0.06):
        self.mouth_smile(y, w, depth)
        self.ellipse(0.5 + 0.03, y + 0.045, 0.028, 0.04, "#f26d7d")

    def mouth_o(self, y=0.72, r=0.032):
        self.circle(0.5, y, r, INK)

    # -- extras
    def cheeks(self, color="#ff8f8f", alpha=110, cx=0.28, y=0.57, r=0.04):
        layer = Image.new("RGBA", self.im.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        rgb = tuple(int(color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        for s in (-1, 1):
            cxp, cyp = self.px(0.5 + s * cx, y)
            rr = r * self.w
            ld.ellipse([cxp - rr, cyp - rr * 0.7, cxp + rr, cyp + rr * 0.7], fill=rgb + (alpha,))
        self.im = Image.alpha_composite(self.im, layer)
        self.d = ImageDraw.Draw(self.im)

    def freckles(self, color="#b9743f", n=5):
        import random
        rng = random.Random(3)
        for s in (-1, 1):
            for _ in range(n):
                self.circle(0.5 + s * rng.uniform(0.14, 0.30), rng.uniform(0.53, 0.60), 0.006, color)

    def glasses(self, cx=0.17, y=0.42, r=0.07, color="#222222", width=0.008):
        for s in (-1, 1):
            self.circle(0.5 + s * cx, y, r, None, outline=color, width=width)
        self.line([(0.5 - cx + r, y), (0.5 + cx - r, y)], color, width)

    def stubble(self, color="#00000040"):
        import random
        rng = random.Random(5)
        for _ in range(90):
            x, y = rng.uniform(0.3, 0.7), rng.uniform(0.7, 0.88)
            self.circle(x, y, 0.004, "#3b3b3b")

    def mustache(self, color="#3b261b", y=0.62, w=0.12):
        self.line(self.arc_points(0.5 - w / 2, y, w / 2, 0.035, 200, 360), color, 0.022)
        self.line(self.arc_points(0.5 + w / 2, y, w / 2, 0.035, 180, 340), color, 0.022)

    def scar(self, color="#c4584a"):
        self.line([(0.66, 0.30), (0.74, 0.5)], color, 0.01)

    def eyepatch(self, side=1, color="#222222"):
        x = 0.5 + side * 0.17
        self.circle(x, 0.42, 0.065, color)
        self.line([(x, 0.40), (0.5 - side * 0.35, 0.18)], color, 0.008)


class TorsoCanvas(_Canvas):
    """256x240 torso print. The shirt colour shows through the transparent parts."""
    W, H = 256, 240

    def stripe(self, y, h, color, x0=0.0, x1=1.0):
        self.rect(x0, y, x1, y + h, color)

    def vneck(self, color="#ffffff", depth=0.34):
        self.polygon([(0.36, 0.0), (0.64, 0.0), (0.5, depth)], color)

    def collar(self, color="#ffffff"):
        self.polygon([(0.34, 0.0), (0.5, 0.0), (0.5, 0.2), (0.42, 0.26)], color)
        self.polygon([(0.66, 0.0), (0.5, 0.0), (0.5, 0.2), (0.58, 0.26)], color)

    def buttons(self, n=4, y0=0.25, y1=0.85, color="#f4f4f4", r=0.022):
        for i in range(n):
            self.circle(0.5, y0 + (y1 - y0) * i / max(1, n - 1), r, color)

    def zipper(self, color="#d0d0d0", y0=0.0, y1=1.0):
        self.rect(0.495, y0, 0.505, y1, color)
        for i in range(10):
            yy = y0 + (y1 - y0) * (i + 0.5) / 10
            self.rect(0.485, yy, 0.515, yy + 0.02, color)

    def pocket(self, x=0.25, y=0.55, w=0.22, h=0.2, color="#00000030"):
        self.rect(x, y, x + w, y + h, color, radius=0.01)

    def belt(self, y=0.86, h=0.12, color="#3a2a20", buckle="#d8c26a"):
        self.rect(0.0, y, 1.0, y + h, color)
        self.rect(0.45, y + 0.01, 0.55, y + h - 0.01, buckle, radius=0.005)

    def star(self, x=0.5, y=0.5, r=0.16, color="#ffcf33"):
        pts = []
        for i in range(10):
            rr = r if i % 2 == 0 else r * 0.45
            a = math.radians(-90 + i * 36)
            pts.append((x + rr * math.cos(a) * (self.h / self.w), y + rr * math.sin(a)))
        self.polygon(pts, color)

    def heart(self, x=0.5, y=0.5, r=0.12, color="#ff4d6d"):
        k = self.h / self.w
        self.circle(x - r * 0.5 * k, y - r * 0.3, r * 0.55 * k, color)
        self.circle(x + r * 0.5 * k, y - r * 0.3, r * 0.55 * k, color)
        self.polygon([(x - r * 1.03 * k, y - r * 0.1), (x + r * 1.03 * k, y - r * 0.1), (x, y + r * 1.15)], color)

    def circle_logo(self, x=0.5, y=0.5, r=0.13, color="#ffffff", inner=None):
        k = self.h / self.w
        self.ellipse(x, y, r * k, r, color)
        if inner:
            self.ellipse(x, y, r * k * 0.55, r * 0.55, inner)

    def label(self, s, y=0.5, size=0.2, color="#ffffff", font=None):
        self.text(0.5, y, s, size, color, font)
