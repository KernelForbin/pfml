"""scripts/publish.py: the album-art lookup and cache. Offline: Spotify's
endpoint is faked here. tests/test_live_spotify.py checks the real one."""
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


if __name__ == "__main__":
    unittest.main()
