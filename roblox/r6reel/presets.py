"""Presets: time-of-day lighting, locations (world layouts), shot-size rhythm and emotion tables.

Everything here is plain data + tiny helpers, so a Scene JSON can name them ("lighting": "sunset",
"location": "cafeteria") and a Director can look them up.

Lighting presets give the world lighting keys (sun_dir, sun_color, sun_intensity, ambient, sky_top,
sky_bottom, fog_color, fog_density, shadow_extent) plus a ``post`` dict of PostFx defaults.  The sun
direction is the direction the light TRAVELS.  Presets assume the camera lives on the -Z side of the
action (``cam_side=-1``); for sets with ``cam_side=+1`` the z component is mirrored by the Scene so
faces stay lit.
"""
from __future__ import annotations

import copy

# --------------------------------------------------------------------------------------------
# Lighting / time of day
# --------------------------------------------------------------------------------------------

LIGHTING = {
    "day": dict(
        sun_dir=(-0.55, -0.80, 0.45), sun_color=(1.0, 0.95, 0.86), sun_intensity=1.05,
        ambient=(0.60, 0.65, 0.78), sky_top="#4f9bff", sky_bottom="#cfe9ff",
        fog_color="#cfe9ff", fog_density=0.0035, shadow_extent=40.0,
        post=dict(bloom=0.16, vignette=0.17, saturation=1.12, contrast=1.06, exposure=1.0)),
    "sunset": dict(
        sun_dir=(-0.85, -0.38, 0.55), sun_color=(1.0, 0.66, 0.38), sun_intensity=0.9,
        ambient=(0.55, 0.46, 0.54), sky_top="#5d6fd0", sky_bottom="#ffb06a",
        fog_color="#ffb98a", fog_density=0.006, shadow_extent=45.0,
        post=dict(bloom=0.26, vignette=0.24, saturation=1.2, contrast=1.08, exposure=1.0)),
    "night": dict(
        sun_dir=(-0.4, -0.85, 0.45), sun_color=(0.55, 0.68, 1.0), sun_intensity=0.55,
        ambient=(0.30, 0.34, 0.56), sky_top="#070d26", sky_bottom="#1d2c5c",
        fog_color="#16224a", fog_density=0.006, shadow_extent=40.0,
        post=dict(bloom=0.34, vignette=0.32, saturation=1.05, contrast=1.1, exposure=1.08)),
    "snow": dict(
        sun_dir=(-0.35, -0.9, 0.3), sun_color=(0.92, 0.95, 1.0), sun_intensity=0.7,
        ambient=(0.78, 0.82, 0.92), sky_top="#b7c6d8", sky_bottom="#eef3f8",
        fog_color="#e3ebf3", fog_density=0.018, shadow_extent=36.0,
        post=dict(bloom=0.2, vignette=0.2, saturation=0.9, contrast=0.98, exposure=1.02)),
    "indoor_warm": dict(
        sun_dir=(-0.3, -0.9, 0.35), sun_color=(1.0, 0.82, 0.58), sun_intensity=0.75,
        ambient=(0.78, 0.62, 0.50), sky_top="#8a6a50", sky_bottom="#c9a27a",
        fog_color=None, fog_density=0.0, shadow_extent=24.0,
        post=dict(bloom=0.22, vignette=0.26, saturation=1.1, contrast=1.05, exposure=1.0)),
    "school_day": dict(
        sun_dir=(-0.35, -0.9, 0.35), sun_color=(0.98, 0.97, 0.94), sun_intensity=0.55,
        ambient=(0.52, 0.56, 0.66), sky_top="#8fc2ff", sky_bottom="#dff0ff",
        fog_color=None, fog_density=0.0, shadow_extent=26.0,
        post=dict(bloom=0.12, vignette=0.16, saturation=1.08, contrast=1.04, exposure=1.0)),
    "cinematic_dark": dict(
        sun_dir=(-0.6, -0.55, 0.55), sun_color=(1.0, 0.78, 0.55), sun_intensity=0.8,
        ambient=(0.26, 0.28, 0.40), sky_top="#0b1020", sky_bottom="#2a2f45",
        fog_color="#1a1e30", fog_density=0.009, shadow_extent=34.0,
        post=dict(bloom=0.3, vignette=0.42, saturation=0.95, contrast=1.16, exposure=1.0, grain=0.03)),
}
LIGHTING_ALIASES = {"daytime": "day", "dusk": "sunset", "evening": "sunset", "dark": "cinematic_dark",
                    "winter": "snow", "indoor": "indoor_warm", "school": "school_day", "night_time": "night"}

