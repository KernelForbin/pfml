"""Commissioner tools (asked 2026-11-25; README, Commissioner tools): pausing
a season, the Now tab (+1 hour, +1 day, Close now, Nudge), sitting a round
out, the activity log, a round's own days, prompt rotation, scheduled and
season-only announcements, invite links from the page, and the
Commissioner page in tabs.

The SQL runs in the user's rehearsal
(supabase/checks/2026-11-25_commissioner_tools_rehearsal.sql), and ran
before that on a local Postgres with Supabase's auth, cron and storage
stubbed; tests/test_live_commissioner_tools.py checks the live functions
are there and turn strangers away. These pin the rules in the text; the
pages were checked in a browser."""
import re
import unittest

from support import ROOT
from test_reminders import js_body
from test_submissions import function, read, schema

SITE = ROOT / "site"
MIG = read(ROOT / "supabase" / "migrations" / "2026-11-25_commissioner_tools.sql")
REHEARSAL = read(ROOT / "supabase" / "checks" / "2026-11-25_commissioner_tools_rehearsal.sql")

# what the pages call: each checks who's asking
PAGE_FUNCTIONS = (("site_activity_list", "bigint, int"), ("my_prompt_turns", ""), ("send_prompt_turn", "uuid, text, text"),
                  ("site_prompt_turns_list", ""), ("decide_prompt_turn", "uuid, text, text"),
                  ("set_site_season_rotation", "text, boolean"),
                  ("pause_season", "text, timestamptz, uuid, timestamptz, text"), ("set_pause_resume", "text, timestamptz"),
                  ("resume_season", "text"), ("site_pauses", ""), ("extend_site_round", "uuid, int, int"),
                  ("site_round_status", "uuid"), ("nudge_round", "uuid"), ("site_round_last_nudge", "uuid"),
                  ("ask_sit_out", "uuid, boolean"), ("decide_sit_out", "uuid, text, boolean"),
                  ("set_site_round_days", "uuid, int, int"), ("create_invite", "text"),
                  ("post_announcement", "text, timestamptz, text"), ("edit_announcement", "uuid, text, timestamptz"))
# the inner workings: nobody signed in calls them
INNER = (("site_log", "text, text, uuid, uuid"), ("site_pause_move", "text, timestamptz, int"),
         ("site_pause_begin", "uuid, timestamptz, uuid"), ("site_pause_end", "uuid, timestamptz, uuid"),
         ("site_pause_tick", ""), ("site_rotation_tick", ""), ("site_round_waiting", "uuid"),
         ("site_notify", "uuid, text, text, text"), ("site_notify_commissioners", "text, text, text"),
         ("site_round_winners", "uuid"), ("site_writes_allowed", ""), ("site_owner_not_sitting_out", ""))


