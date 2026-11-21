"""Generates demo_three_formats.json: three short pieces, one per format.

All content is original. The brand "Bluebox" and its products are invented for this demo.
  1. Edit run: on-beat cuts between a plain look and a product look, product as the last cut.
  2. Reveal skit: a game-show setup, one reversal, then the product behind the door.
  3. Interactive challenge: follow the mug under the cups, then the reveal.

Every character is the `main` avatar (avatars/main.json) or one of its variants. Every shot has
one fixed camera (a named preset from styles/house.json); the view changes by cutting. No shake.

Run:  py examples/make_demo_scene.py   (writes examples/demo_three_formats.json)
"""
import json
import random
from pathlib import Path

LABEL_Y = 0.075


def shot(sid, dur, camera, actions=(), dialogue=(), overlays=(), label=None, fade_in=0.0, fade_out=0.0):
    ov = list(overlays)
    if label:
        ov.append({"t": 0.0, "duration": dur, "text": label, "style": "label", "y": LABEL_Y})
    s = {"id": sid, "duration": round(dur, 3), "camera": camera, "actions": list(actions)}
    if dialogue:
        s["dialogue"] = list(dialogue)
    if ov:
        s["overlays"] = ov
    if fade_in:
        s["fade_in"] = fade_in
    if fade_out:
        s["fade_out"] = fade_out
    return s


def cam(preset, focus, yaw=0.0, fov=None):
    c = {"preset": preset, "focus": focus, "yaw": yaw}
    if fov:
        c["fov"] = fov
    return c


def fixed(position, look_at, fov):
    return {"position": position, "look_at": look_at, "fov": fov}


characters = {
    # Format 1: one person, two looks. The product look is the jacket variant.
    "plain": {"avatar": "main", "variant": "plain", "position": [-20, 0, 0], "yaw": 0},
    "jacket": {"avatar": "main", "variant": "jacket", "position": [20, 0, 0], "yaw": 0},
    # Format 2: host and contestant, both from the same avatar file
    "host": {"avatar": "main", "variant": "host", "position": [2.5, 0, -297.0], "yaw": -22},
    "guest": {"avatar": "main", "variant": "guest", "position": [-2.5, 0, -297.0], "yaw": 22},
}

props = []
shots = []


ROOT = Path(__file__).resolve().parent.parent


def _have(ids):
    return [i for i in ids if (ROOT / "parts" / "sets" / f"{i}.json").exists()]


TREES = _have(["nature_01", "nature_02", "nature_03", "tree_01"]) or ["tree_01"]
BUSHES = _have(["nature_04"])
ROCKS = _have(["nature_05"])
FLOWERS = _have(["nature_06"])
HILLS = _have(["nature_08"])


def scenery(tag, cx, cz, seed, trees=12, front_clear=4.0):
    """Trees, bushes, rocks, flowers and hills around a stage, so the background is never an empty colour.
    All of it is set templates from parts/sets/. Nothing goes in front of the camera side (z > cz + front_clear)."""
    import math
    rng = random.Random(seed)

    def spot(rmin, rmax, a0=0.0, a1=6.2832):
        for _ in range(200):
            a = rng.uniform(a0, a1)
            r = rng.uniform(rmin, rmax)
            x, z = cx + r * math.cos(a), cz + r * math.sin(a)
            if z <= cz + front_clear:
                return x, z
        return cx - rmin, cz - rmin

    def put(kind, ids, n, rmin, rmax, smin, smax, a0=0.0, a1=6.2832):
        if not ids:
            return
        for i in range(n):
            x, z = spot(rmin, rmax, a0, a1)
            props.append({"id": f"{tag}_{kind}{i}", "template": rng.choice(ids), "position": [round(x, 2), 0, round(z, 2)],
                          "rotation_y": rng.uniform(0, 360), "scale": round(rng.uniform(smin, smax), 2), "cast_shadow": False})

    put("tree", TREES, trees, 12, 42, 0.9, 1.3)
    put("bush", BUSHES, 6, 8, 22, 0.8, 1.3, 3.3, 6.1)
    put("rock", ROCKS, 3, 9, 24, 0.7, 1.2, 3.3, 6.1)
    put("flower", FLOWERS, 6, 6, 16, 0.9, 1.4, 3.3, 6.1)
    for i, (hx, hd, hs) in enumerate(((-26, 55, 44), (6, 62, 52), (34, 52, 40))):       # distant hills
        props.append({"id": f"{tag}_hill{i}", "type": "cylinder", "position": [cx + hx, 1.0, cz - hd],
                      "size": [hs, 12, hs], "color": ["#8fd16a", "#86ca62", "#98d874"][i], "cast_shadow": False, "bevel": 4.5})


zones = []


