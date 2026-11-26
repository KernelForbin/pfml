"""The live room (asked 2026-11-25; README, The live room): one room at /tt
where members take turns DJing a track each, live, from YouTube or
SoundCloud, with a crowd, Awesome and Lame, and a chat that keeps its
history. Only the DJ playing, the admin or a commissioner can skip (the
user's call: Lames never skip).

The SQL runs in the user's rehearsal
(supabase/checks/2026-11-25_live_room_rehearsal.sql), and ran before that on
a local Postgres; tests/test_live_room.py checks the live functions are
there and turn strangers away. These pin the rules in the text; the page
was checked in a browser, with real YouTube and SoundCloud players."""
import re
import unittest

from support import ROOT
from test_reminders import js_body
from test_submissions import function, read, schema

SITE = ROOT / "site"
MIG = read(ROOT / "supabase" / "migrations" / "2026-11-25_live_room.sql")
REHEARSAL = read(ROOT / "supabase" / "checks" / "2026-11-25_live_room_rehearsal.sql")
TABLES = ("room_tracks", "room_plays", "room_state", "room_djs", "room_presence", "room_votes", "room_messages")
PAGE_FUNCTIONS = (("room_here", "bigint"), ("room_leave", ""), ("room_step_up", ""), ("room_step_down", ""), ("room_skip", ""),
                  ("room_remove_dj", "text"), ("room_vote", "int"), ("room_set_length", "bigint, int"), ("room_say", "text"),
                  ("room_remove_message", "bigint"), ("room_recent", ""), ("room_library", ""),
                  ("room_library_add", "text, text, text, text, int, boolean"), ("room_library_remove", "uuid"),
                  ("room_queue_set", "uuid[]"))
INNER = (("room_bump", ""), ("room_who", "uuid"), ("room_touch", ""), ("room_start_next", ""), ("room_advance", ""))


