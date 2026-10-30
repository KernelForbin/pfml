"""The commissioner extras (README, Commissioner extras): allowed services,
submitter notes, a repeat rule within a round, and announcements. The
database rules as text (there's no Postgres here;
supabase/checks/2026-10-25_extras_rehearsal.sql plays them in the real
database and rolls back), the sender and the build, and the page wiring
(the pages were checked in a browser)."""
import json
import re
import unittest

from support import ROOT, build, quiet, sandbox
from test_reminders import js_body
from test_submissions import function, read, schema

SITE = ROOT / "site"
FN = ROOT / "supabase" / "functions" / "send-reminders" / "index.ts"
MIGRATION = ROOT / "supabase" / "migrations" / "2026-10-25_extras.sql"
REHEARSAL = ROOT / "supabase" / "checks" / "2026-10-25_extras_rehearsal.sql"


class TheDatabase(unittest.TestCase):
    def setUp(self):
        self.sql = schema()

    def test_the_migration_is_the_end_of_the_schema(self):
        mig = read(MIGRATION)
        self.assertIn(mig[mig.index("-- Which services a round takes, and what it does about a repeat within it:"):], self.sql)

    def test_every_round_keeps_what_it_has(self):
        for table in ("site_seasons", "site_rounds"):
            with self.subTest(table):
                self.assertIn(f"alter table public.{table} add column if not exists services text[] not null default '{{spotify,youtube,soundcloud}}';", self.sql)
                self.assertIn(f"alter table public.{table} add column if not exists repeat_rule text not null default 'warn';", self.sql)
        self.assertIn("repeat_rule in ('off', 'warn', 'block_song', 'block_artist'));", self.sql)
        self.assertIn("cardinality(services) between 1 and 3 and services <@ array['spotify', 'youtube', 'soundcloud']", self.sql)

    def test_only_the_rounds_services(self):
        fn = function(self.sql, "submit_track")
        self.assertIn("if not (p_platform = any(r.services)) then", fn)
        self.assertLess(fn.index("if not (p_platform = any(r.services)) then"), fn.index("insert into public.site_submissions"))

    def test_a_blocking_round_takes_tracks_only_with_their_description(self):
        fn = function(self.sql, "submit_track")
        self.assertIn("if r.repeat_rule in ('block_song', 'block_artist') and current_setting('pfml.checked_round', true) is distinct from p_round::text then", fn)
        desc = function(self.sql, "submit_described")
        # checked, then let through, then the gate shut again
        order = [desc.index(s) for s in ("if kinds && array['track', 'version', 'song'] then",
                                         "if r.repeat_rule = 'block_artist' and kinds && array['artist'] then",
                                         "perform set_config('pfml.checked_round', p_round::text, true);",
                                         "new_tag := public.submit_track(p_round, p_platform, p_track);",
                                         "perform set_config('pfml.checked_round', '', true);")]
        self.assertEqual(order, sorted(order))

    def test_the_check_is_one_at_a_time_and_counts_the_right_tracks(self):
        desc = function(self.sql, "submit_described")
        self.assertLess(desc.index("for update;"), desc.index("public.fp_kind("))
        # the track a send would swap doesn't count against itself
        self.assertIn("and not (r.songs_per_round = 1 and exists (select 1 from public.site_submission_owners o", desc)
        self.assertIn("if not public.fp_ok(p_song, p_names, p_text) then", desc)
        self.assertIn("o.user_id = uid and s.tag = new_tag;", desc)

    def test_notes(self):
        self.assertIn("alter table public.site_submissions add constraint site_submissions_note_length check (char_length(note) <= 1000);", self.sql)
        fn = function(self.sql, "set_submission_note")
        self.assertIn("where id = p_round and votes_on_site", fn)
        self.assertIn("(closed_at is not null or now() >= closes_at)", fn)
        self.assertIn("o.round_id = p_round and o.user_id = auth.uid() and s.tag = p_tag;", fn)
        # since 2026-10-25_note_toggle.sql the notes live in their own table,
        # and my_submission and the export read them there: test_note_toggle.py

    def test_announcements(self):
        self.assertIn("alter table public.site_announcements enable row level security;", self.sql)
        self.assertIn("grant select on table public.site_announcements to authenticated;", self.sql)
        self.assertNotRegex(self.sql, r"create policy[^;]*on public\.site_announcements\s+for (insert|update|delete|all)")
        for name in ("post_announcement", "delete_announcement"):
            with self.subTest(name):
                self.assertTrue(function(self.sql, name).split("begin", 1)[1].lstrip().startswith("if not public.is_commissioner() then"))
        claim = function(self.sql, "announcements_claim")
        self.assertIn("perform pg_advisory_xact_lock(hashtext('pfml.announcements_claim'));", claim)
        self.assertIn("update public.site_announcements a set pushed_at = now()\n     where a.pushed_at is null and a.created_at > now() - interval '1 day'", claim)
        self.assertIn("coalesce((select rs.announcements from public.reminder_settings rs where rs.user_id = m.user_id), true);", claim)
        self.assertIn("#variable_conflict use_column", claim)

    def test_the_bell_has_an_announcements_switch(self):
        self.assertIn("coalesce(s.announcements, true)", function(self.sql, "my_notification_choices"))
        self.assertIn("'voting', 'announcements') or p_on is null then", function(self.sql, "set_notification_choice"))
        self.assertIn('["announcements", "Announcements from the commissioners"]', read(SITE / "account.js"))

    def test_seasons_pass_them_on(self):
        self.assertIn("services = s.services, repeat_rule = s.repeat_rule\n   where season_key = p_key and closed_at is null and now() < closes_at;",
                      function(self.sql, "update_site_season"))
        for name in ("create_site_season", "add_site_season_round"):
            with self.subTest(name):
                # what a round hides from Spectators follows them in create_site_season (2026-10-29)
                self.assertRegex(function(self.sql, name), r"s\.songs_per_round, s\.downvotes, s\.max_down_per_track, s\.services, s\.repeat_rule[,)]")

    def test_grants(self):
        for sig in ("my_submission(uuid)", "submit_described(uuid, text, text, text, text[], text)", "set_submission_note(uuid, text, text)",
                    "post_announcement(text)", "delete_announcement(uuid)", "my_notification_choices()"):
            with self.subTest(sig):
                self.assertIn(f"revoke all on function public.{sig} from public, anon;", self.sql)
                self.assertIn(f"grant execute on function public.{sig} to authenticated;", self.sql)
        self.assertIn("revoke all on function public.announcements_claim() from public, anon, authenticated;", self.sql)
        self.assertIn("grant execute on function public.announcements_claim() to service_role;", self.sql)
        # a function dropped and made again loses its grants: they come after
        mig = read(MIGRATION)
        self.assertLess(mig.index("drop function if exists public.my_notification_choices();"),
                        mig.index("grant execute on function public.my_notification_choices() to authenticated;"))

    def test_the_rehearsal_keeps_nothing_and_plays_the_real_role(self):
        script = read(REHEARSAL)
        self.assertTrue(script.rstrip().endswith("raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;\nend $$;"))
        self.assertNotRegex(script, r"(?i)\bcommit\b(?! drop)")
        self.assertIn("execute 'set local role authenticated';", script)
        self.assertEqual(script.count("checks := checks + 1;"),
                         int(re.search(r"Rehearsal passed: (\d+) checks held", script).group(1)))


