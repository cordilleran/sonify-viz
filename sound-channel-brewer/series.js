/**
 * Real data series as sources for V1 and V2 (Slice A of the 261116 data-feed spec). Pure, no DOM.
 * A series from the pack (series.json, built by scripts/build_brewer_series.py) becomes one item per loop slot:
 *   Fit   – the whole period cut into as many groups as the loop has events, each group summarised
 *           (median for smooth kinds, maximum for spiky ones);
 *   Slice – one event per step (day, month, year) for a window that starts where the listener puts it.
 * Each item is then transformed (Lin, Log or Rank) and binned into the channel's levels over the whole period,
 * so a level means the same in Fit and in Slice. Gaps, and zeros when "zero is a rest" is on, become rests.
 */

export const TRANSFORMS = ['lin', 'log', 'rank'];
export const TRANSFORM_LABELS = { lin: 'Lin', log: 'Log', rank: 'Rank' };
export const TIME_MODES = ['fit', 'slice'];

/** Defaults by kind: the transform, how Fit summarises a group, and the toggles. */
export const KIND_DEFAULTS = {
  skewed: { transform: 'log', agg: 'median', zeroRest: false, signed: false, why: 'Skewed: most days are low and a few are very high, so Log spreads the low days over more levels.' },
  slow: { transform: 'lin', agg: 'median', zeroRest: false, signed: false, why: 'Slow and smooth: equal steps between the lowest and highest value.' },
  signed: { transform: 'lin', agg: 'median', zeroRest: false, signed: true, why: 'Signed: values above and below zero. Levels are cut the same width on both sides, so with an odd number of levels zero gets the middle one.' },
  spiky: { transform: 'log', agg: 'max', zeroRest: true, signed: false, why: 'Spiky and mostly zero: zero is a rest, and Log spreads the wet days. Fit keeps each group’s wettest day.' },
  bounded: { transform: 'lin', agg: 'median', zeroRest: true, signed: false, fixed: [0, 1], why: 'A fraction from 0 to 1: levels are cut on the fixed range, not the data’s own, so a quarter covered is always the same level. Zero (open water) is a rest.' },
  trend: { transform: 'lin', agg: 'median', zeroRest: false, signed: false, why: 'A trend: equal steps, so the climb is heard as it is.' },
  seasonal: { transform: 'lin', agg: 'median', zeroRest: false, signed: false, why: 'A seasonal cycle: equal steps.' },
  peaks: { transform: 'lin', agg: 'max', zeroRest: false, signed: false, why: 'One peak per year: equal steps; Fit keeps the biggest peak in each group.' },
};

/** The lane source a series starts with: its kind's defaults. */
export function defaultSource(series) {
  const d = KIND_DEFAULTS[series.kind] ?? KIND_DEFAULTS.slow;
  return { series: series.id, transform: d.transform, zeroRest: d.zeroRest && hasZeros(series), signed: d.signed && hasNegatives(series), flip: false, start: 0 };
}

export const hasZeros = (s) => s.values.some((v) => v === 0);
export const hasNegatives = (s) => s.values.some((v) => v != null && v < 0);
/** Log needs positive values (zeros are allowed: they become rests or sit below the smallest wet value). */
export const logAllowed = (s) => !hasNegatives(s);

const median = (a) => { const b = [...a].sort((x, y) => x - y), h = b.length >> 1; return b.length % 2 ? b[h] : (b[h - 1] + b[h]) / 2; };

/** Index ranges flagged (for example ice) as a per-index boolean array. */
export function flagMask(series, name = 'ice') {
  const m = new Array(series.values.length).fill(false);
  for (const [a, b] of series.flags?.[name] ?? []) for (let i = a; i <= b; i++) m[i] = true;
  return m;
}

/**
 * Fit: the whole period into m groups, in time order. Group k covers indices [floor(kN/m), floor((k+1)N/m)).
 * The value is the median (or the maximum for spiky kinds) of the group's values; a group with no values is a gap.
 * A group is flagged when at least half its indices are.
 */
export function fitGroups(values, m, agg = 'median', mask = null) {
  const N = values.length, out = [];
  for (let k = 0; k < m; k++) {
    let i0 = Math.floor((k * N) / m), i1 = Math.floor(((k + 1) * N) / m) - 1;
    if (i1 < i0) i1 = i0; // fewer values than events: a value can serve two events
    const vs = [];
    let fl = 0;
    for (let i = i0; i <= i1; i++) { if (values[i] != null) vs.push(values[i]); if (mask && mask[i]) fl++; }
    out.push({ i0, i1, raw: vs.length ? (agg === 'max' ? Math.max(...vs) : median(vs)) : null, flag: mask ? fl * 2 >= i1 - i0 + 1 : false });
  }
  return out;
}