MOOD_LIGHTING = {  # mood word -> lighting preset (director)
    "happy": "day", "funny": "day", "calm": "day", "tense": "cinematic_dark", "scary": "night",
    "sad": "sunset", "dramatic": "sunset", "cozy": "indoor_warm", "cold": "snow", "school": "school_day",
}


def lighting_names():
    return sorted(LIGHTING)


def get_lighting(name_or_dict) -> dict:
    """Lighting preset -> a fresh dict (with a 'post' sub-dict). Accepts a name or a dict (merged over 'day')."""
    if isinstance(name_or_dict, dict):
        base = copy.deepcopy(LIGHTING[name_or_dict.get("base", "day")])
        for k, v in name_or_dict.items():
            if k == "post":
                base["post"].update(v)
            elif k != "base":
                base[k] = v
        return base
    name = LIGHTING_ALIASES.get(str(name_or_dict), str(name_or_dict))
    if name not in LIGHTING:
        raise KeyError(f"unknown lighting preset {name_or_dict!r}; known: {lighting_names()}")
    return copy.deepcopy(LIGHTING[name])


# --------------------------------------------------------------------------------------------
# Locations (world layouts)
# --------------------------------------------------------------------------------------------

def B(builder, pos=(0, 0, 0), rot=(0, 0, 0), scale=None, **args):
    d = {"builder": builder, "args": args, "position": list(pos), "rotation": list(rot)}
    if scale is not None:
        d["scale"] = scale
    return d


def _street():
    b = [B("ground", size=(260, 260)),
         B("road", (0, 0, 0), length=200, width=10),
         B("sidewalk", (0, 0, 7.5), length=200, width=5, height=0.1),
         B("sidewalk", (0, 0, -7.5), length=200, width=5, height=0.1)]
    cols = ["#f5cd30", "#e8e0c8", "#6fb1e8", "#e88a8a", "#9bd16f", "#f2a65a"]
    roofs = ["#c4281c", "#3a3d42", "#8c5a2b", "#0d69ac"]
    for i, x in enumerate(range(-72, 80, 16)):
        b.append(B("house", (x, 0, 20), w=10, d=10, h=7 + (i % 3), color=cols[i % 6], roof_color=roofs[i % 4]))
        b.append(B("fence", (x, 0, 13.5), length=11, height=2.2))
        if i % 2 == 0:
            b.append(B("tree", (x + 8, 0, 14), kind="round"))
        b.append(B("lamp_post", (x + 6, 0, 10.2)))
    b.append(B("car", (-16, 0.1, 2.0), (0, 90, 0), color="#0d69ac"))
    b.append(B("sign", (14, 0, 10.5), (0, 180, 0)))
    for x in (-60, -30, 30, 60):
        b.append(B("cloud", (x, 55, 120), puffs=6, seed=abs(x)))
    return dict(builders=b, lighting="day", y=0.1, cam_side=-1,
                bounds=[-80, 80, -10, 18], slots=[(-3, 7.5), (0.5, 7.5), (4, 7.5)],
                run=[(-24, 7.5), (24, 7.5)], prop_spot=(2, 7.5), seat=None)


