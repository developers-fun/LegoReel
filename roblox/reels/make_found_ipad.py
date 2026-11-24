"""Sand Blast! found-iPad POV, Roblox style: fast cuts (~1.2 s), whip transitions, dutch, word-by-word captions.
Writes reels/found_ipad.json. Ends on a flat-green iPad card for the real gameplay recording."""
import json, os
D = os.path.dirname(os.path.abspath(__file__))
X0 = 14.0
IP = (X0, 0.2, -12.5)   # iPad on the ground
HELD = (X0 - 3.0, 3.4, -10.4)


def ipad_props():
    keys = lambda extra: [
        {"t": 4.1, "position": list(IP), "rotation": [0, 0, 0]},
        {"t": 4.9, "position": list(HELD), "rotation": extra, "ease": "cubic_out"},
    ]
    return [
        {"name": "ipad_body", "builder": "plate", "args": {"size": [1.9, 0.12, 2.5], "color": "#2a2a30"},
         "position": list(IP), "rotation": [0, 0, 0], "scale": 1.0, "keys": keys([90, 0, 0])},
        {"name": "ipad_screen", "builder": "plate", "args": {"size": [1.65, 0.05, 2.2], "color": "#2a3a6e", "material": "neon"},
         "position": [IP[0], IP[1] + 0.07, IP[2]], "rotation": [0, 0, 0], "scale": 1.0,
         "keys": [{"t": 4.1, "position": [IP[0], IP[1] + 0.07, IP[2]], "rotation": [0, 0, 0]},
                  {"t": 4.9, "position": [HELD[0], HELD[1], HELD[2] + 0.06], "rotation": [90, 0, 0], "ease": "cubic_out"}]},
    ]


def stage_builders():
    return [
        {"builder": "plate", "args": {"size": [30, 20, 0.5], "color": "#0d0e14"}, "position": [0, 6, -60.5]},
        {"builder": "plate", "args": {"size": [3.5, 4.6, 0.2], "color": "#2a2a30"}, "position": [0, 3.2, -58.4]},
        {"builder": "plate", "args": {"size": [3.0, 4.0, 0.1], "color": "#00ff00", "material": "neon"}, "position": [0, 3.2, -58.2]},
    ]


def build():
    words = [["POV:", 0.1, 0.55], ["you", 0.55, 0.8], ["find", 0.8, 1.1], ["someone's", 1.1, 1.7], ["iPad", 1.7, 2.3],
             ["UHH.", 4.9, 5.4], ["ITS", 5.4, 5.7], ["STILL", 5.7, 6.1], ["ON.", 6.1, 6.9]]
    caps = [{"style": "storytime", "y": 0.2, "font_scale": 1.0, "words": words[:5]},
            {"style": "storytime", "y": 0.2, "font_scale": 1.1, "words": words[5:]}]
    sc = {
        "version": 1, "name": "found_ipad_roblox", "width": 1080, "height": 1920, "fps": 30, "seed": 3, "duration": 11.0,
        "sets": {
            "plaza": {"name": "plaza", "location": "town_square", "lighting": "night"},
            "stage": {"name": "stage", "location": None, "lighting": "day", "builders": stage_builders(),
                      "ground_y": -50},
        },
        "characters": [{"name": "Jay", "avatar": {"hair": "spiky:#2b1d14", "shirt_color": "#ff5e4d", "pants_color": "#31456a",
                                                  "accessories": [], "skin": "#f2c9a0"},
                        "position": [X0, 0, 0], "facing": 0.0, "sets": ["plaza"]}],
        "actions": [
            {"character": "Jay", "type": "place", "t": 0.0, "pos": [X0, 0, 0.0], "facing": 0.0},
            {"character": "Jay", "type": "face", "t": 0.0, "name": "Smile"},
            {"character": "Jay", "type": "move_to", "t0": 0.0, "t1": 2.2, "pos": [X0, 0, -8.6], "ease": "linear", "gait": "walk"},
            {"character": "Jay", "type": "play", "clip": "walk", "t": 0.0, "until": 2.2},
            {"character": "Jay", "type": "face", "t": 2.4, "name": "Shocked"},
            {"character": "Jay", "type": "play", "clip": "shock", "t": 2.4, "until": 3.5},
            {"character": "Jay", "type": "play", "clip": "tie_shoes", "t": 3.6, "until": 5.0},
            {"character": "Jay", "type": "face", "t": 4.9, "name": "Shocked Surprised"},
            {"character": "Jay", "type": "play", "clip": "idle", "t": 5.0, "until": 11.0},
            {"character": "Jay", "type": "look_at", "t0": 5.0, "t1": 5.4, "target": list(HELD)},
        ],
        "props": ipad_props(),
        "shots": [
            {"t0": 0.0, "t1": 1.3, "kind": "wide", "set": "plaza", "subject": "Jay", "azimuth": 20, "elevation": 5, "fill": 0.5,
             "label": "s1"},
            {"t0": 1.3, "t1": 2.4, "set": "plaza", "kind": "insert", "camera": {"position": [X0 + 1.3, 0.6, -9.4], "target": [X0, 0.1, -12.5], "fov": 45},
             "transition": {"type": "whip"}, "label": "s2 iPad insert"},
            {"t0": 2.4, "t1": 3.5, "kind": "closeup", "set": "plaza", "subject": "Jay", "azimuth": 15, "elevation": -8,
             "moves": [{"type": "dutch", "amount": 8}], "label": "s3 shock"},
            {"t0": 3.5, "t1": 4.7, "kind": "high_angle", "set": "plaza",
             "camera": {"position": [X0 + 1.5, 4.8, -15.8], "target": [X0, 1.5, -10.5], "fov": 45},
             "transition": {"type": "whip"}, "label": "s4 pickup"},
            {"t0": 4.7, "t1": 6.4, "set": "plaza", "kind": "over_shoulder",
             "camera": {"position": [HELD[0] - 0.6, 4.6, -5.0], "target": [HELD[0], 3.3, -10.4], "fov": 40}, "label": "s5 screen"},
            {"t0": 6.4, "t1": 7.4, "set": "plaza", "kind": "insert",
             "camera": {"position": [HELD[0] - 0.3, 3.7, -6.8], "target": [HELD[0], 3.4, -10.4], "fov": 26},
             "transition": {"type": "zoom_punch"}, "label": "s6 push"},
            {"t0": 7.4, "t1": 11.0, "set": "stage", "kind": "insert",
             "camera": {"position": [0, 3.2, -46.0], "target": [0, 3.2, -58.2], "fov": 34},
             "transition": {"type": "whip"}, "label": "s7 gameplay placeholder"},
        ],
        "captions": caps, "fx": [], "post": {},
        "audio": {"master": 0.85, "cues": [
            {"sfx": "step", "times": "steps:Jay", "gain": 0.5, "pitch_jitter": 0.08},
            {"sfx": "whoosh", "times": "transition:whip", "delay": -0.15, "gain": 0.7},
            {"sfx": "shimmer", "t": 6.2, "gain": 0.5},
            {"sfx": "sparkle", "t": 4.3, "gain": 0.4},
            {"sfx": "thump", "t": 3.9, "gain": 0.6},
            {"sfx": "tick", "times": "words", "gain": 0.25},
        ]},
    }
    return sc


if __name__ == "__main__":
    p = os.path.join(D, "found_ipad.json")
    json.dump(build(), open(p, "w"), indent=1)
    print("wrote", p)
