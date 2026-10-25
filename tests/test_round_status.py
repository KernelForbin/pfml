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

    def test_the_icon_is_the_favicons_shape(self):
        spec = importlib.util.spec_from_file_location("make_icons", ROOT / "scripts" / "make_icons.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertIn("M30 74V26h22a14 14 0 010 28H44v20z", read("index.html"))
        self.assertIn("rx='22'", read("index.html"))
        self.assertEqual(mod.ICONS["icon-192.png"][1], 22)
        # inside the stem and the bowl; outside, and in the notch under the bowl
        self.assertTrue(mod.in_p(35, 70) and mod.in_p(60, 40))
        self.assertFalse(mod.in_p(50, 65) or mod.in_p(70, 30) or mod.in_p(25, 50))

    def test_the_deploy_guard_doesnt_mistake_it_for_league_data(self):
        # the workflow refuses *.json in site/; the manifest isn't named that
        self.assertFalse(list(SITE.glob("*.json")))
        self.assertIn("-name '*.json'", (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8"))


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
        self.assertIn("PFML.api.mySubmission(round.id)", mine)
        self.assertIn('mine ? "\\u2713 You\'re in" : "You haven\'t submitted yet"', mine)
        self.assertIn('if (mine) $("submitBannerGo").textContent = "Change your track \\u2192";', mine)

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
        submit = read("submit.js")
        admin = js_body(submit, "function renderAdmin() {")
        self.assertIn('if (!me || me.role !== "admin") { $("subAdmin").hidden = true; return; }', admin)
        self.assertIn("renderLeagueStatus();", admin.split('if (!me || me.role !== "admin")', 1)[1])
        self.assertEqual(submit.count("renderLeagueStatus();"), 1)

    def test_published_means_when_index_json_was_uploaded(self):
        published = js_body(read("auth.js"), "dataPublishedAt: function () {").split("},\n", 1)[0]
        self.assertIn('client.storage.from("league-data").list("", { limit: 100 })', published)
        self.assertIn('f.name === "index.json"', published)
        self.assertIn("index.updated_at", published)


if __name__ == "__main__":
    unittest.main()
