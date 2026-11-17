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
    """Home's rounds (asked 2026-11-06 for a round's prompt, 2026-11-17 for
    the next round and the results tile), the prompts from the hand-kept
    round_material.json."""

    def setUp(self):
        self.js = read("app.js")
        self.fn = body(self.js, "function renderHomeRounds(index) {")
        self.tile = body(self.js, "function roundTile(season, n, r, submit) {")
        self.results = body(self.js, "function renderResultsTile(season) {")

    def test_home_draws_them_with_the_seasons_and_hides_without_the_file(self):
        self.assertIn("renderHomeRounds(index);", body(self.js, "function initHome() {"))
        self.assertIn('PFML.loadJSON("round_material.json")', self.fn)
        self.assertIn('$("block-material").hidden = false;', self.fn)
        self.assertIn('$("block-next").hidden = false;', self.fn)
        self.assertIn(".catch(function () { /* no material file: no round tiles */ });", self.fn)
        html = read("index.html")
        for block in ("block-results", "block-material", "block-next"):
            with self.subTest(block):
                self.assertRegex(html, r'<section class="shell block[a-z -]*" id="' + block + '" hidden>')

    def test_home_reads_results_current_next_season_vault_past_seasons_then_playlists(self):
        # asked 2026-11-17: the round just finished on top, then the current
        # round, the next one below; 2026-11-15: the current season under
        # them, Past Seasons above Playlists
        html = read("index.html")
        order = [html.index('id="' + b + '"') for b in ("block-results", "block-material", "block-next", "block-now",
                                                      "block-vault", "block-seasons", "block-playlists")]
        self.assertEqual(order, sorted(order))
        for head in ("<h2>Just finished</h2>", "<h2>Current round</h2>", "<h2>Next round</h2>", "<h2>Past Seasons</h2>"):
            with self.subTest(head):
                self.assertIn(head, html)

    def test_the_rounds_follow_the_export_so_a_new_round_moves_every_tile_along(self):
        # the export holds finished rounds only: the one after the last is current
        self.assertIn("var current = season.roundCount + 1;", self.fn)
        self.assertIn('$("materialCard").innerHTML = roundTile(season, current, prompts[current], submit);', self.fn)
        self.assertIn('$("nextCard").innerHTML = roundTile(season, current + 1, prompts[current + 1], null);', self.fn)
        self.assertIn("if (!m || m.season !== season.key) return;", self.fn)
        self.assertIn("return s.key === index.currentSeason;", self.fn)
        self.assertIn("return !(m.lastRound > 0) || n <= m.lastRound;", self.fn)

    def test_a_round_without_its_prompt_says_it_is_waiting(self):
        self.assertIn("Waiting for its prompt", self.tile)
        self.assertIn('esc(season.label) + " &middot; Round " + n', self.tile)

    def test_the_text_is_escaped_and_the_link_is_one_of_our_pages(self):
        self.assertIn("esc(p.trim())", self.tile)
        self.assertIn("esc(r.title)", self.tile)
        self.assertIn('var link = r && MATERIAL_LINK.test(r.link || "") ? r.link : null;', self.tile)
        # search, like JavaScript's .test(): the rule has to anchor itself
        rule = re.search(r"var MATERIAL_LINK = /(.+)/;", self.js).group(1)
        self.assertTrue(re.search(rule, "round-9-prompt"))
        for bad in ("https://example.com", "//example.com", "javascript:alert(1)", 'x" onmouseover="y', "round.html"):
            with self.subTest(bad):
                self.assertIsNone(re.search(rule, bad))

    def test_the_submit_button_goes_only_to_a_league_on_music_league_and_only_on_the_current_round(self):
        # asked 2026-11-14: "Submit on Music League", in a new tab
        self.assertIn('var submit = MATERIAL_SUBMIT.test(m.submitLink || "") ? m.submitLink : null;', self.fn)
        self.assertIn('href="\' + submit + \'" target="_blank" rel="noopener">Submit on Music League', self.tile)
        self.assertEqual(self.fn.count("submit)"), 1, "the next round never gets the button")
        rule = re.search(r"var MATERIAL_SUBMIT = /(.+)/;", self.js).group(1).replace("\\/", "/")
        self.assertTrue(re.search(rule, "https://app.musicleague.com/l/0123456789abcdef0123456789abcdef/"))
        for bad in ("https://app.musicleague.com.evil.com/l/0123456789abcdef0123456789abcdef/",
                    "http://app.musicleague.com/l/0123456789abcdef0123456789abcdef/",
                    "https://app.musicleague.com/l/0123456789abcdef0123456789abcdef/-/data",
                    "https://app.musicleague.com/l/x\" onmouseover=\"y/",
                    "javascript:alert(1)", "round-9-prompt"):
            with self.subTest(bad):
                self.assertIsNone(re.search(rule, bad))

    def test_the_results_tile_shows_for_24_hours_from_when_the_results_came_in(self):
        self.assertIn("var RESULTS_FOR_MS = 24 * 60 * 60 * 1000;", self.js)
        self.assertIn('var seen = r && r.id && Date.parse(r.seenAt || "");', self.results)
        self.assertIn("if (!seen || Date.now() - seen >= RESULTS_FOR_MS) return;", self.results)
        self.assertIn("renderResultsTile(season);", self.fn)
        self.assertIn('$("block-results").hidden = false;', self.results)

    def test_the_results_tile_links_the_rounds_results_and_escapes_its_tracks(self):
        self.assertIn('a.href = "round?s=" + encodeURIComponent(season.key) + "&r=" + encodeURIComponent(r.id);', self.results)
        for field in ("esc(r.name)", "esc(t.title)", "esc(t.artistText)", "esc(t.submitterName)"):
            with self.subTest(field):
                self.assertIn(field, self.results)
        self.assertIn('(shared(t) ? "T" : "") + t.place', self.results)

    def test_the_prompt_never_ships_in_the_repo(self):
        # the league's own text, and it can name a player: data, not page
        for text in ("Exquisite", "Gender Bender", "Deformity"):
            with self.subTest(text):
                self.assertNotIn(text, read("index.html"))
                self.assertNotIn(text, self.js)
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


