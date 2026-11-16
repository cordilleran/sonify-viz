/**
 * Events plus a chosen pair of channels become notes with physical values.
 * Pure. The crowding guard and the solo live here, so the tests can see them.
 */
import { byId, levels, restOf, DEFAULT_VOICE, LEGACY_VOICE, ALL_CHANNELS, LAYOUTS, UNAVAILABLE, VOICES, OCTAVES, SPANS, PITCH_DEFAULTS, ROOTS, SCALE_IDS,
  MIN_LEVELS, MATRIX_SIZE, DEFAULT_SLOTS, maxLevelsOf } from './channels.js';
import { MODEL_IDS, STREAM_IDS, STREAM_USES, MAX_SEED } from './pool.js';
import { DRONE_MODE_IDS, DRONE_DEFAULTS, DRONE_LEVEL_RANGE, BREATHS } from './drone.js';
import { TRANSFORMS, TIME_MODES } from './series.js';

/** Transition (crossfade) length in seconds, 11-15. */
export const TRANSITION_RANGE = [0.05, 12];
export const TRANSITION_DEFAULT = 0.35;
import { DRUM_IDS, DRUM_CHANNEL_IDS, DRUM_DEFAULTS, DRUM_LEVEL_RANGE } from './drum.js';

const drumLevel = (v) => {
  if (v == null) return DRUM_DEFAULTS.level;
  const [lo, hi] = DRUM_LEVEL_RANGE;
  if (!Number.isInteger(v) || v < lo || v > hi) throw new Error(`Drum level "${v}" must be a whole number of dB from ${lo} to ${hi}.`);
  return v;
};

/** The drone block of a pair JSON, checked. */
function readDrone(d) {
  const out = { ...DRONE_DEFAULTS, ...d };
  if (!DRONE_MODE_IDS.includes(out.mode)) throw new Error(`Drone "${out.mode}" is not one of: ${DRONE_MODE_IDS.join(', ')}.`);
  const [lo, hi] = DRONE_LEVEL_RANGE;
  if (!Number.isInteger(out.level) || out.level < lo || out.level > hi) throw new Error(`Drone level must be a whole number of dB from ${lo} to ${hi}.`);
  if (!BREATHS.includes(out.breaths)) throw new Error(`Drone breaths must be one of ${BREATHS.join(', ')}.`);
  for (const k of ['depth', 'bright']) if (typeof out[k] !== 'number' || out[k] < 0 || out[k] > 1) throw new Error(`Drone ${k} must be between 0 and 1.`);
  return { mode: out.mode, level: out.level, breaths: out.breaths, depth: out.depth, bright: out.bright };
}

export const SOLO_DROP_DB = 18;

/**
 * Crowding guard: as the count rises, notes get quieter and shorter so
 * the loop does not become a wash. Power is held about constant above 8 events.
 */
export function crowding(count, layout) {
  const gainDb = -10 * Math.log10(Math.max(1, count / 8));
  const durScale = layout === 'lines' ? 1 : Math.max(0.4, Math.min(1, 16 / count));
  return { gainDb, durScale };
}

/**
 * @typedef {object} Note
 * @property {number} t      onset, s
 * @property {number} dur    sounding length before release, s
 * @property {number} freq   Hz
 * @property {number} gainDb
 * @property {number} cutoff Hz
 * @property {number} am     flutter rate, Hz (0 = smooth)
 * @property {number} pan    -1..1
 * @property {number} wet    reverberation send, 0..0.9 (the distance channel)
 * @property {number} vib    vibrato depth, cents (5.5 Hz)
 * @property {string} inst   the voice
 * @property {string} artic
 * @property {boolean} dim   soloed out
 * @property {boolean} sustained
 * @property {number} v1
 * @property {number} v2
 */

/**
 * @param {{onset:number, v1:number, v2:number, hold:number|null}[]} events
 * @param {{c1:string, c2:string, n1:number, n2:number, layout:string, count:number,
 *          solo?: {v:1|2, level:number}|null, voice?:string, octave?:number, span?:number}} s
 * @returns {Note[]}
 */
