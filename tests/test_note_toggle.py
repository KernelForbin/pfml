"""A submitter's note: hidden until the results, unless they switch on
"Show it to voters while they vote" (supabase/migrations/
2026-10-25_note_toggle.sql; README, Commissioner extras, Notes)."""
import re
import unittest

from support import ROOT
from test_reminders import js_body
from test_submissions import function, read, schema

MIGRATION = ROOT / "supabase" / "migrations" / "2026-10-25_note_toggle.sql"
REHEARSAL = ROOT / "supabase" / "checks" / "2026-10-25_note_toggle_rehearsal.sql"
SITE = ROOT / "site"
SUBMIT = read(SITE / "submit.js")
AUTH = read(SITE / "auth.js")


class TheDatabase(unittest.TestCase):
    def setUp(self):
        self.sql = schema()
        self.tail = self.sql[self.sql.rindex("-- ---------------------------------------------------------------- notes shown when chosen"):]

    def test_the_migration_is_in_the_schema(self):
        mig = read(MIGRATION)
        self.assertIn(mig[mig.index("create table if not exists public.site_submission_notes"):], self.sql)

    def test_off_by_default(self):
        self.assertIn("in_voting     boolean not null default false", self.tail)

    def test_who_reads_a_note_and_when(self):
        policies = re.findall(r"create policy[^;]*on public\.site_submission_notes[^;]*;", self.sql)
        self.assertEqual(len(policies), 1)
        self.assertIn("for select to authenticated using (\n    public.is_member() and (\n"
                      "      public.site_round_phase(round_id) = 'finished'\n"
                      "      or (in_voting and public.site_round_phase(round_id) = 'voting')));", policies[0])
        self.assertIn("alter table public.site_submission_notes enable row level security;", self.tail)
        self.assertIn("revoke all on table public.site_submission_notes from anon, authenticated;\n"
                      "grant select on table public.site_submission_notes to authenticated;", self.tail)

    def test_the_old_column_goes_after_its_notes_move(self):
        move = self.tail.index("insert into public.site_submission_notes (submission_id, round_id, note)")
        self.assertLess(move, self.tail.index("alter table public.site_submissions drop column note;"))
        # nothing after the drop reads the column
        after = self.tail[self.tail.index("alter table public.site_submissions drop column note;"):]
        self.assertNotRegex(after, r"\bs\.note\b")

    def test_the_owner_sets_note_and_switch_while_open(self):
        fn = function(self.sql, "set_submission_note")
        self.assertIn("(p_round uuid, p_tag text, p_note text, p_in_voting boolean)", fn)
        self.assertIn("where id = p_round and votes_on_site", fn)
        self.assertIn("(closed_at is not null or now() >= closes_at)", fn)
        self.assertIn("where o.round_id = p_round and o.user_id = auth.uid() and s.tag = p_tag;", fn)
        self.assertIn("values (sid, p_round, body, coalesce(p_in_voting, false))", fn)
        self.assertIn("on conflict (submission_id) do update set note = excluded.note, in_voting = excluded.in_voting;", fn)
        self.assertIn("if body = '' then\n    delete from public.site_submission_notes where submission_id = sid;", fn)
        self.assertIn("drop function if exists public.set_submission_note(uuid, text, text);", self.tail)

    def test_the_owner_and_the_export_read_the_new_table(self):
        mine = function(self.sql, "my_submission")
        self.assertIn("coalesce(n.note, ''), coalesce(n.in_voting, false)", mine)
        self.assertIn("left join public.site_submission_notes n on n.submission_id = s.id", mine)
        export = function(self.sql, "site_rounds_export")
        self.assertIn("'note', coalesce(n.note, '')", export)
        self.assertIn("left join public.site_submission_notes n on n.submission_id = s.id", export)
        self.assertIn("public.site_round_phase(r.id) = 'finished'", export)

    def test_grants(self):
        for line in ("grant execute on function public.set_submission_note(uuid, text, text, boolean) to authenticated;",
                     "grant execute on function public.my_submission(uuid) to authenticated;",
                     "revoke all on function public.site_rounds_export() from public, anon, authenticated;",
                     "grant execute on function public.site_rounds_export() to service_role;"):
            with self.subTest(line):
                self.assertIn(line, self.tail)

    def test_the_rehearsal_counts_what_it_says(self):
        script = read(REHEARSAL)
        held = int(re.search(r'"Rehearsal passed: (\d+) checks held', script).group(1))
        self.assertEqual(script.count("checks := checks + 1;"), held)


