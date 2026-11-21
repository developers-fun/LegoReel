"""Artwork for the dig-skit recreation (sky, dirt, tunnels, shaft, gold wall, token). Static art; animated by props.
Use: "plugins": ["stickreel.art_dig"] and {"kind":"art","name":"dig_tunnel","right":300,"keys":[...]}."""
from PIL import Image
from . import dig_bg as B
from .render import art
from .engine import poly, glow, circle


@art("dig_sky")
def _sky(img, cam, p, t):
    B.draw_sky(img, cam)


@art("dig_dirt")
def _dirt(img, cam, p, t):
    B.draw_dirt(img, cam)


@art("dig_tunnel")
def _tunnel(img, cam, p, t):
    B.draw_tunnel(img, dict(top=p["top"], bot=p["bot"], right=p["right"]), cam, p["orb_y"])


@art("dig_shaft")
def _shaft(img, cam, p, t):
    d = p["depth"]
    if d <= 1:
        return
    x0, x1, top = p["x0"], p["x1"], p["top"]
    pts = [(x0, top - 3), (x1, top - 3)]
    steps = max(2, int(d / 12))
    for i in range(steps + 1):
        pts.append((x1 + (4 if i % 2 else -3), top + d * i / steps))
    for i in range(steps, -1, -1):
        pts.append((x0 + (-4 if i % 2 else 3), top + d * i / steps))
    poly(img, pts, cam, fill=(112, 64, 28, 255), outline=(70, 38, 16, 255), width=2.4)


@art("dig_wall")
def _wall(img, cam, p, t):
    B.draw_wall(img, cam)


@art("dig_sign")
def _sign(img, cam, p, t):
    B.draw_sign(img, cam)


@art("dig_token")
def _token(img, cam, p, t):
    B.draw_token(img, (p["x"], p["y"]), p["r"], cam, p.get("glow", 1.0))


@art("dig_pile")
def _pile(img, cam, p, t):
    import random
    rnd = random.Random(4)
    for i in range(16):
        x = p["x"] + rnd.uniform(-34, 34)
        y = p["y"] - abs(rnd.uniform(0, 1)) ** 1.5 * 9 - (1 - abs(x - p["x"]) / 34) * 4
        circle(img, (x, y), rnd.uniform(5, 7), cam, fill=(246, 196, 40, 255), outline=(120, 74, 12, 255), width=1.2)
