"""Doodled faces. Coordinates are in head units: u across (-1 left .. 1 right as seen from the front), v down,
the head circle has radius 1. Primitives (JSON friendly, so scenes can add their own under "faces"):
  ["dot", u, v, rx, ry]                 filled dark ellipse
  ["ellipse", u, v, rx, ry, fill, stroke]   fill/stroke are "#rrggbb[aa]" or null
  ["line", [[u,v],...], width]          dark stroked line (width in head units)
  ["fill", [[u,v],...], "#color"]       filled polygon (colour optional = dark)
A face is a dict: {"parts": [...], "mouth": [...]}. `mouth` is replaced by an animated mouth while `talk` is on.
Seen from the side the features wrap around the head; from behind the face is hidden.
"""
import math

INK = "#34303a"


def arc(u0, u1, v, depth, n=9):
    """curve from u0..u1 at height v bulging by depth (positive = smile)."""
    return [[u0 + (u1 - u0) * i / n, v + depth * (1 - ((2 * i / n - 1) ** 2))] for i in range(n + 1)]


def _eyes(v=0.0, rx=0.085, ry=0.13, gap=0.36):
    return [["dot", -gap, v, rx, ry], ["dot", gap, v, rx, ry]]


def _arch(u, v, w=0.17, up=True):
    h = -0.12 if up else 0.12
    return ["line", arc(u - w, u + w, v + (0.05 if up else -0.05), h, 6), 0.07]


