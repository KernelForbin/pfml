"""Taste twins on profiles, From the vault on Home, and the round recap
(README, Profiles; From the vault; Results by round, Recap). The build
side runs on made-up seasons; the page side is pinned as text and was
checked in a browser against the real data."""
import json
import re
import unittest

from support import ROOT, build, make_season, quiet, sandbox, uri

SITE = ROOT / "site"


def read(name):
    return (SITE / name).read_text(encoding="utf-8")


def body(js, signature):
    return js.split(signature, 1)[1].split("\n  }\n", 1)[0]


def agreeing_rounds(n):
    """n rounds where Ann (p1) and Ben (p2) back the same songs, and Cat
    (p3) and Dan (p4) back opposite ones: tracks a..d sent by p1..p4."""
    rounds = []
    for i in range(n):
        t = [f"r{i}{x}" for x in "abcd"]
        rounds.append({
            "id": f"r{i}", "name": f"Round {i}", "created": f"2025-01-{i + 1:02d}T00:00:00Z",
            "subs": [(t[0], "p1"), (t[1], "p2"), (t[2], "p3"), (t[3], "p4")],
            "votes": [("p1", t[2], 3), ("p1", t[3], 1), ("p2", t[2], 3), ("p2", t[3], 1),
                      ("p3", t[0], 1), ("p3", t[1], 3), ("p4", t[0], 3), ("p4", t[1], 1)],
        })
    return rounds


def profiles_for(rounds):
    with sandbox() as root, quiet():
        make_season(root / "data" / "season1", rounds)
        build.main()
        return json.loads((root / "site" / "data" / "profiles.json").read_text(encoding="utf-8"))["players"]


class TasteTwins(unittest.TestCase):
    def test_players_who_back_the_same_songs_are_twins_and_opposites_arent(self):
        players = profiles_for(agreeing_rounds(6))
        self.assertEqual(players["p1"]["tasteTwins"], [{"id": "p2", "name": "Ben", "rounds": 6}])
        self.assertEqual(players["p2"]["tasteTwins"], [{"id": "p1", "name": "Ann", "rounds": 6}])
        self.assertEqual(players["p3"]["tasteTwins"], [])
        self.assertEqual(players["p4"]["tasteTwins"], [])

    def test_too_few_shared_rounds_make_no_twin(self):
        players = profiles_for(agreeing_rounds(build.TASTE_TWIN_MIN_ROUNDS - 1))
        self.assertEqual(players["p1"]["tasteTwins"], [])

    def test_spreading_points_widely_isnt_agreeing(self):
        # The real-league finding: with plain cosine, someone who gives
        # every song a point looked like everyone's twin. Here Ann (p1) and
        # Ben (p2) both rate c above d, loosely; Eve (p5) gives b, c and d a
        # point each. Plain cosine scores Ann-Eve 0.73 over Ann-Ben 0.67;
        # backing songs more than your own average, Eve backs nothing.
        rounds = []
        for i in range(6):
            a, b, c, d, e = (f"r{i}{x}" for x in "abcde")
            rounds.append({
                "id": f"r{i}", "name": f"Round {i}", "created": f"2025-01-{i + 1:02d}T00:00:00Z",
                "subs": [(a, "p1"), (b, "p2"), (c, "p3"), (d, "p4"), (e, "p5")],
                "votes": [("p1", c, 3), ("p1", d, 1), ("p2", c, 2), ("p2", e, 2),
                          ("p3", a, 1), ("p3", b, 3), ("p4", a, 3), ("p4", b, 1),
                          ("p5", b, 1), ("p5", c, 1), ("p5", d, 1)],
            })
        players = profiles_for_with_eve(rounds)
        self.assertEqual([t["id"] for t in players["p1"]["tasteTwins"]], ["p2"])

    def test_a_long_name_cant_push_the_lists_off_a_phone(self):
        # Measured 2026-10-24: the third list made the profile 417px wide in
        # a 371px phone frame ("Samantha Lemansky Yarsike" + "over 46
        # rounds"); a grid column won't shrink below its content without this
        css = re.sub(r"/\*.*?\*/", "", read("style.css"), flags=re.S)
        rule = re.search(r"\.pf-people \{([^}]*)\}", css).group(1)
        self.assertRegex(rule, r"min-width:\s*0")
        self.assertRegex(css, r"\.pf-people a span \{[^}]*text-overflow:\s*ellipsis")

    def test_the_profile_lists_them_by_rounds_not_a_percentage(self):
        fans = body(read("app.js"), "function renderProfileFans(prof, name) {")
        self.assertIn('peopleList("Votes most like them", (prof && prof.tasteTwins) || [],', fans)
        self.assertIn('return "<small>over " + x.rounds + " rounds</small>";', fans)
        self.assertNotRegex(fans, r"match|%")


