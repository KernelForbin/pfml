"""The group toggles on the Performance over time chart: Front of the pack,
Back of the pack, Biggest rises and falls, Most volatile, Steadiest, Been #1
(build.trend_groups), and You (the page). Made-up rounds only."""
import re
import unittest

from support import ROOT, build, make_season, quiet, sandbox

APP = (ROOT / "site" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "site" / "style.css").read_text(encoding="utf-8")
FIELD = [{"id": i} for i in "abcdef"]


def rounds(*points):
    """Each argument is one round: {player: points}."""
    return [{"songs": [{"submitterId": p, "points": v} for p, v in r.items()]} for r in points]


def groups(rs, field=FIELD):
    return {g["key"]: [(p["id"], p["value"]) for p in g["players"]] for g in build.trend_groups(rs, field)}


def js_body(signature):
    return APP.split(signature, 1)[1].split("\n  }\n", 1)[0]


class Places(unittest.TestCase):
    def test_a_tie_shares_a_place_and_the_next_skips(self):
        places = build.standing_after_each_round(rounds({"a": 5, "b": 5, "c": 3}), ["a", "b", "c"])
        self.assertEqual(places, {"a": [1], "b": [1], "c": [3]})

    def test_a_daily_double_counts_as_on_the_chart(self):
        rs = rounds({"a": 5, "b": 6})
        rs[0]["songs"][0]["dailyDouble"] = {"bonus": 5}
        self.assertEqual(build.standing_after_each_round(rs, ["a", "b"]), {"a": [1], "b": [2]})

    def test_a_player_outside_the_standings_is_left_out(self):
        self.assertEqual(build.standing_after_each_round(rounds({"a": 1, "x": 9}), ["a"]), {"a": [1]})

    def test_more_songs_from_one_player_add_up(self):
        rs = [{"songs": [{"submitterId": "a", "points": 3}, {"submitterId": "a", "points": 3},
                         {"submitterId": "b", "points": 5}]}]
        self.assertEqual(build.standing_after_each_round(rs, ["a", "b"]), {"a": [1], "b": [2]})


class Groups(unittest.TestCase):
    def test_nothing_before_round_two(self):
        self.assertEqual(build.trend_groups(rounds({"a": 5, "b": 1}), FIELD), [])
        self.assertEqual(build.trend_groups([], FIELD), [])

    def test_front_and_back_of_the_pack_with_ties(self):
        g = groups(rounds({"a": 1, "b": 1, "c": 1, "d": 1, "e": 1, "f": 1},
                          {"a": 9, "b": 8, "c": 7, "d": 7, "e": 2, "f": 1}))
        self.assertEqual(g["front"], [("a", 1), ("b", 2), ("c", 3), ("d", 3)])
        self.assertEqual(g["back"], [("f", 6), ("e", 5), ("c", 3), ("d", 3)])

    def test_rises_and_falls_count_from_round_one(self):
        g = groups(rounds({"a": 6, "b": 5, "c": 4, "d": 3, "e": 2, "f": 1},
                          {"f": 20, "e": 18, "a": 0}))
        # after round 1: a1 b2 c3 d4 e5 f6; after round 2: f1 e2 a3 b4 c5 d6
        self.assertEqual(g["rises"], [("f", 5), ("e", 3)])
        self.assertEqual(g["falls"], [("a", 2), ("b", 2), ("c", 2), ("d", 2)])

    def test_nobody_moved_means_no_rises_or_falls(self):
        g = groups(rounds({"a": 6, "b": 5, "c": 4, "d": 3, "e": 2, "f": 1},
                          {"a": 6, "b": 5, "c": 4, "d": 3, "e": 2, "f": 1}))
        self.assertNotIn("rises", g)
        self.assertNotIn("falls", g)

    def test_players_who_never_moved_are_neither_risers_nor_volatile(self):
        # only e and f swap places; nobody else moves all season
        g = groups(rounds({"a": 12, "b": 10, "c": 8, "d": 6, "e": 4, "f": 2}, {"f": 3}, {"a": 0}))
        self.assertEqual(g["rises"], [("f", 1)])
        self.assertEqual(g["falls"], [("e", 1)])
        self.assertEqual(g["volatile"], [("e", 0.5), ("f", 0.5)])

    def test_volatile_and_steady_from_round_three(self):
        two = rounds({"a": 6, "b": 5, "c": 4, "d": 3, "e": 2, "f": 1}, {"f": 20})
        self.assertNotIn("volatile", groups(two))
        self.assertNotIn("steady", groups(two))
        g = groups(two + rounds({"a": 30, "e": 4, "b": 1}))
        # places a 1,2,1  b 2,3,3  c 3,4,5  d 4,5,6  e 5,6,3  f 6,1,2
        self.assertEqual(g["volatile"], [("f", 3.0), ("e", 2.0), ("a", 1.0), ("c", 1.0), ("d", 1.0)])
        self.assertEqual(g["steady"], [("b", 0.5), ("a", 1.0), ("c", 1.0), ("d", 1.0)])

    def test_moves_a_round_are_to_one_decimal(self):
        g = groups(rounds({"a": 6, "b": 5, "c": 4, "d": 3, "e": 2, "f": 1}, {"f": 20}, {"a": 30, "e": 4},
                          {"b": 40}))
        values = [v for _, v in g["volatile"] + g["steady"]]
        self.assertTrue(values)
        self.assertTrue(all(v == round(v, 1) for v in values))
        self.assertIn(0.7, values)  # 2 places over 3 moves, not 0.6666...

    def test_been_number_one_counts_the_rounds(self):
        g = groups(rounds({"a": 5, "b": 1}, {"b": 10}, {"c": 1}))
        self.assertEqual(g["leaders"], [("b", 2), ("a", 1)])

    def test_a_group_of_the_whole_field_is_left_out(self):
        g = groups(rounds({"a": 1, "b": 1, "c": 1, "d": 1, "e": 1, "f": 1},
                          {"a": 1, "b": 1, "c": 1, "d": 1, "e": 1, "f": 1}))
        # everyone shares #1 all season: front, back and Been #1 would be everyone
        self.assertEqual(g, {})

    def test_the_season_file_carries_them(self):
        r = [{"id": f"r{n}", "name": f"Round {n}", "created": f"2026-01-0{n}T00:00:00Z",
              "subs": [(f"t{n}a", "p1"), (f"t{n}b", "p2"), (f"t{n}c", "p3"), (f"t{n}d", "p4")],
              "votes": [("p1", f"t{n}b", 3 + n), ("p2", f"t{n}c", 2), ("p3", f"t{n}a", 1), ("p4", f"t{n}a", 1)]}
             for n in (1, 2, 3)]
        with sandbox() as root, quiet():
            data, _ = build.build_season(make_season(root / "data" / "season1", r), "season1", "Season 1")
        self.assertEqual(data["trendGroups"], build.trend_groups(data["rounds"], data["standings"]))
        self.assertIn("front", [g["key"] for g in data["trendGroups"]])


