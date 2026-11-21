"""Keyframe tracks. A thing (actor, object, camera) has static props plus `keys`:

    {"t": 1.5, "x": 300, "ease": "out"}      # values arrive at t; unspecified props keep their last value

Values can be numbers, lists of numbers, "#rrggbb" colours (blended), or anything else (strings, null, true: they
switch when the key time is reached). `ease` is the curve of the segment that ENDS at this key; `eases` can set a
different curve per property: {"eases": {"x": "linear"}}.
"""
from .ease import ease


class SceneError(ValueError):
    pass


def is_color(v):
    return isinstance(v, str) and len(v) in (4, 7, 9) and v.startswith("#")


def parse_color(v):
    h = v[1:]
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    a = 255 if len(h) == 6 else int(h[6:8], 16)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


def to_hex(c):
    return "#%02x%02x%02x%02x" % tuple(max(0, min(255, int(round(x)))) for x in c)


def blend(a, b, u):
    """value between a and b at 0..1, or None if they do not blend (caller then steps)."""
    if isinstance(a, bool) or isinstance(b, bool):
        return None
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a + (b - a) * u
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)) and len(a) == len(b):
        out = []
        for x, y in zip(a, b):
            v = blend(x, y, u)
            if v is None:
                return None
            out.append(v)
        return out
    if is_color(a) and is_color(b):
        ca, cb = parse_color(a), parse_color(b)
        return to_hex([x + (y - x) * u for x, y in zip(ca, cb)])
    return None


class Track:
    """all props of one thing over time."""

    def __init__(self, static, keys, where="?", defaults=None):
        self.static = dict(static)
        self.keys = sorted(keys, key=lambda k: k["t"])
        self.where = where
        for k in self.keys:
            if "t" not in k or not isinstance(k["t"], (int, float)):
                raise SceneError(f"{where}: every key needs a numeric 't' (seconds): {k}")
        self.props = set(self.static)
        for k in self.keys:
            self.props |= {p for p in k if p not in ("t", "ease", "eases")}
        # per-prop timeline: [(t, value, ease)]
        self.lines = {p: [] for p in self.props}
        for k in self.keys:
            for p, v in k.items():
                if p in ("t", "ease", "eases"):
                    continue
                e = (k.get("eases") or {}).get(p, k.get("ease", "inout"))
                if e not in __import__("stickreel.ease", fromlist=["EASES"]).EASES:
                    raise SceneError(f"{where}: unknown ease '{e}' at t={k['t']}. Known: "
                                     + ", ".join(__import__("stickreel.ease", fromlist=["EASES"]).EASES))
                self.lines[p].append((k["t"], v, e))
        # A property first mentioned in a later key starts from its default/static value at the key BEFORE it, so
        # it neither holds its final value backwards in time nor creeps from t=0.
        defaults = defaults or {}
        for p, ln in self.lines.items():
            if not ln:
                continue
            first_t = ln[0][0]
            earlier = [k["t"] for k in self.keys if k["t"] < first_t]
            have = p in self.static or p in defaults
            base = self.static.get(p, defaults.get(p))
            if earlier and have:
                ln.insert(0, (earlier[-1], base, "linear"))

    def get(self, prop, t, default=None):
        ln = self.lines.get(prop)
        if not ln:
            return self.static.get(prop, default)
        if t <= ln[0][0]:
            return ln[0][1] if not (self.static.get(prop) is not None and False) else self.static[prop]
        if t >= ln[-1][0]:
            return ln[-1][1]
        # find segment
        lo, hi = 0, len(ln) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if ln[mid][0] <= t:
                lo = mid
            else:
                hi = mid
        (t0, v0, _), (t1, v1, e1) = ln[lo], ln[hi]
        u = (t - t0) / max(t1 - t0, 1e-9)
        b = blend(v0, v1, ease(e1, u))
        if b is None:
            return v0 if ease("step", u) < 1 else v1
        return b

    def times(self, prop):
        return [x[0] for x in self.lines.get(prop, [])]
