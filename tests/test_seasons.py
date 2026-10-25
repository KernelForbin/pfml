"""Seasons set up on the site (README, Seasons on the site): a commissioner
sets one up in steps, its rounds are scheduled ahead and open on their own,
and it votes on pfml.fun. The database rules as text (there's no Postgres
here; supabase/checks/2026-10-25_seasons_rehearsal.sql plays them in the real
database, as the 'authenticated' role, and rolls back), and the page wiring
(the pages were checked in a browser)."""
import re
import unittest

from support import ROOT
from test_reminders import js_body
from test_submissions import function, read, schema

SITE = ROOT / "site"
MIGRATION = ROOT / "supabase" / "migrations" / "2026-10-25_seasons.sql"
REHEARSAL = ROOT / "supabase" / "checks" / "2026-10-25_seasons_rehearsal.sql"
COMMISSIONER_CALLS = {"create_site_season": "jsonb", "update_site_season": "text, jsonb", "add_site_season_round": "text, text, text",
                      "move_site_season_round": "uuid, boolean", "remove_site_season_round": "uuid",
                      "set_site_season_players": "text, text[]"}
INSIDE_ONLY = {"site_add_days": "timestamptz, int", "site_season_reschedule": "text", "site_season_shift": "text, interval",
               "site_round_finish_early": "uuid"}


class TheTables(unittest.TestCase):
    def setUp(self):
        self.sql = schema()

    def test_the_migration_is_the_end_of_the_schema(self):
        mig = read(MIGRATION)
        self.assertIn(mig[mig.index("-- A season set up on the site, with the rules"):], self.sql)

    def test_season_3_and_before_can_never_be_one(self):
        table = self.sql.split("create table if not exists public.site_seasons (", 1)[1].split(");", 1)[0]
        self.assertIn("check (key ~ '^season[0-9]+$' and substring(key from 7)::int >= 4)", table)
        self.assertIn("if k is null or k !~ '^season[0-9]+$' or substring(k from 7)::int < 4 then", function(self.sql, "create_site_season"))

    def test_members_read_them_and_only_the_functions_write(self):
        for table in ("site_seasons", "site_season_players"):
            with self.subTest(table):
                self.assertRegex(self.sql, rf"alter table public\.{table}\s+enable row level security;")
                self.assertIn(f"revoke all on table public.{table} from anon, authenticated;", self.sql)
                self.assertIn(f"grant select on table public.{table} to authenticated;", self.sql)
                self.assertNotRegex(self.sql, rf"grant (insert|update|delete|all)[^;]*on table public\.{table}\b")
                self.assertNotRegex(self.sql, rf"create policy[^;]*on public\.{table}\s+for (insert|update|delete|all)")
                self.assertRegex(self.sql, rf"create policy[^;]*on public\.{table}\s+for select to authenticated using \(public\.is_member\(\)\);")

    def test_every_round_opens_at_a_time_and_old_ones_opened_when_made(self):
        self.assertIn("update public.site_rounds set opens_at = least(created_at, closes_at - interval '1 minute') where opens_at is null;", self.sql)
        self.assertIn("alter table public.site_rounds alter column opens_at set not null;", self.sql)
        self.assertIn("alter table public.site_rounds add constraint site_rounds_opens_first check (opens_at < closes_at);", self.sql)
        # the update above comes before not null, or it fails on old rows
        self.assertLess(self.sql.index("set opens_at = least(created_at"), self.sql.index("alter column opens_at set not null"))


