/**
 * Seeded event pool, data models, layouts and the third variable, V3.
 * Pure, deterministic. One pool of POOL draws is sliced to the event count, so
 * moving the count adds or removes events instead of re-rolling all of them.
 * Each variable's value x in [0, 1] comes from its data model; level = floor(x · n).
 * Temporal pattern: a smooth periodic curve over the loop; events that take it get
 * the level of the curve at their onset, cut at the curve's quantiles, so every
 * level covers an equal share of the loop.
 * V3 is a slow stream variable over time that can drive density or pace.
 */

export const POOL = 300;
export const MAX_LINES = 8;
export const DEFAULT_SEED = 1028;
const WALK_NODES = 128;

/** mulberry32: small seeded PRNG returning floats in [0, 1). */
export function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const clamp01 = (x) => Math.min(1, Math.max(0, x));
/** Box-Muller: two uniforms to one standard normal. */
const normal = (a, b) => Math.sqrt(-2 * Math.log(1 - a)) * Math.cos(2 * Math.PI * b);
const r2 = (x) => x.toFixed(2);

/** A random walk on WALK_NODES nodes, rescaled to 0.05..0.95, read by linear interpolation. */
function walk(r) {
  const w = [0];
  for (let i = 1; i <= WALK_NODES; i++) w.push(w[i - 1] + normal(r(), r()));
  const lo = Math.min(...w), hi = Math.max(...w);
  const v = w.map((x) => 0.05 + (0.9 * (x - lo)) / (hi - lo || 1));
  const at = (f) => { const p = clamp01(f) * WALK_NODES, j = Math.min(WALK_NODES - 1, Math.floor(p)); return v[j] + (p - j) * (v[j + 1] - v[j]); };
  return { at, lo, hi };
}

/**
 * Data models for V1 and V2. Each gives x in [0, 1] for one draw at loop fraction f.
 * `plain` explains it in words, `tex` gives the formula with the numbers this pool drew, and `x` is the code that runs.
 */
export const MODELS = {
  uniform: { label: 'Uniform', plain: () => 'Use it to hear the pair with no structure in the data at all. Every value between 0 and 1 is equally likely, so every level turns up about equally often.', tex: () => String.raw`x = u`, x: (d) => d.u },
  normal: { label: 'Normal', plain: () => 'Most real measurements cluster around a typical value. Here x sits near the middle and rarely reaches the ends: about two events in three fall between 0.33 and 0.67. Listen for whether the middle levels stay distinct when they carry most of the notes.', tex: () => String.raw`x = 0.5 + z/6`, x: (d) => clamp01(0.5 + d.z / 6) },
  skewed: { label: 'Skewed (exponential)', plain: () => 'Many environmental quantities, such as rain or streamflow, are mostly small with a few large values. Here most x are low and a long tail reaches up; half the events fall below about 0.17. Listen for whether the rare high levels stand out.', tex: () => String.raw`x = -\ln(1-u)/4`, x: (d) => clamp01(-Math.log(1 - d.u) / 4) },
  bimodal: { label: 'Bimodal', plain: () => 'Some data have two usual states, such as ice and open water. Here x sits near 0.25 or near 0.75, and a coin b decides which. Listen for whether the two clusters read as two groups.', tex: () => String.raw`x = \begin{cases} 0.25 + z/14 & b < 0.5 \\ 0.75 + z/14 & b \ge 0.5 \end{cases}`, x: (d) => clamp01((d.b < 0.5 ? 0.25 : 0.75) + d.z / 14) },
  walk: { label: 'Random walk', plain: () => 'A random walk is how a slowly drifting series behaves, such as groundwater or a reservoir level: each step starts where the last one ended. Events close in time get similar values and the line wanders. Listen for whether the drift comes through.', tex: () => String.raw`x = W(t) + z/40, \quad W_{j+1} = W_j + z_j \ \text{(rescaled to } [0.05, 0.95])`, x: (d, f, p) => clamp01(p.walk.at(f) + d.z / 40) },
  seasonal: { label: 'Seasonal cycle + noise', plain: () => 'A seasonal cycle rises and falls once per loop, like temperature over a year, with a little noise on top. Listen for the cycle.', tex: (p) => String.raw`x = 0.5 + 0.38\sin(2\pi t/T + ${r2(p.phase)}) + z/16`, x: (d, f, p) => clamp01(0.5 + 0.38 * Math.sin(2 * Math.PI * f + p.phase) + d.z / 16) },
  trend: { label: 'Trend + noise', plain: () => 'A trend climbs steadily across the loop, with noise, like a warming record. Listen for whether the rise is heard from the first event to the last.', tex: () => String.raw`x = 0.08 + 0.84\,t/T + z/16`, x: (d, f) => clamp01(0.08 + 0.84 * f + d.z / 16) },
  spikes: { label: 'Rare spikes', plain: () => 'Mostly quiet with rare events, such as storms or floods: about one event in ten jumps near the top and the rest stay low. Listen for whether the spikes pop out.', tex: () => String.raw`x = \begin{cases} 0.8 + 0.2u & b < 0.1 \\ 0.2u & \text{otherwise} \end{cases}`, x: (d) => (d.b < 0.1 ? 0.8 + 0.2 * d.u : 0.2 * d.u) },
};
export const MODEL_IDS = Object.keys(MODELS);

