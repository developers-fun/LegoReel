"""Sound for r6reel: the stickreel synthesised-sfx engine (see sfx.py, no sample files, no licences).

Scene "audio" is either a path to an audio file (muxed as before) or a dict:
  "audio": {"master": 0.9, "music": {"file": "bed.mp3", "gain": 0.25, "start": 0, "fade_out": 1.0},
            "cues": [ {"sfx": "whoosh", "times": "transition:whip", "delay": -0.12, "gain": 0.3},
                      {"sfx": "step", "times": "steps:Jay", "gain": 0.22, "pitch_jitter": 0.08},
                      {"sfx": "pop", "times": "words", "gain": 0.12},
                      {"sfx": "ding", "t": 4.9}, {"file": "sfx/clap.mp3", "t": 3.0} ]}
cue keys: sfx | file, t | times, gain (1.0), pitch (1.0), pitch_jitter (0), pan (-1..1), delay (s, shifts every time), seed.
times: [seconds...] | {"from","to","every"} | "shots" (every shot start) | "transition:<type>" (starts of shots entered with that
  transition, e.g. whip, zoom_punch) | "steps:<character>" (footfalls of that character's walk/run move_to actions)
  | "words" (every caption word start).
List the sounds: python3 -m r6reel sfx        Mix only the sound: python3 -m r6reel audio scene.json --out mix.wav
Rule of the owner's taste: a hard cut gets a soft sound; put a whoosh before a blur, never a sharp sound on a hard cut.
"""
import os
import subprocess

import numpy as np

from .sfx import SR, SFX, render_sfx

CUE_KEYS = {"sfx", "file", "t", "times", "gain", "pitch", "pitch_jitter", "pan", "delay", "seed"}
AUDIO_KEYS = {"master", "music", "cues"}
STEP_EVERY = {"walk": 0.36, "run": 0.24}


def is_spec(audio):
    return isinstance(audio, dict)


def validate(spec):
    """-> list of warning strings."""
    W = []
    for k in spec:
        if k not in AUDIO_KEYS:
            W.append(f"audio: unknown key {k!r}. Allowed: {', '.join(sorted(AUDIO_KEYS))}")
    for i, c in enumerate(spec.get("cues", [])):
        w = f"audio cue {i}"
        for k in c:
            if k not in CUE_KEYS:
                W.append(f"{w}: unknown key {k!r}. Allowed: {', '.join(sorted(CUE_KEYS))}")
        if ("sfx" in c) == ("file" in c):
            W.append(f"{w}: give exactly one of 'sfx' or 'file'")
        if "sfx" in c and c["sfx"] not in SFX:
            W.append(f"{w}: unknown sfx {c['sfx']!r}. Built in: {', '.join(SFX)}")
        if ("t" in c) == ("times" in c):
            W.append(f"{w}: give exactly one of 't' or 'times'")
    return W


def _tr_type(tr):
    if tr is None:
        return []
    if isinstance(tr, (str, dict)):
        tr = [tr]
    return [(x if isinstance(x, str) else x.get("type", "cut")) for x in tr]


def resolve_times(scene, spec):
    """-> list of seconds."""
    if isinstance(spec, (int, float)):
        return [float(spec)]
    if isinstance(spec, (list, tuple)):
        return [float(x) for x in spec]
    if isinstance(spec, dict):
        t, out = float(spec["from"]), []
        while t <= float(spec["to"]) + 1e-9:
            out.append(t)
            t += float(spec["every"])
        return out
    if spec == "shots":
        return [s.t0 for s in scene.shots]
    if spec == "words":
        out = []
        for c in scene.captions:
            if "words" in c:
                out += [float(w[1]) for w in c["words"]]
            else:
                out.append(float(c["t0"]))
        return out
    if isinstance(spec, str) and spec.startswith("transition:"):
        kind = spec.split(":", 1)[1]
        return [s.t0 for s in scene.shots if kind in _tr_type(s.transition)]
    if isinstance(spec, str) and spec.startswith("steps:"):
        who, out = spec.split(":", 1)[1], []
        for a in scene.actions:
            if a.get("character") == who and a["type"] == "move_to" and a.get("gait", "walk") in STEP_EVERY:
                t, t1, dt = float(a["t0"]), float(a["t1"]), STEP_EVERY[a.get("gait", "walk")]
                t += dt / 2
                while t < t1:
                    out.append(t)
                    t += dt
        return out
    raise ValueError(f"audio: cannot read times {spec!r}")


_FILES = {}


def load_file(path):
    if path not in _FILES:
        p = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                           capture_output=True)
        if p.returncode != 0:
            raise RuntimeError(f"audio: cannot read '{path}': {p.stderr.decode()[:200]}")
        _FILES[path] = np.frombuffer(p.stdout, dtype=np.float32).reshape(-1, 2).copy()
    return _FILES[path]


def _stereo(mono, pan):
    pan = max(-1.0, min(1.0, pan))
    ang = (pan + 1) * np.pi / 4
    return np.stack([mono * np.cos(ang), mono * np.sin(ang)], axis=1)


def mix(scene, spec, start=0.0, end=None, base_dir="."):
    """-> float32 (n, 2) covering [start, end) seconds."""
    end = scene.duration if end is None else end
    n = int(round((end - start) * SR))
    out = np.zeros((n, 2), dtype=np.float32)

    def add(samples, t, gain):
        i0 = int(round((t - start) * SR))
        if i0 >= n or i0 + len(samples) <= 0:
            return
        a0, a1 = max(0, -i0), min(len(samples), n - i0)
        out[i0 + a0:i0 + a1] += samples[a0:a1] * gain

    res = lambda p: p if os.path.isabs(p) else os.path.join(base_dir, p)
    for ci, c in enumerate(spec.get("cues", [])):
        times = resolve_times(scene, c["t"] if "t" in c else c["times"])
        rng = np.random.default_rng(int(c.get("seed", 0)) * 1000 + ci)
        for k, t in enumerate(times):
            t = t + c.get("delay", 0.0)
            pitch = c.get("pitch", 1.0) * (1.0 + rng.uniform(-1, 1) * c.get("pitch_jitter", 0.0))
            gain = c.get("gain", 1.0) * (1.0 + rng.uniform(-0.08, 0.08))
            st = _stereo(render_sfx(c["sfx"], pitch, seed=ci * 101 + k), c.get("pan", 0.0)) if "sfx" in c \
                else load_file(res(c["file"]))
            add(st, t, gain)
    m = spec.get("music")
    if m:
        st = load_file(res(m["file"]))
        seg = st[int(max(0.0, start - m.get("start", 0.0)) * SR):][:n]
        g = np.full(len(seg), m.get("gain", 0.3), dtype=np.float32)
        fo = m.get("fade_out", 0.0)
        if fo > 0:
            nf = min(int(fo * SR), len(g))
            g[len(g) - nf:] *= np.linspace(1, 0, nf)
        out[:len(seg)] += seg * g[:, None]
    out *= spec.get("master", 0.9)
    peak = float(np.max(np.abs(out))) if n else 0.0
    if peak > 0.98:
        out *= 0.98 / peak
    return out


def write_wav(path, stereo):
    import wave
    pcm = (np.clip(stereo, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
