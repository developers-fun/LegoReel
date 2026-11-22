"""Clip library: snappy Roblox-storytime animation. clips.get(name) / clips.names().

Authoring DSL: P(...) builds a pose. Sign cheat sheet (right limbs; mirror = (rx,-ry,-rz)):
  arm rx>0 forward/up, rz>0 outward; hip rx>0 leg forward; neck rx>0 up, ry>0 look left;
  bend=deg folds the torso forward at the hips (legs stay vertical); rot=(rx..) rotates the whole body.
Key easing = how the segment INTO that key moves: back_out gives the quick-overshoot snap,
cubic_out fast-then-settle, linear for loops.
"""
from __future__ import annotations
import math
from .anim import Clip
from . import rig

S = math.sin
C = math.cos
TAU = 2 * math.pi


def M(v):
    return (v[0], -v[1], -v[2])


def P(dy=0.0, dx=0.0, dz=0.0, rot=(0, 0, 0), bend=0.0, neck=(0, 0, 0), arms=None, rs=None, ls=None,
      legs=None, rh=None, lh=None, ground=False):
    z = (0.0, 0.0, 0.0)
    rs = rs if rs is not None else (arms if arms is not None else z)
    ls = ls if ls is not None else (M(arms) if arms is not None else z)
    rh = rh if rh is not None else (legs if legs is not None else z)
    lh = lh if lh is not None else (M(legs) if legs is not None else z)
    b = math.radians(bend)
    rot = (rot[0] - bend, rot[1], rot[2])
    dy += C(b) - 1.0; dz += -S(b)
    rh = (rh[0] + bend, rh[1], rh[2]); lh = (lh[0] + bend, lh[1], lh[2])
    pose = {"root": {"pos": (dx, dy, dz), "rot": tuple(rot)}, "Neck": tuple(neck),
            "Right Shoulder": tuple(rs), "Left Shoulder": tuple(ls),
            "Right Hip": tuple(rh), "Left Hip": tuple(lh)}
    if ground:
        pose["root"]["pos"] = (dx, dy - rig.lowest_y(pose), dz)
    return pose


def K(t, e="cubic_out", **kw):
    return (t, P(**kw), e)


_REG = {}


def clip(name):
    def deco(fn):
        _REG[name] = fn
        return fn
    return deco


def cyc(name, dur, fn, n=16, ref_speed=None, **kw):
    """Seamless loop sampled from fn(phase) -> pose, n keys per cycle."""
    keys = [(dur * i / n, fn(i / n), "linear") for i in range(n)]
    return Clip(name, dur, keys, loop=True, ref_speed=ref_speed, **kw)


def seq(name, keys, hold=False, loop=False, **kw):
    return Clip(name, keys[-1][0], keys, loop=loop, hold=hold, **kw)


# ============================================================ idles
@clip("idle")
def _():
    return cyc("idle", 3.2, lambda p: P(ground=True, rot=(0.6 * S(TAU * p), 0, 0), neck=(1.4 * S(TAU * p - .6), 0, 0),
                                       arms=(2 + 1.5 * S(TAU * p), 0, 6 + 1.2 * S(TAU * p)), legs=(0, 0, 2.5)), 12)


@clip("breathe")
def _():
    return cyc("breathe", 2.4, lambda p: P(ground=True, rot=(0.8 * S(TAU * p), 0, 0), neck=(1.0 * S(TAU * p), 0, 0),
                                          arms=(0, 0, 3 + 1.8 * S(TAU * p)), legs=(0, 0, 2)), 8)


@clip("idle_bored")
def _():
    a = dict(arms=(4, 0, 4), legs=(0, 0, 2))
    return seq("idle_bored", [
        K(0, "linear", ground=True, neck=(-4, 0, 0), **a),
        K(0.7, "cubic_inout", ground=True, neck=(-14, 8, 6), rot=(0, 0, -3), bend=3, **a),
        K(1.6, "cubic_inout", ground=True, neck=(-10, 30, 4), rot=(0, 0, -3), bend=2,
          arms=(10, 0, 9), legs=(0, 0, 2)),
        K(2.1, "back_out", ground=True, neck=(6, -25, -4), rot=(0, 3, 3), arms=(-4, 0, 7), legs=(0, 0, 2)),
        K(3.0, "cubic_inout", ground=True, neck=(-8, -6, 3), rot=(0, 0, 2), **a),
        K(3.8, "cubic_inout", ground=True, neck=(-4, 0, 0), **a),
    ], loop=True)


