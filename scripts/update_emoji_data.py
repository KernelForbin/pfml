#!/usr/bin/env python3
"""Regenerate site/emoji-data.js, the data behind the round page's reaction
search picker, from Unicode's own emoji list.

    python scripts/update_emoji_data.py

Downloads data-by-emoji.json from the unicode-emoji-json npm package
(pinned version below) via jsdelivr, keeps just the emoji, its name and a
group index, and writes site/emoji-data.js as plain JS (a <script> tag,
not a fetch): no extra request when a member opens the picker.

The 6 "quick reaction" emoji PFML has used since reactions shipped (fire,
face with tears of joy, hundred points, eyes, grimacing face, red heart)
are left out on purpose. Those are still offered, without searching, using
the same stored value ("fire", "heart", ...) real comment_reactions rows
already use, so old and new reactions of those 6 count together instead of
splitting into two chips. Only run this to pick up a newer Unicode emoji
release; site/emoji-data.js is committed, so a normal build never touches
it. Still stdlib-only.
"""
import json
import urllib.request

VERSION = "0.9.0"
SRC_URL = f"https://cdn.jsdelivr.net/npm/unicode-emoji-json@{VERSION}/data-by-emoji.json"
OUT_PATH = __import__("pathlib").Path(__file__).resolve().parent.parent / "site" / "emoji-data.js"

LEGACY_GLYPHS = {
    "\U0001F525",  # fire
    "\U0001F602",  # face with tears of joy
    "\U0001F4AF",  # hundred points
    "\U0001F440",  # eyes
    "\U0001F62C",  # grimacing face
    "❤️",  # red heart
}


def fetch():
    req = urllib.request.Request(SRC_URL, headers={"User-Agent": "pfml-update-emoji-data"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def build(data):
    groups, group_index, rows = [], {}, []
    for emoji, meta in data.items():
        if emoji in LEGACY_GLYPHS:
            continue
        g = meta["group"]
        if g not in group_index:
            group_index[g] = len(groups)
            groups.append(g)
        rows.append((emoji, meta["name"], group_index[g]))

    def js_str(s):
        return json.dumps(s, ensure_ascii=False)

    lines = [
        "/* Emoji data for the round page's reaction search picker.",
        f"   Source: unicode-emoji-json {VERSION}, {SRC_URL}",
        "   Regenerate with scripts/update_emoji_data.py if the site ever needs a newer",
        "   Unicode emoji set. The 6 \"quick reaction\" emoji (fire, face with tears of",
        "   joy, hundred points, eyes, grimacing face, red heart) are left out here on",
        "   purpose: they're offered without searching, using the same stored value",
        "   (\"fire\", \"heart\", ...) PFML has used since reactions shipped, so old and new",
        "   reactions of those 6 count together instead of splitting into two chips. */",
        "window.PFML_EMOJI_GROUPS = [",
    ]
    lines += [f"  {js_str(g)}," for g in groups]
    lines.append("];")
    lines.append("window.PFML_EMOJI_DATA = [")
    lines += [f"  [{js_str(e)},{js_str(n)},{gi}]," for e, n, gi in rows]
    lines.append("];")
    return "\n".join(lines) + "\n", len(rows), groups


def main():
    data = fetch()
    out, count, groups = build(data)
    OUT_PATH.write_text(out, encoding="utf-8", newline="\n")
    print(f"{OUT_PATH}: {count} emoji across {len(groups)} groups "
          f"({len(out.encode('utf-8'))} bytes)")


if __name__ == "__main__":
    main()
