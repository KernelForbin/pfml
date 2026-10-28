"""The voters' lounge (asked 2026-10-28): while voting is open, only the
people who have submitted their ballot can chat, anonymously, each as an
instrument for the round. The user's calls: one message every 24 hours,
280 characters, chatters never named, and when voting closes it locks and
stays readable under the results. The SQL runs only in the user's
rehearsal (supabase/checks/2026-10-28_voters_lounge_rehearsal.sql) and
tests/test_live_voters_lounge.py; the page was checked in a browser
(README, Voters' lounge)."""
import re
import unittest

from support import ROOT
from test_reminders import js_body

SITE = ROOT / "site"
SQL = (ROOT / "supabase" / "schema.sql").read_text(encoding="utf-8")
MIG = (ROOT / "supabase" / "migrations" / "2026-10-28_voters_lounge.sql").read_text(encoding="utf-8")
REHEARSAL = (ROOT / "supabase" / "checks" / "2026-10-28_voters_lounge_rehearsal.sql").read_text(encoding="utf-8")
LOUNGE = (SITE / "lounge.js").read_text(encoding="utf-8")


def sql_function(text, name):
    start = text.index(f"create or replace function public.{name}(")
    return text[start:text.index("$$;", start)]


class TheDatabase(unittest.TestCase):
    def test_schema_has_the_migration(self):
        self.assertIn(MIG[MIG.index("create table if not exists public.site_lounge_aliases"):], SQL)

    def test_only_the_functions_reach_the_tables(self):
        for table in ("site_lounge_aliases", "site_lounge_messages", "site_lounge_reactions"):
            with self.subTest(table):
                self.assertIn(f"alter table public.{table} enable row level security;", MIG)
                self.assertIn(f"revoke all on table public.{table} from anon, authenticated;", MIG)
                self.assertNotRegex(MIG, rf"grant [^;]* on table public\.{table}")
        self.assertNotIn("create policy", MIG)
        for name, args in (("lounge_status", "uuid, boolean"), ("lounge_messages", "uuid, boolean"),
                           ("lounge_post", "uuid, boolean, text"), ("lounge_react", "bigint, text, boolean"),
                           ("lounge_remove", "bigint")):
            with self.subTest(name):
                self.assertIn(f"revoke all on function public.{name}({args}) from public, anon;", MIG)
                self.assertIn(f"grant execute on function public.{name}({args}) to authenticated;", MIG)
        for name, args in (("lounge_alias_name", "int"), ("lounge_state", "uuid, boolean"),
                           ("lounge_can", "uuid, boolean, boolean"), ("lounge_alias", "uuid, boolean"), ("lounge_gap", "boolean")):
            with self.subTest(name):
                self.assertIn(f"revoke all on function public.{name}({args}) from public, anon, authenticated;", MIG)

    def test_nothing_a_member_can_call_gives_out_who(self):
        for name in ("lounge_status", "lounge_messages"):
            with self.subTest(name):
                head = sql_function(MIG, name).split("as $$", 1)[0]
                self.assertNotRegex(head, r"user_id|competitor_id|\bname\b")
        status = sql_function(MIG, "lounge_status")
        self.assertNotIn("user_id", status.split("return jsonb_build_object(", 1)[1])

    def test_in_means_voted_and_open_means_three_voters_while_voting(self):
        state = sql_function(MIG, "lounge_state")
        self.assertIn("else exists (select 1 from public.site_votes v where v.round_id = r.id and v.user_id = auth.uid()) end,", state)
        self.assertIn("case when p_practice then 1 else 3 end", state)
        can = sql_function(MIG, "lounge_can")
        self.assertIn("select (s.phase = 'voting' and s.is_in and s.voters >= s.needed)", can)
        # read only, every member, once voting has closed; never the practice one
        self.assertIn("or (not p_write and not p_practice and s.phase = 'finished')", can)

    def test_a_music_league_round_has_no_lounge(self):
        state = sql_function(MIG, "lounge_state")
        self.assertIn("when not r.votes_on_site then 'closed'", state)

    def test_one_message_a_day_280_characters(self):
        post = sql_function(MIG, "lounge_post")
        self.assertIn("if char_length(body) > 280 then", post)
        self.assertIn("perform pg_advisory_xact_lock(", post)
        self.assertIn("if last_at is not null and last_at + public.lounge_gap(p_practice) > at then", post)
        # a removed message still counts: the check doesn't skip them
        self.assertNotIn("removed_at", post.split("select max(m.created_at) into last_at", 1)[1].split(";", 1)[0])
        self.assertIn("then interval '10 minutes' else interval '24 hours' end", sql_function(MIG, "lounge_gap"))
        self.assertIn("check (char_length(body) between 1 and 280)", MIG)

    def test_only_the_admin_removes_and_never_sees_who(self):
        remove = sql_function(MIG, "lounge_remove")
        self.assertIn("if not public.is_admin() then", remove)
        self.assertNotIn("returns", remove.split("as $$", 1)[1])

    def test_reactions_are_the_six(self):
        self.assertIn("check (reaction in ('fire', 'laugh', 'hundred', 'eyes', 'heart', 'grimace'))", MIG)
        self.assertIn("if not public.lounge_can(m.round_id, m.practice, true) then", sql_function(MIG, "lounge_react"))

    def test_the_rehearsal_counts_its_checks(self):
        self.assertEqual(len(re.findall(r"^  checks := checks \+ 1;", REHEARSAL, re.M)), 13)
        self.assertIn('"Rehearsal passed: 13 checks held. Nothing was kept."', REHEARSAL)