def _house_exterior():
    b = [B("ground", size=(260, 260)),
         B("road", (0, 0, -3), length=200, width=8),
         B("sidewalk", (0, 0, 3), length=200, width=3, height=0.1),
         B("house", (0, 0, 22), w=16, d=12, h=9, color="#e8e0c8", roof_color="#8c5a2b"),
         B("house", (-24, 0, 24), color="#6fb1e8", roof_color="#3a3d42"),
         B("house", (24, 0, 24), color="#e88a8a", roof_color="#c4281c"),
         B("fence", (-8, 0, 12), length=14, height=2.2), B("fence", (8, 0, 12), length=14, height=2.2),
         B("tree", (-12, 0, 16), kind="round"), B("tree", (13, 0, 17), kind="round", leaf_color="#2e7d32"),
         B("bush", (-3, 0, 14.8)), B("bush", (3, 0, 14.8)),
         B("door", (0, 0, 15.7), color="#c4281c")]
    return dict(builders=b, lighting="day", y=0.1, cam_side=-1, bounds=[-60, 60, -14, 12],
                slots=[(-3, 5), (0, 5), (3, 5)], run=[(-22, 5), (22, 5)], prop_spot=(2, 5), seat=None)


def _park():
    b = [B("ground", size=(260, 260), color="#5fb04e")]
    for i, (x, z) in enumerate([(-22, 18), (-10, 26), (8, 22), (24, 16), (-34, 8), (36, 6), (0, 34)]):
        b.append(B("tree", (x, 0, z), kind="round" if i % 3 else "pine"))
    b += [B("bench", (-6, 0, 8), (0, 180, 0)), B("bench", (7, 0, 9), (0, 180, 0)),
          B("lamp_post", (-14, 0, 10)), B("lamp_post", (14, 0, 10)),
          B("bush", (-18, 0, 9)), B("bush", (19, 0, 11)), B("sidewalk", (0, 0, 0), length=120, width=5, height=0.1),
          B("fence", (0, 0, 42), length=80, height=3), B("cloud", (-40, 50, 110), puffs=7, seed=2),
          B("cloud", (30, 56, 120), puffs=5, seed=5)]
    return dict(builders=b, lighting="day", y=0.0, cam_side=-1, bounds=[-70, 70, -30, 36],
                slots=[(-3, 3), (0.5, 3), (4, 3)], run=[(-26, 1), (26, 1)], prop_spot=(2, 3), seat=None)


def _snow_field():
    b = [B("ground", size=(300, 300), color="#f3f7fb", material="smooth")]
    for i, (x, z) in enumerate([(-20, 18), (-8, 28), (10, 20), (26, 30), (-34, 10), (36, 12), (0, 40), (-26, 36)]):
        b.append(B("tree", (x, 0, z), kind="pine", leaf_color="#2f6b4f"))
    b += [B("bench", (-6, 0, 10), (0, 180, 0), color="#8c5a2b"), B("lamp_post", (12, 0, 12)),
          B("house", (-30, 0, 44), color="#e8e0c8", roof_color="#f2f3f3")]
    return dict(builders=b, lighting="snow", y=0.0, cam_side=-1, bounds=[-90, 90, -40, 60],
                slots=[(-3, 2), (0.5, 2), (4, 2)], run=[(-26, 0), (26, 0)], prop_spot=(2, 2), seat=None,
                fx=[{"type": "snow", "density": 1.0}])


def _school_hallway():
    b = [B("school_hallway", length=60),
         B("brick_wall", (0, 0, 30.2), w=13, h=12, color="#e5e4df"),
         B("door", (0, 0, 29.6), (0, 180, 0), color="#0d69ac"),
         B("ground", (0, -0.1, 0), size=(120, 120), material="plastic", color="#8a8a90")]
    return dict(builders=b, lighting="school_day", y=0.0, cam_side=-1, bounds=[-5.2, 5.2, -29, 28],
                slots=[(-1.8, -6), (1.8, -6), (0, -2.5)], run=[(0, 16), (0, -12)], prop_spot=(0, -5), seat=None)


def _classroom():
    b = [B("classroom", rows=4, cols=5),
         B("ground", (0, -0.1, 0), size=(160, 160), material="plastic", color="#8a8a90"),
         B("window_wall", (-16.2, 2.0, 2), (0, 90, 0), w=12, h=7, cols=3, rows=1)]
    return dict(builders=b, lighting="school_day", y=0.0, cam_side=1, bounds=[-15.5, 15.5, -17, 17.3],
                slots=[(-5, -14.6), (0, -14.6), (5, -14.6)], run=[(-14, -14.6), (14, -14.6)],
                prop_spot=(0, -14.6), seat=(0, 1.1, -9.6))