/** Slice: m consecutive steps from start (clamped so the window fits). */
export function sliceItems(values, m, start = 0, mask = null) {
  const N = values.length;
  const s = Math.max(0, Math.min(Math.max(0, N - m), Math.round(start)));
  return Array.from({ length: m }, (_, k) => {
    const i = Math.min(N - 1, s + k);
    return { i0: i, i1: i, raw: values[i] ?? null, flag: mask ? mask[i] : false };
  });
}

/**
 * A binning of one series into n levels, over the whole period (so Fit and Slice agree).
 * @returns {{level:(raw:number|null)=>number|null, norm:(raw:number|null)=>number|null, edges:number[], rest:(raw)=>boolean}}
 *   level is null for a rest; norm is the position 0..1 used to draw the line; edges are the cut points in norm space.
 */
export function binner(series, src, n) {
  // One update can ask for the same binning several times (setting, legends, shape row, strip): keep the last few.
  const key = `${series.id}|${series.values.length}|${src.transform}|${!!src.zeroRest}|${!!src.signed}|${!!src.flip}|${n}`;
  const hit = BIN_CACHE.get(key);
  if (hit && hit.series === series) return hit.b;
  const b = makeBinner(series, src, n);
  if (BIN_CACHE.size > 32) BIN_CACHE.clear();
  BIN_CACHE.set(key, { series, b });
  return b;
}
const BIN_CACHE = new Map();
function makeBinner(series, src, n) {
  const kind = KIND_DEFAULTS[series.kind] ?? KIND_DEFAULTS.slow;
  const tr = src.transform === 'log' && !logAllowed(series) ? 'lin' : src.transform;
  const isRest = (v) => v == null || (src.zeroRest && v === 0);
  const pool = series.values.filter((v) => !isRest(v));
  const flip = (l) => (src.flip ? n - 1 - l : l);
  const cut = (x) => Math.min(n - 1, Math.max(0, Math.floor(x * n)));
  const edges = Array.from({ length: n - 1 }, (_, k) => (k + 1) / n);
  let norm;
  if (tr === 'rank') {
    const sorted = [...pool].sort((a, b) => a - b);
    const below = (v) => { let lo = 0, hi = sorted.length; while (lo < hi) { const mid = (lo + hi) >> 1; if (sorted[mid] < v) lo = mid + 1; else hi = mid; } return lo; };
    const upto = (v) => { let lo = 0, hi = sorted.length; while (lo < hi) { const mid = (lo + hi) >> 1; if (sorted[mid] <= v) lo = mid + 1; else hi = mid; } return lo; };
    norm = (v) => (below(v) + upto(v)) / 2 / sorted.length; // mid-rank, 0..1
  } else {
    const minPos = Math.min(...pool.filter((v) => v > 0));
    const y = tr === 'log' ? (v) => Math.log10(v > 0 ? v : minPos / 2) : (v) => v;
    const ys = pool.map(y);
    let lo, hi;
    if (kind.fixed && tr === 'lin') [lo, hi] = kind.fixed;
    else if (src.signed && tr === 'lin') { const M = Math.max(...ys.map(Math.abs)) || 1; lo = -M; hi = M; } else { lo = Math.min(...ys); hi = Math.max(...ys); }
    const span = hi - lo || 1;
    norm = (v) => Math.min(1, Math.max(0, (y(v) - lo) / span));
  }
  return {
    transform: tr,
    rest: isRest,
    norm: (v) => (isRest(v) ? null : norm(v)),
    level: (v) => (isRest(v) ? null : flip(cut(norm(v)))),
    edges,
  };
}

