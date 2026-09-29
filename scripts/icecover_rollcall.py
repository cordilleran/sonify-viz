"""
Superior Ice Year: the roll call (2026-09-28). A ~50 s orientation file, played from a dashboard button,
never baked into the track: each region sounds once from west to east at its own pitch and pan, then each layer
solo, then a soft end bell (zhao2008a's west-to-east sweep; sawe2020a: a short mapping explanation anchors listeners).

    python icecover_rollcall.py [OUT_DIR]     # -> icecover_rollcall.wav/.mp3 and icecover_rollcall_cues.json
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import icecover as I
import sampler as S
import synth as Y
from sampler import Bus, Instrument, make_ir, SR

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else I.W.HEAVY_OUT / "icecover"
REGION_S, LAYER_S = 1.5, 3.0


def main():
    P = I.DEFAULTS
    rng = np.random.default_rng(P["seed"])
    D = I.load()
    ids, pan = D["ids"], D["pan"]
    K = S.vsco_kit()
    organ = Instrument("Keys/Organ/Quiet", glob="NT5_Man3Quiet_*.wav", mapping=lambda nm: (int(nm.split("_")[2]) - 86, 1))
    cues, t = [], 0.8
    layers = [("ice", "Ice: a bowed-glass tone per region, louder as the ice thickens"),
              ("freeze", "Freeze: a glass ping and tick"),
              ("breakup", "Breakup: a low drop and a crack"),
              ("water", "Open water: low strings, fuller as it warms"),
              ("air", "Air temperature: the organ, brighter when warm"),
              ("sun", "Daylight: the choir, opening from oo to ah"),
              ("wind", "Wind: filtered noise, gated by gales"),
              ("snow", "Snow: dry high ticks"),
              ("rain", "Rain: soft harp drops"),
              ("birds", "Birds: loon and goose, timed from ice-off and warmth"),
              ("ghost", "Ghost: the 2008-2025 median ice, a quiet detuned glass")]
    total = t + len(ids) * REGION_S + 1.0 + len(layers) * LAYER_S + 5.0
    n = int(total * SR)
    B = {k: Bus(k, n, **kw) for k, kw in I.LAYER_BUSES.items() if k in
         ("ice", "pings", "drops", "water", "organ", "choir", "wind", "snow", "rain", "birds", "ghost")}

    def env(m, a=0.15, r=0.6):
        k = np.arange(m) / SR
        return np.minimum(1, np.minimum(k / a, (m / SR - k) / r)).astype(np.float32)

    for i, rid in enumerate(ids):   # the map, west to east
        m = int(REGION_S * 1.6 * SR)
        x = I.glass(P["ice_pitch"][i], m, 0.9, rng) * env(m, 0.08, 0.9) * 0.5
        B["ice"].add(Y.stereo(x, width=0.5), int(t * SR), pan=pan[rid])
        cues.append({"t": round(t, 2), "kind": "region", "label": D["names"][rid], "pan": round(float(pan[rid]), 2)})
        t += REGION_S
    t += 1.0
    for key, label in layers:
        at, m = int(t * SR), int(LAYER_S * SR)
        e = env(m, 0.3, 0.9)
        if key == "ice":
            for i, rid in enumerate(ids):
                B["ice"].add(Y.stereo(I.glass(P["ice_pitch"][i], m, 0.5, rng) * e * 0.3, width=0.5), at, pan=pan[rid])
        elif key == "freeze":
            for k, i in enumerate((1, 4, 6)):
                B["pings"].add(Y.stereo(I.ping(P["ice_pitch"][i] + 12, 0.8, rng), width=0.3), at + int(k * 0.8 * SR), pan=pan[ids[i]])
        elif key == "breakup":
            for k, i in enumerate((2, 5)):
                B["drops"].add(Y.stereo(I.drop(P["drop_pitch"][i], 0.9, rng), width=0.3), at + int(k * 1.2 * SR), pan=pan[ids[i]])
        elif key == "water":
            x = S.sustain(K["cello"], 50, 0.5, LAYER_S + 1, rng, seg=6.0, xf=1.0)[:m]
            B["water"].add(x * e[:len(x), None], at)
        elif key == "air":
            x = S.sustain(organ, 62, 0.55, LAYER_S + 1, rng, seg=9.0, xf=1.0, release=1.0)[:m]
            B["organ"].add(x * e[:len(x), None], at)
        elif key == "sun":
            for j, mi in enumerate(P["choir_pitch"]):
                v = np.linspace(0, 1, m)
                B["choir"].add(Y.stereo(I.sung_voice(mi, m, v, rng) * e * 0.5, width=0.4), at, pan=(-0.25, 0.25)[j])
        elif key == "wind":
            x = Y.bandpass(rng.standard_normal(m), 250, 1400) * e * np.sin(np.linspace(0, np.pi, m)) * 0.3
            B["wind"].add(I.pan_curve(x, np.linspace(-0.5, 0.5, m)), at)
        elif key == "snow":
            for _ in range(14):
                B["snow"].add(Y.stereo(I.flake(float(rng.uniform(0.3, 0.8)), rng), width=0.2), at + int(rng.uniform(0, LAYER_S - 0.3) * SR),
                              pan=float(rng.uniform(-0.6, 0.6)))
        elif key == "rain":
            for k in range(6):
                x = K["harp"].note(P["rain_pitch"][int(rng.integers(8))], float(rng.uniform(0.25, 0.5)), dur=1.5, release=0.8, rng=rng)
                B["rain"].add(x, at + int(k * 0.45 * SR), pan=float(rng.uniform(-0.6, 0.6)), gain=0.6)
        elif key == "birds":
            loon = S.bird_phrases("common_loon")[0]
            B["birds"].add(loon[:m], at, pan=-0.3, gain=0.5)
        elif key == "ghost":
            f0 = float(Y.midi_hz(P["ghost_pitch"]))
            x = I.ghost_carrier(f0, np.linspace(0, 30, m), True) * e * 0.3
            B["ghost"].add(Y.stereo(x, width=0.5), at)
        cues.append({"t": round(t, 2), "kind": "layer", "label": label})
        t += LAYER_S
    bell = I.ping(P["ice_pitch"][0] + 12, 0.6, rng, dur=4.0)   # the soft end bell: the lowest region's freeze ping, let ring
    B["pings"].add(Y.stereo(bell, width=0.5), int((t + 0.5) * SR))
    cues.append({"t": round(t + 0.5, 2), "kind": "end", "label": "End of the roll call"})

    OUT.mkdir(parents=True, exist_ok=True)
    irs = {"open": make_ir(5.5, bright=0.5, seed=23)}
    S.master(list(B.values()), irs, OUT / "icecover_rollcall.wav")
    S.to_mp3(OUT / "icecover_rollcall.wav", OUT / "icecover_rollcall.mp3")
    (OUT / "icecover_rollcall_cues.json").write_text(json.dumps({"duration_s": total, "cues": cues}, indent=1))
    print("roll call", round(total, 1), "s,", len(cues), "cues")


if __name__ == "__main__":
    main()
