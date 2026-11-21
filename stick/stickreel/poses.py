"""Named poses and loops. A pose is just a dict of skeleton params; a loop is a repeating set of keys over phase 0..1.

Scenes can add their own under "poses" and "loops" (same format), so an agent never has to touch Python.
"""
import math

POSES = {
    "stand": {},
    "relax": dict(arm_r=[4, 8], arm_l=[-4, 8], leg_r=[3, 0], leg_l=[-3, 0]),
    "hands_up": dict(arm_r=[152, 6], arm_l=[-152, 6], lean=-2),
    "hands_up_wide": dict(arm_r=[140, 6], arm_l=[-140, 6], lean=-3),
    "cheer": dict(arm_r=[150, 14], arm_l=[-150, 14], lean=-4, head=-6),
    "wave": dict(arm_r=[150, 50], arm_l=[-6, 10]),
    "point": dict(arm_r=[92, 0], arm_l=[-8, 10], lean=4),
    "reach_forward": dict(arm_r=[100, 0], arm_l=[92, 0], lean=8),
    "crouch": dict(leg_r=[62, 118], leg_l=[40, 100], lean=22, arm_r=[40, 30], arm_l=[20, 30]),
    "sit": dict(leg_r=[90, 90], leg_l=[84, 90], lean=2, arm_r=[20, 40], arm_l=[10, 40]),
    "slump": dict(lean=14, head=18, arm_r=[10, 6], arm_l=[-2, 6]),
    "shrug": dict(arm_r=[40, 70], arm_l=[-40, 70], head=6),
    "hold_overhead": dict(arm_r=[160, 30], arm_l=[160, 30], lean=-4),
    "fall": dict(arm_r=[150, 8], arm_l=[-150, 8], leg_r=[28, 10], leg_l=[-28, 10], rot=-8),
    "tired": dict(lean=18, head=22, arm_r=[6, 4], arm_l=[-6, 4], leg_r=[6, 12], leg_l=[-6, 12]),
}


def _sin_keys(fn, n=8):
    return [dict(t=i / n, **fn(2 * math.pi * i / n)) for i in range(n)]


def _walk(amp, knee, arm, lean, lift=0.0):
    def k(th):
        c, s = math.cos(th), math.sin(th)
        c2, s2 = math.cos(th + math.pi), math.sin(th + math.pi)
        return dict(
            leg_r=[amp * c, knee * max(0.0, -s)], leg_l=[amp * c2, knee * max(0.0, -s2)],
            arm_r=[-arm * c, 6 + 8 * max(0.0, -c)], arm_l=[-arm * c2, 6 + 8 * max(0.0, -c2)], lean=lean, lift=lift * abs(s))
    return _sin_keys(k, 12)


# mode "add": values are added to whatever the keys set; "replace": loop values win.
# source "distance": one cycle = `stride` pixels travelled (feet do not slide); "time": one cycle = `period` seconds;
# "hits": phase follows the actor's `hits` list (see docs).
LOOPS = {
    "walk": dict(mode="add", source="distance", stride=150, keys=_walk(26, 50, 22, 3)),
    "run": dict(mode="add", source="distance", stride=250, keys=_walk(44, 95, 55, 14, lift=9)),
    "idle": dict(mode="add", source="time", period=2.4, keys=_sin_keys(lambda th: dict(
        lean=1.2 * math.sin(th), head=1.5 * math.sin(th - 0.8), arm_r=[1.5 * math.sin(th), 0], arm_l=[-1.5 * math.sin(th), 0]), 8)),
    "wave": dict(mode="add", source="time", period=0.7, keys=_sin_keys(lambda th: dict(arm_r=[0, 28 * math.sin(th)]), 8)),
    "bounce": dict(mode="add", source="time", period=0.5, keys=_sin_keys(lambda th: dict(lift=7 * (1 - math.cos(th)) / 2), 8)),
    "dance": dict(mode="add", source="time", period=0.8, keys=_sin_keys(lambda th: dict(
        arm_r=[60 * math.sin(th), 30], arm_l=[-60 * math.sin(th), 30], lean=6 * math.sin(th), lift=4 * abs(math.sin(th)),
        head=8 * math.sin(th)), 12)),
    # Hand-keyed two-handed overhead chop (both hands on ONE grip, rigid tool). phase 0 = tool back behind the head.
    # grip_rel is hip-relative; prop_angle 0 = tool pointing forward(right), -90 = up. Hit = contact (hit_phase).
    "chop": dict(mode="replace", source="hits", period=0.733, hit_phase=4 / 22, keys=[
        dict(t=0 / 22, grip_rel=[-45, -86], prop_angle=-148, lean=6, head=0, foot_r_rel=[16, 82], foot_l_rel=[-20, 81]),
        dict(t=2 / 22, grip_rel=[-40, -90], prop_angle=-132, lean=4, head=0, foot_r_rel=[16, 83], foot_l_rel=[-20, 82]),
        dict(t=3 / 22, grip_rel=[8, -80], prop_angle=-70, lean=16, head=-6, foot_r_rel=[20, 81], foot_l_rel=[-24, 80]),
        dict(t=4 / 22, grip_rel=[76, -38], prop_angle=8, lean=30, head=-13, foot_r_rel=[26, 78], foot_l_rel=[-30, 77]),
        dict(t=7 / 22, grip_rel=[80, -36], prop_angle=6, lean=31, head=-14, foot_r_rel=[26, 77], foot_l_rel=[-30, 76]),
        dict(t=9.5 / 22, grip_rel=[78, -38], prop_angle=0, lean=30, head=-14, foot_r_rel=[26, 78], foot_l_rel=[-30, 77]),
        dict(t=11.5 / 22, grip_rel=[68, -52], prop_angle=-14, lean=26, head=-17, foot_r_rel=[24, 79], foot_l_rel=[-27, 78]),
        dict(t=14 / 22, grip_rel=[46, -72], prop_angle=-30, lean=21, head=-17, foot_r_rel=[22, 81], foot_l_rel=[-22, 80]),
        dict(t=17 / 22, grip_rel=[44, -86], prop_angle=-56, lean=14, head=-11, foot_r_rel=[20, 83], foot_l_rel=[-18, 82]),
        dict(t=19.5 / 22, grip_rel=[12, -98], prop_angle=-92, lean=7, head=-3, foot_r_rel=[18, 84], foot_l_rel=[-17, 83]),
    ]),
}
for _k in LOOPS["chop"]["keys"]:
    _k.update(grip_w=1.0, foot_r_w=1.0, foot_l_w=1.0)
