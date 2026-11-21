"""Two original stick-figure promo videos from the owner's storyboards (2026-11-21).
A: Sand Blast! 'one more game' (13 s, hero sits and plays on a phone, camera in front then behind, push in, green phone).
B: Lazy Blocks cozy contrast (12 s, hero on a couch with an iPad, push in, green iPad).
No side-on shots. Game name is not on screen. The green rectangles are for the owner's real recordings.
Run: python3 scenes/promo_sitting.py   -> scenes/promo_a_one_more_game.json, scenes/promo_b_cozy_ipad.json"""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
INK, WALL, FLOOR, ACC, COUCH, COUCH2, GLOW = "#1f1f24", "#2b2d33", "#c9ccd3", "#ff5e4d", "#7a5c9e", "#68508a", "#bfe3ff"
FLOORY = 760
CANVAS = dict(w=576, h=1024, fps=30, scale=1.875, bg=WALL, blur=1, out=[1080, 1920])


def rect(x, y, w, h, fill, z=-50, outline=INK, ow=2, **kw):
    d = dict(kind="rect", x=x, y=y, w=w, h=h, fill=fill, outline=outline, ow=ow, z=z)
    d.update(kw); return d


def room(show=None):
    o = {"wall": rect(288, 512, 600, 1060, WALL, z=-100, outline=None),
         "floor": rect(288, 892, 600, 264, FLOOR, z=-99, outline=None),
         "stripe": rect(288, 705, 600, 12, ACC, z=-98, outline=None)}
    if show:
        for v in o.values(): v["show"] = show
    return o


def couch_front(show):
    return {"cb": rect(288, 640, 270, 130, COUCH, z=-60, show=show),
            "cseat": rect(288, 736, 270, 52, COUCH2, z=-55, show=show),
            "carm_l": rect(166, 712, 30, 110, COUCH, z=-56, show=show),
            "carm_r": rect(410, 712, 30, 110, COUCH, z=-56, show=show)}


def couch_back(show):
    return {"cbk": rect(288, 735, 330, 150, COUCH, z=20, show=show),
            "cbk2": rect(288, 668, 330, 18, COUCH2, z=21, show=show),
            "cbk_seam": dict(kind="line", x=288, y=670, x2=288, y2=808, color="#5b4478", width=2, z=22, show=show)}


def hook(lines, t0, t1, y=150, size=30):
    o = {}
    for i, s in enumerate(lines):
        o[f"hook_{t0}_{i}"] = dict(kind="text", text=s, x=230, y=y + i * 44, size=size, fill="#ffffff", outline=INK, ow=5, weight=800,
                                   space="screen", z=90, show=[t0, t1],
                                   keys=[{"t": t0, "alpha": 0.0}, {"t": t0 + 0.12, "alpha": 1.0, "ease": "out"}])
    return o


def green_phone(t0, t1):
    return {"gp_bezel": rect(288, 520, 312, 650, "#2a2a30", z=200, ow=3, space="screen", show=[t0, t1]),
            "gp_screen": rect(288, 520, 288, 616, "#00ff00", z=201, outline=None, space="screen", show=[t0, t1])}


def green_ipad(t0, t1):
    return {"gi_bezel": rect(288, 520, 432, 576, "#2a2a30", z=200, ow=3, space="screen", show=[t0, t1]),
            "gi_screen": rect(288, 520, 396, 540, "#00ff00", z=201, outline=None, space="screen", show=[t0, t1])}


WIDE = dict(zoom=1.5, cx=288, cy=640)


