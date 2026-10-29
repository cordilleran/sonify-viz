/**
 * Four aligned strips for the sound picker: Data, Score, Waveform, Spectrogram,
 * plus a playhead. Pure helpers (envelope, fft, spectrogram, timeTicks) never
 * touch the DOM; painters take a CanvasRenderingContext2D-like ctx and sizes in
 * CSS pixels.
 */

/**
 * Minimum frequency in Hz represented at the bottom row.
 * @type {number}
 */
export const FMIN = 40;

/**
 * Maximum frequency in Hz represented at the top row.
 * @type {number}
 */
export const FMAX = 8000;

/**
 * @typedef {{sr: number, L: Float32Array, R: Float32Array, loopSec: number}} RenderedBuffer
 * @typedef {{onset: number, dur: number, v1: number, v2: number, dim: boolean}} PickerEvent
 * @typedef {{fg: string, muted: string, grid: string, accent: string, v1: string, v2: string, bg: string}} VizColors
 * @typedef {{cols: number, rows: number, data: Float32Array}} Spec
 */

/**
 * Maps a frequency in Hz to a 0..1 fraction on a log axis (0 at FMIN, 1 at FMAX).
 *
 * @param {number} f Frequency in Hz.
 * @returns {number} Fraction clamped to [0, 1].
 */
export function freqToFrac(f) {
  if (!(f > FMIN)) return 0;
  if (f >= FMAX) return 1;
  return Math.log(f / FMIN) / Math.log(FMAX / FMIN);
}

/**
 * Per-pixel min/max of a sample array. Spans cover the whole array; when the
 * array is shorter than nPix the nearest sample is repeated.
 *
 * @param {Float32Array} samples Mono samples.
 * @param {number} nPix Number of pixel columns.
 * @returns {{min: Float32Array, max: Float32Array}} Envelope.
 */
export function envelope(samples, nPix) {
  const n = Math.max(0, Math.floor(nPix));
  const min = new Float32Array(n);
  const max = new Float32Array(n);
  const len = samples.length;
  if (len === 0) return { min, max };
  for (let i = 0; i < n; i++) {
    let a = Math.floor((i * len) / n);
    let b = Math.floor(((i + 1) * len) / n);
    if (len < n) {
      a = Math.min(len - 1, a);
      b = a + 1;
    } else if (b <= a) {
      b = a + 1;
    }
    let lo = Infinity;
    let hi = -Infinity;
    for (let j = a; j < b; j++) {
      const v = samples[j];
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
    min[i] = lo;
    max[i] = hi;
  }
  return { min, max };
}

/** Twiddle factors exp(-2πik/n) for k < n/2, cached per length (the spectrogram calls fft hundreds of times). */
const TWIDDLES = new Map();
function twiddles(n) {
  let t = TWIDDLES.get(n);
  if (!t) {
    const c = new Float64Array(n >> 1), s = new Float64Array(n >> 1);
    for (let k = 0; k < n >> 1; k++) { c[k] = Math.cos((-2 * Math.PI * k) / n); s[k] = Math.sin((-2 * Math.PI * k) / n); }
    t = [c, s];
    TWIDDLES.set(n, t);
  }
  return t;
}

/**
 * In-place iterative radix-2 complex FFT.
 *
 * @param {Float32Array|Float64Array} re Real parts.
 * @param {Float32Array|Float64Array} im Imaginary parts.
 * @returns {void}
 * @throws {Error} If the length is not a power of two or the arrays differ in length.
 */
export function fft(re, im) {
  const n = re.length;
  if (n < 1 || (n & (n - 1)) !== 0 || im.length !== n) {
    throw new Error('fft: length must be a power of two and re/im must match');
  }
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      let t = re[i]; re[i] = re[j]; re[j] = t;
      t = im[i]; im[i] = im[j]; im[j] = t;
    }
  }
  const [cosT, sinT] = twiddles(n);
  for (let size = 2; size <= n; size <<= 1) {
    const half = size >> 1;
    const stride = n / size;
    for (let start = 0; start < n; start += size) {
      for (let k = 0; k < half; k++) {
        const wr = cosT[k * stride];
        const wi = sinT[k * stride];
        const a = start + k;
        const b = a + half;
        const xr = re[b] * wr - im[b] * wi;
        const xi = re[b] * wi + im[b] * wr;
        re[b] = re[a] - xr;
        im[b] = im[a] - xi;
        re[a] += xr;
        im[a] += xi;
      }
    }
  }
}

