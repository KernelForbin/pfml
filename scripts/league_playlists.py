#!/usr/bin/env python3
"""Keep the league's own Spotify playlists up to date with finished rounds.

    python scripts/league_playlists.py --dry-run     # say what's missing; add nothing
    python scripts/league_playlists.py               # add it
    python scripts/league_playlists.py --season 3    # a particular season (default: the newest)

Asked for 2026-11-02: once a round's data comes in, every track goes on
"All Tracks Submitted" and the season's "All Submissions", and its top 3
on "All Podium Tracks" and the season's "Podium Tracks". The playlists are
the ones linked on Home (site/data/playlists.json), all on the user's own
Spotify account, so this uses round_playlists.py's sign-in (.env).

What it reads is what publish.py just built: site/data/seasonN.json, each
round's tracks with their places. The top 3 is every track placed 1st to
3rd, so a tie at 3rd adds every tied track (the user's call, 2026-11-02);
a site round's YouTube or SoundCloud pick goes by its Spotify copy, and a
track with none is skipped and named. A track already on a playlist is
never added again, so a rerun adds nothing, and nothing is ever removed.

Where new tracks go follows how the user had been adding them by hand
(measured 2026-11-02): at the end, round by round, in the export's order
(Music League's own), except "All Podium Tracks", where the newest round
goes on top, then each round's tracks by place.

Nothing secret is printed. Stdlib only.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402
import round_playlists as rp  # noqa: E402

PLAYLISTS_FILE = "playlists.json"
ALL_TRACKS, ALL_PODIUM = "All Tracks Submitted", "All Podium Tracks"
SEASON_ALL, SEASON_PODIUM = "All Submissions", "Podium Tracks"
PODIUM = 3


def playlist_key(url):
    m = re.search(r"open\.spotify\.com/(?:intl-[\w-]+/)?playlist/([A-Za-z0-9]{22})", url or "")
    return m.group(1) if m else None


def find_playlists(config, season_label):
    """{kind: (label, playlist id)} for the four this season fills, from
    Home's playlists.json. A name ending says which is which; one that
    isn't there, or has no link yet, is left out."""
    found = {}
    for kind, items in ((ALL_TRACKS, config.get("leagueWide")), (ALL_PODIUM, config.get("leagueWide"))):
        for it in items or []:
            if it.get("label", "").endswith(kind) and playlist_key(it.get("url")):
                found[kind] = (it["label"], playlist_key(it["url"]))
    for group in config.get("seasons") or []:
        if group.get("season") != season_label:
            continue
        for kind in (SEASON_ALL, SEASON_PODIUM):
            for it in group.get("items") or []:
                if it.get("label", "").endswith(kind) and playlist_key(it.get("url")):
                    found[kind] = (it["label"], playlist_key(it["url"]))
    return found


def export_order(folder):
    """{(round id, spotify id): position} in the order the rounds' tracks
    were exported: Music League's submissions.csv, then site rounds."""
    order = {}
    for row in build.read_csv(folder / "submissions.csv"):
        order.setdefault((row["Round ID"], build.track_id(row["Spotify URI"])), len(order))
    _, _, subs, _, extras = build.site_season_rows(folder)
    for row in subs:
        spotify = (extras.get((row["Round ID"], row["Spotify URI"])) or {}).get("spotifyId")
        order.setdefault((row["Round ID"], spotify), len(order))
    return order


def same_song(title, artists):
    """A track's name and artists, to know it again under another id."""
    return (title or "").strip().casefold(), (artists or "").strip().casefold()


def season_tracks(season, order):
    """Per round, oldest first: (round name, every track in export order,
    the podium by place). Each track is (spotify id or None, title, its
    same_song)."""
    out = []
    for r in season["rounds"]:
        songs = r.get("songs") or []
        everything = sorted(songs, key=lambda s: order.get((r["id"], s.get("spotifyId")), len(order)))
        podium = sorted((s for s in songs if s.get("place") and s["place"] <= PODIUM), key=lambda s: s["place"])
        pick = lambda ss: [(s.get("spotifyId"), f'{s.get("title")} - {s.get("artistText")}',
                            same_song(s.get("title"), s.get("artistText"))) for s in ss]
        out.append((r.get("name") or r["id"], pick(everything), pick(podium)))
    return out


def on_playlist(row, have):
    """Whether a planned (round, id, title, same_song) is on a playlist
    already. By id, or by exact name and artists: Spotify can keep another
    recording than the id it was sent, with nothing saying so (measured
    2026-11-02: one track sent as a single went on as a compilation's copy),
    and a rerun would otherwise add it again."""
    ids, songs = have
    return row[1] in ids or row[3] in songs


