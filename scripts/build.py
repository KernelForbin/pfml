#!/usr/bin/env python3
"""
PFML build step.

Reads the raw Music League CSV exports from data/season*/ and writes the
JSON the site loads from site/data/. Re-run after every fresh export; the
GitHub Action does this automatically on push.

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
    zero-point row in both seasons carries a comment. They are counted as
    commentary, never as scoring.
  - Self-voting is blocked. The only rows where voter == submitter are
    zero-point comments on your own track.
  - Season 1 allowed negative points (35 downvotes, -5 to -1). Season 2
    did not. Downvotes net against the same budget.

Because the budget is fixed, "average points given" is not a measure of
generosity: everyone gives exactly the same budget a round. The stats
below measure where a voter puts their points instead.
"""
import csv
import json
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "site" / "data"

# minimum chances-to-vote before a voter/submitter pair is shown in the
# taste matrix, so one lucky round does not read as a lifelong grudge
MIN_PAIR_OPPORTUNITIES = 5

# Same guard for the comment matrix. It's the same denominator (chances to
# vote on that submitter's tracks), so a pair below this threshold is
# hidden there too rather than reading a single round as a habit.
MIN_COMMENT_PAIR_OPPORTUNITIES = MIN_PAIR_OPPORTUNITIES

# Vocabulary richness is measured on fixed-size chunks of this many words
# (see sampled_richness). 500 sits below the smallest real corpus in the
# data (813 words), so everyone who clears one chunk is compared on the
# same amount of text.
VOCAB_SAMPLE_WORDS = 500

# Minimum comments before someone is eligible for a comment superlative or
# a rate-based stat. Rates over two or three comments are noise: one
# exclamation mark would read as a 33% exclamation rate.
MIN_COMMENTS_FOR_RATES = 10

# Career Score = total points + WIN_BONUS per round won + PODIUM_BONUS per
# podium finish (podiums include the win itself). See build_career() for
# where these numbers come from.
WIN_BONUS = 10
PODIUM_BONUS = 5

# Optional, produced by scripts/enrich_comments.py, never by this build.
# Absent is the normal case: the site just omits sentiment-based stats.
SENTIMENT_PATH = DATA_DIR / "comment_sentiment.json"

# The sentiment labels the site knows how to render. A label outside this
# set in comment_sentiment.json is ignored rather than rendered blindly,
# so a change to the enrichment prompt can't inject arbitrary keys here.
SENTIMENT_LABELS = ("witty", "funny", "rude", "appreciative", "storytelling", "analytical")

# Deliberately small and hand-written: a dependency-free stopword list for
# picking out someone's distinctive recurring word. Covers English
# function words plus the handful of words that dominate *every* Music
# League comment ("song", "track", "love") and would otherwise be the top
# word for all 16 players, telling you nothing about any of them.
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
    """SHOUTING, not "I" or "A" or "OK". Two letters minimum, and it has to
    have an uppercase letter to begin with, so "a" never qualifies."""
    return len(w) >= 3 and w.isupper() and w.isalpha()


def comment_id(round_id, uri, voter_id):
    """Stable id for a single voter comment, matching the key
    scripts/enrich_comments.py writes into data/comment_sentiment.json.
    Round + track + voter is unique: a voter gets one vote row per track
    per round."""
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
        out[cid] = {"labels": labels, "rationale": (entry.get("rationale") or "").strip()}
    return out


# Season 3 rule: once per season, a submitter can ask in their own note on
# a submission to have that track's points doubled toward their total. Which
# notes are real requests is a judgement about intent (a note can mention the
# prop without invoking it), so nothing here parses notes. The decisions are
# made by reading them and recorded by hand in data/seasonN/daily_doubles.json;
# this build only applies what that file says, and only where it exists.
DAILY_DOUBLE_FILE = "daily_doubles.json"


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
    requests = raw.get("requests", [])
    return {
        "reviewed": {r["roundId"] for r in raw.get("reviewedRounds", []) if r.get("roundId")},
        "accepted": [r for r in requests if r.get("decision") == "accepted"],
    }


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
    """spotify:track:XXXX -> XXXX"""
    if not uri:
        return None
    parts = uri.split(":")
    return parts[-1] if len(parts) == 3 and parts[1] == "track" else None


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

    The four style rates (exclamation, question, ALL-CAPS, emoji) are all
    the *share of that player's comments containing at least one*, not a
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
        "emojiRate": containing(lambda t: EMOJI_RE.search(t) is not None),
        # unique words / total words, lowercased. Type-token ratio falls as
        # a body of text grows, so this is only comparable between players
        # with a similar number of comments; the page guards it with
        # MIN_COMMENTS_FOR_RATES and the README says so.
        # Raw unique/total. Kept because it's the number people expect to
        # see, but it is NOT comparable between players: it falls as a
        # corpus grows. Nothing ranks on it; vocabRichnessSampled does.
        "vocabRichness": round(len(set(all_words)) / total_words, 3) if total_words else 0,
        "vocabRichnessSampled": sampled_richness(all_words),
        "uniqueWords": len(set(all_words)),
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


