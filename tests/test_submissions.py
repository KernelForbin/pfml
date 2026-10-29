"""Submissions on the site (/submit): the database rules that keep them
anonymous, even to the admin, and the page wiring around them.

There's no Postgres here, so these read supabase/schema.sql and the
migration as text and pin the rules that matter; the behaviour itself was
checked in a browser against a stand-in that follows the same rules, and
gets checked for real once the migration has run (README, Submissions on
the site)."""
import re
import unittest

from support import ROOT

SITE = ROOT / "site"
MIGRATION = ROOT / "supabase" / "migrations" / "2026-10-18_site_submissions.sql"
FUNCTIONS = ["submit_track", "my_submission", "withdraw_submission", "site_submission_count"]


def read(path):
    return path.read_text(encoding="utf-8")


def schema():
    return read(ROOT / "supabase" / "schema.sql")


def block(sql, start):
    """From `start` to the end of that statement (a function runs to its
    closing $$;). The last one, when there are several: schema.sql runs top
    to bottom, so a function a later migration redefines (it says so at its
    section's head) stands as last written."""
    i = sql.rindex(start)
    end = "$$;" if start.startswith("create or replace function") else ";\n"
    return sql[i:sql.index(end, i) + len(end)]


def function(sql, name):
    return block(sql, f"create or replace function public.{name}(")


class SameInBothPlaces(unittest.TestCase):
    def test_schema_has_every_line_the_migration_adds(self):
        # a fresh install and the live project end up with the same rules
        migration = read(MIGRATION)
        body = migration[migration.index("create table if not exists public.site_rounds"):]
        self.assertIn(body, schema())


class Anonymous(unittest.TestCase):
    def setUp(self):
        self.sql = schema()

    def test_a_submission_row_holds_no_user_and_no_time(self):
        table = block(self.sql, "create table if not exists public.site_submissions")
        self.assertNotRegex(table, r"user_id|auth\.uid|created_at|timestamptz")

    def test_who_sent_which_has_no_policies_at_all(self):
        self.assertIn("alter table public.site_submission_owners enable row level security", self.sql)
        self.assertNotRegex(self.sql, r"create policy[^;]*on public\.site_submission_owners")

    def test_submissions_are_read_only_and_only_once_the_round_has_closed(self):
        policies = re.findall(r"create policy[^;]*on public\.site_submissions\b[^;]*;", self.sql)
        self.assertEqual(len(policies), 1, policies)
        self.assertIn("for select", policies[0])
        self.assertIn("public.is_member()", policies[0])
        self.assertIn("r.closed_at is not null or now() >= r.closes_at", policies[0])

    def test_only_commissioners_open_or_change_a_round(self):
        # the last policy for each is the one that stands: commissioners
        # (the admin among them) since 2026-10-25, deleting the admin's alone
        for verb, who in (("insert", "public.is_commissioner()"), ("update", "public.is_commissioner()"), ("delete", "public.is_admin()")):
            with self.subTest(verb):
                policy = re.findall(r"create policy[^;]*on public\.site_rounds\s+for " + verb + r"[^;]*;", self.sql)[-1]
                self.assertIn(who, policy)
                self.assertNotIn("is_member", policy)

    def test_functions_that_touch_owners_only_ever_match_the_caller(self):
        for name in ("my_submission", "withdraw_submission"):
            with self.subTest(name):
                self.assertIn("o.user_id = auth.uid()", function(self.sql, name))
        submit = function(self.sql, "submit_track")
        self.assertIn("uid uuid := auth.uid();", submit)
        self.assertIn("o.user_id = uid", submit)
        self.assertIn("values (mine, p_round, uid)", submit)

    def test_the_count_is_a_number_and_only_for_members(self):
        count = function(self.sql, "site_submission_count")
        self.assertIn("returns integer", count)
        self.assertIn("public.is_member()", count)
        self.assertNotIn("owners", count)

    def test_no_page_code_reads_the_owners_table(self):
        for path in SITE.glob("*.js"):
            with self.subTest(path.name):
                self.assertNotIn("site_submission_owners", read(path))


