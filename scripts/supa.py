"""Tiny stdlib-only Supabase helper shared by publish.py and invites.py.

Reads SUPABASE_URL and SUPABASE_SECRET_KEY from the environment, or from a
`.env` file at the repo root (git-ignored). The secret key bypasses every
row level security rule, so it is only ever used by these local scripts:
never printed, never logged, never put in the site.
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"


def _load_env_file():
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def config():
    _load_env_file()
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SECRET_KEY", "")
    missing = [n for n, v in (("SUPABASE_URL", url), ("SUPABASE_SECRET_KEY", key)) if not v]
    if missing:
        raise SystemExit(
            f"Missing {', '.join(missing)}. Put them in {ENV_FILE.name} at the repo root "
            "(it's git-ignored), e.g.\n  SUPABASE_URL=https://xxxx.supabase.co\n"
            "  SUPABASE_SECRET_KEY=sb_secret_...")
    if not key.startswith("sb_secret_"):
        # The legacy service_role JWT also works, but the publishable key
        # would silently fail every write, so catch that mix-up early.
        if key.startswith("sb_publishable_"):
            raise SystemExit("SUPABASE_SECRET_KEY is set to the publishable key. Use the secret key.")
    return url, key


def request(method, path, body=None, headers=None, raw=None):
    """One HTTP call. `body` is JSON-encoded; `raw` is sent as bytes as-is.
    Secret keys go on the apikey header only (they aren't JWTs)."""
    url, key = config()
    h = {"apikey": key}
    h.update(headers or {})
    data = None
    if raw is not None:
        data = raw
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read().decode("utf-8")
            return json.loads(text) if text else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        raise SystemExit(f"Supabase {method} {path} failed: HTTP {e.code} {detail}")
    except urllib.error.URLError as e:
        raise SystemExit(f"Couldn't reach Supabase ({e.reason}). Check SUPABASE_URL.")


def upload(bucket, name, data_bytes, content_type):
    """Create or replace one object in a private bucket."""
    return request(
        "POST", f"/storage/v1/object/{bucket}/{name}", raw=data_bytes,
        headers={"Content-Type": content_type, "x-upsert": "true", "cache-control": "no-cache"},
    )
