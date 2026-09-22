"""scripts/update_emoji_data.py: turning Unicode's emoji list into
site/emoji-data.js. Offline: build() gets a small made-up payload shaped
like the real one. tests/test_live_emoji_data.py checks the real source."""
import json
import re
import unittest

import support  # noqa: F401  (puts scripts/ on the path)
import update_emoji_data as ued

FAKE = {
    "\U0001F600": {"name": "grinning face", "group": "Smileys & Emotion"},
    "\U0001F525": {"name": "fire", "group": "Travel & Places"},          # a quick-row emoji
    "❤️": {"name": "red heart", "group": "Smileys & Emotion"},  # a quick-row emoji
    "\U0001F436": {"name": "dog face", "group": "Animals & Nature"},
    "\U0001F355": {"name": "pizza", "group": "Food & Drink"},
    "\U0001F43A": {"name": "wolf", "group": "Animals & Nature"},
}


def rows_of(js):
    return [(json.loads('"%s"' % e), n, int(g))
            for e, n, g in re.findall(r'^\s*\["((?:[^"\\]|\\.)*)","([^"]*)",(\d+)\],$', js, re.M)]


def groups_of(js):
    block = js.split("window.PFML_EMOJI_GROUPS = [", 1)[1].split("];", 1)[0]
    return re.findall(r'"([^"]+)"', block)


class Build(unittest.TestCase):
    def test_quick_row_emoji_are_left_out(self):
        # Offered in the quick row under their old names ("fire", "heart");
        # also listing them in the grid would store a second value for them.
        js, count, _ = ued.build(FAKE)
        glyphs = [e for e, _, _ in rows_of(js)]
        self.assertNotIn("\U0001F525", glyphs)
        self.assertNotIn("❤️", glyphs)
        self.assertEqual(count, 4)

    def test_keeps_source_order_and_indexes_groups(self):
        js, _, groups = ued.build(FAKE)
        self.assertEqual(groups, ["Smileys & Emotion", "Animals & Nature", "Food & Drink"])
        self.assertEqual(groups_of(js), groups)
        self.assertEqual(rows_of(js), [
            ("\U0001F600", "grinning face", 0),
            ("\U0001F436", "dog face", 1),
            ("\U0001F355", "pizza", 2),
            ("\U0001F43A", "wolf", 1),
        ])

    def test_output_is_a_plain_script_setting_both_globals(self):
        js, _, _ = ued.build(FAKE)
        self.assertIn("window.PFML_EMOJI_GROUPS = [", js)
        self.assertIn("window.PFML_EMOJI_DATA = [", js)
        self.assertTrue(js.endswith("];\n"))

    def test_quotes_in_a_name_cannot_break_the_script(self):
        js, _, _ = ued.build({"\U0001F600": {"name": 'say "cheese"', "group": "Smileys & Emotion"}})
        self.assertIn('say \\"cheese\\"', js)


if __name__ == "__main__":
    unittest.main()
