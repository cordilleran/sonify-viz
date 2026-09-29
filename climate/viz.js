/* Climate Pair visualizer: a spiral of year rings drawn in time with the music.
   One ring per year from 1958 at the centre to 2025 at the edge, January at the
   top, clockwise. Colour: global ocean surface temperature anomaly. Thickness:
   ENSO strength (|ONI|). Sparks: storms at their peak, sized by category.
   Atlantic: a pale sea-ice line along the inside of each ring from Nov 1978.
   Pacific: green blooms at the Kettle River's annual peak. Underneath: a
   timeline strip (scrub it), the current guide event, a dashboard of every
   layer's value this month beside its instrument's loudness, and hover
   readouts on the spiral and the strip (added 2026-09-27). Sunspots and ocean
   heat are shown as loudness only: their terms don't allow republishing values.
   Data: climate/viz_{basin}.json, written by scripts/export_climate_viz.py.
   The audio element's clock drives everything. No libraries. */
(() => {
  const root = document.getElementById("cviz");
  if (!root) return;
  const BASINS = ["pacific", "atlantic"];
  const AUDIO = b => `audio/climate_${b}_1958_2025.mp3`;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)");
  const C = { ground: "#0c1618", line: "#223538", text: "#dde7e4", muted: "#8aa0a0", river: "#5db4b8", sun: "#e7b44f" };
  // ocean surface anomaly (deg C) -> colour; cool blue through pale to ember
  const RAMP = [[-0.25, [27, 58, 82]], [0.1, [47, 127, 149]], [0.4, [143, 198, 184]], [0.7, [231, 180, 79]], [1.05, [232, 87, 60]]];
  const sstRGB = v => {
    if (v <= RAMP[0][0]) return RAMP[0][1];
    for (let i = 1; i < RAMP.length; i++) if (v <= RAMP[i][0]) {
      const [a, ca] = RAMP[i - 1], [b, cb] = RAMP[i], f = (v - a) / (b - a);
      return ca.map((c, k) => Math.round(c + f * (cb[k] - c)));
    }
    return RAMP[RAMP.length - 1][1];
  };
  const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
  const LAYERS = {
    drone: ["Drone", "CO₂", "R"], cello: ["Cellos", "ocean surface temp.", "R"], deep: ["Contrabass", "ocean heat", "R"],
    pulse: ["Pulse", "ENSO", "R"], pad: ["Pad", "PDO / AMO", "D"], storms: ["Drums", "storms", "R"],
    rumble: ["Rumble", "storm energy", "R"], shimmer: ["Shimmer", "sunspots", "R"], heat: ["High violin", "global temp.", "R"],
    events: ["Gong", "volcanoes", "D"], local: ["Harp bloom", "Kettle River", "R"], ice: ["Glass", "Arctic sea ice", "R"],
  };
  const STORM_TINT = { wpac: [200, 226, 255], nepac: [255, 226, 190], atl: [255, 236, 205] };
  const fmt = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
  const ffill = a => { let last = null; return a.map(v => (v == null ? last : (last = v))); };

  // ---------------------------------------------------------------- DOM ---
  root.innerHTML = `
    <div class="cviz-bar">
      <div class="cviz-seg" role="group" aria-label="Piece to hear">
        ${BASINS.map(b => `<button type="button" data-b="${b}">${b[0].toUpperCase() + b.slice(1)}</button>`).join("")}
      </div>
      <label class="cviz-both"><input type="checkbox"> both side by side</label>
    </div>
    <div class="cviz-stage">
      ${BASINS.map(b => `<figure data-b="${b}"><canvas role="img"></canvas><figcaption></figcaption></figure>`).join("")}
    </div>
    <p class="cviz-caption"><span class="t"></span><span class="e"></span></p>
    <div class="cviz-dash" role="table" aria-label="Each layer's value this month and how loud its instrument is"></div>
    <canvas class="cviz-strip" tabindex="0" aria-label="Timeline, 1958 to 2025. Click, drag, or use the arrow keys to move by a year."></canvas>
    <audio controls preload="metadata"></audio>
    <div class="cviz-layers" aria-hidden="true"></div>
    <div class="cviz-tip" aria-hidden="true"></div>`;
  const audio = root.querySelector("audio");
  const strip = root.querySelector(".cviz-strip");
  const both = root.querySelector(".cviz-both input");
  const cap = root.querySelector(".cviz-caption");
  const figs = Object.fromEntries(BASINS.map(b => [b, root.querySelector(`figure[data-b="${b}"]`)]));
  let heard = "pacific", started = false, D = {}, geo = {}, pendingT = null;
  // until the audio has loaded, a deep link or a scrub holds the time itself
  const curT = () => (pendingT != null && audio.readyState < 1 ? pendingT : audio.currentTime || 0);
  const setT = s => { if (audio.readyState < 1) pendingT = s; else audio.currentTime = s; };
  audio.addEventListener("loadedmetadata", () => { if (pendingT != null) { audio.currentTime = pendingT; pendingT = null; } });

  // --------------------------------------------------------- geometry ---
  function layout(b, size) {
    const d = D[b], cvs = figs[b].querySelector("canvas"), dpr = Math.min(devicePixelRatio || 1, 2);
    cvs.width = cvs.height = Math.round(size * dpr);
    cvs.style.width = cvs.style.height = size + "px";
    const cx = size / 2, R = size / 2 - 10, r0 = size * 0.16, sp = (R - r0) / d.years;
    const pos = (u, off = 0) => {        // u: years since Jan 1958 (continuous)
      const a = -Math.PI / 2 + 2 * Math.PI * (u % 1), r = r0 + sp * u + off;
      return [cx + r * Math.cos(a), cx + r * Math.sin(a)];
    };
    const k = size / 620;
    geo[b] = {
      cvs, ctx: cvs.getContext("2d"), dpr, size, cx, R, r0, sp, pos, k,
      storms: d.storms.map(s => {
        const [t, cat, bi] = s, j = ((Math.sin(t * 12.9898) * 43758.5453) % 1) * 0.8;   // fixed jitter across the ring
        return { t, cat, basin: d.storm_basins[bi], land: s[3], xy: pos(t / d.bar, sp * j), r: (0.45 + 0.38 * cat) * k };
      }),
    };
  }

  function segPath(ctx, g, u0, u1, off = 0) {
    const n = Math.max(2, Math.ceil((u1 - u0) * 72));
    ctx.beginPath();
    for (let i = 0; i <= n; i++) {
      const [x, y] = g.pos(u0 + (u1 - u0) * i / n, off);
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    }
  }

  const envAt = (d, key, t) => {
    const e = d.env[key];
    if (!e) return 0;
    const i = Math.min(e.length - 1, Math.max(0, Math.floor(t * d.env_hz)));
    return e[i] / 100;
  };

  // ------------------------------------------------------------- spiral ---
  function drawSpiral(b, t) {
    const d = D[b], g = geo[b];
    if (!g) return;
    const { ctx, dpr, size, cx, r0, sp, k } = g;
    const poster = !started || audio.ended;
    const uNow = poster ? d.years : Math.min(d.years, t / d.bar);
    const live = !poster && b === heard, motion = !reduce.matches;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size, size);

    // drone (CO2) glow behind everything; the deep ocean's glow at the centre
    const drone = poster ? 0.5 : envAt(d, "drone", t), deep = poster ? 0.4 : envAt(d, "deep", t);
    let gr = ctx.createRadialGradient(cx, cx, r0 * 0.5, cx, cx, size / 2);
    gr.addColorStop(0, rgba([93, 180, 184], 0.05 + 0.10 * drone));
    gr.addColorStop(1, "rgba(12,22,24,0)");
    ctx.fillStyle = gr; ctx.fillRect(0, 0, size, size);
    gr = ctx.createRadialGradient(cx, cx, 0, cx, cx, r0);
    gr.addColorStop(0, rgba([30, 70, 120], 0.15 + 0.5 * deep));
    gr.addColorStop(1, "rgba(30,70,120,0)");
    ctx.fillStyle = gr; ctx.beginPath(); ctx.arc(cx, cx, r0, 0, 7); ctx.fill();

    // ghost of the years still to come
    if (uNow < d.years) {
      ctx.strokeStyle = "rgba(138,160,160,0.13)"; ctx.lineWidth = sp * 0.35;
      segPath(ctx, g, uNow, d.years); ctx.stroke();
    }
    // the rings: one stroke per month
    const sst = d._sst, oni = d._oni, ice = d.monthly.ice;
    ctx.lineCap = "butt";
    const mEnd = Math.min(d.years * 12, Math.ceil(uNow * 12));
    for (let m = 0; m < mEnd; m++) {
      ctx.strokeStyle = rgba(sstRGB(sst[m]), 1);
      ctx.lineWidth = sp * (0.3 + 0.6 * Math.min(1, Math.abs(oni[m]) / 2));
      segPath(ctx, g, m / 12, Math.min(uNow, (m + 1) / 12 + 0.0015)); ctx.stroke();
    }
    if (ice) {                                      // sea ice: a pale line inside the ring, its own pass
      ctx.strokeStyle = "rgb(196,214,226)";
      for (let m = 0; m < mEnd; m++) {
        if (ice[m] == null) continue;
        ctx.lineWidth = Math.max(0.3, sp * 0.3 * ice[m] / 16.5);
        segPath(ctx, g, m / 12, Math.min(uNow, (m + 1) / 12), -sp * 0.45); ctx.stroke();
      }
    }
    // volcanoes: a small grey mark outside the ring
    for (const v of d.volcanoes) {
      if (v.t > (poster ? 1e9 : t)) continue;
      const [x, y] = g.pos(v.t / d.bar, sp * 1.1), age = t - v.t;
      ctx.fillStyle = "rgba(170,170,170,0.85)";
      ctx.beginPath(); ctx.arc(x, y, 2.2 * k, 0, 7); ctx.fill();
      if (live && motion && age < 14) {             // ~2 years of ash haze
        ctx.strokeStyle = `rgba(150,150,150,${0.25 * (1 - age / 14)})`; ctx.lineWidth = 3 * k;
        ctx.beginPath(); ctx.arc(x, y, (6 + age * 1.2) * k, 0, 7); ctx.stroke();
      }
    }
    // Kettle River peaks: green blooms
    for (const kp of d.kettle || []) {
      if (!poster && kp.t > t) continue;
      const [x, y] = g.pos(kp.t / d.bar, sp * 0.9), age = t - kp.t, r = (1 + 2.2 * kp.rank) * k;
      ctx.fillStyle = "rgba(150,214,140,0.8)";
      ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill();
      if (live && motion && age < 2.5) {
        ctx.fillStyle = `rgba(150,214,140,${0.4 * (1 - age / 2.5)})`;
        ctx.beginPath(); ctx.arc(x, y, r + age * 9 * k * (0.4 + kp.rank), 0, 7); ctx.fill();
      }
    }
    // storms: sparks, and a flare as each one sounds
    for (const s of g.storms) {
      if (!poster && s.t > t) break;
      const tint = STORM_TINT[s.basin], age = t - s.t;
      ctx.fillStyle = rgba(tint, s.cat >= 5 ? 0.95 : 0.2 + 0.1 * s.cat);
      ctx.beginPath(); ctx.arc(s.xy[0], s.xy[1], s.r, 0, 7); ctx.fill();
      if (live && motion && age < 1.6 && s.cat >= 1) {
        const a = 1 - age / 1.6;
        ctx.fillStyle = rgba(tint, 0.28 * a * (s.cat / 5 + 0.2));
        ctx.beginPath(); ctx.arc(s.xy[0], s.xy[1], s.r + (4 + 5 * s.cat) * k * (0.3 + age), 0, 7); ctx.fill();
        if (s.land) {
          ctx.strokeStyle = rgba(tint, 0.6 * a); ctx.lineWidth = 1;
          ctx.beginPath(); ctx.arc(s.xy[0], s.xy[1], s.r + 3 * k + age * 10 * k, 0, 7); ctx.stroke();
        }
      }
    }
    // heat: an outer halo once the high violin plays
    const heat = poster ? 0 : envAt(d, "heat", t);
    if (heat > 0.2) {
      ctx.strokeStyle = rgba([232, 87, 60], 0.5 * (heat - 0.2));
      ctx.lineWidth = 3 * k;
      ctx.beginPath(); ctx.arc(cx, cx, g.R + 5, 0, 7); ctx.stroke();
    }
    // the playhead, with shimmer (sunspots) as twinkles around it
    if (!poster) {
      const [px, py] = g.pos(uNow);
      gr = ctx.createRadialGradient(px, py, 0, px, py, 16 * k);
      gr.addColorStop(0, "rgba(255,250,235,0.95)"); gr.addColorStop(1, "rgba(255,250,235,0)");
      ctx.fillStyle = gr; ctx.beginPath(); ctx.arc(px, py, 16 * k, 0, 7); ctx.fill();
      const sh = envAt(d, "shimmer", t);
      if (live && motion && sh > 0.25) {
        for (let i = 0; i < 6; i++) {
          const ph = t * 1.7 + i * 2.4, rr = (18 + 14 * ((i * 37) % 7) / 7) * k;
          const a = (0.5 + 0.5 * Math.sin(ph * 3.1)) * (sh - 0.25);
          ctx.fillStyle = `rgba(255,236,190,${a})`;
          ctx.beginPath(); ctx.arc(px + rr * Math.cos(ph), py + rr * Math.sin(ph), 1.1 * k, 0, 7); ctx.fill();
        }
      }
    }
    // centre: the year and the CO2 reading
    const yi = Math.min(d.years - 1, Math.floor(uNow - (poster ? 1 : 0))), yr = d.yearly[Math.max(0, yi)];
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillStyle = C.text;
    ctx.font = `${Math.round(size * (poster ? 0.05 : 0.068))}px Gloock, Georgia, serif`;
    ctx.fillText(poster ? "1958–2025" : String(yr.year), cx, cx - size * 0.012);
    ctx.fillStyle = C.muted;
    ctx.font = `${Math.max(9, Math.round(size * 0.02))}px "JetBrains Mono", monospace`;
    ctx.fillText(poster ? (b === heard ? "press play" : "") : `CO₂ ${yr.co2_ppm} ppm`, cx, cx + size * 0.045);
    if (!poster) ctx.fillText(yr.mode, cx, cx + size * 0.075);
  }

  // -------------------------------------------------------------- strip ---
  function drawStrip(t) {
    const d = D[heard];
    const dpr = Math.min(devicePixelRatio || 1, 2), w = strip.clientWidth, lanes = d.monthly.ice ? 5 : 4;
    const lh = 17, h = lanes * lh + 22;
    if (strip.width !== Math.round(w * dpr) || strip.height !== Math.round(h * dpr)) {
      strip.width = Math.round(w * dpr); strip.height = Math.round(h * dpr); strip.style.height = h + "px";
    }
    const ctx = strip.getContext("2d"), L = 92, W = w - L - 4, span = d.years * d.bar;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
    const xt = s => L + (s / span) * W, now = started ? t : span;
    const lane = (i, label, fn) => {
      const y0 = i * lh + 2;
      ctx.fillStyle = C.muted; ctx.font = '10px "JetBrains Mono", monospace'; ctx.textAlign = "right"; ctx.textBaseline = "middle";
      ctx.fillText(label, L - 8, y0 + lh / 2);
      fn(y0, lh - 3);
    };
    const monthly = (arr, lo, hi, colour) => (y0, hh) => {
      for (let m = 0; m < arr.length; m++) {
        if (arr[m] == null) continue;
        const v = Math.max(0, Math.min(1, (arr[m] - lo) / (hi - lo))), x = xt(m * d.bar / 12);
        ctx.fillStyle = colour(arr[m], m * d.bar / 12 <= now);
        ctx.fillRect(x, y0 + hh * (1 - v), Math.max(1, W / arr.length), hh * v + 0.5);
      }
    };
    const dim = (c, on) => rgba(c, on ? 0.9 : 0.25);
    lane(0, "CO₂", monthly(d.monthly.co2, 300, 430, (v, on) => dim([93, 180, 184], on)));
    lane(1, "ocean temp.", monthly(d._sst, -0.35, 1.05, (v, on) => dim(sstRGB(v), on)));
    lane(2, "ENSO", (y0, hh) => {
      const mid = y0 + hh / 2;
      d._oni.forEach((v, m) => {
        const x = xt(m * d.bar / 12), on = m * d.bar / 12 <= now;
        ctx.fillStyle = dim(v > 0 ? [232, 87, 60] : [93, 150, 210], on);
        ctx.fillRect(x, v > 0 ? mid - hh / 2 * Math.min(1, v / 2.5) : mid, Math.max(1, W / d._oni.length), hh / 2 * Math.min(1, Math.abs(v) / 2.5));
      });
    });
    lane(3, "storm energy", (y0, hh) => {
      const mx = Math.max(...d.yearly.map(y => y.ace));
      d.yearly.forEach((y, i) => {
        const v = y.ace / mx, on = i * d.bar <= now;
        ctx.fillStyle = dim([255, 236, 205], on);
        ctx.fillRect(xt(i * d.bar) + 0.5, y0 + hh * (1 - v), Math.max(1, W / d.years - 1), hh * v);
      });
    });
    if (d.monthly.ice) lane(4, "sea ice", monthly(d.monthly.ice, 0, 17, (v, on) => dim([226, 240, 255], on)));
    // decade ticks and the playhead
    const yb = lanes * lh + 4;
    ctx.fillStyle = C.muted; ctx.textAlign = "center"; ctx.textBaseline = "top"; ctx.font = '10px "JetBrains Mono", monospace';
    for (let yr = 1960; yr <= 2020; yr += 10) ctx.fillText(yr, xt((yr - d.y0) * d.bar), yb + 3);
    if (started) {
      ctx.fillStyle = "#fffaf0"; ctx.fillRect(xt(Math.min(t, span)) - 0.75, 0, 1.5, yb + 2);
    }
    ctx.strokeStyle = C.line; ctx.beginPath(); ctx.moveTo(L, yb + 0.5); ctx.lineTo(L + W, yb + 0.5); ctx.stroke();
    strip._x = [L, W, span];
  }

  // ---------------------------------------------------- caption, chips ---
  const chips = root.querySelector(".cviz-layers");
  function buildChips() {
    const d = D[heard];
    chips.innerHTML = Object.keys(LAYERS).filter(k => d.env[k]).map(k => {
      let [ins, data, tag] = LAYERS[k];
      if (k === "local" && heard === "atlantic") [ins, data] = ["Winter wind", "NAO"];
      if (k === "pad") data = heard === "pacific" ? "PDO" : "AMO";
      return `<span class="chip" data-k="${k}"><b>${ins}</b> ${data} <span class="src ${tag}">${tag}</span></span>`;
    }).join("");
  }
  let lastEv = null;
  function updateText(t) {
    const d = D[heard];
    const on = started && !audio.ended;
    for (const el of chips.children) {
      const v = on ? envAt(d, el.dataset.k, t) : 0;
      el.style.setProperty("--lvl", Math.max(0, (v - 0.3) / 0.55).toFixed(2));
    }
    let ev = null;
    if (on) for (const e of d.events) { if (e[0] <= t) { if (t - e[0] < 9) ev = e; } else break; }
    if (ev !== lastEv) {
      lastEv = ev;
      cap.querySelector(".t").textContent = ev ? fmt(ev[0]) : "";
      cap.querySelector(".e").textContent = ev ? ev[1].replace(/ - /g, " · ") : (on ? "" : "Every timed event from the listening guide appears here as it sounds.");
    }
  }

  // ----------------------------------------------------------- readouts ---
  const MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const sgn = (v, dp) => (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(dp);
  const at = (arr, m) => (arr && m >= 0 && m < arr.length ? arr[m] : null);
  const ensoWord = v => (v >= 0.5 ? "El Niño range" : v <= -0.5 ? "La Niña range" : "neutral");
  const monthOf = (d, t) => Math.max(0, Math.min(d.years * 12 - 1, Math.floor(t / d.bar * 12)));
  // one value per layer for month m of basin d, as text (null: no reading); kept to what may be published
  function layerValue(k, d, m, b) {
    const yi = Math.floor(m / 12), yr = d.yearly[yi], y0 = yi * d.bar, y1 = y0 + d.bar;
    switch (k) {
      case "drone": { const v = at(d.monthly.co2, m); return v == null ? null : `${v.toFixed(1)} ppm`; }
      case "cello": { const v = at(d.monthly.sst, m); return v == null ? null : `${sgn(v, 2)} °C`; }
      case "heat": { const v = at(d.monthly.gistemp, m); return v == null ? null : `${sgn(v, 2)} °C`; }
      case "pulse": { const v = at(d.monthly.oni, m); return v == null ? null : `ONI ${sgn(v, 1)} · ${ensoWord(v)}`; }
      case "pad": { const v = at(d.monthly.mode_index, m); return v == null ? null : `${b === "pacific" ? "PDO" : "AMO"} ${sgn(v, 2)}`; }
      case "ice": { const v = at(d.monthly.ice, m); return v == null ? "no record yet" : `${v.toFixed(2)} M km²`; }
      case "rumble": return yr ? `ACE ${Math.round(yr.ace)} (${yr.year})` : null;
      case "storms": {
        const tEnd = y0 + (m % 12 + 1) / 12 * d.bar, ss = d.storms.filter(s => s[0] >= y0 && s[0] < Math.min(y1, tEnd));
        return `${ss.length} by ${MON[m % 12]} · top cat. ${ss.length ? Math.max(...ss.map(s => s[1])) : "–"}`;
      }
      case "events": { const v = d.volcanoes.filter(v => v.t <= (m + 1) / 12 * d.bar && (m + 1) / 12 * d.bar - v.t < 2 * d.bar).pop();
        return v ? v.name.split(",")[0] : "none recent"; }
      case "local":
        if (b === "atlantic") { const v = at(d.monthly.nao, m); return v == null ? null : `NAO ${sgn(v, 2)}`; }
        { const kp = (d.kettle || []).find(x => x.t >= y0 && x.t < y1); return kp ? `${kp.q} m³/s peak` : null; }
      case "deep": case "shimmer": return "heard only";
    }
    return null;
  }
  const HEARD_ONLY = "Shown only as loudness: the source's terms don't allow republishing its values here.";
  const dash = root.querySelector(".cviz-dash");
  function buildDash() {
    const d = D[heard];
    dash.innerHTML = `<div class="hd" role="row"><span role="columnheader">Layer · this month</span><span role="columnheader">Instrument · how loud now</span></div>` +
      Object.keys(LAYERS).filter(k => d.env[k]).map(k => {
        let [ins, data, tag] = LAYERS[k];
        if (k === "local" && heard === "atlantic") [ins, data] = ["Winter wind", "NAO"];
        if (k === "pad") data = heard === "pacific" ? "PDO" : "AMO";
        const ho = k === "deep" || k === "shimmer";
        return `<div class="drow" role="row" data-k="${k}"${ho ? ` title="${HEARD_ONLY}"` : ""}><span class="lab" role="cell">${data}</span>` +
          `<span class="val${ho ? " none" : ""}" role="cell"></span><span class="src ${tag}" role="cell">${tag}</span>` +
          `<span class="ins" role="cell"><span>${ins}</span><span class="m"><i></i></span></span></div>`;
      }).join("") + `<p class="note">Ocean heat and sunspots are heard, not shown: their data terms don't allow republishing the values. Storm energy is the year's accumulated cyclone energy (ACE).</p>`;
  }
  function updateDash(t) {
    const d = D[heard], m = monthOf(d, started ? t : d.years * d.bar - 0.01), on = started && !audio.ended;
    dash.querySelector(".hd span").textContent = `Layer · ${MON[m % 12]} ${d.y0 + Math.floor(m / 12)}`;
    for (const row of dash.querySelectorAll(".drow")) {
      const k = row.dataset.k, v = layerValue(k, d, m, heard), e = on ? envAt(d, k, t) : 0;
      const val = row.querySelector(".val"); val.textContent = v == null ? "no reading" : v;
      row.querySelector(".m i").style.width = (100 * Math.max(0, (e - 0.3) / 0.55)).toFixed(0) + "%";
    }
  }
  const tip = root.querySelector(".cviz-tip");
  function showTip(clientX, clientY, html) {
    const rr = root.getBoundingClientRect();
    tip.innerHTML = html; tip.classList.add("on");
    let x = clientX - rr.left + 14, y = clientY - rr.top + 14;
    if (x + tip.offsetWidth > rr.width - 4) x = clientX - rr.left - tip.offsetWidth - 14;
    tip.style.left = Math.max(4, x) + "px"; tip.style.top = y + "px";
  }
  const hideTip = () => tip.classList.remove("on");
  function monthTip(b, m, extra) {
    const d = D[b], keys = ["cello", "pulse", "drone", "heat", "pad"].concat(b === "atlantic" ? ["ice"] : []);
    const rows = keys.map(k => [k === "pad" ? "" : LAYERS[k][1], layerValue(k, d, m, b)]).filter(r => r[1] != null);
    return `<b>${MON[m % 12]} ${d.y0 + Math.floor(m / 12)}</b>${b !== heard ? ` <span class="d">· ${b}</span>` : ""}` +
      rows.map(([lab, v]) => `<div>${lab ? `<span class="d">${lab}</span> ` : ""}<span class="v">${v}</span></div>`).join("") + (extra || "");
  }
  // spiral: angle gives the month, radius the year; nearby storms, peaks and eruptions are named
  function onSpiral(b, e) {
    const g = geo[b], d = D[b]; if (!g) return;
    const r = g.cvs.getBoundingClientRect(), k = g.size / r.width;
    const x = (e.clientX - r.left) * k, y = (e.clientY - r.top) * k, dx = x - g.cx, dy = y - g.cx;
    let f = (Math.atan2(dy, dx) + Math.PI / 2) / (2 * Math.PI); f -= Math.floor(f);
    const n = Math.round((Math.hypot(dx, dy) - g.r0) / g.sp - f);
    if (n < 0 || n >= d.years || Math.abs(Math.hypot(dx, dy) - (g.r0 + g.sp * (n + f))) > g.sp * 0.8) { hideTip(); return; }
    const m = n * 12 + Math.min(11, Math.floor(f * 12)), near = 7 * g.k;
    let extra = "";
    const st = g.storms.filter(s => Math.hypot(s.xy[0] - x, s.xy[1] - y) < Math.max(near, s.r + 2)).sort((a, c) => c.cat - a.cat)[0];
    if (st) extra += `<div class="w">A category ${st.cat} storm at its peak${st.land ? ", with landfall" : ""} (${{ wpac: "West Pacific", nepac: "Northeast Pacific", atl: "Atlantic" }[st.basin]})</div>`;
    const kp = (d.kettle || []).find(p => { const [px, py] = g.pos(p.t / d.bar, g.sp * 0.9); return Math.hypot(px - x, py - y) < near + 3 * g.k; });
    if (kp) extra += `<div class="w">Kettle River's peak for the year: ${kp.q} m³/s</div>`;
    const vo = d.volcanoes.find(v => { const [px, py] = g.pos(v.t / d.bar, g.sp * 1.1); return Math.hypot(px - x, py - y) < near + 3 * g.k; });
    if (vo) extra += `<div class="w">Eruption: ${vo.name}</div>`;
    showTip(e.clientX, e.clientY, monthTip(b, m, extra));
  }
  for (const b of BASINS) {
    const c = figs[b].querySelector("canvas");
    c.addEventListener("pointermove", e => onSpiral(b, e));
    c.addEventListener("pointerdown", e => { if (e.pointerType !== "mouse") onSpiral(b, e); });  // a tap reads the month too
    c.addEventListener("pointerleave", hideTip);
  }
  // strip: the lane under the pointer, at that month
  const STRIP_LANES = ["drone", "cello", "pulse", "rumble", "ice"];
  function onStrip(e) {
    const d = D[heard]; if (!strip._x) return;
    const [L, W, span] = strip._x, r = strip.getBoundingClientRect(), x = e.clientX - r.left, i = Math.floor((e.clientY - r.top - 2) / 17);
    if (x < L || x > L + W || i < 0 || i >= (d.monthly.ice ? 5 : 4)) { hideTip(); return; }
    const m = monthOf(d, (x - L) / W * span), k = STRIP_LANES[i];
    showTip(e.clientX, e.clientY, `<b>${MON[m % 12]} ${d.y0 + Math.floor(m / 12)}</b><div><span class="d">${LAYERS[k][1]}</span> <span class="v">${layerValue(k, d, m, heard) ?? "no reading"}</span></div>`);
  }
  strip.addEventListener("pointerleave", hideTip);

  // --------------------------------------------------------------- loop ---
  function frame() {
    const t = curT();
    for (const b of BASINS) if (!figs[b].hidden) drawSpiral(b, t);
    drawStrip(t); updateText(t); updateDash(t);
  }
  let raf = 0;
  const loop = () => { frame(); raf = audio.paused ? 0 : requestAnimationFrame(loop); };
  const kick = () => { if (!raf) raf = requestAnimationFrame(loop); };

  function sizeAll() {
    if (!D[heard]) return;  // the ResizeObserver can fire before the data arrives
    const w = root.querySelector(".cviz-stage").clientWidth;
    const pair = both.checked, side = pair && w >= 640;
    const size = Math.floor(Math.min(pair ? (side ? (w - 24) / 2 : w) : w, 620));
    root.classList.toggle("pair", pair);
    for (const b of BASINS) {
      figs[b].hidden = !pair && b !== heard;
      figs[b].classList.toggle("heard", b === heard);
      if (!figs[b].hidden && (!geo[b] || geo[b].size !== size)) layout(b, size);
      figs[b].querySelector("figcaption").innerHTML = pair
        ? `<b>${b[0].toUpperCase() + b.slice(1)}</b>${b === heard ? " · playing" : ` · <button type="button" data-b="${b}">hear this one</button>`}` : "";
    }
    frame();
  }

  function choose(b) {
    if (b === heard && audio.src) return;
    const t = curT(), playing = !audio.paused;
    heard = b;
    root.querySelectorAll(".cviz-seg button").forEach(x => x.setAttribute("aria-pressed", String(x.dataset.b === b)));
    audio.src = AUDIO(b);
    if (started) {
      pendingT = t;
      if (playing) audio.addEventListener("loadedmetadata", () => audio.play(), { once: true });
    }
    buildChips(); buildDash(); lastEv = undefined; sizeAll();
  }

  // ------------------------------------------------------------- events ---
  root.addEventListener("click", e => { const btn = e.target.closest("button[data-b]"); if (btn) choose(btn.dataset.b); });
  both.addEventListener("change", sizeAll);
  audio.addEventListener("play", () => { started = true; kick(); });
  for (const ev of ["seeked", "timeupdate", "ended", "pause"]) audio.addEventListener(ev, () => { if (!raf) frame(); });
  const seekTo = clientX => {
    const [L, W, span] = strip._x, r = strip.getBoundingClientRect();
    started = true;
    setT(Math.max(0, Math.min(span, ((clientX - r.left - L) / W) * span)));
    frame();
  };
  let drag = false;
  strip.addEventListener("pointerdown", e => { drag = true; strip.setPointerCapture(e.pointerId); seekTo(e.clientX); });
  strip.addEventListener("pointermove", e => { if (drag) { seekTo(e.clientX); hideTip(); } else onStrip(e); });
  strip.addEventListener("pointerup", () => { drag = false; });
  strip.addEventListener("keydown", e => {
    const step = { ArrowRight: 7, ArrowLeft: -7, PageUp: 70, PageDown: -70 }[e.key];
    if (step === undefined) return;
    e.preventDefault(); started = true;
    setT(Math.max(0, curT() + step)); frame();
  });
  // Space plays and pauses, as on the other pieces (not while typing or on a control that uses it)
  window.addEventListener("keydown", e => {
    if (e.code !== "Space" || ["BUTTON", "SELECT", "INPUT", "TEXTAREA", "AUDIO"].includes(e.target.tagName)) return;
    e.preventDefault(); audio.paused ? audio.play().catch(() => {}) : audio.pause();
  });
  new ResizeObserver(() => sizeAll()).observe(root.querySelector(".cviz-stage"));
  reduce.addEventListener?.("change", frame);

  // --------------------------------------------------------------- load ---
  Promise.all(BASINS.map(b => fetch(`climate/viz_${b}.json`).then(r => r.json()).then(d => {
    d._sst = ffill(d.monthly.sst); d._oni = ffill(d.monthly.oni); D[b] = d;
  }))).then(() => document.fonts.ready).then(() => {
    for (const b of BASINS) figs[b].querySelector("canvas").setAttribute("aria-label",
      `${b} piece as a spiral of year rings, 1958 at the centre to 2025 at the edge; colour is ocean surface temperature, thickness is ENSO strength, sparks are storms`);
    // deep links: ?piece=atlantic&year=1998&both=1
    const q = new URLSearchParams(location.search), yr = parseInt(q.get("year"), 10);
    both.checked = q.get("both") === "1";
    choose(q.get("piece") === "atlantic" ? "atlantic" : "pacific");
    if (yr >= 1958 && yr <= 2025) {
      started = true;
      setT((yr - 1958 + 0.99) * 7);
      frame();
    }
  }).catch(err => { root.insertAdjacentHTML("beforeend", `<p class="cviz-err">The visualizer could not load its data (${err}). The audio players below still work.</p>`); });
})();
