#!/usr/bin/env python3
"""Stamp the site's own scripts and stylesheet with a version, at deploy.

    python scripts/stamp_assets.py site <version>

GitHub Pages tells browsers to keep every file for 10 minutes
(Cache-Control: max-age=600, measured 2026-10-19). Right after a deploy, a
browser that had app.js or auth.js from an earlier visit can run a new page
with the old shared scripts. It happened the evening the Submit page shipped:
the page sat at "Loading the round." with an empty top bar, because the
cached auth.js had none of the calls the new submit.js makes.

Rewriting src="app.js" to src="app.js?v=<version>" (and the same for
style.css) in every page means a page always asks for the files it was
built with. A page that is itself still cached asks for the old version
string, so it gets a matching old set. The repo's own files are never
changed; the deploy workflow runs this on its checkout, after the tests.
Stdlib only.
"""
import re
import sys
from pathlib import Path

# A local file name: no scheme, no slash, no query yet.
LOCAL = r'(?P<name>[A-Za-z0-9_.-]+\.(?:js|css))'
PATTERN = re.compile(r'(?P<attr>(?:src|href))="' + LOCAL + '"')


def stamp(html, version):
    """The page with each local .js/.css reference given ?v=<version>."""
    return PATTERN.sub(lambda m: f'{m.group("attr")}="{m.group("name")}?v={version}"', html)


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: stamp_assets.py <site dir> <version>")
    site, version = Path(sys.argv[1]), sys.argv[2]
    if not re.fullmatch(r"[A-Za-z0-9]{6,40}", version):
        sys.exit(f"version should be a commit hash, got {version!r}")
    for page in sorted(site.glob("*.html")):
        text = page.read_text(encoding="utf-8")
        new = stamp(text, version)
        if new != text:
            page.write_text(new, encoding="utf-8")
            print(f"stamped {page.name}")


if __name__ == "__main__":
    main()