# ============================================================ locomotion
def _walk_pose(p, A=34, B=30, lean=0.0, bob_ground=True):
    s = S(TAU * p); c = C(TAU * p)
    return P(ground=True, rot=(-lean, 4 * s, 2 * c), neck=(lean * 0.6, -4 * s, -1.5 * c),
             arms=(-B * s, 0, 4), ls=(B * s, 0, -4), rh=(A * s, 0, 1.5), lh=(-A * s, 0, -1.5))


@clip("walk")
def _():
    return cyc("walk", 0.72, lambda p: _walk_pose(p, 34, 30, 3), 16, ref_speed=6.5)


@clip("jog")
def _():
    return cyc("jog", 0.56, lambda p: _walk_pose(p, 46, 52, 9), 16, ref_speed=11.0)


def _run_pose(p, A, B, lean, arm_out, back=0.0, hop=0.22):
    s = S(TAU * p); c = C(TAU * p)
    return P(dy=hop * s * s - 0.1, rot=(-lean, 7 * s, 3 * c), neck=(lean * 0.9, -6 * s, 0),
             arms=(-B * s - back, 0, arm_out), ls=(B * s - back, 0, -arm_out),
             rh=(A * s + lean * 0.5, 0, 3), lh=(-A * s + lean * 0.5, 0, -3))


@clip("run")
def _():
    return cyc("run", 0.46, lambda p: _run_pose(p, 52, 72, 16, 16), 16, ref_speed=16.0)


@clip("sprint_panic")
def _():
    return cyc("sprint_panic", 0.38, lambda p: _run_pose(p, 58, 30, 20, 28, back=70, hop=0.3), 16, ref_speed=24.0)


@clip("sneak")
def _():
    def f(p):
        s = S(TAU * p)
        return P(dy=-0.0, bend=22, rot=(0, 4 * s, 0), neck=(24, -3 * s, 0), arms=(-14 * s + 15, 0, 6), ls=(14 * s + 15, 0, -6),
                 rh=(22 * s, 0, 2), lh=(-22 * s, 0, -2), ground=True)
    return cyc("sneak", 1.1, f, 16, ref_speed=3.0)


# ============================================================ air
@clip("jump")
def _():
    return seq("jump", [
        K(0, "linear", ground=True, arms=(0, 0, 5)),
        K(0.1, "cubic_out", bend=14, neck=(15, 0, 0), arms=(-45, 0, 8), legs=(0, 0, 4), dy=-0.35),
        K(0.3, "back_out", dy=1.9, rot=(-4, 0, 0), arms=(150, 0, 22), rh=(30, 0, 5), lh=(-8, 0, -5), neck=(8, 0, 0)),
        K(0.55, "sine_inout", dy=2.3, arms=(135, 0, 40), rh=(35, 0, 8), lh=(-12, 0, -8)),
        K(0.8, "quad_in", dy=0.4, arms=(95, 0, 35), rh=(12, 0, 4), lh=(5, 0, -4)),
        K(0.9, "cubic_out", ground=True, bend=10, arms=(40, 0, 20)),
        K(1.1, "cubic_out", ground=True, arms=(0, 0, 5)),
    ])


@clip("fall")
def _():
    def f(p):
        s = S(TAU * p)
        return P(dy=1.0, rot=(-8 * s, 0, 5 * s), neck=(12, 0, 0), arms=(150 + 15 * s, 0, 35 + 10 * s),
                 ls=(150 - 15 * s, 0, -(35 - 10 * s)), rh=(20 + 25 * s, 0, 8), lh=(20 - 25 * s, 0, -8))
    return cyc("fall", 0.4, f, 8)