def profiles_for_with_eve(rounds):
    with sandbox() as root, quiet():
        make_season(root / "data" / "season1", rounds,
                    players={"p1": "Ann", "p2": "Ben", "p3": "Cat", "p4": "Dan", "p5": "Eve"})
        build.main()
        return json.loads((root / "site" / "data" / "profiles.json").read_text(encoding="utf-8"))["players"]


class Vault(unittest.TestCase):
    ROUND = {
        "id": "r1", "name": "Round One", "created": "2025-01-01T00:00:00Z",
        "subs": [("a", "p1", "my note"), ("b", "p2"), ("c", "p3")],
        "votes": [("p2", "a", 3, "short"), ("p3", "a", 3, "a longer comment"), ("p4", "a", 1, "the longest comment of all here"),
                  ("p1", "b", 2), ("p4", "c", 2)],
    }
    TIE = {
        "id": "r2", "name": "Round Two", "created": "2025-01-08T00:00:00Z",
        "subs": [("e", "p1"), ("f", "p2")],
        "votes": [("p3", "e", 2), ("p3", "f", 1), ("p4", "e", 1), ("p4", "f", 2)],
    }

    def vault(self, translations=None):
        with sandbox() as root, quiet():
            make_season(root / "data" / "season1", [self.ROUND, self.TIE])
            if translations:
                (root / "data" / "translations.json").write_text(json.dumps(translations), encoding="utf-8")
            build.main()
            return json.loads((root / "site" / "data" / "vault.json").read_text(encoding="utf-8"))["winners"]

    def test_each_round_winner_with_its_note_and_its_biggest_backers_comment(self):
        w = self.vault()[0]
        self.assertEqual((w["roundNumber"], w["title"], w["submitterName"], w["points"], w["note"]),
                         (1, "Song a", "Ann", 7, "my note"))
        # 3 points beat 1; between the two 3s, the longer comment
        self.assertEqual(w["comment"], {"voterName": "Cat", "comment": "a longer comment"})

    def test_a_tie_for_first_lists_each_winner(self):
        self.assertEqual([(w["roundNumber"], w["title"]) for w in self.vault()[1:]], [(2, "Song e"), (2, "Song f")])

    def test_a_translated_comment_brings_its_english(self):
        cid = build.comment_id("r1", uri("a"), "p3")
        w = self.vault({"comments": {cid: {"from": "Swedish", "original": "a longer comment", "text": "in English"}}})[0]
        self.assertEqual(w["comment"]["translation"]["text"], "in English")

    def test_home_shows_one_at_random_and_hides_without_the_file(self):
        js = read("app.js")
        vault = body(js, "function renderVault() {")
        self.assertIn("var w = list[Math.floor(Math.random() * list.length)];", vault)
        self.assertIn("PFML.translationHtml(c.translation)", vault)
        self.assertIn('$("block-vault").hidden = false;', vault)
        self.assertIn("renderVault();", body(js, "function initHome() {"))
        self.assertIn('<section class="shell block" id="block-vault" hidden>', read("index.html"))


