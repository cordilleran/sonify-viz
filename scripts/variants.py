"""
Variants and remixes (2026-09-27): named parameter overrides of a piece.

A piece declares its parameters and their defaults, then calls setup():

    P, Y, NAME, META = V.setup("granby", DEFAULTS)

and reads P["bpm"], P["mute"] and so on. With no flags, P is the defaults
and NAME is the published name, so the published render is unchanged.

  piece.py wy2019                       another year (see timegrid.Year.parse)
  piece.py --variant frozen             a named variant from variants/<piece>.yaml
  piece.py --remix remixes/dusk.yaml    a remix: its own track, with lineage and credits
  piece.py --set bpm=60 --set mute=[perc]   ad hoc overrides (named __set-<hash>)

VARIANTS are for listening A/Bs and version history: variants/<piece>.yaml maps
a name to overrides plus an optional `note`. A variant renders as
<piece>_<year>__<variant>.

A REMIX is a new track built from a parent (remixes/*.yaml):

    remix: granby-wy2024-dusk          # the new track's id
    parent: {piece: granby, track: granby-wy2024, version: "1.0"}
    keeps: [the Granby and Burrell flow records, the ice record, the mapping]
    changes: {bpm: 60, mute: [perc], mode: Dorian}
    credits: [{name: ..., role: remix}]
    notes: why this remix exists

It renders under its own id, and renders.py records its parent in the lock.
Every override key must be one the piece declares, so a typo fails loudly
instead of quietly rendering the default.
"""
import argparse
import hashlib
import json
from pathlib import Path

import yaml

import timegrid

ROOT = Path(__file__).resolve().parent.parent
VARIANTS = ROOT / "variants"
REMIX_KEYS = {"remix", "parent", "keeps", "changes", "credits", "notes"}


def load_remix(path):
    r = yaml.safe_load(Path(path).read_text())
    missing = {"remix", "parent", "changes", "credits"} - set(r)
    extra = set(r) - REMIX_KEYS
    if missing or extra:
        raise SystemExit(f"{path}: missing {sorted(missing)} / unknown {sorted(extra)} (keys: {sorted(REMIX_KEYS)})")
    return r


def _check(piece, defaults, over, where):
    bad = set(over) - set(defaults)
    if bad:
        raise SystemExit(f"{where}: {piece} has no parameter(s) {sorted(bad)}; it has {sorted(defaults)}")


def setup(piece, defaults, argv=None):
    """-> (params, Year, output name, meta). meta is {} for the published default."""
    ap = argparse.ArgumentParser(description=f"render {piece}")
    ap.add_argument("year", nargs="?", help="e.g. wy2024 (default), wy2019, cy2023")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--variant", help=f"a name from variants/{piece}.yaml")
    g.add_argument("--remix", help="a remix spec (remixes/*.yaml)")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="override one parameter")
    a = ap.parse_args(argv)

    P, over, meta, tag, name = dict(defaults), {}, {}, "", None
    if a.variant:
        spec = yaml.safe_load((VARIANTS / f"{piece}.yaml").read_text())
        if a.variant not in spec:
            raise SystemExit(f"no variant {a.variant!r} in variants/{piece}.yaml; there are {sorted(spec)}")
        over = {k: v for k, v in spec[a.variant].items() if k != "note"}
        _check(piece, defaults, over, f"variants/{piece}.yaml:{a.variant}")
        meta = {"variant": a.variant, "overrides": over, "note": spec[a.variant].get("note")}
        tag = f"__{a.variant}"
    if a.remix:
        r = load_remix(a.remix)
        if r["parent"].get("piece") != piece:
            raise SystemExit(f"{a.remix} is a remix of {r['parent'].get('piece')!r}, not {piece!r}")
        over = dict(r["changes"])
        _check(piece, defaults, over, a.remix)
        meta = {"remix": r["remix"], "parent": r["parent"], "overrides": over, "credits": r["credits"]}
        name = r["remix"].replace("-", "_")
    extra = {}
    for s in a.set:
        k, _, v = s.partition("=")
        extra[k] = yaml.safe_load(v)
    if extra:
        _check(piece, defaults, extra, "--set")
        over.update(extra)
        meta.setdefault("overrides", {}).update(extra)
        tag += "__set-" + hashlib.sha256(json.dumps(extra, sort_keys=True).encode()).hexdigest()[:6]
    if a.year:
        over["year"] = P["year"] = a.year
        if meta:
            meta["overrides"]["year"] = a.year
    P.update(over)
    Y = timegrid.Year.parse(P["year"])
    if name is None:
        name = f"{piece}_{Y.label.lower()}{tag}"
    elif tag:
        name += tag
    return P, Y, name, meta


def bus_settings(base, P):
    """Apply P['gains'] to a {bus: settings} table, checking every name in
    P['gains'] and P['mute'] is a layer. Muted layers are still built (the
    score code writes to them); the piece leaves them out of the master."""
    unknown = (set(P.get("mute", [])) | set(P.get("gains", {}))) - set(base)
    if unknown:
        raise SystemExit(f"no layer(s) {sorted(unknown)}; the layers are {sorted(base)}")
    out = {}
    for k, kw in base.items():
        kw = dict(kw)
        if k in P.get("gains", {}):
            kw["gain"] = float(P["gains"][k])
        out[k] = kw
    return out
