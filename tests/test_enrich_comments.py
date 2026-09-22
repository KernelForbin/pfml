"""scripts/enrich_comments.py, offline: the parts that decide what gets
stored. Nothing here calls the API: the SDK is imported only inside main,
and the tests that run main swap in a fake one."""
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

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


class CommentIds(unittest.TestCase):
    def test_script_and_build_make_the_same_comment_id(self):
        # Labels are looked up by this id; if the two copies drift, every
        # label silently stops matching.
        self.assertEqual(ec.comment_id("r1", "spotify:track:x", "v1"), build.comment_id("r1", "spotify:track:x", "v1"))


class Store(unittest.TestCase):
    """What a run keeps of data/comment_sentiment.json. main() runs with
    the SDK faked out and the request step replaced, so nothing is sent."""

    def run_main(self, argv, existing_text, comments):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        out = self.out = tmp / "comment_sentiment.json"
        if existing_text is not None:
            out.write_text(existing_text, encoding="utf-8")

        def fake_sync(client, batches, store):
            for b in batches:
                for c in b:
                    store[c["id"]] = {"labels": ["funny"], "strength": {"funny": 2}, "rationale": "new"}
            return sum(len(b) for b in batches)

        fake_sdk = types.SimpleNamespace(Anthropic=lambda: object())
        with mock.patch.object(ec, "OUT_PATH", out), mock.patch.object(ec, "ROOT", tmp), \
             mock.patch.object(ec, "collect_comments", lambda season: comments), \
             mock.patch.object(ec, "run_sync", fake_sync), \
             mock.patch.dict(sys.modules, {"anthropic": fake_sdk}), \
             mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}), \
             mock.patch.object(sys, "argv", ["enrich_comments.py", "--sync"] + argv), \
             mock.patch("builtins.print"):
            ec.main()
        return json.loads(out.read_text(encoding="utf-8"))["comments"]

    def test_force_keeps_labels_outside_the_run(self):
        existing = '{"comments": {"s1|a|p1": {"labels": ["mean"], "strength": {"mean": 1}, "rationale": "old"}}}'
        store = self.run_main(["--force", "--season", "season2"], existing, [{"id": "s2|b|p2", "text": "hi"}])
        self.assertEqual(sorted(store), ["s1|a|p1", "s2|b|p2"])
        self.assertEqual(store["s1|a|p1"]["rationale"], "old")

    def test_unreadable_store_stops_the_run_instead_of_being_overwritten(self):
        with self.assertRaises(SystemExit):
            self.run_main([], "{not json", [{"id": "s2|b|p2", "text": "hi"}])
        self.assertEqual(self.out.read_text(encoding="utf-8"), "{not json")


if __name__ == "__main__":
    unittest.main()
