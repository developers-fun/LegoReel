import json, math, sys
import numpy as np, cv2
from PIL import Image
from scipy.ndimage import gaussian_filter1d, median_filter
from stickreel.rotofit import build, draw_mask

def metal(im):
    r, g, b = [im[..., i].astype(int) for i in range(3)]
    mx = np.maximum(np.maximum(r, g), b); mn = np.minimum(np.minimum(r, g), b)
    m = ((mx - mn <= 36) & (mn >= 112) & (mx <= 238) & (b >= r - 10)) | ((mx < 100) & (mx - mn < 40))
    return m.astype(np.uint8)

def detect(fitjson, N):
    d = json.load(open(fitjson)); res = {k: [None] * N for k in ('f', 'y')}
    for n in range(1, N + 1):
        im = np.array(Image.open(f'A_all/f{n:03d}.png').convert('RGB')); H, W = im.shape[:2]
        M = metal(im); M[:300] = 0; M[:, 440:] = 0
        body = np.zeros((H, W), np.uint8); grips = {}
        for key, bk in (('f', 'bf'), ('y', 'by')):
            pose = build(np.array(d[str(n)][key]), tuple(d[str(n)][bk]))
            m, _ = draw_mask(pose, (0, 0, W, H), im.shape); body = np.maximum(body, m)
            grips[key] = np.mean(pose['hands'], 0)
        M = M * (1 - cv2.dilate(body, np.ones((9, 9), np.uint8)))
        M = cv2.morphologyEx(M, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        M = cv2.dilate(M, np.ones((5, 5), np.uint8))
        k, lab, stats, cen = cv2.connectedComponentsWithStats(M)
        comps = [(cen[i], stats[i, cv2.CC_STAT_AREA]) for i in range(1, k) if 150 <= stats[i, cv2.CC_STAT_AREA] <= 2500]
        for key in ('f', 'y'):
            g = grips[key]
            best = None
            for c, a in comps:
                dist = math.hypot(c[0] - g[0], c[1] - g[1])
                if 40 <= dist <= 100:
                    sc = a - 4 * abs(dist - 72)
                    if best is None or sc > best[0]: best = (sc, c, dist)
            if best:
                c, dist = best[1], best[2]
                res[key][n - 1] = (math.degrees(math.atan2(c[1] - g[1], c[0] - g[0])), dist)
    return res

if __name__ == '__main__':
    N = int(sys.argv[3]); res = detect(sys.argv[1], N)
    out = json.load(open('pick8_all.json'))
    for key in ('f', 'y'):
        ang = np.array([np.nan if r is None else r[0] for r in res[key]])
        ln = np.array([np.nan if r is None else r[1] for r in res[key]])
        ok = ~np.isnan(ang); print(key, 'detected', ok.sum(), 'of', N)
        idx = np.arange(N)
        u = np.rad2deg(np.unwrap(np.deg2rad(np.interp(idx, idx[ok], ang[ok]))))
        ln = np.interp(idx, idx[ok], ln[ok])
        u = gaussian_filter1d(median_filter(u, size=3, mode='nearest'), 0.8, mode='nearest')
        ln = gaussian_filter1d(median_filter(ln, size=5, mode='nearest'), 2.0, mode='nearest')
        for i in range(N):
            out[str(i + 1)][key] = [float(u[i]), float(np.clip(ln[i] - 8, 50, 80)), 0.0]
    json.dump(out, open(sys.argv[2], 'w'))
