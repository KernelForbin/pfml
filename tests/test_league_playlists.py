"""scripts/league_playlists.py: the league's own playlists on Home (All
Tracks Submitted, All Podium Tracks, and each season's All Submissions and
Podium Tracks), kept up to date with finished rounds (asked 2026-11-02).

Offline: Spotify is a fake here, and the season is made up and built in a
sandbox. The real API's shapes were measured 2026-11-02 (README, The
league's playlists); the first real run, the same day, was the check."""
import contextlib
import io
import json
import unittest

from support import make_season, quiet, sandbox

import build  # noqa: E402
import league_playlists as lp  # noqa: E402


def pid(name):
    """A made-up 22-character playlist id."""
    return name.ljust(22, "x")


PLAYLISTS = {
    "leagueWide": [
        {"label": "PFML - All Tracks Submitted", "url": f"https://open.spotify.com/playlist/{pid('ALLTRACKS')}?si=1"},
        {"label": "PFML - All Podium Tracks", "url": f"https://open.spotify.com/playlist/{pid('ALLPODIUM')}?si=2"},
    ],
    "seasons": [
        {"season": "Season 1", "items": [
            {"label": "PFML - S1 - All Submissions", "url": f"https://open.spotify.com/playlist/{pid('S1ALL')}"},
            {"label": "PFML - S1 - Podium Tracks", "url": f"https://open.spotify.com/playlist/{pid('S1PODIUM')}"}]},
        {"season": "Season 2", "items": [
            {"label": "PFML - S2 - All Submissions", "url": f"https://open.spotify.com/playlist/{pid('S2ALL')}"},
            {"label": "PFML - S2 - Podium Tracks", "url": f"https://open.spotify.com/playlist/{pid('S2PODIUM')}"}]},
    ],
}

# Round 1's export order isn't its finishing order, and two tie for 3rd:
# t1 6, t2 5, t3 3, t4 3, t5 1. Round 2: t6 2, t7 1.
ROUNDS = [
    {"id": "r1", "name": "First", "created": "2026-01-01T00:00:00Z",
     "subs": [("t3", "p3"), ("t1", "p1"), ("t5", "p1"), ("t2", "p2"), ("t4", "p4")],
     "votes": [("p2", "t1", 6), ("p1", "t2", 5), ("p4", "t3", 3), ("p3", "t4", 3), ("p2", "t5", 1)]},
    {"id": "r2", "name": "Second", "created": "2026-01-08T00:00:00Z",
     "subs": [("t6", "p1"), ("t7", "p2")],
     "votes": [("p2", "t6", 2), ("p1", "t7", 1)]},
]


def track(t):
    return {"type": "track", "id": t, "name": f"Song {t}", "artists": [{"name": f"Artist {t}"}]}


class FakeSpotify:
    """Playlists as lists of tracks, read a page at a time like the real
    one (rows carry "item"), and added to with POST, at the end or at a
    position. `swap` stands in for Spotify keeping another recording than
    the id it was sent."""

    def __init__(self, playlists=None, swap=None, drop=()):
        self.lists = {k: [track(t) for t in v] for k, v in (playlists or {}).items()}
        self.swap, self.drop, self.calls = swap or {}, set(drop), []

    def call(self, method, path, params=None, body=None):
        self.calls.append((method, path, params, body))
        key = path.split("/")[2]
        items = self.lists.setdefault(key, [])
        if method == "GET":
            off, limit = params["offset"], params["limit"]
            nxt = "more" if off + limit < len(items) else None
            return {"items": [{"item": t, "is_local": False} for t in items[off:off + limit]], "next": nxt}
        assert method == "POST", f"only reads and adds: {method} {path}"
        new = []
        for u in body["uris"]:
            t = u.split(":")[-1]
            if t in self.drop:
                continue
            new.append(self.swap.get(t) or track(t))
        at = body.get("position", len(items))
        items[at:at] = new
        return {"snapshot_id": "s"}

    def ids(self, name):
        return [t["id"] for t in self.lists.get(pid(name), [])]


@contextlib.contextmanager
def season(rounds=ROUNDS, playlists=PLAYLISTS, seasons=1):
    """A sandbox with made-up seasons built as publish.py would, and Home's
    playlists file. The newest season gets `rounds`."""
    with sandbox() as root, quiet():
        for n in range(1, seasons + 1):
            make_season(root / "data" / f"season{n}", rounds if n == seasons else ROUNDS[1:])
        build.main()
        (build.OUT_DIR / "playlists.json").write_text(json.dumps(playlists), encoding="utf-8")
        yield root


