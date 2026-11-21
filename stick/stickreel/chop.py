"""Hand-keyed chop cycle for the stick-figure rig.

One template figure, both hands on a single grip point on the pick handle, the pick is a rigid stick that swings
about that grip. Every key is hand-authored: (time in frames, grip relative to hip, pick angle in degrees (0 = right,
-90 = straight up), torso lean in radians (+ = forward), head tilt, hip bob, feet).
"""
import math
import numpy as np
from scipy.interpolate import PchipInterpolator
from .figure import ik2

TL, HL = 58.0, 19.0
PERIOD = 22.0

#       t    grip_rel_hip   pick   lean  tilt  hip_dy  footA     footB
YOU_KEYS = [
    (0.0,  (-45, -86), -148, 0.06, 0.00,  0, (16, 82), (-20, 81)),   # BACK: pick behind the head, body upright
    (2.0,  (-40, -90), -132, 0.04, 0.00, -1, (16, 82), (-20, 81)),   # wind-up settle
    (3.0,  (  8, -80),  -70, 0.28, -0.10, 1, (20, 82), (-24, 81)),   # snap forward (fast)
    (4.0,  ( 76, -38),    8, 0.52, -0.22, 4, (26, 82), (-30, 80)),   # CONTACT
    (7.0,  ( 80, -36),    6, 0.54, -0.24, 5, (26, 82), (-30, 80)),   # hold, flash
    (9.5,  ( 78, -38),    0, 0.52, -0.24, 4, (26, 82), (-30, 80)),   # pull
    (11.5, ( 68, -52),  -14, 0.46, -0.30, 3, (24, 82), (-27, 81)),   # recoil
    (14.0, ( 46, -72),  -30, 0.36, -0.30, 1, (22, 82), (-22, 81)),   # raise
    (17.0, ( 44, -86),  -56, 0.24, -0.20, -1, (20, 82), (-18, 81)),  # high
    (19.5, ( 12, -98),  -92, 0.12, -0.05, -2, (18, 82), (-17, 81)),  # overhead
    (22.0, (-45, -86), -148, 0.06, 0.00,  0, (16, 82), (-20, 81)),   # BACK again
]


def _interp(keys, t, period):
    """periodic PCHIP over the key table; returns dict of values at time t (frames)."""
    ts = np.array([k[0] for k in keys])
    cols = {
        "gx": [k[1][0] for k in keys], "gy": [k[1][1] for k in keys], "pick": [k[2] for k in keys],
        "lean": [k[3] for k in keys], "tilt": [k[4] for k in keys], "dy": [k[5] for k in keys],
        "ax": [k[6][0] for k in keys], "ay": [k[6][1] for k in keys], "bx": [k[7][0] for k in keys], "by": [k[7][1] for k in keys],
    }
    t = t % period
    out = {}
    for name, vals in cols.items():
        v = np.array(vals, float)
        T = np.concatenate([ts[:-1] - period, ts, ts[1:] + period])
        V = np.concatenate([v[:-1], v, v[1:]])
        out[name] = float(PchipInterpolator(T, V)(t))
    return out


def pose_from(v, hip_x, hip_y, speed_scale=1.0):
    hip = (hip_x, hip_y + v["dy"])
    a = v["lean"]
    neck = (hip[0] + TL * math.sin(a), hip[1] - TL * math.cos(a))
    hd = a + v["tilt"]
    head = (neck[0] + HL * math.sin(hd), neck[1] - HL * math.cos(hd))
    grip = (hip[0] + v["gx"], hip[1] + v["gy"])
    feet = [(hip[0] + v["ax"], hip[1] + v["ay"]), (hip[0] + v["bx"], hip[1] + v["by"])]
    return dict(head=head, neck=neck, hip=hip, hands=[grip, grip], feet=feet, eb=[1, 1], kb=[-1, -1],
                pick=v["pick"], pick_len=64)


def chop_pose(keys, t, hip_x, hip_y, period=PERIOD):
    return pose_from(_interp(keys, t, period), hip_x, hip_y)
