import json, numpy as np
from scipy.ndimage import gaussian_filter1d, median_filter
fit = json.load(open('fit_all7.json')); pick = json.load(open('pick7_all.json'))
N = 152
out = json.load(open('fit_all7.json')); pk = json.load(open('pick7_all.json'))
for key, bk in (('f', 'bf'), ('y', 'by')):
    P = np.array([fit[str(n)][key] for n in range(1, N + 1)], float)
    B = np.array([fit[str(n)][bk] for n in range(1, N + 1)], int)
    # 1) keep hand identity continuous: swap hand0/hand1 (and their elbow bends) if that is closer to the previous frame
    for i in range(1, N):
        h0p, h1p = P[i-1, 4:6], P[i-1, 6:8]
        a = np.hypot(*(P[i, 4:6] - h0p)) + np.hypot(*(P[i, 6:8] - h1p))
        b = np.hypot(*(P[i, 6:8] - h0p)) + np.hypot(*(P[i, 4:6] - h1p))
        if b < a - 4:
            P[i, 4:8] = np.concatenate([P[i, 6:8], P[i, 4:6]]); B[i, 0], B[i, 1] = B[i, 1], B[i, 0]
        f0p, f1p = P[i-1, 8:10], P[i-1, 10:12]
        a = np.hypot(*(P[i, 8:10] - f0p)) + np.hypot(*(P[i, 10:12] - f1p))
        b = np.hypot(*(P[i, 10:12] - f0p)) + np.hypot(*(P[i, 8:10] - f1p))
        if b < a - 4:
            P[i, 8:12] = np.concatenate([P[i, 10:12], P[i, 8:10]]); B[i, 2], B[i, 3] = B[i, 3], B[i, 2]
    # 2) reject single-frame outliers with a median filter, then low-pass
    Pm = median_filter(P, size=(5, 1), mode='nearest')
    Ps = gaussian_filter1d(Pm, sigma=2.0, axis=0, mode='nearest')
    Ps[:, 8:12] = gaussian_filter1d(Pm[:, 8:12], sigma=3.0, axis=0, mode='nearest')   # feet move less
    # 3) elbow/knee bend sides: fixed per figure (the mode), no flipping frame to frame
    bm = [int(np.sign(B[:, k].sum()) or 1) for k in range(4)]
    for i, n in enumerate(range(1, N + 1)):
        out[str(n)][key] = Ps[i].tolist(); out[str(n)][bk] = bm
    # 4) pick angle: unwrap, median, low-pass; fixed length
    ang = np.array([pick[str(n)][key][0] for n in range(1, N + 1)])
    u = np.rad2deg(np.unwrap(np.deg2rad(ang)))
    u = median_filter(u, size=7, mode='nearest')
    u = gaussian_filter1d(u, sigma=2.0, mode='nearest')
    for i, n in enumerate(range(1, N + 1)):
        pk[str(n)][key] = [float(u[i]), 64.0, 0.0]
    d = np.hypot(*np.diff(Ps[:, 4:6], axis=0).T)
    print(key, 'hand speed px/frame mean', d.mean().round(1), 'max', d.max().round(1), 'bends', bm)
json.dump(out, open('fit_all8.json', 'w')); json.dump(pk, open('pick8_all.json', 'w'))
