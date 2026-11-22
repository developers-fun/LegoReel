"""Promo v3 (2026-11-21 evening, round 2). People lie on the couch. The over-the-shoulder shot is tilted ("crooked") and stays tilted
to the end; a finger drags pieces on the screen and lets go when each piece is placed (drawn over the green so it can stay on top of the
real recording: see tools/overlay_recording.py). One plain whoosh for the zoom, no other zoom sounds.
A (Sand Blast!): opens as a walk-in-from-behind shot that keeps zooming into the phone. B (Lazy Blocks): lying on the couch with an iPad.
Run: python3 scenes/promo_v3.py   (writes promo3_*.json and promo3_geometry.json)"""
import json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from promo_v2 import Scene, fade, living_room, hook, dip, INK, FLOORY, CANVAS, rr

P = (288, 520)          # device centre in world space at the hold


class TS(Scene):
    """Scene whose tilt-flagged objects are rotated by th degrees about P (positive = clockwise on screen)."""
    def __init__(self, th):
        super().__init__(); self.th = th; self.tilt = False
    def T(self, x, y):
        a = math.radians(self.th); dx, dy = x - P[0], y - P[1]
        return [round(P[0] + dx * math.cos(a) - dy * math.sin(a), 2), round(P[1] + dx * math.sin(a) + dy * math.cos(a), 2)]
    def add(self, kind, name=None, **kw):
        if self.tilt:
            if "x" in kw and "y" in kw and kind != "text": kw["x"], kw["y"] = self.T(kw["x"], kw["y"])
            if kind == "line": kw["x2"], kw["y2"] = self.T(kw["x2"], kw["y2"])
            if kind in ("rect", "ellipse", "poly", "rays", "sprite"): kw["rot"] = kw.get("rot", 0) + self.th
        return super().add(kind, name, **kw)


def drift(S, names, t0, t1, dx, dy=0):
    for n in names:
        o = S.o[n]; k = list(o.get("keys", [])); x0, y0 = o["x"], o["y"]
        if o["kind"] == "line":
            x2, y2 = o["x2"], o["y2"]
            k += [{"t": t0, "x": x0, "y": y0, "x2": x2, "y2": y2}, {"t": t1, "x": x0 + dx, "y": y0 + dy, "x2": x2 + dx, "y2": y2 + dy, "ease": "inout"}]
        else:
            k += [{"t": t0, "x": x0, "y": y0}, {"t": t1, "x": x0 + dx, "y": y0 + dy, "ease": "inout"}]
        o["keys"] = k


