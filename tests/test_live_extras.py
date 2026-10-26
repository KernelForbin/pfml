"""LIVE TEST: the commissioner extras, against the real database.

Skipped unless PFML_LIVE=1, and needs SUPABASE_URL and SUPABASE_SECRET_KEY
in .env and supabase/migrations/2026-10-25_extras.sql run. Read-only: a
stranger is refused every new function and the announcements table, and
post_announcement refuses the secret key too (it isn't a commissioner), so
nothing is written. The full rules are
supabase/checks/2026-10-25_extras_rehearsal.sql, which only the user can run,
in the SQL Editor.

    PFML_LIVE=1 python -m unittest discover -s tests -p test_live_extras.py -v
"""
import unittest

import support  # noqa: F401  (puts scripts/ on the path)
import supa  # noqa: E402
from test_live_reminders import LIVE, has_keys, stranger

CALLS = {"submit_described": {"p_round": None, "p_platform": None, "p_track": None, "p_song": None, "p_names": None, "p_text": None},
         # with its switch since 2026-10-25_note_toggle.sql
         "set_submission_note": {"p_round": None, "p_tag": None, "p_note": None, "p_in_voting": None},
         "post_announcement": {"p_body": None}, "delete_announcement": {"p_id": None},
         "announcements_claim": {}}


@unittest.skipUnless(LIVE and has_keys(), "live network test; set PFML_LIVE=1, with the keys in .env")
class LiveExtras(unittest.TestCase):
    def test_a_stranger_is_refused(self):
        for name, body in CALLS.items():
            with self.subTest(name):
                self.assertEqual(stranger("POST", f"/rest/v1/rpc/{name}", body), 401)
        self.assertEqual(stranger("GET", "/rest/v1/site_announcements?select=*"), 401)

    def test_only_a_commissioner_posts(self):
        with self.assertRaises(SystemExit) as caught:
            supa.request("POST", "/rest/v1/rpc/post_announcement", body={"p_body": "test"})
        self.assertIn("Only the admin or a commissioner can post an announcement.", str(caught.exception))

    def test_every_round_keeps_what_it_had(self):
        rows = supa.request("GET", "/rest/v1/site_rounds?select=id,services,repeat_rule")
        self.assertTrue(rows)
        for r in rows:
            with self.subTest(r["id"]):
                self.assertEqual(sorted(r["services"]), ["soundcloud", "spotify", "youtube"])
                self.assertEqual(r["repeat_rule"], "warn")


if __name__ == "__main__":
    unittest.main()