@clip("land")
def _():
    return seq("land", [
        K(0, "linear", dy=0.6, arms=(120, 0, 30), rh=(15, 0, 4), lh=(5, 0, -4)),
        K(0.08, "cubic_in", ground=True, bend=34, neck=(30, 0, 0), arms=(30, 0, 50), legs=(20, 0, 8), dy=-0.2),
        K(0.28, "back_out", ground=True, bend=14, neck=(10, 0, 0), arms=(10, 0, 30), legs=(4, 0, 4)),
        K(0.5, "cubic_inout", ground=True, arms=(2, 0, 6), legs=(0, 0, 2.5)),
    ])


# ============================================================ sitting (seat surface = 1.0 above character origin)
SIT = dict(dy=-1.0, legs=(90, 0, 3))


@clip("sit")
def _():
    return seq("sit", [K(0, "linear", ground=True, arms=(0, 0, 5)),
                       K(0.12, "cubic_out", bend=-8, dy=0.1, arms=(10, 0, 20), legs=(40, 0, 3)),
                       K(0.35, "back_out", arms=(28, 0, -6), neck=(2, 0, 0), **SIT)], hold=True)


@clip("sit_slouch")
def _():
    return seq("sit_slouch", [K(0, "linear", arms=(28, 0, -6), **SIT),
                              K(0.4, "cubic_out", bend=18, neck=(24, 0, 0), arms=(35, 0, -10), **SIT)], hold=True)


@clip("sit_desk")
def _():
    def f(p):
        s = S(TAU * p * 3)
        return P(bend=20, neck=(-18 + 0 * s, 0, 3), rs=(75 + 4 * s, 0, -14 + 6 * s), ls=(62, 0, 12), **SIT)
    c = cyc("sit_desk", 1.2, f, 12)
    return c


@clip("stand_up")
def _():
    return seq("stand_up", [K(0, "linear", arms=(28, 0, -6), **SIT),
                            K(0.15, "cubic_out", bend=28, dy=-0.4, neck=(14, 0, 0), arms=(50, 0, 10), legs=(70, 0, 3)),
                            K(0.32, "back_out", ground=True, bend=6, arms=(-10, 0, 14), legs=(8, 0, 3)),
                            K(0.55, "cubic_inout", ground=True, arms=(2, 0, 6), legs=(0, 0, 2.5))])


# ============================================================ gestures
@clip("wave")
def _():
    keys = [K(0, "linear", ground=True, arms=(0, 0, 5)),
            K(0.15, "back_out", ground=True, rs=(8, 0, 128), ls=(0, 0, -6), neck=(4, -6, -5), rot=(0, 0, -2))]
    for i in range(5):
        keys.append(K(0.15 + 0.14 * (2 * i + 1), "sine_inout", ground=True, rs=(8, 0, 150), ls=(0, 0, -6), neck=(4, -6, -5), rot=(0, 0, -2)))
        keys.append(K(0.15 + 0.14 * (2 * i + 2), "sine_inout", ground=True, rs=(8, 0, 118), ls=(0, 0, -6), neck=(4, -6, -5), rot=(0, 0, -2)))
    t = keys[-1][0]
    keys += [K(t + 0.2, "cubic_inout", ground=True, arms=(0, 0, 5))]
    return seq("wave", keys)


@clip("point")
def _():
    a = dict(ground=True, ls=(0, 0, -6), neck=(3, 8, 0))
    return seq("point", [K(0, "linear", ground=True, arms=(0, 0, 5)),
                         K(0.12, "back_out", rs=(88, 0, 12), rot=(0, 6, 0), **a),
                         K(0.2, "cubic_out", rs=(94, 0, 12), rot=(0, 6, 0), bend=3, **a),
                         K(0.9, "linear", rs=(94, 0, 12), rot=(0, 6, 0), bend=3, **a),
                         K(1.15, "cubic_inout", ground=True, arms=(0, 0, 5))])


@clip("point_up")
def _():
    return seq("point_up", [K(0, "linear", ground=True, arms=(0, 0, 5)),
                            K(0.14, "back_out", ground=True, rs=(170, 0, 12), ls=(0, 0, -6), neck=(18, 0, 0)),
                            K(1.0, "linear", ground=True, rs=(172, 0, 14), ls=(0, 0, -6), neck=(18, 0, 0)),
                            K(1.25, "cubic_inout", ground=True, arms=(0, 0, 5))])