/** Stream models for V3: slow functions of time only. */
export const STREAM_MODELS = {
  seasonal: { label: 'Seasonal cycle', plain: 'V3 rises and falls once per loop.', tex: (p) => String.raw`x_3 = 0.5 + 0.45\sin(2\pi t/T + ${r2(p.phase3)})`, f: (t, p) => 0.5 + 0.45 * Math.sin(2 * Math.PI * t + p.phase3) },
  trend: { label: 'Trend', plain: 'V3 climbs from low to high across the loop.', tex: () => String.raw`x_3 = 0.05 + 0.9\,t/T`, f: (t) => 0.05 + 0.9 * t },
  walk: { label: 'Random walk', plain: 'V3 wanders, each step starting where the last ended.', tex: () => String.raw`x_3 = W_3(t)`, f: (t, p) => p.walk3.at(t) },
  bursts: { label: 'Bursts', plain: 'V3 stays low except for three short bursts at times drawn from the seed.', tex: (p) => String.raw`x_3 = 0.1 + 0.9\sum_{c} e^{-((t/T - c)/0.06)^2},\ c \in \{${p.bursts.map(r2).join(', ')}\}`, f: (t, p) => clamp01(0.1 + p.bursts.reduce((s, c) => s + 0.9 * Math.exp(-(((((t - c + 1.5) % 1) - 0.5) / 0.06) ** 2)), 0)) },
};
export const STREAM_IDS = Object.keys(STREAM_MODELS);
export const STREAM_USES = ['off', 'density', 'pace'];

/**
 * Draw the pool. Every draw is made in a fixed order, so a seed always gives
 * the same pool whatever layout, count or model is used later.
 */
export function makePool(seed = DEFAULT_SEED) {
  const r = rng(seed);
  const draws = [];
  for (let i = 0; i < POOL; i++) {
    const d = { u1: r(), u2: r(), rc1: r(), rc2: r(), cloud: r(), keep: r() };
    d.z1 = normal(r(), r()); d.z2 = normal(r(), r());
    d.b1 = r(); d.b2 = r();
    draws.push(d);
  }
  // Two smooth curves (three harmonics each, periodic over the loop) for the temporal pattern on V1 and V2.
  const curve = () => {
    const ph = [r(), r(), r()].map((x) => x * 2 * Math.PI);
    const amp = [1, 0.5 + 0.3 * r(), 0.25 + 0.2 * r()];
    const fn = (f) => amp.reduce((s, a, k) => s + a * Math.sin(2 * Math.PI * (k + 1) * f + ph[k]), 0);
    fn.params = { ph, amp };
    return fn;
  };
  const curve1 = curve(), curve2 = curve();
  const p1 = { phase: 2 * Math.PI * r(), walk: walk(r) };
  const p2 = { phase: 2 * Math.PI * r(), walk: walk(r) };
  const p3 = { phase3: 2 * Math.PI * r(), walk3: walk(r), bursts: [r(), r(), r()].sort() };
  // The drum lane's V4, drawn last so every draw above is the same as before it existed.
  const p4 = { phase: 2 * Math.PI * r(), walk: walk(r) };
  const drum4 = Array.from({ length: 16 }, () => ({ u: r(), z: normal(r(), r()), b: r(), k: r() }));
  return { seed, draws, curve1, curve2, p1, p2, p3, p4, drum4 };
}

/** The draw seen by a model for one variable. */
const view = (d, which) => (which === 1 ? { u: d.u1, z: d.z1, b: d.b1 } : { u: d.u2, z: d.z2, b: d.b2 });

/** V3 at loop fraction f (0..1). */
export function streamAt(pool, model, f) { return clamp01(STREAM_MODELS[model].f(f, pool.p3)); }

/**
 * Levels from fixed cut points: the curve's quantiles over the whole loop, so
 * every level covers the same share of time and an event's level never depends
 * on which other events are in the slice.
 */
