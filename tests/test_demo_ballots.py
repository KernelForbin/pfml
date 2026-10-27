"""The round demo's practice ballot in the database (asked 2026-10-27, when
a comment made on the demo on a phone didn't show on the computer). It has
its own table, apart from every real vote and draft. The SQL runs only in
the user's rehearsal (supabase/checks/2026-10-27_demo_ballots_rehearsal.sql)
and tests/test_live_demo_ballots.py; README, Round demo."""
import re
import unittest

from support import ROOT

SQL = (ROOT / "supabase" / "schema.sql").read_text(encoding="utf-8")
MIG = (ROOT / "supabase" / "migrations" / "2026-10-27_demo_ballots.sql").read_text(encoding="utf-8")
REHEARSAL = (ROOT / "supabase" / "checks" / "2026-10-27_demo_ballots_rehearsal.sql").read_text(encoding="utf-8")


def sql_function(text, name):
    start = text.index(f"create or replace function public.{name}(")
    return text[start:text.index("$$;", start)]


class ThePracticeTable(unittest.TestCase):
    def test_schema_has_the_migration(self):
        self.assertIn(MIG[MIG.index("create table if not exists public.site_demo_ballots"):], SQL)

    def test_only_the_functions_reach_it(self):
        self.assertIn("alter table public.site_demo_ballots enable row level security;", MIG)
        self.assertIn("revoke all on table public.site_demo_ballots from anon, authenticated;", MIG)
        self.assertNotRegex(MIG, r"grant [^;]* on table public\.site_demo_ballots")
        self.assertNotIn("create policy", MIG)
        for name, args in (("save_demo_ballot", "uuid, jsonb, boolean"), ("my_demo_ballot", "uuid")):
            with self.subTest(name):
                self.assertIn(f"revoke all on function public.{name}({args}) from public, anon;", MIG)
                self.assertIn(f"grant execute on function public.{name}({args}) to authenticated;", MIG)
        self.assertIn("revoke all on function public.demo_ballot_problem(uuid, jsonb) from public, anon, authenticated;", MIG)

    def test_it_never_touches_a_real_vote_or_draft(self):
        for name in ("save_demo_ballot", "my_demo_ballot", "demo_ballot_problem"):
            with self.subTest(name):
                body = sql_function(MIG, name)
                self.assertNotIn("site_votes", body)
                self.assertNotIn("site_ballot_drafts", body)

    def test_each_member_reads_and_writes_their_own(self):
        save = sql_function(MIG, "save_demo_ballot")
        self.assertIn("uid uuid := auth.uid();", save)
        self.assertIn("where user_id = uid;", save)
        self.assertIn("if not public.is_member() then", save)
        mine = sql_function(MIG, "my_demo_ballot")
        self.assertIn("where d.user_id = auth.uid() and d.source_round = p_round and public.is_member();", mine)

    def test_it_takes_only_what_the_demo_can_make(self):
        rules = sql_function(MIG, "demo_ballot_problem")
        self.assertIn("jsonb_array_length(p_ballot) > 150", rules)
        self.assertIn("where s.round_id = p_round and s.id::text = e->>'submission'", rules)
        self.assertIn("count(distinct e->>'submission')", rules)
        self.assertIn("char_length(coalesce(e->>'comment', '')) > 2000", rules)
        # the cast only ever sees a number
        self.assertIn("or case when jsonb_typeof(e->'points') = 'number'\n                             then (e->>'points')::numeric", rules)

    def test_a_new_round_s_demo_starts_afresh_and_a_submit_keeps_both(self):
        save = sql_function(MIG, "save_demo_ballot")
        self.assertIn("set draft = case when source_round = p_round then draft else '[]'::jsonb end,", save)
        self.assertIn("update public.site_demo_ballots set ballot = clean, draft = clean, draft_saved_at = at where user_id = uid;", save)

    def test_the_rehearsal_counts_its_checks(self):
        self.assertEqual(len(re.findall(r"^  checks := checks \+ 1;", REHEARSAL, re.M)), 9)
        self.assertIn('"Rehearsal passed: 9 checks held. Nothing was kept."', REHEARSAL)


if __name__ == "__main__":
    unittest.main()