@clip("cheer")
def _():
    up = lambda a, h: dict(dy=h, arms=(a, 0, 150), legs=(0, 0, 8), neck=(14, 0, 0))
    return seq("cheer", [K(0, "linear", ground=True, arms=(0, 0, 5)),
                         K(0.1, "cubic_out", dy=-0.2, arms=(-30, 0, 20), legs=(0, 0, 5), bend=8),
                         K(0.26, "back_out", **up(10, 1.0)), K(0.42, "quad_in", ground=True, arms=(25, 0, 140), legs=(0, 0, 8)),
                         K(0.56, "cubic_out", **up(0, 0.9)), K(0.72, "quad_in", ground=True, arms=(20, 0, 145), legs=(0, 0, 8)),
                         K(0.86, "cubic_out", **up(10, 0.8)), K(1.0, "quad_in", ground=True, arms=(25, 0, 140), legs=(0, 0, 8)),
                         K(1.5, "linear", ground=True, arms=(25, 0, 140), legs=(0, 0, 8), neck=(14, 0, 0)),
                         K(1.8, "cubic_inout", ground=True, arms=(0, 0, 5))])


@clip("shrug")
def _():
    sh = dict(ground=True, arms=(38, 0, 42), neck=(-4, 0, 14), rot=(0, 0, 3))
    return seq("shrug", [K(0, "linear", ground=True, arms=(0, 0, 5)),
                         K(0.1, "cubic_out", ground=True, arms=(-6, 0, 12), neck=(6, 0, 0)),
                         K(0.22, "back_out", **sh), K(1.0, "linear", **sh),
                         K(1.3, "cubic_inout", ground=True, arms=(0, 0, 5))])


@clip("facepalm")
def _():
    fp = dict(ground=True, rs=(132, -10, -52), ls=(0, 0, -6), neck=(-14, 0, 0), bend=6)
    return seq("facepalm", [K(0, "linear", ground=True, arms=(0, 0, 5)),
                            K(0.08, "cubic_out", ground=True, rs=(100, -5, -20), ls=(0, 0, -6)),
                            K(0.24, "back_out", **fp), K(1.3, "linear", **fp),
                            K(1.6, "cubic_inout", ground=True, arms=(0, 0, 5))])


@clip("laugh")
def _():
    def f(p):
        s = S(TAU * p * 2)
        return P(ground=True, bend=-10, rot=(0, 0, 4 * S(TAU * p * 2)), neck=(24 + 4 * s, 0, -8 * C(TAU * p * 2)),
                 arms=(52 + 6 * s, 0, -30), ls=(52 + 6 * s, 0, 30), legs=(0, 0, 4), dy=0.0)
    return cyc("laugh", 0.5, f, 8)


@clip("cry")
def _():
    def f(p):
        s = S(TAU * p * 2)
        return P(ground=True, bend=8, rot=(0, 0, 0), neck=(-26 + 2 * s, 0, 4 * S(TAU * p)), rs=(150, 0, -25 + 3 * s),
                 ls=(150, 0, 25 - 3 * s), legs=(0, 0, 2), dx=0.04 * s)
    return cyc("cry", 0.8, f, 8)


@clip("shock")
def _():
    sh = dict(bend=-14, neck=(14, 0, 0), arms=(35, 0, 105), legs=(0, 0, 9))
    return seq("shock", [K(0, "linear", ground=True, arms=(0, 0, 5)),
                         K(0.06, "cubic_out", dy=0.45, **sh), K(0.14, "quad_in", ground=True, **sh),
                         K(0.2, "back_out", ground=True, **dict(sh, neck=(10, 0, 0))),
                         K(1.2, "linear", ground=True, **dict(sh, neck=(10, 0, 0))),
                         K(1.5, "cubic_inout", ground=True, arms=(0, 0, 5))], hold=False)


@clip("scared")
def _():
    def f(p):
        s = S(TAU * p * 4)
        return P(ground=True, bend=26, neck=(-10, 0, 0), dx=0.05 * s, rs=(145, 0, -28), ls=(145, 0, 28),
                 legs=(14, 0, -2), rot=(0, 0, 2 * s))
    return cyc("scared", 0.5, f, 8)


