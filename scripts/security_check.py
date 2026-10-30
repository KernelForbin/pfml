#!/usr/bin/env python3
"""The daily security check (README, Security check). Network, stdlib only.

    python scripts/security_check.py [--since 2026-10-24T11:00:00Z]

The Security check workflow runs this every morning; when it passes, the
deploy writes the time onto the privacy page. It fails (exit 1) when:

  1. an advisory in GitHub's database affects the exact version of something
     the site runs: supabase-js and the packages it bundles, and every
     GitHub Action the workflows pin
  2. the live Storage or Auth service reports a version inside the range of
     one of Supabase's own advisories for it
  3. Supabase published an advisory on any of its repos since --since that
     isn't in scripts/security_reviewed.txt: a person has to judge whether
     it touches PFML. That's how the 2026-10-14 Storage advisory surfaced;
     it's only on Supabase's repo, not in GitHub's global database, and
     only 2 of 24 NVD entries mentioning Supabase in four months were
     Supabase's own (measured 2026-10-24)
  4. the outside test, with only the public key, can read a row, write,
     run a members-only function, see a stored file, or use the search

--since defaults to 48 hours ago; the workflow passes the start of the last
clean run, so a missed day widens the window instead of skipping it.
Everything is read-only: the write attempts use rows that break a check
constraint, so they can't land even if a policy let them through.
Prints a summary, and appends it to $GITHUB_STEP_SUMMARY when that's set.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GITHUB = "https://api.github.com"
REVIEWED = ROOT / "scripts" / "security_reviewed.txt"

# Supabase's own code lives in its org; PostgREST, which serves the tables,
# is a separate project Supabase runs.
SUPABASE_ORGS = ("supabase",)
EXTRA_REPOS = ("PostgREST/postgrest",)

# Services that report their version, and the repo whose advisories cover them.
SERVICES = (("Storage", "/storage/v1/version", "supabase/storage"),
            ("Auth", "/auth/v1/health", "supabase/auth"))

# Callable by anyone on purpose: they only answer "false" to a stranger.
ANON_FUNCTIONS = {"is_member": "false", "is_admin": "false"}

# A row each table's insert policy must refuse. Each also breaks a check
# constraint, so even a broken policy couldn't let it land. A test keeps
# this in step with the tables schema.sql gives an insert policy.
INVALID_ROWS = {
    "comment_votes": {"comment_id": "security-check", "value": 0},
    "comment_reactions": {"comment_id": "security-check", "reaction": ""},
    "comment_replies": {"comment_id": "security-check", "body": ""},
    "site_rounds": {"season_key": "security-check", "name": "", "closes_at": "2000-01-01T00:00:00Z"},
}


# ---------------------------------------------------------------- the repo

def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def supabase_js_version():
    """The one supabase-js version every page loads."""
    found = set()
    for page in sorted((ROOT / "site").glob("*.html")):
        found.update(re.findall(r"cdn\.jsdelivr\.net/npm/@supabase/supabase-js@(\d+\.\d+\.\d+)/", page.read_text(encoding="utf-8")))
    if len(found) != 1:
        raise SystemExit(f"expected one supabase-js version across the pages, found {sorted(found) or 'none'}")
    return found.pop()


def pinned_actions():
    """(name, version) for every action the workflows pin: uses: x/y@<sha> # vN.N.N"""
    out = set()
    for wf in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        for line in wf.read_text(encoding="utf-8").splitlines():
            if re.match(r"\s*-?\s*uses:", line):
                m = re.search(r"uses:\s*([\w.-]+/[\w.-]+)@[0-9a-f]{40}\s*#\s*v?(\d+(?:\.\d+)*)\s*$", line)
                if not m:
                    raise SystemExit(f"{wf.name}: an action isn't pinned as <sha> # vN.N.N: {line.strip()}")
                out.add((m.group(1), m.group(2)))
    return sorted(out)


def schema_tables(sql):
    return re.findall(r"create table if not exists public\.(\w+)", sql)


def insert_policy_tables(sql):
    return sorted(set(re.findall(r"create policy [^;]*? on public\.(\w+)\s+for (?:insert|all)\b", sql)))


def schema_functions(sql):
    """(name, [argument names]) for every function schema.sql creates that
    can be called, once each; a trigger function can't be, through the API
    or at all. A function a later "drop function" removes, and nothing
    creates again with the same argument types, no longer exists to call:
    the old three-argument set_submission_note was probed after its drop
    and came back 404, failing every run from 2026-10-26."""
    def types(args):
        return tuple(a.split()[1].lower() for a in args.replace("\n", " ").split(",") if a.strip())

    created = {}   # (name, argument types) -> (where it's last created, argument names)
    for m in re.finditer(r"create or replace function public\.(\w+)\(([^)]*)\)\s*returns\s+(\w+)", sql):
        name, args, returns = m.groups()
        if returns == "trigger":
            continue
        created[(name, types(args))] = (m.start(), [a.split()[0] for a in args.replace("\n", " ").split(",") if a.strip()])
    dropped = {}
    for m in re.finditer(r"drop function if exists public\.(\w+)\(([^)]*)\)", sql):
        dropped[(m.group(1), tuple(t.strip().lower() for t in m.group(2).split(",") if t.strip()))] = m.start()
    return [(name, names) for (name, sig), (at, names) in sorted(created.items(), key=lambda kv: kv[1][0])
            if dropped.get((name, sig), -1) < at]


