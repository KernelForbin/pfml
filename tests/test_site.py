"""The site's static contracts: what the pages load, how they link, and what
must never be in the repo. Reads only tracked page files, never data.

Wording on the features page is meant to change; these tests check the
mechanics around it (what it loads, the mode switch wiring, the links)."""
import re
import subprocess
import unittest
from html.parser import HTMLParser
from urllib.parse import urlparse

from support import ROOT

SITE = ROOT / "site"
MEMBER_PAGES = ["index.html", "career.html", "round.html", "season.template.html"]
FONT_HOSTS = {"fonts.googleapis.com", "fonts.gstatic.com"}


class Page(HTMLParser):
    """Collects every tag with its attributes, plus inline script text."""

    def __init__(self, text):
        super().__init__()
        self.tags, self.scripts, self._in_script = [], [], False
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        self._in_script = tag == "script"

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_script = False

    def handle_data(self, data):
        if self._in_script:
            self.scripts.append(data)

    def find(self, tag=None, **attrs):
        return [a for t, a in self.tags
                if (tag is None or t == tag) and all(a.get(k) == v for k, v in attrs.items())]


def read(name):
    return (SITE / name).read_text(encoding="utf-8")


def tracked_files():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return out.stdout.splitlines()


class FeaturesPageIsStandalone(unittest.TestCase):
    def setUp(self):
        self.page = Page(read("features.html"))

    def test_loads_nothing_but_itself_and_its_fonts(self):
        for tag, attrs in self.page.tags:
            for key in ("src", "href"):
                url = attrs.get(key)
                if not url or url.startswith(("#", "?", "data:")):
                    continue
                if tag == "a":
                    continue   # links are navigation, not loads; checked below
                host = urlparse(url).netloc
                self.assertIn(host, FONT_HOSTS, f"<{tag} {key}={url}> loads from outside the page")
        self.assertEqual(self.page.find("script", src=None), self.page.find("script"),
                         "no external scripts")
        script = "".join(self.page.scripts)
        for call in ("fetch(", "XMLHttpRequest", "import(", "loadJSON", "supabase"):
            self.assertNotIn(call, script)

    def test_shares_no_code_with_the_site(self):
        loads = [a.get("href") or a.get("src") for t, a in self.page.tags if t in ("link", "script")]
        for name in ("style.css", "app.js", "auth.js", "rounds.js", "config.js"):
            self.assertNotIn(name, loads)

    def test_mode_switch_is_wired_to_real_sections(self):
        links = self.page.find("a")
        modes = [a["data-mode"] for a in links if "data-mode" in a]
        self.assertTrue(modes)
        for m in modes:
            self.assertEqual(self.page.find("a", **{"data-mode": m})[0]["href"], f"?mode={m}")
            self.assertEqual(len(self.page.find("section", **{"data-mode": m})), 1, m)
        script = "".join(self.page.scripts)
        listed = re.search(r"var MODES = \[([^\]]*)\]", script).group(1)
        self.assertEqual(re.findall(r'"(\w+)"', listed), modes, "script's MODES must match the switch")
        default = re.search(r'var DEFAULT = "(\w+)"', script).group(1)
        self.assertEqual(default, modes[0], "the default mode is the first one shown")

    def test_links_back_to_the_site(self):
        hrefs = [a.get("href") for a in self.page.find("a")]
        self.assertIn("./", hrefs)


class Linking(unittest.TestCase):
    def test_every_member_page_links_to_the_features_page(self):
        for name in MEMBER_PAGES:
            hrefs = [a.get("href") for a in Page(read(name)).find("a")]
            self.assertIn("features", hrefs, name)

    def test_clean_links_point_at_real_pages(self):
        # GitHub Pages serves /features from features.html; keep the target real.
        for target in ("features", "privacy"):
            self.assertTrue((SITE / f"{target}.html").exists(), target)


class GeneratedPages(unittest.TestCase):
    def test_season_pages_match_the_template(self):
        # seasonN.html are build.py output; edit the template, then rebuild.
        template = read("season.template.html")
        pages = sorted(SITE.glob("season[0-9]*.html"))
        self.assertTrue(pages)
        for p in pages:
            key = p.stem
            label = "Season " + key[len("season"):]
            expected = (template.replace("{{TITLE}}", f"PFML - {label}")
                        .replace("{{SEASON_KEY}}", key).replace("{{LABEL}}", label))
            self.assertEqual(p.read_text(encoding="utf-8"), expected, f"{p.name} is stale: run scripts/build.py")


