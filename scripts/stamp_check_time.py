#!/usr/bin/env python3
"""Put the time of the last clean security check on the privacy page, at deploy.

    python scripts/stamp_check_time.py site <ISO time, or "" for none yet>

The Security check workflow runs scripts/security_check.py every morning and
a clean run triggers a deploy; every deploy (that one or a push) looks up the
latest clean run and passes its time here. Like stamp_assets.py, it changes
only the deploy's checkout, never the repo's file, so no commit is needed to
move the time. A failed check moves nothing: the page keeps saying when it
last passed. The page shows the UTC time, and its own script turns that into
the reader's local time. Stdlib only.
"""
import datetime as dt
import re
import sys
from pathlib import Path

MARK = '<span class="sec-when" id="secAuto">Daily check: not run yet</span>'


def stamp(html, iso):
    """The page with the placeholder replaced by the check's time."""
    when = dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")
    shown = f"{when:%B} {when.day}, {when.year}, {when:%H:%M} UTC"
    return html.replace(MARK, f'<span class="sec-when" id="secAuto">Daily check passed '
                              f'<time datetime="{iso}">{shown}</time></span>')


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: stamp_check_time.py <site dir> <ISO time or empty>")
    page, iso = Path(sys.argv[1]) / "privacy.html", sys.argv[2]
    text = page.read_text(encoding="utf-8")
    # loud, so rewording the page can't quietly stop the time showing
    if text.count(MARK) != 1:
        sys.exit(f"privacy.html should hold the placeholder exactly once: {MARK}")
    if not iso:
        print("no clean security check yet; privacy.html keeps its placeholder")
        return
    if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", iso):
        sys.exit(f"expected a time like 2026-10-25T11:17:42Z, got {iso!r}")
    page.write_text(stamp(text, iso), encoding="utf-8")
    print(f"privacy.html: daily check passed {iso}")


if __name__ == "__main__":
    main()
