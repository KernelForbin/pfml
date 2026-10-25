"""The daily security check (README, Security check): scripts/security_check.py
against a made-up world (no network), the time it puts on the privacy page
(scripts/stamp_check_time.py), and the workflows that run it. The real
services are checked by test_live_security_check.py."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from support import ROOT

import security_check as sc  # noqa: E402  (support puts scripts/ on the path)
import stamp_check_time as stc  # noqa: E402

SINCE = "2026-10-24T11:00:00Z"
SCHEMA = (ROOT / "supabase" / "schema.sql").read_text(encoding="utf-8")


def read_root(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


class World:
    """A fake of everything the check talks to, clean by default. Tests
    change one thing and expect the check to notice."""

    def __init__(self):
        self.url, _ = sc.project()
        self.affecting = []             # advisories GitHub says affect a pinned version
        self.package_advisories = []    # advisories for a package, any version
        self.repo_advisories = {"supabase/storage": [], "supabase/auth": []}
        self.versions = {"/storage/v1/version": "1.80.2", "/auth/v1/health": '{"version":"v2.197.0","name":"GoTrue"}'}
        self.readable = {}              # table -> rows a stranger gets
        self.insert_reply = (401, '{"code":"42501","message":"new row violates row-level security policy"}')
        self.rpc_open = set()           # functions a stranger may call
        self.bucket_files = []
        self.public_bucket = False
        self.search_status = 401
        self.calls = []

    def __call__(self, method, url, headers=None, body=None):
        self.calls.append((method, url))
        path = url.split("?", 1)[0]
        if url.startswith("https://registry.npmjs.org/@supabase/supabase-js/"):
            v = url.rsplit("/", 1)[1]
            deps = {n: v for n in ("@supabase/auth-js", "@supabase/postgrest-js", "@supabase/storage-js")}
            return 200, json.dumps({"dependencies": dict(deps, tslib="2.8.1")}), ""
        if path == sc.GITHUB + "/advisories":
            return 200, json.dumps(self.affecting if "%40" in url.split("affects=", 1)[1].split("&", 1)[0][1:] else self.package_advisories), ""
        if path == sc.GITHUB + "/orgs/supabase/repos":
            return 200, json.dumps([{"full_name": r, "archived": False} for r in self.repo_advisories if r.startswith("supabase/")]), ""
        m = re.fullmatch(re.escape(sc.GITHUB) + r"/repos/([\w.-]+/[\w.-]+)/security-advisories", path)
        if m:
            return 200, json.dumps(self.repo_advisories.get(m.group(1), [])), ""
        rest = url[len(self.url):] if url.startswith(self.url) else None
        if rest in self.versions:
            return 200, self.versions[rest], ""
        if rest is not None and rest.startswith("/rest/v1/rpc/"):
            name = rest.rsplit("/", 1)[1]
            if name in sc.ANON_FUNCTIONS:
                return 200, sc.ANON_FUNCTIONS[name], ""
            if name in self.rpc_open:
                return 200, "null", ""
            return 401, '{"code":"42501","message":"permission denied for function ' + name + '"}', ""
        if rest is not None and rest.startswith("/rest/v1/"):
            table = rest[len("/rest/v1/"):].split("?", 1)[0]
            if method == "POST":
                return self.insert_reply + ("",)
            return 200, json.dumps(self.readable.get(table, [])), ""
        if rest == "/storage/v1/bucket":
            return 200, "[]", ""
        if rest is not None and rest.startswith("/storage/v1/object/list/"):
            return 200, json.dumps(self.bucket_files), ""
        if rest is not None and rest.startswith("/storage/v1/object/public/"):
            return (200, "{}", "") if self.public_bucket else (400, '{"error":"not found"}', "")
        if rest is not None and rest.startswith("/functions/v1/"):
            return self.search_status, "{}", ""
        raise AssertionError(f"the fake world doesn't know {method} {url}")


def advisory(ghsa, published="2026-10-24T12:00:00Z", ranges=("<= 1.0.0",), severity="high"):
    return {"ghsa_id": ghsa, "published_at": published, "severity": severity, "summary": "made up",
            "vulnerabilities": [{"vulnerable_version_range": r} for r in ranges]}


def run(world, reviewed_ids=()):
    with tempfile.TemporaryDirectory() as tmp:
        listed = Path(tmp) / "reviewed.txt"
        listed.write_text("".join(f"{i}  2026-10-24  made up\n" for i in reviewed_ids), encoding="utf-8")
        with mock.patch.object(sc, "REVIEWED", listed):
            check = sc.Check(SINCE, fetch=world)
            return check.run(), check


class WhatTheSiteRuns(unittest.TestCase):
    def test_the_supabase_js_version_is_the_one_the_pages_load(self):
        version = sc.supabase_js_version()
        self.assertIn(f"@supabase/supabase-js@{version}/", read_root("site/index.html"))

    def test_every_pinned_action_is_checked(self):
        pinned = dict(sc.pinned_actions())
        for wf in (ROOT / ".github" / "workflows").glob("*.yml"):
            for name, tag in re.findall(r"uses:\s*([\w.-]+/[\w.-]+)@[0-9a-f]{40}\s*#\s*v([\d.]+)", wf.read_text(encoding="utf-8")):
                self.assertEqual(pinned.get(name), tag, f"{wf.name}: {name}")
        self.assertIn("actions/deploy-pages", pinned)

    def test_every_table_with_an_insert_policy_gets_a_write_attempt(self):
        # a new insert policy needs a row here, one that breaks a check constraint
        self.assertEqual(sorted(sc.INVALID_ROWS), sc.insert_policy_tables(SCHEMA))

    def test_every_table_function_bucket_and_edge_function_is_tried(self):
        world = World()
        self.assertTrue(run(world)[0])
        called = {u for _, u in world.calls}
        for t in sc.schema_tables(SCHEMA):
            self.assertTrue(any(f"/rest/v1/{t}?select=" in u for u in called), t)
        for name, _ in sc.schema_functions(SCHEMA):
            self.assertIn(f"{world.url}/rest/v1/rpc/{name}", called)
        self.assertEqual(sc.buckets(), ["league-data", "league-exports"])
        self.assertIn(f"{world.url}/functions/v1/search-tracks", called)

    def test_the_reviewed_list_says_why_for_each_advisory(self):
        for line in read_root("scripts/security_reviewed.txt").splitlines():
            if line.strip() and not line.startswith("#"):
                with self.subTest(line[:20]):
                    self.assertRegex(line, r"^GHSA(-[0-9a-z]{4}){3}  \d{4}-\d\d-\d\d  \S.{10,}")


class VersionRanges(unittest.TestCase):
    def test_the_forms_advisories_use(self):
        cases = [("1.80.1", "<= 1.80.1", True), ("1.80.2", "<= 1.80.1", False), ("1.80.0", " <= 1.80.0", True),
                 ("2.100.0", ">= 2.29.7 and < 2.146.0", True), ("2.146.0", ">= 2.29.7 and < 2.146.0", False),
                 ("4.1.2", ">= 4.0.0, < 4.1.3", True), ("3.9.9", ">= 4.0.0, < 4.1.3", False),
                 ("v2.197.0", "< 2.185.0", False), ("1.2.3", "= 1.2.3", True)]
        for version, spec, want in cases:
            with self.subTest(f"{version} {spec}"):
                self.assertIs(sc.in_range(version, spec), want)

    def test_an_unreadable_range_is_left_to_a_person(self):
        for spec in ("", None, "all versions", "~> 1.2"):
            self.assertIsNone(sc.in_range("1.0.0", spec))


class TheCheck(unittest.TestCase):
    def test_a_clean_world_passes(self):
        ok, check = run(World())
        self.assertTrue(ok, check.failures)
        self.assertIn("Storage is 1.80.2", check.notes)

    def test_an_advisory_on_a_version_the_site_runs(self):
        world = World()
        world.affecting = [advisory("GHSA-aaaa-bbbb-cccc", published="2025-01-01T00:00:00Z")]
        ok, check = run(world)
        self.assertFalse(ok)
        self.assertIn("GHSA-aaaa-bbbb-cccc", check.failures[0])

    def test_a_new_advisory_for_another_version_is_only_noted(self):
        world = World()
        world.package_advisories = [advisory("GHSA-aaaa-bbbb-cccc")]
        ok, check = run(world)
        self.assertTrue(ok)
        self.assertTrue(any("GHSA-aaaa-bbbb-cccc" in n for n in check.notes))

    def test_a_new_supabase_advisory_waits_for_a_person(self):
        world = World()
        world.repo_advisories["supabase/storage"] = [advisory("GHSA-aaaa-bbbb-cccc", ranges=("<= 1.0.0",))]
        self.assertFalse(run(world)[0])
        self.assertTrue(run(world, reviewed_ids=["GHSA-aaaa-bbbb-cccc"])[0])

    def test_an_older_supabase_advisory_isnt_new(self):
        world = World()
        world.repo_advisories["supabase/storage"] = [advisory("GHSA-aaaa-bbbb-cccc", published="2026-10-01T00:00:00Z")]
        self.assertTrue(run(world)[0])

    def test_a_live_service_inside_an_advisorys_range_fails_even_once_reviewed(self):
        # the 2026-10-14 Storage advisory: live 1.80.1 would have been inside it
        world = World()
        world.versions["/storage/v1/version"] = "1.80.1"
        world.repo_advisories["supabase/storage"] = [advisory("GHSA-8rrf-w776-x75g", published="2026-10-14T08:27:47Z",
                                                              ranges=("<= 1.80.1",), severity="critical")]
        ok, check = run(world, reviewed_ids=["GHSA-8rrf-w776-x75g"])
        self.assertFalse(ok)
        self.assertIn("live Storage 1.80.1", check.failures[0])

    def test_a_service_that_wont_say_its_version(self):
        world = World()
        world.versions["/auth/v1/health"] = '{"name":"GoTrue"}'
        self.assertFalse(run(world)[0])

    def test_anything_a_stranger_can_reach(self):
        breaks = {
            "a readable row": lambda w: w.readable.update(players=[{"id": "x"}]),
            "a write a policy let through": lambda w: setattr(w, "insert_reply", (400, '{"code":"23514","message":"violates check constraint"}')),
            "a members-only function": lambda w: w.rpc_open.add("site_round_submitters"),
            "a listed file": lambda w: setattr(w, "bucket_files", [{"name": "index.json"}]),
            "a public bucket": lambda w: setattr(w, "public_bucket", True),
            "the search": lambda w: setattr(w, "search_status", 200),
        }
        for label, breaking in breaks.items():
            with self.subTest(label):
                world = World()
                breaking(world)
                self.assertFalse(run(world)[0])

    def test_the_summary_says_what_needs_a_look(self):
        world = World()
        world.search_status = 200
        ok, check = run(world)
        text = sc.summary(check)
        self.assertIn("**Needs a look:**", text)
        self.assertIn("search-tracks", text)


class TimeOnThePrivacyPage(unittest.TestCase):
    def test_the_page_holds_the_placeholder_once(self):
        self.assertEqual(read_root("site/privacy.html").count(stc.MARK), 1)

    def test_it_writes_the_time_in_utc_for_the_page_to_localise(self):
        out = stc.stamp("<p>" + stc.MARK + "</p>", "2026-10-25T11:17:42Z")
        self.assertIn('<time datetime="2026-10-25T11:17:42Z">October 25, 2026, 11:17 UTC</time>', out)
        self.assertNotIn("not run yet", out)
        script = read_root("site/privacy.html").split("<script>")[-1]
        self.assertIn('document.querySelector("#secAuto time")', script)
        self.assertIn('checked.getAttribute("datetime")', script)

    def run_script(self, page_text, iso):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "privacy.html").write_text(page_text, encoding="utf-8")
            r = subprocess.run([sys.executable, str(ROOT / "scripts" / "stamp_check_time.py"), tmp, iso],
                               capture_output=True, text=True)
            return r.returncode, (Path(tmp) / "privacy.html").read_text(encoding="utf-8")

    def test_no_clean_check_yet_leaves_the_placeholder(self):
        code, out = self.run_script(stc.MARK, "")
        self.assertEqual((code, out), (0, stc.MARK))

    def test_it_refuses_a_page_without_the_placeholder_or_a_bad_time(self):
        self.assertNotEqual(self.run_script("<p>reworded</p>", "2026-10-25T11:17:42Z")[0], 0)
        for bad in ("yesterday", "2026-10-25", "2026-10-25T11:17:42Z<script>"):
            with self.subTest(bad):
                code, out = self.run_script(stc.MARK, bad)
                self.assertNotEqual(code, 0)
                self.assertEqual(out, stc.MARK)


class Workflows(unittest.TestCase):
    def setUp(self):
        self.check = read_root(".github/workflows/security-check.yml")
        self.deploy = read_root(".github/workflows/deploy.yml")
        self.build = self.deploy.split("\njobs:", 1)[1].split("\n  deploy:\n", 1)[0]

    def test_it_runs_every_day_and_reads_only(self):
        self.assertRegex(self.check, r'schedule:\n    - cron: "\d+ \d+ \* \* \*"')
        self.assertIn("workflow_dispatch:", self.check)
        self.assertNotRegex(self.check.split("\njobs:", 1)[0], r":\s*write")
        self.assertNotIn("permissions:", self.check.split("\njobs:", 1)[1])
        self.assertIn("python scripts/security_check.py", self.check)
        self.assertRegex(self.check, r"- name: Check\n        timeout-minutes: \d+")

    def test_the_window_starts_at_the_last_clean_run(self):
        self.assertIn("--workflow security-check.yml --status success --limit 1 --json createdAt", self.check)
        self.assertIn('${since:+--since "$since"}', self.check)

    def test_a_clean_check_redeploys_and_a_failed_one_doesnt(self):
        name = re.search(r"^name: (.+)$", self.check, re.M).group(1)
        self.assertIn(f"workflow_run:\n    workflows: [{name}]\n    types: [completed]", self.deploy)
        self.assertIn("if: github.event_name != 'workflow_run' || github.event.workflow_run.conclusion == 'success'", self.build)

    def test_every_deploy_stamps_the_last_clean_time(self):
        step = 'python scripts/stamp_check_time.py site "$at"'
        self.assertIn("--workflow security-check.yml --status success --limit 1 --json updatedAt", self.build)
        order = [self.build.index(s) for s in ("- name: Run tests", "scripts/stamp_assets.py site", step,
                                                "uses: actions/upload-pages-artifact")]
        self.assertEqual(order, sorted(order))
        self.assertIn("permissions:\n      contents: read\n      actions: read", self.build)
        self.assertNotRegex(self.build.split("steps:", 1)[0], r":\s*write")


class PlaylistLinks(unittest.TestCase):
    """Playlist links come from the data in the storage bucket; only https
    ones become links, so a swapped file can't plant a javascript: link."""

    def test_round_playlist(self):
        js = read_root("site/rounds.js")
        self.assertIn("(/^https:\\/\\//i.test(r.playlistUrl || \"\") ? '<a class=\"pill\" href=\"' + esc(r.playlistUrl)", js)

    def test_home_tiles(self):
        js = read_root("site/app.js")
        tile = js.split("function playlistTile(item, group, stats) {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn('var url = /^https:\\/\\//i.test(item.url || "") ? item.url : "";', tile)
        self.assertIn("a.href = url;", tile)
        self.assertNotRegex(tile.split('? item.url : "";', 1)[1], r"item\.url")


if __name__ == "__main__":
    unittest.main()
