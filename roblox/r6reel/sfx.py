"""Procedural sound-effects library for short cartoon/promo videos.

Pure numpy + stdlib. Every sound is synthesised from scratch (no sample files,
no network).

    render_sfx(name, pitch=1.0, seed=0) -> float32 mono array at SR, peak 0.9
    write_wav(path, samples)            -> 16-bit mono PCM WAV
    describe()                          -> {name: one-line description}
    SFX                                 -> {name: fn(rng, pitch)}

pitch is a varispeed multiplier: 2.0 is an octave up and twice as fast.

Self-test: python3 -m r6reel.sfx
"""

import difflib
import wave

import numpy as np

SR = 44100

SFX = {}
_DESC = {}


# ---------------------------------------------------------------- helpers

def _n(sec):
    """Number of samples for a duration in seconds (at pitch 1)."""
    return max(1, int(round(sec * SR)))


def _t(n):
    return np.arange(n) / SR


def _sine(freq, n, phase=0.0):
    """Sine whose frequency may vary per sample. Sample 0 has phase 0."""
    f = np.broadcast_to(np.asarray(freq, dtype=float), (n,))
    ph = np.cumsum(f) - f  # exclusive running sum of frequency
    return np.sin(2.0 * np.pi * ph / SR + phase)


def _env_exp(n, tau):
    """Exponential decay with time constant tau (seconds)."""
    return np.exp(-_t(n) / tau)


def _attack(n, ms):
    """Linear fast attack over ms milliseconds."""
    return np.minimum(1.0, _t(n) / (ms / 1000.0))


def _noise(rng, n):
    return rng.uniform(-1.0, 1.0, n)


def _lp(x, fc):
    """One-pole low-pass. fc may be a scalar or a per-sample array (Hz)."""
    x = np.asarray(x, dtype=float)
    n = x.size
    fc = np.broadcast_to(np.asarray(fc, dtype=float), (n,))
    a = 1.0 - np.exp(-2.0 * np.pi * np.clip(fc, 5.0, 0.45 * SR) / SR)
    out = np.empty(n)
    acc = 0.0
    for i, (xi, ai) in enumerate(zip(x.tolist(), a.tolist())):
        acc += ai * (xi - acc)
        out[i] = acc
    return out


def _hp(x, fc):
    """One-pole high-pass (input minus its low-pass)."""
    x = np.asarray(x, dtype=float)
    return x - _lp(x, fc)


def _glide(f0, f1, n, tau):
    """Frequency falling/rising exponentially from f0 to f1 (tau in seconds)."""
    return f1 + (f0 - f1) * np.exp(-_t(n) / tau)


def _place(out, sig, start):
    """Add sig into out starting at sample start (truncated at the end)."""
    s = int(start)
    if s >= out.size:
        return
    m = min(sig.size, out.size - s)
    out[s:s + m] += sig[:m]


def _varispeed(x, pitch):
    """Resample so the sound plays pitch times faster (and pitch times higher)."""
    if pitch == 1.0:
        return x
    n_out = max(1, int(len(x) / pitch))
    src = np.arange(n_out) * pitch
    return np.interp(src, np.arange(len(x)), x)