def wall(S, show, timelapse=None):
    """Far wall and foreground couch, tilted. timelapse=(t0,t1,t2) makes the window go day to night and spins the clock."""
    S.tilt = True; kw = dict(show=show)
    S.rect(288, 520, 4200, 4200, "#3a3f4f", z=-100, **kw)
    for x in range(-700, 1400, 64): S.rect(x, 520, 30, 3600, "#434a5d", z=-99, **kw)
    S.rect(288, 300, 4200, 10, "#59627a", z=-97, **kw)                       # picture rail
    # window right, with curtains
    S.rect(660, -10, 350, 480, "#e8e2d0", z=-90, **kw)
    S.rect(660, -10, 318, 448, "#8fb8e8", z=-89, name="win_day", **kw)
    S.rect(660, -10, 318, 448, "#e8884f", z=-88, name="win_dusk", alpha=0.0, **kw)
    S.rect(660, -10, 318, 448, "#1c2754", z=-87, name="win_night", alpha=0.0, **kw)
    S.rect(660, -10, 10, 448, "#e8e2d0", z=-86, **kw); S.rect(660, -10, 318, 10, "#e8e2d0", z=-86, **kw)
    S.poly([[0, 0], [70, 0], [60, 520], [0, 520]], 470, -20, "#c76d5a", outline=INK, ow=2, z=-85, **kw)
    S.poly([[0, 0], [70, 0], [70, 520], [14, 520]], 850, -20, "#c76d5a", outline=INK, ow=2, z=-85, **kw)
    S.rect(660, -270, 400, 14, "#59432f", z=-84, **kw)
    S.glow(700, 40, 520, "#ffc66e", 0.35, z=-80, **kw)
    # clock, frames, shelf
    S.circ(250, -230, 80, "#f3efe4", outline=INK, ow=5, z=-90, **kw)
    for k in range(12):
        a = math.radians(30 * k); S.line(250 + 64 * math.sin(a), -230 - 64 * math.cos(a), 250 + 72 * math.sin(a), -230 - 72 * math.cos(a), INK, 4, z=-89, **kw)
    th = S.th
    hk = [{"t": 0, "rot": th + 60}]; mk = [{"t": 0, "rot": th}]
    if timelapse:
        a0, a1 = timelapse[0], timelapse[2]
        hk = [{"t": a0, "rot": th + 60}, {"t": a1, "rot": th + 420, "ease": "linear"}]; mk = [{"t": a0, "rot": th}, {"t": a1, "rot": th + 4320, "ease": "linear"}]
    S.poly([[-4, 0], [4, 0], [4, -44], [-4, -44]], 250, -230, INK, z=-88, keys=hk, **kw)
    S.poly([[-3, 0], [3, 0], [3, -64], [-3, -64]], 250, -230, INK, z=-87, keys=mk, **kw)
    S.circ(250, -230, 7, INK, z=-86, **kw)
    S.rect(50, -300, 110, 140, "#e8e2d0", z=-90, outline=INK, ow=3, **kw); S.rect(50, -300, 86, 116, "#d2745a", z=-89, **kw); S.circ(50, -320, 18, "#f0c36a", z=-88, **kw)
    S.rect(420, -310, 90, 120, "#e8e2d0", z=-90, outline=INK, ow=3, **kw); S.rect(420, -310, 68, 98, "#5aa6a0", z=-89, **kw)
    S.poly([[0, 0], [30, -50], [60, 0]], 390, -290, "#2e7d74", z=-88, **kw)
    S.rect(330, -50, 260, 14, "#6a4a2f", z=-90, **kw)
    for i, (c, h) in enumerate((("#d2745a", 86), ("#5aa6a0", 74), ("#f0c36a", 94), ("#7a5c9e", 80), ("#c76d5a", 70))):
        S.rect(238 + i * 26, -57 - h / 2, 22, h, c, z=-89, outline=INK, ow=2, **kw)
    # foreground couch, cushions, blanket
    S.rrect(200, 1300, 1900, 700, 220, "#7a5c9e", z=-60, outline=INK, ow=4, **kw)
    S.rrect(760, 1050, 400, 300, 90, "#f0b24a", z=-55, rot=14, outline=INK, ow=4, **kw)
    S.rrect(440, 1110, 300, 210, 70, "#5aa6a0", z=-54, rot=-8, outline=INK, ow=4, **kw)
    S.rrect(-60, 1040, 560, 230, 80, "#d9a05b", z=-53, rot=-6, outline=INK, ow=4, **kw)
    for xx in range(-250, 180, 70): S.line(xx, 960, xx + 24, 1130, "#b98240", 4, z=-52, **kw)
    if timelapse:
        t0, t1, t2 = timelapse
        S.o["win_dusk"]["keys"] = [{"t": t0 + 0.2, "alpha": 0.0}, {"t": t0 + 0.9, "alpha": 0.95, "ease": "inout"}, {"t": t2, "alpha": 0.0}]
        S.o["win_night"]["keys"] = [{"t": t0 + 1.0, "alpha": 0.0}, {"t": t2, "alpha": 1.0, "ease": "inout"}]
        S.poly([[0, 0], [150, 0], [260, 900], [60, 900]], -150, -300, "#fff3c4", z=-70, alpha=0.0, show=show,
               keys=[{"t": t0 - 0.1, "alpha": 0.0, "x": S.T(-150, -300)[0]}, {"t": t0 + 0.3, "alpha": 0.28}, {"t": t2 - 0.3, "alpha": 0.28, "x": S.T(900, -300)[0], "ease": "linear"}, {"t": t2, "alpha": 0.0}])
    S.tilt = False


