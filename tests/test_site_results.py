"""Rounds voted on pfml.fun in the season stats (README, Site rounds in the
stats): the database's export (as text), publish.py writing it to
data/<season>/site_rounds.json, build.py counting it next to Music League's
CSVs, and the pages linking a YouTube or SoundCloud pick to where it was
submitted. Offline and made up: the players, rounds and tracks here are
invented."""
import json
import re
import unittest
from unittest import mock

from support import ROOT, build, make_season, publish, quiet, sandbox
from test_build import TIE_ROUND
from test_submissions import function, read, schema

SITE = ROOT / "site"
SPOTIFY = "S" * 22          # a Spotify pick
MATCH = "M" * 22            # the YouTube pick's Spotify copy
YT_MATCHED = "Y1aaaaaaaaa"  # a YouTube pick with a Spotify copy
YT_ALONE = "Y2bbbbbbbbb"    # a YouTube pick with none
SC = "artist/song"          # a SoundCloud pick with none

# Ann, Ben and Cat are in the Music League export too; Eve is only on the
# site. Eve doesn't vote, so her track scores 0 of the 6 it earned.
SITE_ROUND = {
    "id": "site-r1", "season_key": "season1", "name": "Round Two: On the Site", "prompt": "Made up.",
    "created_at": "2025-02-01T00:00:00Z", "voting_ended_at": "2025-02-08T00:00:00Z",
    "spotify_playlist": "P" * 22, "point_budget": 5, "nonvoters_keep_points": False,
    "submissions": [
        {"id": "s1", "tag": "A2", "platform": "spotify", "track": SPOTIFY, "title": "Spotify Song", "artist": "Artist One",
         "spotify_match": None, "position": 1, "submitter": "p1"},
        {"id": "s2", "tag": "B3", "platform": "youtube", "track": YT_MATCHED, "title": "Video Song", "artist": "Artist Two",
         "spotify_match": MATCH, "position": 2, "submitter": "p2"},
        {"id": "s3", "tag": "C4", "platform": "soundcloud", "track": SC, "title": "Cloud Song", "artist": "Artist Three",
         "spotify_match": None, "position": 3, "submitter": "p3"},
        {"id": "s4", "tag": "D5", "platform": "youtube", "track": YT_ALONE, "title": "Lonely Video", "artist": "Artist Four",
         "spotify_match": None, "position": 4, "submitter": "p5"},
    ],
    "votes": [
        {"submission": "s2", "voter": "p1", "points": 3, "comment": "", "cast_at": "2025-02-02T00:00:00Z"},
        {"submission": "s3", "voter": "p1", "points": 2, "comment": "great", "cast_at": "2025-02-02T00:00:00Z"},
        {"submission": "s3", "voter": "p2", "points": 4, "comment": "", "cast_at": "2025-02-03T00:00:00Z"},
        {"submission": "s4", "voter": "p2", "points": 1, "comment": "", "cast_at": "2025-02-03T00:00:00Z"},
        {"submission": "s4", "voter": "p3", "points": 5, "comment": "", "cast_at": "2025-02-04T00:00:00Z"},
        {"submission": "s3", "voter": "p3", "points": 0, "comment": "mine, sorry", "cast_at": "2025-02-04T00:00:00Z"},
    ],
}
PLAYERS = {"p1": "Ann", "p2": "Ben", "p3": "Cat", "p5": "Eve"}


def write_site(folder, rounds=(SITE_ROUND,), players=PLAYERS):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / build.SITE_ROUNDS_FILE).write_text(json.dumps({"rounds": list(rounds), "players": players}), encoding="utf-8")


def site_song(data, title):
    return next(s for r in data["rounds"] for s in r["songs"] if s["title"] == title)