/**
 * Log-frequency spectrogram. data[c * rows + r], r = 0 at FMIN (bottom).
 * Values are (dB - floorDb) / (-floorDb) clamped to 0..1, with a full-scale
 * sine reading about 0 dB.
 *
 * @param {Float32Array} samples Mono samples.
 * @param {number} sr Sample rate in Hz.
 * @param {{nfft?: number, hop?: number, rows?: number, floorDb?: number}} [opts] Options.
 * @returns {Spec} Spectrogram.
 */
export function spectrogram(samples, sr, opts = {}) {
  const nfft = opts.nfft || 1024;
  const hop = opts.hop || 256;
  const rows = opts.rows || 96;
  const floorDb = opts.floorDb === undefined ? -80 : opts.floorDb;
  const cols = Math.max(1, Math.floor((samples.length - nfft) / hop) + 1);
  const data = new Float32Array(cols * rows);
  const nbin = nfft / 2 + 1;

  const win = new Float64Array(nfft);
  for (let i = 0; i < nfft; i++) win[i] = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / nfft);
  const norm = nfft / 4; // Hann-windowed full-scale sine peaks at nfft/4

  // Row plan: bins falling in each row, else interpolation between neighbours.
  const binsOf = Array.from({ length: rows }, () => []);
  for (let k = 1; k < nbin; k++) {
    const f = (k * sr) / nfft;
    if (f < FMIN || f > FMAX) continue;
    const r = Math.min(rows - 1, Math.floor(freqToFrac(f) * rows));
    binsOf[r].push(k);
  }
  const interp = new Array(rows).fill(null);
  for (let r = 0; r < rows; r++) {
    if (binsOf[r].length) continue;
    const fc = FMIN * Math.pow(FMAX / FMIN, (r + 0.5) / rows);
    const kf = Math.min(nbin - 1, Math.max(0, (fc * nfft) / sr));
    const k0 = Math.floor(kf);
    interp[r] = { k0, k1: Math.min(nbin - 1, k0 + 1), t: kf - k0 };
  }

  const re = new Float64Array(nfft);
  const im = new Float64Array(nfft);
  const mag = new Float64Array(nbin);
  for (let c = 0; c < cols; c++) {
    const off = c * hop;
    for (let i = 0; i < nfft; i++) {
      const s = off + i < samples.length ? samples[off + i] : 0;
      re[i] = s * win[i];
      im[i] = 0;
    }
    fft(re, im);
    for (let k = 0; k < nbin; k++) mag[k] = Math.hypot(re[k], im[k]) / norm;
    for (let r = 0; r < rows; r++) {
      let m = 0;
      const list = binsOf[r];
      if (list.length) {
        for (let i = 0; i < list.length; i++) if (mag[list[i]] > m) m = mag[list[i]];
      } else {
        const p = interp[r];
        m = mag[p.k0] * (1 - p.t) + mag[p.k1] * p.t;
      }
      const db = 20 * Math.log10(Math.max(m, 1e-12));
      data[c * rows + r] = Math.min(1, Math.max(0, (db - floorDb) / -floorDb));
    }
  }
  return { cols, rows, data };
}

/**
 * Tick times in seconds, every second, including 0 and loopSec.
 *
 * @param {number} loopSec Loop length in seconds.
 * @returns {number[]} Tick times.
 */
export function timeTicks(loopSec) {
  const out = [];
  for (let t = 0; t < loopSec; t += 1) out.push(t);
  out.push(loopSec);
  return out;
}

/**
 * Draws the Data strip: V1 step ticks in the top half, V2 in the bottom half.
 *
 * @param {CanvasRenderingContext2D} ctx Canvas context.
 * @param {number} w Width in CSS pixels.
 * @param {number} h Height in CSS pixels.
 * @param {PickerEvent[]} events Events.
 * @param {number} n1 Number of V1 levels.
 * @param {number} n2 Number of V2 levels.
 * @param {number} loopSec Loop length in seconds.
 * @param {VizColors} colors Colours.
 * @returns {void}
 */
