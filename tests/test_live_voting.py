"""LIVE TEST: voting on the site's ballot rules, run by the real database.

Skipped unless PFML_LIVE=1, and needs SUPABASE_URL and SUPABASE_SECRET_KEY
in .env and supabase/migrations/2026-10-25_site_voting.sql run. There's no
Postgres here, so this is where ballot_problem's SQL runs: each case is a
ballot and what the database must say about it. It also checks a stranger
can't call any voting function. Read-only: nothing is written. The whole
round, writes included, is rehearsed by
supabase/checks/2026-10-25_site_voting_rehearsal.sql, which the user runs.

    PFML_LIVE=1 python -m unittest discover -s tests -p test_live_voting.py -v
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


def problem(points, own=None, budget=19, most=5):
    own = own if own is not None else [False] * len(points)
    return supa.request("POST", "/rest/v1/rpc/ballot_problem",
                        body={"p_budget": budget, "p_max": most, "p_points": points, "p_own": own})


CASES = [
    ("every point spent, none over the cap", [5, 5, 5, 4], None, None),
    ("the same, with a 0 on your own track", [5, 5, 5, 4, 0], [False, False, False, False, True], None),
    ("a point short", [5, 5, 5, 3], None, "Spend exactly 19 points. This ballot has 18."),
    ("a point over", [5, 5, 5, 5], None, "Spend exactly 19 points. This ballot has 20."),
    ("six on one track", [6, 5, 5, 3], None, "At most 5 points on one track."),
    ("a negative", [5, 5, 5, 5, -1], None, "Points can't be negative."),
    ("points on your own track", [5, 5, 5, 3, 1], [False, False, False, False, True], "You can't give points to your own track."),
    ("lists that don't line up", [5, 5, 5, 4], [False], "The ballot doesn't add up. Reload the page and try again."),
    ("an empty ballot", [], [], "Spend exactly 19 points. This ballot has 0."),
]


@unittest.skipUnless(LIVE and has_keys(), "live network test; set PFML_LIVE=1, with the keys in .env")
class LiveBallotRules(unittest.TestCase):
    def test_each_ballot(self):
        for label, points, own, want in CASES:
            with self.subTest(label):
                self.assertEqual(problem(points, own), want)

    def test_the_rules_come_from_the_round(self):
        self.assertIsNone(problem([3, 1], budget=4, most=3))
        self.assertEqual(problem([4], budget=4, most=3), "At most 3 points on one track.")


def problem_down(points, own=None, budget=19, most=5, down=5, down_most=5):
    """The rule cast_ballot calls since downvotes (README, More songs and
    downvotes)."""
    own = own if own is not None else [False] * len(points)
    return supa.request("POST", "/rest/v1/rpc/ballot_problem",
                        body={"p_budget": budget, "p_max": most, "p_down": down, "p_down_max": down_most,
                              "p_points": points, "p_own": own})


DOWN_CASES = [
    ("downvotes are optional", [5, 5, 5, 4], None, {}, None),
    ("Season 1's shape: 16 up, 5 down", [5, 5, 4, 2, -5], None, {"budget": 16}, None),
    ("downvotes don't count toward the upvotes", [5, 5, 5, 3, -1], None, {}, "Spend exactly 19 points. This ballot has 18."),
    ("one downvote over the limit", [5, 5, 5, 4, -3, -3], None, {}, "At most 5 downvotes in all. This ballot has 6."),
    ("too many on one song", [5, 5, 5, 4, -3], None, {"down_most": 2}, "At most 2 downvotes on one track."),
    ("none allowed", [5, 5, 5, 4, -1], None, {"down": 0, "down_most": 0}, "This round has no downvotes."),
    ("a downvote on your own track", [5, 5, 5, 4, -1], [False, False, False, False, True], {}, "You can't give points to your own track."),
    ("two tracks of your own", [5, 5, 5, 4, 0, 0], [False, False, False, False, True, True], {}, None),
]


@unittest.skipUnless(LIVE and has_keys(), "live network test; set PFML_LIVE=1, with the keys in .env")
class LiveDownvoteRules(unittest.TestCase):
    def test_each_ballot(self):
        for label, points, own, rules, want in DOWN_CASES:
            with self.subTest(label):
                self.assertEqual(problem_down(points, own, **rules), want)


@unittest.skipUnless(LIVE and has_keys(), "live network test; set PFML_LIVE=1, with the keys in .env")
class LiveStrangersAreRefused(unittest.TestCase):
    def test_no_voting_function_answers_without_a_member(self):
        cfg = (support.ROOT / "site" / "config.js").read_text(encoding="utf-8")
        url = re.search(r"https://[a-z0-9]+\.supabase\.co", cfg).group(0)
        key = re.search(r'"(sb_publishable_[^"]+)"', cfg).group(1)
        calls = {"cast_ballot": {"p_round": None, "p_ballot": []}, "my_ballot": {"p_round": None},
                 "site_round_voters": {"p_round": None}, "site_round_results": {"p_round": None},
                 "site_round_votes": {"p_round": None}, "site_round_phase": {"p_round": None},
                 "ballot_problem": {"p_budget": 19, "p_max": 5, "p_points": [19], "p_own": [False]},
                 "withdraw_track": {"p_round": None, "p_tag": None}}
        for name, body in calls.items():
            with self.subTest(name):
                req = urllib.request.Request(f"{url}/rest/v1/rpc/{name}", data=json.dumps(body).encode(), method="POST",
                                             headers={"apikey": key, "Content-Type": "application/json"})
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(req, timeout=30)
                self.assertEqual(caught.exception.code, 401)


if __name__ == "__main__":
    unittest.main()
