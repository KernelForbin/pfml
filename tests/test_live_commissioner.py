"""LIVE TEST: commissioners, against the real database.

Skipped unless PFML_LIVE=1, and needs SUPABASE_URL and SUPABASE_SECRET_KEY
in .env and supabase/migrations/2026-10-25_commissioner.sql run. Read-only:
a stranger is refused both new functions, and set_commissioner refuses the
secret key too (it isn't the admin), so nothing changes. The full rules are
supabase/checks/2026-10-25_commissioner_rehearsal.sql, which only the user
can run, in the SQL Editor.

    PFML_LIVE=1 python -m unittest discover -s tests -p test_live_commissioner.py -v
"""
import unittest

import support  # noqa: F401  (puts scripts/ on the path)
import supa  # noqa: E402
from test_live_reminders import LIVE, has_keys, stranger


@unittest.skipUnless(LIVE and has_keys(), "live network test; set PFML_LIVE=1, with the keys in .env")
class LiveCommissioner(unittest.TestCase):
    def test_a_stranger_is_refused(self):
        for name, body in (("is_commissioner", {}), ("set_commissioner", {"p_competitor": None, "p_on": None})):
            with self.subTest(name):
                self.assertEqual(stranger("POST", f"/rest/v1/rpc/{name}", body), 401)

    def test_only_the_admin_sets_a_role(self):
        # the secret key has no auth.uid(), so it isn't the admin either
        with self.assertRaises(SystemExit) as caught:
            supa.request("POST", "/rest/v1/rpc/set_commissioner", body={"p_competitor": "nobody", "p_on": True})
        self.assertIn("Only the admin can choose commissioners.", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
