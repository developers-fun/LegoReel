"""Sand Blast! "this time it ends differently": the full dig skit, then the two sit down and play.

Copies the beat order and the on-screen words of the cubemonsters "one more game" video (credit them in the
caption): hook text over the first half, YOU and FRIEND digging toward the PIRATE TOKEN in two tunnels, FRIEND
breaks through the floor, they meet, ONE MORE GAME. Then (new) both sit down in the tunnel, a cut from behind,
and a held shot of a flat-green phone for the real Sand Blast! recording.

Shots (hard cuts, fixed cameras, so the house style is untouched):
  dig     0.0 - 7.5   side cutaway. Dirt slices vanish as each digger steps forward, so the digging visibly
                      makes progress; YOU hits the token wall (gold sparks), FRIEND breaks the floor above
  sit     7.5 - 9.0   front-on, both seated with phones
  behind  9.0 - 10.0  from behind, phone glow between them
  hold   10.0 - 15.0  straight-on green phone, nothing else on screen (sized to sit above Instagram's bottom UI)

Needs: `dig` and `phone` pose clips, per-overlay `x` / `size`, and pose `snap` (all added to blockreel 2026-11-21).
Run:  python3 reels/make_dig_skit.py
"""
import json
import math
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent
GREEN = "#00ff00"
DIRT, TUNNEL, FLOOR, GOLD = "#d9a15a", "#a8692f", "#8a5a2b", "#f2c230"
Z2, Z3 = -300.0, -600.0                       # staging areas for the behind shot and the held shot

CAMX = -1.0                                   # cutaway camera looks at x -1 so the left tunnel stays on screen
CAM_A = {"position": [CAMX, 11, 36], "look_at": [CAMX, 11, 0], "fov": 38}


def to_screen(X, Y, Z=0.0):
    d = 36.0 - Z
    hv = 2 * d * math.tan(math.radians(19.0))
    return round(0.5 + (X - CAMX) / (hv * 9 / 16), 4), round(0.5 - (Y - 11.0) / hv, 4)


def box(pid, pos, size, color, **kw):
    d = {"id": pid, "position": pos, "size": size, "color": color, "cast_shadow": False}
    d.update(kw)
    return d


def zone(cx, cz, w=40):
    return {"rect": [cx - w / 2, cz - 12, cx + w / 2, cz + 24], "colors": ["#c98f4a", "#c28945"], "tile": 1.164,
            "variation": 0.01, "line_strength": 0.0, "studs": 0.3}


# ---- digging ---------------------------------------------------------------------------------------------------
HZ = 1.6                                   # chops per second (matches the `dig` pose)
SHOULDER_Y, ARM = 4.0, 1.7
STEP = 0.25                                # seconds a digger takes to step forward


def hand(rx, ry, phase):
    a = math.radians(125.0 + 45.0 * math.sin(phase * 2 * math.pi * HZ))
    return rx + ARM * math.sin(a), ry + SHOULDER_Y - ARM * math.cos(a)


def digger(x0, steps, dig_start):
    """steps = [(t, dx)]. Returns root_x(t), phase_start(t), moving(t) and the step segments."""
    segs = []
    x = x0
    for t, dx in steps:
        segs.append((t, t + STEP, x, x + dx))
        x += dx

    def root(t):
        cur = x0
        for a, b, xa, xb in segs:
            if t >= b:
                cur = xb
            elif t >= a:
                return xa + (xb - xa) * (t - a) / (b - a)
        return cur

    def phase_start(t):
        ps = dig_start
        for a, b, _, _ in segs:
            if t >= b:
                ps = b
        return ps

    def moving(t):
        return any(a <= t < b for a, b, _, _ in segs)

    return root, phase_start, moving, segs


def pick_keys(root, phase_start, moving, ry, t0, t1, end_at, rest):
    h_keys, k_keys = [], []
    t = t0
    while t <= t1 + 1e-6:
        ph = 0.0 if moving(t) else t - phase_start(t)
        hx, hy = hand(root(t), ry, ph)
        h_keys.append({"t": round(t, 3), "position": [round(hx + 1.0, 3), round(hy, 3), 0.75]})
        k_keys.append({"t": round(t, 3), "position": [round(hx + 2.55, 3), round(hy - 0.2, 3), 0.75]})
        t += 0.05
    h_keys.append({"t": end_at, "position": list(rest), "ease": "ease_out"})
    k_keys.append({"t": end_at, "position": [rest[0] + 1.55, rest[1], rest[2]], "ease": "ease_out"})
    return h_keys, k_keys