def person(S, show):
    """Head, shoulders and the right arm of the person lying on the couch, seen from behind the head. Returns the object names."""
    S.tilt = True; kw = dict(show=show); pre = set(S.o)
    S.rrect(-250, 330, 520, 230, 90, "#e8e2d0", z=218, outline=INK, ow=6, **kw)             # pillow
    S.circ(-210, 60, 240, "#3b2a1e", z=220, outline=INK, ow=7, **kw)                           # hair
    S.ell(-150, 20, 130, 90, "#5a4230", z=221, alpha=0.55, **kw)
    for k in range(7): S.line(-380 + k * 40, 120 + (k % 3) * 20, -330 + k * 40, 260 + (k % 2) * 30, "#241810", 4, z=221, **kw)
    S.ell(28, 120, 34, 54, "#f4f4f4", z=221, outline=INK, ow=5, **kw)                          # ear
    S.rrect(-200, 300, 120, 150, 40, "#f4f4f4", z=219, outline=INK, ow=6, **kw)               # neck
    S.rrect(-330, 650, 980, 560, 250, "#f4f4f4", z=222, outline=INK, ow=7, **kw)              # shoulders
    S.line(-200, 400, -200, 900, "#c9c9d0", 6, z=223, **kw)
    S.rrect(60, 880, 130, 460, 60, "#f4f4f4", rot=-38, z=224, outline=INK, ow=6, **kw)        # forearm
    S.line(10, 800, 90, 900, "#c9c9d0", 5, z=225, **kw)
    S.rrect(560, 860, 150, 250, 70, "#f4f4f4", rot=-12, z=232, outline=INK, ow=6, **kw)       # right hand on the phone
    S.rrect(420, 790, 58, 100, 28, "#f4f4f4", rot=26, z=233, outline=INK, ow=5, **kw)         # right thumb
    S.tilt = False
    return [n for n in S.o if n not in pre]


def left_hand(S, show, ipad=False):
    S.tilt = True; kw = dict(show=show)
    if ipad:
        S.rrect(30, 760, 150, 250, 70, "#f4f4f4", rot=10, z=232, outline=INK, ow=6, **kw); S.rrect(122, 690, 52, 92, 26, "#f4f4f4", rot=-24, z=233, outline=INK, ow=5, **kw)
    else:
        S.rrect(60, 790, 150, 220, 70, "#f4f4f4", rot=14, z=232, outline=INK, ow=6, **kw); S.rrect(188, 760, 58, 100, 28, "#f4f4f4", rot=-28, z=233, outline=INK, ow=5, **kw)
    S.tilt = False


def phone(S, show, key_persp, key_flat):
    S.tilt = True; kw = dict(show=show)
    S.poly([[-132, -300], [132, -300], [164, 330], [-164, 330]], 288, 520, "#15151a", outline="#3a3a44", ow=2, z=200, alpha=1.0, keys=key_persp, **kw)
    S.poly([[-118, -276], [118, -276], [146, 304], [-146, 304]], 288, 520, "#00ff00", z=201, alpha=1.0, keys=key_persp, **kw)
    S.rrect(288, 258, 70, 20, 10, "#050507", z=205, alpha=1.0, keys=key_persp, **kw)
    a = dict(alpha=0.0, keys=key_flat)
    S.rrect(446, 430, 5, 70, 2, "#0c0c10", z=202, **kw, **a); S.rrect(130, 400, 5, 46, 2, "#0c0c10", z=202, **kw, **a)
    S.rrect(288, 520, 316, 654, 52, "#15151a", z=200, outline="#3a3a44", ow=2, **kw, **a)
    S.rrect(288, 520, 292, 630, 40, "#00ff00", z=201, **kw, **a)
    S.rrect(288, 228, 84, 24, 12, "#050507", z=205, **kw, **a)
    S.tilt = False


def ipad(S, show, key_persp, key_flat):
    S.tilt = True; kw = dict(show=show)
    S.poly([[-210, -300], [210, -300], [258, 320], [-258, 320]], 288, 520, "#d98b5f", outline=INK, ow=3, z=198, alpha=1.0, keys=key_persp, **kw)
    S.poly([[-190, -282], [190, -282], [236, 300], [-236, 300]], 288, 520, "#101014", outline="#3a3a44", ow=2, z=200, alpha=1.0, keys=key_persp, **kw)
    S.poly([[-172, -262], [172, -262], [214, 280], [-214, 280]], 288, 520, "#00ff00", z=201, alpha=1.0, keys=key_persp, **kw)
    a = dict(alpha=0.0, keys=key_flat)
    S.rrect(288, 520, 484, 640, 54, "#d98b5f", z=198, outline=INK, ow=3, **kw, **a)
    S.rrect(288, 520, 448, 604, 40, "#101014", z=200, outline="#3a3a44", ow=2, **kw, **a)
    S.rrect(288, 520, 420, 576, 14, "#00ff00", z=201, **kw, **a)
    S.circ(288, 225, 4.5, "#2e3340", z=202, **kw, **a); S.circ(288, 225, 2, "#0a0c14", z=203, **kw, **a)
    S.rrect(178, 198, 60, 6, 3, "#1b1b20", z=199, **kw, **a)
    S.tilt = False


