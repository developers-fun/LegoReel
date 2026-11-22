"""Shared helpers: color parsing and small 4x4 matrix toolkit (column-vector convention)."""
from __future__ import annotations
import math
import numpy as np

_NAMED = {
    "white": (1, 1, 1), "black": (0, 0, 0), "red": (1, 0.1, 0.1), "green": (0.1, 0.8, 0.2),
    "blue": (0.1, 0.3, 1), "yellow": (1, 0.9, 0.1), "orange": (1, 0.55, 0.1),
    "purple": (0.6, 0.2, 0.9), "pink": (1, 0.45, 0.7), "gray": (0.5, 0.5, 0.5), "grey": (0.5, 0.5, 0.5),
}


def color(c) -> tuple:
    """Parse a color into an (r, g, b) float tuple in 0..1.

    Accepts "#rgb", "#rrggbb", "#rrggbbaa" (alpha dropped), named colors, 0..1 float
    sequences, or 0..255 sequences (auto-detected when any component > 1). Extra alpha
    component of a sequence is dropped.
    """
    if isinstance(c, str):
        s = c.strip().lower()
        if s in _NAMED:
            return tuple(float(x) for x in _NAMED[s])
        s = s.lstrip("#")
        if len(s) in (3, 4):
            s = "".join(ch * 2 for ch in s)
        if len(s) not in (6, 8):
            raise ValueError(f"bad color string: {c!r}")
        return tuple(int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    a = [float(x) for x in np.asarray(c, dtype=np.float64).ravel()]
    if len(a) == 1:
        a = a * 3
    if len(a) < 3:
        raise ValueError(f"bad color: {c!r}")
    a = a[:3]
    if max(a) > 1.0:
        a = [x / 255.0 for x in a]
    return tuple(min(1.0, max(0.0, x)) for x in a)


def normalize(v):
    v = np.asarray(v, np.float64)
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def translate(x, y=None, z=None) -> np.ndarray:
    if y is None:
        x, y, z = x
    m = np.eye(4)
    m[:3, 3] = (x, y, z)
    return m


def scale(x, y=None, z=None) -> np.ndarray:
    if y is None:
        if np.ndim(x) == 0:
            x, y, z = x, x, x
        else:
            x, y, z = x
    return np.diag([x, y, z, 1.0])


def rotate_euler_deg(rx=0.0, ry=0.0, rz=0.0) -> np.ndarray:
    """Rotation matrix R = Rx @ Ry @ Rz (Roblox CFrame.Angles order), angles in degrees."""
    if np.ndim(rx) > 0:
        rx, ry, rz = rx
    ax, ay, az = (math.radians(a) for a in (rx, ry, rz))
    cx, sx, cy, sy, cz, sz = math.cos(ax), math.sin(ax), math.cos(ay), math.sin(ay), math.cos(az), math.sin(az)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    m = np.eye(4)
    m[:3, :3] = Rx @ Ry @ Rz
    return m


def compose(position=(0, 0, 0), rotation=(0, 0, 0), scale_=(1, 1, 1)) -> np.ndarray:
    """T @ R @ S with euler degrees rotation (see rotate_euler_deg)."""
    s = np.broadcast_to(np.asarray(scale_, np.float64), (3,))
    return translate(*position) @ rotate_euler_deg(*rotation) @ np.diag([s[0], s[1], s[2], 1.0])


def look_at(eye, target, up=(0, 1, 0), roll_deg=0.0) -> np.ndarray:
    """World -> view matrix (camera looks down -Z). roll rotates `up` about the view axis."""
    eye = np.asarray(eye, np.float64)
    f = normalize(np.asarray(target, np.float64) - eye)
    if np.linalg.norm(f) < 1e-9:
        f = np.array([0.0, 0.0, -1.0])
    up = normalize(up)
    if abs(float(np.dot(f, up))) > 0.9995:        # looking straight up/down
        up = np.array([0.0, 0.0, -1.0]) if abs(f[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    if roll_deg:
        a = math.radians(roll_deg)
        up = up * math.cos(a) + np.cross(f, up) * math.sin(a) + f * np.dot(f, up) * (1 - math.cos(a))
    r = normalize(np.cross(f, up))
    u = np.cross(r, f)
    m = np.eye(4)
    m[0, :3], m[1, :3], m[2, :3] = r, u, -f
    m[:3, 3] = -m[:3, :3] @ eye
    return m


def perspective(fov_y_deg, aspect, near, far) -> np.ndarray:
    t = 1.0 / math.tan(math.radians(fov_y_deg) * 0.5)
    m = np.zeros((4, 4))
    m[0, 0], m[1, 1] = t / aspect, t
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = 2 * far * near / (near - far)
    m[3, 2] = -1.0
    return m


def ortho(l, r, b, t, n, f) -> np.ndarray:
    m = np.eye(4)
    m[0, 0], m[1, 1], m[2, 2] = 2 / (r - l), 2 / (t - b), -2 / (f - n)
    m[:3, 3] = (-(r + l) / (r - l), -(t + b) / (t - b), -(f + n) / (f - n))
    return m
