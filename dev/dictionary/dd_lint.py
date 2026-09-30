"""Style check for the data dictionaries. Exits 1 with a list of problems.

  python dev/dictionary/dd_lint.py

Rules (2026-09-30):
  1. every table has a description;
  2. every column except an enum has a description;
  3. every number(quantity) column has units and a range;
  4. units use one spelling: '%' (not 'percent'), '°C' (not 'degrees C'), and a described 'ppm (...)' (not bare 'ppm');
  5. every stated range holds for the data (to the precision the file states).

It also catches a sync that has overwritten the dictionaries with an older copy: the old copy fails rules 1 to 4.
"""
import glob, os, sys
import pyarrow.compute as pc, pyarrow.parquet as pq, yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FILES = ["data/parquet/data-dict.yaml", "data/climate/parquet/data-dict.yaml"] + sorted(
    os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, "tracks/mapping/*/data-dict.yaml")))
BAD_UNITS = {"percent": "%", "degrees C": "°C", "ppm": "ppm (µmol per mol of dry air)"}
problems = []
for f in FILES:
    d = yaml.safe_load(open(os.path.join(ROOT, f)))
    base = os.path.dirname(os.path.join(ROOT, f))
    for t in d["tables"]:
        where = f"{f.replace('/data-dict.yaml', '')} :: {t['name']}"
        if "description" not in t:
            problems.append(f"{where}: table has no description")
        tab = pq.read_table(os.path.join(base, t["source"]["parquet"]))
        for c in t["columns"]:
            n, ty = c["name"], c["type"]
            if "description" not in c and ty != "enum":
                problems.append(f"{where}.{n}: no description")
            if ty == "number(quantity)":
                if "units" not in c: problems.append(f"{where}.{n}: quantity without units")
                if "range" not in c: problems.append(f"{where}.{n}: quantity without a range")
            u = c.get("units")
            if u in BAD_UNITS:
                problems.append(f"{where}.{n}: units '{u}' should be '{BAD_UNITS[u]}'")
            if "range" in c and ty.startswith("number") and n in tab.column_names:
                mm = pc.min_max(tab.column(n).cast("float64")).as_py()
                lo, hi = c["range"]
                tol = 1e-3
                if mm["min"] is not None and (mm["min"] < lo - tol or mm["max"] > hi + tol):
                    problems.append(f"{where}.{n}: data {mm['min']}..{mm['max']} outside range {c['range']}")
print(f"{len(FILES)} dictionaries checked; {len(problems)} problem(s)")
for p in problems: print("  " + p)
sys.exit(1 if problems else 0)
