-- A rehearsal of the commissioner tools, run by the real database and then
-- undone: nothing it does is kept. Run it in the Supabase SQL Editor after
-- supabase/migrations/2026-11-25_commissioner_tools.sql (README, Commissioner
-- tools). It always ends in an error, on purpose, because an error rolls
-- everything back:
--
--   "Rehearsal passed: 17 checks held. Nothing was kept."  every rule held
--   "Rehearsal FAILED: ..."                               says which didn't
--
-- It plays the admin (A) and the first four members who are neither admin
-- nor commissioner (B, C, D and E), signed in as them and as the
-- 'authenticated' role, as the site would, through three made-up seasons:
-- season97 (Steady, for pausing), season98 (Accelerated, for sitting out)
-- and season99 (Steady with prompt rotation). The database's clock stands
-- still inside one transaction, so where a check needs time to pass, it
-- moves a round's times instead, as the database itself (signed in as
-- nobody). All of it is rolled back.

do $$
declare
  a uuid; ca text;
  b uuid; cb text;
  c uuid; cc text;
  d uuid; cd text;
  e uuid; ce text;
  stranger text;
  r1 uuid; r2 uuid; r3 uuid; r4 uuid;
  q1 uuid; q2 uuid;
  w1 uuid; w2 uuid; w3 uuid;
  c1 timestamptz; v1 timestamptz; o2 timestamptz; o3 timestamptz;
  t timestamptz;
  sb uuid; sc uuid;
  aid uuid;
  code1 text; code2 text;
  n int;
  msg text;
  checks int := 0;
