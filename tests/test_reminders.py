"""Reminders (README, Reminders): app notifications now, email built and
dormant. The database rules as text (there's no Postgres here;
supabase/checks/2026-10-25_reminders_rehearsal.sql runs them in the real
database and rolls back), the send-reminders Edge Function as text (there's
no Deno here either), the service worker and the page wiring. The push
encryption itself (the block between index.ts's webpush markers, taken out
as it stands) was run in a browser on 2026-10-25 against
RFC 8291's worked example (Section 5, Appendix A) and matched byte for byte,
with a fresh message decrypting back and the VAPID signature verifying."""
import json
import re
import unittest

from support import ROOT
from test_submissions import block, function, read, schema

SITE = ROOT / "site"
FN = ROOT / "supabase" / "functions" / "send-reminders"
MIGRATION = ROOT / "supabase" / "migrations" / "2026-10-25_reminders.sql"
MEMBER_CALLS = {"save_push_subscription": "text, text, text", "remove_push_subscription": "text",
                "my_push_subscriptions": "", "set_email_reminders": "boolean",
                "my_notification_choices": "", "set_notification_choice": "text, boolean"}
SENDER_CALLS = {"reminders_claim": "text[]", "forget_push_endpoint": "text", "email_reminders_off": "uuid", "inbox_claim": ""}


def js_body(js, signature, indent="  "):
    return js.split(signature, 1)[1].split(f"\n{indent}}}\n", 1)[0]


