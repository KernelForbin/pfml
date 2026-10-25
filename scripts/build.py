#!/usr/bin/env python3
"""
PFML build step.

Reads the raw Music League CSV exports from data/season*/ and writes the
JSON the site loads into site/data/, plus site/seasonN.html. The site is
members-only, so neither the exports nor the JSON are in the public repo:
run scripts/publish.py (which runs this) to publish the data to the private
Supabase bucket the site reads from.

Season folders are discovered by name (season1, season2, season3, ... any
number, numeric order). A season with only competitors.csv and no rounds
yet still builds, with empty stats, so Season 3 renders cleanly from day
one and fills in as you re-export.

SCORING MODEL (verified against the real exports, not assumed):
  - Each voter gets a fixed point budget per round to spread across
    other people's tracks: 16 in Seasons 1 and 2, 19 in Season 3. The build
    reads it from the votes (`pointBudget`, the most common per-voter
    round total) rather than assuming it. A handful of Season 1
    voter-rounds total 11 instead of 16.
  - A votes.csv row with 0 points is a comment, not a vote. Every single
    zero-point row in every season carries a comment. They are counted as
    commentary, never as scoring.
  - Self-voting is blocked. The only rows where voter == submitter are
    zero-point comments on your own track.
  - Season 1 allowed negative points (35 downvotes, -5 to -1). Seasons 2
    and 3 did not. Downvotes net against the same budget.

Because the budget is fixed, "average points given" is not a measure of
generosity: everyone gives exactly the same budget a round. The stats
below measure where a voter puts their points instead.
"""
import csv
import json
import math
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "site" / "data"

# minimum chances-to-vote before a voter/submitter pair is shown in the
# taste matrix, so one lucky round does not read as a lifelong grudge. A
# pair gets one chance per round they both play, so this is also how many
# rounds a season needs before the matrix shows anything. 4 since
# 2026-10-11 (it was 5): the league wanted Season 3's after four rounds.
# The page's note reads it from the season file (tasteMinChances).
MIN_PAIR_OPPORTUNITIES = 4

# The comment matrix's guard (Silent treatment, Most talked at). Same
# denominator as the taste matrix, chances to vote on that submitter's
# tracks, and the same number until the taste one came down to 4; this
# one stayed at 5, since only the taste matrix was asked for.
MIN_COMMENT_PAIR_OPPORTUNITIES = 5

# Vocabulary richness is measured on fixed-size chunks of this many words
# (see sampled_richness). 500 sits below the smallest real corpus in the
# data (813 words), so everyone who clears one chunk is compared on the
# same amount of text.
VOCAB_SAMPLE_WORDS = 500

# Minimum comments before someone is eligible for a comment superlative or
# a rate-based stat. Rates over two or three comments are noise: one
# exclamation mark would read as a 33% exclamation rate.
MIN_COMMENTS_FOR_RATES = 10

# Tastemaker (whose biggest vote of a round most often won it): rounds voted
# before someone qualifies in a season. All-Time uses MIN_SCORED_ROUNDS.
MIN_TASTEMAKER_ROUNDS = 5

# The group toggles on the Performance over time chart (trend_groups): how
# many players each group names, plus anyone tied with the last of them.
TREND_GROUP_SIZE = 3

# Career Score (chosen by the league, 2026-09-22; README, Career Score):
#   PER_ROUND_SCALE x points per round played    ("Avg season")
# + ROUND_BONUS for each 1st / 2nd / 3rd place in a round
# + SEASON_BONUS for finishing a finished season 1st / 2nd / 3rd
# Only players with MIN_SCORED_ROUNDS rounds or more get a score.
PER_ROUND_SCALE = 20
ROUND_BONUS = {1: 3, 2: 2, 3: 1}
SEASON_BONUS = {1: 6, 2: 4, 3: 2}
MIN_SCORED_ROUNDS = 10

# Optional, produced by scripts/enrich_comments.py, never by this build.
# Absent is the normal case: the site just omits sentiment-based stats.
SENTIMENT_PATH = DATA_DIR / "comment_sentiment.json"

# The sentiment labels the site knows how to render, and the only ones
# enrich_comments.py asks for. A label outside this set in
# comment_sentiment.json is ignored rather than rendered blindly, so a
# change to the enrichment prompt can't inject arbitrary keys here.
SENTIMENT_LABELS = ("funny", "witty", "angry", "mean", "heartfelt", "hot_take",
                    "appreciative", "storytelling", "analytical")
SENTIMENT_STRENGTHS = (1, 2, 3)

# Single-comment awards from the labels: the strongest comment for each.
# Many comments share the top strength, so each award breaks the tie its
# own way: a joke or a jab lands best short, a heartfelt one long.
SENTIMENT_QUOTE_AWARDS = (
    # (key, label, prefer shorter?)
    ("funniest", "funny", True),
    ("wittiest", "witty", True),
    ("angriest", "angry", True),
    ("meanest", "mean", True),
    ("mostHeartfelt", "heartfelt", False),
    ("hottestTake", "hot_take", True),
)
# Per-player titles: the highest share of their comments carrying the
# label(s), among players with MIN_COMMENTS_FOR_RATES comments.
SENTIMENT_PLAYER_AWARDS = (
    ("classClown", ("funny", "witty")),
    ("sweetheart", ("heartfelt", "appreciative")),
    ("grump", ("angry", "mean")),
    ("hotTakeArtist", ("hot_take",)),
)

# Deliberately small and hand-written: a dependency-free stopword list for
# picking out someone's distinctive recurring word. Covers English
# function words plus the handful of words that dominate *every* Music
# League comment ("song", "track", "love") and would otherwise be the top
# word for every player, telling you nothing about any of them.
STOPWORDS = frozenset("""
a about after all also am an and any are as at be because been before being but by
can cant cause come could did didnt do does doesnt doing dont down each even ever
every for from get gets getting go goes going good got great had has have havent he
her here hers him his how i id if ill im in into is isnt it its ive just know like
ll little lot m me more most much my never no not now of off oh ok on once one only
or other our out over own re really right s said same say see she should since so
some still such than that thats the their them then there these they thing things
this those though thought through to too two up us very was wasnt way we well were
what when where which while who why will with without would yeah yes yet you your
youre song songs track tracks album albums listen listening love loved lovely
wouldve couldve shouldve woulda coulda shoulda gonna gotta wanna kinda sorta
""".split())

EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"  # pictographs, emoticons, symbols, supplemental
    "\U00002600-\U000027BF"  # misc symbols + dingbats
    "\U0001F1E6-\U0001F1FF"  # regional indicators (flags)
    "\U00002190-\U000021FF"  # arrows
    "\U00002B00-\U00002BFF"  # misc symbols and arrows
    "]"
)

WORD_RE = re.compile(r"[A-Za-z']+")


def comment_words(text):
    """Words for counting: letters and apostrophes only, so "don't" is one
    word and "2024" or a bare "..." is none. Used for every word-based
    stat so they all count the same thing."""
    return WORD_RE.findall(text or "")


def norm_word(w):
    """Lowercased, apostrophes stripped, so "don't", "dont" and "Don't" are
    one word. The stopword list is written without apostrophes and is
    matched against this, otherwise every contraction slips through the
    filter and wins "distinctive word" on rarity alone."""
    return w.lower().replace("'", "")


def is_allcaps_word(w):
    """SHOUTING, not "I" or "A" or "OK": three letters minimum, and it has to
    have an uppercase letter to begin with, so "a" never qualifies."""
    return len(w) >= 3 and w.isupper() and w.isalpha()


def best_of(items, key, lowest=False, order=None):
    """Every item tied for the best value of `key`, not just the first one
    max() or min() happens to meet.

    Returns a list. The first entry is the one a superlative names; the
    rest are what it's tied with. The list is sorted by `order`, so which
    of several tied entries leads is a stable, visible rule (alphabetical
    for people, date for rounds) rather than an accident of the data's
    order. Empty in, empty out."""
    items = list(items)
    if not items:
        return []
    vals = [key(i) for i in items]
    best = min(vals) if lowest else max(vals)
    group = [i for i, v in zip(items, vals) if v == best]
    if order is not None:
        group.sort(key=order)
    return group


def with_ties(entry, group, label):
    """The entry a superlative shows, plus "tiedWith": display labels for
    the rest of its tie. No "tiedWith" key at all when there's no tie."""
    entry = dict(entry)
    others = [label(g) for g in group[1:]]
    if others:
        entry["tiedWith"] = others
    return entry


def by_name(x):
    return (x.get("name") or "").lower()


def pair_order(x):
    return ((x.get("voterName") or "").lower(), (x.get("submitterName") or "").lower())


def pair_label(x):
    return f'{x.get("voterName")} \u2192 {x.get("submitterName")}'


def standing_after_each_round(rounds, ids):
    """Each player's place after every round, exactly as the trend chart
    draws it (app.js, computeTrendSeries, mode "standing"): points so far
    with any Daily Double bonus, and a tie shares a place (1, 1, 3)."""
    total = {i: 0 for i in ids}
    places = {i: [] for i in ids}
    for r in rounds:
        for s in r["songs"]:
            if s["submitterId"] in total:
                total[s["submitterId"]] += s["points"] + (s.get("dailyDouble") or {}).get("bonus", 0)
        order = sorted(ids, key=lambda i: -total[i])
        place = {}
        for n, i in enumerate(order):
            place[i] = place[order[n - 1]] if n and total[order[n - 1]] == total[i] else n + 1
        for i in ids:
            places[i].append(place[i])
    return places


def top_with_ties(pairs, n=TREND_GROUP_SIZE):
    """The n (id, value) pairs with the highest value, plus any tied with
    the nth, highest first. Equal values keep the order they came in."""
    ranked = sorted(pairs, key=lambda p: -p[1])
    if len(ranked) <= n:
        return ranked
    return [p for p in ranked if p[1] >= ranked[n - 1][1]]


def trend_groups(rounds, standings):
    """Who's in each group toggle on the Performance over time chart, from
    the places the chart's standing view shows. A list of {"key",
    "players": [{"id", "value"}]}, in the order the page shows them:

    - front: in the top TREND_GROUP_SIZE places now (value: place);
    - back: the bottom TREND_GROUP_SIZE now (value: place);
    - rises / falls: most places gained / lost since round 1 (value: places);
    - volatile / steady: most / fewest places moved a round, on average
      (value: places a round, to one decimal), from round 3;
    - leaders: everyone who's been #1 after any round (value: rounds at #1).

    Ties at the cut-off are all in. A group with nobody in it, or with the
    whole field (it singles nobody out), is left out. Nothing before round 2,
    when the chart itself appears."""
    ids = [p["id"] for p in standings]
    if len(rounds) < 2 or not ids:
        return []
    places = standing_after_each_round(rounds, ids)
    now = [(i, places[i][-1]) for i in ids]
    candidates = [
        ("front", sorted([p for p in now if p[1] <= TREND_GROUP_SIZE], key=lambda p: p[1])),
        ("back", top_with_ties(now)),
        ("rises", top_with_ties([(i, places[i][0] - places[i][-1]) for i in ids
                                 if places[i][0] > places[i][-1]])),
        ("falls", top_with_ties([(i, places[i][-1] - places[i][0]) for i in ids
                                 if places[i][-1] > places[i][0]])),
    ]
    if len(rounds) >= 3:
        moved = [(i, round(sum(abs(b - a) for a, b in zip(places[i], places[i][1:])) / (len(rounds) - 1), 1))
                 for i in ids]
        candidates.append(("volatile", top_with_ties([p for p in moved if p[1] > 0])))
        candidates.append(("steady", [(i, -v) for i, v in top_with_ties([(i, -v) for i, v in moved])]))
    candidates.append(("leaders", sorted([(i, places[i].count(1)) for i in ids if 1 in places[i]],
                                         key=lambda p: -p[1])))
    return [{"key": key, "players": [{"id": i, "value": v} for i, v in members]}
            for key, members in candidates if 0 < len(members) < len(ids)]


