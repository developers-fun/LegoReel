"""Character: a timeline of where it is and what it is doing, plus the box geometry.

Part sizes and joint offsets come from the rig file (rigs/r6.json), not from numbers in this
module: change the rig and every character changes with it. The meshes are generated in code.
"""
from __future__ import annotations

import math
from collections import namedtuple

import numpy as np

from . import poses
from .errors import SceneError
from .mathutil import (clamp, lerp_angle, mat_mul, rot_x, rot_y, rot_z, scale_m,
                       smoothstep, translate, vec3, wrap_angle)

# Bump when the code that builds the figure (face, hair, clothes geometry) changes, so the fingerprint changes too.
FIGURE_VERSION = 2

Item = namedtuple("Item", "model size color shape bevel casts extra", defaults=("box", None, True, None))
# extra: None or a dict: top/bottom (taper ratios), subdiv, spec (plastic highlight), file/scale (obj), image (decal PNG), arc.
# model: 4x4, size: (w, h, d), color: (r, g, b), shape: box | head | cylinder,
# bevel: studs or None for the scene default, casts: whether it throws a ground shadow

POSE_BLEND = 0.2     # seconds to blend between poses
LOOK_BLEND = 0.25    # seconds to blend head-look targets
HEAD_HEIGHT = 4.5    # studs above the feet (head centre of the R6 rig), used as the head look-at point


class _Seg:
    __slots__ = ("t0", "t1", "p0", "p1")

    def __init__(self, t0, t1, p0, p1):
        self.t0, self.t1, self.p0, self.p1 = t0, t1, p0, p1


