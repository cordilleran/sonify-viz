/**
 * Page wiring for the Sound Channel Brewer: matrix, transport, legends, strips.
 * State lives in `S`; every change calls `update()`, which re-renders the loop and redraws.
 */
import { DEFAULT_SLOTS, benchOf, UNAVAILABLE, LAYOUTS, LAYOUT_INFO, byId, levels, pairInfo, pairKey, clampLevels, maxLevelsOf, FROM_OUR_PIECES,
  VOICES, DEFAULT_VOICE, OCTAVES, SPANS, PITCH_DEFAULTS, SCALES, SCALE_IDS, ROOTS, NOTE_NAMES } from './channels.js';
import { rng, poolFor, MAX_SEED, eventsFor, DEFAULT_SEED, MODELS, MODEL_IDS, STREAM_MODELS, STREAM_IDS, STREAM_USES, streamAt, explain, slotCount } from './pool.js';
import { TRANSFORMS, TRANSFORM_LABELS, TIME_MODES, KIND_DEFAULTS, STEP_WORD, PRESETS, defaultSource, laneItems, explainLane, binner, flagMask,
  hasZeros, hasNegatives, logAllowed, maxStart, stepLabel, midiOf, pitchName, noteValue, dynamicOf } from './series.js';
import { mapEvents, crowding, levelNotes, bindingJSON, pairFromJSON, TRANSITION_RANGE, TRANSITION_DEFAULT } from './map.js';
import { DRONE_MODES, DRONE_DEFAULTS, DRONE_LEVEL_RANGE, BREATHS, droneSpec, explainDrone } from './drone.js';
import { DRUMS, DRUM_CHANNELS, DRUM_DEFAULTS, DRUM_LEVEL_RANGE, DRUM_STEPS, drumById, drumHits, explainDrum } from './drum.js';
import { render } from './dsp.js';
import { spectrogram, drawData, drawScore, drawWave, drawSpec, timeTicks, FMIN, FMAX } from './viz.js';

const LOOP = 4;
const MASTER_TRIM = 0.8; // headroom: the rendered loop peaks at −6 dBFS and a limiter sits after this gain
const DUCK_BACK = 0.35; // seconds for a dipped loop to come back after a legend audition
const YOUNG_CUT = 0.25; // a loop still fading in when the next change comes leaves this fast, so a dragged slider cannot pile up loops
const MAX_LIVE = 8; // loops allowed to sound at once (playing or fading); older ones are faded out fast
const DUCK = 0.2; // loop gain while a legend button plays its level over it
const $ = (id) => document.getElementById(id);

const S = {
  c1: 'pitch', c2: 'brightness', n1: 5, n2: 5,
  layout: 'grid', count: 16, corr: 0, target: 'both',
  seed: DEFAULT_SEED, variation: 0, direction: 1, transition: TRANSITION_DEFAULT, solo: null, vol: 0.6,
  voice: DEFAULT_VOICE, ...PITCH_DEFAULTS,
  slots: [...DEFAULT_SLOTS], lastSwap: null,
  m1: 'uniform', m2: 'uniform', stream: { model: 'seasonal', use: 'off' },
  src1: null, src2: null, time: 'fit', twin: false, // real series on V1 and V2 (Slice A, 11-16)
  drum: { ...DRUM_DEFAULTS },
  drone: { ...DRONE_DEFAULTS },
  show: { data: true, score: true, wave: true, spec: true },
};
let pool = poolFor(S.seed, S.variation, S.direction);
const rebuildPool = () => { pool = poolFor(S.seed, S.variation, S.direction); };
let cur = null; // { notes, buf, spec }

/* ---------- audio ---------- */
/*
 * Every source that is playing or fading sits in `live`, and all of them pass through one gate, so Stop silences
 * all of them, not only the newest (DK57: in Firefox on Android, Stop left a crossfaded loop playing).
 */
const live = new Set();
let gate = null, gateClosed = false;
let ctx = null, master = null, loopSrc = null, loopGain = null, startAt = 0, playing = false, oneShot = null, rafId = 0;

const dbLabel = (v) => `${v > 0 ? '+' : ''}${v} dB`.replace('-', '−');
function ensureCtx() {
  if (ctx) return ctx;
  ctx = new (window.AudioContext || window.webkitAudioContext)();
  const lim = ctx.createDynamicsCompressor(); // safety limiter after the rendered −6 dBFS cap
  lim.threshold.value = -3; lim.knee.value = 0; lim.ratio.value = 20; lim.attack.value = 0.002; lim.release.value = 0.12;
  master = ctx.createGain();
  master.gain.value = S.vol * MASTER_TRIM;
  master.connect(lim).connect(ctx.destination);
  gate = ctx.createGain();
  gate.connect(master);
  return ctx;
}
const sr = () => (ctx ? ctx.sampleRate : 48000);

function toAudioBuffer(b) {
  const ab = ctx.createBuffer(2, b.L.length, b.sr);
  ab.copyToChannel(b.L, 0); ab.copyToChannel(b.R, 1);
  return ab;
}

function openGate() {
  if (!gateClosed) return;
  // A fresh gate: sources still dying behind the closed one stay silent even if Play comes within 50 ms of Stop.
  gate = ctx.createGain();
  gate.connect(master);
  gateClosed = false;
}
/** Track a source until it ends, then let it go. */
function track(src, g) {
  const e = { src, g };
  live.add(e);
  src.addEventListener('ended', () => { live.delete(e); try { src.disconnect(); g.disconnect(); } catch { /* already gone */ } });
  return e;
}
/** For the browser checks only: how many sources sound, whether the gate is shut, the context state. */
window.__scbAudio = () => ({ live: live.size, gateClosed, state: ctx ? ctx.state : 'none', playing });
function startLoop() {
  ensureCtx();
  if (ctx.state === 'suspended') ctx.resume();
  openGate();
  stopOneShot();
  if (cur.buf.sr !== ctx.sampleRate) { renderLoop(); draw(); } // the strips must show what plays
  const now = ctx.currentTime;
  const offset = playing ? (now - startAt) % LOOP : 0;
  const src = ctx.createBufferSource();
  src.buffer = toAudioBuffer(cur.buf);
  src.loop = true;
  const g = ctx.createGain();
  // A change while playing crossfades (equal power) from the old loop at the same point in the loop, over the transition length.
  const fade = playing ? S.transition : 0.03;
  g.gain.value = 0;
  curveGain(g, 0, 1, fade);
  src.connect(g).connect(gate);
  src.start(now, offset);
  if (loopSrc) {
    const p = plans.get(loopGain), young = p && p.rising && now < p.t1 - 0.01;
    fadeOut(loopSrc, loopGain, young ? Math.min(fade, YOUNG_CUT) : fade);
  }
  track(src, g);
  if (live.size > MAX_LIVE) {
    for (const e of live) { if (live.size <= MAX_LIVE || e.src === src) break; fadeOut(e.src, e.g, 0.05); live.delete(e); }
  }
  loopSrc = src; loopGain = g; startAt = now - offset; playing = true;
  $('play').textContent = 'Playing';
  if (!rafId) rafId = requestAnimationFrame(tick);
}

/*
 * Each gain's last plan (start, end, shape), so a new ramp starts from where the gain is now.
 * Reading AudioParam.value mid-ramp is not reliable in every browser, so the page keeps its own record.
 */
const plans = new WeakMap();
function gainNow(g, t) {
  const p = plans.get(g);
  if (!p) return g.gain.value;
  return p.at(Math.min(1, Math.max(0, (t - p.t0) / Math.max(1e-6, p.t1 - p.t0))));
}
/** A linear ramp from wherever the gain is now to `target`. */
function rampGain(g, target, dur) {
  const t = ctx.currentTime, v = gainNow(g, t);
  g.gain.cancelScheduledValues(t);
  g.gain.setValueAtTime(v, t);
  g.gain.linearRampToValueAtTime(target, t + dur);
  plans.set(g, { t0: t, t1: t + dur, at: (f) => v + (target - v) * f });
}
/**
 * An equal-power fade (quarter sine), so two different loops crossfading keep their summed power.
 * Built from short linear ramps, not setValueCurveAtTime: Firefox refuses any new event while a curve runs
 * ("Can't add events during a curve event"), which broke Stop mid-fade (DK57). A ramp ends at its own time,
 * so cancelScheduledValues removes it cleanly in every browser.
 */
function curveGain(g, from, to, dur) {
  const t = ctx.currentTime, n = Math.max(4, Math.min(48, Math.ceil(dur / 0.05)));
  const at = (f) => (to > from ? from + (to - from) * Math.sin((Math.PI / 2) * f) : to + (from - to) * Math.cos((Math.PI / 2) * f));
  g.gain.cancelScheduledValues(t);
  g.gain.setValueAtTime(from, t);
  for (let i = 1; i <= n; i++) g.gain.linearRampToValueAtTime(at(i / n), t + (dur * i) / n);
  plans.set(g, { t0: t, t1: t + dur, at, rising: to > from });
}

function fadeOut(src, g, dur = 0.03) {
  if (!src) return;
  curveGain(g, gainNow(g, ctx.currentTime), 0, dur);
  try { src.stop(ctx.currentTime + dur + 0.02); } catch { /* already stopped */ }
}

/** Stop everything: close the gate in 30 ms, stop every live source, and suspend the context shortly after as a backstop. */
function stopAll() {
  if (ctx) {
    const t = ctx.currentTime;
    gate.gain.cancelScheduledValues(t);
    gate.gain.setValueAtTime(gateClosed ? 0 : 1, t);
    gate.gain.linearRampToValueAtTime(0, t + 0.03);
    gateClosed = true;
    for (const e of live) { try { e.src.stop(t + 0.05); } catch { /* already stopped */ } }
    oneShot = null;
    const c = ctx;
    setTimeout(() => { if (!playing && !oneShot && c.state === 'running') c.suspend().catch(() => {}); }, 150);
  }
  loopSrc = null; loopGain = null; playing = false;
  $('play').textContent = 'Play';
  document.querySelectorAll('.ph').forEach((p) => { p.style.opacity = 0; });
}

function stopOneShot() { if (oneShot) { fadeOut(oneShot.src, oneShot.g); oneShot = null; } }

