"""The build stats at the bottom of the features page
(scripts/stamp_build_stats.py), and the deploy step that fills them in."""
import datetime as dt
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from support import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import stamp_build_stats as sbs  # noqa: E402

PAGE = (ROOT / "site" / "features.html").read_text(encoding="utf-8")
DEPLOY = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
NUMBERS = {"commits": 140, "code": 30201, "tests": 666, "deploys": 114, "checks": 2,
           "readme": 2616, "claude": 564, "changelog": 1917}


class ThePage(unittest.TestCase):
    def test_it_holds_every_placeholder_once(self):
        for m in [sbs.mark(k) for k in sbs.STATS] + [sbs.WHEN]:
            with self.subTest(m):
                self.assertEqual(PAGE.count(m), 1)

    def test_they_sit_at_the_bottom_above_the_footer(self):
        built = PAGE.index('<section class="built"')
        self.assertGreater(built, PAGE.index('<section class="key"'))
        self.assertGreater(built, max(PAGE.index(f'id="mode-{m}"') for m in ("seasons", "rounds", "home")))
        self.assertLess(PAGE.index("</section>", built), PAGE.index('<footer class="foot">'))
        self.assertEqual(PAGE[built:].count("<section"), 1)

    def test_it_names_the_model(self):
        self.assertIn("Built with Claude Opus 5.5", PAGE[PAGE.index('<section class="built"'):])


class Stamping(unittest.TestCase):
    def test_every_number_goes_in_with_thousands_separators(self):
        out = sbs.stamp(PAGE, NUMBERS, dt.date(2026, 10, 25))
        self.assertIn('<dd data-stat="code">30,201</dd>', out)
        self.assertIn('<dd data-stat="commits">140</dd>', out)
        self.assertNotIn('&mdash;</dd>', out[out.index('<section class="built"'):])
        self.assertIn('<span data-stat="when">Counted at the last deploy, '
                      '<time datetime="2026-10-25">October 25, 2026</time>.</span>', out)
        self.assertNotIn(sbs.WHEN, out)
        self.assertEqual(out.count("Counted at the last deploy"), 1)

    def run_script(self, page, *counts):
        """The script on a made-up checkout that's whole apart from `page`,
        so a refusal can only come from what's being tested."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "site").mkdir()
            (root / "tests").mkdir()
            (root / "site" / "features.html").write_text(page, encoding="utf-8")
            (root / "tests" / "test_fake_one.py").write_text(
                "import unittest\n\n\nclass One(unittest.TestCase):\n    def test_it(self):\n        pass\n",
                encoding="utf-8")
            for name, n in (("README.md", 1234), ("CLAUDE.md", 5), ("CHANGELOG.md", 7)):
                (root / name).write_text("x\n" * n, encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            r = subprocess.run([sys.executable, str(ROOT / "scripts" / "stamp_build_stats.py"),
                                str(root / "site"), *counts], capture_output=True, text=True)
            return r.returncode, (root / "site" / "features.html").read_text(encoding="utf-8")

    def test_the_made_up_checkout_works(self):
        # without this, every refusal below could be the checkout failing
        self.assertEqual(self.run_script(PAGE, "1", "2", "3")[0], 0)

    def test_it_refuses_a_count_that_isnt_one(self):
        for bad in (["", "1", "2"], ["1", "x", "2"], ["1", "2", "3; rm"], ["1", "2"], [" 7", "1", "2"],
                    ["+7", "1", "2"]):
            with self.subTest(bad):
                code, out = self.run_script(PAGE, *bad)
                self.assertNotEqual(code, 0)
                self.assertEqual(out, PAGE)

    def test_it_refuses_a_page_missing_a_placeholder(self):
        page = PAGE.replace(sbs.mark("checks"), "<dd>reworded</dd>")
        self.assertNotEqual(self.run_script(page, "1", "2", "3")[0], 0)

    def test_a_whole_run_counts_from_the_folder_above_site(self):
        code, out = self.run_script(PAGE, "140", "113", "2")
        self.assertEqual(code, 0)
        for key, shown in (("commits", "140"), ("deploys", "114"), ("checks", "2"), ("tests", "1"),
                           ("readme", "1,234"), ("claude", "5"), ("changelog", "7"),
                           ("code", f"{len(PAGE.splitlines()) + 6:,}")):
            with self.subTest(key):   # deploys: this one counts too
                self.assertIn(f'<dd data-stat="{key}">{shown}</dd>', out)


class Counting(unittest.TestCase):
    def test_skipped_tests_dont_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "test_fake_counted.py").write_text(textwrap.dedent("""
                import unittest

                class Runs(unittest.TestCase):
                    def test_a(self): pass
                    def test_b(self): pass
                    @unittest.skip("live")
                    def test_c(self): pass

                @unittest.skipUnless(False, "live")
                class Live(unittest.TestCase):
                    def test_d(self): pass
                """), encoding="utf-8")
            self.assertEqual(sbs.tests_run(Path(tmp)), 2)

    def test_code_leaves_out_docs_and_generated_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "site").mkdir()
            files = {"a.py": "1\n2\n", "site/x.js": "1\n2\n3\n", "site/emoji-data.js": "1\n" * 50,
                     "site/season3.html": "1\n" * 50, "site/season.template.html": "1\n",
                     "README.md": "1\n" * 9, "site/icon.png": "1\n" * 9}
            for name, text in files.items():
                (root / name).write_text(text, encoding="utf-8")
            (root / "untracked.py").write_text("1\n" * 9, encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "add", *files], cwd=root, check=True)
            self.assertEqual(sbs.code_lines(root), 6)


class TheDeploy(unittest.TestCase):
    def setUp(self):
        self.build = DEPLOY.split("\njobs:", 1)[1].split("\n  deploy:\n", 1)[0]

    def test_the_build_checks_out_the_whole_history(self):
        self.assertIn("persist-credentials: false\n          fetch-depth: 0", self.build)

    def test_it_stamps_after_the_tests_and_before_the_upload(self):
        step = 'python scripts/stamp_build_stats.py site "$(git rev-list --count HEAD)" "$deploys" "$checks"'
        order = [self.build.index(s) for s in ("- name: Run tests", step, "uses: actions/upload-pages-artifact")]
        self.assertEqual(order, sorted(order))

    def test_it_counts_successful_deploys_and_every_finished_check(self):
        self.assertIn('actions/workflows/deploy.yml/runs?status=success&per_page=1" --jq .total_count', self.build)
        self.assertIn('actions/workflows/security-check.yml/runs?status=completed&per_page=1" --jq .total_count',
                      self.build)


if __name__ == "__main__":
    unittest.main()