/** The date or time of index i, as text. */
export function stepLabel(series, i) {
  const st = series.start;
  if (series.step === 'day') { const d = new Date(`${st}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + i); return d.toISOString().slice(0, 10); }
  if (series.step === 'month') { const [y, mo] = st.split('-').map(Number), t = y * 12 + (mo - 1) + i; return `${Math.floor(t / 12)}-${String((t % 12) + 1).padStart(2, '0')}`; }
  if (series.step === 'year') return String(Number(st) + i);
  if (series.step === '6h') { const d = new Date(`${st}:00:00Z`); d.setUTCHours(d.getUTCHours() + 6 * i); return `${d.toISOString().slice(0, 13).replace('T', ' ')}:00`; }
  return String(i);
}
export const STEP_WORD = { day: 'day', month: 'month', year: 'year', '6h': 'six-hour step' };
export function itemLabel(series, it) {
  return it.i0 === it.i1 ? stepLabel(series, it.i0) : `${stepLabel(series, it.i0)} to ${stepLabel(series, it.i1)}`;
}

/**
 * One lane's items for the loop: m slots in time order, each with its raw value, level (null = rest), norm and flag.
 * @param {object} series  a series from the pack
 * @param {{transform:string, zeroRest:boolean, signed:boolean, flip:boolean, start:number}} src
 * @param {{mode:'fit'|'slice', m:number, n:number}} o
 */
export function laneItems(series, src, o) {
  const mask = flagMask(series);
  const agg = (KIND_DEFAULTS[series.kind] ?? KIND_DEFAULTS.slow).agg;
  const raw = o.mode === 'slice' ? sliceItems(series.values, o.m, src.start, mask) : fitGroups(series.values, o.m, agg, mask);
  const b = binner(series, src, o.n);
  return raw.map((it) => ({ ...it, level: b.level(it.raw), norm: b.norm(it.raw), label: itemLabel(series, it) }));
}

/** The largest useful Slice start for a series and window length. */
export const maxStart = (series, m) => Math.max(0, series.values.length - m);

/** Plain words for the formula panel. */
export function explainLane(series, src, o, which) {
  const K = KIND_DEFAULTS[series.kind] ?? KIND_DEFAULTS.slow;
  const b = binner(series, src, o.n);
  const N = series.values.length, per = N / o.m;
  const time = o.mode === 'slice'
    ? `Slice plays ${o.m} ${STEP_WORD[series.step]}s in a row, one per event, starting at ${stepLabel(series, Math.min(src.start, maxStart(series, o.m)))}.`
    : `Fit plays the whole period, ${N} ${STEP_WORD[series.step]}s, as ${o.m} groups of about ${per.toFixed(1)}; each event takes its group’s ${K.agg === 'max' ? 'largest value' : 'median'}.`;
  const tr = { lin: 'Lin cuts the range into equal steps.', log: 'Log takes the logarithm first, so each level covers the same ratio (for example 2 to 20 and 20 to 200) instead of the same difference.', rank: 'Rank puts every value in order and gives each level the same number of values, so all levels are used equally; it hides how far apart the values are.' }[b.transform];
  const extra = [src.signed && b.transform === 'lin' ? 'The steps are cut the same width either side of zero.' + (o.n % 2 ? ' Zero sits in the middle level.' : ' With an even number of levels there is no middle level, so zero falls on the upper one.') : '',
    src.zeroRest ? 'Zero is a rest: those events are silent.' : '', src.flip ? 'Flip is on: bigger values take lower levels.' : '',
    (series.flags?.ice ?? []).length ? 'Days the gauge marked as affected by ice play with a muted tick and are shaded in the data strip.' : ''].filter(Boolean).join(' ');
  return {
    title: `V${which}: ${series.title} (real data)`,
    plain: `${series.place}, ${series.units}. ${K.why} ${time} ${tr} ${extra} Source: ${series.source}. ${series.licence}.`,
    tex: binTex(series, src, b, o.n),
    code: `fitGroups = ${fitGroups.toString()};\nsliceItems = ${sliceItems.toString()};\n// levels: binner() keeps the last few of these\nmakeBinner = ${makeBinner.toString()};`,
  };
}

/** The binning as a formula, matching makeBinner: fixed range, signed, log floor for zeros, rank, flip. */
function binTex(series, src, b, n) {
  const K = KIND_DEFAULTS[series.kind] ?? KIND_DEFAULTS.slow;
  let core, note = '';
  if (b.transform === 'rank') { core = String.raw`\min\!\left(n-1, \lfloor n\,F(x) \rfloor\right)`; note = String.raw`F = \text{mid-rank of } x \text{ over the period}`; }
  else if (b.transform === 'log') {
    core = String.raw`\min\!\left(n-1, \left\lfloor n\,\frac{\log_{10} x - \log_{10} x_{\min}}{\log_{10} x_{\max} - \log_{10} x_{\min}} \right\rfloor\right)`;
    if (!src.zeroRest && hasZeros(series)) note = String.raw`x = 0 \text{ taken as half the smallest value above zero}`;
  } else if (K.fixed) { core = String.raw`\min\!\left(n-1, \left\lfloor n\,\frac{x - ${K.fixed[0]}}{${K.fixed[1]} - ${K.fixed[0]}} \right\rfloor\right)`; note = String.raw`\text{a fixed range}`; }
  else if (src.signed) { core = String.raw`\min\!\left(n-1, \left\lfloor n\,\frac{x + M}{2M} \right\rfloor\right)`; note = String.raw`M = \max|x|`; }
  else core = String.raw`\min\!\left(n-1, \left\lfloor n\,\frac{x - x_{\min}}{x_{\max} - x_{\min}} \right\rfloor\right)`;
  // Flip subtracts only the level term; definitions and notes follow it.
  const lhs = src.flip ? String.raw`\ell = n - 1 - \left(${core}\right)` : String.raw`\ell = ${core}`;
  const tail = [note, src.zeroRest ? String.raw`x = 0 \Rightarrow \text{rest}` : '', `n = ${n}`].filter(Boolean).join(String.raw`,\quad `);
  return String.raw`${lhs},\quad ${tail}`;
}

/** Three presets (DK72): each sketches a mapping and has one "Try this" that flips one setting. */
export const PRESETS = [
  {
    id: 'flow-temp', title: 'Granby flow on pitch, Summerland temperature on brightness',
    sketch: 'Water Year Rings in miniature: the freshet climbs in pitch while the year warms and cools in tone colour.',
    set: { c1: 'pitch', c2: 'brightness', n1: 5, n2: 5, layout: 'grid', count: 32, mode: 'fit', src1: { series: 'granby' }, src2: { series: 'summerland-temp' } },
    tryLabel: 'Try: Log to Lin on the flow', try: (S) => ({ src1: { ...S.src1, transform: S.src1?.transform === 'lin' ? 'log' : 'lin' } }),
    teach: 'With Lin, most of the year sits on the lowest level and only the freshet climbs; Log spreads the low flows out.',
  },
  {
    id: 'temp-precip', title: 'Summerland temperature and precipitation',
    sketch: 'The climate pair at one station: temperature on pitch, rain on loudness, dry days as rests.',
    set: { c1: 'pitch', c2: 'loudness', n1: 5, n2: 4, layout: 'grid', count: 16, mode: 'slice', start: 'Wettest day', src1: { series: 'summerland-temp' }, src2: { series: 'summerland-precip' } },
    tryLabel: 'Try: swap the channels', try: (S) => ({ c1: S.c2, c2: S.c1, n1: S.n2, n2: S.n1 }),
    teach: 'Rain on pitch makes the wet days jump out as melody; on loudness they are accents under the temperature line.',
  },
  {
    id: 'oni-pan', title: 'ENSO on pitch and pan',
    sketch: 'Sixty-eight years of the Oceanic Niño Index on two channels at once: El Niño high and right, La Niña low and left.',
    set: { c1: 'pitch', c2: 'pan', n1: 5, n2: 5, layout: 'grid', count: 48, mode: 'fit', src1: { series: 'oni' }, src2: { series: 'oni' } },
    tryLabel: 'Try: 5 levels to 4', try: (S) => ({ n1: S.n1 === 4 ? 5 : 4, n2: S.n2 === 4 ? 5 : 4 }),
    teach: 'With five levels a neutral year has its own middle note and sits in the centre; with four there is no middle, so neutral sounds like a weak El Niño.',
  },
];

/** MIDI number and name of a frequency. */
export function midiOf(freq) { return Math.round(69 + 12 * Math.log2(freq / 440)); }
const NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
export function pitchName(midi) { return `${NAMES[((midi % 12) + 12) % 12]}${Math.floor(midi / 12) - 1}`; }
/** Note value of a duration at a tempo (beats per minute, quarter = one beat). */
export function noteValue(sec, bpm) {
  const beats = (sec * bpm) / 60;
  const vals = [[4, 'whole'], [3, 'dotted half'], [2, 'half'], [1.5, 'dotted quarter'], [1, 'quarter'], [0.75, 'dotted eighth'], [0.5, 'eighth'], [0.25, 'sixteenth'], [0.125, 'thirty-second']];
  return vals.reduce((best, v) => (Math.abs(Math.log(v[0] / beats)) < Math.abs(Math.log(best[0] / beats)) ? v : best))[1];
}
/** Dynamic marking of a gain in dB (0 dB = forte). */
export function dynamicOf(db) {
  const marks = [[-30, 'ppp'], [-24, 'pp'], [-18, 'p'], [-12, 'mp'], [-6, 'mf'], [0, 'f'], [6, 'ff']];
  return marks.reduce((best, m) => (Math.abs(m[0] - db) < Math.abs(best[0] - db) ? m : best))[1];
}