FACES = {
    "calm": dict(parts=_eyes(), mouth=[["line", arc(-0.2, 0.2, 0.42, 0.05), 0.065]]),
    "happy": dict(parts=[_arch(-0.36, 0.02), _arch(0.36, 0.02), ["ellipse", -0.62, 0.3, 0.14, 0.08, "#ff9aa855", None],
                         ["ellipse", 0.62, 0.3, 0.14, 0.08, "#ff9aa855", None]],
                  mouth=[["line", arc(-0.32, 0.32, 0.34, 0.2), 0.07]]),
    "laugh": dict(parts=[_arch(-0.36, 0.0), _arch(0.36, 0.0)],
                  mouth=[["fill", arc(-0.34, 0.34, 0.3, 0.0, 2) + arc(0.34, -0.34, 0.3, 0.42, 8)[1:], INK],
                         ["fill", arc(-0.18, 0.18, 0.58, 0.1, 6), "#e8708a"]]),
    "sad": dict(parts=_eyes(0.05) + [["line", [[-0.55, -0.2], [-0.18, -0.34]], 0.06], ["line", [[0.55, -0.2], [0.18, -0.34]], 0.06],
                                     ["ellipse", -0.4, 0.34, 0.05, 0.1, "#7ec8ff", None]],
                mouth=[["line", arc(-0.22, 0.22, 0.56, -0.12), 0.065]]),
    "angry": dict(parts=_eyes(0.06, 0.08, 0.1) + [["line", [[-0.62, -0.32], [-0.14, -0.12]], 0.09], ["line", [[0.62, -0.32], [0.14, -0.12]], 0.09]],
                  mouth=[["line", [[-0.28, 0.5], [-0.1, 0.42], [0.1, 0.42], [0.28, 0.5]], 0.07]]),
    "scared": dict(parts=[["ellipse", -0.34, 0.0, 0.16, 0.2, "#ffffff", INK], ["ellipse", 0.34, 0.0, 0.16, 0.2, "#ffffff", INK],
                          ["dot", -0.34, 0.02, 0.04, 0.05], ["dot", 0.34, 0.02, 0.04, 0.05],
                          ["line", [[-0.6, -0.34], [-0.2, -0.44]], 0.05], ["line", [[0.6, -0.34], [0.2, -0.44]], 0.05],
                          ["ellipse", 0.78, -0.2, 0.06, 0.12, "#7ec8ff", None]],
                  mouth=[["line", [[-0.26, 0.5], [-0.13, 0.42], [0, 0.5], [0.13, 0.42], [0.26, 0.5]], 0.06]]),
    "surprised": dict(parts=[["ellipse", -0.34, 0.0, 0.14, 0.18, "#ffffff", INK], ["ellipse", 0.34, 0.0, 0.14, 0.18, "#ffffff", INK],
                             ["dot", -0.34, 0.0, 0.05, 0.07], ["dot", 0.34, 0.0, 0.05, 0.07],
                             ["line", arc(-0.55, -0.15, -0.4, -0.1, 6), 0.05], ["line", arc(0.15, 0.55, -0.4, -0.1, 6), 0.05]],
                     mouth=[["ellipse", 0, 0.5, 0.1, 0.15, INK, None]]),
    "smirk": dict(parts=_eyes(0.02) + [["line", [[0.14, -0.3], [0.56, -0.38]], 0.06], ["line", [[-0.56, -0.24], [-0.14, -0.24]], 0.06]],
                  mouth=[["line", [[-0.2, 0.48], [0.05, 0.48], [0.3, 0.36]], 0.065]]),
    "cool": dict(parts=[["fill", [[-0.7, -0.14], [0.7, -0.14], [0.62, 0.16], [0.08, 0.16], [0.0, 0.0], [-0.08, 0.16], [-0.62, 0.16]], "#1d1b22"]],
                 mouth=[["line", arc(-0.18, 0.2, 0.46, 0.06), 0.065]]),
    "sleepy": dict(parts=[["line", [[-0.5, 0.04], [-0.2, 0.04]], 0.07], ["line", [[0.2, 0.04], [0.5, 0.04]], 0.07]],
                   mouth=[["ellipse", 0, 0.5, 0.07, 0.07, INK, None]]),
    "wink": dict(parts=[["dot", -0.36, 0, 0.085, 0.13], _arch(0.36, 0.02, 0.16)],
                 mouth=[["line", arc(-0.3, 0.3, 0.36, 0.17), 0.07]]),
    "dead": dict(parts=[["line", [[-0.5, -0.12], [-0.22, 0.14]], 0.07], ["line", [[-0.5, 0.14], [-0.22, -0.12]], 0.07],
                        ["line", [[0.22, -0.12], [0.5, 0.14]], 0.07], ["line", [[0.22, 0.14], [0.5, -0.12]], 0.07]],
                 mouth=[["line", [[-0.2, 0.5], [0.2, 0.5]], 0.065]]),
    "cry": dict(parts=[["line", arc(-0.52, -0.2, 0.0, -0.1, 6), 0.07], ["line", arc(0.2, 0.52, 0.0, -0.1, 6), 0.07],
                       ["ellipse", -0.38, 0.3, 0.06, 0.2, "#7ec8ff", None], ["ellipse", 0.38, 0.3, 0.06, 0.2, "#7ec8ff", None]],
               mouth=[["fill", arc(-0.26, 0.26, 0.5, -0.2, 8) + arc(0.26, -0.26, 0.5, -0.02, 4)[1:], INK]]),
    "blank": dict(parts=_eyes(0.0, 0.07, 0.07), mouth=[]),
    "love": dict(parts=[["fill", [[-0.36, 0.2], [-0.62, -0.02], [-0.5, -0.16], [-0.36, -0.06], [-0.22, -0.16], [-0.1, -0.02]], "#e8446a"],
                        ["fill", [[0.36, 0.2], [0.1, -0.02], [0.22, -0.16], [0.36, -0.06], [0.5, -0.16], [0.62, -0.02]], "#e8446a"]],
                 mouth=[["line", arc(-0.3, 0.3, 0.38, 0.18), 0.07]]),
    "smug": dict(parts=[["line", [[-0.52, 0.06], [-0.2, 0.06]], 0.07], ["line", [[0.2, 0.06], [0.52, 0.06]], 0.07],
                        ["line", [[-0.56, -0.2], [-0.16, -0.28]], 0.055]],
                 mouth=[["line", arc(-0.22, 0.34, 0.42, 0.1), 0.065]]),
}


def talk_mouth(openness):
    """mouth primitives for talking, openness 0..1."""
    if openness < 0.12:
        return [["line", arc(-0.2, 0.2, 0.44, 0.04), 0.065]]
    ry = 0.06 + 0.2 * openness
    return [["ellipse", 0, 0.46 + ry * 0.3, 0.07 + 0.1 * openness, ry, INK, None]]


def talk_amount(t, seed=0):
    """deterministic flappy mouth: new random target every 1/9 s, smoothed."""
    def r(i):
        x = math.sin(i * 12.9898 + seed * 78.233) * 43758.5453
        return x - math.floor(x)
    s = t * 9.0
    i = math.floor(s)
    u = s - i
    u = u * u * (3 - 2 * u)
    a, b = r(i), r(i + 1)
    v = a + (b - a) * u
    return 0.0 if v < 0.25 else min(1.0, (v - 0.25) / 0.6)
