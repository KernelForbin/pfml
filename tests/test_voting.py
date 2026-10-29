"""Voting on the site (README, Voting on the site): built 2026-10-25 and off
until the user switches it on. The database rules read as text (there's no
Postgres here; supabase/checks/2026-10-25_site_voting_rehearsal.sql runs a
whole round in the real database and undoes it, and
test_live_voting.py runs the ballot rules there), the switch that keeps it
dark, the promise that a round already open (Round 7) can never get it, and
the page wiring. The pages were checked in a browser against a stand-in
with the switch on."""
import re
import unittest

from support import ROOT
from test_submissions import block, function, read, schema

SITE = ROOT / "site"
MIGRATION = ROOT / "supabase" / "migrations" / "2026-10-25_site_voting.sql"
REHEARSAL = ROOT / "supabase" / "checks" / "2026-10-25_site_voting_rehearsal.sql"
MEMBER_CALLS = ["site_round_phase", "cast_ballot", "my_ballot", "site_round_voters", "site_round_results", "site_round_votes"]


def js_body(js, signature):
    return js.split(signature, 1)[1].split("\n  }\n", 1)[0]


class SameInBothPlaces(unittest.TestCase):
    def test_schema_has_what_the_migration_adds(self):
        migration = read(MIGRATION)
        body = migration[migration.index("-- Which rounds vote here"):]
        self.assertIn(body, schema())

    def test_the_rehearsal_plays_a_round_and_keeps_nothing(self):
        script = read(REHEARSAL)
        self.assertIn("2026-10-25_site_voting.sql", script)
        # an error at the end rolls the whole thing back, whatever happened
        self.assertTrue(script.rstrip().endswith("raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;\nend $$;"))
        self.assertNotRegex(script, r"(?i)\bcommit\b")
        for call in ("submit_track", "cast_ballot", "my_ballot", "site_round_voters", "site_round_results", "site_round_votes"):
            self.assertIn(f"public.{call}(", script)

    def test_the_rehearsals_ballots_are_jsonb(self):
        # cast_ballot takes jsonb, and Postgres won't turn json into it on a
        # call: the first run stopped at "function public.cast_ballot(uuid,
        # json) does not exist" (2026-10-25)
        script = read(REHEARSAL)
        self.assertNotRegex(script, r"cast_ballot\(rid, json_build")
        self.assertEqual(len(re.findall(r"perform public\.cast_ballot\(rid, jsonb_build_array\(", script)), 3)
        for call in re.findall(r"select public\.cast_ballot\(%L, %L(::\w+)?\)", script):
            self.assertEqual(call, "::jsonb")


class Round7CanNeverVoteHere(unittest.TestCase):
    """A round has site voting only if it was opened with it; nothing can add
    it later, so every round that exists today keeps voting in Music League."""

    def setUp(self):
        self.sql = schema()

    def test_off_for_every_existing_round(self):
        self.assertIn("alter table public.site_rounds add column if not exists votes_on_site boolean not null default false;", self.sql)

    def test_the_trigger_refuses_to_switch_it_either_way(self):
        fn = function(self.sql, "site_rounds_voting_fixed")
        self.assertIn("if new.votes_on_site is distinct from old.votes_on_site then\n    raise exception", fn)
        self.assertIn("create trigger site_rounds_voting_fixed before update on public.site_rounds\n  for each row", self.sql)

    def test_a_round_that_votes_here_has_a_voting_deadline_after_submissions(self):
        shape = block(self.sql, "alter table public.site_rounds add constraint site_rounds_voting_shape")
        self.assertIn("votes_on_site = (voting_closes_at is not null)", shape)
        self.assertIn("voting_closes_at > closes_at", shape)
        self.assertIn("max_per_track <= point_budget", shape)

    def test_the_rules_freeze_when_submissions_close(self):
        fn = function(self.sql, "site_rounds_voting_fixed")
        self.assertIn("(new.point_budget, new.max_per_track, new.nonvoters_keep_points, new.downvotes, new.max_down_per_track)", fn)
        self.assertIn("and (old.closed_at is not null or now() >= old.closes_at) then", fn)
        self.assertIn("if new.songs_per_round is distinct from old.songs_per_round and now() >= old.opens_at then", fn)

    def test_the_defaults_are_season_3s_and_non_voters_score_0(self):
        self.assertIn("point_budget smallint not null default 19", self.sql)
        self.assertIn("max_per_track smallint not null default 5", self.sql)
        self.assertIn("nonvoters_keep_points boolean not null default false", self.sql)


