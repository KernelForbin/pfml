"""Repeats within an open round, on the Submit page: the database rules that
keep the round's tracks unread while still saying what kind of repeat a pick
would be, and the page wiring around them.

No Postgres here, so the SQL is pinned as text; fp_kind's rules run against
the live database in test_live_round_repeats.py once the migration is in,
and the page was checked in a browser against a stand-in that follows the
same rules (README, Submissions on the site, Repeats in this round)."""
import re
import unittest

from support import ROOT
from test_submissions import block, function, read, schema

SITE = ROOT / "site"
MIGRATION = ROOT / "supabase" / "migrations" / "2026-10-23_round_repeats.sql"
CALLED = {"describe_submission": "uuid, text, text, text, text[], text",
          "my_submission_described": "uuid",
          "round_repeats": "uuid, text, text, text, text[], text"}
HELPERS = {"fp_has": "text, text", "fp_name_in": "text, text", "fp_ok": "text, text[], text",
           "fp_kind": "text, text, text, text[], text, text, text, text, text[], text"}


class SameInBothPlaces(unittest.TestCase):
    def test_schema_has_every_line_the_migration_adds(self):
        migration = read(MIGRATION)
        body = migration[migration.index("alter table public.site_submissions add column if not exists fp_song"):]
        self.assertIn(body, schema())


class StillAnonymous(unittest.TestCase):
    def setUp(self):
        self.sql = schema()
        self.check = function(self.sql, "round_repeats")

    def test_the_check_answers_kinds_only(self):
        self.assertIn("returns text[]", self.check)
        self.assertIn("array_agg(distinct x.kind)", self.check)
        # nothing that could say which track, or whose
        self.assertNotRegex(self.check, r"\b(tag|title|artist|position|user_id\s*,)\b")
        self.assertNotRegex(self.check, r"return\s+query|setof")

    def test_the_callers_own_track_is_left_out(self):
        self.assertIn("not exists (select 1 from public.site_submission_owners o", self.check)
        self.assertIn("o.user_id = auth.uid()", self.check)

    def test_members_only_and_only_plain_words(self):
        for name in ("round_repeats", "describe_submission"):
            with self.subTest(name):
                fn = function(self.sql, name)
                self.assertRegex(fn, r"if not public\.is_member\(\) then\s+raise exception")
                self.assertRegex(fn, r"if not public\.fp_ok\(p_song, p_names, p_text\) then\s+raise exception")

    def test_a_fingerprint_left_from_another_track_is_ignored(self):
        self.assertIn("s.fp_for is not distinct from s.platform || ':' || s.track as described", self.check)
        for col in ("fp_song", "fp_names", "fp_text"):
            self.assertIn(f"case when d.described then s.{col} else", self.check)

    def test_describing_touches_only_the_callers_current_track_while_open(self):
        fn = function(self.sql, "describe_submission")
        self.assertIn("o.user_id = auth.uid()", fn)
        self.assertIn("s.platform = p_platform and s.track = p_track", fn)
        self.assertIn("fp_for = s.platform || ':' || s.track", fn)
        self.assertRegex(fn, r"\(closed_at is not null or now\(\) >= closes_at\)\) then\s+raise exception")

    def test_whether_mine_is_described_reads_only_mine(self):
        fn = function(self.sql, "my_submission_described")
        self.assertIn("returns boolean", fn)
        self.assertIn("o.user_id = auth.uid()", fn)

    def test_existing_policies_still_hide_an_open_rounds_tracks(self):
        policies = re.findall(r"create policy[^;]*on public\.site_submissions\b[^;]*;", self.sql)
        self.assertEqual(len(policies), 1, policies)


class LockedDown(unittest.TestCase):
    def setUp(self):
        self.sql = schema()

    def test_the_page_calls_are_members_only_and_definer(self):
        for name, types in CALLED.items():
            with self.subTest(name):
                self.assertIn("security definer set search_path = public", function(self.sql, name))
                self.assertIn(f"revoke all on function public.{name}({types}) from public, anon;", self.sql)
                self.assertIn(f"grant execute on function public.{name}({types}) to authenticated;", self.sql)

    def test_the_helpers_are_pure_and_not_for_anon(self):
        for name, types in HELPERS.items():
            with self.subTest(name):
                fn = function(self.sql, name)
                self.assertIn("immutable", fn)
                self.assertNotIn("security definer", fn)
                self.assertNotIn("auth.uid()", fn)
                self.assertIn(f"revoke all on function public.{name}({types}) from public, anon;", self.sql)


