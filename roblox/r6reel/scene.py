"""Scene: the complete description of one video (Python API and JSON), plus frame composition and rendering.

A Scene holds: sets (worlds/locations), characters with action tracks, props, shots (camera + transition),
captions, fx and global post.  ``Scene.frame(t)`` is a pure function of t returning everything the renderer
needs; ``Scene.render()`` writes an mp4.  See docs/SCENE_SCHEMA.md for the JSON format.
"""
from __future__ import annotations

import copy
import json
import math
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import numpy as np

from . import presets as PR
from . import camera as C
from . import transitions as T
from .timeline import Shot, Timeline, SHOT_KINDS, TRANSITION_TYPES

SCHEMA_VERSION = 1
AVATAR_KEYS = {"skin", "shirt", "pants", "shirt_color", "pants_color", "face", "hair", "hair_color", "accessories",
                "body_colors", "scale"}
ACTION_TYPES = ("play", "move_to", "look_at", "face", "turn", "place")


def _t(v):
    return None if v is None else round(float(v), 5)


class _Ctx:
    """What timeline.build_camera needs from the scene."""

    def __init__(self, scene):
        self.s = scene
        self.aspect = scene.width / scene.height

    def resolver(self, name, t):
        return self.s._resolve_point(name, t)

    def char_pos(self, name, t):
        return self.s._anim(name).position_at(t)

    def char_facing(self, name, t):
        return self.s._anim(name).facing_at(t)

    def char_height(self, name):
        return 5.0 * float(self.s._char_spec(name).get("avatar", {}).get("scale", 1.0))

    def prop_pos(self, name, t):
        return self.s._prop_state(name, t)[0]

    def cam_side(self, set_name):
        return self.s._set(set_name)["cam_side"]

    def first_char(self, set_name):
        for c in self.s.characters:
            if c.get("sets") is None or set_name in c["sets"]:
                return c["name"]
        return self.s.characters[0]["name"] if self.s.characters else [0, 0, 0]


