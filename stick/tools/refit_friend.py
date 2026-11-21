import sys, json, math, time
import numpy as np, cv2
from stickreel.rotofit import *
from fit_run import load, care_mask
from refit import enum_limb, head_target

def descend_sub(fit, ref, q, b, box, other, care, cache, free, rounds=10):
    Lq = fit.loss(ref, q, b, box, other, care, None, 0, cache); step = STEPS.copy()
    for _ in range(rounds):
        imp = False
        for i in free:
            for s in (1, -1):
                r = q.copy(); r[i] += s * step[i]
                Lr = fit.loss(ref, r, b, box, other, care, None, 0, cache)
                if Lr < Lq - 1e-5: q, Lq, imp = r, Lr, True; break
        if not imp: step *= 0.55
        if step[0] < 0.4: break
    return q, Lq

if __name__ == '__main__':
    f0, f1, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    d = json.load(open('fit_all4.json'))
    F = np.array([d[str(n)]['f'] for n in range(1, 233)])
    W = 12
    base = F.copy()
    for i in range(len(F)):
        lo, hi = max(0, i - W), min(len(F), i + W + 1)
        for k in (0, 1, 2): base[i, k] = np.median(F[lo:hi, k])
        base[i, 1] = min(max(base[i, 1], 490), 504)
        base[i, 8], base[i, 9] = base[i, 0] + 12, 574.0
        base[i, 10], base[i, 11] = base[i, 0] - 28, 572.0
    fit = Fitter(); res = {}; t = time.time()
    for n in range(f0, f1 + 1):
        r = d[str(n)]; ref = white_mask(load(n)); care = care_mask(ref.shape)
        p = np.array(r['f'], float); p[[0, 1, 2, 8, 9, 10, 11]] = base[n - 1, [0, 1, 2, 8, 9, 10, 11]]
        b = [1, 1, -1, -1]
        shp = (0, 0, ref.shape[1], ref.shape[0])
        ym = draw_mask(build(np.array(r['y']), tuple(r['by'])), shp, ref.shape)[0]
        yh = build(np.array(r['y']), tuple(r['by']))['head']
        fit.ht = head_target(ref, p, b, yh)
        box = fit.region(ref, p, 120); cache = fit.prep(ref, box, ym, care)
        cur_p, cur_b = p.copy(), list(b)
        for rnd in range(2):
            pose = build(cur_p, tuple(cur_b)); sh = (pose['neck'][0], pose['neck'][1] + 8)
            for idx, bidx in ((4, 0), (6, 1)):
                L, cur_p, cur_b = enum_limb(fit, ref, cur_p, cur_b, box, ym, care, cache, idx, bidx, sh, (30, 48, 62, 72))
            cur_p, L = descend_sub(fit, ref, cur_p, tuple(cur_b), box, ym, care, cache, [3, 4, 5, 6, 7])
        res[str(n)] = dict(f=cur_p.tolist(), bf=cur_b, Lf=L)
        if n % 10 == 0: print(n, round(L, 3), round(time.time() - t, 1), flush=True)
        json.dump(res, open(out, 'w'))
