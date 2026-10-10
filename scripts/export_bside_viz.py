"""
Export the B-side's per-bar state for the picture (no audio). The rules (rubato, notes sounding, open water, swell, cello register, bass gate) are the
functions in arctic_bside.py, so a retuned take changes the picture too; tests/test_arctic_bside.py checks that.
    python export_bside_viz.py [--out DIR]        default DIR: arctic/page/ in the workbench, arctic-bside/src/ in the published repo   (writes bside_state.json and arctic_page_min.json)
Per bar: rubato edges (fractions of the bar at each of 52 pulses), smoothed weekly extent, notes sounding, open-water level, the six cello register
indices, the bass gate and the cello-and-bass swell. Only the register index and the year's mean volume leave the engine from PIOMAS (a model, M).
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import arctic_data as A
import arctic_bside as B

HERE = Path(__file__).resolve().parent.parent
DEFAULT_OUT = HERE / "arctic" / "page" if (HERE / "arctic" / "page").exists() else HERE / "arctic-bside" / "src"   # the workbench, or the published repo


def build_state(D=None, P=None):
    P = dict(B.DEFAULTS) if P is None else P
    D = A.load() if D is None else D
    labels = list(range(P["y0"], P["y1"] + 1))
    lo, hi = P["ext_range"]
    vlo, vhi = P["vol_range"]
    pio = A.month_curve(D["piomas"], 1979, 2026)
    bars = []
    for y in labels:
        weeks, days = B.weekly_extent(D, y)
        ext = B.smooth(weeks, 3)
        edges = np.concatenate([[0], np.cumsum(B.rubato_weights(ext, P["rubato"]))])
        edges = edges / edges[-1]
        vol = pio(np.array([d.toordinal() for d in days], float))
        vm = float(vol.mean())
        bars.append({"y": y, "edges": [round(float(e), 4) for e in edges], "ext": [round(float(e), 2) for e in ext],
                     "nn": [B.active_slots(float(e), lo, hi)[0] for e in ext], "ow": [round(B.open_water(float(e)), 3) for e in ext],
                     "cello": [[B.cello_index(float(vol[int(k * len(days) / 6 + len(days) / 12)]), vlo, vhi)] for k in range(6)],
                     "vol": round(vm, 1), "gate": round(B.bass_gate(vm, P["bass_gate"]), 3),
                     "swell": [round(float(B.swell(float(e))), 3) for e in ext]})
    nn, _ = B.active_slots(float(D["total"][-6:].mean()), lo, hi)
    return {"bar_s": P["bar_s"], "coda_s": P["coda_s"], "duration_s": len(labels) * P["bar_s"] + P["coda_s"] + P["tail_s"],
            "wheel": B.WHEEL, "cello_pitches": B.CELLO, "per": 52, "pulse_offset": 0,
            "coda": {"n": nn, "pulse_s": 0.34, "pulses": 20, "cello": [67, 74]}, "bars": bars,
            "provenance": "extent NSIDC v4 (R); volume PIOMAS (M); computed by the same functions as arctic_bside.py"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    out = Path(ap.parse_args().out)
    out.mkdir(parents=True, exist_ok=True)
    state = build_state()
    (out / "bside_state.json").write_text(json.dumps(state, separators=(",", ":")))
    # the page needs only the daily total extent (NSIDC, R); the PIOMAS, regional, CO2, GISTEMP and SST series are not shipped with this picture
    full = json.loads((HERE / "data" / "arctic" / "arctic_daily.json").read_text())
    (out / "arctic_page_min.json").write_text(json.dumps({"dates": full["dates"], "total": full["total"], "co2_brw_ppm": {}, "sst_global_anom_c": {},
                                                          "gistemp": {}, "note": "NSIDC Sea Ice Index v4 daily total extent (R). Trimmed for the B-side picture."},
                                                         separators=(",", ":")))
    print("wrote", out / "bside_state.json", "and arctic_page_min.json;", len(state["bars"]), "bars")


if __name__ == "__main__":
    main()
