"""LIVE TEST: the commissioner tools, against the real database.

Skipped unless PFML_LIVE=1, and needs SUPABASE_URL and SUPABASE_SECRET_KEY
in .env and supabase/migrations/2026-11-25_commissioner_tools.sql run.
Checks the functions are there and turn away both a stranger and the
secret key (which signs in as nobody, so isn't a commissioner), and that a
stranger can't read the pauses. Nothing is written. The whole flow is
rehearsed by supabase/checks/2026-11-25_commissioner_tools_rehearsal.sql,
which the user runs.

    PFML_LIVE=1 python -m unittest discover -s tests -p test_live_commissioner_tools.py -v
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
NOBODY = "00000000-0000-0000-0000-000000000000"

# each function the pages call, with arguments that touch nothing, and the
# refusal it gives someone who isn't a commissioner (or the admin)
CALLS = (
    ("pause_season", {"p_key": "season99", "p_starts_at": None, "p_after_round": None, "p_resume_at": None, "p_note": ""},
     "Only the admin or a commissioner can pause a season."),
    ("resume_season", {"p_key": "season99"}, "Only the admin or a commissioner can resume a season."),
    ("extend_site_round", {"p_round": NOBODY, "p_hours": 1, "p_days": None}, "Only the admin or a commissioner can move a deadline."),
    ("nudge_round", {"p_round": NOBODY}, "Only the admin or a commissioner can nudge."),
    ("site_round_status", {"p_round": NOBODY}, "Only the admin or a commissioner can see who"),
    ("decide_sit_out", {"p_round": NOBODY, "p_competitor": "nobody", "p_approve": True}, "Only the admin or a commissioner can answer that."),
    ("site_activity_list", {"p_before": None, "p_limit": 1}, "Only the admin or a commissioner can read the activity log."),
    ("create_invite", {"p_competitor": "nobody"}, "Only the admin can make invite links."),
    ("set_site_round_days", {"p_round": NOBODY, "p_submit": 3, "p_vote": None}, "Only the admin or a commissioner can change a round."),
    ("decide_prompt_turn", {"p_round": NOBODY, "p_name": None, "p_prompt": None}, "Only the admin or a commissioner can approve a prompt."),
    ("edit_announcement", {"p_id": NOBODY, "p_body": "x", "p_send_at": None}, "Only the admin or a commissioner can edit an announcement."),
)


def has_keys():
    supa._load_env_file()
    return all(os.environ.get(n) for n in ("SUPABASE_URL", "SUPABASE_SECRET_KEY"))


def stranger(name, body):
    cfg = (support.ROOT / "site" / "config.js").read_text(encoding="utf-8")
    url = re.search(r"https://[a-z0-9]+\.supabase\.co", cfg).group(0)
    key = re.search(r'"(sb_publishable_[^"]+)"', cfg).group(1)
    req = urllib.request.Request(f"{url}/rest/v1/rpc/{name}", data=json.dumps(body).encode(), method="POST",
                                 headers={"apikey": key, "Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=30)


@unittest.skipUnless(LIVE and has_keys(), "live network test; set PFML_LIVE=1, with the keys in .env")
class LiveCommissionerTools(unittest.TestCase):
    def test_they_are_there_and_want_a_commissioner(self):
        for name, body, refusal in CALLS:
            with self.subTest(name):
                # supa.request stops with SystemExit, carrying the database's message
                with self.assertRaises(SystemExit) as caught:
                    supa.request("POST", f"/rest/v1/rpc/{name}", body=body)
                self.assertIn(refusal, str(caught.exception))

    def test_a_stranger_is_refused(self):
        for name, body, _ in CALLS + (("site_pauses", {}, ""), ("site_pause_tick", {}, "")):
            with self.subTest(name):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    stranger(name, body)
                self.assertIn(caught.exception.code, (401, 403, 404))


if __name__ == "__main__":
    unittest.main()
