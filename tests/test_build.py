"""scripts/build.py: the scoring rules the site shows. Offline, made-up data."""
import json
import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

from support import ROOT, build, make_season, quiet, sandbox, uri

# One round, four players. a and b tie on 3; Dan's row on c is 0 points
# with a comment, which is a comment, not a vote.
TIE_ROUND = {
    "id": "r1", "name": "Round One", "created": "2025-01-01T00:00:00Z",
    "subs": [("a", "p1"), ("b", "p2"), ("c", "p3"), ("d", "p4")],
    "votes": [("p1", "b", 2), ("p1", "c", 1),
              ("p2", "a", 2), ("p2", "c", 1),
              ("p3", "a", 1), ("p3", "b", 1), ("p3", "d", 1),
              ("p4", "c", 0, "nice pick")],
}
# A second round: e (Ann) and f (Ben) tie on 3.
SECOND_ROUND = {
    "id": "r2", "name": "Round Two", "created": "2025-01-08T00:00:00Z",
    "subs": [("e", "p1"), ("f", "p2")],
    "votes": [("p3", "e", 2), ("p3", "f", 1), ("p4", "e", 1), ("p4", "f", 2)],
}


def song(data, track):
    for r in data["rounds"]:
        for s in r["songs"]:
            if s["spotifyId"] == track:
                return s
    raise KeyError(track)


def player(data, pid):
    return next(p for p in data["standings"] if p["id"] == pid)


def dd_request(round_id, track, submitter, decision="accepted"):
    return {"roundId": round_id, "spotifyUri": uri(track), "submitterId": submitter, "decision": decision}


class Scoring(unittest.TestCase):
    def build(self, rounds, **kw):
        with sandbox() as root, quiet():
            folder = make_season(root / "data" / "season1", rounds, **kw)
            data, _ = build.build_season(folder, "season1", "Season 1")
        return data

    def test_zero_point_row_is_a_comment_not_a_vote(self):
        c = song(self.build([TIE_ROUND]), "c")
        self.assertEqual(c["points"], 2)
        self.assertEqual(sorted(v[0] for v in c["votes"]), ["p1", "p2"])
        self.assertIn("p4", [x["voterId"] for x in c["comments"]])

    def test_comment_id_is_round_track_voter(self):
        # Member votes, reactions and replies in Supabase are keyed on this.
        c = song(self.build([TIE_ROUND]), "c")
        self.assertEqual(c["comments"][0]["id"], "r1|spotify:track:c|p4")

    def test_equal_points_share_a_place_in_a_round(self):
        data = self.build([TIE_ROUND])
        places = {s["spotifyId"]: s["place"] for s in data["rounds"][0]["songs"]}
        self.assertEqual(places, {"a": 1, "b": 1, "c": 3, "d": 4})

    def test_standings_ties_share_a_place_and_are_flagged(self):
        data = self.build([TIE_ROUND])
        ranks = {p["id"]: (p["rank"], p["tied"]) for p in data["standings"]}
        self.assertEqual(ranks, {"p1": (1, True), "p2": (1, True), "p3": (3, False), "p4": (4, False)})

    def test_daily_double_doubles_the_total_not_the_round_score(self):
        data = self.build([TIE_ROUND, SECOND_ROUND],
                          daily_doubles={"reviewedRounds": [], "requests": [dd_request("r2", "e", "p1")]})
        ann = player(data, "p1")
        self.assertEqual(ann["points"], 3 + 3 + 3)
        self.assertEqual(ann["avgPerSubmission"], 3.0)
        self.assertEqual(song(data, "e")["points"], 3)
        self.assertEqual(song(data, "e")["dailyDouble"], {"bonus": 3})

    def test_second_daily_double_by_the_same_player_is_ignored(self):
        data = self.build([TIE_ROUND, SECOND_ROUND], daily_doubles={
            "reviewedRounds": [], "requests": [dd_request("r1", "a", "p1"), dd_request("r2", "e", "p1")]})
        self.assertEqual(player(data, "p1")["points"], 9)
        self.assertEqual(player(data, "p1")["dailyDouble"]["roundId"], "r1")
        self.assertNotIn("dailyDouble", song(data, "e"))

    def test_rejected_daily_double_is_not_applied(self):
        data = self.build([TIE_ROUND, SECOND_ROUND], daily_doubles={
            "reviewedRounds": [], "requests": [dd_request("r2", "e", "p1", decision="rejected")]})
        self.assertEqual(player(data, "p1")["points"], 6)

    def test_daily_double_matching_no_submission_stops_the_build(self):
        with self.assertRaises(SystemExit):
            self.build([TIE_ROUND], daily_doubles={"reviewedRounds": [],
                                                    "requests": [dd_request("r1", "nope", "p1")]})

    def test_unreadable_daily_double_file_stops_the_build(self):
        with self.assertRaises(SystemExit):
            self.build([TIE_ROUND], daily_doubles="{not json")

    def test_blowout_is_hidden_when_no_round_was_won_by_more_than_the_closest(self):
        self.assertNotIn("blowoutRound", self.build([TIE_ROUND])["highlights"])

    def test_blowout_names_the_widest_winning_margin(self):
        wide = {"id": "r2", "name": "Round Two", "created": "2025-01-08T00:00:00Z",
                "subs": [("e", "p1"), ("f", "p2")],
                "votes": [("p3", "e", 3), ("p4", "e", 2), ("p4", "f", 1)]}
        blowout = self.build([TIE_ROUND, wide])["highlights"]["blowoutRound"]
        self.assertEqual((blowout["name"], blowout["margin"]), ("Round Two", 4))

    def test_album_art_comes_from_the_cache_and_is_optional(self):
        with sandbox() as root, quiet():
            (root / "data" / "track_art.json").write_text(json.dumps({"a": "https://img.example/a.jpg"}))
            folder = make_season(root / "data" / "season1", [TIE_ROUND])
            data, _ = build.build_season(folder, "season1", "Season 1")
        self.assertEqual(song(data, "a")["art"], "https://img.example/a.jpg")
        self.assertIsNone(song(data, "b")["art"])


