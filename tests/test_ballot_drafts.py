"""Ballot drafts (asked 2026-10-27): points and comments save on their own
as a member gives them, to their account, so they follow them between
devices and survive leaving the page; Save keeps their place, Submit (only
with every point given) is what counts. The database side runs only in the
user's rehearsal (supabase/checks/2026-10-27_ballot_drafts_rehearsal.sql)
and tests/test_live_ballot_drafts.py; the page side was checked in a
browser (README, Voting on the site, Drafts)."""
import re
import unittest

from support import ROOT
from test_reminders import js_body

SITE = ROOT / "site"
SQL = (ROOT / "supabase" / "schema.sql").read_text(encoding="utf-8")
MIG = (ROOT / "supabase" / "migrations" / "2026-10-27_ballot_drafts.sql").read_text(encoding="utf-8")
REHEARSAL = (ROOT / "supabase" / "checks" / "2026-10-27_ballot_drafts_rehearsal.sql").read_text(encoding="utf-8")
VOTING = (SITE / "voting.js").read_text(encoding="utf-8")
AUTH = (SITE / "auth.js").read_text(encoding="utf-8")


def sql_function(text, name):
    start = text.index(f"create or replace function public.{name}(")
    return text[start:text.index("$$;", start)]


class TheDatabase(unittest.TestCase):
    def test_schema_has_the_migration(self):
        block = MIG[MIG.index("create table if not exists public.site_ballot_drafts"):]
        self.assertIn(block, SQL)

    def test_only_the_functions_reach_the_table(self):
        self.assertIn("alter table public.site_ballot_drafts enable row level security;", MIG)
        self.assertIn("revoke all on table public.site_ballot_drafts from anon, authenticated;", MIG)
        self.assertNotRegex(MIG, r"grant [^;]* on table public\.site_ballot_drafts")
        self.assertNotIn("create policy", MIG)
        for name, args in (("save_ballot_draft", "uuid, jsonb"), ("my_ballot_draft", "uuid")):
            with self.subTest(name):
                self.assertIn(f"revoke all on function public.{name}({args}) from public, anon;", MIG)
                self.assertIn(f"grant execute on function public.{name}({args}) to authenticated;", MIG)
        self.assertIn("revoke all on function public.draft_problem(int, int, int, int, int[], boolean[]) from public, anon, authenticated;", MIG)

    def test_a_draft_saves_only_while_voting_and_only_for_a_player_with_a_track(self):
        save = sql_function(MIG, "save_ballot_draft")
        self.assertIn("if public.site_round_phase(p_round) is distinct from 'voting' then", save)
        self.assertIn("where o.round_id = p_round and o.user_id = uid;", save)
        self.assertIn("raise exception 'Only players with a track in this round can vote.';", save)
        self.assertIn("on conflict (round_id, user_id) do update set ballot = excluded.ballot, saved_at = excluded.saved_at;", save)
        # the same rules as a ballot, but the total may be short
        self.assertIn("problem := public.draft_problem(r.point_budget, r.max_per_track, r.downvotes, r.max_down_per_track, pts,", save)
        self.assertNotIn("site_votes", save)

    def test_draft_rules_allow_a_short_total_never_a_long_one(self):
        rules = sql_function(MIG, "draft_problem")
        self.assertIn("where p > 0), 0) > p_budget", rules)
        self.assertNotIn("<> p_budget", rules)
        self.assertIn("where own and p <> 0)", rules)

    def test_a_member_reads_only_their_own_while_voting(self):
        mine = sql_function(MIG, "my_ballot_draft")
        self.assertIn("where d.round_id = p_round and d.user_id = auth.uid() and public.is_member()", mine)
        self.assertIn("and public.site_round_phase(p_round) = 'voting';", mine)

    def test_the_rehearsal_counts_its_checks(self):
        self.assertEqual(len(re.findall(r"^  checks := checks \+ 1;", REHEARSAL, re.M)), 11)
        self.assertIn('"Rehearsal passed: 11 checks held. Nothing was kept."', REHEARSAL)
        self.assertTrue(REHEARSAL.rstrip().endswith("raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;\nend $$;"))