class TheDatabase(unittest.TestCase):
    def setUp(self):
        self.sql = schema()
        self.claim = function(self.sql, "reminders_claim")

    def test_schema_has_what_the_migration_adds(self):
        migration = read(MIGRATION)
        self.assertIn(migration[migration.index("-- One row per phone or browser"):], self.sql)

    def test_the_tables_are_reached_only_through_the_functions(self):
        for table in ("push_subscriptions", "reminder_settings", "reminders_sent", "inbox_notified"):
            with self.subTest(table):
                self.assertIn(f"alter table public.{table} enable row level security;", self.sql)
                self.assertIn(f"revoke all on table public.{table} from anon, authenticated;", self.sql)
                self.assertNotRegex(self.sql, rf"create policy[^;]*on public\.{table}\b")
        for path in SITE.glob("*.js"):
            self.assertNotRegex(path.read_text(encoding="utf-8"), r'from\("(push_subscriptions|reminder_settings|reminders_sent|inbox_notified)"\)')

    def test_members_call_their_own_and_only_the_sender_calls_the_rest(self):
        for name, args in MEMBER_CALLS.items():
            with self.subTest(name):
                self.assertIn(f"revoke all on function public.{name}({args}) from public, anon;", self.sql)
                self.assertIn(f"grant execute on function public.{name}({args}) to authenticated;", self.sql)
        for name, args in SENDER_CALLS.items():
            with self.subTest(name):
                self.assertIn(f"revoke all on function public.{name}({args}) from public, anon, authenticated;", self.sql)
                self.assertIn(f"grant execute on function public.{name}({args}) to service_role;", self.sql)

    def test_a_member_only_ever_touches_their_own_devices(self):
        self.assertIn("if not public.is_member() then", function(self.sql, "save_push_subscription"))
        self.assertIn("values (p_endpoint, auth.uid(), p_p256dh, p_auth)", function(self.sql, "save_push_subscription"))
        self.assertIn("where endpoint = p_endpoint and user_id = auth.uid();", function(self.sql, "remove_push_subscription"))
        self.assertIn("where public.is_member();", function(self.sql, "my_notification_choices"))
        self.assertIn("if not public.is_member() then", function(self.sql, "set_notification_choice"))
        self.assertIn("where s.user_id = auth.uid() and public.is_member();", function(self.sql, "my_push_subscriptions"))

    def test_each_reminder_is_claimed_once_before_it_is_sent(self):
        self.assertIn("primary key (round_id, kind, user_id, channel)", block(self.sql, "create table if not exists public.reminders_sent"))
        self.assertIn("insert into public.reminders_sent (round_id, kind, user_id, channel)", self.claim)
        self.assertIn("on conflict do nothing", self.claim)

    def test_who_gets_what(self):
        # a round opened before reminders existed isn't announced late; a
        # round scheduled ahead is announced when it opens, not when it was
        # made (seasons on the site, 2026-10-25)
        self.assertIn("where r.phase = 'submitting' and r.opens_at > now() - interval '6 hours'", self.claim)
        self.assertIn("r.playlists_built_at > now() - interval '12 hours'", self.claim)
        # voting: only players with a track who haven't voted (the user's call,
        # 2026-10-25), and the round's Spectators who haven't (2026-10-29)
        self.assertIn("join (select o.round_id, o.user_id from public.site_submission_owners o\n            union\n", self.claim)
        self.assertIn("where public.site_round_role(x.id, p.competitor_id) = 'spectator') w on w.round_id = r.id", self.claim)
        self.assertIn("and not exists (select 1 from public.site_votes v where v.round_id = r.id and v.user_id = w.user_id)", self.claim)
        self.assertIn("where r.phase = 'voting'", self.claim)
        # only the latest reminder that's passed, and none from before voting opened
        self.assertIn("where t.due <= now() and t.due >= r.voting_opened\n         order by t.due desc limit 1", self.claim)
        for kind, due in (("vote_halfway", "r.voting_opened + (r.voting_closes_at - r.voting_opened) / 2"),
                          ("vote_5h", "r.voting_closes_at - interval '5 hours'"),
                          ("vote_2h", "r.voting_closes_at - interval '2 hours'"),
                          ("vote_1h", "r.voting_closes_at - interval '1 hour'")):
            self.assertIn(f"('{kind}', {due})", self.claim)

    def test_a_channel_only_when_the_sender_has_it_and_the_member_can_get_it(self):
        self.assertIn("where 'push' = any(p_channels)\n       and exists (select 1 from public.push_subscriptions s where s.user_id = t.user_id)", self.claim)
        self.assertIn("where 'email' = any(p_channels)", self.claim)
        self.assertIn("coalesce((select rs.email_on from public.reminder_settings rs where rs.user_id = t.user_id), true)", self.claim)

    def test_the_rehearsal_keeps_nothing(self):
        script = read(ROOT / "supabase" / "checks" / "2026-10-25_reminders_rehearsal.sql")
        self.assertTrue(script.rstrip().endswith("raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;\nend $$;"))
        self.assertNotRegex(script, r"(?i)\bcommit\b(?! drop)")
        self.assertNotIn("https://fcm.", script)

    def test_the_timer_setup_holds_no_secret(self):
        setup = read(ROOT / "supabase" / "setup" / "reminders_cron.sql")
        self.assertIn("select vault.create_secret('PASTE_THE_REMINDERS_SECRET', 'reminders_secret'", setup)
        self.assertIn("(select decrypted_secret from vault.decrypted_secrets where name = 'reminders_secret')", setup)
        self.assertIn("cron.schedule('pfml-reminders', '*/5 * * * *'", setup)
        self.assertNotRegex(setup, r"[A-Za-z0-9_-]{32,}(?<!PASTE_THE_REMINDERS_SECRET)'")