/** A legend button: play three notes of one level. A playing loop dips under them and comes back. */
function auditionLevel(which, k) {
  ensureCtx();
  if (ctx.state === 'suspended') ctx.resume();
  openGate();
  stopOneShot();
  if (playing && loopGain) rampGain(loopGain, DUCK, 0.06);
  // Ceiling 1: a lone note must not be turned down, or the loudness levels would sound alike.
  const b = render(levelNotes(S, which, k), { sr: ctx.sampleRate, loopSec: 2, seed: S.seed, ceiling: 1 });
  const src = ctx.createBufferSource();
  src.buffer = toAudioBuffer(b);
  const g = ctx.createGain();
  src.connect(g).connect(gate);
  src.start();
  oneShot = track(src, g);
  src.onended = () => {
    if (oneShot && oneShot.src !== src) return; // a newer audition took over and keeps the dip
    oneShot = null;
    if (playing && loopGain) rampGain(loopGain, 1, DUCK_BACK);
  };
}

function tick() {
  if (!playing) { rafId = 0; return; }
  const f = ((ctx.currentTime - startAt) % LOOP) / LOOP;
  document.querySelectorAll('.ph').forEach((p) => {
    p.style.opacity = 1;
    p.style.left = `calc(${(f * 100).toFixed(3)}% - 1px)`;
  });
  rafId = requestAnimationFrame(tick);
}

/* ---------- render and draw ---------- */
function setting() {
  const s = { ...S, n1: clampLevels(S.c1, S.n1, S), n2: clampLevels(S.c2, S.n2, S), loopSec: LOOP };
  const m = slotCount(s);
  for (const w of [1, 2]) {
    const src = S[`src${w}`], ser = src && seriesOf(src.series);
    if (!ser) continue;
    if (S.twin) { s[`m${w}`] = ser.twin; continue; } // the synthetic twin: the nearest seeded model plays instead
    const o = { mode: S.time, m, n: s[`n${w}`] };
    s[`real${w}`] = laneItems(ser, src, o);
    s[`realInfo${w}`] = explainLane(ser, src, o, w);
  }
  return s;
}

/* ---------- real series (Slice A of the 261116 spec) ---------- */
let PACK = null, packNote = '';
const seriesOf = (id) => PACK?.series.find((x) => x.id === id) ?? null;
const seriesIds = () => (PACK ? PACK.series.map((x) => x.id) : null);
const pairOpts = () => ({ ...S, seriesIds: seriesIds() });
/** Fetch series.json from the page's own folder; without it the page plays synthetic data only. */
async function loadPack() {
  try {
    const ctl = new AbortController(), to = setTimeout(() => ctl.abort(), 6000);
    const r = await fetch('./series.json', { signal: ctl.signal });
    clearTimeout(to);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const j = await r.json();
    if (j.schema !== 'sound-channel-brewer/series@1' || !Array.isArray(j.series)) throw new Error('not a series pack');
    PACK = j;
  } catch {
    PACK = null;
    packNote = 'The real data series could not be loaded here, so only the synthetic models are offered.';
  }
}
/** The lane whose period the time bar follows: V1 if it plays a real series, else V2 (0: none). */
const leadLane = () => (S.src1 && seriesOf(S.src1.series) ? 1 : S.src2 && seriesOf(S.src2.series) ? 2 : 0);
const realLane = (w) => !!(S[`src${w}`] && seriesOf(S[`src${w}`].series) && !S.twin);
const fmtRaw = (v) => (v == null ? '–' : Math.abs(v) >= 100 ? String(Math.round(v)) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2)).replace('-', '−');
const vName = (w) => (S[`src${w}`] && seriesOf(S[`src${w}`].series) ? `V${w} (${seriesOf(S[`src${w}`].series).short}${S.twin ? ', twin' : ''})` : `V${w}`);

/** Move the Slice start. The lead lane takes v; the other real lane takes the same step if it shares the calendar, else the same share of its own period. */
function setStart(v) {
  const L = leadLane();
  if (!L) return;
  const m = slotCount(S), lead = S[`src${L}`], ls = seriesOf(lead.series);
  const lmax = maxStart(ls, m), sv = Math.max(0, Math.min(lmax, Math.round(v)));
  S[`src${L}`] = { ...lead, start: sv };
  const O = 3 - L, os = S[`src${O}`] && seriesOf(S[`src${O}`].series);
  if (os) {
    const omax = maxStart(os, m), same = os.step === ls.step && os.start === ls.start;
    S[`src${O}`] = { ...S[`src${O}`], start: same ? Math.min(omax, sv) : Math.round(lmax ? (sv / lmax) * omax : 0) };
  }
}

const srcVal = (w) => (S[`src${w}`] && seriesOf(S[`src${w}`].series) ? `s:${S[`src${w}`].series}` : S[`m${w}`]);
/** The V1 or V2 source menu: real series grouped by timescale, then the synthetic models. */
function fillSource(w) {
  const el = $(`m${w}`), escA = (x) => x.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
  const real = PACK ? PACK.scales.map((sc) => {
    const list = PACK.series.filter((x) => x.scale === sc.id);
    return list.length ? `<optgroup label="Real data · ${escA(sc.label)}">${list.map((x) => `<option value="s:${escA(x.id)}">${escA(x.short)}</option>`).join('')}</optgroup>` : '';
  }).join('') : '';
  el.innerHTML = `${real}<optgroup label="Synthetic models">${MODEL_IDS.map((m) => `<option value="${m}">${MODELS[m].label}</option>`).join('')}</optgroup>`;
  el.value = srcVal(w);
}
function sourcePick(w) {
  const el = $(`m${w}`);
  fillSource(w);
  el.addEventListener('change', () => {
    const v = el.value;
    if (v.startsWith('s:')) {
      // A lane that turns real joins the other real lane's window (the same step on a shared calendar, else the same share of its period).
      const ser = seriesOf(v.slice(2)), O = 3 - w, osrc = S[`src${O}`], os = osrc && seriesOf(osrc.series), m = slotCount(S);
      let start = 0;
      if (os) { const same = os.step === ser.step && os.start === ser.start, omax = maxStart(os, m), mx = maxStart(ser, m); start = same ? Math.min(mx, osrc.start ?? 0) : Math.round(omax ? ((osrc.start ?? 0) / omax) * mx : 0); }
      S[`src${w}`] = { ...defaultSource(ser), start };
    }
    else { S[`src${w}`] = null; S[`m${w}`] = v; }
    S.solo = null;
    update(); if (playing) startLoop();
  });
}

/** The shape row under a real source: transform pills, zero = rest, signed, flip, and the source line. */
function shapeUI(w) {
  const box = $(`shape${w}`), lab = $(`shape${w}-l`);
  const src = S[`src${w}`], ser = src && seriesOf(src.series);
  box.hidden = lab.hidden = !ser;
  if (!ser) { box.innerHTML = ''; return; }
  const ae = document.activeElement, keep = box.contains(ae) ? (ae.dataset.t ? `[data-t="${ae.dataset.t}"]` : `[data-k="${ae.dataset.k}"]`) : null;
  const n = clampLevels(S[`c${w}`], S[`n${w}`], S), b = binner(ser, src, n);
  box.innerHTML = `<div class="seg" role="group" aria-label="V${w} transform">${TRANSFORMS.map((t) => `<button type="button" data-t="${t}" aria-pressed="${b.transform === t}"${t === 'log' && !logAllowed(ser) ? ' disabled title="Log needs values of zero or more"' : ''}>${TRANSFORM_LABELS[t]}</button>`).join('')}</div>`
    + (hasZeros(ser) ? `<label title="Zero values are silent"><input type="checkbox" data-k="zeroRest"${src.zeroRest ? ' checked' : ''}> Zero = rest</label>` : '')
    + (hasNegatives(ser) ? `<label title="Cut the levels the same width either side of zero (Lin only)"><input type="checkbox" data-k="signed"${src.signed ? ' checked' : ''}${b.transform !== 'lin' ? ' disabled' : ''}> Signed</label>` : '')
    + `<label title="Bigger values take lower levels"><input type="checkbox" data-k="flip"${src.flip ? ' checked' : ''}> Flip</label><span class="hint src-line"></span>`;
  box.querySelector('.src-line').textContent = `${ser.title}, ${ser.place}, ${ser.units}. ${(KIND_DEFAULTS[ser.kind] ?? KIND_DEFAULTS.slow).why} Source: ${ser.source}. ${ser.licence}.`;
  box.querySelectorAll('[data-t]').forEach((btn) => btn.addEventListener('click', () => { S[`src${w}`] = { ...S[`src${w}`], transform: btn.dataset.t }; update(); if (playing) startLoop(); }));
  box.querySelectorAll('input[data-k]').forEach((inp) => inp.addEventListener('change', () => { S[`src${w}`] = { ...S[`src${w}`], [inp.dataset.k]: inp.checked }; update(); if (playing) startLoop(); }));
  if (keep) box.querySelector(keep)?.focus();
}

/** The time bar above the strips: Fit or Slice, the start, bookmarks, the synthetic twin. Hidden with no real lane. */
function timeUI() {
  const L = leadLane();
  $('timebar').hidden = !L;
  if (!L) return;
  refreshTmode();
  const src = S[`src${L}`], ser = seriesOf(src.series), m = slotCount(S), N = ser.values.length, word = STEP_WORD[ser.step];
  const slice = S.time === 'slice', mx = maxStart(ser, m), s0 = Math.min(src.start ?? 0, mx);
  const st = $('tstart');
  st.max = String(mx); st.value = String(s0); st.disabled = !slice;
  st.setAttribute('aria-valuetext', stepLabel(ser, s0));
  $('tstart-o').textContent = slice ? stepLabel(ser, s0) : '';
  const marks = $('tmarks'), ae = document.activeElement, keep = marks.contains(ae) ? ae.dataset.b : null;
  marks.innerHTML = '';
  for (const bm of ser.bookmarks ?? []) {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'btn sm'; b.dataset.b = bm.label; b.textContent = bm.label;
    b.setAttribute('aria-pressed', String(slice && s0 === Math.min(bm.start, mx)));
    b.title = `Slice ${m} ${word}s from ${stepLabel(ser, Math.min(bm.start, mx))}`;
    b.addEventListener('click', () => { S.time = 'slice'; setStart(bm.start); update(); if (playing) startLoop(); });
    marks.append(b);
  }
  if (keep) marks.querySelector(`[data-b="${keep}"]`)?.focus();
  $('twin').checked = S.twin;
  $('time-o').textContent = timeText();
}
/** The time summary in words, from state alone (the time bar and the score both use it). */
function timeText() {
  const L = leadLane();
  if (!L) return '';
  const src = S[`src${L}`], ser = seriesOf(src.series), m = slotCount(S), N = ser.values.length, word = STEP_WORD[ser.step];
  const slice = S.time === 'slice', s0 = Math.min(src.start ?? 0, maxStart(ser, m));
  const O = 3 - L, os = S[`src${O}`] && seriesOf(S[`src${O}`].series);
  const own = os && !(os.step === ser.step && os.start === ser.start) ? ` V${O} (${os.short}) runs on its own calendar, ${slice ? `from ${stepLabel(os, Math.min(S[`src${O}`].start, maxStart(os, m)))}` : `${stepLabel(os, 0)} to ${stepLabel(os, os.values.length - 1)}`}.` : '';
  return (slice
    ? `Slice: ${Math.min(m, N)} ${word}s in a row, ${stepLabel(ser, s0)} to ${stepLabel(ser, Math.min(N - 1, s0 + m - 1))}, one per event. Move the start or pick a bookmark.`
    : `Fit: the whole period, ${stepLabel(ser, 0)} to ${stepLabel(ser, N - 1)} (${N} ${word}s), as ${m} groups of about ${(N / m).toFixed(1)}.`) + own
    + (S.twin ? ' Synthetic twin is on: each real lane plays its nearest seeded model, so you can hear what the real data add.' : '');
}

