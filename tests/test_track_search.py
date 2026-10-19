"""Searching on the Submit page: the search-tracks Edge Function, its
cache table, and the page's wiring.

The function is TypeScript for Supabase's Deno runtime; there's no Deno
here, so these pin its rules as text, and its real behaviour is checked
once it's deployed (README, Submissions on the site, Searching). The page
was checked in a browser against a stand-in for the function."""
import re
import unittest

from support import ROOT

SITE = ROOT / "site"
FUNCTION = ROOT / "supabase" / "functions" / "search-tracks" / "index.ts"
MIGRATION = ROOT / "supabase" / "migrations" / "2026-10-19_search_cache.sql"


def read(path):
    return path.read_text(encoding="utf-8")


class EdgeFunction(unittest.TestCase):
    def setUp(self):
        self.ts = read(FUNCTION)
        self.handler = self.ts.split("Deno.serve(", 1)[1]

    def test_members_only_checked_before_anything_else(self):
        self.assertIn("rest/v1/rpc/is_member", self.ts)
        member_check = self.handler.index("isMember(")
        for later in ("req.json()", "spotifySearch(", "youtubeSearch(", "cached("):
            self.assertLess(member_check, self.handler.index(later), later)
        self.assertIn('return reply({ error: "members only" }, 401, origin);', self.handler)

    def test_answers_only_the_site(self):
        allowed = re.search(r"const ALLOWED_ORIGINS = \[([^\]]*)\]", self.ts).group(1)
        self.assertEqual(re.findall(r'"([^"]+)"', allowed),
                         ["https://pfml.fun", "http://localhost:8000", "http://127.0.0.1:8000"])
        self.assertNotIn('"Access-Control-Allow-Origin": "*"', self.ts)

    def test_takes_only_two_services_and_short_searches(self):
        self.assertIn('if (service !== "spotify" && service !== "youtube")', self.handler)
        self.assertIn("if (q.length < 1 || q.length > 120)", self.handler)

    def test_keys_come_from_secrets_and_youtube_uses_its_own_project(self):
        for name in ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "YOUTUBE_SEARCH_KEY"):
            self.assertIn(f'Deno.env.get("{name}")', self.ts)
        # the playlist builder's Google sign-in must never be what search spends
        self.assertNotIn("GOOGLE_CLIENT", self.ts)
        self.assertNotIn("REFRESH_TOKEN", self.ts)
        self.assertNotRegex(self.ts, r"sb_secret_|sb_publishable_[A-Za-z0-9]|AIza[0-9A-Za-z_-]{20}")

    def test_the_cache_never_learns_who_searched(self):
        remember = self.ts.split("async function remember(", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("JSON.stringify({ service, query, results, cached_on:", remember)
        self.assertNotRegex(remember, r"(?i)user|uid|authorization|member")

    def test_spotify_search_asks_for_at_most_ten(self):
        self.assertIn("type=track&limit=10", self.ts)

    def test_a_used_up_youtube_allowance_is_its_own_answer(self):
        self.assertIn('if (e instanceof QuotaError) return reply({ error: "quota" }, 200, origin);', self.handler)


class CacheTable(unittest.TestCase):
    def test_no_user_column_rls_on_and_no_policies(self):
        sql = read(ROOT / "supabase" / "schema.sql")
        table = sql[sql.index("create table if not exists public.search_cache"):]
        table = table[:table.index(");") + 2]
        self.assertNotRegex(table, r"user|uid|member")
        self.assertIn("alter table public.search_cache enable row level security", sql)
        self.assertNotRegex(sql, r"create policy[^;]*on public\.search_cache")

    def test_schema_has_what_the_migration_adds(self):
        migration = read(MIGRATION)
        body = migration[migration.index("create table if not exists public.search_cache"):]
        self.assertIn(body, read(ROOT / "supabase" / "schema.sql"))


class Page(unittest.TestCase):
    def setUp(self):
        self.js = read(SITE / "submit.js")

    def test_the_page_calls_the_function_by_its_folder_name(self):
        self.assertIn('client.functions.invoke("search-tracks"', read(SITE / "auth.js"))
        self.assertTrue(FUNCTION.exists())

    def test_enter_searches_and_never_sends_a_track(self):
        self.assertRegex(self.js, r'if \(ev\.key === "Enter"\) \{ ev\.preventDefault\(\); search\(\); \}')

    def test_three_service_buttons_and_each_can_search_its_own_site(self):
        html = read(SITE / "submit.html")
        self.assertEqual(re.findall(r'data-svc="(\w+)"', html), ["spotify", "youtube", "soundcloud"])
        for url in ("https://open.spotify.com/search/", "https://www.youtube.com/results?search_query=",
                    "https://soundcloud.com/search/sounds?q="):
            self.assertIn(url, self.js)

    def test_a_result_is_taken_from_the_service_that_was_searched(self):
        pick = self.js.split("function pickResult(ev) {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn("platform: state.results.service", pick)

    def test_links_still_work_in_the_same_box(self):
        on_type = self.js.split("function onType() {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn("if (looksLikeLink(text)) {", on_type)
        self.assertIn("parseLink(text)", on_type)

    def test_the_results_list_really_hides(self):
        css = re.sub(r"/\*.*?\*/", "", read(SITE / "style.css"), flags=re.S)
        self.assertRegex(css, r"\.sub-results\[hidden\]\s*\{\s*display:\s*none")


if __name__ == "__main__":
    unittest.main()
