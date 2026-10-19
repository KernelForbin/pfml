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
    closing $$;)."""
    i = sql.index(start)
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

    def test_only_the_admin_opens_or_changes_a_round(self):
        for verb in ("insert", "update", "delete"):
            with self.subTest(verb):
                policy = re.search(r"create policy[^;]*on public\.site_rounds\s+for " + verb + r"[^;]*;", self.sql).group(0)
                self.assertIn("public.is_admin()", policy)
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

    def test_boxes_the_code_hides_really_hide(self):
        # The emoji search lesson (CLAUDE.md): a class that sets display
        # beats [hidden] unless [hidden] is restated for it.
        css = re.sub(r"/\*.*?\*/", "", read(SITE / "style.css"), flags=re.S)
        for cls in ("sub-embed", "sub-actions"):
            with self.subTest(cls):
                self.assertRegex(css, r"\." + cls + r"\[hidden\]\s*\{\s*display:\s*none")


if __name__ == "__main__":
    unittest.main()
