"""Shots, transitions and the shot timeline.

A :class:`Shot` is a time window [t0, t1] with a camera description.  The camera is built lazily from the
description by :func:`build_camera` (using camera.shot presets, or hand-made framing for inserts / two shots)
and every shot owns its own :class:`r6reel.camera.Camera`, so moves never leak between shots.

The ``transition`` of a shot describes how the cut INTO that shot is hidden.  All windows are centred on the
cut (``shot.t0``), so the shot lengths never change:

  cut (default) | whip{dur,direction,degrees,blur} | dust_cover{dur,size} | zoom_punch{strength,dur} |
  flash{dur} | fade_in{dur} | fade_out{dur} | shake_hit{amp,dur} | sweep{dur,color,direction}

``transition`` may also be a list (e.g. zoom_punch + flash).
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field, fields, asdict
from typing import Any, Optional

import numpy as np

from . import camera as C
from . import transitions as T
from .presets import SIZE_CLASS

TRANSITION_TYPES = ("cut", "whip", "dust_cover", "zoom_punch", "flash", "fade_in", "fade_out", "shake_hit", "sweep")
MOVE_TYPES = ("push_in", "pull_out", "drift", "dutch", "orbit", "shake", "crane", "low_angle", "whip_pan",
              "dolly_zoom", "look_at", "follow")
SHOT_KINDS = tuple(C.PRESETS) + ("insert",)
FOCI = ("head", "torso", "feet", "hands", "full")


@dataclass
class Shot:
    t0: float
    t1: float
    kind: str = "medium"
    set: Optional[str] = None
    subject: Any = None            # character name | "prop:<name>" | [x,y,z]
    other: Optional[str] = None    # second character (over_shoulder / two_shot)
    follow: bool = False           # camera trails the subject (delta mode)
    damping: float = 0.3
    azimuth: Optional[float] = None    # degrees from the subject's front (+ = subject's left)
    elevation: Optional[float] = None  # degrees above (+) / below (-) the framed point
    fill: Optional[float] = None
    fov: Optional[float] = None
    screen_y: Optional[float] = None   # 0 top .. 1 bottom: where the framed region centre lands
    facing: Optional[float] = None     # override the subject's facing used for the preset
    distance: Optional[float] = None   # insert shots
    focus: Optional[str] = None        # insert: head|torso|feet|hands|full
    moves: list = field(default_factory=list)
    camera: Optional[dict] = None      # manual camera {position, target, fov, roll}
    lighting: Any = None               # preset name or dict override for this shot
    post: Optional[dict] = None        # PostFx field overrides for this shot
    transition: Any = None             # see module docstring
    motion_blur: Optional[bool] = None
    label: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        defaults = Shot(0, 0)
        out = {"t0": round(self.t0, 4), "t1": round(self.t1, 4)}
        for f in fields(self):
            if f.name in ("t0", "t1"):
                continue
            v = d[f.name]
            if v != getattr(defaults, f.name) and not (f.name == "kind" and v == "medium" and False):
                out[f.name] = v
        out.setdefault("kind", self.kind)
        return out

    @classmethod
    def from_dict(cls, d: dict) -> "Shot":
        names = {f.name for f in fields(cls)}
        bad = set(d) - names
        if bad:
            raise ValueError(f"unknown shot keys {sorted(bad)}; valid: {sorted(names)}")
        return cls(**d)

    @property
    def duration(self):
        return self.t1 - self.t0


# ---------------------------------------------------------------------------------------- transitions
def _as_list(tr):
    if tr is None:
        return []
    if isinstance(tr, str):
        return [{"type": tr}]
    if isinstance(tr, dict):
        return [tr]
    return list(tr)


def make_transitions(spec, cut_t: float, seed=0):
    """-> (list[Transition], list[fx spec dicts]) for the transition INTO a shot that starts at cut_t."""
    trs, fxs = [], []
    for s in _as_list(spec):
        ty = s.get("type", "cut")
        if ty == "cut":
            continue
        if ty == "whip":
            d = float(s.get("dur", 0.17))
            trs.append(T.whip(cut_t - d / 2, cut_t + d / 2, s.get("direction", "right"),
                              float(s.get("degrees", 70.0)), float(s.get("blur", 0.09)), float(s.get("chroma", 0.0))))
        elif ty == "dust_cover":
            d = float(s.get("dur", 0.42))
            trs.append(T.dust_cover(cut_t - d / 2, d, float(s.get("size", 1.0))))
            fxs.append({"type": "dust_cover", "t": cut_t - d / 2, "duration": d, "size": float(s.get("size", 1.0)),
                        "seed": seed})
        elif ty == "zoom_punch":
            trs.append(T.zoom_punch(cut_t, float(s.get("strength", 0.15)), float(s.get("dur", 0.25))))
        elif ty == "flash":
            d = float(s.get("dur", 0.1))
            trs.append(T.flash(cut_t - 0.2 * d, d))
        elif ty == "fade_in":
            d = float(s.get("dur", 0.4))
            trs.append(T.fade(cut_t, cut_t + d, to_black=False))
        elif ty == "fade_out":
            d = float(s.get("dur", 0.4))
            trs.append(T.fade(cut_t - d, cut_t, to_black=True))
        elif ty == "shake_hit":
            trs.append(T.shake_hit(cut_t, float(s.get("amp", 0.5)), float(s.get("dur", 0.35)),
                                   float(s.get("flash", 0.0))))
        elif ty == "sweep":
            d = float(s.get("dur", 0.26))
            fxs.append({"type": "sweep", "t": cut_t - d / 2, "duration": d, "color": s.get("color", (0.12, 0.12, 0.16)),
                        "direction": float(s.get("direction", 1.0))})
        else:
            raise ValueError(f"unknown transition {ty!r}; known: {TRANSITION_TYPES}")
    return trs, fxs


# ---------------------------------------------------------------------------------------- camera build
def _unit(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


def build_camera(shot: Shot, ctx) -> "C.Camera":
    """Create the Camera for a shot. `ctx` provides: aspect, cam_side(set), char_pos(name,t), char_facing(name,t),
    char_height(name), prop_pos(name,t), resolver(name,t), first_char(set)."""
    t0, t1 = shot.t0, shot.t1
    if shot.camera:                                  # manual
        c = shot.camera
        cam = C.Camera(c.get("position", (0, 5, -10)), c.get("target", (0, 3, 0)), fov=c.get("fov", 70.0),
                       roll=c.get("roll", 0.0), resolver=ctx.resolver)
        return _apply_moves(cam, shot, ctx)

    subj = shot.subject if shot.subject is not None else ctx.first_char(shot.set)
    t_ref = t0 if shot.follow else t0 + 0.3 * (t1 - t0)
    if isinstance(subj, str) and subj.startswith("prop:"):
        pos = np.asarray(ctx.prop_pos(subj[5:], t_ref), float)
        H, facing, is_char = 2.0, shot.facing or 0.0, False
    elif isinstance(subj, str):
        pos = np.asarray(ctx.char_pos(subj, t_ref), float)
        H = ctx.char_height(subj)
        facing = shot.facing if shot.facing is not None else ctx.char_facing(subj, t_ref)
        is_char = True
    else:
        pos = np.asarray(subj, float)
        H, facing, is_char = 2.0, shot.facing or 0.0, False

    kind = shot.kind
    side = ctx.cam_side(shot.set)
    az = shot.azimuth
    el = shot.elevation
    if kind == "insert":
        cam = _insert_camera(shot, ctx, pos, H, facing, is_char, side)
    elif kind == "two_shot":
        cam = _two_shot_camera(shot, ctx, pos, side, t_ref)
    else:
        if kind not in C.PRESETS:
            raise ValueError(f"unknown shot kind {kind!r}; choose from {SHOT_KINDS}")
        other = None
        if kind in ("over_shoulder",) and shot.other:
            other = ctx.char_pos(shot.other, t_ref)
        kw = {}
        if shot.fill is not None:
            kw["fill"] = shot.fill
        if shot.fov is not None:
            kw["fov"] = shot.fov
        if shot.screen_y is not None:
            kw["screen_y"] = shot.screen_y
        cam = C.shot(kind, pos, H, facing, azimuth_deg=az, elevation_deg=el, other_pos=other,
                     aspect=ctx.aspect, resolver=ctx.resolver, **kw)
    return _apply_moves(cam, shot, ctx)


def _insert_camera(shot, ctx, pos, H, facing, is_char, side):
    focus = shot.focus or ("hands" if is_char else "full")
    dist = float(shot.distance or 3.4)
    if is_char:
        up = {"head": 4.4, "torso": 3.0, "feet": 0.5, "hands": 2.4, "full": 2.5}[focus] * (H / 5.0)
        fwd = np.array([-math.sin(math.radians(facing)), 0, -math.cos(math.radians(facing))])
        T_ = pos + np.array([0, up, 0]) + (fwd * 0.9 if focus == "hands" else 0)
        base_az = facing
    else:
        T_ = pos + np.array([0, 1.0, 0])
        base_az = 0.0 if side < 0 else 180.0
    az = base_az + float(shot.azimuth if shot.azimuth is not None else 25.0)
    el = float(shot.elevation if shot.elevation is not None else (-12.0 if focus == "feet" else -6.0))
    front = np.array([-math.sin(math.radians(az)), 0, -math.cos(math.radians(az))])
    eye = T_ + dist * (math.cos(math.radians(el)) * front + math.sin(math.radians(el)) * np.array([0, 1, 0]))
    eye[1] = max(eye[1], 0.35)
    cam = C.Camera(eye, T_, fov=float(shot.fov or 72.0), resolver=ctx.resolver)
    cam.info = {"kind": "insert", "distance": dist}
    return cam


def _two_shot_camera(shot, ctx, posA, side, t_ref):
    posB = np.asarray(ctx.char_pos(shot.other, t_ref), float) if shot.other else posA + np.array([3.5, 0, 0])
    mid = (posA + posB) / 2.0
    ab = (posB - posA) * np.array([1, 0, 1])
    sep = float(np.linalg.norm(ab))
    u = _unit(ab) if sep > 1e-6 else np.array([1.0, 0, 0])
    perp = np.array([u[2], 0.0, -u[0]])
    if perp[2] * side < 0:
        perp = -perp
    fov = float(shot.fov or 66.0)
    th = math.tan(math.radians(fov) / 2)
    fill = float(shot.fill or 0.40)
    el = float(shot.elevation if shot.elevation is not None else 6.0)
    d_h = 5.0 / (2 * fill * th)
    d_w = (sep + 3.0) / (0.9 * 2 * th * ctx.aspect)
    d = max(d_h, d_w) + 1.0
    az = float(shot.azimuth or 0.0)
    ca, sa = math.cos(math.radians(az)), math.sin(math.radians(az))
    perp = np.array([perp[0] * ca + perp[2] * sa, 0, -perp[0] * sa + perp[2] * ca])
    centre = mid + np.array([0, 2.6, 0])
    eye = centre + d * (math.cos(math.radians(el)) * perp + math.sin(math.radians(el)) * np.array([0, 1, 0]))
    tgt = centre
    if shot.screen_y is not None:
        tgt = tgt + np.array([0, -(0.5 - shot.screen_y) * 2 * d * th * -1.0, 0]) * 0
    cam = C.Camera(eye, tgt, fov=fov, resolver=ctx.resolver)
    cam.info = {"kind": "two_shot", "distance": d}
    return cam


def _apply_moves(cam, shot: Shot, ctx):
    t0, t1 = shot.t0, shot.t1
    cam.bind(ctx.resolver)
    subj = shot.subject if shot.subject is not None else ctx.first_char(shot.set)
    if shot.follow and isinstance(subj, str) and not subj.startswith("prop:"):
        cam.follow(subj, t0=t0, t1=None, damping=shot.damping)
    for m in shot.moves:
        ty = m.get("type")
        a = t0 + float(m.get("at", 0.0))
        b = a + float(m["dur"]) if m.get("dur") is not None else t1
        ease = m.get("ease", "cubic_inout")
        if ty == "push_in":
            if m.get("amount") is not None:
                cam.push_in(a, b, amount=float(m["amount"]), ease=ease)
            else:
                cam.push_in(a, b, rate=float(m.get("rate", 0.06)))
        elif ty == "pull_out":
            if m.get("amount") is not None:
                cam.pull_out(a, b, amount=float(m["amount"]), ease=ease)
            else:
                cam.pull_out(a, b, rate=float(m.get("rate", 0.06)))
        elif ty == "drift":
            cam.drift(a, b, amount=float(m.get("amount", 0.25)), freq=float(m.get("freq", 0.25)),
                      seed=int(m.get("seed", 1)))
        elif ty == "dutch":
            cam.dutch(a, a + float(m.get("ramp", min(0.5, b - a))), degrees=float(m.get("degrees", 4.0)), ease=ease)
        elif ty == "orbit":
            cam.orbit(a, b, degrees=float(m.get("degrees", 30.0)), around=m.get("around"), ease=ease)
        elif ty == "shake":
            cam.shake(a, b, amp=float(m.get("amp", 0.2)), freq=float(m.get("freq", 9.0)),
                      decay=float(m.get("decay", 0.0)), seed=int(m.get("seed", 2)))
        elif ty == "crane":
            cam.crane(a, b, dy=float(m.get("dy", 4.0)), ease=ease)
        elif ty == "low_angle":
            cam.low_angle(a, b, height=float(m.get("height", 0.8)), ease=ease)
        elif ty == "whip_pan":
            cam.whip_pan(a, b, degrees=float(m.get("degrees", 60.0)), pitch=float(m.get("pitch", 0.0)), ease=ease)
        elif ty == "dolly_zoom":
            cam.dolly_zoom(a, b, fov_to=float(m.get("fov_to", 100.0)), ease=ease)
        elif ty == "look_at":
            cam.look_at(m["target"], a, b)
        elif ty == "follow":
            cam.follow(m["target"], a, b, damping=float(m.get("damping", 0.3)))
        else:
            raise ValueError(f"unknown camera move {ty!r}; known: {MOVE_TYPES}")
    return cam


# ---------------------------------------------------------------------------------------- timeline
class Timeline:
    """Sorted shots + transitions. Pure lookups: shot_index(t), transitions_at(t)."""

    def __init__(self, shots, seed=0):
        self.shots = sorted(shots, key=lambda s: s.t0)
        self.starts = [s.t0 for s in self.shots]
        self.transitions: list = []           # (Transition, shot_index)
        self.fx_specs: list = []
        self.cameras: list = []
        for i, s in enumerate(self.shots):
            trs, fxs = make_transitions(s.transition, s.t0, seed=(seed, i))
            self.transitions += [(tr, i) for tr in trs]
            self.fx_specs += fxs

    def build_cameras(self, ctx):
        self.cameras = [build_camera(s, ctx) for s in self.shots]

    def shot_index(self, t: float) -> int:
        i = bisect.bisect_right(self.starts, t + 1e-9) - 1
        return max(0, i)

    def transitions_at(self, t: float):
        return [tr for tr, _ in self.transitions if tr.t0 - 1e-9 <= t <= tr.t1 + 1e-9]

    def in_whip(self, t: float) -> bool:
        return any(tr.name == "whip" and tr.t0 <= t <= tr.t1 for tr, _ in self.transitions)

    def end(self) -> float:
        return max((s.t1 for s in self.shots), default=0.0)