def run(spotify, **kw):
    log = []
    want = lp.run(spotify=spotify, log=log.append, **kw)
    return want, "\n".join(log)


class WhatGoesWhere(unittest.TestCase):
    def test_every_track_and_the_top_three_go_on_their_four_playlists(self):
        sp = FakeSpotify()
        with season():
            run(sp)
        # every track, round by round, each round in the export's order
        self.assertEqual(sp.ids("ALLTRACKS"), ["t3", "t1", "t5", "t2", "t4", "t6", "t7"])
        self.assertEqual(sp.ids("S1ALL"), ["t3", "t1", "t5", "t2", "t4", "t6", "t7"])
        # the podium by place; a tie at 3rd adds both (the user's call)
        self.assertEqual(sp.ids("S1PODIUM")[:2], ["t1", "t2"])
        self.assertEqual(set(sp.ids("S1PODIUM")[2:4]), {"t3", "t4"})
        self.assertEqual(sp.ids("S1PODIUM")[4:], ["t6", "t7"])
        self.assertNotIn("t5", sp.ids("S1PODIUM"))

    def test_all_podium_tracks_takes_the_newest_round_on_top(self):
        sp = FakeSpotify({pid("ALLPODIUM"): ["old1", "old2"]})
        with season():
            run(sp)
        got = sp.ids("ALLPODIUM")
        self.assertEqual(got[:2], ["t6", "t7"])
        self.assertEqual(got[2:4], ["t1", "t2"])
        self.assertEqual(set(got[4:6]), {"t3", "t4"})
        self.assertEqual(got[6:], ["old1", "old2"], "what was there stays, below")

    def test_the_rest_go_on_the_end(self):
        sp = FakeSpotify({pid("ALLTRACKS"): ["old1"], pid("S1ALL"): ["t3"], pid("S1PODIUM"): ["t1", "t2"]})
        with season():
            run(sp)
        self.assertEqual(sp.ids("ALLTRACKS")[0], "old1")
        self.assertEqual(sp.ids("S1ALL"), ["t3", "t1", "t5", "t2", "t4", "t6", "t7"])
        self.assertEqual(sp.ids("S1PODIUM")[:2], ["t1", "t2"])
        self.assertEqual(sp.ids("S1PODIUM")[-2:], ["t6", "t7"])

    def test_only_the_newest_seasons_own_playlists(self):
        sp = FakeSpotify()
        with season(seasons=2):
            run(sp)
        self.assertEqual(sp.ids("S1ALL"), [], "an older season is left alone")
        self.assertEqual(sp.ids("S2ALL"), ["t3", "t1", "t5", "t2", "t4", "t6", "t7"])

    def test_filling_in_an_older_season_puts_its_podium_on_the_end(self):
        # not on top, above newer seasons' (asked 2026-11-02)
        sp = FakeSpotify({pid("ALLPODIUM"): ["newer1", "newer2"]})
        with season(rounds=ROUNDS[1:] + ROUNDS[:1], seasons=2):
            # season 1 holds just "Second" (t6, t7); season 2 is newest
            _, log = run(sp, season_num=1)
        self.assertEqual(sp.ids("ALLPODIUM"), ["newer1", "newer2", "t6", "t7"])
        self.assertNotIn("(on top)", log)

    def test_an_older_seasons_podium_goes_on_oldest_round_first(self):
        want, _ = lp.plan([("A", [], [("a1", "A1", ("a1", "x"))]), ("B", [], [("b1", "B1", ("b1", "x"))])],
                          {}, newest=False)
        self.assertEqual([r[1] for r in want[lp.ALL_PODIUM]], ["a1", "b1"])
        want, _ = lp.plan([("A", [], [("a1", "A1", ("a1", "x"))]), ("B", [], [("b1", "B1", ("b1", "x"))])], {})
        self.assertEqual([r[1] for r in want[lp.ALL_PODIUM]], ["b1", "a1"], "the newest season: newest first")

    def test_a_season_can_be_named(self):
        sp = FakeSpotify()
        with season(seasons=2):
            run(sp, season_num=1)
        self.assertEqual(sp.ids("S1ALL"), ["t6", "t7"])
        self.assertEqual(sp.ids("S2ALL"), [])


