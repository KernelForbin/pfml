"""LIVE TEST: fetches the real unicode-emoji-json data from jsdelivr.

Skipped unless PFML_LIVE=1. The offline tests hand build() a small fake
payload, so they can't show the real package still has the shape build()
expects, or that site/emoji-data.js is what the pinned version produces.
Run it whenever scripts/update_emoji_data.py or its pinned version changes:

    PFML_LIVE=1 python -m unittest discover -s tests -p test_live_emoji_data.py -v
"""
import os
import unittest

import support  # noqa: F401  (puts scripts/ on the path)
import update_emoji_data as ued


@unittest.skipUnless(os.environ.get("PFML_LIVE") == "1", "live network test; set PFML_LIVE=1 to run")
class LiveEmojiData(unittest.TestCase):
    def test_pinned_source_still_has_the_expected_shape(self):
        data = ued.fetch()
        self.assertGreater(len(data), 1000)
        for glyph in ued.LEGACY_GLYPHS:
            self.assertIn(glyph, data, "a quick-row emoji vanished from the source")
        sample = next(iter(data.values()))
        self.assertIn("name", sample)
        self.assertIn("group", sample)

    def test_committed_file_is_what_the_pinned_version_builds(self):
        out, _, _ = ued.build(ued.fetch())
        committed = ued.OUT_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
        self.assertEqual(committed, out, "site/emoji-data.js is stale: run scripts/update_emoji_data.py")


if __name__ == "__main__":
    unittest.main()
