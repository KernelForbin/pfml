#!/usr/bin/env python3
"""Build the site data and publish it to Supabase, where only members can
read it. This replaces "commit the JSON and let GitHub Pages serve it": the
season data no longer lives in the public repo or on the public site.

    python scripts/publish.py            build, then upload
    python scripts/publish.py --dry-run  build and list what would upload

What it does:
  1. runs scripts/build.py (site/data/*.json + site/seasonN.html)
  2. uploads site/data/*.json to the private `league-data` bucket
  3. upserts every competitor into the `players` table, so invites can
     name them
  4. backs up data/season*/ (CSVs + daily_doubles.json) to the private
     `league-exports` bucket, so the only copy isn't on one laptop

Needs SUPABASE_URL and SUPABASE_SECRET_KEY in .env (see scripts/supa.py).
Still stdlib-only.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402
import supa   # noqa: E402

ROOT = build.ROOT
DATA_BUCKET = "league-data"
EXPORT_BUCKET = "league-exports"


def season_folders():
    return sorted(
        [p for p in build.DATA_DIR.iterdir() if p.is_dir() and re.fullmatch(r"season\d+", p.name)],
        key=lambda p: int(re.search(r"\d+", p.name).group()),
    )


def all_players():
    """Every competitor across every season. Same join as the Career page:
    the first name seen for an id wins."""
    names = {}
    for folder in season_folders():
        for r in build.read_csv(folder / "competitors.csv"):
            names.setdefault(r["ID"], r["Name"])
    return [{"competitor_id": cid, "name": n} for cid, n in names.items()]


def main():
    ap = argparse.ArgumentParser(description="Build and publish PFML data to Supabase.")
    ap.add_argument("--dry-run", action="store_true", help="build and list uploads, send nothing")
    args = ap.parse_args()

    print("Building...")
    build.main()

    json_files = sorted(build.OUT_DIR.glob("*.json"))
    exports = [p for f in season_folders() for p in sorted(f.iterdir())
               if p.suffix in (".csv", ".json")]
    players = all_players()

    if args.dry_run:
        print(f"\nWould upload to {DATA_BUCKET}: {', '.join(p.name for p in json_files)}")
        print(f"Would back up to {EXPORT_BUCKET}: {len(exports)} files")
        print(f"Would upsert {len(players)} players")
        return

    supa.config()  # fail fast on missing keys, before any upload
    for p in json_files:
        supa.upload(DATA_BUCKET, p.name, p.read_bytes(), "application/json")
    print(f"Uploaded {len(json_files)} data files to {DATA_BUCKET}.")

    supa.request("POST", "/rest/v1/players", body=players,
                 headers={"Prefer": "resolution=merge-duplicates,return=minimal"})
    print(f"Upserted {len(players)} players.")

    for p in exports:
        rel = p.relative_to(build.DATA_DIR).as_posix()
        ctype = "text/csv" if p.suffix == ".csv" else "application/json"
        supa.upload(EXPORT_BUCKET, rel, p.read_bytes(), ctype)
    print(f"Backed up {len(exports)} export files to {EXPORT_BUCKET}.")

    print("\nDone. If build.py created or changed site/seasonN.html (a new season), "
          "commit and push those pages; the data itself is never committed.")


if __name__ == "__main__":
    main()