def comment_id(round_id, uri, voter_id):
    """Stable id for a single voter comment: the key in
    data/comment_sentiment.json (enrich_comments.py uses this function) and
    in the comment_* tables. Round + track + voter is unique: a voter gets
    one vote row per track per round."""
    return "%s|%s|%s" % (round_id, uri, voter_id)


def load_sentiment():
    """Reads data/comment_sentiment.json if it exists. Missing file is the
    normal case and not an error: the build carries on and the site omits
    every sentiment-based stat. Labels outside SENTIMENT_LABELS are
    dropped rather than passed through, and nothing here ever invents a
    label for a comment the file doesn't mention."""
    if not SENTIMENT_PATH.exists():
        return {}
    try:
        with open(SENTIMENT_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  ! {SENTIMENT_PATH.name} unreadable ({e}); building without sentiment")
        return {}

    entries = raw.get("comments", raw) if isinstance(raw, dict) else {}
    out = {}
    for cid, entry in entries.items():
        if not isinstance(entry, dict):
            continue
        labels = [l for l in entry.get("labels", []) if l in SENTIMENT_LABELS]
        if not labels:
            continue
        # strength 1-3 per label; a label without one (or a file from the
        # first version of the script) counts as 1, a touch of it
        given = entry.get("strength") if isinstance(entry.get("strength"), dict) else {}
        strength = {l: (given.get(l) if given.get(l) in SENTIMENT_STRENGTHS else 1) for l in labels}
        out[cid] = {"labels": labels, "strength": strength, "rationale": (entry.get("rationale") or "").strip()}
    return out


def sentiment_awards(entries, players):
    """Awards from comment_sentiment.json labels; {} without any labels.

    entries: [(entry, voter name)] for every comment; players: the career
    commenter rows (with "id", "name", "comments")."""
    labelled = [(e, n) for e, n in entries if "sentiment" in e]
    if not labelled:
        return {}
    quotes = {}
    for key, label, shorter in SENTIMENT_QUOTE_AWARDS:
        hits = [(e["sentiment"]["strength"][label], e, n) for e, n in labelled if label in e["sentiment"]["labels"]]
        if not hits:
            continue
        s, e, n = min(hits, key=lambda h: (-h[0], len(h[1]["text"]) if shorter else -len(h[1]["text"]), h[1]["id"]))
        quotes[key] = dict(quote_of(e, n), strength=s)

    titles = {}
    by_voter = {}
    for e, n in labelled:
        by_voter.setdefault(n, []).append(e)
    eligible = [p for p in players if p["comments"] >= MIN_COMMENTS_FOR_RATES]
    for key, labels in SENTIMENT_PLAYER_AWARDS:
        rows = []
        for p in eligible:
            count = sum(1 for e in by_voter.get(p["name"], []) if set(labels) & set(e["sentiment"]["labels"]))
            if count:
                rows.append({"name": p["name"], "count": count, "comments": p["comments"],
                             "rate": round(count / p["comments"], 3)})
        if rows:
            g = best_of(rows, lambda r: r["rate"], order=by_name)
            titles[key] = with_ties(g[0], g, lambda r: r["name"])
    return {"quotes": quotes, "titles": titles, "labelled": len(labelled)}


# English for comments and notes written in another language. Like the
# Daily Double decisions, it's kept by hand (translated when a new export
# arrives; README, Translations) rather than worked out here: the build has
# no network and no API key. Optional: without the file nothing is shown.
TRANSLATIONS_FILE = "translations.json"


def load_translations():
    """{comment id or "<round id>|<spotify uri>": {"from", "original", "text"}}
    from data/translations.json; {} without it. Not a scoring input, so a
    broken file or entry is skipped with a warning rather than stopping
    the build."""
    path = DATA_DIR / TRANSLATIONS_FILE
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"  ! {TRANSLATIONS_FILE} unreadable ({e}); building without translations")
        return {}
    out = {}
    for section in ("comments", "notes"):
        entries = raw.get(section, {}) if isinstance(raw, dict) else {}
        for key, e in (entries.items() if isinstance(entries, dict) else []):
            if isinstance(e, dict) and all(isinstance(e.get(k), str) and e[k].strip() for k in ("from", "original", "text")):
                out[key] = {k: e[k].strip() for k in ("from", "original", "text")}
            else:
                print(f"  ! {TRANSLATIONS_FILE}: {section}[{key!r}] needs \"from\", \"original\" and \"text\"; skipped")
    return out


def translation_for(translations, key, text, used):
    """The English for one comment or note, or None. Only when it was made
    from this exact text, so an edited or mistyped entry never puts someone
    else's words under a comment. Records the key in `used`."""
    t = translations.get(key)
    if not t:
        return None
    used.add(key)
    if t["original"] != text:
        print(f"  ! {TRANSLATIONS_FILE}: {key} was translated from different text; not shown")
        return None
    return {"from": t["from"], "text": t["text"]}


# Season 3 rule: once per season, a submitter can ask in their own note on
# a submission to have that track's points doubled toward their total. Which
# notes are real requests is a judgement about intent (a note can mention the
# prop without invoking it), so nothing here parses notes. The decisions are
# made by reading them and recorded by hand in data/seasonN/daily_doubles.json;
# this build only applies what that file says, and only where it exists.
DAILY_DOUBLE_FILE = "daily_doubles.json"
DD_DECISIONS = ("accepted", "rejected")


def load_daily_doubles(folder):
    """The recorded Daily Double decisions for one season, or None when the
    season doesn't use the rule (no file). A broken file stops the build
    rather than being skipped: it's a scoring input, and silently ignoring
    it would publish someone's total without their bonus."""
    path = folder / DAILY_DOUBLE_FILE
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise SystemExit(f"{path}: unreadable ({e}). Fix it before building; it changes totals.")
    check_daily_doubles(path, raw)
    requests = raw.get("requests", [])
    return {
        "reviewed": {r["roundId"] for r in raw.get("reviewedRounds", [])},
        "accepted": [r for r in requests if r["decision"] == "accepted"],
    }


def check_daily_doubles(path, raw):
    """Stops the build, naming the entry, on anything the scoring can't
    trust. Only an exact "accepted" is applied, so a decision spelled
    "Accepted" used to drop the bonus without a word; a missing field
    crashed with a bare traceback instead."""
    def stop(msg):
        raise SystemExit(f"{path}: {msg}. Fix it before building; it changes totals.")

    def text(entry, key):
        return isinstance(entry.get(key), str) and entry[key].strip()

    if not isinstance(raw, dict):
        stop("expected an object with \"requests\" and \"reviewedRounds\"")
    for key in ("requests", "reviewedRounds"):
        if not isinstance(raw.get(key, []), list):
            stop(f"\"{key}\" must be a list")
    for i, r in enumerate(raw.get("reviewedRounds", [])):
        if not isinstance(r, dict) or not text(r, "roundId"):
            stop(f"reviewedRounds[{i}] needs a \"roundId\"")
    for i, r in enumerate(raw.get("requests", [])):
        if not isinstance(r, dict):
            stop(f"requests[{i}] must be an object")
        if r.get("decision") not in DD_DECISIONS:
            stop(f"requests[{i}] has decision {r.get('decision')!r}; it must be exactly "
                 f"\"accepted\" or \"rejected\"")
        if r["decision"] == "accepted":
            missing = [k for k in ("roundId", "spotifyUri", "submitterId") if not text(r, k)]
            if missing:
                stop(f"requests[{i}] is accepted but has no {', '.join(missing)}")


def season_folders():
    """data/seasonN folders in season order, numerically, so season10 comes
    after season9. publish.py and enrich_comments.py use this too."""
    return sorted(
        [p for p in DATA_DIR.iterdir() if p.is_dir() and re.fullmatch(r"season\d+", p.name)],
        key=lambda p: int(re.search(r"\d+", p.name).group()),
    )


def read_csv(path):
    """Rows as dicts, with line breaks inside cells normalised to LF.

    Git stores these CSVs with LF, but a Windows checkout (core.autocrlf)
    hands the build CRLF, and newline="" rightly keeps whatever is inside a
    quoted cell, so a multi-line comment came out as CRLF on Windows and LF
    on the Linux runner that deploys the site: two different builds from
    one commit. Normalising here makes the output the same everywhere."""
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for k, v in row.items():
            if isinstance(v, str) and "\r" in v:
                row[k] = v.replace("\r\n", "\n").replace("\r", "\n")
    return rows


def track_id(uri):
    """spotify:track:XXXX -> XXXX. A site round's YouTube or SoundCloud key
    (site_uri) has the same shape, so the service is checked too."""
    if not uri:
        return None
    parts = uri.split(":")
    return parts[-1] if len(parts) == 3 and parts[0] == "spotify" and parts[1] == "track" else None


# ---- rounds voted on the site (README, Site rounds in the stats) ----

SITE_ROUNDS_FILE = "site_rounds.json"
SITE_NAMES = {"spotify": "Spotify", "youtube": "YouTube", "soundcloud": "SoundCloud"}


def with_link(out, track):
    """out, plus the track's link when it was sent from YouTube or
    SoundCloud: copies of a track carry it wherever its spotifyId goes."""
    if track.get("link"):
        out["link"] = track["link"]
    return out


def site_uri(platform, track):
    """The key a site track goes by here, in place of Music League's Spotify
    URI: Spotify's own for a Spotify pick, so it lines up with everything
    keyed that way, and the same shape for YouTube and SoundCloud."""
    return f"{platform}:track:{track}"


def season_label(folder, num):
    """What a season is called: the name it was given when it was set up on
    the site (site_rounds.json carries it), or "Season N"."""
    path = folder / SITE_ROUNDS_FILE
    if path.exists():
        name = (json.loads(path.read_text(encoding="utf-8")).get("season_name") or "").strip()
        if name:
            return name
    return f"Season {num}"