class ProfilePrompts(unittest.TestCase):
    """A profile's Prompts written (asked 2026-11-17): how many, how many as
    the commissioner and how many from round wins, and each round."""

    def setUp(self):
        self.js = read("app.js")
        self.fn = body(self.js, "function renderProfilePrompts(prof) {")

    def test_the_profile_draws_it_under_season_by_season(self):
        self.assertIn("renderProfilePrompts(prof);", body(self.js, "function initProfile() {"))
        html = read("profile.html")
        self.assertIn('<section class="shell block" id="block-prompts">', html)
        self.assertLess(html.index('id="block-seasons"'), html.index('id="block-prompts"'))
        self.assertLess(html.index('id="block-prompts"'), html.index('id="block-tracks"'))
        # hidden with the other profiles.json sections when that file is missing
        self.assertIn('["block-seasons", "block-prompts", "block-tracks", "block-fans"]', self.js)

    def test_it_splits_commissioner_prompts_from_round_wins(self):
        self.assertIn('"<b>" + n.commissioner + "</b> as the commissioner, <b>" + n.won + "</b> from "', self.fn)
        self.assertIn('!n.commissioner ? "all from round wins"', self.fn)
        self.assertIn('!n.won ? "all as the commissioner"', self.fn)
        self.assertIn('if (!n.total) { host.appendChild(empty("No prompts on record yet.")); return; }', self.fn)
        self.assertIn('(x.commissioner ? \'<span class="rl-commish">Commissioner</span>\' : "Round win")', self.fn)

    def test_each_round_links_to_its_page_with_names_escaped(self):
        self.assertIn('var href = "round?s=" + encodeURIComponent(x.seasonKey) + "&r=" + encodeURIComponent(x.roundId);', self.fn)
        for field in ("esc(x.seasonLabel)", "esc(x.roundName)", "esc(o.name)"):
            with self.subTest(field):
                self.assertIn(field, self.fn)

    def test_a_long_list_folds_after_the_first_few(self):
        self.assertIn("var PROMPTS_SHOWN = 5;", self.js)
        self.assertIn("list.slice(0, PROMPTS_SHOWN)", self.fn)
        self.assertIn('"<summary>Show all " + list.length + "</summary>"', self.fn)


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
