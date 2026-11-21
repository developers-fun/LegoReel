"""Sound: cues from a scene's "audio" section are mixed into one stereo track and muxed into the MP4.

"audio": {"master": 0.9, "music": {"file": "bed.mp3", "gain": 0.25, "start": 0, "fade_out": 1.0},
          "cues": [ {"sfx": "thunk", "times": "you.hit", "gain": 0.8, "pitch_jitter": 0.06},
                    {"sfx": "boom", "t": 8.0, "gain": 1.0},
                    {"sfx": "tick", "times": {"from": 9.4, "to": 9.8, "every": 0.034}, "gain": 0.3},
                    {"file": "sfx/clap.mp3", "t": 3.0} ] }
cue keys: sfx | file, t | times, gain (1.0), pitch (1.0), pitch_jitter (0), pan (-1 left .. 1 right), delay (s, shifts every time), seed.
times: [seconds...] | "actor.hit" | "actor.step" (footfalls of walk/run loops) | {"from","to","every"}.
Built-in sounds are synthesised (stickreel/sfx.py, no files, no licences): python3 -m stickreel sfx
"""
import subprocess

import numpy as np

from .sfx import SR, SFX, render_sfx
from .track import SceneError

CUE_KEYS = {"sfx", "file", "t", "times", "gain", "pitch", "pitch_jitter", "pan", "delay", "seed"}
AUDIO_KEYS = {"master", "music", "cues"}


def validate(spec, suggest):
    bad = [k for k in spec if k not in AUDIO_KEYS]
    if bad:
        raise SceneError(f"audio: unknown key '{bad[0]}'.{suggest(bad[0], AUDIO_KEYS)} Allowed: {', '.join(sorted(AUDIO_KEYS))}")
    for i, c in enumerate(spec.get("cues", [])):
        w = f"audio cue {i}"
        bad = [k for k in c if k not in CUE_KEYS]
        if bad:
            raise SceneError(f"{w}: unknown key '{bad[0]}'.{suggest(bad[0], CUE_KEYS)} Allowed: {', '.join(sorted(CUE_KEYS))}")
        if ("sfx" in c) == ("file" in c):
            raise SceneError(f"{w}: give exactly one of 'sfx' (built-in sound) or 'file'")
        if "sfx" in c and c["sfx"] not in SFX:
            raise SceneError(f"{w}: unknown sfx '{c['sfx']}'.{suggest(c['sfx'], SFX)} Built in: {', '.join(SFX)}")
        if ("t" in c) == ("times" in c):
            raise SceneError(f"{w}: give exactly one of 't' (seconds) or 'times'")


_FILES = {}


def load_file(path):
    """decode any audio file to stereo float32 at SR via ffmpeg (cached)."""
    if path not in _FILES:
        p = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                           capture_output=True)
        if p.returncode != 0:
            raise SceneError(f"audio: cannot read '{path}': {p.stderr.decode()[:200]}")
        _FILES[path] = np.frombuffer(p.stdout, dtype=np.float32).reshape(-1, 2).copy()
    return _FILES[path]


def _resolve_path(scene, p):
    import os
    return p if os.path.isabs(p) else os.path.join(scene.base_dir, p)


def _stereo(mono, pan):
    pan = max(-1.0, min(1.0, pan))
    ang = (pan + 1) * np.pi / 4
    return np.stack([mono * np.cos(ang), mono * np.sin(ang)], axis=1)


def mix(scene, start=0.0, end=None):
    """-> float32 (n, 2) array covering [start, end) seconds."""
    spec = scene.audio or {}
    end = scene.duration if end is None else end
    n = int(round((end - start) * SR))
    out = np.zeros((n, 2), dtype=np.float32)

    def add(samples, t, gain):
        i0 = int(round((t - start) * SR))
        if i0 >= n or i0 + len(samples) <= 0:
            return
        a0 = max(0, -i0)
        a1 = min(len(samples), n - i0)
        out[i0 + a0:i0 + a1] += samples[a0:a1] * gain

    for ci, c in enumerate(spec.get("cues", [])):
        times = [c["t"]] if "t" in c else scene.times(c["times"])
        rng = np.random.default_rng(int(c.get("seed", 0)) * 1000 + ci)
        for k, t in enumerate(times):
            t = t + c.get("delay", 0.0)
            pitch = c.get("pitch", 1.0) * (1.0 + rng.uniform(-1, 1) * c.get("pitch_jitter", 0.0))
            gain = c.get("gain", 1.0) * (1.0 + rng.uniform(-0.08, 0.08))
            if "sfx" in c:
                mono = render_sfx(c["sfx"], pitch, seed=ci * 101 + k)
                st = _stereo(mono, c.get("pan", 0.0))
            else:
                st = load_file(_resolve_path(scene, c["file"]))
            add(st, t, gain)
    m = spec.get("music")
    if m:
        st = load_file(_resolve_path(scene, m["file"]))
        t0 = m.get("start", 0.0)
        seg = st[int(max(0.0, start - t0) * SR):]
        seg = seg[:n]
        g = np.full(len(seg), m.get("gain", 0.3), dtype=np.float32)
        fo = m.get("fade_out", 0.0)
        if fo > 0:
            nf = min(int(fo * SR), len(g))
            g[len(g) - nf:] *= np.linspace(1, 0, nf)
        out[:len(seg)] += seg * g[:, None]
    out *= spec.get("master", 0.9)
    peak = float(np.max(np.abs(out))) if n else 0.0
    if peak > 0.98:                                    # keep it out of clipping
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


def mux(video_path, wav_path, out_path):
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", video_path, "-i", wav_path, "-map", "0:v", "-map", "1:a",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", out_path])
    if r.returncode != 0:
        raise RuntimeError("ffmpeg mux failed")