class TheDatabase(unittest.TestCase):
    def setUp(self):
        self.sql = schema()

    def test_schema_has_the_migration(self):
        self.assertIn(MIG[MIG.index("-- ---------------------------------------------------------------- helpers"):], self.sql)

    def test_new_tables_are_closed_to_the_api(self):
        # a new table gets its grants explicitly (CLAUDE.md, from 2026-10-30)
        for table in ("site_activity", "site_push_notices", "site_season_pauses", "site_prompt_turns", "site_nudges"):
            with self.subTest(table):
                self.assertIn(f"alter table public.{table} enable row level security;", MIG)
                self.assertIn(f"revoke all on table public.{table} from anon, authenticated;", MIG)
                self.assertNotRegex(MIG, rf"grant [^;]* on table public\.{table} ")
        # who's sitting a round out is no secret; who said yes is
        self.assertIn("grant select (round_id, competitor_id, status, asked_at) on table public.site_round_sitouts to authenticated;", MIG)
        self.assertNotRegex(MIG, r"grant (insert|update|delete|all)[^;]* on table public\.site_round_sitouts")

    def test_who_can_call_what(self):
        for name, args in PAGE_FUNCTIONS:
            with self.subTest(name):
                self.assertIn(f"revoke all on function public.{name}({args}) from public, anon;", MIG)
                self.assertIn(f"grant execute on function public.{name}({args}) to authenticated;", MIG)
        for name, args in INNER:
            with self.subTest(name):
                self.assertIn(f"revoke all on function public.{name}({args}) from public, anon, authenticated;", MIG)
        # the old one-argument post_announcement goes, so a call can't be ambiguous
        self.assertIn("drop function if exists public.post_announcement(text);", MIG)

    def test_commissioners_only(self):
        for name in ("pause_season", "set_pause_resume", "resume_season", "extend_site_round", "nudge_round",
                     "decide_sit_out", "set_site_round_days", "set_site_season_rotation", "decide_prompt_turn",
                     "post_announcement", "edit_announcement"):
            with self.subTest(name):
                self.assertTrue(function(self.sql, name).split("\nbegin\n", 1)[1].lstrip().startswith("if not public.is_commissioner() then"))
        for name in ("site_activity_list", "site_round_status", "site_prompt_turns_list", "site_round_last_nudge"):
            with self.subTest(name):
                self.assertIn("if not public.is_commissioner() then", function(self.sql, name))
        # invite links: the admin only, as before
        self.assertTrue(function(self.sql, "create_invite").split("\nbegin\n", 1)[1].lstrip().startswith("if not public.is_admin() then"))

    def test_a_pause_blocks_tracks_and_ballots_by_any_function(self):
        allowed = function(self.sql, "site_writes_allowed")
        self.assertIn("if auth.uid() is not null and public.site_round_paused(rid) then", allowed)
        for table in ("site_submissions", "site_votes"):
            with self.subTest(table):
                self.assertRegex(self.sql, rf"create trigger \w+ before insert or update or delete on public\.{table}\n"
                                           r"  for each row execute function public\.site_writes_allowed\(\);")
        # drafts, comments and the lounge are left alone (the user's call, 2026-11-25)
        for table in ("site_ballot_drafts", "comment_replies", "site_lounge_messages"):
            self.assertNotRegex(self.sql, rf"on public\.{table}\n  for each row execute function public\.site_writes_allowed")

    def test_a_pause_counts_once_its_time_comes(self):
        paused = function(self.sql, "site_season_paused")
        self.assertIn("p.started_at is not null or p.starts_at <= now()", paused)
        self.assertIn("p.after_round is not null and public.site_round_phase(p.after_round) = 'finished'", paused)

    def test_time_stops_in_whole_days(self):
        move = function(self.sql, "site_pause_move")
        self.assertIn("opens_at = case when opens_at >= p_from then public.site_add_days(opens_at, p_days) else opens_at end", move)
        self.assertIn("closes_at = case when closed_at is null and closes_at > p_from", move)
        self.assertIn("voting_closes_at = case when voting_closed_at is null and voting_closes_at > p_from", move)
        begin = function(self.sql, "site_pause_begin")
        self.assertIn("h := case when p.resume_at is null then 365 else public.site_days_until(p_at, p.resume_at) end;", begin)
        end = function(self.sql, "site_pause_end")
        # settles at the real length, rounded up to whole days
        self.assertIn("n := public.site_days_until(p.started_at, greatest(p_at, p.started_at));", end)
        self.assertIn("perform public.site_pause_move(p.season_key, p.started_at, n - p.hold_days);", end)
        days = function(self.sql, "site_days_until")
        self.assertIn("while public.site_add_days(p_from, n) < p_to loop", days)

    def test_while_paused_nothing_moves_on_its_own(self):
        self.assertIn("public.site_season_paused(s.key) then return; end if;", function(self.sql, "site_round_finish_early"))
        self.assertIn("where not public.site_season_paused(r.season_key)),", function(self.sql, "reminders_claim"))
        guard = function(self.sql, "site_rounds_times_guard")
        self.assertIn("and public.site_season_paused(old.season_key) then\n    raise exception 'The league is paused. Resume it before changing a deadline.';", guard)
        self.assertIn("if public.site_round_paused(p_round) then", function(self.sql, "extend_site_round"))
        self.assertIn("if public.site_round_paused(p_round) then", function(self.sql, "nudge_round"))
        # a round laid out again while paused opens no sooner than the hold
        self.assertIn("opens := greatest(now(), prev_vote, held);", function(self.sql, "site_season_reschedule"))

    def test_the_timer_runs_every_minute_where_pg_cron_is(self):
        self.assertIn("if exists (select 1 from pg_extension where extname = 'pg_cron') then\n"
                      "    perform cron.schedule('pfml-pauses', '* * * * *', 'select public.site_pause_tick()');", MIG)
        tick = function(self.sql, "site_pause_tick")
        self.assertIn("perform pg_advisory_xact_lock(hashtext('pfml.site_pause_tick'));", tick)
        self.assertIn("perform public.site_rotation_tick();", tick)

    def test_a_nudge_waits_six_hours_and_reaches_only_those_still_out(self):
        nudge = function(self.sql, "nudge_round")
        self.assertIn("if last > now() - interval '6 hours' then", nudge)
        self.assertIn("from public.site_round_waiting(p_round) w;", nudge)
        waiting = function(self.sql, "site_round_waiting")
        self.assertIn("not public.site_sitting_out(p_round, p.competitor_id)", waiting)

    def test_sitting_out(self):
        self.assertIn("if public.site_sitting_out(new.round_id, me) then", function(self.sql, "site_owner_not_sitting_out"))
        self.assertIn("create trigger site_owner_not_sitting_out before insert on public.site_submission_owners", self.sql)
        ask = function(self.sql, "ask_sit_out")
        self.assertIn("if phase not in ('upcoming', 'submitting') and not (role = 'spectator' and phase = 'voting') then", ask)
        self.assertIn("raise exception 'Take your track out first, then ask to sit the round out.';", ask)
        early = function(self.sql, "site_round_finish_early")
        self.assertEqual(early.count("not public.site_sitting_out(p_round, p.competitor_id)"), 3)

    def test_rotation_hands_round_n_plus_2_to_round_ns_winner(self):
        tick = function(self.sql, "site_rotation_tick")
        self.assertIn("order by y.opens_at, y.id offset 1 limit 1;", tick)
        self.assertIn("where s.prompt_rotation and public.site_round_phase(r.id) = 'finished'", tick)
        winners = function(self.sql, "site_round_winners")
        self.assertIn("from t where t.pts > 0 and t.pts = (select max(pts) from t);", winners)
        decide = function(self.sql, "decide_prompt_turn")
        self.assertIn("perform public.site_round_people_apply(p_round, null, to_jsonb(t.writers));", decide)
        # turning it on mid-season hands out nothing for rounds already done
        self.assertIn("on conflict (from_round) do nothing;", function(self.sql, "set_site_season_rotation"))

    def test_the_log_never_shows_an_invite_link(self):
        self.assertIn("perform public.site_log('Made an invite link for ' || pname, null, null, auth.uid());", function(self.sql, "create_invite"))
        self.assertNotIn("code_ ||", function(self.sql, "create_invite"))

    def test_announcements_wait_for_their_time_and_their_season(self):
        policy = self.sql.split('create policy "members read announcements" on public.site_announcements', )[-1].split(";", 1)[0]
        self.assertIn("(send_at is null or send_at <= now())", policy)
        self.assertIn("where p.season_key = site_announcements.season_key and m.user_id = auth.uid()", policy)
        claim = function(self.sql, "announcements_claim")
        self.assertIn("update public.site_push_notices n set pushed_at = now()", claim)
        self.assertIn("case n.kind when 'nudge_submit' then rs.round_open when 'nudge_vote' then rs.voting else rs.announcements end", claim)

    def test_pages_see_the_pause_and_the_days(self):
        listing = function(self.sql, "site_rounds_list")
        for key in ("'paused', public.site_season_paused(r.season_key)", "'paused_until'", "'submit_days', r.submit_days",
                    "'site_round_sitouts'"):
            self.assertIn(key, listing)
        self.assertIn("coalesce(x.submit_days, s.submit_days) as sd, coalesce(x.vote_days, s.vote_days) as vd",
                      function(self.sql, "site_season_reschedule"))

    def test_the_rehearsal_counts_its_checks(self):
        n = REHEARSAL.count("checks := checks + 1;")
        self.assertEqual(n, 17)
        self.assertIn(f'"Rehearsal passed: {n} checks held. Nothing was kept."', REHEARSAL)


