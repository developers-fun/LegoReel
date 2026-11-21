"""The template stick figure: a small 3D rig described by named numeric parameters, solved to screen joints.

AXES: the figure has forward (f), down (y) and sideways (z) axes. `yaw` turns it about its vertical axis and the
result is projected flat onto the screen, so one figure can face right, turn to the camera, show its back, walk away.
  yaw   0 = profile facing right, 90 = facing the camera, 180 = profile facing left, 270 (or -90) = back to camera.
        yaw tweens like any number, so 0 -> 180 passes through the front, 0 -> -180 passes through the back.
        ("face":"left"/"right" in a key is shorthand for yaw 180/0.)
ANGLES in degrees. A limb angle of 0 = hanging down, 90 = pointing forward, 180 = straight up, -90 = backward.
  arm_r / arm_l = [swing, elbow_bend, out]  swing forward/back, bend folds the forearm forward, out lifts it sideways
  leg_r / leg_l = [swing, knee_bend, out]   bend folds the shin backward           (r = the figure's right side)
  lean = torso tilt (+ forward), head = extra head tilt, rot = whole body pitch about the hip (+ forward)
  x = hip x, ground = floor y (the hip height is solved so the lowest foot touches it), lift = height of a jump
Reach (IK, in screen space, so it works from any yaw), blended by a weight so it can be keyframed on and off:
  hand_r_at / hand_l_at / foot_r_at / foot_l_at = [x, y] world point, or "@name" / "@actor.anchor"
  hand_r_rel / ... = [dx, dy] from the hip, forward being the way the figure faces on screen
  weights ..._w = 0..1, set automatically to 1 when you give a target and to 0 when you write null
  grip_rel = [dx, dy] both hands on one point (two-handed tool grip), grip_w its weight.
"""
import math

UPPER_ARM, FORE_ARM = 33.0, 37.0
THIGH, SHIN = 43.0, 43.0
TORSO, HEAD_OFF, SHOULDER_DROP = 58.0, 19.0, 8.0
SHOULDER_W, HIP_W = 11.0, 7.0

DEFAULTS = dict(
    x=288.0, ground=900.0, lift=0.0, yaw=0.0, rot=0.0, lean=0.0, head=0.0, tint=None,
    arm_r=[16.0, 14.0, 10.0], arm_l=[-12.0, 14.0, 10.0], leg_r=[7.0, 0.0, 4.0], leg_l=[-7.0, 0.0, 4.0],
    hand_r_at=None, hand_l_at=None, foot_r_at=None, foot_l_at=None,
    hand_r_rel=[30.0, -40.0], hand_l_rel=[30.0, -40.0], foot_r_rel=[10.0, 85.0], foot_l_rel=[-10.0, 85.0],
    hand_r_w=0.0, hand_l_w=0.0, foot_r_w=0.0, foot_l_w=0.0,
    grip_rel=[60.0, -40.0], grip_w=0.0,
    expr="calm", talk=False, talk_seed=0,
    prop=None, prop_angle=0.0, prop_hand="auto", prop_l=None, prop_l_angle=0.0,
    anim=None, anim_speed=1.0, anim_blend=0.15, z=10, shadow=True,
)
LIMB_DEFAULT_OUT = dict(arm_r=10.0, arm_l=10.0, leg_r=4.0, leg_l=4.0)
LIMBS = tuple(LIMB_DEFAULT_OUT)


def pad_limb(name, v):
    v = list(v)
    while len(v) < 3:
        v.append(LIMB_DEFAULT_OUT[name] if len(v) == 2 else 0.0)
    return v


def _dir(swing, out, side, flip=False):
    a = math.radians(swing)
    o = math.radians(out)
    return (math.sin(a) * math.cos(o), math.cos(a) * math.cos(o), side * math.sin(o))


def ik2(root, target, l1, l2, score):
    """two-bone IK in screen space. `score(point)` picks between the two bend directions (higher wins)."""
    rx, ry = root
    dx, dy = target[0] - rx, target[1] - ry
    d = max(math.hypot(dx, dy), 1e-3)
    reach = (l1 + l2) * 0.999
    if d > reach:                       # cartoon stretch
        k = d / reach
        l1, l2 = l1 * k, l2 * k
    a = (l1 * l1 - l2 * l2 + d * d) / (2 * d)
    h = math.sqrt(max(l1 * l1 - a * a, 0.0))
    ux, uy = dx / d, dy / d
    px, py = rx + ux * a, ry + uy * a
    c1 = (px - uy * h, py + ux * h)
    c2 = (px + uy * h, py - ux * h)
    return c1 if score(c1) >= score(c2) else c2


def _lerp2(a, b, w):
    return (a[0] + (b[0] - a[0]) * w, a[1] + (b[1] - a[1]) * w)


