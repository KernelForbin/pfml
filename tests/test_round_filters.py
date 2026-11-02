"""Filters on a round's results page (asked 2026-11-02): "Track submitted
by" and "Comments by", each a list of the round's names with Select all
and Clear all, combining. The browser code isn't run here (no Node);
README, Filtering a round's results, says how it was checked in a browser."""
import unittest

from support import ROOT
from test_reminders import js_body

SITE = ROOT / "site"
ROUNDS = (SITE / "rounds.js").read_text(encoding="utf-8")
CSS = (SITE / "style.css").read_text(encoding="utf-8")


class WhatTheyFilter(unittest.TestCase):
    def test_each_track_and_vote_says_whose_it_is(self):
        self.assertIn("'\" data-submitter=\"' + esc(s.submitterId) + '\">'", js_body(ROUNDS, "function trackHtml(s, tiedPlaces) {"))
        self.assertIn("'\" data-voter=\"' + esc(row.voterId) + '\"'", js_body(ROUNDS, "function voteHtml(row) {"))

    def test_the_two_combine(self):
        fn = js_body(ROUNDS, "function applyFilters() {")
        # a track stays when its submitter is picked...
        self.assertIn('var keep = !byOn || !!fs.by.picked[t.getAttribute("data-submitter")];', fn)
        # ...and, with Comments by on, only picked people's comments stay,
        # and a track left with none of them goes
        self.assertIn('var ok = !fromOn || (v.classList.contains("has-comment") && !!fs.from.picked[v.getAttribute("data-voter")]);', fn)
        self.assertIn("if (fromOn && !theirs) keep = false;", fn)
        self.assertIn('t.classList.toggle("is-filtered", !keep);', fn)
        self.assertIn('v.classList.toggle("is-filtered", !ok);', fn)

    def test_hidden_by_a_class_the_cards_own_display_cant_beat(self):
        self.assertIn(".rp-track.is-filtered, .rp-vote.is-filtered { display: none; }", CSS)
        self.assertNotIn(".hidden =", js_body(ROUNDS, "function applyFilters() {"))


class TheLists(unittest.TestCase):
    def test_only_people_in_this_round_and_all_ticked_to_start(self):
        fn = js_body(ROUNDS, "function filtersFor(r) {")
        self.assertIn("r.songs.forEach(function (s) {", fn)
        self.assertIn("(s.comments || []).forEach(function (c) {", fn)
        self.assertIn("list.forEach(function (p) { picked[p.id] = true; });", fn)
        # every name ticked is no filter at all
        self.assertIn("return pickedCount(f) < f.people.length;", js_body(ROUNDS, "function filterOn(f) {"))

    def test_select_all_and_clear_all(self):
        html = js_body(ROUNDS, "function filterHtml(def) {")
        self.assertIn("'<div class=\"rp-filter-all\"><button type=\"button\" data-all=\"1\">Select all</button>'", html)
        self.assertIn("'<button type=\"button\" data-all=\"0\">Clear all</button></div>'", html)
        click = js_body(ROUNDS, "function onFilterClick(ev) {")
        self.assertIn("f.picked = {};\n      if (on) f.people.forEach(function (p) { f.picked[p.id] = true; });", click)
        self.assertIn("box.querySelectorAll('input[type=\"checkbox\"]').forEach(function (cb) { cb.checked = on; });", click)

    def test_both_filters_are_offered(self):
        self.assertIn('{ key: "by", label: "Track submitted by"', ROUNDS)
        self.assertIn('{ key: "from", label: "Comments by"', ROUNDS)
        self.assertIn('box.innerHTML = FILTERS.map(filterHtml).join("")', js_body(ROUNDS, "function renderFilters() {"))


class OnThePage(unittest.TestCase):
    def test_reapplied_after_every_redraw(self):
        tracks = js_body(ROUNDS, "function renderTracks(r) {")
        self.assertLess(tracks.index("state.host.innerHTML ="), tracks.index("applyFilters();"))
        # a vote or reaction redraws one comment, which comes back without its class
        vote = js_body(ROUNDS, "function rerenderVote(id) {")
        self.assertLess(vote.index("node.replaceWith(fresh);"), vote.index("applyFilters();"))

    def test_set_up_before_the_tracks_and_only_for_a_round_with_results(self):
        page = js_body(ROUNDS, "function renderRoundPage(d, roundId) {")
        self.assertIn("(status ? \"\" : '<div class=\"rp-filters\" id=\"rpFilters\"></div>')", page)
        self.assertLess(page.index("state.filters = filtersFor(r);\n    renderFilters();"), page.index("    renderTracks(r);\n    showTarget(target);"))

    def test_it_says_how_much_is_showing_and_offers_everything_back(self):
        fn = js_body(ROUNDS, "function applyFilters() {")
        self.assertIn('status.innerHTML = !byOn && !fromOn ? ""', fn)
        self.assertIn('<button type="button" class="rp-filter-reset" data-reset="1">Show everything</button>', fn)
        self.assertIn(".rp-filter-status:empty { display: none; }", CSS)


if __name__ == "__main__":
    unittest.main()