class Writes(unittest.TestCase):
    def setUp(self):
        self.sql = schema()
        self.submit = function(self.sql, "submit_track")

    def test_every_function_is_locked_down_like_the_existing_ones(self):
        for name in FUNCTIONS:
            with self.subTest(name):
                fn = function(self.sql, name)
                self.assertIn("security definer set search_path = public", fn)
                args = re.search(r"public\." + name + r"\(([^)]*)\)", fn).group(1)
                types = ", ".join(a.split()[1] for a in args.split(","))
                self.assertIn(f"revoke all on function public.{name}({types}) from public, anon;", self.sql)
                self.assertIn(f"grant execute on function public.{name}({types}) to authenticated;", self.sql)

    def test_submit_checks_membership_and_the_deadline_and_locks_the_round(self):
        # each check has to refuse, not just be mentioned
        self.assertRegex(self.submit, r"if not public\.is_member\(\) then\s+raise exception")
        self.assertIn("for update", self.submit)
        self.assertRegex(self.submit, r"if r\.closed_at is not null or now\(\) >= r\.closes_at then\s+raise exception")
        self.assertRegex(function(self.sql, "withdraw_submission"),
                         r"\(closed_at is not null or now\(\) >= closes_at\)\) then\s+raise exception")

    def test_submit_accepts_exactly_the_track_shapes_the_table_allows(self):
        table = block(self.sql, "create table if not exists public.site_submissions")
        shapes = lambda text, col: re.findall(r"\(" + col + r"platform = '(\w+)'\s+and " + col + r"track ~ '([^']+)'\)", text)
        self.assertEqual(shapes(self.submit, "p_"), shapes(table, ""))
        self.assertEqual(len(shapes(table, "")), 3)

    def test_the_page_reads_links_into_the_same_shapes(self):
        js = read(SITE / "submit.js")
        table = block(self.sql, "create table if not exists public.site_submissions")
        sql_shape = dict(re.findall(r"platform = '(\w+)'\s+and track ~ '([^']+)'", table))
        self.assertIn("var SPOTIFY_ID = /" + sql_shape["spotify"] + "/;", js)
        self.assertIn("var YOUTUBE_ID = /" + sql_shape["youtube"] + "/;", js)
        self.assertIn("var SOUNDCLOUD_PART = /^[a-z0-9_-]+$/;", js)
        self.assertIn("[a-z0-9_-]{1,100}/[a-z0-9_-]{1,200}", sql_shape["soundcloud"])
        self.assertIn("user.length <= 100 && slug.length <= 200", js)

    def test_tags_are_drawn_from_the_letters_and_digits_the_table_allows(self):
        table = block(self.sql, "create table if not exists public.site_submissions")
        allowed = re.search(r"tag ~ '\^\[([^\]]+)\]\[([^\]]+)\]\$'", table)
        letters = "".join(chr(c) for c in range(ord("A"), ord("Z") + 1) if re.fullmatch("[" + allowed.group(1) + "]", chr(c)))
        self.assertIn(f"substr('{letters}', 1 + floor(random() * {len(letters)})::int, 1)", self.submit)
        lo, hi = allowed.group(2).split("-")
        self.assertIn(f"({lo} + floor(random() * {int(hi) - int(lo) + 1})::int)::text", self.submit)

    def test_one_track_per_member_and_no_track_twice_in_a_round(self):
        owners = block(self.sql, "create table if not exists public.site_submission_owners")
        self.assertIn("unique (round_id, user_id)", owners)
        subs = block(self.sql, "create table if not exists public.site_submissions")
        self.assertIn("unique (round_id, platform, track)", subs)
        self.assertIn("unique (round_id, tag)", subs)


