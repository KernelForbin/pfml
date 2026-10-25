"""Commissioners (README, Commissioners): the admin and the members the
admin chooses run the site's rounds, on the Commissioner page. The database
rules as text (there's no Postgres here;
supabase/checks/2026-10-25_commissioner_rehearsal.sql runs them in the real
database, as the 'authenticated' role, and rolls back), and the page wiring
(the page itself was checked in a browser)."""
import re
import unittest

from support import ROOT
from test_reminders import js_body
from test_submissions import function, read, schema

SITE = ROOT / "site"
MIGRATION = ROOT / "supabase" / "migrations" / "2026-10-25_commissioner.sql"
REHEARSAL = ROOT / "supabase" / "checks" / "2026-10-25_commissioner_rehearsal.sql"


def last_policy(sql, table, verb):
    # schema.sql is run top to bottom, so the last create for a verb is the
    # one that stands
    found = re.findall(r"create policy[^;]*on public\." + table + r"\s+for " + verb + r"[^;]*;", sql)
    return found[-1]


class TheDatabase(unittest.TestCase):
    def setUp(self):
        self.sql = schema()
        self.guard = function(self.sql, "site_rounds_times_guard")

    def test_the_migration_is_in_the_schema(self):
        mig = read(MIGRATION)
        self.assertIn(mig[mig.index("alter table public.members drop constraint"):], self.sql)

    def test_three_roles(self):
        self.assertIn("alter table public.members add constraint members_role_check check (role in ('member', 'commissioner', 'admin'));", self.sql)
        self.assertIn("role in ('commissioner', 'admin')", function(self.sql, "is_commissioner"))

    def test_commissioners_open_and_change_rounds_only_the_admin_deletes(self):
        self.assertIn("public.is_commissioner()", last_policy(self.sql, "site_rounds", "insert"))
        update = last_policy(self.sql, "site_rounds", "update")
        self.assertIn("using (public.is_commissioner()) with check (public.is_commissioner())", update)
        self.assertIn("public.is_admin()", last_policy(self.sql, "site_rounds", "delete"))
        # the admin's old policies are dropped by name, so they don't linger
        for name in ("admin opens site rounds", "admin edits site rounds"):
            tail = self.sql[self.sql.index("-- ---------------------------------------------------------------- commissioners"):]
            self.assertIn(f'drop policy if exists "{name}" on public.site_rounds;', tail)

    def test_only_the_admin_chooses_and_never_unmakes_the_admin(self):
        fn = function(self.sql, "set_commissioner")
        self.assertLess(fn.index("if not public.is_admin() then"), fn.index("update public.members"))
        self.assertIn("if current_role_ = 'admin' then", fn)
        self.assertIn("if current_role_ is null then", fn)
        self.assertIn("set role = case when p_on then 'commissioner' else 'member' end", fn)

    def test_no_deadline_reopens_for_anyone_signed_in(self):
        g = self.guard
        self.assertIn("if current_user <> 'authenticated' then\n    return new;", g)
        self.assertIn("subs_closed := old.closed_at is not null or now() >= old.closes_at;", g)
        self.assertIn("if subs_closed and (new.closes_at is distinct from old.closes_at or new.closed_at is distinct from old.closed_at) then", g)
        self.assertIn("if subs_closed and new.season_key is distinct from old.season_key then", g)
        self.assertIn("if new.closes_at is distinct from old.closes_at and new.closes_at <= now() then", g)
        self.assertIn("if votes_closed and (new.voting_closes_at is distinct from old.voting_closes_at", g)
        self.assertIn("if new.voting_closes_at is distinct from old.voting_closes_at and new.voting_closes_at <= now() then", g)
        self.assertIn("if new.closes_at <= now() then", g.split("if tg_op = 'INSERT' then", 1)[1])

    def test_closing_early_takes_the_databases_clock(self):
        self.assertIn("if new.closed_at is distinct from old.closed_at then\n    new.closed_at := now();", self.guard)
        self.assertIn("    new.voting_closed_at := now();", self.guard)

    def test_the_guard_runs_on_every_insert_and_update(self):
        self.assertIn("create trigger site_rounds_times_guard before insert or update on public.site_rounds", self.sql)

    def test_grants(self):
        for sig in ("is_commissioner()", "set_commissioner(text, boolean)"):
            with self.subTest(sig):
                self.assertIn(f"revoke all on function public.{sig} from public, anon;", self.sql)
                self.assertIn(f"grant execute on function public.{sig} to authenticated;", self.sql)

    def test_the_rehearsal_keeps_nothing_and_plays_the_real_role(self):
        script = read(REHEARSAL)
        self.assertTrue(script.rstrip().endswith("raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;\nend $$;"))
        self.assertNotRegex(script, r"(?i)\bcommit\b")
        self.assertIn("execute 'set local role authenticated';", script)
        self.assertEqual(script.count("checks := checks + 1;"),
                         int(re.search(r"Rehearsal passed: (\d+) checks held", script).group(1)))