def plan(rounds, have):
    """What to add to each playlist, as {kind: [(round, spotify id, title,
    same_song)]}, in the order it goes in, plus the tracks with no Spotify
    copy. `have` is {kind: playlist_items()}."""
    want = {ALL_TRACKS: [], SEASON_ALL: [], SEASON_PODIUM: [], ALL_PODIUM: []}
    skipped = []
    for name, everything, podium in rounds:
        for kinds, tracks in (((ALL_TRACKS, SEASON_ALL), everything), ((SEASON_PODIUM, ALL_PODIUM), podium)):
            for spotify, title, song in tracks:
                if not spotify:
                    if kinds[0] == ALL_TRACKS:
                        skipped.append((name, title))
                    continue
                for kind in kinds:
                    want[kind].append((name, spotify, title, song))
    # newest round on top of All Podium Tracks, each round still by place
    by_round = {}
    for row in want[ALL_PODIUM]:
        by_round.setdefault(row[0], []).append(row)
    want[ALL_PODIUM] = [row for name in reversed(list(by_round)) for row in by_round[name]]
    for kind, rows in want.items():
        ids, songs = (set(x) for x in have.get(kind) or ([], []))
        keep = []
        for row in rows:
            if not on_playlist(row, (ids, songs)):
                ids.add(row[1])
                songs.add(row[3])
                keep.append(row)
        want[kind] = keep
    return want, skipped


def playlist_items(spotify, playlist_id):
    """(every track id on a playlist, in order; their same_song). Spotify's
    rows carry the track as "item" (measured 2026-11-02; it was "track")."""
    ids, songs, offset = [], [], 0
    while True:
        page = spotify.call("GET", f"/playlists/{playlist_id}/items", {"limit": 100, "offset": offset})
        for row in page.get("items") or []:
            t = row.get("item") or row.get("track")
            if t and t.get("type", "track") == "track" and t.get("id"):
                ids.append(t["id"])
                songs.append(same_song(t.get("name"), ", ".join(a.get("name", "") for a in t.get("artists") or [])))
        if not page.get("next"):
            return ids, songs
        offset += 100


def add_items(spotify, playlist_id, track_ids, top=False):
    """Adds in hundreds (Spotify's limit), at the end, or from the top in
    this order."""
    for i in range(0, len(track_ids), 100):
        body = {"uris": ["spotify:track:" + t for t in track_ids[i:i + 100]]}
        if top:
            body["position"] = i
        spotify.call("POST", f"/playlists/{playlist_id}/items", body=body)


def run(season_num=None, dry_run=False, spotify=None, log=print):
    folders = build.season_folders()
    if season_num is not None:
        folders = [f for f in folders if f.name == f"season{season_num}"]
    if not folders:
        raise SystemExit(f"No data/season{season_num or 'N'} folder.")
    folder = folders[-1]
    season_path = build.OUT_DIR / f"{folder.name}.json"
    if not season_path.exists():
        raise SystemExit(f"No {season_path.name} in site/data. Run python scripts/publish.py first.")
    season = json.loads(season_path.read_text(encoding="utf-8"))
    config_path = build.OUT_DIR / PLAYLISTS_FILE
    config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    label = season.get("label") or f"Season {re.search(r'[0-9]+', folder.name).group()}"
    found = find_playlists(config, label)
    for kind in (ALL_TRACKS, SEASON_ALL, SEASON_PODIUM, ALL_PODIUM):
        if kind not in found:
            log(f"  ! No linked \"{kind}\" playlist for {label} in {PLAYLISTS_FILE}; skipping it.")

    spotify = spotify or rp.Spotify()
    have = {kind: playlist_items(spotify, pid) for kind, (_, pid) in found.items()}
    want, skipped = plan(season_tracks(season, export_order(folder)), have)

    log(f"{label}: {len(season['rounds'])} finished round(s).")
    for name, title in skipped:
        log(f"  ! {name}: no Spotify copy, skipped: {title}")
    added = 0
    for kind in (ALL_TRACKS, SEASON_ALL, SEASON_PODIUM, ALL_PODIUM):
        if kind not in found:
            continue
        playlist, pid = found[kind]
        rows = want[kind]
        where = " (on top)" if kind == ALL_PODIUM else ""
        log(f"{playlist}: has {len(have[kind][0])}, {'would add' if dry_run else 'adding'} {len(rows)}{where}")
        for name, _, title, _ in rows:
            log(f"    {name}: {title}")
        if rows and not dry_run:
            add_items(spotify, pid, [r[1] for r in rows], top=kind == ALL_PODIUM)
            ids, songs = playlist_items(spotify, pid)
            missing = [r for r in rows if not on_playlist(r, (set(ids), set(songs)))]
            if missing:
                raise SystemExit(f"{playlist}: {len(missing)} track(s) didn't go on. Stopped here; "
                                 "the playlists above it were updated, the ones below it weren't.")
            added += len(rows)
    if dry_run:
        log("Dry run: nothing added.")
    else:
        log(f"Added {added} in all; every one checked back on its playlist.")
    return want


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--season", type=int, help="season number (default: the newest)")
    ap.add_argument("--dry-run", action="store_true", help="say what's missing; add nothing")
    args = ap.parse_args()
    # a Windows console's cp1252 can't print every title (Nordic letters
    # stopped the first dry run partway, 2026-11-02)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    run(args.season, args.dry_run)


if __name__ == "__main__":
    main()