@clip("angry")
def _():
    def f(p):
        s = S(TAU * p)
        stomp = max(0.0, S(TAU * p * 2))
        return P(ground=True, bend=10, neck=(-8, 0, 0), rot=(0, 0, 2 * S(TAU * p * 4)),
                 rs=(-8, 0, 14), ls=(-8, 0, -14), rh=(36 * stomp, 0, 3), lh=(0, 0, -3), dy=0.0)
    return cyc("angry", 0.8, f, 16)


@clip("talk")
def _():
    def f(p):
        a, b = S(TAU * p), S(TAU * p * 2 + 1.0)
        return P(ground=True, neck=(3 + 3 * b, 7 * a, 2 * S(TAU * p * 2)), rot=(0, 3 * a, 0),
                 rs=(28 + 24 * b, 0, 12 + 8 * a), ls=(20 + 16 * S(TAU * p * 2 + 2.5), 0, -(10 + 6 * S(TAU * p * 2))),
                 legs=(0, 0, 2.5))
    return cyc("talk", 1.6, f, 16)


@clip("nod")
def _():
    base = dict(ground=True, arms=(0, 0, 5))
    return seq("nod", [K(0, "linear", **base), K(0.1, "cubic_out", neck=(-20, 0, 0), **base),
                       K(0.25, "back_out", neck=(2, 0, 0), **base), K(0.35, "cubic_out", neck=(-16, 0, 0), **base),
                       K(0.5, "back_out", neck=(0, 0, 0), **base), K(0.65, "linear", neck=(0, 0, 0), **base)])


@clip("shake_head")
def _():
    base = dict(ground=True, arms=(0, 0, 5))
    return seq("shake_head", [K(0, "linear", **base)] + [K(0.1 * (i + 1), "cubic_out", neck=(-3, v, 0), **base)
               for i, v in enumerate([32, -32, 26, -26, 0])] + [K(0.75, "linear", neck=(0, 0, 0), **base)])


@clip("lean_in")
def _():
    return seq("lean_in", [K(0, "linear", ground=True, arms=(0, 0, 5)),
                           K(0.25, "back_out", bend=16, neck=(10, 0, 0), arms=(-6, 0, 10), legs=(0, 0, 2)),
                           K(1.2, "linear", bend=16, neck=(10, 0, 0), arms=(-6, 0, 10), legs=(0, 0, 2))], hold=True)


@clip("cross_arms")
def _():
    ca = dict(ground=True, rs=(82, 0, -58), ls=(96, 0, 58), neck=(2, 0, 0), legs=(0, 0, 3))
    return seq("cross_arms", [K(0, "linear", ground=True, arms=(0, 0, 5)), K(0.2, "back_out", **ca),
                              K(1.0, "linear", **ca)], hold=True)


@clip("hands_on_hips")
def _():
    h = dict(ground=True, arms=(-14, 0, 34), neck=(4, 0, 3), legs=(0, 0, 5))
    return seq("hands_on_hips", [K(0, "linear", ground=True, arms=(0, 0, 5)), K(0.18, "back_out", **h),
                                 K(1.0, "linear", **h)], hold=True)


@clip("think")
def _():
    t = dict(ground=True, rs=(132, 20, -60), ls=(0, 0, -6), neck=(-4, 12, 8))
    return seq("think", [K(0, "linear", ground=True, arms=(0, 0, 5)), K(0.2, "back_out", **t),
                         K(1.4, "linear", **t)], hold=True)


@clip("look_around")
def _():
    b = dict(ground=True, arms=(0, 0, 5))
    return seq("look_around", [K(0, "linear", **b), K(0.2, "cubic_out", neck=(2, 40, 0), rot=(0, 10, 0), **b),
                               K(0.8, "linear", neck=(2, 40, 0), rot=(0, 10, 0), **b),
                               K(1.0, "back_out", neck=(2, -40, 0), rot=(0, -10, 0), **b),
                               K(1.6, "linear", neck=(2, -40, 0), rot=(0, -10, 0), **b),
                               K(1.9, "cubic_inout", **b)])


# ============================================================ body actions
@clip("tie_shoes")
def _():
    def f(p):
        s = S(TAU * p * 2)
        return P(dy=-1.35, bend=62, rot=(0, 0, 0), neck=(35, 0, 0), rs=(70 + 12 * s, 0, -8), ls=(70 - 12 * s, 0, 8),
                 rh=(28, 0, 3), lh=(0, 0, -3))
    return cyc("tie_shoes", 0.8, f, 8)