class ThePage(unittest.TestCase):
    def test_the_round_page_loads_it_and_has_its_section(self):
        html = (SITE / "round.html").read_text(encoding="utf-8")
        srcs = re.findall(r'<script src="([^"]+)"', html)
        self.assertLess(srcs.index("lounge.js"), srcs.index("app.js"))
        rounds = (SITE / "rounds.js").read_text(encoding="utf-8")
        site_page = js_body(rounds, "function renderSiteRoundPage(r, label) {")
        # under the results
        self.assertLess(site_page.index('id="rpVote"'), site_page.index('id="rpLounge"'))
        stats_page = js_body(rounds, "function renderRoundPage(d, roundId) {")
        self.assertLess(stats_page.index('id="rpTracks"'), stats_page.index('id="rpLounge"'))

    def test_only_a_round_voted_here_or_the_demo_gets_one(self):
        init = js_body((SITE / "app.js").read_text(encoding="utf-8"), "function initRound() {")
        self.assertIn('if (window.PFMLLounge && $("rpLounge") && (site.votes_on_site || site.practice)) window.PFMLLounge.render($("rpLounge"), site);', init)
        self.assertIn('if (site && site.votes_on_site && window.PFMLLounge && $("rpLounge")) window.PFMLLounge.render($("rpLounge"), site);', init)

    def test_the_page_asks_the_database(self):
        auth = (SITE / "auth.js").read_text(encoding="utf-8")
        for call in ('client.rpc("lounge_status", { p_round: roundId, p_practice: !!practice })',
                     'client.rpc("lounge_messages", { p_round: roundId, p_practice: !!practice })',
                     'client.rpc("lounge_post", { p_round: roundId, p_practice: !!practice, p_body: body })',
                     'client.rpc("lounge_react", { p_message: messageId, p_reaction: reaction, p_on: !!on })',
                     'client.rpc("lounge_remove", { p_message: messageId })'):
            self.assertIn(call, auth)

    def test_submitting_a_ballot_opens_the_door(self):
        voting = (SITE / "voting.js").read_text(encoding="utf-8")
        submit = js_body(voting, "function submit() {")
        self.assertIn('document.dispatchEvent(new CustomEvent("pfml:ballot-submitted"));', submit)
        self.assertIn('document.addEventListener("pfml:ballot-submitted", function () { refresh(); });', js_body(LOUNGE, "function render(host, r) {"))

    def test_live_while_open_quieter_at_the_door_still_once_closed(self):
        self.assertIn("var LIVE_MS = 6000;", LOUNGE)
        self.assertIn("var DOOR_MS = 30000;", LOUNGE)
        refresh = js_body(LOUNGE, "function refresh() {")
        self.assertIn('if (st && st.phase === "voting") state.timer = setTimeout(tick, st.open ? LIVE_MS : DOOR_MS);', refresh)
        self.assertIn('if (st.phase === "finished" && !state.messages.length) { hide(); return; }', refresh)

    def test_a_check_never_touches_what_the_reader_is_typing(self):
        room = js_body(LOUNGE, "function drawRoom() {")
        self.assertIn("if (shown !== state.drawn) {", room)
        self.assertIn("if (mode !== state.compose) {", room)
        self.assertNotIn("lgText", room)

    def test_the_box_or_the_wait(self):
        compose = js_body(LOUNGE, "function drawCompose(mode, next) {")
        self.assertIn('maxlength="\' + MAX + \'"', compose)
        self.assertIn('"Your next message can go in " + leftText(left) + ". Reactions are open any time."', compose)
        self.assertIn("var MAX = 280;", LOUNGE)

    def test_names_and_words_are_escaped(self):
        msg = js_body(LOUNGE, "function messageHtml(m) {")
        self.assertIn("esc(m.alias)", msg)
        self.assertIn("esc(m.body)", msg)

    def test_only_the_admin_sees_remove(self):
        msg = js_body(LOUNGE, "function messageHtml(m) {")
        self.assertIn('var admin = PFML.member && PFML.member.role === "admin";', msg)
        self.assertIn("(admin && open && !m.removed ? '<button type=\"button\" class=\"lg-remove\"", msg)


class TheDemo(unittest.TestCase):
    def test_the_demo_uses_the_practice_lounge_always(self):
        demo = (SITE / "round-demo.js").read_text(encoding="utf-8")
        self.assertIn('var LOUNGE = ["loungeStatus", "loungeMessages", "loungePost"];', demo)
        self.assertIn("args[0] = src.id;\n              args[1] = true;", demo)
        self.assertIn("round.practice = true;", demo)
        self.assertIn("state.practice = !!r.practice;", js_body(LOUNGE, "function render(host, r) {"))


if __name__ == "__main__":
    unittest.main()
