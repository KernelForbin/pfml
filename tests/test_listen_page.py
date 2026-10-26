"""Listening on the round page (asked 2026-10-26): a closed site round's
playlists, tracks and player live on its round page (listen.js), for good,
not on the Submit page until the next round opens. The browser code isn't
run here (no Node); README, Listening on the round page, says how it was
checked in a browser."""
import unittest

from support import ROOT
from test_reminders import js_body

SITE = ROOT / "site"
LISTEN = (SITE / "listen.js").read_text(encoding="utf-8")
APP = (SITE / "app.js").read_text(encoding="utf-8")
ROUNDS = (SITE / "rounds.js").read_text(encoding="utf-8")
SUBMIT = (SITE / "submit.js").read_text(encoding="utf-8")
SUBMIT_HTML = (SITE / "submit.html").read_text(encoding="utf-8")


class WhichRound(unittest.TestCase):
    def test_the_same_id_first_then_round_n_for_a_music_league_round(self):
        fn = js_body(LISTEN, "function statsIndex(statsRounds, site) {")
        self.assertLess(fn.index("if (statsRounds[i].id === site.id) return i;"), fn.index("/^Round (\\d+)\\b/"))
        self.assertIn("var m = !site.votes_on_site && /^Round (\\d+)\\b/.exec(site.name || \"\");", fn)
        self.assertIn("return n >= 1 && n <= statsRounds.length ? n - 1 : -1;", fn)

    def test_a_stats_page_finds_its_site_round_in_its_own_season(self):
        init = js_body(APP, "function initRound() {")
        self.assertIn("return x.season_key === key && window.PFMLListen.statsIndex(d.rounds, x) === i;", init)
        self.assertIn('if (site && $("rpListen")) window.PFMLListen.render($("rpListen"), site);', init)

    def test_a_site_link_shows_the_stats_once_the_round_is_in_them(self):
        init = js_body(APP, "function initRound() {")
        self.assertIn("var i = d ? window.PFMLListen.statsIndex(d.rounds, site) : -1;", init)
        self.assertIn("if (i >= 0) window.PFMLRounds.renderRoundPage(d, d.rounds[i].id);", init)
        self.assertIn("else window.PFMLRounds.renderSiteRoundPage(site,", init)
        self.assertIn('return PFML.loadJSON(site.season_key + ".json").catch(function () { return null; })', init)

    def test_without_the_site_rounds_its_just_the_stats(self):
        init = js_body(APP, "function initRound() {")
        self.assertIn("var siteRounds = PFML.api.siteRounds().catch(function (err) { console.error(err); return []; });", init)

    def test_both_kinds_of_page_have_the_listening_section(self):
        section = "'<section class=\"shell block rp-listen\" id=\"rpListen\" hidden></section>'"
        self.assertIn(section, js_body(ROUNDS, "function renderRoundPage(d, roundId) {"))
        self.assertIn(section, js_body(ROUNDS, "function renderSiteRoundPage(r, label) {"))
        self.assertIn("renderSiteRoundPage: renderSiteRoundPage", ROUNDS)


class TheSection(unittest.TestCase):
    def test_nothing_is_asked_for_before_submissions_close(self):
        render = js_body(LISTEN, "function render(host, r) {")
        self.assertLess(render.index('if (phase === "upcoming" || phase === "submitting") {'),
                        render.index("PFML.api.roundSubmissions(r.id)"))

    def test_the_app_note_names_the_apps_there_are_and_promises_nothing_locked(self):
        render = js_body(LISTEN, "function render(host, r) {")
        self.assertIn('var apps = r.spotify_playlist && r.youtube_playlist ? "the Spotify or YouTube app"\n'
                      '      : r.youtube_playlist ? "the YouTube app" : "the Spotify app";', render)
        self.assertIn("<b>Prefer an app?</b> The whole round as a playlist in ' +\n          apps +", render)
        # the user's call, 2026-10-26: no promise about a locked phone
        self.assertNotIn("locked", render)

    def test_playing_here_comes_first_and_the_apps_after_the_list(self):
        # the user's call, 2026-10-26: the app buttons at the top read as the
        # way to listen, and people left the page for YouTube
        render = js_body(LISTEN, "function render(host, r) {")
        order = [render.index(s) for s in ('<p class="ln-lead">Play the round here: tap any track below',
                                            '<div class="rp" id="lnPlayer"></div>', 'id="lnTracks"', "playlistButtons(r)")]
        self.assertEqual(order, sorted(order))
        buttons = js_body(LISTEN, "function playlistButtons(r) {")
        self.assertIn(">Open in Spotify</a>", buttons)
        self.assertIn(">Open in YouTube</a>", buttons)


class TrackDetails(unittest.TestCase):
    """Asked 2026-10-26: no per-track links off the site, and each track's
    length, album and year (kept by round_playlists.py)."""

    def test_no_track_links_off_the_site(self):
        draw = js_body(LISTEN, "function drawTracks(list) {")
        self.assertNotIn("<a ", draw)
        self.assertNotIn("trackUrl", LISTEN)

    def test_each_track_shows_what_is_known_of_its_length_album_and_year(self):
        details = js_body(LISTEN, "function detailsText(s) {")
        for line in ("if (s.seconds > 0) out.push(lengthText(s.seconds));", "if (s.album) out.push(s.album);",
                     "if (s.year) out.push(String(s.year));", 'return out.join(" · ");'):
            self.assertIn(line, details)
        draw = js_body(LISTEN, "function drawTracks(list) {")
        self.assertIn("(details ? '<small class=\"sub-track-meta\">' + esc(details) + \"</small>\" : \"\")", draw)
        self.assertIn('return h ? h + ":" + pad(m) + ":" + pad(s) : m + ":" + pad(s);', js_body(LISTEN, "function lengthText(seconds) {"))

    def test_the_page_asks_for_them_and_the_database_has_them(self):
        auth = (SITE / "auth.js").read_text(encoding="utf-8")
        self.assertIn("youtube_match, seconds, album, year\").eq(\"round_id\", roundId)", auth)
        sql = (ROOT / "supabase" / "schema.sql").read_text(encoding="utf-8")
        mig = (ROOT / "supabase" / "migrations" / "2026-10-26_track_details.sql").read_text(encoding="utf-8")
        self.assertIn(mig[mig.index("alter table public.site_submissions add column if not exists seconds"):], sql)
        for col in ("seconds integer\n  check (seconds between 1 and 86400)", "album text\n  check (char_length(album) <= 300)",
                    "year smallint\n  check (year between 1000 and 2100)"):
            self.assertIn(col, mig)


class TheSubmitPage(unittest.TestCase):
    def test_a_closed_round_links_to_its_round_page(self):
        self.assertIn('$("subListenLink").href = "round?site=" + encodeURIComponent(r.id);', SUBMIT)
        self.assertIn('<section class="shell block" id="subListen" hidden>', SUBMIT_HTML)

    def test_no_listening_left_on_it(self):
        for gone in ("PFMLPlayer", "roundOrder", "drawTracks", "markPlaying", "roundSubmissions"):
            with self.subTest(gone):
                self.assertNotIn(gone, SUBMIT)
        for gone in ('id="subList"', 'id="subTracks"', "player.js", "listen-demo.js"):
            with self.subTest(gone):
                self.assertNotIn(gone, SUBMIT_HTML)


if __name__ == "__main__":
    unittest.main()
