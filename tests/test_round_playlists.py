"""scripts/round_playlists.py and scripts/connect_accounts.py: the round
playlists (README, Submissions on the site, stage 2).

Offline: Spotify, YouTube, SoundCloud and the database are fakes here, and
.env is a temp file, so nothing touches the network or the real keys. What
Spotify's and YouTube's real APIs accept was read from their docs
(2026-10-19); the first real run is the check on that."""
import contextlib
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from support import ROOT

import round_playlists as rp  # noqa: E402  (support puts scripts/ on the path)
import connect_accounts as ca  # noqa: E402
import supa  # noqa: E402

FAKE_ENV = {
    "SPOTIFY_CLIENT_ID": "spotify-id", "SPOTIFY_CLIENT_SECRET": "spotify-secret", "SPOTIFY_REFRESH_TOKEN": "sp-refresh",
    "GOOGLE_CLIENT_ID": "google-id", "GOOGLE_CLIENT_SECRET": "google-secret", "YOUTUBE_REFRESH_TOKEN": "yt-refresh",
}


@contextlib.contextmanager
def fake_env(extra=None):
    """Fake keys, and a temp .env, so the real one is never read or written."""
    with tempfile.TemporaryDirectory() as tmp:
        env_file = Path(tmp) / ".env"
        env_file.write_text("SUPABASE_URL=https://example.supabase.co\nOTHER=keep me\n", encoding="utf-8")
        with mock.patch.dict(os.environ, dict(FAKE_ENV, **(extra or {})), clear=False), \
             mock.patch.object(supa, "ENV_FILE", env_file), \
             mock.patch.object(supa, "_load_env_file", lambda: None):
            yield env_file


def sid(n):
    """A made-up 22-character Spotify id."""
    return ("S%02d" % n).ljust(22, "x")


def vid(n):
    """A made-up 11-character YouTube id."""
    return ("Y%02d" % n).ljust(11, "x")


class Tidying(unittest.TestCase):
    def test_titles_lose_upload_labels_and_features_but_keep_the_song(self):
        self.assertEqual(rp.clean_title("Distant Lover (Official Audio)"), "distant lover")
        self.assertEqual(rp.clean_title("Such A Night [HD Music Video]"), "such a night")
        self.assertEqual(rp.clean_title("Caravan (feat. Van Morrison)"), "caravan")
        self.assertEqual(rp.clean_title("Shining Star - 2011 Remaster"), "shining star")
        self.assertEqual(rp.clean_title("Señor & Me"), "senor and me")

    def test_a_video_title_splits_into_artist_and_song(self):
        self.assertEqual(rp.split_youtube_title("Distant Lover", "Marvin Gaye - Topic"), ("Marvin Gaye", "Distant Lover"))
        self.assertEqual(rp.split_youtube_title("Sam Cooke - Bring It On Home To Me (Live)", "SamCookeVEVO"),
                         ("Sam Cooke", "Bring It On Home To Me (Live)"))
        self.assertEqual(rp.split_youtube_title("Mercy, Mercy, Mercy", "Cannonball Adderley Official"),
                         ("Cannonball Adderley", "Mercy, Mercy, Mercy"))

    def test_youtube_durations(self):
        self.assertEqual(rp.iso_seconds("PT4M13S"), 253)
        self.assertEqual(rp.iso_seconds("PT1H2M"), 3720)
        self.assertEqual(rp.iso_seconds("PT45S"), 45)
        self.assertIsNone(rp.iso_seconds(""))


