"""LIVE TEST: DJs, Spectators and prompters, against the real database.

Skipped unless PFML_LIVE=1, and needs SUPABASE_URL and SUPABASE_SECRET_KEY
in .env and supabase/migrations/2026-10-29_season_roles.sql run. Checks that
the new columns and functions are there, that a round outside a season set
up on the site makes everyone a DJ, and that a stranger can't call any of it
or read the new tables. Read-only: nothing is written. The whole flow,
members and all, is rehearsed by
supabase/checks/2026-10-29_season_roles_rehearsal.sql, which the user runs.

    PFML_LIVE=1 python -m unittest discover -s tests -p test_live_season_roles.py -v
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
NO_ROUND = "00000000-0000-4000-8000-000000000000"


def has_keys():
    supa._load_env_file()
    return all(os.environ.get(n) for n in ("SUPABASE_URL", "SUPABASE_SECRET_KEY"))


@unittest.skipUnless(LIVE and has_keys(), "live network test; set PFML_LIVE=1, with the keys in .env")
class LiveRoles(unittest.TestCase):
    def test_the_role_column_and_tables_are_there(self):
        supa.request("GET", "/rest/v1/site_season_players?select=role&limit=1")
        supa.request("GET", "/rest/v1/site_round_roles?select=round_id,competitor_id,role&limit=1")
        supa.request("GET", "/rest/v1/site_round_prompters?select=round_id,competitor_id&limit=1")

    def test_outside_a_season_everyone_is_a_dj(self):
        self.assertEqual(supa.request("POST", "/rest/v1/rpc/site_round_role", body={"p_round": NO_ROUND, "p_competitor": "nobody"}), "dj")
        self.assertEqual(supa.request("POST", "/rest/v1/rpc/site_round_dj_count", body={"p_round": NO_ROUND}), 0)


@unittest.skipUnless(LIVE and has_keys(), "live network test; set PFML_LIVE=1, with the keys in .env")
class LiveStrangersAreRefused(unittest.TestCase):
    def setUp(self):
        cfg = (support.ROOT / "site" / "config.js").read_text(encoding="utf-8")
        self.url = re.search(r"https://[a-z0-9]+\.supabase\.co", cfg).group(0)
        self.key = re.search(r'"(sb_publishable_[^"]+)"', cfg).group(1)

    def test_no_function_answers_without_a_member(self):
        calls = {"site_round_roster": {"p_round": NO_ROUND},
                 "set_site_round_people": {"p_round": NO_ROUND, "p_roles": None, "p_prompters": None},
                 "set_site_season_roster": {"p_key": "season99", "p_players": []},
                 "site_round_role": {"p_round": NO_ROUND, "p_competitor": "nobody"},
                 "site_round_people_apply": {"p_round": NO_ROUND, "p_roles": None, "p_prompters": None}}
        for name, body in calls.items():
            with self.subTest(name):
                req = urllib.request.Request(f"{self.url}/rest/v1/rpc/{name}", data=json.dumps(body).encode(), method="POST",
                                             headers={"apikey": self.key, "Content-Type": "application/json"})
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(req, timeout=30)
                self.assertEqual(caught.exception.code, 401)

    def test_a_stranger_reads_none_of_it(self):
        for table in ("site_round_roles", "site_round_prompters"):
            with self.subTest(table):
                req = urllib.request.Request(f"{self.url}/rest/v1/{table}?select=*&limit=1", headers={"apikey": self.key})
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(req, timeout=30)
                self.assertIn(caught.exception.code, (401, 403))


if __name__ == "__main__":
    unittest.main()
