import json, numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.ndimage import median_filter
import pickfit3 as P
N = 152; STEP = 3
fit = json.load(open('fit_all8.json')); out = json.load(open('fit_all8.json'))
pk = json.load(open('pick8_all.json'))
res = P.detect('fit_all8.json', N)
keys = list(range(0, N, STEP)); 
if keys[-1] != N - 1: keys.append(N - 1)
idx = np.arange(N)
for key, bk in (('f', 'bf'), ('y', 'by')):
    Pm = np.array([fit[str(n)][key] for n in range(1, N + 1)], float)
    Pk = np.array([Pm[max(0, k - 1):k + 2].mean(0) for k in keys])      # key value = mean of 3 frames around it
    Pi = PchipInterpolator(keys, Pk, axis=0)(idx)
    ang = np.array([np.nan if r is None else r[0] for r in res[key]]); ln = np.array([np.nan if r is None else r[1] for r in res[key]])
    ok = ~np.isnan(ang)
    c = np.interp(idx, idx[ok], np.cos(np.deg2rad(ang[ok]))); s = np.interp(idx, idx[ok], np.sin(np.deg2rad(ang[ok])))
    ln = np.interp(idx, idx[ok], ln[ok])
    ck = np.array([np.median(c[max(0, k - 1):k + 2]) for k in keys]); sk = np.array([np.median(s[max(0, k - 1):k + 2]) for k in keys])
    lk = np.array([np.median(ln[max(0, k - 1):k + 2]) for k in keys])
    ci = PchipInterpolator(keys, ck)(idx); si = PchipInterpolator(keys, sk)(idx); li = PchipInterpolator(keys, lk)(idx)
    a = np.rad2deg(np.arctan2(si, ci))
    for i, n in enumerate(range(1, N + 1)):
        out[str(n)][key] = Pi[i].tolist(); pk[str(n)][key] = [float(a[i]), float(np.clip(li[i] - 8, 50, 80)), 0.0]
    d = np.hypot(*np.diff(Pi[:, 4:6], axis=0).T); print(key, 'hand speed mean', d.mean().round(1), 'max', d.max().round(1))
json.dump(out, open('fit_all10.json', 'w')); json.dump(pk, open('pick10_all.json', 'w'))