const SAMPLES = 4096;
function cutPoints(curve, n) {
  const v = Array.from({ length: SAMPLES }, (_, i) => curve(i / SAMPLES)).sort((a, b) => a - b);
  return Array.from({ length: n - 1 }, (_, k) => v[Math.floor(((k + 1) * SAMPLES) / n)]);
}
const levelOf = (x, cuts) => cuts.reduce((l, c) => (x >= c ? l + 1 : l), 0);

/** Pace: warp fractions so the local event rate is 0.4 + 1.6 x₃. Returns f -> warped f. */
function paceWarp(pool, model) {
  const M = 512, cum = [0];
  for (let i = 0; i < M; i++) cum.push(cum[i] + 0.4 + 1.6 * streamAt(pool, model, (i + 0.5) / M));
  const tot = cum[M];
  return (f) => {
    const target = f * tot;
    let lo = 0, hi = M;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (cum[mid] <= target) lo = mid; else hi = mid; }
    return (lo + (target - cum[lo]) / (cum[lo + 1] - cum[lo])) / M;
  };
}

/**
 * Events for one setting.
 * @param {ReturnType<typeof makePool>} pool
 * @param {{layout:'grid'|'cloud'|'lines', count:number, n1:number, n2:number,
 *          corr:number, target:'v1'|'v2'|'both', loopSec:number,
 *          m1?:string, m2?:string, stream?:{model:string, use:string}}} o
 * @returns {{i:number, onset:number, v1:number, v2:number, x1:number, x2:number, hold:number|null}[]}
 *   onset in seconds; hold is the sustained length for lines, null otherwise.
 *   Density can drop events, so the result may be shorter than the count.
 */
export function eventsFor(pool, o) {
  const m = o.layout === 'lines' ? Math.min(o.count, MAX_LINES) : Math.min(o.count, POOL);
  const L = o.loopSec;
  const M1 = MODELS[o.m1 ?? 'uniform'], M2 = MODELS[o.m2 ?? 'uniform'];
  const st = o.layout !== 'lines' && o.stream && o.stream.use !== 'off' ? o.stream : null;
  const warp = st && st.use === 'pace' ? paceWarp(pool, st.model) : (f) => f;
  const slice = pool.draws.slice(0, m);
  const fr = slice.map((d, i) => warp(o.layout === 'cloud' ? d.cloud : i / m));
  const cut1 = cutPoints(pool.curve1, o.n1), cut2 = cutPoints(pool.curve2, o.n2);
  const on1 = o.target === 'v1' || o.target === 'both';
  const on2 = o.target === 'v2' || o.target === 'both';
  const hold = o.layout === 'lines' ? Math.min(2.4, Math.max(1.2, (2 * L) / m)) : null;
  const lv = (x, n) => Math.min(n - 1, Math.floor(x * n));
  const out = [];
  slice.forEach((d, i) => {
    const f = fr[i];
    if (st && st.use === 'density' && d.keep >= 0.1 + 0.9 * streamAt(pool, st.model, f)) return;
    const x1 = M1.x(view(d, 1), f, pool.p1), x2 = M2.x(view(d, 2), f, pool.p2);
    out.push({
      i,
      onset: f * L,
      v1: on1 && d.rc1 < o.corr ? levelOf(pool.curve1(f), cut1) : lv(x1, o.n1),
      v2: on2 && d.rc2 < o.corr ? levelOf(pool.curve2(f), cut2) : lv(x2, o.n2),
      x1, x2,
      hold,
    });
  });
  return out;
}

/**
 * The rules that made this loop, three ways (the formula panel): plain words in Molnar's order
 * (why, what it does, a worked number from this seed), the formula as TeX, and the source of the
 * function that actually runs. The code view is read from the live functions, so it cannot drift.
 * @returns {{title:string, plain:string, tex:string, code:string}[]}
 */
