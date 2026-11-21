"""Pose clips: joint angles in degrees as a function of time.

Sign conventions (character faces +z, y is up):
  *_arm_pitch, *_leg_pitch   positive swings the limb forward
  *_arm_roll                 positive raises the arm outward, away from the body
  torso_pitch                positive leans forward
  head_pitch                 positive looks down
  head_yaw, torso_yaw        positive turns toward the character's left
  root_y                     vertical offset of the whole body, in studs
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from .errors import SceneError
from .mathutil import clamp, lerp, smoothstep

TWO_PI = 2.0 * math.pi

JOINTS = (
    "root_y",
    "torso_pitch", "torso_yaw",
    "head_yaw", "head_pitch",
    "r_arm_pitch", "r_arm_roll",
    "l_arm_pitch", "l_arm_roll",
    "r_leg_pitch", "l_leg_pitch",
)

_SWAP = {
    "r_arm_pitch": "l_arm_pitch", "l_arm_pitch": "r_arm_pitch",
    "r_arm_roll": "l_arm_roll", "l_arm_roll": "r_arm_roll",
    "r_leg_pitch": "l_leg_pitch", "l_leg_pitch": "r_leg_pitch",
}


def full(d):
    out = {j: 0.0 for j in JOINTS}
    out.update(d)
    return out


def mirror(p):
    out = dict(p)
    for a, b in _SWAP.items():
        out[a] = p[b]
    out["torso_yaw"] = -p["torso_yaw"]
    out["head_yaw"] = -p["head_yaw"]
    return out


def lerp_pose(a, b, u):
    return {k: lerp(a[k], b[k], u) for k in JOINTS}


# ---- clip functions: (t_seconds, params) -> partial joint dict -------------

def _idle(t, p):
    b = math.sin(t * TWO_PI * 0.35)
    return {
        "torso_pitch": 0.8 * b,
        "head_pitch": 1.2 * b,
        "head_yaw": 2.5 * math.sin(t * TWO_PI * 0.12),
        "r_arm_roll": 5 + 1.5 * b,
        "l_arm_roll": 5 + 1.5 * b,
    }


def _locomotion(t, p, run):
    speed = float(p.get("speed", 6.0 if run else 4.0))
    hz = max(0.3, speed / (4.6 if run else 3.2))
    ph = t * TWO_PI * hz
    s = math.sin(ph)
    amp = 50.0 if run else 30.0
    # Drop the body as the legs spread so the feet stay on the ground.
    dip = -2.0 * (1.0 - math.cos(math.radians(amp * abs(s))))
    return {
        "r_leg_pitch": amp * s,
        "l_leg_pitch": -amp * s,
        "r_arm_pitch": -amp * 0.9 * s,
        "l_arm_pitch": amp * 0.9 * s,
        "r_arm_roll": 6.0,
        "l_arm_roll": 6.0,
        "root_y": dip,
        "torso_pitch": 12.0 if run else 2.0,
        "torso_yaw": 5.0 * s,
    }


def _walk(t, p):
    return _locomotion(t, p, False)


def _run(t, p):
    return _locomotion(t, p, True)


def _wave(t, p):
    s = math.sin(t * TWO_PI * 2.8)
    return {"r_arm_roll": 135 + 22 * s, "head_yaw": 6.0, "head_pitch": -3.0, "torso_yaw": -4.0}


def _point(t, p):
    return {"r_arm_pitch": 88.0, "r_arm_roll": 6.0, "head_pitch": 2.0}


def _think(t, p):
    return {"r_arm_pitch": 115.0, "r_arm_roll": -8.0, "head_pitch": 8.0, "torso_yaw": -3.0}


def _sit(t, p):
    # Legs forward. Put the character's y at (seat_top - 2) so the torso rests on the seat.
    return {"r_leg_pitch": 90.0, "l_leg_pitch": 90.0, "r_arm_pitch": 25.0, "l_arm_pitch": 25.0,
            "r_arm_roll": 4.0, "l_arm_roll": 4.0}


def _look_down(t, p):
    return {"head_pitch": 35.0, "torso_pitch": 4.0}


def _cheer(t, p):
    s = math.sin(t * TWO_PI * 1.6)
    return {"r_arm_pitch": 165 + 8 * s, "l_arm_pitch": 165 + 8 * s,
            "r_arm_roll": 22.0, "l_arm_roll": 22.0, "root_y": 0.5 * abs(s), "head_pitch": -8.0}


def _jump(t, p):
    L = p["_L"]
    u = clamp(t / L, 0.0, 1.0)
    arc = math.sin(math.pi * u)
    return {"root_y": 2.4 * 4.0 * u * (1.0 - u), "r_arm_pitch": 150 * arc, "l_arm_pitch": 150 * arc,
            "r_arm_roll": 20 * arc, "l_arm_roll": 20 * arc,
            "r_leg_pitch": -25 * arc, "l_leg_pitch": 15 * arc, "head_pitch": -6 * arc}


def _surprised(t, p):
    return {"r_arm_roll": 55.0, "l_arm_roll": 55.0, "r_arm_pitch": 15.0, "l_arm_pitch": 15.0,
            "torso_pitch": -10.0, "head_pitch": -6.0,
            "root_y": 0.45 * math.sin(math.pi * min(t / 0.3, 1.0))}


def _shrug(t, p):
    return {"r_arm_roll": 38.0, "l_arm_roll": 38.0, "r_arm_pitch": 12.0, "l_arm_pitch": 12.0,
            "head_pitch": -4.0, "head_yaw": 6.0 * math.sin(t * TWO_PI * 1.2)}


def _nod(t, p):
    return {"head_pitch": 14.0 * math.sin(t * TWO_PI * 2.2)}


def _shake_head(t, p):
    return {"head_yaw": 22.0 * math.sin(t * TWO_PI * 2.5)}


def _dig(t, p):
    # Pickaxe chop: both arms swing up and down together, torso leans into the downstroke.
    hz = float(p.get("speed", 1.6))
    ph = t * TWO_PI * hz
    s = math.sin(ph)
    return {"r_arm_pitch": 125.0 + 45.0 * s, "l_arm_pitch": 125.0 + 45.0 * s,
            "r_arm_roll": 6.0, "l_arm_roll": 6.0,
            "torso_pitch": 12.0 - 10.0 * s, "head_pitch": 8.0, "root_y": 0.12 * abs(s)}


def _phone(t, p):
    # Seated, head down, both forearms out in front as if holding a phone.
    return {"r_leg_pitch": 90.0, "l_leg_pitch": 90.0, "r_arm_pitch": 62.0, "l_arm_pitch": 62.0,
            "r_arm_roll": -6.0, "l_arm_roll": -6.0, "head_pitch": 14.0, "torso_pitch": 4.0}


@dataclass(frozen=True)
class Clip:
    fn: Callable
    kind: str          # loop: repeats | hold: stays until the next pose | oneshot: plays once, returns to idle
    length: float = 0.0


CLIPS = {
    "idle": Clip(_idle, "loop"),
    "walk": Clip(_walk, "loop"),
    "run": Clip(_run, "loop"),
    "wave": Clip(_wave, "loop"),
    "cheer": Clip(_cheer, "loop"),
    "point": Clip(_point, "hold"),
    "think": Clip(_think, "hold"),
    "sit": Clip(_sit, "hold"),
    "look_down": Clip(_look_down, "hold"),
    "dig": Clip(_dig, "loop"),
    "phone": Clip(_phone, "hold"),
    "jump": Clip(_jump, "oneshot", 0.8),
    "surprised": Clip(_surprised, "oneshot", 1.0),
    "shrug": Clip(_shrug, "oneshot", 1.2),
    "nod": Clip(_nod, "oneshot", 0.9),
    "shake_head": Clip(_shake_head, "oneshot", 1.0),
}


def _envelope(t, length, ramp=0.15):
    if t <= 0.0 or t >= length:
        return 0.0
    return smoothstep(min(t / ramp, (length - t) / ramp, 1.0))


def evaluate(name, t, params=None):
    params = params or {}
    clip = CLIPS.get(name)
    if clip is None:
        raise SceneError(f"unknown pose '{name}'. Options: {', '.join(CLIPS)}")
    t = max(0.0, t)
    if clip.kind == "oneshot":
        length = float(params.get("duration", clip.length))
        if length <= 0:
            raise SceneError(f"pose '{name}': duration must be above zero")
        p = dict(params)
        p["_L"] = length
        gesture = full(clip.fn(t, p))
        base = full(_idle(t, p))
        env = _envelope(t, length, 0.08 if name == "jump" else 0.15)
        pose = lerp_pose(base, gesture, env)
    else:
        pose = full(clip.fn(t, params))
    if params.get("hand") == "left":
        pose = mirror(pose)
    return pose
