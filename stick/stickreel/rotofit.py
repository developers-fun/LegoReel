"""Rotoscope fit: find stick-figure rig parameters whose silhouette matches the white figure in a reference frame.

Mask = near-white, not yellow pixels. Loss = 1 - IoU on a region around the figure (don't-care boxes are ignored).
Search = coordinate descent with shrinking steps, tracking from the previous frame; knee/elbow bend sides are
chosen from the 16 combinations. Pure numpy + OpenCV, about 0.3-1 s per figure per frame.
"""
import math
import itertools
import numpy as np
import cv2
from .figure import ik2, UPPER_ARM, FORE_ARM, THIGH, SHIN, LIMB_ARM, LIMB_LEG, LIMB_TORSO, HEAD_R

TL, HL = 58.0, 19.0


def white_mask(rgb):
    r = rgb[..., 0].astype(np.int16)
    g = rgb[..., 1].astype(np.int16)
    b = rgb[..., 2].astype(np.int16)
    mn = np.minimum(np.minimum(r, g), b)
    m = ((mn >= 172) & (b >= r - 4) & (b >= g - 2)).astype(np.uint8)
    return cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))


def build(p, bends):
    hip = (p[0], p[1])
    a = p[2]
    neck = (hip[0] + TL * math.sin(a), hip[1] - TL * math.cos(a))
    hd = a + p[3]
    head = (neck[0] + HL * math.sin(hd), neck[1] - HL * math.cos(hd))
    hands = [(p[4], p[5]), (p[6], p[7])]
    feet = [(p[8], p[9]), (p[10], p[11])]
    return dict(head=head, neck=neck, hip=hip, hands=hands, feet=feet, eb=list(bends[:2]), kb=list(bends[2:]))


def limbs(pose):
    hip, neck = pose["hip"], pose["neck"]
    sh = (neck[0], neck[1] + 8)
    out = []
    stretch = 0.0
    for i in (0, 1):
        f = pose["feet"][i]
        d = math.hypot(f[0] - hip[0], f[1] - hip[1])
        stretch += max(0.0, d / (THIGH + SHIN) - 1.08)
        out.append(([hip, ik2(hip, f, THIGH, SHIN, pose["kb"][i]), f], LIMB_LEG))
    out.append(([neck, hip], LIMB_TORSO))
    for i in (0, 1):
        h = pose["hands"][i]
        d = math.hypot(h[0] - sh[0], h[1] - sh[1])
        stretch += max(0.0, d / (UPPER_ARM + FORE_ARM) - 1.08)
        out.append(([sh, ik2(sh, h, UPPER_ARM, FORE_ARM, pose["eb"][i]), h], LIMB_ARM))
    return out, stretch


