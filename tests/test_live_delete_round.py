"""LIVE TEST: deleting a round, against the real database.

Skipped unless PFML_LIVE=1, and needs SUPABASE_URL and SUPABASE_SECRET_KEY
in .env and supabase/migrations/2026-10-25_delete_round.sql run. Read-only:
a stranger is refused all three functions, and the secret key isn't the
admin, so both page calls refuse it too and nothing is deleted. The full
rules are supabase/checks/2026-10-25_delete_round_rehearsal.sql, which only
the user can run, in the SQL Editor.

    PFML_LIVE=1 python -m unittest discover -s tests -p test_live_delete_round.py -v
"""
import unittest

import support  # noqa: F401  (puts scripts/ on the path)
import supa  # noqa: E402
from test_live_reminders import LIVE, has_keys, stranger

NO_ROUND = "00000000-0000-0000-0000-000000000000"


@unittest.skipUnless(LIVE and has_keys(), "live network test; set PFML_LIVE=1, with the keys in .env")
class LiveDeleteRound(unittest.TestCase):
    def test_a_stranger_is_refused(self):
        for name, body in (("deletable_site_rounds", {}), ("delete_site_round", {"p_round": NO_ROUND}),
                           ("site_round_delete_problem", {"p_round": NO_ROUND})):
            with self.subTest(name):
                self.assertEqual(stranger("POST", f"/rest/v1/rpc/{name}", body), 401)

    def test_only_the_admin_lists_or_deletes(self):
        for name, body in (("deletable_site_rounds", {}), ("delete_site_round", {"p_round": NO_ROUND})):
            with self.subTest(name):
                with self.assertRaises(SystemExit) as caught:
                    supa.request("POST", f"/rest/v1/rpc/{name}", body=body)
                self.assertIn("Only the admin can delete a round.", str(caught.exception))

    def test_no_real_round_qualifies(self):
        # every round there is now was played, or is still open (Round 7)
        for r in supa.request("GET", "/rest/v1/site_rounds?select=id,name"):
            with self.subTest(r["name"]):
                problem = supa.request("POST", "/rest/v1/rpc/site_round_delete_problem", body={"p_round": r["id"]})
                self.assertIsNotNone(problem)


if __name__ == "__main__":
    unittest.main()
