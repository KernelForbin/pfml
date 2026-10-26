"""The round player on the round page (site/player.js, drawn by listen.js;
on the Submit page until 2026-10-26): its wiring and the
lines it mustn't cross. What it does in a browser (playing Spotify, YouTube
and SoundCloud in turn, moving on by itself, the "Tap to play next"
fallback, skipping a dead track) was measured in Chromium with real embeds
(README, Submissions on the site, stage 3); there's no JS runner here."""
import re
import unittest

from support import ROOT

SITE = ROOT / "site"


def read(name):
    return (SITE / name).read_text(encoding="utf-8")


class Wiring(unittest.TestCase):
    def test_the_round_page_loads_it_before_the_code_that_mounts_it(self):
        srcs = re.findall(r'<script src="([^"]+)"', read("round.html"))
        order = [srcs.index(s) for s in ("account.js", "player.js", "listen.js", "rounds.js", "app.js")]
        self.assertEqual(order, sorted(order))
        self.assertIn("window.PFMLPlayer.mount(", read("listen.js"))
        # listening left the Submit page (2026-10-26)
        self.assertNotIn("player.js", read("submit.html"))
        self.assertNotIn("PFMLPlayer", read("submit.js"))

    def test_only_the_three_official_player_apis_and_only_on_demand(self):
        js = read("player.js")
        urls = sorted(set(re.findall(r'"(https://[^"]+)"', js)))
        self.assertEqual(urls, sorted([
            "https://open.spotify.com/embed/iframe-api/v1",
            "https://www.youtube.com/iframe_api",
            "https://w.soundcloud.com/player/api.js",
            "https://www.youtube-nocookie.com",
            "https://w.soundcloud.com/player/?url=",
            "https://soundcloud.com/",
        ]))
        # loaded by the script when Play is pressed, never by a page
        for page in SITE.glob("*.html"):
            for url in ("iframe-api", "iframe_api", "player/api.js"):
                self.assertNotIn(url, page.read_text(encoding="utf-8"), page.name)

    def test_youtube_plays_from_the_privacy_enhanced_host(self):
        self.assertIn('host: "https://www.youtube-nocookie.com"', read("player.js"))

    def test_the_list_starts_the_round_player_instead_of_its_own_embeds(self):
        js = read("listen.js")
        listing = js.split("function render(host, r) {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn("player.playAt(", listing)
        self.assertNotIn("embedHtml(", listing)


class Behaviour(unittest.TestCase):
    """The parts of player.js that keep the round moving the right way."""

    def setUp(self):
        self.js = read("player.js")

    def test_a_track_that_wont_start_gets_a_tap_button(self):
        self.assertIn('class="rp-tap" data-rp="tap" hidden>Tap to play next', self.js)
        self.assertRegex(self.js, r"stallTimer = setTimeout\(function \(\) \{ tap\.hidden = false; \}")
        self.assertRegex(self.js, r"playing: function \(\) \{ clearTimeout\(stallTimer\); tap\.hidden = true; \}")

    def test_spotify_ignores_reports_about_the_track_before(self):
        self.assertIn("if (d.playingURI && d.playingURI !== uri) return;", self.js)

    def test_a_dead_track_is_skipped_not_stuck_on(self):
        self.assertIn('onError: function () { hooks.failed(); }', self.js)
        self.assertIn("widget.bind(E.ERROR, function () { hooks.failed(); });", self.js)
        self.assertIn("go(failedAt + 1, true)", self.js)

    def test_only_one_service_plays_at_a_time(self):
        go = self.js.split("function go(i, automatic) {", 1)[1].split("\n    }\n", 1)[0]
        self.assertIn("if (k !== src.platform) { adapters[k].destroy(); delete adapters[k]; }", go)

    def test_the_source_choice_falls_back_to_the_submitted_track(self):
        fn = self.js.split("function sourceFor(t, pref) {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn('if (pref === "youtube" && t.youtube_match)', fn)
        self.assertIn('if (pref === "spotify" && t.spotify_match)', fn)
        self.assertIn("return { platform: t.platform, id: t.track };", fn)

    def test_a_phone_starts_on_the_youtube_copies_unless_someone_chose(self):
        fn = self.js.split("function readPref() {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn('return saved || (isPhone() ? "youtube" : "submitted");', fn)
        phone = self.js.split("function isPhone() {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn('window.matchMedia("(hover: none) and (pointer: coarse)").matches', phone)

    def test_the_saved_choice_never_breaks_the_page(self):
        for fn in ("readPref", "writePref"):
            body = self.js.split(f"function {fn}(", 1)[1].split("\n  }\n", 1)[0]
            self.assertIn("try {", body, fn)

    def test_boxes_it_hides_really_hide(self):
        # The emoji search lesson (CLAUDE.md): a class that sets display
        # beats [hidden] unless [hidden] is restated for it.
        css = re.sub(r"/\*.*?\*/", "", read("style.css"), flags=re.S)
        hidden_classes = re.findall(r'class="([\w -]+)"[^>]*\bhidden\b', self.js)
        self.assertTrue(hidden_classes)
        for cls in {c.split()[-1] for c in hidden_classes}:
            with self.subTest(cls):
                sets_display = re.search(r"\." + cls + r"\s*\{[^}]*display\s*:", css)
                if sets_display:
                    self.assertRegex(css, r"\." + cls + r"\[hidden\]\s*\{\s*display:\s*none")


if __name__ == "__main__":
    unittest.main()
