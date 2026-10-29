"""Spectators' podium points (chosen 2026-10-29; README, Spectators' podium
points): each point a Spectator gave a track that finished 1st, 2nd or 3rd
in its round earns 3, 2 or 1, places shared on a tie. The build scores it
from the export, which now names each round's Spectators; the round's
results and the season page show it. The SQL runs only in the user's
rehearsal (supabase/checks/2026-10-29_spectator_points_rehearsal.sql); the
pages were checked in a browser."""
import copy
import re
import unittest

from support import ROOT, build, make_season, quiet, sandbox
from test_build import TIE_ROUND
from test_reminders import js_body
from test_site_results import PLAYERS, SITE_ROUND, write_site
from test_submissions import function, read, schema

SITE = ROOT / "site"
MIG = read(ROOT / "supabase" / "migrations" / "2026-10-29_spectator_points.sql")
REHEARSAL = read(ROOT / "supabase" / "checks" / "2026-10-29_spectator_points_rehearsal.sql")


def spectator_round():
    """SITE_ROUND with two Spectators: Zed votes 2 on Cloud Song and 3 on
    Spotify Song; Yan doesn't vote. Cloud Song then has 8 (1st), Spotify
    Song and Video Song 3 each (both 2nd), Lonely Video 0 (its submitter
    didn't vote). Zed earns 2 x 3 + 3 x 2 = 12."""
    r = copy.deepcopy(SITE_ROUND)
    r["spectators"] = ["p9", "p8"]
    r["votes"] += [{"submission": "s3", "voter": "p9", "points": 2, "comment": "", "cast_at": "2025-02-05T00:00:00Z"},
                   {"submission": "s1", "voter": "p9", "points": 3, "comment": "", "cast_at": "2025-02-05T00:00:00Z"}]
    return r


class TheBuild(unittest.TestCase):
    def build(self, rounds):
        with sandbox() as root, quiet():
            folder = root / "data" / "season1"
            make_season(folder, [TIE_ROUND])
            write_site(folder, rounds, dict(PLAYERS, p9="Zed", p8="Yan"))
            data, _ = build.build_season(folder, "season1", "Season 1")
        return data

    def test_points_for_the_podium_with_places_shared(self):
        data = self.build([spectator_round()])
        site = next(r for r in data["rounds"] if r["id"] == "site-r1")
        places = {s["title"]: s["place"] for s in site["songs"]}
        self.assertEqual((places["Cloud Song"], places["Spotify Song"], places["Video Song"]), (1, 2, 2))
        self.assertEqual(site["spectators"], [{"id": "p9", "name": "Zed", "score": 12}, {"id": "p8", "name": "Yan", "score": 0}])

    def test_the_season_table(self):
        data = self.build([spectator_round()])
        self.assertEqual(data["spectatorStandings"], [
            {"id": "p9", "name": "Zed", "points": 12, "rounds": 1, "rank": 1, "tied": False},
            {"id": "p8", "name": "Yan", "points": 0, "rounds": 1, "rank": 2, "tied": False}])
        # never in the DJs' standings
        self.assertFalse({"p8", "p9"} & {p["id"] for p in data["standings"]})

    def test_equal_points_share_a_place(self):
        r = copy.deepcopy(SITE_ROUND)
        r["spectators"] = ["p8", "p9"]
        table = self.build([r])["spectatorStandings"]
        self.assertEqual([(t["id"], t["rank"], t["tied"]) for t in table], [("p8", 1, True), ("p9", 1, True)])

    def test_a_season_without_spectators_has_no_table(self):
        data = self.build([SITE_ROUND])
        self.assertNotIn("spectatorStandings", data)
        self.assertTrue(all("spectators" not in r for r in data["rounds"]))

    def test_the_rule(self):
        self.assertEqual(build.PODIUM_POINTS, {1: 3, 2: 2, 3: 1})
        songs = [{"place": 1, "votes": [["a", 5], ["b", 1]]}, {"place": 3, "votes": [["a", -1], ["b", 4]]},
                 {"place": 4, "votes": [["a", 2]]}]
        self.assertEqual(build.podium_points(songs, [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]),
                         [{"id": "a", "name": "A", "score": 15}, {"id": "b", "name": "B", "score": 7}])


class Publishing(unittest.TestCase):
    def test_a_spectator_who_didnt_vote_keeps_their_name(self):
        from test_site_results import Publishing as P
        saved, _ = P.fetch(None, {"rounds": [spectator_round()], "players": dict(PLAYERS, p9="Zed", p8="Yan", p7="Not In It")})
        players = saved["season1"]["players"]
        self.assertEqual(players.get("p8"), "Yan")
        self.assertNotIn("p7", players)


class TheDatabase(unittest.TestCase):
    def test_schema_has_the_migration(self):
        self.assertIn(MIG[MIG.index("create or replace function public.site_rounds_export()"):], schema())

    def test_the_export_names_each_rounds_spectators(self):
        ex = function(schema(), "site_rounds_export")
        self.assertIn("'spectators', coalesce((\n          select jsonb_agg(p.competitor_id order by p.competitor_id)", ex)
        self.assertIn("and public.site_round_role(r.id, p.competitor_id) = 'spectator'), '[]'::jsonb),", ex)
        # still finished rounds only
        self.assertIn("where r.votes_on_site and public.site_round_phase(r.id) = 'finished'", ex)

    def test_the_rehearsal_counts_its_checks(self):
        self.assertEqual(len(re.findall(r"^  checks := checks \+ 1;", REHEARSAL, re.M)), 3)
        self.assertIn('"Rehearsal passed: 3 checks held. Nothing was kept."', REHEARSAL)


class ThePages(unittest.TestCase):
    def test_the_page_and_the_build_score_alike(self):
        account = read(SITE / "account.js")
        self.assertIn("var PODIUM_POINTS = { 1: 3, 2: 2, 3: 1 };", account)
        self.assertIn("if (v.voter_id === id && v.points > 0) score += v.points * (PODIUM_POINTS[places[v.submission_id]] || 0);",
                      js_body(account, "function podiumScores(places, votes, spectatorIds) {"))

    def test_the_results_show_them_by_the_lists_places(self):
        voting = read(SITE / "voting.js")
        self.assertIn('}).join("") + "</ol>" + podium(results, votes, names, spectators || []);',
                      js_body(voting, "function renderResults(r, results, votes, names, spectators) {"))
        podium = js_body(voting, "function podium(results, votes, names, spectators) {")
        self.assertIn("places[x.submission_id] = 1 + results.filter(function (o) { return o.points > x.points; }).length;", podium)

    def test_the_stats_round_page_and_the_season_page(self):
        self.assertIn("(r.spectators && r.spectators.length ? '<section class=\"shell block\">' + PFML.podiumHtml(r.spectators)",
                      js_body(read(SITE / "rounds.js"), "function renderRoundPage(d, roundId) {"))
        app = read(SITE / "app.js")
        self.assertIn("renderSpectatorStandings(d);", js_body(app, "function initSeason(key) {"))
        table = js_body(app, "function renderSpectatorStandings(d) {")
        self.assertIn("var list = d.spectatorStandings || [];", table)
        self.assertIn("after.parentNode.insertBefore(section, after.nextSibling);", table)


if __name__ == "__main__":
    unittest.main()