def site_season_rows(folder):
    """A season's rounds voted on pfml.fun (site_rounds.json, which
    scripts/publish.py writes from the database's site_rounds_export()), as
    rows shaped like Music League's CSVs, so everything below counts them
    the same way. Plus what those rows can't carry, by (round id, uri): the
    track's Spotify copy (album art, repeat checks), its link when it was
    submitted on YouTube or SoundCloud, and a forfeit when its submitter
    didn't vote and the round says that costs their points.
    Returns (competitors, rounds, submissions, votes, extras)."""
    path = folder / SITE_ROUNDS_FILE
    if not path.exists():
        return [], [], [], [], {}
    data = json.loads(path.read_text(encoding="utf-8"))
    players = data.get("players") or {}
    rounds, subs, votes, extras = [], [], [], {}
    taking_part = set()
    for r in data.get("rounds") or []:
        playlist = r.get("spotify_playlist")
        rounds.append({"ID": r["id"], "Created": r["created_at"], "Name": r["name"],
                       "Description": r.get("prompt") or "",
                       "Playlist URL": f"https://open.spotify.com/playlist/{playlist}" if playlist else ""})
        voted = {v["voter"] for v in r.get("votes") or []}
        uri_of = {}
        for s in r.get("submissions") or []:
            uri = site_uri(s["platform"], s["track"])
            uri_of[s["id"]] = uri
            submitter = s.get("submitter") or ""
            title = s.get("title")
            if not title:
                # the playlists step names tracks; a round it never ran on
                title = f"{SITE_NAMES.get(s['platform'], 'A')} track {s.get('tag') or ''}".strip()
                print(f"  ! {folder.name}: {r['name']}: a track has no title yet (run scripts/round_playlists.py)")
            subs.append({"Spotify URI": uri, "Title": title, "Album": "", "Artist(s)": s.get("artist") or "",
                         "Submitter ID": submitter, "Created": r["created_at"], "Comment": "",
                         "Round ID": r["id"], "Visible To Voters": "Yes"})
            extra = {"spotifyId": s["track"] if s["platform"] == "spotify" else s.get("spotify_match")}
            if s["platform"] != "spotify":
                extra["link"] = {"platform": s["platform"], "id": s["track"]}
            if submitter and submitter not in voted and not r.get("nonvoters_keep_points"):
                extra["forfeit"] = True
            extras[(r["id"], uri)] = extra
            taking_part.add(submitter)
        for v in r.get("votes") or []:
            votes.append({"Spotify URI": uri_of[v["submission"]], "Voter ID": v["voter"],
                          "Created": v.get("cast_at") or "", "Points Assigned": str(v["points"]),
                          "Comment": v.get("comment") or "", "Round ID": r["id"]})
            taking_part.add(v["voter"])
    competitors = [{"ID": pid, "Name": players[pid]} for pid in sorted(taking_part) if pid in players]
    return competitors, rounds, subs, votes, extras


def playlist_id(url):
    """https://open.spotify.com/playlist/XXXX?si=... -> XXXX"""
    if not url:
        return None
    m = re.search(r"open\.spotify\.com/(?:intl-[\w-]+/)?playlist/([A-Za-z0-9]+)", url)
    return m.group(1) if m else None


def split_artists(raw):
    """Music League joins multiple artists with ', '. Good enough to split
    on, with the caveat that an artist whose own name contains a comma will
    be split wrongly. No such case exists in the current exports."""
    if not raw:
        return []
    return [a.strip() for a in raw.split(",") if a.strip()]


def comment_text_stats(comments):
    """Per-player text stats over one player's voter comments.

    `comments` is a list of dicts with at least "text" and "points". Every
    word-based number counts the same thing (see comment_words): letters
    and apostrophes, so "don't" is one word and "2024" is none.

    The three style rates (exclamation, question, ALL-CAPS) are all the
    *share of that player's comments containing at least one*, not a
    per-comment average. One comment shouting "YES!!!!!!!!" would drag an
    average into nonsense; "what fraction of their comments do this" is
    robust to that and is what the page claims.
    """
    texts = [c["text"] for c in comments]
    word_lists = [comment_words(t) for t in texts]
    lengths = [len(w) for w in word_lists]
    total_words = sum(lengths)
    all_words = [norm_word(w) for words in word_lists for w in words]

    n = len(comments)
    containing = lambda pred: round(sum(1 for t in texts if pred(t)) / n, 3) if n else 0

    return {
        "comments": n,
        "totalWords": total_words,
        "meanWords": round(statistics.mean(lengths), 1) if lengths else 0,
        "medianWords": round(statistics.median(lengths), 1) if lengths else 0,
        "zeroPointComments": sum(1 for c in comments if c["points"] == 0),
        # share of comments containing at least one of each
        "exclamationRate": containing(lambda t: "!" in t),
        "questionRate": containing(lambda t: "?" in t),
        "allCapsRate": containing(lambda t: any(is_allcaps_word(w) for w in comment_words(t))),
        # Unique over total words on fixed-size chunks, not the whole corpus
        # (see sampled_richness): a raw ratio falls as someone writes more,
        # so it would rank people by how little they wrote.
        "vocabRichnessSampled": sampled_richness(all_words),
    }


def sampled_richness(words, size=VOCAB_SAMPLE_WORDS):
    """Mean segmental type-token ratio: unique-over-total measured on fixed
    `size`-word chunks and averaged, rather than over someone's whole
    corpus at once.

    A raw unique/total ratio falls as a body of text grows (you run out of
    new words to use), so comparing it between players mostly ranks them
    by how little they wrote. In this league's real data that inversion is
    near total: the top of a raw ranking is the player with 813 words and
    the bottom is the player with 13,549. Chunking fixes the denominator
    so everyone is measured over the same amount of text.

    Returns None below one full chunk, so a short commenter is left out of
    the comparison instead of being given a flattering number.
    """
    if len(words) < size:
        return None
    chunks = [words[i:i + size] for i in range(0, len(words) - size + 1, size)]
    ratios = [len(set(c)) / size for c in chunks]
    return round(statistics.mean(ratios), 3)


def distinctive_word(player_words, league_counts, league_total, min_uses=3):
    """The word this player uses most out of proportion to the league.

    Same shape as the taste index: the player's share of a word divided by
    the league's share of it. A word has to appear at least `min_uses`
    times for that player to qualify, so a one-off doesn't win on a
    denominator of one. Stopwords are dropped first (see STOPWORDS),
    otherwise every player's answer is "the" and then "song".

    Returns None when the player has no qualifying word, which is the
    normal case for someone with only a handful of comments.
    """
    counts = {}
    for w in player_words:
        w = norm_word(w)
        if len(w) < 3 or w in STOPWORDS:
            continue
        counts[w] = counts.get(w, 0) + 1
    total = sum(counts.values())
    if not total or not league_total:
        return None

    best = None
    for w, c in counts.items():
        if c < min_uses:
            continue
        league_share = league_counts.get(w, 0) / league_total
        if not league_share:
            continue
        ratio = (c / total) / league_share
        # ties break on the more-used word, then alphabetically, so the
        # result is stable across builds rather than dict-order luck
        key = (ratio, c, w)
        if best is None or key > best[0]:
            best = (key, {"word": w, "uses": c, "vsLeague": round(ratio, 2)})
    return best[1] if best else None


def comment_superlatives(eligible):
    """The per-player comment superlatives, with ties. Used for a season
    and for a whole career; `eligible` is players with enough comments."""
    out = {}
    name = lambda c: c["name"]

    g = best_of(eligible, lambda c: c["commentRate"], order=by_name)
    out["chattiest"] = with_ties({"name": g[0]["name"], "rate": g[0]["commentRate"],
                                  "comments": g[0]["comments"]}, g, name)
    g = best_of(eligible, lambda c: c["commentRate"], lowest=True, order=by_name)
    out["quietest"] = with_ties({"name": g[0]["name"], "rate": g[0]["commentRate"],
                                 "comments": g[0]["comments"]}, g, name)
    g = best_of(eligible, lambda c: c["meanWords"], order=by_name)
    out["wordiest"] = with_ties({"name": g[0]["name"], "meanWords": g[0]["meanWords"],
                                 "comments": g[0]["comments"]}, g, name)
    g = best_of(eligible, lambda c: c["meanWords"], lowest=True, order=by_name)
    out["tersest"] = with_ties({"name": g[0]["name"], "meanWords": g[0]["meanWords"],
                                "comments": g[0]["comments"]}, g, name)
    g = best_of(eligible, lambda c: c["allCapsRate"], order=by_name)
    if g[0]["allCapsRate"] > 0:
        out["loudest"] = with_ties({"name": g[0]["name"], "rate": g[0]["allCapsRate"]}, g, name)
    sampled = [c for c in eligible if c.get("vocabRichnessSampled") is not None]
    if sampled:
        g = best_of(sampled, lambda c: c["vocabRichnessSampled"], order=by_name)
        out["richestVocab"] = with_ties({"name": g[0]["name"], "richness": g[0]["vocabRichnessSampled"],
                                         "comments": g[0]["comments"], "sampleWords": VOCAB_SAMPLE_WORDS}, g, name)
    g = best_of(eligible, lambda c: c["zeroPointComments"], order=by_name)
    if g[0]["zeroPointComments"] > 0:
        out["mostZeroPoint"] = with_ties({"name": g[0]["name"], "count": g[0]["zeroPointComments"]}, g, name)
    return out


def pair_superlatives(pairs):
    """Silent treatment and most talked at, with ties. The metric is the
    comment rate, with more chances ranking higher at the same rate (a zero
    across 20 chances says more than a zero across 5), so a tie means the
    same rate AND the same number of chances."""
    out = {}
    g = best_of(pairs, lambda p: (p["rate"], -p["chances"]), lowest=True, order=pair_order)
    out["silentTreatment"] = with_ties(g[0], g, pair_label)
    g = best_of(pairs, lambda p: (p["rate"], p["chances"]), order=pair_order)
    out["mostTalkedAt"] = with_ties(g[0], g, pair_label)
    return out


def point_budget(points_at):
    """The points each voter spends a round: the most common per-voter round
    total. It isn't the same in every season (16 in Seasons 1 and 2, 19 in
    Season 3), so the page copy can't hard-code it. A voter who only left
    zero-point comments totals 0 and says nothing about the budget, so those
    are ignored, and the few Season 1 voter-rounds that total 11 lose the
    vote to the 16s. Ties take the larger number, so the answer never
    depends on dict order. None for a season with no votes.

    points_at: {(round id, spotify uri, voter id): points}"""
    round_totals = {}
    for (rid, _uri, vid), pts in points_at.items():
        round_totals[(rid, vid)] = round_totals.get((rid, vid), 0) + pts
    counts = {}
    for total in round_totals.values():
        if total > 0:
            counts[total] = counts.get(total, 0) + 1
    return max(counts, key=lambda t: (counts[t], t)) if counts else None