def edge_functions():
    return sorted(p.name for p in (ROOT / "supabase" / "functions").iterdir() if p.is_dir())


def buckets():
    src = read("scripts/publish.py")
    return re.findall(r'^\w+_BUCKET = "([\w-]+)"', src, re.M)


def project():
    cfg = read("site/config.js")
    return (re.search(r"https://[a-z0-9]+\.supabase\.co", cfg).group(0),
            re.search(r'"(sb_publishable_[^"]+)"', cfg).group(1))


def reviewed():
    """Advisory ids a person has already judged, from security_reviewed.txt."""
    ids = set()
    for line in REVIEWED.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            ids.add(line.split()[0])
    return ids


# ---------------------------------------------------------------- versions

def version_tuple(v):
    return tuple(int(n) for n in re.findall(r"\d+", v)[:4])


def in_range(version, spec):
    """Whether version falls in an advisory range like "<= 1.80.1",
    ">= 2.29.7 and < 2.146.0" or ">= 4.0.0, < 4.1.3". None when the range
    can't be read, so a person looks rather than the check guessing."""
    parts = [p.strip() for p in re.split(r",|\band\b", spec or "") if p.strip()]
    if not parts:
        return None
    v = version_tuple(version)
    for part in parts:
        m = re.fullmatch(r"(<=|>=|<|>|=)?\s*v?(\d+(?:\.\d+)*)", part)
        if not m:
            return None
        op, bound = m.group(1) or "=", version_tuple(m.group(2))
        ok = {"<": v < bound, "<=": v <= bound, ">": v > bound, ">=": v >= bound, "=": v == bound}[op]
        if not ok:
            return False
    return True


# ---------------------------------------------------------------- the network