class RoundMaterial(unittest.TestCase):
    """A round's prompt and a link to its reading, on Home (asked
    2026-11-06), from the hand-kept round_material.json."""

    def setUp(self):
        self.js = read("app.js")
        self.fn = body(self.js, "function renderRoundMaterial(index) {")

    def test_home_draws_it_with_the_seasons_and_hides_without_the_file(self):
        self.assertIn("renderRoundMaterial(index);", body(self.js, "function initHome() {"))
        self.assertIn('PFML.loadJSON("round_material.json")', self.fn)
        self.assertIn('$("block-material").hidden = false;', self.fn)
        html = read("index.html")
        self.assertIn('<section class="shell block block-first" id="block-material" hidden>', html)
        self.assertLess(html.index('id="block-material"'), html.index('id="block-seasons"'), "above the seasons")

    def test_home_reads_prompt_current_season_vault_past_seasons_then_playlists(self):
        # asked 2026-11-14: the tile's heading says where the league is; and
        # 2026-11-15: the current season under the prompt, Past Seasons
        # above Playlists
        html = read("index.html")
        order = [html.index('id="' + b + '"') for b in ("block-material", "block-now", "block-vault", "block-seasons", "block-playlists")]
        self.assertEqual(order, sorted(order))
        self.assertIn("<h2>Past Seasons</h2>", html)
        self.assertNotIn("<h2>Seasons</h2>", html)
        self.assertIn('<h2 id="materialHead">', html)
        self.assertIn('if (season && m.round > 0) $("materialHead").textContent = season.label + ", Round " + m.round;', self.fn)
        self.assertNotIn("innerHTML", self.fn.split('$("materialHead")')[1].split(";")[0], "the label is text, not markup")

    def test_it_goes_once_the_rounds_results_are_in(self):
        self.assertIn("if (season && season.roundCount >= m.round) return;", self.fn)

    def test_the_text_is_escaped_and_the_link_is_one_of_our_pages(self):
        self.assertIn("esc(p.trim())", self.fn)
        self.assertIn("esc(m.title)", self.fn)
        self.assertIn("var link = MATERIAL_LINK.test(m.link || \"\") ? m.link : null;", self.fn)
        # search, like JavaScript's .test(): the rule has to anchor itself
        rule = re.search(r"var MATERIAL_LINK = /(.+)/;", self.js).group(1)
        self.assertTrue(re.search(rule, "round-9-prompt"))
        for bad in ("https://example.com", "//example.com", "javascript:alert(1)", 'x" onmouseover="y', "round.html"):
            with self.subTest(bad):
                self.assertIsNone(re.search(rule, bad))

    def test_the_submit_button_goes_only_to_a_league_on_music_league(self):
        # asked 2026-11-14: "Submit on Music League", in a new tab
        self.assertIn('var submit = MATERIAL_SUBMIT.test(m.submitLink || "") ? m.submitLink : null;', self.fn)
        self.assertIn('href="\' + submit + \'" target="_blank" rel="noopener">Submit on Music League', self.fn)
        rule = re.search(r"var MATERIAL_SUBMIT = /(.+)/;", self.js).group(1).replace("\\/", "/")
        self.assertTrue(re.search(rule, "https://app.musicleague.com/l/0123456789abcdef0123456789abcdef/"))
        for bad in ("https://app.musicleague.com.evil.com/l/0123456789abcdef0123456789abcdef/",
                    "http://app.musicleague.com/l/0123456789abcdef0123456789abcdef/",
                    "https://app.musicleague.com/l/0123456789abcdef0123456789abcdef/-/data",
                    "https://app.musicleague.com/l/x\" onmouseover=\"y/",
                    "javascript:alert(1)", "round-9-prompt"):
            with self.subTest(bad):
                self.assertIsNone(re.search(rule, bad))

    def test_the_prompt_never_ships_in_the_repo(self):
        # the league's own text, and it can name a player: data, not page
        self.assertNotIn("Exquisite", read("index.html"))
        self.assertNotIn("Exquisite", self.js)
        self.assertFalse((SITE / "round_material.json").exists())