class TheRules(unittest.TestCase):
    def setUp(self):
        self.sql = schema()

    def test_upcoming_comes_first(self):
        phase = function(self.sql, "site_round_phase")
        self.assertLess(phase.index("when now() < r.opens_at then 'upcoming'"), phase.index("then 'submitting'"))

    def test_days_follow_the_leagues_clock(self):
        self.assertIn("select ((p_at at time zone 'America/New_York') + make_interval(days => p_days)) at time zone 'America/New_York';",
                      function(self.sql, "site_add_days"))

    def test_rounds_follow_one_another(self):
        create = function(self.sql, "create_site_season")
        self.assertIn("      closes := first_close;\n      opens := greatest(now(), public.site_add_days(closes, -s.submit_days));", create)
        self.assertIn("      opens := public.site_add_days(closes, s.vote_days);\n      closes := public.site_add_days(opens, s.submit_days);", create)
        self.assertIn("public.site_add_days(closes, s.vote_days), s.point_budget, s.max_per_track, s.nonvoters_keep_points);", create)
        self.assertIn("values (k, btrim(coalesce(item->>'name', '')), btrim(coalesce(item->>'prompt', '')), opens, closes, true,", create)
        again = function(self.sql, "site_season_reschedule")
        # from the latest round that has opened: its scheduled end, not an
        # early one (Accelerated keeps the schedule)
        self.assertIn("select x.voting_closes_at into prev_vote from public.site_rounds x\n   where x.season_key = p_season and x.opens_at <= now() order by x.opens_at desc limit 1;", again)
        self.assertIn("where x.season_key = p_season and x.opens_at > now() order by x.opens_at, x.created_at, x.id loop", again)

    def test_a_season_is_checked_before_anything_is_written(self):
        create = function(self.sql, "create_site_season")
        first_write = create.index("insert into public.site_seasons")
        for check in ("if not public.is_commissioner() then", "That season already exists.", "A season needs between 1 and 40 rounds.",
                      "A season needs at least 2 players.", "Give the season a name.", "Every round needs a name.",
                      "if first_close is null or first_close <= now() then"):
            with self.subTest(check):
                self.assertLess(create.index(check), first_write)

    def test_only_commissioners_change_a_season(self):
        for name in COMMISSIONER_CALLS:
            with self.subTest(name):
                fn = function(self.sql, name)
                self.assertIn("if not public.is_commissioner() then", fn)
                self.assertLess(fn.index("if not public.is_commissioner() then"), min(
                    fn.index(w) for w in ("insert into", "update public", "delete from", "perform public") if w in fn))

    def test_only_rounds_that_havent_opened_move_or_go(self):
        for name in ("move_site_season_round", "remove_site_season_round"):
            with self.subTest(name):
                fn = function(self.sql, name)
                self.assertIn("if now() >= r.opens_at then", fn)
                self.assertIn("perform public.site_season_reschedule(r.season_key);", fn)
        self.assertIn("if not found or now() >= o.opens_at then", function(self.sql, "move_site_season_round"))

    def test_rule_changes_reach_only_rounds_still_taking_tracks(self):
        fn = function(self.sql, "update_site_season")
        self.assertIn("where season_key = p_key and closed_at is null and now() < closes_at;", fn)
        self.assertIn("perform public.site_season_reschedule(p_key);", fn)


class Timing(unittest.TestCase):
    def setUp(self):
        self.sql = schema()
        self.early = function(self.sql, "site_round_finish_early")

    def test_steady_never_closes_early(self):
        self.assertIn("if not found or s.timing = 'steady' then return; end if;", self.early)

    def test_submissions_close_when_everyone_playing_on_the_site_is_in(self):
        self.assertIn("where p.season_key = s.key\n                     and not exists (select 1 from public.site_submission_owners o where o.round_id = p_round and o.user_id = m.user_id)) then", self.early)
        self.assertIn("update public.site_rounds set closed_at = now() where id = p_round;", self.early)

    def test_voting_closes_when_everyone_with_a_track_has_voted(self):
        self.assertIn("and not exists (select 1 from public.site_votes v where v.round_id = p_round and v.user_id = o.user_id)) then", self.early)
        self.assertIn("update public.site_rounds set voting_closed_at = now() where id = p_round;", self.early)

    def test_speedy_moves_the_rest_up(self):
        self.assertIn("update public.site_rounds set closes_at = now(), voting_closes_at = voting_closes_at - saved where id = p_round;", self.early)
        self.assertEqual(self.early.count("perform public.site_season_shift(s.key, saved);"), 2)
        self.assertEqual(self.early.count("if s.timing = 'speedy' then"), 2)
        shift = function(self.sql, "site_season_shift")
        self.assertIn("where season_key = p_season and opens_at > now();", shift)

    def test_the_last_track_and_the_last_ballot_check(self):
        submit = function(self.sql, "submit_track")
        # only a new track can complete the round, not a changed one
        self.assertLess(submit.index("    return new_tag;\n  end if;"), submit.index("perform public.site_round_finish_early(p_round);"))
        self.assertIn("perform public.site_round_finish_early(p_round);\nend;", function(self.sql, "cast_ballot"))


class Submitting(unittest.TestCase):
    def setUp(self):
        self.fn = function(schema(), "submit_track")

    def test_not_before_it_opens_and_only_players(self):
        self.assertIn("if now() < r.opens_at then\n    raise exception 'This round hasn''t opened yet.';", self.fn)
        self.assertIn("raise exception 'You aren''t playing this season. Ask a commissioner to add you.';", self.fn)
        self.assertLess(self.fn.index("You aren''t playing"), self.fn.index("insert into public.site_submissions"))