class Ballots(unittest.TestCase):
    def setUp(self):
        self.sql = schema()
        self.cast = function(self.sql, "cast_ballot")

    def test_votes_are_reached_only_through_the_functions(self):
        self.assertIn("alter table public.site_votes enable row level security;", self.sql)
        self.assertIn("revoke all on table public.site_votes from anon, authenticated;", self.sql)
        self.assertNotRegex(self.sql, r"create policy[^;]*on public\.site_votes")
        for path in SITE.glob("*.js"):
            self.assertNotIn('from("site_votes")', path.read_text(encoding="utf-8"), path.name)

    def test_only_a_member_with_a_track_votes_and_only_while_voting_is_open(self):
        order = [self.cast.index(s) for s in (
            "if not public.is_member() then",
            "if public.site_round_phase(p_round) <> 'voting' then",
            # a Spectator, with no track, votes too (2026-10-29)
            "if mine is null and public.site_user_role(p_round, uid) is distinct from 'spectator' then\n"
            "    raise exception 'Only players with a track in this round, and its Spectators, can vote.';",
            "problem := public.ballot_problem(r.point_budget, r.max_per_track, r.downvotes, r.max_down_per_track, pts,",
            "delete from public.site_votes where round_id = p_round and user_id = uid;",
            "insert into public.site_votes")]
        self.assertEqual(order, sorted(order))
        # every one of the voter's tracks (a round can take more than one)
        self.assertIn("select array_agg(o.submission_id) into mine from public.site_submission_owners o", self.cast)
        self.assertIn("array(select s = any(mine) from unnest(sids) s)", self.cast)
        self.assertIn("where t.p <> 0 or t.c <> '';", self.cast)

    def test_every_track_on_the_ballot_is_in_the_round_once(self):
        self.assertIn("where x.id = s and x.round_id = p_round", self.cast)
        self.assertIn("(select count(distinct s) from unnest(sids) s) <> cardinality(sids)", self.cast)

    def test_the_rules_themselves(self):
        # the one cast_ballot calls: upvotes spent in full, downvotes
        # optional up to their limit (Season 1's exports: every ballot spent
        # all 16 upvotes, 15 of 316 used downvotes)
        fn = function(self.sql, "ballot_problem")
        self.assertIn("create or replace function public.ballot_problem(p_budget int, p_max int, p_down int, p_down_max int,", fn)
        self.assertIn("immutable", fn)
        for rule in ("where p < 0) and coalesce(p_down, 0) = 0", "where p > p_max", "where p < -p_down_max", "where own and p <> 0",
                     "where p > 0), 0) <> p_budget", "where p < 0), 0) > p_down\n"):
            with self.subTest(rule):
                self.assertIn(rule, fn)

    def test_a_vote_row_is_points_or_a_comment(self):
        table = block(self.sql, "create table if not exists public.site_votes")
        self.assertIn("primary key (submission_id, user_id)", table)
        # since downvotes: any points but 0, or a comment
        self.assertIn("alter table public.site_votes add constraint site_votes_points_range check (points between -20 and 100);", self.sql)
        self.assertIn("alter table public.site_votes add constraint site_votes_points_or_comment check (points <> 0 or char_length(btrim(comment)) > 0);", self.sql)
        self.assertIn("alter table public.site_votes add constraint site_votes_comment_length check (char_length(comment) <= 2000);", self.sql)


