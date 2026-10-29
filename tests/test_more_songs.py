"""More than one song a round, and downvotes (README, More songs and
downvotes): commissioners, stage 3. The database rules as text (there's no
Postgres here; supabase/checks/2026-10-25_more_songs_rehearsal.sql plays them
in the real database and rolls back), the stats build on made-up rounds, and
the page wiring (the pages were checked in a browser)."""
import json
import re
import unittest

from support import ROOT, build, quiet, sandbox
from test_reminders import js_body
from test_submissions import function, read, schema

SITE = ROOT / "site"
MIGRATION = ROOT / "supabase" / "migrations" / "2026-10-25_more_songs.sql"
REHEARSAL = ROOT / "supabase" / "checks" / "2026-10-25_more_songs_rehearsal.sql"


class TheDatabase(unittest.TestCase):
    def setUp(self):
        self.sql = schema()

    def test_the_migration_is_the_end_of_the_schema(self):
        mig = read(MIGRATION)
        self.assertIn(mig[mig.index("alter table public.site_seasons add column if not exists songs_per_round"):], self.sql)

    def test_every_existing_round_keeps_one_song_and_no_downvotes(self):
        for table in ("site_seasons", "site_rounds"):
            with self.subTest(table):
                self.assertIn(f"alter table public.{table} add column if not exists songs_per_round smallint not null default 1;", self.sql)
                self.assertIn(f"alter table public.{table} add column if not exists downvotes smallint not null default 0;", self.sql)
                self.assertIn(f"alter table public.{table} add column if not exists max_down_per_track smallint not null default 0;", self.sql)
                self.assertIn("songs_per_round between 1 and 5 and downvotes between 0 and 20 and max_down_per_track between 0 and downvotes);",
                              self.sql.split(f"alter table public.{table} add constraint {table}_more_songs check (", 1)[1].split("\n", 2)[1])

    def test_old_rules_are_found_by_what_they_are_not_a_guessed_name(self):
        # unnamed in the original tables: a guessed name would miss silently
        # and leave one track a player, or no downvotes, in force
        self.assertIn("where conrelid = 'public.site_submission_owners'::regclass and contype = 'u' loop", self.sql)
        self.assertIn("where conrelid = 'public.site_votes'::regclass and contype = 'c' loop", self.sql)
        self.assertNotIn("drop constraint if exists site_submission_owners_round_id_user_id_key", self.sql)

    def test_submitting_up_to_the_rounds_songs(self):
        fn = function(self.sql, "submit_track")
        self.assertIn("if r.songs_per_round = 1 and have > 0 then", fn)
        self.assertIn("if have >= r.songs_per_round then", fn)
        # the limit is checked before a new track goes in, not on a swap
        self.assertLess(fn.index("    return new_tag;\n  end if;"), fn.index("if have >= r.songs_per_round then"))
        self.assertLess(fn.index("if have >= r.songs_per_round then"), fn.index("insert into public.site_submissions"))
        # the round row is locked first, so two at once can't both get in
        self.assertLess(fn.index("for update;"), fn.index("select count(*) into have"))

    def test_taking_one_back(self):
        fn = function(self.sql, "withdraw_track")
        self.assertIn("o.round_id = p_round and o.user_id = auth.uid() and s.tag = p_tag;", fn)
        self.assertIn("(closed_at is not null or now() >= closes_at)", fn)
        self.assertIn("grant execute on function public.withdraw_track(uuid, text) to authenticated;", self.sql)
        self.assertIn("select not exists (select 1 from public.site_submissions s", function(self.sql, "my_submission_described"))

    def test_how_many_songs_is_fixed_once_a_round_opens(self):
        self.assertIn("update public.site_rounds set songs_per_round = s.songs_per_round\n   where season_key = p_key and now() < opens_at;",
                      function(self.sql, "update_site_season"))

    def test_accelerated_waits_for_every_song(self):
        self.assertIn("< r.songs_per_round) then", function(self.sql, "site_round_finish_early"))

    def test_the_old_ballot_rule_stays_shut(self):
        self.assertIn("revoke all on function public.ballot_problem(int, int, int, int, int[], boolean[]) from public, anon, authenticated;", self.sql)
        self.assertNotRegex(self.sql, r"grant execute on function public\.ballot_problem\(")

    def test_seasons_pass_it_all_on(self):
        for name in ("create_site_season", "add_site_season_round"):
            with self.subTest(name):
                self.assertIn("songs_per_round, downvotes, max_down_per_track, services, repeat_rule)", function(self.sql, name))

    def test_the_rehearsal_keeps_nothing_and_plays_the_real_role(self):
        script = read(REHEARSAL)
        self.assertTrue(script.rstrip().endswith("raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;\nend $$;"))
        self.assertNotRegex(script, r"(?i)\bcommit\b(?! drop)")
        self.assertIn("execute 'set local role authenticated';", script)
        self.assertEqual(script.count("checks := checks + 1;"),
                         int(re.search(r"Rehearsal passed: (\d+) checks held", script).group(1)))


