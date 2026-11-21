"""Scene file loading, validation and evaluation (time -> things to draw). See `python -m stickreel docs`."""
import difflib
import importlib
import json
import math
import os
import numpy as np

from .ease import periodic_pchip
from .poses import POSES, LOOPS
from .skeleton import DEFAULTS, LIMBS, pad_limb, solve
from .faces import FACES
from .track import Track, SceneError

CANVAS_DEFAULT = dict(w=576, h=1024, fps=30, duration=5.0, scale=2.0, bg="#000000", blur=1)
COMMON = dict(z=0, show=None, alpha=1.0, space="world", follow=None, offset=[0, 0], blend="normal", grow=None)

# kind -> default props. Anything not listed here is rejected, with a did-you-mean hint.
KINDS = {
    "rect": dict(x=288, y=512, w=100, h=100, rot=0, fill="#ffffff", outline=None, ow=2, anchor="center"),
    "circle": dict(x=288, y=512, r=40, fill="#ffffff", outline=None, ow=2),
    "ellipse": dict(x=288, y=512, rx=50, ry=30, rot=0, fill="#ffffff", outline=None, ow=2),
    "line": dict(x=0, y=0, x2=100, y2=100, color="#ffffff", width=3),
    "poly": dict(points=[[0, 0], [50, 0], [25, 40]], x=0, y=0, rot=0, scale=1.0, fill="#ffffff", outline=None, ow=2),
    "text": dict(text="TEXT", x=288, y=512, size=24, fill="#ffffff", outline="#000000", ow=2, track=0.0, width=None,
                 weight=800, grad=None, shadow=None, align="center", reveal=None),
    "glow": dict(x=288, y=512, r=60, color="#ffd27a", strength=0.8, power=1.5),
    "ring": dict(x=288, y=512, r=50, w=3, color="#ffffff"),
    "rays": dict(x=288, y=512, r0=20, r1=200, n=16, w=3, color="#ffffff", rot=0),
    "star": dict(x=288, y=512, r=8, color="#ffffff", thin=0.18),
    "sprite": dict(file=None, x=288, y=512, scale=1.0, rot=0),
    "pick": dict(x=288, y=512, angle=-45, len=64),
    "phone": dict(x=288, y=512, rot=-90, w=26, h=48, scale=1.0, color="#2a2a30", grip_at=0.35, video=None, video_start=0.0,
                  video_speed=1.0, loop=True, screen_color="#101018", len=48),
    "burst": dict(times=[], at=[288, 512], n=10, speed=[40, 140], angle=[-150, -30], gravity=420, life=0.5,
                  size=[1.5, 3.5], color="#8a5a2a", seed=1),
    "pulse": dict(times=[], at=[288, 512], r=[46, 16], color=["#ffd278", "#fffadc"], strength=[0.8, 0.95], dur=0.18),
    "art": dict(name=None),
}
ACTOR_EXTRA = ("keys", "kind")


def _suggest(name, options):
    m = difflib.get_close_matches(name, list(options), n=3, cutoff=0.5)
    return f" Did you mean: {', '.join(m)}?" if m else ""


def _check(where, props, allowed):
    for p in props:
        if p not in allowed:
            raise SceneError(f"{where}: unknown property '{p}'.{_suggest(p, allowed)} Allowed: {', '.join(sorted(allowed))}")


EFFECTORS = ("hand_r", "hand_l", "foot_r", "foot_l")


def _norm_actor_key(k, poses, where):
    """expand `pose`, and make reach targets switch their own weight on/off."""
    k = dict(k)
    if "pose" in k:
        name = k.pop("pose")
        if name not in poses:
            raise SceneError(f"{where}: unknown pose '{name}'.{_suggest(name, poses)} Known: {', '.join(poses)}")
        base = {p: DEFAULTS[p] for p in ("arm_r", "arm_l", "leg_r", "leg_l", "lean", "head", "rot")}
        base.update(poses[name])
        for p, v in base.items():
            k.setdefault(p, v)
    if "face" in k:
        f = k.pop("face")
        if f not in ("left", "right"):
            raise SceneError(f"{where}: 'face' is 'left' or 'right' (or use numeric 'yaw' in degrees), got {f!r}")
        k.setdefault("yaw", 180.0 if f == "left" else 0.0)
    for limb in LIMBS:
        if limb in k and k[limb] is not None:
            k[limb] = pad_limb(limb, k[limb])
    for e in EFFECTORS:
        for suffix in ("_at", "_rel"):
            if e + suffix in k:
                if k[e + suffix] is None:
                    k.pop(e + suffix)
                    k.setdefault(e + "_w", 0.0)
                else:
                    k.setdefault(e + "_w", 1.0)
    if any(k.get(e + "_at") is not None for e in ("hand_r", "hand_l")) and "grip_rel" not in k and "grip_w" not in k:
        k["grip_w"] = 0.0                       # an explicit hand target releases any two-handed grip
    if "grip_rel" in k:
        if k["grip_rel"] is None:
            k.pop("grip_rel")
            k.setdefault("grip_w", 0.0)
        else:
            k.setdefault("grip_w", 1.0)
    if "grip" in k:
        raise SceneError(f"{where}: use 'grip_rel': [dx, dy] (hip-relative) for a two-handed grip, not 'grip'")
    return k


