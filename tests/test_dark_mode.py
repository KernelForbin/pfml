"""Dark mode (README, Dark mode): the colour tokens redefined under
prefers-color-scheme: dark, checked for contrast from the CSS itself, and
the rules that keep fixed light colours from leaking into it. The pages
were also measured in a browser in both modes; there's no JS runner here."""
import re
import unittest

from support import ROOT

SITE = ROOT / "site"


def read(name):
    return (SITE / name).read_text(encoding="utf-8")


def no_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def tokens(block):
    return {k: v.strip() for k, v in re.findall(r"(--[\w-]+):\s*([^;]+);", block)}


def light_tokens(text):
    return tokens(re.search(r":root\s*\{([^}]*)\}", no_comments(text)).group(1))


def dark_tokens(text):
    block = no_comments(text).split("@media (prefers-color-scheme: dark)", 1)[1]
    return tokens(re.search(r":root\s*\{([^}]*)\}", block).group(1))


def luminance(hex_colour):
    h = hex_colour.lstrip("#")
    def channel(c):
        c = int(c, 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(h[i:i + 2]) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# text token, background token, the WCAG minimum for normal text
PAIRS = [("--ink", "--paper"), ("--ink", "--card"), ("--muted", "--paper"), ("--muted", "--card"),
         ("--deep", "--paper"), ("--deep", "--card"), ("--deep", "--wash"), ("--ink", "--wash"),
         ("--magenta-text", "--paper"), ("--magenta-text", "--card"), ("--on-inverse", "--inverse"),
         ("--acid", "--inverse"), ("--neg", "--card"), ("--on-metal", "--gold"), ("--on-metal", "--silver"),
         ("--on-metal", "--bronze")]


class Palette(unittest.TestCase):
    def setUp(self):
        self.css = read("style.css")
        self.light = light_tokens(self.css)
        self.dark = dict(self.light, **dark_tokens(self.css))

    def test_every_text_pair_is_readable_in_both_modes(self):
        for mode, t in (("light", self.light), ("dark", self.dark)):
            for fg, bg in PAIRS:
                with self.subTest(f"{mode}: {fg} on {bg}"):
                    self.assertGreaterEqual(contrast(t[fg], t[bg]), 4.5)

    def test_white_text_on_the_purple_fill_is_readable_in_both_modes(self):
        for mode, t in (("light", self.light), ("dark", self.dark)):
            with self.subTest(mode):
                self.assertGreaterEqual(contrast("#FFFFFF", t["--magenta"]), 4.5)

    def test_light_mode_looks_exactly_as_before(self):
        # the new tokens only name what the old rules used directly
        t = self.light
        self.assertEqual(t["--magenta-text"], t["--magenta"])
        self.assertEqual(t["--inverse"], t["--ink"])
        self.assertEqual(t["--on-inverse"], t["--paper"])
        self.assertEqual(t["--on-metal"], t["--ink"])
        self.assertEqual(t["--topbar"], "rgba(248, 249, 250, 0.86)")
        self.assertEqual(t["--glass"], "rgba(248, 249, 250, 0.55)")

    def test_it_follows_the_devices_setting(self):
        dark = no_comments(self.css).split("@media (prefers-color-scheme: dark)", 1)[1]
        self.assertIn("color-scheme: dark;", dark)
        # the fill behind white text and the metals keep their colour
        for name in ("--magenta", "--gold", "--silver", "--bronze", "--on-metal", "--acid"):
            self.assertNotIn(name, dark_tokens(self.css), name)


class NoFixedLightColours(unittest.TestCase):
    def outside_tokens(self, text):
        css = no_comments(text)
        css = re.sub(r":root\s*\{[^}]*\}", "", css)
        return css.split("@media (prefers-color-scheme: dark)", 1)[0]

    def test_purple_text_uses_the_text_token(self):
        for name in ("style.css", "features.html"):
            with self.subTest(name):
                self.assertNotRegex(self.outside_tokens(read(name)), r"(?<![-\w])color:\s*var\(--magenta\)")

    def test_no_light_background_is_hard_coded(self):
        for name in ("style.css", "features.html"):
            with self.subTest(name):
                css = self.outside_tokens(read(name))
                self.assertNotRegex(css, r"background(-color)?:\s*(#fff\b|#FFF\b|#ffffff|white\b)")
                self.assertNotIn("rgba(248, 249, 250", css)
                self.assertNotRegex(css, r"linear-gradient\([^)]*#fff\b")

    def test_text_on_gold_silver_and_bronze_stays_dark(self):
        for name in ("style.css", "features.html"):
            css = self.outside_tokens(read(name))
            for rule in re.findall(r"\{[^}]*background:\s*var\(--(?:gold|silver|bronze)\)[^}]*\}", css):
                with self.subTest(f"{name}: {rule[:60]}"):
                    if "color:" in rule:
                        self.assertIn("color: var(--on-metal)", rule)
        self.assertRegex(no_comments(read("style.css")),
                         r"\.stand-rank\.is-1, \.stand-rank\.is-2, \.stand-rank\.is-3 \{[^}]*color: var\(--on-metal\)")

    def test_the_crossword_keeps_its_light_print_look(self):
        dark = no_comments(read("style.css")).split("@media (prefers-color-scheme: dark)", 1)[1]
        rule = re.search(r"\.xw-grid, \.xw-paused \{([^}]*)\}", dark).group(1)
        light = light_tokens(read("style.css"))
        for name in ("--ink", "--wash", "--card"):
            self.assertEqual(tokens(rule)[name], light[name], name)


class FeaturesPage(unittest.TestCase):
    def test_its_dark_tokens_match_the_site(self):
        site, page = dark_tokens(read("style.css")), dark_tokens(read("features.html"))
        self.assertEqual(page, site)


if __name__ == "__main__":
    unittest.main()