/** The data strip under real lanes: the series as a faint line, bin edges dotted, gaps hatched, ice shaded. */
function drawReal(c, w, h, s, col) {
  const half = h / 2, pad = 3, m = slotCount(s);
  for (const k of [1, 2]) {
    if (!realLane(k)) continue;
    const src = S[`src${k}`], ser = seriesOf(src.series), n = s[`n${k}`], b = binner(ser, src, n);
    const top = k === 1 ? 0 : half, base = top + half - pad, span = half - 2 * pad, colr = k === 1 ? col.v1 : col.v2;
    const N = ser.values.length, slice = S.time === 'slice';
    const i0 = slice ? Math.min(src.start ?? 0, maxStart(ser, m)) : 0, cnt = slice ? Math.min(m, N) : N;
    const x0 = (i) => ((i - i0) / cnt) * w, bw = w / cnt;
    const mask = flagMask(ser);
    c.save();
    for (let i = i0; i < i0 + cnt; i++) {
      if (mask[i]) { c.globalAlpha = 0.16; c.fillStyle = col.muted; c.fillRect(x0(i), top, bw + 0.5, half); }
      if (ser.values[i] == null) {
        c.globalAlpha = 0.5; c.strokeStyle = col.muted; c.lineWidth = 1; c.beginPath();
        for (let x = x0(i) - half; x < x0(i) + bw; x += 4) { c.moveTo(Math.max(x0(i), x), top + Math.max(0, x0(i) - x)); c.lineTo(Math.min(x0(i) + bw, x + half), top + half - Math.max(0, x + half - x0(i) - bw)); }
        c.stroke();
      }
    }
    c.globalAlpha = 0.55; c.strokeStyle = col.muted; c.lineWidth = 1; c.setLineDash([2, 3]);
    for (const e of b.edges) { const y = Math.round(base - e * span) + 0.5; c.beginPath(); c.moveTo(0, y); c.lineTo(w, y); c.stroke(); }
    c.setLineDash([]); c.globalAlpha = 0.5; c.strokeStyle = colr; c.lineWidth = 1.25; c.beginPath();
    let pen = false;
    for (let i = i0; i < i0 + cnt; i++) {
      const v = b.norm(ser.values[i]);
      if (v == null) { pen = false; continue; }
      const y = base - (src.flip ? 1 - v : v) * span, x = x0(i) + bw / 2;
      if (pen) c.lineTo(x, y); else { c.moveTo(x, y); pen = true; }
    }
    c.stroke();
    const lab = `${ser.short} · ${TRANSFORM_LABELS[b.transform]}${slice ? ' · slice' : ' · fit'}`;
    c.globalAlpha = 1; c.font = '11px system-ui'; c.textAlign = 'right'; c.textBaseline = 'bottom';
    const lw = c.measureText(lab).width;
    c.fillStyle = col.bg; c.fillRect(w - lw - 8, top + half - 15, lw + 8, 14); // a ground under the label, so the line does not run through it
    c.fillStyle = colr; c.fillText(lab, w - 4, top + half - 2);
    c.restore();
  }
}

/** The loop as a score in the notation primer's terms (DK73): one tab-separated line per note. */
function scoreText() {
  const s = setting(), bpm = (60 * 4) / LOOP; // one loop = one bar of 4/4
  const lanes = [1, 2].map((w) => ({ w, ch: byId[s[`c${w}`]], n: s[`n${w}`], real: realLane(w), ser: S[`src${w}`] && seriesOf(S[`src${w}`].series), src: S[`src${w}`], items: s[`real${w}`] }));
  const desc = (L) => (L.real
    ? `${L.ser.title} (${L.ser.units}; ${TRANSFORM_LABELS[binner(L.ser, L.src, L.n).transform]}${L.src.zeroRest ? ', zero = rest' : ''}${L.src.signed ? ', signed' : ''}${L.src.flip ? ', flipped' : ''}; ${S.time === 'slice' ? 'Slice' : 'Fit'}). ${L.ser.source}. ${L.ser.licence}.`
    : `seeded model "${MODELS[s[`m${L.w}`]].label}"${L.ser ? ` (synthetic twin of ${L.ser.title})` : ''}, seed ${S.seed}`);
  const dated = lanes.find((L) => L.real);
  const head = [
    '# Sound Channel Brewer: the loop as a score',
    `key: ${NOTE_NAMES[S.root]} ${SCALES[S.scale].label.toLowerCase()} | tempo: ${bpm} bpm, 4/4, one ${LOOP}-second loop = one bar | layout: ${s.layout} | voice: ${S.voice} | ${cur.notes.length} notes`,
    ...lanes.map((L) => `V${L.w} -> ${L.ch.label.toLowerCase()}, ${L.n} levels <- ${desc(L)}`),
    dated ? `time: ${timeText()}` : 'time: seeded data, no calendar',
    '',
    ['beat', 'V1 date', 'V1 raw', 'V1 bin', 'V2 date', 'V2 raw', 'V2 bin', 'MIDI', 'pitch', 'note value', 'dynamic', 'articulation', 'flag'].join('\t'),
  ];
  const raw = (L, n) => (L.real && n.k != null ? fmtRaw(L.items[n.k].raw) : 'seeded');
  const date = (L, n) => (L.real && n.k != null ? L.items[n.k].label : '');
  const rows = [...cur.notes].sort((a, b) => a.t - b.t).map((n) => {
    const midi = midiOf(n.freq);
    return [(1 + (n.t * bpm) / 60).toFixed(2), date(lanes[0], n), raw(lanes[0], n), n.v1 + 1, date(lanes[1], n), raw(lanes[1], n), n.v2 + 1,
      midi, pitchName(midi), n.sustained ? 'held' : noteValue(n.dur, bpm), dynamicOf(n.gainDb), n.artic, n.flag ? 'ice' : ''].join('\t');
  });
  return [...head, ...rows].join('\n');
}

/** The three presets (DK72), each with one "Try this" that flips one setting. */
let activePreset = null;
function applyChanges(ch, note) {
  const st = { ...S, ...ch };
  return applyPair(bindingJSON({ ...st, n1: clampLevels(st.c1, st.n1, st), n2: clampLevels(st.c2, st.n2, st), loopSec: LOOP }), { play: true, note });
}
function applyPreset(p) {
  const z = p.set, mk = (o) => ({ ...defaultSource(seriesOf(o.series)), ...o });
  const src1 = mk(z.src1), src2 = mk(z.src2);
  if (z.start) {
    const bm = [src1, src2].map((x) => seriesOf(x.series).bookmarks.find((b) => b.label === z.start)).find(Boolean);
    if (bm) { src1.start = bm.start; src2.start = bm.start; }
  }
  const ok = applyChanges({ c1: z.c1, c2: z.c2, n1: z.n1, n2: z.n2, layout: z.layout, count: z.count, time: z.mode, voice: z.voice ?? S.voice, octave: z.octave ?? S.octave, twin: false, src1, src2, solo: null, corr: 0, stream: { ...S.stream, use: 'off' } }, `Preset: ${p.title}.`);
  if (ok) { activePreset = p.id; $('preset-o').textContent = p.sketch; } else $('preset-o').textContent = $('load-o').textContent;
  return ok;
}
function presets() {
  const box = $('presets');
  if (!PACK) { box.innerHTML = '<p class="hint"></p>'; box.querySelector('p').textContent = packNote; return; }
  for (const p of PRESETS) {
    const d = document.createElement('div');
    d.className = 'preset';
    d.innerHTML = '<button type="button" class="go"><b></b><span></span></button><button type="button" class="btn sm try"></button>';
    d.querySelector('b').textContent = p.title;
    d.querySelector('span').textContent = p.sketch;
    d.querySelector('.try').textContent = p.tryLabel;
    const missing = [p.set.src1, p.set.src2].filter((x) => !seriesOf(x.series)).map((x) => x.series);
    if (missing.length) {
      d.querySelectorAll('button').forEach((b) => { b.disabled = true; b.title = `Needs series not in the pack: ${missing.join(', ')}`; });
    }
    d.querySelector('.go').addEventListener('click', () => applyPreset(p));
    d.querySelector('.try').addEventListener('click', () => {
      if (activePreset !== p.id && !applyPreset(p)) return;
      if (applyChanges(p.try(S), `${p.tryLabel}.`)) $('preset-o').textContent = p.teach;
      else $('preset-o').textContent = $('load-o').textContent;
    });
    box.append(d);
  }
}

function renderLoop() {
  const s = setting();
  const ev = eventsFor(pool, s);
  const notes = mapEvents(ev, s);
  const hits = drumHits(pool, s.drum, LOOP);
  const buf = render(notes, { sr: sr(), loopSec: LOOP, seed: S.seed, hits, drone: droneSpec(s) });
  const mono = new Float32Array(buf.L.length);
  for (let i = 0; i < mono.length; i++) mono[i] = 0.5 * (buf.L[i] + buf.R[i]);
  cur = { events: ev, notes, hits, buf, spec: spectrogram(mono, buf.sr, { nfft: 1024, hop: 384, rows: 96 }) };
}

