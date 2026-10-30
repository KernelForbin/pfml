"""LIVE TEST: adding someone new, against the real database.

Skipped unless PFML_LIVE=1, and needs SUPABASE_URL and SUPABASE_SECRET_KEY
in .env and supabase/migrations/2026-10-29_add_person.sql run. Checks the
function is there and turns away both a stranger and the secret key (which
signs in as nobody, so isn't a commissioner). Nothing is written. The whole
flow is rehearsed by supabase/checks/2026-10-29_add_person_rehearsal.sql,
which the user runs.

    PFML_LIVE=1 python -m unittest discover -s tests -p test_live_add_person.py -v
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
class LiveAddPlayer(unittest.TestCase):
    def test_it_is_there_and_wants_a_commissioner(self):
        # supa.request stops with SystemExit, carrying the database's message
        with self.assertRaises(SystemExit) as caught:
            supa.request("POST", "/rest/v1/rpc/add_player", body={"p_name": "Nobody At All"})
        self.assertIn("Only the admin or a commissioner can add someone.", str(caught.exception))

    def test_a_stranger_is_refused(self):
        cfg = (support.ROOT / "site" / "config.js").read_text(encoding="utf-8")
        url = re.search(r"https://[a-z0-9]+\.supabase\.co", cfg).group(0)
        key = re.search(r'"(sb_publishable_[^"]+)"', cfg).group(1)
        req = urllib.request.Request(f"{url}/rest/v1/rpc/add_player", data=json.dumps({"p_name": "x"}).encode(), method="POST",
                                     headers={"apikey": key, "Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(req, timeout=30)
        self.assertEqual(caught.exception.code, 401)


if __name__ == "__main__":
    unittest.main()