def _prop_lookup(d, key):
    return d[key] if key in d else None


class Actor:
    def __init__(self, name, spec, scene):
        self.name, self.scene = name, scene
        spec = dict(spec)
        keys = spec.pop("keys", [])
        spec.pop("kind", None)
        where = f"actor '{name}'"
        _check(where, list(spec), set(DEFAULTS) | set(ACTOR_EXTRA) | {"face"})
        self.segs = []                                  # anim segments
        nkeys = []
        for i, k in enumerate(keys):
            w = f"{where} key {i} (t={k.get('t')})"
            _check(w, [p for p in k if p not in ("pose", "hits", "ease", "eases", "t")], set(DEFAULTS) | {"face"})
            k = _norm_actor_key(k, scene.poses, w)
            hits = k.pop("hits", None)
            if "anim" in k:
                a = k["anim"]
                if a is not None and a not in scene.loops:
                    raise SceneError(f"{w}: unknown anim '{a}'.{_suggest(a, scene.loops)} Known: {', '.join(scene.loops)}")
                self.segs.append(dict(t=k["t"], name=a, hits=sorted(hits) if hits else None))
            elif hits is not None:
                raise SceneError(f"{w}: 'hits' only goes with an 'anim' in the same key")
            nkeys.append(k)
        self.segs.sort(key=lambda s: s["t"])
        static = _norm_actor_key(spec, scene.poses, where) if spec else {}
        self.track = Track(static, nkeys, where, DEFAULTS)
        self._dist = None
        self._cache = {}

    # ---- parameters over time
    def base(self, t):
        return {p: self.track.get(p, t, DEFAULTS[p]) for p in DEFAULTS}

    def dist(self, t):
        if self._dist is None:
            step = 1 / 120
            n = int(self.scene.duration / step) + 2
            xs = np.array([self.track.get("x", i * step, DEFAULTS["x"]) for i in range(n)])
            self._dist = (step, np.concatenate([[0.0], np.cumsum(np.abs(np.diff(xs)))]))
        step, cum = self._dist
        return float(np.interp(t / step, np.arange(len(cum)), cum))

    def phase(self, loop, seg, t, speed):
        if loop["source"] == "distance":
            return ((self.dist(t) - self.dist(seg["t"])) / loop["stride"]) % 1.0
        hits = seg.get("hits")
        if loop["source"] == "hits" and hits:
            ph = loop["hit_phase"]
            if len(hits) == 1:
                return (ph + (t - hits[0]) / loop["period"]) % 1.0
            i = 0
            while i < len(hits) - 2 and t >= hits[i + 1]:
                i += 1
            return (ph + (t - hits[i]) / (hits[i + 1] - hits[i])) % 1.0
        return ((t - seg["t"]) * speed / loop["period"]) % 1.0

    def loop_values(self, loop, phase):
        out = {}
        props = {}
        for k in loop["keys"]:
            for p, v in k.items():
                if p != "t":
                    props.setdefault(p, []).append((k["t"], v))
        for p, pts in props.items():
            xs = [a for a, _ in pts]
            vals = [b for _, b in pts]
            if isinstance(vals[0], (list, tuple)):
                out[p] = [periodic_pchip(xs, [v[i] for v in vals], 1.0, phase) for i in range(len(vals[0]))]
            elif isinstance(vals[0], (int, float)):
                out[p] = periodic_pchip(xs, vals, 1.0, phase)
        return out

    def params(self, t):
        key = round(t, 6)
        if key in self._cache:
            return self._cache[key]
        base = self.base(t)
        res = base
        idx = -1
        for i, s in enumerate(self.segs):
            if s["t"] <= t:
                idx = i
        if idx >= 0:
            cur = self.segs[idx]
            prev = self.segs[idx - 1] if idx > 0 else None
            bl = max(base["anim_blend"], 1e-3)
            w = 1.0 if (cur["t"] <= 0 and prev is None) else min(max((t - cur["t"]) / bl, 0.0), 1.0)
            w = w * w * (3 - 2 * w)

            def applied(seg):
                if seg is None or seg["name"] is None:
                    return base
                loop = self.scene.loops[seg["name"]]
                vals = self.loop_values(loop, self.phase(loop, seg, t, base["anim_speed"]))
                out = dict(base)
                for p, v in vals.items():
                    b = base[p]
                    if isinstance(v, list):
                        o = list(b)
                        for i, y in enumerate(v):
                            o[i] = (o[i] + y) if loop["mode"] == "add" else y
                        out[p] = o
                    else:
                        out[p] = b + v if loop["mode"] == "add" else v
                return out

            a, b = applied(prev), applied(cur)
            res = dict(base)
            for p in DEFAULTS:
                va, vb = a[p], b[p]
                if isinstance(va, list) and isinstance(vb, list):
                    res[p] = [x + (y - x) * w for x, y in zip(va, vb)]
                elif isinstance(va, (int, float)) and isinstance(vb, (int, float)) and not isinstance(va, bool):
                    res[p] = va + (vb - va) * w
                else:
                    res[p] = vb if w >= 0.5 else va
        self._cache[key] = res
        return res

    def hit_times(self):
        out = []
        for i, s in enumerate(self.segs):
            end = self.segs[i + 1]["t"] if i + 1 < len(self.segs) else 1e9
            out += [h for h in (s.get("hits") or []) if s["t"] <= h < end]
        return sorted(out)

    def solve(self, t):
        p = self.params(t)
        pose, anch = solve(p, lambda ref: self.scene.resolve(ref, t, exclude=self.name))
        c = anch["cos_yaw"]

        def world_angle(a):                            # item angle in facing space -> screen angle
            r = math.radians(a)
            return math.degrees(math.atan2(math.sin(r), math.cos(r) * c))

        anch["prop_angle_world"] = world_angle(p["prop_angle"])
        anch["prop_l_angle_world"] = world_angle(p["prop_l_angle"])
        anch["tip"] = anch["grip"]
        obj = self.scene.objects.get(p["prop"]) if p["prop"] else None
        if obj is not None and obj.kind in ("pick", "phone"):
            pr = obj.props(t)
            ln = pr["len"] if obj.kind == "pick" else pr["h"] * pr["scale"] * (1 - pr.get("grip_at", 0.35))
            a = math.radians(anch["prop_angle_world"])
            base = anch["grip"] if p["prop_hand"] in ("auto", "grip") else anch["hand_" + p["prop_hand"]]
            anch["tip"] = (base[0] + math.cos(a) * ln, base[1] + math.sin(a) * ln)
        return pose, anch, p