def solve(p, resolve):
    """params -> (pose dict for figure3d.draw_figure, anchors). resolve(ref) -> (x, y) | None."""
    th = math.radians(p["yaw"])
    cth, sth = math.cos(th), math.sin(th)
    fs = 1.0 if cth >= 0 else -1.0                       # which way "forward" points on screen
    rot = math.radians(p["rot"])
    cr, sr = math.cos(rot), math.sin(rot)

    def pitch(pt):                                       # body pitch about the hip (f, y plane)
        return (pt[0] * cr - pt[1] * sr, pt[0] * sr + pt[1] * cr, pt[2])

    la = math.radians(p["lean"])
    neck = (TORSO * math.sin(la), -TORSO * math.cos(la), 0.0)
    ha = math.radians(p["lean"] + p["head"])
    head = (neck[0] + HEAD_OFF * math.sin(ha), neck[1] - HEAD_OFF * math.cos(ha), 0.0)
    sh = {"r": (neck[0], neck[1] + SHOULDER_DROP, -SHOULDER_W), "l": (neck[0], neck[1] + SHOULDER_DROP, SHOULDER_W)}
    hp = {"r": (0.0, 0.0, -HIP_W), "l": (0.0, 0.0, HIP_W)}

    def chain(root, ang, l1, l2, side, flip):
        sw, bend, out = ang
        d1 = _dir(sw, out, side)
        k = tuple(root[i] + l1 * d1[i] for i in range(3))
        d2 = _dir(sw - bend if flip else sw + bend, out, side)
        e = tuple(k[i] + l2 * d2[i] for i in range(3))
        return k, e

    arms = {s: chain(sh[s], p["arm_" + s], UPPER_ARM, FORE_ARM, -1.0 if s == "r" else 1.0, False) for s in "rl"}
    legs = {s: chain(hp[s], p["leg_" + s], THIGH, SHIN, -1.0 if s == "r" else 1.0, True) for s in "rl"}
    neck, head = pitch(neck), pitch(head)
    sh = {s: pitch(v) for s, v in sh.items()}
    arms = {s: (pitch(k), pitch(e)) for s, (k, e) in arms.items()}
    legs = {s: (pitch(k), pitch(e)) for s, (k, e) in legs.items()}

    def sx(pt):                                          # local (f, y, z) -> screen offset from hip
        return (pt[0] * cth + pt[2] * sth, pt[1])

    def depth(pt):                                       # smaller = nearer the camera
        return -pt[0] * sth + pt[2] * cth

    lows = []
    for s in "rl":
        dy = legs[s][1][1]
        w = p["foot_" + s + "_w"]
        if w > 0 and p["foot_" + s + "_at"] is None:
            dy = dy + (p["foot_" + s + "_rel"][1] - dy) * w
        lows.append(dy)
    hip = (p["x"], p["ground"] - p["lift"] - max(lows))

    def W(pt):
        o = sx(pt)
        return (hip[0] + o[0], hip[1] + o[1])

    n_, h_ = W(neck), W(head)
    sh_w = {s: W(sh[s]) for s in "rl"}
    elbows = {s: W(arms[s][0]) for s in "rl"}
    hands = {s: W(arms[s][1]) for s in "rl"}
    knees = {s: W(legs[s][0]) for s in "rl"}
    feet = {s: W(legs[s][1]) for s in "rl"}
    # depth per part (for draw order)
    dep = {}
    for s in "rl":
        dep["arm_" + s] = (depth(sh[s]) + depth(arms[s][0]) + depth(arms[s][1])) / 3.0
        dep["leg_" + s] = (depth(hp[s]) + depth(legs[s][0]) + depth(legs[s][1])) / 3.0
    dep["torso"] = depth(neck) * 0.5
    dep["head"] = depth(head)

    def target(at, rel):
        if at is not None:
            if isinstance(at, str):
                return resolve(at)
            return (float(at[0]), float(at[1]))
        return (hip[0] + rel[0] * cth, hip[1] + rel[1])

    gw = p.get("grip_w", 0.0)
    for s in "rl":
        w = p["hand_" + s + "_w"]
        tgt = target(p["hand_" + s + "_at"], p["hand_" + s + "_rel"]) if w > 0 else None
        if gw > 0:
            g = (hip[0] + p["grip_rel"][0] * cth, hip[1] + p["grip_rel"][1])
            tgt, w = (g if tgt is None or gw >= w else _lerp2(tgt, g, gw / max(gw + w, 1e-9))), max(w, gw)
        if tgt is not None and w > 0:
            side = -1.0 if s == "r" else 1.0
            pdx = -0.5 * cth + side * sth
            shp = sh_w[s]
            el = ik2(shp, tgt, UPPER_ARM, FORE_ARM, lambda c: c[1] + pdx * (c[0] - shp[0]))
            elbows[s] = _lerp2(elbows[s], el, w)
            hands[s] = _lerp2(hands[s], tgt, w)
    for s in "rl":
        w = p["foot_" + s + "_w"]
        if w > 0:
            tgt = target(p["foot_" + s + "_at"], p["foot_" + s + "_rel"])
            if tgt is not None:
                kn = ik2(hip, tgt, THIGH, SHIN, lambda c: cth * (c[0] - hip[0]))
                knees[s] = _lerp2(knees[s], kn, w)
                feet[s] = _lerp2(feet[s], tgt, w)

    grip = _lerp2(hands["r"], hands["l"], 0.5) if gw >= 0.5 else hands["r"]
    pose = dict(head=h_, neck=n_, hip=hip, shoulders=[sh_w["r"], sh_w["l"]], hands=[hands["r"], hands["l"]],
                feet=[feet["r"], feet["l"]], elbows=[elbows["r"], elbows["l"]], knees=[knees["r"], knees["l"]],
                depth=dep, yaw=p["yaw"], head_tilt=p["lean"] + p["head"], tint=p.get("tint"))
    anchors = dict(head=h_, neck=n_, hip=hip, hand_r=hands["r"], hand_l=hands["l"], grip=grip, foot_r=feet["r"],
                   foot_l=feet["l"], elbow_r=elbows["r"], elbow_l=elbows["l"], knee_r=knees["r"], knee_l=knees["l"],
                   shoulder_r=sh_w["r"], shoulder_l=sh_w["l"], cos_yaw=cth)
    return pose, anchors
