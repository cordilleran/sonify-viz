"""
ARCTIC ROUND, B-side (2026-10-08): "The Wheel". One unbroken take, 48 ice years, cello and organ, in the process-music manner.
Design: reconciled from two independent model reviews of the first design; the decisions are listed in arctic-bside/README.md (Design notes).

    python arctic_bside.py [--set bar_s=16] [--set name=...]      (a bare run uses DEFAULTS, an earlier mix, and writes arctic_bside_v1)
    Take 3, the published B-side:  python arctic_bside.py --set organ_gain=6.5 --set bass_gain=1.1 --set name=arctic_bside_v2

THE PROCESS
  Organ   an 8-note wheel (C3 G3 C4 Eb4 F4 G4 Bb4 C5) turns at a constant pulse, 52 pulses a bar (one a week). The order and the pulse
          never change. The wheel's slots are gated by total extent: as the ice shrinks, the highest and lowest notes fall
          silent first and the middle notes hold longest. This ranks notes, not seas: no note stands for a region. A silenced slot is a rest, not a fade: the notes that remain
          sound at the same touch as in 1979 (D from extent, R). Because 52 is not a multiple of 8 (52 mod 8 = 4), the wheel's phase against the bar line shifts by four slots every year, so a year starts on slot 0, the next on slot 4, and so on: two alternating phases, not a drift.
  Cello   one note every two months. Its register follows PIOMAS volume (M): thick ice low and warm, thin ice high and bare.
  Bass    a contrabass pedal on C2, present while the 12-month volume mean is high; it fades out through the record and does not
          return in winter (volume in March is lower now too).
  Time    every bar is exactly bar_s seconds. Inside a bar the pulses press slightly during freeze-up (-8 %) and drag during
          melt (+10 %): thermal inertia as rubato. Data are smoothed (3 weeks extent, 2 months volume) so satellite noise is not played.
  Room    the reverb crossfades from a dry, dark room (ice) to a wide bright one (open water).
  End     after the last ice year (to 30 Sep 2026) six October days of refreeze: the wheel restarts with a few notes, the cello holds
          an open fifth G4-D5, no bass, and it is left unresolved.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sampler as S
from sampler import Bus, Instrument, make_ir, SR
import dsp_core as W
import arctic_data as A

WHEEL = [48, 55, 60, 63, 65, 67, 70, 72]                 # C3 G3 C4 Eb4 F4 G4 Bb4 C5
CELLO = [39, 41, 43, 48, 55, 60, 63, 67, 72]             # Eb2 F2 G2 C3 G3 C4 Eb4 G4 C5, low and warm to high and bare
DEFAULTS = {"bar_s": 16.0, "tail_s": 24.0, "coda_s": 7.0, "seed": 2026, "name": "arctic_bside_v1", "y0": 1979, "y1": 2026,
            "rubato": True, "bass": True, "organ_gain": 1.6, "cello_gain": 1.3, "bass_gain": 0.55, "cello_attack_s": 1.1, "swell": True, "openwater_octave": True, "ext_range": [3.4, 16.0], "vol_range": [4.0, 32.0], "bass_gate": [14.0, 24.0]}


# The rules below are shared with export_bside_viz.py, so the picture and the sound cannot drift apart.
WHEEL_EXT = [7.2, 12.0, 17.5]       # total extent (M km2) at which 6, 7 and 8 notes sound; the lowest anchor is ext_range[0] (2 notes)
OPEN_WATER_REF = 17.5               # open water = 1 - extent / this
OPEN_WATER_FROM = 0.45              # the organ's upper octave enters above this open-water fraction
SWELL_EXT, SWELL_LEVEL = [3.4, 16.5], [0.15, 1.0]   # strings level as a function of extent
ICE_ENV_REF = 16.0                  # the room is "iced" in proportion to extent / this
RUBATO_PRESS, RUBATO_DRAG = 0.08, 0.10


def rubato_weights(ext, on=True):
    """Relative length of each weekly pulse: pressed in freeze-up, dragged in melt. The bar's total length is fixed elsewhere."""
    d_ext = np.gradient(ext)
    r = np.clip(d_ext / (np.abs(d_ext).max() + 1e-9), -1, 1)           # +1 fastest freeze, -1 fastest melt
    return 1.0 - RUBATO_PRESS * np.clip(r, 0, 1) + RUBATO_DRAG * np.clip(-r, 0, 1) if on else np.ones(len(ext))


def open_water(ext):
    return float(np.clip(1 - ext / OPEN_WATER_REF, 0, 1))


def swell(ext):
    return np.interp(ext, SWELL_EXT, SWELL_LEVEL)


def cello_index(v, vlo, vhi):
    """Register step 0 (Eb2, thick ice) to 8 (C5, thin ice) from PIOMAS volume."""
    return int(np.clip(np.round(np.interp(v, [vlo, vhi], [8, 0])), 0, 8))


def bass_gate(vol_mean, gate):
    return float(np.clip(np.interp(vol_mean, gate, [0, 1]), 0, 1))


