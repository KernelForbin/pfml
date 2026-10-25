-- A rehearsal of the bell's switches and the inbox notifications, run by the
-- real database and then undone: nothing it does is kept. Run it in the
-- Supabase SQL Editor after supabase/migrations/2026-10-25_notification_choices.sql
-- (README, Reminders). It always ends in an error, on purpose, because an
-- error rolls everything back:
--
--   "Rehearsal passed: 12 checks held. Nothing was kept."  every rule held
--   "Rehearsal FAILED: ..."                               says which didn't
--
-- It plays the first three members to join who have no device yet (so a
-- real phone never comes into it), gives them made-up devices
-- (https://push.example.invalid/...), and makes up replies and reactions on
-- made-up comments of theirs. Nothing is sent: claiming only records. All of
-- it is rolled back. now() is the same all through one run, so every
-- made-up time is set by hand, a second or so before it. The two helpers
-- below are temporary, gone when the editor's session ends.

create or replace function pg_temp.as_member(u uuid) returns void language plpgsql as $f$
begin
  perform set_config('request.jwt.claim.sub', coalesce(u::text, ''), true);
  perform set_config('request.jwt.claims', json_build_object('sub', u, 'role', 'authenticated')::text, true);
end $f$;

-- Runs q and passes only if it fails with a message like pattern.
create or replace function pg_temp.expect_error(q text, pattern text) returns void language plpgsql as $f$
begin
  execute q;
  raise exception 'Rehearsal FAILED: expected an error like "%" from: %', pattern, q;
exception when others then
  if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
  if sqlerrm not like pattern then
    raise exception 'Rehearsal FAILED: expected "%", got "%" from: %', pattern, sqlerrm, q;
  end if;
end $f$;

do $$
declare
  a uuid; b uuid; c uuid;
  ca text; cb text; cc text;
  b_name text;
  r_open uuid;
  checks int := 0;
  r record;
  n int;
begin
  select m.user_id, m.competitor_id into a, ca from public.members m
   where not exists (select 1 from public.push_subscriptions s where s.user_id = m.user_id)
   order by m.created_at, m.user_id limit 1;
  select m.user_id, m.competitor_id into b, cb from public.members m
   where not exists (select 1 from public.push_subscriptions s where s.user_id = m.user_id)
   order by m.created_at, m.user_id offset 1 limit 1;
  select m.user_id, m.competitor_id into c, cc from public.members m
   where not exists (select 1 from public.push_subscriptions s where s.user_id = m.user_id)
   order by m.created_at, m.user_id offset 2 limit 1;
  if c is null then raise exception 'Rehearsal FAILED: it needs three members with no device yet'; end if;
  select p.name into b_name from public.players p where p.competitor_id = cb;

  -- 1. The switches: all on to begin with, only the five names, members only.
  perform pg_temp.as_member(a);
  select * into r from public.my_notification_choices();
  if not (r.round_open and r.playlist_ready and r.replies and r.reactions and r.voting) then
    raise exception 'Rehearsal FAILED: every switch should start on';
  end if;
  checks := checks + 1;
  perform pg_temp.expect_error($q$select public.set_notification_choice('email_on', false)$q$, '%isn''t a notification%');
  perform pg_temp.as_member(null);
  perform pg_temp.expect_error($q$select public.set_notification_choice('replies', false)$q$, '%Only league members%');
  if exists (select 1 from public.my_notification_choices()) then
    raise exception 'Rehearsal FAILED: someone not signed in got switches back';
  end if;
  checks := checks + 1;

  -- 2. A turns off "a new round opens" and reactions; B leaves everything on.
  perform pg_temp.as_member(a);
  perform public.set_notification_choice('round_open', false);
  perform public.set_notification_choice('reactions', false);
  select * into r from public.my_notification_choices();
  if r.round_open or r.reactions or not (r.playlist_ready and r.replies and r.voting) then
    raise exception 'Rehearsal FAILED: A''s switches didn''t save as set';
  end if;
  checks := checks + 1;
  perform pg_temp.as_member(null);

  insert into public.push_subscriptions (endpoint, user_id, p256dh, auth, created_at) values
    ('https://push.example.invalid/a', a, repeat('A', 87), repeat('a', 22), now() - interval '10 seconds'),
    ('https://push.example.invalid/b', b, repeat('B', 87), repeat('b', 22), now() - interval '2 seconds'),
    ('https://push.example.invalid/c', c, repeat('C', 87), repeat('c', 22), now() - interval '10 days');

  -- 3. A new round reaches B, not A, who turned it off.
  insert into public.site_rounds (season_key, name, closes_at) values ('season99', 'Rehearsal open', now() + interval '2 days')
  returning id into r_open;
  create temp table claimed on commit drop as
    select * from public.reminders_claim(array['push']) where round_id = r_open;
  if exists (select 1 from claimed where user_id = a) or not exists (select 1 from claimed where user_id = b) then
    raise exception 'Rehearsal FAILED: the new round should reach B and not A, who turned it off';
  end if;
  checks := checks + 1;

  -- 4. On A's comment: two replies from B, one reaction from B (A has
  --    reactions off), and A's own reply. A's mark is a second back.
  insert into public.inbox_notified (user_id, through) values (a, now() - interval '1 second')
  on conflict (user_id) do update set through = excluded.through;
  insert into public.comment_replies (comment_id, user_id, body, created_at) values
    ('rehearsal|spotify:track:x|' || ca, b, 'An older reply, before the mark', now() - interval '5 seconds'),
    ('rehearsal|spotify:track:x|' || ca, b, 'First reply', now() - interval '0.8 seconds'),
    ('rehearsal|spotify:track:x|' || ca, b, 'Second reply', now() - interval '0.5 seconds'),
    ('rehearsal|spotify:track:x|' || ca, a, 'My own reply', now() - interval '0.2 seconds');
  insert into public.comment_reactions (comment_id, user_id, reaction, created_at) values
    ('rehearsal|spotify:track:x|' || ca, b, 'fire', now() - interval '0.3 seconds');
  -- On B's comment: a reaction from A, and a reply from before B turned
  -- their device on (2 seconds ago), which doesn't count.
  insert into public.comment_reactions (comment_id, user_id, reaction, created_at) values
    ('rehearsal|youtube:track:y|' || cb, a, 'heart', now() - interval '0.4 seconds');
  insert into public.comment_replies (comment_id, user_id, body, created_at) values
    ('rehearsal|youtube:track:y|' || cb, a, 'Before B had a device', now() - interval '3 seconds');
  -- On C's comment: a reply two days old. C's device is 10 days old, but
  -- nothing older than a day counts.
  insert into public.comment_replies (comment_id, user_id, body, created_at) values
    ('rehearsal|spotify:track:z|' || cc, a, 'Two days ago', now() - interval '2 days');

  create temp table told on commit drop as select * from public.inbox_claim();

  select * into r from told where user_id = a;
  if not found or r.replies <> 2 or r.reactions <> 0 then
    raise exception 'Rehearsal FAILED: A should hear of B''s 2 new replies and nothing else (got %, %)', r.replies, r.reactions;
  end if;
  checks := checks + 1;
  if r.last_kind <> 'reply' or r.last_text <> 'Second reply' or r.last_actor is distinct from b_name then
    raise exception 'Rehearsal FAILED: A''s latest should be B''s "Second reply" (got %, %, %)', r.last_kind, r.last_actor, r.last_text;
  end if;
  checks := checks + 1;
  if jsonb_array_length(r.subscriptions) <> 1 or r.subscriptions -> 0 ->> 'endpoint' <> 'https://push.example.invalid/a' then
    raise exception 'Rehearsal FAILED: A''s notice should carry A''s one device';
  end if;
  checks := checks + 1;

  select * into r from told where user_id = b;
  if not found or r.replies <> 0 or r.reactions <> 1 or r.last_kind <> 'reaction' or r.last_text <> 'heart' then
    raise exception 'Rehearsal FAILED: B should hear of A''s one reaction, and not the reply from before B''s device';
  end if;
  checks := checks + 1;

  select count(*) into n from public.comment_replies x
   where split_part(x.comment_id, '|', 3) = cc and x.user_id <> c and x.created_at > now() - interval '1 day';
  select coalesce((select replies from told where user_id = c), 0) - n into n;
  if n <> 0 then
    raise exception 'Rehearsal FAILED: C was told of a reply more than a day old';
  end if;
  checks := checks + 1;

  -- 5. Everyone's mark moves to now, so the next run tells nobody again.
  if (select count(*) from public.inbox_notified where user_id in (a, b, c) and through = now()) <> 3 then
    raise exception 'Rehearsal FAILED: the marks didn''t move to now';
  end if;
  checks := checks + 1;
  if exists (select 1 from public.inbox_claim() where user_id in (a, b, c)) then
    raise exception 'Rehearsal FAILED: the second run told someone again';
  end if;
  checks := checks + 1;

  -- 6. A member with no device is never told.
  if exists (select 1 from told t where not exists (select 1 from public.push_subscriptions s where s.user_id = t.user_id)) then
    raise exception 'Rehearsal FAILED: someone with no device was told';
  end if;
  checks := checks + 1;

  raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;
end $$;
