"""The repeat checker page (/repeats): its wiring. The searching itself is
browser JavaScript (no JS runner here) and was checked in a browser against
the real catalog (README, Repeat checker); scripts/build.py's catalog is
tested in test_build.py (Catalog)."""
import re
import unittest

from support import ROOT

SITE = ROOT / "site"


def read(name):
    return (SITE / name).read_text(encoding="utf-8")


class Wiring(unittest.TestCase):
    def test_a_members_page_that_loads_its_script_before_app_js(self):
        html = read("repeats.html")
        self.assertIn('<body class="gated" data-page="repeats">', html)
        srcs = re.findall(r'<script src="([^"]+)"', html)
        self.assertLess(srcs.index("account.js"), srcs.index("repeats.js"))
        self.assertLess(srcs.index("repeats.js"), srcs.index("app.js"))
        self.assertIn("PFML.ready.then(boot)", read("repeats.js"))

    def test_app_js_fills_its_header(self):
        boot = read("app.js").split("function boot() {", 1)[1].split("\n  }\n", 1)[0]
        branch = boot.split('page === "repeats"', 1)[1].split("}", 1)[0]
        self.assertIn("renderNav(index, page)", branch)

    def test_it_reads_only_the_small_catalog_not_the_season_files(self):
        js = read("repeats.js")
        self.assertEqual(re.findall(r'loadJSON\("([^"]+)"\)', js), ["catalog.json"])

    def test_every_element_it_looks_up_exists(self):
        html = read("repeats.html")
        for el_id in sorted(set(re.findall(r'\$\("(\w+)"\)', read("repeats.js")))):
            with self.subTest(el_id):
                self.assertIn(f'id="{el_id}"', html)

    def test_reachable_from_the_menu_and_the_submit_page(self):
        self.assertIn('href="repeats">Repeat checker', read("account.js"))
        self.assertIn('href="repeats"', read("submit.html"))

    def test_each_result_links_to_its_round_page_by_clean_address(self):
        row = read("repeats.js").split("function row(x) {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn('"round?s=" + encodeURIComponent(r.season) + "&r=" + encodeURIComponent(r.id)', row)

    def test_a_band_with_a_comma_in_its_name_is_still_found(self):
        # Measured 2026-10-19: Music League's export splits "Earth, Wind &
        # Fire" into "Earth" and "Wind & Fire", so searching the band's name
        # found nothing until the whole artist line was searched too.
        prep = read("repeats.js").split("function prepare(cat) {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn('artistWords: t.artists.map(words).concat([words(t.artists.join(" "))])', prep)

    def test_the_search_is_kept_in_the_address(self):
        js = read("repeats.js")
        self.assertIn('new URLSearchParams(location.search).get("q")', js)
        self.assertIn("history.replaceState(", js)


if __name__ == "__main__":
    unittest.main()
