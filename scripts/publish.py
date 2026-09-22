#!/usr/bin/env python3
"""Build the site data and publish it to Supabase, where only members can
read it. This replaces "commit the JSON and let GitHub Pages serve it": the
season data no longer lives in the public repo or on the public site.

    python scripts/publish.py            build, then upload
    python scripts/publish.py --dry-run  build and list what would upload

What it does:
  0. looks up album art for any track it hasn't seen before (Spotify's
     public oEmbed endpoint, no key or account) and caches it in
     data/track_art.json, so the build itself stays offline
  1. runs scripts/build.py (site/data/*.json + site/seasonN.html), then
     writes site/data/playlist_stats.json: each home-page playlist's track
     count and running time, from Spotify's public pages (no key)
  2. uploads site/data/*.json to the private `league-data` bucket
  3. upserts every competitor into the `players` table, so invites can
     name them
  4. backs up data/season*/ (CSVs + daily_doubles.json), and
     data/comment_sentiment.json and data/track_art.json when present, to
     the private `league-exports` bucket, so the only copy isn't on one
     laptop

Needs SUPABASE_URL and SUPABASE_SECRET_KEY in .env (see scripts/supa.py).
Still stdlib-only.
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402
import supa   # noqa: E402

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


ART_CACHE = build.DATA_DIR / "track_art.json"


def backup_files():
    """What goes to the export bucket: every season folder's CSVs and JSON
    (the exports, and Season 3's hand-kept daily_doubles.json), plus the
    local-only files the build reads that would cost to rebuild: the
    comment sentiment labels (paid for per run of enrich_comments.py) and
    the album-art cache (hundreds of rate-limited Spotify lookups)."""
    files = [p for f in season_folders() for p in sorted(f.iterdir()) if p.suffix in (".csv", ".json")]
    files += [p for p in (build.SENTIMENT_PATH, ART_CACHE) if p.exists()]
    return files


class RateLimited(Exception):
    pass


def art_for(track_id):
    """Album art for one track from Spotify's oEmbed endpoint (public, no
    key). None when there's no art or the lookup fails; the page then
    shows a placeholder, and the next publish tries again. Spotify answers
    bursts with 429, so back off and retry, and give up for this run (raise
    RateLimited) if it keeps refusing."""
    url = "https://open.spotify.com/oembed?url=" + urllib.parse.quote(f"https://open.spotify.com/track/{track_id}")
    req = urllib.request.Request(url, headers={"User-Agent": "pfml-publish"})
    for wait in (2, 4, 8, 16, None):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read()).get("thumbnail_url")
        except urllib.error.HTTPError as e:
            if e.code != 429:
                return None
            if wait is None:
                raise RateLimited()
            time.sleep(wait)
        except Exception:  # noqa: BLE001 - art is decoration; never block a publish on it
            return None


def refresh_art():
    """Fill data/track_art.json for every track id in the exports that it
    doesn't have yet. Only new tracks are looked up, so after the first run
    this is a handful of requests per export."""
    cache = {}
    if ART_CACHE.exists():
        cache = json.loads(ART_CACHE.read_text(encoding="utf-8"))
    ids = set()
    for folder in season_folders():
        for r in build.read_csv(folder / "submissions.csv"):
            tid = build.track_id(r.get("Spotify URI"))
            if tid:
                ids.add(tid)
    missing = sorted(i for i in ids if not cache.get(i))
    if not missing:
        print(f"Album art: all {len(ids)} tracks cached.")
        return
    print(f"Album art: looking up {len(missing)} new track(s), one at a time...")
    try:
        for n, tid in enumerate(missing, 1):
            art = art_for(tid)
            if art:
                cache[tid] = art
            if n % 50 == 0:
                print(f"  {n}/{len(missing)}")
                ART_CACHE.write_text(json.dumps(cache, indent=0, sort_keys=True), encoding="utf-8")
            time.sleep(0.35)
    except RateLimited:
        print("  Spotify is rate limiting; stopping here. The rest will be looked up next publish.")
    ART_CACHE.write_text(json.dumps(cache, indent=0, sort_keys=True), encoding="utf-8")
    found = sum(1 for i in missing if cache.get(i))
    print(f"Album art: found {found} of {len(missing)}; {len(missing) - found} left for next publish.")


# ---- playlist tiles: track count and running time ----
# No key needed, but neither source is a documented API, so every step
# degrades to "no stats" rather than failing a publish. Measured
# 2026-09-22: the playlist page's <meta name="music:song_count"> is the
# full count (319 for a 319-track playlist); the embed page's __NEXT_DATA__
# lists each track's duration, but only the first 100 tracks, and ignores
# ?offset=. So up to 100 tracks the running time is exact; past that it's
# the first 100's average times the count, and marked as an estimate.

PLAYLIST_STATS = "playlist_stats.json"


def fetch_page(url):
    req = urllib.request.Request(url, headers={"User-Agent": "pfml-publish"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 - decoration; never block a publish on it
        return None


def parse_track_count(page_html):
    m = re.search(r'<meta name="music:song_count" content="(\d+)"', page_html or "")
    return int(m.group(1)) if m else None


def parse_embed_durations(embed_html):
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', embed_html or "", re.S)
    try:
        tracks = json.loads(m.group(1))["props"]["pageProps"]["state"]["data"]["entity"]["trackList"]
        return [int(t["duration"]) for t in tracks]
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def playlist_stats(pid):
    """{"tracks", "durationMs", "exact"} for one public playlist, or None."""
    count = parse_track_count(fetch_page(f"https://open.spotify.com/playlist/{pid}"))
    durations = parse_embed_durations(fetch_page(f"https://open.spotify.com/embed/playlist/{pid}"))
    if count is None or not durations:
        return None
    if len(durations) >= count:
        return {"tracks": count, "durationMs": sum(durations[:count]), "exact": True}
    return {"tracks": count, "durationMs": round(sum(durations) / len(durations) * count), "exact": False}


def refresh_playlist_stats():
    """site/data/playlist_stats.json, keyed by playlist id, for every link in
    the hand-kept playlists.json. A lookup that fails keeps the last good
    numbers, so a bad day at Spotify doesn't blank the tiles."""
    src, out = build.OUT_DIR / "playlists.json", build.OUT_DIR / PLAYLIST_STATS
    if not src.exists():
        return
    pl = json.loads(src.read_text(encoding="utf-8"))
    items = list(pl.get("leagueWide", [])) + [i for g in pl.get("seasons", []) for i in g.get("items", [])]
    ids = [pid for pid in (build.playlist_id(i.get("url") or "") for i in items) if pid]
    old = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    stats = {}
    for pid in ids:
        stats[pid] = playlist_stats(pid) or old.get(pid)
        time.sleep(0.35)
    stats = {k: v for k, v in stats.items() if v}
    out.write_text(json.dumps(stats, indent=0, sort_keys=True), encoding="utf-8")
    print(f"Playlists: stats for {len(stats)} of {len(ids)}.")


def main():
    ap = argparse.ArgumentParser(description="Build and publish PFML data to Supabase.")
    ap.add_argument("--dry-run", action="store_true", help="build and list uploads, send nothing")
    args = ap.parse_args()

    refresh_art()
    print("Building...")
    build.main()
    refresh_playlist_stats()

    json_files = sorted(build.OUT_DIR.glob("*.json"))
    exports = backup_files()
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
