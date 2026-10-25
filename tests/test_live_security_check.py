"""LIVE TEST: runs the daily security check against the real services.

Skipped unless PFML_LIVE=1 and a GitHub token is set: the check reads about
125 GitHub API pages (every Supabase repo's advisories), past the 60 an hour
GitHub allows without one. Read-only, like the check itself. Run it whenever
scripts/security_check.py changes:

    PFML_LIVE=1 GH_TOKEN=$(gh auth token) python -m unittest discover -s tests -p test_live_security_check.py -v
"""
import os
import unittest

import support  # noqa: F401  (puts scripts/ on the path)
import security_check as sc  # noqa: E402

TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")


@unittest.skipUnless(os.environ.get("PFML_LIVE") == "1" and TOKEN,
                     "live network test; set PFML_LIVE=1 and GH_TOKEN to run")
class LiveSecurityCheck(unittest.TestCase):
    def test_the_check_passes_today(self):
        # the last 30 days, so every advisory in security_reviewed.txt is in the window
        check = sc.Check("2026-09-24T00:00:00Z", token=TOKEN)
        self.assertTrue(check.run(), check.failures)
        self.assertTrue(any(n.startswith("Storage is ") for n in check.notes))
        self.assertTrue(any(n.startswith("Auth is ") for n in check.notes))


if __name__ == "__main__":
    unittest.main()
