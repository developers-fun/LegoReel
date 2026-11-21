"""Writes two promo reels that end on a flat-green iPad screen, for the owner to lay gameplay over.

  reels/sand_blast_cover_reveal.json   Sand Blast!  cover-and-countdown reveal
  reels/lazy_blocks_row_clear.json     Lazy Blocks  one slow block completes a row, then the reveal

Structure (principles from the Wants and Needs study, nothing copied): a bit people would watch anyway, the app
appears last as the answer to the bit, one escalation, one payoff. Fixed camera per shot, hard cuts, no shake.
The final shot of both reels is the same straight-on iPad framing, held, so one screen rectangle fits both.

Run:  python3 reels/make_promo_reels.py
"""
import json
from pathlib import Path

GREEN = "#00ff00"
OUT = Path(__file__).resolve().parent

IPAD = [3.4, 4.5, 0.4]            # bezel (w, h, d)
SCREEN = [3.0, 4.0, 0.05]
IPAD_Y = 3.25                      # centre height: 1.0 pedestal + 2.25
FINAL_CAM = lambda z: {"position": [0, 3.45, z + 11.5], "look_at": [0, 3.4, z], "fov": 38}


def meta(title, zones):
    # Flat, even look so the screen stays one uniform green (no vignette, bloom, blur, gloss or tint).
    return {
        "title": title, "style": "house", "width": 1080, "height": 1920, "fps": 30, "supersample": 2,
        "ground": {"zones": zones},
        "look": {"vignette": 0.0, "bloom": 0.0, "dof": None, "saturation": 1.0, "contrast": 1.0,
                 "tint": [1.0, 1.0, 1.0], "gloss": 0.0},
        "light": {"spec_strength": 0.0},
        "export": {"crf": 18, "preset": "medium"},
    }


def zone(cx, cz):
    return {"rect": [cx - 17, cz - 3.0, cx + 17, cz + 16], "colors": ["#d3d5db", "#c9ccd3"], "tile": 1.164,
            "variation": 0.01, "line_strength": 0.0, "studs": 0.3}


def studio(z, prefix=""):
    """Back wall, accent stripe, pedestal and the green-screen iPad, centred on (0, z)."""
    p = prefix
    return [
        {"id": f"{p}wall", "position": [0, 8, z - 3.2], "size": [40, 16, 0.5], "color": "#2b2d33", "cast_shadow": False},
        {"id": f"{p}stripe", "position": [0, 1.7, z - 2.9], "size": [40, 0.5, 0.1], "color": "#ff5e4d", "cast_shadow": False},
        {"id": f"{p}pedestal", "position": [0, 0.5, z], "size": [2.8, 1.0, 2.0], "color": "#fff4e0", "studs": True},
        {"id": f"{p}ipad", "position": [0, IPAD_Y, z], "size": IPAD, "color": "#2a2a30", "bevel": 0.1},
        {"id": f"{p}screen", "position": [0, IPAD_Y, z + 0.22], "size": SCREEN, "color": GREEN, "bevel": 0.0,
         "cast_shadow": False},
    ]


def cam(preset, focus, yaw=0.0):
    return {"preset": preset, "focus": focus, "yaw": yaw}


def shot(sid, dur, camera, actions=(), overlays=()):
    s = {"id": sid, "duration": round(dur, 3), "camera": camera, "actions": list(actions)}
    if overlays:
        s["overlays"] = list(overlays)
    return s


def hook(t, dur, text, **kw):
    return {"t": t, "duration": dur, "text": text, "style": "hook", **kw}


# ------------------------------------------------------------------ Sand Blast!
def sand_blast():
    chars = {"hero": {"avatar": "main", "position": [3.3, 0, 1.4], "yaw": -35}}
    props = studio(0.0)
    sheet_rest = [0, 3.3, 0.12]
    props.append({"id": "sheet", "position": sheet_rest, "size": [3.9, 5.0, 0.9], "color": "#aeb3bd", "bevel": 0.12,
                  "track": {"shot": "a_final", "keys": [
                      {"t": 0, "position": sheet_rest}, {"t": 1.0, "position": sheet_rest},
                      {"t": 1.9, "position": [-7.5, 6.2, 1.2], "ease": "ease_in"}]}})
    shots = [
        shot("a_hook", 2.4, cam("wide", [1.4, 0, 0]),
             [{"t": 0, "character": "hero", "look": "camera"}, {"t": 0.4, "character": "hero", "pose": "point"}],
             [hook(0.1, 2.2, "WATCH WHAT'S UNDER THE SHEET.")]),
        shot("a_three", 1.0, cam("low", [1.0, 0, 0], 18), [], [hook(0.0, 1.0, "3")]),
        shot("a_two", 1.0, cam("medium", [0.9, 0, 0], -16), [], [hook(0.0, 1.0, "2")]),
        # the hero steps out of the held shot so nothing sits beside the screen the gameplay goes on
        shot("a_final", 13.9, FINAL_CAM(0.0), [{"t": 0, "character": "hero", "teleport": [9.0, 0, 1.4]}],
             [hook(0.0, 1.0, "1"), hook(1.9, 12.0, "HOW MANY LINES?"),
              {"t": 1.9, "duration": 12.0, "text": "SAND BLAST!", "style": "label", "y": 0.075}]),
    ]
    return {"meta": meta("Sand Blast! cover reveal", [zone(0, 0)]), "characters": chars, "props": props, "shots": shots}


