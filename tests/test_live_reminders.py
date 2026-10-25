"""LIVE TEST: reminders, against the real database and Edge Function.

Skipped unless PFML_LIVE=1, and needs SUPABASE_URL and SUPABASE_SECRET_KEY
in .env and supabase/migrations/2026-10-25_reminders.sql run. Read-only:
reminders_claim is called with no channel, which claims nothing (the
rehearsal, supabase/checks/2026-10-25_reminders_rehearsal.sql, plays the
real claims and rolls back). A stranger has to be refused by every new
function, and, once send-reminders is deployed, by the function too.

    PFML_LIVE=1 python -m unittest discover -s tests -p test_live_reminders.py -v
"""
import json
import os
import re
import unittest
import urllib.error
import urllib.request

import support  # noqa: F401  (puts scripts/ on the path)
import supa  # noqa: E402

LIVE = os.environ.get("PFML_LIVE") == "1"


def has_keys():
    supa._load_env_file()
    return all(os.environ.get(n) for n in ("SUPABASE_URL", "SUPABASE_SECRET_KEY"))


def public():
    cfg = (support.ROOT / "site" / "config.js").read_text(encoding="utf-8")
    return (re.search(r"https://[a-z0-9]+\.supabase\.co", cfg).group(0),
            re.search(r'"(sb_publishable_[^"]+)"', cfg).group(1))


def stranger(method, path, body=None):
    url, key = public()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url + path, data=data, method=method,
                                 headers={"apikey": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


@unittest.skipUnless(LIVE and has_keys(), "live network test; set PFML_LIVE=1, with the keys in .env")
class LiveReminders(unittest.TestCase):
    def test_no_channel_claims_nothing(self):
        self.assertEqual(supa.request("POST", "/rest/v1/rpc/reminders_claim", body={"p_channels": []}), [])

    def test_no_member_no_switches(self):
        # the secret key is nobody: is_member() is false, so no row
        self.assertEqual(supa.request("POST", "/rest/v1/rpc/my_notification_choices", body={}), [])

    def test_a_stranger_is_refused_by_every_new_function(self):
        calls = {"save_push_subscription": {"p_endpoint": None, "p_p256dh": None, "p_auth": None},
                 "remove_push_subscription": {"p_endpoint": None}, "my_push_subscriptions": {},
                 "set_email_reminders": {"p_on": None}, "reminders_claim": {"p_channels": []},
                 "forget_push_endpoint": {"p_endpoint": None}, "email_reminders_off": {"p_user": None},
                 # the bell (2026-10-25_notification_choices.sql)
                 "my_notification_choices": {}, "set_notification_choice": {"p_kind": None, "p_on": None},
                 "inbox_claim": {}}
        for name, body in calls.items():
            with self.subTest(name):
                self.assertEqual(stranger("POST", f"/rest/v1/rpc/{name}", body), 401)

    def test_the_function_refuses_anyone_without_the_secret(self):
        status = stranger("POST", "/functions/v1/send-reminders", {})
        if status == 404:
            self.skipTest("send-reminders isn't deployed yet")
        self.assertEqual(status, 401)
        self.assertEqual(stranger("POST", "/functions/v1/send-reminders", {"test": True}), 401)
        self.assertEqual(stranger("GET", "/functions/v1/send-reminders?unsubscribe=00000000-0000-0000-0000-000000000000.forged"), 401)


if __name__ == "__main__":
    unittest.main()
