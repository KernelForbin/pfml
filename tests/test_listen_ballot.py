"""Voting in the round's own list (asked 2026-10-26): on the round page,
each track plays, takes points and takes a comment in the same row, and
Shuffle and Original order move the ballot with the play order. The Submit
page, Home's banner and the voting reminders send people there. The
browser code isn't run here (no Node); README, Voting on the site, says how
it was checked in a browser (the round demo, /round?demo=1)."""
import unittest

from support import ROOT
from test_reminders import js_body

SITE = ROOT / "site"


def read(path):
    return path.read_text(encoding="utf-8")


LISTEN = read(SITE / "listen.js")
VOTING = read(SITE / "voting.js")


class TheList(unittest.TestCase):
    def test_a_round_voting_here_gets_its_ballot_in_the_list(self):
        render = js_body(LISTEN, "function render(host, r) {")
        self.assertIn('var voting = !!(window.PFMLVoting && window.PFMLVoting.on(r) && phase === "voting");', render)
        # the plain list first, then redrawn with the ballot once it loads
        order = [render.index(s) for s in ("drawTracks(list);\n      if (!voting) return;",
                                           "window.PFMLVoting.ballot(r, rows, { head: $(\"lnVoteHead\"), list: $(\"lnTracks\"), bar: $(\"lnVoteBar\"),",
                                           "list.ballot = ballot;\n        drawTracks(list);")]
        self.assertEqual(order, sorted(order))
        # the rules above the list, the points left and Save below it
        self.assertLess(render.index('id="lnVoteHead"'), render.index('id="lnTracks"'))
        self.assertLess(render.index('id="lnTracks"'), render.index('id="lnVoteBar"'))

    def test_each_row_plays_takes_points_and_takes_a_comment(self):
        draw = js_body(LISTEN, "function drawTracks(list) {")
        row = draw[draw.index("return '<li class=\"sub-track'"):draw.index('}).join("");')]
        order = [row.index(s) for s in ('class="sub-track-btn"', "(b ? b.controls(s) : \"\")", "gapNote(s)",
                                        "'<p class=\"sub-track-note\"><span class=\"sub-note-from\">From the submitter</span>'", "(b ? b.comment(s) : \"\")")]
        self.assertEqual(order, sorted(order))
        self.assertIn("'\" data-id=\"' + esc(s.id) + '\">'", row)
        # after every draw, Shuffle and Original order included
        self.assertIn('}).join("");\n    if (list.ballot) list.ballot.refresh();', draw)
        self.assertIn("drawTracks(list);", js_body(LISTEN, "function reorder(list, order) {"))

    def test_the_ballot_keeps_to_its_own_buttons(self):
        # the play button has no data-act, the ballot's buttons have one
        self.assertIn('var b = ev.target.closest("button[data-act]");', js_body(VOTING, "function onBallotClick(ev) {"))
        self.assertNotIn("data-act", js_body(LISTEN, "function drawTracks(list) {"))
        self.assertIn('var b = ev.target.closest(".sub-track-btn");', js_body(LISTEN, "function render(host, r) {"))