# Ann sends two tracks; Ben one; Eve one and doesn't vote. Ben downvotes
# Eve's track, so with the round's penalty she keeps only that: -2.
TWO_SONGS = {
    "id": "two-r1", "season_key": "season4", "name": "Two Songs", "prompt": "", "created_at": "2026-11-01T00:00:00Z",
    "voting_ended_at": "2026-11-08T00:00:00Z", "spotify_playlist": None, "point_budget": 8, "nonvoters_keep_points": False,
    "submissions": [
        {"id": "a1", "tag": "A2", "platform": "youtube", "track": "aaaaaaaaaa1", "title": "Ann One", "artist": "X", "spotify_match": None, "position": 1, "submitter": "p1"},
        {"id": "a2", "tag": "B3", "platform": "youtube", "track": "aaaaaaaaaa2", "title": "Ann Two", "artist": "X", "spotify_match": None, "position": 2, "submitter": "p1"},
        {"id": "b1", "tag": "C4", "platform": "youtube", "track": "bbbbbbbbbb1", "title": "Ben One", "artist": "Y", "spotify_match": None, "position": 3, "submitter": "p2"},
        {"id": "e1", "tag": "D5", "platform": "youtube", "track": "eeeeeeeeee1", "title": "Eve One", "artist": "Z", "spotify_match": None, "position": 4, "submitter": "p5"},
    ],
    "votes": [
        {"submission": "a1", "voter": "p2", "points": 5, "comment": "", "cast_at": "2026-11-02T00:00:00Z"},
        {"submission": "a2", "voter": "p2", "points": 3, "comment": "", "cast_at": "2026-11-02T00:00:00Z"},
        {"submission": "e1", "voter": "p2", "points": -2, "comment": "", "cast_at": "2026-11-02T00:00:00Z"},
        {"submission": "b1", "voter": "p1", "points": 4, "comment": "", "cast_at": "2026-11-03T00:00:00Z"},
        {"submission": "e1", "voter": "p1", "points": 4, "comment": "", "cast_at": "2026-11-03T00:00:00Z"},
    ],
}
NAMES = {"p1": "Ann", "p2": "Ben", "p5": "Eve"}


def rounds_of(n):
    """n copies of TWO_SONGS as separate rounds, a day apart."""
    out = []
    for i in range(n):
        r = json.loads(json.dumps(TWO_SONGS))
        r["id"] = f"two-r{i + 1}"
        r["created_at"] = f"2026-11-{i + 1:02d}T00:00:00Z"
        for s in r["submissions"]:
            s["id"] += f"-{i}"
            s["track"] = str(i) + s["track"][1:]
        for v in r["votes"]:
            v["submission"] += f"-{i}"
        out.append(r)
    return out


class InTheStats(unittest.TestCase):
    def build(self, n=1):
        with sandbox() as root, quiet():
            folder = root / "data" / "season4"
            folder.mkdir(parents=True)
            (folder / build.SITE_ROUNDS_FILE).write_text(json.dumps({"rounds": rounds_of(n), "players": NAMES}), encoding="utf-8")
            data, _ = build.build_season(folder, "season4", "Season 4")
        return data

    def test_a_non_voter_keeps_only_their_downvotes(self):
        eve = next(s for s in self.build()["rounds"][0]["songs"] if s["title"] == "Eve One")
        self.assertEqual(eve["points"], -2)
        self.assertEqual(eve["forfeit"], {"earned": 2})

    def test_a_round_is_won_once_and_counted_once(self):
        data = self.build()
        ann = next(p for p in data["standings"] if p["id"] == "p1")
        self.assertEqual((ann["points"], ann["roundsWon"], ann["podiums"], ann["submissions"]), (8, 1, 1, 2))
        with quiet():
            career = build.build_career([data])
        ann = next(p for p in career["players"] if p["id"] == "p1")
        self.assertEqual(ann["rounds"], 1)
        self.assertEqual(ann["roundFinishes"], {"first": 1, "second": 0, "third": 0})

    def test_two_tracks_tied_first_win_one_round(self):
        tied = json.loads(json.dumps(TWO_SONGS))
        for v in tied["votes"]:
            if v["voter"] == "p2" and v["submission"] in ("a1", "a2"):
                v["points"] = 4
        with sandbox() as root, quiet():
            folder = root / "data" / "season4"
            folder.mkdir(parents=True)
            (folder / build.SITE_ROUNDS_FILE).write_text(json.dumps({"rounds": [tied], "players": NAMES}), encoding="utf-8")
            data, _ = build.build_season(folder, "season4", "Season 4")
        places = {s["title"]: s["place"] for s in data["rounds"][0]["songs"]}
        self.assertEqual((places["Ann One"], places["Ann Two"], places["Ben One"]), (1, 1, 1))
        ann = next(p for p in data["standings"] if p["id"] == "p1")
        self.assertEqual((ann["roundsWon"], ann["podiums"]), (1, 1))

    def test_taste_counts_a_round_not_a_track(self):
        data = self.build(build.MIN_PAIR_OPPORTUNITIES)
        pair = next(t for t in data["taste"] if t["voterId"] == "p2" and t["submitterId"] == "p1")
        self.assertEqual(pair["chances"], build.MIN_PAIR_OPPORTUNITIES)
        self.assertEqual(pair["perRound"], 8)


