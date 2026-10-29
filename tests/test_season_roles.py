"""DJs, Spectators and prompters (asked 2026-10-29; README, DJs and
Spectators): everyone playing a season set up on the site is a DJ (sends
tracks and votes) or a Spectator (votes and comments, never sends a track),
for the season, and any round can change that while it still takes tracks.
A round can also name who wrote its prompt. The SQL runs only in the user's
rehearsal (supabase/checks/2026-10-29_season_roles_rehearsal.sql) and
tests/test_live_season_roles.py; the pages were checked in a browser. The
stats build is run here, with a made-up Spectator."""
import copy
import re
import unittest

from support import ROOT, build, make_season, quiet, sandbox
from test_build import TIE_ROUND
from test_reminders import js_body
from test_site_results import PLAYERS, SITE_ROUND, write_site
from test_submissions import function, read, schema

SITE = ROOT / "site"
MIG = read(ROOT / "supabase" / "migrations" / "2026-10-29_season_roles.sql")
REHEARSAL = read(ROOT / "supabase" / "checks" / "2026-10-29_season_roles_rehearsal.sql")
SEASONS = read(SITE / "seasons.js")


class TheDatabase(unittest.TestCase):
    def setUp(self):
        self.sql = schema()

    def test_schema_has_the_migration(self):
        self.assertIn(MIG[MIG.index("alter table public.site_season_players"):], self.sql)

    def test_a_role_per_player_and_per_round(self):
        self.assertIn("add column if not exists role text not null default 'dj' check (role in ('dj', 'spectator'));", MIG)
        roles = MIG.split("create table if not exists public.site_round_roles (", 1)[1].split(");", 1)[0]
        self.assertIn("round_id      uuid not null references public.site_rounds (id) on delete cascade,", roles)
        self.assertIn("role          text not null check (role in ('dj', 'spectator')),", roles)
        self.assertIn("primary key (round_id, competitor_id)", roles)

    def test_members_read_them_and_only_the_functions_write(self):
        # a new table gets its grants explicitly (CLAUDE.md, from 2026-10-30)
        for table in ("site_round_roles", "site_round_prompters"):
            with self.subTest(table):
                self.assertIn(f"alter table public.{table:<20} enable row level security;", MIG)
                self.assertRegex(MIG, rf"create policy \"members read [a-z ]+\" on public\.{table}\n"
                                      r"  for select to authenticated using \(public\.is_member\(\)\);")
                self.assertIn(f"revoke all on table public.{table} from anon, authenticated;", MIG)
                self.assertIn(f"grant select on table public.{table} to authenticated;", MIG)
                self.assertNotRegex(MIG, rf"grant (insert|update|delete|all)[^;]* on table public\.{table}")

    def test_who_can_call_what(self):
        for name, args in (("site_round_roster", "uuid"), ("set_site_round_people", "uuid, jsonb, jsonb"),
                           ("set_site_season_roster", "text, jsonb")):
            with self.subTest(name):
                self.assertIn(f"revoke all on function public.{name}({args}) from public, anon;", MIG)
                self.assertIn(f"grant execute on function public.{name}({args}) to authenticated;", MIG)
        for name, args in (("site_round_role", "uuid, text"), ("site_user_role", "uuid, uuid"), ("site_round_dj_count", "uuid"),
                           ("site_round_people_apply", "uuid, jsonb, jsonb"), ("site_owner_is_dj", "")):
            with self.subTest(name):
                self.assertIn(f"revoke all on function public.{name}({args}) from public, anon, authenticated;", MIG)

    def test_a_round_outside_a_season_has_no_roles(self):
        # Round 7 and every round before it: everyone is a DJ, as before
        role = function(self.sql, "site_round_role")
        self.assertIn("when not exists (select 1 from public.site_rounds r join public.site_seasons s on s.key = r.season_key\n"
                      "                      where r.id = p_round) then 'dj'", role)
        self.assertIn("else (select coalesce(x.role, p.role)", role)
        self.assertIn("join public.site_season_players p on p.season_key = r.season_key and p.competitor_id = p_competitor", role)

    def test_a_spectator_never_sends_a_track(self):
        trigger = function(self.sql, "site_owner_is_dj")
        self.assertIn("if public.site_user_role(new.round_id, new.user_id) = 'spectator' then", trigger)
        self.assertIn("create trigger site_owner_is_dj before insert on public.site_submission_owners\n"
                      "  for each row execute function public.site_owner_is_dj();", self.sql)

    def test_a_spectator_votes_and_saves_drafts(self):
        for name in ("cast_ballot", "save_ballot_draft"):
            with self.subTest(name):
                fn = function(self.sql, name)
                self.assertIn("if mine is null and public.site_user_role(p_round, uid) is distinct from 'spectator' then", fn)
                self.assertIn("mine := coalesce(mine, '{}');", fn)
                self.assertLess(fn.index("mine := coalesce(mine, '{}');"), fn.index("array(select s = any(mine) from unnest(sids) s)"))

    def test_roles_settle_when_submissions_close(self):
        people = function(self.sql, "set_site_round_people")
        self.assertIn("if p_roles is not null and public.site_round_phase(p_round) not in ('upcoming', 'submitting') then", people)
        self.assertLess(people.index("if not public.is_commissioner() then"), people.index("perform public.site_round_people_apply("))
        apply = function(self.sql, "site_round_people_apply")
        # a DJ with a track stays one, and a round keeps 2 DJs
        self.assertIn("raise exception '% has already sent a track to this round, so stays a DJ in it.', who;", apply)
        self.assertLess(apply.index("raise exception '% has already sent a track"), apply.index("delete from public.site_round_roles"))
        self.assertIn("if public.site_round_dj_count(p_round) < 2 then", apply)
        # only the roles that differ from the season's are kept
        self.assertIn("where e.value <> p.role;", apply)
        self.assertIn("raise exception 'A prompter has to be a member who has joined the site.';", apply)

    def test_a_season_change_never_reaches_a_closed_round(self):
        roster = function(self.sql, "set_site_season_roster")
        pin = roster.index("insert into public.site_round_roles (round_id, competitor_id, role)")
        self.assertLess(pin, roster.index("insert into public.site_season_players"))
        self.assertIn("and (public.site_round_phase(r.id) not in ('upcoming', 'submitting')\n"
                      "          or exists (select 1 from public.site_submission_owners o", roster)
        self.assertIn("A season needs at least 2 DJs.", roster)
        self.assertIn("would have fewer than 2 DJs. Change its roles first.", roster)

    def test_a_season_is_set_up_with_roles_and_each_round_with_its_own(self):
        create = function(self.sql, "create_site_season")
        self.assertIn("insert into public.site_season_players (season_key, competitor_id, role)", create)
        self.assertIn("perform public.site_round_people_apply(rid, item->'roles', item->'prompters');", create)
        self.assertLess(create.index("A season needs at least 2 DJs."), create.index("insert into public.site_seasons"))

    def test_only_djs_hold_submissions_open_and_spectators_hold_voting(self):
        early = function(self.sql, "site_round_finish_early")
        submitting = early.split("if public.site_round_phase(p_round) = 'submitting' then", 1)[1].split("saved :=", 1)[0]
        self.assertEqual(submitting.count("public.site_round_role(p_round, p.competitor_id) = 'dj'"), 2)
        voting = early.split("elsif public.site_round_phase(p_round) = 'voting' then", 1)[1]
        self.assertIn("public.site_round_role(p_round, p.competitor_id) = 'spectator'", voting)

    def test_reminders_tell_djs_to_submit_and_everyone_to_vote(self):
        claim = function(self.sql, "reminders_claim")
        self.assertIn("and public.site_round_role(r.id, m.competitor_id) = 'dj'", claim)
        self.assertIn("where public.site_round_role(x.id, p.competitor_id) = 'spectator') w on w.round_id = r.id", claim)

    def test_the_lounge_lets_a_spectator_in(self):
        self.assertIn("or public.site_user_role(r.id, auth.uid()) = 'spectator' end,", function(self.sql, "lounge_state"))

    def test_the_rehearsal_counts_its_checks(self):
        self.assertEqual(len(re.findall(r"^  checks := checks \+ 1;", REHEARSAL, re.M)), 12)
        self.assertIn('"Rehearsal passed: 12 checks held. Nothing was kept."', REHEARSAL)


