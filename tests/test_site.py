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
        self.assertIn("entry(LEGACY_REACT[k], k,", index, "stored by its old name, not the glyph")

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
        self.assertIn("margin: 0 -16px", css.split("@media (max-width: 620px)")[-1].split(".rp-vote-head", 1)[1].split("}", 1)[0],
                      "and edge to edge at phone widths too")


class ReactionsSchema(unittest.TestCase):
    """supabase/schema.sql (fresh installs) and the one-off migration for
    the live project (supabase/migrations/) both have to allow the same
    reaction values, or one of them still rejects a member's tap."""

    def constraint_of(self, sql):
        m = re.search(r"check \(char_length\(reaction\)[^)]*\)", sql)
        self.assertIsNotNone(m, "expected a char_length bound on comment_reactions.reaction")
        return m.group(0)

    def test_schema_no_longer_hardcodes_six_names(self):
        sql = read_root("supabase/schema.sql")
        self.assertNotIn("check (reaction in (", sql)
        self.constraint_of(sql)

    def test_migration_widens_the_same_column_the_same_way(self):
        migrations = sorted((ROOT / "supabase" / "migrations").glob("*.sql"))
        self.assertTrue(migrations, "expected a migration widening comment_reactions.reaction")
        migration = migrations[-1].read_text(encoding="utf-8")
        self.assertIn("comment_reactions", migration)
        self.assertEqual(self.constraint_of(migration), self.constraint_of(read_root("supabase/schema.sql")),
                         "schema.sql and the migration must land on the same constraint")

    def test_migration_finds_the_constraint_instead_of_guessing_its_name(self):
        # An inline `check (...)` gets an auto-generated name; hardcoding a
        # guess risks silently leaving the old, restrictive constraint in
        # place if the guess is wrong.
        migrations = sorted((ROOT / "supabase" / "migrations").glob("*.sql"))
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
