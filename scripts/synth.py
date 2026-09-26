"""
Synthesis layer for the electronic-ambient pieces (2026-09-25): band-limited
oscillators, a slowly swept low-pass filter, electronic drums, filtered
noise, tempo-synced ping-pong delay and sidechain ducking. Everything is
vectorized numpy (no per-sample Python loops) so a 7-8 minute render stays
well under a minute. Outputs are (n, 2) float arrays at sampler.SR, the same
shape the sampled Instruments return, so synth and samples share buses.

Pieces:
  osc(kind, f, n)            - 'sine' | 'saw' | 'square' | 'tri', polyBLEP saws/squares,
                               f may be a per-sample array (glides, vibrato)
  supersaw(f, n, voices)     - detuned saw stack, stereo-spread
  swept_lowpass(x, cutoff)   - 2nd-order low-pass whose cutoff follows an array
  env_adsr(n, a, d, s, r)    - linear-attack, exponential-decay envelope
  pad_note / sub_note / pluck_note / drone
  kick / hat / clap / rim    - electronic kit voices
  noise_band(n, lo, hi)      - band-passed noise (wind, rain, storm rumble)
  pingpong(x, delay_s, fb)   - stereo feedback delay, each repeat darker
  sidechain(n, hits, depth)  - gain curve that ducks after each kick
"""
import numpy as np
from scipy.signal import butter, sosfilt, sosfilt_zi

from sampler import SR


def midi_hz(m):
    return 440.0 * 2 ** ((np.asarray(m, dtype=float) - 69) / 12)


def _as_arr(f, n):
    f = np.asarray(f, dtype=float)
    return np.full(n, float(f)) if f.ndim == 0 else f[:n]


def _polyblep(t, dt):
    """polyBLEP residual for a phase t in [0,1) with increment dt (vectorized)."""
    y = np.zeros_like(t)
    a = t < dt
    x = t[a] / dt[a]
    y[a] = x + x - x * x - 1
    b = t > 1 - dt
    x = (t[b] - 1) / dt[b]
    y[b] = x * x + x + x + 1
    return y


def osc(kind, f, n, phase0=0.0):
    f = _as_arr(f, n)
    dt = f / SR
    ph = (phase0 + np.cumsum(dt)) % 1.0
    if kind == "sine":
        return np.sin(2 * np.pi * ph)
    if kind == "saw":
        return 2 * ph - 1 - _polyblep(ph, dt)
    if kind == "square":
        sq = np.where(ph < 0.5, 1.0, -1.0)
        return sq + _polyblep(ph, dt) - _polyblep((ph + 0.5) % 1.0, dt)
    if kind == "tri":
        return 2 * np.abs(2 * ph - 1) - 1
    raise ValueError(kind)


def supersaw(f, n, voices=5, detune_cents=14, spread=0.8, rng=None):
    rng = rng or np.random.default_rng(0)
    out = np.zeros((n, 2))
    f = _as_arr(f, n)
    for i in range(voices):
        c = (i - (voices - 1) / 2) / max(1, (voices - 1) / 2) * detune_cents
        x = osc("saw", f * 2 ** (c / 1200), n, rng.uniform())
        pan = (i - (voices - 1) / 2) / max(1, (voices - 1) / 2) * spread
        a = (pan + 1) * np.pi / 4
        out[:, 0] += x * np.cos(a)
        out[:, 1] += x * np.sin(a)
    return out / np.sqrt(voices)