class TheGuard(unittest.TestCase):
    def setUp(self):
        self.guard = function(schema(), "site_rounds_times_guard")

    def test_a_seasons_rounds_come_only_from_the_functions(self):
        insert = self.guard.split("if tg_op = 'INSERT' then", 1)[1].split("return new;", 1)[0]
        self.assertIn("if exists (select 1 from public.site_seasons s where s.key = new.season_key) then\n"
                      "      raise exception 'Add a round to this season from its section on the Commissioner page.';", insert)
        self.assertIn("if new.votes_on_site then", insert)
        self.assertIn("new.opens_at := now();", insert)
        self.assertIn("exists (select 1 from public.site_seasons s where s.key in (old.season_key, new.season_key))", self.guard)

    def test_the_opening_time_holds_once_open(self):
        self.assertIn("started := now() >= old.opens_at;", self.guard)
        self.assertIn("This round has opened, so its opening time can''t change.", self.guard)
        self.assertIn("if new.opens_at <= now() then\n      raise exception 'The opening time has to be in the future.';", self.guard)
        self.assertIn("if not started then\n      raise exception 'This round hasn''t opened yet.';", self.guard)


class ReachingPeople(unittest.TestCase):
    def setUp(self):
        self.sql = schema()

    def test_a_round_is_announced_when_it_opens_to_its_players(self):
        claim = function(self.sql, "reminders_claim")
        self.assertIn("where r.phase = 'submitting' and r.opens_at > now() - interval '6 hours'", claim)
        self.assertIn("and (not exists (select 1 from public.site_seasons s where s.key = r.season_key)\n"
                      "            or exists (select 1 from public.site_season_players p\n"
                      "                        where p.season_key = r.season_key and p.competitor_id = m.competitor_id))", claim)

    def test_the_export_dates_rounds_by_opening_and_names_seasons(self):
        ex = function(self.sql, "site_rounds_export")
        self.assertIn("'created_at', r.opens_at,", ex)
        self.assertIn(") order by r.opens_at, r.created_at)", ex)
        self.assertIn("'seasons', coalesce((select jsonb_object_agg(s.key, s.name) from public.site_seasons s), '{}'::jsonb));", ex)


class Grants(unittest.TestCase):
    def setUp(self):
        self.sql = schema()

    def test_commissioners_call_these(self):
        for name, args in COMMISSIONER_CALLS.items():
            with self.subTest(name):
                self.assertIn(f"revoke all on function public.{name}({args}) from public, anon;", self.sql)
                self.assertIn(f"grant execute on function public.{name}({args}) to authenticated;", self.sql)

    def test_nobody_calls_the_inner_ones(self):
        for name, args in INSIDE_ONLY.items():
            with self.subTest(name):
                self.assertIn(f"revoke all on function public.{name}({args}) from public, anon, authenticated;", self.sql)
                self.assertNotRegex(self.sql, rf"grant execute on function public\.{name}\(")

    def test_the_rehearsal_keeps_nothing_and_plays_the_real_role(self):
        script = read(REHEARSAL)
        self.assertTrue(script.rstrip().endswith("raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;\nend $$;"))
        self.assertNotRegex(script, r"(?i)\bcommit\b(?! drop)")
        self.assertIn("execute 'set local role authenticated';", script)
        self.assertEqual(script.count("checks := checks + 1;"),
                         int(re.search(r"Rehearsal passed: (\d+) checks held", script).group(1)))