@clip("crouch")
def _():
    return seq("crouch", [K(0, "linear", ground=True, arms=(0, 0, 5)),
                          K(0.25, "back_out", dy=-1.3, bend=40, neck=(30, 0, 0), arms=(30, 0, 14), legs=(40, 0, 6))], hold=True)


@clip("faint")
def _():
    lay = dict(dy=-2.5, dz=3.0, rot=(90, 0, 0), arms=(10, 0, 55), legs=(0, 0, 12), neck=(0, 0, 0))
    return seq("faint", [K(0, "linear", ground=True, arms=(0, 0, 5)),
                         K(0.22, "cubic_inout", ground=True, bend=-8, neck=(10, 0, 8), arms=(25, 0, 40)),
                         K(0.5, "cubic_inout", ground=True, bend=6, neck=(-6, 0, -8), arms=(-10, 0, 55), rot=(0, 0, 4)),
                         K(0.98, "cubic_in", **lay),
                         K(1.08, "cubic_out", **dict(lay, dy=-2.0, arms=(25, 0, 70))),
                         K(1.2, "bounce_out", **lay)], hold=True)


@clip("ragdoll_fall")
def _():
    end = dict(dy=-2.45, dz=-3.2, rot=(-90, 0, 0), arms=(-160, 0, 40), ls=(-150, 0, -70), rh=(-20, 0, 12), lh=(10, 0, -25), neck=(30, 20, 0))
    return seq("ragdoll_fall", [K(0, "linear", ground=True, arms=(0, 0, 5)),
                                K(0.12, "cubic_out", dy=0.5, rot=(-30, 0, 15), arms=(120, 0, 70), ls=(60, 0, -80), rh=(40, 0, 10), lh=(-30, 0, -20), neck=(20, 0, 0)),
                                K(0.45, "linear", dy=0.2, dz=-1.5, rot=(-150, 0, 40), rs=(160, 0, 80), ls=(-40, 0, -100), rh=(-30, 0, 20), lh=(60, 0, -30), neck=(-30, 40, 0)),
                                K(0.8, "cubic_in", **dict(end, dy=-2.0, rot=(-330, 0, 10))),
                                K(0.92, "cubic_out", **dict(end, dy=-1.9, rot=(-440, 0, 0))),
                                K(1.1, "bounce_out", **dict(end, rot=(-450, 0, 0)))], hold=True)


@clip("sleep_hug")
def _():
    def f(p):
        s = S(TAU * p)
        return P(dy=-2.5 + 0.03 * s, dz=0, rot=(0, 0, 90 + 0.8 * s), neck=(-8, 0, 0), rs=(100, 0, -25), ls=(112, 0, 40),
                 rh=(40, 0, 6), lh=(55, 0, -4), dx=0)
    return cyc("sleep_hug", 3.0, f, 8)


@clip("push")
def _():
    a = dict(ground=True, bend=22, neck=(14, 0, 0), rs=(92, 0, 6), ls=(92, 0, -6), rh=(-22, 0, 3), lh=(20, 0, -3))
    return seq("push", [K(0, "linear", ground=True, arms=(0, 0, 5)),
                        K(0.14, "cubic_out", ground=True, bend=6, arms=(30, 0, 18), rh=(10, 0, 3), lh=(-10, 0, -3)),
                        K(0.3, "back_out", **a), K(0.42, "linear", **dict(a, dz=-0.15)),
                        K(0.54, "linear", **a), K(0.66, "linear", **dict(a, dz=-0.15)),
                        K(1.2, "linear", **a), K(1.5, "cubic_inout", ground=True, arms=(0, 0, 5))])