def _cafeteria():
    b = [B("cafeteria"), B("ground", (0, -0.1, 0), size=(160, 160), material="plastic", color="#8a8a90")]
    return dict(builders=b, lighting="school_day", y=0.0, cam_side=-1, bounds=[-19, 19, -60, 19.2],
                slots=[(-3, -15), (0, -15), (3, -15)], run=[(-16, -15), (16, -15)],
                prop_spot=(0, -14), seat=(0, 1.9 - 0.0, -3.4))


def _bedroom():
    b = [B("bedroom"), B("ground", (0, -0.1, 0), size=(160, 160), material="plastic", color="#8a8a90")]
    return dict(builders=b, lighting="indoor_warm", y=0.0, cam_side=-1, bounds=[-7.4, 7.4, -40, 7.6],
                slots=[(-1.5, -3.2), (1.8, -3.2), (0.2, -1)], run=[(-6, -4), (6, -4)],
                prop_spot=(2, -3), seat=None)


def _town_square():
    b = [B("town_square")]
    return dict(builders=b, lighting="day", y=0.2, cam_side=-1, bounds=[-55, 55, -40, 22],
                slots=[(-3, -13), (0.5, -13), (4, -13)], run=[(-16, -13), (16, -13)],
                prop_spot=(2, -13), seat=None)


def _castle():
    b = [B("ground", size=(300, 300), color="#6a9f55")]
    for i in range(7):
        x = -18 + i * 6
        b.append(B("brick_wall", (x, 0, 18), w=6, h=9 if i % 2 else 10, thickness=2, color="#9a9a9e"))
    b += [B("brick_wall", (-22, 0, 26), w=10, h=9, color="#9a9a9e"),
          B("skyscraper", (0, 0, 34), floors=10, w=14, d=14, floor_h=3.2, color="#8f8f95"),
          B("skyscraper", (-24, 0, 30), floors=8, w=9, d=9, floor_h=3.2, color="#8f8f95"),
          B("skyscraper", (24, 0, 30), floors=8, w=9, d=9, floor_h=3.2, color="#8f8f95"),
          B("door", (0, 0, 17.4), (0, 180, 0), w=6, h=8, color="#5b3a1d"),
          B("stairs", (0, 0, 8), steps=5, step_w=8),
          B("tree", (-30, 0, 6), kind="pine"), B("tree", (30, 0, 6), kind="pine"),
          B("cloud", (0, 50, 100), puffs=7, seed=9)]
    return dict(builders=b, lighting="sunset", y=0.0, cam_side=-1, bounds=[-70, 70, -30, 17],
                slots=[(-3, -4), (0.5, -4), (4, -4)], run=[(-20, -4), (20, -4)], prop_spot=(2, -4), seat=None)


LOCATIONS = {
    "street": _street, "house_exterior": _house_exterior, "park": _park, "snow_field": _snow_field,
    "school_hallway": _school_hallway, "classroom": _classroom, "cafeteria": _cafeteria,
    "bedroom": _bedroom, "town_square": _town_square, "castle": _castle,
}
LOCATION_ALIASES = {
    "hallway": "school_hallway", "hall": "school_hallway", "school": "school_hallway", "corridor": "school_hallway",
    "lunchroom": "cafeteria", "canteen": "cafeteria", "class": "classroom", "room": "bedroom",
    "house": "house_exterior", "yard": "house_exterior", "home": "house_exterior", "outside": "street",
    "road": "street", "sidewalk": "street", "square": "town_square", "plaza": "town_square", "town": "town_square",
    "tower": "castle", "fortress": "castle", "snow": "snow_field", "blizzard": "snow_field", "winter": "snow_field",
    "garden": "park", "playground": "park",
}


def location_names():
    return sorted(LOCATIONS)