class InTheBuild(unittest.TestCase):
    def build(self, with_export=True, rounds=(SITE_ROUND,)):
        with sandbox() as root, quiet():
            folder = root / "data" / "season1"
            if with_export:
                make_season(folder, [TIE_ROUND])
            write_site(folder, rounds)
            data, raw = build.build_season(folder, "season1", "Season 1")
        return data

    def test_a_site_round_joins_the_exports_rounds(self):
        data = self.build()
        self.assertEqual([r["id"] for r in data["rounds"]], ["r1", "site-r1"])
        site = data["rounds"][1]
        self.assertEqual(site["description"], "Made up.")
        self.assertEqual(site["playlistUrl"], "https://open.spotify.com/playlist/" + "P" * 22)
        # Eve, only on the site, joins the season's players
        self.assertIn({"id": "p5", "name": "Eve"}, data["competitors"])

    def test_scores_places_and_standings_count_it(self):
        data = self.build()
        self.assertEqual([(s["title"], s["points"], s["place"]) for s in data["rounds"][1]["songs"]],
                         [("Cloud Song", 6, 1), ("Video Song", 3, 2), ("Spotify Song", 0, 3), ("Lonely Video", 0, 3)])
        cat = next(p for p in data["standings"] if p["id"] == "p3")
        self.assertEqual(cat["roundsWon"], 1)   # the site round; she didn't win Round One

    def test_a_submitter_who_didnt_vote_scores_0(self):
        lonely = site_song(self.build(), "Lonely Video")
        self.assertEqual((lonely["points"], lonely["forfeit"]), (0, {"earned": 6}))
        self.assertEqual(lonely["votes"], [["p3", 5], ["p2", 1]], "the votes still show")
        eve = next(p for p in self.build()["standings"] if p["id"] == "p5")
        self.assertEqual(eve["points"], 0)

    def test_unless_the_round_lets_them_keep_it(self):
        kept = dict(SITE_ROUND, nonvoters_keep_points=True)
        lonely = site_song(self.build(rounds=(kept,)), "Lonely Video")
        self.assertEqual(lonely["points"], 6)
        self.assertNotIn("forfeit", lonely)

    def test_each_track_links_to_where_it_was_submitted(self):
        data = self.build()
        spotify, video, cloud, lonely = (site_song(data, t) for t in ("Spotify Song", "Video Song", "Cloud Song", "Lonely Video"))
        self.assertEqual(spotify["spotifyId"], SPOTIFY)
        self.assertNotIn("link", spotify)
        # the Spotify copy gives album art and repeat checks; the link is the video
        self.assertEqual((video["spotifyId"], video["link"]), (MATCH, {"platform": "youtube", "id": YT_MATCHED}))
        self.assertEqual((cloud["spotifyId"], cloud["link"]), (None, {"platform": "soundcloud", "id": SC}))
        self.assertEqual(lonely["link"], {"platform": "youtube", "id": YT_ALONE})

    def test_a_soundcloud_key_is_never_read_as_a_spotify_id(self):
        self.assertIsNone(build.track_id(build.site_uri("soundcloud", SC)))
        self.assertIsNone(build.track_id(build.site_uri("youtube", YT_ALONE)))
        self.assertEqual(build.track_id(build.site_uri("spotify", SPOTIFY)), SPOTIFY)

    def test_two_tracks_with_no_spotify_copy_arent_one_track(self):
        # Cat's top bet was Eve's video (no Spotify copy); the winner was
        # Cat's own SoundCloud track (none either). Matching on the Spotify
        # id, both were "None", and Cat counted as backing the winner.
        voters = {v["id"]: v for v in self.build(with_export=False)["voters"]}
        self.assertEqual((voters["p3"]["kingmakerHits"], voters["p3"]["kingmakerRounds"]), (0, 1))
        self.assertEqual(voters["p2"]["kingmakerHits"], 1, "Ben's top bet was the winner")

    def test_comments_and_the_comment_lookup(self):
        data = self.build()
        cloud = site_song(data, "Cloud Song")
        self.assertEqual(sorted(c["comment"] for c in cloud["comments"]), ["great", "mine, sorry"])
        self.assertEqual(cloud["comments"][0]["id"], build.comment_id("site-r1", build.site_uri("soundcloud", SC),
                                                                      cloud["comments"][0]["voterId"]))
        lookup = build.build_lookup([dict(data, key="season1", label="Season 1")])
        tracks = lookup["rounds"]["site-r1"]["tracks"]
        self.assertEqual(tracks[build.site_uri("soundcloud", SC)], "Cloud Song")
        self.assertEqual(tracks[build.site_uri("youtube", YT_MATCHED)], "Video Song")
        self.assertEqual(tracks["spotify:track:" + SPOTIFY], "Spotify Song")

    def test_copies_of_a_track_carry_its_link(self):
        data = dict(self.build(), key="season1", label="Season 1")
        catalog = build.build_catalog([data])["tracks"]
        self.assertEqual(next(t for t in catalog if t["title"] == "Cloud Song")["link"]["platform"], "soundcloud")
        vault = build.build_vault([data])["winners"]
        self.assertEqual(next(w for w in vault if w["roundId"] == "site-r1")["link"], {"platform": "soundcloud", "id": SC})
        cat_tracks = build.build_profiles([data])["players"]["p3"]["bestTracks"]
        self.assertEqual(next(t for t in cat_tracks if t["title"] == "Cloud Song")["link"]["id"], SC)

    def test_a_season_played_only_on_the_site(self):
        data = self.build(with_export=False)
        self.assertEqual([r["id"] for r in data["rounds"]], ["site-r1"])
        self.assertEqual(sorted(c["name"] for c in data["competitors"]), ["Ann", "Ben", "Cat", "Eve"])

    def test_a_track_with_no_title_yet_still_builds(self):
        untitled = dict(SITE_ROUND, submissions=[dict(s, title=None) for s in SITE_ROUND["submissions"]])
        titles = sorted(s["title"] for s in self.build(rounds=(untitled,))["rounds"][1]["songs"])
        self.assertEqual(titles, ["SoundCloud track C4", "Spotify track A2", "YouTube track B3", "YouTube track D5"])

    def test_a_season_set_up_on_the_site_keeps_its_name(self):
        with sandbox() as root, quiet():
            folder = root / "data" / "season4"
            write_site(folder)
            self.assertEqual(build.season_label(folder, 4), "Season 4")
            path = folder / build.SITE_ROUNDS_FILE
            saved = json.loads(path.read_text(encoding="utf-8"))
            path.write_text(json.dumps(dict(saved, season_name=" The Summer Season ")), encoding="utf-8")
            self.assertEqual(build.season_label(folder, 4), "The Summer Season")
            path.write_text(json.dumps(dict(saved, season_name="  ")), encoding="utf-8")
            self.assertEqual(build.season_label(folder, 4), "Season 4")
        # and the build names the season with it
        self.assertIn("        label = season_label(folder, num)\n", read(ROOT / "scripts" / "build.py").split("def main():", 1)[1])

    def test_no_file_changes_nothing(self):
        with sandbox() as root, quiet():
            folder = make_season(root / "data" / "season1", [TIE_ROUND])
            self.assertEqual(build.site_season_rows(folder), ([], [], [], [], {}))


