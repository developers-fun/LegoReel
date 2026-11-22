#!/usr/bin/env python3
"""Draw classic Roblox-style cartoon faces (transparent 256x256 decals) for emotions the downloaded set lacks.
Writes assets/faces/decal/classic_<name>.png and prints a name->tags JSON (merged by curate_faces.py)."""
import json, os, math
from PIL import Image, ImageDraw
S = 1024
INK = (24, 24, 24, 255)
OUT = os.path.join(os.path.dirname(__file__), "..", "assets", "faces", "decal")
LW = 46  # stroke width

def new(): im = Image.new("RGBA", (S, S), (0, 0, 0, 0)); return im, ImageDraw.Draw(im)
def dot(d, x, y, r=34, c=INK): d.ellipse([x - r, y - r * 1.5, x + r, y + r * 1.5], fill=c)
def ell(d, x, y, rx, ry, c=INK, w=0, fill=None): d.ellipse([x - rx, y - ry, x + rx, y + ry], fill=fill, outline=c, width=w)
def arc(d, cx, cy, rx, ry, a0, a1, w=LW): d.arc([cx - rx, cy - ry, cx + rx, cy + ry], a0, a1, fill=INK, width=w)
def line(d, pts, w=LW):
    d.line(pts, fill=INK, width=w, joint="curve")
    for p in (pts[0], pts[-1]): d.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=INK)
def wavy(d, x0, x1, y, amp=22, n=3, w=LW):
    pts = [(x0 + (x1 - x0) * i / 60, y + amp * math.sin(2 * math.pi * n * i / 60)) for i in range(61)]; line(d, pts, w)
def blush(d, y=640):
    for x in (270, 754): ell(d, x, y, 70, 38, fill=(255, 110, 120, 120))
def tear(d, x, y, l=260):
    d.polygon([(x, y), (x - 38, y + 90), (x + 38, y + 90)], fill=(110, 190, 255, 255)); d.rounded_rectangle([x - 38, y + 70, x + 38, y + l], 30, fill=(110, 190, 255, 255))
def sweat(d, x=800, y=190):
    d.polygon([(x, y), (x - 40, y + 95), (x + 40, y + 95)], fill=(110, 190, 255, 255)); ell(d, x, y + 105, 40, 40, fill=(110, 190, 255, 255))
def heart(d, cx, cy, r, c=(235, 40, 70, 255)):
    d.ellipse([cx - r, cy - r * 0.9, cx, cy + r * 0.1], fill=c); d.ellipse([cx, cy - r * 0.9, cx + r, cy + r * 0.1], fill=c)
    d.polygon([(cx - r, cy - r * 0.3), (cx + r, cy - r * 0.3), (cx, cy + r * 1.0)], fill=c)