class Judging(unittest.TestCase):
    SRC = {"title": "Distant Lover - Live", "artist": "Marvin Gaye", "seconds": 400}

    def test_same_title_artist_and_length_is_sure(self):
        cand = {"title": "Distant Lover (Live)", "artist": "Marvin Gaye - Topic", "seconds": 401}
        self.assertEqual(rp.judge(self.SRC, cand), "sure")

    def test_a_music_video_with_an_intro_is_only_unsure(self):
        cand = {"title": "Distant Lover (Live) [Official Video]", "artist": "Marvin Gaye", "seconds": 412}
        self.assertEqual(rp.judge(self.SRC, cand), "unsure")

    def test_the_studio_take_never_stands_in_for_the_live_one(self):
        cand = {"title": "Distant Lover", "artist": "Marvin Gaye - Topic", "seconds": 400}
        self.assertIsNone(rp.judge(self.SRC, cand))

    def test_a_cover_by_someone_else_is_not_a_match(self):
        cand = {"title": "Distant Lover (Live)", "artist": "Some Tribute Band", "seconds": 400}
        self.assertIsNone(rp.judge(self.SRC, cand))

    def test_remastered_and_single_versions_count_as_the_same_recording(self):
        src = {"title": "Shining Star", "artist": "Earth, Wind & Fire", "seconds": 170}
        for title in ("Shining Star - 2011 Remaster", "Shining Star - Single Version"):
            with self.subTest(title):
                self.assertIsNotNone(rp.judge(src, {"title": title, "artist": "Earth, Wind & Fire", "seconds": 170}))

    def test_a_duo_matches_a_channel_named_for_one_of_them(self):
        # measured: Spotify credits "Gil Scott-Heron, Brian Jackson"; the
        # YouTube upload is on Gil Scott-Heron's channel
        src = {"title": "H2Ogate Blues", "artist": "Gil Scott-Heron, Brian Jackson", "seconds": 506}
        cand = {"title": "H2Ogate Blues", "artist": "Gil Scott-Heron Gil Scott-Heron - Topic", "seconds": 506}
        self.assertEqual(rp.judge(src, cand), "sure")
        self.assertIsNone(rp.judge(src, dict(cand, artist="Some Cover Band")))

    def test_soundcloud_has_no_length_so_it_is_never_sure_on_its_own(self):
        src = {"title": "Flickermood", "artist": "Forss", "seconds": None}
        self.assertEqual(rp.judge(src, {"title": "Flickermood", "artist": "Forss", "seconds": 300}), "unsure")

    def test_best_prefers_sure_then_closest_length(self):
        far = {"id": "a", "title": "Distant Lover (Live)", "artist": "Marvin Gaye", "seconds": 415}
        near = {"id": "b", "title": "Distant Lover (Live)", "artist": "Marvin Gaye", "seconds": 402}
        studio = {"id": "c", "title": "Distant Lover", "artist": "Marvin Gaye", "seconds": 400}
        self.assertEqual(rp.best(self.SRC, [far, studio, near]), ("sure", near))
        self.assertEqual(rp.best(self.SRC, [studio]), (None, None))