class PageAndDatabaseAgree(unittest.TestCase):
    def setUp(self):
        self.sql = schema()
        self.js = read(SITE / "submit.js")

    def test_the_page_knows_every_kind_the_database_can_answer(self):
        kinds = re.findall(r"then '(\w+)'", function(self.sql, "fp_kind"))
        self.assertEqual(kinds, ["track", "version", "song", "title", "artist"])
        listed = re.findall(r'\["(\w+)", "', self.js.split("var REPEAT_KINDS = [", 1)[1].split("];", 1)[0])
        self.assertEqual(listed, kinds)

    def test_the_page_folds_to_the_words_the_database_takes(self):
        # fp_ok and the column checks allow [a-z0-9 ] only, with these limits
        self.assertIn(".replace(/[^a-z0-9]+/g, \" \").trim();", read(SITE / "sentiment.js"))
        ok = function(self.sql, "fp_ok")
        self.assertIn("'^[a-z0-9 ]{0,300}$'", ok)
        self.assertIn("'^[a-z0-9 ]{0,600}$'", ok)
        self.assertIn("<= 12", ok)
        self.assertIn("'^[a-z0-9 ]{1,120}$'", ok)
        fp = self.js.split("function fpOf(title, artists, text) {", 1)[1].split("\n  }\n", 1)[0]
        for limit in (".slice(0, 12)", ".slice(0, 120)", "songKey(title).slice(0, 300)", "fold(text).slice(0, 600)"):
            self.assertIn(limit, fp)
        self.assertIn("return n && all.indexOf(n) === i;", fp)   # no empty or repeated names

    def test_the_columns_take_what_fp_ok_allows(self):
        for line in ("add column if not exists fp_song text\n  check (fp_song ~ '^[a-z0-9 ]{0,300}$');",
                     "add column if not exists fp_names text[]\n  check (cardinality(fp_names) <= 12);",
                     "add column if not exists fp_text text\n  check (fp_text ~ '^[a-z0-9 ]{0,600}$');"):
            self.assertIn(line, self.sql)


class PageWiring(unittest.TestCase):
    def setUp(self):
        self.js = read(SITE / "submit.js")

    def body(self, signature):
        return self.js.split(signature, 1)[1].split("\n  }\n", 1)[0]

    def test_a_sent_track_gets_its_fingerprint(self):
        send = self.body("function send(ev) {")
        self.assertIn("var fp = state.fp && state.fp.key === key ? state.fp.promise : fingerprintOf(p);", send)
        self.assertIn("describe(r, p, fp);", send.split("submitTrack(", 1)[1])

    def test_a_track_sent_without_one_gets_it_on_its_owners_next_visit(self):
        self.assertIn("describeIfMissing(state.round, mine);", self.body("function load() {"))
        missing = self.body("function describeIfMissing(r, mine) {")
        self.assertIn("if (done === false) describe(r, mine, fingerprintOf(mine));", missing)
        self.assertIn("!isOpen(r)", missing)

    def test_the_check_runs_for_every_pick_but_only_in_an_open_round(self):
        self.assertIn("checkRound(p, key);", self.body("function gaugeFor(p, about) {"))
        check = self.body("function checkRound(p, key) {")
        self.assertIn("if (!r || !isOpen(r) || typeof api().roundRepeats !== \"function\") return;", check)
        self.assertIn("if (gaugeKey === key && found) showRepeats(found);", check)

    def test_a_video_is_named_by_spotify_only_when_title_and_artist_both_appear_in_it(self):
        named = self.body("function nameFromSpotify(text, title) {")
        self.assertIn("return hasWords(words, S.songKey(r.title)) &&", named)
        self.assertIn("S.nameList(String(r.artist || \"\").split(\", \")).some(function (n) { return hasWords(words, n); });", named)

    def test_a_channel_never_stands_in_for_the_artist(self):
        # "KEXP" or "BBC" as an artist would make every session video match
        fp = self.body("function fingerprint(p, about) {")
        self.assertIn('return hit ? fpOf(hit.title, String(hit.artist || "").split(", "), text) : fpOf("", [], text);', fp)
        self.assertNotIn("about.artists, text", fp)

    def test_the_box_really_hides(self):
        css = re.sub(r"/\*.*?\*/", "", read(SITE / "style.css"), flags=re.S)
        self.assertRegex(css, r"\.sub-repeats\[hidden\]\s*\{\s*display:\s*none")


if __name__ == "__main__":
    unittest.main()
