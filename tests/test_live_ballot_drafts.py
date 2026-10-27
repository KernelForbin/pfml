"""LIVE TEST: ballot drafts' rules, run by the real database.

Skipped unless PFML_LIVE=1, and needs SUPABASE_URL and SUPABASE_SECRET_KEY
in .env and supabase/migrations/2026-10-27_ballot_drafts.sql run. There's
no Postgres here, so this is where draft_problem's SQL runs: each case is a
draft and what the database must say about it. It also checks a stranger
can't call the draft functions. Read-only: nothing is written. Saving and
reading drafts as real members is rehearsed by
supabase/checks/2026-10-27_ballot_drafts_rehearsal.sql, which the user runs.

    PFML_LIVE=1 python -m unittest discover -s tests -p test_live_ballot_drafts.py -v
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


def has_keys():
    supa._load_env_file()
    return all(os.environ.get(n) for n in ("SUPABASE_URL", "SUPABASE_SECRET_KEY"))


def problem(points, own=None, budget=19, most=5, down=0, down_most=0):
    own = own if own is not None else [False] * len(points)
    return supa.request("POST", "/rest/v1/rpc/draft_problem",
                        body={"p_budget": budget, "p_max": most, "p_down": down, "p_down_max": down_most,
                              "p_points": points, "p_own": own})


CASES = [
    ("nothing yet", [], None, {}, None),
    ("a few points, far from all", [3, 1], None, {}, None),
    ("every point", [5, 5, 5, 4], None, {}, None),
    ("one over the total", [5, 5, 5, 5], None, {}, "At most 19 points in all. This ballot has 20."),
    ("six on one track", [6], None, {}, "At most 5 points on one track."),
    ("points on your own track", [2, 1], [False, True], {}, "You can't give points to your own track."),
    ("a 0 on your own track", [2, 0], [False, True], {}, None),
    ("a downvote with none allowed", [2, -1], None, {}, "This round has no downvotes."),
    ("a downvote where allowed", [2, -1], None, {"down": 5, "down_most": 2}, None),
    ("too many downvotes", [2, -2, -2], None, {"down": 3, "down_most": 2}, "At most 3 downvotes in all. This ballot has 4."),
    ("lists that don't line up", [2], [], {}, "The ballot doesn't add up. Reload the page and try again."),
]


@unittest.skipUnless(LIVE and has_keys(), "live network test; set PFML_LIVE=1, with the keys in .env")
class LiveDraftRules(unittest.TestCase):
    def test_each_draft(self):
        for label, points, own, rules, want in CASES:
            with self.subTest(label):
                self.assertEqual(problem(points, own, **rules), want)


@unittest.skipUnless(LIVE and has_keys(), "live network test; set PFML_LIVE=1, with the keys in .env")
class LiveStrangersAreRefused(unittest.TestCase):
    def test_no_draft_function_answers_without_a_member(self):
        cfg = (support.ROOT / "site" / "config.js").read_text(encoding="utf-8")
        url = re.search(r"https://[a-z0-9]+\.supabase\.co", cfg).group(0)
        key = re.search(r'"(sb_publishable_[^"]+)"', cfg).group(1)
        calls = {"save_ballot_draft": {"p_round": None, "p_ballot": []}, "my_ballot_draft": {"p_round": None},
                 "draft_problem": {"p_budget": 19, "p_max": 5, "p_down": 0, "p_down_max": 0, "p_points": [1], "p_own": [False]}}
        for name, body in calls.items():
            with self.subTest(name):
                req = urllib.request.Request(f"{url}/rest/v1/rpc/{name}", data=json.dumps(body).encode(), method="POST",
                                             headers={"apikey": key, "Content-Type": "application/json"})
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(req, timeout=30)
                self.assertEqual(caught.exception.code, 401)

    def test_a_stranger_reads_no_draft(self):
        cfg = (support.ROOT / "site" / "config.js").read_text(encoding="utf-8")
        url = re.search(r"https://[a-z0-9]+\.supabase\.co", cfg).group(0)
        key = re.search(r'"(sb_publishable_[^"]+)"', cfg).group(1)
        req = urllib.request.Request(f"{url}/rest/v1/site_ballot_drafts?select=*&limit=1", headers={"apikey": key})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(req, timeout=30)
        self.assertIn(caught.exception.code, (401, 403))


if __name__ == "__main__":
    unittest.main()