# ------------------------------------------------------------------ Lazy Blocks
def lazy_blocks():
    Z2 = -300.0
    chars = {"hero": {"avatar": "main", "position": [0, -0.8, -3.0], "yaw": 0}}
    props = [
        {"id": "wall", "position": [0, 8, -6.4], "size": [40, 16, 0.5], "color": "#2b2d33", "cast_shadow": False},
        {"id": "stripe", "position": [0, 1.7, -6.1], "size": [40, 0.5, 0.1], "color": "#ff5e4d", "cast_shadow": False},
        {"id": "beanbag", "position": [0, 0.6, -3.2], "size": [3.4, 1.2, 3.0], "color": "#8a8f99", "bevel": 0.35,
         "studs": True},
    ]
    xs = [-2.25, -0.75, 0.75, 2.25]
    rest_y, z = 0.7, 1.5
    blue = ["#2f6fe4", "#4f86ee", "#2f6fe4"]
    row = [(f"rb{i}", xs[i], blue[k]) for k, i in enumerate((0, 1, 3))]
    pop_keys = lambda x: [{"t": 0, "position": [x, rest_y, z]}, {"t": 0.4, "position": [x, rest_y, z]},
                          {"t": 1.0, "position": [x, 18.0, z], "ease": "ease_in"}]
    for bid, x, col in row:
        props.append({"id": bid, "position": [x, rest_y, z], "size": [1.4, 1.4, 1.4], "color": col, "bevel": 0.1,
                      "studs": True, "track": {"shot": "b_pop", "keys": pop_keys(x)}})
    props.append({"id": "falling", "position": [0.75, 11.0, z], "size": [1.4, 1.4, 1.4], "color": "#ff5e4d",
                  "bevel": 0.1, "studs": True,
                  "track": {"shot": "b_drop", "keys": [
                      {"t": 0, "position": [0.75, 11.0, z]}, {"t": 0.2, "position": [0.75, 11.0, z]},
                      {"t": 2.3, "position": [0.75, rest_y, z]},
                      # b_drop is 2.6 s long, so these two keys are the same pop the row blocks do in b_pop
                      {"t": 3.0, "position": [0.75, rest_y, z]},
                      {"t": 3.6, "position": [0.75, 18.0, z], "ease": "ease_in"}]}})
    props += studio(Z2, "g_")
    shots = [
        shot("b_hook", 2.4, cam("wide", [0, 0, 0]),
             [{"t": 0, "character": "hero", "pose": "sit"}, {"t": 0, "character": "hero", "expression": "sleepy"}],
             [hook(0.1, 2.2, "TOO TIRED FOR A HARD GAME?")]),
        shot("b_drop", 2.6, cam("wide", [0, 0, 1.0], 24), [], [hook(0.1, 2.4, "ONE BLOCK AT A TIME.")]),
        shot("b_pop", 1.6, cam("wide", [0, 0, 1.5], -12),
             [{"t": 0.3, "character": "hero", "expression": "happy"}], [hook(0.5, 1.0, "SATISFYING, RIGHT?")]),
        shot("b_final", 11.5, FINAL_CAM(Z2), [], [hook(0.1, 11.0, "THIS IS LAZY BLOCKS.")]),
    ]
    return {"meta": meta("Lazy Blocks row clear", [zone(0, 0), zone(0, Z2)]), "characters": chars, "props": props,
            "shots": shots}


if __name__ == "__main__":
    for name, scene in (("sand_blast_cover_reveal", sand_blast()), ("lazy_blocks_row_clear", lazy_blocks())):
        path = OUT / f"{name}.json"
        path.write_text(json.dumps(scene, indent=1), encoding="utf-8")
        print("wrote", path, "shots:", len(scene["shots"]))