class ThePages(unittest.TestCase):
    def setUp(self):
        self.page = read(SITE / "commissioner.js")
        self.html = read(SITE / "commissioner.html")

    def test_the_page_loads_what_it_needs_in_order(self):
        srcs = re.findall(r'<script src="([^"]+)"', self.html)
        self.assertEqual(srcs[1:], ["config.js", "auth.js", "account.js", "voting.js", "commissioner.js", "app.js"])
        self.assertIn('<body class="gated" data-page="commissioner">', self.html)
        self.assertIn('page === "commissioner"', js_body(read(SITE / "app.js"), "function boot() {"))

    def test_only_commissioners_get_the_page_or_the_link(self):
        boot = js_body(self.page, "function boot() {")
        self.assertTrue(boot.lstrip().startswith("if (!isCommissioner()) {"))
        self.assertIn('function isCommissioner() { return role() === "admin" || role() === "commissioner"; }', self.page)
        account = read(SITE / "account.js")
        self.assertIn('<a class="acct-item" href="commissioner" id="acctCommish" hidden>Commissioner</a>', account)
        self.assertIn('$("acctCommish").hidden = member.role !== "admin" && member.role !== "commissioner";', account)

    def test_the_round_form_moved_off_the_submit_page(self):
        submit_js, submit_html = read(SITE / "submit.js"), read(SITE / "submit.html")
        for gone in ("renderAdmin", "saveRound", "closeRound", "updateSiteRound", "openSiteRound"):
            with self.subTest(gone):
                self.assertNotIn(gone, submit_js)
        self.assertNotIn('id="subAdmin"', submit_html)
        self.assertIn('<a href="commissioner">Commissioner page</a>', submit_html)
        self.assertIn('$("subCommish").hidden = !PFML.member || (PFML.member.role !== "admin" && PFML.member.role !== "commissioner");', submit_js)

    def test_a_refused_write_says_so(self):
        # RLS turns a refusal into "no rows", which would otherwise look saved
        self.assertIn('if (!rows || !rows.length) throw new Error("Only the admin or a commissioner can do that.");',
                      js_body(self.page, "function wrote(rows) {"))
        save = js_body(self.page, "function onRoundSave(ev) {")
        self.assertIn("api().updateSiteRound(id, { name: name, prompt: prompt }).then(wrote)", save)

    def test_earlier_rounds_change_only_their_name_and_description(self):
        save = js_body(self.page, "function onRoundSave(ev) {")
        self.assertEqual(re.findall(r"updateSiteRound\(id, (\{[^}]*\})", save), ["{ name: name, prompt: prompt }"])

    def test_the_admin_alone_sees_the_commissioners_and_league_status(self):
        self.assertIn("if (isAdmin()) { renderPeople(); renderLeagueStatus(); }", js_body(self.page, "function render() {"))
        people = js_body(self.page, "function renderPeople() {")
        # the admin's row has no switch
        admin_row = people.split('if (p.role === "admin") {', 1)[1].split("}", 1)[0]
        self.assertNotIn("role=\\\"switch\\\"", admin_row)
        self.assertNotIn('role="switch"', admin_row)

    def test_a_switch_goes_back_if_the_save_fails(self):
        click = js_body(self.page, "function onPersonClick(ev) {")
        self.assertIn('api().setCommissioner(b.getAttribute("data-player"), on).catch(function (err) {', click)
        self.assertIn('b.setAttribute("aria-checked", String(!on));', click)
        # a screen reader hears what the switch means, not just a name
        self.assertIn("aria-label=\"' + esc(p.name) + ' is a commissioner\"", js_body(self.page, "function renderPeople() {"))
        auth = read(SITE / "auth.js")
        self.assertIn('client.rpc("set_commissioner", { p_competitor: competitorId, p_on: on })', auth)
        self.assertIn('client.from("members").select("competitor_id, role")', auth)


if __name__ == "__main__":
    unittest.main()
