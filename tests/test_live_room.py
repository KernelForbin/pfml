"""LIVE TEST: the live room, against the real database.

Skipped unless PFML_LIVE=1, and needs SUPABASE_URL and SUPABASE_SECRET_KEY
in .env and supabase/migrations/2026-11-25_live_room.sql run. Checks the
functions are there and turn away both a stranger and the secret key (which
signs in as nobody, so isn't a member), and that a stranger can't read the
room's row. Nothing is written: each call is refused before it touches
anything. The whole flow is rehearsed by
supabase/checks/2026-11-25_live_room_rehearsal.sql, which the user runs.

    PFML_LIVE=1 python -m unittest discover -s tests -p test_live_room.py -v
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

# each function the page calls that says who it's for, with arguments that
# would touch nothing, and what it tells someone who isn't a member
CALLS = (
    ("room_here", {"p_after": None}, "Only league members can come into the room."),
    ("room_step_up", {}, "Only league members can DJ."),
    ("room_skip", {}, "Only league members can do that."),
    ("room_vote", {"p_vote": 1}, "Only league members can vote."),
    ("room_set_length", {"p_play": 0, "p_seconds": 10}, "Only league members can do that."),
    ("room_say", {"p_body": "x"}, "Only league members can chat."),
    ("room_remove_dj", {"p_competitor": "nobody"}, "Only the admin or a commissioner can take someone off the decks."),
    ("room_library_add", {"p_platform": "youtube", "p_track": "aaaaaaaaaaa", "p_title": "x", "p_artist": "", "p_seconds": 1,
                          "p_queue": False}, "Only league members have a library."),
    ("room_queue_set", {"p_ids": []}, "Only league members have a queue."),
    ("room_peek", {}, "Only league members can see the room."),
)


def has_keys():
    supa._load_env_file()
    return all(os.environ.get(n) for n in ("SUPABASE_URL", "SUPABASE_SECRET_KEY"))


def stranger(path, body=None):
    cfg = (support.ROOT / "site" / "config.js").read_text(encoding="utf-8")
    url = re.search(r"https://[a-z0-9]+\.supabase\.co", cfg).group(0)
    key = re.search(r'"(sb_publishable_[^"]+)"', cfg).group(1)
    req = urllib.request.Request(f"{url}/rest/v1/{path}", data=None if body is None else json.dumps(body).encode(),
                                 method="GET" if body is None else "POST",
                                 headers={"apikey": key, "Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=30)


@unittest.skipUnless(LIVE and has_keys(), "live network test; set PFML_LIVE=1, with the keys in .env")
class LiveRoom(unittest.TestCase):
    def test_they_are_there_and_want_a_member(self):
        for name, body, refusal in CALLS:
            with self.subTest(name):
                # supa.request stops with SystemExit, carrying the database's message
                with self.assertRaises(SystemExit) as caught:
                    supa.request("POST", f"/rest/v1/rpc/{name}", body=body)
                self.assertIn(refusal, str(caught.exception))

    def test_the_lists_give_nobody_nothing(self):
        # signed in as nobody: no library, and no Recently played
        self.assertEqual(supa.request("POST", "/rest/v1/rpc/room_library", body={}), [])
        self.assertEqual(supa.request("POST", "/rest/v1/rpc/room_recent", body={}), [])

    def test_a_stranger_is_refused(self):
        for name, body, _ in CALLS + (("room_recent", {}, ""), ("room_library", {}, ""), ("room_advance", {}, "")):
            with self.subTest(name):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    stranger(f"rpc/{name}", body)
                self.assertIn(caught.exception.code, (401, 403, 404))

    def test_a_stranger_cant_read_the_room(self):
        for table in ("room_state", "room_messages", "room_tracks"):
            with self.subTest(table):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    stranger(f"{table}?select=*")
                self.assertIn(caught.exception.code, (401, 403, 404))


if __name__ == "__main__":
    unittest.main()
