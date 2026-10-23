"""LIVE TEST: the round-repeat rules, run by the real database.

Skipped unless PFML_LIVE=1, and needs SUPABASE_URL and SUPABASE_SECRET_KEY
in .env and supabase/migrations/2026-10-23_round_repeats.sql run. There's no
Postgres here, so this is the only place fp_kind's SQL actually runs: each
case is a pick and one submission, as fingerprints, and the kind it must
come out as. It also checks the page's calls refuse a caller who isn't a
signed-in member. Read-only: nothing is written.

    PFML_LIVE=1 python -m unittest discover -s tests -p test_live_round_repeats.py -v
"""
import os
import unittest

import support  # noqa: F401  (puts scripts/ on the path)
import supa  # noqa: E402

LIVE = os.environ.get("PFML_LIVE") == "1"


def has_keys():
    supa._load_env_file()
    return all(os.environ.get(n) for n in ("SUPABASE_URL", "SUPABASE_SECRET_KEY"))


def kind(m, o):
    body = {"m_platform": m.get("platform", "youtube"), "m_track": m.get("track", "aaaaaaaaaaa"),
            "m_song": m.get("song", ""), "m_names": m.get("names", []), "m_text": m.get("text", ""),
            "o_platform": o.get("platform", "youtube"), "o_track": o.get("track", "bbbbbbbbbbb"),
            "o_song": o.get("song", ""), "o_names": o.get("names", []), "o_text": o.get("text", "")}
    return supa.request("POST", "/rest/v1/rpc/fp_kind", body=body)


# Real cases from the Round 7 research (2026-10-23)
CASES = [
    ("the very same video", {"track": "Y9a49oFalZE"}, {"track": "Y9a49oFalZE"}, "track"),
    ("same song and artist, both named",
     {"song": "rich girl", "names": ["lake street dive"]}, {"song": "rich girl", "names": ["lake street dive"]}, "version"),
    ("a video whose title names the song and artist of a Spotify pick",
     {"text": "righteously anna ash anna ash"}, {"platform": "spotify", "song": "righteously", "names": ["anna ash"]}, "version"),
    ("the other way round",
     {"platform": "spotify", "song": "righteously", "names": ["anna ash"]}, {"text": "righteously anna ash anna ash"}, "version"),
    ("same song, another artist",
     {"song": "rich girl", "names": ["lake street dive"]}, {"song": "rich girl", "names": ["hall and oates"]}, "song"),
    ("a one-word title by someone else is only a title",
     {"song": "river", "names": ["leon bridges"]}, {"song": "river", "names": ["joni mitchell"]}, "title"),
    ("a video's text naming another pick's song and artist",
     {"text": "bill withers ain t no sunshine old grey whistle test"}, {"song": "ain t no sunshine", "names": ["bill withers"]}, "version"),
    ("a multi-word title in text without the artist",
     {"text": "ain t no sunshine cover at the pub"}, {"song": "ain t no sunshine", "names": ["bill withers"]}, "title"),
    ("same artist, different song",
     {"song": "hold on", "names": ["alabama shakes"]}, {"song": "don t wanna fight", "names": ["alabama shakes"]}, "artist"),
    ("an artist named in a video's text",
     {"text": "charles bradley changes live on kexp kexp"}, {"song": "why is it so hard", "names": ["charles bradley"]}, "artist"),
    ("a short one-word name in text doesn't count alone",
     {"text": "live at low memorial library"}, {"song": "sunflower", "names": ["low"]}, None),
    ("a session channel shared by two videos is nothing",
     {"text": "charles bradley why is it so hard kexp"}, {"text": "sharon jones 100 days 100 nights kexp"}, None),
    ("nothing alike", {"song": "quimbara", "names": ["celia cruz"]}, {"song": "radio ga ga", "names": ["queen"]}, None),
    ("an undescribed submission can't match on words",
     {"song": "rich girl", "names": ["lake street dive"]}, {}, None),
]


@unittest.skipUnless(LIVE and has_keys(), "live database test; needs PFML_LIVE=1 and the Supabase keys in .env")
class LiveRoundRepeats(unittest.TestCase):
    def test_every_case_comes_out_as_its_kind(self):
        for name, m, o, want in CASES:
            with self.subTest(name):
                self.assertEqual(kind(m, o), want)

    def test_fp_ok_takes_plain_words_only(self):
        ok = lambda song, names, text: supa.request("POST", "/rest/v1/rpc/fp_ok",
                                                   body={"p_song": song, "p_names": names, "p_text": text})
        self.assertTrue(ok("rich girl", ["lake street dive"], "lake street dive rich girl"))
        self.assertTrue(ok("", [], ""))
        self.assertFalse(ok("Rich Girl", [], ""))
        self.assertFalse(ok("rich-girl", [], ""))
        self.assertFalse(ok("", [""], ""))
        self.assertFalse(ok("", ["a"] * 13, ""))
        self.assertFalse(ok("x" * 301, [], ""))

    def test_the_page_calls_refuse_a_caller_who_isnt_a_member(self):
        # the secret key has no signed-in user, so is_member() is false
        args = {"p_round": "00000000-0000-0000-0000-000000000000", "p_platform": "youtube", "p_track": "aaaaaaaaaaa",
                "p_song": "", "p_names": [], "p_text": ""}
        for name in ("round_repeats", "describe_submission"):
            with self.subTest(name):
                with self.assertRaises(SystemExit) as caught:
                    supa.request("POST", f"/rest/v1/rpc/{name}", body=args)
                self.assertIn("Only league members", str(caught.exception))
        self.assertIs(supa.request("POST", "/rest/v1/rpc/my_submission_described",
                                   body={"p_round": args["p_round"]}), False)


if __name__ == "__main__":
    unittest.main()