function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
function hexRgb(h) {
  const m = h.replace('#', '');
  const v = m.length === 3 ? m.split('').map((c) => c + c).join('') : m;
  return [0, 2, 4].map((i) => parseInt(v.slice(i, i + 2), 16));
}
function ramp(n) {
  const a = hexRgb(css('--ramp-lo')), b = hexRgb(css('--ramp-hi'));
  return Array.from({ length: n }, (_, k) => {
    const t = n === 1 ? 0.5 : k / (n - 1);
    return `rgb(${a.map((x, i) => Math.round(x + t * (b[i] - x))).join(',')})`;
  });
}
function colors() {
  return { fg: css('--fg'), muted: css('--muted'), grid: css('--grid'), accent: css('--accent'), v1: css('--v1'), v2: css('--v2'), v3: css('--v3'), v4: css('--v4'), bg: css('--strip') };
}

function fitCanvas(cv) {
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  // Setting cv.height rewrites the height attribute, so keep the CSS height from the first read.
  if (!cv.dataset.h) cv.dataset.h = cv.getAttribute('height');
  const w = cv.clientWidth, h = Number(cv.dataset.h);
  if (cv.width !== Math.round(w * dpr)) { cv.width = Math.round(w * dpr); }
  cv.style.height = `${h}px`;
  if (cv.height !== Math.round(h * dpr)) cv.height = Math.round(h * dpr);
  const c = cv.getContext('2d');
  c.setTransform(dpr, 0, 0, dpr, 0, 0);
  c.clearRect(0, 0, w, h);
  return { c, w, h };
}

function draw() {
  const s = setting();
  const col = colors();
  const evs = cur.notes.map((n) => ({ onset: n.t, dur: n.dur, v1: n.v1, v2: n.v2, dim: n.dim }));
  const jobs = {
    data: (c, w, h) => { drawData(c, w, h, evs, s.n1, s.n2, LOOP, col); drawReal(c, w, h, s, col); drawStream(c, w, h, s, col); },
    score: (c, w, h) => { drawScore(c, w, h, evs, s.n1, s.n2, LOOP, col, ramp(s.n2)); drawDrum(c, w, h, col); },
    wave: (c, w, h) => drawWave(c, w, h, cur.buf, col),
    spec: (c, w, h) => drawSpec(c, w, h, cur.spec, col),
  };
  for (const [k, fn] of Object.entries(jobs)) {
    const strip = document.querySelector(`.strip[data-k="${k}"]`);
    strip.hidden = !S.show[k];
    if (!S.show[k]) continue;
    const { c, w, h } = fitCanvas($(`cv-${k}`));
    fn(c, w, h);
  }
  $('axis').innerHTML = '';
  for (const t of timeTicks(LOOP)) {
    const sp = document.createElement('span');
    sp.style.left = `${(t / LOOP) * 100}%`;
    sp.textContent = `${t} s`;
    $('axis').append(sp);
  }
  const a = byId[s.c1], b = byId[s.c2];
  $('strip-sum').textContent = `${cur.notes.length} events in ${LOOP} s. ${vName(1)} on ${a.label.toLowerCase()}, ${vName(2)} on ${b.label.toLowerCase()}${streamOn(s) ? `, V3 on ${s.stream.use}` : ''}${droneSpec(s) ? `, a drone on ${droneSpec(s).name}` : ''}${drumOn() ? `, ${cur.hits.length} drum hits with V4 on ${drumById[s.drum.channel].label.toLowerCase()}` : ''}. Hover a strip for values.` +
    (cur.buf.scaled < 1 ? ` The loop was turned down ${(-20 * Math.log10(cur.buf.scaled)).toFixed(1)} dB to stay under the −6 dBFS cap.` : '');
}

const streamOn = (s) => s.layout !== 'lines' && s.stream.use !== 'off';
const drumOn = () => S.drum.voice !== 'off';

/** Drum hits as ticks along the top of the score, taller for a higher V4 level. */
function drawDrum(c, w, h, col) {
  if (!drumOn()) return;
  c.save();
  c.fillStyle = col.v4;
  for (const hit of cur.hits) c.fillRect(Math.round((hit.t / LOOP) * w), 0, 3, 4 + hit.level * 4);
  c.font = '11px system-ui'; c.textAlign = 'right'; c.textBaseline = 'top';
  const lab = `drum · V4 ${drumById[S.drum.channel].label.toLowerCase()}`, lw = c.measureText(lab).width;
  c.fillStyle = col.bg; c.fillRect(w - lw - 8, 0, lw + 8, 15);
  c.fillStyle = col.v4; c.fillText(lab, w - 4, 2);
  c.restore();
}

/** V3 as a line across the data strip, when it drives density or pace. */
function drawStream(c, w, h, s, col) {
  if (!streamOn(s)) return;
  c.save();
  c.strokeStyle = col.v3; c.lineWidth = 1.5; c.setLineDash([4, 3]);
  c.beginPath();
  for (let x = 0; x <= w; x += 2) { const y = h - 3 - streamAt(pool, s.stream.model, x / w) * (h - 6); if (x) c.lineTo(x, y); else c.moveTo(x, y); }
  c.stroke();
  c.fillStyle = col.v3; c.font = '11px system-ui'; c.textAlign = 'right'; c.textBaseline = 'top';
  c.fillText(`V3 · ${s.stream.use}`, w - 4, 2);
  c.restore();
}

/* ---------- strip tooltips ---------- */
const dbfs = (v) => (v < 1e-5 ? '−∞' : (20 * Math.log10(v)).toFixed(1).replace('-', '−'));
/** Notes sounding at time t (wrapped), else the nearest onset. */
function notesAt(t) {
  const on = cur.notes.filter((n) => { const d = (t - n.t + LOOP) % LOOP; return d < Math.max(n.dur, 0.04); });
  if (on.length) return on;
  let best = null, bd = Infinity;
  for (const n of cur.notes) { const d = Math.min(Math.abs(n.t - t), LOOP - Math.abs(n.t - t)); if (d < bd) { bd = d; best = n; } }
  return best ? [best] : [];
}
function noteLine(n, s) {
  const a = byId[s.c1], b = byId[s.c2];
  const lv1 = levels(s.c1, s.n1, s), lv2 = levels(s.c2, s.n2, s);
  return `<b>${n.t.toFixed(2)} s</b>, ${n.sustained ? 'held' : `${Math.round(n.dur * 1000)} ms`}${n.dim ? ' (soloed out)' : ''}<br>` +
    `V1 level ${n.v1 + 1}/${s.n1}: ${a.label.toLowerCase()} ${a.format(lv1[n.v1])}<br>V2 level ${n.v2 + 1}/${s.n2}: ${b.label.toLowerCase()} ${b.format(lv2[n.v2])}`;
}
function stripTip(k, e) {
  const cv = $(`cv-${k}`), rc = cv.getBoundingClientRect();
  const fx = Math.min(1, Math.max(0, (e.clientX - rc.left) / rc.width)), fy = Math.min(1, Math.max(0, (e.clientY - rc.top) / rc.height));
  const t = fx * LOOP, s = setting();
  let html = `<b>${t.toFixed(2)} s</b>`;
  if (k === 'data' || k === 'score') {
    const ns = notesAt(t).slice(0, 3);
    html = ns.map((n) => noteLine(n, s)).join('<hr>') || html;
    if (k === 'score' && drumOn()) {
      const hit = cur.hits.find((x) => Math.abs(x.t - t) < LOOP / DRUM_STEPS / 2);
      const C = drumById[S.drum.channel];
      if (hit) html += `<hr>Drum step ${hit.step + 1}: V4 = ${hit.x4.toFixed(2)}, level ${hit.level + 1} of 4, ${C.label.toLowerCase()} ${C.format(C.values[hit.level])}`;
    }
    if (k === 'data' && (realLane(1) || realLane(2))) {
      const kk = Math.min(slotCount(s) - 1, Math.floor(fx * slotCount(s)));
      for (const w2 of [1, 2]) {
        const it = realLane(w2) && s[`real${w2}`][kk];
        if (!it) continue;
        const ser = seriesOf(S[`src${w2}`].series), agg = it.i0 !== it.i1 ? `${(KIND_DEFAULTS[ser.kind] ?? KIND_DEFAULTS.slow).agg === 'max' ? 'largest' : 'median'} ` : '';
        html += `<hr>V${w2} ${ser.short}, ${it.label}: ${it.raw == null ? 'no data, a rest' : `${agg}${fmtRaw(it.raw)} ${ser.units}${it.level == null ? ', a rest' : `, level ${it.level + 1} of ${s[`n${w2}`]}`}`}${it.flag ? ', ice-affected' : ''}`;
      }
    }
    if (k === 'data' && streamOn(s)) html += `<hr>V3 (${STREAM_MODELS[s.stream.model].label.toLowerCase()}, ${s.stream.use}) = ${streamAt(pool, s.stream.model, fx).toFixed(2)}`;
  } else if (k === 'wave') {
    const b = cur.buf, i0 = Math.round(t * b.sr), win = Math.round(0.005 * b.sr);
    let l = 0, r = 0;
    for (let i = i0 - win; i <= i0 + win; i++) { const j = (i + b.L.length) % b.L.length; l = Math.max(l, Math.abs(b.L[j])); r = Math.max(r, Math.abs(b.R[j])); }
    html += `<br>peak in ±5 ms: left ${dbfs(l)} dBFS, right ${dbfs(r)} dBFS`;
  } else if (k === 'spec') {
    const sp = cur.spec, c = Math.min(sp.cols - 1, Math.floor(fx * sp.cols)), row = Math.min(sp.rows - 1, Math.floor((1 - fy) * sp.rows));
    const f = FMIN * Math.pow(FMAX / FMIN, (row + 0.5) / sp.rows);
    const db = sp.data[c * sp.rows + row] * 80 - 80;
    html += `<br>${f >= 1000 ? `${(f / 1000).toFixed(2)} kHz` : `${Math.round(f)} Hz`}: ${db <= -79.5 ? 'below −80' : db.toFixed(0).replace('-', '−')} dB (full-scale sine = 0)`;
  }
  placeTip(html, e.clientX + 14, e.clientY + 14);
}
function placeTip(html, x, y) {
  const tip = $('tip');
  tip.innerHTML = html; tip.hidden = false;
  const tw = tip.offsetWidth, th = tip.offsetHeight;
  if (x + tw > window.innerWidth - 8) x = Math.max(8, x - tw - 28);
  if (y + th > window.innerHeight - 8) y = Math.max(8, y - th - 28);
  tip.style.left = `${x}px`; tip.style.top = `${y}px`;
}