class Obj:
    def __init__(self, name, spec, scene):
        self.name, self.scene = name, scene
        spec = dict(spec)
        self.kind = spec.pop("kind", None)
        if self.kind not in KINDS:
            raise SceneError(f"object '{name}': unknown kind '{self.kind}'.{_suggest(str(self.kind), KINDS)} Known: {', '.join(KINDS)}")
        keys = spec.pop("keys", [])
        self.defaults = dict(COMMON)
        self.defaults.update(KINDS[self.kind])
        if self.kind == "art":
            self.defaults.update({k: None for k in spec if k not in self.defaults})
        allowed = set(self.defaults)
        _check(f"object '{name}' ({self.kind})", list(spec), allowed)
        for i, k in enumerate(keys):
            _check(f"object '{name}' key {i} (t={k.get('t')})", [p for p in k if p not in ("t", "ease", "eases")],
                   allowed | ({p for p in k} if self.kind == "art" else set()))
        self.track = Track(spec, keys, f"object '{name}'", self.defaults)
        self.artname = spec.get("name")

    def props(self, t):
        out = {p: self.track.get(p, t, d) for p, d in self.defaults.items()}
        for p in self.track.props:
            if p not in out:
                out[p] = self.track.get(p, t)
        g = out.get("grow")
        if g:
            for gg in (g if isinstance(g, list) else [g]):
                times = self.scene.times(gg["times"])
                tot = 0.0
                for th in times:
                    u = min(max((t - th) / max(gg.get("dur", 0.1), 1e-3), 0.0), 1.0)
                    tot += gg["by"] * u * u * (3 - 2 * u)
                out[gg["prop"]] = out[gg["prop"]] + tot
        if out.get("follow"):
            a = self.scene.resolve(out["follow"], t, exclude=self.name)
            if a is not None:
                off = out["offset"]
                out["x"], out["y"] = a[0] + off[0], a[1] + off[1]
        return out

    def visible(self, t):
        s = self.track.get("show", t, None)
        return s is None or (s[0] <= t < s[1])


