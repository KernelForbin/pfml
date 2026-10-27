"""LIVE TEST: the round demo's practice ballot, against the real database.

Skipped unless PFML_LIVE=1, and needs SUPABASE_URL and SUPABASE_SECRET_KEY
in .env and supabase/migrations/2026-10-27_demo_ballots.sql run. Runs
demo_ballot_problem on the newest round with tracks, and checks a stranger
can't call the practice functions or read the table. Read-only: nothing is
written. Saving and reading as real members is rehearsed by
supabase/checks/2026-10-27_demo_ballots_rehearsal.sql, which the user runs.

    PFML_LIVE=1 python -m unittest discover -s tests -p test_live_demo_ballots.py -v
"""
import json
import os
import re
import unittest
import urllib.error
import urllib.request

import support  # noqa: F401  (puts scripts/ on the path)
import supa  # noqa: E402

LIVE = os.environ.get("PFML_LIVE") == "1"
WRONG = "The ballot doesn't add up. Reload the page and try again."


def has_keys():
    supa._load_env_file()
    return all(os.environ.get(n) for n in ("SUPABASE_URL", "SUPABASE_SECRET_KEY"))


def problem(round_id, ballot):
    return supa.request("POST", "/rest/v1/rpc/demo_ballot_problem", body={"p_round": round_id, "p_ballot": ballot})


@unittest.skipUnless(LIVE and has_keys(), "live network test; set PFML_LIVE=1, with the keys in .env")
class LivePracticeRules(unittest.TestCase):
    def test_each_ballot(self):
        rows = supa.request("GET", "/rest/v1/site_submissions?select=id,round_id&order=round_id&limit=2")
        self.assertTrue(rows, "needs a round with tracks")
        rid, sid = rows[0]["round_id"], rows[0]["id"]
        cases = [
            ("nothing yet", [], None),
            ("a few points and a comment", [{"submission": sid, "points": 3, "comment": "Nice"}], None),
            ("a downvote's shape", [{"submission": sid, "points": -2}], None),
            ("a track from nowhere", [{"submission": "00000000-0000-4000-8000-000000000000", "points": 1}], WRONG),
            ("the same track twice", [{"submission": sid, "points": 1}, {"submission": sid, "points": 2}], WRONG),
            ("points as words", [{"submission": sid, "points": "lots"}], WRONG),
            ("half a point", [{"submission": sid, "points": 1.5}], WRONG),
            ("a long comment", [{"submission": sid, "points": 0, "comment": "x" * 2001}], "A comment can be at most 2000 characters."),
            ("not a list", {"submission": sid}, WRONG),
        ]
        for label, ballot, want in cases:
            with self.subTest(label):
                self.assertEqual(problem(rid, ballot), want)


@unittest.skipUnless(LIVE and has_keys(), "live network test; set PFML_LIVE=1, with the keys in .env")
class LiveStrangersAreRefused(unittest.TestCase):
    def setUp(self):
        cfg = (support.ROOT / "site" / "config.js").read_text(encoding="utf-8")
        self.url = re.search(r"https://[a-z0-9]+\.supabase\.co", cfg).group(0)
        self.key = re.search(r'"(sb_publishable_[^"]+)"', cfg).group(1)

    def test_no_practice_function_answers_without_a_member(self):
        calls = {"save_demo_ballot": {"p_round": None, "p_ballot": [], "p_submit": False},
                 "my_demo_ballot": {"p_round": None},
                 "demo_ballot_problem": {"p_round": None, "p_ballot": []}}
        for name, body in calls.items():
            with self.subTest(name):
                req = urllib.request.Request(f"{self.url}/rest/v1/rpc/{name}", data=json.dumps(body).encode(), method="POST",
                                             headers={"apikey": self.key, "Content-Type": "application/json"})
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(req, timeout=30)
                self.assertEqual(caught.exception.code, 401)

    def test_a_stranger_reads_no_practice_ballot(self):
        req = urllib.request.Request(f"{self.url}/rest/v1/site_demo_ballots?select=*&limit=1", headers={"apikey": self.key})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(req, timeout=30)
        self.assertIn(caught.exception.code, (401, 403))


if __name__ == "__main__":
    unittest.main()