class TheSender(unittest.TestCase):
    def setUp(self):
        self.ts = read(FN / "index.ts")
        # the push code, between its markers: the block run in a browser
        # against RFC 8291's example
        self.wp = self.ts.split("// ---- webpush: begin ----\n", 1)[1].split("// ---- webpush: end ----", 1)[0]

    def test_one_file_and_no_libraries(self):
        # one file to paste into the dashboard, like search-tracks
        self.assertEqual([p.name for p in FN.iterdir()], ["index.ts"])
        self.assertNotRegex(self.ts, r"(?m)^import ")
        self.assertNotRegex(self.ts, r"https://(esm\.sh|deno\.land|cdn\.)|npm:|jsr:")

    def test_every_caller_is_checked_and_anyone_else_is_refused(self):
        serve = self.ts.split("Deno.serve(", 1)[1]
        self.assertIn('if (same(req.headers.get("x-reminders-secret") ?? "", Deno.env.get("REMINDERS_SECRET") ?? "")) return await runDue();', serve)
        self.assertIn('if (body.test === true && authorization && authorization.startsWith("Bearer ")) {', serve)
        self.assertTrue(serve.rstrip().endswith('return new Response(JSON.stringify({ error: "not allowed" }), { status: 401, headers: { ...CORS, "Content-Type": "application/json" } });\n});'))
        same = js_body(self.ts, "function same(a: string, b: string): boolean {", "")
        self.assertIn("if (!a || !b || a.length !== b.length) return false;", same)
        self.assertIn("diff |= a.charCodeAt(i) ^ b.charCodeAt(i);", same)

    def test_a_test_goes_only_to_the_callers_own_devices(self):
        test = js_body(self.ts, "async function test(authorization: string): Promise<Response> {", "")
        self.assertIn('rpc("my_push_subscriptions", {}, authorization)', test)
        self.assertNotIn("reminders_claim", test)

    def test_claimed_first_then_sent_and_email_only_once_it_has_a_key(self):
        run = js_body(self.ts, "async function runDue(): Promise<Response> {", "")
        self.assertIn('...(Deno.env.get("RESEND_API_KEY") && Deno.env.get("REMINDERS_FROM") ? ["email"] : [])', run)
        self.assertIn('...(jwk ? ["push"] : [])', run)
        self.assertLess(run.index('rpc("reminders_claim"'), run.index("pushTo("))

    def test_a_device_thats_gone_is_forgotten(self):
        push = js_body(self.ts, "async function pushTo(subs: Sub[], msg: unknown, jwk: JsonWebKey): Promise<number> {", "")
        self.assertIn('if (status === 404 || status === 410) await rpc("forget_push_endpoint", { p_endpoint: s.endpoint });', push)

    def test_the_unsubscribe_link_is_signed(self):
        unsub = js_body(self.ts, "async function unsubscribe(token: string): Promise<Response> {", "")
        self.assertIn("if (!userId || !sig || !same(sig, await signed(userId))) return page(\"That link isn't right.\", 401);", unsub)
        # without the secret it refuses rather than failing: signing with an
        # empty key throws, and the deployed function answered 500 (2026-10-25)
        no_secret = 'if (!Deno.env.get("REMINDERS_SECRET")) return page("That link isn\'t right.", 401);'
        self.assertIn(no_secret, unsub)
        self.assertLess(unsub.index(no_secret), unsub.index("await signed(userId)"))

    def test_the_message_follows_rfc_8291(self):
        self.assertIn('enc.encode("WebPush: info\\0"), uaPublic, asPublic', self.wp)
        self.assertIn('enc.encode("Content-Encoding: aes128gcm\\0"), 16', self.wp)
        self.assertIn('enc.encode("Content-Encoding: nonce\\0"), 12', self.wp)
        self.assertIn("new Uint8Array([0, 0, 16, 0, 65])", self.wp, "record size 4096, a 65-byte key")
        self.assertIn("new Uint8Array([2])", self.wp, "the last-record delimiter")
        self.assertIn('"Content-Encoding": "aes128gcm"', self.wp)