def build_season(folder: Path, season_key: str, label: str, translations=None):
    competitor_rows = read_csv(folder / "competitors.csv")
    round_rows = read_csv(folder / "rounds.csv")
    sub_rows = read_csv(folder / "submissions.csv")
    vote_rows = read_csv(folder / "votes.csv")

    # rounds voted on the site join the export's, in the same shape
    site_people, site_rounds, site_subs, site_votes, site_extra = site_season_rows(folder)
    known = {r["ID"] for r in competitor_rows}
    competitor_rows += [r for r in site_people if r["ID"] not in known]
    round_rows += site_rounds
    sub_rows += site_subs
    vote_rows += site_votes

    def spotify_of(rid, uri):
        """The track's Spotify id: its own, or a site track's Spotify copy."""
        extra = site_extra.get((rid, uri))
        return extra["spotifyId"] if extra else track_id(uri)

    def track_ref(rid, uri):
        """What a page needs to link a track: its Spotify id, and for a site
        track sent from YouTube or SoundCloud, where it was sent from."""
        ref = {"spotifyId": spotify_of(rid, uri)}
        link = site_extra.get((rid, uri), {}).get("link")
        if link:
            ref["link"] = link
        return ref

    names = {r["ID"]: r["Name"] for r in competitor_rows}
    if translations is None:
        translations = load_translations()
    translated = set()   # keys this season used, so main() can name any that match nothing

    subs_by_round = {}
    for r in sub_rows:
        subs_by_round.setdefault(r["Round ID"], []).append(r)

    # (round, uri, voter) -> points, plus a comment index
    points_at = {}
    comments_at = {}
    comments_by_vote = set()   # (round, uri, voter) keys that carry a comment
    voters_in_round = {}
    for v in vote_rows:
        key = (v["Round ID"], v["Spotify URI"], v["Voter ID"])
        points_at[key] = int(v["Points Assigned"])
        if v.get("Comment", "").strip():
            comments_by_vote.add(key)
            cid = comment_id(*key)
            c = {"id": cid, "voterId": v["Voter ID"], "voterName": names.get(v["Voter ID"], "Unknown"),
                 "points": int(v["Points Assigned"]), "comment": v["Comment"].strip()}
            tr = translation_for(translations, cid, c["comment"], translated)
            if tr:
                c["translation"] = tr
            comments_at.setdefault((v["Round ID"], v["Spotify URI"]), []).append(c)
        voters_in_round.setdefault(v["Round ID"], set()).add(v["Voter ID"])

    # accumulators
    player = {cid: {"id": cid, "name": name, "points": 0, "votePoints": 0, "submissions": 0,
                     "roundsWon": 0, "podiums": 0}
              for cid, name in names.items()}
    voter = {cid: {"id": cid, "name": name, "roundsVoted": 0, "tracksBackedTotal": 0,
                    "topBets": [], "kingmakerHits": 0, "kingmakerRounds": 0}
             for cid, name in names.items()}
    pair_points = {}        # (voter, submitter) -> points given
    pair_chances = {}       # (voter, submitter) -> tracks they could have voted on
    pair_comments = {}      # (voter, submitter) -> comments left on their tracks
    # every voter comment with the context the page needs to show it
    voter_comments = {cid: [] for cid in names}
    vote_rows_by_voter = {}

    # lookups so a comment can name the track and round it was left on
    round_name_by_id = {r["ID"]: r.get("Name", "") for r in round_rows}
    sub_by_key = {(r["Round ID"], r["Spotify URI"]): r for r in sub_rows}

    sentiment = load_sentiment()

    # Album art, cached by scripts/publish.py from Spotify's public oEmbed
    # endpoint. Optional: without the file, tracks just have no art.
    art_path = DATA_DIR / "track_art.json"
    track_art = json.loads(art_path.read_text(encoding="utf-8")) if art_path.exists() else {}

    for v in vote_rows:
        vid = v["Voter ID"]
        vote_rows_by_voter[vid] = vote_rows_by_voter.get(vid, 0) + 1
        text = v.get("Comment", "").strip()
        if not text or vid not in voter:
            continue
        sub = sub_by_key.get((v["Round ID"], v["Spotify URI"]))
        cid = comment_id(v["Round ID"], v["Spotify URI"], vid)
        entry = {
            "id": cid,
            "text": text,
            "points": int(v["Points Assigned"]),
            "roundId": v["Round ID"],
            "roundName": round_name_by_id.get(v["Round ID"], ""),
            "trackTitle": sub.get("Title", "") if sub else "",
            **track_ref(v["Round ID"], v["Spotify URI"]),
            "submitterId": sub.get("Submitter ID") if sub else None,
        }
        # Only ever attached when enrich_comments.py has actually labelled
        # this exact comment; never inferred here.
        if cid in sentiment:
            entry["sentiment"] = sentiment[cid]
        tr = translation_for(translations, cid, text, translated)
        if tr:
            entry["translation"] = tr   # follows it into the longest comment and quote cards
        voter_comments[vid].append(entry)

    rounds_out = []
    all_songs = []
    comment_only_votes = 0
    downvotes = 0

    daily = load_daily_doubles(folder)
    dd_by_track = {}
    for r in (daily["accepted"] if daily else []):
        key = (r["roundId"], r["spotifyUri"])
        if key in dd_by_track:
            # two accepted decisions for one track would otherwise collapse
            # to whichever came last, silently
            raise SystemExit(f"{folder / DAILY_DOUBLE_FILE}: more than one accepted request for the "
                             f"same track {key}. Keep one.")
        dd_by_track[key] = r
    dd_matched = set()
    dd_used = {}        # submitter -> the Daily Double actually applied
    dd_ignored = []

    for rnd in sorted(round_rows, key=lambda r: r.get("Created", "")):
        rid = rnd["ID"]
        round_subs = subs_by_round.get(rid, [])
        # sorted, not the raw set: a set of strings iterates in an order that
        # changes with Python's per-process hash seed, and that order used to
        # leak into the taste list (and so into which of several tied pairs
        # won Biggest fan / Coldest shoulder), making every build different
        electorate = sorted(voters_in_round.get(rid, set()))

        songs = []
        for s in round_subs:
            uri = s["Spotify URI"]
            submitter = s["Submitter ID"]
            received = []
            for vid in electorate:
                pts = points_at.get((rid, uri, vid))
                if pts is None:
                    continue
                if pts == 0:
                    comment_only_votes += 1
                    continue
                if pts < 0:
                    downvotes += 1
                received.append({"voterId": vid, "voterName": names.get(vid, "Unknown"), "points": pts})

            earned = sum(r["points"] for r in received)
            # a site round's track whose submitter didn't vote keeps only its
            # downvotes when the round says so, as Music League does: 0 with
            # none (README, Voting on the site; More songs and downvotes)
            forfeit = site_extra.get((rid, uri), {}).get("forfeit", False)
            total = sum(min(r["points"], 0) for r in received) if forfeit else earned
            artists = split_artists(s["Artist(s)"])
            received.sort(key=lambda r: r["points"], reverse=True)

            song = {
                **track_ref(rid, uri),
                "title": s["Title"],
                "album": s["Album"],
                "artists": artists,
                "artistText": s["Artist(s)"],
                "submitterId": submitter,
                "submitterName": names.get(submitter, "Unknown"),
                "roundId": rid,
                "roundName": rnd["Name"],
                "note": s.get("Comment", "").strip(),
                "points": total,
                "backers": len(received),
                "spread": round(statistics.pstdev([r["points"] for r in received]), 2) if len(received) > 1 else 0,
                "comments": comments_at.get((rid, uri), []),
                "art": track_art.get(spotify_of(rid, uri)),
                # every scoring vote, compact: [voter id, points], biggest
                # first. Zero-point rows aren't votes (they're comments,
                # already in "comments"); names come from "competitors".
                "votes": [[r["voterId"], r["points"]] for r in received],
            }
            tr = translation_for(translations, f"{rid}|{uri}", song["note"], translated) if song["note"] else None
            if tr:
                song["noteTranslation"] = tr
            if forfeit:
                song["forfeit"] = {"earned": earned}
            if not track_id(uri):
                # a site track's own key, for the comment lookup (lookup.json)
                song["uri"] = uri
            song["_uri"] = uri      # for this round's kingmaker check; dropped below
            songs.append(song)
            all_songs.append(song)

            # Daily Double: the track's points count twice toward the season
            # total. The track's own score, and so the round's placings,
            # wins and podiums, stay what the votes said.
            bonus = 0
            req = dd_by_track.get((rid, uri))
            if req:
                dd_matched.add((rid, uri))
                if req.get("submitterId") != submitter:
                    dd_ignored.append(f"{rnd['Name']} / {s['Title']}: recorded submitter doesn't match the track's")
                elif submitter in dd_used:
                    dd_ignored.append(f"{rnd['Name']} / {s['Title']}: {names.get(submitter)} already used theirs "
                                      f"in {dd_used[submitter]['roundName']}")
                else:
                    bonus = total
                    dd_used[submitter] = {
                        "roundId": rid, "roundName": rnd["Name"], "trackTitle": s["Title"],
                        "spotifyId": spotify_of(rid, uri), "basePoints": total, "bonus": bonus,
                    }
                    song["dailyDouble"] = {"bonus": bonus}

            if submitter in player:
                player[submitter]["points"] += total + bonus
                player[submitter]["votePoints"] += total
                player[submitter]["submissions"] += 1
                if submitter in dd_used and dd_used[submitter]["roundId"] == rid:
                    player[submitter]["dailyDouble"] = dd_used[submitter]

        songs.sort(key=lambda x: x["points"], reverse=True)

        # placements, ties share the better rank
        rank = 0
        last_points = None
        won, podium = set(), set()
        for i, s in enumerate(songs):
            if s["points"] != last_points:
                rank = i + 1
                last_points = s["points"]
            s["place"] = rank
            pid = s["submitterId"]
            # once a round per player, by their best track: a round can take
            # more than one song from each (README, More songs and downvotes)
            if pid in player:
                if rank == 1 and pid not in won:
                    won.add(pid)
                    player[pid]["roundsWon"] += 1
                if rank <= 3 and pid not in podium:
                    podium.add(pid)
                    player[pid]["podiums"] += 1

        # by the build's own key, not the Spotify id: two site tracks with
        # no Spotify copy would both have none, and look like one track
        winning_uris = {s["_uri"] for s in songs if s.get("place") == 1}
        for s in songs:
            del s["_uri"]

        # voter behaviour for this round
        for vid in electorate:
            backed = 0
            top_bet = 0
            top_uris = []
            for s in round_subs:
                pts = points_at.get((rid, s["Spotify URI"], vid))
                if pts is None or pts <= 0:
                    continue
                backed += 1
                if pts > top_bet:
                    top_bet = pts
                    top_uris = [s["Spotify URI"]]
                elif pts == top_bet:
                    top_uris.append(s["Spotify URI"])
            if vid in voter and backed:
                voter[vid]["roundsVoted"] += 1
                voter[vid]["tracksBackedTotal"] += backed
                voter[vid]["topBets"].append(top_bet)
                voter[vid]["kingmakerRounds"] += 1
                if any(u in winning_uris for u in top_uris):
                    voter[vid]["kingmakerHits"] += 1

            # pair-level: every track they could have scored counts, whether
            # or not they scored it, so a zero is real information. A chance
            # is a round with that submitter's tracks in it: one track a round
            # in every Music League season, and a round on the site can take
            # more than one from each player (README, More songs and
            # downvotes), so their points are added up within the round.
            chanced, commented = set(), set()
            for s in round_subs:
                submitter = s["Submitter ID"]
                if submitter == vid:
                    continue
                pts = points_at.get((rid, s["Spotify URI"], vid), 0)
                pts = max(pts, 0)
                pair_points[(vid, submitter)] = pair_points.get((vid, submitter), 0) + pts
                if submitter not in chanced:
                    chanced.add(submitter)
                    pair_chances[(vid, submitter)] = pair_chances.get((vid, submitter), 0) + 1
                # same denominator as the taste matrix: a "chance" is a
                # round this voter could have voted on that submitter's
                # tracks. Here we count how often they said something.
                if (rid, s["Spotify URI"], vid) in comments_by_vote and submitter not in commented:
                    commented.add(submitter)
                    pair_comments[(vid, submitter)] = pair_comments.get((vid, submitter), 0) + 1

        margin = (songs[0]["points"] - songs[1]["points"]) if len(songs) > 1 else None
        rounds_out.append({
            "id": rid,
            "name": rnd["Name"],
            "description": rnd.get("Description", "").strip(),
            "created": rnd.get("Created", ""),
            "playlistUrl": rnd.get("Playlist URL", "").strip(),
            "songs": songs,
            "margin": margin,
            # Whether anyone has a vote row for this round. Music League's
            # export only holds finished rounds (measured, see the season
            # timeline below), so in a real export this is always true; it
            # stays as a guard for a hand-made or partial folder, where the
            # round list says "voting hasn't started" instead of showing an
            # empty result.
            "hasVotingActivity": len(electorate) > 0,
        })

    # ---- standings ----
    standings = [p for p in player.values() if p["submissions"] > 0]
    standings.sort(key=lambda p: (-p["points"], -p["roundsWon"], p["name"]))
    # Places go by points alone, and equal points share a place (1, 1, 3),
    # the same competition ranking the rounds and the trend chart use.
    # Rounds won only orders people within a shared place; it doesn't break
    # the tie.
    prev_points, place = None, 0
    for i, p in enumerate(standings):
        if p["points"] != prev_points:
            place, prev_points = i + 1, p["points"]
        p["rank"] = place
    for p in standings:
        p["tied"] = sum(1 for q in standings if q["rank"] == p["rank"]) > 1
    for p in standings:
        # per-submission average reflects what the votes gave, so a Daily
        # Double lifts the total without inflating the average
        p["avgPerSubmission"] = round(p["votePoints"] / p["submissions"], 1)

    daily_double = None
    if daily is not None:
        missing = [k for k in dd_by_track if k not in dd_matched]
        if missing:
            raise SystemExit(f"{folder / DAILY_DOUBLE_FILE}: accepted request(s) match no submission "
                             f"(round id + Spotify URI): {missing}. A typo here would silently drop a bonus.")
        for msg in dd_ignored:
            print(f"  ! {season_key} Daily Double ignored: {msg}")
        unreviewed = [r.get("Name", r["ID"]) for r in sorted(round_rows, key=lambda r: r.get("Created", ""))
                      if r["ID"] not in daily["reviewed"]]
        if unreviewed:
            print(f"  ! {season_key}: submitter notes not yet reviewed for Daily Double in: {', '.join(unreviewed)}")
        daily_double = {
            "used": [dict(v, playerId=k, playerName=names.get(k, "Unknown")) for k, v in dd_used.items()],
            "reviewedRounds": sum(1 for r in round_rows if r["ID"] in daily["reviewed"]),
            "unreviewedRounds": unreviewed,
        }

    # ---- season timeline ----
    # startedAt: the Created timestamp of the first round, straight from
    # rounds.csv. liveRound is the latest round in the export, which is
    # always a finished one: Music League's export leaves out a round until
    # it's over. Measured 2026-09-21 against export (3).zip, taken while
    # Season 2's last round was being played: that round was entirely
    # absent (no round row, submissions or votes), and all 19 rounds it did
    # hold had exactly the votes of the final export. So the export can't
    # say which phase an unfinished round is in, and nothing here guesses;
    # this used to call the latest round "Voting" because it had votes.
    started_at = rounds_out[0]["created"] if rounds_out else None
    live_round = {"number": len(rounds_out), "name": rounds_out[-1]["name"]} if rounds_out else None

    # ---- voting style ----
    voters_out = []
    for v in voter.values():
        if not v["roundsVoted"]:
            continue
        v["avgTracksBacked"] = round(v["tracksBackedTotal"] / v["roundsVoted"], 1)
        v["avgTopBet"] = round(statistics.mean(v["topBets"]), 2) if v["topBets"] else 0
        v["kingmakerRate"] = round(v["kingmakerHits"] / v["kingmakerRounds"], 3) if v["kingmakerRounds"] else 0
        del v["topBets"]
        voters_out.append(v)
    voters_out.sort(key=lambda v: v["avgTopBet"], reverse=True)

    # ---- taste: points a round ----
    # How many points a voter gave one submitter's songs, per round they
    # could have voted on them (a "chance"). Every voter spends the same
    # fixed budget a round across nearly the same songs, so this compares
    # fairly between voters as it is, in the league's own units, and an even
    # split comes out near 1 (tasteEvenSplit: 1.08, 1.07 and 1.03 in Seasons
    # 1-3). It replaced a share-of-points ratio ("1.97x") on 2026-10-11 that
    # members found hard to read; both ranked the same top five, every season.
    taste = []
    for (vid, sid), pts in pair_points.items():
        chances = pair_chances[(vid, sid)]
        if chances < MIN_PAIR_OPPORTUNITIES:
            continue
        taste.append({
            "voterId": vid,
            "voterName": names.get(vid, "Unknown"),
            "submitterId": sid,
            "submitterName": names.get(sid, "Unknown"),
            "perRound": round(pts / chances, 2),
            "points": pts,
            "chances": chances,
        })
    chances_all = sum(pair_chances.values())
    taste_even_split = round(sum(pair_points.values()) / chances_all, 2) if chances_all else None

    # ---- comment stats ----
    # Voter comments only. A submitter's own note on their track lives in
    # submissions.csv and is counted separately below, since it's a
    # different act: describing your own pick, not reacting to someone
    # else's, and it's far rarer (60 of 316 in S1 against 2,194 vote
    # comments).
    league_word_counts = {}
    league_word_total = 0
    for cid, entries in voter_comments.items():
        for e in entries:
            for w in comment_words(e["text"]):
                w = norm_word(w)
                if len(w) < 3 or w in STOPWORDS:
                    continue
                league_word_counts[w] = league_word_counts.get(w, 0) + 1
                league_word_total += 1

    commenters = []
    for cid in sorted(names, key=lambda c: names[c]):
        entries = voter_comments.get(cid, [])
        vote_row_count = vote_rows_by_voter.get(cid, 0)
        if not vote_row_count:
            continue
        stats = comment_text_stats([{"text": e["text"], "points": e["points"]} for e in entries])
        stats["id"] = cid
        stats["name"] = names[cid]
        # share of this player's vote rows that carried a comment. The
        # denominator is every row they filed, including the zero-point
        # rows that exist *only* to carry a comment.
        stats["commentRate"] = round(len(entries) / vote_row_count, 3)
        player_words = [w for e in entries for w in comment_words(e["text"])]
        stats["distinctiveWord"] = (
            distinctive_word(player_words, league_word_counts, league_word_total)
            if len(entries) >= MIN_COMMENTS_FOR_RATES else None
        )
        if entries:
            longest = max(entries, key=lambda e: (len(comment_words(e["text"])), len(e["text"])))
            stats["longest"] = comment_card(longest)
        # only present when enrich_comments.py has run; never invented
        labelled = [e for e in entries if "sentiment" in e]
        if labelled:
            counts = {}
            for e in labelled:
                for l in e["sentiment"]["labels"]:
                    counts[l] = counts.get(l, 0) + 1
            stats["sentiment"] = {"labelled": len(labelled), "counts": counts}
        commenters.append(stats)

    commenters.sort(key=lambda c: (-c["comments"], c["name"]))

    # directed comment matrix, same shape and same minimum-sample guard as
    # the taste matrix: how often this voter says something on that
    # submitter's tracks, out of the chances they had to.
    comment_pairs = []
    for (vid, sid), chances in pair_chances.items():
        if chances < MIN_COMMENT_PAIR_OPPORTUNITIES:
            continue
        said = pair_comments.get((vid, sid), 0)
        comment_pairs.append({
            "voterId": vid,
            "voterName": names.get(vid, "Unknown"),
            "submitterId": sid,
            "submitterName": names.get(sid, "Unknown"),
            "comments": said,
            "chances": chances,
            "rate": round(said / chances, 3),
        })
    comment_pairs.sort(key=lambda p: (p["voterName"], p["submitterName"]))

    # submitter notes: the submitter's own comment on their own track
    submitter_notes = []
    notes_by_player = {}
    for r in sub_rows:
        text = (r.get("Comment") or "").strip()
        if not text:
            continue
        notes_by_player.setdefault(r["Submitter ID"], []).append({
            "text": text,
            "words": len(comment_words(text)),
            "roundName": round_name_by_id.get(r["Round ID"], ""),
            "trackTitle": r.get("Title", ""),
            **track_ref(r["Round ID"], r["Spotify URI"]),
        })
    subs_by_player = {}
    for r in sub_rows:
        subs_by_player[r["Submitter ID"]] = subs_by_player.get(r["Submitter ID"], 0) + 1
    for pid, notes in sorted(notes_by_player.items(), key=lambda kv: names.get(kv[0], "")):
        total = subs_by_player.get(pid, 0)
        submitter_notes.append({
            "id": pid,
            "name": names.get(pid, "Unknown"),
            "notes": len(notes),
            "submissions": total,
            "noteRate": round(len(notes) / total, 3) if total else 0,
            "totalWords": sum(n["words"] for n in notes),
            "longest": max(notes, key=lambda n: n["words"]),
        })
    submitter_notes.sort(key=lambda s: (-s["notes"], s["name"]))

    comment_summary = {}
    if commenters:
        total_comments = sum(c["comments"] for c in commenters)
        eligible = [c for c in commenters if c["comments"] >= MIN_COMMENTS_FOR_RATES]
        comment_summary = {
            "totalComments": total_comments,
            "totalWords": sum(c["totalWords"] for c in commenters),
            "commentOnlyVotes": comment_only_votes,
            "minCommentsForRates": MIN_COMMENTS_FOR_RATES,
            "submitterNoteCount": sum(s["notes"] for s in submitter_notes),
            "hasSentiment": any("sentiment" in c for c in commenters),
        }
        if total_comments:
            longest_overall = max(
                (c for c in commenters if c.get("longest")),
                key=lambda c: c["longest"]["words"], default=None)
            if longest_overall:
                comment_summary["longestComment"] = dict(longest_overall["longest"], name=longest_overall["name"])
        if eligible:
            comment_summary.update(comment_superlatives(eligible))
        if comment_pairs:
            comment_summary.update(pair_superlatives(comment_pairs))

    # ---- highlights ----
    highlights = {}
    if all_songs:
        track_label = lambda t: f'{t["title"]} ({t["submitterName"]})'
        track_order = lambda t: (t["title"].lower(), t["submitterName"].lower())
        g = best_of(all_songs, lambda t: t["points"], order=track_order)
        highlights["topTrack"] = with_ties(with_link({k: g[0][k] for k in
                                           ("title", "artistText", "album", "submitterName", "points", "spotifyId", "roundName")}, g[0]),
                                          g, track_label)

        contested = [s for s in all_songs if s["backers"] >= 3]
        if contested:
            g = best_of(contested, lambda t: t["spread"], order=track_order)
            highlights["divisiveTrack"] = with_ties(with_link({k: g[0][k] for k in
                                                    ("title", "artistText", "submitterName", "spread", "spotifyId", "roundName")}, g[0]),
                                                   g, track_label)

        shut_out = [s for s in all_songs if s["points"] <= 0]
        highlights["shutOutCount"] = len(shut_out)

        decided = [r for r in rounds_out if r["margin"] is not None]
        if decided:
            by_date = lambda r: r["created"] or ""
            g = best_of(decided, lambda r: r["margin"], lowest=True, order=by_date)
            highlights["closestRound"] = with_ties({"name": g[0]["name"], "margin": g[0]["margin"]},
                                                   g, lambda r: r["name"])
            # A blowout only means something next to a closer round. With
            # one round (or every round won by the same margin) it would be
            # the closest round again, and after a tie it read "won by 0
            # points". So it's left out until some round was won by more
            # than the closest one.
            widest = max(r["margin"] for r in decided)
            if widest > highlights["closestRound"]["margin"]:
                g = best_of(decided, lambda r: r["margin"], order=by_date)
                highlights["blowoutRound"] = with_ties({"name": g[0]["name"], "margin": g[0]["margin"],
                                                        "winner": g[0]["songs"][0]["submitterName"],
                                                        "title": g[0]["songs"][0]["title"]},
                                                       g, lambda r: r["name"])

        if taste:
            # at the same points a round, more rounds of it is the stronger
            # case, both ways
            g = best_of(taste, lambda t: (t["perRound"], t["chances"]), order=pair_order)
            highlights["biggestFan"] = with_ties(g[0], g, pair_label)
            g = best_of(taste, lambda t: (t["perRound"], -t["chances"]), lowest=True, order=pair_order)
            highlights["coldestShoulder"] = with_ties(g[0], g, pair_label)

        if voters_out:
            name = lambda v: v["name"]
            g = best_of(voters_out, lambda v: v["avgTopBet"], order=by_name)
            highlights["boldestVoter"] = with_ties(g[0], g, name)
            g = best_of(voters_out, lambda v: v["avgTracksBacked"], order=by_name)
            highlights["hedgiestVoter"] = with_ties(g[0], g, name)
            eligible = [v for v in voters_out if v["kingmakerRounds"] >= MIN_TASTEMAKER_ROUNDS]
            if eligible:
                g = best_of(eligible, lambda v: v["kingmakerRate"], order=by_name)
                highlights["bestTastemaker"] = with_ties(g[0], g, name)

        artist_counts = {}
        for s in all_songs:
            for a in s["artists"]:
                entry = artist_counts.setdefault(a, {"name": a, "count": 0, "points": 0})
                entry["count"] += 1
                entry["points"] += s["points"]
        repeats = sorted([a for a in artist_counts.values() if a["count"] > 1],
                         key=lambda a: (-a["count"], -a["points"]))
        highlights["repeatArtists"] = repeats[:10]
        highlights["downvotes"] = downvotes

    data = {
        "key": season_key,
        "label": label,
        "competitors": sorted([{"id": cid, "name": n} for cid, n in names.items()], key=lambda c: c["name"]),
        "rounds": rounds_out,
        "standings": standings,
        "voters": voters_out,
        "taste": taste,
        "tasteMinChances": MIN_PAIR_OPPORTUNITIES,
        "tasteEvenSplit": taste_even_split,
        "commenters": commenters,
        "submitterNotes": submitter_notes,
        "commentSummary": comment_summary,
        "highlights": highlights,
        "trendGroups": trend_groups(rounds_out, standings),
        "songCount": len(all_songs),
        "pointBudget": point_budget(points_at),
        "dailyDouble": daily_double,
        "startedAt": started_at,
        "liveRound": live_round,
    }

    # Side channel for build_career, deliberately NOT part of the season
    # JSON the site downloads. A career median or vocabulary richness can't
    # be recombined from per-season summaries (you need every comment's
    # length, and the union of the words, not two medians averaged), and
    # shipping every raw comment length per player per season would bloat
    # seasonN.json for data no page reads. So the raw corpus goes to
    # build_career() in memory and dies there.
    raw = {
        "key": season_key,
        "label": label,
        "names": names,
        "voterComments": voter_comments,
        "voteRowsByVoter": vote_rows_by_voter,
        "pairChances": pair_chances,
        "pairComments": pair_comments,
        "notesByPlayer": notes_by_player,
        "subsByPlayer": subs_by_player,
        "translated": translated,
    }
    return data, raw


