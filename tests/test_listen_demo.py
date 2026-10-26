"""The listening demo (/round?demo=1, site/listen-demo.js; /submit?demo=1
until listening moved to the round page): the real round page with a
stand-in closed round of 10 tracks, for trying the round player on a phone.
Nothing about the stand-in reaches the database."""
import re
import unittest

from support import ROOT

SITE = ROOT / "site"
DEMO = (SITE / "listen-demo.js").read_text(encoding="utf-8")


def tracks():
    body = DEMO.split("var TRACKS = [", 1)[1].split("\n  ];", 1)[0]
    return re.findall(r'\{ platform: "(\w+)", track: "([^"]+)", title: "[^"]+", artist: "[^"]+", position: (\d+), '
                      r'spotify_match: (null|"[^"]+"), youtube_match: (null|"[^"]+") \},?\s+// (\d+):(\d\d)', body)


class ThePage(unittest.TestCase):
    def test_only_the_round_page_loads_it_after_sign_in_and_before_the_player(self):
        html = (SITE / "round.html").read_text(encoding="utf-8")
        order = [html.index(f'<script src="{s}"></script>')
                 for s in ("auth.js", "account.js", "listen-demo.js", "player.js", "listen.js", "app.js")]
        self.assertEqual(order, sorted(order))
        for page in SITE.glob("*.html"):
            if page.name != "round.html":
                with self.subTest(page.name):
                    self.assertNotIn("listen-demo.js", page.read_text(encoding="utf-8"))

    def test_it_does_nothing_without_demo_1(self):
        start = DEMO.index('"use strict";')
        self.assertTrue(DEMO[start:].split("\n", 2)[2].lstrip().startswith(
            "if (!/(^|[?&])demo=1(&|$)/.test(location.search)) return;"))


class TheRound(unittest.TestCase):
    def test_ten_tracks_five_from_each_each_with_its_copy_and_under_five_minutes(self):
        found = tracks()
        self.assertEqual(len(found), 10)
        self.assertEqual(sorted(p for p, *_ in found), ["spotify"] * 5 + ["youtube"] * 5)
        for platform, track, _, spotify, youtube, minutes, seconds in found:
            with self.subTest(track):
                self.assertRegex(track, r"^[A-Za-z0-9]{22}$" if platform == "spotify" else r"^[A-Za-z0-9_-]{11}$")
                copy = youtube if platform == "spotify" else spotify
                self.assertRegex(copy, r'^"[A-Za-z0-9_-]{11}"$' if platform == "spotify" else r'^"[A-Za-z0-9]{22}"$')
                # its own service's match is the track itself, as round_playlists.py stores it
                own = spotify if platform == "spotify" else youtube
                self.assertEqual(own, f'"{track}"')
                self.assertLess(int(minutes) * 60 + int(seconds), 300)

    def test_each_has_its_place_in_the_rounds_order_and_the_round_its_playlist(self):
        self.assertEqual(sorted(int(p) for _, _, p, *_ in tracks()), list(range(1, 11)))
        self.assertRegex(DEMO, r'spotify_playlist: null, youtube_playlist: "[A-Za-z0-9_-]{10,40}"')

    def test_it_is_closed_and_not_voted_here(self):
        self.assertIn('closes_at: new Date(now - day).toISOString(), closed_at: null', DEMO)
        self.assertIn("votes_on_site: false", DEMO)
        self.assertIn('name: "Listening demo"', DEMO)


class NothingReachesTheDatabase(unittest.TestCase):
    def test_only_the_readers_are_replaced_and_the_rest_guarded(self):
        demo = DEMO.split("var demo = {", 1)[1].split("\n    };", 1)[0]
        self.assertEqual(re.findall(r"^      (\w+): function", demo, re.M), ["siteRounds", "roundSubmissions"])
        self.assertIn("if (id !== DEMO_ROUND) return real.roundSubmissions(id);", demo)
        guard = DEMO.split("PFML.api = new Proxy(real, {", 1)[1]
        self.assertLess(guard.index("if (arguments[i] === DEMO_ROUND) return Promise.resolve([]);"),
                        guard.index("return fn.apply(target, arguments);"))

    def test_it_names_its_round_for_the_round_page(self):
        self.assertIn("window.PFMLDemo = { round: DEMO_ROUND };", DEMO)
        self.assertLess(DEMO.index("window.PFMLDemo = { round: DEMO_ROUND };"), DEMO.index("PFML.ready.then("))
        app = (SITE / "app.js").read_text(encoding="utf-8")
        self.assertIn('var siteId = params.get("site") || (window.PFMLDemo && window.PFMLDemo.round) || "";', app)

    def test_it_waits_for_sign_in(self):
        self.assertIn("PFML.ready.then(function () {\n    var real = PFML.api;", DEMO)


if __name__ == "__main__":
    unittest.main()