export function mapEvents(events, s) {
  const lv1 = levels(s.c1, s.n1, s);
  const lv2 = levels(s.c2, s.n2, s);
  const guard = crowding(events.length, s.layout); // the real count: lines stop at eight
  return events.map((e) => {
    const p = rest(s);
    p[s.c1] = lv1[e.v1];
    p[s.c2] = lv2[e.v2];
    const sustained = e.hold != null;
    const dim = !!s.solo && (s.solo.v === 1 ? e.v1 : e.v2) !== s.solo.level;
    return {
      t: e.onset,
      dur: sustained ? e.hold : p.duration * guard.durScale,
      freq: p.pitch,
      gainDb: p.loudness + guard.gainDb - (dim ? SOLO_DROP_DB : 0),
      cutoff: p.brightness,
      am: p.roughness,
      pan: p.pan,
      wet: p.distance,
      vib: p.vibrato,
      inst: s.voice ?? DEFAULT_VOICE,
      // A flagged day (ice on the gauge) plays with a muted tick, unless a lane already uses articulation.
      artic: sustained ? 'sustain' : e.flag && s.c1 !== 'articulation' && s.c2 !== 'articulation' ? 'tick' : p.articulation,
      dim,
      sustained,
      v1: e.v1,
      v2: e.v2,
      ...(e.k != null ? { k: e.k, flag: !!e.flag } : {}),
    };
  });
}

function rest(o) {
  return Object.fromEntries(Object.values(byId).map((c) => [c.id, restOf(c.id, o)]));
}

/**
 * Three notes of one level of one variable, the other channel at rest: what a
 * legend button plays.
 */
export function levelNotes(s, which, k) {
  const ch = which === 1 ? s.c1 : s.c2;
  const n = which === 1 ? s.n1 : s.n2;
  const p = rest(s);
  p[ch] = levels(ch, n, s)[k];
  const sustained = s.layout === 'lines';
  return [0, 0.45, 0.9].slice(0, sustained ? 1 : 3).map((t) => ({
    t,
    dur: sustained ? 1.2 : p.duration,
    freq: p.pitch, gainDb: p.loudness, cutoff: p.brightness, am: p.roughness, pan: p.pan, wet: p.distance, vib: p.vibrato,
    inst: s.voice ?? DEFAULT_VOICE, artic: sustained ? 'sustain' : p.articulation,
    dim: false, sustained, v1: which === 1 ? k : 0, v2: which === 2 ? k : 0,
  }));
}

/** The kept pair as JSON: enough to bind it to a data lane later, and to play the same loop again. */
export function bindingJSON(s) {
  const src = (v) => (v === 'V1' ? s.src1 : s.src2) ?? null;
  const one = (ch, n, v) => ({
    variable: v,
    channel: ch,
    kind: byId[ch].kind,
    levels: levels(ch, n, s).map((x) => (typeof x === 'number' ? +x.toFixed(4) : x)),
    labels: levels(ch, n, s).map(byId[ch].format),
    range: byId[ch].range,
    tag: src(v) && !s.twin ? 'D' : 'S',
    ...(src(v) ? { source: { series: src(v).series, transform: src(v).transform, zeroRest: !!src(v).zeroRest, signed: !!src(v).signed, flip: !!src(v).flip, start: src(v).start ?? 0 } } : {}),
  });
  const anyReal = !!(s.src1 || s.src2);
  return {
    schema: anyReal ? 'sound-channel-brewer/pair@5' : 'sound-channel-brewer/pair@4', // synthetic-only pairs stay pair@4, so older pages still read them
    note: anyReal ? 'Tag D: the lane plays a real series (its source says which and how). Tag S: a design choice on seeded data.' : 'Tag S: a design choice, chosen by ear on random data. Bind a data lane to make it D.',
    layout: s.layout,
    voice: s.voice ?? DEFAULT_VOICE,
    pitch: { octave: s.octave, span: s.span, root: s.root ?? PITCH_DEFAULTS.root, scale: s.scale ?? PITCH_DEFAULTS.scale },
    lanes: [one(s.c1, s.n1, 'V1'), one(s.c2, s.n2, 'V2')],
    models: { V1: s.m1 ?? 'uniform', V2: s.m2 ?? 'uniform' },
    stream: s.layout !== 'lines' && s.stream && s.stream.use !== 'off' ? { V3: s.stream.model, drives: s.stream.use } : null,
    drum: s.drum && s.drum.voice !== 'off' ? { voice: s.drum.voice, V4: s.drum.model, drives: s.drum.channel, level: s.drum.level ?? DRUM_DEFAULTS.level } : null,
    drone: s.drone && s.drone.mode !== 'off' ? { ...s.drone } : null,
    // What else the loop depends on, so pasting this back plays the same sound (pair@3; variation and transition since pair@4).
    play: { seed: s.seed, variation: s.variation ?? 0, direction: s.direction ?? 1, count: s.count, pattern: s.corr, patternOn: s.target, solo: s.solo ?? null, matrix: s.slots ?? null, transition: s.transition ?? TRANSITION_DEFAULT,
      ...(anyReal ? { time: s.time ?? 'fit', twin: !!s.twin } : {}) },
  };
}

