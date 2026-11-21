"""Builds scenes/dig_skit.json: a recreation study of a stick-figure dig skit, made only from engine features.
Frame numbers are the reference's 1-based frames; T(n) turns them into seconds. Run: python3 scenes/dig_skit.py"""
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FIT = json.load(open(os.path.join(HERE, "..", "data", "fit_all11.json")))


def T(n):
    return round((n - 1) / 30.0, 4)


def smooth(vals, k=9):
    v = np.array(vals, float)
    pad = np.pad(v, (k // 2, k // 2), mode="edge")
    return np.convolve(pad, np.ones(k) / k, mode="valid")


def hip_keys(key, step=6, last=152):
    xs = smooth([FIT[str(n)][key][0] for n in range(1, last + 1)], 9)
    return [{"t": T(n), "x": round(float(xs[n - 1]), 1), "ease": "linear"} for n in range(1, last + 1, step)]


YOU_HITS = [9, 30, 54, 84, 106, 127, 148]
FRIEND_HITS = [13 + 18 * k for k in range(8)]
DIG_HITS = [154, 166, 178, 189]
TOGETHER = [207, 222, 237]
GOLD = [0.95, 0.83, 0.62]
COIN = (297, 618)

loops = {
    # digging DOWN: pick goes overhead, then drives straight down in front of the feet
    "dig_down": dict(mode="replace", source="hits", period=0.4, hit_phase=0.7, keys=[
        dict(t=0.0, grip_rel=[-6, -104], prop_angle=-128, lean=3, head=-2, foot_r_rel=[10, 84], foot_l_rel=[-12, 84], grip_w=1, foot_r_w=1, foot_l_w=1),
        dict(t=0.3, grip_rel=[2, -112], prop_angle=-100, lean=2, head=0, foot_r_rel=[10, 84], foot_l_rel=[-12, 84], grip_w=1, foot_r_w=1, foot_l_w=1),
        dict(t=0.55, grip_rel=[28, -66], prop_angle=-10, lean=22, head=-8, foot_r_rel=[14, 83], foot_l_rel=[-14, 83], grip_w=1, foot_r_w=1, foot_l_w=1),
        dict(t=0.7, grip_rel=[40, -24], prop_angle=104, lean=40, head=-12, foot_r_rel=[16, 80], foot_l_rel=[-16, 80], grip_w=1, foot_r_w=1, foot_l_w=1),
        dict(t=0.82, grip_rel=[38, -28], prop_angle=100, lean=38, head=-12, foot_r_rel=[16, 80], foot_l_rel=[-16, 80], grip_w=1, foot_r_w=1, foot_l_w=1),
        dict(t=0.93, grip_rel=[20, -80], prop_angle=-70, lean=14, head=-4, foot_r_rel=[12, 83], foot_l_rel=[-12, 83], grip_w=1, foot_r_w=1, foot_l_w=1),
    ]),
}


def label(text, follow, off, keys=None, show=None, **kw):
    d = dict(kind="text", text=text, follow=follow, offset=off, size=14, fill="#fff6e2", outline="#462c18", ow=1.6, weight=800, z=30)
    d.update(kw)
    if keys:
        d["keys"] = keys
    if show:
        d["show"] = show
    return d


def ring(t0, dur=0.55, r0=20, r1=240, x=COIN[0], y=COIN[1], w=3):
    return dict(kind="ring", x=x, y=y, r=r0, w=w, color="#fff0b8", alpha=0, z=40, show=[t0, t0 + dur + 0.05],
                keys=[{"t": t0, "r": r0, "alpha": 0.95, "ease": "out"}, {"t": t0 + dur, "r": r1, "alpha": 0.0, "ease": "out"}])


objects = {
    "sky": dict(kind="art", name="dig_sky", z=-100),
    "dirt": dict(kind="art", name="dig_dirt", z=-99),
    "tunnel_up": dict(kind="art", name="dig_tunnel", top=390, bot=572, right=255, orb_y=428, z=-90,
                      grow={"prop": "right", "times": [T(n) for n in FRIEND_HITS], "by": 3.75, "dur": 0.12}),
    "tunnel_lo": dict(kind="art", name="dig_tunnel", top=678, bot=862, right=346, orb_y=715, z=-89,
                      grow={"prop": "right", "times": [T(n) for n in YOU_HITS], "by": 12.5, "dur": 0.12}),
    "shaft": dict(kind="art", name="dig_shaft", x0=190, x1=262, top=572, depth=0, z=-88,
                  grow={"prop": "depth", "times": [T(n) for n in DIG_HITS], "by": 26.5, "dur": 0.15}),
    "wall": dict(kind="art", name="dig_wall", z=-80),
    "sign": dict(kind="art", name="dig_sign", z=-79),
    "token_wall": dict(kind="art", name="dig_token", x=510, y=757, r=33, z=-78, show=[0, T(150)]),
    "strike_glow": dict(kind="glow", x=441, y=757, r=70, color="#ffd278", strength=0.9, z=-70, show=[T(150), T(241)],
                        keys=[{"t": T(150), "strength": 0.0}, {"t": T(154), "strength": 0.95}]),
    "flash_you": dict(kind="pulse", times=[T(n) for n in YOU_HITS + TOGETHER], at="you.tip", r=[58, 20], strength=[0.85, 0.95], dur=0.2, z=35),
    "flash_friend": dict(kind="pulse", times=[T(n) for n in FRIEND_HITS], at="friend.tip", r=[34, 12], strength=[0.6, 0.8], dur=0.15, z=35),
    "dust_you": dict(kind="burst", times=[T(n) for n in YOU_HITS], at="you.tip", n=6, speed=[20, 90], angle=[-200, 20], gravity=380, life=0.45,
                     size=[1.2, 2.6], color="#6a4220", seed=2, z=34),
    "dust_dig": dict(kind="burst", times=[T(n) for n in DIG_HITS], at="friend.tip", n=8, speed=[30, 110], angle=[-160, -20], gravity=420, life=0.5,
                     size=[1.5, 3], color="#6a4220", seed=5, z=34),
    "pick_you": dict(kind="pick", len=64),
    "pick_friend": dict(kind="pick", len=64),
    "hook1": dict(kind="text", text="THIS TIME IT ENDS", x=288, y=101, size=24, fill="#fffaee", outline="#4c3228", ow=2.2, width=300, z=-60),
    "hook2": dict(kind="text", text="DIFFERENTLY.", x=289, y=151, size=40, fill="#ffffff", outline="#4e3426", ow=3.0, width=352,
                  grad=["#fff6d8", "#e8c98a"], weight=900, z=-60),
    "lbl_friend": label("FRIEND", "friend.head", [1, -34], width=84, show=[0, T(197)]),
    "lbl_you": label("YOU", "you.head", [1, -34], width=44, show=[0, T(242)]),
    "one_more": dict(kind="text", text="ONE MORE GAME.", x=270, y=639, size=22, fill="#fff6e2", outline="#3c2614", ow=1.8, width=246,
                     show=[T(207), T(242)], z=30),
    "lbl_friend2": label("FRIEND", "friend.head", [2, -36], width=84, show=[T(197), T(240)], z=30),
    "lbl_friend3": label("FRIEND", "friend.head", [0, -32], width=84, show=[T(242), T(270)], z=30),
    "lbl_you2": label("YOU", "you.head", [0, -32], width=44, show=[T(242), T(270)], z=30),
    "lbl_you3": label("YOU", "you.head", [0, -32], width=44, show=[T(270), 99], z=30),
    "lbl_bro": label("BROTHER", "friend.head", [0, -32], width=70, show=[T(270), 99], z=30),
    # ---- finale
    "beams": dict(kind="rays", x=330, y=700, r0=50, r1=420, n=26, w=9, color="#8a561e30", z=-50, show=[T(248), 99]),
    "pick_l": dict(kind="pick", x=262, y=866, angle=172, len=84, z=2, show=[T(242), 99]),
    "pick_r": dict(kind="pick", x=340, y=866, angle=8, len=84, z=2, show=[T(242), 99]),
    "coin": dict(kind="art", name="dig_token", x=COIN[0], y=COIN[1], r=43, z=20, show=[T(244), 99],
                 keys=[{"t": T(244), "r": 8, "ease": "back"}, {"t": T(251), "r": 43}]),
    "pile": dict(kind="art", name="dig_pile", x=305, y=864, z=3, show=[T(252), 99]),
    "pour": dict(kind="burst", times=[T(246) + 0.02 * i for i in range(14)], at=[318, 700], n=3, speed=[20, 90],
                 angle=[-120, -60], gravity=520, life=0.5, size=[3.5, 5.5], color="#f6c428", seed=3, z=25),
    "pirate_lbl": dict(kind="text", text="PIRATE TOKEN", x=COIN[0], y=COIN[1] - 52, size=12, fill="#fff6e2", outline="#462c18", ow=1.4,
                       width=96, z=30, show=[T(256), T(281)], keys=[{"t": T(256), "alpha": 0.0}, {"t": T(262), "alpha": 1.0}]),
    "rays_burst": dict(kind="rays", x=COIN[0], y=COIN[1], r0=60, r1=260, n=14, w=2, color="#fff4cc", z=41, show=[T(270), T(278)],
                       keys=[{"t": T(270), "alpha": 0.9, "r0": 50}, {"t": T(277), "alpha": 0.0, "r0": 150, "ease": "out"}]),
    "flash1": dict(kind="rect", x=288, y=512, w=640, h=1100, fill="#ffffff", space="screen", z=100, alpha=0.0,
                   keys=[{"t": T(238), "alpha": 0.0}, {"t": T(240.5), "alpha": 0.8, "ease": "out"}, {"t": T(246), "alpha": 0.0}]),
    "flash2": dict(kind="rect", x=288, y=512, w=640, h=1100, fill="#fff4d0", space="screen", z=100, alpha=0.0,
                   keys=[{"t": T(268), "alpha": 0.0}, {"t": T(270), "alpha": 0.7}, {"t": T(274), "alpha": 0.0}]),
    "fade": dict(kind="rect", x=288, y=512, w=640, h=1100, fill="#000000", space="screen", z=110, alpha=0.0,
                 keys=[{"t": T(331), "alpha": 0.0}, {"t": T(339), "alpha": 1.0, "ease": "linear"}]),
}
for i, (a, d) in enumerate([(247, 0.7), (250, 0.8), (253, 0.9), (274, 0.6), (277, 0.7), (280, 0.8), (283, 0.9), (296, 1.0), (303, 1.1)]):
    objects[f"ring{i}"] = ring(T(a), d, 20, 120 if a >= 274 and a < 290 else 260)
for i, (n, s) in enumerate([(282, "SEND"), (286, "SEND THIS TO"), (290, "SEND THIS TO THE ONE")]):
    pass
objects["end1"] = dict(kind="text", text="SEND THIS TO THE ONE", x=103, y=132, size=19, fill="#fff2d0", outline="#5a3a1a", ow=2, align="left",
                       track=4.2, weight=800, space="screen", z=60, show=[T(281), 99],
                       keys=[{"t": T(281), "reveal": 0}, {"t": T(291.5), "reveal": 20, "ease": "linear"}])
objects["end2"] = dict(kind="text", text="WHO WON'T LET YOU QUIT.", x=75, y=164, size=19, fill="#fff2d0", outline="#5a3a1a", ow=2, align="left",
                       track=4.2, weight=800, space="screen", z=60, show=[T(291.5), 99],
                       keys=[{"t": T(291.5), "reveal": 0}, {"t": T(305), "reveal": 23, "ease": "linear"}])
objects["sign"]["show"] = [0, T(243)]
objects["wall_wash"] = dict(kind="rect", x=530, y=626, w=140, h=520, fill="#e6b865", alpha=0.0, z=-77,
                            keys=[{"t": T(241), "alpha": 0.0}, {"t": T(248), "alpha": 0.5}])
actors = {
    "friend": dict(ground=576, shadow=False, x=102, keys=hip_keys("f") + [
        {"t": 0, "pose": "stand", "expr": "blank", "prop": "pick_friend", "anim": "chop", "hits": [T(n) for n in FRIEND_HITS]},
        # walks forward to the shaft spot, then digs down
        {"t": T(148), "anim": "dig_down", "hits": [T(n) for n in DIG_HITS], "anim_blend": 0.12},
        {"t": T(189), "anim": None, "prop": None, "pose": "fall", "expr": "scared", "ease": "step"},
        {"t": T(190), "x": 236, "ground": 576},
        {"t": T(194), "ground": 866, "ease": "in2"},
        {"t": T(198), "pose": "stand", "expr": "blank", "prop": "pick_friend", "lean": 20, "head": 14, "grip_rel": [34, -34], "prop_angle": 140, "ease": "out"},
        {"t": T(204), "x": 238, "ease": "inout"},
        {"t": T(206), "anim": "chop", "hits": [T(n) + 0.03 for n in TOGETHER], "anim_blend": 0.12},
        {"t": T(240), "anim": None, "prop": None, "pose": "cheer", "tint": GOLD, "expr": "happy", "yaw": 0},
        {"t": T(244), "x": 335, "hand_r_at": [330, COIN[1] + 40], "hand_l_at": [350, COIN[1] + 46], "yaw": 90,
         "leg_r": [4, 0, 11], "leg_l": [-4, 0, 11], "ease": "out"},
    ]),
    "you": dict(ground=866, shadow=False, x=201, keys=hip_keys("y") + [
        {"t": 0, "pose": "stand", "expr": "blank", "prop": "pick_you", "anim": "chop", "hits": [T(n) for n in YOU_HITS]},
        {"t": T(151), "anim": None, "pose": "tired", "lean": 34, "head": 24, "grip_rel": [34, -32], "prop_angle": 140, "x": 296, "ease": "out"},
        {"t": T(190), "x": 304, "ease": "linear"},
        {"t": T(200), "x": 280, "ease": "inout"},
        {"t": T(206), "anim": "chop", "hits": [T(n) for n in TOGETHER], "anim_blend": 0.12, "x": 282},
        {"t": T(240), "anim": None, "prop": None, "pose": "cheer", "tint": GOLD, "expr": "happy", "grip_rel": None, "yaw": 0},
        {"t": T(244), "x": 267, "hand_r_at": [252, COIN[1] + 46], "hand_l_at": [272, COIN[1] + 40], "yaw": 90,
         "leg_r": [4, 0, 11], "leg_l": [-4, 0, 11], "ease": "out"},
    ]),
}

scene = dict(
    canvas=dict(w=576, h=1024, fps=30, duration=11.3, scale=2, bg="#000000", blur=2),
    plugins=["stickreel.art_dig"],
    loops=loops,
    camera=dict(zoom=1.0, cx=288, cy=512, keys=[{"t": T(241), "zoom": 1.0, "cx": 288, "cy": 512},
                                                {"t": T(255), "zoom": 1.2, "cx": 366, "cy": 695, "ease": "out"}]),
    objects=objects, actors=actors)

if __name__ == "__main__":
    out = os.path.join(HERE, "dig_skit.json")
    json.dump(scene, open(out, "w"), indent=1)
    print("wrote", out)