class Scene:
    """Python API + JSON for a whole video.

    >>> s = Scene(width=720, height=1280, world="street")
    >>> s.add_character("Milo", position=(0, 0.1, 7.5), hair="spiky:#5a3a22", shirt_color="#c4281c")
    >>> s.play("Milo", "wave", at=0.5)
    >>> s.add_shot(0, 2, "medium", subject="Milo", moves=[{"type": "push_in", "rate": 0.06}])
    >>> s.add_caption("Hello there", 0.2, 1.8)
    >>> s.render("out.mp4", preview=True)
    """

    def __init__(self, width=1080, height=1920, fps=30, seed=0, world=None, lighting=None, duration=None,
                 name="scene", post=None, audio=None):
        self.width, self.height, self.fps = int(width), int(height), float(fps)
        self.seed, self.name, self.audio = seed, name, audio
        self._duration = duration
        self.post: dict = dict(post or {})
        self.sets: dict = {}
        self.characters: list = []
        self.actions: list = []
        self.props: list = []
        self.shots: list = []
        self.captions: list = []
        self.fx: list = []
        self.meta: dict = {}
        self._built = False
        self._renderers: dict = {}
        if world is not None:
            self.add_set("main", **(world if isinstance(world, dict) else {"location": world}),
                         **({"lighting": lighting} if lighting else {}))

    # ================================================================== authoring
    def invalidate(self):
        self._built = False

    def add_set(self, name="main", location=None, builders=None, lighting=None, ground_y=None, cam_side=None,
                bounds=None, fx=None, **extra):
        """Register a set (world). `location` is a presets.LOCATIONS name; `builders` a list of
        {"builder","args","position","rotation","scale"} dicts (appended after the location's)."""
        spec: dict = {"name": name}
        if location:
            loc = PR.get_location(location)
            spec["location"] = loc["name"]
            base = loc
        else:
            base = dict(builders=[], lighting="day", y=0.0, cam_side=-1, bounds=None, slots=[(-3, 0), (3, 0)],
                        run=[(-15, 0), (15, 0)], prop_spot=(0, 0), seat=None)
        if builders:
            spec["builders"] = list(builders)
        if lighting is not None:
            spec["lighting"] = lighting
        if ground_y is not None:
            spec["ground_y"] = ground_y
        if cam_side is not None:
            spec["cam_side"] = cam_side
        if bounds is not None:
            spec["bounds"] = bounds
        if fx:
            spec["fx"] = list(fx)
        spec.update(extra)
        self.sets[name] = spec
        self.invalidate()
        return spec

    def add_character(self, name, avatar=None, position=(0, 0, 0), facing=0.0, sets=None, **avatar_kw):
        avatar = dict(avatar or {})
        avatar.update(avatar_kw)
        bad = set(avatar) - AVATAR_KEYS
        if bad:
            raise ValueError(f"unknown avatar keys {sorted(bad)}; valid: {sorted(AVATAR_KEYS)}")
        if any(c["name"] == name for c in self.characters):
            raise ValueError(f"character {name!r} already exists")
        spec = {"name": name, "avatar": avatar, "position": [float(x) for x in position], "facing": float(facing)}
        if sets is not None:
            spec["sets"] = list(sets)
        self.characters.append(spec)
        self.invalidate()
        return spec

    def _act(self, **a):
        self.actions.append({k: v for k, v in a.items() if v is not None})
        self.invalidate()
        return self

    def play(self, character, clip, at, speed=None, fade_in=None, fade_out=None, weight=None, mask=None, loop=None,
             until=None, face=None):
        return self._act(character=character, type="play", clip=clip, t=_t(at), speed=speed, fade_in=fade_in,
                         fade_out=fade_out, weight=weight, mask=mask, loop=loop, until=_t(until), face=face)

    def move_to(self, character, pos, t0, t1, ease=None, face=None, gait=None):
        return self._act(character=character, type="move_to", pos=[float(x) for x in pos], t0=_t(t0), t1=_t(t1),
                         ease=ease, face=face, gait=gait)

    def look_at(self, character, target, t0, t1):
        return self._act(character=character, type="look_at", target=target, t0=_t(t0), t1=_t(t1))

    def face(self, character, name, t):
        return self._act(character=character, type="face", name=name, t=_t(t))

    def turn(self, character, deg, t, dur=0.25):
        return self._act(character=character, type="turn", deg=float(deg), t=_t(t), dur=dur)

    def place(self, character, pos, t, facing=None):
        """Teleport (use at cuts between sets / beats)."""
        return self._act(character=character, type="place", pos=[float(x) for x in pos], t=_t(t), facing=facing)

    def add_prop(self, name, builder, args=None, position=(0, 0, 0), rotation=(0, 0, 0), scale=1.0, keys=None,
                 attach=None, set=None, visible=None):
        p = {"name": name, "builder": builder, "args": dict(args or {}), "position": list(position),
             "rotation": list(rotation), "scale": scale}
        if keys:
            p["keys"] = keys
        if attach:
            p["attach"] = attach
        if set:
            p["set"] = set
        if visible:
            p["visible"] = list(visible)
        self.props.append(p)
        self.invalidate()
        return p

    def add_shot(self, t0, t1, kind="medium", **kw) -> Shot:
        s = Shot(float(t0), float(t1), kind=kind, **kw)
        self.shots.append(s)
        self.shots.sort(key=lambda x: x.t0)
        self.invalidate()
        return s

    def add_caption(self, text=None, t0=None, t1=None, words=None, style="storytime", y=0.62, font_scale=1.0):
        d = {"style": style, "y": y, "font_scale": font_scale}
        if words is not None:
            d["words"] = [[w, round(float(a), 4), round(float(b), 4)] for w, a, b in words]
        else:
            d["text"], d["t0"], d["t1"] = text, _t(t0), _t(t1)
        self.captions.append(d)
        self.invalidate()
        return d

    def add_fx(self, type, **kw):
        d = {"type": type, **kw}
        self.fx.append(d)
        self.invalidate()
        return d

    @property
    def duration(self) -> float:
        if self._duration is not None:
            return float(self._duration)
        ends = [s.t1 for s in self.shots]
        for c in self.captions:
            ends.append(c["words"][-1][2] if "words" in c else c["t1"])
        return max(ends) if ends else 0.0

    @duration.setter
    def duration(self, v):
        self._duration = v

    # ================================================================== JSON
    def to_dict(self) -> dict:
        d: dict = {"version": SCHEMA_VERSION, "name": self.name, "width": self.width, "height": self.height,
                   "fps": self.fps, "seed": self.seed}
        if self._duration is not None:
            d["duration"] = self._duration
        if self.audio:
            d["audio"] = self.audio
        d["sets"] = copy.deepcopy(self.sets)
        d["characters"] = copy.deepcopy(self.characters)
        d["actions"] = copy.deepcopy(self.actions)
        d["props"] = copy.deepcopy(self.props)
        d["shots"] = [s.to_dict() for s in self.shots]
        d["captions"] = copy.deepcopy(self.captions)
        d["fx"] = copy.deepcopy(self.fx)
        d["post"] = dict(self.post)
        if self.meta:
            d["meta"] = copy.deepcopy(self.meta)
        return json.loads(json.dumps(d, default=_json_default))

    def to_json(self, path=None, indent=1) -> str:
        s = json.dumps(self.to_dict(), indent=indent, default=_json_default)
        if path:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w") as f:
                f.write(s)
        return s

    save = to_json

    @classmethod
    def from_dict(cls, d: dict) -> "Scene":
        d = copy.deepcopy(d)
        v = d.get("version", SCHEMA_VERSION)
        if v > SCHEMA_VERSION:
            raise ValueError(f"scene version {v} is newer than this library ({SCHEMA_VERSION})")
        s = cls(width=d.get("width", 1080), height=d.get("height", 1920), fps=d.get("fps", 30), seed=d.get("seed", 0),
                duration=d.get("duration"), name=d.get("name", "scene"), post=d.get("post"), audio=d.get("audio"))
        s.sets = d.get("sets", {})
        if "world" in d and not s.sets:                       # shorthand: "world": "street" | {...}
            w = d["world"]
            s.add_set("main", **(w if isinstance(w, dict) else {"location": w}))
        for name, spec in list(s.sets.items()):
            spec.setdefault("name", name)
        s.characters = d.get("characters", [])
        s.actions = d.get("actions", [])
        s.props = d.get("props", [])
        s.shots = [Shot.from_dict(x) for x in d.get("shots", [])]
        s.captions = d.get("captions", [])
        s.fx = d.get("fx", [])
        s.meta = d.get("meta", {})
        return s

    @classmethod
    def from_json(cls, src) -> "Scene":
        """src: JSON text, or a path to a .json file."""
        if isinstance(src, dict):
            return cls.from_dict(src)
        s = str(src)
        if not s.lstrip().startswith("{") and os.path.exists(s):
            with open(s) as f:
                s = f.read()
        return cls.from_dict(json.loads(s))

    load = from_json

    # ================================================================== build
    def _set(self, name=None) -> dict:
        if not self.sets:
            raise ValueError("scene has no sets: call add_set() or pass world=")
        if name is None:
            name = "main" if "main" in self.sets else next(iter(self.sets))
        bs = getattr(self, "_built_sets", None)
        return bs[name] if bs and name in bs else self._resolve_set(name)

    def _resolve_set(self, name) -> dict:
        spec = self.sets[name]
        loc = PR.get_location(spec["location"]) if spec.get("location") else None
        out = {
            "name": name, "location": spec.get("location"),
            "builders": (loc["builders"] if loc else []) + list(spec.get("builders", [])),
            "lighting": spec.get("lighting", loc["lighting"] if loc else "day"),
            "ground_y": spec.get("ground_y", loc["y"] if loc else 0.0),
            "cam_side": spec.get("cam_side", loc["cam_side"] if loc else -1),
            "bounds": spec.get("bounds", loc["bounds"] if loc else None),
            "fx": (loc.get("fx", []) if loc else []) + list(spec.get("fx", [])),
            "slots": loc["slots"] if loc else [(-3, 0), (3, 0)],
            "run": loc["run"] if loc else [(-15, 0), (15, 0)],
            "prop_spot": loc["prop_spot"] if loc else (0, 0),
            "seat": loc["seat"] if loc else None,
        }
        return out

    def _char_spec(self, name) -> dict:
        for c in self.characters:
            if c["name"] == name:
                return c
        raise KeyError(f"unknown character {name!r}; known: {[c['name'] for c in self.characters]}")

    def _anim(self, name):
        if not hasattr(self, "_animators") or not self._built and not getattr(self, "_building", False):
            self._ensure_built()
        return self._animators[name]

    def _ensure_built(self):
        if not self._built and not getattr(self, "_building", False):
            self._building = True
            try:
                self._build()
            finally:
                self._building = False

    def _build(self):
        from .avatar import Avatar
        from .anim import Animator
        from . import world as W
        self._built = False
        self._built_sets = {}
        if not self.sets:
            self.add_set("main")
        for name in list(self.sets):
            self._built_sets[name] = self._resolve_set(name)
        # worlds
        self._worlds = {}
        for name, st in self._built_sets.items():
            world = W.World()
            for p in PR.build_world_props(st["builders"]):
                world.add(p)
            self._worlds[name] = {"world": world, "items": world.draw_items()}
        # characters
        self._animators = {}
        self._avatars = {}
        for c in self.characters:
            av = _make_avatar(c["name"], c.get("avatar", {}))
            self._avatars[c["name"]] = av
            self._animators[c["name"]] = Animator(av, position=tuple(c.get("position", (0, 0, 0))),
                                                 facing_deg=c.get("facing", 0.0), seed=c["name"])
        for a in self._animators.values():
            a.resolver = lambda nm, _s=self: _s._animators[nm] if nm in _s._animators else None
        order = sorted(self.actions, key=lambda a: (a.get("t", a.get("t0", 0.0)), 0 if a["type"] == "place" else 1))
        for a in order:
            self._apply_action(a)
        # props
        self._props = {}
        for p in self.props:
            built = PR.build_world_props([p])[0]
            built.name = p["name"]
            self._props[p["name"]] = (p, built)
        # fx
        from .fx import make_fx
        self._fx = []
        for spec in self.fx:
            self._fx.append(make_fx(spec, resolver=self._feet, seed=self.seed))
        for sname, st in self._built_sets.items():
            for spec in st.get("fx", []):
                f = make_fx({"t0": None, "t1": None, **spec}, resolver=self._feet, seed=self.seed)
                f.set = sname
                self._fx.append(f)
        # timeline
        if not self.shots:
            dur = self.duration or 2.0
            first = self.characters[0]["name"] if self.characters else None
            self.shots.append(Shot(0.0, dur, "wide", subject=first))
        for s in self.shots:
            if s.set is None:
                s.set = "main" if "main" in self.sets else next(iter(self.sets))
        self.timeline = Timeline(self.shots, seed=self.seed)
        self.timeline.build_cameras(_Ctx(self))
        for spec in self.timeline.fx_specs:
            self._fx.append(make_fx(spec, seed=self.seed))
        # captions
        from .captions import CaptionTrack
        self._tracks = []
        for c in self.captions:
            style = c.get("style", "storytime")
            if "words" in c:
                tr = CaptionTrack.from_words([tuple(w) for w in c["words"]], style)
            else:
                tr = CaptionTrack.from_text(c["text"], c["t0"], c["t1"], style=style)
            self._tracks.append((tr, c))
        self._built = True

    def _apply_action(self, a):
        an = self._animators[a["character"]]
        ty = a["type"]
        if ty == "play":
            kw = {k: a[k] for k in ("speed", "fade_in", "fade_out", "weight", "mask", "loop", "until", "face") if k in a}
            an.play(a["clip"], at=a["t"], **kw)
        elif ty == "move_to":
            kw = {k: a[k] for k in ("ease", "face", "gait") if k in a}
            an.move_to(a["pos"], a["t0"], a["t1"], **kw)
        elif ty == "look_at":
            an.look_at(a["target"], a["t0"], a["t1"])
        elif ty == "face":
            an.face(a["name"], a["t"])
        elif ty == "turn":
            an.face_dir(a["deg"], a["t"], a.get("dur", 0.25))
        elif ty == "place":
            an.move_to(a["pos"], a["t"] - 0.002, a["t"], gait=None, face=False)
            if a.get("facing") is not None:
                an.face_dir(a["facing"], a["t"], 0.0)
        else:
            raise ValueError(f"unknown action type {ty!r}; known: {ACTION_TYPES}")

    # ---- resolution helpers
    def _feet(self, name, t):
        return self._animators[name].position_at(t)

    def _resolve_point(self, name, t):
        if name in self._animators:
            sc = float(self._char_spec(name).get("avatar", {}).get("scale", 1.0))
            return self._animators[name].position_at(t) + np.array([0, 3.0 * sc, 0])
        if name in self._props:
            return self._prop_state(name, t)[0]
        raise KeyError(f"cannot resolve {name!r} (characters: {list(self._animators)}, props: {list(self._props)})")

    def _prop_state(self, name, t):
        """-> (position, rotation, scale) at t (attachment aware)."""
        spec, _ = self._props[name]
        att = spec.get("attach")
        if att and t < att.get("until", 1e18):
            an = self._animators[att["to"]]
            pose, cf = an.pose_at(t)
            from . import rig
            S = np.diag([an.avatar.scale] * 3 + [1.0])
            M = rig.part_models(pose, cf @ S)[att.get("part", "Right Arm")]
            off = np.array(att.get("offset", (0, -1.0, -0.8)), float)
            p = (M @ np.append(off, 1.0))[:3]
            return p, np.array(att.get("rotation", (0, 0, 0)), float), spec.get("scale", 1.0), (M, off)
        keys = spec.get("keys")
        if not keys:
            return (np.array(spec["position"], float), np.array(spec["rotation"], float), spec.get("scale", 1.0), None)
        ks = sorted(keys, key=lambda k: k["t"])
        def val(k, f, default):
            v = k.get(f, default)
            if isinstance(v, str) and v == "attach":
                return self._attach_world(att, k["t"]) if att else default
            return np.array(v, float) if isinstance(v, (list, tuple)) else v
        if t <= ks[0]["t"]:
            k = ks[0]
            return (val(k, "position", spec["position"]), val(k, "rotation", spec["rotation"]),
                    k.get("scale", spec.get("scale", 1.0)), None)
        if t >= ks[-1]["t"]:
            k = ks[-1]
            return (val(k, "position", spec["position"]), val(k, "rotation", spec["rotation"]),
                    k.get("scale", spec.get("scale", 1.0)), None)
        for k0, k1 in zip(ks, ks[1:]):
            if k0["t"] <= t <= k1["t"]:
                u = (t - k0["t"]) / max(1e-9, k1["t"] - k0["t"])
                e = C.ease(k1.get("ease", "cubic_inout"), u)
                p0, p1 = val(k0, "position", spec["position"]), val(k1, "position", spec["position"])
                r0, r1 = val(k0, "rotation", spec["rotation"]), val(k1, "rotation", spec["rotation"])
                s0, s1 = k0.get("scale", spec.get("scale", 1.0)), k1.get("scale", spec.get("scale", 1.0))
                s0 = np.asarray(s0, float)
                s1 = np.asarray(s1, float)
                return p0 + (p1 - p0) * e, r0 + (r1 - r0) * e, s0 + (s1 - s0) * e, None
        return (np.array(spec["position"], float), np.array(spec["rotation"], float), 1.0, None)

    def _attach_world(self, att, t):
        saved = att.get("until")
        att2 = dict(att)
        att2["until"] = 1e18
        an = self._animators[att["to"]]
        pose, cf = an.pose_at(t)
        from . import rig
        S = np.diag([an.avatar.scale] * 3 + [1.0])
        M = rig.part_models(pose, cf @ S)[att.get("part", "Right Arm")]
        return (M @ np.array(list(att.get("offset", (0, -1.0, -0.8))) + [1.0]))[:3]

    @staticmethod
    def _char_visible(c, t, set_name):
        if c.get("sets") is not None and set_name not in c["sets"]:
            return False
        vis = c.get("visible")
        return vis is None or any(a - 1e-9 <= t < b - 1e-9 for a, b in vis)

    # ================================================================== frame composition
    def _active_shot_cam(self, t):
        i = self.timeline.shot_index(t)
        return i, self.timeline.shots[i], self.timeline.cameras[i]

    def frame(self, t: float):
        """-> (items, CameraState, Lighting, PostFx). Pure function of t."""
        from .renderer import CameraState, Lighting, PostFx
        self._ensure_built()
        i, shot, cam = self._active_shot_cam(t)
        st = self._built_sets[shot.set]
        trs = self.timeline.transitions_at(t)
        fx = T.compose(trs, t) if trs else T.TransitionFx()
        cs = cam.state(t, offset=fx.cam_offset if trs else None)
        eb = st["bounds"]
        if eb:
            eye = list(cs.eye)
            xmin, xmax, zmin, zmax = eb
            eye[0] = min(max(eye[0], xmin), xmax)
            eye[2] = min(max(eye[2], zmin), zmax)
            eye[1] = max(eye[1], st["ground_y"] + 0.35)
            cs = CameraState(eye=tuple(eye), target=cs.target, up=cs.up, fov_y=cs.fov_y, roll=cs.roll,
                             near=cs.near, far=cs.far)
        # items
        items = list(self._worlds[shot.set]["items"])
        for c in self.characters:
            if self._char_visible(c, t, shot.set):
                items += self._animators[c["name"]].draw_items(t)
        for name, (spec, prop) in self._props.items():
            if spec.get("set") not in (None, shot.set):
                continue
            vis = spec.get("visible")
            if vis and not (vis[0] <= t <= vis[1]):
                continue
            pos, rot, sc, parent = self._prop_state(name, t)
            if parent is not None:
                parent, pos = parent
            prop.position, prop.rotation = tuple(pos), tuple(rot)
            prop.scale = tuple(sc) if np.ndim(sc) else (float(sc),) * 3
            items += prop.to_draw_items(parent) if parent is not None else prop.to_draw_items()
        for f in self._fx:
            if f.set not in (None, shot.set) or not f.active(t):
                continue
            items += f.items(t, cs)
        # lighting
        L = PR.get_lighting(shot.lighting if shot.lighting is not None else st["lighting"])
        if st["cam_side"] > 0:
            sd = list(L["sun_dir"])
            sd[2] = -sd[2]
            L["sun_dir"] = tuple(sd)
        post_d = dict(L.pop("post", {}))
        dist = float(np.linalg.norm(np.asarray(cs.eye) - np.asarray(cs.target)))
        extent = min(max(14.0, 1.7 * dist + 8.0), L.get("shadow_extent", 40.0) * 1.3)
        L["shadow_extent"] = extent
        lighting = Lighting(**L)
        post_d.update(self.post)
        if shot.post:
            post_d.update(shot.post)
        post_d.update(fx.post)
        post_d.setdefault("seed", int(round(t * self.fps)))
        return items, cs, lighting, PostFx(**post_d)

    # ================================================================== rendering
    def _renderer(self, w, h, preview):
        key = (w, h, bool(preview))
        if key not in self._renderers:
            from .renderer import Renderer
            for r in self._renderers.values():
                r.close()
            self._renderers.clear()
            self._renderers[key] = Renderer(w, h, quality="preview" if preview else "final")
        return self._renderers[key]

    def close(self):
        for r in self._renderers.values():
            r.close()
        self._renderers.clear()

    def _size(self, preview, size):
        if size:
            return int(size[0]) // 2 * 2, int(size[1]) // 2 * 2
        if preview and self.height > 640:
            h = 640
            return int(round(self.width * h / self.height / 2)) * 2, h
        return self.width // 2 * 2, self.height // 2 * 2

    def caption_overlay(self, t, w, h):
        from .captions import render_caption
        for tr, c in self._tracks:
            if tr.words and tr.t_start - 1e-6 <= t <= tr.t_end + 1e-6:
                ov = render_caption(tr, t, w, h, style=c.get("style"), y=c.get("y", 0.62),
                                    font_scale=c.get("font_scale", 1.0))
                if ov is not None:
                    return ov
        return None

    def render_frame(self, t, preview=False, size=None, captions=True, motion_blur="auto") -> np.ndarray:
        """Render one (H,W,3) uint8 frame at time t (captions burned in)."""
        self._ensure_built()
        w, h = self._size(preview, size)
        r = self._renderer(w, h, preview)
        return self._render_one(r, t, w, h, preview, captions, motion_blur)

    def _render_one(self, r, t, w, h, preview, captions, motion_blur):
        mb = False
        if motion_blur == "auto":
            mb = self.timeline.in_whip(t)
        elif motion_blur:
            mb = True
        if mb:
            img = r.render_motion_blur(self.frame, t, shutter=0.5, subsamples=3 if preview else 4, fps=self.fps)
        else:
            img = r.render(*self.frame(t))
        if captions:
            from .captions import composite
            ov = self.caption_overlay(t, w, h)
            if ov is not None:
                img = composite(img, ov)
        return img

    def render(self, path, start=None, end=None, preview=False, motion_blur="auto", progress: Optional[Callable] = None,
               size=None, audio=None, crf=None, captions=True, fps=None):
        """Render [start, end] to an mp4 and return the path. `progress(i, n)` is called per frame."""
        from .video import VideoWriter
        self._ensure_built()
        fps = float(fps or self.fps)
        t0 = 0.0 if start is None else float(start)
        t1 = self.duration if end is None else float(end)
        n = max(1, int(round((t1 - t0) * fps)))
        w, h = self._size(preview, size)
        r = self._renderer(w, h, preview)
        audio = audio or self.audio
        tmp_wav = None
        if isinstance(audio, dict):                         # synthesised sound from the "audio" section
            import tempfile
            from . import audio as A
            fd, tmp_wav = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            A.write_wav(tmp_wav, A.mix(self, audio, start=t0, end=t1))
            audio = tmp_wav
        vw = VideoWriter(path, w, h, fps=fps, crf=crf if crf is not None else (24 if preview else 18),
                         preset="veryfast", audio=audio, audio_offset=0.0)
        try:
            for i in range(n):
                t = t0 + i / fps
                vw.write(self._render_one(r, t, w, h, preview, captions, motion_blur))
                if progress:
                    progress(i + 1, n)
        finally:
            vw.close()
            if tmp_wav and os.path.exists(tmp_wav):
                os.remove(tmp_wav)
        return str(path)

    def contact_sheet(self, times=None, cols=6, tile_h=240, preview=True, step=None, labels=True):
        """Grid of frames as a PIL image. times: list of seconds, or None = every `step` seconds (default 0.5)."""
        from PIL import Image, ImageDraw
        self._ensure_built()
        if times is None:
            st = step or 0.5
            times = list(np.arange(0.0, max(self.duration - 1e-6, st), st))
        w, h = self._size(True, (int(round(tile_h * self.width / self.height)) // 2 * 2, tile_h))
        r = self._renderer(w, h, True)
        tiles = [Image.fromarray(self._render_one(r, float(t), w, h, True, True, False)) for t in times]
        rows = math.ceil(len(tiles) / cols)
        sheet = Image.new("RGB", (cols * w + 4 * (cols + 1), rows * h + 4 * (rows + 1)), (20, 20, 20))
        d = ImageDraw.Draw(sheet)
        for k, (t, im) in enumerate(zip(times, tiles)):
            x, y = 4 + (k % cols) * (w + 4), 4 + (k // cols) * (h + 4)
            sheet.paste(im, (x, y))
            if labels:
                d.rectangle([x, y, x + 44, y + 12], fill=(0, 0, 0))
                d.text((x + 2, y + 1), f"{t:.2f}s", fill=(255, 255, 255))
        return sheet

    # ================================================================== validation
    def validate(self) -> list:
        """Return a list of human-readable warnings (empty = fine)."""
        from . import clips as CL
        W: list = []
        try:
            self._ensure_built()
        except Exception as e:                                  # noqa: BLE001
            return [f"scene does not build: {type(e).__name__}: {e}"]
        known_clips = set(CL.names())
        # presets / sets
        for name, st in self._built_sets.items():
            try:
                PR.get_lighting(st["lighting"])
            except KeyError as e:
                W.append(f"set {name!r}: {e}")
        for s in self.shots:
            if s.set not in self._built_sets:
                W.append(f"shot {s.t0:.2f}: unknown set {s.set!r}")
            if s.kind not in SHOT_KINDS:
                W.append(f"shot {s.t0:.2f}: unknown kind {s.kind!r}")
            if s.lighting is not None and isinstance(s.lighting, str):
                try:
                    PR.get_lighting(s.lighting)
                except KeyError as e:
                    W.append(f"shot {s.t0:.2f}: {e}")
            for tr in _tr_list(s.transition):
                if tr.get("type", "cut") not in TRANSITION_TYPES:
                    W.append(f"shot {s.t0:.2f}: unknown transition {tr.get('type')!r}")
        if isinstance(self.audio, dict):
            from . import audio as A
            W += A.validate(self.audio)
            for i, c in enumerate(self.audio.get("cues", [])):
                try:
                    if "times" in c and not A.resolve_times(self, c["times"]):
                        W.append(f"audio cue {i}: times {c['times']!r} matches nothing in this scene")
                except Exception as e:                      # noqa: BLE001
                    W.append(f"audio cue {i}: {e}")
        # clips / faces
        for a in self.actions:
            if a["character"] not in self._animators:
                W.append(f"action refers to unknown character {a['character']!r}")
            if a["type"] == "play" and a["clip"] not in known_clips:
                W.append(f"unknown clip {a['clip']!r} for {a['character']} at t={a.get('t')}")
            if a["type"] == "face" and not _face_ok(a["name"]):
                W.append(f"unknown face {a['name']!r} for {a['character']} at t={a.get('t')}")
        # shots: gaps / overlaps / lengths
        shots = sorted(self.shots, key=lambda s: s.t0)
        if shots and shots[0].t0 > 0.05:
            W.append(f"first shot starts at {shots[0].t0:.2f}s (gap at the beginning)")
        for a, b in zip(shots, shots[1:]):
            if b.t0 < a.t1 - 1e-3:
                W.append(f"shots overlap: {a.t0:.2f}-{a.t1:.2f} and {b.t0:.2f}-{b.t1:.2f}")
            elif b.t0 > a.t1 + 1e-3:
                W.append(f"gap between shots {a.t1:.2f}..{b.t0:.2f}")
        for s in shots:
            d = s.t1 - s.t0
            if d < 0.4:
                W.append(f"shot {s.t0:.2f}-{s.t1:.2f} is very short ({d:.2f}s; style: 0.5-2.2s)")
            elif d > 4.0:
                W.append(f"shot {s.t0:.2f}-{s.t1:.2f} is long ({d:.2f}s; style: 1.0-2.2s, rare holds up to 4s)")
        if len(shots) >= 4:
            avg = sum(s.t1 - s.t0 for s in shots) / len(shots)
            if avg > 2.6:
                W.append(f"average shot length {avg:.2f}s is slow for the reference style (~1.4s)")
            elif avg < 0.8:
                W.append(f"average shot length {avg:.2f}s is very fast (~1.4s)")
        # captions
        for tr, c in self._tracks:
            for (w_, a, b) in tr.words:
                if len(w_) >= 3 and (b - a) < 0.12:
                    W.append(f"caption word {w_!r} at {a:.2f}s shows only {b - a:.2f}s (too fast to read)")
            if tr.words:
                n = len(tr.words)
                dur = tr.t_end - tr.t_start
                if dur > 0 and n / dur > 4.8 and n > 3:
                    W.append(f"captions at {tr.t_start:.2f}s run {n / dur:.1f} words/s (style: 2.5-4)")
                if self.duration and tr.t_end > self.duration + 0.01:
                    W.append(f"caption '{tr.words[-1][0]}' ends after the scene duration")
        # framing + clipping (sampled)
        from .camera import project_points
        for s in shots:
            if s.kind == "insert":
                continue
            subs = [x for x in (s.subject, s.other) if isinstance(x, str) and x in self._animators]
            if not subs:
                continue
            tm = s.t0 + 0.5 * (s.t1 - s.t0)
            for t in (s.t0 + 0.12 * (s.t1 - s.t0), tm, s.t1 - 0.1):
                _, _, cs = None, None, None
                i = self.timeline.shots.index(s) if s in self.timeline.shots else 0
                cs = self.timeline.cameras[i].state(t)
                for nm in subs:
                    p = self._animators[nm].position_at(t)
                    pts = np.array([p + [0, 3.0, 0], p + [0, 4.6, 0]])
                    pr = project_points(cs, pts, self.width, self.height)
                    ok = all(q[2] > 0.1 and -0.05 * self.width <= q[0] <= 1.05 * self.width and
                             -0.05 * self.height <= q[1] <= 1.05 * self.height for q in pr)
                    if not ok:
                        W.append(f"character {nm} is off screen in shot {s.t0:.2f}-{s.t1:.2f} at t={t:.2f}")
                        break
                else:
                    continue
                break
        names = [c["name"] for c in self.characters]
        for t in np.arange(0, self.duration, 0.25):
            i = self.timeline.shot_index(t)
            sname = self.timeline.shots[i].set
            here = [n for n in names if self._char_visible(self._char_spec(n), t, sname)]
            for ai in range(len(here)):
                for bi in range(ai + 1, len(here)):
                    pa, pb = self._animators[here[ai]].position_at(t), self._animators[here[bi]].position_at(t)
                    if np.linalg.norm((pa - pb)[[0, 2]]) < 1.0:
                        W.append(f"characters {here[ai]} and {here[bi]} overlap at t={t:.2f}")
                        break
        seen = set()
        out = []
        for w in W:
            if w not in seen:
                seen.add(w)
                out.append(w)
        return out[:80]


# ====================================================================== helpers
def _tr_list(tr):
    if tr is None:
        return []
    if isinstance(tr, (str, dict)):
        return [{"type": tr} if isinstance(tr, str) else tr]
    return list(tr)


def _json_default(o):
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, tuple):
        return list(o)
    raise TypeError(type(o))


def _face_ok(name) -> bool:
    from .avatar import PROCEDURAL_FACES
    if os.path.isfile(str(name)) or str(name).lower() in PROCEDURAL_FACES or str(name).lower() in ("default",):
        return True
    try:
        from . import faces
        return bool(faces.get(name))
    except Exception:
        return False


def _split_color(spec):
    """'name:#hex' | 'name' | ('name', color) -> (name, color|None)."""
    if isinstance(spec, (list, tuple)):
        return spec[0], (spec[1] if len(spec) > 1 else None)
    if isinstance(spec, str) and ":" in spec:
        n, c = spec.split(":", 1)
        return n, c
    return spec, None


def _make_avatar(name, a: dict):
    from .avatar import Avatar
    kw = {k: v for k, v in a.items() if k not in ("hair", "hair_color", "accessories")}
    hair = a.get("hair")
    hair_color = a.get("hair_color")
    if hair:
        hn, hc = _split_color(hair)
        hair, hair_color = hn, hair_color or hc
    accs = []
    for x in a.get("accessories", []) or []:
        n, c = _split_color(x)
        accs.append((n, c) if c else n)
    if "face" not in kw:
        kw["face"] = "smile"
    return Avatar(name=name, hair=hair, hair_color=hair_color, accessories=tuple(accs), **kw)
