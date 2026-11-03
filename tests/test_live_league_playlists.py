"""LIVE TEST: scripts/league_playlists.py's reads against the real Spotify.
Read-only: it reads the league's playlists; it never adds, changes or
removes anything.

Skipped unless PFML_LIVE=1, and without the Spotify keys in .env or Home's
site/data/playlists.json (both local only). Run it whenever
league_playlists.py's reading of Spotify changes:

    PFML_LIVE=1 python -m unittest discover -s tests -p test_live_league_playlists.py -v
"""
import json
import os
import unittest

import support  # noqa: F401  (puts scripts/ on the path)
import build  # noqa: E402
import league_playlists as lp  # noqa: E402
import round_playlists as rp  # noqa: E402

LIVE = os.environ.get("PFML_LIVE") == "1"
CONFIG = build.OUT_DIR / lp.PLAYLISTS_FILE


def ready():
    rp.supa._load_env_file()
    keys = all(os.environ.get(n) for n in ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SPOTIFY_REFRESH_TOKEN"))
    return LIVE and keys and CONFIG.exists()


@unittest.skipUnless(ready(), "live; needs PFML_LIVE=1, the Spotify keys in .env and site/data/playlists.json")
class LiveLeaguePlaylists(unittest.TestCase):
    def test_the_league_wide_playlists_read_as_tracks_with_names(self):
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        found = lp.find_playlists(config, None)
        self.assertEqual(set(found), {lp.ALL_TRACKS, lp.ALL_PODIUM}, "both still linked on Home")
        sp = rp.Spotify()
        for kind, (label, playlist) in found.items():
            ids, songs = lp.playlist_items(sp, playlist)
            # rows still carry the track as "item", with a name and artists
            self.assertGreater(len(ids), 100, label)
            self.assertEqual(len(ids), len(songs))
            self.assertTrue(all(len(i) == 22 for i in ids), label)
            self.assertTrue(all(title and artists for title, artists in songs), label)
