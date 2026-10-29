/**
 * Offline synthesis of a note list into a looping stereo buffer: voices, filter, pan, a room for Distance, and the drum lane.
 * Plain JavaScript, no Web Audio: the same code runs in the page and in Node tests (kept with the
 * source in the authoring workbench, not in this repository),
 * and the same notes always give the same samples.
 * Notes that run past the loop end wrap to the start, and the reverberation is run
 * over the loop twice so its tail wraps too: the loop is seamless.
 */
import { rng } from './pool.js';

export const CEILING = 0.5; // −6 dBFS peak cap on the rendered loop
/**
 * Per-voice trims (dB) so a change of voice is not also a change of loudness.
 * Set by numbers (between the peak and RMS gaps to the reed at the rest settings), not by ear.
 */
export const TRIM_DB = { sine: -3, soft: -2, reed: 0, hollow: -3, pad: 1, organ: -1, epiano: -1, marimba: -2.5, bell: 0, pluck: 9, breath: 0 };
const BASE_GAIN = 1.0; // typical loops peak near −14 dBFS; the loudest are capped at −6
const TABLE = 2048;
const MAX_H = 20;

/** One-cycle wavetable from [harmonic, amplitude] pairs, normalised to peak 1. */
function table(partials) {
  const t = new Float32Array(TABLE + 1);
  for (let i = 0; i < TABLE; i++) {
    let s = 0;
    for (const [h, a] of partials) s += a * Math.sin((2 * Math.PI * h * i) / TABLE);
    t[i] = s;
  }
  let peak = 0;
  for (let i = 0; i < TABLE; i++) peak = Math.max(peak, Math.abs(t[i]));
  for (let i = 0; i < TABLE; i++) t[i] /= peak;
  t[TABLE] = t[0];
  return t;
}
const upTo = (H, step = 1, first = 1) => { const o = []; for (let h = first; h <= H; h += step) o.push(h); return o; };
const SPECTRA = {
  sine: () => [[1, 1]],
  soft: (H) => upTo(H, 2).map((h, k) => [h, (k % 2 ? -1 : 1) / (h * h)]),
  reed: (H) => upTo(H).map((h) => [h, 1 / h]),
  hollow: (H) => upTo(H, 2).map((h) => [h, 1 / h]),
  organ: (H) => [[1, 1], [2, 0.7], [3, 0.5], [4, 0.35], [6, 0.25], [8, 0.18], [10, 0.1]].filter(([h]) => h <= H),
};
/** Tables cached per voice and harmonic count, so high notes drop overtones instead of aliasing. */
const cache = new Map();
function tableFor(inst, freq, sr) {
  const H = Math.max(1, Math.min(MAX_H, Math.floor((0.42 * sr) / freq)));
  const key = `${inst}:${H}`;
  if (!cache.has(key)) cache.set(key, table(SPECTRA[inst](H)));
  return cache.get(key);
}

/** Envelope shapes: attack, the level reached at the note's end, and release. */
function envelope(artic, dur) {
  const d = Math.max(0.03, dur);
  switch (artic) {
    case 'pluck': {
      const a = Math.min(0.003, d / 2), tau = d / 3;
      return { d, rel: 0.03, at: (t) => (t < a ? t / a : Math.exp(-(t - a) / tau)) };
    }
    case 'swell': {
      const a = Math.max(0.02, 0.7 * d);
      return { d, rel: 0.06, at: (t) => (t < a ? (t / a) ** 2 : 1) };
    }
    case 'tick': {
      const a = 0.001;
      return { d, rel: 0.02, at: (t) => (t < a ? t / a : 0.2 + 0.8 * Math.exp(-(t - a) / 0.006)) };
    }
    case 'sustain': {
      const a = Math.min(0.15, d / 3);
      return { d, rel: 0.3, at: (t) => (t < a ? t / a : 1) };
    }
    default: { // soft
      const a = Math.min(0.025, d / 2);
      return { d, rel: 0.08, at: (t) => (t < a ? t / a : 1) };
    }
  }
}