class ThePage(unittest.TestCase):
    def test_the_page_knows_every_group_the_build_makes(self):
        keys = re.findall(r'\["(\w+)", "[^"]+", "[^"]+",', APP.split("var TREND_GROUPS = [", 1)[1].split("];", 1)[0])
        source = (ROOT / "scripts" / "build.py").read_text(encoding="utf-8")
        built = re.findall(r'\(\s*"(\w+)",', source.split("def trend_groups(", 1)[1].split("\ndef ", 1)[0])
        self.assertEqual(keys, ["you"] + built)

    def test_the_groups_come_from_the_season_file_plus_you(self):
        body = js_body("function trendGroupList(d) {")
        self.assertIn("(d.trendGroups || []).forEach", body)
        self.assertIn("if (d.standings.some(function (p) { return p.id === me; })) found.you = [{ id: me }];", body)

    def test_groups_add_up_and_none_on_shows_everyone(self):
        body = js_body("function toggleTrendGroup(key, groups) {")
        self.assertIn("if (ids.indexOf(p.id) === -1) ids.push(p.id);", body)
        self.assertIn("trendSelected = trendGroupsOn.length ? ids : seasonData.standings.map(", body)

    def test_picking_by_hand_turns_the_groups_off(self):
        self.assertIn("trendGroupsOn = [];", js_body("function toggleTrend(id) {"))
        self.assertIn("trendGroupsOn = [];", js_body("function rerenderFiltered() {"))
        controls = APP.split('var controls = el("div", "trend-controls");', 1)[1].split("legend.appendChild(controls);", 1)[0]
        self.assertEqual(controls.count("trendGroupsOn = [];"), 2)

    def test_the_toggles_are_buttons_that_say_whether_they_are_on(self):
        body = js_body("function renderTrend(d) {")
        row = body.split("var groups = trendGroupList(d);", 1)[1].split('var chipRow = el("div", "trend-chips");', 1)[0]
        self.assertIn('b.setAttribute("aria-pressed", String(on));', row)
        self.assertIn("toggleTrendGroup(g.key, groups)", body)

    def test_an_on_toggle_is_the_magenta_fill(self):
        self.assertRegex(CSS, r"button\.trend-group\.is-on \{ background: var\(--magenta\);[^}]*color: #fff; \}")


if __name__ == "__main__":
    unittest.main()