class Order(unittest.TestCase):
    # made-up round id; the tracks are public video and track ids
    ROUND = "ad725b31-069d-4d39-af6a-7ddf5bac7797"
    SUBS = [{"id": f"id{n}", "tag": tag, "platform": p, "track": t, "position": None}
            for n, (tag, p, t) in enumerate([("B4", "youtube", "Y9a49oFalZE"), ("Q7", "spotify", "4uLU6hMCjMI75M1A2tKUQC"),
                                             ("K2", "soundcloud", "artist/song"), ("Z9", "youtube", "dQw4w9WgXcQ")])]

    def test_the_hash_is_the_one_the_page_uses(self):
        # the same values were checked against roundOrder in site/account.js
        # in a browser (2026-10-25); a change here must change both
        self.assertEqual([rp.shuffle_key(self.ROUND, s) for s in self.SUBS], [476005911, 2737754968, 868409426, 2350724550])
        js = (ROOT / "site" / "account.js").read_text(encoding="utf-8")
        self.assertIn('new TextEncoder().encode(roundId + "|" + s.platform + "|" + s.track), h = 0x811c9dc5;', js)
        self.assertIn("h = Math.imul(h ^ bytes[i], 0x01000193) >>> 0;", js)

    def test_a_new_round_gets_the_one_shuffle(self):
        self.assertEqual(rp.shuffled_positions(self.ROUND, self.SUBS), {"id0": 1, "id2": 2, "id3": 3, "id1": 4})

    def test_nothing_but_the_round_and_the_tracks_decides_it(self):
        # not the order they came in, not the tags, not the submission ids
        shuffled = [dict(s, id="x" + s["id"], tag="A2") for s in reversed(self.SUBS)]
        order = [s["track"] for s in rp.round_order(self.ROUND, shuffled)]
        self.assertEqual(order, [s["track"] for s in rp.round_order(self.ROUND, self.SUBS)])
        self.assertNotEqual(order, [s["track"] for s in rp.round_order("another-round", self.SUBS)])

    def test_a_saved_order_is_kept_on_every_later_run(self):
        subs = [dict(s, position=p) for s, p in zip(self.SUBS, [3, 1, 4, 2])]
        self.assertEqual(rp.shuffled_positions(self.ROUND, subs), {"id0": 3, "id1": 1, "id2": 4, "id3": 2})

    def test_each_playlist_follows_the_order_and_skips_its_gaps(self):
        rows = [{"tag": "A2", "position": 2, "spotify_match": sid(1), "youtube_match": None},
                {"tag": "B3", "position": 1, "spotify_match": sid(2), "youtube_match": vid(2)},
                {"tag": "C4", "position": 3, "spotify_match": None, "youtube_match": vid(3)}]
        self.assertEqual(rp.playlist_order(rows, "spotify"), [sid(2), sid(1)])
        self.assertEqual(rp.playlist_order(rows, "youtube"), [vid(2), vid(3)])
        self.assertEqual(rp.describe_gaps(rows), {"spotify": ["C4"], "youtube": ["A2"]})


class Overrides(unittest.TestCase):
    def test_links_or_ids_and_null_for_no_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "o.json"
            path.write_text(json.dumps({
                "round-1": {"Q7": {"spotify": "https://open.spotify.com/track/" + sid(5) + "?si=x",
                                   "youtube": None},
                            "K2": {"youtube": "https://youtu.be/" + vid(6)}},
                "round-2": {"Q7": {"spotify": sid(9)}}}), encoding="utf-8")
            got = rp.overrides_for("round-1", path)
        self.assertEqual(got, {"Q7": {"spotify": sid(5), "youtube": None}, "K2": {"youtube": vid(6)}})

    def test_an_unreadable_link_stops_the_run(self):
        with self.assertRaises(SystemExit):
            rp.read_link("https://example.com/not-a-track", "spotify")


class Env(unittest.TestCase):
    def test_save_replaces_or_adds_one_line_and_keeps_the_rest(self):
        with fake_env() as env_file:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rp.save_env("YOUTUBE_REFRESH_TOKEN", "new-secret-value")
                rp.save_env("YOUTUBE_REFRESH_TOKEN", "newer-secret-value")
            text = env_file.read_text(encoding="utf-8")
        self.assertIn("OTHER=keep me", text)
        self.assertEqual(text.count("YOUTUBE_REFRESH_TOKEN="), 1)
        self.assertIn("YOUTUBE_REFRESH_TOKEN=newer-secret-value", text)
        self.assertNotIn("secret", out.getvalue())


class FakeHttp:
    """Records every call; answers from a list of (method, url-substring, reply)."""

    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, method, url, headers=None, body=None, form=None):
        self.calls.append({"method": method, "url": url, "headers": headers or {}, "body": body, "form": form})
        for i, (m, part, reply) in enumerate(self.replies):
            if m == method and part in url:
                self.replies.pop(i)
                return reply
        raise AssertionError(f"unexpected {method} {url}")