/** Read a wavetable at a phase increment into `out` (adds `gain` times the table). */
function readTable(out, tab, inc, gain, ph0 = 0) {
  let ph = ph0;
  for (let i = 0; i < out.length; i++) {
    const j = ph | 0, f = ph - j;
    out[i] += gain * (tab[j] + f * (tab[j + 1] - tab[j]));
    ph += inc;
    if (ph >= TABLE) ph -= TABLE;
  }
}

/** Fill `out` with the raw oscillator for one note (before envelope and filter). */
function oscillate(out, inst, freq, sr, r) {
  const n = out.length;
  const tw = 2 * Math.PI;
  if (inst === 'bell' || inst === 'epiano') {
    // Two-operator FM; the index falls as the note rings. Bell: inharmonic ratio; piano: ratio 1, softer.
    const [ratio, i0, tau, floor] = inst === 'bell' ? [3.5, 2.5, 0.4, 0.3] : [1, 1.8, 0.35, 0.25];
    for (let i = 0; i < n; i++) {
      const t = i / sr;
      const idx = i0 * Math.exp(-t / tau) + floor;
      out[i] = Math.sin(tw * freq * t + idx * Math.sin(tw * freq * ratio * t));
    }
    return;
  }
  if (inst === 'marimba') {
    // A struck bar: three modes at bar ratios, the upper ones dying first; modes above the band are dropped.
    const modes = [[1, 1, 0.6], [3.93, 0.35, 0.12], [9.2, 0.12, 0.04]].filter(([m]) => m * freq < 0.42 * sr);
    for (let i = 0; i < n; i++) {
      const t = i / sr;
      let s = 0;
      for (const [m, a, d] of modes) s += a * Math.exp(-t / d) * Math.sin(tw * m * freq * t);
      out[i] = s;
    }
    return;
  }
  if (inst === 'pluck') {
    // Karplus-Strong string: a seeded noise burst, then y[i] = 0.498 (y[i-D] + y[i-D-1]).
    // The average adds half a sample of delay, so D = sr/f - 0.5, read with linear interpolation to stay in tune.
    const D = sr / freq - 0.5;
    const at = (x) => { const j = Math.floor(x), f = x - j; return j < 0 ? 0 : out[j] + f * ((out[j + 1] ?? out[j]) - out[j]); };
    const burst = Math.min(n, Math.ceil(D) + 2);
    for (let i = 0; i < burst; i++) out[i] = 2 * r() - 1;
    for (let i = burst; i < n; i++) out[i] = 0.498 * (at(i - D) + at(i - D - 1));
    return;
  }
  if (inst === 'pad') {
    // Two sawtooths 6 cents either side of the note, so the tone beats slowly.
    const tab = tableFor('reed', freq * 1.004, sr);
    const c = Math.pow(2, 6 / 1200);
    readTable(out, tab, (freq * c * TABLE) / sr, 0.5);
    readTable(out, tab, (freq / c * TABLE) / sr, 0.5, TABLE / 3);
    return;
  }
  const base = inst === 'breath' ? 'reed' : SPECTRA[inst] ? inst : 'reed';
  readTable(out, tableFor(base, freq, sr), (freq * TABLE) / sr, 1);
  if (inst === 'breath') {
    let lp = 0;
    for (let i = 0; i < n; i++) {
      lp += 0.2 * (2 * r() - 1 - lp); // softened noise
      out[i] = 0.75 * out[i] + 0.9 * lp;
    }
  }
}

export const VIB_RATE = 5.5;
/**
 * Vibrato for every voice alike: read the note through a delay that swings sinusoidally.
 * A delay swing of A seconds at rate r bends the pitch by a factor 1 ± 2πrA, so A = (2^(c/1200) − 1) / (2πr).
 */
function vibrato(buf, cents, sr) {
  const A = (Math.pow(2, cents / 1200) - 1) / (2 * Math.PI * VIB_RATE) * sr;
  const src = buf.slice();
  for (let i = 0; i < buf.length; i++) {
    const x = i - A * (1 + Math.sin((2 * Math.PI * VIB_RATE * i) / sr));
    const j = Math.floor(x), f = x - j;
    buf[i] = j < 0 ? 0 : src[j] + f * ((src[j + 1] ?? src[j]) - src[j]);
  }
}

