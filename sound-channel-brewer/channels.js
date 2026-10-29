/**
 * The eight auditory channels of the sound Channel Brewer, as data.
 * Pure: no DOM, no audio. Values are physical units (Hz, dB, s), never 0..1.
 * Channel functions take an options object `o` = {octave, span} that only pitch reads.
 */

/** @typedef {'grid'|'cloud'|'lines'} Layout */

export const LAYOUTS = /** @type {const} */ (['grid', 'cloud', 'lines']);

export const LAYOUT_INFO = {
  grid: 'One event per slot on a steady pulse.',
  cloud: 'The same events at random onsets inside the loop.',
  lines: 'Up to eight sustained tones overlapping across the loop.',
};

/** D major pentatonic: semitones above D. */
const PENTA = [0, 2, 4, 7, 9];
export const OCTAVES = [2, 3, 4, 5];
export const SPANS = [1, 2];
export const PITCH_DEFAULTS = { octave: 4, span: 2 };
/** The scale from D at `octave` up to the D `span` octaves higher, as MIDI notes. */
export function pentatonic(o = {}) {
  const { octave, span } = { ...PITCH_DEFAULTS, ...o };
  const d = 12 * (octave + 1) + 2;
  const out = [];
  for (let oc = 0; oc < span; oc++) PENTA.forEach((s) => out.push(d + 12 * oc + s));
  out.push(d + 12 * span);
  return out;
}
const NOTE_NAMES = ['C', 'C♯', 'D', 'D♯', 'E', 'F', 'F♯', 'G', 'G♯', 'A', 'A♯', 'B'];

export const midiToHz = (m) => 440 * Math.pow(2, (m - 69) / 12);
const midiName = (m) => NOTE_NAMES[m % 12] + (Math.floor(m / 12) - 1);

/**
 * The voice every note uses: a pick list, not a data channel, so timbre never competes with the pair.
 * Synthetic stand-ins, not the deck's samples.
 */
export const VOICES = [
  { id: 'sine', label: 'Sine', desc: 'a pure tone with no overtones; brightness has little to open' },
  { id: 'soft', label: 'Soft triangle', desc: 'odd overtones that fall away fast' },
  { id: 'reed', label: 'Reed', desc: 'a sawtooth: every overtone, bright and buzzy' },
  { id: 'hollow', label: 'Square lead', desc: 'odd overtones only, hollow like a clarinet' },
  { id: 'pad', label: 'Saw pad', desc: 'two sawtooths detuned against each other, so the tone shimmers' },
  { id: 'organ', label: 'Organ', desc: 'a few steady overtones, like drawbars' },
  { id: 'epiano', label: 'FM electric piano', desc: 'frequency modulation that softens as the note rings' },
  { id: 'marimba', label: 'Marimba', desc: 'a struck bar: high modes die first' },
  { id: 'bell', label: 'Bell', desc: 'inharmonic frequency modulation, metallic' },
  { id: 'pluck', label: 'Pluck', desc: 'a plucked string (Karplus-Strong)' },
  { id: 'breath', label: 'Breath', desc: 'a reed tone mixed with soft noise' },
];
export const DEFAULT_VOICE = 'reed';

export const ARTICULATIONS = [
  { id: 'soft', label: 'Soft' },
  { id: 'pluck', label: 'Pluck' },
  { id: 'swell', label: 'Swell' },
  { id: 'tick', label: 'Tick' },
];

/** Spread k of n over a fixed range: at any n the ends stay put and levels pack closer. */
const frac = (k, n) => (n <= 1 ? 0.5 : k / (n - 1));

/**
 * @typedef {object} Channel
 * @property {string} id
 * @property {string} label
 * @property {'ordered'|'identity'} kind
 * @property {number} maxLevels
 * @property {string} desc    one-line description for the hover tooltip
 * @property {string} range   the value range in words
 * @property {(k:number, n:number) => number|string} value  level k of n, in physical units or an id
 * @property {(v:any) => string} format  value as a short label
 * @property {number|string} rest  the value used when this channel carries no variable
 */

