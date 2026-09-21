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


if __name__ == "__main__":
    unittest.main()
