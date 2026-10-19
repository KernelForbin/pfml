#!/usr/bin/env python3
"""One-time sign-in that lets scripts/round_playlists.py manage playlists.

    python scripts/connect_accounts.py spotify
    python scripts/connect_accounts.py youtube

Opens your browser at Spotify's or Google's own sign-in page; you approve,
the page sends you back to this script on http://127.0.0.1:8888/callback, and
it saves the long-lived refresh token in .env (git-ignored) as
SPOTIFY_REFRESH_TOKEN or YOUTUBE_REFRESH_TOKEN. The token is never printed.
Run it again any time the playlist script says the sign-in failed.

Needs the app's id and secret in .env first (README, Submissions on the
site, walks through making both apps):
  spotify: SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, with
           http://127.0.0.1:8888/callback added as a Redirect URI
  youtube: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, from a "Desktop app"
           OAuth client
Stdlib only.
"""
import http.server
import secrets
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import round_playlists as rp  # noqa: E402

PORT = 8888
REDIRECT = f"http://127.0.0.1:{PORT}/callback"

SERVICES = {
    "spotify": {
        "authorize": "https://accounts.spotify.com/authorize",
        "token": "https://accounts.spotify.com/api/token",
        "id": "SPOTIFY_CLIENT_ID", "secret": "SPOTIFY_CLIENT_SECRET", "save": "SPOTIFY_REFRESH_TOKEN",
        # make, rename and refill its own playlists; nothing else
        "scope": "playlist-modify-private playlist-modify-public playlist-read-private",
        "extra": {},
    },
    "youtube": {
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "id": "GOOGLE_CLIENT_ID", "secret": "GOOGLE_CLIENT_SECRET", "save": "YOUTUBE_REFRESH_TOKEN",
        # manage the account's YouTube playlists; no Gmail, Drive or anything else
        "scope": "https://www.googleapis.com/auth/youtube",
        # offline + consent: Google only hands out a refresh token this way
        "extra": {"access_type": "offline", "prompt": "consent"},
    },
}


def authorize_url(service, state):
    s = SERVICES[service]
    params = {"client_id": rp.env(s["id"]), "response_type": "code", "redirect_uri": REDIRECT,
              "scope": s["scope"], "state": state}
    params.update(s["extra"])
    return s["authorize"] + "?" + urllib.parse.urlencode(params)


def wait_for_code(state):
    """Serves one request on the callback and returns its ?code=."""
    got = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] != state:
                got["error"] = "the reply didn't carry this sign-in's state (an old tab?)"
            elif "error" in q:
                got["error"] = q["error"][0]
            else:
                got["code"] = q.get("code", [""])[0]
            ok = "code" in got and got["code"]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(("Signed in. You can close this tab." if ok else "Sign-in didn't finish: " + got.get("error", "no code")).encode())

        def log_message(self, *args):           # keep the code out of the terminal
            pass

    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    t = threading.Thread(target=server.handle_request, daemon=True)
    t.start()
    t.join(timeout=300)
    server.server_close()
    if not got.get("code"):
        raise SystemExit("Sign-in didn't finish: " + got.get("error", "no reply within 5 minutes"))
    return got["code"]


def exchange(service, code):
    s = SERVICES[service]
    form = {"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
            "client_id": rp.env(s["id"]), "client_secret": rp.env(s["secret"])}
    status, data, _ = rp.http("POST", s["token"], form=form)
    if status != 200 or not (data or {}).get("refresh_token"):
        raise SystemExit(f"{service} didn't hand back a refresh token ({status}: {rp.describe(data)}).")
    return data["refresh_token"]


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in SERVICES:
        raise SystemExit("usage: python scripts/connect_accounts.py spotify|youtube")
    service = sys.argv[1]
    state = secrets.token_urlsafe(16)
    url = authorize_url(service, state)
    print(f"Opening {service} sign-in in your browser. If it doesn't open, paste this address into it:\n{url}\n")
    webbrowser.open(url)
    token = exchange(service, wait_for_code(state))
    rp.save_env(SERVICES[service]["save"], token)
    print(f"Saved {SERVICES[service]['save']} in .env.")


if __name__ == "__main__":
    main()