/**
 * Freeverb-style room (8 damped combs, 4 allpasses per side) over a looping send.
 * The send is played through twice and the second pass kept, so the tail wraps.
 */
const COMBS = [1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617];
const ALLPASS = [556, 441, 341, 225];
export const WET_GAIN = 2.2; // set by numbers: a 90 % wet note comes out about 3 dB under the dry note (RMS)
function reverb(send, sr, spread) {
  const N = send.length;
  const k = sr / 44100;
  const combs = COMBS.map((d) => ({ buf: new Float32Array(Math.round((d + spread) * k)), i: 0, store: 0 }));
  const aps = ALLPASS.map((d) => ({ buf: new Float32Array(Math.round((d + spread) * k)), i: 0 }));
  const fb = 0.8, damp = 0.3;
  const out = new Float32Array(N);
  for (let pass = 0; pass < 2; pass++) {
    for (let n = 0; n < N; n++) {
      const x = send[n] * 0.015;
      let y = 0;
      for (const c of combs) {
        const o = c.buf[c.i];
        c.store = o * (1 - damp) + c.store * damp;
        c.buf[c.i] = x + c.store * fb;
        if (++c.i >= c.buf.length) c.i = 0;
        y += o;
      }
      for (const a of aps) {
        const b = a.buf[a.i];
        a.buf[a.i] = y + b * 0.5;
        if (++a.i >= a.buf.length) a.i = 0;
        y = b - y;
      }
      if (pass === 1) out[n] = y;
    }
  }
  return out;
}

/* ---------- drum lane ---------- */
/**
 * Per-drum trims (dB), set by numbers like TRIM_DB: at the rest settings and a drum level of 0 dB each drum
 * sits 2 to 3 dB under a reed note (midway between the RMS and peak gaps over 0.5 s). The lane starts at −6 dB.
 */
export const DRUM_TRIM_DB = { kick: -4, snare: -3, hat: 9, block: -4, shaker: -1 };
/**
 * One drum hit into a fresh buffer: kick = a sine whose pitch falls from 3.5x to 1x in about 30 ms;
 * snare = a 190 Hz tone plus high-passed noise; hat = noise above about 7 kHz; block = two
 * sines (820 Hz and 2.7 times that); shaker = noise above about 3 kHz with a 15 ms rise.
 * `tune` scales the pitches and filter corners; `decay` is the noise or body time constant.
 */
export function drumHit(kind, tune, decay, sr, r) {
  const len = Math.ceil(Math.min(1.5, decay * 7 + 0.02) * sr);
  const out = new Float32Array(len);
  const hp = (fc) => { const a = Math.exp((-2 * Math.PI * fc) / sr); let lp = 0; return (x) => { lp = a * lp + (1 - a) * x; return x - lp; }; };
  const noise = () => 2 * r() - 1;
  let ph = 0;
  const hpA = hp(Math.min(sr / 3, (kind === 'hat' ? 7000 : kind === 'shaker' ? 3000 : 1800) * tune)), hpB = hp(Math.min(sr / 3, 7000 * tune));
  for (let i = 0; i < len; i++) {
    const t = i / sr;
    const atk = Math.min(1, t / (kind === 'shaker' ? 0.015 : 0.001));
    let y;
    if (kind === 'kick') {
      ph += (2 * Math.PI * 52 * tune * (1 + 2.5 * Math.exp(-t / 0.03))) / sr;
      y = Math.sin(ph) * Math.exp(-t / decay);
    } else if (kind === 'snare') {
      y = 0.55 * Math.sin(2 * Math.PI * 190 * tune * t) * Math.exp(-t / Math.min(decay, 0.08)) + 0.8 * hpA(noise()) * Math.exp(-t / decay);
    } else if (kind === 'hat') {
      y = hpB(hpA(noise())) * Math.exp(-t / (0.5 * decay));
    } else if (kind === 'block') {
      const e = Math.exp(-t / (0.4 * decay));
      y = (Math.sin(2 * Math.PI * 820 * tune * t) + 0.45 * Math.sin(2 * Math.PI * 820 * 2.7 * tune * t)) * e;
    } else {
      y = hpA(noise()) * Math.exp(-t / decay);
    }
    out[i] = atk * y;
  }
  return out;
}