def get_location(name) -> dict:
    """Location spec dict (fresh): builders, lighting, y, cam_side, bounds, slots, run, prop_spot, seat, fx."""
    key = LOCATION_ALIASES.get(str(name).lower().replace(" ", "_"), str(name).lower().replace(" ", "_"))
    if key not in LOCATIONS:
        raise KeyError(f"unknown location {name!r}; known: {location_names()} (+ aliases {sorted(LOCATION_ALIASES)})")
    d = LOCATIONS[key]()
    d["name"] = key
    return d


def builder_names():
    """World builder functions usable in a scene's 'builders' list."""
    import inspect
    from . import world
    out = []
    for n in sorted(dir(world)):
        f = getattr(world, n)
        if inspect.isfunction(f) and f.__module__ == world.__name__ and not n.startswith("_") \
                and n != "crowd_positions":
            out.append(n)
    return out


def build_world_props(builders):
    """list of builder dicts -> list of world.Prop with transforms applied."""
    from . import world
    props = []
    for spec in builders:
        fn = getattr(world, spec["builder"], None)
        if fn is None or spec["builder"] not in builder_names():
            raise KeyError(f"unknown world builder {spec['builder']!r}; known: {builder_names()}")
        p = fn(**(spec.get("args") or {}))
        p.position = tuple(spec.get("position", (0, 0, 0)))
        p.rotation = tuple(spec.get("rotation", (0, 0, 0)))
        sc = spec.get("scale", 1.0)
        p.scale = tuple(sc) if isinstance(sc, (list, tuple)) else (sc, sc, sc)
        props.append(p)
    return props


# --------------------------------------------------------------------------------------------
# Shot-size rhythm
# --------------------------------------------------------------------------------------------

# size class 0..4 : 0 wide, 1 medium, 2 closeup, 3 extreme closeup, 4 insert.
SIZE_CLASS = {"wide": 0, "high_angle": 0, "top_down": 0, "low_angle_hero": 0, "two_shot": 1, "medium": 1,
              "over_shoulder": 1, "chase_behind": 1, "side_tracking": 1, "pov": 1, "closeup": 2,
              "extreme_closeup": 3, "insert": 4}

# STYLE.md: ESTABLISH -> REACT -> ACTION -> INSERT -> repeat
RHYTHM = ["wide", "extreme_closeup", "medium", "insert", "closeup", "medium", "extreme_closeup", "wide",
          "closeup", "medium", "insert", "extreme_closeup"]

DEFAULT_SHOT_MIX = {"wide": 1.0, "medium": 1.4, "closeup": 1.5, "extreme_closeup": 1.6, "insert": 0.7,
                    "low_angle_hero": 0.5}

# typical lengths in seconds (min, typical, max) per kind
SHOT_LENGTHS = {"wide": (1.4, 2.0, 2.8), "medium": (1.1, 1.5, 2.2), "closeup": (0.9, 1.3, 2.0),
                "extreme_closeup": (0.9, 1.4, 2.4), "insert": (0.5, 0.8, 1.2), "low_angle_hero": (1.0, 1.5, 2.2),
                "two_shot": (1.2, 1.7, 2.4), "over_shoulder": (1.0, 1.5, 2.2), "chase_behind": (1.0, 1.4, 2.0),
                "side_tracking": (1.0, 1.4, 2.0), "high_angle": (1.2, 1.8, 2.6), "pov": (0.8, 1.2, 1.8),
                "top_down": (1.0, 1.5, 2.0)}

PACE = {"fast": dict(avg_shot_len=1.15, wps=4.0), "normal": dict(avg_shot_len=1.4, wps=3.4),
        "slow": dict(avg_shot_len=1.9, wps=2.8)}

# --------------------------------------------------------------------------------------------
# Emotions
# --------------------------------------------------------------------------------------------