class TheBallot(unittest.TestCase):
    def test_it_lives_in_the_list_and_the_rows(self):
        ballot = js_body(VOTING, "function ballot(r, rows, parts) {")
        for line in ('parts.list.addEventListener("click", onBallotClick);', 'parts.list.addEventListener("input", onBallotInput);',
                     "return { controls: controls, comment: commentHtml, refresh: refreshBallot };"):
            self.assertIn(line, ballot)
        self.assertIn('state.parts.list.querySelectorAll(".sub-track[data-id]").forEach(function (li) {',
                      js_body(VOTING, "function refreshBallot() {"))
        self.assertIn("ballot: ballot", VOTING)

    def test_only_a_player_with_a_track_gets_one(self):
        ballot = js_body(VOTING, "function ballot(r, rows, parts) {")
        self.assertLess(ballot.index("if (!mine.length) {"), ballot.index("api().myBallot(r.id)"))
        self.assertIn("Only players with a track in this round vote.", ballot)
        self.assertIn("return null;", ballot)

    def test_points_and_comments_survive_a_reshuffle(self):
        # keyed by track, never by place in the list
        self.assertIn("(state.points[s.id] || 0)", js_body(VOTING, "function controls(s) {"))
        comment = js_body(VOTING, "function commentHtml(s) {")
        self.assertIn('esc(state.comments[s.id] || "") + "</textarea></div>";', comment)
        # and listen.js redraws it when another device's draft comes in
        self.assertIn("redraw: function () { drawTracks(list); }", js_body(LISTEN, "function render(host, r) {"))

    def test_the_comment_box_is_open_from_the_start(self):
        # the user's call, 2026-10-27: no "Add a comment" to press first
        comment = js_body(VOTING, "function commentHtml(s) {")
        self.assertNotIn("hidden", comment)
        self.assertNotIn("data-act", comment)
        self.assertIn('placeholder="Add a comment (optional)"', comment)
        self.assertNotIn("vt-comment-btn", VOTING)

    def test_the_save_bar_stays_in_view_with_its_message(self):
        # the points left, Save and Submit, then the status on its own row
        # (two rows fit a phone; one squeezed the text to a sliver)
        ballot = js_body(VOTING, "function ballot(r, rows, parts) {")
        order = [ballot.index(s) for s in ('id="vtLeft"', 'id="vtSave"', 'id="vtSubmit"', 'id="vtMsg"')]
        self.assertEqual(order, sorted(order))
        css = read(SITE / "style.css")
        self.assertIn(".ln-vote-bar { position: sticky; bottom: 10px;", css)
        self.assertIn(".ln-vote-bar .vt-bar > .sub-msg { flex: 1 1 100%;", css)

    def test_no_ballot_left_anywhere_else(self):
        for gone in ("function renderBallot(", "function ballotRow(", "vt-list", "vt-row"):
            with self.subTest(gone):
                self.assertNotIn(gone, VOTING)
                self.assertNotIn(gone, read(SITE / "style.css"))


class TheResults(unittest.TestCase):
    def test_under_the_list_once_voting_closes_until_the_stats_have_it(self):
        init = js_body(read(SITE / "app.js"), "function initRound() {")
        self.assertIn('if (i < 0 && window.PFMLVoting && $("rpVote")) window.PFMLVoting.render(site, $("rpVote"));', init)
        self.assertLess(init.index('window.PFMLListen.render($("rpListen"), site);'), init.index("window.PFMLVoting.render("))
        page = js_body(read(SITE / "rounds.js"), "function renderSiteRoundPage(r, label) {")
        self.assertLess(page.index('id="rpListen"'), page.index("'<section class=\"shell block\" id=\"rpVote\" hidden></section>'"))


class TheWayThere(unittest.TestCase):
    def test_the_submit_page_links_to_the_round_page(self):
        submit = read(SITE / "submit.js")
        self.assertNotIn("voting().render", submit)
        self.assertIn('$("subListenLink").textContent = phase === "voting" ? "Listen and vote"', submit)
        self.assertIn('$("subListenLink").href = "round?site=" + encodeURIComponent(r.id);', submit)

    def test_home_s_voting_banner_goes_to_the_round_page(self):
        banner = js_body(read(SITE / "app.js"), "function votingBanner(rounds) {")
        self.assertIn("'<a class=\"sub-banner-link\" href=\"round?site=' + encodeURIComponent(r.id) + '\">", banner)
        self.assertNotIn('href="submit"', banner)

    def test_reminders_open_the_round_page_but_a_new_round_the_submit_page(self):
        fn = read(ROOT / "supabase" / "functions" / "send-reminders" / "index.ts")
        self.assertIn('const page = c.kind === "round_open" ? `${SITE}submit` : `${SITE}round?site=${encodeURIComponent(c.round_id)}`;', fn)
        self.assertIn("const at = { url: page, tag: `${c.round_id}:${c.kind}` };", fn)


if __name__ == "__main__":
    unittest.main()
