import json, math
import numpy as np
from stickreel.rotofit import build
fit = json.load(open('fit_all4s.json')); pick = json.load(open('pick4_all.json'))
LIB = list(range(1, 151))
def feat(p, pk):
    head = np.array(p['head']); h = [np.array(x) - head for x in p['hands']]
    return head, h, pk
def cost(fh, fpk, lh, lpk):
    a = np.linalg.norm(fh[0] - lh[0]) + np.linalg.norm(fh[1] - lh[1])
    b = np.linalg.norm(fh[0] - lh[1]) + np.linalg.norm(fh[1] - lh[0])
    d = abs((fpk - lpk + 180) % 360 - 180)
    return min(a, b) / 70.0 + d / 90.0
lib = {m: feat(build(np.array(fit[str(m)]['y']), tuple(fit[str(m)]['by'])), pick[str(m)]['y'][0]) for m in LIB}
T = list(range(1, 153))
C = np.zeros((len(T), len(LIB)))
for i, n in enumerate(T):
    p = build(np.array(fit[str(n)]['f']), tuple(fit[str(n)]['bf']))
    fh = [np.array(x) - np.array(p['head']) for x in p['hands']]
    fpk = pick[str(n)]['f'][0]
    for j, m in enumerate(LIB):
        C[i, j] = cost(fh, fpk, lib[m][1], lib[m][2])
# viterbi: progression by 1..2 frames per step is natural; penalize others
J = len(LIB)
dp = np.zeros_like(C); bp = np.zeros(C.shape, int)
dp[0] = C[0]
idx = np.arange(J)
trans = np.abs(((idx[None, :] - idx[:, None]) - 1.2)) * 0.04          # from i to j
for t in range(1, len(T)):
    cand = dp[t-1][:, None] + trans                                     # i -> j
    # allow wrap-around of the loop: any big jump costs a flat 0.5
    cand = np.minimum(cand, dp[t-1].min() + 0.5)
    bp[t] = cand.argmin(0); dp[t] = C[t] + cand.min(0)
j = int(dp[-1].argmin()); path = [j]
for t in range(len(T) - 1, 0, -1):
    j = bp[t][j]; path.append(j)
path = path[::-1]
out = json.load(open('fit_all4s.json')); pk2 = json.load(open('pick4_all.json'))
heads = np.array([build(np.array(fit[str(n)]['f']), tuple(fit[str(n)]['bf']))['head'] for n in T])
# smooth the target head track a little
hs = heads.copy()
for k in range(2):
    hs[:, k] = np.convolve(np.pad(heads[:, k], 3, mode='edge'), np.ones(7) / 7, mode='valid')
rows = []
for i, n in enumerate(T):
    m = LIB[path[i]]
    py = np.array(fit[str(m)]['y']); p = build(py, tuple(fit[str(m)]['by']))
    dx, dy = hs[i][0] - p['head'][0], hs[i][1] - p['head'][1]
    q = py.copy(); q[0] += dx; q[1] += dy
    for k in (4, 5, 6, 7, 8, 9, 10, 11):
        q[k] += dx if k % 2 == 0 else dy
    out[str(n)]['f'] = q.tolist(); out[str(n)]['bf'] = fit[str(m)]['by']
    pk2[str(n)]['f'] = list(pick[str(m)]['y'])
    rows.append((n, m))
json.dump(out, open('fit_all5.json', 'w')); json.dump(pk2, open('pick5_all.json', 'w'))
print(rows[:40])
