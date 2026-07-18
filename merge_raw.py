#!/usr/bin/env python3
"""
merge_raw.py — combine per-town gather shards into one <slug>.raw.json.

Usage:  python3 merge_raw.py <slug>            # in the folder with the shards
        python3 merge_raw.py <slug> --dir DIR

Looks for every  <slug>.<shard>.raw.json  (e.g. <slug>.bayside.raw.json,
<slug>.facts.raw.json) and merges them:
  - active_raw  : concatenated, de-duped by url then address
  - sales_raw   : concatenated, de-duped by (address, sold_date)
  - snapshot_raw: from the first shard that has it (usually the facts shard)
  - facts       : dict-merged (first non-empty value wins per key)
  - station_times: dict-merged
Writes <slug>.raw.json. Reports per-shard and total counts.
"""
import json, sys, glob, os
from pathlib import Path


def norm_addr(a):
    return "".join(ch for ch in str(a).lower() if ch.isalnum())


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    slug = sys.argv[1]
    d = Path(sys.argv[sys.argv.index("--dir") + 1]) if "--dir" in sys.argv else Path(".")
    shards = sorted(p for p in glob.glob(str(d / f"{slug}.*.raw.json"))
                    if not p.endswith(f"{slug}.raw.json"))
    if not shards:
        print(f"No shards found matching {slug}.*.raw.json in {d}"); sys.exit(1)

    out = {"snapshot_raw": None, "facts": {}, "active_raw": [],
           "sales_raw": [], "station_times": {}}
    seen_listing, seen_sale = set(), set()

    for sp in shards:
        s = json.loads(Path(sp).read_text())
        na = ns = 0
        for L in s.get("active_raw", []) or []:
            key = (L.get("url") or "").strip() or norm_addr(L.get("address", ""))
            if key and key not in seen_listing:
                seen_listing.add(key); out["active_raw"].append(L); na += 1
        for r in s.get("sales_raw", []) or []:
            key = (norm_addr(r.get("address", "")), str(r.get("sold_date", "")))
            if key not in seen_sale:
                seen_sale.add(key); out["sales_raw"].append(r); ns += 1
        if s.get("snapshot_raw") and not out["snapshot_raw"]:
            out["snapshot_raw"] = s["snapshot_raw"]
        for k, v in (s.get("facts") or {}).items():
            if v and not out["facts"].get(k):
                out["facts"][k] = v
        for k, v in (s.get("station_times") or {}).items():
            if v and k not in out["station_times"]:
                out["station_times"][k] = v
        print(f"  {Path(sp).name}: +{na} listings, +{ns} sales")

    Path(d / f"{slug}.raw.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"merged → {slug}.raw.json : {len(out['active_raw'])} listings, "
          f"{len(out['sales_raw'])} sales, facts={list(out['facts'])}")


if __name__ == "__main__":
    main()
