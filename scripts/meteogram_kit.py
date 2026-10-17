"""Sample kit for the meteogram groove: one loader for the Karoryfer sets (Big Rusty Drums, War Tuba, Bear Sax, and the unused-here Growlybass and Black and Green Guitars) and VSCO 2 CE.
Karoryfer sets are CC0 1.0 (LICENSE headers read), cloned from github.com/sfzinstruments into samples/rockkit/; VSCO 2 CE is CC0."""
import re
from pathlib import Path

import numpy as np

from sampler import Instrument, OneShots, VSCO, load, name_to_midi
from dsp_core import SAMPLES

KR = SAMPLES / "rockkit"
rng = np.random.default_rng(1016)


def glide(x, semis):
    """Variable-rate resample: pitch moves linearly by `semis` across the note (a string slide)."""
    n = len(x)
    ratio = 2 ** (np.linspace(0, semis, n) / 12)
    pos = np.cumsum(ratio)
    pos -= pos[0]
    idx = pos[pos < n - 1]
    return np.stack([np.interp(idx, np.arange(n), x[:, c]) for c in range(2)], axis=1).astype(np.float32)


class DrumPool:
    """Multi-mic velocity-layered one-shots: names carry vl<n> and rr<n>; the same name exists in each mic folder and the mics are summed."""

    def __init__(self, mics):
        self.mics = [Path(m) for m in mics]
        names = sorted(p.name for p in self.mics[0].glob("*.flac"))
        self.by_vl = {}
        for nm in names:
            vl = int(re.search(r"vl(\d+)", nm).group(1))
            self.by_vl.setdefault(vl, []).append(nm)
        self.vls = sorted(self.by_vl)

    def hit(self, vel, r=None):
        vl = self.vls[min(len(self.vls) - 1, int(vel * len(self.vls)))]
        pool = self.by_vl[vl]
        nm = pool[(r or rng).integers(len(pool))]
        parts = [load(m / nm) for m in self.mics if (m / nm).exists()]
        n = max(len(p) for p in parts)
        out = np.zeros((n, 2), dtype=np.float32)
        for p in parts:
            out[: len(p)] += p
        return out * (0.3 + 0.7 * vel)


def kr_note_map(octave_offset=0, dyn_names=None):
    def f(fn):
        stem = fn.rsplit(".", 1)[0]
        m = re.match(r"([a-g][b]?\d)", stem)
        if not m:
            return None, 1
        nm = m.group(1)
        midi = name_to_midi(nm[0].upper() + nm[1:], octave_offset)
        if dyn_names:
            d = next((v for k, v in dyn_names.items() if f"_{k}_" in stem + "_"), 1)
        else:
            vm = re.search(r"vl(\d)", stem)
            d = int(vm.group(1)) if vm else 1
        return midi, d
    return f


def build_kit():
    bass_dyn = {"pp": 1, "p": 2, "f": 3, "ff": 4}
    drums = KR / "karoryfer.big-rusty-drums" / "Samples"
    mics = lambda d: [p for p in sorted(Path(d).iterdir()) if p.is_dir()]  # noqa: E731
    k = {}
    k["kick"] = DrumPool(mics(drums / "kick_24/kick"))
    k["snare"] = DrumPool(mics(drums / "snare_14/center"))
    k["hat"] = DrumPool(mics(drums / "hihat_14/cl"))
    k["crash"] = DrumPool(mics(drums / "crash_17/cr"))
    k["ride"] = DrumPool(mics(drums / "ride_22/rd"))
    k["china"] = DrumPool(mics(drums / "china_18/cn"))
    # Growlybass: names are standard pitch (a2 = 110 Hz, checked by FFT)
    k["gbass"] = Instrument(KR / "karoryfer.growlybass/staccato", mapping=lambda n: (name_to_midi(n.split("_")[0][0].upper() + n.split("_")[0][1:]), 1))
    k["gsus"] = Instrument(KR / "karoryfer.growlybass/sustain", mapping=kr_note_map(0, bass_dyn))
    # War Tuba: names sit one octave under standard (a1 = 110 Hz, e1 = 82 Hz; FFT-checked). 'ss' = short, 'sus' = sustained
    tdir = KR / "karoryfer.war-tuba/Samples"
    k["tuba_s"] = Instrument(tdir, glob="*_ss_vl*_dyn.wav", mapping=kr_note_map(1))
    k["tuba_l"] = Instrument(tdir, glob="*_sus_dyn.wav", mapping=lambda n: (name_to_midi(n.split("_")[0][0].upper() + n.split("_")[0][1:], 1), 1))
    # hollowbody guitar staccato: e3 measures 164 Hz, standard naming
    k["gtr"] = Instrument(KR / "karoryfer.black-and-green-guitars/Samples/black/stac", mapping=lambda n: (name_to_midi(n.split("_")[1].upper()[0] + n.split("_")[1][1:]), 1))
    # Bear Sax (1926 Conn baritone, CC0): looped sustains; names sit one octave under standard (d1 = D2, 73 Hz; FFT-checked)
    k["bsax"] = Instrument(KR / "karoryfer.bear-sax/Samples", glob="*_looped_f.wav", mapping=lambda fn: (name_to_midi(fn.split("_")[0][0].upper() + fn.split("_")[0][1:], 1), 1))
    k.update(dict(
        harp=Instrument("Strings/Harp"),
        flute=Instrument("Woodwinds/Flute/susNV", octave_offset=1),
        vln=Instrument("Strings/Violin Section/susVib", octave_offset=1),
        cello=Instrument("Strings/Cello Section/susvib", octave_offset=1),
        cpizz=Instrument("Strings/Cello Section/pizzT", octave_offset=1),
        cb=Instrument("Strings/Solo Contrabass/SusNV", octave_offset=1),
        bpizz=Instrument("Strings/Solo Contrabass/Pizz", octave_offset=1),
        glock=Instrument("Percussion/Glock", octave_offset=1),
        marimba=Instrument("Percussion/Marimba", octave_offset=1),
        perc=OneShots(),
        timp=OneShots(VSCO / "Percussion/Timpani"),
        roll=OneShots(VSCO / "Percussion/Timpani/Rolls"),
    ))
    return k