class ThePhone(unittest.TestCase):
    def setUp(self):
        self.sw = read(SITE / "sw.js")
        self.account = read(SITE / "account.js")

    def test_the_service_worker_only_shows_notifications(self):
        self.assertNotIn('addEventListener("fetch"', self.sw)
        self.assertNotRegex(self.sw, r"caches\.|importScripts")
        self.assertIn("self.registration.showNotification(", self.sw)

    def test_a_tap_only_ever_opens_this_site(self):
        self.assertIn("if (url.origin !== self.location.origin) url = new URL(self.registration.scope);", self.sw)

    def test_hidden_until_the_push_key_is_set_up(self):
        self.assertIn('$("acctBellBtn").hidden = !pushKey();', self.account)

    def test_turning_on_asks_then_registers_then_subscribes_then_saves(self):
        on = js_body(self.account, "function turnOnNotifications() {")
        order = [on.index(s) for s in ("Notification.requestPermission()", 'navigator.serviceWorker.register("sw.js")',
                                       "reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(pushKey()) })",
                                       "api().savePushSubscription(j.endpoint, j.keys.p256dh, j.keys.auth)")]
        self.assertEqual(order, sorted(order))

    def test_iphone_in_safari_is_told_to_install_first(self):
        state = js_body(self.account, "function notificationsState() {")
        self.assertTrue(state.lstrip().startswith('if (platform() === "ios" && !isApp()) return Promise.resolve("ios-browser");'))

    def test_going_live_brings_the_privacy_and_features_pages_with_it(self):
        # vapidPublicKey switches notifications on for members; the pages
        # that describe what the site does have to say so in the same change
        key = re.search(r'vapidPublicKey: "([^"]*)"', read(SITE / "config.js")).group(1)
        if key:
            self.assertRegex(read(SITE / "privacy.html"), r"(?i)notification")
            self.assertRegex(read(SITE / "features.html"), r"Notifications")
        else:
            self.assertEqual(key, "", "off until the user's setup is done")

    def test_the_api(self):
        auth = read(SITE / "auth.js")
        self.assertIn('client.rpc("save_push_subscription", { p_endpoint: endpoint, p_p256dh: p256dh, p_auth: auth })', auth)
        self.assertIn('client.functions.invoke("send-reminders", { body: { test: true } })', auth)
        self.assertIn('client.rpc("my_notification_choices").then(must)', auth)
        self.assertIn('client.rpc("set_notification_choice", { p_kind: kind, p_on: on }).then(must)', auth)


class TheBell(unittest.TestCase):
    """The bell beside the inbox (asked for 2026-10-25): this device's switch
    and a switch for each kind of notification, which are the member's own."""

    def setUp(self):
        self.account = read(SITE / "account.js")
        self.build = js_body(self.account, "function build(member) {")

    def test_in_the_top_bar_beside_the_inbox_not_in_the_menu(self):
        bell = '<button type="button" class="acct-btn acct-bell-btn" id="acctBellBtn"'
        self.assertIn(bell, self.build)
        self.assertLess(self.build.index(bell), self.build.index('id="acctInboxBtn"'))
        menu = self.build.split('id="acctMenu"', 1)[1].split("</div>\" +", 1)[0]
        self.assertNotIn("Notifications", menu)
        self.assertNotIn("acctNotifyItem", self.account)
        self.assertIn('bell: ["acctBellBtn", "acctBell"]', self.account)

    def test_a_switch_for_each_kind_and_voting_only_with_voting(self):
        for kind in ("round_open", "playlist_ready", "replies", "reactions", "voting"):
            self.assertIn(f'["{kind}", ', self.account)
        render = js_body(self.account, "function renderBell(note) {")
        self.assertIn('CHOICES.filter(function (c) { return c[0] !== "voting" || PFML.siteVoting; })', render)
        self.assertIn('data-choice="\' + c[0] + \'" role="switch" aria-checked="\' +', render)

    def test_a_switch_saves_and_goes_back_if_it_fails(self):
        click = js_body(self.account, "function onBellClick(ev) {")
        self.assertIn("api().setNotificationChoice(kind, on).catch(function (err) {", click)
        self.assertIn('b.setAttribute("aria-checked", String(!on));', click)

    def test_the_icon_shows_this_devices_state(self):
        self.assertIn('b.innerHTML = on ? BELL_ICON : BELL_OFF_ICON;', self.account)
        self.assertIn("setBellIcon(st === \"on\");", js_body(self.account, "function renderBell(note) {"))

    def test_opening_it_does_not_close_it_again(self):
        # Found in the browser 2026-10-25: opening the bell redrew its icon
        # in a microtask before the page's click-outside handler ran, which
        # then saw a detached target and closed the panel at once.
        outside = js_body(self.account, "function closeFromOutside(ev) {")
        self.assertIn("ev.composedPath ? ev.composedPath() : [ev.target]", outside)
        self.assertNotIn("ev.target.closest", outside)
        self.assertIn('if (!b || b.getAttribute("data-on") === String(on)) return;', js_body(self.account, "function setBellIcon(on) {"))

    def test_an_inbox_notification_opens_the_inbox(self):
        self.assertIn('if (/(^|&)inbox=1(&|$)/.test(location.search.slice(1))) {', self.build)
        self.assertIn('toggle("inbox");', self.build.split("inbox=1", 1)[1])
        self.assertIn('const at = { url: `${SITE}?inbox=1`, tag: "inbox" };', read(FN / "index.ts"))