class ThePages(unittest.TestCase):
    def test_tracks_come_without_notes_and_notes_come_as_allowed(self):
        body = AUTH.split("roundSubmissions: function (roundId) {", 1)[1].split("\n    },\n", 1)[0]
        self.assertIn('.select("id, tag, platform, track, position, title, artist, spotify_match, youtube_match")', body)
        self.assertIn('client.from("site_submission_notes").select("submission_id, note").eq("round_id", roundId)', body)
        self.assertIn('s.note = notes[s.id] || "";', body)
        self.assertIn("p_in_voting: !!inVoting", AUTH)

    def test_the_switch_starts_off_and_says_both_ways(self):
        self.assertIn('$("subNoteSwitch").innerHTML = noteSwitchHtml(false);', js_body(SUBMIT, "function resetPicker() {"))
        self.assertIn('role="switch" aria-checked="\' + !!on + \'"', js_body(SUBMIT, "function noteSwitchHtml(on) {"))
        self.assertIn('"false": "Off: it shows once the results are posted, with your name."', SUBMIT)
        self.assertIn('"true": "On: voters see it with your track, without your name, while they vote."', SUBMIT)
        self.assertIn('<div id="subNoteSwitch"></div>', read(SITE / "submit.html"))

    def test_sending_and_saving_carry_the_switch(self):
        send = js_body(SUBMIT, "function send(ev) {")
        self.assertIn('var inVoting = noteSwitchOn($("subNoteSwitch").querySelector(".sub-note-switch"));', send)
        self.assertIn("note_in_voting: !!note && inVoting", send)
        save = js_body(SUBMIT, "function saveNote(b) {")
        self.assertIn('var inVoting = noteSwitchOn(b.parentNode.querySelector(".sub-note-switch"));', save)

    def test_your_tracks_say_when_the_note_shows(self):
        mine = js_body(SUBMIT, "function renderMine(open) {")
        self.assertIn('(m.note_in_voting ? "Voters see it while they vote." : "It shows once the results are posted.")', mine)
        self.assertIn("noteSwitchHtml(m.note_in_voting)", mine)

    def test_the_switches_flip(self):
        flip = js_body(SUBMIT, "function flipNoteSwitch(b) {")
        self.assertIn('var on = b.getAttribute("aria-checked") !== "true";', flip)
        self.assertIn('b.querySelector("small").textContent = NOTE_WHEN[on];', flip)
        self.assertIn("if (flip) { flipNoteSwitch(flip); return; }", js_body(SUBMIT, "function removeTrack(ev) {"))
        self.assertIn('$("subNoteSwitch").addEventListener("click", function (ev) {', SUBMIT)

    def test_the_privacy_and_features_pages_name_the_switch_as_the_page_does(self):
        # who sees a note, and when, is a privacy promise: both pages that
        # describe it use the switch's own label, so a renamed switch shows up
        label = re.search(r"<b>(Show it to voters while they vote)</b>", js_body(SUBMIT, "function noteSwitchHtml(on) {")).group(1)
        for page in ("privacy.html", "features.html"):
            with self.subTest(page):
                self.assertIn(f"&ldquo;{label}&rdquo;", read(SITE / page))

    def test_on_is_the_magenta_track(self):
        css = read(SITE / "style.css")
        self.assertIn('.sub-note-switch[aria-checked="true"] .acct-switch { background: var(--magenta); }', css)
        self.assertIn('.sub-note-switch[aria-checked="true"] .acct-switch::after { transform: translateX(16px); }', css)


if __name__ == "__main__":
    unittest.main()
