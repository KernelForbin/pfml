"""Home's Repeat checker sign (asked 2026-11-22): a Vegas marquee linking to
the Repeat checker, at the top of Home above the rounds. The bulbs are
browser JavaScript (no JS runner here); they were checked in a browser at
375px and 1280px, light and dark (README, Repeat checker sign)."""
import re
import unittest

from support import ROOT

SITE = ROOT / "site"


def read(name):
    return (SITE / name).read_text(encoding="utf-8")


def no_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


class Placement(unittest.TestCase):
    def setUp(self):
        self.home = read("index.html")

    def test_the_sign_links_to_the_repeat_checker_and_says_so(self):
        sign = re.search(r'<a class="rsign" id="repeatSign" href="([^"]+)">(.*?)</a>', self.home, re.S)
        self.assertIsNotNone(sign)
        self.assertEqual(sign.group(1), "repeats")
        self.assertIn('<span class="rsign-txt">Check for repeats here</span>', sign.group(2))

    def test_it_sits_above_every_round_on_home(self):
        at = self.home.index('id="repeatSign"')
        for block in ("block-results", "block-material", "block-next"):
            with self.subTest(block):
                self.assertLess(at, self.home.index('id="%s"' % block))

    def test_it_is_always_shown(self):
        section = re.search(r'<section class="shell rsign-wrap"[^>]*>', self.home).group(0)
        self.assertNotIn("hidden", section)

    def test_the_bulbs_and_arrows_are_hidden_from_screen_readers(self):
        self.assertIn('<span class="rsign-lights" aria-hidden="true">', self.home)
        arrows = re.findall(r'<div class="rsign-arrow" data-points="(\w+)" aria-hidden="true"></div>', self.home)
        self.assertEqual(arrows, ["right", "left"], "one each side, pointing in")

    def test_its_font_loads_on_home(self):
        self.assertRegex(self.home, r'fonts\.googleapis\.com/css2\?[^"]*family=Bungee[&"]')
        css = no_comments(read("style.css"))
        self.assertRegex(css, r'\.rsign-txt \{[^}]*"Bungee", "Archivo"')


class Bulbs(unittest.TestCase):
    def setUp(self):
        self.css = no_comments(read("style.css"))
        self.js = read("app.js")

    def test_home_draws_them(self):
        init = self.js.split("function initHome() {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn("renderRepeatSign();", init)
        sign = self.js.split("function renderRepeatSign() {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn("new ResizeObserver(draw).observe(sign)", sign)

    def test_they_blink_slower_than_three_times_a_second(self):
        # flashing faster than 3 a second can trigger seizures
        rule = re.search(r"\.rs-bulb \{([^}]*)\}", self.css).group(1)
        seconds = float(re.search(r"animation: rs-lit ([\d.]+)s", rule).group(1))
        self.assertGreaterEqual(seconds, 1 / 3)

    def test_reduced_motion_keeps_them_lit_and_still(self):
        blocks = re.findall(r"@media \(prefers-reduced-motion: reduce\) \{((?:[^{}]*\{[^{}]*\})*)\s*\}", self.css)
        rule = next((b for b in blocks if ".rs-bulb {" in b), "")
        self.assertRegex(rule, r"\.rs-bulb \{[^}]*animation: none;[^}]*background: var\(--gold\)")

    def test_the_sign_stays_dark_in_both_modes(self):
        rule = re.search(r"\n\.rsign \{([^}]*)\}", self.css).group(1)
        self.assertIn("background: var(--inverse);", rule)
        self.assertIn("color: var(--gold);", rule)


if __name__ == "__main__":
    unittest.main()