class InboxNotifications(unittest.TestCase):
    def setUp(self):
        self.sql = schema()
        self.claim = function(self.sql, "inbox_claim")

    def test_the_new_migration_matches_the_schema(self):
        mig = read(ROOT / "supabase" / "migrations" / "2026-10-25_notification_choices.sql")
        for name in ("reminders_claim", "inbox_claim", "my_notification_choices", "set_notification_choice"):
            with self.subTest(name):
                # in the schema as written (reminders_claim was redefined
                # again later, by the seasons migration)
                self.assertIn(function(mig, name), self.sql)
        for line in [l for l in mig.splitlines() if l.startswith(("alter table", "revoke", "grant", "create table"))]:
            self.assertIn(line, self.sql)

    def test_what_counts_is_what_the_inbox_shows(self):
        # a comment id ends with the commenter's player id; their own don't count
        self.assertIn("join public.comment_replies r on split_part(r.comment_id, '|', 3) = e.competitor_id", self.claim)
        self.assertIn("join public.comment_reactions x on split_part(x.comment_id, '|', 3) = e.competitor_id", self.claim)
        self.assertIn("r.user_id <> e.user_id", self.claim)
        self.assertIn("x.user_id <> e.user_id", self.claim)

    def test_no_flood_and_nothing_twice(self):
        self.assertIn("cutoff - interval '1 day') as since", self.claim)
        self.assertIn("(select min(s.created_at) from public.push_subscriptions s where s.user_id = m.user_id)", self.claim)
        self.assertIn("perform pg_advisory_xact_lock(hashtext('pfml.inbox_claim'));", self.claim)
        self.assertIn("on conflict (user_id) do update set through = excluded.through;", self.claim)
        # the function returns a user_id column, so a bare user_id is a column
        self.assertIn("#variable_conflict use_column", self.claim)

    def test_each_kind_only_if_wanted(self):
        self.assertIn("where e.want_replies and", self.claim)
        self.assertIn("where e.want_reactions and", self.claim)
        claim = function(self.sql, "reminders_claim")
        self.assertIn("from chosen t", claim)
        self.assertNotIn("from targets t\n     where 'push'", claim)

    def test_only_these_six_switches(self):
        fn = function(self.sql, "set_notification_choice")
        self.assertIn("p_kind not in ('round_open', 'playlist_ready', 'replies', 'reactions', 'voting', 'announcements')", fn)
        self.assertIn("execute format('update public.reminder_settings set %I = $1 where user_id = $2', p_kind) using p_on, auth.uid();", fn)
        self.assertLess(fn.index("p_kind not in"), fn.index("execute format("))

    def test_one_notification_per_member_per_run(self):
        ts = read(FN / "index.ts")
        run = js_body(ts, "async function runDue(): Promise<Response> {", "")
        self.assertIn('rpc("inbox_claim", {})', run)
        self.assertIn("inbox += await pushTo(n.subscriptions ?? [], inboxMessage(n), jwk);", run)

    def test_the_rehearsal_keeps_nothing_and_leaves_real_phones_out(self):
        script = read(ROOT / "supabase" / "checks" / "2026-10-25_notification_choices_rehearsal.sql")
        self.assertTrue(script.rstrip().endswith("raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;\nend $$;"))
        self.assertNotRegex(script, r"(?i)\bcommit\b(?! drop)")
        self.assertEqual(script.count("where not exists (select 1 from public.push_subscriptions s where s.user_id = m.user_id)"), 3)
        self.assertNotRegex(script, r"(?i)\bdelete\b|\bdrop (table|function)\b|\btruncate\b")

    def test_the_function_file_stays_plain_ascii(self):
        # it goes through the clipboard into the dashboard
        ts = read(FN / "index.ts")
        self.assertEqual([c for c in ts if ord(c) > 127], [])


if __name__ == "__main__":
    unittest.main()