class AnonymousUntilVotingCloses(unittest.TestCase):
    def setUp(self):
        self.sql = schema()

    def test_who_sent_what_and_every_vote_only_once_voting_has_closed(self):
        for name in ("site_round_results", "site_round_votes"):
            fn = function(self.sql, name)
            self.assertIn("public.is_member()", fn, name)
            self.assertIn("public.site_round_phase(p_round) = 'finished'", fn, name)

    def test_during_voting_only_your_own_ballot_and_who_has_voted(self):
        self.assertIn("v.user_id = auth.uid()", function(self.sql, "my_ballot"))
        voters = function(self.sql, "site_round_voters")
        self.assertIn("returns setof text", voters)
        self.assertNotRegex(voters, r"points|comment|submission_id")

    def test_a_non_voter_scores_0_unless_the_round_says_so(self):
        # only the downvotes they got, as Music League does: 0 with none
        fn = function(self.sql, "site_round_results")
        self.assertIn("or r.nonvoters_keep_points\n              then coalesce(t.total, 0) else coalesce(t.down, 0) end", fn)
        self.assertIn("sum(least(v.points, 0))::int as down", fn)

    def test_grants(self):
        for name in MEMBER_CALLS:
            with self.subTest(name):
                self.assertRegex(self.sql, rf"revoke all on function public\.{name}\([^)]*\) from public, anon;")
                self.assertRegex(self.sql, rf"grant execute on function public\.{name}\([^)]*\) to authenticated;")
        for name in ("ballot_problem", "site_rounds_voting_fixed"):
            self.assertRegex(self.sql, rf"revoke all on function public\.{name}\([^)]*\) from public, anon, authenticated;")
            self.assertNotRegex(self.sql, rf"grant execute on function public\.{name}\(")


class TheSwitch(unittest.TestCase):
    """On since seasons set up on the site (the user's call, 2026-10-25:
    every such season votes on pfml.fun). It changed what the site promises,
    so the pages that say so came with it (README, Voting on the site), and
    a round votes here only through such a season."""

    def test_voting_is_on_and_the_pages_say_what_it_changes(self):
        account = read(SITE / "account.js")
        self.assertEqual(re.findall(r"var SITE_VOTING = (\w+);", account), ["true"])
        self.assertIn("PFML.siteVoting = SITE_VOTING;", account)
        privacy = read(SITE / "privacy.html")
        self.assertIn("Once that round's voting closes, every member sees the results: who submitted each track", privacy)
        self.assertIn("from the site itself once each round's voting has closed", privacy)
        self.assertIn("the results name everyone once voting closes", read(SITE / "submit.html"))
        for page in ("index.html", "career.html", "profile.html", "season.template.html", "round.html"):
            with self.subTest(page):
                self.assertIn("and from pfml.fun for a season played here", read(SITE / page))
                self.assertNotIn("Built from Music League's CSV export.", read(SITE / page))
        self.assertIn("<h3>Vote on the site</h3>", read(SITE / "features.html"))
        self.assertNotIn("Voting still happens in Music League, as usual.", read(SITE / "features.html"))

    def test_everything_voting_shows_waits_for_the_switch(self):
        voting = read(SITE / "voting.js")
        self.assertIn("function on(r) { return !!(PFML.siteVoting && r && r.votes_on_site); }", voting)
        self.assertIn('if (!on(r) || PFML.roundPhase(r) !== "finished") { host.hidden = true; host.innerHTML = ""; return; }',
                      js_body(voting, "function render(r, host) {"))
        self.assertIn('var voting = !!(window.PFMLVoting && window.PFMLVoting.on(r) && phase === "voting");',
                      js_body(read(SITE / "listen.js"), "function render(host, r) {"))
        self.assertIn("if (!PFML.siteVoting || !r || !r.votes_on_site) return \"\";", js_body(voting, "function adminFields(r) {"))
        self.assertIn("if (!on(r) || PFML.roundPhase(r) !== \"voting\") return null;", js_body(voting, "function adminPanel(r, done, fail) {"))
        banner = js_body(read(SITE / "app.js"), "function votingBanner(rounds) {")
        self.assertTrue(banner.lstrip().startswith("if (!PFML.siteVoting) return false;"))

    def test_no_form_asks_for_site_voting(self):
        # a round votes here only as part of a season set up on the site;
        # the database refuses a round opened by hand that asks to
        voting = read(SITE / "voting.js")
        self.assertIn('if (!$("vtAdmBody") || !r) return { fields: {} };', js_body(voting, "function readAdmin(r, closesAt) {"))
        for name in ("voting.js", "submit.js", "commissioner.js", "seasons.js"):
            with self.subTest(name):
                self.assertNotRegex(read(SITE / name), r"votes_on_site\s*[:=]\s*true")
        guard = function(schema(), "site_rounds_times_guard")
        self.assertIn("if new.votes_on_site then\n      raise exception 'Only a season set up on the site votes on the site.';", guard)

    def test_the_page_and_the_database_agree_on_the_phase(self):
        js = js_body(read(SITE / "account.js"), "function roundPhase(r) {")
        sql = function(schema(), "site_round_phase")
        pairs = [('if (r.opens_at && now < Date.parse(r.opens_at)) return "upcoming";', "when now() < r.opens_at then 'upcoming'"),
                 ('if (!r.closed_at && now < Date.parse(r.closes_at)) return "submitting";', "when r.closed_at is null and now() < r.closes_at then 'submitting'"),
                 ('if (!r.votes_on_site) return "closed";', "when not r.votes_on_site then 'closed'"),
                 ('if (!r.voting_closed_at && now < Date.parse(r.voting_closes_at)) return "voting";', "when r.voting_closed_at is null and now() < r.voting_closes_at then 'voting'"),
                 ('return "finished";', "else 'finished' end")]
        for page, db in pairs:
            self.assertIn(page, js)
            self.assertIn(db, sql)


