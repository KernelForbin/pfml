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


class ResultsByRound(unittest.TestCase):
    """The most-used section: right under Standings, and its collapsed bar
    has every element rounds.js fills in (count, latest round, album art)."""

    def setUp(self):
        self.template = read("season.template.html")
        self.page = Page(self.template)

    def test_sits_directly_under_the_standings(self):
        blocks = [a["id"] for a in self.page.find("section") if a.get("id", "").startswith("block-")]
        self.assertEqual(blocks[blocks.index("block-standings") + 1], "block-rounds")

    def test_collapsed_bar_has_what_rounds_js_fills_in(self):
        summary = re.search(r"<summary[^>]*>(.*?)</summary>", self.template, re.S)
        self.assertIsNotNone(summary, "the section is a <details> with a <summary> bar")
        season_list = read("rounds.js").split("function renderList", 1)[1].split("2. The round page", 1)[0]
        ids = set(re.findall(r'getElementById\("(\w+)"\)', season_list))
        self.assertTrue(ids)
        for i in ids:
            self.assertIn(f'id="{i}"', summary.group(1), f"rounds.js fills #{i}, which the bar must contain")
        self.assertRegex(summary.group(1), r"<h2[^>]*>", "the bar carries the section's heading")


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
