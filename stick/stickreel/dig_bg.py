"""Static artwork for the dig skit: sky, sun, dirt, tunnels, gold wall, sign. Everything in reference space."""
import math
import random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from .engine import *

UP_TUNNEL = dict(top=390, bot=572, right=252)      # x grows to the right edge, left edge is off screen
LO_TUNNEL = dict(top=678, bot=862, right=342)
WALL_X0 = 458                                       # left edge of the gold wall (jagged)
WALL_Y0, WALL_Y1 = 368, 885
TOKEN_C = (510, 757)


def zigzag_x(base, y, y0, y1, amp=6.0, n=9):
    """jagged right-hand edge of a tunnel: x as a function of y."""
    u = (y - y0) / (y1 - y0)
    return base + (amp if int(u * n * 2) % 2 == 0 else -amp * 0.6)


def tunnel_poly(t, n=9):
    pts = [(-10, t["top"]), (t["right"] + 6, t["top"])]
    for i in range(1, n + 1):
        y = t["top"] + (t["bot"] - t["top"]) * i / n
        pts.append((t["right"] + (6 if i % 2 == 0 else -3), y - (t["bot"] - t["top"]) / n * 0.5))
        pts.append((t["right"] + (-3 if i % 2 == 0 else 6), y))
    pts.append((-10, t["bot"]))
    return pts


def draw_sky(img, cam, sun_pulse=0.0):
    vgrad(img, 0, 290, [(0, "#443d6f"), (0.21, "#634a79"), (0.345, "#98648a"), (0.59, "#c5777e"), (0.71, "#dd9074"), (1.0, "#f5ac6c")], cam, x0=-400, x1=1000)
    # rays from the sun
    sun = (395, 178)
    rays = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(rays)
    sx, sy = cam.p(*sun)
    for i in range(14):
        a = math.radians(-180 + i * (180 / 13))
        w = math.radians(2.6 if i % 2 else 4.2)
        L = cam.k(460)
        P = [(sx, sy), (sx + math.cos(a - w) * L, sy + math.sin(a - w) * L), (sx + math.cos(a + w) * L, sy + math.sin(a + w) * L)]
        d.polygon(P, fill=(255, 235, 190, 34))
    hz = cam.p(0, 285)[1]
    rays.paste((0, 0, 0, 0), (0, int(hz), img.size[0], img.size[1]))
    img.alpha_composite(rays)
    glow(img, sun, 150, cam, (255, 214, 140), 0.55 + sun_pulse, 1.6)
    glow(img, sun, 62, cam, (255, 244, 205), 0.9, 1.2)
    circle(img, sun, 36, cam, fill=(255, 246, 214, 255))
    # clouds
    for cx, cy, w in ((92, 20, 62), (447, 38, 48), (240, 78, 36)):
        for dx, dy, rx, ry in ((0, 0, w, w * 0.26), (-w * 0.35, w * 0.08, w * 0.55, w * 0.2), (w * 0.4, w * 0.06, w * 0.5, w * 0.19)):
            ellipse(img, (cx + dx, cy + dy), rx, ry, cam, fill=(236, 140, 176, 255))
        ellipse(img, (cx, cy - w * 0.08), w * 0.7, w * 0.14, cam, fill=(246, 172, 196, 255))
    # hills
    pts = [(-400, 262), (0, 262), (40, 250), (90, 246), (150, 258), (220, 268), (300, 262), (380, 252), (450, 258), (520, 246), (576, 252), (1000, 256),
           (1000, 290), (-400, 290)]
    poly(img, pts, cam, fill=(150, 76, 160, 255))
    poly(img, [(-400, 276), (80, 268), (180, 280), (300, 276), (420, 280), (576, 270), (1000, 272), (1000, 290), (-400, 290)], cam,
         fill=(122, 62, 150, 255))
    # grass line
    poly(img, [(-400, 285), (1000, 285), (1000, 294), (-400, 294)], cam, fill=(98, 184, 62, 255))
    line(img, (-400, 285.5), (1000, 285.5), cam, (58, 110, 40, 255), 1.4, cap=False)
    line(img, (-400, 294), (1000, 294), cam, (92, 56, 20, 255), 1.4, cap=False)