class TheDatabase(unittest.TestCase):
    def setUp(self):
        self.sql = schema()

    def test_schema_has_the_migration(self):
        self.assertIn(MIG[MIG.index("-- ---------------------------------------------------------------- tables"):], self.sql)

    def test_tables_are_closed_but_the_one_row_pages_listen_to(self):
        # a new table gets its grants explicitly (CLAUDE.md, from 2026-10-30)
        for table in TABLES:
            with self.subTest(table):
                self.assertRegex(MIG, rf"alter table public\.{table}\s+enable row level security;")
                self.assertRegex(MIG, rf"revoke all on table public\.{table}\s+from anon, authenticated;")
                if table != "room_state":
                    self.assertNotRegex(MIG, rf"grant [^;]* on table public\.{table} ")
        self.assertIn("grant select on table public.room_state to authenticated;", MIG)
        self.assertNotRegex(MIG, r"grant (insert|update|delete|all)[^;]* on table public\.room_state")
        self.assertIn('create policy "members read the room" on public.room_state\n'
                      "  for select to authenticated using (public.is_member());", MIG)

    def test_realtime_gets_only_that_row_and_only_where_it_exists(self):
        self.assertIn("if exists (select 1 from pg_publication where pubname = 'supabase_realtime')", MIG)
        self.assertEqual(re.findall(r"alter publication supabase_realtime add table public\.(\w+);", MIG), ["room_state"])

    def test_who_can_call_what(self):
        for name, args in PAGE_FUNCTIONS:
            with self.subTest(name):
                self.assertIn(f"revoke all on function public.{name}({args}) from public, anon;", MIG)
                self.assertIn(f"grant execute on function public.{name}({args}) to authenticated;", MIG)
        for name, args in INNER:
            with self.subTest(name):
                self.assertIn(f"revoke all on function public.{name}({args}) from public, anon, authenticated;", MIG)

    def test_members_only(self):
        for name in ("room_here", "room_step_up", "room_skip", "room_vote", "room_set_length", "room_say",
                     "room_library_add", "room_queue_set"):
            with self.subTest(name):
                self.assertIn("if not public.is_member() then", function(self.sql, name))
        for name in ("room_recent", "room_library"):
            with self.subTest(name):
                self.assertIn("public.is_member()", function(self.sql, name))

    def test_only_the_dj_the_admin_or_a_commissioner_skips(self):
        skip = function(self.sql, "room_skip")
        self.assertIn("if p.user_id is distinct from auth.uid() and not public.is_commissioner() then", skip)
        self.assertLess(skip.index("not public.is_commissioner() then"), skip.index("update public.room_plays set ended_at = now()"))
        # the user's call (2026-11-25): a Lame never skips a track
        vote = function(self.sql, "room_vote")
        for word in ("room_start_next", "room_advance", "ended_at", "skipped_by"):
            self.assertNotIn(word, vote)

    def test_one_track_each_in_the_order_they_stepped_up(self):
        nxt = function(self.sql, "room_start_next")
        self.assertIn("select * into d from public.room_djs where seq > last order by seq limit 1;", nxt)
        self.assertIn("select * into d from public.room_djs order by seq limit 1;", nxt)
        # the played track goes to the bottom of its DJ's queue
        self.assertIn("set queue_pos = (select coalesce(max(x.queue_pos), 0) + 1 from public.room_tracks x where x.user_id = d.user_id)", nxt)
        # a turn that comes with an empty queue takes its DJ off the decks
        self.assertIn("delete from public.room_djs where user_id = d.user_id;\n      continue;", nxt)
        self.assertIn("if not exists (select 1 from public.room_tracks where user_id = auth.uid() and queue_pos is not null) then",
                      function(self.sql, "room_step_up"))

    def test_the_room_keeps_its_own_time(self):
        adv = function(self.sql, "room_advance")
        self.assertIn("if now() >= p.started_at + make_interval(secs => coalesce(p.seconds, 600)) then", adv)
        # 90 seconds of silence: out of the crowd and off the decks
        self.assertIn("delete from public.room_presence where last_seen <= now() - interval '90 seconds';", adv)
        self.assertIn("delete from public.room_djs d where not exists (select 1 from public.room_presence x where x.user_id = d.user_id);", adv)
        here = function(self.sql, "room_here")
        self.assertIn("'now', now(),", here)
        self.assertLess(here.index("perform public.room_advance();"), here.index("return jsonb_build_object("))

    def test_a_length_is_measured_once_by_the_djs_page(self):
        fn = function(self.sql, "room_set_length")
        self.assertIn("if not found or p.length_known then\n    return;", fn)
        self.assertIn("and exists (select 1 from public.room_presence x where x.user_id = p.user_id) then\n    return;", fn)

    def test_the_chat_keeps_its_history_and_its_limits(self):
        say = function(self.sql, "room_say")
        self.assertIn("if char_length(btrim(coalesce(p_body, ''))) not between 1 and 280 then", say)
        self.assertIn("and created_at > now() - interval '1 minute') >= 20 then", say)
        self.assertIn("order by x.id desc limit 200) m", function(self.sql, "room_here"))
        gone = function(self.sql, "room_remove_message")
        self.assertIn("if m.user_id is distinct from auth.uid() and not public.is_admin() then", gone)
        # removed, not deleted: the row stays, the pages drop it
        self.assertNotIn("delete from", gone)
        self.assertNotRegex(MIG, r"delete from public\.room_messages")

    def test_votes_never_on_your_own_track(self):
        self.assertIn("if p.user_id = auth.uid() then\n    raise exception 'You can''t vote on your own track.';", function(self.sql, "room_vote"))

    def test_a_library_is_capped_and_plays_only_what_the_room_can(self):
        add = function(self.sql, "room_library_add")
        self.assertIn("if p_platform is null or p_platform not in ('youtube', 'soundcloud') then", add)
        self.assertIn("where user_id = auth.uid()) >= 500", add)

    def test_the_rehearsal_counts_its_checks(self):
        n = REHEARSAL.count("checks := checks + 1;")
        self.assertEqual(n, 14)
        self.assertIn(f'"Rehearsal passed: {n} checks held. Nothing was kept."', REHEARSAL)