class Publishing(unittest.TestCase):
    EXPORT = {"rounds": [SITE_ROUND], "players": dict(PLAYERS, p9="Not In It")}

    def fetch(self, export):
        with sandbox() as root, quiet(), mock.patch.object(publish.supa, "request", return_value=export) as req:
            publish.fetch_site_rounds()
            saved = {p.parent.name: json.loads(p.read_text(encoding="utf-8"))
                     for p in (root / "data").glob("*/" + build.SITE_ROUNDS_FILE)}
        return saved, req

    def test_it_asks_the_database_for_finished_rounds_only(self):
        _, req = self.fetch(self.EXPORT)
        req.assert_called_once_with("POST", "/rest/v1/rpc/site_rounds_export", body={})

    def test_each_season_gets_its_rounds_and_only_their_players(self):
        saved, _ = self.fetch(self.EXPORT)
        self.assertEqual(list(saved), ["season1"])
        self.assertEqual(saved["season1"]["rounds"], [SITE_ROUND])
        self.assertEqual(saved["season1"]["players"], PLAYERS)

    def test_a_season_set_up_on_the_site_carries_its_name(self):
        saved, _ = self.fetch(dict(self.EXPORT, seasons={"season1": "The Summer Season", "season9": "Unplayed"}))
        self.assertEqual(saved["season1"]["season_name"], "The Summer Season")
        self.assertNotIn("season9", saved)
        saved, _ = self.fetch(self.EXPORT)
        self.assertNotIn("season_name", saved["season1"])

    def test_a_season_key_the_build_cant_use_stops_it(self):
        bad = {"rounds": [dict(SITE_ROUND, season_key="../x")], "players": {}}
        with self.assertRaises(SystemExit):
            self.fetch(bad)

    def test_a_file_the_database_no_longer_backs_is_kept(self):
        with sandbox() as root, quiet(), mock.patch.object(publish.supa, "request", return_value={"rounds": [], "players": {}}):
            folder = make_season(root / "data" / "season1", [TIE_ROUND])
            write_site(folder)
            publish.fetch_site_rounds()
            self.assertTrue((folder / build.SITE_ROUNDS_FILE).exists())

    def test_album_art_is_looked_up_for_site_tracks_spotify_ids(self):
        with sandbox() as root, quiet():
            write_site(root / "data" / "season1")
            with mock.patch.object(publish, "art_for", return_value="https://art/x.jpg") as art_for, mock.patch("time.sleep"):
                publish.refresh_art()
        self.assertEqual(sorted(c.args[0] for c in art_for.call_args_list), sorted([SPOTIFY, MATCH]))

    def test_the_backup_keeps_it(self):
        with sandbox() as root, quiet():
            folder = make_season(root / "data" / "season1", [TIE_ROUND])
            write_site(folder)
            self.assertIn(folder / build.SITE_ROUNDS_FILE, publish.backup_files())

    def test_the_export_function_is_the_only_door(self):
        # it holds the "only after voting closes" rule; reading the tables
        # with the secret key would skip it
        for name in ("publish.py", "build.py", "round_playlists.py"):
            with self.subTest(name):
                src = read(ROOT / "scripts" / name)
                self.assertNotRegex(src, r"/rest/v1/(site_submission_owners|site_votes|members)\b")

    def test_main_fetches_before_it_builds(self):
        src = read(ROOT / "scripts" / "publish.py")
        body = src.split("def main():", 1)[1]
        self.assertLess(body.index("fetch_site_rounds()"), body.index("build.main()"))
        self.assertLess(body.index("fetch_site_rounds()"), body.index("refresh_art()"))


