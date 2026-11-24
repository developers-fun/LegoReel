"""Sand Blast! "found iPad": a minifigure finds a glowing iPad on the ground, sits down with it, then a held
flat-green iPad shot for the real gameplay recording.

Structure follows the owner's POV-premise reference (premise, discovery, bridge, then the app as the answer).
Five hard cuts (a from-behind shot was tried and dropped: the hero's body hid the screen), one fixed camera per shot, size changes at every cut. No app name on screen.

  s1 plaza wide      0.0 - 1.6   hero walks in from the back, iPad glows on the ground
  s2 low insert      1.6 - 2.5   iPad on the ground, glow at its edges
  s3 medium          2.5 - 3.6   hero stands over it, looks down
  s4 low insert      3.6 - 4.5   iPad is lifted out of frame
  s5 front, seated   4.5 - 7.1   hero on a bench holding the iPad, caption swaps
  s7 hold            7.1 - 11.4  straight-on flat-green iPad for the real recording

Run:  python3 reels/make_found_ipad.py
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
GREEN = "#00ff00"
WARM = "#ffe3a0"
Z2, Z3 = -300.0, -600.0
IPAD, SCREEN = [3.4, 4.5, 0.4], [3.0, 4.0, 0.05]
FINAL_Y = 3.25


def box(pid, pos, size, color, **kw):
    d = {"id": pid, "position": pos, "size": size, "color": color, "cast_shadow": False}
    d.update(kw)
    return d


def zone(cx, cz, colors=("#d3d5db", "#c9ccd3")):
    return {"rect": [cx - 20, cz - 14, cx + 20, cz + 18], "colors": list(colors), "tile": 1.164,
            "variation": 0.01, "line_strength": 0.0, "studs": 0.3}


def hook(t, dur, text, **kw):
    return {"t": t, "duration": dur, "text": text, "style": "hook", **kw}


def build():
    props = []
    # plaza (stage 1): back wall, accent stripe, bench, lamp post, bin
    props += [
        box("wall", [0, 8, -14], [44, 16, 0.5], "#2b2d33"),
        box("stripe", [0, 1.7, -13.7], [44, 0.5, 0.1], "#ff5e4d"),
        box("bench_seat", [-6.5, 1.1, -9], [4.6, 0.4, 1.4], "#8a5a2b", cast_shadow=True),
        box("bench_back", [-6.5, 2.3, -9.6], [4.6, 1.6, 0.3], "#8a5a2b"),
        box("bench_l", [-8.4, 0.5, -9], [0.4, 1.0, 1.2], "#44454d"),
        box("bench_r", [-4.6, 0.5, -9], [0.4, 1.0, 1.2], "#44454d"),
        {"id": "lamp", "type": "cylinder", "position": [7.0, 4.0, -9], "size": [0.5, 8.0, 0.5], "color": "#44454d",
         "cast_shadow": False},
        box("lamp_head", [7.0, 8.2, -9], [1.6, 0.6, 1.6], "#ffe9b0"),
    ]
    # the iPad on the ground (face down) and the glow under its edges
    ipad_rest = [1.4, 0.2, 0.8]
    props.append(box("glow_plate", [1.4, 0.05, 0.8], [2.4, 0.06, 3.1], WARM, rotation_y=20))
    props.append(box("ground_ipad", ipad_rest, [1.9, 0.25, 2.5], "#2a2a30", bevel=0.05, cast_shadow=True,
                     rotation_y=20, track={"shot": "s4", "keys": [
                         {"t": 0, "position": ipad_rest}, {"t": 0.3, "position": ipad_rest},
                         {"t": 0.85, "position": [1.4, 9.0, 1.6], "ease": "ease_in"}]}))
    props[-2]["track"] = {"shot": "s4", "keys": [{"t": 0, "position": [1.4, 0.05, 0.8]},
                                                 {"t": 0.3, "position": [1.4, -60, 0.8]}]}
    # stage 2: bench scene (front camera and from-behind camera)
    props += [
        box("b_wall_back", [0, 8, Z2 - 12], [44, 16, 0.5], "#2b2d33"),
        box("b_stripe", [0, 1.7, Z2 - 11.7], [44, 0.5, 0.1], "#ff5e4d"),
        box("b_wall_front", [0, 8, Z2 + 12], [44, 16, 0.5], "#33363d"),
        box("b_bench_seat", [0, 0.9, Z2], [5.0, 0.4, 1.8], "#8a5a2b", cast_shadow=True),
        box("b_bench_l", [-2.3, 0.4, Z2], [0.4, 0.8, 1.5], "#44454d"),
        box("b_bench_r", [2.3, 0.4, Z2], [0.4, 0.8, 1.5], "#44454d"),
        # held iPad: dark back faces the front camera, glowing screen faces the hero (and the behind camera).
        # The glow is four warm bars that widen the bezel, so it reads as a lit rim from both sides.
        box("h_ipad", [0, 1.75, Z2 + 1.45], [1.9, 2.5, 0.16], "#2a2a30", bevel=0.05),
        box("h_screen", [0, 1.75, Z2 + 1.35], [1.65, 2.2, 0.05], "#e6eefc", bevel=0.0),
        box("h_rim_l", [-1.12, 1.75, Z2 + 1.45], [0.3, 2.9, 0.12], WARM),
        box("h_rim_r", [1.12, 1.75, Z2 + 1.45], [0.3, 2.9, 0.12], WARM),
        box("h_rim_t", [0, 3.17, Z2 + 1.45], [2.54, 0.3, 0.12], WARM),
        box("h_rim_b", [0, 0.33, Z2 + 1.45], [2.54, 0.3, 0.12], WARM),
    ]
    # stage 3: flat-green held iPad
    props += [
        box("f_wall", [0, 8, Z3 - 3.2], [40, 16, 0.5], "#2b2d33"),
        box("f_stripe", [0, 1.7, Z3 - 2.9], [40, 0.5, 0.1], "#ff5e4d"),
        box("f_pedestal", [0, 0.5, Z3], [2.8, 1.0, 2.0], "#fff4e0", studs=True),
        box("f_ipad", [0, FINAL_Y, Z3], IPAD, "#2a2a30", bevel=0.1),
        box("f_screen", [0, FINAL_Y, Z3 + 0.22], SCREEN, GREEN, bevel=0.0),
    ]

    chars = {"hero": {"avatar": "main", "position": [-4.5, 0, -6.0], "yaw": 25}}

    def seat(x, z):
        return [{"t": 0, "character": "hero", "teleport": [x, -0.5, z]},
                {"t": 0, "character": "hero", "face": 0, "turn": 0.0},
                {"t": 0, "character": "hero", "pose": "phone", "snap": True}]

    s1 = {"id": "s1", "duration": 1.6, "camera": {"preset": "wide", "focus": [-0.5, 0, -1.5], "yaw": 14},
          "actions": [{"t": 0, "character": "hero", "pose": "idle"},
                      {"t": 0.1, "character": "hero", "move_to": [-1.2, 0, -1.8], "duration": 1.5, "then_pose": "idle"}],
          "overlays": [hook(0.05, 1.5, "LEFT THEIR IPAD.")]}
    s2 = {"id": "s2", "duration": 0.9,
          "camera": {"position": [3.6, 1.7, 7.5], "look_at": [1.4, 0.2, 0.8], "fov": 40},
          "actions": [{"t": 0, "character": "hero", "teleport": [-14, 0, -1.0]}],
          "overlays": [hook(0.0, 0.9, "LEFT THEIR IPAD.")]}
    s3 = {"id": "s3", "duration": 1.1, "camera": {"position": [3.5, 3.4, 11.0], "look_at": [0.5, 2.3, 0.0], "fov": 40},
          "actions": [{"t": 0, "character": "hero", "teleport": [0.4, 0, -0.6]},
                      {"t": 0, "character": "hero", "face": 30, "turn": 0.0},
                      {"t": 0.1, "character": "hero", "pose": "look_down"}],
          "overlays": [hook(0.0, 1.1, "LEFT THEIR IPAD.")]}
    s4 = {"id": "s4", "duration": 0.9,
          "camera": {"position": [1.0, 1.0, 6.0], "look_at": [1.4, 2.2, 0.8], "fov": 50},
          "actions": [{"t": 0, "character": "hero", "teleport": [40, 0, 0]}],
          "overlays": [hook(0.0, 0.9, "LEFT THEIR IPAD.")]}
    s5 = {"id": "s5", "duration": 2.6,
          "camera": {"position": [0.0, 3.6, Z2 + 8.5], "look_at": [0, 2.9, Z2], "fov": 42},
          "actions": seat(0.0, Z2 + 0.2) + [{"t": 0.1, "character": "hero", "expression": "surprised"}],
          "overlays": [hook(0.05, 2.5, "UHH. ITS STILL ON.")]}
    s6 = {"id": "s6", "duration": 1.1,
          "camera": {"position": [8.0, 4.5, Z2 - 6.0], "look_at": [0.0, 2.0, Z2 + 1.0], "fov": 40},
          "actions": seat(0.0, Z2 + 0.2),
          "overlays": [hook(0.0, 1.1, "STILL ON.")]}
    s7 = {"id": "s7", "duration": 4.3,
          "camera": {"position": [0, 3.45, Z3 + 11.5], "look_at": [0, 3.4, Z3], "fov": 38},
          "actions": [{"t": 0, "character": "hero", "teleport": [60, 0, Z3]}]}

    return {
        "meta": {"title": "Sand Blast! found iPad", "style": "house", "width": 1080, "height": 1920, "fps": 30,
                 "supersample": 2,
                 "ground": {"zones": [zone(0, -2), zone(0, Z2), zone(0, Z3)]},
                 "look": {"vignette": 0.0, "bloom": 0.0, "dof": None, "saturation": 1.0, "contrast": 1.0,
                          "tint": [1.0, 1.0, 1.0], "gloss": 0.0},
                 "light": {"spec_strength": 0.0},
                 "export": {"crf": 18, "preset": "medium"}},
        "characters": chars, "props": props, "shots": [s1, s2, s3, s4, s5, s7]}


if __name__ == "__main__":
    path = OUT / "sand_blast_found_ipad.json"
    scene = build()
    path.write_text(json.dumps(scene, indent=1), encoding="utf-8")
    print("wrote", path, "shots:", len(scene["shots"]), "props:", len(scene["props"]))