def build():
    rnd = random.Random(7)
    props = []
    props += [
        box("dirt", [CAMX, 8, -1.5], [40, 44, 1.0], DIRT),
        box("sky", [CAMX, 22.8, -0.95], [40, 9, 0.2], "#b98fd0"),
        box("sun", [CAMX, 18.6, -0.8], [3.2, 3.2, 0.2], "#ffd27a", bevel=0.5),
        box("grass", [CAMX, 17.25, -0.5], [40, 0.5, 1.2], "#6aa84f"),
    ]
    # tunnels and floors (upper tunnel x -9..-1, lower tunnel x -9..1.4)
    props += [
        box("tun_low", [-3.8, 3.3, -0.85], [10.4, 6.6, 0.3], TUNNEL),
        box("tun_up", [-5.0, 11.7, -0.85], [8.0, 6.6, 0.3], TUNNEL),
        box("floor_low", [-3.8, -0.25, 0], [10.4, 0.5, 2.4], FLOOR),
        box("floor_up_left", [-7.25, 8.15, 0], [3.5, 0.5, 2.4], FLOOR),
    ]
    props.append(box("floor_chunk", [-3.25, 8.15, 0], [4.5, 0.5, 2.4], FLOOR, track={"keys": [
        {"t": 0, "position": [-3.25, 8.15, 0]}, {"t": 5.0, "position": [-3.25, 8.15, 0]},
        {"t": 5.9, "position": [-3.25, -3.0, 0.4], "ease": "ease_in"}, {"t": 5.91, "position": [-3.25, -30, 0]}]}))
    props.append(box("hole", [-3.4, 7.5, -0.84], [3.6, 1.8, 0.3], TUNNEL, track={"keys": [
        {"t": 0, "position": [-3.4, 7.5, -6.0]}, {"t": 4.99, "position": [-3.4, 7.5, -6.0]},
        {"t": 5.0, "position": [-3.4, 7.5, -0.84]}]}))

    # YOU (lower tunnel) and FRIEND (upper tunnel): where they stand over time, which dirt slice goes when
    y_steps = [(1.2, 1.0), (2.4, 1.0), (3.6, 1.0), (4.8, 1.0)]
    f_steps = [(2.6, 0.7)]
    y_root, y_ps, y_mov, y_segs = digger(-6.7, y_steps, 0.0)
    f_root, f_ps, f_mov, f_segs = digger(-6.2, f_steps, 0.2)
    slices = [("sY0", -1.7, 3.3, 1.0, 1.2), ("sY1", -0.7, 3.3, 1.0, 2.4), ("sY2", 0.3, 3.3, 1.0, 3.6),
              ("sY3", 1.3, 3.3, 1.0, 4.8),
              ("sF0", -1.35, 11.7, 0.7, 2.6)]
    for pid, x, y, w, t in slices:
        col = rnd.choice(["#d9a15a", "#d4995a", "#dea760"])
        props.append(box(pid, [x, y, -0.7], [w, 6.6, 0.3], col, track={"keys": [
            {"t": 0, "position": [x, y, -0.7]}, {"t": t, "position": [x, y, -0.7]},
            {"t": t + 0.01, "position": [x, -60, -0.7]}]}))

    # token wall, sign, coin, gold cubes
    props += [
        box("tokenwall", [3.6, 7.8, -0.4], [3.6, 15.6, 1.2], "#5a3d0c"),
        box("sign", [3.6, 16.45, -0.2], [3.6, 0.9, 0.5], "#7b4a1a"),
        box("coin", [3.0, 3.0, 0.45], [1.5, 1.5, 0.3], GOLD, bevel=0.35),
    ]
    for i in range(26):
        props.append(box(f"nug{i}", [round(rnd.uniform(2.0, 5.2), 2), round(rnd.uniform(0.5, 15.0), 2), 0.35],
                         [0.55, 0.55, 0.5], rnd.choice([GOLD, "#e0a81c", "#ffd84a"]), bevel=0.2))
    # sparks when YOU's last swing lands on the wall
    for i in range(10):
        ex, ey = 1.7 - rnd.uniform(0.3, 1.8), 3.2 + rnd.uniform(-1.6, 2.6)
        props.append(box(f"spark{i}", [1.8, -60, 0.9], [0.32, 0.32, 0.32], rnd.choice(["#ffe066", "#fff2a8", GOLD]),
                         bevel=0.1, track={"keys": [
                             {"t": 0, "position": [1.8, -60, 0.9]}, {"t": 5.04, "position": [1.8, -60, 0.9]},
                             {"t": 5.05, "position": [1.8, 3.2, 0.9]},
                             {"t": 5.5, "position": [round(ex, 2), round(ey, 2), 0.9], "ease": "ease_out"},
                             {"t": 5.51, "position": [round(ex, 2), -60, 0.9]}]}))
    # pickaxes
    yk_h, yk_k = pick_keys(y_root, y_ps, y_mov, 0.0, 0.0, 5.3, 5.7, [-3.3, 0.2, 1.0])
    fk_h, fk_k = pick_keys(f_root, f_ps, f_mov, 8.4, 0.2, 5.4, 6.0, [-6.4, 0.2, 1.1])
    for pid, keys, size, col in (("pickY_h", yk_h, [3.2, 0.34, 0.34], "#8b5a2b"), ("pickY_k", yk_k, [0.5, 1.9, 0.34], "#b9bec8"),
                                 ("pickF_h", fk_h, [3.2, 0.34, 0.34], "#8b5a2b"), ("pickF_k", fk_k, [0.5, 1.9, 0.34], "#b9bec8")):
        props.append(box(pid, keys[0]["position"], size, col, bevel=0.05, track={"keys": keys}))
    # sit-down phones (backs of the phones face the front camera)
    for pid, x in (("phoneY", -2.0), ("phoneF", 0.0)):
        props.append(box(pid, [x, 0.9, 1.2], [0.62, 1.05, 0.1], "#2a2a30", bevel=0.05, track={"keys": [
            {"t": 0, "position": [x, -40, 0]}, {"t": 7.49, "position": [x, -40, 0]}, {"t": 7.5, "position": [x, 0.9, 1.2]},
            {"t": 8.99, "position": [x, 0.9, 1.2]}, {"t": 9.0, "position": [x, -40, 0]}]}))
    # stage 2: from behind. A small gap between the two lets the phone light show.
    props += [
        box("b_wall", [-1.0, 5, Z2 + 6], [24, 14, 0.5], DIRT),
        box("b_glow", [-1.0, 1.7, Z2 + 1.0], [0.7, 1.1, 0.12], "#9fd6ff", bevel=0.05),
        box("b_floor", [-1.0, -0.25, Z2 + 1], [20, 0.5, 14], FLOOR),
    ]
    # stage 3: the held shot. Flat green phone on a small stand against the dirt wall.
    PHONE, SCREEN = [2.7, 5.7, 0.4], [2.45, 5.4, 0.05]
    props += [
        box("f_wall", [0, 8, Z3 - 3.2], [40, 16, 0.5], DIRT),
        box("f_stand", [0, 0.5, Z3], [2.8, 1.0, 2.0], FLOOR),
        box("f_phone", [0, 3.85, Z3], PHONE, "#2a2a30", bevel=0.12),
        box("f_screen", [0, 3.85, Z3 + 0.22], SCREEN, GREEN, bevel=0.0),
    ]

    chars = {"you": {"avatar": "main", "position": [-6.7, 0, 0], "yaw": 90},
             "friend": {"avatar": "main", "variant": "jacket", "position": [-6.2, 8.4, 0], "yaw": 90}}

    def lab(text, X, Y, t, d, size=0.034):
        sx, sy = to_screen(X, Y)
        return {"t": t, "duration": round(d, 3), "text": text, "style": "label", "size": size, "x": sx, "y": sy}

    sx_sign, sy_sign = to_screen(3.6, 16.45, -0.2)
    labels = []
    # labels hop with the characters (their positions change at each step)
    cuts = [0.0] + [round(b, 3) for _, b, _, _ in y_segs] + [7.5]
    xs = [-6.7, -5.7, -4.7, -3.7, -2.7]
    for i in range(len(xs)):
        labels.append(lab("YOU", xs[i], 6.4, cuts[i], cuts[i + 1] - cuts[i]))
    fcuts = [0.0] + [round(b, 3) for _, b, _, _ in f_segs] + [5.4]
    fxs = [-6.2, -5.5]
    for i in range(len(fxs)):
        labels.append(lab("FRIEND", fxs[i], 14.8, fcuts[i], fcuts[i + 1] - fcuts[i]))
    labels.append(lab("FRIEND", -4.9, 6.4, 6.0, 1.5))

    acts = [{"t": 0.0, "character": "you", "pose": "dig", "snap": True},
            {"t": 0.0, "character": "friend", "pose": "dig", "snap": True}]
    for t, dx in y_steps:
        acts.append({"t": t, "character": "you", "move_to": [round(y_root(t + STEP), 2), 0, 0], "duration": STEP, "then_pose": "dig"})
    for t, dx in f_steps:
        acts.append({"t": t, "character": "friend", "move_to": [round(f_root(t + STEP), 2), 8.4, 0], "duration": STEP, "then_pose": "dig"})
    acts += [
        {"t": 5.3, "character": "you", "pose": "surprised"},
        {"t": 5.4, "character": "friend", "move_to": [-4.9, 0, 0], "duration": 0.5, "then_pose": "idle"},
        {"t": 6.0, "character": "friend", "face": 90, "turn": 0.2},
        {"t": 6.0, "character": "you", "face": -90, "turn": 0.2},
        {"t": 6.2, "character": "you", "pose": "idle"},
        {"t": 6.4, "character": "you", "expression": "happy"},
        {"t": 6.4, "character": "friend", "expression": "happy"}]

    dig = {"id": "dig", "duration": 7.5, "camera": CAM_A, "actions": acts,
           "overlays": [
               {"t": 0.0, "duration": 7.5, "text": "THIS TIME IT ENDS", "style": "hook", "size": 0.045, "y": 0.135},
               {"t": 0.0, "duration": 7.5, "text": "DIFFERENTLY.", "style": "hook", "size": 0.088, "y": 0.18},
               {"t": 0.0, "duration": 7.5, "text": "PIRATE TOKEN", "style": "label", "size": 0.03, "x": sx_sign, "y": sy_sign},
               *labels,
               lab("ONE MORE GAME.", -3.8, 7.9, 6.5, 1.0, 0.038)]}

    def seat(cid, x, z):
        return [{"t": 0, "character": cid, "teleport": [x, -2.0, z]},
                {"t": 0, "character": cid, "face": 0, "turn": 0.0}]

    sit = {"id": "sit", "duration": 1.5,
           "camera": {"position": [-1.0, 2.8, 14.0], "look_at": [-1.0, 2.3, 0], "fov": 42},
           "actions": seat("you", -2.0, 0) + seat("friend", 0.0, 0) + [
               {"t": 0, "character": "you", "pose": "phone", "snap": True},
               {"t": 0, "character": "friend", "pose": "phone", "snap": True},
               {"t": 0, "character": "you", "expression": "calm"}, {"t": 0, "character": "friend", "expression": "calm"}]}
    behind = {"id": "behind", "duration": 1.0,
              "camera": {"position": [-1.0, 3.0, Z2 - 12.5], "look_at": [-1.0, 2.2, Z2], "fov": 42},
              "actions": seat("you", -2.45, Z2) + seat("friend", 0.45, Z2)}
    hold = {"id": "hold", "duration": 5.0,
            "camera": {"position": [0, 3.25, Z3 + 13.3], "look_at": [0, 3.25, Z3], "fov": 38}, "actions": []}
    scene = {
        "meta": {"title": "Sand Blast! dig skit then sit", "style": "house", "width": 1080, "height": 1920, "fps": 30,
                 "supersample": 2,
                 "ground": {"zones": [zone(0, 0), zone(-1, Z2), zone(0, Z3)]},
                 "look": {"vignette": 0.0, "bloom": 0.0, "dof": None, "saturation": 1.0, "contrast": 1.0,
                          "tint": [1.0, 1.0, 1.0], "gloss": 0.0},
                 "light": {"spec_strength": 0.0},
                 "export": {"crf": 18, "preset": "medium"}},
        "characters": chars, "props": props, "shots": [dig, sit, behind, hold]}
    return scene


if __name__ == "__main__":
    path = OUT / "sand_blast_dig_skit.json"
    scene = build()
    path.write_text(json.dumps(scene, indent=1), encoding="utf-8")
    print("wrote", path, "shots:", len(scene["shots"]), "props:", len(scene["props"]))
