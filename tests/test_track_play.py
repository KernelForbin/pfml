"""A round's track list (the round page's listening section, listen.js;
the Submit page until it moved there, 2026-10-26): no
submission tags, and a play button on each track that turns to pause on
the one playing (asked 2026-10-26). The browser code isn't run here (no
Node); these hold its shape, and README, Listening demo, says how it was
checked in a browser."""
import unittest

from support import ROOT
from test_reminders import js_body

SITE = ROOT / "site"
LISTEN = (SITE / "listen.js").read_text(encoding="utf-8")
PLAYER = (SITE / "player.js").read_text(encoding="utf-8")
CSS = (SITE / "style.css").read_text(encoding="utf-8")


class NoTags(unittest.TestCase):
    def test_the_list_and_the_player_never_show_a_tag(self):
        self.assertNotIn("s.tag", js_body(LISTEN, "function drawTracks(list) {"))
        self.assertNotIn(".tag", PLAYER)

    def test_a_failed_track_is_named_by_its_place(self):
        self.assertIn('now.textContent = "Couldn’t play track " + (failedAt + 1) + " here; skipping it.";', PLAYER)


class PlayAndPause(unittest.TestCase):
    def test_every_track_starts_with_play(self):
        draw = js_body(LISTEN, "function drawTracks(list) {")
        self.assertIn("'<span class=\"sub-track-play\" aria-hidden=\"true\">' + PLAY_ICON + \"</span>\"", draw)
        self.assertIn("'aria-label=\"Play ' + esc(label) + '\" aria-current=\"false\">'", draw)
        self.assertIn("markPlaying(playing ? list.order.indexOf(playing) : -1, list.player.paused());", draw)

    def test_pause_shows_only_on_the_track_that_is_sounding(self):
        mark = js_body(LISTEN, "function markPlaying(playing, paused) {")
        self.assertIn("var on = i === playing, sounding = on && !paused;", mark)
        self.assertIn('li.querySelector(".sub-track-play").innerHTML = sounding ? PAUSE_ICON : PLAY_ICON;', mark)
        self.assertIn('b.setAttribute("aria-label", (sounding ? "Pause " : "Play ") + b.getAttribute("data-label"));', mark)
        self.assertIn('li.classList.toggle("is-playing", on);', mark)

    def test_a_tap_on_the_track_playing_pauses_or_resumes_and_any_other_plays(self):
        self.assertIn("if (list.player.playing() === list.order[i]) list.player.togglePause();\n        else list.player.playAt(i);",
                      LISTEN)
        self.assertIn("function (playing, paused) { markPlaying(playing, paused); }", LISTEN)

    def test_the_player_says_when_it_pauses_once_per_change(self):
        hooks = PLAYER.split("paused: function (p) {", 1)[1].split("\n      },", 1)[0]
        self.assertIn("var changed = p !== isPaused;", hooks)
        self.assertIn("if (changed && onTrack && index >= 0) onTrack(index, p);", hooks)
        go = js_body(PLAYER, "function go(i, automatic) {", "    ")
        self.assertIn("setPaused(false);", go)
        self.assertIn("if (onTrack) onTrack(i, false);", go)
        self.assertIn("if (onTrack) onTrack(-1, false);", js_body(PLAYER, "function stop(message) {", "    "))
        self.assertIn("togglePause: togglePause,", PLAYER)
        self.assertIn("paused: function () { return isPaused; }", PLAYER)

    def test_the_button_is_the_magenta_fill_with_white(self):
        self.assertIn("border-radius: 50%; background: var(--magenta); color: #fff;", CSS.split(".sub-track-play {", 1)[1].split("}", 1)[0])
        self.assertNotIn(".sub-tag", CSS)


if __name__ == "__main__":
    unittest.main()