/** A lane's source block from a pair@5 JSON, checked. `ids` lists the series the page has loaded (null: the pack failed). */
function readSource(src, i, ids) {
  if (!src) return null;
  if (typeof src !== 'object' || typeof src.series !== 'string') throw new Error(`Lane V${i + 1} source must name a series.`);
  if (!ids) throw new Error(`Lane V${i + 1} plays the real series "${src.series}", but the series could not be loaded on this page.`);
  if (!ids.includes(src.series)) throw new Error(`Lane V${i + 1} series "${src.series}" is not one of: ${ids.join(', ')}.`);
  if (!TRANSFORMS.includes(src.transform)) throw new Error(`Lane V${i + 1} transform "${src.transform}" is not one of: ${TRANSFORMS.join(', ')}.`);
  const start = src.start ?? 0;
  if (!Number.isInteger(start) || start < 0) throw new Error(`Lane V${i + 1} start must be a whole number from 0.`);
  return { series: src.series, transform: src.transform, zeroRest: !!src.zeroRest, signed: !!src.signed, flip: !!src.flip, start };
}

/**
 * Read a pair JSON back into page state. Pure: returns the state to apply and notes on
 * anything that was filled in, or throws an Error whose message says what is wrong.
 * pair@2 has no seed or count; the caller's values stay and a note says so.
 */