class Scene:
    def __init__(self, data, base_dir="."):
        data = dict(data)
        self.base_dir = base_dir
        _check("scene", list(data), {"canvas", "poses", "loops", "camera", "actors", "objects", "plugins", "faces", "note", "meta"})
        self.canvas = dict(CANVAS_DEFAULT)
        _check("canvas", list(data.get("canvas", {})), set(CANVAS_DEFAULT))
        self.canvas.update(data.get("canvas", {}))
        self.duration = float(self.canvas["duration"])
        self.fps = int(self.canvas["fps"])
        self.faces = dict(FACES)
        self.faces.update(data.get("faces", {}))
        self.poses = dict(POSES)
        self.poses.update(data.get("poses", {}))
        self.loops = {k: dict(v) for k, v in LOOPS.items()}
        for k, v in data.get("loops", {}).items():
            v = dict(v)
            v.setdefault("mode", "add")
            v.setdefault("source", "time")
            v.setdefault("period", 1.0)
            v.setdefault("stride", 150)
            v.setdefault("hit_phase", 0.0)
            if "keys" not in v:
                raise SceneError(f"loop '{k}' needs 'keys' (phase 0..1)")
            self.loops[k] = v
        for m in data.get("plugins", []):
            importlib.import_module(m)
        cam = dict(data.get("camera", {}))
        ckeys = cam.pop("keys", [])
        cdef = dict(zoom=1.0, cx=288.0, cy=512.0, tx=288.0, ty=512.0)
        _check("camera", list(cam) + [p for k in ckeys for p in k if p not in ("t", "ease", "eases")], set(cdef))
        self.camera = Track(cam, ckeys, "camera", cdef)
        self.cdef = cdef
        self.objects = {}
        for n, spec in data.get("objects", {}).items():
            self.objects[n] = Obj(n, spec, self)
        self.actors = {}
        for n, spec in data.get("actors", {}).items():
            self.actors[n] = Actor(n, spec, self)
        self._solving = set()
        # objects named by any actor's `prop` are tools: drawn only while held
        self.held_names = {v for a in self.actors.values() for pr in ("prop", "prop_l") for (_, v, _) in a.track.lines.get(pr, []) if v}
        for a in self.actors.values():
            for pr in ("prop", "prop_l"):
                if a.track.static.get(pr):
                    self.held_names.add(a.track.static[pr])
            names = [e[1] for e in a.track.lines.get("expr", [])]
            if a.track.static.get("expr"):
                names.append(a.track.static["expr"])
            for n in names:
                if n not in self.faces:
                    raise SceneError(f"actor '{a.name}': unknown expr '{n}'.{_suggest(n, self.faces)} Known: {', '.join(self.faces)}")

    # ---- references and events
    def times(self, ref):
        if isinstance(ref, list):
            return [float(x) for x in ref]
        if isinstance(ref, str) and ref.endswith(".hit"):
            a = self.actors.get(ref[:-4].lstrip("@"))
            if a is None:
                raise SceneError(f"times '{ref}': no actor named '{ref[:-4]}'. Actors: {', '.join(self.actors)}")
            return a.hit_times()
        raise SceneError(f"times must be a list of seconds or 'actor.hit', got {ref!r}")

    def resolve(self, ref, t, exclude=None):
        name, _, anchor = ref.lstrip("@").partition(".")
        if name in self.actors:
            if name == exclude and name in self._solving:
                return None
            if name in self._solving:
                return None
            self._solving.add(name)
            try:
                pose, anch, _ = self.actors[name].solve(t)
            finally:
                self._solving.discard(name)
            a = anchor or "hip"
            if a not in anch:
                raise SceneError(f"reference '{ref}': actors have anchors {', '.join(k for k in anch if k not in ('face', 'prop_angle_world'))}")
            return anch[a]
        if name in self.objects:
            if name == exclude:
                return None
            pr = self.objects[name].props(t)
            return (pr["x"], pr["y"])
        raise SceneError(f"reference '{ref}': no actor or object '{name}'. Have: {', '.join(list(self.actors) + list(self.objects))}")

    def cam_at(self, t):
        return {p: self.camera.get(p, t, d) for p, d in self.cdef.items()}

    @staticmethod
    def load(path):
        with open(path) as fh:
            return Scene(json.load(fh), os.path.dirname(os.path.abspath(path)))
