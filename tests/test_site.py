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
# The one third-party script, pinned by version and by hash. Measured
# 2026-10-22: jsDelivr's file, the npm tarball's and jsDelivr's own API hash
# all agree. A new version needs a new hash: tests/test_live_cdn.py.
SUPABASE_JS_URL = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.116.0/dist/umd/supabase.js"
SUPABASE_JS_INTEGRITY = "sha384-iLddHTLokph6Omwoyid4XKxHaWa6w41BnoEj0q5oOrzmYPpHIKt1wyjReA7s//pP"
MEMBER_PAGES = ["index.html", "career.html", "round.html", "season.template.html", "profile.html", "submit.html", "repeats.html",
                "commissioner.html"]
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


def read_root(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


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

    def test_summary_sits_above_the_section_switch(self):
        # the at-a-glance list first, then a pointer to the details, then
        # the three section pills, all in the intro
        hero = re.search(r'<section class="hero">(.*?)</section>', read("features.html"), re.S).group(1)
        summary, lead, modes = hero.find('<ul class="summary"'), hero.find('class="modes-lead"'), hero.find('<nav class="modes"')
        self.assertTrue(0 <= summary < lead < modes, (summary, lead, modes))
        self.assertGreaterEqual(hero[summary:lead].count("<li>"), 5)

    def test_links_back_to_the_site(self):
        hrefs = [a.get("href") for a in self.page.find("a")]
        self.assertIn("./", hrefs)


class CleanAddresses(unittest.TestCase):
    """No address on the site shows ".html". GitHub Pages serves /career
    from career.html, query strings included (measured 2026-09-22), so
    links use the clean form, and a page reached at an old .html address
    (a bookmark) tidies its own address bar."""

    PAGES_JS = ["app.js", "rounds.js", "account.js", "auth.js"]
    TIDY = 'location.pathname.replace(/\\.html$/i, "").replace(/\\/index$/i, "/") + location.search + location.hash'

    def test_no_link_or_url_the_site_builds_ends_in_html(self):
        # a ".html" right before a quote, ? or # is a link or URL being
        # built; prose in comments ("career.html still loads") isn't
        for name in self.PAGES_JS + [p.name for p in SITE.glob("*.html")]:
            with self.subTest(name):
                # (?<!\\) spares the tidy-up's own regex, /\.html$/
                self.assertEqual(re.findall(r"(?<!\\)\.html(?=[\"'?#])", read(name)), [])

    def test_every_page_tidies_an_old_html_address(self):
        for name in ("auth.js", "features.html", "privacy.html"):
            with self.subTest(name):
                self.assertIn(self.TIDY, read(name))
        # member pages all load auth.js; the tidy-up runs before sign-in
        # reads or stores the address, and before the Supabase client
        auth = read("auth.js")
        self.assertLess(auth.index(self.TIDY), auth.index("stashInviteFromUrl();"))
        self.assertLess(auth.index(self.TIDY), auth.index("createClient("))
        for name in MEMBER_PAGES:
            self.assertIn('<script src="auth.js"></script>', read(name), name)


class LocalPreviewServer(unittest.TestCase):
    """scripts/serve.py: clean links like /career work locally too."""

    def test_clean_paths_serve_the_html_file_and_real_files_stay_as_they_are(self):
        import threading
        import urllib.request
        from functools import partial
        import http.server
        sys_path = str(ROOT / "scripts")
        import sys as _sys
        if sys_path not in _sys.path:
            _sys.path.insert(0, sys_path)
        import serve
        class Quiet(serve.CleanUrlHandler):
            def log_message(self, *a): pass
        handler = partial(Quiet, directory=str(SITE))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            def get(path):
                with urllib.request.urlopen(base + path) as r:
                    return r.status, r.read().decode("utf-8")
            status, body = get("/career")
            self.assertEqual(status, 200)
            self.assertIn("<title>PFML - All-Time</title>", body)
            status, body = get("/round?s=season1&r=x")
            self.assertEqual(status, 200)
            self.assertIn("<title>PFML - Round</title>", body, "query strings kept")
            status, body = get("/career.html")
            self.assertIn("<title>PFML - All-Time</title>", body, "old .html addresses still work")
            status, body = get("/app.js")
            self.assertIn("function renderNav", body)
        finally:
            server.shutdown()
            server.server_close()


class Linking(unittest.TestCase):
    def test_the_features_page_is_in_the_menu_not_the_footers(self):
        # moved from every footer to the initials menu (2026-10-25); the
        # sign-in card keeps its link, since a signed-out visitor has no menu
        build = js_function(read("account.js"), "function build(member)")
        self.assertIn('<a class="acct-item" href="features">Site features</a>', build)
        for name in MEMBER_PAGES + ["privacy.html"]:
            footer = read(name).split("<footer", 1)[1].split("</footer>", 1)[0]
            self.assertNotIn('href="features"', footer, name)
        gate = js_function(read("auth.js"), "function showGate(title, bodyHtml, actions)")
        self.assertIn('<a href="features">', gate)

    def test_privacy_is_linked_from_every_page_and_the_sign_in_card(self):
        # A signed-out visitor sees only the sign-in card (every other
        # element is hidden while gated), so the card needs the link too.
        for name in MEMBER_PAGES + ["features.html"]:
            hrefs = [a.get("href") for a in Page(read(name)).find("a")]
            self.assertIn("privacy", hrefs, name)
        self.assertIn("./", [a.get("href") for a in Page(read("privacy.html")).find("a")])
        gate = js_function(read("auth.js"), "function showGate(title, bodyHtml, actions)")
        self.assertIn('<a href="privacy">Privacy and Security</a>', gate)

    def test_the_round_7_crossword_is_gone(self):
        # retired 2026-10-25: its page, script and styles, and nothing points at it
        for name in ("round7hint2.html", "crossword.js"):
            self.assertFalse((SITE / name).exists(), name)
        for path in sorted(SITE.glob("*.*")):
            if path.suffix in (".html", ".js", ".css"):
                with self.subTest(path.name):
                    self.assertNotRegex(path.read_text(encoding="utf-8"), r"(?i)round7hint|crossword|\.xw-")

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

    def test_bar_says_season_standings(self):
        # "Standings" -> "Season Standings": distinguishes it from Career's
        # own "All-time standings", which keeps its own wording.
        template = read("season.template.html")
        bar = re.search(r'id="standBar"(.*?)id="standPanel"', template, re.S).group(1)
        self.assertIn("Season Standings", bar)


class RoundSwitcher(unittest.TestCase):
    """The round page's jump-to-round dropdown (rounds.js renders it; there
    is no static markup to read, round.html only holds a loading
    placeholder, so these are structural checks on the source, not a run
    of the code -- see CLAUDE.md on what this suite can't cover."""

    def test_every_round_becomes_one_option_wired_to_roundUrl(self):
        js = read("rounds.js")
        self.assertIn("function roundJumpHtml(d, i)", js)
        self.assertIn("roundJumpHtml(d, i) +", js, "the function must actually be called when the header is built")
        self.assertIn('id="rpJump"', js)
        self.assertIn("<select", js)
        # every round in the season, not just the one before/after
        self.assertIn("d.rounds.map(function (r, k)", js)
        self.assertIn("k === i", js, "the current round is preselected")

    def test_choosing_a_round_navigates_there(self):
        js = read("rounds.js")
        self.assertIn('getElementById("rpJump")', js)
        self.assertIn('addEventListener("change"', js)
        self.assertIn("location.href = roundUrl(d.key, jump.value)", js)

    def test_dropdown_sits_at_the_top_of_the_page(self):
        # right after the back link, before the round's own heading
        js = read("rounds.js")
        m = re.search(r'"rp-back".*?roundJumpHtml\(d, i\).*?"rp-kicker"', js, re.S)
        self.assertIsNotNone(m, "roundJumpHtml runs between the back link and the kicker line")


class ReactionPicker(unittest.TestCase):
    """The round page's reaction picker: the original 6 "quick" reactions
    (stored the same way real comment_reactions rows already are, so old
    and new reactions of those 6 still count together) plus a searchable
    grid of the wider Unicode emoji set from site/emoji-data.js."""

    LEGACY = ["fire", "laugh", "hundred", "eyes", "grimace", "heart"]
    LEGACY_GLYPHS = {"\U0001F525", "\U0001F602", "\U0001F4AF", "\U0001F440", "\U0001F62C", "❤️"}

    def test_quick_row_still_uses_the_original_six_names(self):
        # These are the values already sitting in the live comment_reactions
        # table; changing them would split old and new reactions in two.
        js = read("rounds.js")
        m = re.search(r"var LEGACY_REACT_ORDER = \[(.*?)\];", js)
        self.assertIsNotNone(m)
        names = re.findall(r'"(\w+)"', m.group(1))
        self.assertEqual(names, self.LEGACY)

    def test_trigger_icon_is_not_a_unicode_emoji_character(self):
        # The old trigger, the text "+☺" (a smiley character), let each
        # device's emoji font choose how to draw it -- full colour on
        # iOS/Android, not the flat icon it looked like on desktop.
        js = read("rounds.js")
        self.assertNotIn("&#9786;", js)
        self.assertIn("ADD_REACTION_ICON", js)
        self.assertIn('class="cm-add-icon"', js)
        self.assertIn("<svg", js)

    @staticmethod
    def function(js, signature):
        return js.split(signature, 1)[1].split("\n  }\n", 1)[0]

    def test_picker_can_always_be_closed(self):
        # At 375px the "More" bottom sheet covers its own comment, "add a
        # reaction" button included, so it needs a way out of its own.
        js = read("rounds.js")
        more = self.function(js, "function morePickerHtml(c)")
        self.assertIn('class="cm-picker-close" data-act="picker"', more)
        self.assertIn('document.addEventListener("click", closePickerFromOutside)', js)
        self.assertIn('document.addEventListener("keydown", closePickerOnEscape)', js)
        self.assertIn('ev.key === "Escape"', js)

    def test_add_button_opens_only_the_quick_six_and_more(self):
        # Building all ~1,900 emoji on every tap took about a second
        # (measured, desktop Chrome). The quick row must not touch them.
        js = read("rounds.js")
        quick = self.function(js, "function quickPickerHtml(reacts)")
        self.assertIn("LEGACY_REACT_ORDER.map", quick)
        self.assertIn('data-act="more"', quick)
        for heavy in ("emojiData(", "emojiIndex(", "cm-emoji-btn", "cm-emoji-grid"):
            self.assertNotIn(heavy, quick)
        self.assertIn('act === "more"', js)
        self.assertIn("state.pickerMore ? morePickerHtml(c) : quickPickerHtml(reacts)", js)

    def test_search_draws_only_the_matches_and_never_touches_the_box(self):
        # Regression: the search used to set `hidden` on every button, which
        # the buttons' own CSS `display` overrode, so nothing ever vanished
        # (measured: 1,907 "hidden", all 1,908 still shown). Drawing only
        # the matches can't be undone by CSS. The search box itself must
        # never be redrawn, or it loses focus and the cursor mid-type.
        js = read("rounds.js")
        search = self.function(js, "function onEmojiSearch(ev)")
        self.assertIn("fillEmojiGrid(", search)
        fill = self.function(js, "function fillEmojiGrid(picker, id)")
        self.assertIn("searchEmoji(query)", fill)
        self.assertIn("grid.innerHTML =", fill)
        self.assertNotIn("picker.innerHTML", fill)
        self.assertNotIn("input.value =", fill)
        picker_code = js.split("function emojiData()", 1)[1].split("function socialHtml(c)", 1)[0]
        picker_code += search
        self.assertNotIn(".hidden =", picker_code, "hiding with the hidden attribute loses to CSS display rules")

    def test_search_and_categories_draw_a_bounded_amount(self):
        js = read("rounds.js")
        fill = self.function(js, "function fillEmojiGrid(picker, id)")
        self.assertIn("found.slice(0, SEARCH_LIMIT)", fill)
        self.assertIn("e.group === state.emojiGroup", fill, "no query: one category, not all of them")
        self.assertIn("list.slice(0, FIRST_SCREEN)", fill)
        self.assertIn("grid.fillToken === token", fill, "a newer keystroke cancels the rest of an older draw")

    def test_quick_six_can_be_found_in_the_more_panel_under_their_old_names(self):
        # They're left out of emoji-data.js; LEGACY_META puts them back into
        # a real category, still storing the old name.
        js = read("rounds.js")
        meta = re.search(r"var LEGACY_META = \{(.*?)\};", js, re.S).group(1)
        entries = re.findall(r'(\w+): \["([^"]+)", "([^"]+)"\]', meta)
        self.assertEqual([k for k, _, _ in entries], self.LEGACY)
        groups = set(re.findall(r'"([^"]+)"', read("emoji-data.js").split("window.PFML_EMOJI_GROUPS = [", 1)[1].split("];", 1)[0]))
        for key, _name, group in entries:
            self.assertIn(group, groups, key)
        index = self.function(js, "function emojiIndex()")
        self.assertIn("entry(esc(reactionGlyph(k)), k,", index, "stored by its old name, not the glyph")

    def test_search_box_does_not_make_ios_zoom(self):
        # iOS Safari/Chrome zoom the whole page into any input under 16px.
        bodies = css_rules(read("style.css"), ".cm-emoji-search")
        sizes = [m for b in bodies for m in re.findall(r"font-size:\s*(\d+)px", b)]
        self.assertTrue(sizes, "the search box needs an explicit px font size")
        self.assertTrue(all(int(s) >= 16 for s in sizes), sizes)

    def test_data_file_is_a_large_deduplicated_set_without_the_quick_six(self):
        data = read("emoji-data.js")
        self.assertIn("window.PFML_EMOJI_GROUPS = [", data)
        self.assertIn("window.PFML_EMOJI_DATA = [", data)
        rows = re.findall(r'^\s*\["([^"]+)","([^"]*)",(\d+)\],$', data, re.M)
        self.assertGreater(len(rows), 1000, "expected the broad Unicode set, not a short hand-picked list")
        glyphs = [g for g, _name, _group in rows]
        self.assertEqual(len(glyphs), len(set(glyphs)), "a repeated emoji would make two chips for one reaction")
        self.assertTrue(self.LEGACY_GLYPHS.isdisjoint(glyphs),
                        "a quick-row emoji also in the searchable grid would store two different values for it")

    def test_round_page_loads_the_data_file_without_blocking(self):
        html = read("round.html")
        self.assertIn('<script src="emoji-data.js" defer></script>', html)
        # season pages never open a picker; only round.html needs the data
        self.assertNotIn("emoji-data.js", read("season.template.html"))

    def test_grid_hover_is_also_guarded_to_devices_that_actually_hover(self):
        # Same reason as Standings rows: .cm-emoji-grid scrolls under a
        # finger too, on the phone-width bottom sheet.
        css = strip_media(read("style.css"), "(hover: hover)")
        for sel, _ in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            for part in sel.split(","):
                if ":hover" in part:
                    self.assertNotRegex(part, r"cm-pick|cm-emoji-btn|cm-emoji-tab|cm-more",
                                        f"{part.strip()} applies on touch screens too")


class VoterBands(unittest.TestCase):
    def test_each_voter_heading_sits_on_a_magenta_band(self):
        # Members couldn't tell where one voter's comment and replies ended
        # and the next voter began; the name/points row carries a faint
        # magenta gradient across the card's full width.
        css = read("style.css")
        base = [b for b in css_rules(css, ".rp-vote-head") if "background" in b]
        self.assertEqual(len(base), 1)
        self.assertRegex(base[0], r"linear-gradient\(90deg,\s*rgba\(158,\s*0,\s*196")
        self.assertRegex(base[0], r"margin:\s*0 -20px", "the band runs edge to edge, not inset by the card's padding")
        # each phone-width block runs to the first "}" at column 0
        blocks = [b.split("\n}", 1)[0] for b in re.split(r"@media \(max-width: 620px\)\s*\{", css)[1:]]
        phone = [r for b in blocks for r in re.findall(r"\.rp-vote-head\s*\{([^}]*)\}", b)]
        self.assertTrue(phone, "the band is restated for phones")
        self.assertIn("margin: 0 -16px", phone[0], "and edge to edge at phone widths too")


def js_function(js, signature):
    return js.split(signature, 1)[1].split("\n  }\n", 1)[0]


class AccountCorner(unittest.TestCase):
    """account.js: the header's inbox and initials menu, on every page."""

    def test_every_member_page_loads_it_between_auth_and_the_page_code(self):
        # app.js and rounds.js use window.PFML and account.js's helpers
        # without checking they exist, so this order is what keeps them safe.
        for name in MEMBER_PAGES:
            srcs = [a.get("src") for a in Page(read(name)).find("script") if a.get("src")]
            with self.subTest(name):
                self.assertIn("account.js", srcs)
                self.assertLess(srcs.index("config.js"), srcs.index("auth.js"))
                self.assertLess(srcs.index("auth.js"), srcs.index("account.js"))
                self.assertLess(srcs.index("account.js"), srcs.index("app.js"))
                if "rounds.js" in srcs:
                    self.assertLess(srcs.index("account.js"), srcs.index("rounds.js"))
                    self.assertLess(srcs.index("rounds.js"), srcs.index("app.js"))

    def test_season_and_round_pages_load_rounds_js_which_app_js_calls(self):
        for name in ("season.template.html", "round.html"):
            self.assertIn('<script src="rounds.js"></script>', read(name), name)

    def test_sign_out_and_my_profile_live_in_the_initials_menu(self):
        js = read("account.js")
        build = js_function(js, "function build(member)")
        menu = build.split('id="acctMenu"', 1)[1].split('id="acctInbox"', 1)[0]
        self.assertIn('href="profile">My profile', menu)
        self.assertIn('id="acctSignOut">Sign out', menu)
        self.assertIn("PFML.signOut()", build)
        self.assertIn("avatar(member.competitorId, member.name)", build.split('id="acctMeBtn"', 1)[1].split("</button>", 1)[0],
                      "the header shows the initials bubble, not the name")
        self.assertTrue((SITE / "profile.html").exists())
        # and nowhere else: the old name + "Sign out" link in auth.js is gone
        auth = read("auth.js")
        self.assertNotIn("whoami", auth)
        self.assertNotIn("whoami", read("style.css"))

    def test_avatars_reaction_glyphs_and_times_have_one_definition(self):
        # The same person, reaction and time must look the same in the
        # header, the inbox, a round page and a profile. Two copies of
        # when() had drifted: a reply a few days old read as a date on its
        # round page but "3d ago" in the inbox. So account.js has the only
        # copy of each, and shares it.
        account = read("account.js")
        for name in ("avatar", "reactionGlyph", "when", "translationHtml"):
            self.assertIn(f"function {name}(", account)
            self.assertIn(f"PFML.{name} = {name};", account)
        self.assertIn("var LEGACY_REACT = {", account)
        for page_js in ("rounds.js", "app.js"):
            js = read(page_js)
            for name in ("function avatar(", "function reactionGlyph(", "function when(",
                         "function translationHtml(", "var LEGACY_REACT = {"):
                self.assertNotIn(name, js, f"{page_js} has its own {name}")
        self.assertIn("var avatar = PFML.avatar, reactionGlyph = PFML.reactionGlyph, when = PFML.when,\n"
                      "      translationHtml = PFML.translationHtml;", read("rounds.js"))

    def test_inbox_asks_for_this_players_comments_and_not_their_own_reactions(self):
        inbox = js_function(read("auth.js"), "inbox: function (competitorId, limit)")
        self.assertIn('var suffix = "%|" + competitorId', inbox, "comment ids end |<voter id>")
        self.assertEqual(inbox.count('.like("comment_id", suffix)'), 2)
        self.assertEqual(inbox.count('.neq("user_id", uid)'), 2)

    def test_seen_mark_is_read_apart_from_signing_in(self):
        # If the migration hasn't run, a sign-in query naming inbox_seen_at
        # would fail and lock every member out. Only the inbox may ask.
        auth = read("auth.js")
        self.assertNotIn("inbox_seen_at", js_function(auth, "function membership(userId)"))
        self.assertIn('.select("inbox_seen_at")', auth)
        self.assertIn('rpc("mark_inbox_seen")', auth)
        self.assertIn("inboxSeenAt().catch(", read("account.js"), "a missing column costs the count, not the inbox")

    def test_popovers_hide_despite_their_display_rules(self):
        # The emoji search lesson: a class with its own display beats the
        # hidden attribute unless [hidden] is restated for it.
        css = read("style.css")
        js = read("account.js")
        toggled = set(re.findall(r'\$\("(\w+)"\)\.hidden =|(\w+)\.hidden =', js))
        self.assertTrue(toggled, "account.js shows and hides its popovers with hidden")
        for sel in (".acct-badge", ".acct-pop"):
            with self.subTest(sel):
                if any(re.search(r"(^|[\s;])display\s*:", b) for b in css_rules(css, sel)):
                    self.assertTrue(any("display: none" in b for b in css_rules(css, sel + "[hidden]")),
                                    f"{sel} sets display, so {sel}[hidden] must say display: none")
        self.assertTrue(any("display" in b for b in css_rules(css, ".acct-pop")), "the popovers are flex boxes")


class InboxLinks(unittest.TestCase):
    def test_inbox_links_name_the_comment_and_open_replies(self):
        item = js_function(read("account.js"), "function itemHtml(item, ctx, fresh)")
        self.assertIn('"&c=" + encodeURIComponent(item.commentId)', item)
        self.assertIn('item.kind === "reply" ? "&thread=1"', item)

    def test_round_page_scrolls_to_that_comment_after_each_render(self):
        js = read("rounds.js")
        page = js_function(js, "function renderRoundPage(d, roundId)")
        self.assertIn('params.get("c")', page)
        self.assertIn('params.get("thread") === "1"', page)
        self.assertEqual(page.count("showTarget(target)"), 2, "again after the member layer changes the heights")
        self.assertIn('behavior: "instant"', js_function(js, "function showTarget(id)"))


class ProfilePage(unittest.TestCase):
    def test_boot_routes_the_profile_page(self):
        self.assertIn('data-page="profile"', read("profile.html"))
        self.assertIn('page === "profile"', read("app.js"))

    def test_every_element_the_code_fills_exists_on_the_page(self):
        js = read("app.js")
        code = js.split("/* ---- profile page", 1)[1].split("/* ---- round page", 1)[0]
        ids = set(re.findall(r'\$\("(\w+)"\)', code)) | set(re.findall(r'setBlock\("(\w+)"', code))
        ids |= {i for group in re.findall(r"\[([^\]]*)\]\.forEach", code) for i in re.findall(r'"([\w-]+)"', group)}
        ids -= {"pfPick", "pfReacts"}   # created by the code itself
        page = read("profile.html")
        self.assertTrue(ids)
        for i in sorted(ids):
            self.assertIn(f'id="{i}"', page, i)

    def test_career_tiles_are_six_in_three_columns_or_two_on_phones(self):
        career = js_function(read("app.js"), "function renderProfileCareer(c, p, prof)")
        labels = re.findall(r'^\s*(?:if \(prof\) )?g\.appendChild\(careerTile\("([^"]+)"', career, re.M)
        self.assertEqual(labels, ["Career Score", "Total points", "Rounds won", "Top-3 rate",
                                  "Tracks submitted", "Points given"], "two full rows of three, three of two")
        self.assertIn('el("div", "hl-grid hl-pair pf-tiles")', career)
        css = read("style.css")
        self.assertIn("grid-template-columns: repeat(3, minmax(0, 1fr))", " ".join(css_rules(css, ".pf-tiles")))
        # two per row on phones comes from .hl-pair (TwoPerRowOnPhones)

    def test_profile_defaults_to_the_signed_in_member(self):
        init = js_function(read("app.js"), "function initProfile()")
        self.assertIn('get("p") || myId', init)

    def test_career_names_link_to_profiles(self):
        js = read("app.js")
        self.assertIn("careerRowHtml(p)", js_function(js, "function renderCareerStandings(c)"))
        self.assertIn("who(p.name, p.id)", js_function(js, "function careerRowHtml(p)"))


def phone_rules(css, selector):
    """Declaration blocks for `selector` inside the max-width: 620px blocks."""
    blocks = [b.split("\n}", 1)[0] for b in re.split(r"@media \(max-width: 620px\)\s*\{", css.replace("\r\n", "\n"))[1:]]
    return [r for b in blocks for r in re.findall(re.escape(selector) + r"\s*\{([^}]*)\}", b)]


class TwoPerRowOnPhones(unittest.TestCase):
    GRIDS = {
        "function renderProfileCareer(c, p, prof)": "profile Career",
        "function renderProfileComments(cm, id)": "profile Comments",
        "function renderCareerHighlights(c)": "League Highlights",
        "function renderCareerComments(c)": "all-time comment awards",
    }

    def test_these_tile_grids_are_marked_two_per_row(self):
        js = read("app.js")
        for sig, label in self.GRIDS.items():
            with self.subTest(label):
                self.assertRegex(js_function(js, sig), r'el\("div", "hl-grid hl-pair[" ]')

    def test_phone_rule_makes_them_two_columns(self):
        rules = phone_rules(read("style.css"), ".hl-pair")
        self.assertTrue(rules and "repeat(2, minmax(0, 1fr))" in rules[0])

    def test_all_talk_award_is_gone_from_the_all_time_page(self):
        # Asked for: not needed, and it leaves 8 awards, four even rows of two.
        comments = js_function(read("app.js"), "function renderCareerComments(c)")
        self.assertNotIn("all-talk", comments)
        awards = re.findall(r'g\.appendChild\(careerTile\("([^"]+)"', comments)
        self.assertEqual(len(awards), 8, awards)


class HeaderNav(unittest.TestCase):
    """Home | one season pill | All-Time."""

    def test_order_is_home_season_pill_all_time(self):
        nav = js_function(read("app.js"), "function renderNav(index, activeKey)")
        home, pill, alltime = nav.index('home.textContent = "Home"'), nav.index("seasonPicker(index, activeKey)"), nav.index('"All-Time"')
        self.assertLess(home, pill)
        self.assertLess(pill, alltime)
        self.assertNotIn("index.seasons.forEach", nav, "no tab per season any more")

    def test_pill_shows_this_season_or_the_live_one_and_lists_newest_first(self):
        pick = js_function(read("app.js"), "function seasonPicker(index, activeKey)")
        self.assertIn("var shownKey = onSeason ? activeKey : index.currentSeason", pick)
        self.assertIn("index.seasons.slice().reverse().map", pick)
        self.assertIn('ev.key === "Escape"', pick)

    def test_menu_hides_despite_its_display_rule(self):
        css = read("style.css")
        self.assertTrue(any("display" in b for b in css_rules(css, ".season-menu")))
        self.assertTrue(any("display: none" in b for b in css_rules(css, ".season-menu[hidden]")))

    def test_all_time_page_order(self):
        # League Highlights, then All-time standings, then the comments
        sections = [a.get("id") for a in Page(read("career.html")).find("section") if a.get("id")]
        self.assertEqual(sections, ["block-highlights", "block-standings", "block-comments"])

    def test_all_time_page_names(self):
        page = read("career.html")
        self.assertIn("<h1>All-Time League Stats</h1>", page)
        self.assertIn("<h2>League Highlights</h2>", page)
        self.assertNotIn("Career highlights", page)


class Replies(unittest.TestCase):
    def test_reply_is_a_pill_not_underlined_link_text(self):
        js = read("rounds.js")
        social = js_function(js, "function socialHtml(c)")
        self.assertIn('class="cm-chip cm-reply-btn', social)
        self.assertIn("REPLY_ICON", social)
        self.assertNotIn("cm-link", js)
        self.assertNotIn(".cm-link", read("style.css"))

    def test_composer_sends_only_with_text_and_grows(self):
        js = read("rounds.js")
        social = js_function(js, "function socialHtml(c)")
        self.assertIn("""class="cm-send" aria-label="Send reply"' + (draft.trim() ? "" : " disabled")""", social)
        self.assertIn('rows="1"', social)
        self.assertIn('addEventListener("input", onReplyInput)', js)
        self.assertIn('addEventListener("keydown", onReplyKey)', js)
        grow = js_function(js, "function onReplyInput(ev)")
        self.assertIn("fitReplyBox(ta)", grow)
        self.assertIn('ta.style.height = ta.scrollHeight + "px"', js_function(js, "function fitReplyBox(ta)"))
        self.assertIn("send.disabled = !ta.value.trim()", grow)
        self.assertIn("(ev.ctrlKey || ev.metaKey)", js_function(js, "function onReplyKey(ev)"))

    def test_a_draft_survives_a_redraw_of_its_comment(self):
        # A vote or reaction on the same comment redraws it, and used to
        # replace the reply box with an empty one mid-sentence.
        js = read("rounds.js")
        self.assertIn("state.drafts[id] = ta.value", js_function(js, "function onReplyInput(ev)"))
        social = js_function(js, "function socialHtml(c)")
        self.assertIn('var draft = state.drafts[c.id] || "";', social)
        self.assertIn('+ esc(draft) + "</textarea>"', social)
        redraw = js_function(js, "function rerenderVote(id)")
        self.assertIn("box.focus();", redraw)
        self.assertIn("box.setSelectionRange(typing.selectionStart, typing.selectionEnd)", redraw)

    def test_a_draft_is_dropped_only_once_the_reply_is_saved(self):
        submit = js_function(read("rounds.js"), "function onSubmit(ev)")
        self.assertIn("api().addReply(id, text).then(function () { delete state.drafts[id]; })", submit)

    def test_reply_box_does_not_make_ios_zoom(self):
        sizes = [m for b in css_rules(read("style.css"), ".cm-compose textarea") for m in re.findall(r"font-size:\s*(\d+)px", b)]
        self.assertTrue(sizes and all(int(s) >= 16 for s in sizes), sizes)


class NamesLinkToProfiles(unittest.TestCase):
    def test_round_page_names_are_profile_links(self):
        js = read("rounds.js")
        self.assertIn("personLink(row.voterId, row.name)", js_function(js, "function voteHtml(row)"))
        self.assertIn("personLink(s.submitterId, s.submitterName)", js_function(js, "function trackHtml(s, tiedPlaces)"))
        page = js_function(js, "function renderRoundPage(d, roundId)")
        self.assertIn("personLink(top[0].submitterId, top[0].submitterName)", page)
        self.assertIn("personLink(who.competitorId, memberName(r.user_id))", js_function(js, "function socialHtml(c)"))
        link = js_function(js, "function personLink(id, name)")
        self.assertIn('\'<a class="plink" href="profile?p=\' + encodeURIComponent(id)', link)

    def test_app_helper_links_known_names_and_leaves_others_plain(self):
        js = read("app.js")
        helper = js_function(js, "function who(name, id)")
        self.assertIn("id = id || profileIds[name]", helper)
        self.assertIn("if (!id) return esc(name);", helper)
        self.assertIn('\'<a class="plink" href="profile?p=\' + encodeURIComponent(id)', helper)
        # every page type that shows names teaches it who's who first
        self.assertIn("knowPeople(d.competitors)", js_function(js, "function initSeason(key)"))
        self.assertIn("knowPeople(c.players)", js_function(js, "function initCareer()"))
        self.assertIn("knowPeople(c.players)", js_function(js, "function initProfile()"))

    # function -> a call that must be in it (one per kind of name spot)
    SPOTS = {
        "function tieLine(ties)": "return who(n);",
        "function renderFocus(d)": "titleEl.innerHTML = who(nameOf(d, selected[0]), selected[0])",
        "function renderFocusGroup(d, ids, host)": "who(r.name, r.id)",
        "function renderFocusIndividual(d, id, host)": "who(fansOf[0].voterName, fansOf[0].voterId)",
        "function renderHighlights(d)": "who(h.biggestFan.voterName) + \" &rarr; \" + who(h.biggestFan.submitterName)",
        "function trackRow(s, pos, showRound, highlightSet)": "who(s.submitterName, s.submitterId)",
        "function renderTasteGrid(d, people, host, phoneToo)": "who(voter.name, voter.id)",
        "function renderVoters(d)": "who(v.name, v.id)",
        "function commentQuote(c, label, stats)": "who(c.name)",
        "function renderComments(d)": "who(summary.chattiest.name)",
        "function renderCareerComments(c)": "who(s.mostTalkative.name)",
        "function renderCareerHighlights(c)": "who(h.topScore.name)",
    }

    def test_names_link_across_season_and_all_time_pages(self):
        js = read("app.js")
        for sig, call in self.SPOTS.items():
            with self.subTest(sig):
                self.assertIn(call, js_function(js, sig))

    def test_no_link_inside_a_tap_target(self):
        # A Standings row is itself a button (tap = compare) and the
        # collapsed bar folds the section: a link inside either fights the
        # tap and reads badly to screen readers. The focus panel links instead.
        js = read("app.js")
        self.assertNotIn("who(", js_function(js, "function renderStandings(d)"))
        self.assertNotIn("who(", js_function(js, "function renderStandingsSummary(d)"))
        self.assertNotIn("who(", js_function(js, "function renderStandingsFilters(d)"))

    def test_links_look_like_the_text_they_replace(self):
        # Not obvious: same colour and no underline, even on hover, which
        # sticks after a tap on touch screens.
        css = read("style.css")
        base = css_rules(css, ".plink:hover")
        self.assertTrue(any("color: inherit" in b and "text-decoration: none" in b for b in base))


class CareerScoreTable(unittest.TestCase):
    def test_columns_add_up_to_the_score(self):
        cols = read("app.js").split("var CAREER_COLUMNS = [", 1)[1].split("];", 1)[0]
        self.assertEqual(re.findall(r'key: "(\w+)"', cols),
                         ["name", "careerScore", "avgSeason", "roundBonus", "seasonBonus", "rounds"])
        self.assertEqual(re.findall(r'label: "([^"]+)"', cols),
                         ["Player", "Score", "Avg season", "Round Podium Pts", "Season Podium Pts", "Rounds"])

    def test_unscored_players_have_no_parts_to_sort_by(self):
        # One round would otherwise top "Avg season" at 400-odd.
        value = js_function(read("app.js"), "function careerFieldValue(p, key)")
        self.assertIn('if (key === "rounds") return p.rounds;', value)
        self.assertIn("if (!p.rated) return null;", value)
        row = js_function(read("app.js"), "function careerRowHtml(p)")
        self.assertIn("if (!p.rated)", row)
        self.assertIn("needs ", row)

    def test_note_and_profile_use_the_formula_from_the_data(self):
        js = read("app.js")
        init = js_function(js, "function initCareer()")
        for part in ("f.perRoundScale", 'f.roundBonus.join("/")', 'f.seasonBonus.join("/")', "f.minRounds"):
            self.assertIn(part, init)
        rank = js_function(js, "function careerRank(players, p)")
        self.assertIn("if (!p.rated) return null;", rank)
        self.assertIn("var rated = players.filter(function (x) { return x.rated; });", rank)


class QuoteAwardsPage(unittest.TestCase):
    def test_all_time_page_shows_every_award_with_longest(self):
        js = read("app.js")
        self.assertIn("renderQuoteAwards(s, host);", js_function(js, "function renderCareerComments(c)"))
        cards = js_function(js, "function renderQuoteAwards(s, host)")
        for key in ("s.longestComment", "q.shortest", "q.loudest", "q.mostExcited", "q.mostQuestions",
                    "q.mostEmoji", "q.mostWordsForZero"):
            self.assertIn("[" + key + ",", cards)
        # clipped first, then measured: measured unclipped, nothing ever overflows
        clip, measure = cards.index('bq.classList.add("is-clipped")'), cards.index("bq.scrollHeight <= bq.clientHeight")
        self.assertLess(clip, measure)
        self.assertIn('bq.classList.remove("is-clipped")', cards, "and unclipped again when it fits")

    def test_clipping_and_toggle_css(self):
        css = read("style.css")
        self.assertIn("max-height", " ".join(css_rules(css, ".quote-grid blockquote.is-clipped")))
        self.assertIn("max-height: none", " ".join(css_rules(css, ".quote-grid blockquote.is-open")))


class AvatarStaysCentred(unittest.TestCase):
    def test_no_rule_in_the_menu_turns_the_avatar_into_a_column(self):
        # Regression: ".acct-menu-head span { display: flex; flex-direction:
        # column }" meant for the name also hit the avatar (a span), sliding
        # its initials to the top left when the menu opened.
        css = read("style.css")
        self.assertEqual(css_rules(css, ".acct-menu-head span"), [])
        self.assertIn("flex-direction: column", " ".join(css_rules(css, ".acct-menu-who")))
        self.assertIn('class="acct-menu-who"', js_function(read("account.js"), "function build(member)"))


class PlaylistTiles(unittest.TestCase):
    def test_league_wide_first_then_newest_season_first(self):
        render = js_function(read("app.js"), "function renderPlaylists(pl, stats)")
        league, seasons = render.index("pl.leagueWide"), render.index("(pl.seasons || []).slice().reverse()")
        self.assertLess(league, seasons)
        self.assertIn('el("div", "pl-grid")', render)

    def test_tile_shortens_the_name_and_only_links_when_there_is_a_url(self):
        tile = js_function(read("app.js"), "function playlistTile(item, group, stats)")
        self.assertIn(r'.replace(/^PFML\s*-\s*(S\d+\s*-\s*)?/i, "")', tile)
        self.assertIn('el("div", "pl-tile is-soon", inner)', tile, "no url: a tile that isn't a link")
        self.assertIn('a.target = "_blank"; a.rel = "noopener"', tile)

    def test_tile_shows_track_count_and_running_time_when_known(self):
        js = read("app.js")
        tile = js_function(js, "function playlistTile(item, group, stats)")
        self.assertIn("var st = idm && stats && stats[idm[1]];", tile)
        self.assertIn('!st ? "Open in Spotify" :', tile, "no stats: the old line")
        self.assertIn('<span class="pl-stat">', tile)
        self.assertIn('<span class="pl-out" aria-hidden="true">&nearr;</span>', tile)
        self.assertIn('", opens in Spotify"', tile)
        line = js_function(js, "function playlistStatsParts(st)")
        self.assertIn('plural(st.tracks, "track")', line)
        self.assertIn("runTime(st.durationMs, st.exact)", line)
        run = js_function(js, "function runTime(ms, exact)")
        self.assertIn('if (!exact) return "about "', run, "an estimate says so")
        self.assertIn('PFML.loadJSON("playlist_stats.json").catch(', js_function(js, "function initHome()"))

    def test_phones_stack_the_count_over_the_time(self):
        # side by side, "648 tracks ·" / "about 43 hr" wrapped mid-phrase at 375px
        css = read("style.css")
        phone = [b for block in re.findall(r"@media \(max-width: 620px\) \{(.*?)\n\}", css, re.S)
                 for b in css_rules(block, ".pl-stat")]
        self.assertTrue(any("display: block" in b for b in phone))
        self.assertIn("white-space: nowrap", " ".join(css_rules(css, ".pl-stat")))

    def test_old_chip_styles_are_gone(self):
        css = read("style.css")
        for sel in (".pill.pill-live", ".pill.is-disabled", ".playlist-row", ".playlist-group"):
            self.assertEqual(css_rules(css, sel), [], sel)
        self.assertIn("repeat(4, minmax(0, 1fr))", " ".join(css_rules(css, ".pl-grid")))


class SentimentAwardsPage(unittest.TestCase):
    def test_judged_cards_and_titles_appear_only_with_labels(self):
        js = read("app.js")
        cards = js_function(js, "function renderQuoteAwards(s, host)")
        for key in ("sq.funniest", "sq.wittiest", "sq.angriest", "sq.meanest", "sq.mostHeartfelt", "sq.hottestTake"):
            self.assertIn("[" + key + ",", cards)
        self.assertIn("(s.sentimentAwards && s.sentimentAwards.quotes) || {}", cards)
        self.assertIn('"judged by Claude"', cards)
        self.assertIn("if (judged.length)", cards, "the AI note only when there are AI picks")
        comments = js_function(js, "function renderCareerComments(c)")
        for key in ("classClown", "sweetheart", "grump", "hotTakeArtist"):
            self.assertIn('["' + key + '",', comments)


class ProfileScoreParts(unittest.TestCase):
    def test_profile_shows_score_as_its_parts(self):
        js = read("app.js")
        self.assertIn("scoreParts(c, p)", js_function(js, "function renderProfileCareer(c, p, prof)"))
        parts = js_function(js, "function scoreParts(c, p)")
        for field in ("p.careerScore", "p.avgSeason", "p.roundBonus", "p.seasonBonus"):
            self.assertIn(field, parts)
        self.assertIn("if (!p.rated)", parts)


class AllTimeTables(unittest.TestCase):
    """All-time standings and the all-time comment table on phones: every
    column, scrolling sideways in their box, Player pinned; both sortable."""

    def test_both_tables_scroll_sideways_with_player_pinned(self):
        js = read("app.js")
        self.assertIn('el("div", "framed career-table table-wide")', js_function(js, "function renderCareerStandings(c)"))
        self.assertIn('el("div", "framed table-wide cmt-table-box")', js_function(js, "function renderCareerCommentTable(rows)"))
        css = read("style.css")
        self.assertIn("overflow-x: auto", " ".join(css_rules(css, ".table-wide")))
        pinned = " ".join(css_rules(css, ".table-wide > * > :first-child"))
        self.assertIn("position: sticky", pinned)
        self.assertIn("left: 0", pinned)
        self.assertIn("background: inherit", pinned, "opaque, or scrolled numbers show through the names")
        self.assertIn("min-width: 600px", " ".join(css_rules(css, ".career-table.table-wide > .vrow")))
        self.assertIn("min-width: 800px", " ".join(css_rules(css, ".cmt-table-box > .crow")))

    def test_no_column_is_hidden_from_them(self):
        # Regression: a phone rule for the season Voting table hid every
        # .vrow's 4th cell, which on All-time standings was Season 3 (and
        # "Won" on a profile's seasons); the comment table dropped 4 columns.
        css = read("style.css").replace("\r\n", "\n")
        self.assertNotRegex(css, r"(^|\n)\s*\.vrow > :nth-child\(4\)")
        self.assertIn(".framed:not(.career-table):not(.table-wide) > .vrow > :nth-child(4) { display: none; }", css)
        # every comment table scrolls now, so nothing trims their columns
        self.assertNotIn(".crow > :nth-child(n + 6)", css)

    def test_hint_only_on_phones(self):
        css = read("style.css")
        self.assertTrue(any("display: none" in b for b in css_rules(css, ".table-hint")))
        self.assertTrue(any("display: block" in b for b in phone_rules(css, ".table-hint")))
        js = read("app.js")
        self.assertIn("tableHint(", js_function(js, "function renderCareerStandings(c)"))
        self.assertIn("tableHint(", js_function(js, "function renderCareerComments(c)"))

    def test_comment_table_sorts_by_every_column(self):
        js = read("app.js")
        cols = re.search(r"var COMMENT_COLUMNS = \[(.*?)\];", js, re.S).group(1)
        self.assertEqual(re.findall(r'key: "(\w+)"', cols),
                         ["name", "comments", "commentRate", "meanWords", "medianWords", "zeroPointComments",
                          "exclamationRate", "questionRate", "allCapsRate"])
        table = js_function(js, "function renderCareerCommentTable(rows)")
        self.assertIn("COMMENT_COLUMNS.forEach", table, "every column's heading is a sort button")
        self.assertIn('commentSort.dir = commentSort.dir === "desc" ? "asc" : "desc"', table, "tap again to flip")
        self.assertIn("renderCareerCommentTable(rows);", table)
        self.assertIn('var commentSort = { field: "comments", dir: "desc" }', js, "starts in today's order")

    def test_season_voting_and_comment_tables_scroll_too(self):
        js = read("app.js")
        voters = js_function(js, "function renderVoters(d)")
        self.assertIn('el("div", "framed table-wide voters-box")', voters)
        self.assertIn("tableHint()", voters)
        comments = js_function(js, "function renderComments(d)")
        self.assertIn('el("div", "framed table-wide cmt-table-box cmt-table")', comments)
        self.assertIn("tableHint()", comments)
        self.assertIn("min-width: 480px", " ".join(css_rules(read("style.css"), ".voters-box > .vrow")))

    def test_hint_mentions_sorting_only_where_tables_sort(self):
        js = read("app.js")
        hint = js_function(js, "function tableHint(sortable)")
        self.assertIn('(sortable ? " Tap a heading to sort." : "")', hint)
        self.assertIn("tableHint(true)", js_function(js, "function renderCareerStandings(c)"))
        self.assertIn("tableHint(true)", js_function(js, "function renderCareerComments(c)"))
        self.assertNotIn("tableHint(true)", js_function(js, "function renderVoters(d)"))
        self.assertNotIn("tableHint(true)", js_function(js, "function renderComments(d)"))

    def test_standard_space_above_the_comment_table(self):
        css = read("style.css")
        self.assertIn("margin-top: 18px", " ".join(css_rules(css, ".cmt-table")))


class InboxSchema(unittest.TestCase):
    """schema.sql (new projects) and the migration (the live one) must add
    the same column and function."""

    def migration(self):
        return read_root("supabase/migrations/2026-09-23_inbox_seen.sql")

    def test_both_add_the_seen_column(self):
        for name, sql in (("schema", read_root("supabase/schema.sql")), ("migration", self.migration())):
            with self.subTest(name):
                self.assertIn("alter table public.members add column if not exists inbox_seen_at timestamptz", sql)

    def test_mark_seen_only_touches_the_callers_own_row(self):
        fn = re.compile(r"create or replace function public\.mark_inbox_seen\(\).*?\$\$;", re.S)
        schema_fn = fn.search(read_root("supabase/schema.sql")).group(0)
        self.assertEqual(schema_fn, fn.search(self.migration()).group(0))
        self.assertIn("security definer set search_path = public", schema_fn)
        self.assertIn("set inbox_seen_at = now() where user_id = auth.uid()", schema_fn)
        for sql in (read_root("supabase/schema.sql"), self.migration()):
            self.assertIn("revoke all on function public.mark_inbox_seen() from public, anon;", sql)

    def test_members_still_has_no_update_policy(self):
        # A member able to update their own row could make themselves admin.
        self.assertNotRegex(read_root("supabase/schema.sql"), r"on public\.members\s+for update")


class ReactionsSchema(unittest.TestCase):
    """supabase/schema.sql (fresh installs) and the one-off migration for
    the live project (supabase/migrations/) both have to allow the same
    reaction values, or one of them still rejects a member's tap."""

    def constraint_of(self, sql):
        m = re.search(r"check \(char_length\(reaction\)[^)]*\)", sql)
        self.assertIsNotNone(m, "expected a char_length bound on comment_reactions.reaction")
        return m.group(0)

    def test_schema_no_longer_hardcodes_six_names(self):
        # comment_reactions only: the voters' lounge keeps to the six quick
        # reactions on purpose (site_lounge_reactions; README, Voters' lounge)
        sql = read_root("supabase/schema.sql")
        start = sql.index("create table if not exists public.comment_reactions (")
        table = sql[start:sql.index(");", start)]
        self.assertNotIn("check (reaction in (", table)
        self.constraint_of(sql)

    def test_migration_widens_the_same_column_the_same_way(self):
        migrations = sorted((ROOT / "supabase" / "migrations").glob("*widen_comment_reactions.sql"))
        self.assertTrue(migrations, "expected a migration widening comment_reactions.reaction")
        migration = migrations[-1].read_text(encoding="utf-8")
        self.assertIn("comment_reactions", migration)
        self.assertEqual(self.constraint_of(migration), self.constraint_of(read_root("supabase/schema.sql")),
                         "schema.sql and the migration must land on the same constraint")

    def test_migration_finds_the_constraint_instead_of_guessing_its_name(self):
        # An inline `check (...)` gets an auto-generated name; hardcoding a
        # guess risks silently leaving the old, restrictive constraint in
        # place if the guess is wrong.
        migrations = sorted((ROOT / "supabase" / "migrations").glob("*widen_comment_reactions.sql"))
        migration = migrations[-1].read_text(encoding="utf-8")
        self.assertIn("pg_constraint", migration)
        self.assertIn("drop constraint", migration.lower())


def css_rules(css, selector):
    """The declaration blocks of every rule whose selector list includes
    `selector` exactly."""
    out = []
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)   # a comment right before a rule isn't its selector
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


