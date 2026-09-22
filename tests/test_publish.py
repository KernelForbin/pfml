"""scripts/publish.py: the album-art lookup and cache, the playlist stats,
and the backup. Offline: Spotify's pages are faked here.
tests/test_live_spotify.py checks the real ones."""
import io
import json
import unittest
import urllib.error
from unittest import mock

from support import make_season, publish, quiet, sandbox

ROUND = {"id": "r1", "name": "Round One", "created": "2025-01-01T00:00:00Z",
         "subs": [("aaa", "p1"), ("bbb", "p2"), ("ccc", "p3")], "votes": []}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code):
    return urllib.error.HTTPError("https://open.spotify.com/oembed", code, "err", {}, None)


class ArtFor(unittest.TestCase):
    def test_returns_the_thumbnail_url(self):
        body = json.dumps({"thumbnail_url": "https://image-cdn.example/x.jpg"}).encode()
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(body)) as urlopen:
            self.assertEqual(publish.art_for("abc"), "https://image-cdn.example/x.jpg")
        self.assertEqual(urlopen.call_args[0][0].full_url,
                         "https://open.spotify.com/oembed?url=https%3A//open.spotify.com/track/abc")

    def test_rate_limit_backs_off_then_gives_up(self):
        with mock.patch("urllib.request.urlopen", side_effect=http_error(429)), \
             mock.patch("time.sleep") as sleep:
            with self.assertRaises(publish.RateLimited):
                publish.art_for("abc")
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [2, 4, 8, 16])

    def test_rate_limit_then_success_returns_art(self):
        body = json.dumps({"thumbnail_url": "https://image-cdn.example/y.jpg"}).encode()
        with mock.patch("urllib.request.urlopen", side_effect=[http_error(429), FakeResponse(body)]), \
             mock.patch("time.sleep"):
            self.assertEqual(publish.art_for("abc"), "https://image-cdn.example/y.jpg")

    def test_other_errors_mean_no_art_not_a_failed_publish(self):
        for err in (http_error(404), urllib.error.URLError("offline"), ValueError("bad json")):
            with mock.patch("urllib.request.urlopen", side_effect=err):
                self.assertIsNone(publish.art_for("abc"), err)


class RefreshArt(unittest.TestCase):
    def test_looks_up_only_tracks_not_already_cached(self):
        with sandbox() as root, quiet():
            make_season(root / "data" / "season1", [ROUND])
            publish.ART_CACHE.write_text(json.dumps({"aaa": "https://cached/a.jpg"}))
            with mock.patch.object(publish, "art_for", side_effect=lambda t: f"https://new/{t}.jpg") as art_for, \
                 mock.patch("time.sleep"):
                publish.refresh_art()
            cache = json.loads(publish.ART_CACHE.read_text())
        self.assertEqual(sorted(c.args[0] for c in art_for.call_args_list), ["bbb", "ccc"])
        self.assertEqual(cache, {"aaa": "https://cached/a.jpg", "bbb": "https://new/bbb.jpg",
                                 "ccc": "https://new/ccc.jpg"})

    def test_rate_limit_stops_early_and_keeps_what_it_found(self):
        def art_for(track):
            if track == "ccc":
                raise publish.RateLimited()
            return f"https://new/{track}.jpg"
        with sandbox() as root, quiet():
            make_season(root / "data" / "season1", [ROUND])
            with mock.patch.object(publish, "art_for", side_effect=art_for), mock.patch("time.sleep"):
                publish.refresh_art()
            cache = json.loads(publish.ART_CACHE.read_text())
        self.assertEqual(cache, {"aaa": "https://new/aaa.jpg", "bbb": "https://new/bbb.jpg"})


class AllPlayers(unittest.TestCase):
    def test_first_name_seen_for_an_id_wins(self):
        with sandbox() as root:
            make_season(root / "data" / "season1", [ROUND], players={"p1": "Ann"})
            make_season(root / "data" / "season2", [ROUND], players={"p1": "Annie", "p2": "Ben"})
            players = publish.all_players()
        self.assertEqual(players, [{"competitor_id": "p1", "name": "Ann"},
                                   {"competitor_id": "p2", "name": "Ben"}])


