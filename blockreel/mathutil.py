from __future__ import annotations

import math
from functools import reduce

import numpy as np

from .errors import SceneError


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, u):
    return a + (b - a) * u


def smoothstep(u):
    u = clamp(u, 0.0, 1.0)
    return u * u * (3.0 - 2.0 * u)


def lerp_angle(a, b, u):
    """Interpolate degrees along the shortest arc."""
    d = ((b - a + 180.0) % 360.0) - 180.0
    return a + d * u


def wrap_angle(a):
    return ((a + 180.0) % 360.0) - 180.0


def normalize(v):
    v = np.asarray(v, dtype=np.float64)
    n = np.linalg.norm(v)
    if n < 1e-12:
        raise ValueError("zero-length vector")
    return v / n


def translate(x, y=None, z=None):
    if y is None:
        x, y, z = x
    m = np.eye(4)
    m[0, 3], m[1, 3], m[2, 3] = x, y, z
    return m


def scale_m(s):
    m = np.eye(4)
    m[0, 0] = m[1, 1] = m[2, 2] = s
    return m


def rot_x(deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    m = np.eye(4)
    m[1, 1], m[1, 2], m[2, 1], m[2, 2] = c, -s, s, c
    return m


def rot_y(deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    m = np.eye(4)
    m[0, 0], m[0, 2], m[2, 0], m[2, 2] = c, s, -s, c
    return m


def rot_z(deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    m = np.eye(4)
    m[0, 0], m[0, 1], m[1, 0], m[1, 1] = c, -s, s, c
    return m


def mat_mul(*ms):
    return reduce(np.matmul, ms)


EASES = {
    "linear": lambda u: u,
    "ease_in": lambda u: u * u,
    "ease_out": lambda u: 1.0 - (1.0 - u) * (1.0 - u),
    "ease_in_out": smoothstep,
    "hold": lambda u: 0.0,  # stay on the first key until the next one, then jump
}


def apply_ease(name, u):
    try:
        return EASES[name](clamp(u, 0.0, 1.0))
    except KeyError:
        raise SceneError(f"unknown ease '{name}'. Options: {', '.join(EASES)}")


def parse_color(value, ctx="color"):
    """'#rgb', '#rrggbb' or [r, g, b] (0-255) to an (r, g, b) int tuple."""
    if isinstance(value, str):
        s = value.strip().lstrip("#")
        if len(s) == 3:
            s = "".join(ch * 2 for ch in s)
        if len(s) != 6:
            raise SceneError(f"{ctx}: '{value}' is not a #rrggbb colour")
        try:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
        except ValueError:
            raise SceneError(f"{ctx}: '{value}' is not a #rrggbb colour")
    if isinstance(value, (list, tuple)) and len(value) == 3:
        try:
            return tuple(int(clamp(float(c), 0, 255)) for c in value)
        except (TypeError, ValueError):
            pass
    raise SceneError(f"{ctx}: expected '#rrggbb' or [r, g, b], got {value!r}")


def vec3(value, ctx="vector"):
    try:
        arr = np.array(value, dtype=np.float64)
    except (TypeError, ValueError):
        raise SceneError(f"{ctx}: expected three numbers, got {value!r}")
    if arr.shape != (3,):
        raise SceneError(f"{ctx}: expected three numbers, got {value!r}")
    return arr