class ThePages(unittest.TestCase):
    def setUp(self):
        self.cm = read(SITE / "commissioner.js")
        self.html = read(SITE / "commissioner.html")
        self.now = read(SITE / "now.js")
        self.css = read(SITE / "style.css")

    def test_the_page_is_in_tabs(self):
        tabs = re.findall(r'<a href="#(\w+)" data-tab="(\w+)"', self.html)
        self.assertEqual([t[0] for t in tabs], ["now", "seasons", "announce", "people", "log", "more"])
        self.assertEqual([t[0] for t in tabs], [t[1] for t in tabs])
        panels = set(re.findall(r'data-panel="(\w+)"', self.html))
        self.assertEqual(panels, {t[0] for t in tabs})
        # each tab hides every other panel, whatever the panel's own display
        for t in panels:
            self.assertIn(f'main[data-tab="{t}"] [data-panel]:not([data-panel="{t}"])', self.css)
        self.assertIn('var TABS = ["now", "seasons", "announce", "people", "log", "more"];', self.cm)
        # the People tab is the admin's only
        self.assertIn('if (t === "people" && !isAdmin()) t = "";', js_body(self.cm, "function currentTab() {"))

    def test_now_draws_with_the_rest(self):
        self.assertIn("if (window.PFMLNow) window.PFMLNow.render({ rounds: state.rounds, seasons: state.seasons, reload: load });",
                      js_body(self.cm, "function render() {"))

    def test_it_asks_in_the_page_before_anything_that_counts(self):
        click = js_body(self.now, "function onClick(ev) {")
        for act, call in (("close", "api().updateSiteRound(r.id"), ("nudge", "api().nudgeRound(r.id)"),
                          ("resume", "api().resumeSeason(s.key)"), ("cancel-pause", "api().resumeSeason(s.key)")):
            with self.subTest(act):
                part = click.split('if (act === "' + act + '") {', 1)[1]
                self.assertLess(part.index("ask(b,"), part.index(call))
        submit = js_body(self.now, "function onSubmit(ev) {")
        self.assertLess(submit.index("ask(btn,"), submit.index("api().pauseSeason("))
        # no browser box left on the Commissioner page's own code
        for name in ("commissioner.js", "seasons.js", "now.js"):
            src = read(SITE / name)
            self.assertNotRegex(src, r"if \(!?window\.confirm\(", name)

    def test_the_nudge_button_waits_as_long_as_the_database(self):
        self.assertIn("var NUDGE_GAP_MS = 6 * 3600 * 1000;", self.now)
        self.assertIn("if last > now() - interval '6 hours' then", MIG)

    def test_a_hidden_form_stays_hidden(self):
        # .sub-admin-form's display would beat the hidden attribute (CLAUDE.md)
        self.assertIn("'<form class=\"sub-admin-form cn-resume-form\" data-act=\"set-resume\" hidden novalidate>'", self.now)
        self.assertIn(".cn-resume-form[hidden] { display: none; }", self.css)

    def test_invite_links_from_the_page(self):
        status = js_body(self.cm, "function renderLeagueStatus() {")
        self.assertIn('data-act="invite"', status)
        self.assertNotIn("scripts/invites.py", status)
        self.assertIn('var link = "https://pfml.fun/?invite=" + encodeURIComponent(code);', js_body(self.cm, "function onInvite(ev) {"))

    def test_announcements_can_wait_and_go_to_one_season(self):
        post = js_body(self.cm, "function postAnnouncement(form) {")
        self.assertIn("api().postAnnouncement(text, at.at, season)", post)
        auth = read(SITE / "auth.js")
        self.assertIn('client.rpc("post_announcement", { p_body: body, p_send_at: sendAt || null, p_season: seasonKey || null })', auth)
        self.assertIn('client.rpc("edit_announcement", { p_id: id, p_body: body, p_send_at: sendAt || null })', auth)

    def test_the_season_setup_is_kept_as_it_goes(self):
        seasons = read(SITE / "seasons.js")
        self.assertIn('var DRAFT_KEY = "pfml.seasonDraft";', seasons)
        self.assertIn("saveDraft();", js_body(seasons, "function drawWizard() {"))
        create = js_body(seasons, "function create() {")
        # dropped once the season exists, before the page redraws
        self.assertIn("wizard = null;\n        dropDraft();\n        return Promise.resolve(ctx.reload())", create)
        self.assertIn("api().setSeasonRotation(d.key, true)", create)
        # a draft for a season since created is thrown away
        self.assertIn("if (draft && ctx.seasons.some(function (s) { return s.key === draft.d.key; })) { dropDraft(); draft = null; }", seasons)

    def test_a_rounds_own_days_only_before_it_opens(self):
        seasons = read(SITE / "seasons.js")
        self.assertIn('(upcoming ? daysFields(r) : "") +', js_body(seasons, "function roundRow(r, i, rounds) {"))
        self.assertIn("return api().setSiteRoundDays(id, sd, vd);", js_body(seasons, "function onSubmit(ev) {"))


