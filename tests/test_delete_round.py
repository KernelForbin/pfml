"""Deleting a round from the Commissioner page: the admin only, and only a
round that was never really played (supabase/migrations/
2026-10-25_delete_round.sql; README, Deleting a round)."""
import re
import unittest

from support import ROOT
from test_reminders import js_body
from test_submissions import function, read, schema

MIGRATION = ROOT / "supabase" / "migrations" / "2026-10-25_delete_round.sql"
REHEARSAL = ROOT / "supabase" / "checks" / "2026-10-25_delete_round_rehearsal.sql"
PAGE = read(ROOT / "site" / "commissioner.js")
AUTH = read(ROOT / "site" / "auth.js")


class TheDatabase(unittest.TestCase):
    def setUp(self):
        self.sql = schema()
        self.problem = function(self.sql, "site_round_delete_problem")
        self.listing = function(self.sql, "deletable_site_rounds")
        self.delete = function(self.sql, "delete_site_round")

    def test_the_migration_is_in_the_schema(self):
        mig = read(MIGRATION)
        start = "drop policy if exists \"admin deletes site rounds\" on public.site_rounds;"
        self.assertIn(mig[mig.index(start):], self.sql)

    def test_the_direct_delete_is_gone(self):
        # dropped after the last create of it, so a fresh install ends without it
        name = '"admin deletes site rounds" on public.site_rounds'
        self.assertGreater(self.sql.rindex(f"drop policy if exists {name};"), self.sql.rindex(f"create policy {name}"))
        self.assertNotRegex(self.sql[self.sql.rindex(f"drop policy if exists {name};"):],
                            r"create policy[^;]*on public\.site_rounds\s+for delete")

    def test_a_played_round_never_qualifies(self):
        for rule in ("when r.id is null then",
                     "when r.votes_on_site or exists (select 1 from public.site_seasons s where s.key = r.season_key)",
                     "when r.closed_at is null and r.closes_at > now()\n",
                     "when r.playlists_built_at is not null or r.spotify_playlist is not null or r.youtube_playlist is not null",
                     "when (select count(distinct o.user_id) from public.site_submission_owners o where o.round_id = r.id) > 1",
                     "when exists (select 1 from public.site_votes v where v.round_id = r.id)"):
            with self.subTest(rule):
                self.assertIn(rule, self.problem)
        self.assertIn("left join public.site_rounds r on r.id = p_round", self.problem)

    def test_the_list_and_the_delete_use_the_same_rule_and_only_for_the_admin(self):
        for body in (self.listing, self.delete):
            self.assertLess(body.index("if not public.is_admin() then"), body.index("public.site_round_delete_problem("))
            self.assertIn("raise exception 'Only the admin can delete a round.';", body)
        self.assertIn("where public.site_round_delete_problem(r.id) is null", self.listing)

    def test_the_delete_locks_then_checks_then_deletes(self):
        order = [self.delete.index(s) for s in ("perform 1 from public.site_rounds where id = p_round for update;",
                                                 "problem := public.site_round_delete_problem(p_round);",
                                                 "raise exception '%', problem;",
                                                 "delete from public.site_rounds where id = p_round returning name into gone;")]
        self.assertEqual(order, sorted(order))

    def test_who_may_call_what(self):
        tail = self.sql[self.sql.rindex("-- ---------------------------------------------------------------- deleting a round"):]
        self.assertIn("revoke all on function public.site_round_delete_problem(uuid) from public, anon, authenticated;", tail)
        self.assertNotIn("grant execute on function public.site_round_delete_problem", tail)
        for sig in ("deletable_site_rounds()", "delete_site_round(uuid)"):
            with self.subTest(sig):
                self.assertIn(f"revoke all on function public.{sig} from public, anon;", tail)
                self.assertIn(f"grant execute on function public.{sig} to authenticated;", tail)

    def test_the_rehearsal_counts_what_it_says(self):
        script = read(REHEARSAL)
        held = int(re.search(r'"Rehearsal passed: (\d+) checks held', script).group(1))
        self.assertEqual(script.count("checks := checks + 1;"), held)
        self.assertTrue(script.rstrip().endswith("end $$;"))
        self.assertIn("raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;", script)


class ThePage(unittest.TestCase):
    def test_the_calls(self):
        self.assertIn('client.rpc("deletable_site_rounds")', AUTH)
        self.assertIn('client.rpc("delete_site_round", { p_round: roundId })', AUTH)

    def test_only_the_admin_asks_and_a_failure_offers_nothing(self):
        load = js_body(PAGE, "function load() {")
        self.assertIn("var deletable = isAdmin()\n      ? api().deletableSiteRounds().catch(", load)
        self.assertIn(": Promise.resolve([]);", load)
        self.assertIn("state.deletable = {};", load)
        self.assertIn("state.deletable[d.round_id] = d.tracks;", load)

    def test_the_button_shows_only_on_a_round_the_database_listed(self):
        rounds = js_body(PAGE, "function renderRounds(open) {")
        self.assertIn("(r.id in state.deletable ? '<button type=\"button\" class=\"sub-btn sub-btn-quiet cm-round-delete\">", rounds)

    def test_it_asks_first_and_reloads_after(self):
        body = js_body(PAGE, "function onRoundDelete(ev) {")
        self.assertLess(body.index("window.confirm("), body.index("api().deleteSiteRound(id)"))
        self.assertIn("if (!r || !window.confirm(", body)
        self.assertIn("api().deleteSiteRound(id).then(load).catch(", body)
        self.assertIn('$("cmRoundList").addEventListener("click", onRoundDelete);', js_body(PAGE, "function boot() {"))


if __name__ == "__main__":
    unittest.main()