begin
  select user_id, competitor_id into a, ca from public.members where role = 'admin' order by created_at limit 1;
  select user_id, competitor_id into b, cb from public.members where role = 'member' order by created_at, user_id limit 1;
  select user_id, competitor_id into c, cc from public.members where role = 'member' order by created_at, user_id offset 1 limit 1;
  select user_id, competitor_id into d, cd from public.members where role = 'member' order by created_at, user_id offset 2 limit 1;
  select user_id, competitor_id into e, ce from public.members where role = 'member' order by created_at, user_id offset 3 limit 1;
  if a is null or e is null then raise exception 'Rehearsal FAILED: it needs the admin and four other members'; end if;
  -- someone who hasn't joined, made up for the invite check
  stranger := 'rehearsal-stranger';
  insert into public.players (competitor_id, name) values (stranger, 'Rehearsal Stranger');

  -- The admin sets up the three seasons. Each first round opens now.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.create_site_season(jsonb_build_object('key', 'season97', 'name', 'Rehearsal Pause', 'timing', 'steady',
    'point_budget', 2, 'max_per_track', 2, 'first_playlist_at', now() + interval '1 day',
    'players', jsonb_build_array(ca, cb, cc),
    'rounds', jsonb_build_array(jsonb_build_object('name', 'P1'), jsonb_build_object('name', 'P2'),
                                jsonb_build_object('name', 'P3'), jsonb_build_object('name', 'P4'))));
  perform public.create_site_season(jsonb_build_object('key', 'season98', 'name', 'Rehearsal Sit Out', 'timing', 'accelerated',
    'point_budget', 2, 'max_per_track', 2, 'first_playlist_at', now() + interval '1 day',
    'players', jsonb_build_array(ca, cb, cc, jsonb_build_object('id', cd, 'role', 'spectator')),
    'rounds', jsonb_build_array(jsonb_build_object('name', 'S1'), jsonb_build_object('name', 'S2'))));
  perform public.create_site_season(jsonb_build_object('key', 'season99', 'name', 'Rehearsal Rotation', 'timing', 'steady',
    'point_budget', 2, 'max_per_track', 2, 'first_playlist_at', now() + interval '1 day',
    'players', jsonb_build_array(ca, cb, cc),
    'rounds', jsonb_build_array(jsonb_build_object('name', 'W1'), jsonb_build_object('name', 'W2'),
                                jsonb_build_object('name', 'W3'))));
  execute 'reset role';
  select id into r1 from public.site_rounds where season_key = 'season97' and name = 'P1';
  select id into r2 from public.site_rounds where season_key = 'season97' and name = 'P2';
  select id into r3 from public.site_rounds where season_key = 'season97' and name = 'P3';
  select id into r4 from public.site_rounds where season_key = 'season97' and name = 'P4';
  select id into q1 from public.site_rounds where season_key = 'season98' and name = 'S1';
  select id into q2 from public.site_rounds where season_key = 'season98' and name = 'S2';
  select id into w1 from public.site_rounds where season_key = 'season99' and name = 'W1';
  select id into w2 from public.site_rounds where season_key = 'season99' and name = 'W2';
  select id into w3 from public.site_rounds where season_key = 'season99' and name = 'W3';
  if public.site_round_phase(r1) <> 'submitting' or public.site_round_phase(r2) <> 'upcoming' then
    raise exception 'Rehearsal FAILED: the first round didn''t open now';
  end if;
  -- opened an hour ago, as a round really would have been (one opening at
  -- the very moment a pause starts is held back with the rest)
  update public.site_rounds set opens_at = now() - interval '1 hour' where id in (r1, q1, w1);
  select closes_at, voting_closes_at into c1, v1 from public.site_rounds where id = r1;
  select opens_at into o2 from public.site_rounds where id = r2;
  -- setting the seasons up logged one line each, not one per round
  select count(*) into n from public.site_activity where at = now() and action like 'Set up the season "Rehearsal%';
  if n <> 3 or exists (select 1 from public.site_activity where at = now() and action like 'Added the round%') then
    raise exception 'Rehearsal FAILED: setting up 3 seasons logged % season lines, or a line per round', n;
  end if;
  checks := checks + 1;

  -- 1. The admin pauses season97 now, until 2 days 3 hours from now: every
  --    deadline ahead moves out 3 whole days, so each keeps its time of day.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.pause_season('season97', null, null, now() + interval '2 days 3 hours', 'Rehearsal break');
  execute 'reset role';
  if (select closes_at from public.site_rounds where id = r1) <> public.site_add_days(c1, 3)
     or (select voting_closes_at from public.site_rounds where id = r1) <> public.site_add_days(v1, 3)
     or (select opens_at from public.site_rounds where id = r2) <> public.site_add_days(o2, 3) then
    raise exception 'Rehearsal FAILED: pausing didn''t move every deadline 3 days';
  end if;
  if not public.site_season_paused('season97') or public.site_season_paused('season99') then
    raise exception 'Rehearsal FAILED: the wrong season is paused';
  end if;
  if not exists (select 1 from public.site_announcements where season_key = 'season97' and body like 'Rehearsal Pause is paused until%Rehearsal break') then
    raise exception 'Rehearsal FAILED: pausing posted no announcement';
  end if;
  checks := checks + 1;

  -- 2. While it's paused, no track goes in and no deadline moves, by the
  --    page or by the Now panel's buttons; nudges wait too.
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  begin
    perform public.submit_track(r1, 'youtube', 'rehearsal0b');
    raise exception 'Rehearsal FAILED: a track went in while paused';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'The league is paused, so tracks and votes can''t go in until it resumes.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  begin
    update public.site_rounds set closes_at = closes_at + interval '1 hour' where id = r1;
    raise exception 'Rehearsal FAILED: a deadline moved while paused';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'The league is paused. Resume it before changing a deadline.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  begin
    perform public.extend_site_round(r1, 1, null);
    raise exception 'Rehearsal FAILED: the Now panel moved a deadline while paused';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'The league is paused. Resume it before changing a deadline.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  begin
    perform public.nudge_round(r1);
    raise exception 'Rehearsal FAILED: a paused round was nudged';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'The league is paused, so there''s nothing to nudge about.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  execute 'reset role';
  checks := checks + 1;

  -- 3. Members see the pause on the list and the strip; reminders hold off.
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  if not (select (x->>'paused')::boolean from jsonb_array_elements(public.site_rounds_list()) x where x->>'id' = r1::text)
     or (select count(*) from public.site_pauses() p where p.season_key = 'season97' and p.state = 'paused') <> 1 then
    raise exception 'Rehearsal FAILED: a member couldn''t see the pause';
  end if;
  execute 'reset role';
  perform set_config('request.jwt.claim.sub', '', true);
  perform set_config('request.jwt.claims', '', true);
  insert into public.push_subscriptions (endpoint, user_id, p256dh, auth)
  values ('https://push.example.test/rehearsal-b', b, repeat('A', 87), repeat('B', 22));
  if exists (select 1 from public.reminders_claim(array['push']) x where x.round_id = r1) then
    raise exception 'Rehearsal FAILED: a reminder went out for a paused round';
  end if;
  checks := checks + 1;

  -- 4. Resuming at once gives every deadline back exactly: the pause took
  --    no time at all. The reminder goes out now.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.resume_season('season97');
  execute 'reset role';
  if (select closes_at from public.site_rounds where id = r1) <> c1 or (select opens_at from public.site_rounds where id = r2) <> o2
     or public.site_season_paused('season97') then
    raise exception 'Rehearsal FAILED: resuming didn''t put the deadlines back';
  end if;
  if not exists (select 1 from public.site_announcements where season_key = 'season97' and body like 'Rehearsal Pause is back on. Round 1: P1 takes tracks until%') then
    raise exception 'Rehearsal FAILED: resuming posted no announcement';
  end if;
  perform set_config('request.jwt.claim.sub', '', true);
  perform set_config('request.jwt.claims', '', true);
  if not exists (select 1 from public.reminders_claim(array['push']) x where x.round_id = r1 and x.user_id = b and x.kind = 'round_open') then
    raise exception 'Rehearsal FAILED: the reminder didn''t go out after resuming';
  end if;
  checks := checks + 1;

  -- 5. A pause after round 1's voting: scheduled, not on yet. Once round 1
  --    finishes (an hour ago, voting closed early), time stops at that
  --    moment: the timer starts it there and holds round 2 back a year. A
  --    resume time a day and 3 hours after the stop settles it at 2 days;
  --    resuming now, an hour in, settles it at 1.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.pause_season('season97', null, r1, null, '');
  if public.site_season_paused('season97')
     or (select p.state from public.site_pauses() p where p.season_key = 'season97') <> 'scheduled' then
    raise exception 'Rehearsal FAILED: a pause after a round started early';
  end if;
  execute 'reset role';
  perform set_config('request.jwt.claim.sub', '', true);
  perform set_config('request.jwt.claims', '', true);
  update public.site_rounds set opens_at = now() - interval '3 days', closed_at = now() - interval '2 hours',
         voting_closed_at = now() - interval '1 hour' where id = r1;
  if not public.site_season_paused('season97') then
    raise exception 'Rehearsal FAILED: the pause wasn''t on once round 1 finished';
  end if;
  perform public.site_pause_tick();
  if (select started_at from public.site_season_pauses where season_key = 'season97' and ended_at is null) <> now() - interval '1 hour'
     or (select opens_at from public.site_rounds where id = r2) <> public.site_add_days(o2, 365) then
    raise exception 'Rehearsal FAILED: the timer didn''t stop time when round 1 finished';
  end if;
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.set_pause_resume('season97', now() + interval '1 day 2 hours');
  execute 'reset role';
  if (select opens_at from public.site_rounds where id = r2) <> public.site_add_days(o2, 2) then
    raise exception 'Rehearsal FAILED: a resume time didn''t settle the hold at 2 days';
  end if;
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.resume_season('season97');
  execute 'reset role';
  if (select opens_at from public.site_rounds where id = r2) <> public.site_add_days(o2, 1)
     or (select opens_at from public.site_rounds where id = r3) <> public.site_add_days((select voting_closes_at from public.site_rounds where id = r2), 0) then
    raise exception 'Rehearsal FAILED: resuming an hour in didn''t settle at 1 day';
  end if;
  checks := checks + 1;

  -- 6. A member can't pause, resume or read the log; a stranger can't call
  --    any of it.
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  begin
    perform public.pause_season('season97', null, null, null, '');
    raise exception 'Rehearsal FAILED: a member paused a season';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'Only the admin or a commissioner can pause a season.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  begin
    perform public.site_activity_list(null, 10);
    raise exception 'Rehearsal FAILED: a member read the activity log';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
  end;
  begin
    perform 1 from public.site_activity;
    raise exception 'Rehearsal FAILED: a member read the log''s table';
  exception when insufficient_privilege then
    null;
  end;
  execute 'reset role';
  execute 'set local role anon';
  begin
    perform public.resume_season('season97');
    raise exception 'Rehearsal FAILED: a stranger could resume a season';
  exception when insufficient_privilege then
    null;
  end;
  begin
    perform public.site_pauses();
    raise exception 'Rehearsal FAILED: a stranger could read the pauses';
  exception when insufficient_privilege then
    null;
  end;
  execute 'reset role';
  checks := checks + 1;

  -- 7. +1 day on the open round (round 2, opened now for the check): its
  --    deadlines and everything after move a day on the league's clock.
  perform set_config('request.jwt.claim.sub', '', true);
  perform set_config('request.jwt.claims', '', true);
  update public.site_rounds set opens_at = now() - interval '1 hour' where id = r2;
  select closes_at into c1 from public.site_rounds where id = r2;
  select opens_at into o3 from public.site_rounds where id = r3;
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  t := public.extend_site_round(r2, null, 1);
  execute 'reset role';
  if t <> public.site_add_days(c1, 1) or (select opens_at from public.site_rounds where id = r3) <> public.site_add_days(o3, 1) then
    raise exception 'Rehearsal FAILED: +1 day didn''t move the round and the ones after it';
  end if;
  checks := checks + 1;

  -- 8. A nudge reaches only those still out, then waits 6 hours.
  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.submit_track(r2, 'youtube', 'rehearsal0c');
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  n := public.nudge_round(r2);
  if n <> 2 then raise exception 'Rehearsal FAILED: the nudge went to %, not the 2 still out', n; end if;
  begin
    perform public.nudge_round(r2);
    raise exception 'Rehearsal FAILED: a round was nudged twice in a row';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'This round was nudged less than 6 hours ago.%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  execute 'reset role';
  if exists (select 1 from public.site_push_notices where kind = 'nudge_submit' and user_id = c and created_at = now())
     or not exists (select 1 from public.site_push_notices where kind = 'nudge_submit' and user_id = b and body like 'Still waiting on your track for Round 2: P2.%') then
    raise exception 'Rehearsal FAILED: the nudge reached the wrong people';
  end if;
  checks := checks + 1;

  -- 9. The nudge goes out through the announcements' sender, to B's device.
  perform set_config('request.jwt.claim.sub', '', true);
  perform set_config('request.jwt.claims', '', true);
  if not exists (select 1 from public.announcements_claim() x where x.user_id = b and x.body like 'Still waiting on your track%') then
    raise exception 'Rehearsal FAILED: the nudge wasn''t handed to the sender';
  end if;
  checks := checks + 1;

  -- 10. C asks to sit out S1 of the Accelerated season; the commissioners
  --     hear of it; B can't answer; A says yes; C can't then send a track.
  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  if public.ask_sit_out(q1, true) <> 'asked' then raise exception 'Rehearsal FAILED: the ask didn''t go in'; end if;
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  begin
    perform public.decide_sit_out(q1, cc, true);
    raise exception 'Rehearsal FAILED: a member said yes to a sit-out';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
  end;
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  perform public.decide_sit_out(q1, cc, true);
  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  begin
    perform public.submit_track(q1, 'youtube', 'rehearsal1c');
    raise exception 'Rehearsal FAILED: a player sitting out sent a track';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'You''re sitting this round out. Take that back on the Submit page first.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  execute 'reset role';
  if not exists (select 1 from public.site_push_notices where kind = 'sitout' and user_id = a and body like 'Asked to sit out Round 1: S1.%')
     or not exists (select 1 from public.site_push_notices where kind = 'sitout' and user_id = c and body like 'You''re sitting out%') then
    raise exception 'Rehearsal FAILED: the sit-out messages didn''t go';
  end if;
  checks := checks + 1;

  -- 11. Accelerated doesn't wait for C: once A and B are in, S1 closes.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.submit_track(q1, 'youtube', 'rehearsal1a');
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  perform public.submit_track(q1, 'youtube', 'rehearsal1b');
  execute 'reset role';
  if (select closed_at from public.site_rounds where id = q1) is null then
    raise exception 'Rehearsal FAILED: Accelerated waited on a player sitting out';
  end if;
  checks := checks + 1;

  -- 12. Rotation: W1 finishes with B on top, so B writes W3's prompt; A
  --     approves it, edited, and it becomes W3's name, prompt and writer.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.set_site_season_rotation('season99', true);
  perform public.submit_track(w1, 'youtube', 'rehearsal2a');
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  perform public.submit_track(w1, 'youtube', 'rehearsal2b');
  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  perform public.submit_track(w1, 'youtube', 'rehearsal2c');
  execute 'reset role';
  perform set_config('request.jwt.claim.sub', '', true);
  perform set_config('request.jwt.claims', '', true);
  update public.site_rounds set opens_at = now() - interval '3 days', closed_at = now() - interval '1 day' where id = w1;
  select s.id into sb from public.site_submissions s join public.site_submission_owners o on o.submission_id = s.id
   where s.round_id = w1 and o.user_id = b;
  select s.id into sc from public.site_submissions s join public.site_submission_owners o on o.submission_id = s.id
   where s.round_id = w1 and o.user_id = c;
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.cast_ballot(w1, jsonb_build_array(jsonb_build_object('submission', sb, 'points', 2)));
  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  perform public.cast_ballot(w1, jsonb_build_array(jsonb_build_object('submission', sb, 'points', 2)));
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  perform public.cast_ballot(w1, jsonb_build_array(jsonb_build_object('submission', sc, 'points', 2)));
  execute 'reset role';
  perform set_config('request.jwt.claim.sub', '', true);
  perform set_config('request.jwt.claims', '', true);
  update public.site_rounds set voting_closed_at = now() - interval '1 minute' where id = w1;
  perform public.site_pause_tick();
  if (select writers from public.site_prompt_turns where from_round = w1) <> array[cb]
     or (select round_id from public.site_prompt_turns where from_round = w1) <> w3 then
    raise exception 'Rehearsal FAILED: W1''s win didn''t hand B the prompt for W3';
  end if;
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  if (select count(*) from public.my_prompt_turns() x where x.round_id = w3) <> 1 then
    raise exception 'Rehearsal FAILED: B didn''t see the turn';
  end if;
  perform public.send_prompt_turn(w3, 'Rehearsal Prompt', 'Pick a song for the rehearsal.');
  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  begin
    perform public.send_prompt_turn(w3, 'Hijack', 'Not mine to write.');
    raise exception 'Rehearsal FAILED: someone else wrote B''s prompt';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
  end;
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  if (select count(*) from public.site_prompt_turns_list() x where x.round_id = w3 and x.status = 'sent') <> 1 then
    raise exception 'Rehearsal FAILED: the commissioners didn''t see the sent prompt';
  end if;
  perform public.decide_prompt_turn(w3, 'Rehearsal Prompt, edited', 'Pick a song for the rehearsal.');
  execute 'reset role';
  if (select name from public.site_rounds where id = w3) <> 'Rehearsal Prompt, edited'
     or (select array_agg(competitor_id) from public.site_round_prompters where round_id = w3) <> array[cb] then
    raise exception 'Rehearsal FAILED: approving didn''t set W3''s name and writer';
  end if;
  checks := checks + 1;

  -- 13. A round's own days: W3, not open yet, takes 4 days to submit.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.set_site_round_days(w3, 4, null);
  execute 'reset role';
  if (select closes_at from public.site_rounds where id = w3)
     <> public.site_add_days((select opens_at from public.site_rounds where id = w3), 4) then
    raise exception 'Rehearsal FAILED: W3 didn''t take its own 4 days';
  end if;
  checks := checks + 1;

  -- 14. A season's announcement, scheduled: nobody but the commissioners
  --    sees it before its time, and the sender leaves it alone till then.
  --    E isn't in season97, so never sees one meant for it.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  aid := public.post_announcement('Rehearsal: later, for season97', now() + interval '1 day', 'season97');
  perform public.edit_announcement(aid, 'Rehearsal: later, edited', now() + interval '2 days');
  perform public.post_announcement('Rehearsal: now, for season97', null, 'season97');
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  if exists (select 1 from public.site_announcements where id = aid)
     or not exists (select 1 from public.site_announcements where body = 'Rehearsal: now, for season97') then
    raise exception 'Rehearsal FAILED: B saw the wrong announcements';
  end if;
  perform set_config('request.jwt.claim.sub', e::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', e, 'role', 'authenticated')::text, true);
  if exists (select 1 from public.site_announcements where body like 'Rehearsal:%') then
    raise exception 'Rehearsal FAILED: someone outside the season saw its announcement';
  end if;
  execute 'reset role';
  perform set_config('request.jwt.claim.sub', '', true);
  perform set_config('request.jwt.claims', '', true);
  if exists (select 1 from public.announcements_claim() x where x.announcement_id = aid) then
    raise exception 'Rehearsal FAILED: a scheduled announcement went out early';
  end if;
  checks := checks + 1;

  -- 15. Invite links: the admin only, the same link again while unused, and
  --     never for someone who has joined.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  code1 := public.create_invite(stranger);
  code2 := public.create_invite(stranger);
  if code1 is null or code1 <> code2 then raise exception 'Rehearsal FAILED: a second link replaced an unused one'; end if;
  begin
    perform public.create_invite(cb);
    raise exception 'Rehearsal FAILED: a link was made for someone who joined';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
  end;
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  begin
    perform public.create_invite(stranger);
    raise exception 'Rehearsal FAILED: a member made an invite link';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'Only the admin can make invite links.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  execute 'reset role';
  checks := checks + 1;

  -- 16. The log has each of it, by who did it, and never the link itself.
  msg := 'Paused "Rehearsal Pause" until ' || public.site_when(now() + interval '2 days 3 hours');
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  select count(*) into n from public.site_activity_list(null, 200) x
   where x.at = now() and x.action in (msg, 'Resumed "Rehearsal Pause"', 'Nudged 2 players to send tracks to "P2"',
                                       'Made an invite link for Rehearsal Stranger')
     and x.who = (select p.name from public.players p where p.competitor_id = ca);
  if n <> 4 then raise exception 'Rehearsal FAILED: the log had % of the 4 lines checked', n; end if;
  if exists (select 1 from public.site_activity_list(null, 200) x where x.action like '%' || code1 || '%') then
    raise exception 'Rehearsal FAILED: the log showed an invite link';
  end if;
  execute 'reset role';
  checks := checks + 1;

  raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;
end $$;
