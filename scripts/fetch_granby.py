"""
Fetch the Granby pilot's source data into data/ (cached JSON; skipped if the
file is already there). Uses the same ECCC OGC API helpers as fetch_okanagan.py.

Hydrometric (ECCC OGC API, hydrometric-daily-mean, 2010-2024):
  08NN002  Granby River at Grand Forks   - DISCHARGE + ice-condition flags
  08NN023  Burrell Creek above Gloucester Creek - DISCHARGE (a flashy tributary)
Climate (ECCC OGC API, climate-daily, 2010-2024):
  STN_ID 1100  Billings (Grand Forks area)
The Granby valley MODIS GPP pull is in fetch_okanagan.py ("gpp").
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_okanagan import hydro, climate

if __name__ == "__main__":
    hydro("08NN002", "granby")
    hydro("08NN023", "burrell")
    climate(1100, "billings")