export function drawData(ctx, w, h, events, n1, n2, loopSec, colors) {
  ctx.save();
  ctx.clearRect(0, 0, w, h);
  const half = h / 2;
  const pad = 3;
  const panels = [
    { top: 0, n: n1, key: 'v1', color: colors.v1, label: 'V1' },
    { top: half, n: n2, key: 'v2', color: colors.v2, label: 'V2' },
  ];
  ctx.lineWidth = 2;
  for (const p of panels) {
    const base = p.top + half - pad;
    const span = half - 2 * pad;
    ctx.strokeStyle = p.color;
    for (const ev of events) {
      const x = (ev.onset / loopSec) * w;
      const tw = Math.max(3, (ev.dur / loopSec) * w);
      const y = base - ((ev[p.key] + 1) / p.n) * span;
      ctx.globalAlpha = ev.dim ? 0.25 : 1;
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(Math.min(w, x + tw), y);
      if (x + tw > w) { ctx.moveTo(0, y); ctx.lineTo(x + tw - w, y); } // wraps like the audio and the score
      ctx.stroke();
    }
  }
  ctx.globalAlpha = 1;
  ctx.fillStyle = colors.muted;
  ctx.font = '11px system-ui';
  ctx.textBaseline = 'top';
  ctx.textAlign = 'left';
  ctx.fillText('V1', 4, 2);
  ctx.fillText('V2', 4, half + 2);
  ctx.restore();
}

/**
 * Draws the Score strip: one bar per event, lane by V1, colour by V2.
 * Bars that run past loopSec wrap to the start.
 *
 * @param {CanvasRenderingContext2D} ctx Canvas context.
 * @param {number} w Width in CSS pixels.
 * @param {number} h Height in CSS pixels.
 * @param {PickerEvent[]} events Events.
 * @param {number} n1 Number of lanes.
 * @param {number} n2 Number of V2 levels.
 * @param {number} loopSec Loop length in seconds.
 * @param {VizColors} colors Colours.
 * @param {string[]} ramp n2 colours for V2 levels.
 * @returns {void}
 */
export function drawScore(ctx, w, h, events, n1, n2, loopSec, colors, ramp) {
  ctx.save();
  ctx.clearRect(0, 0, w, h);
  const lane = h / n1;
  ctx.strokeStyle = colors.grid;
  ctx.lineWidth = 1;
  ctx.globalAlpha = 0.6;
  for (let i = 0; i <= n1; i++) {
    const y = Math.round(i * lane) + 0.5;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }
  const pxPerSec = w / loopSec;
  for (const ev of events) {
    const y = h - (ev.v1 + 1) * lane + 1;
    const bh = Math.max(1, lane - 2);
    const x = ev.onset * pxPerSec;
    const bw = Math.max(2, ev.dur * pxPerSec);
    ctx.globalAlpha = ev.dim ? 0.25 : 1;
    ctx.fillStyle = ramp[Math.min(ramp.length - 1, Math.max(0, ev.v2))];
    ctx.fillRect(x, y, Math.min(bw, w - x), bh);
    if (ev.onset + ev.dur > loopSec) {
      ctx.fillRect(0, y, Math.max(2, (ev.onset + ev.dur - loopSec) * pxPerSec), bh);
    }
  }
  ctx.restore();
}

/**
 * Draws the Waveform strip: L on top, R below, filled min/max envelope.
 * Vertical scale is fixed (+-1 fills each half).
 *
 * @param {CanvasRenderingContext2D} ctx Canvas context.
 * @param {number} w Width in CSS pixels.
 * @param {number} h Height in CSS pixels.
 * @param {RenderedBuffer} buf Rendered buffer.
 * @param {VizColors} colors Colours.
 * @returns {void}
 */
export function drawWave(ctx, w, h, buf, colors) {
  ctx.save();
  ctx.clearRect(0, 0, w, h);
  const half = h / 2;
  const nPix = Math.max(1, Math.ceil(w));
  const chans = [buf.L, buf.R];
  ctx.strokeStyle = colors.grid;
  ctx.lineWidth = 1;
  for (let c = 0; c < 2; c++) {
    const yc = half * c + half / 2;
    ctx.beginPath();
    ctx.moveTo(0, yc);
    ctx.lineTo(w, yc);
    ctx.stroke();
  }
  ctx.fillStyle = colors.accent;
  for (let c = 0; c < 2; c++) {
    const yc = half * c + half / 2;
    const amp = half / 2;
    const env = envelope(chans[c], nPix);
    for (let x = 0; x < nPix; x++) {
      const top = yc - Math.min(1, env.max[x]) * amp;
      const bot = yc - Math.max(-1, env.min[x]) * amp;
      ctx.fillRect(x, top, 1, Math.max(1, bot - top));
    }
  }
  ctx.restore();
}