class Timeline:
    """Everything a character does, in global seconds."""

    def __init__(self, cid, start_pos, start_yaw, scale):
        self.cid = cid
        self.scale = scale
        self.start_pos = np.array(start_pos, dtype=np.float64)
        self.segs = []
        # (t, yaw_deg or None, turn_seconds, spec); spec is ("toward", id) / ("look_at", [x, z]) / None
        self.yaw_keys = [(-1e9, float(start_yaw), 0.0, None)]
        self.pose_keys = [(0.0, "idle", {})]
        self.look_keys = [(-1e9, None)]
        self.expr_keys = [(-1e9, None)]

    # ---- building ---------------------------------------------------------

    def add_pose(self, t, name, params):
        if name not in poses.CLIPS:
            raise SceneError(f"character '{self.cid}': unknown pose '{name}'. Options: {', '.join(poses.CLIPS)}")
        self.pose_keys.append((t, name, params))

    def add_teleport(self, t, pos):
        self._truncate_at(t)
        self.segs.append(_Seg(t, t, np.array(pos, dtype=np.float64), np.array(pos, dtype=np.float64)))

    def add_move(self, t, target, speed, duration, face, pose, then_pose):
        p0 = self.pos_at(t)
        if len(target) == 3:
            p1 = np.array(target, dtype=np.float64)
        else:
            p1 = np.array([target[0], p0[1], target[1]], dtype=np.float64)
        dist = float(np.linalg.norm(p1 - p0))
        if duration is None:
            duration = dist / speed if speed and speed > 0 else 1.0
        if speed is None or speed <= 0:
            speed = dist / duration if duration > 0 else 1.0
        duration = max(duration, 1e-3)
        self._truncate_at(t)
        self.segs.append(_Seg(t, t + duration, p0, p1))
        if face and dist > 1e-6:
            yaw = math.degrees(math.atan2(p1[0] - p0[0], p1[2] - p0[2]))
            self.yaw_keys.append((t, yaw, 0.15, None))
        self.add_pose(t, pose, {"speed": speed})
        self.add_pose(t + duration, then_pose, {})
        return t + duration

    def _truncate_at(self, t):
        if self.segs and self.segs[-1].t1 > t:
            last = self.segs[-1]
            cut = self.pos_at(t)
            last.t1 = max(t, last.t0)
            last.p1 = cut

    def add_face(self, t, yaw, spec, turn):
        self.yaw_keys.append((t, yaw, turn, spec))

    def add_look(self, t, target):
        self.look_keys.append((t, target))

    def add_expression(self, t, name):
        self.expr_keys.append((t, name))

    def expression_at(self, T):
        cur = None
        for k in self.expr_keys:
            if k[0] <= T:
                cur = k[1]
        return cur

    def finalize(self):
        # stable sort keeps declaration order for equal times (later actions win)
        self.pose_keys.sort(key=lambda k: k[0])
        self.yaw_keys.sort(key=lambda k: k[0])
        self.look_keys.sort(key=lambda k: k[0])
        self.expr_keys.sort(key=lambda k: k[0])

    # ---- evaluation -------------------------------------------------------

    def pos_at(self, T):
        pos = self.start_pos
        for s in self.segs:
            if T >= s.t1:
                pos = s.p1
                continue
            if T >= s.t0:
                u = (T - s.t0) / (s.t1 - s.t0) if s.t1 > s.t0 else 1.0
                return s.p0 + (s.p1 - s.p0) * u
            break
        return pos.copy()

    def _yaw_of(self, key, scene):
        t, yaw, _turn, spec = key
        if spec is None:
            return yaw
        mine = self.pos_at(max(t, 0.0))
        if spec[0] == "toward":
            other = scene.timelines[spec[1]].pos_at(max(t, 0.0))
            dx, dz = other[0] - mine[0], other[2] - mine[2]
        else:
            dx, dz = spec[1][0] - mine[0], spec[1][1] - mine[2]
        if abs(dx) < 1e-9 and abs(dz) < 1e-9:
            return 0.0
        return math.degrees(math.atan2(dx, dz))

    def yaw_at(self, T, scene):
        idx = 0
        for i, k in enumerate(self.yaw_keys):
            if k[0] <= T:
                idx = i
            else:
                break
        cur = self._yaw_of(self.yaw_keys[idx], scene)
        if idx == 0:
            return cur
        prev = self._yaw_of(self.yaw_keys[idx - 1], scene)
        t, _y, turn, _s = self.yaw_keys[idx]
        u = 1.0 if turn <= 0 else smoothstep((T - t) / turn)
        return lerp_angle(prev, cur, u)

    def _pose_key_eval(self, idx, T):
        t0, name, params = self.pose_keys[idx]
        return poses.evaluate(name, T - t0, params)

    def pose_at(self, T, cam_pos, scene, pos, yaw):
        idx = 0
        for i, k in enumerate(self.pose_keys):
            if k[0] <= T:
                idx = i
            else:
                break
        pose = self._pose_key_eval(idx, T)
        t0 = self.pose_keys[idx][0]
        if idx > 0 and T - t0 < POSE_BLEND and not self.pose_keys[idx][2].get("snap"):
            prev = self._pose_key_eval(idx - 1, T)
            pose = poses.lerp_pose(prev, pose, smoothstep((T - t0) / POSE_BLEND))

        # head look
        li = 0
        for i, k in enumerate(self.look_keys):
            if k[0] <= T:
                li = i
            else:
                break
        cur = self._look_angles(self.look_keys[li][1], T, cam_pos, scene, pos, yaw)
        if li > 0:
            prev = self._look_angles(self.look_keys[li - 1][1], T, cam_pos, scene, pos, yaw)
            u = smoothstep((T - self.look_keys[li][0]) / LOOK_BLEND)
            cur = (prev[0] + (cur[0] - prev[0]) * u, prev[1] + (cur[1] - prev[1]) * u)
        pose["head_yaw"] += cur[0]
        pose["head_pitch"] += cur[1]
        return pose

    def _look_angles(self, target, T, cam_pos, scene, pos, yaw):
        if target is None:
            return (0.0, 0.0)
        if target == "camera":
            p = cam_pos
        elif isinstance(target, str):
            other = scene.timelines[target]
            p = other.pos_at(T) + np.array([0.0, HEAD_HEIGHT * other.scale, 0.0])
        else:
            p = np.array(target, dtype=np.float64)
        head = pos + np.array([0.0, HEAD_HEIGHT * self.scale, 0.0])
        d = p - head
        flat = math.hypot(d[0], d[2])
        if flat < 1e-6 and abs(d[1]) < 1e-6:
            return (0.0, 0.0)
        world_yaw = math.degrees(math.atan2(d[0], d[2]))
        rel = clamp(wrap_angle(world_yaw - yaw), -75.0, 75.0)
        elev = math.degrees(math.atan2(d[1], max(flat, 1e-6)))
        return (rel, clamp(-elev, -35.0, 35.0))


# ---- geometry --------------------------------------------------------------

