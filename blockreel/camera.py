from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .errors import SceneError


@dataclass
class Camera:
    position: np.ndarray
    right: np.ndarray
    up: np.ndarray
    fwd: np.ndarray
    fov: float  # vertical field of view, degrees
    focus_dist: float = 10.0  # distance to the look-at point, used for depth of field

    @classmethod
    def from_look_at(cls, position, target, fov):
        position = np.asarray(position, dtype=np.float64)
        f = np.asarray(target, dtype=np.float64) - position
        n = np.linalg.norm(f)
        if n < 1e-9:
            raise SceneError("camera position and look-at point are the same")
        f = f / n
        world_up = np.array([0.0, 1.0, 0.0])
        r = np.cross(f, world_up)
        if np.linalg.norm(r) < 1e-6:  # looking straight up or down
            r = np.cross(f, np.array([0.0, 0.0, 1.0]))
        r = r / np.linalg.norm(r)
        u = np.cross(r, f)
        return cls(position, r, u, f, float(fov), float(n))
