import json, math, sys, time
import numpy as np
from PIL import Image, ImageDraw
from stickreel.engine import *
from stickreel import dig_bg as B
from stickreel.dig_bg import *
from stickreel.figure import *
from stickreel.rotofit import build

FIT = json.load(open('data/fit_all11.json'))
PICK = json.load(open('data/pick10_all.json'))
TUN = json.load(open('data/tun_meas.json'))
N0, N1 = 1, 152

def smooth_series(key, n_frames=range(N0, N1 + 1), w=(0.0, 1.0, 0.0)):
    out = {}
    for i, n in enumerate(n_frames):
        acc = np.zeros(12); ws = 0
        for d, wt in zip((-1, 0, 1), w):
            m = min(max(n + d, N0), N1)
            acc += wt * np.array(FIT[str(m)][key]); ws += wt
        out[n] = acc / ws
    return out

def med_bends(bk, n):
    cols = [FIT[str(min(max(n + d, N0), N1))][bk] for d in (-1, 0, 1)]
    return tuple(int(sorted(c[i] for c in cols)[1]) for i in range(4))

SM = {'f': smooth_series('f'), 'y': smooth_series('y')}

def smooth_pick(key, n, k=0):
    vals = []
    for d in range(-k, k + 1):
        m = min(max(n + d, N0), N1)
        vals.append(PICK[str(m)][key][0])
    ref = vals[k]
    vs = [(v - ref + 180) % 360 - 180 for v in vals]
    return ref + sum(vs) / len(vs), PICK[str(n)][key][1]

def tun_series(field, lo, hi):
    arr = np.array([TUN[str(n)][field] for n in range(N0, N1 + 1)], float)
    arr = np.where((arr < lo) | (arr > hi), np.nan, arr)
    idx = np.arange(len(arr))
    good = ~np.isnan(arr)
    arr = np.interp(idx, idx[good], arr[good])
    # monotone non-decreasing (tunnels only grow)
    arr = np.maximum.accumulate(arr)
    return arr

UPR = tun_series('up', 240, 300)
LOR = tun_series('lo', 300, 460)
LOR = np.minimum(np.maximum(LOR, 346), 445)

def shaft_depth(n):
    return float(np.clip((n - 157) * 4.3, 0, 106))

def draw_shaft(img, cam, n):
    d = shaft_depth(n)
    if d <= 1: return
    x0, x1 = 190, 262
    top = 572
    pts = [(x0, top - 3), (x1, top - 3)]
    steps = max(2, int(d / 12))
    for i in range(steps + 1):
        y = top + d * i / steps
        pts.append((x1 + (4 if i % 2 else -3), y))
    for i in range(steps, -1, -1):
        y = top + d * i / steps
        pts.append((x0 + (-4 if i % 2 else 3), y))
    poly(img, pts, cam, fill=(112, 64, 28, 255), outline=(70, 38, 16, 255), width=2.4)

def flash_level(n):
    a = np.array(Image.open(f'A_all/f{n:03d}.png').convert('RGB'))
    lo = int(LOR[n - N0])
    reg = a[690:860, max(0, lo - 10):lo + 70]
    m = (reg[..., 0] > 250) & (reg[..., 1] > 225) & (reg[..., 2] > 150)
    return float(min(1.0, m.mean() * 6))

import os
BLUR = int(os.environ.get('BLUR', '1'))

from stickreel.chop import YOU_KEYS, chop_pose
from scipy.ndimage import gaussian_filter1d
CONTACT = {'y': [9, 30, 54, 84, 106, 127, 148], 'f': [13 + 18 * k for k in range(9)]}
HIPX = {k: gaussian_filter1d(np.array([FIT[str(n)][k][0] for n in range(N0, N1 + 1)], float), 4, mode='nearest') for k in ('f', 'y')}
HIPY = {'f': 496.0, 'y': 787.0}

def cycle_t(key, t):
    c = CONTACT[key]
    if t < c[0]:
        L = c[1] - c[0]
        return 4 + (t - c[0]) * 22.0 / L
    for i in range(len(c) - 1):
        if t < c[i + 1] or i == len(c) - 2:
            L = c[i + 1] - c[i]
            return 4 + (t - c[i]) * 22.0 / L
    return 4.0

def pose_at(key, t):
    t = min(max(t, N0), N1)
    hx = float(np.interp(t, np.arange(N0, N1 + 1), HIPX[key]))
    return chop_pose(YOU_KEYS, cycle_t(key, t), hx, HIPY[key])

def render_frame(n):
    cam = Cam()
    img = new_canvas()
    B.UP_TUNNEL = dict(top=390, bot=572, right=float(UPR[n - N0]))
    B.LO_TUNNEL = dict(top=678, bot=862, right=float(LOR[n - N0]))
    draw_sky(img, cam); draw_dirt(img, cam)
    draw_tunnel(img, B.UP_TUNNEL, cam, 428); draw_tunnel(img, B.LO_TUNNEL, cam, 715)
    draw_shaft(img, cam, n)
    draw_wall(img, cam); draw_sign(img, cam); draw_token(img, TOKEN_C, 33, cam)
    draw_hook(img, cam)
    fl = flash_level(n)
    if fl > 0.05:
        lo = float(LOR[n - N0])
        glow(img, (lo + 10, 755), 46, cam, (255, 214, 120), 0.8 * fl, 1.3)
        glow(img, (lo + 10, 755), 16, cam, (255, 250, 220), 0.95 * fl, 1.0)
    poses = {k: pose_at(k, n) for k in ('f', 'y')}
    if BLUR <= 1:
        for key in ('f', 'y'):
            draw_figure(img, poses[key], cam)
    else:
        offs = [(-0.5 + (i + 0.5) / BLUR) for i in range(BLUR)]
        acc = None
        for o in offs:
            layer = img.copy()
            for key in ('f', 'y'):
                draw_figure(layer, pose_at(key, n + o), cam)
            arr = np.asarray(layer.convert('RGB'), dtype=np.float32)
            acc = arr if acc is None else acc + arr
        img = Image.fromarray((acc / len(offs)).astype(np.uint8)).convert('RGBA')
    for key, name in (('f', 'FRIEND'), ('y', 'YOU')):
        h = poses[key]['head']
        draw_label(img, name, (h[0] + 1, h[1] - 34), cam)
    if n >= 205:
        text(img, 'ONE MORE GAME.', (270, 639), 22, cam, fill=(255, 246, 226, 255), outline=(60, 38, 20, 255), ow=1.8, weight=800, width=246)
    return img.convert('RGB').resize((576, 1024), Image.LANCZOS)

if __name__ == '__main__':
    a, b = int(sys.argv[1]), int(sys.argv[2])
    import os
    os.makedirs('out_dig', exist_ok=True)
    t = time.time()
    for n in range(a, b + 1):
        render_frame(n).save(f'out_dig/m{n:03d}.png')
    print('done', (time.time() - t) / (b - a + 1), 's/frame')
