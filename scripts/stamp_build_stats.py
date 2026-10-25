#!/usr/bin/env python3
"""Put the build stats at the bottom of the features page, at deploy.

    python scripts/stamp_build_stats.py site <commits> <deploys before this one> <security checks run>

The user asked (2026-10-25) for numbers about how the site is built, at the
bottom of the features page. They're counted at every deploy, so they're
never stale and moving them needs no commit: like stamp_assets.py and
stamp_check_time.py, this changes only the deploy's checkout, and the repo's
page keeps its dashes.

The workflow passes what only git and GitHub know: the commit count (from a
full checkout) and how many deploys and security checks have run (the
Actions API). This counts the rest from the checkout:

- lines of code: the tracked code files (CODE_SUFFIXES), tests and workflows
  included, the docs and the generated files (GENERATED) not;
- tests run on every deploy: the suite's tests, less the ones that skip
  themselves there (the live tests, which need PFML_LIVE=1);
- lines in README.md, CLAUDE.md and CHANGELOG.md.

Stdlib only.
"""
import datetime as dt
import re
import subprocess
import sys
import unittest
from pathlib import Path

CODE_SUFFIXES = {".py", ".js", ".ts", ".html", ".css", ".sql", ".yml"}
# written by scripts, not by hand: emoji-data.js (update_emoji_data.py) and
# the season pages (build.py, from season.template.html)
GENERATED = re.compile(r"^site/(emoji-data\.js|season\d+\.html)$")
DOCS = {"readme": "README.md", "claude": "CLAUDE.md", "changelog": "CHANGELOG.md"}

# One placeholder per number, exactly as features.html holds it.
STATS = ("commits", "code", "tests", "deploys", "checks", "readme", "claude", "changelog")
WHEN = '<span data-stat="when">Counted at every deploy.</span>'


def mark(key):
    return f'<dd data-stat="{key}">&mdash;</dd>'


def lines(path):
    return len(Path(path).read_text(encoding="utf-8").splitlines())


def code_lines(root):
    """Lines in the tracked code files, less the generated ones."""
    files = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True).stdout.split("\n")
    return sum(lines(Path(root) / f) for f in files
               if Path(f).suffix in CODE_SUFFIXES and not GENERATED.match(f) and (Path(root) / f).is_file())


def cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from cases(item)
        else:
            yield item


def tests_run(tests_dir):
    """The suite's tests, less those marked to skip (the live ones, here)."""
    suite = unittest.TestLoader().discover(str(tests_dir), top_level_dir=str(tests_dir))
    return sum(1 for c in cases(suite)
               if not getattr(type(c), "__unittest_skip__", False)
               and not getattr(getattr(c, c._testMethodName), "__unittest_skip__", False))


def stamp(html, numbers, today):
    """The page with each placeholder replaced by its number."""
    for key in STATS:
        html = html.replace(mark(key), f'<dd data-stat="{key}">{numbers[key]:,}</dd>')
    return html.replace(WHEN, f'<span data-stat="when">Counted at the last deploy, '
                              f'<time datetime="{today:%Y-%m-%d}">{today:%B} {today.day}, {today.year}</time>.</span>')


def main():
    if len(sys.argv) != 5:
        sys.exit("usage: stamp_build_stats.py <site dir> <commits> <deploys before this one> <security checks run>")
    site = Path(sys.argv[1])
    given = sys.argv[2:]
    if not all(re.fullmatch(r"\d{1,7}", n) for n in given):
        sys.exit(f"expected three counts, got {given!r}")
    page = site / "features.html"
    text = page.read_text(encoding="utf-8")
    # loud, so rewording the page can't quietly stop a number showing
    missing = [m for m in [mark(k) for k in STATS] + [WHEN] if text.count(m) != 1]
    if missing:
        sys.exit(f"features.html should hold each placeholder exactly once: {missing}")
    root = site.resolve().parent
    numbers = {"commits": int(given[0]), "deploys": int(given[1]) + 1, "checks": int(given[2]),
               "code": code_lines(root), "tests": tests_run(root / "tests")}
    numbers.update({key: lines(root / name) for key, name in DOCS.items()})
    page.write_text(stamp(text, numbers, dt.datetime.now(dt.timezone.utc).date()), encoding="utf-8")
    print("features.html: " + ", ".join(f"{k} {numbers[k]:,}" for k in STATS))


if __name__ == "__main__":
    main()