# emotion -> clips (first = primary), face tags (library search), procedural face fallbacks (avatar.py),
# camera preference, cut energy (0..1; affects shot length + transition choice)
EMOTIONS = {
    "neutral":   dict(clips=["talk", "idle"], face_tags=["smile"], faces=["smile", "neutral"],
                      cams=["medium", "closeup"], energy=0.3),
    "happy":     dict(clips=["cheer", "wave", "talk"], face_tags=["happy", "smile"], faces=["happy", "smile", "wink"],
                      cams=["closeup", "medium", "low_angle_hero"], energy=0.5),
    "laughing":  dict(clips=["laugh"], face_tags=["laughing", "happy"], faces=["laugh", "happy"],
                      cams=["extreme_closeup", "closeup"], energy=0.7),
    "excited":   dict(clips=["cheer", "dance_1", "jump"], face_tags=["happy", "excited"], faces=["happy", "laugh"],
                      cams=["low_angle_hero", "closeup"], energy=0.8),
    "shocked":   dict(clips=["shock"], face_tags=["shocked", "surprised"], faces=["shock", "scared"],
                      cams=["extreme_closeup", "closeup"], energy=1.0),
    "angry":     dict(clips=["angry", "point"], face_tags=["angry", "mad"], faces=["angry"],
                      cams=["extreme_closeup", "low_angle_hero"], energy=0.85),
    "sad":       dict(clips=["cry", "idle_bored"], face_tags=["sad", "crying"], faces=["sad", "cry", "worried"],
                      cams=["closeup", "medium"], energy=0.3),
    "scared":    dict(clips=["scared"], face_tags=["scared", "shocked"], faces=["scared", "shock", "worried"],
                      cams=["extreme_closeup", "closeup"], energy=0.9),
    "bored":     dict(clips=["idle_bored", "shrug"], face_tags=["bored", "neutral"], faces=["neutral", "sleep"],
                      cams=["medium", "closeup"], energy=0.15),
    "confused":  dict(clips=["shrug", "think", "look_around"], face_tags=["confused", "worried"],
                      faces=["worried", "neutral"], cams=["closeup", "medium"], energy=0.4),
    "smirk":     dict(clips=["hands_on_hips", "cross_arms"], face_tags=["smirk", "sly"], faces=["smirk", "wink"],
                      cams=["closeup", "low_angle_hero"], energy=0.5),
    "embarrassed": dict(clips=["facepalm", "shrug"], face_tags=["embarrassed", "worried"],
                        faces=["worried", "sad"], cams=["closeup"], energy=0.4),
    "thinking":  dict(clips=["think", "look_around"], face_tags=["thinking", "confused"], faces=["neutral", "worried"],
                      cams=["closeup", "medium"], energy=0.3),
}
EMOTION_ALIASES = {"surprised": "shocked", "shock": "shocked", "mad": "angry", "furious": "angry", "upset": "sad",
                   "crying": "sad", "afraid": "scared", "terrified": "scared", "scary": "scared", "laugh": "laughing",
                   "funny": "laughing", "joy": "happy", "smile": "happy", "sly": "smirk", "annoyed": "angry",
                   "tired": "bored", "worried": "confused", "puzzled": "confused", "calm": "neutral",
                   "normal": "neutral", "think": "thinking", "hyped": "excited", "proud": "smirk",
                   "nervous": "scared", "awkward": "embarrassed"}


def emotion_names():
    return sorted(EMOTIONS)


def get_emotion(name) -> dict:
    n = EMOTION_ALIASES.get(str(name).lower(), str(name).lower()) if name else "neutral"
    return EMOTIONS.get(n, EMOTIONS["neutral"])


def norm_emotion(name) -> str:
    n = EMOTION_ALIASES.get(str(name).lower(), str(name).lower()) if name else "neutral"
    return n if n in EMOTIONS else "neutral"