def _finish(x, fi_ms=3.0, fo_ms=6.0):
    """Short linear fades at both ends (no clicks), then clip to [-1, 1]."""
    n = x.size
    fi = min(max(1, int(fi_ms * SR / 1000.0)), max(1, n // 4))
    fo = min(max(1, int(fo_ms * SR / 1000.0)), max(1, n // 4))
    env = np.ones(n)
    env[:fi] *= np.linspace(0.0, 1.0, fi, endpoint=False)
    env[n - fo:] *= np.linspace(1.0, 0.0, fo)
    return np.clip(x * env, -1.0, 1.0)


def _sfx(name, desc):
    """Register a native-pitch generator fn(rng) as SFX[name] = fn(rng, pitch)."""
    def deco(gen):
        def run(rng, pitch=1.0):
            x = _varispeed(gen(rng), float(pitch))
            return _finish(x).astype(np.float32)
        run.__doc__ = desc
        run.__name__ = name
        SFX[name] = run
        _DESC[name] = desc
        return gen
    return deco


def _clink_raw(n, ratio=1.0, amp=1.0):
    t = _t(n)
    y = 0.6 * np.sin(2 * np.pi * 2300.0 * ratio * t)
    y += 0.4 * np.sin(2 * np.pi * 3100.0 * ratio * t)
    tr = np.random.default_rng(7).standard_normal(n)         # metal transient: a few ms of band-passed noise
    tr = _lp(_hp(tr, 3000.0), 9000.0) * np.exp(-t / 0.003) * 0.9
    return amp * (y * np.exp(-t / 0.07) + tr) * _attack(n, 0.5)


# ---------------------------------------------------------------- sounds

@_sfx("thunk", "pick hitting rock: low sine drop 120->50 Hz plus noise crack, 0.25 s")
def _thunk(rng):
    n = _n(0.25)
    t = _t(n)
    body = _sine(_glide(120.0, 50.0, n, 0.05), n) * np.exp(-t / 0.09) * 0.9
    crack = _lp(_hp(_noise(rng, n), 1200.0), 6000.0) * np.exp(-t / 0.008) * 1.3
    knock = _sine(_glide(260.0, 130.0, n, 0.03), n) * np.exp(-t / 0.045) * 0.9      # mid layer: phone speakers drop the sub
    return 0.7 * body + crack + knock


@_sfx("whoosh", "swing: band-limited noise, swelling then falling, filter sweeps up then down, 0.35 s")
def _whoosh(rng):
    n = _n(0.35)
    t = _t(n)
    fc = 300.0 + 2800.0 * np.sin(np.pi * t / 0.35) ** 2
    y = _lp(_lp(_noise(rng, n), fc), fc)
    y = _hp(y, 150.0)
    env = np.where(t < 0.16, (t / 0.16) ** 2, np.exp(-(t - 0.16) / 0.1))
    return y * env


@_sfx("dirt", "crumbling dirt: 5-9 tiny noise ticks scattered over 0.4 s, low-passed")
def _dirt(rng):
    n = _n(0.4)
    out = np.zeros(n)
    for _ in range(int(rng.integers(5, 10))):
        start = rng.uniform(0.0, 0.37) * SR
        ln = _n(rng.uniform(0.004, 0.009))
        burst = _noise(rng, ln) * np.exp(-_t(ln) / 0.0025) * rng.uniform(0.3, 1.0)
        _place(out, burst, start)
    return _lp(out, 2200.0)


@_sfx("clink", "single coin clink: two inharmonic sines near 2.3k and 3.1k Hz, fast decay, 0.3 s")
def _clink(rng):
    return _clink_raw(_n(0.3))


@_sfx("coins", "coin pour: 14-20 random clinks of varied pitch over 0.9 s")
def _coins(rng):
    n = _n(0.9)
    out = np.zeros(n)
    for _ in range(int(rng.integers(14, 21))):
        start = rng.uniform(0.0, 0.85) * SR
        ratio = rng.uniform(0.8, 1.3)
        amp = rng.uniform(0.4, 0.9)
        _place(out, _clink_raw(_n(0.3), ratio, amp), start)
    return out


@_sfx("ding", "clean bell: 880 Hz with 2.7x and 4.1x partials, 1.2 s decay")
def _ding(rng):
    n = _n(1.2)
    t = _t(n)
    y = np.sin(2 * np.pi * 880.0 * t) * np.exp(-t / 0.45)
    y += 0.35 * np.sin(2 * np.pi * 880.0 * 2.7 * t) * np.exp(-t / 0.25)
    y += 0.15 * np.sin(2 * np.pi * 880.0 * 4.1 * t) * np.exp(-t / 0.12)
    return y * _attack(n, 2.0)


@_sfx("sparkle", "magic sparkle: 3-5 fast rising bell glints over 0.6 s")
def _sparkle(rng):
    n = _n(0.6)
    out = np.zeros(n)
    k = int(rng.integers(3, 6))
    starts = np.sort(rng.uniform(0.0, 0.38, k))
    ratios = np.sort(rng.uniform(1.0, 1.6, k))
    for s, r in zip(starts, ratios):
        m = _n(0.22)
        t = _t(m)
        f = 1100.0 * r
        tone = _sine(_glide(0.8 * f, f, m, 0.02), m) * np.exp(-t / 0.07)
        tone += 0.25 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t / 0.03)
        _place(out, 0.6 * tone, s * SR)
    return out


@_sfx("riser", "rising sweep: noise and sine 200->1200 Hz, level rising, 1.2 s")
def _riser(rng):
    n = _n(1.2)
    u = _t(n) / 1.2
    tone = 0.5 * u ** 2 * _sine(200.0 * 6.0 ** u, n)
    noise = _lp(_noise(rng, n), 300.0 * 20.0 ** u) * u ** 1.5
    return tone + noise


@_sfx("boom", "flash impact: sine drop 90->35 Hz plus noise burst, long tail, 1.0 s")
def _boom(rng):
    n = _n(1.0)
    t = _t(n)
    body = _sine(35.0 + 55.0 * np.exp(-t / 0.08), n) * np.exp(-t / 0.35)
    body = 0.5 * body + 0.7 * np.tanh(3.0 * body)           # saturation adds harmonics a phone speaker can reproduce
    burst = _lp(_noise(rng, n), 1200.0) * np.exp(-t / 0.12) * 0.8
    mid = _lp(_noise(rng, n), 700.0) * np.exp(-t / 0.22) * 1.2 + _sine(_glide(180.0, 90.0, n, 0.12), n) * np.exp(-t / 0.25) * 0.8
    return 0.5 * body + burst + mid


@_sfx("shimmer", "soft ring expansion: detuned high sines, slow swell and decay, 1.0 s")
def _shimmer(rng):
    n = _n(1.0)
    t = _t(n)
    base = 1500.0 * (1.0 + 0.12 * (1.0 - np.exp(-t / 0.5)))
    y = np.zeros(n)
    for ratio, detune, amp in ((1.0, 0.0, 0.5), (1.5, 4.0, 0.25), (2.01, -5.0, 0.15)):
        y += amp * _sine(base * ratio + detune, n)
    env = (1.0 - np.exp(-t / 0.15)) * np.exp(-t / 0.4)
    return y * env


@_sfx("tick", "tiny typewriter click: high noise transient plus a short 3.2 kHz blip, 0.04 s")
def _tick(rng):
    n = _n(0.04)
    t = _t(n)
    click = _lp(_hp(_noise(rng, n), 1200.0), 6500.0) * np.exp(-t / 0.004)
    blip = 0.5 * np.sin(2 * np.pi * 1900.0 * t) * np.exp(-t / 0.003)
    return click + blip


@_sfx("pop", "bubble pop: short sine pitch up 300->900 Hz, 0.1 s")
def _pop(rng):
    n = _n(0.1)
    t = _t(n)
    f = 900.0 - 600.0 * np.exp(-t / 0.025)
    return _sine(f, n) * np.exp(-t / 0.03)


@_sfx("step", "footstep: low thud with a soft noise puff, 0.12 s")
def _step(rng):
    n = _n(0.12)
    t = _t(n)
    thud = 0.9 * _sine(70.0 + 50.0 * np.exp(-t / 0.015), n) * np.exp(-t / 0.03)
    soft = 2.0 * _lp(_noise(rng, n), 700.0) * np.exp(-t / 0.04)
    return thud + soft


@_sfx("thump", "body hits floor: lower and softer than thunk, 0.2 s")
def _thump(rng):
    n = _n(0.2)
    t = _t(n)
    body = 0.8 * _sine(40.0 + 30.0 * np.exp(-t / 0.03), n) * np.exp(-t / 0.06)
    body = 0.5 * body + 0.7 * np.tanh(3.0 * body)
    soft = 1.5 * _lp(_noise(rng, n), 380.0) * np.exp(-t / 0.05)
    mid = _sine(_glide(190.0, 110.0, n, 0.03), n) * np.exp(-t / 0.05) * 0.9
    return 0.6 * body + soft + mid


# ---------------------------------------------------------------- API

def render_sfx(name, pitch=1.0, seed=0):
    """Render a named sound as float32 mono at SR, peak-normalised to 0.9."""
    if name not in SFX:
        close = difflib.get_close_matches(str(name), list(SFX), n=3, cutoff=0.4)
        hint = f" Did you mean {', '.join(close)}?" if close else ""
        raise KeyError(f"unknown sound {name!r}.{hint}")
    pitch = float(pitch)
    if not pitch > 0:
        raise ValueError(f"pitch must be > 0, got {pitch}")
    rng = np.random.default_rng(seed)
    x = SFX[name](rng, pitch).astype(np.float64)
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    if peak > 0:
        x *= 0.9 / peak
    return x.astype(np.float32)


def write_wav(path, samples):
    """Write float samples in [-1, 1] as 16-bit mono PCM WAV at SR."""
    x = np.clip(np.asarray(samples, dtype=float), -1.0, 1.0)
    pcm = np.round(x * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def describe():
    """Return {name: one-line description}."""
    return dict(_DESC)


# ---------------------------------------------------------------- self-test

def _dominant(x):
    spec = np.abs(np.fft.rfft(x * np.hanning(x.size)))
    freqs = np.fft.rfftfreq(x.size, 1.0 / SR)
    spec[0] = 0.0
    return float(freqs[int(np.argmax(spec))])


def _selftest():
    import os

    outdir = "/tmp/sfx_test"
    os.makedirs(outdir, exist_ok=True)
    problems = []
    print(f"{'name':<9}{'pitch':>6}{'sec':>7}{'peak':>7}{'rms':>7}{'dom_Hz':>9}")
    for name in SFX:
        for pitch in (1.0, 1.3):
            where = f"{name} @ {pitch}"
            x = render_sfx(name, pitch, seed=0).astype(np.float64)
            sec = x.size / SR
            peak = float(np.max(np.abs(x)))
            rms = float(np.sqrt(np.mean(x ** 2)))
            dom = _dominant(x)
            if not np.all(np.isfinite(x)):
                problems.append(f"{where}: NaN/inf")
            if peak > 1.0:
                problems.append(f"{where}: peak {peak:.3f} > 1")
            if not (0.03 <= sec <= 1.6):
                problems.append(f"{where}: duration {sec:.3f} s out of range")
            if abs(x[0]) >= 0.02 or abs(x[-1]) >= 0.02:
                problems.append(f"{where}: edge not at zero ({x[0]:.4f}, {x[-1]:.4f})")
            if not rms > 0.01:
                problems.append(f"{where}: rms {rms:.4f} too quiet / silent")
            print(f"{name:<9}{pitch:>6.1f}{sec:>7.3f}{peak:>7.3f}{rms:>7.3f}{dom:>9.0f}")
            fname = f"{name}.wav" if pitch == 1.0 else f"{name}_p1.3.wav"
            write_wav(os.path.join(outdir, fname), x)
    if problems:
        print("\nFAILED:")
        for p in problems:
            print("  " + p)
        return 1
    print(f"\nall {len(SFX)} sounds passed at pitch 1.0 and 1.3; WAVs in {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
