"""The open round at a glance: Add to Home Screen (the manifest and icons),
the Home banner's deadline and "you're in", and the admin's league panel
(README, Add to Home Screen; Submissions on the site, Admin status). The
browser side was checked against a stand-in; there's no JS runner here."""
import importlib.util
import json
import re
import struct
import unittest

from support import ROOT
from test_site import MEMBER_PAGES
from test_submissions import function, schema

SITE = ROOT / "site"


def read(name):
    return (SITE / name).read_text(encoding="utf-8")


def js_body(js, signature):
    return js.split(signature, 1)[1].split("\n  }\n", 1)[0]


def png_size(path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path.name
    return struct.unpack(">II", data[16:24])


class AddToHomeScreen(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(read("manifest.webmanifest"))

    def test_every_member_page_links_the_manifest_and_the_ios_icon(self):
        for name in MEMBER_PAGES + ["season1.html", "season2.html", "season3.html"]:
            with self.subTest(name):
                page = read(name)
                self.assertIn('<link rel="manifest" href="manifest.webmanifest">', page)
                self.assertIn('<link rel="apple-touch-icon" href="icon-180.png">', page)

    def test_the_standalone_pages_stay_standalone(self):
        # features and privacy load nothing but themselves and their fonts
        for name in ("features.html", "privacy.html"):
            with self.subTest(name):
                self.assertNotIn("manifest", read(name))

    def test_the_manifest_opens_the_site_like_an_app(self):
        m = self.manifest
        self.assertEqual((m["name"], m["start_url"], m["scope"], m["display"]), ("PFML", "./", "./", "standalone"))
        self.assertEqual(m["theme_color"], "#9E00C4")
        self.assertIn('<meta name="theme-color" content="#9E00C4">', read("index.html"))

    def test_every_icon_exists_at_its_stated_size(self):
        icons = self.manifest["icons"] + [{"src": "icon-180.png", "sizes": "180x180"}]
        self.assertEqual(sorted(i.get("purpose", "ios") for i in icons), ["any", "any", "ios", "maskable"])
        for icon in icons:
            with self.subTest(icon["src"]):
                w, h = (int(n) for n in icon["sizes"].split("x"))
                self.assertEqual(png_size(SITE / icon["src"]), (w, h))

    def test_the_committed_icon_is_what_the_script_draws(self):
        spec = importlib.util.spec_from_file_location("make_icons", ROOT / "scripts" / "make_icons.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        size, radius = mod.ICONS["icon-180.png"]
        self.assertEqual(mod.draw(size, radius), (SITE / "icon-180.png").read_bytes())

    def make_icons(self):
        spec = importlib.util.spec_from_file_location("make_icons", ROOT / "scripts" / "make_icons.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_every_page_shows_the_same_icon_the_pngs_are_drawn_from(self):
        # one source (scripts/make_icons.py) for the tab icon and the PNGs
        href = self.make_icons().favicon_href()
        for path in sorted(SITE.glob("*.html")):
            with self.subTest(path.name):
                self.assertEqual(re.findall(r'<link rel="icon" href="([^"]*)">', path.read_text(encoding="utf-8")), [href])

    def test_the_drawing_is_the_record_on_purple(self):
        # the design chosen 2026-10-24 ("g3"), point by point
        m = self.make_icons()
        self.assertEqual(m.colour_at(8, 50, 22), m.PURPLE)        # the tile, outside the record
        self.assertEqual(m.colour_at(30, 70, 22), m.INK)          # the record
        self.assertEqual(m.colour_at(50, 18, 22), m.LAVENDER)     # the top of the outer lit groove
        self.assertEqual(m.colour_at(50, 50, 22), m.WHITE)        # the P, on the label
        self.assertEqual(m.colour_at(54, 55, 22), m.PURPLE)       # the label, under the P's bowl
        self.assertIsNone(m.colour_at(1, 1, 22))                  # a rounded corner
        self.assertEqual(m.colour_at(1, 1, 0), m.PURPLE)          # full-bleed for iOS and maskable
        self.assertEqual((m.PURPLE, m.INK), ("#9E00C4", "#16111A"))
        self.assertIn("<circle cx='50' cy='50' r='36' fill='#16111A'/>", m.svg())

    def test_the_deploy_guard_doesnt_mistake_it_for_league_data(self):
        # the workflow refuses *.json in site/; the manifest isn't named that
        self.assertFalse(list(SITE.glob("*.json")))
        self.assertIn("-name '*.json'", (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8"))


class Splash(unittest.TestCase):
    """The installed app's splash (README, Splash screen): design B, chosen
    2026-10-25. Only when PFML opens from the home screen, once per opening,
    lifted once sign-in is done, never for long. Timings were measured in a
    browser against a stand-in; there's no JS runner here."""

    def setUp(self):
        self.home = read("index.html")
        self.head = self.home.split("</head>", 1)[0]
        self.css = re.sub(r"/\*.*?\*/", "", read("style.css"), flags=re.S)
        self.account = read("account.js")

    def test_only_in_the_installed_app_and_once_per_opening(self):
        line = re.search(r"<script>try\{if\(\(matchMedia[^<]*</script>", self.head).group(0)
        self.assertIn('(matchMedia("(display-mode: standalone)").matches||navigator.standalone===true)', line)
        self.assertIn('!sessionStorage.getItem("pfml.splashSeen")', line)
        self.assertIn('document.documentElement.classList.add("app-splash")', line)
        # after the theme-color it swaps, and before anything paints
        self.assertLess(self.head.index('<meta name="theme-color"'), self.head.index(line))
        self.assertLess(self.head.index(line), self.head.index('rel="stylesheet"'))
        self.assertIn('try { sessionStorage.setItem("pfml.splashSeen", "1"); }', self.account)

    def test_it_lifts_after_sign_in_and_never_late(self):
        self.assertIn("var SPLASH_MIN_MS = 600, SPLASH_MAX_MS = 2000;", self.account)
        fn = self.account.split("(function splash() {", 1)[1].split("\n  })();", 1)[0]
        self.assertIn("PFML.ready.then(function () { setTimeout(lift, Math.max(0, SPLASH_MIN_MS - performance.now())); });", fn)
        self.assertIn("setTimeout(lift, Math.max(0, SPLASH_MAX_MS - performance.now()));", fn)
        self.assertIn('meta.content = meta.getAttribute("data-was")', fn, "the status bar gets its purple back")

    def test_hidden_unless_opening_and_shown_through_the_gate(self):
        self.assertRegex(self.css, r"(?m)^\.splash \{ display: none; \}")
        self.assertRegex(self.css, r"html\.app-splash \.splash \{[^}]*position: fixed; inset: 0;")
        # the gate hides everything else until sign-in; the splash holds only the logo
        self.assertIn("body.gated > *:not(#gate):not(#splash) { display: none !important; }", self.css)
        body = self.home.split("<body", 1)[1]
        self.assertIn('<div class="splash" id="splash" aria-hidden="true">', body)
        self.assertNotIn('id="splash"', "".join(read(n) for n in MEMBER_PAGES if n != "index.html"))

    def test_still_for_anyone_who_turns_motion_off(self):
        self.assertRegex(self.css, r"@media \(prefers-reduced-motion: reduce\) \{\s*\.splash-record, \.splash-grooves, \.splash-word \{ animation: none; \}")

    def test_the_phones_own_splash_is_the_same_dark(self):
        # Android draws its own from the manifest first; matching it means no flash
        manifest = json.loads(read("manifest.webmanifest"))
        bg = re.search(r"html\.app-splash \.splash \{[^}]*background: (#[0-9A-Fa-f]{6});", self.css).group(1)
        self.assertEqual(manifest["background_color"], bg)
        self.assertIn('m.content="#16111A"', self.head)


class GetTheApp(unittest.TestCase):
    """The "Get the app" button and the menu's Add to home screen
    (account.js): Android's own install prompt where the browser offers it,
    otherwise how to do it on that device."""

    def setUp(self):
        self.js = read("account.js")

    def test_the_browsers_install_prompt_is_kept_from_the_start(self):
        # Chrome fires it once, early; listening only after sign-in would miss it
        # at the top level of the file (two-space indent inside its wrapper),
        # so it runs as soon as account.js loads, not inside a function
        top = self.js.split("function build(member) {", 1)[0]
        self.assertIn('\n  window.addEventListener("beforeinstallprompt", function (ev) {\n    ev.preventDefault();\n    installEvent = ev;', top)
        self.assertIn('\n  window.addEventListener("appinstalled"', top)

    def test_nothing_offers_it_once_running_as_the_app(self):
        app = js_body(self.js, "function isApp() {")
        self.assertIn('window.matchMedia("(display-mode: standalone)").matches', app)
        self.assertIn("navigator.standalone === true", app)
        shown = js_body(self.js, "function showInstallControls() {")
        self.assertIn('if (get) get.hidden = isApp() || platform() === "desktop" || installSeen();', shown)
        self.assertIn("if (item) item.hidden = isApp();", shown)

    def test_one_tap_installs_where_it_can_and_explains_where_it_cant(self):
        add = js_body(self.js, "function addToHomeScreen() {")
        self.assertIn('localStorage.setItem(INSTALL_SEEN_KEY, "1")', add)
        self.assertIn("if (installEvent) {", add)
        self.assertIn("ev.prompt();", add)
        self.assertIn("showInstallHelp();", add.split("return;", 1)[1])

    def test_every_kind_of_device_gets_its_own_steps(self):
        steps = self.js.split("var INSTALL_STEPS = {", 1)[1].split("};", 1)[0]
        for key in ("ios", "android", "inapp", "desktop"):
            self.assertRegex(steps, r"\n    " + key + r": ")
        self.assertIn("Add to Home Screen", steps.split("android:", 1)[0])
        platform_ = js_body(self.js, "function platform() {")
        for ret in ('return "inapp";', 'return "ios";', 'return "android";', 'return "desktop";'):
            self.assertIn(ret, platform_)
        # an app's built-in browser is checked before iOS or Android, since its
        # user agent says iPhone or Android too
        self.assertLess(platform_.index('return "inapp";'), platform_.index('return "ios";'))

    def test_in_the_top_bar_and_the_menu(self):
        build = js_body(self.js, "function build(member) {")
        self.assertIn('<button type="button" class="acct-get" id="acctGet" hidden>Get the app</button>', build)
        self.assertIn('<button type="button" class="acct-item" id="acctInstall" hidden>Add to home screen</button>', build)
        self.assertIn('$("acctGet").addEventListener("click", addToHomeScreen);', build)
        self.assertIn('$("acctInstall").addEventListener("click", addToHomeScreen);', build)
        css = re.sub(r"/\*.*?\*/", "", read("style.css"), flags=re.S)
        self.assertRegex(css, r"\.acct-get\[hidden\]\s*\{\s*display:\s*none")
        # .acct-item sets display: block, which beats [hidden] on its own
        self.assertRegex(css, r"\.acct-item\[hidden\]\s*\{\s*display:\s*none")


class HomeBanner(unittest.TestCase):
    def setUp(self):
        self.app = read("app.js")

    def test_it_says_when_the_round_closes(self):
        banner = js_body(self.app, "function renderSubmitBanner() {")
        self.assertIn("var closes = PFML.closes(open.closes_at);", banner)
        self.assertIn('Closes \' + esc(closes.at) + " \\u00b7 " + esc(closes.left)', banner)

    def test_it_says_whether_you_have_a_track_in(self):
        self.assertIn("bannerMine(open);", js_body(self.app, "function renderSubmitBanner() {"))
        mine = js_body(self.app, "function bannerMine(round) {")
        self.assertIn("PFML.api.mySubmissions(round.id)", mine)
        # in once all of the round's tracks from them are
        self.assertIn("var all = mine.length >= n;", mine)
        self.assertIn('all ? "\\u2713 You\'re in"', mine)
        self.assertIn(': mine.length ? mine.length + " of your " + n + " tracks in" : "You haven\'t submitted yet";', mine)

    def test_one_deadline_wording_for_the_banner_and_the_submit_page(self):
        account = read("account.js")
        self.assertIn("function closes(iso) {", account)
        self.assertIn("PFML.closes = closes;", account)
        submit = read("submit.js")
        self.assertIn("PFML.closes(r.closes_at).at", submit)
        self.assertNotIn("function fromNow(", submit)
        self.assertNotIn("function when(", submit)

    def test_empty_parts_take_no_room(self):
        css = re.sub(r"/\*.*?\*/", "", read("style.css"), flags=re.S)
        self.assertRegex(css, r"\.sub-banner-mine:empty\s*\{\s*display:\s*none")
        self.assertRegex(css, r"\.sub-admin-status:empty\s*\{\s*display:\s*none")


class AdminStatus(unittest.TestCase):
    def setUp(self):
        self.sql = schema()
        self.fn = function(self.sql, "admin_invite_status")

    def test_schema_has_what_the_migration_adds(self):
        migration = (ROOT / "supabase" / "migrations" / "2026-10-24_admin_invite_status.sql").read_text(encoding="utf-8")
        self.assertIn(migration[migration.index("create or replace function public.admin_invite_status"):], self.sql)

    def test_only_the_admin_and_never_the_link_itself(self):
        self.assertRegex(self.fn, r"if not public\.is_admin\(\) then\s+raise exception")
        self.assertIn("returns table (competitor_id text, made_at timestamptz)", self.fn)
        self.assertNotRegex(self.fn, r"\bcode\b")
        self.assertIn("where i.claimed_by is null", self.fn)
        self.assertIn("security definer set search_path = public", self.fn)
        self.assertIn("revoke all on function public.admin_invite_status() from public, anon;", self.sql)
        self.assertIn("grant execute on function public.admin_invite_status() to authenticated;", self.sql)

    def test_the_invites_table_itself_stays_unreadable(self):
        self.assertNotRegex(self.sql, r"create policy[^;]*on public\.invites")
        for path in SITE.glob("*.js"):
            with self.subTest(path.name):
                self.assertNotRegex(path.read_text(encoding="utf-8"), r'from\("invites"\)')

    def test_the_panel_is_drawn_only_for_the_admin(self):
        # on the Commissioner page since 2026-10-25; a commissioner gets the
        # rounds, never the invite status
        page = read("commissioner.js")
        render = js_body(page, "function render() {")
        self.assertIn("if (isAdmin()) { renderPeople(); renderLeagueStatus(); }", render)
        self.assertEqual(page.count("renderLeagueStatus();"), 1)
        self.assertIn('function isAdmin() { return role() === "admin"; }', page)
        self.assertNotIn("renderLeagueStatus", read("submit.js"))

    def test_published_means_when_index_json_was_uploaded(self):
        published = js_body(read("auth.js"), "dataPublishedAt: function () {").split("},\n", 1)[0]
        self.assertIn('client.storage.from("league-data").list("", { limit: 100 })', published)
        self.assertIn('f.name === "index.json"', published)
        self.assertIn("index.updated_at", published)


if __name__ == "__main__":
    unittest.main()