def draw_dirt(img, cam):
    vgrad(img, 293, 1400, [(0, "#dcac5e"), (0.16, "#d2a053"), (0.5, "#bc8840"), (1.0, "#b3813a")], cam, x0=-400, x1=1000)
    rnd = random.Random(11)
    spots = [(35, 355, 11, 8), (272, 340, 26, 17), (330, 390, 13, 20), (433, 375, 13, 15), (24, 592, 10, 9),
             (305, 548, 25, 16), (130, 612, 12, 9), (410, 690, 9, 20), (432, 640, 18, 22), (52, 930, 20, 13),
             (130, 915, 14, 10), (250, 960, 18, 12), (350, 935, 16, 10), (475, 985, 20, 14), (360, 990, 12, 9),
             (115, 985, 15, 11), (205, 900, 11, 7), (540, 930, 12, 8), (60, 640, 11, 8), (180, 625, 10, 6)]
    for x, y, rx, ry in spots:
        ellipse(img, (x, y), rx, ry, cam, fill=(206, 138, 60, 255), outline=(190, 120, 46, 255), width=1.5, rot=0.35)
        ellipse(img, (x - rx * 0.1, y - ry * 0.15), rx * 0.62, ry * 0.5, cam, fill=(224, 158, 74, 255), rot=0.35)


def draw_tunnel(img, t, cam, orb_y):
    pts = tunnel_poly(t)
    # shadowed body, lighter toward the bottom
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).polygon([cam.p(*p) for p in pts], fill=255)
    top_y, bot_y = cam.p(0, t["top"])[1], cam.p(0, t["bot"])[1]
    H = img.size[1]
    ts = np.clip((np.arange(H) - top_y) / max(1.0, bot_y - top_y), 0, 1)
    c0, c1 = np.array([104, 58, 24]), np.array([150, 90, 42])
    col = (c0[None, :] * (1 - ts[:, None]) + c1[None, :] * ts[:, None]).astype(np.uint8)
    arr = np.repeat(col[:, None, :], img.size[0], axis=1)
    img.paste(Image.fromarray(arr, "RGB").convert("RGBA"), (0, 0), mask)
    poly(img, pts, cam, outline=(70, 38, 16, 255), width=2.6)
    # dark top lip
    poly(img, [(-10, t["top"]), (t["right"] + 5, t["top"]), (t["right"] + 5, t["top"] + 9), (-10, t["top"] + 9)], cam,
         fill=(86, 46, 18, 120))
    glow(img, (53, orb_y), 38, cam, (255, 196, 110), 0.7, 1.4)
    glow(img, (53, orb_y), 15, cam, (255, 244, 206), 0.9, 1.0)


def coin_positions(seed=5):
    rnd = random.Random(seed)
    out = []
    for _ in range(210):
        x = rnd.uniform(WALL_X0 + 8, 700)
        y = rnd.uniform(WALL_Y0 + 6, WALL_Y1 - 6)
        # leave the token clear
        if math.hypot(x - TOKEN_C[0], y - TOKEN_C[1]) < 40:
            continue
        # keep inside the jagged left edge
        edge = WALL_X0 + 10 + 8 * math.sin(y * 0.21)
        if x < edge:
            continue
        out.append((x, y, rnd.choice([7.0, 8.0, 9.0, 10.0])))
    return out


COINS = coin_positions()
SPARKS = [(600, 450, 8), (640, 560, 7), (610, 700, 8), (650, 820, 7), (558, 408, 8), (488, 455, 7), (527, 543, 9), (515, 572, 7), (505, 672, 9), (470, 742, 8), (528, 790, 9),
          (466, 590, 6), (557, 705, 6), (500, 405, 6), (545, 860, 7)]


