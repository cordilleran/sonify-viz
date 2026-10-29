/**
 * The drum lane: a first look at a percussion layer. One drum plays sixteen steps a loop
 * under the tonal pair, and one variable, V4, sets one drum channel at four levels.
 * Pure, deterministic. V4's draws come from the pool (made after every other draw, so the
 * tonal loop for a seed is the same with or without the drum).
 */
import { MODELS } from './pool.js';

export const DRUM_STEPS = 16;
export const DRUM_LEVELS = 4;

export const DRUMS = [
  { id: 'off', label: 'Off', desc: 'No drum lane.' },
  { id: 'kick', label: 'Kick', desc: 'A low thump whose pitch drops fast.' },
  { id: 'snare', label: 'Snare', desc: 'A short tone with a burst of bright noise.' },
  { id: 'hat', label: 'Hi-hat', desc: 'High noise only: a tick or a hiss.' },
  { id: 'block', label: 'Woodblock', desc: 'A hollow knock with two ringing tones.' },
  { id: 'shaker', label: 'Shaker', desc: 'Soft noise with a slower start.' },
];
export const DRUM_IDS = DRUMS.map((d) => d.id);

/** The channels V4 can drive. `values` are the four levels; `rest` is the value when V4 drives another channel. */
export const DRUM_CHANNELS = [
  { id: 'accent', label: 'Accent', desc: 'How hard each hit is, from soft to full.', values: [-18, -12, -6, 0], rest: -6, format: (v) => `${v} dB`.replace('-', '−') },
  { id: 'decay', label: 'Decay', desc: 'How long each hit rings, from a click to a long tail.', values: [0.04, 0.09, 0.2, 0.45], rest: 0.15, format: (v) => `${Math.round(v * 1000)} ms` },
  { id: 'chance', label: 'Hit chance', desc: 'How likely each step is to sound, from sparse to nearly every step.', values: [0.2, 0.45, 0.7, 0.95], rest: 1, format: (v) => `${Math.round(v * 100)} %` },
  { id: 'tuning', label: 'Tuning', desc: 'How high the drum is tuned, in semitones from its normal pitch.', values: [-7, -2, 3, 8], rest: 0, format: (v) => `${v > 0 ? '+' : ''}${v} st`.replace('-', '−') },
];
export const drumById = Object.fromEntries(DRUM_CHANNELS.map((c) => [c.id, c]));
export const DRUM_CHANNEL_IDS = DRUM_CHANNELS.map((c) => c.id);
export const DRUM_DEFAULTS = { voice: 'off', channel: 'accent', model: 'seasonal', level: -6 };
/** The lane's own level control, in dB on top of the accent; it starts 6 dB down so the drum sits under the pair. */
export const DRUM_LEVEL_RANGE = [-24, 0];

/** The model sees one step's draws; k decides whether the step sounds under "Hit chance". */
const view = (d) => ({ u: d.u, z: d.z, b: d.b });

/**
 * The hits for one setting.
 * @param {{drum4:{u:number,z:number,b:number,k:number}[], p4:object}} pool
 * @param {{voice:string, channel:string, model:string, level?:number}} dr
 * @returns {{step:number, t:number, x4:number, level:number, gainDb:number, decay:number, tune:number, kind:string}[]}
 */
export function drumHits(pool, dr, loopSec) {
  if (!dr || dr.voice === 'off') return [];
  const M = MODELS[dr.model];
  const val = (id, level) => (dr.channel === id ? drumById[id].values[level] : drumById[id].rest);
  const out = [];
  pool.drum4.forEach((d, step) => {
    const f = step / DRUM_STEPS;
    const x4 = M.x(view(d), f, pool.p4);
    const level = Math.min(DRUM_LEVELS - 1, Math.floor(x4 * DRUM_LEVELS));
    if (d.k >= val('chance', level)) return;
    out.push({ step, t: f * loopSec, x4, level, gainDb: val('accent', level) + (dr.level ?? DRUM_DEFAULTS.level), decay: val('decay', level), tune: Math.pow(2, val('tuning', level) / 12), kind: dr.voice });
  });
  return out;
}

/** The rule in the three registers of the formula panel. */
export function explainDrum(pool, dr, hits) {
  const C = drumById[dr.channel], M = MODELS[dr.model];
  const h = hits[0];
  const worked = h ? ` In this loop the first hit is step ${h.step + 1}: x = ${h.x4.toFixed(2)}, which is level ${h.level + 1} of 4, so its ${C.label.toLowerCase()} is ${C.format(C.values[h.level])}.` : '';
  return {
    title: `V4: ${M.label} on the drum's ${C.label.toLowerCase()}`,
    plain: `The drum lane is a first look at a percussion layer. The ${DRUMS.find((d) => d.id === dr.voice).label.toLowerCase()} has sixteen steps in the loop, and one variable, V4, sets its ${C.label.toLowerCase()} at four levels (${C.values.map(C.format).join(', ')}). ${M.plain(pool.p4)}${dr.channel === 'chance' ? ' Each step also has a number k between 0 and 1 and sounds only if k is below the chance for its level.' : ''}${worked}`,
    tex: `${M.tex(pool.p4).replace(/^x\b/, 'x_4')}, \\qquad \\ell_4 = \\min(3, \\lfloor 4\\,x_4 \\rfloor), \\qquad t_s = s\\,T/16`,
    code: `MODELS.${dr.model}.x = ${M.x.toString()};\n// the hits\n${drumHits.toString()}`,
  };
}
