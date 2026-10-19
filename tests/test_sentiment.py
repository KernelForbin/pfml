"""Estimated League Sentiment (site/sentiment.js): the wiring and the lines
it mustn't cross. The scoring is browser JavaScript (no JS runner here);
every rule was checked in a browser against the real catalog, each scoring
as designed (README, Repeat checker)."""
import re
import unittest

from support import ROOT

SITE = ROOT / "site"


def read(name):
    return (SITE / name).read_text(encoding="utf-8")


class Wiring(unittest.TestCase):
    def test_both_pages_load_it_before_their_own_code(self):
        for page, script in (("repeats.html", "repeats.js"), ("submit.html", "submit.js")):
            with self.subTest(page):
                srcs = re.findall(r'<script src="([^"]+)"', read(page))
                self.assertLess(srcs.index("account.js"), srcs.index("sentiment.js"))
                self.assertLess(srcs.index("sentiment.js"), srcs.index(script))

    def test_it_reads_only_the_catalog_and_the_season_index(self):
        self.assertEqual(sorted(re.findall(r'loadJSON\("([^"]+)"\)', read("sentiment.js"))),
                         ["catalog.json", "index.json"])

    def test_the_search_function_returns_the_album_the_album_rule_needs(self):
        ts = (ROOT / "supabase" / "functions" / "search-tracks" / "index.ts").read_text(encoding="utf-8")
        self.assertIn("album: t.album?.name ?? null,", ts)


class Rules(unittest.TestCase):
    def setUp(self):
        self.js = read("sentiment.js")

    def test_the_score_is_never_printed(self):
        # The weights are the user's call and not for members to see: the
        # score only turns the needle and picks the verdict.
        gauge = self.js.split("function gaugeHtml(result) {", 1)[1].split("\n  }\n", 1)[0]
        self.assertEqual(re.findall(r"result\.score", gauge), ["result.score"])
        self.assertIn("var a = Math.PI * (1 - Math.min(100, result.score) / 100);", gauge)
        self.assertNotRegex(gauge, r"\.weight|RULES\[[^\]]+\]\.(now|past)")

    def test_every_rule_says_what_it_is_and_has_both_seasons(self):
        rules = re.search(r"var RULES = \{(.*?)\n  \};", self.js, re.S).group(1)
        entries = re.findall(r"(\w+):\s+\{ now: (\d+), past: (\d+), says: \"([^\"]+)\" \}", rules)
        self.assertEqual(len(entries), 11)
        for name, now, past, says in entries:
            with self.subTest(name):
                self.assertTrue(0 <= int(past) <= 100 and 0 <= int(now) <= 100)
                self.assertTrue(says)
        self.assertEqual(dict((n, (int(a), int(b))) for n, a, b, _ in entries)["exact"], (100, 100))

    def test_an_exact_repeat_gets_the_extra_warning(self):
        self.assertIn("if (result.exact) {", self.js)
        self.assertIn('class="sg-warning"', self.js)

    def test_a_comma_in_a_name_cant_break_matching_either_side(self):
        names = self.js.split("function names(pieces) {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn('fold(pieces.slice(i, j + 1).join(", "))', names)
        self.assertIn("names: names(pick.artists || [])", self.js)

    def test_free_text_needs_title_and_artist_and_a_one_word_title_alone_never_counts(self):
        tk = self.js.split("function textKind(textWords, p) {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn("if (!phrase(textWords, p.songWords)) return null;", tk)
        self.assertIn('return "crossService";', tk)
        self.assertIn('return p.songWords.length > 1 ? "titleOnly" : null;', tk)

    def test_a_cross_service_match_warns_as_high_as_another_version(self):
        table = re.search(r"var RULES = \{(.*?)\n  \};", self.js, re.S).group(1)
        rules = {name: (now, past) for name, now, past in re.findall(r"(\w+):\s+\{ now: (\d+), past: (\d+)", table)}
        self.assertEqual(rules["crossService"], rules["version"])

    def test_on_a_tie_free_text_says_another_service_not_another_version(self):
        judge = self.js.split("function judge(pick) {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn("if (t && (!k || RULES[t][when] >= RULES[k][when])) k = t;", judge)

    def test_artists_unknown_means_only_the_text_judges_the_song(self):
        kind = self.js.split("function kind(pick, p) {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn("if (!Object.keys(pick.names.all).length) return null;", kind)

    def test_the_this_season_rules_use_the_current_season_from_the_index(self):
        self.assertIn("current = res[1].currentSeason", self.js)


class SubmitPage(unittest.TestCase):
    def test_a_pasted_link_is_looked_up_by_the_catalog_then_the_services_oembed(self):
        js = read("submit.js")
        gauge = js.split("function gaugeFor(p, about) {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn('if (p.platform === "spotify" && PFMLSentiment.known(p.track)) return PFMLSentiment.known(p.track);', gauge)
        self.assertIn("return aboutLink(p);", gauge)
        self.assertIn("if (gaugeKey !== key || !pick) return;", gauge)
        for url in ("https://www.youtube.com/oembed?format=json&url=", "https://soundcloud.com/oembed?format=json&url=",
                    "https://open.spotify.com/oembed?url="):
            self.assertIn(url, js)

    def test_a_youtube_pick_is_free_text_not_a_guessed_artist_and_song(self):
        # Measured 2026-10-19: Anna Ash's own upload is titled "Righteously -
        # Anna Ash", song first, so splitting at the dash made "Righteously"
        # the artist and the gauge said Fresh for a Season 1 repeat.
        js = read("submit.js")
        about = js.split("function aboutResult(service, r) {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn("return { title: r.title, artists: [r.artist], text: r.title + \" \" + r.artist };", about)
        self.assertNotRegex(about, r"split\[\d\]")
        link = js.split("function aboutLink(p) {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn('text: o.title + " " + author', link)

    def test_the_repeat_checker_offers_spotify_picks_only_for_words(self):
        js = read("repeats.js")
        picks = js.split("function spotifyPicks(text) {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn("if (text.length < 3 || SPOTIFY_TRACK.test(text))", picks)
        self.assertIn('PFML.api.searchTracks("spotify", text)', picks)

    def test_the_pick_list_really_hides(self):
        css = re.sub(r"/\*.*?\*/", "", read("style.css"), flags=re.S)
        self.assertRegex(css, r"\.rc-pick\[hidden\]\s*\{\s*display:\s*none")


if __name__ == "__main__":
    unittest.main()