class CurrentSeasonCard(unittest.TestCase):
    """Asked 2026-11-15: the season in progress in its own kind of tile
    under the round's prompt, the rest under Past Seasons."""

    def setUp(self):
        self.js = read("app.js")
        self.home = body(self.js, "function initHome() {")
        self.card = body(self.js, "function nowCard(s) {")

    def test_the_current_season_gets_the_card_and_is_left_out_of_past_seasons(self):
        self.assertIn("return s.key === index.currentSeason;", self.home)
        self.assertIn('setBlock("nowCard", nowCard(current));', self.home)
        self.assertIn('$("block-now").hidden = false;', self.home)
        self.assertIn("if (s !== current) grid.appendChild(seasonCard(s));", self.home)
        self.assertIn('<section class="shell block" id="block-now" hidden>', read("index.html"))

    def test_past_season_cards_name_the_winner_never_a_leader(self):
        card = body(self.js, "function seasonCard(s) {")
        self.assertIn('"Winner"', card)
        self.assertNotIn("Leading", card)
        self.assertNotIn("live-badge", card)

    def test_it_shows_the_top_places_with_ties_and_where_the_season_is(self):
        self.assertIn("var top = live ? (s.top || []) : [];", self.card)
        self.assertIn('(p.tied ? "T" : "") + p.rank', self.card)
        self.assertIn("esc(p.name)", self.card)
        self.assertIn("esc(s.liveRound.name)", self.card)
        self.assertIn("Not started yet", self.card)

    def test_it_is_a_card_like_its_neighbours_in_both_modes(self):
        # It was a dark --inverse tile that ignored light mode; it's now the
        # same card surface as the prompt and vault cards (2026-11-16).
        css = read("style.css")
        rule = css.split(".now-card {", 1)[1].split("}", 1)[0]
        self.assertIn("background: var(--card)", rule)
        self.assertIn("color: var(--ink)", rule)
        self.assertNotIn("inverse", css.split("/* ---------- home page: the current season", 1)[1]
                         .split("/* ---------- home page: playlists", 1)[0])
        # the site-wide a:hover would otherwise turn every line purple
        self.assertIn(".now-card:hover { color: var(--ink); }", css)

    def test_it_leads_with_where_the_season_is_as_a_kicker(self):
        self.assertIn('<p class="now-kicker">', self.card)
        self.assertIn('" underway"', self.card)


class RoundTilePromptBy(unittest.TestCase):
    """Results by round: each round's tile names who wrote its prompt, with
    the Commissioner tag (asked 2026-11-14)."""

    def setUp(self):
        self.js = read("rounds.js")
        self.fn = body(self.js, "function promptByLine(r) {")

    def test_every_tile_carries_it(self):
        self.assertIn("promptByLine(r) +", body(self.js, "function renderList(host, d, opts) {"))

    def test_names_escaped_not_linked_and_the_commissioner_tagged(self):
        # the tile is itself a link, so the names can't be
        self.assertIn('"<b>" + esc(p.name) + "</b>"', self.fn)
        self.assertNotIn("<a", self.fn)
        self.assertNotIn("personLink", self.fn)
        self.assertIn('(by.commissioner ? \' <span class="rl-commish">Commissioner</span>\' : "")', self.fn)

    def test_nothing_without_a_writer(self):
        self.assertIn('if (!by || !by.people || !by.people.length) return "";', self.fn)


class Recap(unittest.TestCase):
    def setUp(self):
        self.js = read("rounds.js")

    def test_four_lines_from_the_rounds_own_numbers(self):
        lines = body(self.js, "function recapLines(r, names) {")
        for label in ("Winner", "Most talked about", "Broadest support", "Biggest bet"):
            self.assertIn('label: "' + label + '"', lines)
        self.assertIn('(r.margin ? ", won by " + counted(r.margin, "point") : "")', lines)
        self.assertIn('html: "a tie at " + top[0].points + " pts: "', lines)
        self.assertIn("if (talked && talked.comments.length >= 2) {", lines)

    def test_only_for_a_round_with_results(self):
        page = body(self.js, "function renderRoundPage(d, roundId) {")
        self.assertIn("var recap = status ? [] : recapLines(r, state.names);", page)
        self.assertIn('(status ? "" : recapHtml(recap))', page)

    def test_no_copy_button(self):
        # removed at the user's request (2026-10-24), with its plain-text lines
        self.assertNotRegex(self.js, r"(?i)copy recap|rpRecapCopy|recapText|clipboard")
        self.assertNotIn("text:", body(self.js, "function recapLines(r, names) {"))
        self.assertNotRegex(read("features.html"), r"(?i)copy recap")
        self.assertNotIn("rp-recap-copy", read("style.css"))

    def test_names_and_titles_are_escaped_on_the_page(self):
        lines = body(self.js, "function recapLines(r, names) {")
        self.assertNotRegex(lines, r'html: [^\n]*"<b>" \+ (w|s|talked|broad|bet\.song)\.title')
        self.assertIn('"<b>" + esc(w.title) + "</b> ("', lines)


if __name__ == "__main__":
    unittest.main()