class ThePage(unittest.TestCase):
    def setUp(self):
        self.html = read(SITE / "tt.html")
        self.js = read(SITE / "tt.js")

    def test_it_is_at_tt_and_loads_what_it_needs_in_order(self):
        srcs = re.findall(r'<script src="([^"]+)"', self.html)
        self.assertEqual(srcs[1:], ["config.js", "auth.js", "account.js", "sentiment.js", "tt.js", "app.js"])
        self.assertIn('<body class="gated" data-page="tt">', self.html)

    def test_listen_live_is_in_every_pages_top_bar(self):
        # asked 2026-11-25: a Listen Live pill after All-Time, lit on the room's own page
        nav = js_body(read(SITE / "app.js"), "function renderNav(index, activeKey) {")
        self.assertIn('live.href = "tt";', nav)
        self.assertIn("Listen Live';", nav)
        self.assertIn('live.setAttribute("aria-current", String(activeKey === "tt"));', nav)
        self.assertLess(nav.index("nav.appendChild(career);"), nav.index("nav.appendChild(live);"))
        # the room's page hands renderNav its own key
        self.assertIn('page === "tt") {', js_body(read(SITE / "app.js"), "function boot() {"))
        self.assertIn("@media (prefers-reduced-motion: reduce) { .live-dot { animation: none; } }", read(SITE / "style.css"))
        # one way in from the top bar, not a second name in the menu
        self.assertNotIn('href="tt"', read(SITE / "account.js"))

    def test_four_pills_fit_one_row_on_a_phone(self):
        # measured 2026-11-25: one row from 360px wide up with these, two
        # rows (a 144px top bar) without
        css = read(SITE / "style.css")
        self.assertRegex(css, r"@media \(max-width: 480px\) \{\n  \.seasons \{ gap: 5px; \}\n  \.season-tab \{ padding: 7px 8px; font-size: 0\.8rem; gap: 5px; \}")
        self.assertRegex(css, r"@media \(max-width: 400px\) \{\n  \.seasons \{ gap: 4px; \}\n  \.season-tab \{ padding: 7px 7px; font-size: 0\.76rem; gap: 4px; \}")

    def test_the_repeats_sign_is_gone_from_home(self):
        # a brief joke (2026-11-22 to 2026-11-25), taken down with its font
        home, app, css = read(SITE / "index.html"), read(SITE / "app.js"), read(SITE / "style.css")
        for text, needle in ((home, "rsign"), (home, "Bungee"), (app, "renderRepeatSign"), (css, ".rsign"), (css, "rs-bulb")):
            self.assertNotIn(needle, text)

    def test_nothing_plays_before_a_tap(self):
        # a browser starts sound only from a tap (an iPhone: only in a
        # player that already exists), so the page starts untuned and a
        # player made before the tap only cues its track
        self.assertIn("var tuned = false;", self.js)
        self.assertIn("playerVars: { autoplay: tuned ? 1 : 0, playsinline: 1,", self.js)
        self.assertIn('"&auto_play=" + (tuned ? "true" : "false")', self.js)
        tune = js_body(self.js, "function tuneIn() {")
        self.assertIn("yt.player.playVideo();", tune)
        self.assertIn("sc.widget.play();", tune)

    def test_players_follow_the_databases_clock(self):
        self.assertIn("return Math.max(0, (Date.now() + offset - Date.parse(st.play.started_at)) / 1000);", js_body(self.js, "function position() {"))
        self.assertIn("offset = Date.parse(state.now) - (sentAt + Date.now()) / 2;", js_body(self.js, "function refresh() {"))
        sync = js_body(self.js, "function sync() {")
        self.assertIn("if (Math.abs(yt.player.getCurrentTime() - pos) > DRIFT_S) yt.player.seekTo(pos, true);", sync)

    def test_it_says_its_here_well_inside_the_90_seconds(self):
        beat = int(re.search(r"var HEARTBEAT_MS = (\d+);", self.js).group(1))
        self.assertLessEqual(beat * 3, 90000)
        self.assertIn("beat = setInterval(refresh, live ? HEARTBEAT_MS : POLL_MS);", self.js)

    def test_skip_shows_only_to_who_may(self):
        acts = js_body(self.js, "function drawActs() {")
        self.assertIn("if (play && (play.dj === me || isCommish())) {", acts)
        self.assertEqual(self.js.count('data-act="skip"'), 1)
        # and nobody votes on their own track
        self.assertIn("if (play && play.dj !== me) {", acts)

    def test_a_track_that_cant_play_anywhere_skips_itself_for_its_dj_only(self):
        failed = js_body(self.js, "function playerFailed(playId, everywhere) {")
        self.assertIn("if (everywhere && st.play.dj === me && !skipSent[playId]) {", failed)

    def test_chat_text_is_escaped(self):
        self.assertIn("'</p><p class=\"tt-msg-body\">' + esc(m.body) + \"</p></div></li>\";", js_body(self.js, "function drawChat(force) {"))

    def test_it_asks_no_browser_boxes_and_keeps_clean_links(self):
        self.assertNotIn("window.confirm", self.js)
        self.assertNotIn(".html", self.js)

    def test_the_room_only_takes_youtube_and_soundcloud_links(self):
        parse = js_body(self.js, "function parseLink(raw) {")
        self.assertIn('return { error: "The room plays YouTube and SoundCloud. Paste a link from one of them." };', parse)
        self.assertNotIn("spotify", parse.lower())

    def test_the_site_says_so(self):
        features = read(SITE / "features.html")
        self.assertIn("<h3>The live room</h3>", features)
        self.assertRegex(features, r'<li data-shipped="2026-11-25">.*?<b>The live room\.</b>')
        self.assertIn("live room", read(SITE / "privacy.html"))


if __name__ == "__main__":
    unittest.main()