class NeverTwiceNeverRemoved(unittest.TestCase):
    def test_a_rerun_adds_nothing(self):
        sp = FakeSpotify()
        with season():
            run(sp)
            before = {k: list(v) for k, v in sp.lists.items()}
            want, _ = run(sp)
        self.assertEqual(sp.lists, before)
        self.assertEqual(sum(len(v) for v in want.values()), 0)

    def test_a_track_already_there_from_another_season_isnt_added_again(self):
        sp = FakeSpotify({pid("ALLTRACKS"): ["t2"]})
        with season():
            run(sp)
        self.assertEqual(sp.ids("ALLTRACKS").count("t2"), 1)

    def test_a_track_spotify_kept_as_another_recording_counts_as_there(self):
        # measured 2026-11-02: a single went on as a compilation's copy
        other = dict(track("t1"), id="t1-other-copy")
        sp = FakeSpotify(swap={"t1": other})
        with season():
            _, log = run(sp)
            self.assertNotIn("didn't go on", log)
            want, _ = run(sp)
        self.assertEqual(sp.ids("ALLTRACKS").count("t1-other-copy"), 1)
        self.assertNotIn("t1", sp.ids("ALLTRACKS"))
        self.assertEqual(sum(len(v) for v in want.values()), 0, "and a rerun doesn't add it again")

    def test_only_reads_and_adds(self):
        sp = FakeSpotify({pid("S1ALL"): ["stray"]})
        with season():
            run(sp)
        self.assertEqual({c[0] for c in sp.calls}, {"GET", "POST"})
        self.assertIn("stray", sp.ids("S1ALL"))

    def test_a_dry_run_only_reads(self):
        sp = FakeSpotify()
        with season():
            want, log = run(sp, dry_run=True)
        self.assertEqual({c[0] for c in sp.calls}, {"GET"})
        self.assertEqual(len(want[lp.ALL_TRACKS]), 7)
        self.assertIn("Dry run: nothing added.", log)


class WhenSomethingsOff(unittest.TestCase):
    def test_a_track_that_doesnt_go_on_stops_the_run(self):
        sp = FakeSpotify(drop={"t5"})
        with season(), self.assertRaises(SystemExit) as stop:
            run(sp)
        self.assertIn("1 track(s) didn't go on", str(stop.exception))
        self.assertEqual(sp.ids("S1ALL"), [], "nothing after the failed playlist")

    def test_a_playlist_not_linked_yet_is_skipped_and_said(self):
        config = json.loads(json.dumps(PLAYLISTS))
        config["seasons"][0]["items"][1]["url"] = None
        sp = FakeSpotify()
        with season(playlists=config):
            _, log = run(sp)
        self.assertIn('No linked "Podium Tracks" playlist for Season 1', log)
        self.assertEqual(sp.ids("S1PODIUM"), [])
        self.assertEqual(len(sp.ids("ALLPODIUM")), 6)

    def test_a_track_with_no_spotify_copy_is_skipped_and_named(self):
        # a site round's YouTube or SoundCloud pick that has no Spotify copy
        want, skipped = lp.plan([("Second", [(None, "A YouTube pick", ("a", "b"))], [])], {})
        self.assertEqual(skipped, [("Second", "A YouTube pick")])
        self.assertEqual(sum(len(v) for v in want.values()), 0)

    def test_needs_the_built_season(self):
        with sandbox() as root, quiet():
            make_season(root / "data" / "season1", ROUNDS)
            with self.assertRaises(SystemExit) as stop:
                lp.run(spotify=FakeSpotify(), log=lambda *_: None)
        self.assertIn("Run python scripts/publish.py first", str(stop.exception))


class TalkingToSpotify(unittest.TestCase):
    def test_reads_every_page(self):
        sp = FakeSpotify({pid("BIG"): [f"t{i}" for i in range(250)]})
        ids, songs = lp.playlist_items(sp, pid("BIG"))
        self.assertEqual(len(ids), 250)
        self.assertEqual(songs[0], ("song t0", "artist t0"))
        self.assertEqual([c[2]["offset"] for c in sp.calls], [0, 100, 200])

    def test_adds_in_hundreds_keeping_the_order_on_top(self):
        sp = FakeSpotify({pid("BIG"): ["old"]})
        new = [f"n{i}" for i in range(150)]
        lp.add_items(sp, pid("BIG"), new, top=True)
        self.assertEqual(sp.ids("BIG"), new + ["old"])
        self.assertEqual([len(c[3]["uris"]) for c in sp.calls], [100, 50])

    def test_playlists_found_by_their_names_on_home(self):
        found = lp.find_playlists(PLAYLISTS, "Season 2")
        self.assertEqual({k: v[1] for k, v in found.items()},
                         {lp.ALL_TRACKS: pid("ALLTRACKS"), lp.ALL_PODIUM: pid("ALLPODIUM"),
                          lp.SEASON_ALL: pid("S2ALL"), lp.SEASON_PODIUM: pid("S2PODIUM")})


if __name__ == "__main__":
    unittest.main()
