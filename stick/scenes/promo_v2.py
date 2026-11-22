"""Promo v2 (2026-11-21 evening): more detailed rooms, realistic phone/iPad, over-the-shoulder continuous zoom onto the device,
blurred time-lapse for 'one hour later' (blur is added afterwards by tools/promo_post.sh), soft dissolves and soft sounds only.
A: Sand Blast! one more game (phone), B: Lazy Blocks cozy contrast (iPad). Screens are flat green (chroma key) for the owner's recordings.
Run: python3 scenes/promo_v2.py"""
import json, math, os
HERE = os.path.dirname(os.path.abspath(__file__))
INK = "#1f1f24"
FLOORY = 760
CANVAS = dict(w=576, h=1024, fps=30, scale=1.875, bg="#20232d", blur=1, out=[1080, 1920])


def rr(w, h, r, n=6):
    r = min(r, w / 2, h / 2); pts = []
    for cx, cy, a0 in ((w / 2 - r, -h / 2 + r, -90), (w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n); pts.append([round(cx + r * math.cos(a), 2), round(cy + r * math.sin(a), 2)])
    return pts


class Scene:
    def __init__(self): self.o = {}; self.n = 0
    def add(self, kind, name=None, **kw):
        self.n += 1; name = name or f"{kind}{self.n}"; self.o[name] = dict(kind=kind, **kw); return name
    def rect(self, x, y, w, h, fill, **kw): return self.add("rect", x=x, y=y, w=w, h=h, fill=fill, **kw)
    def rrect(self, x, y, w, h, r, fill, **kw): return self.add("poly", points=rr(w, h, r), x=x, y=y, fill=fill, **kw)
    def circ(self, x, y, r, fill, **kw): return self.add("circle", x=x, y=y, r=r, fill=fill, **kw)
    def ell(self, x, y, rx, ry, fill, **kw): return self.add("ellipse", x=x, y=y, rx=rx, ry=ry, fill=fill, **kw)
    def poly(self, pts, x, y, fill, **kw): return self.add("poly", points=pts, x=x, y=y, fill=fill, **kw)
    def line(self, x, y, x2, y2, color, width=2, **kw): return self.add("line", x=x, y=y, x2=x2, y2=y2, color=color, width=width, **kw)
    def glow(self, x, y, r, color, strength, **kw): return self.add("glow", x=x, y=y, r=r, color=color, strength=strength, **kw)


def fade(t0, t1, a0=0.0, a1=1.0): return [{"t": t0, "alpha": a0}, {"t": t1, "alpha": a1, "ease": "inout"}]


def living_room(S, show, with_blanket=False, with_phone=False, lamp_t=None):
    """Front view of the room: window wall behind a couch. Camera sees x 90..486, y 290..990 when zoom 1.45 centred (288,640)."""
    kw = dict(show=show)
    S.rect(288, 512, 700, 1100, "#3a3f4f", z=-100, **kw)                                   # wall
    for x in range(30, 600, 64): S.rect(x, 520, 30, 1000, "#434a5d", z=-99, **kw)           # wallpaper stripes
    S.rect(288, 700, 700, 130, "#2f3442", z=-98, **kw)                                       # wainscot
    S.rect(288, 636, 700, 10, "#59627a", z=-97, **kw)                                        # rail
    S.rect(288, 757, 700, 14, "#e6e0d2", z=-96, **kw)                                        # baseboard
    S.rect(288, 892, 700, 270, "#c8a37a", z=-95, **kw)                                       # wood floor
    for y in range(780, 1010, 46): S.rect(288, y, 700, 2, "#b58f66", z=-94, **kw)
    for i, y in enumerate(range(780, 1010, 46)):
        for x in range(60 + (i % 2) * 60, 600, 150): S.rect(x, y + 23, 2, 46, "#b58f66", z=-94, **kw)
    # window with curtains (left)
    S.rect(150, 470, 124, 204, "#e8e2d0", z=-90, **kw)
    S.rect(150, 470, 108, 188, "#8fb8e8", z=-89, name="win_day", **kw)
    S.rect(150, 470, 108, 188, "#e8884f", z=-88, name="win_dusk", alpha=0.0, **kw)
    S.rect(150, 470, 108, 188, "#1c2754", z=-87, name="win_night", alpha=0.0, **kw)
    S.rect(150, 470, 5, 188, "#e8e2d0", z=-86, **kw); S.rect(150, 470, 108, 5, "#e8e2d0", z=-86, **kw)
    S.poly([[0, 0], [38, 0], [30, 230], [0, 230]], 70, 358, "#c76d5a", outline=INK, ow=1.5, z=-85, **kw)
    S.poly([[0, 0], [38, 0], [38, 230], [8, 230]], 192, 358, "#c76d5a", outline=INK, ow=1.5, z=-85, **kw)
    S.rect(150, 356, 160, 8, "#59432f", z=-84, **kw)
    # frames and clock above the couch
    S.rect(224, 450, 44, 56, "#e8e2d0", z=-90, outline=INK, ow=1.5, **kw); S.rect(224, 450, 34, 46, "#d2745a", z=-89, **kw)
    S.circ(224, 462, 8, "#f0c36a", z=-88, **kw)
    S.rect(352, 450, 44, 56, "#e8e2d0", z=-90, outline=INK, ow=1.5, **kw); S.rect(352, 450, 34, 46, "#5aa6a0", z=-89, **kw)
    S.poly([[0, 0], [14, -22], [28, 0]], 338, 470, "#2e7d74", z=-88, **kw)
    S.circ(288, 450, 32, "#f3efe4", z=-90, outline=INK, ow=3, **kw)
    for k in range(12):
        a = math.radians(30 * k); S.line(288 + 26 * math.sin(a), 450 - 26 * math.cos(a), 288 + 29 * math.sin(a), 450 - 29 * math.cos(a), INK, 2, z=-89, **kw)
    S.poly([[-2, 0], [2, 0], [2, -18], [-2, -18]], 288, 450, INK, z=-88, name="clock_h", keys=[{"t": 0, "rot": 60}], **kw)
    S.poly([[-1.5, 0], [1.5, 0], [1.5, -26], [-1.5, -26]], 288, 450, INK, z=-87, name="clock_m", keys=[{"t": 0, "rot": 0}], **kw)
    S.circ(288, 450, 3, INK, z=-86, **kw)
    # shelf and plant (right)
    S.rect(438, 520, 120, 8, "#6a4a2f", z=-90, **kw)
    for i, (c, h) in enumerate((("#d2745a", 44), ("#5aa6a0", 38), ("#f0c36a", 48), ("#7a5c9e", 40))):
        S.rect(396 + i * 14, 516 - h / 2, 11, h, c, z=-89, outline=INK, ow=1, **kw)
    S.rrect(478, 503, 22, 24, 5, "#b86a5c", z=-89, **kw)
    for ang in (-35, 0, 35): S.poly([[0, 0], [6, -12], [0, -26], [-6, -12]], 478, 492, "#3f8f5a", rot=ang, z=-90, **kw)
    # floor decor
    S.ell(288, 850, 250, 56, "#b86a5c", z=-92, **kw); S.ell(288, 850, 210, 42, "#e0b9a0", z=-91, **kw); S.ell(288, 850, 150, 28, "#b86a5c", z=-90, **kw)
    S.ell(288, 778, 160, 16, "#000000", z=-80, alpha=0.28, **kw)
    S.rrect(148, 742, 34, 38, 8, "#b86a5c", z=-30, **kw)
    for ang in (-50, -15, 20, 55): S.poly([[0, 0], [9, -22], [0, -50], [-9, -22]], 148, 726, "#3f8f5a", rot=ang, z=-31, outline=INK, ow=1, **kw)
    # couch (front)
    S.rrect(288, 640, 276, 136, 30, "#7a5c9e", z=-60, outline=INK, ow=2, **kw)
    S.rrect(168, 714, 34, 114, 16, "#7a5c9e", z=-56, outline=INK, ow=2, **kw); S.rrect(408, 714, 34, 114, 16, "#7a5c9e", z=-56, outline=INK, ow=2, **kw)
    S.rrect(288, 736, 238, 56, 18, "#68508a", z=-55, outline=INK, ow=2, **kw)
    S.line(288, 712, 288, 764, "#503d6c", 2, z=-54, **kw)
    S.rect(206, 770, 10, 12, "#3a2d22", z=-61, **kw); S.rect(370, 770, 10, 12, "#3a2d22", z=-61, **kw)
    S.rrect(222, 668, 52, 48, 14, "#5aa6a0", rot=-8, z=-50, outline=INK, ow=1.5, **kw)
    S.rrect(354, 668, 52, 48, 14, "#f0b24a", rot=8, z=-50, outline=INK, ow=1.5, **kw)
    # lamp and side table (right)
    S.rrect(440, 748, 60, 44, 6, "#6a4a2f", z=-70, outline=INK, ow=1.5, **kw)
    S.rect(440, 696, 8, 70, "#6a5a45", z=-69, **kw); S.rrect(440, 724, 28, 6, 3, "#6a5a45", z=-69, **kw)
    S.poly([[0, 0], [54, 0], [44, 40], [10, 40]], 413, 626, "#f7dc9a", outline=INK, ow=2, z=-68, **kw)
    S.glow(440, 650, 190, "#ffc66e", 0.55, z=-85, name="lamp_glow", alpha=(0.0 if lamp_t else 0.35), show=show, keys=(fade(*lamp_t) if lamp_t else []))
    S.rrect(420, 722, 18, 20, 4, "#ffffff", z=-60, outline=INK, ow=1.2, **kw); S.line(428, 716, 430, 710, "#ffffff", 1.5, z=-60, alpha=0.5, **kw)
    if with_blanket:
        S.rrect(288, 722, 170, 56, 20, "#d9a05b", z=4, outline=INK, ow=2, **kw)
        for xx in range(212, 372, 18): S.line(xx, 700, xx + 6, 745, "#b98240", 2, z=5, **kw)
    if with_phone:
        S.rrect(288, 726, 38, 68, 8, "#2a2a30", z=8, outline=INK, ow=1.5, **kw)
        S.glow(288, 700, 70, "#cfe6ff", 0.25, z=7, **kw)


def phone_flat(S, show, cx=288, cy=520, key=None):
    kw = dict(show=show); a = {"alpha": 0.0, "keys": key} if key else {}
    S.rrect(cx + 158, cy - 90, 5, 70, 2, "#0c0c10", z=202, **kw, **a); S.rrect(cx - 158, cy - 120, 5, 46, 2, "#0c0c10", z=202, **kw, **a)
    S.rrect(cx, cy, 316, 654, 52, "#15151a", z=200, outline="#3a3a44", ow=2, **kw, **a)
    S.rrect(cx, cy, 292, 630, 40, "#00ff00", z=201, **kw, **a)
    S.rrect(cx, cy - 292, 84, 24, 12, "#050507", z=205, **kw, **a)


def phone_persp(S, show, cx=288, cy=520, key=None):
    kw = dict(show=show); a = {"alpha": 1.0, "keys": key} if key else {}
    S.poly([[-132, -300], [132, -300], [164, 330], [-164, 330]], cx, cy, "#15151a", outline="#3a3a44", ow=2, z=200, **kw, **a)
    S.poly([[-118, -276], [118, -276], [146, 304], [-146, 304]], cx, cy, "#00ff00", z=201, **kw, **a)
    S.rrect(cx, cy - 262, 70, 20, 10, "#050507", z=205, **kw, **a)


def ipad_flat(S, show, cx=288, cy=520, key=None):
    kw = dict(show=show); a = {"alpha": 0.0, "keys": key} if key else {}
    S.rrect(cx, cy, 484, 640, 54, "#d98b5f", z=198, outline=INK, ow=3, **kw, **a)                       # folio case
    S.rrect(cx, cy, 448, 604, 40, "#101014", z=200, outline="#3a3a44", ow=2, **kw, **a)                    # bezel
    S.rrect(cx, cy, 420, 576, 14, "#00ff00", z=201, **kw, **a)                                              # screen
    S.circ(cx, cy - 295, 4.5, "#2e3340", z=202, **kw, **a); S.circ(cx, cy - 295, 2, "#0a0c14", z=203, **kw, **a)
    S.rrect(cx - 110, cy - 322, 60, 6, 3, "#1b1b20", z=199, **kw, **a)                                      # top button on the case edge


def ipad_persp(S, show, cx=288, cy=520, key=None):
    kw = dict(show=show); a = {"alpha": 1.0, "keys": key} if key else {}
    S.poly([[-210, -300], [210, -300], [258, 320], [-258, 320]], cx, cy, "#d98b5f", outline=INK, ow=3, z=198, **kw, **a)
    S.poly([[-190, -282], [190, -282], [236, 300], [-236, 300]], cx, cy, "#101014", outline="#3a3a44", ow=2, z=200, **kw, **a)
    S.poly([[-172, -262], [172, -262], [214, 280], [-214, 280]], cx, cy, "#00ff00", z=201, **kw, **a)


def hands_phone(S, show, key=None):
    kw = dict(show=show); a = {"keys": key} if key else {}
    S.rrect(60, 790, 150, 220, 70, "#f4f4f4", rot=14, z=232, outline=INK, ow=6, **kw, **a)           # left hand
    S.rrect(560, 860, 150, 250, 70, "#f4f4f4", rot=-12, z=232, outline=INK, ow=6, **kw, **a)         # right hand
    S.rrect(188, 760, 58, 100, 28, "#f4f4f4", rot=-28, z=233, outline=INK, ow=5, **kw, **a)          # left thumb over the bezel edge
    S.rrect(420, 790, 58, 100, 28, "#f4f4f4", rot=26, z=233, outline=INK, ow=5, **kw, **a)           # right thumb over the bezel edge


def hands_ipad(S, show, key=None):
    kw = dict(show=show); a = {"keys": key} if key else {}
    S.rrect(30, 720, 140, 230, 66, "#f4f4f4", rot=10, z=232, outline=INK, ow=6, **kw, **a)
    S.rrect(548, 740, 140, 230, 66, "#f4f4f4", rot=-10, z=232, outline=INK, ow=6, **kw, **a)
    S.rrect(104, 690, 52, 92, 26, "#f4f4f4", rot=-24, z=233, outline=INK, ow=5, **kw, **a)
    S.rrect(474, 700, 52, 92, 26, "#f4f4f4", rot=24, z=233, outline=INK, ow=5, **kw, **a)


def ots_person(S, show, key=None):
    kw = dict(show=show); a = {"keys": key} if key else {}
    S.circ(-210, 60, 240, "#3b2a1e", z=220, outline=INK, ow=7, **kw, **a)                    # back of head (hair)
    S.ell(-150, 20, 130, 90, "#5a4230", z=221, alpha=0.55, **kw, **a)                         # hair highlight
    for k in range(7): S.line(-380 + k * 40, 120 + (k % 3) * 20, -330 + k * 40, 260 + (k % 2) * 30, "#241810", 4, z=221, alpha=0.6, **kw, **a)
    S.ell(28, 120, 34, 54, "#f4f4f4", z=221, outline=INK, ow=5, **kw, **a)                    # ear
    S.rrect(-200, 300, 120, 150, 40, "#f4f4f4", z=219, outline=INK, ow=6, **kw, **a)         # neck
    S.rrect(-330, 650, 980, 560, 250, "#f4f4f4", z=222, outline=INK, ow=7, **kw, **a)        # shoulders and back
    S.line(-200, 400, -200, 900, "#c9c9d0", 6, z=223, **kw, **a)                              # spine seam
    S.rrect(60, 880, 130, 460, 60, "#f4f4f4", rot=-38, z=224, outline=INK, ow=6, **kw, **a)  # forearm
    S.line(10, 800, 90, 900, "#c9c9d0", 5, z=225, **kw, **a)


def drift(S, names, t0, t1, dx, dy=0):
    for n in names:
        o = S.o[n]; k = list(o.get("keys", []))
        x0, y0 = o["x"], o["y"]
        if o["kind"] == "line":
            x2, y2 = o["x2"], o["y2"]
            k += [{"t": t0, "x": x0, "y": y0, "x2": x2, "y2": y2}, {"t": t1, "x": x0 + dx, "y": y0 + dy, "x2": x2 + dx, "y2": y2 + dy, "ease": "inout"}]
        else:
            k += [{"t": t0, "x": x0, "y": y0}, {"t": t1, "x": x0 + dx, "y": y0 + dy, "ease": "inout"}]
        o["keys"] = k


def fade_all(S, names, t0, t1, a0, a1):
    for n in names: S.o[n]["keys"] = fade(t0, t1, a0, a1)


def dip(S, t_in0, t_in1, t_out0, t_out1, color="#14161c"):
    S.rect(288, 512, 700, 1200, color, z=150, space="screen", alpha=0.0,
           keys=[{"t": t_in0, "alpha": 0.0}, {"t": t_in1, "alpha": 1.0, "ease": "in"}, {"t": t_out0, "alpha": 1.0}, {"t": t_out1, "alpha": 0.0, "ease": "out"}])


def hook(S, lines, t0, t1, y=140, size=30, x=230):
    for i, s in enumerate(lines):
        S.add("text", text=s, x=x, y=y + i * 44, size=size, fill="#ffffff", outline=INK, ow=5, weight=800, space="screen", z=190, show=[t0, t1],
              keys=[{"t": t0, "alpha": 0.0}, {"t": t0 + 0.3, "alpha": 1.0, "ease": "out"}, {"t": t1 - 0.3, "alpha": 1.0}, {"t": t1, "alpha": 0.0}])


def stage_bg(S, show):
    kw = dict(show=show)
    S.rect(288, 520, 3200, 3200, "#20232d", z=-100, **kw)
    for (x, y, r, c, s) in ((900, 150, 300, "#ffb86b", 0.5), (-250, 860, 340, "#ff8a5c", 0.35), (760, 980, 260, "#6aa5ff", 0.3), (240, -180, 280, "#ffd27a", 0.3)):
        S.glow(x, y, r, c, s, z=-95, **kw)


def scene_a():
    S = Scene()
    ROOM, STAGE = [0, 5.95], [5.8, 13.5]
    living_room(S, ROOM, with_phone=True, lamp_t=(3.0, 4.2))
    # time-lapse: clock spins, light sweeps, window goes dusk then night, room dims
    S.o["clock_h"]["keys"] = [{"t": 2.6, "rot": 60}, {"t": 4.4, "rot": 420, "ease": "linear"}]
    S.o["clock_m"]["keys"] = [{"t": 2.6, "rot": 0}, {"t": 4.4, "rot": 4320, "ease": "linear"}]
    S.o["win_dusk"]["keys"] = [{"t": 2.9, "alpha": 0.0}, {"t": 3.5, "alpha": 0.95, "ease": "inout"}, {"t": 4.3, "alpha": 0.0}]
    S.o["win_night"]["keys"] = [{"t": 3.6, "alpha": 0.0}, {"t": 4.3, "alpha": 1.0, "ease": "inout"}]
    S.poly([[0, 0], [90, 0], [150, 190], [60, 190]], 90, 770, "#fff3c4", z=-60, alpha=0.0, show=ROOM,
           keys=[{"t": 2.5, "alpha": 0.0, "x": 90}, {"t": 2.8, "alpha": 0.3}, {"t": 4.0, "alpha": 0.3, "x": 300, "ease": "linear"}, {"t": 4.3, "alpha": 0.0}])
    S.rect(288, 512, 700, 1200, "#0a1030", z=80, space="screen", alpha=0.0, show=ROOM,
           keys=[{"t": 2.6, "alpha": 0.0}, {"t": 4.3, "alpha": 0.34, "ease": "inout"}])
    hook(S, ["ONE MORE GAME."], 0.1, 2.7)
    hook(S, ["1 HOUR LATER."], 4.45, 5.85)
    dip(S, 5.45, 5.85, 5.95, 6.4)
    stage_bg(S, STAGE)
    S.rrect(200, 1300, 1900, 700, 220, "#7a5c9e", z=-60, outline=INK, ow=4, show=STAGE)
    S.rrect(760, 1050, 400, 300, 90, "#f0b24a", z=-55, rot=14, outline=INK, ow=4, show=STAGE)
    S.glow(288, 520, 760, "#cfe6ff", 0.3, z=150, show=STAGE, blend="add")
    phone_persp(S, STAGE, key=[{"t": 7.2, "alpha": 1.0}, {"t": 8.0, "alpha": 0.0, "ease": "inout"}])
    phone_flat(S, STAGE, key=[{"t": 7.2, "alpha": 0.0}, {"t": 8.0, "alpha": 1.0, "ease": "inout"}])
    pre = set(S.o)
    hands_phone(S, STAGE); ots_person(S, STAGE)
    drift(S, [n for n in S.o if n not in pre], 7.0, 8.7, -1300, 200)
    actors = {
        "hero": dict(x=288, ground=FLOORY, z=0, keys=[
            {"t": 0.0, "pose": "stand", "yaw": 90, "expr": "calm"},
            {"t": 0.7, "pose": "stand", "yaw": 90, "expr": "happy", "ease": "linear"},
            {"t": 1.4, "pose": "sit", "yaw": 90, "expr": "happy", "head": 14, "hand_r_at": [304, 728], "hand_l_at": [272, 728], "ease": "out"},
            {"t": 4.5, "expr": "smirk"},
            {"t": 5.8, "hand_r_at": None, "hand_l_at": None, "ease": "step"},
            {"t": 5.9, "x": -900, "ease": "step"}]),
        "friend": dict(x=640, ground=FLOORY, z=3, tint="#9ec9ff", keys=[
            {"t": 2.7, "x": 640, "yaw": 180, "pose": "stand", "anim": "run"},
            {"t": 3.1, "x": -140, "ease": "linear"},
            {"t": 3.3, "x": -140, "yaw": 90, "ease": "step"},
            {"t": 3.8, "x": 640, "ease": "linear"},
            {"t": 4.0, "x": 640, "yaw": 180, "anim": "walk", "ease": "step"},
            {"t": 4.9, "x": 410, "ease": "linear"},
            {"t": 5.0, "anim": None, "pose": "shrug", "expr": "sad"},
            {"t": 5.9, "x": -900, "ease": "step"}]),
    }
    camera = {"zoom": 1.45, "cx": 288, "cy": 610, "keys": [
        {"t": 0, "zoom": 1.45, "cx": 288, "cy": 610}, {"t": 5.6, "zoom": 1.5, "cx": 288, "cy": 610},
        {"t": 5.9, "zoom": 0.6, "cx": 60, "cy": 430, "ease": "step"},
        {"t": 6.4, "zoom": 0.6, "cx": 60, "cy": 430},
        {"t": 8.6, "zoom": 1.0, "cx": 288, "cy": 520, "ease": "inout"}]}
    audio = {"master": 0.8, "cues": [
        {"sfx": "whoosh", "t": 1.0, "gain": 0.12}, {"sfx": "whoosh", "t": 2.2, "gain": 0.4}, {"sfx": "shimmer", "t": 2.9, "gain": 0.16},
        {"sfx": "shimmer", "t": 3.6, "gain": 0.12}, {"sfx": "whoosh", "t": 5.2, "gain": 0.3}, {"sfx": "shimmer", "t": 6.4, "gain": 0.2},
        {"sfx": "whoosh", "t": 7.0, "gain": 0.2}]}
    return {"canvas": dict(CANVAS, duration=13.5), "camera": camera, "actors": actors, "objects": S.o, "audio": audio}


def scene_b():
    S = Scene()
    ROOM, STAGE = [0, 4.95], [4.8, 12.5]
    living_room(S, ROOM, with_blanket=True)
    S.rrect(288, 700, 92, 14, 5, "#1b1b1f", rot=-6, z=5, outline=INK, ow=1.5, show=ROOM)
    S.glow(288, 650, 110, "#cfe6ff", 0.3, z=3, show=ROOM)
    hook(S, ["EVERYONE IS", "PLAYING GTA 6."], 0.1, 2.5)
    hook(S, ["ME:"], 2.75, 4.5, y=165, size=42, x=120)
    dip(S, 4.45, 4.85, 4.95, 5.4)
    stage_bg(S, STAGE)
    S.rrect(288, 1230, 1900, 800, 200, "#d9a05b", z=-60, outline=INK, ow=4, show=STAGE)
    for xx in range(-500, 1100, 90): S.line(xx, 900, xx + 40, 1600, "#b98240", 4, z=-59, show=STAGE)
    S.glow(288, 520, 760, "#cfe6ff", 0.3, z=150, show=STAGE, blend="add")
    ipad_persp(S, STAGE, key=[{"t": 6.1, "alpha": 1.0}, {"t": 6.9, "alpha": 0.0, "ease": "inout"}])
    ipad_flat(S, STAGE, key=[{"t": 6.1, "alpha": 0.0}, {"t": 6.9, "alpha": 1.0, "ease": "inout"}])
    pre = set(S.o)
    hands_ipad(S, STAGE); ots_person(S, STAGE)
    drift(S, [n for n in S.o if n not in pre], 6.0, 7.6, -1300, 200)
    actors = {"hero": dict(x=288, ground=FLOORY, z=0, keys=[
        {"t": 0.0, "pose": "sit", "yaw": 90, "expr": "calm", "head": 10},
        {"t": 2.7, "expr": "sleepy"},
        {"t": 4.9, "x": -900, "ease": "step"}])}
    camera = {"zoom": 1.45, "cx": 288, "cy": 610, "keys": [
        {"t": 0, "zoom": 1.45, "cx": 288, "cy": 610}, {"t": 2.2, "zoom": 1.45, "cx": 288, "cy": 610},
        {"t": 4.5, "zoom": 2.1, "cx": 288, "cy": 660, "ease": "inout"},
        {"t": 4.8, "zoom": 0.6, "cx": 60, "cy": 430, "ease": "step"},
        {"t": 5.3, "zoom": 0.6, "cx": 60, "cy": 430},
        {"t": 7.5, "zoom": 1.0, "cx": 288, "cy": 520, "ease": "inout"}]}
    audio = {"master": 0.8, "cues": [
        {"sfx": "whoosh", "t": 2.3, "gain": 0.16}, {"sfx": "whoosh", "t": 4.1, "gain": 0.3},
        {"sfx": "shimmer", "t": 5.3, "gain": 0.2}, {"sfx": "whoosh", "t": 5.9, "gain": 0.2}]}
    return {"canvas": dict(CANVAS, duration=12.5), "camera": camera, "actors": actors, "objects": S.o, "audio": audio}


if __name__ == "__main__":
    for name, sc in (("promo2_a_one_more_game", scene_a()), ("promo2_b_cozy_ipad", scene_b())):
        json.dump(sc, open(os.path.join(HERE, name + ".json"), "w"))
        print("wrote", name, len(sc["objects"]), "objects")
