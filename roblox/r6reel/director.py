"""Director: story beats in, a fully directed Scene out, in the reference style (docs/STYLE.md).

    from r6reel.director import Director, Beat
    scene = Director([
        Beat("Lunch period was supposed to be normal.", character="Milo", location="cafeteria"),
        Beat("Then Milo dropped his tray.", character="Milo", emotion="shocked", action="drop"),
    ], seed=7).build()
    scene.render("out/story.mp4", preview=True)

Every automatic choice (clip, face, shot kind/length, camera angle, transition, caption timing, lighting) can be
overridden per beat (Beat fields) or afterwards by editing the Scene (scene.shots, scene.actions, ...).
The same seed always gives the same Scene.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, fields
from typing import Any, Optional

import numpy as np

from . import presets as PR
from .scene import Scene
from .timeline import Shot

CAPTION_VARIANTS = {   # STYLE.md "4 variants": style, y, font scale
    "A": dict(style="yellow_pop", y=0.50, font_scale=1.05),
    "B": dict(style="storytime", y=0.68, font_scale=0.85),
    "C": dict(style="storytime", y=0.64, font_scale=1.0),
    "D": dict(style="two_line", y=0.33, font_scale=0.85),
}
RUN_ACTIONS = ("run", "sprint", "chase", "flee")
_STOP_NAMES = {"He", "She", "The", "Then", "They", "It", "This", "That", "And", "But", "So", "When", "After", "Suddenly",
               "Everyone", "I", "We", "You", "His", "Her", "There", "What", "Why", "How", "One", "Today", "Now", "My",
               "Lunch", "Nobody", "Somebody", "At", "In", "On", "As", "If", "Not"}


# ============================================================================================ Beat
@dataclass
class Beat:
    """One narration beat. Everything except `text` is optional (None = decide automatically)."""
    text: str = ""
    character: Optional[str] = None     # who the beat is about / speaking
    emotion: Optional[str] = None       # presets.EMOTIONS key (aliases ok)
    location: Optional[str] = None      # presets.LOCATIONS key (aliases ok); sticks until changed
    action: Optional[str] = None        # presets.ACTIONS key (drop, run, wave, ...) or a clip name
    duration: Optional[float] = None    # seconds; None = from text length and pace
    target: Optional[str] = None        # second character (dialogue partner / chase target)
    cast: Optional[list] = None         # extra characters present
    prop: Optional[str] = None          # "tray" | "duck" | "ball" | "coin" | world builder name
    shot: Any = None                    # force shot kind(s): "closeup" or ["wide", "extreme_closeup", ...]
    transition: Any = None              # force the transition into this beat's first shot
    camera: Optional[dict] = None       # overrides for every shot of the beat: azimuth, elevation, fov, moves, ...
    face: Optional[str] = None          # force a face name/path for `character`
    lighting: Optional[str] = None      # lighting preset for this beat
    mood: Optional[str] = None          # mood word -> lighting preset
    fx: Optional[list] = None           # extra fx: names ("coins") or spec dicts
    silent: bool = False                # no caption

    @classmethod
    def from_dict(cls, d: dict) -> "Beat":
        d = dict(d)
        alias = {"say": "text", "line": "text", "char": "character", "name": "character", "loc": "location",
                 "to": "target", "dur": "duration", "emote": "emotion"}
        for k, v in alias.items():
            if k in d and v not in d:
                d[v] = d.pop(k)
        names = {f.name for f in fields(cls)}
        bad = set(d) - names
        if bad:
            raise ValueError(f"unknown beat keys {sorted(bad)}; valid: {sorted(names)}")
        return cls(**d)


# ============================================================================================ script parsing
_LINE = re.compile(r"^\s*(?P<name>[A-Z][\w]*(?: [A-Z][\w]*)?)\s*(?:\((?P<opts>[^)]*)\))?\s*:\s*(?P<text>.+?)\s*$")
_DIRECTIVE = re.compile(r"^\s*(?:@|\[)\s*(?P<loc>[\w ]+?)\s*\]?\s*$")


def parse_script(text: str, known=()) -> list:
    """Plain script -> [Beat]. Syntax (one beat per line, '#' comments):

        @cafeteria                              (location directive; sticks until changed)
        Milo (shocked, drop, to=Ava, prop=tray, loc=cafeteria, dur=2.5): He dropped his tray.
        Ava: Nice one.                          (dialogue with `to=` omitted: partner = last other speaker)
        Then everybody laughed.                 (narration: emotion/action/character inferred from the words)
    """
    beats, loc, last = [], None, None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _DIRECTIVE.match(line)
        if m and (line.startswith("@") or line.startswith("[")) and not _LINE.match(line):
            loc = m.group("loc").strip()
            continue
        m = _LINE.match(line)
        if m and (m.group("name") in known or not known or " " not in m.group("name")) and len(m.group("name")) < 24:
            b = Beat(text=m.group("text"), character=m.group("name"))
            for tok in [t.strip() for t in (m.group("opts") or "").split(",") if t.strip()]:
                if "=" in tok:
                    k, v = [x.strip() for x in tok.split("=", 1)]
                    k = {"to": "target", "loc": "location", "dur": "duration", "trans": "transition"}.get(k, k)
                    if k == "duration":
                        v = float(v)
                    if k == "shot" and "|" in v:
                        v = v.split("|")
                    if k == "cast":
                        v = [x.strip() for x in v.split("|")]
                    if hasattr(b, k):
                        setattr(b, k, v)
                elif PR.norm_emotion(tok) != "neutral" or tok.lower() in PR.EMOTIONS or tok.lower() in PR.EMOTION_ALIASES:
                    b.emotion = tok.lower()
                elif tok.lower() in PR.ACTIONS:
                    b.action = tok.lower()
                else:
                    b.mood = tok.lower()
        else:
            b = Beat(text=line)
        if b.location is None and loc:
            b.location = loc
        beats.append(b)
        last = b
    return beats


def _infer(beat: Beat, known_names, prev_char):
    """Fill emotion / action / character from the words when not given."""
    low = " " + beat.text.lower() + " "
    if beat.emotion is None:
        for keys, emo in PR.KEYWORD_EMOTION:
            if any(k in low for k in keys):
                beat.emotion = emo
                break
    if beat.action is None:
        for keys, act in PR.KEYWORD_ACTION:
            if any(k in low for k in keys):
                beat.action = act
                break
    if beat.character is None:
        found = [n for n in known_names if re.search(rf"\b{re.escape(n)}\b", beat.text)]
        if found:
            beat.character = found[0]
        else:
            caps = [w for w in re.findall(r"\b[A-Z][a-z]{2,}\b", beat.text) if w not in _STOP_NAMES]
            beat.character = caps[0] if caps else (prev_char or (known_names[0] if known_names else "Milo"))
    return beat


# ============================================================================================ faces
def _faces_mod():
    try:
        from . import faces                       # may not exist yet (separate module)
        return faces
    except Exception:
        return None


def _face_name(f):
    if f is None:
        return None
    if isinstance(f, str):
        return f
    if isinstance(f, dict):
        return f.get("id") or f.get("name") or f.get("file")
    return getattr(f, "id", None) or getattr(f, "name", None) or getattr(f, "path", None)


class FacePicker:
    """Picks faces for an emotion: library search first (faces.search/random), procedural faces as fallback."""

    def __init__(self, seed=0, use_library=True):
        self.seed = seed
        self.mod = _faces_mod() if use_library else None
        self._cache = {}
        self.library_ok = False
        if self.mod is not None:
            try:
                self.library_ok = bool(self.mod.search(["happy"], any_=True, limit=1) or self.mod.search(["smile"], any_=True, limit=1))
            except Exception:
                self.library_ok = False

    def pool(self, emotion):
        emo = PR.get_emotion(emotion)
        key = PR.norm_emotion(emotion)
        if key in self._cache:
            return self._cache[key]
        names = []
        if self.library_ok:
            for tags in ([emo["face_tags"][0]], emo["face_tags"][:2]):
                try:
                    res = self.mod.search(list(tags), any_=True, limit=40)
                except Exception:
                    res = []
                for r in res or []:
                    n = _face_name(r)
                    if n and n not in names:
                        names.append(n)
                if len(names) >= 6:
                    break
        names = names[:40] + list(emo["faces"])
        self._cache[key] = names
        return names

    def pick(self, emotion, rng, avoid=None):
        pool = self.pool(emotion)
        lib, proc = pool[:-len(PR.get_emotion(emotion)["faces"])] or pool, PR.get_emotion(emotion)["faces"]
        cand = [p for p in (lib if self.library_ok and len(pool) > len(proc) else pool) if p != avoid]
        return str(cand[int(rng.integers(len(cand)))]) if cand else "smile"


# ============================================================================================ Director
@dataclass
class _Plan:
    kind: str
    subject: Any = None
    other: Optional[str] = None
    follow: bool = False
    az: Optional[float] = None
    el: Optional[float] = None
    fill: Optional[float] = None
    fov: Optional[float] = None
    screen_y: Optional[float] = None
    focus: Optional[str] = None
    distance: Optional[float] = None
    moves: list = field(default_factory=list)
    role: str = "normal"
    damping: float = 0.3
    transition: Any = None
    face_emotion: Optional[str] = None


class Director:
    """Turns a story (list of Beat / dicts / script text / JSON) into a Scene.

    Parameters
      pace            "fast" | "normal" | "slow" (shot length + speaking rate); or a float multiplier of avg_shot_len
      style           caption style "storytime" | "yellow_pop" | "two_line", or a variant letter "A".."D"
      shot_mix        weights {"wide":1,"medium":1.4,"closeup":1.5,"extreme_closeup":1.6,"insert":.7,"low_angle_hero":.5}
      avg_shot_len    seconds (default from pace, 1.4)
      characters      {name: avatar-dict}; list of names or dicts; missing characters get varied outfits
      lighting/mood   force one lighting preset for the whole story; or a mood word
      face_variety    0..1 chance of a second face swap inside long shots
      transitions     0..1 scales how often cut-hiding transitions are used (1 = reference density)
      seed            everything random derives from it
    """

    def __init__(self, story, characters=None, seed=0, pace="normal", style="storytime", shot_mix=None,
                 avg_shot_len=None, size=(1080, 1920), fps=30, lighting=None, mood=None, caption_y=None,
                 face_variety=0.8, transitions=1.0, use_faces=True, default_location="street", name="story",
                 style_variant=None, words_per_sec=None, end_hold=0.5):
        self.seed = int(seed)
        self.pace = pace
        pcfg = PR.PACE.get(pace) if isinstance(pace, str) else None
        if pcfg is None:
            pcfg = dict(avg_shot_len=1.4 * float(pace), wps=3.4 / float(pace)) if not isinstance(pace, str) else PR.PACE["normal"]
        self.avg = float(avg_shot_len or pcfg["avg_shot_len"])
        self.wps = float(words_per_sec or pcfg["wps"])
        var = style_variant or (style if style in CAPTION_VARIANTS else None)
        self.cap = dict(CAPTION_VARIANTS[var]) if var else dict(style=style, y=0.64, font_scale=1.0)
        if caption_y is not None:
            self.cap["y"] = caption_y
        self.mix = dict(PR.DEFAULT_SHOT_MIX)
        self.mix.update(shot_mix or {})
        self.size, self.fps, self.name = size, fps, name
        self.force_lighting = lighting
        self.mood = mood
        self.face_variety, self.transitions = float(face_variety), float(transitions)
        self.use_faces = use_faces
        self.default_location = default_location
        self.end_hold = end_hold
        self._char_in = characters
        self.story = story
        self.beats: list = []
        self.scene: Optional[Scene] = None
        self.log: list = []

    # ------------------------------------------------------------------ input normalisation
    def _normalise(self):
        names = []
        if self._char_in:
            for c in (self._char_in.items() if isinstance(self._char_in, dict) else
                      [(x, {}) if isinstance(x, str) else (x["name"], x) for x in self._char_in]):
                names.append(c[0])
        story = self.story
        if isinstance(story, str):
            s = story.strip()
            if s.startswith("[") or s.startswith("{"):
                import json
                story = json.loads(s)
                if isinstance(story, dict):
                    story = story.get("beats", [])
            else:
                story = parse_script(story, known=names)
        beats = []
        for b in story:
            if isinstance(b, Beat):
                beats.append(Beat(**{f.name: getattr(b, f.name) for f in fields(Beat)}))
            elif isinstance(b, str):
                beats.append(Beat(text=b))
            elif isinstance(b, dict):
                beats.append(Beat.from_dict(b))
            else:
                raise TypeError(f"cannot read beat {b!r}")
        prev_char, loc = None, None
        known = list(names)
        for b in beats:
            _infer(b, known, prev_char)
            if b.character and b.character not in known:
                known.append(b.character)
            if b.target and b.target not in known:
                known.append(b.target)
            for c in (b.cast or []):
                if c not in known:
                    known.append(c)
            prev_char = b.character
            if b.location:
                loc = b.location
            else:
                b.location = loc or self.default_location
            b.emotion = PR.norm_emotion(b.emotion)
            b.action = (b.action or "").lower() or None
        self.beats = beats
        self._names = known

    def _make_characters(self):
        given = {}
        if self._char_in:
            items = self._char_in.items() if isinstance(self._char_in, dict) else \
                [(x, {}) if isinstance(x, str) else (x["name"], {k: v for k, v in x.items() if k != "name"}) for x in self._char_in]
            for n, a in items:
                given[n] = dict(a)
        order = list(range(len(PR.OUTFITS)))
        np.random.default_rng(self.seed).shuffle(order)
        out = {}
        for i, n in enumerate(self._names):
            a = dict(given.get(n, {}))
            if not (a.get("hair") or a.get("shirt") or a.get("shirt_color")):
                o = dict(PR.OUTFITS[order[i % len(order)]])
                o["skin"] = PR.SKINS[(order[i % len(order)] + self.seed) % len(PR.SKINS)]
                o.update(a)
                a = o
            out[n] = a
        return out

    # ------------------------------------------------------------------ build
    def build(self) -> Scene:
        self._normalise()
        W, H = self.size
        sc = Scene(W, H, self.fps, seed=self.seed, name=self.name)
        self.scene = sc
        chars = self._make_characters()
        for n, a in chars.items():
            sc.add_character(n, avatar=a, position=(0, 0, 0))
        faces = FacePicker(self.seed, self.use_faces)
        self.faces = faces
        vis: dict = {n: [] for n in chars}               # visible windows
        cur = {n: dict(pos=np.zeros(3), yaw=0.0, face=None) for n in chars}
        loc_sets: dict = {}
        prev_loc = None
        prev_size = None
        prev_present: list = []
        prev_dutch = 1
        t = 0.0
        last_main = None
        run_count = 0
        for bi, b in enumerate(self.beats):
            rng = np.random.default_rng([self.seed, bi, 17])
            loc_info = PR.get_location(b.location)
            lname = loc_info["name"]
            light = self._lighting_for(b, loc_info)
            set_key = lname if light == loc_info["lighting"] else f"{lname}@{light}"
            if set_key not in loc_sets:
                sc.add_set(set_key, location=lname, lighting=light)
                loc_sets[set_key] = loc_info
            loc_change = prev_loc is not None and set_key != prev_loc
            first_in_loc = (set_key != prev_loc)
            main = b.character or last_main or next(iter(chars))
            last_main = main
            end = dirv = speed = None
            self._cur_set = set_key
            action = b.action
            is_run = action in RUN_ACTIONS
            emo = b.emotion
            emo_cfg = PR.get_emotion(emo)
            # ---------------- duration
            D = self._duration(b, bi)
            t0, t1 = t, t + D
            if bi == len(self.beats) - 1:
                t1 += self.end_hold
                D += self.end_hold
            # ---------------- captions (word timing)
            words = []
            if b.text and not b.silent:
                from .captions import CaptionTrack
                tr = CaptionTrack.from_text(b.text, t0 + 0.04, max(t0 + 0.5, t0 + D - (self.end_hold if bi == len(self.beats) - 1 else 0.06)),
                                            style=self.cap["style"])
                words = list(tr.words)
                sc.add_caption(words=words, style=self.cap["style"], y=self.cap["y"], font_scale=self.cap["font_scale"])
            wstarts = [w[1] for w in words]
            # ---------------- staging
            others = []
            for c in ([b.target] if b.target else []) + list(b.cast or []):
                if c and c != main and c not in others:
                    others.append(c)
            dialogue = bool(b.target) and not is_run and b.target in chars
            present = [main] + others
            if not is_run and not b.cast and not b.target:
                present += [c for c in prev_present if c not in present and prev_loc == set_key and not self._was_run(prev_loc, bi)]
            if is_run:
                present = [main] + ([b.target] if b.target else [])
            heading = 0.0 if loc_info["cam_side"] < 0 else 180.0
            y0 = loc_info["y"]
            slots = [(x, z) for x, z in loc_info["slots"]]
            place = {}
            if is_run:
                run_count += 1
                p0, p1 = [np.array([x, y0, z], float) for x, z in loc_info["run"]]
                if run_count % 2 == 0:
                    p0, p1 = p1, p0
                d = p1 - p0
                full = float(np.linalg.norm(d))
                dirv = d / max(full, 1e-6)
                speed = 21.0 if (action in ("sprint", "flee") or emo == "scared") else 16.0
                T_run = max(0.5, D - 0.25)
                dist = min(full, speed * T_run)
                end = p0 + dirv * dist
                yaw = math.degrees(math.atan2(-dirv[0], -dirv[2]))
                place[main] = (p0, yaw)
                if len(present) > 1:
                    place[present[1]] = (p0 - dirv * 5.5, yaw)
            elif dialogue:
                cx, cz = slots[1] if len(slots) > 1 else slots[0]
                a_pos = np.array([cx - 2.4, y0, cz])
                b_pos = np.array([cx + 2.4, y0, cz])
                place[main] = (a_pos, -90.0)
                place[b.target] = (b_pos, 90.0)
                k = 0
                for c in present:
                    if c not in place:
                        place[c] = (np.array([cx + (4.6 + 3.2 * k) * (1 if k % 2 == 0 else -1), y0, cz + 2.0]), heading)
                        k += 1
            else:
                order = [main] + [c for c in present if c != main]
                n = len(order)
                use = slots if n >= 3 else ([slots[1]] if n == 1 else [slots[0], slots[2]])
                if n == 2:
                    # main on the camera-left slot facing the camera; partner beside
                    use = [slots[1], slots[2]] if rng.random() < 0.5 else [slots[0], slots[1]]
                for k, c in enumerate(order):
                    x, z = use[k % len(use)]
                    place[c] = (np.array([x, y0, z]), heading)
            # place actions (teleports only when needed)
            for c, (p, yaw) in place.items():
                st = cur[c]
                moved = float(np.linalg.norm((st["pos"] - p))) > 0.05 or abs(((st["yaw"] - yaw + 180) % 360) - 180) > 4
                if moved or first_in_loc or c not in prev_present:
                    sc.place(c, p, t0, facing=yaw)
                    st["pos"], st["yaw"] = p.copy(), yaw
            for c in chars:
                if c in present:
                    vis[c].append([t0, t1])
            # ---------------- actions / animation
            self._animate(sc, b, bi, rng, faces, chars, main, present, dialogue, is_run, t0, t1, D, loc_info, place,
                          cur, end, dirv, speed, wstarts)
            # ---------------- shots
            plans = self._plan_shots(b, bi, rng, main, present, dialogue, is_run, emo, emo_cfg, D, first_in_loc,
                                     loc_info, prev_size, prev_dutch, bi == 0)
            lens = self._lengths(plans, D, wstarts, t0, rng)
            if b.transition is not None:
                plans[0].transition = b.transition
            elif first_in_loc and bi > 0:
                plans[0].transition = self._loc_transition(rng)
            tt = t0
            for k, (p, ln) in enumerate(zip(plans, lens)):
                sh = Shot(tt, tt + ln if k < len(plans) - 1 else t1, kind=p.kind, set=set_key, subject=p.subject,
                          other=p.other, follow=p.follow, damping=p.damping, azimuth=p.az, elevation=p.el, fill=p.fill, fov=p.fov,
                          screen_y=p.screen_y, focus=p.focus, distance=p.distance, moves=p.moves,
                          transition=p.transition, label=f"b{bi}:{p.role}")
                self._apply_camera_override(sh, b)
                sc.shots.append(sh)
                if k == 0 and plans[0].face_emotion is None:
                    pass
                tt += ln
                prev_size = PR.SIZE_CLASS.get(p.kind, 1)
                if p.moves and any(m.get("type") == "dutch" for m in p.moves):
                    prev_dutch = -1 if p.moves[0].get("degrees", 1) > 0 else 1
            # face micro-variation + reaction face timing
            self._faces_for_beat(sc, b, rng, faces, main, present, chars, emo, plans, [s for s in sc.shots if s.label and s.label.startswith(f"b{bi}:")], cur)
            prev_loc = set_key
            prev_present = list(present)
            t = t1
        for n, w in vis.items():
            merged = []
            for a, bb in w:
                if merged and abs(merged[-1][1] - a) < 1e-6:
                    merged[-1][1] = bb
                else:
                    merged.append([a, bb])
            spec = sc._char_spec(n)
            spec["visible"] = merged
        sc.invalidate()
        sc.meta["director"] = {"seed": self.seed, "pace": self.pace, "style": self.cap, "beats": len(self.beats)}
        return sc

    # ------------------------------------------------------------------ helpers
    def _was_run(self, loc, bi):
        return bi > 0 and self.beats[bi - 1].action in RUN_ACTIONS

    def _lighting_for(self, b: Beat, loc_info):
        if b.lighting:
            return b.lighting
        if b.mood:
            return PR.MOOD_LIGHTING.get(b.mood, loc_info["lighting"])
        if self.force_lighting:
            return self.force_lighting
        if self.mood:
            return PR.MOOD_LIGHTING.get(self.mood, loc_info["lighting"])
        low = b.text.lower()
        if "night" in low or "midnight" in low:
            return "night"
        if "sunset" in low or "evening" in low:
            return "sunset"
        if "snow" in low or "blizzard" in low:
            return "snow"
        return loc_info["lighting"]

    def _duration(self, b: Beat, bi: int) -> float:
        if b.duration:
            return float(b.duration)
        n = len(b.text.split()) if (b.text and not b.silent) else 0
        D = n / self.wps + 0.25 if n else 1.4
        floor = 1.3
        if b.action == "drop":
            floor = 2.4
        elif b.action in RUN_ACTIONS:
            floor = 2.2
        elif PR.get_emotion(b.emotion)["energy"] >= 0.85:
            floor = 1.7
        return max(floor, D)

    # ------------------------------------------------------------------ animation
    def _animate(self, sc, b, bi, rng, faces, chars, main, present, dialogue, is_run, t0, t1, D, loc_info, place, cur,
                 end, dirv, speed, wstarts):
        emo, emo_cfg, action = b.emotion, PR.get_emotion(b.emotion), b.action
        y0 = loc_info["y"]
        act = PR.ACTIONS.get(action) if action else None
        clip = (act or {}).get("clip") if act else (action if action else None)
        if clip is None:
            clip = emo_cfg["clips"][int(rng.integers(len(emo_cfg["clips"])))]
            if dialogue and emo in ("neutral", "happy"):
                clip = "talk"
        # --- run / chase
        if is_run:
            gait = "sprint_panic" if (speed and speed > 18) else "run"
            T0 = t0 + 0.1
            for k, c in enumerate(present):
                p0, yaw = place[c]
                delay = 0.0 if k == 0 else 0.3
                if end is None:
                    continue
                dist = float(np.linalg.norm(end - p0)) if k == 0 else float(np.linalg.norm(end - place[main][0]))
                tgt = p0 + dirv * (dist)
                sc.move_to(c, tgt, T0 + delay, t1 - 0.1, ease="linear", face=False, gait=gait if k == 0 else "run")
                sc.add_fx("footsteps", character=c, t0=T0 + delay, t1=t1 - 0.1, y=y0, set=None)
                cur[c]["pos"] = tgt
            if emo in ("scared", "shocked"):
                pass
            return
        # --- main character acting
        t_act = t0 + float(rng.uniform(0.0, 0.12))
        if action == "drop":
            self._tray_drop(sc, b, bi, main, t0, t1, D, y0, place[main][0], cur)
        elif act and act.get("move"):                          # walk / jog / sneak: short stroll
            p = place[main][0]
            dirx = 1.0 if rng.random() < 0.5 else -1.0
            tgt = p + np.array([dirx * min(7.0, 2.2 * D), 0, 0.0])
            sc.move_to(main, tgt, t0 + 0.1, t1 - 0.15, face=True, gait=("sneak" if clip == "sneak" else "auto"))
            cur[main]["pos"] = tgt
        else:
            sc.play(main, clip, t_act, until=t1)
            if emo in ("angry", "scared") and clip != emo_cfg["clips"][0] and rng.random() < 0.0:
                pass
        # --- dialogue: both look at each other, listener reacts a bit
        if dialogue:
            tgt = b.target
            sc.look_at(main, tgt, t0, t1)
            sc.look_at(tgt, main, t0, t1)
            if wstarts:
                sc.play(tgt, "nod" if emo not in ("angry", "shocked") else "shock", t0 + max(0.6, 0.5 * D), until=t1)
        # --- others present: ambient acting
        for c in present:
            if c == main or (dialogue and c == b.target) or is_run:
                continue
            if rng.random() < 0.7:
                sc.play(c, ["talk", "nod", "clap", "shrug", "cheer"][int(rng.integers(5))] if emo in ("happy", "laughing", "excited") else
                        ["idle_bored", "nod", "look_around"][int(rng.integers(3))], t0 + float(rng.uniform(0.1, 0.6)), until=t1)
        if b.prop and action != "drop":
            self._prop(sc, b, bi, main, t0, t1, y0, place[main][0])
        for f in (b.fx or []):
            spec = {"type": f} if isinstance(f, str) else dict(f)
            spec.setdefault("t", t0 + 0.3)
            p = place[main][0]
            spec.setdefault("pos", [float(p[0]), float(p[1]), float(p[2])])
            sc.add_fx(**spec)

    _PROPS = {"tray": ("crate", dict(size=(2.2, 0.18, 1.7), color="#b9bcc4")),
              "duck": ("duck_toy", {}), "ball": ("ball", dict(radius=0.9, color="#c4281c")),
              "coin": ("coin", dict(radius=0.9)), "crate": ("crate", {}), "sign": ("sign", {}),
              "table": ("table", {}), "chair": ("chair", {}), "car": ("car", {})}

    def _prop(self, sc, b, bi, main, t0, t1, y0, p):
        spec = self._PROPS.get(b.prop, (b.prop, {}))
        name = f"{b.prop}{bi}"
        sc.add_prop(name, spec[0], spec[1], position=[float(p[0]) + 1.6, y0, float(p[2]) - 1.6],
                    visible=[t0 - 0.01, t1 + 0.5], set=self._cur_set)

    def _tray_drop(self, sc, b, bi, main, t0, t1, D, y0, p, cur):
        t_drop = t0 + 0.62 * D
        name = f"tray{bi}"
        floor = [float(p[0]), y0, float(p[2]) - 1.7]
        # tray + a few food blocks as children
        sc.add_prop(name, "crate", dict(size=(2.2, 0.18, 1.7), color="#b9bcc4"), position=floor,
                    attach={"to": main, "part": "Right Arm", "part_offset": None, "offset": [0.0, -1.05, -0.9],
                            "rotation": [0, 0, 0], "until": t_drop},
                    set=self._cur_set, visible=[t0 - 0.01, 1e9],
                    keys=[{"t": t_drop, "position": "attach", "rotation": [0, 0, 0]},
                          {"t": t_drop + 0.5, "position": [floor[0] + 0.5, y0 + 0.02, floor[2] - 0.9],
                           "rotation": [0, 35, 12], "ease": "bounce_out"},
                          {"t": t_drop + 0.9, "position": [floor[0] + 0.5, y0 + 0.02, floor[2] - 0.9],
                           "rotation": [0, 35, 0]}])
        # food: three blocks that tumble from the tray
        cols = ["#c4281c", "#f5cd30", "#4caf50"]
        for k in range(3):
            fn = f"food{bi}_{k}"
            dx = (k - 1) * 0.55
            sc.add_prop(fn, "crate", dict(size=(0.7, 0.5, 0.7), color=cols[k]), position=floor,
                        attach={"to": main, "part": "Right Arm", "offset": [dx * 0.8, -1.35, -0.9 + 0.1 * k],
                                "rotation": [0, 0, 0], "until": t_drop},
                        set=self._cur_set, visible=[t0 - 0.01, 1e9],
                        keys=[{"t": t_drop, "position": "attach", "rotation": [0, 0, 0]},
                              {"t": t_drop + 0.55, "position": [floor[0] + dx * 3.2 + 0.4, y0 + 0.02, floor[2] - 1.2 - 0.6 * k],
                               "rotation": [180 * (k + 1), 90 * k, 40], "ease": "bounce_out"},
                              {"t": t_drop + 1.2, "position": [floor[0] + dx * 3.4 + 0.5, y0 + 0.02, floor[2] - 1.3 - 0.6 * k],
                               "rotation": [180 * (k + 1), 90 * k, 40]}])
        sc.add_fx("dust", t=t_drop + 0.4, pos=[floor[0] + 0.5, y0, floor[2] - 0.9], size=0.7, count=5)
        sc.play(main, "shock", t_drop + 0.05, until=t1)

    # ------------------------------------------------------------------ shot planning
    def _wchoice(self, rng, kinds):
        w = np.array([max(1e-6, self.mix.get(k, 0.5)) for k in kinds], float)
        return kinds[int(rng.choice(len(kinds), p=w / w.sum()))]

    def _plan_shots(self, b, bi, rng, main, present, dialogue, is_run, emo, emo_cfg, D, first_in_loc, loc_info,
                    prev_size, prev_dutch, very_first):
        avg = self.avg * (1.12 - 0.35 * emo_cfg["energy"])
        n = max(1, int(round(D / avg)))
        if D / n > 2.5:
            n += 1
        n = min(n, 6)
        forced = b.shot if isinstance(b.shot, list) else ([b.shot] if b.shot else None)
        if forced:
            n = len(forced)
        tgt = b.target
        prop_name = None
        if b.action == "drop":
            prop_name = f"prop:tray{bi}"
        elif b.prop:
            prop_name = f"prop:{b.prop}{bi}"
        seq: list = []
        energy = emo_cfg["energy"]
        react = energy >= 0.85 or (b.action == "drop")
        if forced:
            seq = [(k, "forced") for k in forced]
        elif is_run:
            narrow = bool(loc_info.get("bounds")) and (loc_info["bounds"][1] - loc_info["bounds"][0]) < 24
            chaser = len(present) > 1
            if narrow:
                pat = ["front_tracking", "insert_feet", "front_tracking", "chase_behind"]
            else:
                pat = ["side_tracking", "front_tracking", "insert_feet", "low_angle_hero", "side_tracking"]
            if not chaser and not narrow:
                pat = ["side_tracking", "chase_behind", "insert_feet", "low_angle_hero", "side_tracking"]
            off = int(rng.integers(len(pat)))
            seq = [(pat[(off + k) % len(pat)], "run") for k in range(n)]
        elif dialogue:
            pat = ["two_shot", "closeup_main", "closeup_target", "over_shoulder", "extreme_closeup_main", "closeup_target"]
            if n == 1:
                seq = [("over_shoulder", "dialogue")]
            else:
                seq = [(pat[k % len(pat)], "dialogue") for k in range(n)]
        elif b.action == "drop":
            pat = ["medium", "insert_prop", "extreme_closeup", "closeup", "wide"]
            if first_in_loc:
                pat = ["wide", "medium", "insert_prop", "extreme_closeup", "closeup"]
            seq = [(pat[k % len(pat)], "drop") for k in range(n)]
        elif react:
            if n == 1:
                seq = [("extreme_closeup", "react")]
            elif n == 2:
                seq = [("medium", "action"), ("extreme_closeup", "react")]
            else:
                seq = [("wide", "establish"), ("extreme_closeup", "react"), ("closeup", "react"), ("medium", "action"),
                       ("insert", "insert")][:n]
                while len(seq) < n:
                    seq.append(("medium", "action"))
        else:
            prev = prev_size
            for k in range(n):
                if k == 0 and (first_in_loc or very_first):
                    kind = "wide"
                else:
                    pref = emo_cfg["cams"]
                    cands = ["wide", "medium", "closeup", "extreme_closeup", "insert", "low_angle_hero"]
                    cands = [c for c in cands if prev is None or abs(PR.SIZE_CLASS[c] - prev) >= 1]
                    if prev is not None and prev >= 2:
                        cands = [c for c in cands if PR.SIZE_CLASS[c] < 2 or c == "insert"] or cands
                    if any(s[0] == "insert" for s in seq):
                        cands = [c for c in cands if c != "insert"] or cands
                    if not (prop_name or True):
                        cands = [c for c in cands if c != "insert"]
                    w = np.array([self.mix.get(c, 0.5) * (1.8 if c in pref else 1.0) for c in cands])
                    kind = cands[int(rng.choice(len(cands), p=w / w.sum()))]
                prev = PR.SIZE_CLASS[kind]
                seq.append((kind, "establish" if kind == "wide" and k == 0 else "normal"))
        plans = []
        sign = -prev_dutch if prev_dutch else 1
        for k, (kind, role) in enumerate(seq):
            p = self._make_plan(kind, role, b, bi, rng, main, tgt, prop_name, loc_info, k, sign, emo, energy)
            if p.moves and any(m.get("type") == "dutch" for m in p.moves):
                sign = -sign
            plans.append(p)
        # transition choice inside the beat
        for k, p in enumerate(plans):
            if k == 0:
                continue
            p.transition = self._inner_transition(p, plans[k - 1], rng, emo, is_run)
        # size must change on every cut (also across beats)
        alt = {"wide": "medium", "medium": "closeup", "closeup": "medium", "extreme_closeup": "medium",
               "low_angle_hero": "closeup", "high_angle": "closeup"}
        before = prev_size
        for p in plans:
            if p.role in ("normal", "action", "establish") and before is not None and p.kind in alt \
                    and PR.SIZE_CLASS[p.kind] == before and not forced:
                self._make_plan_inplace(p, alt[p.kind], b, bi, rng, main, tgt, prop_name, loc_info, emo, energy)
            before = PR.SIZE_CLASS.get(p.kind, 1)
        # shock beat: punch-in on the first reaction shot
        for p in plans:
            if p.role in ("react", "drop") and "extreme_closeup" in p.kind and emo in ("shocked", "scared") and p.transition is None:
                p.transition = {"type": "zoom_punch", "strength": 0.16}
                if emo == "shocked" and rng.random() < 0.5 * self.transitions:
                    p.transition = [p.transition, {"type": "flash", "dur": 0.08}]
                break
        return plans

    def _make_plan_inplace(self, p, kind, b, bi, rng, main, tgt, prop_name, loc_info, emo, energy):
        q = self._make_plan(kind, p.role, b, bi, rng, main, tgt, prop_name, loc_info, 0, 1, emo, energy)
        q.subject = p.subject if kind != "insert" else q.subject
        p.__dict__.update(q.__dict__)

    def _make_plan(self, kind, role, b, bi, rng, main, tgt, prop_name, loc_info, k, sign, emo, energy):
        side = 1 if rng.random() < 0.5 else -1
        P = _Plan(kind=kind, subject=main, role=role)
        if kind.startswith("closeup_") or kind.startswith("extreme_closeup_"):
            who = kind.rsplit("_", 1)[1]
            P.kind = kind[: -len(who) - 1]
            P.subject = tgt if (who == "target" and tgt) else main
            P.other = None
            kind = P.kind
        if kind == "insert_feet":
            P.kind, P.focus, P.subject, P.follow, P.damping = "insert", "feet", main, True, 0.1
            P.distance, P.az, P.el = 3.4, side * 30, -10
            P.moves = [{"type": "drift", "amount": 0.15}]
            return P
        if kind == "insert_prop":
            if prop_name:
                P.kind, P.subject = "insert", prop_name
                P.distance, P.az, P.el, P.fov = 4.6, side * 25, 15, 70
            else:
                P.kind, P.focus, P.distance, P.az, P.el = "insert", "hands", 3.0, side * 25, -4
            return P
        if kind == "insert":
            if prop_name and rng.random() < 0.8:
                P.subject, P.distance, P.az, P.el = prop_name, 4.2, side * 25, 12
            else:
                P.focus, P.distance, P.az, P.el = ("hands" if rng.random() < 0.6 else "feet"), 3.2, side * 28, -6
            return P
        if kind == "wide":
            P.az, P.el, P.fill = side * float(rng.uniform(15, 38)), float(rng.uniform(-2, 8)), float(rng.uniform(0.34, 0.46))
            P.screen_y = 0.46
            P.moves = [{"type": "push_in", "rate": float(rng.uniform(0.05, 0.09))}, {"type": "drift", "amount": 0.3}]
            if loc_info["name"] in ("school_hallway", "cafeteria", "classroom") and rng.random() < 0.3:
                P.kind, P.el, P.fill = "high_angle", float(rng.uniform(28, 42)), 0.30
        elif kind == "medium":
            P.az, P.el, P.screen_y = side * float(rng.uniform(8, 28)), float(rng.uniform(-9, -2)), 0.45
            P.moves = [{"type": "push_in", "rate": float(rng.uniform(0.04, 0.07))}]
            if rng.random() < 0.5:
                P.moves.append({"type": "drift", "amount": 0.2})
            if role in ("action",) and b.action and b.action in PR.ACTIONS and PR.ACTIONS[b.action].get("move"):
                P.follow = True
        elif kind == "closeup":
            P.az, P.el, P.fov, P.screen_y = side * float(rng.uniform(8, 24)), float(rng.uniform(-10, -4)), 78.0, 0.40
            P.moves = [{"type": "push_in", "rate": float(rng.uniform(0.05, 0.07))}]
            if rng.random() < 0.6:
                P.moves.append({"type": "dutch", "degrees": sign * float(rng.uniform(3, 5)), "ramp": 0.4})
        elif kind == "extreme_closeup":
            P.az, P.el, P.fov, P.screen_y = side * float(rng.uniform(8, 22)), float(rng.uniform(-9, -3)), 82.0, 0.42
            P.moves = [{"type": "push_in", "rate": float(rng.uniform(0.06, 0.08))},
                       {"type": "dutch", "degrees": sign * float(rng.uniform(3, 6)), "ramp": 0.35}]
            if emo in ("shocked", "angry", "scared"):
                P.moves.append({"type": "shake", "amp": 0.03, "freq": 11.0})
        elif kind == "low_angle_hero":
            P.az, P.el, P.fill, P.screen_y = side * float(rng.uniform(10, 30)), -20.0, 0.52, 0.46
            P.moves = [{"type": "push_in", "rate": 0.05}]
        elif kind == "two_shot":
            P.other, P.subject = tgt, main
            P.az, P.el, P.fill = side * float(rng.uniform(0, 14)), 6.0, 0.40
            P.moves = [{"type": "push_in", "rate": 0.04}, {"type": "drift", "amount": 0.2}]
        elif kind == "over_shoulder":
            P.other, P.subject = tgt, main
            P.moves = [{"type": "push_in", "rate": 0.05}, {"type": "drift", "amount": 0.15}]
            if k % 2 == 1:
                P.subject, P.other = tgt or main, main
        elif kind == "front_tracking":
            P.kind, P.follow, P.damping = "medium", True, 0.08
            P.az, P.el, P.screen_y = side * float(rng.uniform(0, 10)), -4.0, 0.45
            P.moves = [{"type": "shake", "amp": 0.05, "freq": 7.0}]
        elif kind in ("side_tracking", "chase_behind"):
            P.follow = True
            P.damping = 0.18
            P.el = float(rng.uniform(2, 10))
            P.moves = [{"type": "drift", "amount": 0.12}]
            if kind == "chase_behind":
                P.az = side * float(rng.uniform(0, 8 if (loc_info.get("bounds") and loc_info["bounds"][1] - loc_info["bounds"][0] < 24) else 25))
            if role == "run":
                P.moves.append({"type": "shake", "amp": 0.05, "freq": 7.0})
        return P

    def _loc_transition(self, rng):
        return ({"type": "whip", "direction": ["left", "right"][int(rng.integers(2))], "dur": 0.17}
                if rng.random() < 0.45 else {"type": "dust_cover", "dur": 0.42})

    def _inner_transition(self, p, prev, rng, emo, is_run):
        r = rng.random()
        k = self.transitions
        if p.role == "run" or is_run:
            if r < 0.40 * k:
                return {"type": "whip", "direction": ["left", "right"][int(rng.integers(2))], "dur": 0.15}
            return None
        big = abs(PR.SIZE_CLASS.get(p.kind, 1) - PR.SIZE_CLASS.get(prev.kind, 1)) >= 2
        if p.kind == "extreme_closeup" and r < 0.18 * k:
            return {"type": "sweep", "dur": 0.24, "direction": 1.0 if rng.random() < 0.5 else -1.0}
        if big and r < 0.22 * k:
            return {"type": "dust_cover", "dur": 0.4}
        if r < 0.10 * k:
            return {"type": "whip", "direction": ["left", "right", "up"][int(rng.integers(3))], "dur": 0.15}
        return None

    # ------------------------------------------------------------------ shot lengths / cut snapping
    def _lengths(self, plans, D, wstarts, t0, rng):
        n = len(plans)
        base = []
        for p in plans:
            lo, typ, hi = PR.SHOT_LENGTHS.get(p.kind, (1.0, 1.5, 2.2))
            if p.kind == "insert":
                typ = 0.8
            base.append(typ * float(rng.uniform(0.85, 1.2)))
        s = sum(base)
        lens = [D * x / s for x in base]
        # cuts land on caption word starts
        if n > 1 and wstarts:
            cum = np.cumsum(lens)[:-1] + t0
            new = []
            prev_cut = t0
            for ci, c in enumerate(cum):
                j = int(np.argmin([abs(w - c) for w in wstarts]))
                cand = wstarts[j]
                if abs(cand - c) <= 0.32 and cand - prev_cut >= 0.55:
                    c = cand
                new.append(c)
                prev_cut = c
            edges = [t0] + new + [t0 + D]
            ls = [edges[i + 1] - edges[i] for i in range(n)]
            if min(ls) >= 0.5:
                lens = ls
        return lens

    def _apply_camera_override(self, sh: Shot, b: Beat):
        o = b.camera or {}
        for k, v in o.items():
            if k == "moves":
                sh.moves = list(sh.moves) + list(v)
            elif k == "azimuth":
                sh.azimuth = v
            elif k == "elevation":
                sh.elevation = v
            elif hasattr(sh, k):
                setattr(sh, k, v)

    # ------------------------------------------------------------------ faces
    def _faces_for_beat(self, sc, b, rng, faces, main, present, chars, emo, plans, shots, cur):
        t0 = shots[0].t0
        # main: expression change on the reaction shot (or at the beat start if there is none)
        react = next((s for s, p in zip(shots, plans) if p.role in ("react", "drop")), None)
        t_main = (react.t0 - 0.04) if (react is not None and emo != "neutral") else t0
        if b.action == "drop":
            t_main = react.t0 - 0.04 if react else t0 + 0.62 * (shots[-1].t1 - t0)
        face = b.face or faces.pick(emo, rng, avoid=cur[main]["face"])
        sc.face(main, face, max(0.0, t_main))
        cur[main]["face"] = face
        for c in present:
            if c == main:
                continue
            e2 = {"laughing": "laughing", "happy": "happy"}.get(emo, "neutral") if emo != "shocked" else "shocked"
            if c == b.target and emo in ("angry", "shocked", "scared"):
                e2 = "scared" if emo == "angry" else "shocked"
            f2 = faces.pick(e2, rng, avoid=cur[c]["face"])
            sc.face(c, f2, t0 + float(rng.uniform(0.2, 0.7)))
            cur[c]["face"] = f2
        # mid-shot swaps: closeups longer than ~1.2 s get a second expression (STYLE: faces swap every 0.5-2 s)
        for s, p in zip(shots, plans):
            if s.kind in ("closeup", "extreme_closeup") and (s.t1 - s.t0) >= 1.25 and rng.random() < self.face_variety:
                who = p.subject if isinstance(p.subject, str) and p.subject in chars else main
                e = emo if who == main else "neutral"
                f3 = faces.pick(e, rng, avoid=cur[who]["face"])
                if f3 != cur[who]["face"]:
                    sc.face(who, f3, s.t0 + 0.55 * (s.t1 - s.t0))
                    cur[who]["face"] = f3


def direct(story, **kw) -> Scene:
    """Shortcut: Director(story, **kw).build()."""
    return Director(story, **kw).build()