class ThePages(unittest.TestCase):
    def setUp(self):
        self.submit = read(SITE / "submit.js")
        self.voting = read(SITE / "voting.js")

    def test_your_tracks_each_with_remove(self):
        mine = js_body(self.submit, "function renderMine(open) {")
        self.assertIn("$(\"subMineEmbed\").innerHTML = list.map(function (m) {", mine)
        self.assertIn("(n > 1 && open ? '<button type=\"button\" class=\"sub-btn sub-btn-quiet sub-remove\" data-tag=\"' + esc(m.tag) + '\">Remove</button>' : \"\")", mine)
        self.assertIn('$("subMineActions").hidden = n > 1 || !open || state.changing;', mine)
        self.assertIn('if (open && state.role !== "spectator" && (state.mine.length < songsOf(r) || state.changing)) renderForm();',
                      js_body(self.submit, "function render() {"))
        remove = js_body(self.submit, "function removeTrack(ev) {")
        self.assertIn("api().withdrawTrack(state.round.id, tag)", remove)
        self.assertLess(remove.index("window.confirm("), remove.index("api().withdrawTrack("))

    def test_the_note_says_what_can_change_only_while_it_can(self):
        # found in the browser: "you can remove one" showed after the close
        mine = js_body(self.submit, "function renderMine(open) {")
        self.assertIn('$("subMineNote").textContent = !open ? (n === 1 ? "Your track in this round." : "Your " + list.length + " tracks in this round.")', mine)

    def test_a_negative_score_shows_a_minus_sign(self):
        self.assertIn('(res.points < 0 ? "−" + (-res.points) : res.points)', js_body(self.voting, "function resultRow(r, item, rank, votes, names) {"))

    def test_one_song_a_round_still_swaps(self):
        send = js_body(self.submit, "function send(ev) {")
        self.assertIn("state.mine = songsOf(r) === 1 ? [entry] : state.mine.concat([entry]);", send)
        form = js_body(self.submit, "function renderForm() {")
        self.assertIn("swapping = n === 1 && have > 0;", form)

    def test_no_points_on_any_of_your_tracks(self):
        self.assertIn("function own(s) { return state.mineTags.indexOf(s.tag) !== -1; }", self.voting)
        self.assertTrue(js_body(self.voting, "function controls(s) {").lstrip().startswith(
            "if (own(s)) return '<span class=\"vt-own\">Your track</span>';"))
        entries = js_body(self.voting, "function entries() {")
        self.assertIn("points: own(s) ? 0 : (state.points[s.id] || 0)", entries)
        self.assertIn("}).filter(function (v) { return v.points !== 0 || v.comment; });", entries)

    def test_downvotes_on_the_ballot(self):
        click = js_body(self.voting, "function onBallotClick(ev) {")
        self.assertIn("state.points[id] = Math.max(-(r.max_down_per_track || 0), Math.min(r.max_per_track, pts + (act === \"plus\" ? 1 : -1)));", click)
        refresh = js_body(self.voting, "function refreshBallot() {")
        self.assertIn('li.querySelector(\'[data-act="minus"]\').disabled = pts <= 0 && (pts <= -(r.max_down_per_track || 0) || downLeft <= 0);', refresh)
        self.assertIn("$(\"vtSubmit\").disabled = left !== 0 || downLeft < 0 || unchanged;", refresh)
        self.assertIn("return sum + Math.max(state.points[id] || 0, 0);", js_body(self.voting, "function spent() {"))

    def test_a_voter_is_counted_once(self):
        self.assertIn("submitters = submitters.filter(function (id, i) { return submitters.indexOf(id) === i; });",
                      js_body(self.voting, "function votedLine(voters, submitters, names) {"))

    def test_the_banner_counts_a_player_in_once_all_are(self):
        count = js_body(read(SITE / "app.js"), "function bannerCount(round) {")
        self.assertIn("var done = players.filter(function (p) { return sent[p.id] >= n; }).length;", count)

    def test_the_setup_sends_them(self):
        seasons = read(SITE / "seasons.js")
        self.assertIn("songs_per_round: d.songs_per_round, downvotes: d.downvotes, max_down_per_track: d.max_down_per_track,",
                      js_body(seasons, "function create() {"))
        self.assertIn('if (t && t.name === "downvotes") {', js_body(seasons, "function onWizardInput(ev) {"))
        self.assertNotIn("come in the next update", seasons)

    def test_the_round_form_can_set_downvotes(self):
        read_admin = js_body(self.voting, "function readAdmin(r, closesAt) {")
        self.assertIn("if (!down) downMax = 0;", read_admin)
        self.assertIn("downvotes: down, max_down_per_track: downMax", read_admin)


if __name__ == "__main__":
    unittest.main()