def plaza(cx, cz, half_x=15.0, front=14.0, back=-14.0):
    zones.append({"rect": [cx - half_x, cz + back, cx + half_x, cz + front],
                  "colors": ["#d3d5db", "#c9ccd3"], "tile": 1.164, "variation": 0.01,
                  "line_strength": 0.0, "studs": 0.3})


# ---------------------------------------------------------------- Format 1: edit run
L1 = "EDIT RUN"
PX, JX = -20, 20
plaza(-20, 0)
plaza(20, 0)
scenery("a1", -20, 0, 11)
scenery("a2", 20, 0, 12)

shots.append(shot("a_hook", 1.8, cam("medium", [PX, 0, 0]),
                  actions=[{"t": 0, "character": "plain", "look": "camera"}],
                  overlays=[{"t": 0.1, "duration": 1.6, "text": "COUNT THE CUTS.", "style": "hook"}],
                  label=L1))
cut_plan = [
    ("plain", PX, "medium", 0, "look_down"), ("jacket", JX, "close", -18, "point"),
    ("plain", PX, "low", 16, "shrug"), ("jacket", JX, "medium", 24, "think"),
    ("plain", PX, "close", -14, "idle"), ("jacket", JX, "low", -22, "wave"),
    ("plain", PX, "medium", 18, "look_down"), ("jacket", JX, "close", 0, "cheer"),
]
for i, (cid, x, preset, yaw, pose) in enumerate(cut_plan):
    shots.append(shot(f"a_cut{i + 1}", 0.5, cam(preset, [x, 0, 0], yaw),
                      actions=[{"t": 0, "character": cid, "pose": pose}], label=L1))
shots.append(shot("a_product", 3.9, cam("medium", [JX, 0, 0], 0),
                  actions=[{"t": 0, "character": "jacket", "pose": "wave"},
                           {"t": 0, "character": "jacket", "look": "camera"}],
                  overlays=[{"t": 0.1, "duration": 2.1, "text": "THAT WAS A SETUP FOR A JACKET.", "style": "hook", "y": 0.15},
                            {"t": 2.35, "duration": 1.45, "text": "BLUEBOX JACKET. OUT NOW.", "style": "hook", "y": 0.15},
                            {"t": 2.35, "duration": 1.45, "text": "(made-up product)", "style": "note", "y": 0.225}],
                  label=L1))

# ---------------------------------------------------------------- Format 2: reveal skit
L2 = "REVEAL SKIT"
Z = -300.0
door_cols = ["#6b707a", "#8a8f99", "#2f3a52"]
door_x = [-2.2, 0.0, 2.2]
DOOR_Y, DOOR_UP = 2.25, 7.3
props += [
    {"id": "wall", "position": [0, 8, Z - 2.6], "size": [34, 16, 0.5], "color": "#2b2d33", "cast_shadow": False},
    {"id": "wainscot", "position": [0, 1.6, Z - 2.3], "size": [34, 3.2, 0.2], "color": "#1f2127", "cast_shadow": False},
    {"id": "pedestal", "position": [0, 0.55, Z - 1.8], "size": [2.0, 1.0, 1.6], "color": "#fff4e0", "studs": True},
    {"id": "mug_body_b", "type": "cylinder", "position": [0, 1.75, Z - 1.8], "size": [1.2, 1.4, 1.2], "color": "#2f6fe4"},
    {"id": "mug_handle_b", "position": [0.78, 1.75, Z - 1.8], "size": [0.4, 0.8, 0.3], "color": "#2f6fe4"},
    {"id": "banner", "position": [0, 5.6, Z - 0.4], "size": [8, 0.5, 0.2], "color": "#ff5e4d"},
]
for i in range(-8, 9):        # wallpaper stripes
    props.append({"id": f"stripe{i}", "position": [i * 2.0, 9.2, Z - 2.3], "size": [0.9, 11, 0.1],
                  "color": "#34373e", "cast_shadow": False})
for i, (x, c) in enumerate(zip(door_x, door_cols)):
    props.append({"id": f"door{i + 1}", "position": [x, DOOR_Y, Z], "size": [1.9, 4.5, 0.3], "color": c, "bevel": 0.1})
zones.append({"rect": [-17, Z - 2.4, 17, Z + 16], "colors": ["#c9ccd2", "#bfc3ca"], "tile": 1.164, "variation": 0.012,
              "line_strength": 0.0, "studs": 0.3})


def door_open(idx, shot_id, t0, t1):
    """Door idx rises between t0 and t1 of shot_id and stays up for the rest of the film."""
    for p in props:
        if p["id"] == f"door{idx}":
            x = door_x[idx - 1]
            p["track"] = {"shot": shot_id, "keys": [
                {"t": 0, "position": [x, DOOR_Y, Z]}, {"t": t0, "position": [x, DOOR_Y, Z]},
                {"t": t1, "position": [x, DOOR_UP, Z]}, {"t": 99, "position": [x, DOOR_UP, Z]}]}