def finger(S, show, drags, lift=56, L=300, wd=58, dirv=(0.42, 0.91)):
    """One index finger, tip at the contact point, base off the lower right. drags: dicts with t_down, t_up and a=(x,y), b=(x,y)
    relative to the device centre (pre-tilt). The finger touches down, drags, holds a beat, then lifts away when the piece is placed."""
    n = math.hypot(*dirv); d = (dirv[0] / n, dirv[1] / n); phi = -math.degrees(math.atan2(d[0], d[1])) + S.th
    def tip(p): return (P[0] + p[0], P[1] + p[1])
    def away(p, k): return (p[0] + d[0] * k, p[1] + d[1] * k)
    def ctr(p, k=L / 2): q = away(tip(p), k); return S.T(*q)
    keys_f, keys_n, a0 = [], [], drags[0]["a"]
    first = True
    for g in drags:
        far_a = away(g["a"], 300)
        if first:
            keys_f.append({"t": g["t_down"] - 0.7, "p": far_a}); first = False
        keys_f += [{"t": g["t_down"] - 0.22, "p": away(g["a"], 60), "ease": "inout"}, {"t": g["t_down"], "p": g["a"], "ease": "inout"},
                   {"t": g["t_up"], "p": g["b"], "ease": "inout"}, {"t": g["t_up"] + 0.14, "p": g["b"]},
                   {"t": g["t_up"] + 0.34, "p": away(g["b"], lift), "ease": "out"}, {"t": g["t_up"] + 0.7, "p": away(g["b"], 300), "ease": "inout"}]
    def mk(k, off):
        out = []
        for e in keys_f:
            c = S.T(*away(tip(e["p"]), off)); out.append({"t": round(e["t"], 3), "x": c[0], "y": c[1], **({"ease": e["ease"]} if "ease" in e else {})})
        return out
    t0 = keys_f[0]["t"]; kf = mk(keys_f, L / 2); c0 = kf[0]
    S.add("poly", points=rr(wd, L, wd / 2), x=c0["x"], y=c0["y"], rot=phi, fill="#f4f4f4", outline=INK, ow=5, z=240, show=[t0 - 0.05, keys_f[-1]["t"] + 0.05], keys=kf)
    kn = mk(keys_f, 34); S.add("poly", points=rr(wd * 0.56, 40, 12), x=kn[0]["x"], y=kn[0]["y"], rot=phi, fill="#fbe3dc", outline=INK, ow=2.5, z=241, show=[t0 - 0.05, keys_f[-1]["t"] + 0.05], keys=kn)
    for g in drags:                               # touch ring while the finger is down
        k = [{"t": g["t_down"], "x": S.T(*tip(g["a"]))[0], "y": S.T(*tip(g["a"]))[1], "r": 8}, {"t": g["t_down"] + 0.16, "r": 22, "ease": "out"},
             {"t": g["t_up"], "x": S.T(*tip(g["b"]))[0], "y": S.T(*tip(g["b"]))[1], "ease": "inout"}]
        S.add("ring", x=k[0]["x"], y=k[0]["y"], r=8, w=3, color="#ffffff", z=239, show=[g["t_down"], g["t_up"] + 0.12], keys=k)


def cam(S, items):
    keys = []
    for t, z, c, ease in items:
        w = S.T(*c) if isinstance(c, tuple) and len(c) == 2 and c != ("w",) else c
        k = {"t": t, "zoom": z, "cx": w[0], "cy": w[1]}
        if ease: k["ease"] = ease
        keys.append(k)
    return keys


