"""LIVE TEST: the note switch, against the real database.

Skipped unless PFML_LIVE=1, and needs SUPABASE_URL and SUPABASE_SECRET_KEY
in .env and supabase/migrations/2026-10-25_note_toggle.sql run. Read-only,
and it never reads a note: a stranger is refused the notes table and the
note function, and a track no longer carries a note column at all. The full
rules are supabase/checks/2026-10-25_note_toggle_rehearsal.sql, which only
the user can run, in the SQL Editor.

    PFML_LIVE=1 python -m unittest discover -s tests -p test_live_note_toggle.py -v
"""
import unittest

import support  # noqa: F401  (puts scripts/ on the path)
import supa  # noqa: E402
from test_live_reminders import LIVE, has_keys, stranger


@unittest.skipUnless(LIVE and has_keys(), "live network test; set PFML_LIVE=1, with the keys in .env")
class LiveNoteToggle(unittest.TestCase):
    def test_a_stranger_is_refused(self):
        self.assertEqual(stranger("GET", "/rest/v1/site_submission_notes?select=submission_id"), 401)
        self.assertEqual(stranger("POST", "/rest/v1/rpc/set_submission_note",
                                  {"p_round": None, "p_tag": None, "p_note": None, "p_in_voting": None}), 401)

    def test_a_track_carries_no_note(self):
        with self.assertRaises(SystemExit) as caught:
            supa.request("GET", "/rest/v1/site_submissions?select=note&limit=1")
        self.assertIn("does not exist", str(caught.exception))

    def test_the_old_three_argument_call_is_gone(self):
        with self.assertRaises(SystemExit) as caught:
            supa.request("POST", "/rest/v1/rpc/set_submission_note", body={"p_round": None, "p_tag": None, "p_note": None})
        self.assertIn("PGRST202", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