class FeaturesPageWhatsNew(unittest.TestCase):
    """The "New in the last 30 days" box at the top of the features page:
    each item dated by the CHANGELOG entry it shipped in, and an inline
    script that hides what's older than 30 days. The hiding was checked in a
    browser with the clock moved forward."""

    def setUp(self):
        self.page = read("features.html")
        self.box = re.search(r'<aside class="whats-new" id="whatsNew"[^>]*>(.*?)</aside>', self.page, re.S).group(1)
        self.items = re.findall(r'<li data-shipped="([\d-]+)"><time datetime="([\d-]+)">([^<]+)</time><span>(.*?)</span></li>', self.box)

    def test_it_sits_at_the_top_above_the_summary(self):
        self.assertLess(self.page.index("<h1>What this site can do</h1>"), self.page.index('id="whatsNew"'))
        self.assertLess(self.page.index('id="whatsNew"'), self.page.index('<ul class="summary"'))

    def test_every_item_is_dated_by_a_real_changelog_entry_newest_first(self):
        import datetime
        headings = set(re.findall(r"^## (\d{4}-\d{2}-\d{2})", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), re.M))
        self.assertGreaterEqual(len(self.items), 5)
        self.assertEqual(self.box.count("<li"), len(self.items), "every item has the date markup")
        dates = [d for d, _, _, _ in self.items]
        self.assertEqual(dates, sorted(dates, reverse=True))
        for shipped, datetime_attr, label, _ in self.items:
            with self.subTest(shipped):
                self.assertIn(shipped, headings)
                self.assertEqual(shipped, datetime_attr)
                self.assertEqual(datetime.date.fromisoformat(shipped).strftime("%b %d").replace(" 0", " "), label)

    def test_it_keeps_only_the_last_30_days_and_hides_when_empty(self):
        script = self.page.split("/* What's new:", 1)[1].split("})();", 1)[0]
        self.assertIn("var cutoff = Date.now() - 30 * 24 * 60 * 60 * 1000;", script)
        self.assertIn('li.hidden = !(shipped >= cutoff);', script)
        self.assertIn("box.hidden = left === 0;", script)
        self.assertRegex(self.page, r"\.whats-new\[hidden\], \.whats-new li\[hidden\] \{ display: none; \}")

    def test_the_home_button_knows_the_newest_line(self):
        # forget to move FEATURES_UPDATED and Home stops saying New
        newest = max(d for d, _, _, _ in self.items)
        self.assertIn(f'var FEATURES_UPDATED = "{newest}";', read("app.js"))

    def test_visiting_records_the_newest_line_the_home_button_checks(self):
        script = self.page.split("/* What's new:", 1)[1].split("})();", 1)[0]
        self.assertIn('try { if (newest) localStorage.setItem("pfml.featuresSeen", newest); } catch (e)', script)
        app = read("app.js")
        self.assertIn('var FEATURES_SEEN_KEY = "pfml.featuresSeen";', app)
        button = app.split("function renderFeaturesButton() {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn("try { seen = localStorage.getItem(FEATURES_SEEN_KEY) || \"\"; } catch (e) { return; }", button)
        self.assertIn("var unseen = recent && seen < FEATURES_UPDATED;", button)
        self.assertIn('$("featuresNew").hidden = !unseen;', button)
        self.assertIn("renderFeaturesButton();", app.split("function initHome() {", 1)[1].split("\n  }\n", 1)[0])

    def test_the_button_is_the_first_thing_on_home(self):
        home = read("index.html")
        main = home.split("<main>", 1)[1]
        self.assertTrue(main.lstrip().startswith('<div class="shell home-top">'))
        self.assertIn('<a class="feat-btn" id="featuresBtn" href="features">', main)
        css = re.sub(r"/\*.*?\*/", "", read("style.css"), flags=re.S)
        self.assertRegex(css, r"\.feat-new\[hidden\]\s*\{\s*display:\s*none")

    def test_only_what_an_ordinary_member_sees(self):
        # the page's scope rule: no admin powers
        self.assertNotRegex(self.box, r"(?i)admin panel|league status|invite")


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


class ChoosingTheGoogleAccount(unittest.TestCase):
    """Signing in with the wrong Google account used to be a dead end:
    signing out and in again reused it without asking (2026-10-24). Google
    now shows its account picker every time (measured: supabase-js 2.116.0
    puts prompt=select_account on the authorize address, and Supabase passes
    it to accounts.google.com), and the not-linked and failed-invite cards
    offer a different account directly."""

    def setUp(self):
        self.auth = read("auth.js")

    def test_every_sign_in_asks_google_for_the_account_picker(self):
        sign_in = js_function(self.auth, "function signIn() {")
        self.assertIn('options: { redirectTo: location.origin + location.pathname, queryParams: { prompt: "select_account" } }', sign_in)
        self.assertEqual(self.auth.count("signInWithOAuth("), 1, "one way to start a sign-in")

    def test_a_different_account_leaves_this_session_then_picks_again(self):
        switch = js_function(self.auth, "function useAnotherAccount() {")
        self.assertIn("client.auth.signOut().then(signIn, signIn);", switch)

    def test_the_dead_end_cards_offer_it_first(self):
        offer = '{ label: "Use a different Google account", primary: true, onClick: useAnotherAccount }'
        self.assertIn(offer, js_function(self.auth, "function showNotLinked(user) {"))
        self.assertIn(offer, self.auth.split("That invite didn't work", 1)[1].split("return;", 1)[0])
        self.assertEqual(self.auth.count(offer), 2)


class QuietSignIn(unittest.TestCase):
    """Members with a saved sign-in see the page and a loading bar, not the
    "Signing you in" card, on every page change. The browser behaviour was
    checked against the real auth.js with a fake Supabase client; these pin
    what it depends on."""

    def test_session_key_was_read_from_the_pinned_library(self):
        # auth.js looks for supabase-js's default storage key,
        # sb-<project ref>-auth-token, as read from version 2.116.0. A
        # different version may store it elsewhere: recheck, then update
        # both this test and the comment in auth.js.
        versions = set()
        for name in ("index.html", "career.html", "round.html", "season.template.html"):
            versions |= set(re.findall(r"@supabase/supabase-js@([\d.]+)/", read(name)))
        self.assertEqual(versions, {"2.116.0"})
        self.assertIn('"sb-" + ref + "-auth-token"', read("auth.js"))

    def test_the_library_is_held_to_its_hash(self):
        # supabase-js runs on every signed-in page with the member's session,
        # so a tampered copy on the CDN could act as them. The integrity hash
        # makes the browser refuse any file that isn't the one we checked
        # (README, Members only). The live test checks the CDN still serves it.
        tags = {}
        for path in sorted(SITE.glob("*.html")):
            for tag in re.findall(r"<script[^>]*supabase-js[^>]*>", read(path.name)):
                tags.setdefault(path.name, []).append(tag)
        self.assertEqual(sorted(tags), sorted(MEMBER_PAGES + ["season1.html", "season2.html", "season3.html"]))
        for name, found in tags.items():
            with self.subTest(name):
                self.assertEqual(len(found), 1)
                self.assertIn(f'integrity="{SUPABASE_JS_INTEGRITY}"', found[0])
                self.assertIn('crossorigin="anonymous"', found[0])
                self.assertIn(f'src="{SUPABASE_JS_URL}"', found[0])

    def test_the_checking_state_is_styled(self):
        self.assertIn('classList.add("auth-checking")', read("auth.js"))
        self.assertIn("body.auth-checking::before", read("style.css"))


def strip_media(css, query):
    """css with every `@media <query> { ... }` block removed (braces matched)."""
    out, i = [], 0
    pattern = re.compile(r"@media\s*" + re.escape(query) + r"\s*\{")
    while True:
        m = pattern.search(css, i)
        if not m:
            out.append(css[i:])
            return "".join(out)
        out.append(css[i:m.start()])
        depth, j = 1, m.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(css[j], 0)
            j += 1
        i = j


class TouchFriendlyStandings(unittest.TestCase):
    def test_hover_effects_only_on_devices_that_hover(self):
        # On a phone, :hover sticks to whatever a finger touched, including
        # the start of a scroll: Standings names turned purple while
        # scrolling. These parts may only hover on hover-capable devices.
        css = strip_media(read("style.css"), "(hover: hover)")
        for sel, _ in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            for part in sel.split(","):
                if ":hover" in part:
                    self.assertNotRegex(part, r"stand-row|fold-bar|stand-filter",
                                        f"{part.strip()} applies on touch screens too")

    def test_tapped_controls_and_cards_dont_keep_a_hover_look(self):
        # The same sticking, on things that toggle or lift: an un-voted
        # arrow stayed magenta, a tapped sort heading looked like the active
        # sort, and cards stayed lifted after a tap.
        css = strip_media(read("style.css"), "(hover: hover)")
        sticky = (r"trend-chip|trend-group|cm-vote|cm-chip:|career-sort-btn|season-tab:hover|focus-chip|"
                  r"\.pill:|\.art:|season-card|rl-card|rp-jump-select")
        for sel, _ in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            for part in sel.split(","):
                if ":hover" in part:
                    self.assertNotRegex(part, sticky, f"{part.strip()} applies on touch screens too")

    def test_filter_row_spans_the_whole_bar(self):
        # Squeezed into the title column beside Show all, each chip took a
        # line of its own and the bar grew by ~100px on the first tap.
        bar = re.search(r'id="standBar"(.*?)id="standPanel"', read("season.template.html"), re.S).group(1)
        text_col = re.search(r'<span class="fold-text">(.*?)</span>\s*<button', bar, re.S).group(1)
        self.assertNotIn('id="standFilters"', text_col, "filters sit outside the narrow text column")
        self.assertIn('id="standFilters"', bar)
        rule = " ".join(css_rules(read("style.css"), ".stand-filters"))
        self.assertIn("grid-column: 1 / -1", rule)

    def test_on_a_phone_the_chips_are_one_swipeable_line(self):
        # measured at 375px: wrapping chips grew the bar ~36px per pick
        css = read("style.css")
        phone = re.search(r"@media \(max-width: 620px\) \{(.*?)\n\}", css[css.index("folding sections"):], re.S)
        self.assertIsNotNone(phone)
        rule = " ".join(css_rules(phone.group(1), ".stand-filters"))
        self.assertIn("flex-wrap: nowrap", rule)
        self.assertIn("overflow-x: auto", rule)


class MemberTextIsEscaped(unittest.TestCase):
    """Reactions are free text in the database (any 1-32 characters, so
    any emoji fits), and names are whatever players call themselves on
    Music League. Either could carry markup into innerHTML."""

    def test_every_reaction_glyph_is_escaped(self):
        for name in ("rounds.js", "account.js"):
            js = read(name)
            calls = [m.start() for m in re.finditer(r"reactionGlyph\(", js)
                     if not js[max(0, m.start() - 9):m.start()].endswith("function ")]
            self.assertTrue(calls, name)
            for at in calls:
                self.assertTrue(js[:at].endswith("esc("), f"{name}: unescaped reactionGlyph at {at}")

    def test_a_reaction_named_like_an_object_property_is_just_text(self):
        # found 2026-10-24: a reaction stored as "constructor" or "__proto__"
        # matched Object's own property, threw, and blanked votes, reactions
        # and replies on that round for everyone ("__proto__" also set
        # Object.prototype.count). Reproduced in Chrome before the fix.
        self.assertIn("by = Object.create(null);", js_function(read("rounds.js"), "function reactionsFor(id)"))
        tally = read("app.js").split("function fillProfileReactions(id) {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn("var counts = Object.create(null), total = 0;", tally)
        self.assertIn("Object.prototype.hasOwnProperty.call(LEGACY_REACT, key) ? LEGACY_REACT[key] : key",
                      read("account.js").split("function reactionGlyph(key) {", 1)[1].split("\n", 1)[0])

    def test_translations_are_escaped(self):
        # hand-typed into data/translations.json, so treated like any text
        fn = js_function(read("account.js"), "function translationHtml(tr)")
        self.assertIn("esc(tr.from)", fn)
        self.assertIn("esc(tr.text)", fn)
        self.assertNotRegex(fn, r"\+ tr\.(from|text)\b", "every field goes through esc()")

    def test_taste_panel_titles_escape_the_name(self):
        js = read("app.js")
        lists = js_function(js, "function renderTasteLists(d, id, host)")
        self.assertIn("name = esc(nameOf(d, id))", lists)
        self.assertIn('"How " + name + " rates everyone else"', lists)
        self.assertIn('"How everyone else rates " + name', lists)
        # the phone's player menu and the "not shown yet" names too
        self.assertIn("esc(p.name)", js_function(js, "function renderTastePhone(d, people, host)"))
        self.assertIn("esc(p.name)", js_function(js, "function renderTaste(d)"))


class SecurityCheckCard(unittest.TestCase):
    """The plain-language security summary on the privacy page (README,
    Members only). A recheck moves its date and rewrites what it found."""

    def test_it_is_dated_and_near_the_top(self):
        page = read("privacy.html")
        card = page.split('<section class="sec-card"', 1)[1].split("</section>", 1)[0]
        self.assertRegex(card, r'<span class="sec-when">Full review: [A-Z][a-z]+ \d{1,2}, 20\d\d</span>')
        self.assertLess(page.index('class="sec-card"'), page.index("<h2>When you sign in with Google</h2>"))


class PinnedTrackBar(unittest.TestCase):
    """On a round page, the song being commented on stays pinned under the
    top bar while its comments scroll past, until the next song's do."""

    def test_bar_sits_in_the_card_just_before_the_votes(self):
        # a direct child of the card, so it pins only within that card and
        # the next card's takes over
        track = js_function(read("rounds.js"), "function trackHtml(s, tiedPlaces)")
        self.assertIn("pinHtml(s) + '<div class=\"rp-votes\">'", track)
        pin = js_function(read("rounds.js"), "function pinHtml(s)")
        self.assertIn('class="rp-pin" aria-hidden="true"', pin, "it repeats the header")
        self.assertIn("esc(s.title)", pin)
        self.assertIn("esc(s.artistText)", pin)

    def test_it_never_moves_the_page(self):
        # 0px tall and sticky: showing the bar overlays, it doesn't push
        pin = " ".join(css_rules(read("style.css"), ".rp-pin"))
        self.assertIn("position: sticky", pin)
        self.assertIn("height: 0", pin)
        self.assertIn("top: var(--topbar-h", pin)
        bar = " ".join(css_rules(read("style.css"), ".rp-pin-bar"))
        self.assertIn("position: absolute", bar)
        self.assertIn("pointer-events: none", bar)
        self.assertIn("visibility: hidden", bar)
        self.assertTrue(css_rules(read("style.css"), ".rp-pin.is-stuck .rp-pin-bar"))

    def test_the_card_clips_without_stopping_sticky(self):
        # overflow: hidden makes the card a scroll container, and sticky
        # children then never stick; clip keeps the corners without that
        card = " ".join(css_rules(read("style.css"), ".rp-track"))
        self.assertIn("overflow: clip", card)
        self.assertGreater(card.index("overflow: clip"), card.index("overflow: hidden"), "clip wins where supported")

    def test_it_sits_under_the_real_top_bar(self):
        sync = js_function(read("app.js"), "function syncScrollPadding()")
        self.assertIn('setProperty("--topbar-h", bar.offsetHeight + "px")', sync)

    def test_shown_only_while_stuck_measured_then_toggled(self):
        js = read("rounds.js")
        update = js_function(js, "function updatePins()")
        self.assertLess(update.index("getBoundingClientRect"), update.index('classList.toggle("is-stuck"'),
                        "every read before any write")
        self.assertIn('window.addEventListener("scroll", schedulePins, { passive: true })', js)
        self.assertIn("updatePins();", js_function(js, "function renderTracks(r)"), "and after each redraw")


class TasteOnPhones(unittest.TestCase):
    """The taste grid is about six screens wide on a phone (one column
    visible at a time), so phones get one player's lists instead, opening
    on the signed-in member; everyone gets the league's strongest and
    coldest pairings; and nobody shows as a blank row."""

    def setUp(self):
        self.js = read("app.js")
        self.taste = js_function(self.js, "function renderTaste(d)")

    def test_unfiltered_it_draws_the_phone_lists_the_pairs_and_the_grid(self):
        unfiltered = self.taste.split("if (!selected.length) {", 1)[1].split("}", 1)[0]
        self.assertIn("renderTastePhone(d, people, host)", unfiltered)
        self.assertIn("renderTastePairs(d, host)", unfiltered)
        # the grid is wide-screen only unless players are picked in Standings
        self.assertIn("renderTasteGrid(d, people, host, selected.length > 0)", self.taste)
        grid = js_function(self.js, "function renderTasteGrid(d, people, host, phoneToo)")
        self.assertIn('"taste-grid" + (phoneToo ? "" : " is-wide-only")', grid)
        self.assertIn("if (selected.length === 1) { renderTasteLists(d, selected[0], host); return; }", self.taste)

    def test_css_swaps_the_grid_for_the_lists_on_phones_only(self):
        css = read("style.css")
        self.assertIn("display: none", " ".join(css_rules(css, ".taste-phone")))
        self.assertIn("display: block", " ".join(phone_rules(css, ".taste-phone")))
        self.assertIn("display: none", " ".join(phone_rules(css, ".taste-grid.is-wide-only")))
        self.assertIn("1fr", " ".join(phone_rules(css, ".taste-pairs")), "the two pairing lists stack")

    def test_phone_view_opens_on_you_and_can_switch(self):
        phone = js_function(self.js, "function renderTastePhone(d, people, host)")
        self.assertIn("var me = PFML.member.competitorId;", phone)
        self.assertIn("ids.indexOf(me) !== -1 ? me :", phone, "you, when you played this season")
        self.assertIn('(p.id === me ? " (you)" : "")', phone)
        self.assertIn("tasteFocus = ev.target.value;", phone)
        lists = js_function(self.js, "function renderTasteLists(d, id, host)")
        self.assertIn('"How you rate everyone else"', lists)
        self.assertIn('"How everyone else rates you"', lists)

    def test_pairs_are_the_five_strongest_and_five_coldest(self):
        pairs = js_function(self.js, "function renderTastePairs(d, host)")
        self.assertIn("b.perRound - a.perRound || b.points - a.points", pairs)
        self.assertIn("a.perRound - b.perRound || b.chances - a.chances", pairs, "a zero over more rounds is colder")
        self.assertIn('renderTasteRowList("Strongest pairings", strongest.slice(0, 5).map(row), wrap,', pairs)
        self.assertIn('renderTasteRowList("Coldest pairings", coldest.slice(0, 5).map(row), wrap,', pairs)

    def test_players_with_nothing_to_show_are_named_not_blank_rows(self):
        self.assertIn("var people = pool.filter(function (p) { return inTaste[p.id]; });", self.taste)
        self.assertIn("var waiting = pool.filter(function (p) { return !inTaste[p.id]; });", self.taste)
        self.assertIn("Not shown until they've played enough rounds: ", self.taste)


class TasteInPointsARound(unittest.TestCase):
    """Members didn't follow "1.97x", even with the note. Taste now reads in
    the league's own units, points a round, with column headers."""

    FUNCTIONS = ["function renderTasteRowList(title, rows, host, firstCol, cols, cls)", "function renderTasteGrid(d, people, host, phoneToo)",
                 "function renderTastePairs(d, host)", "function renderTasteLists(d, id, host)",
                 "function renderFocusIndividual(d, id, host)", "function renderFocusGroup(d, ids, host)",
                 "function renderHighlights(d)", "function renderTaste(d)"]

    def test_no_ratio_left_anywhere_taste_shows(self):
        js = read("app.js")
        for name in self.FUNCTIONS:
            with self.subTest(name):
                body = js_function(js, name)
                self.assertNotIn("&times;", body)
                self.assertNotRegex(body, r"\.index\b")

    def test_lists_have_column_headers(self):
        js = read("app.js")
        lists = js_function(js, "function renderTasteRowList(title, rows, host, firstCol, cols, cls)")
        self.assertIn("esc(firstCol)", lists)
        self.assertIn("(cols || TASTE_COLS).map(", lists, "every list has a header row")
        self.assertIn('var TASTE_COLS = ["Points a round", "Points", "Rounds"];', js)
        self.assertIn("return [t.perRound.toFixed(1), t.points, t.chances];", js_function(js, "function tasteCells(t)"))

    def test_figures_say_what_an_even_split_is(self):
        js = read("app.js")
        self.assertIn('return n.toFixed(1) + " points a round";', js_function(js, "function aRound(n)"))
        self.assertIn('" (an even split is " + d.tasteEvenSplit.toFixed(1) + ")"', js_function(js, "function evenSplit(d)"))
        note = js_function(js, "function renderTaste(d)")
        self.assertIn("d.pointBudget", note)
        self.assertIn("d.tasteEvenSplit.toFixed(1)", note)


class LopsidedPairings(unittest.TestCase):
    """Who gives someone's songs far more a round than they get back: a
    third list beside strongest and coldest."""

    def setUp(self):
        self.js = read("app.js")
        self.fn = js_function(self.js, "function lopsidedPairs(d)")

    def test_each_pair_once_from_the_bigger_giver_and_only_both_ways(self):
        self.assertIn('var back = byKey[t.submitterId + "|" + t.voterId];', self.fn)
        # needs the return direction, and an equal pair isn't lopsided
        self.assertIn("if (!back) return;", self.fn)
        self.assertIn("if (gives > gets) out.push(", self.fn)

    def test_the_gap_is_the_difference_of_the_figures_shown(self):
        # rounded apart, 1.15 and 0.35 showed as 1.1 and 0.4 with a gap of 0.8
        self.assertIn("var shown = function (n) { return +n.toFixed(1); };", self.fn)
        self.assertIn("var gives = shown(t.perRound), gets = shown(back.perRound);", self.fn)
        self.assertIn("gap: Math.round((gives - gets) * 10) / 10", self.fn)
        self.assertIn("return b.gap - a.gap || b.gives.perRound - a.gives.perRound ||", self.fn)

    def test_listed_with_its_own_columns_full_width_on_desktop(self):
        pairs = js_function(self.js, "function renderTastePairs(d, host)")
        self.assertIn('renderTasteRowList("Most lopsided pairings", lopsidedPairs(d).slice(0, 5).map(', pairs)
        self.assertIn('["Gives a round", "Gets back", "Gap"], "taste-lopsided")', pairs)
        self.assertIn("grid-column: 1 / -1", " ".join(css_rules(read("style.css"), ".taste-lopsided")))


class Tastemaker(unittest.TestCase):
    """Whose biggest vote of a round most often went to the winner: one
    award, one name and one wording on a season page and All-Time."""

    def test_one_tile_says_rounds_of_rounds_and_the_percent(self):
        js = read("app.js")
        fn = js_function(js, "function tastemakerTile(t)")
        self.assertIn('tile("Tastemaker", who(t.name),', fn)
        self.assertIn('t.kingmakerHits + " of " +', fn)
        self.assertIn('t.kingmakerRounds + " rounds (" + pct(t.kingmakerRate) + ")", false, t.tiedWith)', fn)

    def test_season_and_all_time_both_use_it(self):
        js = read("app.js")
        for fn in ("function renderHighlights(d)", "function renderCareerHighlights(c)"):
            self.assertIn("g.appendChild(tastemakerTile(h.bestTastemaker))", js_function(js, fn), fn)
        self.assertNotIn("Best read on the room", js)


class TasteNote(unittest.TestCase):
    def test_note_takes_the_minimum_from_the_data(self):
        # it said "five" in words, and would have gone stale when it became 4
        taste = js_function(read("app.js"), "function renderTaste(d)")
        self.assertIn("d.tasteMinChances", taste)
        self.assertNotRegex(taste, r"\b(four|five) chances\b")


class Translations(unittest.TestCase):
    """A comment or note in another language shows the original first, then
    its English underneath, marked as a translation (README, Translations)."""

    def test_round_page_comments_and_notes_show_it_inside_the_original(self):
        js = read("rounds.js")
        vote = js_function(js, "function voteHtml(row)")
        self.assertIn("esc(c.comment) + translationHtml(c.translation) + \"</p>\"", vote, "under the comment, in its box")
        track = js_function(js, "function trackHtml(s, tiedPlaces)")
        self.assertIn("esc(s.note) + translationHtml(s.noteTranslation) + \"</p>\"", track)

    def test_quote_cards_show_it_inside_the_quote(self):
        # inside the blockquote, so a long one is clipped and opened with it
        quote = js_function(read("app.js"), "function commentQuote(c, label, stats)")
        self.assertIn('"<blockquote>" + esc(c.text) + PFML.translationHtml(c.translation) + "</blockquote>"', quote)

    def test_it_is_labelled_and_kept_out_of_the_note_label_styling(self):
        fn = js_function(read("account.js"), "function translationHtml(tr)")
        self.assertIn("Translated from ", fn)
        self.assertIn('if (!tr) return "";', fn, "nothing at all for an English comment")
        # .rp-note span styles the "Their note" label; the translation mustn't use spans
        self.assertNotIn("<span", fn)
        css = read("style.css")
        self.assertTrue(css_rules(css, ".tr"))
        self.assertTrue(any("display: block" in b for b in css_rules(css, ".tr")))
        self.assertTrue(any("display: block" in b for b in css_rules(css, ".tr-label")))


class PickerClosesCleanly(unittest.TestCase):
    def test_a_reaction_closes_the_open_picker_right_away(self):
        # A chip on comment B used to clear state.picker without redrawing
        # comment A, so A's picker stayed on screen with its button stuck on
        # "close"; a failed save left it open the same way.
        js = read("rounds.js")
        branch = js.split('} else if (act === "react") {', 1)[1].split("} else if", 1)[0]
        self.assertRegex(branch, r"var open = state\.picker;[\s\S]*state\.picker = null;[\s\S]*if \(open\) rerenderVote\(open\);[\s\S]*refreshAfter\(")

    def test_a_tap_outside_doesnt_move_focus(self):
        js = read("rounds.js")
        outside = js.split("function closePickerFromOutside", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn("closePicker(true)", outside)
        self.assertRegex(js, r"function closePicker\(quiet\) \{[\s\S]*?if \(quiet\) return;[\s\S]*?\.focus\(\)")


class InboxBadge(unittest.TestCase):
    def test_inbox_opened_before_its_first_load_still_marks_items_seen(self):
        # refresh() used to only redraw an open inbox, so opening it before
        # the first fetch landed never cleared the badge.
        js = read("account.js")
        refresh = js.split("function refresh()", 1)[1].split("function isNew", 1)[0]
        self.assertIn('if (state.open === "inbox") openInbox();', refresh)

    def test_a_late_refresh_keeps_the_later_seen_time(self):
        refresh = read("account.js").split("function refresh()", 1)[1].split("function isNew", 1)[0]
        self.assertIn("Date.parse(state.seenAt) > Date.parse(seen)", refresh)


class JumpMenus(unittest.TestCase):
    def test_profile_switcher_is_wrapped_for_its_arrow(self):
        # .rp-jump::after draws the arrow; a bare select had none
        self.assertIn('<div class="rp-jump"><select id="pfPick" class="rp-jump-select">', read("app.js"))

    def test_menu_text_is_16px_on_phones(self):
        # iOS zooms the page in when a select under 16px is tapped
        css = read("style.css")
        phones = re.findall(r"@media \(max-width: 620px\) \{(.*?)\n\}", css, re.S)
        rules = [r for block in phones for r in css_rules(block, ".rp-jump-select")]
        self.assertTrue(any("font-size: 16px" in r for r in rules))


class DeployWorkflow(unittest.TestCase):
    """What the deploy may do. Text checks: there's no YAML parser in the
    stdlib, and the file is short and flat enough for them."""

    def setUp(self):
        self.yml = read_root(".github/workflows/deploy.yml")
        self.build, self.deploy = self.yml.split("\n  deploy:\n", 1)

    def test_only_the_deploy_job_can_write_pages(self):
        top = self.yml.split("\njobs:", 1)[0]
        self.assertNotIn("pages: write", top)
        self.assertNotIn("id-token: write", top)
        self.assertNotIn("pages:", self.build.split("\njobs:", 1)[1])
        self.assertIn("pages: write", self.deploy)
        self.assertIn("id-token: write", self.deploy)

    def test_actions_are_pinned_to_commits(self):
        uses = re.findall(r"uses:\s*(\S+)", self.yml)
        self.assertTrue(uses)
        for u in uses:
            self.assertRegex(u, r"@[0-9a-f]{40}$", u)

    def test_the_guard_refuses_data_and_secrets(self):
        for pattern in ("'*.json'", "'*.csv'", "'.env*'", "[ -d data ]"):
            self.assertIn(pattern, self.build)

    def test_a_newer_push_doesnt_cancel_a_deploy(self):
        self.assertIn("cancel-in-progress: false", self.yml)

    def test_tests_gate_the_deploy_on_a_pinned_python(self):
        self.assertRegex(self.build, r'python-version: "3\.\d+"')
        self.assertIn("python -m unittest discover -s tests", self.build)
        self.assertIn("needs: build", self.deploy)

    def test_a_runner_backlog_doesnt_cancel_the_deploy(self):
        # A job's timeout-minutes covers the wait for a runner too, so a tight
        # one cancels the deploy during a GitHub capacity incident instead of
        # waiting it out. That happened 2026-10-05 at 10 minutes. These jobs
        # run in about 12 seconds, so the job clock is only queue headroom.
        job_timeouts = [int(m) for m in re.findall(
            r"^    timeout-minutes: (\d+)$", self.yml, re.M)]
        self.assertEqual(len(job_timeouts), 2, "both jobs set one")
        for t in job_timeouts:
            self.assertGreaterEqual(t, 30, "too tight to ride out a runner backlog")

    def test_a_hung_step_is_still_caught(self):
        # The hang protection the job clock used to provide moves to the steps,
        # where the clock starts when the step does, not when it is queued.
        step_timeouts = re.findall(r"^        timeout-minutes: (\d+)$", self.yml, re.M)
        self.assertTrue(step_timeouts, "no step bounds its own run time")
        tests_step = self.build.split("- name: Run tests", 1)[1].split("- name:", 1)[0]
        self.assertRegex(tests_step, r"timeout-minutes: \d+", "the suite can hang")

    def test_pages_ask_for_this_deploys_scripts_not_a_cached_copy(self):
        # Pages caches every file for 10 minutes; without the stamp a new
        # page ran with an old auth.js (2026-10-19). It runs after the tests
        # (which read the unstamped files) and before the upload.
        step = 'run: python scripts/stamp_assets.py site "${GITHUB_SHA::12}"'
        self.assertIn(step, self.build)
        # the step itself, not the comment above it that names the script
        order = [self.build.index(s) for s in ("- name: Run tests", step, "uses: actions/upload-pages-artifact")]
        self.assertEqual(order, sorted(order))


class StampAssets(unittest.TestCase):
    """scripts/stamp_assets.py, which the deploy runs on its checkout."""

    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("stamp_assets", ROOT / "scripts" / "stamp_assets.py")
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_local_scripts_and_styles_get_the_version_and_nothing_else_changes(self):
        cdn = '<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.116.0/dist/umd/supabase.js"></script>'
        page = (cdn + '\n<link rel="stylesheet" href="style.css">\n<script src="auth.js"></script>\n'
                '<a href="features">x</a> <a href="./">home</a> <link rel="icon" href="data:image/svg+xml,<svg/>">')
        out = self.mod.stamp(page, "abc123def456")
        self.assertIn('href="style.css?v=abc123def456"', out)
        self.assertIn('src="auth.js?v=abc123def456"', out)
        self.assertIn(cdn, out)
        self.assertIn('<a href="features">x</a> <a href="./">home</a>', out)
        self.assertIn('href="data:image/svg+xml,<svg/>"', out)

    def test_every_page_stamps_every_local_script_and_only_those(self):
        for path in sorted(SITE.glob("*.html")):
            with self.subTest(path.name):
                html = read(path.name)
                out = self.mod.stamp(html, "abc123def456")
                local = [s for s in re.findall(r'(?:src|href)="([^"]+\.(?:js|css))"', html) if "/" not in s]
                for name in local:
                    self.assertIn(f'"{name}?v=abc123def456"', out)
                self.assertEqual(out.replace("?v=abc123def456", ""), html)

    def test_refuses_a_version_that_isnt_a_commit_hash(self):
        import subprocess
        import sys
        for bad in ("", "a b", "x" * 50, "../x"):
            with self.subTest(bad):
                r = subprocess.run([sys.executable, str(ROOT / "scripts" / "stamp_assets.py"), str(SITE), bad],
                                   capture_output=True, text=True)
                self.assertNotEqual(r.returncode, 0)


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