def swept_lowpass(x, cutoff, q_order=2, block=1024):
    """Low-pass with a time-varying cutoff (Hz, scalar or per-sample array).
    Coefficients are recomputed per block and the filter state carried over,
    which is click-free for the slow sweeps used here."""
    x = np.atleast_2d(x.T).T if x.ndim == 1 else x
    n = len(x)
    cut = _as_arr(cutoff, n)
    y = np.empty_like(x)
    zi = None
    for s in range(0, n, block):
        c = float(np.clip(cut[min(s + block // 2, n - 1)], 20, SR * 0.45))
        sos = butter(q_order, c, "lowpass", fs=SR, output="sos")
        if zi is None:
            zi = np.stack([sosfilt_zi(sos) * x[0, ch] for ch in range(x.shape[1])], axis=-1)
        seg = x[s:s + block]
        out, zi = sosfilt(sos, seg, axis=0, zi=zi)
        y[s:s + block] = out
    return y


def bandpass(x, lo, hi, order=2):
    sos = butter(order, [lo, hi], "bandpass", fs=SR, output="sos")
    return sosfilt(sos, x, axis=0)


def highpass(x, hz, order=2):
    return sosfilt(butter(order, hz, "highpass", fs=SR, output="sos"), x, axis=0)


def env_adsr(n, a=0.01, d=0.2, s=0.7, r=0.4, hold=None):
    """Attack (linear) -> decay (exp) to sustain -> release (exp) over n samples.
    `hold` = seconds before release starts (default: n minus release)."""
    t = np.arange(n) / SR
    hold = (n / SR - r) if hold is None else hold
    e = np.where(t < a, t / max(a, 1e-4), s + (1 - s) * np.exp(-(t - a) / max(d, 1e-4)))
    rel = t >= hold
    if rel.any():
        e0 = e[np.argmax(rel)]
        e[rel] = e0 * np.exp(-(t[rel] - hold) / max(r / 4, 1e-4))
    return e


def stereo(x, width=0.0, delay_ms=9):
    """mono -> (n,2); width>0 adds a short Haas offset on the right."""
    if width <= 0:
        return np.stack([x, x], axis=1)
    d = int(delay_ms * SR / 1000)
    r = np.concatenate([np.zeros(d), x[:-d]]) if d else x
    return np.stack([x, (1 - width) * x + width * r], axis=1)


# -------------------------------------------------------------- voices -----
def pad_note(midi, dur, vel=0.6, cutoff=1200, a=1.5, r=2.5, rng=None, voices=5, detune=12):
    """Warm analogue-style pad: supersaw through a low-pass, slow attack."""
    n = int((dur + r) * SR)
    x = supersaw(midi_hz(midi), n, voices=voices, detune_cents=detune, rng=rng)
    x = swept_lowpass(x, cutoff)
    return x * env_adsr(n, a=a, d=1.0, s=0.85, r=r, hold=dur)[:, None] * vel * 0.35


def sub_note(midi, dur, vel=0.7, r=0.25, drive=1.4):
    """Sine sub with a touch of saturation (adds the 2nd/3rd harmonics that
    make a sub audible on small speakers)."""
    n = int((dur + r) * SR)
    x = np.tanh(drive * osc("sine", midi_hz(midi), n)) / np.tanh(drive)
    return stereo(x * env_adsr(n, a=0.02, d=0.3, s=0.9, r=r, hold=dur) * vel * 0.6)


def pluck_note(midi, vel=0.6, decay=0.35, cutoff=2600, rng=None):
    """Short filtered saw pluck for arpeggios."""
    n = int((decay * 4 + 0.05) * SR)
    x = 0.6 * osc("saw", midi_hz(midi), n) + 0.4 * osc("square", midi_hz(midi) * 1.002, n)
    e = np.exp(-np.arange(n) / SR / decay)
    cut = 300 + cutoff * e ** 0.7  # filter closes with the note
    x = swept_lowpass((x * e)[:, None], cut, block=256)[:, 0]
    return stereo(x * vel * 0.4, width=0.3)


def drone(midis, n, cutoff, level, rng=None, breathe=None, voices=3, detune=7):
    """Long sustained drone over n samples. cutoff/level: per-sample arrays.
    breathe: optional per-sample 0..1 amplitude modulation (e.g. an annual cycle)."""
    rng = rng or np.random.default_rng(1)
    x = np.zeros((n, 2))
    for m in midis:
        x += supersaw(midi_hz(m), n, voices=voices, detune_cents=detune, spread=0.6, rng=rng)
        x += 0.5 * stereo(osc("sine", midi_hz(m - 12), n))  # sub-octave body
    x = swept_lowpass(x, cutoff, block=2048)
    amp = _as_arr(level, n)
    if breathe is not None:
        amp = amp * (0.75 + 0.25 * _as_arr(breathe, n))
    return x * amp[:, None] * 0.25 / max(1, len(midis))


# ---------------------------------------------------------------- drums ----
def kick(vel=0.8, f0=52, f_start=140, decay=0.45, click=0.25):
    n = int((decay * 3) * SR)
    t = np.arange(n) / SR
    f = f0 + (f_start - f0) * np.exp(-t / 0.035)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / decay)
    x += click * np.random.default_rng(3).standard_normal(n) * np.exp(-t / 0.003)
    return stereo(np.tanh(1.5 * x) * vel * 0.8)


def hat(vel=0.3, open_=False, rng=None):
    rng = rng or np.random.default_rng(5)
    d = 0.22 if open_ else 0.045
    n = int(d * 4 * SR)
    x = highpass(rng.standard_normal(n), 7000, order=4) * np.exp(-np.arange(n) / SR / d)
    return stereo(x * vel * 0.5, width=0.4)


def clap(vel=0.4, rng=None):
    rng = rng or np.random.default_rng(6)
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    env = sum(np.exp(-np.maximum(t - o, 0) / 0.006) * (t >= o) for o in (0, 0.011, 0.022))
    env = env + 0.6 * np.exp(-np.maximum(t - 0.03, 0) / 0.09) * (t >= 0.03)
    x = bandpass(rng.standard_normal(n), 900, 3200) * env
    return stereo(x * vel * 0.6, width=0.5)


def rim(vel=0.35):
    n = int(0.12 * SR)
    t = np.arange(n) / SR
    x = (np.sin(2 * np.pi * 1650 * t) + 0.5 * np.sin(2 * np.pi * 540 * t)) * np.exp(-t / 0.012)
    return stereo(x * vel * 0.5)


def noise_band(n, lo, hi, rng=None, order=2):
    """Stereo band-passed noise (independent channels -> wide)."""
    rng = rng or np.random.default_rng(8)
    x = rng.standard_normal((n, 2))
    return bandpass(x, lo, hi, order)


# --------------------------------------------------------------- effects ---
def pingpong(x, delay_s, fb=0.45, repeats=6, damp_hz=3500, mix=0.35):
    """Stereo ping-pong echo: repeats alternate sides and get darker. Returns
    only the wet signal (add it to the dry)."""
    n = len(x)
    d = int(delay_s * SR)
    wet = np.zeros_like(x)
    tap = x.mean(axis=1)
    sos = butter(1, damp_hz, "lowpass", fs=SR, output="sos")
    for k in range(1, repeats + 1):
        tap = sosfilt(sos, tap)
        off = k * d
        if off >= n:
            break
        side = (k + 1) % 2
        wet[off:, side] += tap[: n - off] * (fb ** k)
    return wet * mix


def sidechain(n, hit_samples, depth=0.45, release=0.18):
    """Gain curve: dips by `depth` at each kick and recovers exponentially."""
    g = np.zeros(n)
    k = np.exp(-np.arange(int(release * 5 * SR)) / SR / release)
    for h in hit_samples:
        h = int(h)
        if 0 <= h < n:
            m = min(len(k), n - h)
            g[h:h + m] = np.maximum(g[h:h + m], k[:m])
    return 1 - depth * g


# ------------------------------------------------ warm voices (2026-09-25) --
def saturate(x, drive=1.3):
    """Soft tape-style saturation: tanh with unity gain at low level."""
    return np.tanh(drive * x) / np.tanh(drive)


def ep_note(midi, dur, vel=0.5, bright=0.5, r=0.6):
    """Electric-piano (Rhodes-ish) voice: 2-operator FM, modulator at 1x with
    a decaying index (the bell-like 'tine' attack), plus a quiet 14x tine."""
    n = int((dur + r) * SR)
    t = np.arange(n) / SR
    f = float(midi_hz(midi))
    idx = (0.6 + 2.2 * bright * vel) * np.exp(-t / 0.35)
    mod = np.sin(2 * np.pi * f * t)
    x = np.sin(2 * np.pi * f * t + idx * mod)
    x += 0.08 * vel * np.sin(2 * np.pi * f * 14 * t) * np.exp(-t / 0.05)
    amp = env_adsr(n, a=0.004, d=0.9, s=0.35, r=r, hold=dur)
    trem = 1 + 0.12 * np.sin(2 * np.pi * 4.5 * t)                 # stereo tremolo
    y = x * amp * vel * 0.45
    return np.stack([y * trem, y * (2 - trem)], axis=1)


VOWELS = {"oh": (450, 800, 2830), "ah": (730, 1090, 2440), "oo": (325, 700, 2530),
          "eh": (530, 1840, 2480), "ee": (300, 2200, 3000)}


def vox_chop(midi, dur, vowel="oh", vel=0.5, bend=0.0, rng=None):
    """Synthesized vocal chop: a glottal-ish pulse (saw with vibrato) through
    three formant band-passes. `bend` semitones glide into the note, like a
    chopped and repitched vocal. Not a sample of any real voice."""
    rng = rng or np.random.default_rng(12)
    n = int((dur + 0.08) * SR)
    t = np.arange(n) / SR
    f = float(midi_hz(midi)) * 2 ** ((bend * np.exp(-t / 0.05)) / 12) * (1 + 0.006 * np.sin(2 * np.pi * 5.5 * t))
    src = osc("saw", f, n) + 0.05 * rng.standard_normal(n)
    y = np.zeros(n)
    for fc, g in zip(VOWELS[vowel], (1.0, 0.7, 0.35)):
        bw = 0.12 * fc + 60
        y += g * bandpass(src, max(40, fc - bw), fc + bw, order=2)
    e = env_adsr(n, a=0.008, d=0.12, s=0.8, r=0.06, hold=dur)
    return stereo(y * e * vel * 0.9, width=0.25)


def lead_note(midi, dur, vel=0.5, cutoff=3000, voices=4, detune=10, rng=None):
    """Bright-but-warm detuned lead for arpeggios: supersaw, fixed low-pass,
    quick attack, medium decay."""
    n = int((dur + 0.5) * SR)
    x = supersaw(midi_hz(midi), n, voices=voices, detune_cents=detune, spread=0.7, rng=rng)
    x = sosfilt(butter(2, cutoff, "lowpass", fs=SR, output="sos"), x, axis=0)
    e = env_adsr(n, a=0.005, d=0.25, s=0.45, r=0.45, hold=dur)
    return x * e[:, None] * vel * 0.4


def split_normal_cdf(x, mode, sd_lo, sd_hi):
    """CDF of a two-piece normal (different spread either side of the mode),
    used to approximate an asymmetric posterior from its median and 95% interval."""
    from scipy.stats import norm
    x = np.asarray(x, dtype=float)
    w_lo = sd_lo / (sd_lo + sd_hi)
    return np.where(x < mode, 2 * w_lo * norm.cdf(x, mode, sd_lo),
                    w_lo + (1 - w_lo) * (2 * norm.cdf(x, mode, sd_hi) - 1))