# Quote awards need a real showing to be worth an award: a comment with
# one exclamation mark isn't "the most excited" of anything.
MIN_QUOTE_AWARD_COUNT = 3
SKIN_TONE_RE = re.compile("[\U0001F3FB-\U0001F3FF]")


def comment_card(e):
    """One comment as a quote card shows it: the text, its English when it
    was written in another language, and the track and round it was on."""
    card = with_link({"text": e["text"], "words": len(comment_words(e["text"])), "roundName": e["roundName"],
                      "trackTitle": e["trackTitle"], "spotifyId": e["spotifyId"], "points": e["points"]}, e)
    if e.get("translation"):
        card["translation"] = e["translation"]
    return card


def quote_of(e, name):
    """A comment card for the all-time awards: who wrote it, and when."""
    return dict(comment_card(e), name=name, seasonLabel=e.get("seasonLabel", ""))


def quote_awards(entries):
    """Single comments that stand out, all-time: [(entry, voter name)].

    Each award is one comment, picked by a count with a fixed tie-break
    (then the shorter text, then the comment id) so the same export always
    picks the same comment. Counted from the text alone; nothing here
    needs comment_sentiment.json. An award is left out when its best count
    is under MIN_QUOTE_AWARD_COUNT.
    """
    def best(count):
        scored = [(count(e), e, n) for e, n in entries]
        scored = [s for s in scored if s[0] > 0]
        if not scored:
            return None
        return min(scored, key=lambda s: (-s[0], len(s[1]["text"]), s[1]["id"]))

    def caps(t):
        return sum(1 for w in comment_words(t) if is_allcaps_word(w))

    def emoji(t):
        # a skin tone rides on the emoji before it: one clap, not two
        return len(EMOJI_RE.findall(SKIN_TONE_RE.sub("", t)))

    awards = {}
    for key, count, unit in (("loudest", lambda e: caps(e["text"]), "all-caps words"),
                             ("mostExcited", lambda e: e["text"].count("!"), "exclamation marks"),
                             ("mostQuestions", lambda e: e["text"].count("?"), "question marks"),
                             ("mostEmoji", lambda e: emoji(e["text"]), "emoji")):
        s = best(count)
        if s and s[0] >= MIN_QUOTE_AWARD_COUNT:
            awards[key] = dict(quote_of(s[1], s[2]), count=s[0], unit=unit)

    # the most said while giving nothing: longest comment on a 0-point row
    zero = [(e, n) for e, n in entries if e["points"] == 0 and comment_words(e["text"])]
    if zero:
        e, n = min(zero, key=lambda x: (-len(comment_words(x[0]["text"])), len(x[0]["text"]), x[0]["id"]))
        awards["mostWordsForZero"] = quote_of(e, n)

    # the least said: fewest words (at least one), then the biggest vote,
    # then the fewest letters
    worded = [(e, n) for e, n in entries if comment_words(e["text"])]
    if worded:
        e, n = min(worded, key=lambda x: (len(comment_words(x[0]["text"])), -x[0]["points"], len(x[0]["text"]), x[0]["id"]))
        awards["shortest"] = quote_of(e, n)
    return awards