class ServiceCalls(unittest.TestCase):
    def test_spotify_uses_the_2026_playlist_endpoints_and_keeps_it_private(self):
        token = (200, {"access_token": "t"}, {})
        fake = FakeHttp([("POST", "accounts.spotify.com/api/token", token),
                         ("POST", "/v1/me/playlists", (201, {"id": sid(1)}, {})),
                         ("PUT", f"/v1/playlists/{sid(1)}/items", (200, {}, {}))])
        with fake_env(), mock.patch.object(rp, "http", fake):
            sp = rp.Spotify()
            pid = sp.create_playlist("PFML · Round 7", "desc")
            sp.set_items(pid, [sid(2), sid(3)])
        create = fake.calls[1]
        self.assertFalse(create["body"]["public"])
        self.assertEqual(fake.calls[2]["body"], {"uris": ["spotify:track:" + sid(2), "spotify:track:" + sid(3)]})
        self.assertNotIn("/users/", "".join(c["url"] for c in fake.calls))
        self.assertNotRegex("".join(c["url"] for c in fake.calls), r"/tracks(\?|$)")

    def test_spotify_search_asks_for_at_most_ten(self):
        token = (200, {"access_token": "t"}, {})
        item = {"id": sid(4), "name": "Distant Lover - Live", "duration_ms": 400000, "artists": [{"name": "Marvin Gaye"}]}
        fake = FakeHttp([("POST", "api/token", token), ("GET", "/v1/search", (200, {"tracks": {"items": [item]}}, {}))])
        with fake_env(), mock.patch.object(rp, "http", fake):
            found = rp.Spotify().search('Distant "Lover"', "Marvin Gaye")
        self.assertIn("limit=10", fake.calls[1]["url"])
        self.assertNotIn("%22Lover%22%22", fake.calls[1]["url"])
        self.assertEqual(found[0]["id"], sid(4))

    def test_a_track_lookup_brings_its_album_and_year(self):
        token = (200, {"access_token": "t"}, {})
        item = {"id": sid(1), "name": "X", "duration_ms": 200000, "artists": [{"name": "Y"}],
                "album": {"name": "Blue", "release_date": "1971-06-22"}}
        fake = FakeHttp([("POST", "api/token", token), ("GET", f"/v1/tracks/{sid(1)}", (200, item, {})),
                         ("GET", "/v1/search", (200, {"tracks": {"items": [item]}}, {}))])
        with fake_env(), mock.patch.object(rp, "http", fake):
            sp = rp.Spotify()
            info = sp.track(sid(1))
            found = sp.search("X", "Y")
        self.assertEqual((info["album"], info["year"], info["seconds"]), ("Blue", 1971, 200))
        self.assertEqual((found[0]["album"], found[0]["year"]), ("Blue", 1971))

    def test_a_rotated_spotify_token_is_saved_and_never_printed(self):
        fake = FakeHttp([("POST", "api/token", (200, {"access_token": "t", "refresh_token": "rotated-secret"}, {})),
                         ("GET", f"/v1/tracks/{sid(1)}", (200, {"id": sid(1), "name": "X", "duration_ms": 1000,
                                                                 "artists": [{"name": "Y"}]}, {}))])
        out = io.StringIO()
        with fake_env() as env_file, mock.patch.object(rp, "http", fake), contextlib.redirect_stdout(out):
            rp.Spotify().track(sid(1))
            saved = env_file.read_text(encoding="utf-8")
        self.assertIn("SPOTIFY_REFRESH_TOKEN=rotated-secret", saved)
        self.assertNotIn("rotated-secret", out.getvalue())

    def test_youtube_playlists_are_unlisted_and_refilled_in_order(self):
        token = (200, {"access_token": "t"}, {})
        listing = (200, {"items": [{"id": "old1", "snippet": {"resourceId": {"videoId": vid(9)}}}]}, {})
        fake = FakeHttp([("POST", "oauth2.googleapis.com/token", token),
                         ("POST", "/youtube/v3/playlists", (200, {"id": "PLabc123xyz"}, {})),
                         ("GET", "/youtube/v3/playlistItems", listing),
                         ("DELETE", "/youtube/v3/playlistItems", (204, None, {})),
                         ("POST", "/youtube/v3/playlistItems", (200, {}, {})),
                         ("POST", "/youtube/v3/playlistItems", (200, {}, {}))])
        with fake_env(), mock.patch.object(rp, "http", fake):
            yt = rp.YouTube()
            pid = yt.create_playlist("PFML · Round 7", "desc")
            yt.set_items(pid, [vid(1), vid(2)])
        self.assertEqual(fake.calls[1]["body"]["status"]["privacyStatus"], "unlisted")
        inserts = [c["body"]["snippet"] for c in fake.calls if c["method"] == "POST" and "playlistItems" in c["url"]]
        self.assertEqual([(s["position"], s["resourceId"]["videoId"]) for s in inserts], [(0, vid(1)), (1, vid(2))])

    def test_youtube_waits_out_a_new_playlist_and_an_aborted_add(self):
        # both measured 2026-10-26: a just-made playlist is "not found" for a
        # moment, and an add is sometimes "409 The operation was aborted"
        token = (200, {"access_token": "t"}, {})
        listing = (200, {"items": []}, {})
        fake = FakeHttp([("POST", "oauth2.googleapis.com/token", token),
                         ("GET", "/youtube/v3/playlistItems", (404, {"error": {"message": "playlistNotFound"}}, {})),
                         ("GET", "/youtube/v3/playlistItems", listing),
                         ("POST", "/youtube/v3/playlistItems", (409, {"error": {"message": "The operation was aborted."}}, {})),
                         ("POST", "/youtube/v3/playlistItems", (200, {}, {}))])
        with fake_env(), mock.patch.object(rp, "http", fake), mock.patch.object(rp.time, "sleep") as slept:
            rp.YouTube().set_items("PLabc123xyz", [vid(1)])
        self.assertEqual(slept.call_count, 2)
        self.assertEqual(len([c for c in fake.calls if c["method"] == "POST" and "playlistItems" in c["url"]]), 2)

    def test_youtube_gives_up_on_a_lasting_refusal_and_never_waits_on_other_404s(self):
        token = (200, {"access_token": "t"}, {})
        aborted = (409, {"error": {"message": "The operation was aborted."}}, {})
        fake = FakeHttp([("POST", "oauth2.googleapis.com/token", token)] +
                        [("POST", "/youtube/v3/playlistItems", aborted)] * rp.YouTube.TRIES)
        with fake_env(), mock.patch.object(rp, "http", fake), mock.patch.object(rp.time, "sleep"):
            # the real refusal, not a misleading "not signed in"
            with self.assertRaisesRegex(rp.ApiError, "409"):
                rp.YouTube().call("POST", "/playlistItems", {"part": "snippet"}, body={})
        missing = FakeHttp([("POST", "oauth2.googleapis.com/token", token),
                            ("GET", "/youtube/v3/videos", (404, {"error": {"message": "nope"}}, {}))])
        with fake_env(), mock.patch.object(rp, "http", missing), mock.patch.object(rp.time, "sleep") as slept:
            with self.assertRaises(rp.ApiError):
                rp.YouTube().call("GET", "/videos", {"id": vid(1)})
        self.assertEqual(slept.call_count, 0)

    def test_soundcloud_title_drops_the_by_artist_tail(self):
        fake = FakeHttp([("GET", "soundcloud.com/oembed", (200, {"title": "Flickermood by Forss", "author_name": "Forss"}, {}))])
        with mock.patch.object(rp, "http", fake):
            self.assertEqual(rp.soundcloud_info("forss/flickermood"), {"title": "Flickermood", "artist": "Forss", "seconds": None})