class ThePages(unittest.TestCase):
    def test_the_database_calls(self):
        auth = read(SITE / "auth.js")
        for call in ('client.rpc("site_round_roster", { p_round: roundId })',
                     'client.rpc("set_site_season_roster", { p_key: key, p_players: players })',
                     'client.rpc("set_site_round_people", { p_round: roundId, p_roles: roles, p_prompters: prompters })',
                     '"site_round_prompters(competitor_id), site_round_roles(competitor_id, role)"',
                     '"site_season_players(competitor_id, role)"'):
            self.assertIn(call, auth)
        # the old call, which knew nothing of roles, is gone from the pages
        self.assertNotIn("set_site_season_players", auth)

    def test_a_round_outside_a_season_makes_everyone_a_dj(self):
        account = read(SITE / "account.js")
        self.assertIn("if (!list) return \"dj\";", js_body(account, "function myRole(r) {"))

    def test_a_spectator_gets_no_submit_form(self):
        render = js_body(read(SITE / "submit.js"), "function render() {")
        self.assertIn('if (open && state.role !== "spectator" && (state.mine.length < songsOf(r) || state.changing)) renderForm();', render)
        self.assertIn('state.role === "spectator" ? \'<p class="sub-role">', render)

    def test_a_spectator_gets_a_ballot(self):
        ballot = js_body(read(SITE / "voting.js"), "function ballot(r, rows, parts) {")
        self.assertIn('state.spectators = roster.filter(function (x) { return x.role === "spectator" && x.joined; })', ballot)
        self.assertIn("if (!mine.length && !spectator) {", ballot)
        # they count among who's still to vote
        self.assertIn("submitters = submitters.concat(state.spectators);", ballot)

    def test_home_tells_a_spectator_to_vote_not_submit(self):
        app = read(SITE / "app.js")
        self.assertIn('if (res[1] === "spectator") {', js_body(app, "function bannerMine(round) {"))
        self.assertIn('if (!res[0].length && res[2] !== "spectator")', js_body(app, "function votingBanner(rounds) {"))

    def test_the_prompter_shows_on_the_round_and_the_submit_page(self):
        rounds = read(SITE / "rounds.js")
        for sig in ("function renderSiteRoundPage(r, label) {", "function renderRoundPage(d, roundId) {"):
            self.assertIn('<p class="rp-prompter" id="rpPrompter" hidden></p>', js_body(rounds, sig))
        self.assertIn("PFML.promptBy(r).then(", js_body(read(SITE / "submit.js"), "function render() {"))

    def test_players_come_before_rounds_in_the_setup(self):
        self.assertIn('var STEPS = ["Details", "Songs + Votes", "Timing", "Players", "Rounds"];', SEASONS)
        draw = js_body(SEASONS, "function drawWizard() {")
        self.assertLess(draw.index("step === PLAYERS_STEP"), draw.index("promptersField([]) + rolesField(roster, {})"))

    def test_each_round_starts_from_the_season_role(self):
        self.assertIn("roleSelect(\"rrole-\" + p.id, own[p.id] || p.role,", js_body(SEASONS, "function rolesField(season, own) {"))
        # only the changes are kept, and sent with every player's role
        self.assertIn("if (Object.keys(changed).length) out.roles = fullRoles(roster, changed);",
                      js_body(SEASONS, "function roundForCreate(r, roster) {"))

    def test_prompters_are_members_who_have_joined(self):
        self.assertIn("people.players.filter(function (p) { return p.joined; })", js_body(SEASONS, "function promptersField(chosen) {"))

    def test_the_players_form_saves_roles(self):
        submit = js_body(SEASONS, "function onSubmit(ev) {")
        self.assertIn("done = api().setSiteSeasonRoster(key, list);", submit)
        self.assertIn("if (rosterProblem(list)) { panelMsg(form, rosterProblem(list)); return; }", submit)


class TheStats(unittest.TestCase):
    """A Spectator's votes count like anyone's, and they're never in the
    standings, since they never send a track."""
    def test_a_spectator_votes_but_isnt_in_the_standings(self):
        r = copy.deepcopy(SITE_ROUND)
        r["votes"].append({"submission": "s1", "voter": "p9", "points": 5, "comment": "from the stands", "cast_at": "2025-02-05T00:00:00Z"})
        with sandbox() as root, quiet():
            folder = root / "data" / "season1"
            make_season(folder, [TIE_ROUND])
            write_site(folder, [r], dict(PLAYERS, p9="Zed"))
            data, raw = build.build_season(folder, "season1", "Season 1")
            profiles = build.build_profiles([data])
        song = next(s for x in data["rounds"] for s in x["songs"] if s["title"] == "Spotify Song")
        self.assertEqual(song["points"], 5)
        self.assertNotIn("p9", [p["id"] for p in data["standings"]])
        self.assertNotIn("p9", profiles)


if __name__ == "__main__":
    unittest.main()