def build_career_comments(raw_seasons):
    """Career comment stats, recomputed from every season's raw comments
    rather than by averaging per-season summaries.

    That matters for two of these: a career median words-per-comment is
    the median over all of someone's comments, not the mean of their
    per-season medians, and career vocabulary richness needs the union of
    the words they used, not a sum of per-season unique counts. Both come
    out wrong if you aggregate the summaries. Everything else here is a
    plain sum and would have survived either way.

    Seasons with no rounds contribute nothing, same as the standings join.
    """
    by_player = {}
    names = {}
    for raw in raw_seasons:
        for cid, name in raw["names"].items():
            names.setdefault(cid, name)
        for cid, entries in raw["voterComments"].items():
            slot = by_player.setdefault(cid, {"entries": [], "voteRows": 0})
            rows = raw["voteRowsByVoter"].get(cid, 0)
            if not rows:
                continue
            slot["entries"].extend(entries)
            slot["voteRows"] += rows

    league_word_counts = {}
    league_word_total = 0
    for slot in by_player.values():
        for e in slot["entries"]:
            for w in comment_words(e["text"]):
                w = norm_word(w)
                if len(w) < 3 or w in STOPWORDS:
                    continue
                league_word_counts[w] = league_word_counts.get(w, 0) + 1
                league_word_total += 1

    players = []
    for cid, slot in by_player.items():
        if not slot["voteRows"]:
            continue
        entries = slot["entries"]
        stats = comment_text_stats([{"text": e["text"], "points": e["points"]} for e in entries])
        stats["id"] = cid
        stats["name"] = names.get(cid, "Unknown")
        stats["commentRate"] = round(len(entries) / slot["voteRows"], 3)
        player_words = [w for e in entries for w in comment_words(e["text"])]
        stats["distinctiveWord"] = (
            distinctive_word(player_words, league_word_counts, league_word_total)
            if len(entries) >= MIN_COMMENTS_FOR_RATES else None
        )
        if entries:
            longest = max(entries, key=lambda e: (len(comment_words(e["text"])), len(e["text"])))
            stats["longest"] = dict(comment_card(longest), seasonLabel=longest.get("seasonLabel", ""))
        # present only for comments enrich_comments.py actually labelled
        labelled = [e for e in entries if "sentiment" in e]
        if labelled:
            counts = {}
            for e in labelled:
                for l in e["sentiment"]["labels"]:
                    counts[l] = counts.get(l, 0) + 1
            stats["sentiment"] = {"labelled": len(labelled), "counts": counts}
        players.append(stats)
    players.sort(key=lambda p: (-p["comments"], p["name"]))

    # career comment matrix: chances and comments summed across seasons,
    # then the same minimum-sample guard applied once to the career totals
    pair_chances, pair_comments = {}, {}
    for raw in raw_seasons:
        for key, n in raw["pairChances"].items():
            pair_chances[key] = pair_chances.get(key, 0) + n
        for key, n in raw["pairComments"].items():
            pair_comments[key] = pair_comments.get(key, 0) + n
    pairs = []
    for (vid, sid), chances in pair_chances.items():
        if chances < MIN_COMMENT_PAIR_OPPORTUNITIES:
            continue
        said = pair_comments.get((vid, sid), 0)
        pairs.append({
            "voterName": names.get(vid, "Unknown"), "submitterName": names.get(sid, "Unknown"),
            "comments": said, "chances": chances, "rate": round(said / chances, 3),
        })
    pairs.sort(key=lambda p: (p["voterName"], p["submitterName"]))

    notes = {}
    subs = {}
    for raw in raw_seasons:
        for pid, lst in raw["notesByPlayer"].items():
            notes.setdefault(pid, []).extend(lst)
        for pid, n in raw["subsByPlayer"].items():
            subs[pid] = subs.get(pid, 0) + n

    summary = {}
    if players:
        eligible = [p for p in players if p["comments"] >= MIN_COMMENTS_FOR_RATES]
        summary["totalComments"] = sum(p["comments"] for p in players)
        summary["totalWords"] = sum(p["totalWords"] for p in players)
        summary["minCommentsForRates"] = MIN_COMMENTS_FOR_RATES
        summary["hasSentiment"] = any("sentiment" in p for p in players)
        longest_overall = max((p for p in players if p.get("longest")),
                              key=lambda p: p["longest"]["words"], default=None)
        if longest_overall:
            summary["longestComment"] = dict(longest_overall["longest"], name=longest_overall["name"])
        all_entries = [(e, names.get(cid, "Unknown")) for cid, slot in by_player.items() if slot["voteRows"] for e in slot["entries"]]
        summary["quoteAwards"] = quote_awards(all_entries)
        sentiment = sentiment_awards(all_entries, players)
        if sentiment:
            summary["sentimentAwards"] = sentiment
        if eligible:
            sup = comment_superlatives(eligible)
            # the career page calls these two by career-flavoured names
            sup["mostTalkative"] = sup.pop("chattiest")
            sup["mostTerse"] = sup.pop("tersest")
            summary.update(sup)
        if pairs:
            # "silent treatment": the pair with the lowest comment rate over
            # the most chances, i.e. the person you've had every chance to
            # say something to and never have.
            summary.update(pair_superlatives(pairs))
        if notes:
            noters = [{"name": names.get(pid, "Unknown"), "notes": len(lst), "submissions": subs.get(pid, 0)}
                      for pid, lst in notes.items()]
            g = best_of(noters, lambda n: n["notes"], order=by_name)
            summary["mostSubmitterNotes"] = with_ties(g[0], g, lambda n: n["name"])
            summary["submitterNoteCount"] = sum(len(v) for v in notes.values())

    return {"players": players, "summary": summary}