class ThePage(unittest.TestCase):
    def test_pages_load_voting_before_what_uses_it(self):
        # the ballot is on the round page since 2026-10-26; the Submit page
        # only asks whether a round votes here
        for page, user in (("round.html", "listen.js"), ("submit.html", "submit.js")):
            with self.subTest(page):
                srcs = re.findall(r'<script src="([^"]+)"', read(SITE / page))
                self.assertLess(srcs.index("voting.js"), srcs.index(user))
        self.assertNotIn('id="subVote"', read(SITE / "submit.html"))

    def test_the_ballot_lists_tracks_in_the_rounds_one_shuffle(self):
        # the same order the track list above starts in (PFML.roundOrder)
        voting = read(SITE / "voting.js")
        self.assertIn("state.rows = PFML.roundOrder(r.id, res[0] || []);", voting)
        self.assertNotIn("a.tag < b.tag", voting)
        # the ballot is the listening list itself, so it has the list's order
        self.assertIn("window.PFMLVoting.ballot(r, rows, { head: $(\"lnVoteHead\"), list: $(\"lnTracks\"), bar: $(\"lnVoteBar\"),",
                      js_body(read(SITE / "listen.js"), "function render(host, r) {"))

    def test_submit_js_works_without_it(self):
        fallback = js_body(read(SITE / "submit.js"), "function voting() {")
        self.assertIn("return window.PFMLVoting || { on: function () { return false; }", fallback)

    def test_the_round_list_asks_for_what_voting_needs(self):
        auth = read(SITE / "auth.js")
        rounds = auth.split("siteRounds: function () {", 1)[1].split("},", 1)[0]
        for col in ("votes_on_site", "voting_closes_at", "voting_closed_at", "point_budget", "max_per_track", "nonvoters_keep_points"):
            self.assertIn(col, rounds)
        self.assertIn('select("id, tag, platform, track,', auth)

    def test_names_votes_and_comments_are_escaped(self):
        voting = read(SITE / "voting.js")
        self.assertIn("esc(v.comment)", voting)
        self.assertIn('esc(names[id] || "Member")', voting)
        self.assertIn("esc(s.title)", voting)
        self.assertIn('esc(state.comments[s.id] || "") + "</textarea></div>";', voting)


if __name__ == "__main__":
    unittest.main()