class TheExport(unittest.TestCase):
    def setUp(self):
        self.sql = schema()
        self.fn = function(self.sql, "site_rounds_export")

    def test_schema_has_what_the_migration_adds(self):
        migration = read(ROOT / "supabase" / "migrations" / "2026-10-25_site_rounds_export.sql")
        self.assertIn(migration[migration.index("create or replace function public.site_rounds_export"):], self.sql)

    def test_only_rounds_whose_voting_has_closed(self):
        self.assertIn("where r.votes_on_site and public.site_round_phase(r.id) = 'finished'", self.fn)

    def test_only_the_secret_key_can_call_it(self):
        self.assertIn("revoke all on function public.site_rounds_export() from public, anon, authenticated;", self.sql)
        self.assertIn("grant execute on function public.site_rounds_export() to service_role;", self.sql)
        self.assertNotRegex(self.sql, r"grant execute on function public\.site_rounds_export\(\) to (anon|authenticated)")


class OnThePages(unittest.TestCase):
    def setUp(self):
        self.account = read(SITE / "account.js")

    def test_a_track_links_to_where_it_was_submitted(self):
        fn = self.account.split("function songUrl(t) {", 1)[1].split("\n  }\n", 1)[0]
        order = [fn.index(s) for s in ('link.platform === "youtube"', 'link.platform === "soundcloud"', "t.spotifyId ?")]
        self.assertEqual(order, sorted(order), "the submitted version first, Spotify after")
        # nothing about Spotify comes before the submitted version's checks
        self.assertNotRegex(fn.split('link.platform === "youtube"', 1)[0], r"(?i)spotify")
        self.assertIn("encodeURIComponent(link.id)", fn)
        self.assertIn("PFML.songUrl = songUrl;", self.account)

    def test_no_page_builds_a_spotify_track_link_itself(self):
        # every track link goes through PFML.songUrl, so none points a YouTube
        # pick at Spotify (or at nothing)
        for name in ("app.js", "rounds.js", "repeats.js"):
            with self.subTest(name):
                self.assertNotIn("open.spotify.com/track/", read(SITE / name))
        self.assertIn("function trackLink(t) { return PFML.songUrl(t); }", read(SITE / "app.js"))

    def test_the_round_page_says_why_a_track_scored_0(self):
        rounds = read(SITE / "rounds.js")
        self.assertIn("(s.forfeit ? '<p class=\"rp-forfeit\">Didn\\u2019t vote, so it scored 0'", rounds)


if __name__ == "__main__":
    unittest.main()