def build_career(season_datas, raw_seasons=None):
    """Aggregates standings across every season by competitor id. IDs and
    names were checked to be stable for the same person across seasons in
    the real exports (no mismatches found), so this is a safe join, not a
    guess. A season with zero rounds contributes nothing (nobody has a
    standings entry yet)."""
    names = {}
    totals = {}
    played_seasons = [d for d in season_datas if d["rounds"]]

    for d in season_datas:
        for c in d["competitors"]:
            names.setdefault(c["id"], c["name"])
        for p in d["standings"]:
            t = totals.setdefault(p["id"], {
                "id": p["id"], "name": p["name"], "totalPoints": 0,
                "roundsWon": 0, "podiums": 0, "submissions": 0, "extraSongs": 0,
                "seasonsPlayed": 0, "bestSeasonPoints": None, "bestSeasonKey": None,
                "roundFinishes": {"first": 0, "second": 0, "third": 0}, "seasonPodiums": [],
            })
            t["totalPoints"] += p["points"]
            t["roundsWon"] += p["roundsWon"]
            t["podiums"] += p["podiums"]
            t["submissions"] += p["submissions"]
            t["seasonsPlayed"] += 1
            if t["bestSeasonPoints"] is None or p["points"] > t["bestSeasonPoints"]:
                t["bestSeasonPoints"] = p["points"]
                t["bestSeasonKey"] = d["key"]
        # 1st/2nd/3rd in each round, from the tracks' own places (a tie
        # shares the place, so both tracks count), and the rounds each
        # player played. Once a round per player, by their best track: a
        # round on the site can take more than one song from each.
        for r in d["rounds"]:
            best, sent = {}, {}
            for s in r["songs"]:
                sent[s["submitterId"]] = sent.get(s["submitterId"], 0) + 1
                if s.get("place") and (s["submitterId"] not in best or s["place"] < best[s["submitterId"]]):
                    best[s["submitterId"]] = s["place"]
            for pid, n in sent.items():
                if pid in totals:
                    totals[pid]["extraSongs"] += n - 1
            for pid, place in best.items():
                slot = {1: "first", 2: "second", 3: "third"}.get(place)
                if slot and pid in totals:
                    totals[pid]["roundFinishes"][slot] += 1

    # A season's final podium counts once a newer season exists: the export
    # never says a season is over (CLAUDE.md), and the newest one may be a
    # round in, with a leader who hasn't won anything yet.
    finished = [d for d in season_datas[:-1] if d["rounds"]]
    for d in finished:
        for p in d["standings"]:
            if p["rank"] in SEASON_BONUS and p["id"] in totals:
                totals[p["id"]]["seasonPodiums"].append({"key": d["key"], "label": d["label"], "place": p["rank"]})

    players = []
    for t in totals.values():
        t["avgPointsPerSeason"] = round(t["totalPoints"] / t["seasonsPlayed"], 1) if t["seasonsPlayed"] else 0
        # Career Score: an average rather than a total, so a missed season
        # (or round) doesn't count against anyone, plus bonuses for finishing
        # on top. "Rounds" is rounds played: tracks submitted, less any
        # second or third track in the same round (every Music League season
        # took one a round). Points include any Daily Double bonus, as the
        # season totals do.
        t["rounds"] = t["submissions"] - t.pop("extraSongs")
        f = t["roundFinishes"]
        t["avgSeason"] = round(PER_ROUND_SCALE * t["totalPoints"] / t["rounds"], 1) if t["rounds"] else 0
        t["roundBonus"] = ROUND_BONUS[1] * f["first"] + ROUND_BONUS[2] * f["second"] + ROUND_BONUS[3] * f["third"]
        t["seasonBonus"] = sum(SEASON_BONUS[s["place"]] for s in t["seasonPodiums"])
        t["rated"] = t["rounds"] >= MIN_SCORED_ROUNDS
        # rounded to one decimal, so equal scores compare equal (ties)
        t["careerScore"] = round(t["avgSeason"] + t["roundBonus"] + t["seasonBonus"], 1) if t["rated"] else None
        players.append(t)
    # rated players by score; the rest after them, most rounds first
    players.sort(key=lambda p: (not p["rated"], -(p["careerScore"] or 0), -p["rounds"], p["name"]))

    highlights = {}
    if players:
        name = lambda p: p["name"]
        rated = [p for p in players if p["rated"]]
        if rated:
            g = best_of(rated, lambda p: p["careerScore"], order=by_name)
            highlights["topScore"] = with_ties({"name": g[0]["name"], "careerScore": g[0]["careerScore"]}, g, name)
        g = best_of(players, lambda p: p["roundsWon"], order=by_name)
        highlights["mostWins"] = with_ties({"name": g[0]["name"], "roundsWon": g[0]["roundsWon"]}, g, name)
        g = best_of(players, lambda p: p["podiums"], order=by_name)
        highlights["mostPodiums"] = with_ties({"name": g[0]["name"], "podiums": g[0]["podiums"]}, g, name)
        # Tastemaker, all-time: how often a player's biggest vote
        # of a round went to that round's winner, summed over every season
        # (each season's voters carry kingmakerHits and kingmakerRounds, the
        # rounds they voted in). Scored after MIN_SCORED_ROUNDS rounds, like
        # the Career Score: measured, 3 of 4 rounds (75%) would otherwise
        # top it. At the same rate, more hits wins.
        reads = {}
        for d in season_datas:
            for v in d["voters"]:
                r = reads.setdefault(v["id"], {"name": names.get(v["id"], v["name"]), "kingmakerHits": 0, "kingmakerRounds": 0})
                r["kingmakerHits"] += v["kingmakerHits"]
                r["kingmakerRounds"] += v["kingmakerRounds"]
        eligible = [r for r in reads.values() if r["kingmakerRounds"] >= MIN_SCORED_ROUNDS]
        for r in eligible:
            r["kingmakerRate"] = round(r["kingmakerHits"] / r["kingmakerRounds"], 3)
        if eligible:
            g = best_of(eligible, lambda r: (r["kingmakerRate"], r["kingmakerHits"]), order=by_name)
            highlights["bestTastemaker"] = with_ties(g[0], g, name)

        labels = {d["key"]: d["label"] for d in season_datas}
        g = best_of(players, lambda p: p["bestSeasonPoints"], order=by_name)
        highlights["bestSingleSeason"] = with_ties(
            {"name": g[0]["name"], "points": g[0]["bestSeasonPoints"], "season": labels.get(g[0]["bestSeasonKey"], "")},
            g, lambda p: f'{p["name"]} ({labels.get(p["bestSeasonKey"], "")})')

    comments = build_career_comments(raw_seasons or [])

    return {
        "players": players,
        "highlights": highlights,
        "seasons": [{"key": d["key"], "label": d["label"]} for d in played_seasons],
        "careerScoreFormula": {"perRoundScale": PER_ROUND_SCALE, "roundBonus": [ROUND_BONUS[1], ROUND_BONUS[2], ROUND_BONUS[3]],
                               "seasonBonus": [SEASON_BONUS[1], SEASON_BONUS[2], SEASON_BONUS[3]],
                               "minRounds": MIN_SCORED_ROUNDS},
        "commenters": comments["players"],
        "commentSummary": comments["summary"],
    }


PROFILE_TOP_TRACKS = 5
PROFILE_TOP_PEOPLE = 3
# A taste twin needs this many rounds both players voted in. Fewer rounds
# also count for less (TASTE_TWIN_SHRINK), so a newcomer's six lucky rounds
# don't outrank years of agreeing.
TASTE_TWIN_MIN_ROUNDS = 5
TASTE_TWIN_SHRINK = 10


def taste_twins(season_datas):
    """Who votes most like whom, for the profile page: player id -> up to
    PROFILE_TOP_PEOPLE others, closest first, as {id, rounds}.

    In each round both voted in, take each one's points over the songs
    neither of them sent (nobody can vote for their own), less their own
    average for that round: which songs they backed more than usual. The
    match is the correlation of those, pooled over every shared round, then
    scaled by rounds / (rounds + TASTE_TWIN_SHRINK). Only a positive match
    counts.

    Measured on the real league 2026-10-24: the plain cosine of points made
    one player who spreads small points widely everyone's twin, because
    spreading looks like agreeing; centring each round removed that. It also
    paired the two players who share a surname, over 46 rounds. The
    correlations are modest (the best is about 0.3), so the page shows the
    order and the rounds, not a percentage."""
    pairs = {}
    for d in season_datas:
        for r in d["rounds"]:
            given = {}
            for n, s in enumerate(r["songs"]):
                for voter, pts in s["votes"]:
                    given.setdefault(voter, {})[n] = pts
            voters = sorted(given)
            for i, a in enumerate(voters):
                for b in voters[i + 1:]:
                    shared = [n for n, s in enumerate(r["songs"]) if s["submitterId"] not in (a, b)]
                    if not shared:
                        continue
                    xa = [given[a].get(n, 0) for n in shared]
                    xb = [given[b].get(n, 0) for n in shared]
                    ma, mb = sum(xa) / len(xa), sum(xb) / len(xb)
                    acc = pairs.setdefault((a, b), [0, 0, 0, 0])   # sum of products, squares a, squares b, rounds
                    for va, vb in zip(xa, xb):
                        acc[0] += (va - ma) * (vb - mb)
                        acc[1] += (va - ma) ** 2
                        acc[2] += (vb - mb) ** 2
                    acc[3] += 1
    twins = {}
    for (a, b), (dot, na, nb, rounds) in pairs.items():
        if rounds < TASTE_TWIN_MIN_ROUNDS or not na or not nb:
            continue
        score = dot / math.sqrt(na * nb) * rounds / (rounds + TASTE_TWIN_SHRINK)
        if score <= 0:
            continue
        twins.setdefault(a, []).append((score, rounds, b))
        twins.setdefault(b, []).append((score, rounds, a))
    return {pid: [{"id": b, "rounds": rounds} for _, rounds, b in sorted(lst, key=lambda t: (-t[0], -t[1], t[2]))[:PROFILE_TOP_PEOPLE]]
            for pid, lst in twins.items()}