@clip("throw")
def _():
    base = dict(ground=True)
    return seq("throw", [K(0, "linear", ground=True, arms=(0, 0, 5)),
                         K(0.2, "cubic_out", bend=-12, rot=(0, -38, 0), rs=(-110, 0, 22), ls=(70, 0, -30), neck=(8, 30, 0), lh=(18, 0, 0), rh=(-10, 0, 0), ground=True),
                         K(0.3, "back_out", bend=14, rot=(0, 28, 0), rs=(125, 0, 10), ls=(-20, 0, -40), neck=(-4, -18, 0), lh=(-12, 0, 0), rh=(26, 0, 0), ground=True),
                         K(0.75, "cubic_out", bend=8, rot=(0, 22, 0), rs=(80, 0, 12), ls=(-10, 0, -30), rh=(18, 0, 0), ground=True),
                         K(1.1, "cubic_inout", ground=True, arms=(0, 0, 5))])


@clip("catch")
def _():
    c = dict(ground=True, bend=6, neck=(-6, 0, 0), arms=(72, 0, 14))
    return seq("catch", [K(0, "linear", ground=True, arms=(0, 0, 5)),
                         K(0.1, "back_out", ground=True, arms=(80, 0, 38), bend=-4),
                         K(0.28, "cubic_in", **dict(c, arms=(70, 0, -12))),
                         K(0.4, "back_out", **dict(c, arms=(66, 0, -4))),
                         K(0.9, "linear", **dict(c, arms=(66, 0, -4))), K(1.2, "cubic_inout", ground=True, arms=(0, 0, 5))])


@clip("hug")
def _():
    return seq("hug", [K(0, "linear", ground=True, arms=(0, 0, 5)),
                       K(0.2, "cubic_out", ground=True, bend=4, arms=(82, 0, 52), neck=(3, 0, 6)),
                       K(0.42, "back_out", ground=True, bend=10, arms=(78, 0, -34), neck=(-8, 0, 8)),
                       K(0.7, "cubic_inout", ground=True, bend=12, arms=(76, 0, -40), neck=(-10, 0, 9)),
                       K(1.0, "cubic_inout", ground=True, bend=10, arms=(78, 0, -34), neck=(-8, 0, 8))], hold=True)


@clip("kick")
def _():
    return seq("kick", [K(0, "linear", ground=True, arms=(0, 0, 5)),
                        K(0.18, "cubic_out", ground=True, bend=-6, rot=(0, 0, 0), rh=(-48, 0, 2), lh=(0, 0, -2), rs=(40, 0, 20), ls=(-30, 0, -20)),
                        K(0.3, "back_out", ground=True, bend=-10, rh=(92, 0, 2), lh=(0, 0, -2), rs=(-30, 0, 30), ls=(50, 0, -10), neck=(8, 0, 0)),
                        K(0.7, "cubic_out", ground=True, bend=-6, rh=(80, 0, 2), lh=(0, 0, -2), rs=(-24, 0, 28), ls=(40, 0, -12)),
                        K(1.0, "cubic_inout", ground=True, arms=(0, 0, 5))])


@clip("swim")
def _():
    def f(p):
        s = S(TAU * p * 4)
        return P(dy=-0.4, rot=(-80, 0, 0), neck=(70, 0, 0), rs=(360 * p, 0, 8), ls=(360 * ((p + 0.5) % 1.0) + 0, 0, -8),
                 rh=(20 * s, 0, 2), lh=(-20 * s, 0, -2))
    return cyc("swim", 1.2, f, 24)


@clip("climb")
def _():
    def f(p):
        s = S(TAU * p)
        return P(dy=0.25 * abs(s), bend=-8, neck=(18, 0, 0), rs=(125 + 45 * s, 0, 10), ls=(125 - 45 * s, 0, -10),
                 rh=(50 + 30 * s, 0, 3), lh=(50 - 30 * s, 0, -3))
    return cyc("climb", 0.9, f, 16)


@clip("salute")
def _():
    sa = dict(ground=True, rs=(120, -60, -52), ls=(0, 0, -6), neck=(4, 0, 0), legs=(0, 0, 2))
    return seq("salute", [K(0, "linear", ground=True, arms=(0, 0, 5)), K(0.14, "back_out", **sa),
                          K(1.1, "linear", **sa), K(1.3, "cubic_inout", ground=True, arms=(0, 0, 5))])