def build_items(app, rig, pos, yaw, pose, scale):
    """Return a list of Items for one character at one instant, posed on `rig`."""
    items = []
    I = np.eye(4)
    root = mat_mul(translate(pos[0], pos[1] + pose["root_y"] * scale, pos[2]), rot_y(yaw), scale_m(scale))

    def add(parent, pivot, rot, offset, size, color, shape="box", bevel=None):
        m = mat_mul(parent, translate(*pivot), rot, translate(*offset))
        items.append(Item(m, (float(size[0]), float(size[1]), float(size[2])), color, shape, bevel))

    J = rig.joint
    P = rig.part_size
    skin = app["skin"]
    o = app["outfit"]
    shirt, pants, shoes = o["shirt"], o["pants"], o["shoes"]

    hips = mat_mul(root, translate(0, rig.torso_center_y, 0))       # torso frame before any lean
    tp = rig.torso_pivot
    torso = mat_mul(hips, translate(*tp), rot_y(pose["torso_yaw"]), rot_x(pose["torso_pitch"]), translate(*(-tp)))

    # legs: hung from the hip joints, which sit on the unleaned torso frame
    ls = P["right_leg"]
    for key, side in (("r_leg_pitch", "right_hip"), ("l_leg_pitch", "left_hip")):
        j = J[side]
        rot = rot_x(-pose[key])
        base = skin if o["shorts"] else pants
        add(hips, j["pivot"], rot, j["offset"], ls, base)
        if o["shorts"]:
            add(hips, j["pivot"], rot, j["offset"] + np.array([0.0, ls[1] / 2 - 0.5 + 0.01, 0.0]),
                (ls[0] + 0.04, 1.0, ls[2] + 0.04), pants)
        add(hips, j["pivot"], rot, j["offset"] + np.array([0.0, -ls[1] / 2 + 0.225 - 0.01, 0.12]),
            (ls[0] + 0.06, 0.45, ls[2] + 0.3), shoes)

    # torso
    ts = P["torso"]
    add(torso, (0, 0, 0), I, (0, 0, 0), ts, shirt)
    if o["stripe"]:
        st = o["stripe"]
        add(torso, (0, 0, 0), I, (0, -ts[1] / 2 + st["y"], 0), (ts[0] + 0.04, st["height"], ts[2] + 0.04), st["color"])
    if o["chest_patch"]:
        cp = o["chest_patch"]
        add(torso, (0, 0, 0), I, (0, 0.3, ts[2] / 2 + 0.005), (cp["size"], cp["size"], 0.03), cp["color"], bevel=0.0)

    # arms: pivot at the shoulder joint, 0.5 below the top of the arm
    sleeve_len = {"none": 0.0, "short": 1.0, "long": 1.7}[o["sleeves"]]
    for key, rk, side, sign in (("r_arm_pitch", "r_arm_roll", "right_shoulder", -1),
                                ("l_arm_pitch", "l_arm_roll", "left_shoulder", 1)):
        j = J[side]
        a = P["right_arm"]
        # roll is "outward positive": the right arm sits at -x, so its roll is negated
        rot = mat_mul(rot_z(sign * pose[rk]), rot_x(-pose[key]))
        add(torso, j["pivot"], rot, j["offset"], a, skin)
        if sleeve_len > 0:
            add(torso, j["pivot"], rot, j["offset"] + np.array([0.0, a[1] / 2 + 0.02 - sleeve_len / 2, 0.0]),
                (a[0] + 0.04, sleeve_len, a[2] + 0.04), shirt)

    # head: the visible mesh is the rig's head-mesh size, centred on the head part
    hv = rig.head_visible
    nj = J["neck"]
    head = mat_mul(torso, translate(*nj["pivot"]), rot_y(pose["head_yaw"]), rot_x(pose["head_pitch"]),
                   translate(*nj["offset"]))
    add(head, (0, 0, 0), I, (0, 0, 0), hv, skin, shape="head")
    _face(add, head, app, hv)
    _hair(add, head, app, hv)
    for acc in app["accessories"]:
        _accessory(add, head, torso, acc, hv, ts)
    return items