class FoldingSections(unittest.TestCase):
    """Standings and Results by round, the two most-used sections: first on
    the page in that order, each collapsed into a bar that holds the
    heading and every element the code fills in for its summary.

    Results by round folds as a <details>. Standings can't: its bar holds
    buttons (the active filters), so it's a bar plus a real toggle button
    controlling a hidden panel."""

    # section id -> (script, the stretch of it that fills that section's bar)
    FILLERS = {
        "block-standings": ("app.js", "function renderStandingsSummary", "function initStandingsFold"),
        "block-rounds": ("rounds.js", "function renderList", "2. The round page"),
    }

    def setUp(self):
        # comments can mention tags (the one explaining why Standings isn't
        # a <details> does), so look at the markup without them
        self.template = re.sub(r"<!--.*?-->", "", read("season.template.html"), flags=re.S)

    def section(self, section_id):
        m = re.search(r'<section[^>]*id="%s"[^>]*>(.*?)</section>' % section_id, self.template, re.S)
        self.assertIsNotNone(m, section_id)
        return m.group(1)

    def bar(self, section_id):
        body = self.section(section_id)
        if section_id == "block-standings":
            m = re.search(r'id="standBar"(.*?)id="standPanel"', body, re.S)
        else:
            self.assertRegex(body, r"<details[^>]*>", "Results by round folds as a <details>")
            m = re.search(r"<summary[^>]*>(.*?)</summary>", body, re.S)
        self.assertIsNotNone(m, f"{section_id} has a collapsed bar")
        return m.group(1)

    def test_standings_then_results_come_first(self):
        blocks = [a["id"] for a in Page(self.template).find("section") if a.get("id", "").startswith("block-")]
        self.assertEqual(blocks[:2], ["block-standings", "block-rounds"])

    def test_each_collapsed_bar_has_its_heading_and_what_the_code_fills_in(self):
        for section_id, (script, start, end) in self.FILLERS.items():
            with self.subTest(section_id):
                bar = self.bar(section_id)
                self.assertRegex(bar, r"<h2[^>]*>", "the bar carries the section's heading")
                code = read(script).split(start, 1)[1].split(end, 1)[0]
                ids = set(re.findall(r'(?:getElementById\("|\$\(")(\w+)"\)', code))
                self.assertTrue(ids, f"no ids found in {script}")
                for i in ids:
                    self.assertIn(f'id="{i}"', bar, f"{script} fills #{i}; the bar must contain it")

    def test_standings_toggle_controls_a_panel_that_starts_closed(self):
        page = Page(self.template)
        toggle = page.find("button", id="standToggle")
        self.assertEqual(len(toggle), 1, "Standings has a real toggle button")
        self.assertEqual(toggle[0].get("aria-expanded"), "false")
        panel_id = toggle[0].get("aria-controls")
        panel = page.find(id=panel_id)
        self.assertEqual(len(panel), 1, "aria-controls points at the panel")
        self.assertIn("hidden", panel[0], "the panel starts closed")
        after_panel = self.section("block-standings").split('id="%s"' % panel_id, 1)[1]
        self.assertIn('id="standings"', after_panel, "the full list is inside the panel")

    def test_no_buttons_inside_a_summary(self):
        # A button inside <summary> also folds its section when clicked, and
        # screen readers announce it badly: why Standings isn't a <details>.
        for summary in re.findall(r"<summary[^>]*>(.*?)</summary>", self.template, re.S):
            self.assertNotRegex(summary, r"<(button|a)\b")


class LeadsWithStandings(unittest.TestCase):
    def test_title_then_straight_into_standings(self):
        # Members asked for the stat cards and the summary line to go: the
        # title, then Standings. The line stays only for loading/errors.
        template = read("season.template.html")
        sections = Page(template).find("section")
        self.assertIn("hero", sections[0].get("class", ""))
        self.assertEqual(sections[1].get("id"), "block-standings")
        hero = re.search(r'<section class="[^"]*\bhero\b[^"]*"[^>]*>(.*?)</section>', template, re.S).group(1)
        self.assertNotRegex(hero, r"<dl\b", "no stat cards under the title")

    def test_stat_card_code_is_gone(self):
        for name in ("app.js", "style.css", "season.template.html"):
            self.assertNotIn("scoreline", read(name), name)