/* ---------- matrix ---------- */
const cells = new Map(); // "r,c" -> button
/** The eight channels now in the matrix, in slot order. */
const CH = () => S.slots.map((id) => byId[id]);
let focusRC = [1, 0];
const pieceKeys = new Set(FROM_OUR_PIECES.map((p) => pairKey(p.a, p.b)));

function buildMatrix() {
  const m = $('matrix');
  m.innerHTML = '';
  cells.clear();
  for (let r = 1; r < CH().length; r++) {
    const rl = document.createElement('div');
    rl.className = 'rl'; rl.textContent = CH()[r].label;
    m.append(rl);
    for (let c = 0; c < CH().length - 1; c++) {
      if (c >= r) { m.append(document.createElement('div')); continue; }
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'cell'; b.tabIndex = -1;
      b.dataset.r = r; b.dataset.c = c;
      b.addEventListener('click', () => choose(r, c));
      b.addEventListener('mouseenter', (e) => showTip(r, c, e.currentTarget));
      b.addEventListener('mouseleave', hideTip);
      b.addEventListener('focus', (e) => { focusRC = [r, c]; describe(r, c); showTip(r, c, e.currentTarget); });
      b.addEventListener('blur', hideTip);
      cells.set(`${r},${c}`, b);
      m.append(b);
    }
  }
  m.append(document.createElement('div'));
  for (let c = 0; c < CH().length - 1; c++) {
    const cl = document.createElement('div');
    cl.className = 'cl'; cl.textContent = CH()[c].label;
    m.append(cl);
  }
}

/* ---------- bench: swap a channel into the matrix ---------- */
function benchUI() {
  const bench = benchOf(S.slots);
  $('bench').innerHTML = bench.map((id) => `<option value="${id}">${byId[id].label}</option>`).join('');
  const sl = $('slot'), keep = sl.value;
  sl.innerHTML = S.slots.map((id) => `<option value="${id}">${byId[id].label}</option>`).join('');
  sl.value = S.slots.includes(keep) ? keep : S.slots[S.slots.length - 2];
  $('bench-o').textContent = bench.length ? `On the bench: ${bench.map((id) => byId[id].label).join(', ')}.` : '';
  const b = $('swap-back');
  b.hidden = !S.lastSwap;
  if (S.lastSwap) b.textContent = `Swap back: ${byId[S.lastSwap.out].label} for ${byId[S.lastSwap.in].label}`;
}

/** Put a bench channel in place of a matrix channel. If the kept pair used it, the newcomer takes its place. */
function swapChannel(inId, outId) {
  const i = S.slots.indexOf(outId);
  if (i < 0 || S.slots.includes(inId)) return;
  S.slots[i] = inId;
  if (S.c1 === outId) S.c1 = inId;
  if (S.c2 === outId) S.c2 = inId;
  const un = UNAVAILABLE[S.layout];
  if (un[S.c1] || un[S.c2]) S.layout = 'grid';
  S.solo = null;
  S.lastSwap = { in: inId, out: outId };
  buildMatrix();
  focusRC = keptRC();
  benchUI();
  update(); describe(...focusRC);
  if (playing) startLoop();
}

function refreshMatrix() {
  const kept = pairKey(S.c1, S.c2);
  for (const [rc, b] of cells) {
    const [r, c] = rc.split(',').map(Number);
    const a = CH()[r].id, z = CH()[c].id;
    const info = pairInfo(a, z, S.layout);
    const k = pairKey(a, z);
    b.className = `cell ${info.status === 'free' ? '' : info.status}${k === kept ? ' kept' : ''}${pieceKeys.has(k) ? ' piece' : ''}`;
    b.textContent = info.status === 'linked' ? '↔' : '';
    b.setAttribute('aria-pressed', String(k === kept));
    b.setAttribute('aria-disabled', String(info.status === 'unavailable'));
    b.setAttribute('aria-label', `${CH()[r].label} and ${CH()[c].label}, ${info.status}${k === kept ? ', kept' : ''}`);
    b.tabIndex = r === focusRC[0] && c === focusRC[1] ? 0 : -1;
  }
}

function onMatrixKey(e) {
  let [r, c] = focusRC;
  const mv = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] }[e.key];
  if (mv) {
    e.preventDefault();
    r = Math.min(CH().length - 1, Math.max(1, r + mv[0]));
    c = Math.max(0, Math.min(r - 1, c + mv[1]));
    focusRC = [r, c];
    refreshMatrix();
    cells.get(`${r},${c}`).focus();
  } else if (e.key === ' ' || e.key === 'Spacebar') {
    e.preventDefault();
    stopAll();
  } else if (e.key === 'Home') {
    e.preventDefault(); focusRC = [r, 0]; refreshMatrix(); cells.get(`${r},0`).focus();
  } else if (e.key === 'End') {
    e.preventDefault(); focusRC = [r, r - 1]; refreshMatrix(); cells.get(`${r},${r - 1}`).focus();
  }
}

function pairText(a, z) {
  const A = byId[a], Z = byId[z];
  const info = pairInfo(a, z, S.layout);
  const piece = FROM_OUR_PIECES.find((p) => pairKey(p.a, p.b) === pairKey(a, z));
  return `<b>${A.label}</b> (${A.kind}, ${A.range}): ${A.desc}<br><b>${Z.label}</b> (${Z.kind}, ${Z.range}): ${Z.desc}<br>${info.text}` +
    (piece ? `<br><i>${piece.note}</i>` : '');
}

/** Matrix row and column of the kept pair (the row is always the later channel). */
function keptRC() {
  const i = CH().findIndex((c) => c.id === S.c1), j = CH().findIndex((c) => c.id === S.c2);
  return i > j ? [i, j] : [j, i];
}

function describe(r, c) { $('pair-desc').innerHTML = pairText(CH()[r].id, CH()[c].id); }

function showTip(r, c, el) {
  const tip = $('tip');
  tip.innerHTML = pairText(CH()[r].id, CH()[c].id);
  tip.hidden = false;
  const rc = el.getBoundingClientRect();
  const tw = tip.offsetWidth, th = tip.offsetHeight;
  let x = rc.right + 8, y = rc.top - 4;
  if (x + tw > window.innerWidth - 8) x = Math.max(8, rc.left - tw - 8);
  if (y + th > window.innerHeight - 8) y = Math.max(8, window.innerHeight - th - 8);
  tip.style.left = `${x}px`; tip.style.top = `${y}px`;
}
function hideTip() { $('tip').hidden = true; }

/** Keep a pair and hear it. Unavailable pairs only explain themselves. */
function choose(r, c) {
  const a = CH()[r].id, z = CH()[c].id;
  focusRC = [r, c];
  describe(r, c);
  if (pairInfo(a, z, S.layout).status === 'unavailable') { refreshMatrix(); return; }
  if (pairKey(a, z) !== pairKey(S.c1, S.c2)) { S.c1 = a; S.c2 = z; S.solo = null; }
  update();
  startLoop();
}

/* ---------- controls ---------- */
function seg(id, values, labels, get, set) {
  const el = $(id);
  el.innerHTML = '';
  values.forEach((v, i) => {
    const b = document.createElement('button');
    b.type = 'button'; b.textContent = labels[i]; b.dataset.v = v;
    b.addEventListener('click', () => { set(v); update(); if (playing) startLoop(); });
    el.append(b);
  });
  return () => el.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === get())));
}

const refreshLayout = seg('layout', LAYOUTS, ['Grid', 'Cloud', 'Lines'], () => S.layout, (v) => {
  S.layout = v;
  // A channel this layout cannot carry is swapped for the first one it can.
  const un = UNAVAILABLE[v];
  if (un[S.c1] || un[S.c2]) {
    const pick = (other) => CH().find((c) => !un[c.id] && c.id !== other).id;
    if (un[S.c1]) S.c1 = pick(S.c2);
    if (un[S.c2]) S.c2 = pick(S.c1);
    S.solo = null;
  }
});
const refreshTarget = seg('target', ['v1', 'v2', 'both'], ['V1', 'V2', 'Both'], () => S.target, (v) => { S.target = v; });
const refreshBreaths = seg('breaths', BREATHS.map(String), BREATHS.map((b) => (b ? String(b) : 'Still')), () => String(S.drone.breaths), (v) => { S.drone = { ...S.drone, breaths: Number(v) }; });
const refreshOct = seg('octave', OCTAVES.map(String), OCTAVES.map((o) => `D${o}`), () => String(S.octave), (v) => { S.octave = Number(v); S.solo = null; });
const refreshSpan = seg('span', SPANS.map(String), SPANS.map((n) => `${n} oct`), () => String(S.span), (v) => { S.span = Number(v); S.solo = null; });
/* ---------- how the data are made: plain words, formulas, code ---------- */
let fview = 'plain';
const esc = (t) => t.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c]);
/** TeX to MathML with the vendored KaTeX (no stylesheet needed); the TeX itself if KaTeX did not load. */
function math(tex) {
  try {
    if (window.katex) return splitTex(tex).map((t) => `<div class="m">${window.katex.renderToString(t, { output: 'mathml', displayMode: true, throwOnError: false })}</div>`).join('');
  } catch { /* fall through */ }
  return `<code>${esc(tex)}</code>`;
}
/** Display math does not wrap, so a rule joined by ", \qquad" (or ", \quad", ",\ ") becomes one line per part. Splits only outside braces and environments. */
function splitTex(tex) {
  const out = [];
  let depth = 0, from = 0;
  for (let i = 0; i < tex.length; i++) {
    const ch = tex[i];
    if (ch === '\\' && tex.startsWith('\\begin', i)) depth++;
    else if (ch === '\\' && tex.startsWith('\\end', i)) depth--;
    else if (ch === '{') depth++;
    else if (ch === '}') depth--;
    else if (ch === ',' && depth === 0) {
      const m = /^,\s*\\(qquad|quad| )\s*/.exec(tex.slice(i));
      if (m) { out.push(tex.slice(from, i)); from = i + m[0].length; i = from - 1; }
    }
  }
  out.push(tex.slice(from));
  return out.map((t) => t.trim()).filter(Boolean);
}
/** A line still wider than the panel (a phone) is set smaller, down to 70 %; past that it scrolls. */
function fitMath() {
  document.querySelectorAll('#explain .m').forEach((d) => {
    d.style.fontSize = '';
    const w = d.clientWidth, need = d.scrollWidth;
    if (w && need > w + 1) d.style.fontSize = `${Math.max(0.7, w / need).toFixed(3)}em`;
  });
}
function explainPanel(s) {
  const secs = explain(pool, s, cur ? cur.events : []);
  if (drumOn()) secs.push(explainDrum(pool, S.drum, cur ? cur.hits : []));
  const dsp = droneSpec(s);
  if (dsp) secs.push(explainDrone(dsp, LOOP));
  $('explain').innerHTML = secs.map((x) => `<section><h3>${esc(x.title)}</h3>${
    fview === 'plain' ? `<p>${esc(x.plain)}</p>` : fview === 'math' ? math(x.tex) : `<pre><code>${esc(x.code)}</code></pre>`}</section>`).join('');
  fitMath();
}
const refreshView = seg('fview', ['plain', 'math', 'code'], ['Plain words', 'Formulas', 'Code that runs'], () => fview, (v) => { fview = v; });
const refreshUse = seg('stream-use', STREAM_USES, ['Off', 'Density', 'Pace'], () => S.stream.use, (v) => { S.stream = { ...S.stream, use: v }; });
const refreshTmode = seg('tmode', TIME_MODES, ['Fit', 'Slice'], () => S.time, (v) => { S.time = v; });

