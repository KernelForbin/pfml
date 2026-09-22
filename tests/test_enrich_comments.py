"""scripts/enrich_comments.py, offline: the parts that decide what gets
stored. Nothing here calls the API (the SDK is imported only inside main,
and these tests never reach it)."""
import unittest

import support  # noqa: F401  (puts scripts/ on the path)
import build
import enrich_comments as ec


class Labels(unittest.TestCase):
    def test_script_and_build_agree_on_the_labels(self):
        # build.py drops any label it doesn't know, so a mismatch would
        # silently throw away everything the script paid for.
        self.assertEqual(tuple(ec.LABELS), build.SENTIMENT_LABELS)
        self.assertEqual(tuple(ec.STRENGTHS), build.SENTIMENT_STRENGTHS)

    def test_prompt_defines_every_label_and_strength(self):
        for label in ec.LABELS:
            self.assertIn(f"- {label}:", ec.SYSTEM_PROMPT, label)
        for s in ec.STRENGTHS:
            self.assertIn(f"- {s}:", ec.SYSTEM_PROMPT)

    def test_response_schema_only_allows_known_labels_and_strengths(self):
        item = ec.RESPONSE_SCHEMA["properties"]["results"]["items"]["properties"]["labels"]["items"]
        self.assertEqual(item["properties"]["label"]["enum"], ec.LABELS)
        self.assertEqual(item["properties"]["strength"]["enum"], list(ec.STRENGTHS))


class Merge(unittest.TestCase):
    def test_keeps_known_labels_with_valid_strengths_only(self):
        self.assertEqual(ec.clean_labels([
            {"label": "funny", "strength": 3},
            {"label": "funny", "strength": 1},        # repeated: the strongest wins
            {"label": "rude", "strength": 2},         # retired label
            {"label": "mean", "strength": 5},         # out of range
            {"label": "heartfelt"},                   # no strength
            "angry",                                  # wrong shape
        ]), {"funny": 3})

    def test_merge_stores_labels_strengths_and_rationale(self):
        batch = [{"id": "c1"}, {"id": "c2"}]
        store = {}
        added = ec.merge_results(store, batch, {"results": [
            {"index": 0, "labels": [{"label": "witty", "strength": 2}, {"label": "mean", "strength": 1}], "rationale": " pun "},
            {"index": 7, "labels": [{"label": "funny", "strength": 3}], "rationale": "bad index"},
        ]})
        self.assertEqual(added, 1)
        self.assertEqual(store, {"c1": {"labels": ["mean", "witty"], "strength": {"witty": 2, "mean": 1}, "rationale": "pun"}})


if __name__ == "__main__":
    unittest.main()