/** Every channel the page knows. The matrix shows eight of them; the rest wait on the bench. @type {Channel[]} */
export const ALL_CHANNELS = [
  {
    id: 'pitch', label: 'Pitch', kind: 'ordered', maxLevels: 7,
    desc: 'How high the note is. Every level is a note of one D major pentatonic scale; the octave and span are set in “Pitch from”.',
    range: 'from D at the chosen octave, one or two octaves up',
    value: (k, n, o) => { const sc = pentatonic(o); return midiToHz(sc[Math.round(frac(k, n) * (sc.length - 1))]); },
    format: (hz) => midiName(Math.round(69 + 12 * Math.log2(hz / 440))),
    rest: (o) => midiToHz(pentatonic(o)[3]), // the A above the bottom D
  },
  {
    id: 'loudness', label: 'Loudness', kind: 'ordered', maxLevels: 7,
    desc: 'How loud the note is, in equal decibel steps.',
    range: '−24 dB to 0 dB',
    value: (k, n) => -24 + 24 * frac(k, n),
    format: (db) => `${db.toFixed(0).replace('-', '−')} dB`,
    rest: -8,
  },
  {
    id: 'brightness', label: 'Brightness', kind: 'ordered', maxLevels: 7,
    desc: 'How dull or bright the tone is: a low-pass filter opens in equal octave steps.',
    range: '300 Hz to 4.8 kHz cutoff (4 octaves)',
    value: (k, n) => 300 * Math.pow(2, 4 * frac(k, n)),
    format: (hz) => (hz >= 1000 ? `${(hz / 1000).toFixed(1)} kHz` : `${Math.round(hz)} Hz`),
    rest: 1500,
  },
  {
    id: 'duration', label: 'Duration', kind: 'ordered', maxLevels: 7,
    desc: 'How long each note lasts, in steps of a fixed ratio.',
    range: '60 ms to 1 s',
    value: (k, n) => 0.06 * Math.pow(1 / 0.06, frac(k, n)),
    format: (s) => (s < 1 ? `${Math.round(s * 1000)} ms` : `${s.toFixed(1)} s`),
    rest: 0.22,
  },
  {
    id: 'roughness', label: 'Roughness', kind: 'ordered', maxLevels: 7,
    desc: 'A flutter in loudness: from smooth, through a slow beat, to a buzz.',
    range: '0 (smooth) to 30 Hz flutter',
    value: (k, n) => 30 * frac(k, n),
    format: (hz) => (hz === 0 ? 'smooth' : `${hz.toFixed(hz < 10 ? 1 : 0)} Hz`),
    rest: 0,
  },
  {
    id: 'pan', label: 'Pan', kind: 'ordered', maxLevels: 7,
    desc: 'Where the note sits between your ears. Needs headphones or two speakers.',
    range: 'left to right',
    value: (k, n) => -0.9 + 1.8 * frac(k, n),
    format: (p) => (Math.abs(p) < 0.05 ? 'centre' : `${Math.round(Math.abs(p) * 100)} % ${p < 0 ? 'L' : 'R'}`),
    rest: 0,
  },
  {
    id: 'distance', label: 'Distance', kind: 'ordered', maxLevels: 7,
    desc: 'How near or far the note sounds: the direct sound falls and the reverberation rises.',
    range: 'dry (near) to 90 % reverberation (far)',
    value: (k, n) => 0.9 * frac(k, n),
    format: (w) => (w < 0.005 ? 'dry' : `${Math.round(w * 100)} % wet`),
    rest: 0.1,
  },
  {
    id: 'vibrato', label: 'Vibrato', kind: 'ordered', maxLevels: 7,
    desc: 'A slow wobble in pitch at 5.5 per second, from none to wide.',
    range: 'none to ±60 cents at 5.5 Hz',
    value: (k, n) => 60 * frac(k, n),
    format: (c) => (c < 0.5 ? 'none' : `±${Math.round(c)} ¢`),
    rest: 0,
  },
  {
    id: 'articulation', label: 'Articulation', kind: 'identity', maxLevels: ARTICULATIONS.length,
    desc: 'How a note starts and ends: soft, plucked, swelling, or a tick with a quiet tail.',
    range: `${ARTICULATIONS.length} shapes`,
    value: (k) => ARTICULATIONS[k].id,
    format: (id) => ARTICULATIONS.find((a) => a.id === id)?.label ?? id,
    rest: 'soft',
  },
];