export function explain(pool, o, events = []) {
  const fx = (x) => x.toFixed(2);
  const out = [{
    title: `The seed (${pool.seed})`,
    plain: 'Nothing here is truly random. The seed starts a small arithmetic recipe, mulberry32, that scrambles a counter into numbers u between 0 and 1. The same seed always gives the same numbers, so the same loop comes back; Shuffle picks a new seed. Each event takes its numbers in a fixed order: two values, two pattern draws, a cloud onset, a keep number, two bell-curve numbers z (made from pairs of u by the Box–Muller rule) and two coins b.',
    tex: String.raw`u_i = \operatorname{mulberry32}(${pool.seed})_i \in [0, 1), \qquad z = \sqrt{-2\ln(1-u_a)}\,\cos(2\pi u_b)`,
    code: rng.toString(),
  }];
  for (const which of [1, 2]) {
    const id = (which === 1 ? o.m1 : o.m2) ?? 'uniform', M = MODELS[id], n = which === 1 ? o.n1 : o.n2;
    const p = which === 1 ? pool.p1 : pool.p2;
    const x = events.length ? events[0][`x${which}`] : null;
    const lx = x == null ? 0 : Math.min(n - 1, Math.floor(x * n)), played = events.length ? events[0][`v${which}`] : lx;
    const worked = x == null ? '' : ` In this loop the first event drew x = ${fx(x)}; with ${n} levels that is level ${lx + 1} of ${n}, because ${fx(x)} × ${n} = ${fx(x * n)}, whose whole part is ${lx}, and the levels are counted from 0.${
      played !== lx ? ` This event follows the temporal pattern, though, so it plays level ${played + 1}, taken from the curve.` : ''}`;
    out.push({
      title: `V${which}: ${M.label}`,
      plain: `${M.plain(p)} The value x is held between 0 and 1, and the level is x times the number of levels, rounded down.${worked}`,
      tex: `${M.tex(p)}, \\qquad \\ell = \\min\\left(n - 1, \\lfloor n\\,x \\rfloor\\right),\\ n = ${n}`,
      code: `// x for one event (d = its draws, f = its time as a fraction of the loop, p = this variable's drawn settings)\nMODELS.${id}.x = ${M.x.toString()};\n// level\nconst lv = (x, n) => Math.min(n - 1, Math.floor(x * n));`,
    });
  }
  if (o.corr > 0) {
    const tgt = o.target === 'both' ? 'V1 and V2' : o.target.toUpperCase();
    // One sine term per row, so the curve fits a phone screen.
    const c = (fn) => fn.params.amp.map((a, j) => `${fx(a)}\\sin(${j + 1}\\cdot 2\\pi t/T + ${fx(fn.params.ph[j])})`).join(' \\\\ &\\quad + ');
    const parts = [];
    if (o.target !== 'v2') parts.push(`c_1(t) &= ${c(pool.curve1)}`);
    if (o.target !== 'v1') parts.push(`c_2(t) &= ${c(pool.curve2)}`);
    out.push({
      title: `Temporal pattern (${Math.round(o.corr * 100)} % on ${tgt})`,
      plain: `To test whether a pattern over time comes through, a share of events ignore their data model and take their level from a slow, smooth curve instead. Each event draws a number r; if r is below ${o.corr}, it follows the curve. The curve is cut into bands that each cover the same share of the loop, so every level gets equal time. At ${Math.round(o.corr * 100)} %, about ${Math.round(o.corr * 100)} events in 100 follow it.`,
      tex: `\\begin{aligned} ${parts.join(' \\\\ ')} \\end{aligned}`,
      code: `// the curve: three sine waves whose sizes and phases come from the seed\nconst curve = ${pool.curve1.toString()};\n// V1: amp = [${pool.curve1.params.amp.map(fx)}], ph = [${pool.curve1.params.ph.map(fx)}]`,
    });
  }
  if (o.layout !== 'lines' && o.stream && o.stream.use !== 'off') {
    const S = STREAM_MODELS[o.stream.model];
    const use = o.stream.use === 'density'
      ? { plain: 'V3 decides how busy the loop is. Each event has a keep number k between 0 and 1 and sounds only if k is below 0.1 + 0.9 × V3 at its time: where V3 is near 1 nearly every event plays, where it is near 0 only about one in ten.', tex: String.raw`\text{keep the event if } k < 0.1 + 0.9\,x_3(t)` }
      : { plain: 'V3 decides how fast events come. The local rate is 0.4 + 1.6 × V3, so the pulse runs at 0.4 times its base rate where V3 is 0 and twice the base rate where V3 is 1; the onsets are stretched to fit, and the count stays the same.', tex: String.raw`\text{rate}(t) \propto 0.4 + 1.6\,x_3(t)` };
    out.push({
      title: `V3: ${S.label}, driving ${o.stream.use}`,
      plain: `${S.plain} ${use.plain}`,
      tex: `${S.tex(pool.p3)}, \\qquad ${use.tex}`,
      code: `STREAM_MODELS.${o.stream.model}.f = ${S.f.toString()};`,
    });
  }
  return out;
}

/** The same rules as plain text lines (tests). */
export function formulas(pool, o) {
  return explain(pool, o).map((s) => `${s.title}: ${s.tex}`);
}