class PageCode(unittest.TestCase):
    def test_every_rpc_the_site_calls_exists_in_the_schema(self):
        sql = schema()
        for name in re.findall(r'client\.rpc\("(\w+)"', read(SITE / "auth.js")):
            with self.subTest(name):
                self.assertIn(f"create or replace function public.{name}(", sql)

    def test_every_element_the_code_looks_up_exists(self):
        html, js = read(SITE / "submit.html"), read(SITE / "submit.js")
        for el_id in sorted(set(re.findall(r'\$\("(\w+)"\)', js))):
            with self.subTest(el_id):
                self.assertTrue(f'id="{el_id}"' in html or f'id="{el_id}"' in js, el_id)

    def test_the_page_is_reachable_from_the_menu_and_the_home_page(self):
        self.assertIn('href="submit">Submit a track', read(SITE / "account.js"))
        self.assertIn('id="submitBanner"', read(SITE / "index.html"))
        app = read(SITE / "app.js")
        home = app.split("function initHome() {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn("renderSubmitBanner();", home)
        banner = app.split("function renderSubmitBanner() {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn('href="submit"', banner)
        boot = app.split("function boot() {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn('page === "submit"', boot)

    def test_members_arent_asked_to_link_a_submission_in_music_league(self):
        # Dropped 2026-10-19: voting stays in Music League as usual, so no
        # page or playlist asks anyone to copy a tag into a Music League note.
        for path in (SITE / "submit.html", SITE / "submit.js", SITE / "features.html", ROOT / "scripts" / "round_playlists.py"):
            with self.subTest(path.name):
                self.assertNotRegex(read(path), r"(?i)placeholder['’]s note|in its note|Music League notes?\b")

    def test_boxes_the_code_hides_really_hide(self):
        # The emoji search lesson (CLAUDE.md): a class that sets display
        # beats [hidden] unless [hidden] is restated for it.
        css = re.sub(r"/\*.*?\*/", "", read(SITE / "style.css"), flags=re.S)
        for cls in ("sub-embed", "sub-actions"):
            with self.subTest(cls):
                self.assertRegex(css, r"\." + cls + r"\[hidden\]\s*\{\s*display:\s*none")


class WhoIsIn(unittest.TestCase):
    """x/20 submitted, and who has and hasn't (the user's call, 2026-10-23):
    who has a track in, never which track."""

    def setUp(self):
        self.sql = schema()
        self.fn = function(self.sql, "site_round_submitters")
        self.js = read(SITE / "submit.js")

    def test_schema_has_what_the_migration_adds(self):
        migration = read(ROOT / "supabase" / "migrations" / "2026-10-23_round_submitters.sql")
        body = migration[migration.index("create or replace function public.site_round_submitters"):]
        self.assertIn(body, self.sql)

    def test_it_answers_player_ids_only_in_id_order_for_members(self):
        self.assertIn("returns setof text", self.fn)
        self.assertIn("select m.competitor_id\n", self.fn)
        self.assertNotRegex(self.fn, r"\b(track|platform|tag|title|artist|position|fp_\w+|site_submissions)\b")
        # id order, so not even the order people sent them
        self.assertIn("order by m.competitor_id;", self.fn)
        self.assertIn("and public.is_member()", self.fn)
        self.assertIn("security definer set search_path = public", self.fn)
        self.assertIn("revoke all on function public.site_round_submitters(uuid) from public, anon;", self.sql)
        self.assertIn("grant execute on function public.site_round_submitters(uuid) to authenticated;", self.sql)

    def body(self, js, signature):
        return js.split(signature, 1)[1].split("\n  }\n", 1)[0]

    def test_the_submit_page_counts_out_of_the_players_taking_part(self):
        who = self.body(self.js, "function renderWho(r, open) {")
        # out of the round's DJs; its Spectators are listed apart (2026-10-29)
        self.assertIn("api().roundSubmitters(r.id), api().people(), PFML.roundDJs(r), PFML.roundRoster(r)", who)
        self.assertIn("var players = res[2];", who)
        self.assertIn('$("subCount").innerHTML = "<b>" + done.length + "/" + players.length + "</b> submitted"', who)
        # in once all of the round's songs from them are; until then pending,
        # with how many so far
        self.assertIn("(res[0] || []).forEach(function (id) { sent[id] = (sent[id] || 0) + 1; });", who)
        self.assertIn("var done = players.filter(function (p) { return sent[p.id] >= n; });", who)
        self.assertIn("var pending = players.filter(function (p) { return !(sent[p.id] >= n); })", who)
        # who's playing: the season's own list when it was set up on the
        # site, else everyone in its latest finished round (index.json)
        players = self.body(read(SITE / "account.js"), "function seasonPlayers(seasonKey) {")
        self.assertIn("if (list && list.length) return list;", players)
        self.assertIn("return s && s.activePlayers && s.activePlayers.length ? s.activePlayers : null;", players)
        self.assertLess(players.index("api_.seasonRoster(seasonKey)"), players.index('PFML.loadJSON("index.json")'))

    def test_players_who_havent_joined_the_site_are_marked(self):
        who = self.body(self.js, "function renderWho(r, open) {")
        self.assertIn("linked[res[1][u].competitorId] = true;", who)
        group = self.body(self.js, "function whoGroup(kind, title, list, linked, none) {")
        self.assertIn('(linked[p.id] ? "" : \'<small class="sub-not-joined">not joined yet</small>\')', group)
        self.assertIn("PFML.avatar(p.id, p.name)", group)

    def test_the_list_has_its_own_section_below_the_picker(self):
        # twenty names in the round card pushed the form off a phone screen
        html = read(SITE / "submit.html")
        self.assertLess(html.index('id="subForm"'), html.index('id="subWhoBox"'))
        self.assertIn('<div class="sub-who" id="subWho"></div>', html.split('id="subWhoBox"', 1)[1].split("</section>", 1)[0])
        self.assertIn('"subWhoBox"', self.body(self.js, "function render() {"))
        who = self.body(self.js, "function renderWho(r, open) {")
        self.assertIn('$("subWhoBox").hidden = false;', who)
        self.assertIn('<a href="#subWhoBox">See who</a>', who)

    def test_without_the_list_or_the_function_it_still_counts_tracks(self):
        who = self.body(self.js, "function renderWho(r, open) {")
        self.assertIn('if (typeof api().roundSubmitters !== "function") { trackCount(r, open); return; }', who)
        self.assertIn("if (!players) { trackCount(r, open); return; }", who)
        self.assertIn(".catch(function (err) { console.error(err); trackCount(r, open); });", who)

    def test_the_home_banner_shows_the_count(self):
        app = read(SITE / "app.js")
        self.assertIn("bannerCount(open);", self.body(app, "function renderSubmitBanner() {"))
        count = self.body(app, "function bannerCount(round) {")
        # out of the round's DJs: a Spectator sends no track (2026-10-29)
        self.assertIn("Promise.all([PFML.roundDJs(round), PFML.api.roundSubmitters(round.id)])", count)
        self.assertIn('$("submitBannerCount").textContent = done + "/" + players.length + " submitted";', count)

    def test_empty_boxes_take_no_room(self):
        css = re.sub(r"/\*.*?\*/", "", read(SITE / "style.css"), flags=re.S)
        self.assertRegex(css, r"\.sub-who:empty\s*\{\s*display:\s*none")
        self.assertRegex(css, r"\.sub-banner-count:empty\s*\{\s*display:\s*none")


class RoundOrder(unittest.TestCase):
    """A closed round's tracks: one shuffle, the same for everyone from the
    close and the same as the playlists, with nothing about who sent a track
    or when in it; then Shuffle and Original order for each listener (the
    user's calls, 2026-10-25). The hash itself is pinned against the
    playlist script's in test_round_playlists.py."""

    def setUp(self):
        # the list moved with listening to the round page (listen.js), 2026-10-26
        self.listen = read(SITE / "listen.js")
        self.account = read(SITE / "account.js")

    def body(self, js, signature):
        return js.split(signature, 1)[1].split("\n  }\n", 1)[0]

    def test_everyone_starts_from_the_rounds_one_shuffle(self):
        render = self.body(self.listen, "function render(host, r) {")
        self.assertIn("rows = PFML.roundOrder(r.id, rows || []);", render)
        self.assertIn("var list = { original: rows, order: rows, player: null, built: built, ballot: null };", render)
        # the old tag order is gone, and nothing else sorts the list
        self.assertNotIn("a.tag < b.tag", self.listen)
        self.assertIn("PFML.roundOrder = roundOrder;", self.account)

    def test_the_order_comes_from_the_round_and_the_tracks_alone(self):
        order = self.body(self.account, "function roundOrder(roundId, rows) {")
        self.assertIn("return rows.slice().sort(function (a, b) { return a.position - b.position; });", order)
        key = self.body(self.account, "function shuffleKey(roundId, s) {")
        self.assertNotRegex(key, r"\.tag|\.id\b|created|user|owner")

    def test_shuffle_is_for_this_listener_and_never_saved(self):
        shuffle = self.body(self.listen, "function shuffled(list) {")
        self.assertIn("Math.random()", shuffle)
        self.assertIn("var next = playing ? [playing].concat(rest) : rest.slice();", shuffle)
        for name in ("function shuffled(list) {", "function reorder(list, order) {"):
            self.assertNotRegex(self.body(self.listen, name), r"api\b|localStorage|sessionStorage")

    def test_original_order_puts_back_what_everyone_first_saw(self):
        render = self.body(self.listen, "function render(host, r) {")
        self.assertIn('$("lnOriginal").onclick = function () { reorder(list, list.original); };', render)
        self.assertIn("list.player.setOrder(order);", self.body(self.listen, "function reorder(list, order) {"))
        self.assertIn('$("lnOriginal").hidden = !mixed;', self.body(self.listen, "function drawTracks(list) {"))

    def test_the_list_is_numbered_in_play_order(self):
        draw = self.body(self.listen, "function drawTracks(list) {")
        self.assertIn("list.order.map(function (s, i) {", draw)
        self.assertIn("'<span class=\"sub-pos\">' + (i + 1) + \"</span>\"", draw)

    def test_the_player_follows_a_new_order_without_stopping(self):
        player = read(SITE / "player.js")
        # nested inside mount(), so it closes at four spaces
        set_order = player.split("function setOrder(list) {", 1)[1].split("\n    }\n", 1)[0]
        self.assertIn("tracks = list;", set_order)
        self.assertIn("index = tracks.indexOf(playing);", set_order)
        self.assertNotIn("stop(", set_order)
        self.assertIn("setOrder: setOrder,", player)

    def test_the_buttons(self):
        self.assertIn("'<div class=\"sub-order\" id=\"lnOrder\" hidden>' +", self.listen)
        self.assertIn("'<button type=\"button\" class=\"sub-btn sub-btn-quiet\" id=\"lnOriginal\" hidden>Original order</button>' +", self.listen)
        css = re.sub(r"/\*.*?\*/", "", read(SITE / "style.css"), flags=re.S)
        self.assertRegex(css, r"\.sub-order\[hidden\], \.sub-order \.sub-btn\[hidden\] \{ display: none; \}")


if __name__ == "__main__":
    unittest.main()