class TheSender(unittest.TestCase):
    def test_announcements_go_out_push_only(self):
        ts = read(FN)
        run = js_body(ts, "async function runDue(): Promise<Response> {", "")
        self.assertIn('const res = await rpc("announcements_claim", {});', run)
        self.assertIn("announced += await pushTo(a.subscriptions ?? [], announcementMessage(a), jwk);", run)
        self.assertLess(run.index("  if (jwk) {\n    const res = await rpc(\"announcements_claim\""), run.index("announced += await pushTo("))
        self.assertIn("return Response.json({ claimed: claims.length, sent, inbox, announced });", run)
        self.assertEqual([c for c in ts if ord(c) > 127], [])


class TheStats(unittest.TestCase):
    def test_a_site_tracks_note_is_its_comment(self):
        rnd = {"id": "n-r1", "season_key": "season4", "name": "Notes", "prompt": "", "created_at": "2026-11-01T00:00:00Z",
               "voting_ended_at": "2026-11-08T00:00:00Z", "spotify_playlist": None, "point_budget": 4, "nonvoters_keep_points": True,
               "submissions": [{"id": "s1", "tag": "A2", "platform": "youtube", "track": "aaaaaaaaaa1", "title": "T", "artist": "X",
                                "spotify_match": None, "position": 1, "submitter": "p1", "note": "Heard this live once."}],
               "votes": [{"submission": "s1", "voter": "p2", "points": 4, "comment": "", "cast_at": "2026-11-02T00:00:00Z"}]}
        with sandbox() as root, quiet():
            folder = root / "data" / "season4"
            folder.mkdir(parents=True)
            (folder / build.SITE_ROUNDS_FILE).write_text(json.dumps({"rounds": [rnd], "players": {"p1": "Ann", "p2": "Ben"}}), encoding="utf-8")
            data, _ = build.build_season(folder, "season4", "Season 4")
        self.assertEqual(data["rounds"][0]["songs"][0]["note"], "Heard this live once.")