export function pairFromJSON(j, o = {}) {
  if (!j || typeof j !== 'object') throw new Error('This is not a JSON object.');
  const m = /^sound-channel-brewer\/pair@(\d+)$/.exec(j.schema ?? '');
  if (!m || +m[1] < 2 || +m[1] > 5) throw new Error(`Unknown schema "${j.schema}"; this page reads pair@2 to pair@5.`);
  const notes = [];
  const oneOf = (v, list, what) => { if (!list.includes(v)) throw new Error(`${what} "${v}" is not one of: ${list.join(', ')}.`); return v; };
  const ids = ALL_CHANNELS.map((c) => c.id);
  if (!Array.isArray(j.lanes) || j.lanes.length !== 2) throw new Error('"lanes" must list two lanes, V1 and V2.');
  const [c1, c2] = j.lanes.map((l, i) => oneOf(l && l.channel, ids, `Lane V${i + 1} channel`));
  if (c1 === c2) throw new Error('The two lanes use the same channel.');
  const layout = oneOf(j.layout, LAYOUTS, 'Layout');
  if (UNAVAILABLE[layout][c1] || UNAVAILABLE[layout][c2]) throw new Error(`The ${layout} layout cannot carry ${UNAVAILABLE[layout][c1] ? c1 : c2}.`);
  const st = {
    c1, c2, layout,
    voice: oneOf(j.voice ?? LEGACY_VOICE, VOICES.map((v) => v.id), 'Voice'),
    octave: oneOf(j.pitch?.octave ?? PITCH_DEFAULTS.octave, OCTAVES, 'Octave'),
    span: oneOf(j.pitch?.span ?? PITCH_DEFAULTS.span, SPANS, 'Span'),
    root: oneOf(j.pitch?.root ?? PITCH_DEFAULTS.root, ROOTS, 'Key root'),
    scale: oneOf(j.pitch?.scale ?? PITCH_DEFAULTS.scale, SCALE_IDS, 'Scale'),
    drone: j.drone ? readDrone(j.drone) : { ...DRONE_DEFAULTS, ...(o.drone ?? {}), mode: 'off' },
    m1: oneOf(j.models?.V1 ?? 'uniform', MODEL_IDS, 'V1 data model'),
    m2: oneOf(j.models?.V2 ?? 'uniform', MODEL_IDS, 'V2 data model'),
    drum: j.drum ? { voice: oneOf(j.drum.voice, DRUM_IDS.filter((d) => d !== 'off'), 'Drum'), model: oneOf(j.drum.V4, MODEL_IDS, 'V4 data model'), channel: oneOf(j.drum.drives, DRUM_CHANNEL_IDS, 'V4 drives'), level: drumLevel(j.drum.level) } : { ...DRUM_DEFAULTS, ...(o.drum ?? {}), voice: 'off' },
    stream: j.stream ? { model: oneOf(j.stream.V3, STREAM_IDS, 'V3 model'), use: oneOf(j.stream.drives, STREAM_USES, 'V3 drives') } : { model: o.stream?.model ?? 'seasonal', use: 'off' },
  };
  [st.src1, st.src2] = j.lanes.map((l, i) => readSource(l.source, i, o.seriesIds ?? null));
  st.time = j.play?.time ? oneOf(j.play.time, TIME_MODES, 'Time mode') : (o.time ?? 'fit');
  st.twin = !!j.play?.twin;
  [st.n1, st.n2] = j.lanes.map((l, i) => {
    const n = Array.isArray(l.levels) ? l.levels.length : NaN;
    const ch = i ? c2 : c1;
    if (!(n >= MIN_LEVELS && n <= maxLevelsOf(ch, st))) throw new Error(`Lane V${i + 1} has ${l.levels?.length ?? 'no'} levels; ${ch} takes ${MIN_LEVELS} to ${maxLevelsOf(ch, st)} here.`);
    return n;
  });
  const p = j.play;
  if (p) {
    if (!Number.isInteger(p.seed) || p.seed < 1 || p.seed > MAX_SEED) throw new Error(`Seed "${p.seed}" must be a whole number from 1 to ${MAX_SEED}.`);
    const v = p.variation ?? 0, dir = p.direction ?? 1, tr = p.transition ?? o.transition ?? TRANSITION_DEFAULT;
    if (typeof v !== 'number' || v < 0 || v > 1) throw new Error('"variation" must be between 0 and 1.');
    if (!Number.isInteger(dir) || dir < 1 || dir > 99) throw new Error('"direction" must be a whole number from 1 to 99.');
    if (typeof tr !== 'number' || tr < TRANSITION_RANGE[0] || tr > TRANSITION_RANGE[1]) throw new Error(`"transition" must be ${TRANSITION_RANGE[0]} to ${TRANSITION_RANGE[1]} seconds.`);
    Object.assign(st, { variation: v, direction: dir, transition: tr });
    if (!Number.isInteger(p.count) || p.count < 4 || p.count > 64) throw new Error(`Count "${p.count}" must be a whole number from 4 to 64.`);
    if (typeof p.pattern !== 'number' || p.pattern < 0 || p.pattern > 1) throw new Error('"pattern" must be between 0 and 1.');
    Object.assign(st, { seed: p.seed, count: p.count, corr: p.pattern, target: oneOf(p.patternOn ?? 'both', ['v1', 'v2', 'both'], 'Pattern on') });
    if (p.solo) {
      const n = p.solo.v === 1 ? st.n1 : st.n2;
      if (![1, 2].includes(p.solo.v) || !Number.isInteger(p.solo.level) || p.solo.level < 0 || p.solo.level >= n) throw new Error('"solo" must name lane 1 or 2 and one of its levels.');
      st.solo = { v: p.solo.v, level: p.solo.level };
    } else st.solo = null;
    if (p.matrix) {
      if (!Array.isArray(p.matrix) || p.matrix.length !== MATRIX_SIZE || new Set(p.matrix).size !== MATRIX_SIZE) throw new Error(`"matrix" must list ${MATRIX_SIZE} different channels.`);
      p.matrix.forEach((id) => oneOf(id, ids, 'Matrix channel'));
      st.slots = [...p.matrix];
    }
  } else {
    st.solo = null;
    st.variation = 0;
    notes.push('This JSON is pair@2, which has no seed or count, so it plays on the seed and count already set here.');
  }
  // A lane's channel must be in the matrix to be heard; put it in place of a channel the pair does not use.
  const slots = [...(st.slots ?? o.slots ?? DEFAULT_SLOTS)];
  for (const c of [c1, c2]) {
    if (slots.includes(c)) continue;
    const i = slots.findLastIndex((id) => id !== c1 && id !== c2);
    notes.push(`${byId[c].label} was on the bench; it takes the place of ${byId[slots[i]].label}.`);
    slots[i] = c;
  }
  st.slots = slots;
  return { state: st, notes };
}