class ThePage(unittest.TestCase):
    def test_the_page_calls_them(self):
        self.assertIn('client.rpc("save_ballot_draft", { p_round: roundId, p_ballot: ballot })', AUTH)
        self.assertIn('client.rpc("my_ballot_draft", { p_round: roundId })', AUTH)

    def test_every_change_is_kept_here_at_once_and_saved_soon(self):
        changed = js_body(VOTING, "function changed() {")
        self.assertLess(changed.index("writeLocal();"), changed.index("schedule();"))
        self.assertIn("var DRAFT_MS = 800, DRAFT_MAX_MS = 4000, RETRY_MS = 10000,", VOTING)
        schedule = js_body(VOTING, "function schedule() {")
        self.assertIn("Math.min(DRAFT_MS, state.firstChange + DRAFT_MAX_MS - now)", schedule)
        for fn in ("function onBallotClick(ev) {", "function onBallotInput(ev) {"):
            self.assertIn("changed();", js_body(VOTING, fn))

    def test_one_save_at_a_time_and_none_when_nothing_changed(self):
        save = js_body(VOTING, "function saveDraft() {")
        self.assertIn("if (state.saving) { state.again = true; return state.saving; }", save)
        self.assertIn("if (text === state.savedJson) { status(); return Promise.resolve(); }", save)
        self.assertIn("if (state.again) { state.again = false; return saveDraft(); }", save)
        # this browser's copy goes once the database has it all
        self.assertIn("if (json() === text) clearLocal();", save)
        # a refusal won't change by waiting; anything else is tried again
        self.assertIn('if (!(err && err.code === "P0001")) state.timer = setTimeout(saveDraft, RETRY_MS);', save)

    def test_leaving_saves_and_coming_back_syncs(self):
        ballot = js_body(VOTING, "function ballot(r, rows, parts) {")
        self.assertIn('if (document.visibilityState === "hidden") flush();\n          else sync();', ballot)
        self.assertIn('window.addEventListener("pagehide", flush);', ballot)
        sync = js_body(VOTING, "function sync() {")
        self.assertTrue(sync.lstrip().startswith("if (state.saving || state.timer || json() !== state.savedJson) return;"))
        self.assertIn("var newer = draft && (Date.parse(draft.saved_at) || 0) > state.savedAt;", sync)

    def test_an_open_page_checks_in_too(self):
        # found 2026-10-27: neither visibility nor pageshow fires for a page
        # left open on screen, or a window only moved behind another
        ballot = js_body(VOTING, "function ballot(r, rows, parts) {")
        self.assertIn('window.addEventListener("focus", sync);', ballot)
        self.assertIn('setInterval(function () { if (document.visibilityState === "visible") sync(); }, SYNC_MS);', ballot)
        self.assertIn("SYNC_MS = 15000;", VOTING)

    def test_a_check_redraws_only_for_something_new_and_keeps_the_cursor(self):
        sync = js_body(VOTING, "function sync() {")
        self.assertIn("if (json() !== before) redrawKeepingFocus();", sync)
        self.assertNotIn("state.parts.redraw();", sync)
        keep = js_body(VOTING, "function redrawKeepingFocus() {")
        self.assertLess(keep.index("var id = li && li.getAttribute(\"data-id\");"), keep.index("state.parts.redraw();"))
        self.assertIn("if (box) { box.focus(); box.setSelectionRange(box.value.length, box.value.length); }", keep)

    def test_it_opens_on_the_draft_or_this_browser_s_newer_copy(self):
        ballot = js_body(VOTING, "function ballot(r, rows, parts) {")
        order = [ballot.index(s) for s in ("apply(submitted);", "if (draft) apply(draft.ballot || []);",
                                           "state.savedJson = json();",
                                           "if (local && local.at > state.savedAt) apply(local.ballot || []);")]
        self.assertEqual(order, sorted(order))
        self.assertIn("else if (local) clearLocal();", ballot)

    def test_save_and_submit(self):
        ballot = js_body(VOTING, "function ballot(r, rows, parts) {")
        self.assertIn('id="vtSave">Save</button>', ballot)
        self.assertIn('id="vtSubmit">Submit</button>', ballot)
        self.assertIn('$("vtSave").addEventListener("click", function () { saveDraft(); });', ballot)
        self.assertIn('$("vtSubmit").addEventListener("click", submit);', ballot)
        # Submit only with every point given, and something new to submit
        refresh = js_body(VOTING, "function refreshBallot() {")
        self.assertIn('$("vtSubmit").disabled = left !== 0 || downLeft < 0 || unchanged;', refresh)
        submit = js_body(VOTING, "function submit() {")
        self.assertLess(submit.index("api().castBallot(r.id, body)"), submit.index("return saveDraft();"))

    def test_the_status_says_whether_it_counts_yet(self):
        status = js_body(VOTING, "function status(text) {")
        for line in ('text = "Saved. It counts once you Submit, with every point given.";',
                     'text = "Submitted. You can change it until voting closes.";',
                     'text = "Saved. Submit again for these changes to count.";'):
            self.assertIn(line, status)

    def test_this_browser_s_copy_is_per_round_and_reader(self):
        self.assertIn('return "pfml.ballot." + state.round.id + "." + ((PFML.member && PFML.member.competitorId) || "");',
                      js_body(VOTING, "function localKey() {"))


if __name__ == "__main__":
    unittest.main()
