"""LIVE TEST: talks to Spotify's real oEmbed endpoint over the network.

Skipped unless PFML_LIVE=1. The offline tests fake this endpoint, so they
can't show that Spotify still answers the request publish.py builds, or
still puts the art in "thumbnail_url". Run it whenever the album-art lookup
changes:

    PFML_LIVE=1 python -m unittest discover -s tests -p test_live_spotify.py -v

The track is a well-known public release, not anything from the league."""
import os
import unittest

from support import publish

PUBLIC_TRACK = "4uLU6hMCjMI75M1A2tKUQC"   # Rick Astley, "Never Gonna Give You Up"


@unittest.skipUnless(os.environ.get("PFML_LIVE") == "1", "live network test; set PFML_LIVE=1 to run")
class LiveSpotifyOembed(unittest.TestCase):
    def test_real_endpoint_returns_an_image_url(self):
        art = publish.art_for(PUBLIC_TRACK)
        self.assertIsNotNone(art, "no thumbnail_url: the endpoint or its response shape changed")
        self.assertTrue(art.startswith("https://"), art)


@unittest.skipUnless(os.environ.get("PFML_LIVE") == "1", "live network test; set PFML_LIVE=1 to run")
class LiveSpotifyPlaylistPages(unittest.TestCase):
    """The home page's playlist tiles read two undocumented pages; this is
    the check that they still carry what publish.py parses. Run it whenever
    the playlist stats lookup changes."""

    def test_count_and_durations_are_still_on_the_public_pages(self):
        pid = "37i9dQZF1DXcBWIGoYBM5M"   # Spotify's own Today's Top Hits, public and about 50 tracks
        stats = publish.playlist_stats(pid)
        self.assertIsNotNone(stats, "count meta or embed __NEXT_DATA__ trackList missing: a page changed")
        self.assertGreater(stats["tracks"], 0)
        self.assertGreater(stats["durationMs"], stats["tracks"] * 30000, "durations look wrong")


if __name__ == "__main__":
    unittest.main()