def weekly_extent(D, label):
    """52 weekly mean extents for the ice year (Oct 1 .. Sep 30) and their dates."""
    days = A.bar_days("ice", label)
    idx = np.clip([(d - D["first"]).days for d in days], 0, D["n"] - 1)
    x = D["total"][idx]
    return np.array([x[7 * k:7 * k + 7].mean() for k in range(52)]), days


def smooth(x, w):
    p = w // 2
    return np.convolve(np.pad(x, (p, w - 1 - p), mode="edge"), np.ones(w) / w, "valid")


def active_slots(ext, lo, hi):
    """Notes sounding in the wheel for a given total extent. Piecewise: the 1979-88 September mean (7.2) keeps six of eight notes,
    the 2012 record low (3.6) keeps two, a full March (16+) all eight. Straight-line scaling from 3.4 to 16 would leave 1979
    and 2020 only one note apart in September, which hides the loss the piece is about."""
    n = int(np.clip(np.round(np.interp(ext, [lo] + WHEEL_EXT, [2, 6, 7, 8])), 2, 8))
    start = (8 - n) // 2
    return n, set(range(start, start + n))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", action="append", default=[])
    a = ap.parse_args(argv)
    P = dict(DEFAULTS)
    for s in a.set:
        k, _, v = s.partition("=")
        if k not in P:
            raise SystemExit(f"unknown parameter {k!r}; known: {sorted(P)}")
        P[k] = yaml.safe_load(v)
    OUT, HEAVY = W.LIGHT_OUT / "arctic", W.HEAVY_OUT / "arctic"
    OUT.mkdir(parents=True, exist_ok=True)
    HEAVY.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(P["seed"])
    D = A.load()
    labels = list(range(P["y0"], P["y1"] + 1))
    bar_s = float(P["bar_s"])
    dur = len(labels) * bar_s + P["coda_s"]
    n = int((dur + P["tail_s"]) * SR)
    pio = A.month_curve(D["piomas"], 1979, 2026)
    K = S.vsco_kit()
    organ = Instrument("Keys/Organ/Quiet", glob="NT5_Man3Quiet_*.wav", mapping=lambda nm: (int(nm.split("_")[2]) - 86, 1))
    B = {"organ": Bus("organ", n, gain=P["organ_gain"], hp=100, send=0.6), "cello": Bus("cello", n, gain=P["cello_gain"], hp=50, send=0.55),
         "bass": Bus("bass", n, gain=P["bass_gain"], hp=25, send=0.35)}
    lo, hi = P["ext_range"]
    vlo, vhi = P["vol_range"]
    pulse_i = 0                       # the wheel turns continuously across bars
    rows = []
    pulse_events = 0

    def build_bar(label, t0, length, weeks, days_in_week_dates):
        nonlocal pulse_i, pulse_events
        ext = smooth(weeks, 3)
        wgt = rubato_weights(ext, P["rubato"])
        edges = np.concatenate([[0], np.cumsum(wgt)]) / wgt.sum() * length    # bar length is exact whatever the rubato
        counts = []
        for w in range(len(ext)):
            nn, act = active_slots(ext[w], lo, hi)
            slot = pulse_i % 8
            counts.append(nn)
            if slot in act:
                d = edges[w + 1] - edges[w]
                x = organ.note(WHEEL[slot], 0.6 + (0.1 if slot == 0 else 0.0), dur=d * 0.95, release=0.35, rng=rng)
                B["organ"].add(x, int((t0 + edges[w]) * SR), pan=(-0.35, 0.35)[w % 2] * 0.5)
                pulse_events += 1
                if P["openwater_octave"]:      # open water (D) is light: the wheel gains its upper octave as the sea opens
                    ow = open_water(ext[w])
                    if ow > OPEN_WATER_FROM:
                        x2 = organ.note(WHEEL[slot] + 12, 0.5, dur=d * 0.9, release=0.3, rng=rng)
                        B["organ"].add(x2, int((t0 + edges[w]) * SR), gain=float((ow - OPEN_WATER_FROM) / (1 - OPEN_WATER_FROM)) ** 1.2 * 0.8, pan=(-0.35, 0.35)[w % 2] * 0.8)
            pulse_i += 1
        return ext, counts

    # ---- the ice years
    bass_gate_curve, vol_curve, t_curve = [], [], []
    for b, y in enumerate(labels):
        t0 = b * bar_s
        weeks, days = weekly_extent(D, y)      # WY2026 (Oct 2025 - Sep 2026) uses the same construction; the data run to 6 Oct 2026
        ext, counts = build_bar(y, t0, bar_s, weeks, days)
        ords = np.array([d.toordinal() for d in days], float)
        vol = pio(ords)
        vm = float(vol.mean())
        # cello: one note every two months (6 per bar); register from the volume at that time
        seg = bar_s / 6
        for k in range(6):
            v = float(vol[int(k * len(days) / 6 + len(days) / 12)])
            ci = cello_index(v, vlo, vhi)
            vel = float(np.interp(v, [vlo, vhi], [0.35, 0.7]))
            x = K["cello"].note(CELLO[ci], vel, dur=seg * 1.25, release=0.9, rng=rng)
            ra = int(P["cello_attack_s"] * SR)       # a bowed swell, not a strike
            x[:ra] *= (np.linspace(0, 1, ra) ** 1.5)[:, None]
            B["cello"].add(x, int((t0 + k * seg) * SR), pan=-0.15)
        t_curve.append(t0 + bar_s / 2)
        bass_gate_curve.append(bass_gate(vm, P["bass_gate"]))
        vol_curve.append(vm)
        rows.append({"ice_year": y, "organ_notes_march": counts[22], "organ_notes_sept": counts[-3], "min_notes": int(min(counts)),
                     "vol_mean_1000km3": round(vm, 1), "bass_gate": round(bass_gate_curve[-1], 2),
                     "cello_index_start": cello_index(float(vol[0]), vlo, vhi)})
    # ---- bass pedal: one long sustained C2 with the gate as its level
    if P["bass"]:
        xs = S.sustain(K["bass"], 36, 0.55, dur + 1, rng, seg=7.0, xf=2.0)[:n]
        g = np.interp(np.arange(len(xs)) / SR, [0] + t_curve + [dur], [bass_gate_curve[0]] + bass_gate_curve + [0.0])
        g = g * np.minimum(1, np.arange(len(xs)) / (3 * SR))
        B["bass"].add(xs * g[:, None].astype(np.float32), 0, pan=0.0)

    # ---- coda: six October days; the wheel restarts thin, the cello holds G4-D5, nothing underneath
    t0 = len(labels) * bar_s
    coda_ext = D["total"][-6:]
    nn, act = active_slots(float(coda_ext.mean()), lo, hi)
    pulses = 20
    for k in range(pulses):
        slot = pulse_i % 8
        if slot in act:
            x = organ.note(WHEEL[slot], 0.5, dur=0.3, release=0.35, rng=rng)
            B["organ"].add(x, int((t0 + k * 0.34) * SR), pan=(-0.17, 0.17)[k % 2])
        pulse_i += 1
    for m, vel in ((67, 0.4), (74, 0.38)):
        B["cello"].add(S.sustain(K["cello"], m, vel, P["coda_s"] + 4, rng, seg=5.0, xf=1.5)[: int((P["coda_s"] + 12) * SR)], int(t0 * SR), pan=-0.1)

    # ---- the strings fill with the year's ice and fall away at the melt's own rate (thickness stays in register and bass)
    ext_t = np.array([w for b in range(len(labels)) for w in smooth(weekly_extent(D, labels[b])[0], 3)])      # smoothed weekly extent, computed once
    tt = np.concatenate([[(b + (k + 0.5) / 52) * bar_s for k in range(52)] for b in range(len(labels))])
    if P["swell"]:
        full = np.interp(np.arange(n) / SR, tt, swell(ext_t)).astype(np.float32)
        full[int(len(labels) * bar_s * SR):] = full[int(len(labels) * bar_s * SR) - 1]
        for k in ("cello", "bass"):
            B[k].buf *= full[:, None]

    # ---- master: dry and dark while the sea is frozen, wide and bright as it opens
    ice_env = np.interp(np.arange(n) / SR, tt, np.clip(ext_t / ICE_ENV_REF, 0, 1) * 0.8).astype(np.float32)
    irs = {"open": make_ir(5.5, bright=0.5, seed=23), "iced": make_ir(2.4, bright=0.25, seed=31)}
    mix, stems = S.master(list(B.values()), irs, HEAVY / f"{P['name']}.wav", ir_env={"open": 1 - ice_env, "iced": ice_env})
    S.to_mp3(HEAVY / f"{P['name']}.wav", OUT / f"{P['name']}.mp3")
    score = {"name": P["name"], "params": P,
             "constants": {"wheel_ext": WHEEL_EXT, "open_water_ref": OPEN_WATER_REF, "open_water_from": OPEN_WATER_FROM, "swell_ext": SWELL_EXT,
                           "swell_level": SWELL_LEVEL, "ice_env_ref": ICE_ENV_REF, "rubato_press": RUBATO_PRESS, "rubato_drag": RUBATO_DRAG}, "bars": len(labels), "duration_s": n / SR, "organ_events": pulse_events,
             "years": rows, "wheel": WHEEL, "cello_pitches": CELLO,
             "provenance": "extent: NSIDC Sea Ice Index v4 (R); volume: PIOMAS (M), Mar-Sep 2026 repeat 2025 (extended, flagged); see fetch_arctic.py"}
    (OUT / f"{P['name']}_score.json").write_text(json.dumps(score, indent=1))
    print("stems dBFS", {k: round(float(20 * np.log10(np.sqrt((v ** 2).mean()) + 1e-12)), 1) for k, v in stems.items()})
    print(f"{P['name']}: {len(labels)} bars x {bar_s} s + coda = {n / SR / 60:.1f} min incl. tail; organ notes {pulse_events}")
    for r in rows[::6] + [rows[-1]]:
        print(" ", r)


if __name__ == "__main__":
    main()
