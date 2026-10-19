#!/usr/bin/env python3
"""Build a closed site round's Spotify and YouTube playlists.

    python scripts/round_playlists.py                 # newest closed round not built yet
    python scripts/round_playlists.py --round <id>    # a particular round (also rebuilds)
    python scripts/round_playlists.py --dry-run       # match and report; write nothing
    python scripts/round_playlists.py --accept Q7 K4  # use the "unsure" matches for these tags

Once a round on the Submit page has closed, this:
  1. shuffles its tracks once (kept on every later run),
  2. looks up what each track is on its own service (Spotify, YouTube, or
     SoundCloud's oEmbed),
  3. finds its copy on the other service, by searching and comparing title,
     artist and length; a match it isn't sure of is left out and listed, never
     guessed (--accept takes it, data/playlist_overrides.json sets one by hand),
  4. creates or updates a Spotify playlist and an unlisted YouTube playlist in
     the shuffled order, leaving a gap where a track has no copy, and
  5. saves the order, titles, matches and playlist ids for the round page.

It never reads who submitted anything (site_submission_owners).

Needs, in .env (git-ignored; README, Submissions on the site, has the setup):
  SUPABASE_URL, SUPABASE_SECRET_KEY
  SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REFRESH_TOKEN
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN
The refresh tokens come from scripts/connect_accounts.py. Nothing secret is
ever printed. Stdlib only.

Spotify (measured against its docs, 2026-10-19): playlists are created with
POST /me/playlists and filled with PUT /playlists/{id}/items (the old
/users/{id}/playlists and /tracks paths were removed in February 2026), search
returns at most 10 results, and a Development Mode app works only while its
owner has Premium. YouTube: search.list has its own 100-a-day allowance;
inserting or deleting a playlist item costs 50 of the 10,000 daily units.
"""
import argparse
import base64
import difflib
import json
import os
import random
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import supa  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OVERRIDES = ROOT / "data" / "playlist_overrides.json"

SPOTIFY_ID = re.compile(r"^[A-Za-z0-9]{22}$")
YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


class ApiError(Exception):
    pass


# ---------------------------------------------------------------- .env

def env(name):
    supa._load_env_file()
    value = os.environ.get(name, "")
    if not value:
        raise SystemExit(f"Missing {name} in .env. README, Submissions on the site, has the setup.")
    return value