/** A <select> bound to state; re-renders and keeps playing. */
function pick(id, items, get, set) {
  const el = $(id);
  el.innerHTML = items.map(([v, label]) => `<option value="${v}">${label}</option>`).join('');
  el.value = get();
  el.addEventListener('change', () => { set(el.value); update(); if (playing) startLoop(); });
}

function bindRange(id, fmt, set) {
  const el = $(id), out = $(`${id}-o`);
  let raf = 0;
  el.addEventListener('input', () => {
    set(Number(el.value));
    out.textContent = fmt(Number(el.value));
    if (id === 'vol') { if (master) master.gain.setTargetAtTime(S.vol * MASTER_TRIM, ctx.currentTime, 0.02); return; }
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(() => { update(); if (playing) startLoop(); });
  });
  out.textContent = fmt(Number(el.value));
}

function legends() {
  const box = $('legends');
  const keep = document.activeElement && box.contains(document.activeElement) ? document.activeElement.dataset.f : null;
  box.innerHTML = '';
  const s = setting();
  selected[1] = Math.min(selected[1], s.n1 - 1);
  selected[2] = Math.min(selected[2], s.n2 - 1);
  [[1, s.c1, s.n1, '--v1'], [2, s.c2, s.n2, '--v2']].forEach(([which, ch, n, cvar]) => {
    const C = byId[ch];
    const lv = levels(ch, n, s);
    const rp = which === 2 ? ramp(n) : null;
    const d = document.createElement('div');
    d.className = 'legend';
    d.style.setProperty('--c', `var(${cvar})`);
    d.innerHTML = `<div class="hd"><span class="nm">V${which}: ${C.label}<small>${C.kind}</small></span>
      <span class="stepper"><button type="button" aria-label="Fewer levels for V${which}">−</button><span>${n} levels</span><button type="button" aria-label="More levels for V${which}">+</button></span></div>
      ${realLane(which) ? `<div class="badge">V${which} · ${esc(seriesOf(S[`src${which}`].series).short)} [${TRANSFORM_LABELS[binner(seriesOf(S[`src${which}`].series), S[`src${which}`], n).transform]} · ${n}]</div>` : ''}
      <div class="lvs"></div>
      <div class="tools"><label><input type="checkbox" aria-label="Solo the selected level of V${which}, ${C.label}; others drop 18 dB"${S.solo && S.solo.v === which ? ' checked' : ''}> Solo the selected level (others −18 dB)</label></div>`;
    const [minus, plus] = d.querySelectorAll('.stepper button');
    minus.disabled = n <= 2; plus.disabled = n >= maxLevelsOf(ch, s);
    minus.dataset.f = `minus${which}`; plus.dataset.f = `plus${which}`;
    d.querySelector('input').dataset.f = `solo${which}`;
    const step = (dlt) => {
      if (which === 1) S.n1 = clampLevels(ch, n + dlt, S); else S.n2 = clampLevels(ch, n + dlt, S);
      S.solo = null; update(); if (playing) startLoop();
    };
    minus.addEventListener('click', () => step(-1));
    plus.addEventListener('click', () => step(1));
    const lvs = d.querySelector('.lvs');
    lv.forEach((v, k) => {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'lv'; b.dataset.f = `lv${which}-${k}`;
      const sel = S.solo && S.solo.v === which && S.solo.level === k;
      b.setAttribute('aria-pressed', String(!!sel));
      b.style.setProperty('--sw', which === 1 ? `color-mix(in srgb, var(--v1) ${Math.round(35 + 65 * (n === 1 ? 1 : k / (n - 1)))}%, transparent)` : rp[k]);
      b.innerHTML = `<i></i>${C.format(v)}`;
      b.title = `Hear level ${k + 1} of ${n}: three notes, with the loop dipped under them if it is playing`;
      b.addEventListener('click', () => {
        selected[which] = k;
        if (S.solo && S.solo.v === which) {
          // Solo on: the click moves the solo level, heard in context if the loop is playing.
          S.solo = { v: which, level: k };
          update();
          if (playing) startLoop();
        } else {
          auditionLevel(which, k);
          legendsMark();
        }
      });
      lvs.append(b);
    });
    d.querySelector('input').addEventListener('change', (e) => {
      S.solo = e.target.checked ? { v: which, level: selected[which] ?? 0 } : null;
      update(); if (playing) startLoop();
    });
    box.append(d);
  });
  if (keep) {
    // At the end of its range a stepper button is disabled and cannot hold focus; move to its partner.
    const el = box.querySelector(`[data-f="${keep}"]`);
    const alt = keep.replace(/^plus/, 'minus#').replace(/^minus(?!#)/, 'plus').replace('#', '');
    (el && !el.disabled ? el : box.querySelector(`[data-f="${alt}"]`))?.focus();
  }
}
const selected = { 1: 0, 2: 0 };
function legendsMark() {
  document.querySelectorAll('.legend').forEach((d, i) => {
    const which = i + 1;
    d.querySelectorAll('.lv').forEach((b, k) => b.setAttribute('aria-pressed', String(selected[which] === k)));
  });
}

function nowLine() {
  const s = setting();
  const n = cur.notes.length; // the real count: lines stop at eight, density drops events
  const g = crowding(n, s.layout);
  $('now').innerHTML = `<b>V1 ${byId[s.c1].label}</b> × <b>V2 ${byId[s.c2].label}</b> · ${s.layout} · ${n} events · crowding ${g.gainDb.toFixed(1).replace('-', '−')} dB${s.layout === 'lines' ? '' : `, length ×${g.durScale.toFixed(2)}`}`;
  $('layout-hint').textContent = LAYOUT_INFO[s.layout] + (s.layout === 'lines' ? ' The count stops at 8, and V3 is off: held tones have no density or pace.' : '');
  seedUI();
  explainPanel(s);
  $('stream-use').querySelectorAll('button').forEach((b) => { b.disabled = s.layout === 'lines'; });
  $('stream-model').disabled = s.layout === 'lines' || s.stream.use === 'off';
  $('drum-ch').disabled = $('drum-model').disabled = $('drum-level').disabled = !drumOn();
  const dOff = S.drone.mode === 'off';
  for (const id of ['drone-level', 'drone-depth', 'drone-bright']) $(id).disabled = dOff;
  $('breaths').querySelectorAll('button').forEach((b) => { b.disabled = dOff; });
  const D = DRUMS.find((d) => d.id === S.drum.voice), C = drumById[S.drum.channel];
  $('drum-o').textContent = drumOn()
    ? `${D.label}: ${D.desc.toLowerCase().replace(/\.$/, '')}. V4 sets its ${C.label.toLowerCase()}: ${C.desc.charAt(0).toLowerCase()}${C.desc.slice(1)} Levels: ${C.values.map(C.format).join(', ')}. ${cur.hits.length} of ${DRUM_STEPS} steps sound.`
    : 'The drum lane is a first look at a percussion layer: one drum on sixteen steps under the pair, with one variable, V4, on one of its channels at four levels.';
  const w = [];
  if (s.c1 === 'pan' || s.c2 === 'pan') w.push('Pan needs headphones or two speakers.');
  const info = pairInfo(s.c1, s.c2, s.layout);
  if (info.status === 'linked') w.push(info.text);
  $('warn').hidden = !w.length;
  $('warn').textContent = w.join(' ');
}

/** A piece's pair can be kept only while both its channels are in the matrix. */
function refreshPieces() {
  $('pieces').querySelectorAll('button').forEach((b) => {
    const out = [b.dataset.a, b.dataset.b].filter((id) => !S.slots.includes(id));
    b.disabled = out.length > 0;
    b.title = out.length ? `${out.map((id) => byId[id].label).join(' and ')} is on the bench; swap it back to hear this pair.` : '';
  });
}

function update() {
  renderLoop();
  refreshPieces();
  refreshMatrix(); refreshLayout(); refreshTarget(); refreshOct(); refreshSpan(); refreshUse(); refreshView(); refreshBreaths();
  for (const w of [1, 2]) { $(`m${w}`).value = srcVal(w); shapeUI(w); }
  timeUI();
  $('series-o').textContent = packNote; $('series-o').hidden = !packNote;
  legends(); legendsMark(); nowLine(); draw();
  $('octave').querySelectorAll('button').forEach((b) => { b.textContent = `${NOTE_NAMES[S.root]}${b.dataset.v}`; });
  $('json').hidden = true;
  scheduleTrail();
}

/* ---------- seed, variation, cousins, transition (11-15) ---------- */
const XF_SPAN = TRANSITION_RANGE[1] / TRANSITION_RANGE[0];
const xfFromSlider = (v) => +(TRANSITION_RANGE[0] * Math.pow(XF_SPAN, v / 100)).toFixed(2);
const xfToSlider = (sec) => Math.round((100 * Math.log(sec / TRANSITION_RANGE[0])) / Math.log(XF_SPAN));
const xfText = (sec) => (sec < 1 ? `${sec.toFixed(2)} s` : `${sec.toFixed(1)} s`);
function seedUI() {
  if (document.activeElement !== $('seed')) $('seed').value = String(S.seed);
  $('seed-dial').setAttribute('aria-valuenow', String(S.seed));
  $('var').value = S.variation; $('var-o').textContent = `${Math.round(S.variation * 100)} %`;
  $('dir-o').textContent = `direction ${S.direction}${S.variation > 0 ? ` (toward seed ${pool.partner})` : ''}`;
  $('dir-dn').disabled = S.direction <= 1; $('dir-up').disabled = S.direction >= 99;
  $('xfade').value = xfToSlider(S.transition); $('xfade-o').textContent = xfText(S.transition);
  const kname = `${NOTE_NAMES[S.root]} ${SCALES[S.scale].label.toLowerCase()}`;
  $('seed-o').textContent = `Seed ${S.seed}${S.variation > 0 ? `, ${Math.round(S.variation * 100)} % of the way to seed ${pool.partner}` : ''}. Key: ${kname}.`;
}
/** Set the seed (wrapped into range) and hear it. */
function setSeed(v) {
  const n = Math.round(Number(v));
  if (!Number.isFinite(n)) return;
  S.seed = ((n - 1) % MAX_SEED + MAX_SEED) % MAX_SEED + 1;
  rebuildPool(); update(); if (playing) startLoop();
}
/** The dial: a drag of 8 px is one seed; arrow keys step one, Page Up and Down ten. */
function seedDial() {
  const d = $('seed-dial');
  let x0 = 0, y0 = 0, s0 = 0, raf = 0, on = false;
  d.addEventListener('pointerdown', (e) => { on = true; x0 = e.clientX; y0 = e.clientY; s0 = S.seed; d.setPointerCapture(e.pointerId); e.preventDefault(); });
  d.addEventListener('pointermove', (e) => {
    if (!on) return;
    const steps = Math.round(((e.clientX - x0) - (e.clientY - y0)) / 8);
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(() => { if (s0 + steps !== S.seed) setSeed(s0 + steps); });
  });
  const end = () => { on = false; };
  d.addEventListener('pointerup', end); d.addEventListener('pointercancel', end);
  d.addEventListener('keydown', (e) => {
    const k = { ArrowUp: 1, ArrowRight: 1, ArrowDown: -1, ArrowLeft: -1, PageUp: 10, PageDown: -10 }[e.key];
    if (k) { e.preventDefault(); setSeed(S.seed + k); }
  });
}

/* ---------- the trail, stars and the link (11-15) ---------- */
const DWELL_MS = 2000, TRAIL_MAX = 30;
/** Inside the site's iframe the address bar belongs to the article, so the trail leaves its history alone. */
const EMBEDDED = /[?&]embed\b/.test(location.search) && window.parent !== window;
const store = {
  get(k, dflt) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : dflt; } catch { return dflt; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* storage off: the trail lasts this visit */ } },
};
const chipOK = (c) => c && typeof c === 'object' && typeof c.k === 'string' && typeof c.label === 'string' && c.j && typeof c.j === 'object';
const storedChips = (k) => { const v = store.get(k, []); return Array.isArray(v) ? v.filter(chipOK) : []; };
let trail = storedChips('scb.trail.v1'), stars = storedChips('scb.stars.v1');
let dwellT = 0, nowKey = '';
const keyOf = (j) => JSON.stringify(j);
function b64e(str) { const b = new TextEncoder().encode(str); let t = ''; for (const x of b) t += String.fromCharCode(x); return btoa(t).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''); }
function b64d(s) { const t = atob(s.replace(/-/g, '+').replace(/_/g, '/')); return new TextDecoder().decode(Uint8Array.from(t, (c) => c.charCodeAt(0))); }
const hashOf = (j) => `#p=${b64e(keyOf(j))}`;
function chipLabel(j) {
  const p = j.play ?? {}, ch = (j.lanes ?? []).map((l) => `${l.source?.series ? `${String(l.source.series).slice(0, 7)}→` : ''}${(byId[l.channel]?.label ?? '?').slice(0, 5)}`).join('×');
  return `${p.seed ?? '?'}${p.variation ? `~${Math.round(p.variation * 100)}` : ''} ${ch} ${NOTE_NAMES[j.pitch?.root ?? 2]}${j.drone ? ' ◦' : ''}`;
}
function thumb() {
  const cv = document.createElement('canvas');
  cv.width = 96; cv.height = 32;
  try { drawSpec(cv.getContext('2d'), 96, 32, cur.spec, colors()); return cv.toDataURL('image/png'); } catch { return ''; }
}
function scheduleTrail() {
  clearTimeout(dwellT);
  nowKey = keyOf(bindingJSON(setting()));
  markChips();
  dwellT = setTimeout(commitTrail, DWELL_MS);
}
function commitTrail() {
  const j = bindingJSON(setting()), k = keyOf(j);
  if (!playing) return;
  if (!EMBEDDED) { try { if (location.hash !== hashOf(j)) history.pushState(null, '', hashOf(j)); } catch { /* sandboxed: no address to follow */ } }
  if (trail.some((c) => c.k === k)) return;
  trail.unshift({ k, j, img: thumb(), label: chipLabel(j) });
  trail = trail.slice(0, TRAIL_MAX);
  store.set('scb.trail.v1', trail);
  chips();
}
function chipEl(c, where) {
  const d = document.createElement('div');
  d.className = 'chip'; d.dataset.k = c.k;
  const starred = stars.some((x) => x.k === c.k);
  d.innerHTML = `<button class="go" type="button" title="Hear this again"><img alt=""><span class="lbl"></span></button><button class="star" type="button" aria-pressed="${starred}" aria-label="${starred ? 'Unstar' : 'Star'} this sound">${starred ? '★' : '☆'}</button>`;
  if (typeof c.img === 'string' && c.img.startsWith('data:image/png;base64,')) d.querySelector('img').src = c.img; // set as a property, never parsed as HTML
  d.querySelector('.lbl').textContent = c.label;
  d.querySelector('.go').title = `Hear this again: ${c.label}`;
  d.querySelector('.go').addEventListener('click', () => applyPair(c.j, { play: true, note: `Playing ${c.label} from your ${where}.` }));
  d.querySelector('.star').addEventListener('click', () => {
    if (stars.some((x) => x.k === c.k)) stars = stars.filter((x) => x.k !== c.k); else stars.unshift(c);
    store.set('scb.stars.v1', stars);
    chips();
  });
  return d;
}
function chips() {
  for (const [id, list, where, empty] of [['stars', stars, 'stars', 'No stars yet.'], ['trail', trail, 'trail', 'Nothing yet: press Play and listen.']]) {
    const box = $(id);
    box.innerHTML = '';
    if (!list.length) { box.innerHTML = `<p class="hint">${empty}</p>`; continue; }
    list.forEach((c) => box.append(chipEl(c, where)));
  }
  markChips();
}
function markChips() { document.querySelectorAll('.chip').forEach((d) => d.classList.toggle('now', d.dataset.k === nowKey)); }
function copyText(txt, okMsg, out) {
  const fallback = () => { const ta = $('json'); ta.value = txt; ta.hidden = false; ta.focus(); ta.select(); out.textContent = 'Copy was refused here; the text is selected in the box under Copy pair as JSON.'; };
  try { navigator.clipboard.writeText(txt).then(() => { out.textContent = okMsg; }, fallback); } catch { fallback(); }
}
function linkHere() {
  const u = new URL(location.href);
  u.searchParams.delete('embed');
  u.hash = hashOf(bindingJSON(setting()));
  return u.toString();
}
/** The page address's pair as text, or '' if there is none or it cannot be decoded. */
function safeHashText() { const m = /^#p=([A-Za-z0-9_-]+)$/.exec(location.hash); try { return m ? b64d(m[1]) : ''; } catch { return ''; } }
function readHash(play) {
  const m = /^#p=([A-Za-z0-9_-]+)$/.exec(location.hash);
  if (!m) return false;
  try { return applyPair(JSON.parse(b64d(m[1])), { play, note: 'Set from the page address.' }); } catch { return false; }
}

function pieces() {
  const box = $('pieces');
  FROM_OUR_PIECES.forEach((p) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.innerHTML = `<b>${byId[p.a].label} × ${byId[p.b].label}</b><br>${p.note}`;
    b.dataset.a = p.a; b.dataset.b = p.b;
    b.addEventListener('click', () => {
      S.c1 = p.a; S.c2 = p.b; S.solo = null;
      if (pairInfo(p.a, p.b, S.layout).status === 'unavailable') S.layout = 'grid';
      focusRC = keptRC();
      update(); describe(...focusRC); startLoop();
    });
    box.append(b);
  });
}