# keyword -> emotion hints for plain-text scripts (checked in order)
KEYWORD_EMOTION = [
    (("gasped", "shocked", "froze", "dropped", "screamed", "couldn't believe", "no way", "wait what",
      "suddenly", "stunned", "jaw"), "shocked"),
    (("laughed", "giggled", "hilarious", "funny", "lol", "cracked up"), "laughing"),
    (("angry", "yelled", "furious", "mad ", "shouted", "slammed", "snapped"), "angry"),
    (("cried", "tears", "sad", "heartbroken", "alone", "lonely", "sobbed"), "sad"),
    (("scared", "terrified", "afraid", "panic", "creepy", "followed", "chased", "nervous", "hid "), "scared"),
    (("smirked", "grinned", "plan", "secret", "sneaky", "little did"), "smirk"),
    (("confused", "weird", "strange", "what?", "huh", "wondered", "didn't know", "puzzled"), "confused"),
    (("bored", "boring", "tired", "yawn"), "bored"),
    (("excited", "amazing", "won ", "finally", "best day", "yay", "cheered"), "excited"),
    (("happy", "smiled", "loved", "fun"), "happy"),
]
KEYWORD_ACTION = [
    (("ran ", "run ", "running", "sprinted", "chased", "raced", "bolted", "fled", "escaped", "ran."), "run"),
    (("dropped", "tripped", "spilled", "fell"), "drop"),
    (("walked", "strolled", "headed", "went to", "arrived"), "walk"),
    (("waved", "said hi", "hello"), "wave"),
    (("pointed", "looked at", "noticed", "saw "), "point"),
    (("jumped", "leaped"), "jump"),
    (("danced", "dancing"), "dance"),
    (("sat ", "sitting", "sat."), "sit"),
]

# action word -> clip (+ options)
ACTIONS = {
    "drop": dict(clip="shock", prop="tray"), "run": dict(clip="run", move=True), "sprint": dict(clip="sprint_panic", move=True),
    "chase": dict(clip="run", move=True), "flee": dict(clip="sprint_panic", move=True),
    "walk": dict(clip="walk", move=True), "jog": dict(clip="jog", move=True), "sneak": dict(clip="sneak", move=True),
    "wave": dict(clip="wave"), "point": dict(clip="point"), "jump": dict(clip="jump"), "cheer": dict(clip="cheer"),
    "dance": dict(clip="dance_1"), "talk": dict(clip="talk"), "shrug": dict(clip="shrug"), "facepalm": dict(clip="facepalm"),
    "sit": dict(clip="sit"), "laugh": dict(clip="laugh"), "cry": dict(clip="cry"), "faint": dict(clip="faint"),
    "fall": dict(clip="ragdoll_fall"), "throw": dict(clip="throw"), "kick": dict(clip="kick"), "think": dict(clip="think"),
    "nod": dict(clip="nod"), "shake_head": dict(clip="shake_head"), "bow": dict(clip="bow"), "hug": dict(clip="hug"),
    "flex": dict(clip="flex"), "salute": dict(clip="salute"), "clap": dict(clip="clap"), "scared": dict(clip="scared"),
    "shock": dict(clip="shock"), "angry": dict(clip="angry"), "lean_in": dict(clip="lean_in"),
    "cross_arms": dict(clip="cross_arms"), "stand": dict(clip="idle"), "idle": dict(clip="idle"),
    "look_around": dict(clip="look_around"), "spin": dict(clip="spin"), "climb": dict(clip="climb"),
}

# default avatar looks for variety (STYLE.md "Characters seen")
OUTFITS = [
    dict(hair="spiky:#5a3a22", shirt_color="#3d4468", pants_color="#31456a", accessories=[]),
    dict(hair="pigtails:#e7a1c0", shirt_color="#f08cb4", pants_color="#4a5d8c", accessories=[]),
    dict(hair="buzz:#2a2a2a", shirt_color="#f08c2c", pants_color="#4b5b3a", accessories=[]),
    dict(hair="bun:#9aa0a6", shirt_color="#8e5fb8", pants_color="#6f5a8a", accessories=["glasses"]),
    dict(hair="cap:#c4281c", shirt_color="#c4281c", pants_color="#2d3340", accessories=[]),
    dict(hair="long:#1a1a1a", shirt_color="#f2f3f3", pants_color="#2d3340", accessories=[]),
    dict(hair="afro:#3a2a1a", shirt_color="#ffd23f", pants_color="#3a3d42", accessories=[]),
    dict(hair="bacon:#e0a050", shirt_color="#4caf50", pants_color="#c9b27a", accessories=[]),
]
SKINS = ["#f5cd30", "#f2c9a0", "#d9a577", "#a9764f", "#f5cd30", "#e7b890"]
