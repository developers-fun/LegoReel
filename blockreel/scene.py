"""Scene file loading, validation and time-based lookups (camera, text, characters)."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .appearance import resolve_appearance
from .avatar import load_avatar
from .camera import Camera
from .character import Timeline
from .errors import SceneError
from .mathutil import apply_ease, parse_color, rot_y, translate, vec3, EASES
from .raster import Lighting
from .rig import load_rig
from .style import DEFAULT_RULES, load_style

TEXT_STYLES = {
    # size is a fraction of frame width; y is the block centre as a fraction of frame height.
    # stroke_width is a fraction of size. bg is an optional "#rrggbbaa" box behind the text.
    "caption": {"size": 0.058, "color": "#ffffff", "stroke": "#000000", "stroke_width": 0.12,
                "y": 0.70, "max_width": 0.86, "bg": None},
    "hook": {"size": 0.085, "color": "#ffffff", "stroke": "#000000", "stroke_width": 0.12,
             "y": 0.20, "max_width": 0.86, "bg": None},
    "label": {"size": 0.045, "color": "#ffffff", "stroke": "#000000", "stroke_width": 0.10,
              "y": 0.12, "max_width": 0.86, "bg": None},
}

DEFAULT_META = {
    "title": "Untitled",
    "style": "house",       # styles/<name>.json: camera rules and look defaults. null for no style.
    "width": 1080,
    "height": 1920,
    "fps": 30,
    "supersample": 2,
    "background": {"top": "#6fb4f5", "bottom": "#dcefff", "sun_glow": 0.35, "clouds": None},
    "ground": {"y": 0.0, "zones": [], "studs": 0.0, "geo_studs": False, "tile": 4.0, "colors": ["#6fbf73", "#63b068"],
               "fog_distance": 60.0, "fog_color": "#dcefff", "far": 400.0,
               "line_color": "#4f9a5a", "line_width": 0.07, "line_strength": 0.35, "variation": 0.02},
    # direction points toward the sun. ambient is the sky/ground hemisphere strength.
    "light": {"direction": [-0.45, 0.85, 0.55], "ambient": 0.55, "sun_color": "#fff1da", "sun_strength": 0.8,
              "sky_color": "#bfd8ff", "ground_color": "#8a9a72", "fill_strength": 0.14, "ao": 0.22,
              "spec_strength": 0.35, "spec_power": 36.0},
    "shadows": {"enabled": True, "strength": 0.42, "softness": 0.2, "range": 40.0, "contact": 0.2,
                "tint": [1.0, 0.97, 0.86]},
    # bevel: edge chamfer in studs. vignette, saturation, contrast: final colour pass.
    "look": {"bevel": 0.06, "gloss": 0.0, "vignette": 0.10, "saturation": 1.05, "contrast": 1.03,
             "bloom": 0.0, "dof": None, "tint": [1.0, 1.0, 1.0]},
    "font_path": None,
    "show_speaker": False,
    "text_styles": {},
    "audio": None,
    "export": {"crf": 18, "preset": "medium"},
}

_ACTION_KEYS = {
    "pose": {"t", "character", "pose", "duration", "hand", "speed"},
    "move_to": {"t", "character", "move_to", "speed", "duration", "face", "pose", "then_pose"},
    "teleport": {"t", "character", "teleport"},
    "face": {"t", "character", "face", "turn"},
    "look": {"t", "character", "look"},
    "expression": {"t", "character", "expression"},
}


@dataclass
class CamKey:
    t: float
    position: np.ndarray
    look_at: object          # np.ndarray or None
    target_char: object      # str or None
    target_offset: np.ndarray
    follow: object           # str or None
    fov: float
    ease: str


@dataclass
class Shot:
    id: str
    start: float
    duration: float
    cam_keys: list
    shake: float
    fade_in: float
    fade_out: float

    @property
    def end(self):
        return self.start + self.duration


@dataclass
class Text:
    t0: float
    t1: float
    text: str
    style: str
    y: object
    speaker: object


@dataclass
class Prop:
    id: str
    position: np.ndarray
    rotation_y: float
    size: tuple
    color: tuple
    shape: str = "box"
    bevel: object = None
    casts: bool = True
    track_raw: object = None
    track: object = None   # list of (global_t, position ndarray, ease) once resolved
    template: object = None      # a loaded set Part, when the prop is a template instance
    palette: object = None
    studs: bool = False
    scale: float = 1.0


def _deep_update(base, over):
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_update(out[k], v)
        else:
            out[k] = v
    return out


def _num(d, key, ctx, default=None, minimum=None):
    v = d.get(key, default)
    if v is None:
        raise SceneError(f"{ctx}: '{key}' is required")
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise SceneError(f"{ctx}: '{key}' must be a number, got {v!r}")
    if minimum is not None and v < minimum:
        raise SceneError(f"{ctx}: '{key}' must be at least {minimum}, got {v}")
    return float(v)


class Scene:
    def __init__(self, data, base_dir, width_scale=1.0, supersample=None):
        self.base_dir = Path(base_dir)
        if not isinstance(data, dict):
            raise SceneError("scene file must be a JSON object")
        unknown = set(data) - {"meta", "characters", "props", "shots"}
        if unknown:
            raise SceneError(f"unknown top-level keys: {', '.join(sorted(unknown))}")
        raw_meta = data.get("meta", {})
        style_name = raw_meta.get("style", DEFAULT_META["style"])
        self.style = load_style(style_name, self.base_dir) if style_name else None
        self.rules = dict(self.style["rules"]) if self.style else dict(DEFAULT_RULES)
        self.presets = dict(self.style["presets"]) if self.style else {}
        meta = _deep_update(_deep_update(DEFAULT_META, self.style["meta"] if self.style else {}), raw_meta)
        self.meta = meta
        self.title = str(meta["title"])
        self.fps = int(_num(meta, "fps", "meta", minimum=1))
        w = int(_num(meta, "width", "meta", minimum=16))
        h = int(_num(meta, "height", "meta", minimum=16))
        if width_scale != 1.0:
            w = max(16, int(round(w * width_scale / 2.0)) * 2)
            h = max(16, int(round(h * width_scale / 2.0)) * 2)
        if w % 2 or h % 2:
            raise SceneError("meta.width and meta.height must be even numbers (H.264 requirement)")
        self.width, self.height = w, h
        ss = supersample if supersample is not None else meta["supersample"]
        if not isinstance(ss, int) or not (1 <= ss <= 4):
            raise SceneError("supersample must be an integer from 1 to 4")
        self.supersample = ss

        bg = meta["background"]
        self.bg_top = parse_color(bg["top"], "meta.background.top")
        self.bg_bottom = parse_color(bg["bottom"], "meta.background.bottom")
        self.sun_glow = float(bg.get("sun_glow", 0.0))
        self.clouds = None
        if bg.get("clouds"):
            cl = dict(bg["clouds"])
            cl["color"] = parse_color(cl.get("color", "#ffffff"), "meta.background.clouds.color")
            self.clouds = cl
        g = meta["ground"]
        self.ground = {
            "y": float(g["y"]),
            "tile": float(g["tile"]),
            "colors": [parse_color(c, "meta.ground.colors") for c in g["colors"]],
            "fog_distance": float(g["fog_distance"]),
            "fog_color": parse_color(g["fog_color"], "meta.ground.fog_color"),
            "far": float(g["far"]),
            "line_color": parse_color(g["line_color"], "meta.ground.line_color"),
            "line_width": float(g["line_width"]),
            "line_strength": float(g["line_strength"]),
            "variation": float(g["variation"]),
            "zones": [],
            "studs": float(g.get("studs", 0.0)),
            # real raised studs on the lattice of tiles (pitch = tile, radius = studs * tile), built from the camera's view
            "geo_studs": bool(g.get("geo_studs", False)),
            "tile": float(g["tile"]),
        }
        for i, zn in enumerate(g.get("zones", [])):
            if len(zn.get("rect", [])) != 4 or len(zn.get("colors", [])) != 2:
                raise SceneError(f"meta.ground.zones[{i}]: needs rect [x0,z0,x1,z1] and two colours")
            self.ground["zones"].append({
                "rect": [float(v) for v in zn["rect"]],
                "colors": [parse_color(c, f"meta.ground.zones[{i}].colors") for c in zn["colors"]],
                "tile": float(zn.get("tile", g["tile"])),
                "variation": float(zn.get("variation", g["variation"])),
                "line_color": parse_color(zn.get("line_color", g["line_color"]), f"meta.ground.zones[{i}].line_color"),
                "line_width": float(zn.get("line_width", g["line_width"])),
                "line_strength": float(zn.get("line_strength", g["line_strength"])),
                "studs": float(zn.get("studs", g.get("studs", 0.0))),
            })
        if len(self.ground["colors"]) != 2 or self.ground["tile"] <= 0:
            raise SceneError("meta.ground: needs two colours and a tile size above zero")
        L = meta["light"]
        d = np.array(L["direction"], dtype=np.float64)
        if d.shape != (3,) or np.linalg.norm(d) < 1e-9:
            raise SceneError("meta.light.direction: expected three numbers, not all zero")
        self.light_dir = d / np.linalg.norm(d)
        lt = dict(L)
        lt["sun_color"] = parse_color(L["sun_color"], "meta.light.sun_color")
        lt["sky_color"] = parse_color(L["sky_color"], "meta.light.sky_color")
        lt["ground_color"] = parse_color(L["ground_color"], "meta.light.ground_color")
        self.lighting = Lighting(lt, self.ground["y"], self.ground["fog_color"], self.ground["fog_distance"])
        self.shadow_cfg = dict(meta["shadows"])
        self.look = dict(meta["look"])
        self.font_path = meta["font_path"]
        self.show_speaker = bool(meta["show_speaker"])
        self.text_styles = _deep_update(TEXT_STYLES, meta["text_styles"])
        for name, st in self.text_styles.items():
            parse_color(st["color"], f"text style {name}")
            parse_color(st["stroke"], f"text style {name}")
            for k in ("highlight",):
                if st.get(k):
                    parse_color(st[k], f"text style {name}.{k}")
        audio = meta["audio"]
        self.audio_path = None
        if audio:
            p = (self.base_dir / audio)
            self.audio_path = p
        self.export = meta["export"]

        self._load_characters(data.get("characters", {}))
        self._load_props(data.get("props", []))
        self._load_shots(data.get("shots", []))
        for tl in self.timelines.values():
            tl.finalize()

    # ---- loading ----------------------------------------------------------

    @classmethod
    def load(cls, path, **kw):
        path = Path(path)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            raise SceneError(f"scene file not found: {path}")
        except json.JSONDecodeError as e:
            raise SceneError(f"{path}: not valid JSON (line {e.lineno}, column {e.colno}): {e.msg}")
        return cls(data, path.parent, **kw)

    def _load_characters(self, chars):
        if not isinstance(chars, dict) or not chars:
            raise SceneError("'characters' must be an object with at least one character")
        self.raw_characters = chars
        self.appearances = {}
        self.rigs = {}
        self.avatars = {}
        self.timelines = {}
        self.scales = {}
        for cid, c in chars.items():
            ctx = f"characters.{cid}"
            unknown = set(c) - {"avatar", "variant", "avatar_fingerprint", "appearance", "appearance_file",
                                "position", "yaw", "scale"}
            if unknown:
                raise SceneError(f"{ctx}: unknown keys {', '.join(sorted(unknown))}")
            scale = _num(c, "scale", ctx, default=1.0, minimum=0.05)
            if "avatar" in c:
                if "appearance" in c or "appearance_file" in c:
                    raise SceneError(f"{ctx}: a character uses either 'avatar' or an inline appearance, not both. "
                                     f"To change the look, add a variant to the avatar file.")
                if abs(scale - 1.0) > 1e-9:
                    raise SceneError(f"{ctx}: avatars keep their exact measurements, so 'scale' must be 1")
                av = load_avatar(str(c["avatar"]), c.get("variant"), self.base_dir)
                pin = c.get("avatar_fingerprint")
                if pin and pin != av.fingerprint:
                    raise SceneError(f"{ctx}: avatar '{av.label}' is now fingerprint {av.fingerprint}, but the scene "
                                     f"pins {pin}. The avatar file changed since this scene was written.")
                self.avatars[cid] = av
                self.appearances[cid] = av.appearance
                self.rigs[cid] = av.rig
            else:
                if self.rules["require_avatar"]:
                    raise SceneError(
                        f"{ctx}: style '{self.style['name']}' requires every character to use an avatar file. "
                        f"Use \"avatar\": \"main\" (look changes belong in a variant inside avatars/main.json), "
                        f"or point meta.style at a style that does not require avatars.")
                user = dict(c.get("appearance", {}))
                if "appearance_file" in c:
                    p = self.base_dir / c["appearance_file"]
                    try:
                        with open(p, "r", encoding="utf-8") as fh:
                            from_file = json.load(fh)
                    except FileNotFoundError:
                        raise SceneError(f"{ctx}: appearance_file not found: {p}")
                    except json.JSONDecodeError as e:
                        raise SceneError(f"{p}: not valid JSON: {e.msg} (line {e.lineno})")
                    user = _deep_update(from_file, user)
                self.appearances[cid] = resolve_appearance(user)
                self.rigs[cid] = load_rig("r6", str(self.base_dir))
            self.scales[cid] = scale
            pos = vec3(c.get("position", [0, 0, 0]), f"{ctx}.position")
            yaw = _num(c, "yaw", ctx, default=0.0)
            self.timelines[cid] = Timeline(cid, pos, yaw, scale)

    def _load_props(self, props):
        if not isinstance(props, list):
            raise SceneError("'props' must be a list")
        self.props = []
        for i, p in enumerate(props):
            ctx = f"props[{i}]"
            if "template" in p:
                from .parts import load_part
                unknown = set(p) - {"id", "template", "position", "rotation_y", "palette", "scale", "track", "cast_shadow"}
                if unknown:
                    raise SceneError(f"{ctx}: unknown keys {', '.join(sorted(unknown))}")
                part = load_part("sets", str(p["template"]), self.base_dir)
                pos = vec3(p.get("position"), f"{ctx}.position")
                self.props.append(Prop(str(p.get("id", f"prop{i}")), pos, float(p.get("rotation_y", 0.0)), (1.0, 1.0, 1.0),
                                       (255, 255, 255), "template", None, bool(p.get("cast_shadow", True)), p.get("track"),
                                       None, part, dict(p.get("palette", {})), False, float(p.get("scale", 1.0))))
                continue
            shape = p.get("type", "box")
            if shape not in ("box", "cylinder"):
                raise SceneError(f"{ctx}: type must be 'box' or 'cylinder' (or use \"template\": id for a set piece)")
            unknown = set(p) - {"id", "type", "position", "size", "color", "rotation_y", "track", "bevel", "cast_shadow", "studs"}
            if unknown:
                raise SceneError(f"{ctx}: unknown keys {', '.join(sorted(unknown))}")
            pos = vec3(p.get("position"), f"{ctx}.position")
            size = vec3(p.get("size"), f"{ctx}.size")
            if (size <= 0).any():
                raise SceneError(f"{ctx}.size: all values must be above zero")
            color = parse_color(p.get("color", "#cccccc"), f"{ctx}.color")
            bevel = p.get("bevel")
            self.props.append(Prop(str(p.get("id", f"prop{i}")), pos, float(p.get("rotation_y", 0.0)),
                                   tuple(float(s) for s in size), color, shape,
                                   float(bevel) if bevel is not None else None,
                                   bool(p.get("cast_shadow", True)), p.get("track"), None, None, None,
                                   bool(p.get("studs", False))))

    def _load_shots(self, shots):
        if not isinstance(shots, list) or not shots:
            raise SceneError("'shots' must be a list with at least one shot")
        self.shots = []
        self.texts = []
        cursor = 0.0
        for i, s in enumerate(shots):
            ctx = f"shots[{i}]"
            unknown = set(s) - {"id", "start", "duration", "camera", "shake", "fade_in", "fade_out",
                                "actions", "dialogue", "overlays", "note"}
            if unknown:
                raise SceneError(f"{ctx}: unknown keys {', '.join(sorted(unknown))}")
            dur = _num(s, "duration", ctx, minimum=0.1)
            start = _num(s, "start", ctx, default=cursor, minimum=0.0)
            sid = str(s.get("id", f"shot{i + 1}"))
            ctx = f"shot '{sid}'"
            cam = s.get("camera")
            if cam is None:
                raise SceneError(f"{ctx}: 'camera' is required (an object, or a list of keyframes)")
            keys = self._parse_cam(cam if isinstance(cam, list) else [cam], ctx)
            shake = _num(s, "shake", ctx, default=0.0, minimum=0.0)
            if shake > 0 and not self.rules["allow_shake"]:
                raise SceneError(f"{ctx}: screen shake is off in style '{self.style['name']}'. Remove 'shake', or "
                                 f"use a style with \"allow_shake\": true.")
            shot = Shot(sid, start, dur, keys,
                        shake,
                        _num(s, "fade_in", ctx, default=0.0, minimum=0.0),
                        _num(s, "fade_out", ctx, default=0.0, minimum=0.0))
            self.shots.append(shot)
            cursor = shot.end
            self._load_actions(s.get("actions", []), shot, ctx)
            for j, d in enumerate(s.get("dialogue", [])):
                c2 = f"{ctx}.dialogue[{j}]"
                t = _num(d, "t", c2, default=0.0, minimum=0.0)
                dd = _num(d, "duration", c2, minimum=0.1)
                spk = d.get("speaker")
                if spk is not None and spk not in self.timelines:
                    raise SceneError(f"{c2}: unknown speaker '{spk}'")
                self.texts.append(Text(start + t, start + t + dd, str(d.get("text", "")),
                                       d.get("style", "caption"), d.get("y"), spk))
            for j, d in enumerate(s.get("overlays", [])):
                c2 = f"{ctx}.overlays[{j}]"
                t = _num(d, "t", c2, default=0.0, minimum=0.0)
                dd = _num(d, "duration", c2, minimum=0.1)
                self.texts.append(Text(start + t, start + t + dd, str(d.get("text", "")),
                                       d.get("style", "hook"), d.get("y"), None))
        for t in self.texts:
            if t.style not in self.text_styles:
                raise SceneError(f"unknown text style '{t.style}'. Options: {', '.join(self.text_styles)}")
        self.shots.sort(key=lambda s: s.start)
        self._resolve_tracks()
        self.duration = max(s.end for s in self.shots)
        self.frame_count = max(1, int(round(self.duration * self.fps)))

    def _resolve_tracks(self):
        starts = {sh.id: sh.start for sh in self.shots}
        for p in self.props:
            raw = p.track_raw
            if not raw:
                continue
            ctx = f"props '{p.id}'.track"
            if not isinstance(raw, dict) or not isinstance(raw.get("keys"), list) or not raw["keys"]:
                raise SceneError(f"{ctx}: expected {{\"shot\": id (optional), \"keys\": [{{t, position, ease}}]}}")
            base = 0.0
            if raw.get("shot") is not None:
                if raw["shot"] not in starts:
                    raise SceneError(f"{ctx}: unknown shot '{raw['shot']}'")
                base = starts[raw["shot"]]
            keys = []
            for k, kr in enumerate(raw["keys"]):
                c2 = f"{ctx}.keys[{k}]"
                ease = kr.get("ease", "ease_in_out")
                if ease not in EASES:
                    raise SceneError(f"{c2}: unknown ease '{ease}'")
                keys.append((base + _num(kr, "t", c2, minimum=0.0), vec3(kr.get("position"), f"{c2}.position"), ease))
            keys.sort(key=lambda k: k[0])
            p.track = keys

    def prop_model(self, p, T):
        pos = p.position
        if p.track:
            keys = p.track
            if T <= keys[0][0]:
                pos = keys[0][1]
            elif T >= keys[-1][0]:
                pos = keys[-1][1]
            else:
                for a, b in zip(keys, keys[1:]):
                    if a[0] <= T < b[0]:
                        u = apply_ease(a[2], (T - a[0]) / (b[0] - a[0]))
                        pos = a[1] + (b[1] - a[1]) * u
                        break
        return translate(*pos) @ rot_y(p.rotation_y)

    def _parse_cam(self, keys, ctx):
        out = []
        for k, raw in enumerate(keys):
            c2 = f"{ctx}.camera[{k}]"
            unknown = set(raw) - {"t", "position", "look_at", "target", "target_offset", "follow", "fov", "ease",
                                  "preset", "focus", "yaw"}
            if unknown:
                raise SceneError(f"{c2}: unknown keys {', '.join(sorted(unknown))}")
            follow = raw.get("follow")
            if follow is not None and follow not in self.timelines:
                raise SceneError(f"{c2}: unknown character '{follow}' in follow")
            target = raw.get("target", follow)
            if target is not None and target not in self.timelines:
                raise SceneError(f"{c2}: unknown character '{target}' in target")
            fov = _num(raw, "fov", c2, default=50.0, minimum=5.0) if "fov" in raw else None
            if "preset" in raw:
                name = raw["preset"]
                if name not in self.presets:
                    raise SceneError(f"{c2}: unknown camera preset '{name}'. "
                                     f"Options: {', '.join(self.presets) or 'none (the style defines none)'}")
                pr = self.presets[name]
                focus = vec3(raw.get("focus", [0, 0, 0]), f"{c2}.focus")
                yawm = rot_y(_num(raw, "yaw", c2, default=0.0))[:3, :3]
                position = focus + yawm @ np.array(pr["offset"], dtype=np.float64)
                look_at = focus + yawm @ np.array(pr["look_offset"], dtype=np.float64)
                if fov is None:
                    fov = float(pr.get("fov", 50.0))
            else:
                if "focus" in raw or "yaw" in raw:
                    raise SceneError(f"{c2}: 'focus' and 'yaw' only go with a 'preset'")
                position = vec3(raw.get("position"), f"{c2}.position")
                look_at = vec3(raw["look_at"], f"{c2}.look_at") if raw.get("look_at") is not None else None
                if look_at is None and target is None:
                    raise SceneError(f"{c2}: needs a 'preset', or 'look_at' [x, y, z], or 'target' (a character id)")
                if fov is None:
                    fov = 50.0
            if fov >= 150:
                raise SceneError(f"{c2}: fov must be under 150")
            ease = raw.get("ease", "ease_in_out")
            if ease not in EASES:
                raise SceneError(f"{c2}: unknown ease '{ease}'. Options: {', '.join(EASES)}")
            out.append(CamKey(
                _num(raw, "t", c2, default=0.0, minimum=0.0), position, look_at, target,
                vec3(raw.get("target_offset", [0, 3, 0]), f"{c2}.target_offset"), follow, fov, ease))
        out.sort(key=lambda k: k.t)
        if self.rules["fixed_cameras"]:
            moving = len(out) > 1 or any(k.follow or k.target_char for k in out)
            if moving:
                raise SceneError(
                    f"{ctx}: this camera moves (several keyframes, 'follow' or 'target'). Style "
                    f"'{self.style['name']}' uses fixed cameras: give the shot one camera with a 'preset' or "
                    f"'position' + 'look_at', and cut to another shot to change the view. To allow camera "
                    f"motion, copy the style file with \"fixed_cameras\": false and point meta.style at it.")
        return out

    def _load_actions(self, actions, shot, ctx):
        if not isinstance(actions, list):
            raise SceneError(f"{ctx}.actions: expected a list")
        indexed = sorted(enumerate(actions), key=lambda ia: (float(ia[1].get("t", 0.0)), ia[0]))
        for i, a in indexed:
            c2 = f"{ctx}.actions[{i}]"
            cid = a.get("character")
            if cid not in self.timelines:
                raise SceneError(f"{c2}: unknown character '{cid}'. Known: {', '.join(self.timelines)}")
            tl = self.timelines[cid]
            t = shot.start + _num(a, "t", c2, default=0.0, minimum=0.0)
            kinds = [k for k in ("pose", "move_to", "teleport", "face", "look", "expression") if k in a]
            if len(kinds) != 1:
                raise SceneError(f"{c2}: needs exactly one of pose, move_to, teleport, face, look (found {kinds or 'none'})")
            kind = kinds[0]
            extra = set(a) - _ACTION_KEYS[kind]
            if extra:
                raise SceneError(f"{c2}: keys not valid for '{kind}': {', '.join(sorted(extra))}")
            if kind == "pose":
                params = {}
                if "duration" in a:
                    params["duration"] = _num(a, "duration", c2, minimum=0.1)
                if "hand" in a:
                    if a["hand"] not in ("left", "right"):
                        raise SceneError(f"{c2}: hand must be 'left' or 'right'")
                    params["hand"] = a["hand"]
                if "speed" in a:
                    params["speed"] = _num(a, "speed", c2, minimum=0.1)
                tl.add_pose(t, a["pose"], params)
            elif kind == "move_to":
                tgt = a["move_to"]
                if not isinstance(tgt, list) or len(tgt) not in (2, 3):
                    raise SceneError(f"{c2}.move_to: expected [x, z] or [x, y, z]")
                speed = _num(a, "speed", c2, default=0.0, minimum=0.0) or None
                dur = _num(a, "duration", c2, default=0.0, minimum=0.0) or None
                if speed is None and dur is None:
                    speed = 4.0
                tl.add_move(t, tgt, speed, dur, bool(a.get("face", True)),
                            a.get("pose", "walk"), a.get("then_pose", "idle"))
            elif kind == "teleport":
                tl.add_teleport(t, vec3(a["teleport"], f"{c2}.teleport"))
            elif kind == "face":
                f = a["face"]
                turn = _num(a, "turn", c2, default=0.25, minimum=0.0)
                if isinstance(f, (int, float)) and not isinstance(f, bool):
                    tl.add_face(t, float(f), None, turn)
                elif isinstance(f, dict) and "toward" in f:
                    if f["toward"] not in self.timelines:
                        raise SceneError(f"{c2}.face.toward: unknown character '{f['toward']}'")
                    tl.add_face(t, 0.0, ("toward", f["toward"]), turn)
                elif isinstance(f, dict) and "look_at" in f and len(f["look_at"]) == 2:
                    tl.add_face(t, 0.0, ("look_at", [float(f["look_at"][0]), float(f["look_at"][1])]), turn)
                else:
                    raise SceneError(f"{c2}.face: use a yaw number in degrees, {{\"toward\": id}} or {{\"look_at\": [x, z]}}")
            elif kind == "expression":
                av = self.avatars.get(cid)
                name = a["expression"]
                if av is None or not hasattr(av, "expressions"):
                    raise SceneError(f"{c2}: 'expression' needs a brick avatar with an \"expressions\" list")
                if name != "neutral" and name not in av.expressions:
                    raise SceneError(f"{c2}.expression: '{name}' is not defined by avatar '{av.label}'. "
                                     f"Options: neutral, {', '.join(av.expressions) or 'none defined'}")
                tl.add_expression(t, None if name == "neutral" else name)
            elif kind == "look":
                lk = a["look"]
                if lk in (None, "none"):
                    tl.add_look(t, None)
                elif lk == "camera":
                    tl.add_look(t, "camera")
                elif isinstance(lk, str):
                    if lk not in self.timelines:
                        raise SceneError(f"{c2}.look: unknown character '{lk}'")
                    tl.add_look(t, lk)
                else:
                    tl.add_look(t, vec3(lk, f"{c2}.look").tolist())

    # ---- lookups ----------------------------------------------------------

    def shot_at(self, T):
        for s in self.shots:
            if s.start <= T < s.end:
                return s
        return self.shots[-1] if T >= self.shots[-1].end else self.shots[0]

    def camera_at(self, T):
        shot = self.shot_at(T)
        local = T - shot.start
        keys = shot.cam_keys

        def resolve(k):
            pos = k.position.copy()
            if k.follow:
                pos = pos + self.timelines[k.follow].pos_at(T)
            if k.look_at is not None:
                tgt = k.look_at.copy()
            else:
                tgt = self.timelines[k.target_char].pos_at(T) + k.target_offset
            return pos, tgt, k.fov

        if local <= keys[0].t or len(keys) == 1:
            pos, tgt, fov = resolve(keys[0])
        elif local >= keys[-1].t:
            pos, tgt, fov = resolve(keys[-1])
        else:
            i = max(j for j in range(len(keys) - 1) if keys[j].t <= local)
            a, b = keys[i], keys[i + 1]
            u = apply_ease(a.ease, (local - a.t) / (b.t - a.t))
            pa, ta, fa = resolve(a)
            pb, tb, fb = resolve(b)
            pos, tgt, fov = pa + (pb - pa) * u, ta + (tb - ta) * u, fa + (fb - fa) * u

        if shot.shake > 0:
            n = np.array([
                math.sin(T * 17.3) + 0.6 * math.sin(T * 31.7 + 1.3),
                math.sin(T * 13.1 + 2.1) + 0.6 * math.sin(T * 27.9),
                math.sin(T * 19.7 + 0.7) + 0.6 * math.sin(T * 23.3 + 2.9),
            ]) * 0.5
            pos = pos + n * shot.shake
            tgt = tgt + n[::-1] * shot.shake
        return Camera.from_look_at(pos, tgt, fov)

    def fade_at(self, T):
        """Brightness 0..1 from the shot's fade_in / fade_out."""
        s = self.shot_at(T)
        local = T - s.start
        f = 1.0
        if s.fade_in > 0 and local < s.fade_in:
            f = min(f, local / s.fade_in)
        if s.fade_out > 0 and local > s.duration - s.fade_out:
            f = min(f, max(0.0, (s.duration - local) / s.fade_out))
        return f

    def texts_at(self, T):
        return [t for t in self.texts if t.t0 <= T < t.t1]

    # ---- validation report -------------------------------------------------

    def report(self):
        lines = [f"title: {self.title}",
                 "style: " + (f"{self.style['name']} v{self.style['version']}  (fixed cameras: {self.rules['fixed_cameras']}, "
                              f"shake allowed: {self.rules['allow_shake']}, avatar required: {self.rules['require_avatar']})"
                              if self.style else "none"),
                 f"output: {self.width}x{self.height} at {self.fps} fps, supersample {self.supersample}",
                 f"duration: {self.duration:.2f}s ({self.frame_count} frames)",
                 "characters:"]
        for cid in self.timelines:
            av = self.avatars.get(cid)
            if av:
                lines.append(f"  {cid:<10} avatar {av.label} v{av.version}  fingerprint {av.fingerprint}  rig {av.rig.name}")
            else:
                lines.append(f"  {cid:<10} inline appearance (no avatar file)  rig {self.rigs[cid].name}")
        lines.append("shots:")
        for s in self.shots:
            cam = "fixed camera" if len(s.cam_keys) == 1 else f"{len(s.cam_keys)} camera keys"
            lines.append(f"  {s.id:<14} {s.start:6.2f}s -> {s.end:6.2f}s  ({s.duration:.2f}s, {cam}{', shake' if s.shake else ''})")
        warnings = []
        for t in self.texts:
            if t.style == "label":
                continue  # labels repeat across cuts on purpose
            words = len(t.text.split())
            dur = t.t1 - t.t0
            if dur > 0 and words / dur > 3.5:
                warnings.append(f"text at {t.t0:.2f}s is {words} words in {dur:.1f}s (over 3.5 words/s, hard to read)")
            sh = self.shot_at(t.t0)
            if t.t1 > sh.end + 1e-6:
                warnings.append(f"text at {t.t0:.2f}s runs past the end of shot '{sh.id}'")
        for a, b in zip(self.shots, self.shots[1:]):
            if b.start < a.end - 1e-6:
                warnings.append(f"shots '{a.id}' and '{b.id}' overlap")
            elif b.start > a.end + 1e-6:
                warnings.append(f"gap between shots '{a.id}' and '{b.id}' (the earlier shot's last frame holds)")
        if self.audio_path and not self.audio_path.exists():
            warnings.append(f"audio file not found: {self.audio_path}")
        if warnings:
            lines.append("warnings:")
            lines += [f"  - {w}" for w in warnings]
        else:
            lines.append("warnings: none")
        return "\n".join(lines)