@clip("bow")
def _():
    return seq("bow", [K(0, "linear", ground=True, arms=(0, 0, 5)),
                       K(0.12, "cubic_out", ground=True, bend=-6, arms=(-6, 0, 8)),
                       K(0.4, "back_out", ground=True, bend=58, neck=(12, 0, 0), arms=(-18, 0, 10)),
                       K(1.1, "linear", ground=True, bend=58, neck=(12, 0, 0), arms=(-18, 0, 10)),
                       K(1.5, "cubic_inout", ground=True, arms=(0, 0, 5))])


@clip("flex")
def _():
    def f(p):
        s = S(TAU * p * 4)
        return P(ground=True, bend=-8, neck=(10, 0, 3 * s), rs=(8, 0, 78 + 3 * s), ls=(8, 0, -(78 + 3 * s)),
                 legs=(0, 0, 12), rot=(0, 0, 0.8 * s))
    return seq("flex", [K(0, "linear", ground=True, arms=(0, 0, 5)),
                        K(0.12, "cubic_out", ground=True, bend=6, arms=(-20, 0, 22)),
                        K(0.28, "back_out", ground=True, bend=-8, neck=(10, 0, 0), arms=(8, 0, 78), legs=(0, 0, 12)),
                        K(1.4, "linear", ground=True, bend=-8, neck=(10, 0, 0), arms=(8, 0, 78), legs=(0, 0, 12)),
                        K(1.7, "cubic_inout", ground=True, arms=(0, 0, 5))])


@clip("clap")
def _():
    def f(p):
        c = (1 - C(TAU * p * 2)) / 2   # 0 open, 1 closed
        return P(ground=True, bend=-4, neck=(4, 0, 0), arms=(84, 0, 28 - 62 * c), legs=(0, 0, 3), dy=0.0)
    return cyc("clap", 0.7, f, 14)


@clip("spin")
def _():
    return seq("spin", [K(0, "linear", ground=True, arms=(0, 0, 5)),
                        K(0.1, "cubic_out", ground=True, bend=6, arms=(-20, 0, 40)),
                        K(0.55, "cubic_inout", dy=0.4, rot=(0, 360, 0), arms=(10, 0, 90), legs=(0, 0, 6)),
                        K(0.75, "back_out", ground=True, rot=(0, 360, 0), arms=(0, 0, 5))])


# ============================================================ dances
@clip("dance_1")
def _():
    def f(p):
        s = S(TAU * p); a = (1 + S(TAU * p * 2)) / 2
        return P(ground=True, dy=0.18 * (1 - C(TAU * p * 4)) / 2, rot=(0, 10 * s, 6 * s), neck=(4, 0, -8 * s),
                 rs=(10, 0, 20 + 130 * max(0, s)), ls=(10, 0, -(20 + 130 * max(0, -s))), rh=(0, 0, 8 + 5 * s), lh=(0, 0, -(8 - 5 * s)))
    return cyc("dance_1", 0.8, f, 16)


@clip("dance_2")
def _():
    def f(p):
        s = S(TAU * p); c = C(TAU * p)
        return P(ground=True, dy=0.14 * (1 - C(TAU * p * 2)) / 2, rot=(0, 16 * s, 3 * c), neck=(0, -10 * s, 6 * s),
                 rs=(70 + 30 * c, 0, -(10 + 40 * s)), ls=(70 - 30 * c, 0, 10 - 40 * s), rh=(12 * s, 0, 6), lh=(-12 * s, 0, -6))
    return cyc("dance_2", 1.0, f, 16)


@clip("dance_3")
def _():
    def f(p):
        s = S(TAU * p); h = max(0, S(TAU * p)); h2 = max(0, -S(TAU * p))
        return P(ground=True, bend=-6 + 4 * C(TAU * p * 2), rot=(0, 22 * s, 8 * s), neck=(8, -18 * s, 0),
                 rs=(40 + 120 * h, 0, 40 + 50 * h), ls=(40 + 120 * h2, 0, -(40 + 50 * h2)),
                 rh=(30 * h, 0, 6), lh=(30 * h2, 0, -6))
    return cyc("dance_3", 1.2, f, 16)


# ============================================================ registry
_CACHE = {}


def get(name):
    if name not in _CACHE:
        if name not in _REG:
            raise KeyError(f"unknown clip '{name}'. Known: {names()}")
        _CACHE[name] = _REG[name]()
    return _CACHE[name]


def names():
    return sorted(_REG)
