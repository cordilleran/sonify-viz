"""
Export a pilot's score + stem envelopes + audio into listen/ for the
listening-companion page (listen/index.html).

  python export_companion.py            # both pilots
Writes listen/<name>.json and listen/<name>.mp3 (160 kbps, encoded from the master WAV).
"""
import json, subprocess, sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dsp_core import ROOT, HEAVY_OUT

P = ROOT / "rendered" / "pilots"
HEAVY = HEAVY_OUT / "pilots"  # master WAV + stems
OUT = ROOT / "listen"
ENV_HZ = 8

VOICES = {  # stem -> (label, colour key)
    "piano": ("Piano ostinato", "river"), "bass": ("Contrabass + cello", "deep"),
    "drone": ("Lake drone", "deep"), "pad": ("Violins", "moss"), "ice": ("Ice", "ice"),
    "frost": ("Frost", "ice"), "precip": ("Rain + snow", "rain"), "perc": ("Hand drums", "clay"),
    "fish": ("Fish", "salmon"), "heat": ("Heat violin", "sun"), "birds": ("Birds", "sun"),
}

LANES = {
    "granby_wy2024": [
        # key, label, colour, transform, source, stem, what the sound does
        ("flow", "Granby River flow", "river", "log", "R", "piano", "Piano gets denser as flow rises; contrabass holds the root, cello adds a 5th at high flow."),
        ("flow_pct_normal", "Flow vs. 15-yr normal", "river2", "lin", "D", "piano", "Sets the harmony's brightness: below normal leans one mode darker, above normal one brighter."),
        ("burrell", "Burrell Creek flow", "clay", "log", "R", "perc", "Hand drums: tumba, conga, shaker, and a 3-3-2 log-drum figure at the peak."),
        ("ice", "Ice conditions (WSC flag)", "ice", "flag", "R", "ice", "Freeze: falling glockenspiel + bowed cymbal. Frozen: crackle and descending singing-ice chirps. Breakup: cymbal swell and rising harp."),
        ("temp", "Air temperature, Billings", "sun", "temp", "R", "ice", "Colder days make the ice crackle denser; also brightens the harmony across the season."),
        ("rain", "Rain", "rain", "sqrt", "R", "precip", "Each rainy day scatters harp notes from the current chord."),
        ("snow", "Snowfall", "snow", "sqrt", "R", "precip", "Snowfall scatters soft glockenspiel notes, high up."),
        ("snow_on_ground", "Snow on ground", "snow", "lin", "R", None, "Deep snow swaps the reverb to a dark, short room: snow absorbs sound."),
        ("gpp_norm", "Plant productivity (MODIS GPP)", "moss", "lin", "R", "pad", "Violins swell with photosynthesis."),
        ("trout_sim", "Redband trout spawning", "salmon", "lin", "S", "fish", "A short rising flute figure. Timing is modelled from temperature and season."),
        ("whitefish_sim", "Mountain whitefish spawning", "salmon2", "lin", "S", "fish", "A falling cello pizzicato figure. Timing is modelled."),
        ("daylength", "Day length", "sun2", "lin", "D", None, "With temperature, sets how bright the mode is."),
    ],
    "okanagan_wy2024": [
        ("lake_level", "Okanagan Lake level, Kelowna", "deep", "lin", "R", "drone", "A low F held under everything, louder as the lake fills; cello adds a 5th while it rises."),
        ("lake_pct_normal", "Lake vs. 15-yr normal", "river2", "lin", "D", "drone", "Sets the harmony's brightness: below normal leans one mode darker."),
        ("penticton", "Outflow at Penticton dam", "river", "lin", "R", "piano", "Piano density follows the release. When the dam holds the flow flat, the piano plays strictly, with no variation."),
        ("oliver", "Okanagan River near Oliver", "clay", "log", "R", "perc", "Soft log drums, conga and shaker."),
        ("sockeye", "Sockeye passing Wells Dam", "salmon", "log", "R", "fish", "Marimba runs climb the chord; more fish means more notes, and the runs start higher as the season goes."),
        ("wells_temp", "Water temperature at Wells", "sun", "lin", "R", "heat", "Above 18 C a violin holds a high note: thermal stress for migrating sockeye."),
        ("spawn_sim", "Sockeye spawning near Oliver", "salmon2", "lin", "S", "fish", "Low, falling cello pizzicato around mid-October, scaled by run size. Timing is modelled."),
        ("temp", "Air temperature, Summerland", "sun2", "temp", "R", "frost", "Below -8 C: frost crackle."),
        ("rain", "Rain", "rain", "sqrt", "D", "precip", "Harp notes from the current chord. Rain vs. snow is split by temperature."),
        ("snow_we", "Snow", "snow", "sqrt", "D", "precip", "Soft, high glockenspiel."),
        ("humidity_min", "Humidity (daily min)", "ice", "lin", "R", None, "Humid days get a long hall reverb; dry days a short, bright room."),
        ("gpp_norm", "Plant productivity (MODIS GPP)", "moss", "lin", "R", "pad", "Violins swell with photosynthesis."),
    ],
}