def build_season(folder: Path, season_key: str, label: str):
    competitor_rows = read_csv(folder / "competitors.csv")
    round_rows = read_csv(folder / "rounds.csv")
    sub_rows = read_csv(folder / "submissions.csv")
    vote_rows = read_csv(folder / "votes.csv")

    names = {r["ID"]: r["Name"] for r in competitor_rows}

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
            comments_at.setdefault((v["Round ID"], v["Spotify URI"]), []).append(
                {"voterId": v["Voter ID"], "voterName": names.get(v["Voter ID"], "Unknown"),
                 "points": int(v["Points Assigned"]), "comment": v["Comment"].strip()}
            )
        voters_in_round.setdefault(v["Round ID"], set()).add(v["Voter ID"])

    # accumulators
    player = {cid: {"id": cid, "name": name, "points": 0, "votePoints": 0, "submissions": 0,
                     "roundsWon": 0, "bestFinish": None, "podiums": 0}
              for cid, name in names.items()}
    voter = {cid: {"id": cid, "name": name, "roundsVoted": 0, "pointsSpent": 0,
                    "tracksBackedTotal": 0, "topBets": [], "kingmakerHits": 0,
                    "kingmakerRounds": 0, "commentsLeft": 0}
             for cid, name in names.items()}
    pair_points = {}        # (voter, submitter) -> points given
    pair_chances = {}       # (voter, submitter) -> tracks they could have voted on
    pair_comments = {}      # (voter, submitter) -> comments left on their tracks
    voter_total_points = {}
    voter_total_chances = {}
    # every voter comment with the context the page needs to show it
    voter_comments = {cid: [] for cid in names}
    vote_rows_by_voter = {}

    # lookups so a comment can name the track and round it was left on
    round_name_by_id = {r["ID"]: r.get("Name", "") for r in round_rows}
    sub_by_key = {(r["Round ID"], r["Spotify URI"]): r for r in sub_rows}

    sentiment = load_sentiment()

    for v in vote_rows:
        vid = v["Voter ID"]
        vote_rows_by_voter[vid] = vote_rows_by_voter.get(vid, 0) + 1
        text = v.get("Comment", "").strip()
        if not text or vid not in voter:
            continue
        voter[vid]["commentsLeft"] += 1
        sub = sub_by_key.get((v["Round ID"], v["Spotify URI"]))
        cid = comment_id(v["Round ID"], v["Spotify URI"], vid)
        entry = {
            "id": cid,
            "text": text,
            "points": int(v["Points Assigned"]),
            "roundId": v["Round ID"],
            "roundName": round_name_by_id.get(v["Round ID"], ""),
            "trackTitle": sub.get("Title", "") if sub else "",
            "trackArtist": sub.get("Artist(s)", "") if sub else "",
            "spotifyId": track_id(v["Spotify URI"]),
            "submitterId": sub.get("Submitter ID") if sub else None,
        }
        # Only ever attached when enrich_comments.py has actually labelled
        # this exact comment; never inferred here.
        if cid in sentiment:
            entry["sentiment"] = sentiment[cid]
        voter_comments[vid].append(entry)

    rounds_out = []
    all_songs = []
    scoring_votes = 0
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
                scoring_votes += 1
                if pts < 0:
                    downvotes += 1
                received.append({"voterId": vid, "voterName": names.get(vid, "Unknown"), "points": pts})

            total = sum(r["points"] for r in received)
            artists = split_artists(s["Artist(s)"])
            received.sort(key=lambda r: r["points"], reverse=True)

            song = {
                "spotifyId": track_id(uri),
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
                "topVote": received[0]["points"] if received else 0,
                "spread": round(statistics.pstdev([r["points"] for r in received]), 2) if len(received) > 1 else 0,
                "comments": comments_at.get((rid, uri), []),
            }
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
                        "spotifyId": track_id(uri), "basePoints": total, "bonus": bonus,
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
        for i, s in enumerate(songs):
            if s["points"] != last_points:
                rank = i + 1
                last_points = s["points"]
            s["place"] = rank
            pid = s["submitterId"]
            if pid in player:
                if rank == 1:
                    player[pid]["roundsWon"] += 1
                if rank <= 3:
                    player[pid]["podiums"] += 1
                cur = player[pid]["bestFinish"]
                player[pid]["bestFinish"] = rank if cur is None else min(cur, rank)

        winning_uris = {s["spotifyId"] for s in songs if s.get("place") == 1}

        # voter behaviour for this round
        for vid in electorate:
            spent = 0
            backed = 0
            top_bet = 0
            top_uris = []
            for s in round_subs:
                pts = points_at.get((rid, s["Spotify URI"], vid))
                if pts is None or pts <= 0:
                    continue
                spent += pts
                backed += 1
                if pts > top_bet:
                    top_bet = pts
                    top_uris = [track_id(s["Spotify URI"])]
                elif pts == top_bet:
                    top_uris.append(track_id(s["Spotify URI"]))
            if vid in voter and backed:
                voter[vid]["roundsVoted"] += 1
                voter[vid]["pointsSpent"] += spent
                voter[vid]["tracksBackedTotal"] += backed
                voter[vid]["topBets"].append(top_bet)
                voter[vid]["kingmakerRounds"] += 1
                if any(u in winning_uris for u in top_uris):
                    voter[vid]["kingmakerHits"] += 1

            # pair-level: every track they could have scored counts, whether
            # or not they scored it, so a zero is real information
            for s in round_subs:
                submitter = s["Submitter ID"]
                if submitter == vid:
                    continue
                pts = points_at.get((rid, s["Spotify URI"], vid), 0)
                pts = max(pts, 0) if pts < 0 else pts
                pair_points[(vid, submitter)] = pair_points.get((vid, submitter), 0) + pts
                pair_chances[(vid, submitter)] = pair_chances.get((vid, submitter), 0) + 1
                voter_total_points[vid] = voter_total_points.get(vid, 0) + pts
                voter_total_chances[vid] = voter_total_chances.get(vid, 0) + 1
                # same denominator as the taste index above: a "chance" is
                # one of that submitter's tracks this voter could have
                # voted on. Here we count how often they said something.
                if (rid, s["Spotify URI"], vid) in comments_by_vote:
                    pair_comments[(vid, submitter)] = pair_comments.get((vid, submitter), 0) + 1

        margin = (songs[0]["points"] - songs[1]["points"]) if len(songs) > 1 else None
        rounds_out.append({
            "id": rid,
            "name": rnd["Name"],
            "description": rnd.get("Description", "").strip(),
            "created": rnd.get("Created", ""),
            "playlistUrl": rnd.get("Playlist URL", "").strip(),
            "playlistId": playlist_id(rnd.get("Playlist URL", "")),
            "songs": songs,
            "margin": margin,
            "voterCount": len(electorate),
            "submissionCount": len(round_subs),
            # Music League's export has no explicit phase field. A voter
            # only appears in votes.csv for a round once voting has opened
            # for it (even a zero-point comment-only row means they were
            # able to vote), so "someone has a vote row for this round" is
            # the best available signal that it left song-selection and
            # entered voting. This is an inference, not a fact the export
            # states outright.
            "hasVotingActivity": len(electorate) > 0,
        })

    # ---- standings ----
    standings = [p for p in player.values() if p["submissions"] > 0]
    standings.sort(key=lambda p: (-p["points"], -p["roundsWon"], p["name"]))
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
    # rounds.csv. liveRound describes whichever round was created most
    # recently, on the assumption that's the one currently in play; its
    # "phase" is the hasVotingActivity heuristic explained above, not a
    # field the export provides directly.
    started_at = rounds_out[0]["created"] if rounds_out else None
    live_round = None
    if rounds_out:
        latest = rounds_out[-1]
        live_round = {
            "number": len(rounds_out),
            "name": latest["name"],
            "submissionCount": latest["submissionCount"],
            "phase": "Voting" if latest["hasVotingActivity"] else "Song Selection",
        }

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

    # ---- taste index ----
    # share of a voter's points that went to one submitter, divided by the
    # share you'd expect if they spread points evenly across every track
    # they saw. 1.00 is neutral. 2.00 is twice their baseline.
    taste = []
    for (vid, sid), pts in pair_points.items():
        chances = pair_chances[(vid, sid)]
        if chances < MIN_PAIR_OPPORTUNITIES:
            continue
        vtp = voter_total_points.get(vid, 0)
        vtc = voter_total_chances.get(vid, 0)
        if not vtp or not vtc:
            continue
        actual_share = pts / vtp
        expected_share = chances / vtc
        taste.append({
            "voterId": vid,
            "voterName": names.get(vid, "Unknown"),
            "submitterId": sid,
            "submitterName": names.get(sid, "Unknown"),
            "index": round(actual_share / expected_share, 2) if expected_share else 0,
            "points": pts,
            "chances": chances,
        })

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
        stats["voteRows"] = vote_row_count
        # share of this player's vote rows that carried a comment. The
        # denominator is every row they filed, including the zero-point
        # rows that exist *only* to carry a comment.
        stats["commentRate"] = round(len(entries) / vote_row_count, 3) if vote_row_count else 0
        player_words = [w for e in entries for w in comment_words(e["text"])]
        stats["distinctiveWord"] = (
            distinctive_word(player_words, league_word_counts, league_word_total)
            if len(entries) >= MIN_COMMENTS_FOR_RATES else None
        )
        if entries:
            longest = max(entries, key=lambda e: (len(comment_words(e["text"])), len(e["text"])))
            stats["longest"] = {
                "text": longest["text"],
                "words": len(comment_words(longest["text"])),
                "chars": len(longest["text"]),
                "roundName": longest["roundName"],
                "trackTitle": longest["trackTitle"],
                "trackArtist": longest["trackArtist"],
                "spotifyId": longest["spotifyId"],
                "points": longest["points"],
            }
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
            "spotifyId": track_id(r["Spotify URI"]),
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
            "minPairOpportunities": MIN_COMMENT_PAIR_OPPORTUNITIES,
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
            chattiest = max(eligible, key=lambda c: c["commentRate"])
            comment_summary["chattiest"] = {"name": chattiest["name"], "rate": chattiest["commentRate"],
                                            "comments": chattiest["comments"]}
            quietest = min(eligible, key=lambda c: c["commentRate"])
            comment_summary["quietest"] = {"name": quietest["name"], "rate": quietest["commentRate"],
                                           "comments": quietest["comments"]}
            wordiest = max(eligible, key=lambda c: c["meanWords"])
            comment_summary["wordiest"] = {"name": wordiest["name"], "meanWords": wordiest["meanWords"]}
            tersest = min(eligible, key=lambda c: c["meanWords"])
            comment_summary["tersest"] = {"name": tersest["name"], "meanWords": tersest["meanWords"]}
            loudest = max(eligible, key=lambda c: c["allCapsRate"])
            if loudest["allCapsRate"] > 0:
                comment_summary["loudest"] = {"name": loudest["name"], "rate": loudest["allCapsRate"]}
            sampled = [c for c in eligible if c.get("vocabRichnessSampled") is not None]
            if sampled:
                richest = max(sampled, key=lambda c: c["vocabRichnessSampled"])
                comment_summary["richestVocab"] = {"name": richest["name"],
                                                   "richness": richest["vocabRichnessSampled"],
                                                   "comments": richest["comments"],
                                                   "sampleWords": VOCAB_SAMPLE_WORDS}
            most_zero = max(eligible, key=lambda c: c["zeroPointComments"])
            if most_zero["zeroPointComments"] > 0:
                comment_summary["mostZeroPoint"] = {"name": most_zero["name"],
                                                    "count": most_zero["zeroPointComments"]}
        if comment_pairs:
            warmest = max(comment_pairs, key=lambda p: (p["rate"], p["chances"]))
            comment_summary["mostTalkedAt"] = warmest
            silent = min(comment_pairs, key=lambda p: (p["rate"], -p["chances"]))
            comment_summary["silentTreatment"] = silent

    # ---- highlights ----
    highlights = {}
    if all_songs:
        top = max(all_songs, key=lambda s: s["points"])
        highlights["topTrack"] = {k: top[k] for k in
                                  ("title", "artistText", "album", "submitterName", "points", "spotifyId", "roundName")}

        contested = [s for s in all_songs if s["backers"] >= 3]
        if contested:
            divisive = max(contested, key=lambda s: s["spread"])
            highlights["divisiveTrack"] = {k: divisive[k] for k in
                                           ("title", "artistText", "submitterName", "spread", "spotifyId", "roundName")}

        shut_out = [s for s in all_songs if s["points"] <= 0]
        highlights["shutOutCount"] = len(shut_out)

        decided = [r for r in rounds_out if r["margin"] is not None]
        if decided:
            closest = min(decided, key=lambda r: r["margin"])
            blowout = max(decided, key=lambda r: r["margin"])
            highlights["closestRound"] = {"name": closest["name"], "margin": closest["margin"]}
            highlights["blowoutRound"] = {"name": blowout["name"], "margin": blowout["margin"],
                                          "winner": blowout["songs"][0]["submitterName"],
                                          "title": blowout["songs"][0]["title"]}

        if taste:
            biggest_fan = max(taste, key=lambda t: t["index"])
            coldest = min(taste, key=lambda t: t["index"])
            highlights["biggestFan"] = biggest_fan
            highlights["coldestShoulder"] = coldest

        if voters_out:
            highlights["boldestVoter"] = max(voters_out, key=lambda v: v["avgTopBet"])
            highlights["hedgiestVoter"] = max(voters_out, key=lambda v: v["avgTracksBacked"])
            eligible = [v for v in voters_out if v["kingmakerRounds"] >= 5]
            if eligible:
                highlights["bestTastemaker"] = max(eligible, key=lambda v: v["kingmakerRate"])

        artist_counts = {}
        for s in all_songs:
            for a in s["artists"]:
                entry = artist_counts.setdefault(a, {"name": a, "count": 0, "points": 0})
                entry["count"] += 1
                entry["points"] += s["points"]
        repeats = sorted([a for a in artist_counts.values() if a["count"] > 1],
                         key=lambda a: (-a["count"], -a["points"]))
        highlights["repeatArtists"] = repeats[:10]
        highlights["uniqueArtists"] = len(artist_counts)

        highlights["scoringVotes"] = scoring_votes
        highlights["commentOnlyVotes"] = comment_only_votes
        highlights["downvotes"] = downvotes

    # ---- point budget ----
    # Every voter spends the same fixed budget each round, but it isn't the
    # same number in every season (16 in Seasons 1 and 2, 19 in Season 3),
    # so the page copy can't hard-code it. It's the most common per-voter
    # round total; a voter who only left zero-point comments totals 0 and
    # says nothing about the budget, so those are ignored, and the few
    # Season 1 voter-rounds that total 11 lose the vote to the 16s. Ties
    # take the larger number so the answer never depends on dict order.
    round_totals = {}
    for (rid_, _uri, vid_), pts_ in points_at.items():
        round_totals[(rid_, vid_)] = round_totals.get((rid_, vid_), 0) + pts_
    total_counts = {}
    for t_ in round_totals.values():
        if t_ > 0:
            total_counts[t_] = total_counts.get(t_, 0) + 1
    point_budget = max(total_counts, key=lambda t_: (total_counts[t_], t_)) if total_counts else None

    data = {
        "key": season_key,
        "label": label,
        "competitors": sorted([{"id": cid, "name": n} for cid, n in names.items()], key=lambda c: c["name"]),
        "rounds": rounds_out,
        "standings": standings,
        "voters": voters_out,
        "taste": taste,
        "commenters": commenters,
        "commentPairs": comment_pairs,
        "submitterNotes": submitter_notes,
        "commentSummary": comment_summary,
        "highlights": highlights,
        "songCount": len(all_songs),
        "voteRowCount": len(vote_rows),
        "scoringVoteCount": scoring_votes,
        "pointBudget": point_budget,
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
    }
    return data, raw


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
            slot = by_player.setdefault(cid, {"entries": [], "voteRows": 0, "seasons": 0})
            rows = raw["voteRowsByVoter"].get(cid, 0)
            if not rows:
                continue
            slot["entries"].extend(entries)
            slot["voteRows"] += rows
            slot["seasons"] += 1

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
        stats["voteRows"] = slot["voteRows"]
        stats["seasons"] = slot["seasons"]
        stats["commentRate"] = round(len(entries) / slot["voteRows"], 3)
        player_words = [w for e in entries for w in comment_words(e["text"])]
        stats["distinctiveWord"] = (
            distinctive_word(player_words, league_word_counts, league_word_total)
            if len(entries) >= MIN_COMMENTS_FOR_RATES else None
        )
        if entries:
            longest = max(entries, key=lambda e: (len(comment_words(e["text"])), len(e["text"])))
            stats["longest"] = {
                "text": longest["text"],
                "words": len(comment_words(longest["text"])),
                "chars": len(longest["text"]),
                "roundName": longest["roundName"],
                "trackTitle": longest["trackTitle"],
                "trackArtist": longest["trackArtist"],
                "spotifyId": longest["spotifyId"],
                "points": longest["points"],
                "seasonLabel": longest.get("seasonLabel", ""),
            }
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
        summary["minPairOpportunities"] = MIN_COMMENT_PAIR_OPPORTUNITIES
        summary["hasSentiment"] = any("sentiment" in p for p in players)
        longest_overall = max((p for p in players if p.get("longest")),
                              key=lambda p: p["longest"]["words"], default=None)
        if longest_overall:
            summary["longestComment"] = dict(longest_overall["longest"], name=longest_overall["name"])
        if eligible:
            talkative = max(eligible, key=lambda p: p["commentRate"])
            summary["mostTalkative"] = {"name": talkative["name"], "rate": talkative["commentRate"],
                                        "comments": talkative["comments"]}
            terse = min(eligible, key=lambda p: p["meanWords"])
            summary["mostTerse"] = {"name": terse["name"], "meanWords": terse["meanWords"],
                                    "comments": terse["comments"]}
            wordiest = max(eligible, key=lambda p: p["meanWords"])
            summary["wordiest"] = {"name": wordiest["name"], "meanWords": wordiest["meanWords"]}
            quietest = min(eligible, key=lambda p: p["commentRate"])
            summary["quietest"] = {"name": quietest["name"], "rate": quietest["commentRate"],
                                   "comments": quietest["comments"]}
            sampled = [p for p in eligible if p.get("vocabRichnessSampled") is not None]
            if sampled:
                richest = max(sampled, key=lambda p: p["vocabRichnessSampled"])
                summary["richestVocab"] = {"name": richest["name"],
                                           "richness": richest["vocabRichnessSampled"],
                                           "comments": richest["comments"],
                                           "sampleWords": VOCAB_SAMPLE_WORDS}
            loudest = max(eligible, key=lambda p: p["allCapsRate"])
            if loudest["allCapsRate"] > 0:
                summary["loudest"] = {"name": loudest["name"], "rate": loudest["allCapsRate"]}
            zero = max(eligible, key=lambda p: p["zeroPointComments"])
            if zero["zeroPointComments"] > 0:
                summary["mostZeroPoint"] = {"name": zero["name"], "count": zero["zeroPointComments"]}
        if pairs:
            # "silent treatment": the pair with the lowest comment rate over
            # the most chances, i.e. the person you've had every chance to
            # say something to and never have.
            silent = min(pairs, key=lambda p: (p["rate"], -p["chances"]))
            summary["silentTreatment"] = silent
            chatty = max(pairs, key=lambda p: (p["rate"], p["chances"]))
            summary["mostTalkedAt"] = chatty
        if notes:
            noter = max(notes.items(), key=lambda kv: len(kv[1]))
            summary["mostSubmitterNotes"] = {
                "name": names.get(noter[0], "Unknown"),
                "notes": len(noter[1]),
                "submissions": subs.get(noter[0], 0),
            }
            summary["submitterNoteCount"] = sum(len(v) for v in notes.values())

    return {"players": players, "pairs": pairs, "summary": summary}


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
                "roundsWon": 0, "podiums": 0, "submissions": 0,
                "seasonsPlayed": 0, "bySeasson": {}, "bestSeasonPoints": None, "bestSeasonKey": None,
            })
            t["totalPoints"] += p["points"]
            t["roundsWon"] += p["roundsWon"]
            t["podiums"] += p["podiums"]
            t["submissions"] += p["submissions"]
            t["seasonsPlayed"] += 1
            t["bySeasson"][d["key"]] = p["points"]
            if t["bestSeasonPoints"] is None or p["points"] > t["bestSeasonPoints"]:
                t["bestSeasonPoints"] = p["points"]
                t["bestSeasonKey"] = d["key"]

    players = []
    for t in totals.values():
        t["avgPointsPerSeason"] = round(t["totalPoints"] / t["seasonsPlayed"], 1) if t["seasonsPlayed"] else 0
        t["bySeason"] = t.pop("bySeasson")
        # Career Score = total points + a bonus for rounds won + a bonus for
        # podium finishes. The weights aren't arbitrary: across the real
        # data, a round winner scores about 10 points above the field
        # average (26.0 vs 15.8 in Season 1, 25.6 vs 15.7 in Season 2), and
        # a podium finisher scores about 7-8 points above average. WIN_BONUS
        # and PODIUM_BONUS below round those premiums to 10 and 5. Podiums
        # already include the win itself (a round win is a podium finish
        # too), so a win earns both bonuses: +15 on top of its raw points.
        t["careerScore"] = t["totalPoints"] + WIN_BONUS * t["roundsWon"] + PODIUM_BONUS * t["podiums"]
        players.append(t)
    players.sort(key=lambda p: (-p["careerScore"], -p["totalPoints"], p["name"]))

    highlights = {}
    if players:
        top_score = players[0]
        highlights["topScore"] = {"name": top_score["name"], "careerScore": top_score["careerScore"]}
        most_wins = max(players, key=lambda p: p["roundsWon"])
        highlights["mostWins"] = {"name": most_wins["name"], "roundsWon": most_wins["roundsWon"]}
        most_podiums = max(players, key=lambda p: p["podiums"])
        highlights["mostPodiums"] = {"name": most_podiums["name"], "podiums": most_podiums["podiums"]}
        best_single = max(players, key=lambda p: p["bestSeasonPoints"])
        season_label = next((d["label"] for d in season_datas if d["key"] == best_single["bestSeasonKey"]), "")
        highlights["bestSingleSeason"] = {"name": best_single["name"], "points": best_single["bestSeasonPoints"],
                                          "season": season_label}

    comments = build_career_comments(raw_seasons or [])

    return {
        "players": players,
        "highlights": highlights,
        "seasons": [{"key": d["key"], "label": d["label"]} for d in played_seasons],
        "totalSeasons": len(played_seasons),
        "careerScoreFormula": {"winBonus": WIN_BONUS, "podiumBonus": PODIUM_BONUS},
        "commenters": comments["players"],
        "commentSummary": comments["summary"],
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    folders = sorted(
        [p for p in DATA_DIR.iterdir() if p.is_dir() and re.fullmatch(r"season\d+", p.name)],
        key=lambda p: int(re.search(r"\d+", p.name).group()),
    )
    if not folders:
        raise SystemExit("No data/seasonN folders found.")

    template_path = OUT_DIR.parent / "season.template.html"
    template = template_path.read_text(encoding="utf-8") if template_path.exists() else None

    index = []
    season_datas = []
    raw_seasons = []
    for folder in folders:
        num = int(re.search(r"\d+", folder.name).group())
        key = f"season{num}"
        label = f"Season {num}"
        data, raw = build_season(folder, key, label)
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
            "leaderPoints": leader["points"] if leader else None,
            "startedAt": data["startedAt"],
            "liveRound": data["liveRound"],
        })

        if template:
            page = (template
                     .replace("{{TITLE}}", f"PFML - {label}")
                     .replace("{{SEASON_KEY}}", key)
                     .replace("{{LABEL}}", label))
            (OUT_DIR.parent / f"{key}.html").write_text(page, encoding="utf-8")

        print(f"{key}: {len(data['rounds'])} rounds, {data['songCount']} songs, "
              f"{data['scoringVoteCount']} scoring votes")

    # newest season with any rounds is the default tab; if none have rounds,
    # fall back to the newest season overall
    with_rounds = [s for s in index if s["roundCount"] > 0]
    default_key = (with_rounds or index)[-1]["key"]
    # if the newest season has started at all, prefer it
    if index[-1]["roundCount"] > 0:
        default_key = index[-1]["key"]

    with open(OUT_DIR / "index.json", "w", encoding="utf-8") as f:
        json.dump({"seasons": index, "defaultSeason": default_key,
                   "currentSeason": index[-1]["key"]}, f, ensure_ascii=False, separators=(",", ":"))
    print(f"index.json: {len(index)} seasons, default {default_key}")

    career = build_career(season_datas, raw_seasons)
    with open(OUT_DIR / "career.json", "w", encoding="utf-8") as f:
        json.dump(career, f, ensure_ascii=False, separators=(",", ":"))
    print(f"career.json: {len(career['players'])} players across {career['totalSeasons']} played seasons")


if __name__ == "__main__":
    main()