def scene_a():
    objs = {}
    objs.update(room())
    objs.update(couch_front([0, 5.0]))
    objs.update(couch_back([5.0, 8.0]))
    objs["clock"] = dict(kind="circle", x=288, y=520, r=34, fill="#ffffff", outline=INK, ow=3, z=-40, show=[0, 5.0])
    objs["clock_h"] = dict(kind="line", x=288, y=520, x2=288, y2=496, color=INK, width=4, z=-39, show=[0, 5.0])
    objs["clock_m"] = dict(kind="line", x=288, y=520, x2=310, y2=506, color=INK, width=3, z=-39, show=[0, 2.5])
    objs["clock_m2"] = dict(kind="line", x=288, y=520, x2=288, y2=490, color=INK, width=3, z=-39, show=[2.5, 5.0])
    objs["door"] = rect(430, 600, 80, 320, "#3a3d46", z=-70, show=[0, 5.0])
    objs["door_far"] = rect(120, 600, 80, 320, "#3a3d46", z=-70, show=[5.0, 8.0])
    objs["bag"] = rect(0, 0, 34, 42, ACC, z=6, show=[3.0, 5.0], follow="friend.hand_l", offset=[0, 20])
    objs["ph_front"] = rect(288, 724, 34, 60, "#2a2a30", z=8, ow=2, show=[1.3, 5.0])
    objs["ph_back"] = rect(344, 650, 58, 112, GLOW, z=30, ow=3, show=[6.0, 8.0])
    objs.update(hook(["ONE MORE GAME."], 0.0, 2.5))
    objs.update(hook(["1 HOUR LATER."], 2.5, 5.0))
    objs.update(green_phone(8.0, 13.0))
    actors = {
        "hero": dict(x=288, ground=FLOORY, z=0, keys=[
            {"t": 0.0, "pose": "stand", "yaw": 90, "expr": "calm"},
            {"t": 0.8, "pose": "stand", "yaw": 90, "expr": "happy", "ease": "linear"},
            {"t": 1.4, "pose": "sit", "yaw": 90, "expr": "happy", "head": 14, "hand_r_at": [304, 726], "hand_l_at": [272, 726], "ease": "out"},
            {"t": 5.0, "yaw": 270, "expr": None, "hand_r_at": None, "hand_l_at": None, "ease": "step"},
            {"t": 8.0, "yaw": 270}]),
        "friend": dict(x=560, ground=FLOORY, z=3, keys=[
            {"t": 2.3, "x": 520, "yaw": 180, "pose": "stand", "expr": "calm", "anim": "walk"},
            {"t": 3.2, "x": 396, "ease": "linear"},
            {"t": 3.4, "anim": None, "pose": "shrug", "expr": "sad"},
            {"t": 4.9, "pose": "shrug"},
            {"t": 5.0, "x": 190, "yaw": 180, "anim": "walk", "ease": "step"},
            {"t": 6.4, "x": 90, "ease": "linear"},
            {"t": 6.5, "x": -400, "anim": None, "ease": "step"}]),
    }
    camera = {"zoom": 1.5, "cx": 288, "cy": 640, "keys": [
        {"t": 0, "zoom": 1.5, "cx": 288, "cy": 640},
        {"t": 6.4, "zoom": 1.5, "cx": 288, "cy": 640},
        {"t": 7.95, "zoom": 3.4, "cx": 318, "cy": 650, "ease": "inout"},
        {"t": 8.0, "zoom": 1.0, "cx": 288, "cy": 512, "ease": "step"}]}
    audio = {"master": 0.9, "cues": [
        {"sfx": "pop", "t": 0.0, "gain": 0.3}, {"sfx": "thump", "t": 1.35, "gain": 0.8}, {"sfx": "whoosh", "t": 2.5, "gain": 0.5},
        {"sfx": "step", "times": "friend.step", "gain": 0.35, "pitch_jitter": 0.1}, {"sfx": "tick", "t": 5.0, "gain": 0.3},
        {"sfx": "whoosh", "t": 6.5, "gain": 0.3}, {"sfx": "shimmer", "t": 8.0, "gain": 0.25}]}
    return {"canvas": dict(CANVAS, duration=13.0), "camera": camera, "actors": actors, "objects": objs, "audio": audio}