def _face(add, head, app, hv):
    f = app["face"]
    I = np.eye(4)
    w, h, d = hv
    fz = d / 2.0                 # decals are 0.06 deep, centred on the face plane so they sit inlaid
    ec = f["eye_color"]

    def feat(x, y, fw, fh, color, dz=0.0):
        add(head, (0, 0, 0), I, (x * w, y * h, fz + dz), (fw * w, fh * h, 0.06), color, bevel=0.0)

    def disc(x, y, diam, color, dz=0.0):
        """Round decal: a thin cylinder turned to face forward. x, y in head widths/heights, diam in studs."""
        add(head, (0, 0, 0), rot_x(90), (x * w, y * h, fz + dz), (diam, 0.06, diam), color, shape="cylinder", bevel=0.0)

    for sx in (-1, 1):
        x = 0.22 * sx
        if f["eyes"] == "dots":
            blush = tuple(int(c * 0.62 + b * 0.38) for c, b in zip(app["skin"], (238, 122, 120)))
            disc(0.36 * sx, -0.13, 0.24, blush, -0.012)
            disc(x, 0.07, 0.235, ec)
            disc(x + 0.045 * sx, 0.15, 0.085, (255, 255, 255), 0.015)
        elif f["eyes"] == "wide":
            feat(x, 0.08, 0.14, 0.34, (245, 245, 245))
            feat(x, 0.06, 0.07, 0.2, ec, 0.015)
            feat(x + 0.012 * sx, 0.12, 0.03, 0.06, (255, 255, 255), 0.03)
        elif f["eyes"] == "closed":
            feat(x, 0.05, 0.14, 0.05, ec)
        elif f["eyes"] == "happy":
            feat(x - 0.05 * sx, 0.04, 0.05, 0.06, ec)
            feat(x, 0.10, 0.05, 0.06, ec)
            feat(x + 0.05 * sx, 0.04, 0.05, 0.06, ec)

    m = f["mouth"]
    mc = f["mouth_color"]
    if m == "smile":
        for k in range(9):                                   # a curved smile: a row of overlapping dots
            t = (k - 4) / 4.0
            disc(t * 0.21, -0.36 + 0.13 * t * t, 0.085, mc)
    elif m == "flat":
        feat(0.0, -0.28, 0.22, 0.07, mc)
    elif m == "open":
        feat(0.0, -0.28, 0.2, 0.22, mc)
    elif m == "smirk":
        feat(0.0, -0.28, 0.22, 0.07, mc)
        feat(0.13, -0.23, 0.05, 0.07, mc)
    elif m == "frown":
        feat(0.0, -0.26, 0.22, 0.07, mc)
        feat(-0.13, -0.32, 0.05, 0.07, mc)
        feat(0.13, -0.32, 0.05, 0.07, mc)
    elif m == "o":
        feat(0.0, -0.28, 0.1, 0.2, mc)

    if f["brows"] != "none":
        y = 0.29 if f["brows"] == "flat" else 0.34
        for sx in (-1, 1):
            feat(0.22 * sx, y, 0.15, 0.035, f["brow_color"])


def _hair(add, head, app, hv):
    hr = app["hair"]
    style, c = hr["style"], hr["color"]
    if style == "none":
        return
    I = np.eye(4)
    w, h, d = hv
    top = h / 2.0

    def box(x, y, z, sx, sy, sz, shape="box"):
        add(head, (0, 0, 0), I, (x, y, z), (sx, sy, sz), c, shape=shape)

    if style != "mohawk":
        box(0, top + 0.04, 0, w + 0.08, 0.32, d + 0.08, "head")          # cap of hair
        if style in ("flat", "spiky", "bob", "long"):                    # sideburns and a back piece, so it reads as hair
            for sx in (-1, 1):
                box(sx * (w / 2 + 0.01), top - 0.38, -0.12, 0.1, 0.62, d * 0.7)
            box(0, top - 0.3, -(d / 2 + 0.02), w * 0.98, 0.7, 0.1)
        if hr["fringe"] and style in ("flat", "bob", "long", "spiky"):
            box(0, top - 0.13, d / 2 - 0.01, w + 0.02, 0.2, 0.13)
    if style == "spiky":
        heights = (0.45, 0.7, 0.55, 0.75, 0.45)
        for i, hh in enumerate(heights):
            x = (-0.4 + 0.2 * i) * w
            box(x, top + 0.2 + hh / 2, 0, w * 0.18, hh, d * 0.5)
    elif style == "mohawk":
        box(0, top + 0.28, 0, 0.22, 0.62, d + 0.06)
    elif style in ("long", "bob"):
        drop = 1.2 if style == "long" else 0.35
        t_y, b_y = top + 0.1, -h / 2 - drop
        box(0, (t_y + b_y) / 2, -(d / 2 + 0.1), w + 0.1, t_y - b_y, 0.3)
        for sx in (-1, 1):
            side_b = -h / 2 - (drop - 0.7 if style == "long" else 0.15)
            box(sx * (w / 2 + 0.05), (t_y + side_b) / 2, -0.05, 0.22, t_y - side_b, d * 0.9)


def _accessory(add, head, torso, acc, hv, ts):
    I = np.eye(4)
    c = acc["color"]
    t = acc["type"]
    w, h, d = hv
    top = h / 2.0
    if t == "cap":
        add(head, (0, 0, 0), I, (0, top + 0.1, 0), (w + 0.1, 0.46, d + 0.1), c, shape="head")
        add(head, (0, 0, 0), I, (0, top - 0.1, d / 2 + 0.3), (w * 0.75, 0.07, 0.6), c)
    elif t == "backpack":
        add(torso, (0, 0, 0), I, (0, 0.1, -(ts[2] / 2 + 0.3)), (1.4, 1.6, 0.6), c)
    elif t == "scarf":
        add(torso, (0, 0, 0), I, (0, ts[1] / 2 - 0.2, 0), (ts[0] + 0.15, 0.4, ts[2] + 0.15), c)
    elif t == "cape":
        add(torso, (0, 0, 0), I, (0, -0.2, -(ts[2] / 2 + 0.06)), (ts[0] - 0.1, 2.4, 0.12), c)