def draw_mask(pose, box, shape):
    """binary mask of the figure inside box = (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box
    m = np.zeros((y1 - y0, x1 - x0), np.uint8)
    ls, stretch = limbs(pose)
    for pts, w in ls:
        P = [(int(round(x - x0)), int(round(y - y0))) for x, y in pts]
        for a, b in zip(P[:-1], P[1:]):
            cv2.line(m, a, b, 1, int(round(w)))
        for q in P:
            cv2.circle(m, q, int(round(w / 2)), 1, -1)
    c = pose["head"]
    cv2.circle(m, (int(round(c[0] - x0)), int(round(c[1] - y0))), int(HEAD_R), 1, -1)
    return m, stretch


STEPS = np.array([4, 4, 0.07, 0.08, 5, 5, 5, 5, 5, 5, 5, 5], dtype=np.float64)


class Fitter:
    def __init__(self, dontcare=()):
        self.dontcare = dontcare

    def region(self, ref, p, pad=60):
        pose = build(p, (1, 1, 1, 1))
        xs = [pose["head"][0], pose["hip"][0]] + [h[0] for h in pose["hands"]] + [f[0] for f in pose["feet"]]
        ys = [pose["head"][1], pose["hip"][1]] + [h[1] for h in pose["hands"]] + [f[1] for f in pose["feet"]]
        H, W = ref.shape
        return (max(0, int(min(xs)) - pad), max(0, int(min(ys)) - pad), min(W, int(max(xs)) + pad), min(H, int(max(ys)) + pad))

    def prep(self, ref, box, other, care):
        x0, y0, x1, y1 = box
        r = ref[y0:y1, x0:x1].copy()
        c = care[y0:y1, x0:x1] if care is not None else np.ones_like(r)
        r = r * c
        o = other[y0:y1, x0:x1] if other is not None else None
        dref = cv2.distanceTransform((r == 0).astype(np.uint8), cv2.DIST_L2, 3)
        return r, c, o, dref

    def loss(self, ref, p, bends, box, other=None, care=None, prior=None, lam=0.0, cache=None):
        pose = build(p, bends)
        m, stretch = draw_mask(pose, box, ref.shape)
        r, c, o, dref = cache
        if o is not None:
            m = np.maximum(m, o)
        m = m * c
        inter = np.count_nonzero(m & r)
        union = np.count_nonzero(m | r)
        iou = inter / max(1, union)
        nm = max(1, np.count_nonzero(m))
        nr = max(1, np.count_nonzero(r))
        dmine = cv2.distanceTransform((m == 0).astype(np.uint8), cv2.DIST_L2, 3)
        A = float((m * dref).sum()) / nm
        B = float((r * dmine).sum()) / nr
        L = 1.0 - iou + 0.03 * min(A + B, 40.0) + 0.6 * stretch
        shp = (pose['neck'][0], pose['neck'][1] + 8)
        pen = 0.0
        for h in pose['hands']:
            pen += max(0.0, 40.0 - math.hypot(h[0] - shp[0], h[1] - shp[1]))
        for f in pose['feet']:
            pen += max(0.0, 46.0 - math.hypot(f[0] - pose['hip'][0], f[1] - pose['hip'][1]))
        L += 0.025 * pen
        ht = getattr(self, 'ht', None)
        if ht is not None:
            L += 0.012 * min(40.0, math.hypot(pose['head'][0] - ht[0], pose['head'][1] - ht[1]))
        if prior is not None and lam > 0:
            L += lam * float(np.sum(((p - prior) / STEPS) ** 2)) / len(p)
        return L

    def descend(self, ref, q, b, box, other, care, prior, lam, cache, rounds=10):
        Lq = self.loss(ref, q, b, box, other, care, prior, lam, cache)
        step = STEPS.copy()
        for _ in range(rounds):
            improved = False
            for i in range(len(q)):
                for sgn in (1, -1):
                    r = q.copy()
                    r[i] += sgn * step[i]
                    Lr = self.loss(ref, r, b, box, other, care, prior, lam, cache)
                    if Lr < Lq - 1e-5:
                        q, Lq, improved = r, Lr, True
                        break
            if not improved:
                step *= 0.55
            if step[0] < 0.4:
                break
        return q, Lq

    def fit(self, ref, p0, bends0, care=None, other=None, prior=None, lam=0.002, rounds=10, try_bends=True, restarts=5, seed=0, trigger=0.30):
        p = np.array(p0, dtype=np.float64)
        box = self.region(ref, p, 80)
        cache = self.prep(ref, box, other, care)
        cands = [tuple(bends0)]
        if try_bends:
            cands += [c for c in itertools.product((1, -1), repeat=4) if c != tuple(bends0)]
        scored = sorted(((self.loss(ref, p, b, box, other, care, prior, lam, cache) + (0.0 if b == tuple(bends0) else 0.035 * sum(x != y for x, y in zip(b, bends0))), b) for b in cands), key=lambda t: t[0])
        results = []
        for L0, b in scored[:3]:
            q, Lq = self.descend(ref, p.copy(), b, box, other, care, prior, lam, cache, rounds)
            results.append((Lq + (0.0 if b == tuple(bends0) else 0.035 * sum(x != y for x, y in zip(b, bends0))), b, q))
        results.sort(key=lambda t: t[0])
        L, b, q = results[0]
        rng = np.random.default_rng(seed)
        k = 0
        while L > trigger and k < restarts:
            k += 1
            q0 = q + rng.normal(0, 1, len(q)) * STEPS * 2.2
            for bb in (b,) + tuple(c for _, c, _ in results[1:2]):
                q2, L2 = self.descend(ref, q0.copy(), bb, box, other, care, prior, lam, cache, rounds)
                if L2 < L:
                    L, b, q = L2, bb, q2
        return q, b, L