def fetch(method, url, headers=None, body=None):
    """(status, text, Link header). Never raises for an HTTP status."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    h = {"User-Agent": "pfml-security-check", **(headers or {})}
    if data is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace"), r.headers.get("Link") or ""
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), ""


class Check:
    def __init__(self, since, fetch=fetch, token=None):
        self.since = since
        self.fetch = fetch
        self.gh_headers = {"Accept": "application/vnd.github+json"}
        if token:
            self.gh_headers["Authorization"] = f"Bearer {token}"
        self.failures, self.notes = [], []

    def fail(self, msg):
        self.failures.append(msg)

    def note(self, msg):
        self.notes.append(msg)

    def github(self, path):
        """A list from the GitHub API, following its Link: rel="next" pages
        (the advisory endpoints page by cursor, not page number)."""
        out, url = [], GITHUB + path
        for _ in range(50):
            status, text, link = self.fetch("GET", url, self.gh_headers)
            if status != 200:
                raise SystemExit(f"GitHub API {path}: HTTP {status} {text[:200]}")
            out += json.loads(text)
            nxt = re.search(r'<([^>]+)>;\s*rel="next"', link)
            if not nxt:
                return out
            url = nxt.group(1)
        raise SystemExit(f"GitHub API {path}: more than 50 pages")

    # 1. what the site runs, at its exact version
    def packages(self):
        js = supabase_js_version()
        status, text, _ = self.fetch("GET", f"https://registry.npmjs.org/@supabase/supabase-js/{js}")
        if status != 200:
            raise SystemExit(f"npm registry: HTTP {status}")
        bundled = sorted((name, v) for name, v in json.loads(text).get("dependencies", {}).items() if name.startswith("@supabase/"))
        npm = [("@supabase/supabase-js", js)] + bundled
        return [("npm", n, v) for n, v in npm] + [("actions", n, v) for n, v in pinned_actions()]

    def advisories_for(self, ecosystem, name, version):
        for kind in ("reviewed", "malware"):
            q = urllib.parse.urlencode({"ecosystem": ecosystem, "affects": f"{name}@{version}", "type": kind, "per_page": 100})
            for a in self.github(f"/advisories?{q}"):
                self.fail(f"{a['ghsa_id']} ({a.get('severity')}) affects {name} {version}, which the site runs: {a.get('summary')}")
        q = urllib.parse.urlencode({"ecosystem": ecosystem, "affects": name, "per_page": 100})
        for a in self.github(f"/advisories?{q}"):
            if (a.get("published_at") or "") >= self.since:
                self.note(f"new: {a['ghsa_id']} for {name}, not the version the site runs ({version})")

    # 2 and 3. Supabase's own advisories
    def supabase_repos(self):
        repos = []
        for org in SUPABASE_ORGS:
            repos += [r["full_name"] for r in self.github(f"/orgs/{org}/repos?type=public&per_page=100") if not r.get("archived")]
        return sorted(repos) + list(EXTRA_REPOS)

    def supabase_advisories(self, url, key):
        seen = reviewed()
        by_repo = {}
        for repo in self.supabase_repos():
            rows = self.github(f"/repos/{repo}/security-advisories?state=published&per_page=100")
            by_repo[repo] = rows
            for a in rows:
                if (a.get("published_at") or "") >= self.since and a["ghsa_id"] not in seen:
                    self.fail(f"{a['ghsa_id']} ({a.get('severity')}) on {repo}, published {a['published_at'][:10]}, "
                              f"needs a person to judge, then a line in scripts/security_reviewed.txt: {a.get('summary')}")
        for label, path, repo in SERVICES:
            version = self.live_version(url + path, key)
            if version is None:
                self.fail(f"{label} didn't report its version ({path})")
                continue
            self.note(f"{label} is {version}")
            for a in by_repo.get(repo, []):
                for v in a.get("vulnerabilities") or [{}]:
                    hit = in_range(version, v.get("vulnerable_version_range"))
                    if hit:
                        self.fail(f"live {label} {version} is inside {a['ghsa_id']}'s range "
                                  f"({v.get('vulnerable_version_range')}): {a.get('summary')}")

    def live_version(self, url, key):
        status, text, _ = self.fetch("GET", url, {"apikey": key})
        if status != 200:
            return None
        text = text.strip()
        if text.startswith("{"):
            text = str(json.loads(text).get("version") or "")
        return text if re.fullmatch(r"v?\d+(\.\d+)+", text) else None

    # 4. the outside test
    def outside(self, url, key):
        sql = read("supabase/schema.sql")
        h = {"apikey": key}
        for t in schema_tables(sql):
            status, text, _ = self.fetch("GET", f"{url}/rest/v1/{t}?select=*&limit=1", h)
            if status == 200 and text.strip() == "[]":
                continue
            if status in (401, 403):
                continue
            self.fail(f"a stranger reading {t} got HTTP {status}: {text[:120]}")
        for t, row in INVALID_ROWS.items():
            status, text, _ = self.fetch("POST", f"{url}/rest/v1/{t}", dict(h, Prefer="return=minimal"), row)
            if status not in (401, 403) or '"42501"' not in text:
                self.fail(f"a stranger's insert into {t} wasn't refused by its policy: HTTP {status} {text[:120]}")
        for name, args in schema_functions(sql):
            status, text, _ = self.fetch("POST", f"{url}/rest/v1/rpc/{name}", h, {a: None for a in args})
            if name in ANON_FUNCTIONS:
                if status != 200 or text.strip() != ANON_FUNCTIONS[name]:
                    self.fail(f"{name} should answer a stranger with {ANON_FUNCTIONS[name]}: HTTP {status} {text[:120]}")
            elif status not in (401, 403) or '"42501"' not in text:
                self.fail(f"a stranger could call {name}: HTTP {status} {text[:120]}")
        status, text, _ = self.fetch("GET", f"{url}/storage/v1/bucket", h)
        if not (status in (400, 401, 403) or (status == 200 and text.strip() == "[]")):
            self.fail(f"a stranger listing the buckets got HTTP {status}: {text[:120]}")
        for b in buckets():
            status, text, _ = self.fetch("POST", f"{url}/storage/v1/object/list/{b}", h, {"prefix": "", "limit": 5})
            if status == 200 and text.strip() != "[]":
                self.fail(f"a stranger can list the files in {b}")
            status, text, _ = self.fetch("GET", f"{url}/storage/v1/object/public/{b}/index.json", h)
            if status == 200:
                self.fail(f"{b} serves files to anyone with the link")
        for fn in edge_functions():
            status, text, _ = self.fetch("POST", f"{url}/functions/v1/{fn}", h, {})
            if status not in (401, 403):
                self.fail(f"a stranger could use the {fn} function: HTTP {status} {text[:120]}")

    def run(self):
        url, key = project()
        for ecosystem, name, version in self.packages():
            self.advisories_for(ecosystem, name, version)
        self.supabase_advisories(url, key)
        self.outside(url, key)
        return not self.failures


def summary(check):
    lines = ["## Security check", "", f"Advisories since {check.since}.", ""]
    if check.failures:
        lines += ["**Needs a look:**", ""] + [f"- {f}" for f in check.failures] + [""]
    else:
        lines += ["**Passed.**", ""]
    lines += [f"- {n}" for n in check.notes]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="PFML's daily security check.")
    ap.add_argument("--since", help="ISO time; advisories published after it count as new (default: 48 hours ago)")
    args = ap.parse_args()
    since = args.since or (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", since):
        raise SystemExit(f"--since should look like 2026-10-24T11:00:00Z, got {since!r}")
    check = Check(since, token=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
    ok = check.run()
    text = summary(check)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(text)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
