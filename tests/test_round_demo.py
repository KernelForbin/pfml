"""The round demo (/round?demo=1, site/round-demo.js; asked 2026-10-26):
the real round page with the newest closed round's real tracks (Round 7),
read from the database at runtime, as if it voted here: the listening
section and the ballot. It replaced the listening demo's stand-in tracks.
No vote, and nothing else about the stand-in round, reaches the database.
The browser code isn't run here (no Node); README, Round demo, says how it
was checked in a browser."""
import re
import unittest

from support import ROOT
from test_reminders import js_body

SITE = ROOT / "site"
DEMO = (SITE / "round-demo.js").read_text(encoding="utf-8")


def demo_block():
    return DEMO.split("var demo = {", 1)[1].split("\n    };", 1)[0]


class ThePage(unittest.TestCase):
    def test_only_the_round_page_loads_it_after_sign_in_and_before_the_page(self):
        html = (SITE / "round.html").read_text(encoding="utf-8")
        order = [html.index(f'<script src="{s}"></script>')
                 for s in ("auth.js", "account.js", "round-demo.js", "voting.js", "player.js", "listen.js", "rounds.js", "app.js")]
        self.assertEqual(order, sorted(order))
        for page in SITE.glob("*.html"):
            if page.name != "round.html":
                with self.subTest(page.name):
                    self.assertNotIn("round-demo.js", page.read_text(encoding="utf-8"))
        self.assertFalse((SITE / "listen-demo.js").exists())

    def test_the_admin_alone_has_a_link_to_it_in_the_initials_menu(self):
        # the installed app has no address bar (asked 2026-10-26)
        account = (SITE / "account.js").read_text(encoding="utf-8")
        self.assertIn("'<a class=\"acct-item\" href=\"round?demo=1\" id=\"acctDemo\" hidden>Round demo</a>' +", account)
        self.assertIn('$("acctDemo").hidden = member.role !== "admin";', account)
        css = (SITE / "style.css").read_text(encoding="utf-8")
        self.assertIn(".acct-item[hidden] { display: none; }", css)

    def test_it_does_nothing_without_demo_1(self):
        start = DEMO.index('"use strict";')
        self.assertTrue(DEMO[start:].split("\n", 2)[2].lstrip().startswith(
            "if (!/(^|[?&])demo=1(&|$)/.test(location.search)) return;"))

    def test_it_waits_for_sign_in_and_names_its_round_first(self):
        self.assertIn("PFML.ready.then(function (member) {\n    var real = PFML.api;", DEMO)
        self.assertLess(DEMO.index("window.PFMLDemo = { round: DEMO_ROUND };"), DEMO.index("PFML.ready.then("))
        app = (SITE / "app.js").read_text(encoding="utf-8")
        self.assertIn('var siteId = params.get("site") || (window.PFMLDemo && window.PFMLDemo.round) || "";', app)


class TheBallot(unittest.TestCase):
    def test_the_demo_alone_gets_a_ballot_under_the_listening(self):
        init = js_body((SITE / "app.js").read_text(encoding="utf-8"), "function initRound() {")
        self.assertIn('if (window.PFMLDemo && window.PFMLVoting && $("rpVote")) {', init)
        self.assertIn('window.PFMLVoting.render(site, mine || [], $("rpVote"));', init)
        self.assertLess(init.index('window.PFMLListen.render($("rpListen"), site);'), init.index("window.PFMLVoting.render("))
        page = js_body((SITE / "rounds.js").read_text(encoding="utf-8"), "function renderSiteRoundPage(r, label) {")
        self.assertLess(page.index('id="rpListen"'), page.index("'<section class=\"shell block\" id=\"rpVote\" hidden></section>'"))

    def test_voting_draws_where_it_is_told_the_submit_page_by_default(self):
        voting = (SITE / "voting.js").read_text(encoding="utf-8")
        self.assertIn('host = state.host = host || $("subVote");', js_body(voting, "function render(r, mine, host) {"))
        self.assertNotIn('$("subVote")', voting.replace('host = state.host = host || $("subVote");', ""))


class TheRound(unittest.TestCase):
    def test_the_newest_closed_round_with_its_playlists_voting_for_two_more_days(self):
        rounds = demo_block().split("siteRounds: function () {", 1)[1].split("castBallot:", 1)[0]
        self.assertIn('return (p === "closed" || p === "finished") && (x.spotify_playlist || x.youtube_playlist);', rounds)
        self.assertIn("return Date.parse(b.closed_at || b.closes_at) - Date.parse(a.closed_at || a.closes_at);", rounds)
        for line in ("round.id = DEMO_ROUND;", "round.votes_on_site = true;",
                     "round.voting_closes_at = new Date(Date.now() + 2 * 864e5).toISOString();",
                     "round.voting_closed_at = null;", 'round.name = "Demo: " + src.name;',
                     "Nothing here is saved or counted."):
            self.assertIn(line, rounds)

    def test_no_league_data_in_the_file(self):
        # the tracks come from the database at runtime: the repo is public
        self.assertNotRegex(DEMO, r"[A-Za-z0-9]{22}")
        self.assertEqual(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", DEMO),
                         ["00000000-0000-4000-8000-00000000de30"])
        self.assertNotIn("title:", DEMO)


class NothingReachesTheDatabase(unittest.TestCase):
    def test_the_ballot_and_who_voted_stay_on_the_page(self):
        demo = demo_block()
        self.assertEqual(re.findall(r"^      (\w+): function", demo, re.M),
                         ["siteRounds", "castBallot", "myBallot", "roundVoters"])
        # the one call to the real database is the round list
        self.assertEqual(re.findall(r"real\.(\w+)", demo), ["siteRounds"])

    def test_only_the_reads_reach_the_database_and_with_the_real_round(self):
        self.assertIn('var READS = ["roundSubmissions", "mySubmissions", "roundSubmitters"];', DEMO)
        guard = DEMO.split("PFML.api = new Proxy(real, {", 1)[1]
        order = [guard.index(s) for s in ("if (args[i] !== DEMO_ROUND) continue;",
                                          "if (READS.indexOf(name) === -1 || !src) return Promise.resolve([]);",
                                          "args[i] = src.id;", "return fn.apply(target, args);")]
        self.assertEqual(order, sorted(order))


if __name__ == "__main__":
    unittest.main()