/** Five-stop dark-to-light map (viridis-like), [r, g, b]. */
const SPEC_STOPS = [
  [8, 6, 28],
  [62, 74, 137],
  [38, 130, 142],
  [109, 205, 89],
  [253, 231, 37],
];

/**
 * Colour for a 0..1 spectrogram value.
 *
 * @param {number} v Value 0..1.
 * @returns {number[]} [r, g, b, a].
 */
function specColor(v) {
  const x = Math.min(1, Math.max(0, v)) * (SPEC_STOPS.length - 1);
  const i = Math.min(SPEC_STOPS.length - 2, Math.floor(x));
  const t = x - i;
  const a = SPEC_STOPS[i];
  const b = SPEC_STOPS[i + 1];
  return [
    a[0] + (b[0] - a[0]) * t,
    a[1] + (b[1] - a[1]) * t,
    a[2] + (b[2] - a[2]) * t,
    Math.round(255 * Math.min(1, 0.05 + v * 4)),
  ];
}

/**
 * Makes an offscreen canvas, or null when none is available.
 *
 * @param {CanvasRenderingContext2D} ctx Canvas context.
 * @param {number} cw Width in pixels.
 * @param {number} ch Height in pixels.
 * @returns {any} Canvas-like object or null.
 */
function makeOffscreen(ctx, cw, ch) {
  try {
    if (typeof OffscreenCanvas !== 'undefined') return new OffscreenCanvas(cw, ch);
    const doc = ctx.canvas && ctx.canvas.ownerDocument;
    if (doc) {
      const el = doc.createElement('canvas');
      el.width = cw;
      el.height = ch;
      return el;
    }
  } catch (e) {
    return null;
  }
  return null;
}

/**
 * Draws the Spectrogram strip with frequency tick labels.
 *
 * @param {CanvasRenderingContext2D} ctx Canvas context.
 * @param {number} w Width in CSS pixels.
 * @param {number} h Height in CSS pixels.
 * @param {Spec} spec Spectrogram.
 * @param {VizColors} colors Colours.
 * @returns {void}
 */
export function drawSpec(ctx, w, h, spec, colors) {
  ctx.save();
  ctx.clearRect(0, 0, w, h);
  const off = makeOffscreen(ctx, spec.cols, spec.rows);
  const octx = off && off.getContext && off.getContext('2d');
  if (octx && octx.createImageData) {
    const img = octx.createImageData(spec.cols, spec.rows);
    for (let c = 0; c < spec.cols; c++) {
      for (let r = 0; r < spec.rows; r++) {
        const rgba = specColor(spec.data[c * spec.rows + r]);
        const p = ((spec.rows - 1 - r) * spec.cols + c) * 4;
        img.data[p] = rgba[0];
        img.data[p + 1] = rgba[1];
        img.data[p + 2] = rgba[2];
        img.data[p + 3] = rgba[3];
      }
    }
    octx.putImageData(img, 0, 0);
    ctx.drawImage(off, 0, 0, spec.cols, spec.rows, 0, 0, w, h);
  }
  ctx.fillStyle = colors.muted;
  ctx.strokeStyle = colors.muted;
  ctx.lineWidth = 1;
  ctx.font = '11px system-ui';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  const ticks = [[100, '100 Hz'], [1000, '1 kHz'], [4000, '4 kHz']];
  for (const [f, label] of ticks) {
    const y = h * (1 - freqToFrac(f));
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(4, y);
    ctx.stroke();
    ctx.fillText(label, 6, y);
  }
  ctx.restore();
}

/**
 * Draws the playhead as a 1.5 px vertical line. Used by the viz tests; the page moves a DOM line instead.
 *
 * @param {CanvasRenderingContext2D} ctx Canvas context.
 * @param {number} w Width in CSS pixels.
 * @param {number} h Height in CSS pixels.
 * @param {number} frac Position 0..1 along the loop.
 * @param {VizColors} colors Colours.
 * @returns {void}
 */
export function drawPlayhead(ctx, w, h, frac, colors) {
  const x = frac * w;
  ctx.save();
  ctx.strokeStyle = colors.fg;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(x, 0);
  ctx.lineTo(x, h);
  ctx.stroke();
  ctx.restore();
}