def geometry(name, hold_start, zoom, size, th, rad):
    s = zoom * 1.875
    return {"video": name, "hold_start": hold_start, "centre_px": [P[0] * 0 + 540, 960], "screen_px": [round(size[0] * s), round(size[1] * s)],
            "angle_deg": th, "corner_radius_px": round(rad * s)}


def scene_a(TH=-12):
    S = TS(TH); ROOM = [0, 13.5]
    TL = (2.6, 3.5, 4.3)
    wall(S, ROOM, timelapse=TL)
    hook(S, ["ONE MORE GAME."], 0.1, 2.5)
    hook(S, ["1 HOUR LATER."], 4.5, 6.0)
    S.rect(288, 512, 700, 1200, "#0a1030", z=80, space="screen", alpha=0.0,
           keys=[{"t": 2.5, "alpha": 0.0}, {"t": 4.3, "alpha": 0.36, "ease": "inout"}, {"t": 6.2, "alpha": 0.36}, {"t": 7.6, "alpha": 0.0, "ease": "inout"}])
    names = person(S, ROOM); left_hand(S, ROOM)
    phone(S, ROOM, [{"t": 6.6, "alpha": 1.0}, {"t": 7.7, "alpha": 0.0, "ease": "inout"}], [{"t": 6.6, "alpha": 0.0}, {"t": 7.7, "alpha": 1.0, "ease": "inout"}])
    drift(S, names, 6.2, 8.0, -1300, 200)
    HOLD = 8.3
    finger(S, ROOM, [dict(t_down=8.9, t_up=9.7, a=(30, 215), b=(-40, -10)), dict(t_down=10.7, t_up=11.5, a=(70, 230), b=(20, 60)),
                     dict(t_down=12.5, t_up=13.2, a=(-30, 215), b=(-10, -40))])
    items = [(0.0, 0.55, (330, 330), None)]
    for i in range(1, 8):
        t = 0.35 * i; amp = max(0.0, 1 - max(0, t - 2.4) / 1.1) * 5
        w = S.T(330, 330); items.append((t, 0.55 + 0.05 * t / 2.4, (w[0] + (2 if i % 2 else -2) * amp / 5, w[1] + (amp if i % 2 else -amp)), "inout"))
    keys = []
    for t, z, c, e in items:
        w = c if t else S.T(*c); w = S.T(*c) if t == 0 else c
        k = {"t": t, "zoom": z, "cx": w[0], "cy": w[1]}; k.update({"ease": e} if e else {}); keys.append(k)
    w = S.T(310, 420); keys.append({"t": 4.4, "zoom": 0.74, "cx": w[0], "cy": w[1], "ease": "inout"})
    keys.append({"t": 8.2, "zoom": 1.0, "cx": P[0], "cy": P[1], "ease": "inout"})
    audio = {"master": 0.8, "cues": [{"sfx": "whoosh", "t": 5.4, "gain": 0.32, "pitch": 0.85}]}
    return {"canvas": dict(CANVAS, duration=13.5, bg="#20232d"), "camera": dict(zoom=0.55, cx=keys[0]["cx"], cy=keys[0]["cy"], keys=keys),
            "actors": {}, "objects": S.o, "audio": audio}, geometry("promo3_a_one_more_game", HOLD, 1.0, (292, 630), TH, 40)