class MembersSeeIt(unittest.TestCase):
    def test_the_pause_strip_on_every_page(self):
        account = read(SITE / "account.js")
        strip = js_body(account, "function renderPauseStrip() {")
        self.assertIn("api_.pauses().then(function (rows) {", strip)
        self.assertIn('if (bar) bar.insertAdjacentElement("afterend", box);', strip)
        self.assertIn("PFML.ready.then(renderPauseStrip);", account)
        self.assertIn("PFML.pauseNote = pauseNote;", account)

    def test_a_paused_round_says_so_instead_of_its_countdown(self):
        for name, needle in (("app.js", "PFML.pauseNote(open, open.closes_at)"), ("app.js", "PFML.pauseNote(r, r.voting_closes_at)"),
                             ("rounds.js", "PFML.pauseNote(r, phase === \"submitting\" ? r.closes_at : r.voting_closes_at)"),
                             ("submit.js", "PFML.pauseNote(r, open ? r.closes_at : r.voting_closes_at)"),
                             ("voting.js", "PFML.pauseNote(r, r.voting_closes_at)")):
            with self.subTest(name):
                self.assertIn(needle, read(SITE / name))

    def test_sitting_out_on_the_submit_page(self):
        submit = read(SITE / "submit.js")
        self.assertIn('api().askSitOut(row.getAttribute("data-sitout"), row.getAttribute("data-on") === "1")', js_body(submit, "function onSitOut(ev) {"))
        self.assertIn('if (!r || !r.votes_on_site || !PFML.member || typeof api().askSitOut !== "function") return "";',
                      js_body(submit, "function sitOutHtml(r, open) {"))

    def test_a_winner_writes_the_prompt_on_home(self):
        app = read(SITE / "app.js")
        self.assertIn('<section class="shell announce" id="promptTurnBox" hidden></section>', read(SITE / "index.html"))
        self.assertIn("renderPromptTurns();", js_body(app, "function initHome() {"))
        self.assertIn('PFML.api.sendPromptTurn(form.getAttribute("data-turn"), name, prompt)', js_body(app, "function onPromptTurn(ev) {"))

    def test_home_holds_a_scheduled_announcement_back(self):
        home = js_body(read(SITE / "app.js"), "function renderAnnouncements() {")
        self.assertIn("return at(a) > since && at(a) <= Date.now(); })", home)


if __name__ == "__main__":
    unittest.main()