def build_profiles(season_datas):
    """Per-player extras for the profile page (profile.html), keyed by
    competitor id: each season's finish, their highest-scoring tracks, who
    gave them the most points and who they gave the most. Totals, Career
    Score and comment stats are already in career.json; the page reads both.
    Everything here is summed from the season data rather than from the raw
    CSVs, so it agrees with what the season pages show."""
    profiles = {}

    def profile(pid, name):
        return profiles.setdefault(pid, {"id": pid, "name": name, "seasons": [], "tracks": [],
                                         "_fans": {}, "_favorites": {}, "pointsGiven": 0})

    for d in season_datas:
        # (a season with no rounds has no standings or songs: adds nothing)
        names = {c["id"]: c["name"] for c in d["competitors"]}
        field = len(d["standings"])
        for p in d["standings"]:
            profile(p["id"], p["name"])["seasons"].append({
                "key": d["key"], "label": d["label"], "rank": p["rank"], "tied": p["tied"], "field": field,
                "points": p["points"], "roundsWon": p["roundsWon"], "podiums": p["podiums"],
                "submissions": p["submissions"],
            })
        for n, r in enumerate(d["rounds"], 1):
            for s in r["songs"]:
                sub = profile(s["submitterId"], s["submitterName"])
                sub["tracks"].append(with_link({
                    "title": s["title"], "artistText": s["artistText"], "spotifyId": s["spotifyId"],
                    "art": s.get("art"), "points": s["points"], "place": s["place"],
                    "roundId": r["id"], "roundName": r["name"], "roundNumber": n,
                    "seasonKey": d["key"], "seasonLabel": d["label"],
                }, s))
                for voter, pts in s["votes"]:
                    if pts <= 0:
                        continue
                    sub["_fans"][voter] = sub["_fans"].get(voter, 0) + pts
                    v = profile(voter, names.get(voter, "Unknown"))
                    v["_favorites"][s["submitterId"]] = v["_favorites"].get(s["submitterId"], 0) + pts
                    v["pointsGiven"] += pts

    def top_people(totals):
        ranked = sorted(totals.items(), key=lambda kv: (-kv[1], profiles[kv[0]]["name"] if kv[0] in profiles else kv[0]))
        return [{"id": pid, "name": profiles[pid]["name"] if pid in profiles else "Unknown", "points": pts}
                for pid, pts in ranked[:PROFILE_TOP_PEOPLE]]

    twins = taste_twins(season_datas)
    out = {}
    for pid, p in profiles.items():
        # newest season first within equal points, so a recent hit isn't
        # buried under an older one on the same score
        order = {d["key"]: i for i, d in enumerate(season_datas)}
        tracks = sorted(p["tracks"], key=lambda t: (-t["points"], -order[t["seasonKey"]], -t["roundNumber"], t["title"]))
        out[pid] = {
            "id": pid, "name": p["name"], "seasons": p["seasons"],
            "bestTracks": tracks[:PROFILE_TOP_TRACKS],
            "fans": top_people(p["_fans"]),
            "favorites": top_people(p["_favorites"]),
            "tasteTwins": [{"id": t["id"], "name": profiles[t["id"]]["name"], "rounds": t["rounds"]}
                           for t in twins.get(pid, []) if t["id"] in profiles],
            "pointsGiven": p["pointsGiven"],
        }
    return {"players": dict(sorted(out.items()))}


def build_vault(season_datas):
    """Every round's winning track, for the Home page's From the vault tile
    (one at random on each visit): what it was, who sent it, their note,
    and the comment from whoever backed it most (the longest, on a tie).
    A tie for first lists each winner."""
    winners = []
    for d in season_datas:
        for n, r in enumerate(d["rounds"], 1):
            for s in r["songs"]:
                if s.get("place") != 1:
                    continue
                comments = sorted(s["comments"], key=lambda c: (-c["points"], -len(c["comment"])))
                best = comments[0] if comments else None
                winners.append(with_link({
                    "seasonKey": d["key"], "seasonLabel": d["label"], "roundId": r["id"], "roundNumber": n,
                    "roundName": r["name"], "title": s["title"], "artistText": s["artistText"],
                    "submitterId": s["submitterId"], "submitterName": s["submitterName"],
                    "spotifyId": s["spotifyId"], "art": s.get("art"), "points": s["points"], "note": s["note"],
                    "comment": {k: best[k] for k in ("voterName", "comment", "translation") if k in best} if best else None,
                }, s))
    return {"winners": winners}


def build_lookup(season_datas):
    """Round id -> where it lives and what's in it, for the header's inbox:
    an inbox item only has a comment id ("<round>|<spotify uri>|<voter>"),
    and the season files are ~1MB each, too much to fetch just to name the
    round and track a reaction was on. This is a few tens of KB."""
    rounds = {}
    for d in season_datas:
        for n, r in enumerate(d["rounds"], 1):
            rounds[r["id"]] = {
                "season": d["key"], "seasonLabel": d["label"], "number": n, "name": r["name"],
                # keyed as comment ids are: a site track by its own key
                "tracks": {s.get("uri") or "spotify:track:" + s["spotifyId"]: s["title"]
                           for s in r["songs"] if s.get("uri") or s["spotifyId"]},
            }
    return {"rounds": rounds}


def build_catalog(season_datas):
    """Every track ever submitted, for the repeat checker (site/repeats.html;
    README, Repeat checker), so it can search artists, songs and albums on
    a phone without fetching the ~1MB season files. Rounds are listed once,
    oldest first, and each track points at its round by position."""
    rounds, tracks = [], []
    for d in season_datas:
        for n, r in enumerate(d["rounds"], 1):
            rounds.append({"season": d["key"], "seasonLabel": d["label"], "number": n,
                           "name": r["name"], "id": r["id"]})
            for s in r["songs"]:
                tracks.append(with_link({"title": s["title"], "artists": s["artists"], "album": s["album"],
                                         "round": len(rounds) - 1, "submitterName": s["submitterName"],
                                         "place": s.get("place"), "spotifyId": s["spotifyId"], "art": s.get("art")}, s))
    return {"rounds": rounds, "tracks": tracks}


def active_players(data):
    """The players taking part now: everyone with a track in the season's
    latest round, by name. The Submit page and the Home banner count site
    submissions out of these (the user's "20 eligible players", 2026-10-23,
    which is exactly Round 6's submitters); someone who sat that round out
    counts again once they play another."""
    if not data["rounds"]:
        return []
    players = {s["submitterId"]: {"id": s["submitterId"], "name": s["submitterName"]}
               for s in data["rounds"][-1]["songs"] if s["submitterId"]}
    return sorted(players.values(), key=lambda p: p["name"].lower())


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    folders = season_folders()
    if not folders:
        raise SystemExit("No data/seasonN folders found.")

    template_path = OUT_DIR.parent / "season.template.html"
    template = template_path.read_text(encoding="utf-8") if template_path.exists() else None

    index = []
    season_datas = []
    raw_seasons = []
    translations = load_translations()
    translated = set()
    for folder in folders:
        num = int(re.search(r"\d+", folder.name).group())
        key = f"season{num}"
        label = season_label(folder, num)
        data, raw = build_season(folder, key, label, translations)
        translated |= raw["translated"]
        season_datas.append(data)
        # tag each comment with the season it came from, so a career
        # superlative can say which season it happened in
        for entries in raw["voterComments"].values():
            for e in entries:
                e["seasonLabel"] = label
        raw_seasons.append(raw)
        with open(OUT_DIR / f"{key}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

        leader = data["standings"][0] if data["standings"] else None
        index.append({
            "key": key,
            "label": label,
            "roundCount": len(data["rounds"]),
            "songCount": data["songCount"],
            "playerCount": len(data["competitors"]),
            "leaderName": leader["name"] if leader else None,
            # everyone sharing first place, in standings order
            "leaderNames": [p["name"] for p in data["standings"] if p["rank"] == 1],
            "leaderPoints": leader["points"] if leader else None,
            "startedAt": data["startedAt"],
            "liveRound": data["liveRound"],
            "activePlayers": active_players(data),
        })

        if template:
            page = (template
                     .replace("{{TITLE}}", f"PFML - {label}")
                     .replace("{{SEASON_KEY}}", key)
                     .replace("{{LABEL}}", label))
            (OUT_DIR.parent / f"{key}.html").write_text(page, encoding="utf-8")

        scoring = sum(len(s["votes"]) for r in data["rounds"] for s in r["songs"])
        print(f"{key}: {len(data['rounds'])} rounds, {data['songCount']} songs, {scoring} scoring votes")

    # an id that matches no comment is a typo, and its English would never show
    unmatched = sorted(set(translations) - translated)
    if unmatched:
        print(f"  ! {TRANSLATIONS_FILE}: no comment or note has the id {', '.join(unmatched)}")

    # The newest season is the current one: the home page marks it live and
    # the season button names it (README, The "live" season).
    current = index[-1]["key"]
    with open(OUT_DIR / "index.json", "w", encoding="utf-8") as f:
        json.dump({"seasons": index, "currentSeason": current}, f, ensure_ascii=False, separators=(",", ":"))
    print(f"index.json: {len(index)} seasons, current {current}")

    career = build_career(season_datas, raw_seasons)
    with open(OUT_DIR / "career.json", "w", encoding="utf-8") as f:
        json.dump(career, f, ensure_ascii=False, separators=(",", ":"))
    print(f"career.json: {len(career['players'])} players across {len(career['seasons'])} played seasons")

    profiles = build_profiles(season_datas)
    with open(OUT_DIR / "profiles.json", "w", encoding="utf-8") as f:
        json.dump(profiles, f, ensure_ascii=False, separators=(",", ":"))
    lookup = build_lookup(season_datas)
    with open(OUT_DIR / "lookup.json", "w", encoding="utf-8") as f:
        json.dump(lookup, f, ensure_ascii=False, separators=(",", ":"))
    catalog = build_catalog(season_datas)
    with open(OUT_DIR / "catalog.json", "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, separators=(",", ":"))
    vault = build_vault(season_datas)
    with open(OUT_DIR / "vault.json", "w", encoding="utf-8") as f:
        json.dump(vault, f, ensure_ascii=False, separators=(",", ":"))
    print(f"profiles.json: {len(profiles['players'])} players; lookup.json: {len(lookup['rounds'])} rounds; "
          f"catalog.json: {len(catalog['tracks'])} tracks; vault.json: {len(vault['winners'])} winners")


if __name__ == "__main__":
    main()
