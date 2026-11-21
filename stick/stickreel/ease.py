"""Easing functions (0..1 -> 0..1) and a small monotone cubic (PCHIP) for periodic loops. No scipy needed."""
import math
import numpy as np


def _c(u):
    return 0.0 if u < 0 else 1.0 if u > 1 else u


EASES = {
    "linear": lambda u: _c(u),
    "in": lambda u: _c(u) ** 3,
    "out": lambda u: 1 - (1 - _c(u)) ** 3,
    "inout": lambda u: (lambda u: u * u * (3 - 2 * u))(_c(u)),
    "in2": lambda u: _c(u) ** 2,
    "out2": lambda u: 1 - (1 - _c(u)) ** 2,
    "back": lambda u: (lambda u: 1 + 2.70158 * (u - 1) ** 3 + 1.70158 * (u - 1) ** 2)(_c(u)),     # overshoot, then settle
    "backin": lambda u: (lambda u: 2.70158 * u ** 3 - 1.70158 * u ** 2)(_c(u)),                    # pull back first
    "elastic": lambda u: 0.0 if u <= 0 else 1.0 if u >= 1 else 2 ** (-10 * u) * math.sin((u * 10 - 0.75) * (2 * math.pi / 3)) + 1,
    "bounce": lambda u: _bounce(_c(u)),
    "step": lambda u: 1.0 if u >= 1 else 0.0,      # value jumps when the key time is reached
}


def _bounce(u):
    n, d = 7.5625, 2.75
    if u < 1 / d:
        return n * u * u
    if u < 2 / d:
        u -= 1.5 / d
        return n * u * u + 0.75
    if u < 2.5 / d:
        u -= 2.25 / d
        return n * u * u + 0.9375
    u -= 2.625 / d
    return n * u * u + 0.984375


def ease(name, u):
    return EASES[name](u)


def _pchip_slopes(x, y):
    h = np.diff(x)
    d = np.diff(y) / h
    m = np.zeros_like(y)
    m[1:-1] = np.where(d[:-1] * d[1:] > 0, 2 * d[:-1] * d[1:] / (d[:-1] + d[1:] + 1e-12), 0.0)
    m[0] = d[0]
    m[-1] = d[-1]
    return m


def periodic_pchip(xs, ys, period, t):
    """monotone cubic through (xs, ys) repeating every `period`; xs in [0, period), ys same length."""
    xs = np.asarray(xs, float)
    ys = np.asarray(ys, float)
    X = np.concatenate([xs - period, xs, xs + period])
    Y = np.concatenate([ys, ys, ys])
    m = _pchip_slopes(X, Y)
    t = t % period
    i = int(np.searchsorted(X, t, side="right") - 1)
    i = min(max(i, 0), len(X) - 2)
    h = X[i + 1] - X[i]
    s = (t - X[i]) / h
    h00, h10, h01, h11 = 2 * s ** 3 - 3 * s ** 2 + 1, s ** 3 - 2 * s ** 2 + s, -2 * s ** 3 + 3 * s ** 2, s ** 3 - s ** 2
    return float(h00 * Y[i] + h10 * h * m[i] + h01 * Y[i + 1] + h11 * h * m[i + 1])