function toggles() {
  const box = $('toggles');
  [['data', 'Data'], ['score', 'Score'], ['wave', 'Waveform'], ['spec', 'Spectrogram']].forEach(([k, label]) => {
    const l = document.createElement('label');
    l.innerHTML = `<input type="checkbox" id="show-${k}" checked> ${label}`;
    l.querySelector('input').addEventListener('change', (e) => { S.show[k] = e.target.checked; draw(); });
    box.append(l);
  });
}

/** Inside the site's page (?embed): drop the page's own title and tell the parent its height. */
function embed() {
  if (!/[?&]embed\b/.test(location.search) || window.parent === window) return;
  document.documentElement.classList.add('embed');
  const post = () => { try { window.parent.postMessage({ wyrHeight: document.documentElement.scrollHeight }, location.origin); } catch { /* not allowed */ } };
  new ResizeObserver(post).observe(document.body);
  post();
}

/** Play a pair from pasted or opened JSON: the same JSON gives the same loop. */
function loadPair(text) {
  const out = $('load-o');
  let j;
  try { j = JSON.parse(text); } catch (e) { out.textContent = `Not valid JSON: ${e.message}`; return; }
  if (j && /^sound-channel-brewer\/stars@1$/.test(j.schema ?? '') && Array.isArray(j.stars)) {
    let added = 0;
    for (const p of j.stars) {
      let q;
      try { q = bindingJSON({ ...setting(), ...pairFromJSON(p, pairOpts()).state }); } catch { continue; } // only pairs this page can play, kept in this page's own form
      const k = keyOf(q);
      if (stars.some((x) => x.k === k)) continue;
      stars.push({ k, j: q, img: '', label: chipLabel(q) }); added++;
    }
    store.set('scb.stars.v1', stars); chips();
    out.textContent = `Added ${added} of ${j.stars.length} stars (the rest were here already or could not be read). Their pictures come back when you play them.`;
    return;
  }
  applyPair(j, { play: true, note: 'Playing the pair from the JSON.' });
}

