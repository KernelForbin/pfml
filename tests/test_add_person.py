"""Someone new (asked 2026-10-29; README, Someone new): the admin or a
commissioner adds a person who never played in Music League, by name, from
the Commissioner page's player lists, ticked as a Spectator. Their invite
link comes from scripts/invites.py like anyone's. The SQL runs only in the
user's rehearsal (supabase/checks/2026-10-29_add_person_rehearsal.sql) and
tests/test_live_add_person.py; the page was checked in a browser."""
import re
import unittest

from support import ROOT
from test_reminders import js_body
from test_submissions import function, read, schema

SITE = ROOT / "site"
MIG = read(ROOT / "supabase" / "migrations" / "2026-10-29_add_person.sql")
REHEARSAL = read(ROOT / "supabase" / "checks" / "2026-10-29_add_person_rehearsal.sql")
SEASONS = read(SITE / "seasons.js")


class TheDatabase(unittest.TestCase):
    def test_schema_has_the_migration(self):
        self.assertIn(MIG[MIG.index("create or replace function public.add_player("):], schema())

    def test_commissioners_only_one_name_each(self):
        add = function(schema(), "add_player")
        order = [add.index(s) for s in ("if not public.is_commissioner() then", "if char_length(body) not between 1 and 60 then",
                                        "where lower(p.name) = lower(body)) then", "insert into public.players")]
        self.assertEqual(order, sorted(order))
        # never mistaken for a Music League id
        self.assertIn("cid := 'site' || replace(gen_random_uuid()::text, '-', '');", add)
        self.assertIn("revoke all on function public.add_player(text) from public, anon;", MIG)
        self.assertIn("grant execute on function public.add_player(text) to authenticated;", MIG)

    def test_publish_never_removes_a_player(self):
        # it only adds and updates Music League's, so a newcomer stays
        publish = read(ROOT / "scripts" / "publish.py")
        self.assertNotRegex(publish, r'"DELETE"[^\n]*players')

    def test_the_rehearsal_counts_its_checks(self):
        self.assertEqual(len(re.findall(r"^  checks := checks \+ 1;", REHEARSAL, re.M)), 5)
        self.assertIn('"Rehearsal passed: 5 checks held. Nothing was kept."', REHEARSAL)


class ThePage(unittest.TestCase):
    def test_the_call(self):
        self.assertIn('client.rpc("add_player", { p_name: name })', read(SITE / "auth.js"))

    def test_on_both_player_lists(self):
        self.assertIn("checklist(d.players, d.roles) + \"</div>\" + addPersonHtml();", js_body(SEASONS, "function drawWizard() {"))
        self.assertIn("esc(rosterLine(roster)) + \"</p>\" + addPersonHtml());", js_body(SEASONS, "function fillPlayers() {"))

    def test_added_as_a_spectator_and_ticked(self):
        add = js_body(SEASONS, "function addPerson(b) {")
        self.assertIn("wizard.d.players.push(id);", add)
        self.assertIn('wizard.d.roles[id] = "spectator";', add)
        self.assertIn('var list = readRoster(form).concat([{ id: id, role: "spectator" }]), roles = {};', add)
        # the list is reloaded, so their name is there
        self.assertLess(add.index("people = null;"), add.index("return loadPeople().then("))

    def test_enter_in_the_name_adds_rather_than_saving(self):
        submit = js_body(SEASONS, "function onSubmit(ev) {")
        self.assertLess(submit.index('typing.hasAttribute("data-new-person")'), submit.index('if (ev.target.id === "cmWizardForm")'))


if __name__ == "__main__":
    unittest.main()