def scene_b():
    objs = {}
    objs.update(room())
    objs.update(couch_front([0, 4.5]))
    objs.update(couch_back([4.5, 7.0]))
    objs["lamp_pole"] = rect(440, 640, 12, 170, "#6a5a45", z=-70, show=[0, 4.5])
    objs["lamp_shade"] = dict(kind="poly", points=[[0, 0], [46, 0], [38, 34], [8, 34]], x=417, y=520, fill="#ffe7a8", outline=INK, ow=2, z=-69, show=[0, 4.5])
    objs["lamp_glow"] = dict(kind="glow", x=440, y=545, r=140, color="#ffd27a", strength=0.35, z=-95, show=[0, 4.5])
    objs["lamp_pole_b"] = rect(150, 640, 12, 170, "#6a5a45", z=-70, show=[4.5, 7.0])
    objs["lamp_shade_b"] = dict(kind="poly", points=[[0, 0], [46, 0], [38, 34], [8, 34]], x=127, y=520, fill="#ffe7a8", outline=INK, ow=2, z=-69, show=[4.5, 7.0])
    objs["lamp_glow_b"] = dict(kind="glow", x=150, y=545, r=140, color="#ffd27a", strength=0.35, z=-95, show=[4.5, 7.0])
    objs["mug"] = rect(150, 750, 24, 26, "#ffffff", z=-30, show=[0, 4.5])
    objs["blanket"] = rect(288, 712, 150, 40, "#d9a05b", z=4, show=[0, 4.5])
    objs["ipad_lap"] = rect(288, 690, 90, 14, "#1f1f24", z=5, show=[0, 4.5])
    objs["blanket_back"] = dict(kind="poly", points=[[0, 0], [250, 0], [215, 190], [35, 190]], x=163, y=690, fill="#d9a05b", outline=INK, ow=3, z=29, show=[5.5, 7.0])
    objs["ipad_back"] = dict(kind="poly", points=[[0, 0], [150, 0], [126, 120], [24, 120]], x=213, y=720, fill=GLOW, outline=INK, ow=4, z=30, show=[5.5, 7.0])
    objs.update(hook(["EVERYONE IS", "PLAYING GTA 6."], 0.0, 2.5))
    objs.update(hook(["ME:"], 2.5, 4.5, size=40))
    objs.update(green_ipad(7.0, 12.0))
    actors = {"hero": dict(x=288, ground=FLOORY, z=0, keys=[
        {"t": 0.0, "pose": "sit", "yaw": 90, "expr": "calm", "head": 6},
        {"t": 2.5, "expr": "sleepy", "ease": "step"},
        {"t": 4.5, "yaw": 270, "expr": None, "ease": "step"},
        {"t": 7.0, "yaw": 270}])}
    camera = {"zoom": 1.5, "cx": 288, "cy": 640, "keys": [
        {"t": 0, "zoom": 1.5, "cx": 288, "cy": 640},
        {"t": 2.4, "zoom": 1.5, "cx": 288, "cy": 640},
        {"t": 2.5, "zoom": 2.2, "cx": 288, "cy": 660, "ease": "step"},
        {"t": 4.4, "zoom": 2.2, "cx": 288, "cy": 660},
        {"t": 4.5, "zoom": 1.5, "cx": 288, "cy": 640, "ease": "step"},
        {"t": 5.5, "zoom": 1.5, "cx": 288, "cy": 640},
        {"t": 6.95, "zoom": 2.4, "cx": 288, "cy": 700, "ease": "inout"},
        {"t": 7.0, "zoom": 1.0, "cx": 288, "cy": 512, "ease": "step"}]}
    audio = {"master": 0.9, "cues": [
        {"sfx": "pop", "t": 0.0, "gain": 0.3}, {"sfx": "tick", "t": 2.5, "gain": 0.35}, {"sfx": "whoosh", "t": 4.5, "gain": 0.25},
        {"sfx": "whoosh", "t": 5.5, "gain": 0.25}, {"sfx": "tick", "t": 8.0, "gain": 0.2}, {"sfx": "tick", "t": 9.6, "gain": 0.2}]}
    return {"canvas": dict(CANVAS, duration=12.0), "camera": camera, "actors": actors, "objects": objs, "audio": audio}


if __name__ == "__main__":
    for name, sc in (("promo_a_one_more_game", scene_a()), ("promo_b_cozy_ipad", scene_b())):
        json.dump(sc, open(os.path.join(HERE, name + ".json"), "w"), indent=1)
        print("wrote", name)
