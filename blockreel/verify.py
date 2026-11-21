"""Check that the built figure matches the rig file, in the rest pose."""
from __future__ import annotations

import numpy as np

from . import poses
from .character import build_items
from .errors import SceneError

_APP = None


def _plain_appearance():
    from .appearance import resolve_appearance
    return resolve_appearance({"hair": {"style": "none"}, "face": {"brows": "none"},
                               "outfit": {"sleeves": "none"}})


def rest_extents(rig):
    """World-space bounding boxes (min, max) of the body parts in the rest pose, standing at the origin."""
    items = build_items(_plain_appearance(), rig, np.zeros(3), 0.0, poses.full({}), 1.0)
    from .meshes import get_mesh
    boxes = []
    for it in items:
        if it.shape == "head":
            V, _, _ = get_mesh("head", it.size, 0.0)
        else:
            V = np.array([[x, y, z] for x in (-.5, .5) for y in (-.5, .5) for z in (-.5, .5)]) * np.array(it.size)
        W = V @ it.model[:3, :3].T + it.model[:3, 3]
        boxes.append((W.min(axis=0), W.max(axis=0), it))
    return boxes


def check_rig(rig, tol=1e-6):
    """Return a text report; raise SceneError if the geometry and the rig disagree."""
    boxes = rest_extents(rig)
    lo = np.min([b[0] for b in boxes], axis=0)
    hi = np.max([b[1] for b in boxes], axis=0)
    problems = []
    # skip shoes (overlays) when measuring the body: they are clothing, drawn 0.01 below the sole
    body = [b for b in boxes if not (b[2].size[1] == 0.45)]
    blo = np.min([b[0] for b in body], axis=0)
    bhi = np.max([b[1] for b in body], axis=0)
    if abs(blo[1]) > 0.02:
        problems.append(f"feet are {blo[1]:+.3f} studs from the ground")
    height = bhi[1] - blo[1]
    if abs(height - rig.height) > 0.03:
        problems.append(f"height {height:.3f} but the rig says {rig.height:.3f}")
    width = bhi[0] - blo[0]
    want_w = 2 * (abs(rig.joint["right_shoulder"]["pivot"][0] + rig.joint["right_shoulder"]["offset"][0])
                  + rig.part_size["right_arm"][0] / 2)
    if abs(width - want_w) > 0.05:
        problems.append(f"width across the arms {width:.3f} but the rig says {want_w:.3f}")
    lines = ["built-figure check (rest pose, no clothing overlays):",
             f"  height  {height:.4f} studs   (rig: {rig.height:.4f})",
             f"  width   {width:.4f} studs across the arms   (rig: {want_w:.4f})",
             f"  depth   {bhi[2] - blo[2]:.4f} studs"]
    if problems:
        raise SceneError("figure does not match the rig: " + "; ".join(problems))
    lines.append("  result: matches the rig")
    return "\n".join(lines)