def save_env(name, value, path=None):
    """Set NAME=value in .env, keeping every other line. Never prints it."""
    path = Path(path or supa.ENV_FILE)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    out, done = [], False
    for line in lines:
        if re.match(r"\s*" + re.escape(name) + r"\s*=", line):
            if not done:
                out.append(f"{name}={value}")
                done = True
            continue
        out.append(line)
    if not done:
        out.append(f"{name}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.environ[name] = value


# ---------------------------------------------------------------- HTTP

def http(method, url, headers=None, body=None, form=None):
    """(status, parsed JSON or None, response headers). Tests replace this."""
    data, h = None, dict(headers or {})
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        h["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            text = r.read().decode("utf-8")
            return r.status, (json.loads(text) if text.strip() else None), dict(r.headers)
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = {"error": text[:300]}
        return e.code, parsed, dict(e.headers or {})


def describe(payload):
    """A short error description from an API response, for messages."""
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err)[:300]
        if err:
            return str(payload.get("error_description") or err)[:300]
    return str(payload)[:300]


# ---------------------------------------------------------------- tidy text

# Words that make a recording a different version. A match must agree with the
# source on each of them: "Live at Montreux" mustn't match the studio take.
# ("Remastered", "Single Version", "Radio Edit" and "Mono Mix" are left off on
# purpose: services label the same recording those ways.)
VERSION_WORDS = ["live", "cover", "karaoke", "remix", "instrumental", "acoustic", "demo",
                 "sped up", "slowed", "nightcore", "8d", "session"]

# Labels a service puts on a title to say which take it is. They're trimmed
# before titles are compared; version_words above still makes a live take
# match only a live take.
VERSION_LABELS = (r"remaster(?:ed)?|version|edit|mix|mono|stereo|single|album|live|recorded|bonus|demo|take|"
                  r"session|from|acoustic|remix|instrumental|cover")

# Bracketed or trailing bits that describe the upload, not the recording.
UPLOAD_WORDS = r"official|video|audio|lyric|lyrics|visuali[sz]er|hd|hq|4k|mv|music video|clip|explicit|clean|full song"


def fold(s):
    """Lower case, accents off, & as and."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().replace("&", " and ")


def clean_title(s):
    s = fold(s)
    s = re.sub(r"[\(\[][^\)\]]*\b(?:" + UPLOAD_WORDS + r")\b[^\)\]]*[\)\]]", " ", s)
    s = re.sub(r"[\(\[]\s*(?:feat|ft|featuring|with)\b[^\)\]]*[\)\]]", " ", s)
    # "(Live)", "[2011 Remaster]": labels, like the " - " ones below
    s = re.sub(r"[\(\[][^\)\]]*\b(?:" + VERSION_LABELS + r")\b[^\)\]]*[\)\]]", " ", s)
    s = re.sub(r"\s(?:feat|ft|featuring)\.?\s.*$", " ", s)
    # Spotify's " - 2011 Remaster", " - Single Version", " - Live at ...": the
    # song is what's before it (version_words still compares live, demo etc.)
    s = re.sub(r"\s[-\u2013]\s[^-\u2013]*\b(?:" + VERSION_LABELS + r")\b[^-\u2013]*$", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def clean_artist(s):
    s = fold(s)
    s = re.sub(r"\s-\stopic$", "", s)
    s = re.sub(r"vevo$|\bofficial\b|\bmusic\b$", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def version_words(s):
    s = " " + fold(s) + " "
    return {w for w in VERSION_WORDS if re.search(r"[^a-z]" + re.escape(w) + r"[^a-z]", s)}


def similar(a, b):
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def split_youtube_title(title, channel):
    """(artist, title) as best a video's title and channel say."""
    if channel.endswith(" - Topic"):
        return channel[: -len(" - Topic")], title
    for sep in (" - ", " – ", " — ", " | "):
        if sep in title:
            artist, rest = title.split(sep, 1)
            return artist.strip(), rest.strip()
    return re.sub(r"(?i)vevo$|\s*official$", "", channel).strip(), title


def iso_seconds(iso):
    """YouTube's PT4M13S as seconds."""
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60 + s


# ---------------------------------------------------------------- judging a match

def judge(src, cand):
    """'sure', 'unsure' or None for whether `cand` is the same recording as
    `src`. Both are {title, artist, seconds}; artist on a YouTube candidate is
    its channel plus whatever its title names."""
    if version_words(src["title"]) != version_words(cand["title"]):
        return None
    t = similar(clean_title(src["title"]), clean_title(cand["title"]))
    a_src, a_cand = clean_artist(src["artist"]), clean_artist(cand["artist"])
    artist_ok = bool(a_src) and (a_src in a_cand or a_cand in a_src or similar(a_src, a_cand) >= 0.8)
    if not artist_ok:
        return None
    if src.get("seconds") is None or cand.get("seconds") is None:
        gap = None
    else:
        gap = abs(src["seconds"] - cand["seconds"])
    if t >= 0.85 and gap is not None and gap <= 3:
        return "sure"
    if t >= 0.7 and (gap is None or gap <= 20):
        return "unsure"
    return None


def best(src, candidates):
    """(verdict, candidate) for the best of `candidates`: a sure one if any,
    else the closest unsure one, else (None, None)."""
    ranked = []
    for c in candidates:
        v = judge(src, c)
        if v:
            gap = abs((src.get("seconds") or 0) - (c.get("seconds") or 0))
            ranked.append((v != "sure", -similar(clean_title(src["title"]), clean_title(c["title"])), gap, c))
    if not ranked:
        return None, None
    ranked.sort(key=lambda r: r[:3])
    top = ranked[0]
    return ("sure" if not top[0] else "unsure"), top[3]


# ---------------------------------------------------------------- Spotify

class Spotify:
    API = "https://api.spotify.com/v1"

    def __init__(self):
        self.token = None

    def _auth(self):
        basic = base64.b64encode(f"{env('SPOTIFY_CLIENT_ID')}:{env('SPOTIFY_CLIENT_SECRET')}".encode()).decode()
        status, data, _ = http("POST", "https://accounts.spotify.com/api/token",
                               headers={"Authorization": "Basic " + basic},
                               form={"grant_type": "refresh_token", "refresh_token": env("SPOTIFY_REFRESH_TOKEN")})
        if status != 200:
            raise SystemExit(f"Spotify sign-in failed ({status}: {describe(data)}). "
                             "Run python scripts/connect_accounts.py spotify again.")
        self.token = data["access_token"]
        if data.get("refresh_token"):               # Spotify sometimes rotates it
            save_env("SPOTIFY_REFRESH_TOKEN", data["refresh_token"])

    def call(self, method, path, params=None, body=None):
        if not self.token:
            self._auth()
        url = self.API + path + ("?" + urllib.parse.urlencode(params) if params else "")
        for attempt in range(5):
            status, data, headers = http(method, url, headers={"Authorization": "Bearer " + self.token}, body=body)
            if status == 401 and attempt == 0:
                self._auth()
                continue
            if status == 429:
                time.sleep(min(int(headers.get("Retry-After", "2") or 2), 30))
                continue
            if status >= 400:
                raise ApiError(f"Spotify {method} {path}: {status} {describe(data)}")
            return data
        raise ApiError(f"Spotify {method} {path}: still rate limited")

    def track(self, track_id):
        d = self.call("GET", f"/tracks/{track_id}")
        return {"title": d["name"], "artist": ", ".join(a["name"] for a in d["artists"]),
                "seconds": round(d["duration_ms"] / 1000), "id": d["id"]}

    def search(self, title, artist):
        seen, out = set(), []
        title, artist = title.replace('"', ""), artist.replace('"', "")
        for q in (f'track:"{title}" artist:"{artist}"', f"{artist} {title}"):
            d = self.call("GET", "/search", {"q": q, "type": "track", "limit": 10})
            for t in (d.get("tracks") or {}).get("items") or []:
                if t and t["id"] not in seen:
                    seen.add(t["id"])
                    out.append({"id": t["id"], "title": t["name"], "seconds": round(t["duration_ms"] / 1000),
                                "artist": ", ".join(a["name"] for a in t["artists"])})
            if out:
                break
        return out

    def create_playlist(self, name, description):
        d = self.call("POST", "/me/playlists", body={"name": name, "description": description, "public": False})
        return d["id"]

    def update_playlist(self, playlist_id, name, description):
        self.call("PUT", f"/playlists/{playlist_id}", body={"name": name, "description": description, "public": False})

    def set_items(self, playlist_id, track_ids):
        # PUT replaces the whole list (up to 100), in this order
        self.call("PUT", f"/playlists/{playlist_id}/items",
                  body={"uris": ["spotify:track:" + t for t in track_ids[:100]]})


# ---------------------------------------------------------------- YouTube

class YouTube:
    API = "https://www.googleapis.com/youtube/v3"

    def __init__(self):
        self.token = None

    def _auth(self):
        status, data, _ = http("POST", "https://oauth2.googleapis.com/token", form={
            "client_id": env("GOOGLE_CLIENT_ID"), "client_secret": env("GOOGLE_CLIENT_SECRET"),
            "refresh_token": env("YOUTUBE_REFRESH_TOKEN"), "grant_type": "refresh_token"})
        if status != 200:
            raise SystemExit(f"YouTube sign-in failed ({status}: {describe(data)}). "
                             "Run python scripts/connect_accounts.py youtube again. If it fails every "
                             "7 days, the Google app is still in Testing (README has the fix).")
        self.token = data["access_token"]

    def call(self, method, path, params=None, body=None):
        if not self.token:
            self._auth()
        url = self.API + path + "?" + urllib.parse.urlencode(params or {})
        for attempt in range(2):
            status, data, _ = http(method, url, headers={"Authorization": "Bearer " + self.token}, body=body)
            if status == 401 and attempt == 0:
                self._auth()
                continue
            if status >= 400:
                raise ApiError(f"YouTube {method} {path}: {status} {describe(data)}")
            return data
        raise ApiError(f"YouTube {method} {path}: not signed in")

    def videos(self, ids):
        out = {}
        for i in range(0, len(ids), 50):
            d = self.call("GET", "/videos", {"part": "snippet,contentDetails", "id": ",".join(ids[i:i + 50])})
            for v in d.get("items") or []:
                channel = v["snippet"]["channelTitle"]
                artist, title = split_youtube_title(v["snippet"]["title"], channel)
                out[v["id"]] = {"id": v["id"], "title": title, "artist": artist, "channel": channel,
                                "seconds": iso_seconds(v["contentDetails"].get("duration"))}
        return out

    def search(self, title, artist):
        d = self.call("GET", "/search", {"part": "snippet", "type": "video", "videoCategoryId": "10",
                                         "maxResults": 10, "q": f"{artist} {title}"})
        ids = [i["id"]["videoId"] for i in d.get("items") or [] if i.get("id", {}).get("videoId")]
        found = self.videos(ids) if ids else {}
        # the channel counts as artist too, so an "Artist - Topic" upload titled
        # just the song still matches
        return [dict(v, artist=v["artist"] + " " + v["channel"]) for v in (found[i] for i in ids if i in found)]

    def create_playlist(self, title, description):
        d = self.call("POST", "/playlists", {"part": "snippet,status"}, body={
            "snippet": {"title": title, "description": description},
            "status": {"privacyStatus": "unlisted"}})
        return d["id"]

    def update_playlist(self, playlist_id, title, description):
        self.call("PUT", "/playlists", {"part": "snippet,status"}, body={
            "id": playlist_id, "snippet": {"title": title, "description": description},
            "status": {"privacyStatus": "unlisted"}})

    def items(self, playlist_id):
        out, token = [], None
        while True:
            params = {"part": "id,snippet", "playlistId": playlist_id, "maxResults": 50}
            if token:
                params["pageToken"] = token
            d = self.call("GET", "/playlistItems", params)
            out += [(i["id"], i["snippet"]["resourceId"]["videoId"]) for i in d.get("items") or []]
            token = d.get("nextPageToken")
            if not token:
                return out

    def set_items(self, playlist_id, video_ids):
        current = self.items(playlist_id)
        if [v for _, v in current] == list(video_ids):
            return
        for item_id, _ in current:
            self.call("DELETE", "/playlistItems", {"id": item_id})
        for n, vid in enumerate(video_ids):
            self.call("POST", "/playlistItems", {"part": "snippet"}, body={"snippet": {
                "playlistId": playlist_id, "position": n,
                "resourceId": {"kind": "youtube#video", "videoId": vid}}})


# ---------------------------------------------------------------- SoundCloud

def soundcloud_info(path):
    """{title, artist} from SoundCloud's public oEmbed (no account; measured
    2026-10-19: "Flickermood by Forss"), or None if it's gone or private."""
    url = "https://soundcloud.com/oembed?" + urllib.parse.urlencode(
        {"format": "json", "url": "https://soundcloud.com/" + path})
    status, data, _ = http("GET", url)
    if status != 200 or not isinstance(data, dict):
        return None
    title, author = data.get("title") or "", data.get("author_name") or ""
    if author and title.endswith(" by " + author):
        title = title[: -len(" by " + author)]
    return {"title": title, "artist": author, "seconds": None}


# ---------------------------------------------------------------- overrides

def read_link(text, service):
    """A track id for `service` from an id or a link, or None for "no copy"."""
    if text is None:
        return None
    text = str(text).strip()
    if service == "spotify":
        m = re.search(r"(?:track[/:])([A-Za-z0-9]{22})", text) or re.fullmatch(r"([A-Za-z0-9]{22})", text)
    else:
        m = (re.search(r"(?:[?&]v=|youtu\.be/|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})", text)
             or re.fullmatch(r"([A-Za-z0-9_-]{11})", text))
    if not m:
        raise SystemExit(f"Can't read a {service} track from {text!r} in {OVERRIDES.name}.")
    return m.group(1)


def overrides_for(round_id, path=None):
    """{tag: {"spotify": id|None, "youtube": id|None}} set by hand for a round.
    A key that's present and null means "no copy, leave the gap"."""
    path = Path(path or OVERRIDES)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8")).get(round_id) or {}
    return {tag: {svc: read_link(v, svc) for svc, v in entry.items() if svc in ("spotify", "youtube")}
            for tag, entry in data.items()}


# ---------------------------------------------------------------- the round

def shuffled_positions(subs, rng=None):
    """{submission id: position}. Positions already saved are kept; only a
    round with none yet is shuffled, once."""
    if subs and all(s.get("position") for s in subs):
        return {s["id"]: s["position"] for s in subs}
    order = [s["id"] for s in sorted(subs, key=lambda s: s["tag"])]
    (rng or random.SystemRandom()).shuffle(order)
    return {sid: n + 1 for n, sid in enumerate(order)}


def playlist_order(rows, service):
    """Track ids for one service in round order, skipping the gaps."""
    key = service + "_match"
    return [r[key] for r in sorted(rows, key=lambda r: r["position"]) if r.get(key)]


def describe_gaps(rows):
    gaps = {"spotify": [], "youtube": []}
    for r in sorted(rows, key=lambda r: r["position"]):
        for svc in gaps:
            if not r.get(svc + "_match"):
                gaps[svc].append(r["tag"])
    return gaps


def match_round(subs, spotify, youtube, overrides, accept=(), rematch=False, log=print):
    """Looks up and matches every submission. Returns (rows, unsure) where rows
    carry title, artist, spotify_match and youtube_match, and unsure lists the
    matches left out for a person to check."""
    rows, unsure = [], []
    yt_info = youtube.videos([s["track"] for s in subs if s["platform"] == "youtube"])
    for s in sorted(subs, key=lambda s: s["tag"]):
        row = {k: s.get(k) for k in ("id", "tag", "platform", "track", "position", "spotify_match", "youtube_match")}
        if s["platform"] == "spotify":
            info = spotify.track(s["track"])
            row["spotify_match"] = s["track"]
        elif s["platform"] == "youtube":
            info = yt_info.get(s["track"])
            row["youtube_match"] = s["track"]
        else:
            info = soundcloud_info(s["track"])
        if not info:
            log(f"  {s['tag']}: couldn't look up the {s['platform']} track (gone or private?); left out")
            row.update(title=None, artist=None)
            rows.append(row)
            continue
        row["title"], row["artist"] = info["title"][:300], info["artist"][:300]
        fixed = overrides.get(s["tag"], {})
        for svc, finder in (("spotify", spotify), ("youtube", youtube)):
            if s["platform"] == svc:
                continue
            if svc in fixed:                                   # set by hand, even to "none"
                row[svc + "_match"] = fixed[svc]
                continue
            if row.get(svc + "_match") and not rematch:          # matched on an earlier run
                continue
            verdict, cand = best(info, finder.search(info["title"], info["artist"]))
            if verdict == "sure" or (verdict == "unsure" and s["tag"] in accept):
                row[svc + "_match"] = cand["id"]
            else:
                row[svc + "_match"] = None
                if verdict == "unsure":
                    unsure.append((s["tag"], svc, info, cand))
        rows.append(row)
    return rows, unsure


def link(service, track_id):
    return ("https://open.spotify.com/track/" + track_id if service == "spotify"
            else "https://www.youtube.com/watch?v=" + track_id)


def report(rows, unsure, log=print):
    log("\nPos  Tag  From        Spotify  YouTube  Track")
    for r in sorted(rows, key=lambda r: r["position"]):
        s = "yes" if r.get("spotify_match") else "-"
        y = "yes" if r.get("youtube_match") else "-"
        name = f"{r.get('artist') or '?'} - {r.get('title') or '?'}"
        log(f"{r['position']:>3}  {r['tag']:<3}  {r['platform']:<10}  {s:<7}  {y:<7}  {name}")
    for tag, svc, info, cand in unsure:
        log(f"\n  Not sure about {tag} on {svc}: \"{info['artist']} - {info['title']}\" vs "
            f"\"{cand['artist']} - {cand['title']}\" ({link(svc, cand['id'])}).")
        log(f"  If that's right: --accept {tag}. If not, set it in {OVERRIDES.relative_to(ROOT)}.")


# ---------------------------------------------------------------- database

def closed(r, now=None):
    if r.get("closed_at"):
        return True
    deadline = datetime.fromisoformat(r["closes_at"].replace("Z", "+00:00"))
    return deadline <= (now or datetime.now(timezone.utc))


def pick_round(rounds, round_id=None):
    if round_id:
        found = [r for r in rounds if r["id"] == round_id]
        if not found:
            raise SystemExit(f"No site round with id {round_id}.")
        r = found[0]
    else:
        todo = [r for r in rounds if closed(r) and not r.get("playlists_built_at")]
        if not todo:
            raise SystemExit("No closed round is waiting for its playlists. Use --round <id> to rebuild one.")
        r = max(todo, key=lambda r: datetime.fromisoformat(r["closes_at"].replace("Z", "+00:00")))
    if not closed(r):
        raise SystemExit(f"\"{r['name']}\" is still open for submissions.")
    return r


def load_round(round_id=None, db=None):
    db = db or supa.request
    rounds = db("GET", "/rest/v1/site_rounds?select=*&order=created_at.desc") or []
    r = pick_round(rounds, round_id)
    # never site_submission_owners: who sent what is none of this script's business
    subs = db("GET", "/rest/v1/site_submissions?round_id=eq." + urllib.parse.quote(r["id"]) +
              "&select=id,tag,platform,track,position,title,artist,spotify_match,youtube_match") or []
    return r, subs


def save_round(r, rows, spotify_id, youtube_id, db=None):
    db = db or supa.request
    for row in rows:
        db("PATCH", "/rest/v1/site_submissions?id=eq." + urllib.parse.quote(row["id"]), body={
            k: row.get(k) for k in ("position", "title", "artist", "spotify_match", "youtube_match")},
            headers={"Prefer": "return=minimal"})
    db("PATCH", "/rest/v1/site_rounds?id=eq." + urllib.parse.quote(r["id"]), body={
        "spotify_playlist": spotify_id, "youtube_playlist": youtube_id,
        "playlists_built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
        headers={"Prefer": "return=minimal"})


def playlist_text(r, rows):
    name = f"PFML · {r['name']}"[:150]
    gaps = describe_gaps(rows)

    def desc(svc):
        missing = gaps[svc]
        tail = (f" Not on {'Spotify' if svc == 'spotify' else 'YouTube'}: {', '.join(missing)}." if missing else "")
        return ("Every track from the round, shuffled. Tags match the Music League notes." + tail)[:300]
    return name, desc("spotify"), desc("youtube")


def build(round_id=None, dry_run=False, accept=(), rematch=False, spotify=None, youtube=None, db=None, log=print):
    r, subs = load_round(round_id, db)
    if not subs:
        raise SystemExit(f"\"{r['name']}\" has no tracks.")
    log(f"{r['name']}: {len(subs)} tracks")
    spotify, youtube = spotify or Spotify(), youtube or YouTube()
    positions = shuffled_positions(subs)
    for s in subs:
        s["position"] = positions[s["id"]]
    rows, unsure = match_round(subs, spotify, youtube, overrides_for(r["id"]), accept, rematch, log)
    report(rows, unsure, log)
    if dry_run:
        log("\nDry run: nothing written, no playlists touched.")
        return r, rows, None, None
    name, sdesc, ydesc = playlist_text(r, rows)
    sp_id, yt_id = r.get("spotify_playlist"), r.get("youtube_playlist")
    if sp_id:
        spotify.update_playlist(sp_id, name, sdesc)
    else:
        sp_id = spotify.create_playlist(name, sdesc)
    spotify.set_items(sp_id, playlist_order(rows, "spotify"))
    if yt_id:
        youtube.update_playlist(yt_id, name, ydesc)
    else:
        yt_id = youtube.create_playlist(name, ydesc)
    youtube.set_items(yt_id, playlist_order(rows, "youtube"))
    save_round(r, rows, sp_id, yt_id, db)
    log(f"\nSpotify: https://open.spotify.com/playlist/{sp_id}")
    log(f"YouTube: https://www.youtube.com/playlist?list={yt_id}")
    return r, rows, sp_id, yt_id


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--round", help="a site round id (default: the newest closed one not built yet)")
    ap.add_argument("--dry-run", action="store_true", help="match and report; write nothing")
    ap.add_argument("--accept", nargs="*", default=[], metavar="TAG", help="use the unsure matches for these tags")
    ap.add_argument("--rematch", action="store_true", help="search again even where a match was saved")
    args = ap.parse_args()
    try:
        build(args.round, args.dry_run, set(t.upper() for t in args.accept), args.rematch)
    except ApiError as e:
        raise SystemExit(str(e))


if __name__ == "__main__":
    main()
