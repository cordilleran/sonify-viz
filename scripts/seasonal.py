"""
Compatibility shim (2026-09-27). The engine that lived here is now three
modules, and this file re-exports them so older scripts and the published
repo keep working:

  timegrid.py  Year (the year and its framing), Grid, per_bar, daily helpers
  harmony.py   the mode ladder, chords, voice leading, progressions (pure)
  records.py   cached-pull loaders and the per-year daily arrays

plus sampler.sustain (sample playback). The module-level DAYS, N_DAYS,
N_BARS and WY_START are the WY2024 defaults; new code should build a
timegrid.Year and pass it (the pilots take --year, e.g. wy2023, cy2024).
"""
import datetime as dt  # noqa: F401  (pieces use W.dt)

from dsp_core import SR, HEAVY_OUT, LIGHT_OUT, SITE_AUDIO, day_length_hours  # noqa: F401
from timegrid import (  # noqa: F401
    DAYS_PER_BAR, FRAMINGS, WY2024, Grid, Year, events_from_flag, fmt_time, new_moons_from,
    norm01, per_bar, smooth, solstice,
)
from harmony import (  # noqa: F401
    MODES, chord, chord_track, degree_to_midi, fire_bars, mode_track, phase_bars, voice_lead,
)
from records import (  # noqa: F401
    DATA, HERE, check_coverage, climate_series, coverage, dart_run_totals, dart_sockeye, doy_percentile, growing_degree_days,
    in_year, modis_gpp_daily, wsc_series,
)
from sampler import sustain  # noqa: F401

WY_START = WY2024.start
DAYS = WY2024.days
N_DAYS = WY2024.n_days
N_BARS = WY2024.n_bars
wy = in_year  # the old name, from when every piece was a water year


def doy_index(doy):
    return WY2024.doy_index(doy)


def daylength(lat):
    return WY2024.daylength(lat)