def draw_wall(img, cam):
    pts = [(WALL_X0 + 8 * math.sin(y * 0.21) + 6, y) for y in range(WALL_Y0, WALL_Y1 + 1, 9)]
    full = pts + [(720, WALL_Y1), (720, WALL_Y0)]
    poly(img, full, cam, fill=(66, 38, 16, 255), outline=(40, 22, 8, 255), width=2.2)
    glow(img, (500, 640), 160, cam, (90, 50, 14), 0.25, 1.0)
    for x, y, r in COINS:
        circle(img, (x, y), r, cam, fill=(246, 196, 40, 255), outline=(120, 74, 12, 255), width=1.4)
        circle(img, (x - r * 0.12, y - r * 0.12), r * 0.62, cam, fill=(255, 226, 112, 255))
        circle(img, (x, y), r * 0.3, cam, fill=(226, 160, 28, 255))
    for x, y, r in SPARKS:
        star(img, (x, y), r, cam)


def draw_token(img, c, r, cam, glow_k=1.0):
    glow(img, c, r * 2.6, cam, (255, 214, 110), 0.7 * glow_k, 1.4)
    circle(img, c, r, cam, fill=(250, 200, 48, 255), outline=(150, 96, 14, 255), width=2.6)
    circle(img, c, r * 0.84, cam, fill=(255, 224, 104, 255), outline=(206, 140, 24, 255), width=1.6)
    circle(img, c, r * 0.68, cam, fill=(222, 156, 30, 255))
    # skull and crossbones
    x, y = c
    line(img, (x - r * 0.4, y + r * 0.34), (x + r * 0.4, y - r * 0.05), cam, (255, 238, 170, 255), r * 0.1)
    line(img, (x + r * 0.4, y + r * 0.34), (x - r * 0.4, y - r * 0.05), cam, (255, 238, 170, 255), r * 0.1)
    circle(img, (x, y - r * 0.12), r * 0.3, cam, fill=(255, 238, 170, 255))
    circle(img, (x - r * 0.1, y - r * 0.13), r * 0.07, cam, fill=(150, 96, 14, 255))
    circle(img, (x + r * 0.1, y - r * 0.13), r * 0.07, cam, fill=(150, 96, 14, 255))


def draw_sign(img, cam, text_alpha=255):
    line(img, (472, 285), (472, 304), cam, (60, 36, 18, 255), 2.0, cap=False)
    line(img, (543, 285), (543, 304), cam, (60, 36, 18, 255), 2.0, cap=False)
    poly(img, [(446, 303), (572, 303), (572, 356), (446, 356)], cam, fill=(190, 122, 52, 255), outline=(60, 32, 12, 255), width=3.0)
    poly(img, [(452, 309), (566, 309), (566, 350), (452, 350)], cam, outline=(224, 160, 84, 255), width=1.6)
    text(img, "PIRATE", (508, 317), 19, cam, fill=(255, 244, 226, 255), outline=(60, 32, 12, 255), ow=1.6, weight=800, width=88)
    text(img, "TOKEN", (509, 337), 19, cam, fill=(255, 244, 226, 255), outline=(60, 32, 12, 255), ow=1.6, weight=800, width=82)


def draw_background(img, cam, token=True, labels_alpha=1.0):
    draw_sky(img, cam)
    draw_dirt(img, cam)
    draw_tunnel(img, UP_TUNNEL, cam, 428)
    draw_tunnel(img, LO_TUNNEL, cam, 715)
    draw_wall(img, cam)
    draw_sign(img, cam)
    if token:
        draw_token(img, TOKEN_C, 33, cam)


def draw_hook(img, cam):
    text(img, "THIS TIME IT ENDS", (288, 101), 24, cam, fill=(255, 250, 238, 255), outline=(76, 50, 40, 255), ow=2.2,
         weight=800, width=300)
    text(img, "DIFFERENTLY.", (289, 151), 40, cam, fill=(255, 255, 255, 255), outline=(78, 52, 38, 255), ow=3.0,
         weight=900, grad=("#fff6d8", "#e8c98a"), width=352)


def draw_label(img, name, c, cam, alpha=1.0):
    text(img, name, c, 14, cam, fill=(255, 246, 226, 255), outline=(70, 44, 24, 255), ow=1.6, weight=800,
         width={"FRIEND": 84, "YOU": 44}.get(name, 70), alpha=alpha)