class FakeSpotify:
    def __init__(self):
        self.created, self.updated, self.items = [], [], {}
        self.catalog = {sid(1): {"id": sid(1), "title": "Bring It On Home To Me - Live", "artist": "Sam Cooke", "seconds": 230,
                                 "album": "Live at the Harlem Square Club, 1963", "year": 1985},
                        sid(2): {"id": sid(2), "title": "Mercy, Mercy, Mercy - Live", "artist": "Cannonball Adderley", "seconds": 310,
                                 "album": "Mercy, Mercy, Mercy!", "year": 1966}}

    def track(self, t):
        self.looked_up = getattr(self, "looked_up", []) + [t]
        # like the real one: a track Spotify doesn't have is an API error
        if t not in self.catalog:
            raise rp.ApiError(f"Spotify GET /tracks/{t}: 404")
        return dict(self.catalog[t])

    def search(self, title, artist):
        return [v for v in self.catalog.values() if rp.clean_title(v["title"]) == rp.clean_title(title)]

    def create_playlist(self, name, desc):
        self.created.append((name, desc))
        return sid(99)

    def update_playlist(self, pid, name, desc):
        self.updated.append(pid)

    def set_items(self, pid, ids):
        self.items[pid] = list(ids)


class FakeYouTube(FakeSpotify):
    def __init__(self):
        super().__init__()
        self.catalog = {vid(1): {"id": vid(1), "title": "Bring It On Home To Me (Live)", "artist": "Sam Cooke - Topic", "seconds": 231},
                        vid(3): {"id": vid(3), "title": "Pancho and Lefty (Live)", "artist": "Townes Van Zandt", "seconds": 260},
                        vid(4): {"id": vid(4), "title": "Mercy, Mercy, Mercy (Live)", "artist": "Cannonball Adderley", "seconds": 330}}

    def videos(self, ids):
        return {i: dict(self.catalog[i], artist=self.catalog[i]["artist"].replace(" - Topic", "")) for i in ids if i in self.catalog}

    def create_playlist(self, name, desc):
        self.created.append((name, desc))
        return "PLnew0000000"