class ThePages(unittest.TestCase):
    def setUp(self):
        self.seasons = read(SITE / "seasons.js")
        self.cm = read(SITE / "commissioner.js")

    def test_the_preview_lays_rounds_out_like_the_database(self):
        sched = js_body(self.seasons, "function schedule(firstClose, count, submitDays, voteDays) {")
        self.assertIn("if (i === 0) opens = new Date(Math.max(Date.now(), addDays(closes, -submitDays).getTime()));", sched)
        self.assertIn("else { opens = addDays(closes, voteDays); closes = addDays(opens, submitDays); }", sched)
        self.assertIn("out.push({ opens: opens, closes: closes, voting: addDays(closes, voteDays) });", sched)

    def test_what_the_page_sends_is_what_the_database_reads(self):
        create = js_body(self.seasons, "function create() {")
        sent = re.search(r"var p = \{(.*?)\};", create, re.S).group(1)
        keys = set(re.findall(r"(\w+):", sent))
        fn = function(schema(), "create_site_season")
        read_keys = set(re.findall(r"p->>?'(\w+)'", fn))
        self.assertEqual(keys, read_keys)
        settings = js_body(self.seasons, "function readSettings(form) {")
        self.assertEqual(set(re.findall(r"(\w+):", settings.split("return {", 1)[1])) - {"value"},
                         set(re.findall(r"p->>'(\w+)'", function(schema(), "update_site_season"))))

    def test_no_limit_means_the_whole_budget(self):
        self.assertIn('max_per_track: f.max_per_track.value === "none" ? budget : Math.min(+f.max_per_track.value, budget),',
                      js_body(self.seasons, "function readSettings(form) {"))
        self.assertIn('var picked = max >= budget ? "none" : max;', js_body(self.seasons, "function maxOptions(budget, max) {"))

    def test_a_new_season_is_season_4_or_later(self):
        self.assertIn('return "season" + Math.max(4, Math.max.apply(null, nums.concat([0])) + 1);', js_body(self.seasons, "function nextKey() {"))

    def test_the_five_steps(self):
        self.assertIn('var STEPS = ["Details", "Songs + Votes", "Timing", "Rounds", "Players"];', self.seasons)
        for mode in ("steady", "accelerated", "speedy"):
            self.assertIn(f"    {mode}: {{ name: ", self.seasons)

    def test_a_step_is_checked_before_moving_on_and_all_of_them_before_creating(self):
        go = js_body(self.seasons, "function goStep(n) {")
        self.assertIn("if (problem && n > wizard.step) { wizardMsg(problem); return; }", go)
        create = js_body(self.seasons, "function create() {")
        self.assertLess(create.index("if (!d.name)"), create.index("api().createSiteSeason(p)"))
        self.assertLess(create.index("first.getTime() <= Date.now()"), create.index("api().createSiteSeason(p)"))
        self.assertLess(create.index("window.confirm("), create.index("api().createSiteSeason(p)"))

    def test_the_commissioner_page_hands_seasons_over_and_keeps_their_rounds_apart(self):
        self.assertIn("window.PFMLSeasons.render({ rounds: state.rounds, seasons: state.seasons, index: state.index, reload: load });",
                      js_body(self.cm, "function render() {"))
        self.assertIn("return r !== open && !inSiteSeason(r);", js_body(self.cm, "function renderRounds(open) {"))
        form = js_body(self.cm, "function renderRoundForm(r) {")
        self.assertIn("filter(function (s) { return !inSiteSeason({ season_key: s.key }); })", form)
        self.assertNotIn("(new)", form)

    def test_the_submit_page_waits_for_a_round_to_open_and_shows_whats_coming(self):
        submit = read(SITE / "submit.js")
        self.assertIn('function isOpen(r) { return PFML.roundPhase(r) === "submitting"; }', submit)
        self.assertIn('var started = state.rounds.filter(function (x) { return PFML.roundPhase(x) !== "upcoming"; });', submit)
        self.assertIn("state.round = started.filter(isOpen)[0] || started[0] || null;", submit)
        self.assertIn(": state.upcoming.length ? state.upcoming[0].opens_at : null;", submit)
        self.assertIn('$("subNext").hidden = !list.length;', js_body(submit, "function renderNext() {"))
        self.assertIn('<ol class="sub-next" id="subNextList"></ol>', read(SITE / "submit.html"))
        self.assertIn('return PFML.roundPhase(r) === "submitting"; })[0];', js_body(read(SITE / "app.js"), "function renderSubmitBanner() {"))

    def test_enter_in_the_setup_never_reloads_the_page(self):
        # found in the browser 2026-10-25: Enter in a field submitted the
        # setup's form, which reloaded the page and lost everything typed
        submit = js_body(self.seasons, "function onSubmit(ev) {")
        self.assertTrue(submit.lstrip().split("\n", 2)[2].lstrip().startswith('if (ev.target.id === "cmWizardForm") {'))
        self.assertIn("ev.preventDefault();", submit.split('if (ev.target.id === "cmWizardForm") {', 1)[1].split("return;", 1)[0])
        self.assertIn('document.activeElement.id === "cmNew-rname") onWizardClick("w-add", null);', submit)

    def test_the_setup_opens_below_the_sticky_top_bar(self):
        # found in the browser: scrollIntoView put its steps under the bar
        show = js_body(self.seasons, "function showWizard() {")
        self.assertIn('var bar = document.querySelector(".topbar");', show)
        self.assertIn("- (bar ? bar.getBoundingClientRect().height : 0) - 12;", show)
        self.assertNotIn("scrollIntoView", self.seasons)

    def test_a_change_keeps_its_season_open(self):
        click = js_body(self.seasons, "function onClick(ev) {")
        self.assertIn('done.then(function () { return ctx.reload(); }).then(function () { reopen(key, ""); })', click)
        self.assertIn('.then(function () { reopen(key, "Saved."); })', js_body(self.seasons, "function onSubmit(ev) {"))

    def test_an_empty_schedule_takes_no_room(self):
        css = re.sub(r"/\*.*?\*/", "", read(SITE / "style.css"), flags=re.S)
        self.assertRegex(css, r"\.cm-sched:empty\s*\{\s*display:\s*none")

    def test_rounds_come_newest_opening_first(self):
        rounds = read(SITE / "auth.js").split("siteRounds: function () {", 1)[1].split("\n    },", 1)[0]
        self.assertIn('.order("opens_at", { ascending: false }).limit(100)', rounds)
        self.assertIn("opens_at", rounds.split(".select(", 1)[1].split(")", 1)[0])


if __name__ == "__main__":
    unittest.main()
