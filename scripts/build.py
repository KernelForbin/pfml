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
  - Each voter gets a fixed 16-point budget per round to spread across
    other people's tracks. A handful of Season 1 voter-rounds total 11
    instead of 16.
  - A votes.csv row with 0 points is a comment, not a vote. Every single
    zero-point row in both seasons carries a comment. They are counted as
    commentary, never as scoring.
  - Self-voting is blocked. The only rows where voter == submitter are
    zero-point comments on your own track.
  - Season 1 allowed negative points (35 downvotes, -5 to -1). Season 2
    did not. Downvotes net against the same 16-point budget.

Because the budget is fixed, "average points given" is not a measure of
generosity: everyone gives exactly 16 a round. The stats below measure
where a voter puts their 16 instead.
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

# Career Score = total points + WIN_BONUS per round won + PODIUM_BONUS per
# podium finish (podiums include the win itself). See build_career() for
# where these numbers come from.
WIN_BONUS = 10
PODIUM_BONUS = 5


def read_csv(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


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
    voters_in_round = {}
    for v in vote_rows:
        key = (v["Round ID"], v["Spotify URI"], v["Voter ID"])
        points_at[key] = int(v["Points Assigned"])
        if v.get("Comment", "").strip():
            comments_at.setdefault((v["Round ID"], v["Spotify URI"]), []).append(
                {"voterId": v["Voter ID"], "voterName": names.get(v["Voter ID"], "Unknown"),
                 "points": int(v["Points Assigned"]), "comment": v["Comment"].strip()}
            )
        voters_in_round.setdefault(v["Round ID"], set()).add(v["Voter ID"])

    # accumulators
    player = {cid: {"id": cid, "name": name, "points": 0, "submissions": 0,
                     "roundsWon": 0, "bestFinish": None, "podiums": 0}
              for cid, name in names.items()}
    voter = {cid: {"id": cid, "name": name, "roundsVoted": 0, "pointsSpent": 0,
                    "tracksBackedTotal": 0, "topBets": [], "kingmakerHits": 0,
                    "kingmakerRounds": 0, "commentsLeft": 0}
             for cid, name in names.items()}
    pair_points = {}        # (voter, submitter) -> points given
    pair_chances = {}       # (voter, submitter) -> tracks they could have voted on
    voter_total_points = {}
    voter_total_chances = {}

    for v in vote_rows:
        if v.get("Comment", "").strip() and v["Voter ID"] in voter:
            voter[v["Voter ID"]]["commentsLeft"] += 1

    rounds_out = []
    all_songs = []
    scoring_votes = 0
    comment_only_votes = 0
    downvotes = 0

    for rnd in sorted(round_rows, key=lambda r: r.get("Created", "")):
        rid = rnd["ID"]
        round_subs = subs_by_round.get(rid, [])
        electorate = voters_in_round.get(rid, set())

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

            if submitter in player:
                player[submitter]["points"] += total
                player[submitter]["submissions"] += 1

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
        p["avgPerSubmission"] = round(p["points"] / p["submissions"], 1)

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

    return {
        "key": season_key,
        "label": label,
        "competitors": sorted([{"id": cid, "name": n} for cid, n in names.items()], key=lambda c: c["name"]),
        "rounds": rounds_out,
        "standings": standings,
        "voters": voters_out,
        "taste": taste,
        "highlights": highlights,
        "songCount": len(all_songs),
        "voteRowCount": len(vote_rows),
        "scoringVoteCount": scoring_votes,
        "startedAt": started_at,
        "liveRound": live_round,
    }


def build_career(season_datas):
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

    return {
        "players": players,
        "highlights": highlights,
        "seasons": [{"key": d["key"], "label": d["label"]} for d in played_seasons],
        "totalSeasons": len(played_seasons),
        "careerScoreFormula": {"winBonus": WIN_BONUS, "podiumBonus": PODIUM_BONUS},
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
    for folder in folders:
        num = int(re.search(r"\d+", folder.name).group())
        key = f"season{num}"
        label = f"Season {num}"
        data = build_season(folder, key, label)
        season_datas.append(data)
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

    career = build_career(season_datas)
    with open(OUT_DIR / "career.json", "w", encoding="utf-8") as f:
        json.dump(career, f, ensure_ascii=False, separators=(",", ":"))
    print(f"career.json: {len(career['players'])} players across {career['totalSeasons']} played seasons")


if __name__ == "__main__":
    main()
