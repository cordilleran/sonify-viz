/**
 * The drone bed (11-15): a held chord on the key's root under the pair, after the workbench's
 * `synth.drone()` (scripts/synth.py): detuned sawtooths with a sine an octave down, a low-pass, and a slow breath.
 * Pure: this file only says what to play; dsp.js renders it. Every frequency is rounded to a whole number of
 * cycles per loop, and the breath to a whole number per loop, so the loop stays seamless.
 */
import { NOTE_NAMES, PITCH_DEFAULTS } from './channels.js';

export const DRONE_MODES = [
  { id: 'off', label: 'Off', steps: null },
  { id: 'root', label: 'Root', steps: [0] },
  { id: 'fifth', label: 'Root and fifth', steps: [0, 7] },
  { id: 'octave', label: 'Root, fifth, octave', steps: [0, 7, 12] },
];
export const DRONE_MODE_IDS = DRONE_MODES.map((m) => m.id);
export const BREATHS = [0, 1, 2, 4]; // breaths per 4-second loop
export const DRONE_LEVEL_RANGE = [-30, 0];
export const DRONE_DEFAULTS = { mode: 'off', level: -6, breaths: 1, depth: 0.5, bright: 0.35 };
export const SAWS = 5; // per note, spread over ±DETUNE cents
export const DETUNE = 9;

/** Cutoff in Hz from brightness 0..1 (150 Hz to 3 kHz, even steps in pitch). */
export const droneCutoff = (b) => 150 * Math.pow(20, Math.min(1, Math.max(0, b)));

/** What the drone plays for a page state, or null when it is off. Two octaves under "Pitch from", never below octave 2 (11-15: octave 1, 37 to 62 Hz, was lost on laptop speakers). */
export function droneSpec(s) {
  const d = { ...DRONE_DEFAULTS, ...(s.drone ?? {}) };
  const mode = DRONE_MODES.find((m) => m.id === d.mode);
  if (!mode || !mode.steps) return null;
  const root = s.root ?? PITCH_DEFAULTS.root, oct = Math.max(2, (s.octave ?? PITCH_DEFAULTS.octave) - 2);
  const base = 12 * (oct + 1) + root;
  return { midis: mode.steps.map((x) => base + x), gainDb: d.level, breaths: d.breaths, depth: d.depth, cutoff: droneCutoff(d.bright), name: `${NOTE_NAMES[root]}${oct}` };
}

/** The formula panel's section for the drone. */
export function explainDrone(spec, loopSec) {
  const notes = spec.midis.map((m) => `${NOTE_NAMES[m % 12]}${Math.floor(m / 12) - 1}`).join(', ');
  return {
    title: `Drone bed (${notes})`,
    plain: `A held chord on the key's root, under everything, like the drones in our river and climate pieces. Each note is ${SAWS} sawtooth waves spread over ±${DETUNE} cents, so they beat slowly against each other, plus a sine an octave down for body. A low-pass filter at about ${Math.round(spec.cutoff)} Hz softens it. ${spec.breaths ? `It breathes ${spec.breaths} time${spec.breaths > 1 ? 's' : ''} per loop: the level dips by up to ${Math.round(spec.depth * 100)} % and the filter closes a little at the bottom of each breath.` : 'Breathing is off, so it holds steady.'} Every frequency is rounded to a whole number of cycles in the ${loopSec}-second loop (steps of ${(1 / loopSec).toFixed(2)} Hz), so the loop joins without a click. The drone carries no data.`,
    tex: String.raw`y(t) = \Big(\sum_{k} \operatorname{saw}(2\pi f_k t) + \tfrac12 \sin(\pi f_0 t)\Big) \cdot \big(1 - d\,\tfrac{1-\cos(2\pi b t/T)}{2}\big),\quad f_k = \tfrac{1}{T}\operatorname{round}\big(T f_0\, 2^{c_k/1200}\big),\ d = ${spec.depth.toFixed(2)},\ b = ${spec.breaths}`,
    code: `droneSpec = ${droneSpec.toString()}`,
  };
}