# How the dashboard reads each record's value on a day: (unit, decimals). Special units:
# "pct" a percentile vs. the 2010-24 record, "flag" yes/no, "peak" a share of a
# typical peak day (MODIS 95th percentile, 2015-24), "sim" a modelled 0-1 window.
UNITS = {
    "flow": ("m³/s", 1), "flow_pct_normal": ("pct", 0), "burrell": ("m³/s", 2), "ice": ("flag", 0),
    "temp": ("°C", 1), "rain": ("mm", 1), "snow": ("cm", 1), "snow_on_ground": ("cm", 0),
    "gpp_norm": ("peak", 2), "trout_sim": ("sim", 2), "whitefish_sim": ("sim", 2), "daylength": ("h", 1),
    "lake_level": ("m", 3), "lake_pct_normal": ("pct", 0), "penticton": ("m³/s", 1), "oliver": ("m³/s", 1),
    "sockeye": ("fish", 0), "wells_temp": ("°C", 1), "spawn_sim": ("sim", 2), "snow_we": ("mm", 1),
    "humidity_min": ("%", 0),
}

TITLES = {
    "granby_wy2024": dict(title="Granby River", sub="Grand Forks, BC · WSC 08NN002 + Burrell Creek 08NN023 · Billings climate",
                          key="D", year_label="WY 2024", blurb="A warm El Niño winter. The gauge flagged ice on only 28 days, in broken episodes, and the freshet came early and small: 147 m³/s, against 465 in the 2010–24 record."),
    "okanagan_wy2024": dict(title="Okanagan", sub="Okanagan Lake 08NM083 · Penticton 08NM050 · Oliver 08NM085 · Summerland CS · Wells Dam",
                            key="F", year_label="WY 2024", blurb="A drought year on the lake, which rose only 0.7 m, that was also the biggest sockeye return in ten years of Wells Dam counts."),
}


def transform(v, how):
    v = np.array([np.nan if x is None else float(x) for x in v])
    if how == "flag":
        return np.nan_to_num(v).clip(0, 1)
    if how == "log":
        v = np.log1p(np.nan_to_num(v) / max(np.nanpercentile(v, 5), 1e-3))
    elif how == "sqrt":
        v = np.sqrt(np.nan_to_num(v))
    elif how == "temp":
        lo, hi = np.nanmin(v), np.nanmax(v)
        return np.round(np.nan_to_num((v - lo) / (hi - lo), nan=0), 3), float(-lo / (hi - lo))
    hi, lo = np.nanpercentile(v, 99), np.nanmin(v)
    return np.round(np.clip(np.nan_to_num((v - lo) / (hi - lo + 1e-12), nan=0), 0, 1), 3)


# Records whose daily values this site does not republish: the page plays them and draws their
# normalized shape (as the 09-25 release did), but its dashboard shows no numbers for them.
WITHHELD = {
    "sockeye": "Columbia River DART counts are not republished here; you hear them, and the ring draws their shape.",
    "wells_temp": "Columbia River DART temperatures are not republished here; you hear them, and the ring draws their shape.",
}


def main():
    OUT.mkdir(exist_ok=True)
    for name, lanes in LANES.items():
        with open(P / f"{name}_score.json") as fh:
            sc = json.load(fh)
        days = sc["days"]
        out_lanes = []
        for key, label, col, how, src, stem, does in lanes:
            r = transform([d[key] for d in days], how)
            if isinstance(r, tuple):  # "temp" also returns where 0 C sits; the page doesn't draw it
                r = r[0]
            unit, dp = UNITS[key]
            raw = [None if d[key] is None else (float(d[key]) if unit != "flag" else int(bool(d[key])))
                   for d in days]
            lane = dict(key=key, label=label, color=col, source=src, stem=stem, does=does,
                        v=[float(x) for x in r], raw=raw, unit=unit, dp=dp)
            if key in WITHHELD:  # heard, and drawn as a shape, but no values published
                lane.update(raw=None, withheld=WITHHELD[key])
            out_lanes.append(lane)
        env = {}
        for f in sorted((HEAVY / f"{name}_stems").glob("*.flac")):
            x, sr = sf.read(f)
            m = x.mean(axis=1) * 4
            blk = sr // ENV_HZ
            r = np.sqrt(np.array([(m[i:i + blk] ** 2).mean() for i in range(0, len(m) - blk, blk)]) + 1e-12)
            db = 20 * np.log10(r)
            env[f.stem] = [round(float(x), 2) for x in np.clip((db + 62) / 40, 0, 1)]
        voices = [dict(stem=k, label=VOICES[k][0], color=VOICES[k][1]) for k in env]
        with open(OUT / f"{name}.json", "w") as fh:
            json.dump(dict(**TITLES[name], name=name, duration=sc["duration_s"], bar_seconds=sc["bar_seconds"],
                           n_days=len(days), dates=[d["date"] for d in days], t=[d["t"] for d in days], lanes=out_lanes,
                           bars=sc["bars"], events=sc["events"], env_hz=ENV_HZ, env=env, voices=voices,
                           gpp_source=sc["gpp_source"]),
                      fh, separators=(",", ":"))
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(HEAVY / f"{name}.wav"), "-b:a", "160k",
                        str(OUT / f"{name}.mp3")], check=True)
        print(name, (OUT / f"{name}.json").stat().st_size // 1024, "KB json,",
              (OUT / f"{name}.mp3").stat().st_size // 1024 // 1024, "MB mp3")


if __name__ == "__main__":
    main()
