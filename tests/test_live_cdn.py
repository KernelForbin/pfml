"""LIVE TEST: fetches supabase-js from jsDelivr over the network.

Skipped unless PFML_LIVE=1. Every members-only page loads supabase-js with
an integrity hash, and a browser refuses a file that doesn't match it, which
would leave every page stuck before sign-in. The offline tests pin the hash;
this checks the CDN still serves the file it describes, and with the CORS
header a crossorigin script needs. Run it whenever the version or hash
changes:

    PFML_LIVE=1 python -m unittest discover -s tests -p test_live_cdn.py -v
"""
import base64
import hashlib
import os
import unittest
import urllib.request

from test_site import SUPABASE_JS_INTEGRITY, SUPABASE_JS_URL


@unittest.skipUnless(os.environ.get("PFML_LIVE") == "1", "live network test; set PFML_LIVE=1 to run")
class LiveSupabaseJs(unittest.TestCase):
    def test_the_cdn_serves_the_file_the_pages_hash(self):
        req = urllib.request.Request(SUPABASE_JS_URL, headers={"Origin": "https://pfml.fun"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            cors = resp.headers.get("Access-Control-Allow-Origin")
        digest = "sha384-" + base64.b64encode(hashlib.sha384(body).digest()).decode()
        self.assertEqual(digest, SUPABASE_JS_INTEGRITY)
        self.assertIn(cors, ("*", "https://pfml.fun"))


if __name__ == "__main__":
    unittest.main()