stage_focus = [0, 0, Z + 2.0]
shots.append(shot("b_setup", 2.8, cam("wide", stage_focus),
                  actions=[{"t": 0.2, "character": "host", "pose": "point", "hand": "left"},
                           {"t": 0, "character": "host", "look": "camera"},
                           {"t": 0, "character": "guest", "pose": "idle"}],
                  dialogue=[{"t": 0.9, "duration": 1.8, "speaker": "host", "text": "Door one, two or three?"}],
                  overlays=[{"t": 0.1, "duration": 1.8, "text": "PICK A DOOR.", "style": "hook", "y": 0.15}],
                  label=L2))
shots.append(shot("b_pick", 3.0, cam("medium", [-2.5, 0, Z + 3.0], 14),
                  actions=[{"t": 0, "character": "guest", "pose": "think"},
                           {"t": 1.4, "character": "guest", "pose": "wave"},
                           {"t": 1.4, "character": "guest", "look": "camera"}],
                  dialogue=[{"t": 1.6, "duration": 1.2, "speaker": "guest", "text": "Two."}],
                  label=L2))
shots.append(shot("b_twist", 2.8, cam("wide", stage_focus),
                  actions=[{"t": 0.8, "character": "guest", "pose": "surprised"},
                           {"t": 0.8, "character": "guest", "expression": "surprised"},
                           {"t": 2.0, "character": "guest", "expression": "neutral"},
                           {"t": 1.0, "character": "host", "pose": "think"},
                           {"t": 2.0, "character": "guest", "pose": "shake_head"}],
                  dialogue=[{"t": 0.9, "duration": 1.0, "speaker": "host", "text": "Want to switch?"},
                            {"t": 2.0, "duration": 0.8, "speaker": "guest", "text": "No."}],
                  label=L2))
door_open(1, "b_twist", 0.3, 0.9)
shots.append(shot("b_turn", 2.0, cam("wide", stage_focus),
                  actions=[{"t": 0, "character": "guest", "pose": "idle"},
                           {"t": 0, "character": "host", "pose": "idle"}],
                  overlays=[{"t": 0.15, "duration": 1.8, "text": "THIS WAS NEVER A GAME SHOW.", "style": "hook", "y": 0.15}],
                  label=L2))
door_open(2, "b_turn", 0.5, 1.2)
shots.append(shot("b_product", 3.2, fixed([0, 2.7, Z + 5.6], [0, 1.9, Z - 1.8], 38),
                  actions=[{"t": 0, "character": "guest", "pose": "cheer"},
                           {"t": 0, "character": "host", "pose": "cheer"}],
                  overlays=[{"t": 0.2, "duration": 3.0, "text": "BLUEBOX MUG. OUT NOW.", "style": "hook", "y": 0.15},
                            {"t": 0.2, "duration": 3.0, "text": "(made-up product)", "style": "note", "y": 0.225}],
                  label=L2))

# ---------------------------------------------------------------- Format 3: interactive challenge
L3 = "CUP CHALLENGE"
CZ = -600.0
TABLE_TOP = 0.1
slots = [-1.9, 0.0, 1.9]
REST = TABLE_TOP + 0.95          # cup centre height when it sits on the table
CUP = [1.5, 1.9, 1.5]
LIFT = 1.8                        # how far a cup rises to show what is under it
cups = {"cupA": 0, "cupB": 1, "cupC": 2}        # cup id -> slot index
cup_keys = {k: [{"t": 0.0, "position": [slots[v], REST, CZ]}] for k, v in cups.items()}


def hold(cid, t):
    cup_keys[cid].append({"t": t, "position": list(cup_keys[cid][-1]["position"])})


def swap(a, b, t0, dur):
    pa, pb = cups[a], cups[b]
    for cid, frm, to, off in ((a, pa, pb, 1.5), (b, pb, pa, -1.5)):
        hold(cid, t0)
        mid = [(slots[frm] + slots[to]) / 2, REST, CZ + off]
        cup_keys[cid].append({"t": t0 + dur / 2, "position": mid})
        cup_keys[cid].append({"t": t0 + dur, "position": [slots[to], REST, CZ]})
    cups[a], cups[b] = pb, pa


def lift(cid, t0, t1, t2, t3):
    hold(cid, t0)
    p = cup_keys[cid][-1]["position"]
    up = [p[0], REST + LIFT, p[2]]
    cup_keys[cid] += [{"t": t1, "position": up}, {"t": t2, "position": up}, {"t": t3, "position": p}]