export const MIN_LEVELS = 2;
export const byId = Object.fromEntries(ALL_CHANNELS.map((c) => [c.id, c]));
export const MATRIX_SIZE = 8;
/** The eight channels in the matrix at load; the others start on the bench. */
export const DEFAULT_SLOTS = ['pitch', 'loudness', 'brightness', 'duration', 'roughness', 'pan', 'distance', 'articulation'];
export const benchOf = (slots) => ALL_CHANNELS.filter((c) => !slots.includes(c.id)).map((c) => c.id);
/** The resting value of a channel (used when it carries no variable). */
export const restOf = (id, o = {}) => { const r = byId[id].rest; return typeof r === 'function' ? r(o) : r; };
/** Most levels a channel can show; pitch over one octave has six notes. */
export const maxLevelsOf = (id, o = {}) => (id === 'pitch' ? Math.min(byId.pitch.maxLevels, pentatonic(o).length) : byId[id].maxLevels);

/** Channels a layout cannot vary, with the reason shown in the matrix. */
export const UNAVAILABLE = {
  grid: {},
  cloud: {},
  lines: {
    duration: 'not available on lines: a sustained tone has no note length',
    articulation: 'not available on lines: a sustained tone has no attack shape',
  },
};

/** Pairs that are not two free channels: one sound property that two channels both move. Keys are sorted ids joined by '|'. */
export const LINKED = {
  'distance|loudness': 'Linked: quietness and reverberation are both cues for distance, so the two can blur into one.',
  'pitch|vibrato': 'Linked: vibrato is a wobble in pitch, so wide vibrato blurs the pitch steps.',
};

/** Pairs our pieces use or propose, from the deck pick list (261023-deck-covariate-and-instrument-pick-list). */
export const FROM_OUR_PIECES = [
  { a: 'duration', b: 'loudness', note: 'Meridian Chorus: day length sets the length and loudness of each voice’s note (built).' },
  { a: 'pitch', b: 'brightness', note: 'Meridian pick list: sea temperature as pitch, noon sun height as filter brightness (proposed).' },
  { a: 'pan', b: 'loudness', note: 'Pick list: wind direction as pan; Godbout: harp loudness from the dew-point gap (proposed pair).' },
];

export const pairKey = (a, b) => [a, b].sort().join('|');

/** All levels of a channel at n steps. */
export function levels(id, n, o = {}) {
  const c = byId[id];
  if (!c) throw new Error(`unknown channel ${id}`);
  const m = clampLevels(id, n, o);
  return Array.from({ length: m }, (_, k) => c.value(k, m, o));
}

export function clampLevels(id, n, o = {}) {
  return Math.max(MIN_LEVELS, Math.min(maxLevelsOf(id, o), Math.round(n)));
}

/**
 * Status of an unordered pair on a layout, for the matrix and its tooltip.
 * @returns {{status:'free'|'linked'|'unavailable', text:string}}
 */
export function pairInfo(a, b, layout) {
  const un = UNAVAILABLE[layout];
  const gone = [a, b].filter((x) => un[x]);
  if (gone.length) {
    return { status: 'unavailable', text: gone.map((x) => `${byId[x].label} is ${un[x]}.`).join(' ') };
  }
  const link = LINKED[pairKey(a, b)];
  if (link) return { status: 'linked', text: link };
  return { status: 'free', text: `${byId[a].label} carries one variable and ${byId[b].label} the other. Click or press Enter to hear them together.` };
}