class ThePages(unittest.TestCase):
    def setUp(self):
        self.submit = read(SITE / "submit.js")
        self.seasons = read(SITE / "seasons.js")

    def test_only_the_rounds_services_show_and_go(self):
        form = js_body(self.submit, "function renderForm() {")
        self.assertIn('b.hidden = allowed.indexOf(b.getAttribute("data-svc")) === -1;', form)
        self.assertIn("if (allowed.indexOf(state.service) === -1) setService(allowed[0]);", form)
        pick = js_body(self.submit, "function setPick(p, about) {")
        self.assertTrue(pick.lstrip().split("\n", 1)[1].lstrip().startswith(
            "if (p && state.round && servicesOf(state.round).indexOf(p.platform) === -1) {"))
        # a hidden button has to actually vanish (its CSS gives it a display)
        css = re.sub(r"/\*.*?\*/", "", read(SITE / "style.css"), flags=re.S)
        self.assertRegex(css, r"\.sub-svc\[hidden\]\s*\{\s*display:\s*none")

    def test_a_refused_service_keeps_its_message_and_the_round_says_what_it_takes(self):
        # found in the browser: the usual "check the player" line replaced
        # the refusal, and the form's text still offered Spotify
        self.assertIn("else if (p && state.pasted) showMsg(CHECK, \"\");", js_body(self.submit, "function onType() {"))
        form = js_body(self.submit, "function renderForm() {")
        self.assertIn('$("subOnly").hidden = allowed.length === 3;', form)
        self.assertIn('<p class="block-note sub-only" id="subOnly" hidden></p>', read(SITE / "submit.html"))

    def test_a_gauge_that_fails_leaves_the_round_check_showing(self):
        # found in the browser: one catch hid the repeat box when the gauge
        # failed, leaving Send off with no reason given
        check = js_body(self.submit, "function checkRound(p, key) {")
        self.assertIn("return PFMLSentiment.load().then(function () { if (gaugeKey === key) drawGauge(); }, function (err) { console.error(err); });", check)

    def test_the_repeat_rule_on_the_page(self):
        check = js_body(self.submit, "function checkRound(p, key) {")
        self.assertIn('ruleOf(r) === "off"', check)
        show = js_body(self.submit, "function showRepeats(found) {")
        self.assertIn('if (blocked.length) $("subSend").disabled = true;', show)
        blocked = js_body(self.submit, "function blockedBy(found) {")
        self.assertIn('rule === "block_artist" ? ["track", "version", "song", "artist"] : rule === "block_song" ? ["track", "version", "song"] : [];', blocked)
        send = js_body(self.submit, "function send(ev) {")
        self.assertIn('var blocking = ruleOf(r).indexOf("block") === 0 && typeof api().submitDescribed === "function";', send)
        self.assertIn("? fp.then(function (f) { return api().submitDescribed(r.id, p.platform, p.track, f || { song: \"\", names: [], text: \"\" }); })", send)

    def test_notes_on_the_page(self):
        send = js_body(self.submit, "function send(ev) {")
        self.assertIn('var note = r.votes_on_site ? $("subNote").value.trim() : "";', send)
        # the switch that goes with it: test_note_toggle.py
        self.assertIn("if (note) api().setSubmissionNote(r.id, tag, note, inVoting)", send)
        self.assertIn('$("subNoteBox").hidden = !(state.round && state.round.votes_on_site);', js_body(self.submit, "function renderForm() {"))
        self.assertIn("api().setSubmissionNote(state.round.id, tag, text, inVoting)", js_body(self.submit, "function saveNote(b) {"))
        # the round's list, on the round page since 2026-10-26
        # labelled as the submitter's, never with their name (asked 2026-10-27)
        self.assertIn("(s.note ? '<p class=\"sub-track-note\"><span class=\"sub-note-from\">From the submitter</span>' + esc(s.note) + \"</p>\" : \"\")",
                      js_body(read(SITE / "listen.js"), "function drawTracks(list) {"))
        voting = read(SITE / "voting.js")
        self.assertIn("(item.s.note ? '<p class=\"vt-track-note\">' + esc(item.s.note) + \"</p>\" : \"\")",
                      js_body(voting, "function resultRow(r, item, rank, votes, names) {"))

    def test_the_season_and_round_forms_set_them(self):
        rules = js_body(self.seasons, "function readRules(form) {")
        self.assertIn('if (!services.length) return { error: "Tick at least one service." };', rules)
        self.assertIn("services: d.services, repeat_rule: d.repeat_rule,", js_body(self.seasons, "function create() {"))
        cm = read(SITE / "commissioner.js")
        save = js_body(cm, "function saveRound(r) {")
        self.assertIn("var rules = window.PFMLSeasons.readRules($(\"subAdminForm\"));", save)
        self.assertLess(save.index("if (rules.error) return adminMsg(rules.error);"), save.index("api().updateSiteRound(r.id, fields)"))
        # with what it hides from Spectators since 2026-10-29
        self.assertIn("(upcoming || phase === \"submitting\" ? ruleFields(r, \"cmR-\" + r.id) + hideFields(r) : \"\")", js_body(self.seasons, "function roundRow(r, i, rounds) {"))

    def test_announcements_on_the_pages(self):
        cm = read(SITE / "commissioner.js")
        announce = js_body(cm, "function onAnnounce(ev) {")
        self.assertLess(announce.index("window.confirm(\"Post this"), announce.index("api().postAnnouncement(text)"))
        self.assertIn("renderAnnouncements();", js_body(cm, "function render() {"))
        home = js_body(read(SITE / "app.js"), "function renderAnnouncements() {")
        self.assertIn("var since = Date.now() - ANNOUNCE_DAYS * 864e5;", home)
        self.assertIn("return Date.parse(a.created_at) > since; }).slice(0, 3);", home)
        self.assertIn('<section class="shell announce" id="announceBox" hidden></section>', read(SITE / "index.html"))


if __name__ == "__main__":
    unittest.main()