/** Apply a pair object to the page; returns false (and says why) when it cannot be read. */
function applyPair(j, { play = true, note = '' } = {}) {
  const out = $('load-o');
  let r;
  try { r = pairFromJSON(j, pairOpts()); } catch (e) { out.textContent = e.message; return false; }
  Object.assign(S, r.state);
  rebuildPool();
  S.lastSwap = null;
  selected[1] = 0; selected[2] = 0;
  if (S.solo) selected[S.solo.v] = S.solo.level;
  for (const id of ['voice', 'm1', 'm2', 'root', 'scale']) $(id).value = S[id];
  $('drone').value = S.drone.mode;
  for (const [k, f] of [['level', (v) => `${v} dB`.replace('-', '−')], ['depth', (v) => `${Math.round(v * 100)} %`], ['bright', brightText]]) { $(`drone-${k}`).value = S.drone[k]; $(`drone-${k}-o`).textContent = f(S.drone[k]); }
  $('stream-model').value = S.stream.model;
  for (const [id, k] of [['drum', 'voice'], ['drum-ch', 'channel'], ['drum-model', 'model']]) $(id).value = S.drum[k];
  $('drum-level').value = S.drum.level; $('drum-level-o').textContent = dbLabel(S.drum.level);
  $('count').value = S.count; $('count-o').textContent = String(S.count);
  $('corr').value = S.corr; $('corr-o').textContent = `${Math.round(S.corr * 100)} %`;
  voiceHint();
  buildMatrix(); benchUI();
  focusRC = keptRC();
  update(); describe(...focusRC);
  if (play) startLoop();
  out.textContent = [note, ...r.notes].join(' ');
  return true;
}
const brightText = (v) => `${Math.round(150 * Math.pow(20, v))} Hz`;

function voiceHint() { const v = VOICES.find((x) => x.id === S.voice); $('voice-o').textContent = v ? v.desc : ''; }

function init() {
  const packP = loadPack(); // in parallel: the page plays seeded data at once and gains the real series when they arrive
  buildMatrix();
  $('matrix').addEventListener('keydown', onMatrixKey);
  $('matrix').addEventListener('keyup', (e) => { if (e.key === ' ' || e.key === 'Spacebar') e.preventDefault(); });
  benchUI();
  $('swap-ch').addEventListener('click', () => swapChannel($('bench').value, $('slot').value));
  $('swap-back').addEventListener('click', () => { const l = S.lastSwap; if (l) swapChannel(l.out, l.in); });
  pieces();
  toggles();
  document.querySelectorAll('.cv').forEach((cv) => { const p = document.createElement('div'); p.className = 'ph'; cv.append(p); });
  for (const k of ['data', 'score', 'wave', 'spec']) {
    const cv = $(`cv-${k}`);
    cv.addEventListener('mousemove', (e) => stripTip(k, e));
    cv.addEventListener('mouseleave', hideTip);
  }
  pick('voice', VOICES.map((v) => [v.id, v.label]), () => S.voice, (v) => { S.voice = v; });
  $('voice').addEventListener('change', voiceHint);
  sourcePick(1); sourcePick(2);
  let rafT = 0;
  $('tstart').addEventListener('input', (e) => {
    setStart(Number(e.target.value));
    cancelAnimationFrame(rafT);
    rafT = requestAnimationFrame(() => { update(); if (playing) startLoop(); });
  });
  $('twin').addEventListener('change', (e) => { S.twin = e.target.checked; update(); if (playing) startLoop(); });
  $('score-copy').addEventListener('click', () => copyText(scoreText(), `Copied the loop as a score: ${cur.notes.length} notes, one per line, tab-separated.`, $('trail-o')));
  pick('stream-model', STREAM_IDS.map((m) => [m, STREAM_MODELS[m].label]), () => S.stream.model, (v) => { S.stream = { ...S.stream, model: v }; });
  pick('drum', DRUMS.map((d) => [d.id, d.label]), () => S.drum.voice, (v) => { S.drum = { ...S.drum, voice: v }; });
  pick('drum-ch', DRUM_CHANNELS.map((c) => [c.id, c.label]), () => S.drum.channel, (v) => { S.drum = { ...S.drum, channel: v }; });
  pick('drum-model', MODEL_IDS.map((m) => [m, MODELS[m].label]), () => S.drum.model, (v) => { S.drum = { ...S.drum, model: v }; });
  voiceHint();
  bindRange('count', (v) => String(v), (v) => { S.count = v; });
  bindRange('corr', (v) => `${Math.round(v * 100)} %`, (v) => { S.corr = v; });
  Object.assign($('drum-level'), { min: DRUM_LEVEL_RANGE[0], max: DRUM_LEVEL_RANGE[1], value: DRUM_DEFAULTS.level });
  bindRange('drum-level', dbLabel, (v) => { S.drum = { ...S.drum, level: v }; });
  bindRange('vol', (v) => `${Math.round(v * 100)} %`, (v) => { S.vol = v; });
  $('play').addEventListener('click', () => startLoop());
  $('stop').addEventListener('click', stopAll);
  $('swap').addEventListener('click', () => {
    [S.c1, S.c2] = [S.c2, S.c1]; [S.n1, S.n2] = [S.n2, S.n1]; [selected[1], selected[2]] = [selected[2], selected[1]]; S.solo = null;
    update(); if (playing) startLoop();
  });
  $('shuffle').addEventListener('click', () => setSeed(1 + Math.floor(rng(S.seed)() * (MAX_SEED - 1)))); // the next seed, drawn from this one
  $('seed-dn').addEventListener('click', () => setSeed(S.seed - 1));
  $('seed-up').addEventListener('click', () => setSeed(S.seed + 1));
  $('seed').addEventListener('change', (e) => setSeed(e.target.value));
  $('seed').addEventListener('keydown', (e) => { if (e.key === 'Enter') setSeed(e.target.value); });
  seedDial();
  bindRange('var', (v) => `${Math.round(v * 100)} %`, (v) => { S.variation = v; rebuildPool(); });
  const dir = (d) => { S.direction = Math.min(99, Math.max(1, S.direction + d)); rebuildPool(); update(); if (playing) startLoop(); };
  $('dir-dn').addEventListener('click', () => dir(-1));
  $('dir-up').addEventListener('click', () => dir(1));
  $('xfade').addEventListener('input', (e) => { S.transition = xfFromSlider(Number(e.target.value)); $('xfade-o').textContent = xfText(S.transition); });
  pick('root', ROOTS.map((r) => [String(r), NOTE_NAMES[r]]), () => String(S.root), (v) => { S.root = Number(v); S.solo = null; });
  pick('scale', SCALE_IDS.map((k) => [k, SCALES[k].label]), () => S.scale, (v) => { S.scale = v; S.solo = null; });
  pick('drone', DRONE_MODES.map((m) => [m.id, m.label]), () => S.drone.mode, (v) => { S.drone = { ...S.drone, mode: v }; });
  bindRange('drone-level', (v) => `${v} dB`.replace('-', '−'), (v) => { S.drone = { ...S.drone, level: v }; });
  bindRange('drone-depth', (v) => `${Math.round(v * 100)} %`, (v) => { S.drone = { ...S.drone, depth: v }; });
  bindRange('drone-bright', brightText, (v) => { S.drone = { ...S.drone, bright: v }; });
  $('link').addEventListener('click', () => copyText(linkHere(), 'Link copied. It opens this sound; press Play to hear it.', $('trail-o')));
  $('stars-copy').addEventListener('click', () => copyText(JSON.stringify({ schema: 'sound-channel-brewer/stars@1', stars: stars.map((c) => c.j) }, null, 2), `Copied ${stars.length} stars as JSON.`, $('trail-o')));
  $('trail-clear').addEventListener('click', () => { trail = []; store.set('scb.trail.v1', trail); chips(); $('trail-o').textContent = 'Trail cleared; stars kept.'; });
  window.addEventListener('popstate', () => readHash(playing));
  $('copy').addEventListener('click', () => {
    const txt = JSON.stringify(bindingJSON(setting()), null, 2);
    const ta = $('json');
    ta.value = txt;
    const fallback = () => { ta.hidden = false; ta.focus(); ta.select(); $('copy-o').textContent = 'Copy was refused here; the JSON is selected below.'; };
    try {
      navigator.clipboard.writeText(txt).then(() => { $('copy-o').textContent = 'Copied.'; }, fallback);
    } catch { fallback(); }
  });
  $('load-play').addEventListener('click', () => loadPair($('load-ta').value));
  $('load-open').addEventListener('click', () => $('load-file').click());
  $('load-file').addEventListener('change', async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    if (f.size > 100000) { $('load-o').textContent = 'That file is too large to be a pair JSON.'; return; }
    $('load-ta').value = await f.text();
    e.target.value = '';
    loadPair($('load-ta').value);
  });
  $('fold-math').addEventListener('toggle', fitMath);
  new ResizeObserver(fitMath).observe($('explain'));
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') stopAll(); });
  focusRC = keptRC();
  const hashFirst = /^#p=/.test(location.hash), hashReal = hashFirst && /"source"/.test(safeHashText());
  if (!hashFirst || hashReal || !readHash(false)) update(); // a link with no real lane opens at once; one with a real lane waits for the pack
  describe(...focusRC);
  packP.then(() => {
    fillSource(1); fillSource(2);
    presets();
    // A link to a real series needs the pack; read it again now (it fails with a plain message if the pack did not load).
    if (hashReal) { if (!readHash(false)) update(); } else update();
    describe(...focusRC);
  });
  chips();
  embed();
  new ResizeObserver(() => draw()).observe($('strips'));
  const redraw = () => { legends(); legendsMark(); draw(); };
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', redraw);
  new MutationObserver(redraw).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
}

init();