class FakeDb:
    def __init__(self, rounds, subs):
        self.rounds, self.subs, self.writes, self.paths = rounds, subs, [], []

    def __call__(self, method, path, body=None, headers=None):
        self.paths.append(path)
        if method == "GET" and path.startswith("/rest/v1/site_rounds"):
            return [dict(r) for r in self.rounds]
        if method == "GET" and path.startswith("/rest/v1/site_submissions"):
            return [dict(s) for s in self.subs]
        if method == "PATCH":
            self.writes.append((path, body))
            return None
        raise AssertionError(f"unexpected {method} {path}")


ROUND = {"id": "r1", "name": "Round 7: Live Tracks", "closes_at": "2026-10-01T20:00:00+00:00", "closed_at": None,
         "spotify_playlist": None, "youtube_playlist": None, "playlists_built_at": None, "created_at": "2026-09-28T00:00:00+00:00"}


def subs():
    return [{"id": "a", "tag": "Q7", "platform": "spotify", "track": sid(1)},        # on both
            {"id": "b", "tag": "K2", "platform": "youtube", "track": vid(3)},        # YouTube only
            {"id": "c", "tag": "B4", "platform": "spotify", "track": sid(2)}]        # YouTube copy has a long intro


class Build(unittest.TestCase):
    def run_build(self, rounds=None, rows=None, **kw):
        db = FakeDb(rounds or [dict(ROUND)], rows or subs())
        sp, yt, out = FakeSpotify(), FakeYouTube(), []
        overrides = kw.pop("overrides", {})
        with fake_env(), mock.patch.object(rp, "overrides_for", lambda rid, path=None: overrides):
            result = rp.build(spotify=sp, youtube=yt, db=db, log=out.append, **kw)
        return result, db, sp, yt, "\n".join(out)

    def test_first_run_shuffles_matches_builds_both_and_saves(self):
        (r, rows, sp_id, yt_id), db, sp, yt, log = self.run_build()
        by_tag = {row["tag"]: row for row in rows}
        self.assertEqual(sorted(row["position"] for row in rows), [1, 2, 3])
        self.assertEqual(by_tag["Q7"]["youtube_match"], vid(1))          # sure: Topic upload, same length
        self.assertIsNone(by_tag["K2"]["spotify_match"])                  # no copy: a gap
        self.assertIsNone(by_tag["B4"]["youtube_match"])                  # unsure: left out, listed
        self.assertIn("Not sure about B4 on youtube", log)
        order = sorted(rows, key=lambda x: x["position"])
        self.assertEqual(sp.items[sid(99)], [x["spotify_match"] for x in order if x["spotify_match"]])
        self.assertEqual(yt.items["PLnew0000000"], [x["youtube_match"] for x in order if x["youtube_match"]])
        self.assertIn("Not on Spotify: K2", sp.created[0][1])
        round_write = [b for p, b in db.writes if "site_rounds" in p][0]
        self.assertEqual((round_write["spotify_playlist"], round_write["youtube_playlist"]), (sid(99), "PLnew0000000"))

    def test_each_track_keeps_its_length_album_and_year(self):
        # asked 2026-10-26: shown with each track on the round page
        (_, rows, _, _), db, *_ = self.run_build(overrides={"K2": {"spotify": sid(2)}})
        by_tag = {r["tag"]: r for r in rows}
        # a Spotify track: its own length, album and year
        self.assertEqual((by_tag["Q7"]["seconds"], by_tag["Q7"]["album"], by_tag["Q7"]["year"]),
                         (230, "Live at the Harlem Square Club, 1963", 1985))
        # a YouTube track: the video's length, the album and year of its Spotify copy
        self.assertEqual((by_tag["K2"]["seconds"], by_tag["K2"]["album"], by_tag["K2"]["year"]),
                         (260, "Mercy, Mercy, Mercy!", 1966))
        written = {b["position"]: b for p, b in db.writes if "site_submissions" in p}
        self.assertTrue(all({"seconds", "album", "year"} <= set(b) for b in written.values()))

    def test_a_spotify_track_is_looked_up_once(self):
        (_, rows, _, _), db, sp, yt, _ = self.run_build(dry_run=True)
        spotify_sent = [r["track"] for r in rows if r["platform"] == "spotify"]
        self.assertEqual(sorted(sp.looked_up), sorted(spotify_sent))

    def test_a_spotify_copy_spotify_has_lost_leaves_the_album_blank(self):
        (_, rows, _, _), *_ = self.run_build(overrides={"K2": {"spotify": sid(7)}})
        k2 = {r["tag"]: r for r in rows}["K2"]
        self.assertEqual((k2["seconds"], k2["album"], k2["year"]), (260, None, None))

    def test_album_and_year_come_from_spotifys_album(self):
        self.assertEqual(rp.album_of({"album": {"name": "Blue", "release_date": "1971-06-22"}}), {"album": "Blue", "year": 1971})
        self.assertEqual(rp.album_of({"album": {"name": "", "release_date": "0000"}}), {"album": None, "year": None})
        self.assertEqual(rp.album_of({}), {"album": None, "year": None})
        self.assertEqual(len(rp.album_of({"album": {"name": "x" * 400}})["album"]), 300)

    def test_accept_takes_an_unsure_match(self):
        (_, rows, _, _), *_ = self.run_build(accept={"B4"})
        self.assertEqual({r["tag"]: r for r in rows}["B4"]["youtube_match"], vid(4))

    def test_an_override_wins_even_when_it_says_no_copy(self):
        (_, rows, _, _), *_ = self.run_build(overrides={"Q7": {"youtube": None}, "K2": {"spotify": sid(7)}})
        by_tag = {r["tag"]: r for r in rows}
        self.assertIsNone(by_tag["Q7"]["youtube_match"])
        self.assertEqual(by_tag["K2"]["spotify_match"], sid(7))

    def test_a_rebuild_keeps_the_order_and_updates_the_same_playlists(self):
        built = dict(ROUND, spotify_playlist=sid(50), youtube_playlist="PLold0000000", playlists_built_at="2026-10-02T00:00:00Z")
        saved = [dict(s, position=p) for s, p in zip(subs(), [2, 3, 1])]
        (_, rows, sp_id, yt_id), db, sp, yt, _ = self.run_build(rounds=[built], rows=saved, round_id="r1")
        self.assertEqual({r["tag"]: r["position"] for r in rows}, {"Q7": 2, "K2": 3, "B4": 1})
        self.assertEqual((sp_id, yt_id), (sid(50), "PLold0000000"))
        self.assertEqual((sp.created, yt.created), ([], []))
        self.assertEqual((sp.updated, yt.updated), ([sid(50)], ["PLold0000000"]))

    def test_dry_run_writes_nothing_and_touches_no_playlist(self):
        _, db, sp, yt, log = self.run_build(dry_run=True)
        self.assertEqual(db.writes, [])
        self.assertEqual((sp.created, sp.items, yt.created, yt.items), ([], {}, [], {}))
        self.assertIn("Dry run", log)

    def test_never_asks_who_submitted_what(self):
        _, db, *_ = self.run_build()
        self.assertFalse(any("owners" in p for p in db.paths))
        self.assertNotIn("site_submission_owners?", (ROOT / "scripts" / "round_playlists.py").read_text(encoding="utf-8"))

    def test_an_open_round_is_refused(self):
        open_round = dict(ROUND, closes_at="2999-01-01T00:00:00+00:00")
        with self.assertRaises(SystemExit):
            self.run_build(rounds=[open_round], round_id="r1")

    def test_with_nothing_to_build_it_says_so(self):
        done = dict(ROUND, playlists_built_at="2026-10-02T00:00:00Z")
        with self.assertRaises(SystemExit):
            self.run_build(rounds=[done])


