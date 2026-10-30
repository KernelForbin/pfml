"""LIVE TEST: hidden prompts and guesses, against the real database and the
deployed grade-guesses Edge Function.

Skipped unless PFML_LIVE=1, and needs SUPABASE_URL and SUPABASE_SECRET_KEY
in .env, supabase/migrations/2026-10-29_hidden_prompts.sql run and
grade-guesses deployed. Checks the new columns and functions are there,
that a stranger can't call any of it, read the guesses, or a round's name
and prompt straight from the table, and that the Edge Function turns a
stranger away. Read-only: nothing is written, and Claude is never called.
The whole flow is rehearsed by
supabase/checks/2026-10-29_hidden_prompts_rehearsal.sql, which the user runs.

    PFML_LIVE=1 python -m unittest discover -s tests -p test_live_hidden_prompts.py -v
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
NO_ROUND = "00000000-0000-4000-8000-000000000000"


def has_keys():
    supa._load_env_file()
    return all(os.environ.get(n) for n in ("SUPABASE_URL", "SUPABASE_SECRET_KEY"))


@unittest.skipUnless(LIVE and has_keys(), "live network test; set PFML_LIVE=1, with the keys in .env")
class LiveParts(unittest.TestCase):
    def test_the_columns_and_table_are_there(self):
        supa.request("GET", "/rest/v1/site_rounds?select=hide_prompt,hide_prompter&limit=1")
        supa.request("GET", "/rest/v1/site_prompt_guesses?select=id,round_id,guess,prompter,score,graded_by&limit=1")

    def test_a_missing_round_has_nothing_to_grade(self):
        self.assertIsNone(supa.request("POST", "/rest/v1/rpc/prompt_guesses_claim", body={"p_round": NO_ROUND}))


@unittest.skipUnless(LIVE and has_keys(), "live network test; set PFML_LIVE=1, with the keys in .env")
class LiveStrangersAreRefused(unittest.TestCase):
    def setUp(self):
        cfg = (support.ROOT / "site" / "config.js").read_text(encoding="utf-8")
        self.url = re.search(r"https://[a-z0-9]+\.supabase\.co", cfg).group(0)
        self.key = re.search(r'"(sb_publishable_[^"]+)"', cfg).group(1)

    def post(self, path, body):
        req = urllib.request.Request(f"{self.url}{path}", data=json.dumps(body).encode(), method="POST",
                                     headers={"apikey": self.key, "Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(req, timeout=30)
        return caught.exception.code

    def test_no_function_answers_without_a_member(self):
        calls = {"site_rounds_list": {}, "save_prompt_guess": {"p_round": NO_ROUND, "p_guess": "x", "p_prompter": None},
                 "my_prompt_guess": {"p_round": NO_ROUND}, "site_round_guesses": {"p_round": NO_ROUND},
                 "set_prompt_guess_score": {"p_guess": NO_ROUND, "p_score": 1},
                 "prompt_guesses_claim": {"p_round": NO_ROUND}, "prompt_guesses_grade": {"p_grades": []}}
        for name, body in calls.items():
            with self.subTest(name):
                self.assertEqual(self.post(f"/rest/v1/rpc/{name}", body), 401)

    def test_a_stranger_reads_neither_guesses_nor_names(self):
        for path in ("/rest/v1/site_prompt_guesses?select=*&limit=1", "/rest/v1/site_rounds?select=name,prompt&limit=1"):
            with self.subTest(path):
                req = urllib.request.Request(f"{self.url}{path}", headers={"apikey": self.key})
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(req, timeout=30)
                self.assertIn(caught.exception.code, (401, 403))

    def test_the_grader_turns_a_stranger_away(self):
        self.assertEqual(self.post("/functions/v1/grade-guesses", {"round": NO_ROUND}), 401)


if __name__ == "__main__":
    unittest.main()
