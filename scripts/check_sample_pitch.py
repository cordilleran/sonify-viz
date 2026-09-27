"""
Measure every sampled note's pitch against the note its filename (plus the
kit's octave offset) says it is. This is the check that found VSCO naming
middle C "C3" (2026-09-24): six instruments read exactly 12 semitones high.

  python check_sample_pitch.py            # summary per instrument
  python check_sample_pitch.py --all      # every sample
  python check_sample_pitch.py --csv out.csv

It answers two questions separately (both checked 2026-09-27):
  TUNING  the strongest spectral peak within a semitone of the labelled pitch
          (1-second spectrum after the attack), in cents; flagged beyond 50.
  OCTAVE  sampler.estimate_f0 (autocorrelation), only for labels between
          60 Hz and 1 kHz, where it is reliable. Outside that range it
          misreads: glockenspiel and top-piano overtones are strong and
          inharmonic, and the lowest notes' second harmonic outweighs a weak
          fundamental, so a spectral "loudest peak" rule calls them an octave
          high when they aren't. An octave error means fix octave_offset in
          sampler.vsco_kit. One offset covers a whole instrument, so the
          verdict is the majority of its checked samples; samples that
          disagree are listed to listen to (short pizzicato notes decay
          inside the window and can read an octave low on their own).
"""
import argparse
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sampler as S


def _peak(freqs, mag, hz):
    """Strongest bin within +-1 semitone of hz, refined by parabolic interpolation -> (Hz, magnitude)."""
    band = np.flatnonzero((freqs > hz * 2 ** (-1 / 12)) & (freqs < hz * 2 ** (1 / 12)))
    if len(band) == 0:
        return hz, 0.0
    i = band[np.argmax(mag[band])]
    if i in (band[0], band[-1]):
        return None, 0.0  # the maximum is the window's edge: no clear peak at this pitch
    if 0 < i < len(mag) - 1:
        a, b, c = np.log(mag[i - 1:i + 2] + 1e-12)
        d = float(np.clip(0.5 * (a - c) / (a - 2 * b + c), -0.5, 0.5)) if (a - 2 * b + c) else 0.0
        return float(freqs[i] + d * (freqs[1] - freqs[0])), float(mag[i])
    return float(freqs[i]), float(mag[i])


OCTAVE_RANGE = (60.0, 1000.0)  # Hz: where the autocorrelation estimate can be trusted


def label_check(x, label_hz, sr=S.SR):
    """-> (Hz of the peak at the label, octave error in octaves or None if not checkable)."""
    m = x.mean(axis=1)[int(0.05 * sr):int(1.05 * sr)]
    n = 1 << 17  # zero-pad for a fine grid
    mag = np.abs(np.fft.rfft(m * np.hanning(len(m)), n))
    at = _peak(np.fft.rfftfreq(n, 1 / sr), mag, label_hz)[0]
    octave = None
    if OCTAVE_RANGE[0] <= label_hz <= OCTAVE_RANGE[1]:
        r = np.log2(S.estimate_f0(x) / label_hz)
        octave = int(round(r)) if abs(r - round(r)) < 0.05 else 0  # not near a whole octave: a misread, not a label error
    return at, octave


def measure(kit):
    rows = []
    for name, ins in kit.items():
        if not isinstance(ins, S.Instrument):
            continue  # unpitched one-shots
        for midi, dyn, path in ins.zones:
            label_hz = 440.0 * 2 ** ((midi - 69) / 12)
            f0, octave = label_check(S.load(path), label_hz)
            cents = 1200 * np.log2(f0 / label_hz) if f0 else np.nan
            rows.append({"instrument": name, "file": path.name, "label_midi": midi, "dyn": dyn,
                         "label_hz": round(label_hz, 1), "measured_hz": round(float(f0), 1) if f0 else None,
                         "cents": None if np.isnan(cents) else round(float(cents)), "octave_error": octave,
                         "flag": bool(abs(cents) > 50)})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="print every sample, not just the summary")
    ap.add_argument("--csv", help="write every sample to this CSV")
    a = ap.parse_args()
    rows = measure(S.vsco_kit())
    if a.csv:
        with open(a.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    if a.all:
        for r in rows:
            print(f"{'FLAG' if r['flag'] else '    '} {r['instrument']:8s} {r['file']:40s} "
                  f"{r['label_hz']:8.1f} Hz label, {r['measured_hz']:8.1f} measured, {r['cents']:+5d} cents")
    print(f"{'instrument':10s} {'samples':>7s} {'median cents':>12s} {'off >50c':>8s}  octave (majority of checked)")
    listen = []
    for name in dict.fromkeys(r["instrument"] for r in rows):
        rs = [r for r in rows if r["instrument"] == name]
        oct_ = [r["octave_error"] for r in rs if r["octave_error"] is not None]
        if len(oct_) >= 3:
            vals, counts = np.unique(oct_, return_counts=True)
            major = int(vals[np.argmax(counts)])
            verdict = (f"{'OK' if major == 0 else f'OFF BY {major:+d}'} ({counts.max()}/{len(oct_)} agree)")
            listen += [r for r in rs if r["octave_error"] is not None and r["octave_error"] != major]
        else:
            verdict = f"too few samples in 60 Hz-1 kHz to judge ({len(oct_)})"
        med = np.median([r["cents"] for r in rs if r["cents"] is not None])
        print(f"{name:10s} {len(rs):7d} {int(med):+12d} "
              f"{sum(r['flag'] for r in rs):8d}  {verdict}")
    weak = [r for r in rows if r["cents"] is None]
    if weak:
        print(f"  no clear peak at the labelled pitch (weak fundamental; not a tuning error): "
              + ", ".join(f"{r['instrument']} {r['file']}" for r in weak))
    for r in [r for r in rows if r["flag"]] + listen:
        why = f"{r['cents']:+d} cents" if r["flag"] else f"estimator reads {r['octave_error']:+d} octave(s)"
        print(f"  listen: {r['instrument']:8s} {r['file']:34s} {why}")


if __name__ == "__main__":
    main()