lift("cupB", 0.3, 0.8, 1.5, 2.0)
for cid in ("cupA", "cupC"):
    hold(cid, 2.0)
t = 2.1
for a, b in (("cupA", "cupB"), ("cupB", "cupC"), ("cupA", "cupC"), ("cupA", "cupB"), ("cupB", "cupC")):
    swap(a, b, t, 0.5)
    t += 0.56
t_end_swaps = t
reveal_t = t_end_swaps + 1.9
# the cup that hides the mug is cupB (it started on the middle slot with the mug)
hold("cupB", reveal_t)
p = cup_keys["cupB"][-1]["position"]
cup_keys["cupB"] += [{"t": reveal_t + 0.6, "position": [p[0], REST + LIFT, p[2]]},
                     {"t": reveal_t + 3.0, "position": [p[0], REST + LIFT, p[2]]}]
c_dur = reveal_t + 2.6

TABLE = "#dba466"
SOFT, DARK = "#c78f55", "#a8733f"     # the table colour, two steps darker, for the contact shadows
CUPCOL = "#ff5e4d"
zones.append({"rect": [-16, CZ - 14, 16, CZ + 14], "colors": ["#d3d5db", "#c9ccd3"], "tile": 1.164, "variation": 0.0,
              "line_strength": 0.0, "studs": 0.3})
# no scenery here: the cup table is shot from above and the label needs a clean background
for cid in ("cupA", "cupB", "cupC"):
    props.append({"id": cid, "type": "cylinder", "position": cup_keys[cid][0]["position"], "size": CUP,
                  "color": CUPCOL, "bevel": 0.12,
                  "track": {"shot": "c_cups", "keys": cup_keys[cid]}})

# contact shadows on the table: two stacked discs that follow each cup and sink out of sight when it lifts
for cid in ("cupA", "cupB", "cupC"):
    for tag, size, col, y in (("s1", 2.5, SOFT, TABLE_TOP + 0.008), ("s2", 1.85, DARK, TABLE_TOP + 0.016)):
        keys = [{"t": k["t"], "position": [k["position"][0], y if k["position"][1] <= REST + 0.01 else 0.0,
                                            k["position"][2]]} for k in cup_keys[cid]]
        props.append({"id": f"{cid}_{tag}", "type": "cylinder", "position": keys[0]["position"],
                      "size": [size, 0.02, size], "color": col, "cast_shadow": False,
                      "track": {"shot": "c_cups", "keys": keys}})

mug_y = TABLE_TOP + 0.55
mug_keys = [{"t": k["t"], "position": [k["position"][0], mug_y, k["position"][2]]} for k in cup_keys["cupB"]]
handle_keys = [{"t": k["t"], "position": [k["position"][0] + 0.7, mug_y, k["position"][2]]} for k in mug_keys]
props.append({"id": "mug_body_c", "type": "cylinder", "position": mug_keys[0]["position"], "size": [0.9, 1.1, 0.9],
              "color": "#2f6fe4", "track": {"shot": "c_cups", "keys": mug_keys}})
props.append({"id": "mug_handle_c", "position": handle_keys[0]["position"], "size": [0.3, 0.6, 0.25], "color": "#2f6fe4",
              "track": {"shot": "c_cups", "keys": handle_keys}})
props.append({"id": "table_c", "position": [0, 0.05, CZ], "size": [7, 0.1, 4], "color": TABLE, "cast_shadow": False})

shots.append(shot("c_cups", c_dur, fixed([0, 15.0, CZ + 10.5], [0, 0.2, CZ + 0.4], 46),
                  overlays=[{"t": 0.1, "duration": 1.8, "text": "FOLLOW THE MUG.", "style": "hook", "y": 0.15},
                            {"t": t_end_swaps + 0.1, "duration": 2.0, "text": "WHERE IS IT? PAUSE AND PICK.", "style": "hook", "y": 0.15},
                            {"t": reveal_t + 0.5, "duration": 2.0, "text": "BLUEBOX MUG. OUT NOW.", "style": "hook", "y": 0.15},
                            {"t": reveal_t + 0.5, "duration": 2.0, "text": "(made-up product)", "style": "note", "y": 0.225}],
                  label=L3, fade_out=0.4))

scene = {
    "meta": {
        "title": "Three formats demo",
        "style": "house",
        "width": 1080, "height": 1920, "fps": 30, "supersample": 2,
        "ground": {"zones": zones},
        "export": {"crf": 18, "preset": "medium"},
    },
    "characters": characters,
    "props": props,
    "shots": shots,
}

out = Path(__file__).with_name("demo_three_formats.json")
out.write_text(json.dumps(scene, indent=1), encoding="utf-8")
print("wrote", out, "shots:", len(shots))