class Backup(unittest.TestCase):
    def run_publish(self):
        uploads = []
        with mock.patch.object(publish, "refresh_art"), \
             mock.patch.object(publish.supa, "config"), \
             mock.patch.object(publish.supa, "request"), \
             mock.patch.object(publish.supa, "upload", side_effect=lambda b, n, d, t: uploads.append((b, n))), \
             mock.patch("sys.argv", ["publish.py"]):
            publish.main()
        return [n for b, n in uploads if b == publish.EXPORT_BUCKET]

    def test_paid_for_sentiment_labels_and_art_cache_are_backed_up(self):
        with sandbox() as root, quiet():
            make_season(root / "data" / "season1", [ROUND])
            (root / "data" / "comment_sentiment.json").write_text('{"comments": {}}')
            (root / "data" / "track_art.json").write_text("{}")
            backed_up = self.run_publish()
        self.assertIn("comment_sentiment.json", backed_up)
        self.assertIn("track_art.json", backed_up)
        self.assertIn("season1/votes.csv", backed_up)

    def test_missing_local_files_are_simply_skipped(self):
        with sandbox() as root, quiet():
            make_season(root / "data" / "season1", [ROUND])
            backed_up = self.run_publish()
        self.assertNotIn("comment_sentiment.json", backed_up)
        self.assertIn("season1/votes.csv", backed_up)


def playlist_page(count):
    # the one tag publish.py reads from open.spotify.com/playlist/<id>
    return f'<html><head><meta name="music:song_count" content="{count}"/></head></html>'


def embed_page(durations):
    # open.spotify.com/embed/playlist/<id>: __NEXT_DATA__, at most 100 tracks
    data = {"props": {"pageProps": {"state": {"data": {"entity": {
        "trackList": [{"uri": f"spotify:track:t{i}", "duration": d} for i, d in enumerate(durations)]}}}}}}
    return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'


class PlaylistStats(unittest.TestCase):
    def stats(self, count, durations):
        pages = {"https://open.spotify.com/playlist/p1": playlist_page(count) if count is not None else "<html></html>",
                 "https://open.spotify.com/embed/playlist/p1": embed_page(durations) if durations is not None else "<html></html>"}
        with mock.patch.object(publish, "fetch_page", side_effect=pages.get):
            return publish.playlist_stats("p1")

    def test_up_to_100_tracks_the_running_time_is_exact(self):
        self.assertEqual(self.stats(3, [60000, 120000, 180000]), {"tracks": 3, "durationMs": 360000, "exact": True})

    def test_past_100_tracks_it_is_an_estimate_from_the_average(self):
        self.assertEqual(self.stats(300, [200000] * 100), {"tracks": 300, "durationMs": 60000000, "exact": False})

    def test_a_page_that_changed_shape_means_no_stats_not_a_crash(self):
        self.assertIsNone(self.stats(None, [60000]))
        self.assertIsNone(self.stats(3, None))
        self.assertIsNone(publish.parse_embed_durations('<script id="__NEXT_DATA__" type="application/json">{"props": {}}</script>'))

    def test_refresh_keeps_the_last_good_numbers_when_a_lookup_fails(self):
        with sandbox() as root, quiet():
            out = root / "site" / "data"
            (out / "playlists.json").write_text(json.dumps({
                "leagueWide": [{"label": "A", "url": "https://open.spotify.com/playlist/aaa?si=x"}],
                "seasons": [{"season": "Season 1", "items": [{"label": "B", "url": "https://open.spotify.com/playlist/bbb"},
                                                             {"label": "C", "url": None}]}]}))
            (out / "playlist_stats.json").write_text(json.dumps({"bbb": {"tracks": 9, "durationMs": 1, "exact": True}}))
            fresh = {"aaa": {"tracks": 2, "durationMs": 5, "exact": True}}
            with mock.patch.object(publish, "playlist_stats", side_effect=fresh.get), mock.patch("time.sleep"):
                publish.refresh_playlist_stats()
            stats = json.loads((out / "playlist_stats.json").read_text())
        self.assertEqual(stats, {"aaa": {"tracks": 2, "durationMs": 5, "exact": True},
                                 "bbb": {"tracks": 9, "durationMs": 1, "exact": True}})


if __name__ == "__main__":
    unittest.main()
