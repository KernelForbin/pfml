"""LIVE TEST: the voters' lounge, against the real database.

Skipped unless PFML_LIVE=1, and needs SUPABASE_URL and SUPABASE_SECRET_KEY
in .env and supabase/migrations/2026-10-28_voters_lounge.sql run. Checks
the instrument names and that a stranger can't call any lounge function or
read its tables. Read-only: nothing is written. The whole lounge, members
and all, is rehearsed by supabase/checks/2026-10-28_voters_lounge_rehearsal.sql,
which the user runs.

    PFML_LIVE=1 python -m unittest discover -s tests -p test_live_voters_lounge.py -v
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


@unittest.skipUnless(LIVE and has_keys(), "live network test; set PFML_LIVE=1, with the keys in .env")
class LiveNames(unittest.TestCase):
    def name(self, n):
        return supa.request("POST", "/rest/v1/rpc/lounge_alias_name", body={"p_alias": n})

    def test_instruments_then_numbers(self):
        self.assertEqual(self.name(0), "Kazoo")
        self.assertEqual(self.name(47), "Harpsichord")
        self.assertEqual(self.name(48), "Kazoo 2")
        names = [self.name(n) for n in range(48)]
        self.assertEqual(len(set(names)), 48)


@unittest.skipUnless(LIVE and has_keys(), "live network test; set PFML_LIVE=1, with the keys in .env")
class LiveStrangersAreRefused(unittest.TestCase):
    def setUp(self):
        cfg = (support.ROOT / "site" / "config.js").read_text(encoding="utf-8")
        self.url = re.search(r"https://[a-z0-9]+\.supabase\.co", cfg).group(0)
        self.key = re.search(r'"(sb_publishable_[^"]+)"', cfg).group(1)

    def test_no_lounge_function_answers_without_a_member(self):
        calls = {"lounge_status": {"p_round": None, "p_practice": False},
                 "lounge_messages": {"p_round": None, "p_practice": False},
                 "lounge_post": {"p_round": None, "p_practice": False, "p_body": "hi"},
                 "lounge_react": {"p_message": 1, "p_reaction": "fire", "p_on": True},
                 "lounge_remove": {"p_message": 1},
                 "lounge_alias_name": {"p_alias": 0}}
        for name, body in calls.items():
            with self.subTest(name):
                req = urllib.request.Request(f"{self.url}/rest/v1/rpc/{name}", data=json.dumps(body).encode(), method="POST",
                                             headers={"apikey": self.key, "Content-Type": "application/json"})
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(req, timeout=30)
                self.assertEqual(caught.exception.code, 401)

    def test_a_stranger_reads_none_of_it(self):
        for table in ("site_lounge_messages", "site_lounge_aliases", "site_lounge_reactions"):
            with self.subTest(table):
                req = urllib.request.Request(f"{self.url}/rest/v1/{table}?select=*&limit=1", headers={"apikey": self.key})
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(req, timeout=30)
                self.assertIn(caught.exception.code, (401, 403))


if __name__ == "__main__":
    unittest.main()