def mouth_open(d, cx, cy, rx, ry, teeth=False, tongue=False):
    d.pieslice([cx - rx, cy - ry, cx + rx, cy + ry], 0, 180, fill=(90, 20, 25, 255), outline=INK, width=LW // 2)
    if tongue: ell(d, cx, cy + ry * 0.55, rx * 0.5, ry * 0.4, fill=(235, 90, 110, 255))
    if teeth: d.rectangle([cx - rx * 0.8, cy + 8, cx + rx * 0.8, cy + ry * 0.28], fill=(250, 250, 250, 255))
    d.arc([cx - rx, cy - ry, cx + rx, cy + ry], 0, 180, fill=INK, width=LW // 2)

E1, E2, EY, MY = 340, 684, 400, 680
F = {}
def face(name, tags):
    def deco(fn): F[name] = (fn, tags); return fn
    return deco

@face("smile", ["happy", "smile", "default"])
def _(d): dot(d, E1, EY); dot(d, E2, EY); arc(d, 512, 560, 230, 190, 20, 160)
@face("grin", ["happy", "smile", "open_mouth"])
def _(d): dot(d, E1, EY); dot(d, E2, EY); mouth_open(d, 512, 610, 230, 190, teeth=True)
@face("joy", ["happy", "closed_eyes", "smile"])
def _(d): arc(d, E1, 430, 80, 80, 200, 340); arc(d, E2, 430, 80, 80, 200, 340); arc(d, 512, 560, 230, 190, 20, 160)
@face("laugh_open", ["laughing", "happy", "open_mouth"])
def _(d): arc(d, E1, 430, 80, 80, 200, 340); arc(d, E2, 430, 80, 80, 200, 340); mouth_open(d, 512, 590, 250, 230, tongue=True)
@face("laugh_xd", ["laughing", "closed_eyes", "open_mouth"])
def _(d): line(d, [(260, 340), (400, 410), (260, 480)]); line(d, [(764, 340), (624, 410), (764, 480)]); mouth_open(d, 512, 590, 260, 240, teeth=True)
@face("laugh_tears", ["laughing", "crying", "closed_eyes"])
def _(d): arc(d, E1, 430, 80, 80, 200, 340); arc(d, E2, 430, 80, 80, 200, 340); tear(d, 230, 470, 120); tear(d, 794, 470, 120); mouth_open(d, 512, 600, 240, 220)
@face("wink", ["happy", "wink", "smirk"])
def _(d): dot(d, E1, EY); arc(d, E2, 430, 80, 80, 200, 340); arc(d, 512, 560, 230, 190, 20, 160)
@face("shocked", ["shocked", "surprised", "open_mouth"])
def _(d): dot(d, E1, EY, 34); dot(d, E2, EY, 34); ell(d, 512, 650, 70, 100, fill=(60, 15, 20, 255), w=LW // 2); line(d, [(250, 250), (400, 230)], 38); line(d, [(624, 230), (774, 250)], 38)
@face("scream", ["shocked", "scared", "open_mouth"])
def _(d): ell(d, E1, EY, 62, 80, w=26, fill=(255, 255, 255, 255)); ell(d, E2, EY, 62, 80, w=26, fill=(255, 255, 255, 255)); dot(d, E1, EY, 14); dot(d, E2, EY, 14); ell(d, 512, 680, 120, 160, fill=(60, 15, 20, 255), w=LW // 2)
@face("scared", ["scared", "worried", "nervous"])
def _(d): ell(d, E1, EY, 70, 90, w=26, fill=(255, 255, 255, 255)); ell(d, E2, EY, 70, 90, w=26, fill=(255, 255, 255, 255)); dot(d, E1 + 15, EY, 12); dot(d, E2 - 15, EY, 12); wavy(d, 330, 694, 700, 24, 3); sweat(d)
@face("angry", ["angry", "serious"])
def _(d): dot(d, E1, EY + 30); dot(d, E2, EY + 30); line(d, [(220, 250), (420, 330)], 56); line(d, [(804, 250), (604, 330)], 56); arc(d, 512, 800, 200, 150, 200, 340)
@face("furious", ["angry", "open_mouth"])
def _(d): dot(d, E1, EY + 30); dot(d, E2, EY + 30); line(d, [(220, 240), (420, 330)], 60); line(d, [(804, 240), (604, 330)], 60); mouth_open(d, 512, 740, 220, 150, teeth=True)
@face("sad", ["sad"])
def _(d): dot(d, E1, EY + 20); dot(d, E2, EY + 20); line(d, [(230, 300), (400, 250)], 40); line(d, [(794, 300), (624, 250)], 40); arc(d, 512, 800, 190, 140, 200, 340)
@face("crying", ["crying", "sad"])
def _(d): arc(d, E1, 440, 70, 50, 0, 180); arc(d, E2, 440, 70, 50, 0, 180); tear(d, E1, 490); tear(d, E2, 490); line(d, [(230, 300), (400, 250)], 40); line(d, [(794, 300), (624, 250)], 40); mouth_open(d, 512, 800, 140, 90)
@face("sob", ["crying", "sad", "open_mouth"])
def _(d): line(d, [(250, 400), (400, 440)]); line(d, [(774, 400), (624, 440)]); tear(d, 300, 470, 300); tear(d, 724, 470, 300); mouth_open(d, 512, 720, 190, 200)
@face("confused", ["confused", "worried"])
def _(d): dot(d, E1, EY); dot(d, E2, EY); line(d, [(250, 280), (410, 280)], 38); line(d, [(614, 230), (774, 280)], 38); wavy(d, 360, 664, 690, 22, 2)
@face("bored", ["bored", "neutral"])
def _(d):
    for x in (E1, E2): d.pieslice([x - 80, EY - 80, x + 80, EY + 80], 0, 180, fill=INK); line(d, [(x - 95, EY), (x + 95, EY)], 30)
    line(d, [(400, 690), (624, 690)])
@face("deadpan", ["neutral", "serious", "bored"])
def _(d): dot(d, E1, EY, 28); dot(d, E2, EY, 28); line(d, [(380, 650), (644, 650)])
@face("smirk", ["smirk", "happy"])
def _(d): dot(d, E1, EY); dot(d, E2, EY); line(d, [(620, 260), (780, 230)], 38); arc(d, 560, 600, 160, 110, 10, 130); line(d, [(690, 640), (730, 580)], 30)
@face("worried", ["worried", "nervous", "sad"])
def _(d): dot(d, E1, EY + 10); dot(d, E2, EY + 10); line(d, [(240, 300), (400, 250)], 38); line(d, [(784, 300), (624, 250)], 38); wavy(d, 370, 654, 710, 20, 3); sweat(d)
@face("nervous", ["nervous", "embarrassed", "scared"])
def _(d): dot(d, E1 - 20, EY); dot(d, E2 - 20, EY); d.rounded_rectangle([340, 640, 684, 740], 20, fill=(250, 250, 250, 255), outline=INK, width=LW // 2); [line(d, [(x, 640), (x, 740)], 18) for x in (426, 512, 598)]; line(d, [(340, 690), (684, 690)], 18); sweat(d)
@face("embarrassed", ["embarrassed", "blush", "cute"])
def _(d): arc(d, E1, 430, 70, 60, 200, 340); arc(d, E2, 430, 70, 60, 200, 340); blush(d); wavy(d, 440, 584, 690, 16, 2, 34)
@face("cool", ["cool", "smirk"])
def _(d):
    d.rounded_rectangle([200, 330, 480, 470], 30, fill=INK); d.rounded_rectangle([544, 330, 824, 470], 30, fill=INK); line(d, [(480, 360), (544, 360)], 28); arc(d, 512, 590, 200, 150, 30, 150)
@face("silly", ["silly", "happy", "tongue"])
def _(d): dot(d, E1, EY); dot(d, E2, EY); arc(d, 512, 560, 230, 190, 20, 160); d.rounded_rectangle([450, 700, 580, 840], 60, fill=(235, 90, 110, 255), outline=INK, width=24)
@face("derp", ["silly", "confused", "tongue"])
def _(d): ell(d, E1, EY, 80, 80, w=22, fill=(255, 255, 255, 255)); ell(d, E2, EY + 20, 60, 60, w=22, fill=(255, 255, 255, 255)); dot(d, E1 + 30, EY - 10, 22); dot(d, E2 - 20, EY + 30, 22); arc(d, 512, 600, 190, 130, 10, 170); d.rounded_rectangle([520, 700, 640, 820], 55, fill=(235, 90, 110, 255), outline=INK, width=24)
@face("love", ["love", "happy"])
def _(d): heart(d, E1, EY + 10, 85); heart(d, E2, EY + 10, 85); arc(d, 512, 580, 230, 190, 20, 160)
@face("dizzy", ["dizzy", "confused", "sick"])
def _(d):
    for x in (E1, E2):
        for k in range(1, 4): ell(d, x, EY, 28 * k, 28 * k, w=14)
    wavy(d, 370, 654, 700, 24, 3)
@face("sleepy", ["sleepy", "bored", "closed_eyes"])
def _(d): arc(d, E1, 400, 80, 60, 0, 180); arc(d, E2, 400, 80, 60, 0, 180); ell(d, 512, 700, 50, 60, fill=(60, 15, 20, 255), w=LW // 2)
@face("evil", ["evil", "smirk", "angry"])
def _(d): dot(d, E1, EY + 30); dot(d, E2, EY + 30); line(d, [(230, 260), (420, 330)], 56); line(d, [(794, 260), (604, 330)], 56); mouth_open(d, 512, 650, 260, 170, teeth=True)
@face("sick", ["sick", "worried"])
def _(d): arc(d, E1, 430, 80, 70, 0, 180); arc(d, E2, 430, 80, 70, 0, 180); wavy(d, 340, 684, 720, 28, 3); ell(d, 270, 640, 70, 40, fill=(120, 200, 120, 130)); ell(d, 754, 640, 70, 40, fill=(120, 200, 120, 130))
@face("annoyed", ["serious", "bored", "angry"])
def _(d):
    for x in (E1, E2): d.pieslice([x - 80, EY - 70, x + 80, EY + 90], 0, 180, fill=INK)
    line(d, [(240, 330), (420, 340)], 44); line(d, [(784, 330), (604, 340)], 44); line(d, [(400, 700), (624, 700)])
@face("proud", ["happy", "smirk", "cool"])
def _(d): arc(d, E1, 430, 80, 80, 200, 340); arc(d, E2, 430, 80, 80, 200, 340); arc(d, 512, 560, 200, 160, 20, 160); blush(d, 560)

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True); tags = {}
    for name, (fn, tg) in F.items():
        im, d = new(); fn(d); im.resize((256, 256), Image.LANCZOS).save(os.path.join(OUT, f"classic_{name}.png")); tags[name] = tg
    json.dump(tags, open(os.path.join(OUT, "_classic_tags.json"), "w"), indent=1); print(len(tags), "classic faces")
