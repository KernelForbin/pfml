"""Shared test helpers.

Every test builds its own tiny, made-up season in a temp directory and
points build.py's data paths there, so no test ever reads or writes the
real exports in data/ or the real output in site/data/. Players, rounds and
tracks here are invented; none of it is league data."""
import contextlib
import csv
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build  # noqa: E402
import publish  # noqa: E402

REAL_DATA_DIR = build.DATA_DIR
REAL_OUT_DIR = build.OUT_DIR

# Music League's export columns, copied from a real export's header row.
HEADERS = {
    "competitors": ["ID", "Name"],
    "rounds": ["ID", "Created", "Name", "Description", "Playlist URL"],
    "submissions": ["Spotify URI", "Title", "Album", "Artist(s)", "Submitter ID", "Created",
                    "Comment", "Round ID", "Visible To Voters"],
    "votes": ["Spotify URI", "Voter ID", "Created", "Points Assigned", "Comment", "Round ID"],
}

PLAYERS = {"p1": "Ann", "p2": "Ben", "p3": "Cat", "p4": "Dan"}


def uri(track):
    return f"spotify:track:{track}"


def write_csv(path, kind, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADERS[kind])
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in HEADERS[kind]})


def make_season(folder, rounds, players=PLAYERS, daily_doubles=None):
    """rounds: list of dicts
         {"id", "name", "created", "subs": [(track, submitter, note)],
          "votes": [(voter, track, points, comment)]}
    Writes the four CSVs (and daily_doubles.json if given) into folder."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    write_csv(folder / "competitors.csv", "competitors",
              [{"ID": pid, "Name": name} for pid, name in players.items()])
    write_csv(folder / "rounds.csv", "rounds", [
        {"ID": r["id"], "Created": r["created"], "Name": r["name"],
         "Description": r.get("description", ""), "Playlist URL": ""} for r in rounds])
    subs, votes = [], []
    for r in rounds:
        for track, submitter, *rest in r["subs"]:
            subs.append({"Spotify URI": uri(track), "Title": f"Song {track}", "Album": f"Album {track}",
                         "Artist(s)": f"Artist {track}", "Submitter ID": submitter,
                         "Created": r["created"], "Comment": rest[0] if rest else "",
                         "Round ID": r["id"], "Visible To Voters": "Yes"})
        for voter, track, points, *rest in r.get("votes", []):
            votes.append({"Spotify URI": uri(track), "Voter ID": voter, "Created": r["created"],
                          "Points Assigned": str(points), "Comment": rest[0] if rest else "",
                          "Round ID": r["id"]})
    write_csv(folder / "submissions.csv", "submissions", subs)
    write_csv(folder / "votes.csv", "votes", votes)
    if daily_doubles is not None:
        (folder / "daily_doubles.json").write_text(
            daily_doubles if isinstance(daily_doubles, str) else json.dumps(daily_doubles),
            encoding="utf-8")
    return folder


@contextlib.contextmanager
def sandbox():
    """A temp root with data/ and site/data/, and build.py + publish.py
    pointed at it for the duration. Yields the root Path."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        data_dir, out_dir = root / "data", root / "site" / "data"
        data_dir.mkdir()
        out_dir.mkdir(parents=True)
        with mock.patch.object(build, "DATA_DIR", data_dir), \
             mock.patch.object(build, "OUT_DIR", out_dir), \
             mock.patch.object(build, "SENTIMENT_PATH", data_dir / "comment_sentiment.json"), \
             mock.patch.object(publish, "ART_CACHE", data_dir / "track_art.json"):
            assert build.DATA_DIR != REAL_DATA_DIR and build.OUT_DIR != REAL_OUT_DIR
            yield root


def quiet():
    """build.py prints progress and warnings; keep test output readable."""
    return contextlib.redirect_stdout(io.StringIO())