class Connect(unittest.TestCase):
    def test_sign_in_asks_only_for_playlists_and_never_sends_the_secret(self):
        with fake_env():
            sp = ca.authorize_url("spotify", "state123")
            yt = ca.authorize_url("youtube", "state123")
        for url in (sp, yt):
            self.assertIn("redirect_uri=http%3A%2F%2F127.0.0.1%3A8888%2Fcallback", url)
            self.assertIn("state=state123", url)
            self.assertNotIn("secret", url)
        self.assertIn("scope=playlist-modify-private+playlist-modify-public+playlist-read-private", sp)
        self.assertIn("scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fyoutube&", yt)
        self.assertIn("access_type=offline", yt)


class Database(unittest.TestCase):
    def test_schema_has_the_playlist_columns_the_migration_adds(self):
        migration = (ROOT / "supabase" / "migrations" / "2026-10-19_round_playlists.sql").read_text(encoding="utf-8")
        body = migration[migration.index("alter table public.site_rounds add column"):]
        self.assertIn(body, (ROOT / "supabase" / "schema.sql").read_text(encoding="utf-8"))

    def test_no_column_added_to_submissions_says_who_or_when(self):
        sql = (ROOT / "supabase" / "schema.sql").read_text(encoding="utf-8")
        for col in re.findall(r"alter table public\.site_submissions add column if not exists (\w+) (\w+)", sql):
            with self.subTest(col[0]):
                self.assertNotRegex(" ".join(col), r"user|uid|time|created|timestamptz|date")

    def test_the_page_reads_what_the_script_writes(self):
        auth = (ROOT / "site" / "auth.js").read_text(encoding="utf-8")
        for col in ("position", "title", "artist", "spotify_match", "youtube_match"):
            self.assertRegex(auth, r'site_submissions"\)\.select\("[^"]*\b' + col + r'\b')
        for col in ("spotify_playlist", "youtube_playlist"):
            self.assertRegex(auth, r'site_rounds"\)\.select\("[^"]*\b' + col + r'\b')
        js = (ROOT / "site" / "listen.js").read_text(encoding="utf-8")
        self.assertIn("https://open.spotify.com/playlist/", js)
        self.assertIn("https://www.youtube.com/playlist?list=", js)
        css = re.sub(r"/\*.*?\*/", "", (ROOT / "site" / "style.css").read_text(encoding="utf-8"), flags=re.S)
        self.assertRegex(css, r"\.sub-playlists\[hidden\]\s*\{\s*display:\s*none")


if __name__ == "__main__":
    unittest.main()
