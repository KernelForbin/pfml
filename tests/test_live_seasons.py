"""LIVE TEST: seasons set up on the site, against the real database.

Skipped unless PFML_LIVE=1, and needs SUPABASE_URL and SUPABASE_SECRET_KEY
in .env and supabase/migrations/2026-10-25_seasons.sql run. Read-only: a
stranger is refused every new function and both new tables, and
create_site_season refuses the secret key too (it isn't a commissioner), so
nothing is written. The full rules are
supabase/checks/2026-10-25_seasons_rehearsal.sql, which only the user can run,
in the SQL Editor.

    PFML_LIVE=1 python -m unittest discover -s tests -p test_live_seasons.py -v
"""
import unittest

import support  # noqa: F401  (puts scripts/ on the path)
import supa  # noqa: E402
from test_live_reminders import LIVE, has_keys, stranger

CALLS = {"create_site_season": {"p": {}}, "update_site_season": {"p_key": None, "p": {}},
         "add_site_season_round": {"p_key": None, "p_name": None, "p_prompt": None},
         "move_site_season_round": {"p_round": None, "p_earlier": None}, "remove_site_season_round": {"p_round": None},
         "set_site_season_players": {"p_key": None, "p_players": None},
         "site_season_reschedule": {"p_season": None}, "site_round_finish_early": {"p_round": None}}


@unittest.skipUnless(LIVE and has_keys(), "live network test; set PFML_LIVE=1, with the keys in .env")
class LiveSeasons(unittest.TestCase):
    def test_a_stranger_is_refused_every_function(self):
        for name, body in CALLS.items():
            with self.subTest(name):
                self.assertEqual(stranger("POST", f"/rest/v1/rpc/{name}", body), 401)

    def test_a_stranger_reads_neither_table(self):
        for table in ("site_seasons", "site_season_players"):
            with self.subTest(table):
                self.assertEqual(stranger("GET", f"/rest/v1/{table}?select=*"), 401)

    def test_only_a_commissioner_sets_up_a_season(self):
        # the secret key has no auth.uid(), so it isn't a commissioner
        with self.assertRaises(SystemExit) as caught:
            supa.request("POST", "/rest/v1/rpc/create_site_season", body={"p": {"key": "season99"}})
        self.assertIn("Only the admin or a commissioner can set up a season.", str(caught.exception))

    def test_every_round_has_an_opening_time(self):
        rows = supa.request("GET", "/rest/v1/site_rounds?select=id,opens_at,created_at,closes_at")
        self.assertTrue(rows)
        for r in rows:
            with self.subTest(r["id"]):
                self.assertTrue(r["opens_at"])
                self.assertLess(r["opens_at"], r["closes_at"])


if __name__ == "__main__":
    unittest.main()
