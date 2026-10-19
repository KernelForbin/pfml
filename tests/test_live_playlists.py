"""LIVE TEST: the round-playlist lookups against the real Spotify, YouTube and
SoundCloud. Read-only: it looks tracks up and searches; it never creates,
changes or deletes a playlist.

Skipped unless PFML_LIVE=1. The SoundCloud check needs nothing else; the
Spotify and YouTube ones also need the keys in .env (README, Submissions on
the site) and skip without them. Run it whenever scripts/round_playlists.py's
lookups or matching change, and once after the accounts are first connected:

    PFML_LIVE=1 python -m unittest discover -s tests -p test_live_playlists.py -v

The tracks are well-known public releases, not anything from the league."""
import os
import unittest

import support  # noqa: F401  (puts scripts/ on the path)
import round_playlists as rp  # noqa: E402

LIVE = os.environ.get("PFML_LIVE") == "1"
SPOTIFY_TRACK = "4uLU6hMCjMI75M1A2tKUQC"   # Rick Astley, "Never Gonna Give You Up"
YOUTUBE_VIDEO = "dQw4w9WgXcQ"              # the same, its official video


def has_keys(*names):
    rp.supa._load_env_file()
    return all(os.environ.get(n) for n in names)


@unittest.skipUnless(LIVE, "live network test; set PFML_LIVE=1 to run")
class LiveSoundCloud(unittest.TestCase):
    def test_oembed_still_names_the_track_and_artist(self):
        info = rp.soundcloud_info("forss/flickermood")
        self.assertEqual(info, {"title": "Flickermood", "artist": "Forss", "seconds": None})


@unittest.skipUnless(LIVE and has_keys("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SPOTIFY_REFRESH_TOKEN"),
                     "live; needs PFML_LIVE=1 and the Spotify keys in .env")
class LiveSpotify(unittest.TestCase):
    def test_a_track_looks_up_and_finds_itself(self):
        sp = rp.Spotify()
        info = sp.track(SPOTIFY_TRACK)
        self.assertEqual(info["artist"], "Rick Astley")
        self.assertGreater(info["seconds"], 200)
        verdict, cand = rp.best(info, sp.search(info["title"], info["artist"]))
        self.assertEqual(verdict, "sure", "matching can't find a track by its own title")


@unittest.skipUnless(LIVE and has_keys("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"),
                     "live; needs PFML_LIVE=1 and the YouTube keys in .env")
class LiveYouTube(unittest.TestCase):
    def test_a_video_looks_up_and_search_finds_a_copy(self):
        yt = rp.YouTube()
        info = yt.videos([YOUTUBE_VIDEO])[YOUTUBE_VIDEO]
        self.assertIn("Rick Astley", info["artist"] + info["channel"])
        found = yt.search("Never Gonna Give You Up", "Rick Astley")
        self.assertTrue(found, "search found nothing")
        self.assertTrue(all(c.get("seconds") for c in found), "durations missing from videos.list")


if __name__ == "__main__":
    unittest.main()
