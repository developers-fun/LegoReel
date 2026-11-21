import sys, json, time, math
import numpy as np
import cv2
from PIL import Image
from stickreel.rotofit import *
from fit_run import load, care_mask

ANG = np.deg2rad(np.arange(0, 360, 15))

def enum_limb(fit, ref, p, b, box, other, care, cache, idx, bidx, center, radii):
    p = p.copy(); b = list(b)
    best = (fit.loss(ref, p, tuple(b), box, other, care, None, 0, cache), p.copy(), list(b))
    for a in ANG:
        for r in radii:
            for bs in (1, -1):
                q = p.copy(); q[idx] = center[0] + r * math.cos(a); q[idx + 1] = center[1] + r * math.sin(a)
                bb = list(b); bb[bidx] = bs
                L = fit.loss(ref, q, tuple(bb), box, other, care, None, 0, cache)
                if L < best[0]:
                    best = (L, q.copy(), list(bb))
    return best

def head_target(ref, p, b, other_head):
    pose = build(np.array(p, float), tuple(b)); hx, hy = pose['head']
    m = ref.copy()
    dt = cv2.distanceTransform(m, cv2.DIST_L2, 5)
    H, W = m.shape
    x0, x1, y0, y1 = int(max(0, hx - 40)), int(min(W, hx + 40)), int(max(0, hy - 40)), int(min(H, hy + 40))
    win = dt[y0:y1, x0:x1].copy()
    yy, xx = np.mgrid[y0:y1, x0:x1]
    if other_head is not None:
        win[np.hypot(xx - other_head[0], yy - other_head[1]) < 22] = 0
    win[np.hypot(xx - hx, yy - hy) > 40] = 0
    if win.max() < 11:
        return None
    # centroid of the near-maximal pixels
    sel = win >= win.max() - 1.0
    return (float(xx[sel].mean()), float(yy[sel].mean()))

def refit_one(fit, ref, p, b, other, care, other_head=None):
    p = np.array(p, float)
    fit.ht = head_target(ref, p, b, other_head)
    box = fit.region(ref, p, 120)
    cache = fit.prep(ref, box, other, care)
    L0 = fit.loss(ref, p, tuple(b), box, other, care, None, 0, cache)
    cur_p, cur_b = p.copy(), list(b)
    for rnd in range(2):
        pose = build(cur_p, tuple(cur_b))
        sh = (pose['neck'][0], pose['neck'][1] + 8)
        for idx, bidx in ((4, 0), (6, 1)):
            L, cur_p, cur_b = enum_limb(fit, ref, cur_p, cur_b, box, other, care, cache, idx, bidx, sh, (30, 48, 62, 72))
        hip = (cur_p[0], cur_p[1])
        for idx, bidx in ((8, 2), (10, 3)):
            L, cur_p, cur_b = enum_limb(fit, ref, cur_p, cur_b, box, other, care, cache, idx, bidx, hip, (46, 64, 78, 88))
        cur_p, L = fit.descend(ref, cur_p, tuple(cur_b), box, other, care, None, 0, cache, rounds=10)
    return cur_p, tuple(cur_b), L, L0

if __name__ == '__main__':
    src, out, f0, f1 = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    d = json.load(open(src)); fit = Fitter(); res = {}
    t = time.time()
    for n in range(f0, f1 + 1):
        r = d[str(n)]
        ref = white_mask(load(n)); care = care_mask(ref.shape)
        shp = (0, 0, ref.shape[1], ref.shape[0])
        ymask = draw_mask(build(np.array(r['y']), tuple(r['by'])), shp, ref.shape)[0]
        yh = build(np.array(r['y']), tuple(r['by']))['head']
        pf, bf, Lf, Lf0 = refit_one(fit, ref, r['f'], r['bf'], ymask, care, yh)
        if Lf0 <= Lf: pf, bf, Lf = np.array(r['f']), tuple(r['bf']), Lf0
        fmask = draw_mask(build(pf, bf), shp, ref.shape)[0]
        fh = build(pf, bf)['head']
        py, by, Ly, Ly0 = refit_one(fit, ref, r['y'], r['by'], fmask, care, fh)
        if Ly0 <= Ly: py, by, Ly = np.array(r['y']), tuple(r['by']), Ly0
        res[str(n)] = dict(f=pf.tolist(), y=py.tolist(), bf=list(bf), by=list(by), Lf=Lf, Ly=Ly, Lf0=Lf0, Ly0=Ly0)
        print(n, round(Lf0, 3), '->', round(Lf, 3), round(Ly0, 3), '->', round(Ly, 3), round(time.time() - t, 1), flush=True)
        json.dump(res, open(out, 'w'))