/**
 * Render notes into one loop.
 * @param {import('./map.js').Note[]} notes
 * @param {{sr:number, loopSec:number, seed?:number, ceiling?:number, hits?:ReturnType<typeof import('./drum.js').drumHits>}} o
 *   hits: the drum lane, mixed dry and centred under the notes.
 * @returns {{sr:number, loopSec:number, L:Float32Array, R:Float32Array, peak:number, scaled:number}}
 *   peak is before the cap; scaled is the gain applied to meet the cap (1 if none).
 */
export function render(notes, o) {
  const { sr, loopSec } = o;
  const ceiling = o.ceiling ?? CEILING;
  const N = Math.round(sr * loopSec);
  const L = new Float32Array(N), R = new Float32Array(N);
  const sL = new Float32Array(N), sR = new Float32Array(N);
  let anyWet = false;
  notes.forEach((nt, j) => {
    const env = envelope(nt.artic, nt.dur);
    const len = Math.min(N, Math.ceil((env.d + env.rel) * sr));
    const buf = new Float32Array(len);
    oscillate(buf, nt.inst, nt.freq, sr, rng((o.seed ?? 1) * 7919 + j));
    if (nt.vib > 0.5) vibrato(buf, nt.vib, sr);
    const f1 = 2 * Math.sin((Math.PI * Math.min(nt.cutoff, sr / 6)) / sr);
    const q = 1.414;
    let low = 0, band = 0;
    const g = BASE_GAIN * Math.pow(10, (nt.gainDb + (TRIM_DB[nt.inst] ?? 0)) / 20);
    const wet = nt.wet ?? 0;
    const dry = 1 - 0.75 * wet; // farther: less direct sound
    if (wet > 0.001) anyWet = true;
    const pl = Math.cos(((nt.pan + 1) * Math.PI) / 4), pr = Math.sin(((nt.pan + 1) * Math.PI) / 4);
    const end = env.at(env.d);
    const start = Math.round(nt.t * sr);
    for (let i = 0; i < len; i++) {
      const t = i / sr;
      const e = t < env.d ? env.at(t) : end * Math.max(0, 1 - (t - env.d) / env.rel);
      const am = nt.am > 0 ? 1 - 0.6 * (0.5 - 0.5 * Math.cos(2 * Math.PI * nt.am * t)) : 1;
      low += f1 * band;
      const high = buf[i] - low - q * band;
      band += f1 * high;
      const y = g * low * e * am;
      const k = (start + i) % N;
      L[k] += dry * pl * y;
      R[k] += dry * pr * y;
      if (wet > 0.001) { sL[k] += wet * pl * y; sR[k] += wet * pr * y; }
    }
  });
  (o.hits ?? []).forEach((h, j) => {
    const buf = drumHit(h.kind, h.tune, h.decay, sr, rng((o.seed ?? 1) * 104729 + j));
    const g = BASE_GAIN * Math.SQRT1_2 * Math.pow(10, (h.gainDb + (DRUM_TRIM_DB[h.kind] ?? 0)) / 20);
    const start = Math.round(h.t * sr);
    for (let i = 0; i < Math.min(buf.length, N); i++) { const k = (start + i) % N; L[k] += g * buf[i]; R[k] += g * buf[i]; }
  });
  if (anyWet) {
    const rl = reverb(sL, sr, 0), rr = reverb(sR, sr, 23);
    for (let i = 0; i < N; i++) { L[i] += WET_GAIN * rl[i]; R[i] += WET_GAIN * rr[i]; }
  }
  let peak = 0;
  for (let i = 0; i < N; i++) peak = Math.max(peak, Math.abs(L[i]), Math.abs(R[i]));
  const scaled = peak > ceiling ? ceiling / peak : 1;
  if (scaled < 1) for (let i = 0; i < N; i++) { L[i] *= scaled; R[i] *= scaled; }
  return { sr, loopSec, L, R, peak, scaled };
}
