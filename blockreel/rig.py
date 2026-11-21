"""Rig loader: exact part sizes and joint offsets from rigs/<name>.json.

The file stores Roblox-space numbers. Here they are converted once to blockreel space
(x and z flipped, so the character faces +z and its right side is at -x) and exposed
as plain numbers the character builder uses. Nothing in the geometry is hard-coded
any more: change the rig file and the character changes.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from .errors import SceneError

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_PARTS = ("head", "torso", "right_arm", "left_arm", "right_leg", "left_leg")
REQUIRED_JOINTS = ("neck", "right_shoulder", "left_shoulder", "right_hip", "left_hip")


def _flip(v):
    return np.array([-v[0], v[1], -v[2]], dtype=np.float64)


class Rig:
    def __init__(self, data, path):
        self.path = path
        self.name = str(data.get("name", "rig"))
        self.version = data.get("version", 1)
        self.raw = data
        parts = data.get("parts", {})
        joints = data.get("joints", {})
        for p in REQUIRED_PARTS:
            if p not in parts:
                raise SceneError(f"rig '{self.name}': missing part '{p}'")
        for j in REQUIRED_JOINTS:
            if j not in joints:
                raise SceneError(f"rig '{self.name}': missing joint '{j}'")
        self.part_size = {k: tuple(float(x) for x in v["size"]) for k, v in parts.items()}
        head_mesh = parts["head"].get("mesh", {})
        hs = float(head_mesh.get("scale", 1.0))
        # A Head mesh ignores the part's 2x1x1 aspect and renders as a cube of side `scale`.
        self.head_visible = (hs, hs, hs) if head_mesh.get("type") == "head" else self.part_size["head"]
        self.joint = {}
        for k, j in joints.items():
            c0, c1 = _flip(j["c0"]), _flip(j["c1"])
            self.joint[k] = {"parent": j["parent"], "child": j["child"],
                             "pivot": c0,          # joint position in the parent part's frame
                             "offset": -c1}        # child part centre relative to the joint
        self.torso_center_y = float(data.get("stance", {}).get("torso_center_y", 3.0))
        ext = data.get("extensions", {})
        self.torso_pivot = np.array(ext.get("torso_pivot", [0, -1, 0]), dtype=np.float64)
        self.head_center_y = self.torso_center_y + self.joint["neck"]["pivot"][1] + self.joint["neck"]["offset"][1]
        self.height = self.head_center_y + self.head_visible[1] / 2.0
        # sanity check: legs must reach the ground when standing
        leg_bottom = (self.torso_center_y + self.joint["right_hip"]["pivot"][1]
                      + self.joint["right_hip"]["offset"][1] - self.part_size["right_leg"][1] / 2.0)
        if abs(leg_bottom) > 1e-6:
            raise SceneError(f"rig '{self.name}': legs end {leg_bottom:+.3f} studs from the ground; check stance.torso_center_y")

    def measure_report(self):
        L = ["rig: %s v%s  (%s)" % (self.name, self.version, self.path),
             "", "parts (studs, w x h x d)"]
        for k in REQUIRED_PARTS:
            s = self.part_size[k]
            extra = ""
            if k == "head":
                v = self.head_visible
                extra = "   visible mesh %.3g x %.3g x %.3g" % v
            L.append("  %-10s %.3g x %.3g x %.3g%s" % (k, s[0], s[1], s[2], extra))
        L += ["", "joints in blockreel axes (pivot in parent frame, child centre relative to pivot)"]
        for k in REQUIRED_JOINTS:
            j = self.joint[k]
            L.append("  %-15s pivot (% .3g, % .3g, % .3g)   child offset (% .3g, % .3g, % .3g)"
                     % (k, *j["pivot"], *j["offset"]))
        L += ["", "standing height to top of head: %.4g studs (head mesh top)" % self.height,
              "torso centre above feet: %.3g studs" % self.torso_center_y]
        return "\n".join(L)

    def fingerprint_data(self):
        return {"name": self.name, "version": self.version, "parts": self.raw["parts"],
                "joints": self.raw["joints"], "stance": self.raw.get("stance"),
                "extensions": self.raw.get("extensions")}


@lru_cache(maxsize=8)
def load_rig(name="r6", search_dir=None):
    dirs = []
    if search_dir:
        dirs.append(Path(search_dir) / "rigs")
    dirs.append(ROOT / "rigs")
    for d in dirs:
        p = d / f"{name}.json"
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                raise SceneError(f"{p}: not valid JSON: {e.msg} (line {e.lineno})")
            return Rig(data, p)
    raise SceneError(f"rig '{name}' not found. Looked in: {', '.join(str(d) for d in dirs)}")
