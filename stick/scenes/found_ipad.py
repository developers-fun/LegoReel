"""Sand Blast! "found iPad" as one continuous 2D take (no cuts): the camera does the work.
Writes scenes/found_ipad.json.  Run: python3 scenes/found_ipad.py
Style contrast with the 3D version: zero cuts, slow camera pushes, night plaza, one stick figure.
The end is a flat-green iPad card (3:4) for the real gameplay recording."""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
G = 866            # ground line
IX = 330           # where the iPad lies


def build():
    objects = {
        "sky": {"kind": "rect", "x": 288, "y": 512, "w": 3000, "h": 3600, "fill": "#1b1f33", "z": -10},
        "moon": {"kind": "circle", "x": 90, "y": 150, "r": 34, "fill": "#f5efd2", "z": -9},
        "moonglow": {"kind": "glow", "x": 90, "y": 150, "r": 120, "color": "#cfd8ff", "strength": 0.25, "z": -9},
        "ground": {"kind": "rect", "x": 288, "y": G + 200, "w": 3000, "h": 400, "fill": "#2a2f48", "z": -5},
        "edge": {"kind": "rect", "x": 288, "y": G + 2, "w": 3000, "h": 4, "fill": "#3b405c", "z": -4},
        "pole": {"kind": "rect", "x": 480, "y": 700, "w": 10, "h": 330, "fill": "#3b405c", "z": -4},
        "lamphead": {"kind": "rect", "x": 480, "y": 538, "w": 54, "h": 14, "fill": "#e8d9a8", "z": -4},
        "lampglow": {"kind": "glow", "x": 480, "y": 560, "r": 190, "color": "#ffd88a", "strength": 0.32, "z": -4},
        "seat": {"kind": "rect", "x": 105, "y": 826, "w": 150, "h": 14, "fill": "#6a4a2b", "z": -3},
        "backrest": {"kind": "rect", "x": 105, "y": 782, "w": 150, "h": 10, "fill": "#6a4a2b", "z": -3},
        "leg1": {"kind": "rect", "x": 50, "y": 846, "w": 8, "h": 40, "fill": "#44454d", "z": -3},
        "leg2": {"kind": "rect", "x": 160, "y": 846, "w": 8, "h": 40, "fill": "#44454d", "z": -3},
        "stripe": {"kind": "rect", "x": 288, "y": 905, "w": 3000, "h": 8, "fill": "#ff5e4d", "z": -4},
        # the iPad on the ground and its glow
        "ipad_flat": {"kind": "rect", "x": IX, "y": G - 5, "w": 92, "h": 8, "fill": "#2a2a30", "outline": "#0d0e14",
                      "z": 1, "show": [0, 3.45]},
        "ipad_glow": {"kind": "glow", "x": IX, "y": G - 5, "r": 80, "color": "#ffe3a0", "strength": 0.7, "z": 0,
                      "show": [0, 3.6],
                      "keys": [{"t": 0, "strength": 0.5}, {"t": 0.8, "strength": 0.85, "ease": "inout"},
                               {"t": 1.6, "strength": 0.5, "ease": "inout"}, {"t": 2.4, "strength": 0.85, "ease": "inout"},
                               {"t": 3.2, "strength": 0.6, "ease": "inout"}]},
        # held iPad (drawn in the hand)
        "ipad": {"kind": "phone", "w": 26, "h": 34, "scale": 1.0, "color": "#2a2a30", "screen_color": "#e6eefc",
                 "grip_at": 0.3},
        # light from the screen on the figure
        "facelight": {"kind": "glow", "follow": "you.head", "offset": [0, 40], "r": 90, "color": "#cfe0ff",
                      "strength": 0.0, "z": 2,
                      "keys": [{"t": 4.5, "strength": 0.0}, {"t": 5.3, "strength": 0.45, "ease": "out"}]},
        # captions (screen space)
        "cap1": {"kind": "text", "text": "POV: you find someone's iPad", "x": 288, "y": 140, "size": 27, "fill": "#ffffff",
                 "outline": "#000000", "ow": 5, "space": "screen", "z": 20, "show": [0, 5.4]},
        "cap2": {"kind": "text", "text": "UHH. ITS STILL ON.", "x": 288, "y": 140, "size": 30, "fill": "#ffffff",
                 "outline": "#000000", "ow": 5, "space": "screen", "z": 20, "show": [5.4, 9.2]},
        # end card: dim, bezel, flat green screen (3:4) for the real recording
        "dim": {"kind": "rect", "x": 288, "y": 512, "w": 700, "h": 1200, "fill": "#0d0e14", "space": "screen", "z": 30,
                "alpha": 0.0, "keys": [{"t": 8.5, "alpha": 0.0}, {"t": 9.1, "alpha": 1.0, "ease": "inout"}]},
        "bezel": {"kind": "rect", "x": 288, "y": 540, "w": 440, "h": 580, "fill": "#2a2a30", "space": "screen", "z": 31,
                  "alpha": 0.0, "keys": [{"t": 8.9, "alpha": 0.0}, {"t": 9.4, "alpha": 1.0, "ease": "out"}]},
        "screen": {"kind": "rect", "x": 288, "y": 540, "w": 396, "h": 528, "fill": "#00ff00", "space": "screen", "z": 32,
                   "alpha": 0.0, "keys": [{"t": 8.9, "alpha": 0.0}, {"t": 9.4, "alpha": 1.0, "ease": "out"}]},
    }
    you = {
        "ground": G, "shadow": True, "x": -40, "yaw": 45,
        "keys": [
            {"t": 0, "x": -40, "yaw": 45, "pose": "stand", "expr": "calm", "anim": "walk"},
            {"t": 2.4, "x": 292, "ease": "linear"},
            {"t": 2.45, "anim": None, "pose": "stand", "expr": "surprised", "ease": "step"},
            {"t": 2.9, "pose": "crouch", "yaw": 60, "ease": "inout", "hand_r_at": [IX - 12, G - 12]},
            {"t": 3.45, "prop": "ipad", "prop_hand": "r", "prop_angle": -70, "ease": "step"},
            {"t": 4.1, "pose": "stand", "hand_r_at": None, "hand_r_rel": [24, -45], "expr": "calm", "ease": "inout"},
            {"t": 4.7, "yaw": 90, "ease": "inout", "hand_r_rel": [26, -40], "hand_l_rel": [22, -38], "lean": 6},
            {"t": 5.4, "expr": "surprised", "ease": "step"},
            {"t": 6.2, "head": 10, "ease": "inout"},
            {"t": 7.4, "head": -4, "ease": "inout"},
        ],
    }
    camera = {"zoom": 1.0, "cx": 288, "cy": 640, "keys": [
        {"t": 0, "zoom": 1.0, "cx": 288, "cy": 640},
        {"t": 1.8, "zoom": 1.0, "cx": 288, "cy": 640},
        {"t": 2.8, "zoom": 1.8, "cx": 318, "cy": 790, "ease": "inout"},
        {"t": 3.9, "zoom": 1.9, "cx": 305, "cy": 780, "ease": "inout"},
        {"t": 4.9, "zoom": 1.6, "cx": 296, "cy": 730, "ease": "inout"},
        {"t": 5.6, "zoom": 2.1, "cx": 294, "cy": 740, "ease": "inout"},
        {"t": 8.8, "zoom": 3.4, "cx": 300, "cy": 770, "ease": "in2"},
    ]}
    audio = {"master": 0.85, "cues": [
        {"sfx": "step", "times": "you.step", "gain": 0.22, "pitch_jitter": 0.08},
        {"sfx": "sparkle", "t": 4.6, "gain": 0.18},
        {"sfx": "whoosh", "t": 8.2, "gain": 0.3},
    ]}
    return {"canvas": {"w": 576, "h": 1024, "fps": 30, "duration": 13.0, "scale": 2.0, "bg": "#1b1f33", "blur": 2,
                       "out": [1080, 1920], "post": {"vignette": 0.12, "grain": 0.015}},
            "camera": camera, "audio": audio, "objects": objects, "actors": {"you": you}}


if __name__ == "__main__":
    p = OUT / "found_ipad.json"
    p.write_text(json.dumps(build(), indent=1), encoding="utf-8")
    print("wrote", p)