class ReadCsv(unittest.TestCase):
    def test_line_breaks_inside_cells_become_lf(self):
        # A Windows checkout hands the build CRLF; the Linux deploy sees LF.
        with sandbox() as root:
            p = root / "votes.csv"
            p.write_bytes(b'Comment,Round ID\r\n"line one\r\nline two",r1\r\n')
            rows = build.read_csv(p)
        self.assertEqual(rows[0]["Comment"], "line one\nline two")


class Main(unittest.TestCase):
    def test_writes_season_page_and_names_every_co_leader(self):
        with sandbox() as root, quiet():
            (root / "site" / "season.template.html").write_text(
                "<title>{{TITLE}}</title><body data-season-key=\"{{SEASON_KEY}}\">{{LABEL}}", encoding="utf-8")
            make_season(root / "data" / "season1", [TIE_ROUND])
            build.main()
            page = (root / "site" / "season1.html").read_text(encoding="utf-8")
            index = json.loads((root / "site" / "data" / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(page, '<title>PFML - Season 1</title><body data-season-key="season1">Season 1')
        self.assertEqual(index["seasons"][0]["leaderNames"], ["Ann", "Ben"])


class Deterministic(unittest.TestCase):
    def test_same_output_under_different_hash_seeds(self):
        # A set of voter ids once leaked Python's per-process hash order into
        # the taste list, so every build differed. Build the same season in
        # fresh interpreters with different seeds and compare byte for byte.
        runner = textwrap.dedent(f"""
            import json, sys
            sys.path.insert(0, {str(ROOT / 'tests')!r})
            from support import build, make_season, sandbox, quiet
            from test_build import TIE_ROUND, SECOND_ROUND
            with sandbox() as root, quiet():
                folder = make_season(root / "data" / "season1", [TIE_ROUND, SECOND_ROUND])
                data, _ = build.build_season(folder, "season1", "Season 1")
            sys.stdout.write(json.dumps(data, sort_keys=False))
        """)
        outputs = set()
        for seed in ("1", "2", "3", "4", "5", "6"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            res = subprocess.run([sys.executable, "-c", runner], capture_output=True, text=True, env=env,
                                 cwd=str(ROOT / "tests"))
            self.assertEqual(res.returncode, 0, res.stderr)
            outputs.add(res.stdout)
        self.assertEqual(len(outputs), 1)


if __name__ == "__main__":
    unittest.main()