def css_rules(css, selector):
    """The declaration blocks of every rule whose selector list includes
    `selector` exactly."""
    out = []
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        if selector in [s.strip() for s in sel.split(",")]:
            out.append(body)
    return out


class PodiumColours(unittest.TestCase):
    # every badge that shows a 1st/2nd/3rd place, per page
    PLACES = {
        "style.css": [".rp-place.is-{n}", ".stand-top-chip.is-{n} .pl", ".stand-rank.is-{n}"],
        "features.html": [".place.is-{n}"],
    }
    MEDAL = {1: "--gold", 2: "--silver", 3: "--bronze"}

    def test_places_are_gold_silver_bronze_not_acid(self):
        for name, selectors in self.PLACES.items():
            css = read(name)
            for pattern in selectors:
                for n, medal in self.MEDAL.items():
                    sel = pattern.format(n=n)
                    with self.subTest(file=name, selector=sel):
                        rules = css_rules(css, sel)
                        self.assertTrue(rules, "no rule found")
                        backgrounds = re.findall(r"background:\s*([^;]+)", " ".join(rules))
                        self.assertTrue(any(f"var({medal})" in b for b in backgrounds), backgrounds)
                        self.assertNotIn("--acid", " ".join(rules))

    def test_leader_bar_is_gold_not_acid(self):
        rule = " ".join(css_rules(read("style.css"), ".stand-row:first-child .bar > i"))
        self.assertIn("var(--gold)", rule)
        self.assertNotIn("--acid", rule)


class FeaturesPageTokens(unittest.TestCase):
    def test_copied_tokens_match_the_site(self):
        # features.html copies style.css's tokens rather than loading it; a
        # palette change there has to reach here too.
        def tokens(text):
            root = re.search(r":root\s*\{([^}]*)\}", text).group(1)
            return dict(re.findall(r"(--[\w-]+):\s*([^;]+);", root))
        site, page = tokens(read("style.css")), tokens(read("features.html"))
        for name, value in page.items():
            if name in site:
                self.assertEqual(value.strip(), site[name].strip(), name)
        for name in ("--gold", "--silver", "--bronze", "--magenta", "--ink", "--paper"):
            self.assertIn(name, page, f"features.html is missing {name}")


class CleanText(unittest.TestCase):
    def test_no_control_characters_in_site_files(self):
        # A generated CSS edit once turned the escape "\25BE" (the arrow on
        # Show all) into a control character plus "BE", and the page showed
        # a broken glyph. Browsers don't complain; this does.
        control = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
        for f in tracked_files():
            if f.startswith("site/") and f.endswith((".html", ".css", ".js")):
                m = control.search((ROOT / f).read_text(encoding="utf-8"))
                self.assertIsNone(m, f"{f} has a control character {m.group()!r} at {m.start()}" if m else "")


class NothingPrivateIsTracked(unittest.TestCase):
    def test_no_league_data_in_the_repo(self):
        for f in tracked_files():
            self.assertFalse(f.startswith(("data/", "site/data/")), f)
            self.assertFalse(f.startswith("site/") and f.endswith(".json"), f)
            self.assertFalse(re.search(r"(^|/)\.env", f) and not f.endswith(".env.example"), f)

    def test_no_secret_keys_in_tracked_files(self):
        secret = re.compile(r"sb_secret_[A-Za-z0-9_-]{8,}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.")
        for f in tracked_files():
            path = ROOT / f
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            self.assertIsNone(secret.search(text), f"{f} contains what looks like a secret key")

    def test_config_holds_only_the_publishable_key(self):
        key = re.search(r'supabasePublishableKey:\s*"([^"]+)"', read("config.js")).group(1)
        self.assertTrue(key.startswith("sb_publishable_"), "config.js must hold the publishable key only")


if __name__ == "__main__":
    unittest.main()