def scene_b(TH=-10):
    S = TS(TH); ROOM, STAGE = [0, 4.95], [4.8, 12.5]
    living_room(S, ROOM)
    S.rrect(205, 706, 74, 34, 14, "#e8e2d0", z=-4, outline=INK, ow=2, show=ROOM)                  # pillow under the head
    S.rrect(352, 704, 130, 46, 18, "#d9a05b", z=6, outline=INK, ow=2.5, show=ROOM)                # blanket over the legs
    for xx in range(306, 410, 20): S.line(xx, 684, xx + 5, 722, "#b98240", 2, z=7, show=ROOM)
    S.rrect(318, 700, 64, 40, 6, "#2a2a30", rot=-14, z=6, outline=INK, ow=2, show=ROOM)           # iPad held on the chest (back of it)
    S.glow(262, 690, 100, "#cfe6ff", 0.4, z=5, show=ROOM)
    # sticker face on the lying head (the actor's own face is hidden when the body is pitched flat)
    for dx in (-3.4, 3.4):
        S.add("poly", points=rr(4.2, 1.2, 0.55), x=0, y=0, fill=INK, follow="hero.head", offset=[dx, -0.6], z=20, show=ROOM)
    S.add("poly", points=[[-3, 0], [-1.5, 1.6], [1.5, 1.6], [3, 0], [1.5, 0.9], [-1.5, 0.9]], x=0, y=0, fill=INK, follow="hero.head", offset=[0, 3.6], z=20, show=ROOM)
    for i, (txt, dx, dy, sz) in enumerate((("z", 14, -14, 10), ("Z", 22, -25, 13), ("Z", 31, -38, 16))):
        t0 = 2.8 + i * 0.45
        S.add("text", text=txt, x=0, y=0, size=sz, fill="#ffffff", outline=INK, ow=1.2, weight=800, follow="hero.head", offset=[dx, dy], z=30, show=[t0, 4.8],
              alpha=0.0, keys=[{"t": t0, "alpha": 0.0}, {"t": t0 + 0.35, "alpha": 1.0, "ease": "out"}, {"t": 4.6, "alpha": 1.0}, {"t": 4.8, "alpha": 0.0}])
    hook(S, ["EVERYONE IS", "PLAYING GTA 6."], 0.1, 2.5)
    hook(S, ["ME:"], 2.75, 4.5, y=165, size=42, x=120)
    dip(S, 4.45, 4.85, 4.95, 5.4)
    wall(S, STAGE)
    names = person(S, STAGE); left_hand(S, STAGE, ipad=True)
    ipad(S, STAGE, [{"t": 6.6, "alpha": 1.0}, {"t": 7.4, "alpha": 0.0, "ease": "inout"}], [{"t": 6.6, "alpha": 0.0}, {"t": 7.4, "alpha": 1.0, "ease": "inout"}])
    drift(S, names, 6.2, 7.8, -1300, 200)
    HOLD = 7.6
    finger(S, STAGE, [dict(t_down=8.2, t_up=9.0, a=(40, 200), b=(-30, -20)), dict(t_down=9.9, t_up=10.7, a=(90, 220), b=(40, 40)),
                      dict(t_down=11.6, t_up=12.3, a=(-20, 210), b=(10, -60))])
    actors = {"hero": dict(x=300, ground=715, z=0, keys=[
        {"t": 0.0, "pose": "relax", "yaw": 0, "rot": -88, "head": 60, "expr": "calm", "hand_r_at": [330, 706], "hand_l_at": [304, 708]},
        {"t": 2.7, "expr": "sleepy"}, {"t": 4.9, "x": -900, "hand_r_at": None, "hand_l_at": None, "ease": "step"}])}
    w = S.T(330, 330)
    keys = [{"t": 0, "zoom": 1.45, "cx": 288, "cy": 610}, {"t": 2.2, "zoom": 1.45, "cx": 288, "cy": 610},
            {"t": 4.5, "zoom": 3.0, "cx": 262, "cy": 692, "ease": "inout"},
            {"t": 4.8, "zoom": 0.62, "cx": w[0], "cy": w[1], "ease": "step"}, {"t": 5.3, "zoom": 0.62, "cx": w[0], "cy": w[1]},
            {"t": 7.5, "zoom": 0.92, "cx": P[0], "cy": P[1], "ease": "inout"}]
    audio = {"master": 0.8, "cues": [{"sfx": "whoosh", "t": 2.3, "gain": 0.16}, {"sfx": "whoosh", "t": 5.8, "gain": 0.3, "pitch": 0.85}]}
    return {"canvas": dict(CANVAS, duration=12.5), "camera": {"zoom": 1.45, "cx": 288, "cy": 610, "keys": keys}, "actors": actors,
            "objects": S.o, "audio": audio}, geometry("promo3_b_cozy_ipad", HOLD, 0.92, (420, 576), TH, 14)


if __name__ == "__main__":
    geo = []
    for name, (sc, g) in (("promo3_a_one_more_game", scene_a()), ("promo3_b_cozy_ipad", scene_b())):
        json.dump(sc, open(os.path.join(HERE, name + ".json"), "w")); geo.append(g); print("wrote", name, len(sc["objects"]), "objects")
    json.dump(geo, open(os.path.join(HERE, "promo3_geometry.json"), "w"), indent=1)
