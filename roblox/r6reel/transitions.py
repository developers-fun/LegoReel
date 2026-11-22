"""r6reel.transitions - data-driven transition library (pure functions of time).

Every factory returns a :class:`Transition`; ``transition.at(t)`` (or calling it) gives a
:class:`TransitionFx` for that frame time:

* ``post``       sparse dict of PostFx field values (only the keys the transition drives):
                 ``blur_dir`` (dx, dy) unit axis, ``blur_amount`` (fraction of frame WIDTH at
                 peak, e.g. 0.07), ``flash`` 0..1 (white), ``fade`` 0..1 (to black), ``chroma``.
* ``cam_offset`` always-complete dict applied on top of the Camera state (neutral values
                 outside the transition): ``fov_scale`` (multiplies fov_y; <1 zooms in),
                 ``yaw`` (deg, +right), ``pitch`` (deg, +up), ``roll`` (deg), ``shake`` (studs).
                 Apply with ``camera.apply_cam_offset(state, cam_offset, t)`` or
                 ``Camera.state(t, offset=cam_offset)``.
* ``meta``       descriptors for the integrator (e.g. dust_cover sprite request).

Use :func:`compose` to merge any number of transitions for a frame.  Whip transitions
expose ``cut_time`` (the blur peak): switch shots there; the yaw sweep is continuous
through the cut (first half sweeps away, second half arrives).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional, Sequence, Union

from .camera import ease as _ease, _Noise  # noqa: F401  (both live in camera.py, same package)


def neutral_cam() -> dict:
    return {"fov_scale": 1.0, "yaw": 0.0, "pitch": 0.0, "roll": 0.0, "shake": 0.0}


@dataclass
class TransitionFx:
    post: dict = field(default_factory=dict)
    cam_offset: dict = field(default_factory=neutral_cam)
    meta: dict = field(default_factory=dict)

    @property
    def is_neutral(self) -> bool:
        return not any(self.post.values()) and self.cam_offset == neutral_cam()


class Transition:
    """A named effect active on [t0, t1]; ``at(t)`` is pure."""

    def __init__(self, name: str, t0: float, t1: float, fn: Callable[[float], TransitionFx],
                 cut_time: Optional[float] = None, meta: Optional[dict] = None):
        self.name, self.t0, self.t1, self.fn = name, float(t0), float(t1), fn
        self.cut_time = cut_time
        self.meta = dict(meta or {})

    def active(self, t: float) -> bool:
        return self.t0 <= t <= self.t1

    def at(self, t: float) -> TransitionFx:
        if not self.active(t):
            return TransitionFx()
        return self.fn(t)

    __call__ = at

    def frames(self, fps: float = 30.0):
        n = int(round((self.t1 - self.t0) * fps))
        return [self.t0 + i / fps for i in range(n + 1)]

    def __repr__(self):
        return f"Transition({self.name!r}, {self.t0:.3f}..{self.t1:.3f}, cut={self.cut_time})"


def _u(t, t0, t1):
    return 0.0 if t1 <= t0 else min(1.0, max(0.0, (t - t0) / (t1 - t0)))


# --------------------------------------------------------------------------- #
# Factories
# --------------------------------------------------------------------------- #


def hard_cut(t: float) -> Transition:
    """A plain cut at t (no fx); exists so a shot list can be uniformly transitions."""
    return Transition("hard_cut", t, t, lambda tt: TransitionFx(), cut_time=t, meta={"t": t})


def whip(t0: float, t1: float, direction: str = "right", degrees: float = 70.0,
         blur: float = 0.07, chroma: float = 0.0) -> Transition:
    """Whip pan/tilt across a cut.  direction in left/right/up/down.

    First half: the camera accelerates (cubic_in) through ``degrees`` while blur ramps up; at the
    midpoint (``cut_time``, blur peak) swap shots; second half: the new shot arrives from the
    opposite side and decelerates (cubic_out) to rest.  Angular speed is continuous at the cut.
    Blur strength is sin(pi*u) of the whole window, i.e. it peaks exactly mid-way."""
    direction = direction.lower()
    if direction not in ("left", "right", "up", "down"):
        raise ValueError("direction must be left/right/up/down")
    sign = {"right": 1.0, "up": 1.0, "left": -1.0, "down": -1.0}[direction]
    horizontal = direction in ("left", "right")
    tm = 0.5 * (t0 + t1)

    def fn(t):
        u = _u(t, t0, t1)
        if t <= tm:
            ang = degrees * _ease("cubic_in", _u(t, t0, tm))
        else:
            ang = -degrees + degrees * _ease("cubic_out", _u(t, tm, t1))
        bell = math.sin(math.pi * u)
        post = {"blur_dir": (1.0, 0.0) if horizontal else (0.0, 1.0), "blur_amount": blur * bell}
        if chroma:
            post["chroma"] = chroma * bell
        cam = neutral_cam()
        cam["yaw" if horizontal else "pitch"] = sign * ang
        return TransitionFx(post, cam, {})

    return Transition("whip", t0, t1, fn, cut_time=tm,
                      meta={"direction": direction, "degrees": degrees})


def zoom_punch(t: float, strength: float = 0.15, dur: float = 0.25) -> Transition:
    """Snap zoom-in: image magnification 1.0 -> 1+strength in ~4 frames, then snaps back.
    ``cam_offset['fov_scale'] = 1/magnification`` (so it dips below 1).  A little chroma rides it."""
    rise = min(4.0 / 30.0, 0.6 * dur)

    def mag(tt):
        loc = tt - t
        if loc <= rise:
            return 1.0 + strength * _ease("cubic_out", loc / rise)
        return 1.0 + strength * (1.0 - _ease("cubic_inout", (loc - rise) / max(1e-9, dur - rise)))

    def fn(tt):
        m = mag(tt)
        cam = neutral_cam()
        cam["fov_scale"] = 1.0 / m
        k = (m - 1.0) / strength if strength else 0.0
        return TransitionFx({"chroma": strength * k}, cam, {})

    return Transition("zoom_punch", t, t + dur, fn, meta={"strength": strength})


def flash(t: float, dur: float = 0.08) -> Transition:
    """White flash: full white for the first ~40 % (1-2 frames at 30 fps), then fades out."""
    hold = 0.4 * dur

    def fn(tt):
        loc = tt - t
        v = 1.0 if loc <= hold else 1.0 - (loc - hold) / max(1e-9, dur - hold)
        return TransitionFx({"flash": max(0.0, min(1.0, v))}, neutral_cam(), {})

    return Transition("flash", t, t + dur, fn, cut_time=t + hold * 0.5)


def fade(t0: float, t1: float, to_black: bool = True, easing: str = "linear") -> Transition:
    """Fade to black (fade 0 -> 1) or from black (fade 1 -> 0)."""
    def fn(t):
        p = _ease(easing, _u(t, t0, t1))
        return TransitionFx({"fade": p if to_black else 1.0 - p}, neutral_cam(), {})

    return Transition("fade", t0, t1, fn, meta={"to_black": to_black})


def shake_hit(t: float, amp: float = 0.5, dur: float = 0.35, flash_amt: float = 0.0) -> Transition:
    """Impact shake: amplitude (studs) jumps to ``amp`` at t and decays to 0 over dur
    (quadratic falloff).  Optional ``flash_amt`` adds a faint white pop on the hit frame."""
    def fn(tt):
        u = _u(tt, t, t + dur)
        env = (1.0 - u) ** 2
        cam = neutral_cam()
        cam["shake"] = amp * env
        post = {"flash": flash_amt * env} if flash_amt else {}
        return TransitionFx(post, cam, {})

    return Transition("shake_hit", t, t + dur, fn, meta={"amp": amp})


def dust_cover(t: float, duration: float = 0.4, size: float = 1.0, color=(0.85, 0.8, 0.7)) -> Transition:
    """Descriptor only: the world/integrator spawns the dust sprite at ``t`` for ``duration``.
    Its opacity peaks at ``cut_time`` (mid-way); that is the moment to cut."""
    meta = {"kind": "dust_cover", "t": t, "duration": duration, "size": size, "color": color}
    tr = Transition("dust_cover", t, t + duration, lambda tt: TransitionFx(meta=dict(meta)),
                    cut_time=t + 0.5 * duration, meta=meta)
    return tr


# --------------------------------------------------------------------------- #
# Speed ramp helper
# --------------------------------------------------------------------------- #


class SpeedRamp:
    """Piecewise-linear playback speed curve; maps output time -> source time.

    ``points`` = [(t, speed), ...] in output time; speed is held before the first / after the
    last point.  ``source_time(t)`` integrates the speed exactly (trapezoids)."""

    def __init__(self, points: Sequence[tuple]):
        pts = sorted((float(a), float(b)) for a, b in points)
        if not pts:
            raise ValueError("speed_ramp needs at least one (t, speed) point")
        self.points = pts

    def speed(self, t: float) -> float:
        p = self.points
        if t <= p[0][0]:
            return p[0][1]
        for (ta, sa), (tb, sb) in zip(p, p[1:]):
            if t <= tb:
                return sa + (sb - sa) * (t - ta) / (tb - ta)
        return p[-1][1]

    def source_time(self, t: float, origin: float = 0.0) -> float:
        """Source time at output time t, with source_time(origin) == origin."""
        def integral(x):
            p = self.points
            total = 0.0
            if x <= p[0][0]:
                return p[0][1] * (x - p[0][0])
            total += 0.0
            for (ta, sa), (tb, sb) in zip(p, p[1:]):
                if x >= tb:
                    total += 0.5 * (sa + sb) * (tb - ta)
                else:
                    if x > ta:
                        sx = self.speed(x)
                        total += 0.5 * (sa + sx) * (x - ta)
                    return total
            return total + p[-1][1] * (x - p[-1][0])
        return origin + integral(t) - integral(origin)

    __call__ = source_time


def speed_ramp(t0: float, t1: float, speed_from: float = 1.0, speed_to: float = 0.25,
               hold_to: Optional[float] = None, back_to: Optional[float] = None,
               easing: str = "cubic_inout", steps: int = 8) -> SpeedRamp:
    """Ramp playback speed from ``speed_from`` (before t0) to ``speed_to`` (reached at t1, eased),
    optionally holding until ``hold_to`` and returning to ``speed_from`` by ``back_to``."""
    pts = [(t0, speed_from)]
    for i in range(1, steps + 1):
        u = i / steps
        pts.append((t0 + (t1 - t0) * u, speed_from + (speed_to - speed_from) * _ease(easing, u)))
    if hold_to is not None and hold_to > t1:
        pts.append((hold_to, speed_to))
    if back_to is not None:
        start = hold_to if hold_to is not None and hold_to > t1 else t1
        for i in range(1, steps + 1):
            u = i / steps
            pts.append((start + (back_to - start) * u, speed_to + (speed_from - speed_to) * _ease(easing, u)))
    return SpeedRamp(pts)


# --------------------------------------------------------------------------- #
# Compose
# --------------------------------------------------------------------------- #


def compose(fx_list: Iterable[Union[Transition, TransitionFx]], t: float) -> TransitionFx:
    """Merge transitions/fx for frame time t.  Rules: blur_amount/flash/fade/chroma take the max
    (blur_dir follows the strongest blur); fov_scale multiplies; yaw/pitch/roll add; shake takes
    the max; other post keys: last wins.  meta lists are collected under 'items'."""
    post: dict = {}
    cam = neutral_cam()
    best_blur = -1.0
    metas = []
    for item in fx_list:
        fx = item.at(t) if isinstance(item, Transition) else item
        for k, v in fx.post.items():
            if k == "blur_dir":
                continue
            if k == "blur_amount":
                post[k] = max(post.get(k, 0.0), v)
                if v > best_blur and "blur_dir" in fx.post:
                    best_blur = v
                    post["blur_dir"] = fx.post["blur_dir"]
            elif k in ("flash", "fade", "chroma"):
                post[k] = max(post.get(k, 0.0), v)
            else:
                post[k] = v
        if "blur_dir" in fx.post and "blur_dir" not in post:
            post["blur_dir"] = fx.post["blur_dir"]
        c = fx.cam_offset
        cam["fov_scale"] *= c.get("fov_scale", 1.0)
        for k in ("yaw", "pitch", "roll"):
            cam[k] += c.get(k, 0.0)
        cam["shake"] = max(cam["shake"], c.get("shake", 0.0))
        if fx.meta:
            metas.append(fx.meta)
    return TransitionFx(post, cam, {"items": metas} if metas else {})
