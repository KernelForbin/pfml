-- A rehearsal of seasons set up on the site, run by the real database and
-- then undone: nothing it does is kept. Run it in the Supabase SQL Editor
-- after supabase/migrations/2026-10-25_seasons.sql (README, Seasons on the
-- site). It always ends in an error, on purpose, because an error rolls
-- everything back:
--
--   "Rehearsal passed: 24 checks held. Nothing was kept."  every rule held
--   "Rehearsal FAILED: ..."                               says which didn't
--
-- It plays the admin and the first three members who are neither admin nor
-- commissioner (B, C and D), signed in as them and as the 'authenticated'
-- role, as the site would. The admin, B and C play two made-up seasons
-- (season98 and season99); D isn't in either. Nobody is signed in as them and
-- nothing reaches them: the seasons, rounds, tracks, ballots and made-up
-- devices (https://push.example.invalid/...) are all rolled back.

do $$
declare
  a uuid; ca text;
  b uuid; cb text;
  c uuid; cc text;
  d uuid; cd text;
  r1 uuid; r2 uuid; r3 uuid;
  s1 uuid; s2 uuid; s3 uuid;
  q1 uuid; q2 uuid; q3 uuid;
  rr record;
  t timestamptz;
  n int;
  checks int := 0;
  ex jsonb;
begin
  select user_id, competitor_id into a, ca from public.members where role = 'admin' order by created_at limit 1;
  select user_id, competitor_id into b, cb from public.members where role = 'member' order by created_at, user_id limit 1;
  select user_id, competitor_id into c, cc from public.members where role = 'member' order by created_at, user_id offset 1 limit 1;
  select user_id, competitor_id into d, cd from public.members where role = 'member' order by created_at, user_id offset 2 limit 1;
  if a is null or d is null then raise exception 'Rehearsal FAILED: it needs the admin and three other members'; end if;

  -- 1. A member can't set up a season.
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  begin
    perform public.create_site_season('{"key": "season99"}'::jsonb);
    raise exception 'Rehearsal FAILED: a member set up a season';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'Only the admin or a commissioner%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;
  execute 'reset role';

  -- 2. The admin sets one up: never Season 3 or an existing key.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  begin
    perform public.create_site_season(jsonb_build_object('key', 'season3', 'name', 'Nope', 'rounds', jsonb_build_array(jsonb_build_object('name', 'X')),
      'players', jsonb_build_array(ca, cb), 'first_playlist_at', now() + interval '1 day'));
    raise exception 'Rehearsal FAILED: a season was set up as Season 3';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'A season set up on the site is Season 4 or later.%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;
  perform public.create_site_season(jsonb_build_object('key', 'season99', 'name', 'Rehearsal Season', 'description', 'Made up',
    'point_budget', 6, 'max_per_track', 3, 'nonvoters_keep_points', false, 'timing', 'accelerated', 'submit_days', 2, 'vote_days', 5,
    'first_playlist_at', now() + interval '1 day',
    'rounds', jsonb_build_array(jsonb_build_object('name', 'One', 'prompt', 'First'), jsonb_build_object('name', 'Two'), jsonb_build_object('name', 'Three')),
    'players', jsonb_build_array(ca, cb, cc)));
  begin
    perform public.create_site_season(jsonb_build_object('key', 'season99', 'name', 'Again', 'rounds', jsonb_build_array(jsonb_build_object('name', 'X')),
      'players', jsonb_build_array(ca, cb), 'first_playlist_at', now() + interval '1 day'));
    raise exception 'Rehearsal FAILED: the same season was set up twice';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
  end;
  checks := checks + 1;
  execute 'reset role';

  select id into r1 from public.site_rounds where season_key = 'season99' and name = 'One';
  select id into r2 from public.site_rounds where season_key = 'season99' and name = 'Two';
  select id into r3 from public.site_rounds where season_key = 'season99' and name = 'Three';

  -- 3. The rounds are laid out one after another, all voting here with the
  --    season's rules; round 1 is open now (its first playlist is a day off,
  --    less than its 2 days to submit), the others wait.
  select * into rr from public.site_rounds where id = r1;
  if rr.opens_at <> now() or rr.closes_at <> now() + interval '1 day' or not rr.votes_on_site or rr.point_budget <> 6
     or rr.max_per_track <> 3 or rr.voting_closes_at <> public.site_add_days(rr.closes_at, 5) then
    raise exception 'Rehearsal FAILED: round 1 isn''t laid out as set up';
  end if;
  checks := checks + 1;
  if (select opens_at from public.site_rounds where id = r2) <> rr.voting_closes_at
     or (select closes_at from public.site_rounds where id = r2) <> public.site_add_days(rr.voting_closes_at, 2)
     or (select opens_at from public.site_rounds where id = r3) <> (select voting_closes_at from public.site_rounds where id = r2) then
    raise exception 'Rehearsal FAILED: rounds 2 and 3 don''t follow on';
  end if;
  checks := checks + 1;
  if public.site_round_phase(r1) <> 'submitting' or public.site_round_phase(r2) <> 'upcoming' then
    raise exception 'Rehearsal FAILED: round 1 should be open and round 2 upcoming';
  end if;
  checks := checks + 1;

  -- 4. A round can't be added by hand, or open before its time, and only the
  --    players submit.
  execute 'set local role authenticated';
  begin
    insert into public.site_rounds (season_key, name, closes_at) values ('season99', 'By hand', now() + interval '1 day');
    raise exception 'Rehearsal FAILED: a round was added to the season by hand';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
  end;
  begin
    insert into public.site_rounds (season_key, name, closes_at, votes_on_site, voting_closes_at)
    values ('season98', 'Votes here', now() + interval '1 day', true, now() + interval '2 days');
    raise exception 'Rehearsal FAILED: a round opened by hand votes here';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'Only a season set up on the site votes on the site.%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;
  begin
    perform public.submit_track(r2, 'spotify', 'AAAAAAAAAAAAAAAAAAAAAA');
    raise exception 'Rehearsal FAILED: a track went into a round that hasn''t opened';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'This round hasn''t opened yet.%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;
  perform set_config('request.jwt.claim.sub', d::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', d, 'role', 'authenticated')::text, true);
  begin
    perform public.submit_track(r1, 'spotify', 'DDDDDDDDDDDDDDDDDDDDDD');
    raise exception 'Rehearsal FAILED: someone not playing submitted';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'You aren''t playing this season.%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  -- 5. Accelerated: two tracks in, still open; the third closes it at once,
  --    and round 2 keeps its time.
  t := (select opens_at from public.site_rounds where id = r2);
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  perform public.submit_track(r1, 'spotify', 'AAAAAAAAAAAAAAAAAAAAAA');
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  perform public.submit_track(r1, 'spotify', 'BBBBBBBBBBBBBBBBBBBBBB');
  if public.site_round_phase(r1) <> 'submitting' then raise exception 'Rehearsal FAILED: the round closed before everyone was in'; end if;
  checks := checks + 1;
  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  perform public.submit_track(r1, 'spotify', 'CCCCCCCCCCCCCCCCCCCCCC');
  execute 'reset role';
  if public.site_round_phase(r1) <> 'voting' or (select closed_at from public.site_rounds where id = r1) <> now()
     or (select opens_at from public.site_rounds where id = r2) <> t then
    raise exception 'Rehearsal FAILED: Accelerated should close submissions at the last track and keep round 2''s time';
  end if;
  checks := checks + 1;

  -- 6. Everyone votes: the last ballot closes voting, and the round is out
  --    for the stats, with the season's name.
  select o.submission_id into s1 from public.site_submission_owners o where o.round_id = r1 and o.user_id = a;
  select o.submission_id into s2 from public.site_submission_owners o where o.round_id = r1 and o.user_id = b;
  select o.submission_id into s3 from public.site_submission_owners o where o.round_id = r1 and o.user_id = c;
  execute 'set local role authenticated';
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  perform public.cast_ballot(r1, jsonb_build_array(jsonb_build_object('submission', s2, 'points', 3), jsonb_build_object('submission', s3, 'points', 3)));
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  perform public.cast_ballot(r1, jsonb_build_array(jsonb_build_object('submission', s1, 'points', 3), jsonb_build_object('submission', s3, 'points', 3)));
  if public.site_round_phase(r1) <> 'voting' then raise exception 'Rehearsal FAILED: voting closed before everyone had voted'; end if;
  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  perform public.cast_ballot(r1, jsonb_build_array(jsonb_build_object('submission', s1, 'points', 3), jsonb_build_object('submission', s2, 'points', 3)));
  execute 'reset role';
  if public.site_round_phase(r1) <> 'finished' or (select voting_closed_at from public.site_rounds where id = r1) <> now() then
    raise exception 'Rehearsal FAILED: the last ballot should close voting';
  end if;
  checks := checks + 1;
  ex := public.site_rounds_export();
  if not exists (select 1 from jsonb_array_elements(ex->'rounds') x where x->>'id' = r1::text and (x->>'created_at')::timestamptz = now())
     or ex->'seasons'->>'season99' is distinct from 'Rehearsal Season' then
    raise exception 'Rehearsal FAILED: the export should carry round 1, dated when it opened, and the season''s name';
  end if;
  checks := checks + 1;

  -- 7. Changing the season: the rules reach rounds not closed yet, the days
  --    lay the unopened rounds out again.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.update_site_season('season99', '{"point_budget": 8, "max_per_track": 4, "submit_days": 3}'::jsonb);
  execute 'reset role';
  if (select point_budget from public.site_rounds where id = r1) <> 6 or (select point_budget from public.site_rounds where id = r2) <> 8
     or (select closes_at from public.site_rounds where id = r2) <> public.site_add_days((select opens_at from public.site_rounds where id = r2), 3) then
    raise exception 'Rehearsal FAILED: the change should reach round 2 (rules and days) and not round 1';
  end if;
  checks := checks + 1;

  -- 8. Reorder, remove and add, only among rounds that haven't opened.
  execute 'set local role authenticated';
  perform public.move_site_season_round(r3, true);
  begin
    perform public.move_site_season_round(r1, false);
    raise exception 'Rehearsal FAILED: a round that has opened moved';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
  end;
  execute 'reset role';
  if (select opens_at from public.site_rounds where id = r3) >= (select opens_at from public.site_rounds where id = r2)
     or (select opens_at from public.site_rounds where id = r3) <> (select voting_closes_at from public.site_rounds where id = r1) then
    raise exception 'Rehearsal FAILED: round 3 should now come straight after round 1';
  end if;
  checks := checks + 1;
  execute 'set local role authenticated';
  begin
    perform public.remove_site_season_round(r1);
    raise exception 'Rehearsal FAILED: a round that has opened was removed';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
  end;
  perform public.remove_site_season_round(r2);
  perform public.add_site_season_round('season99', 'Four', '');
  execute 'reset role';
  if exists (select 1 from public.site_rounds where id = r2)
     or (select opens_at from public.site_rounds where season_key = 'season99' and name = 'Four')
        <> (select voting_closes_at from public.site_rounds where id = r3) then
    raise exception 'Rehearsal FAILED: removing round 2 and adding Four should leave Four after round 3';
  end if;
  checks := checks + 1;

  -- 9. The opening time: can't move into the past, or once it has opened.
  execute 'set local role authenticated';
  begin
    update public.site_rounds set opens_at = now() - interval '1 hour' where id = r3;
    raise exception 'Rehearsal FAILED: an opening time moved into the past';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
  end;
  begin
    update public.site_rounds set opens_at = now() + interval '1 hour' where id = r1;
    raise exception 'Rehearsal FAILED: an opened round''s opening time moved';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
  end;
  begin
    update public.site_rounds set season_key = 'season3' where id = r3;
    raise exception 'Rehearsal FAILED: a round left the season';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
  end;
  checks := checks + 1;

  -- 10. Who's playing: at least two, and the list is replaced.
  begin
    perform public.set_site_season_players('season99', array[ca]);
    raise exception 'Rehearsal FAILED: a season was left with one player';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
  end;
  perform public.set_site_season_players('season99', array[ca, cb, cd]);
  execute 'reset role';
  if (select array_agg(competitor_id order by competitor_id) from public.site_season_players where season_key = 'season99')
     <> (select array_agg(x order by x) from unnest(array[ca, cb, cd]) x) then
    raise exception 'Rehearsal FAILED: the players weren''t replaced';
  end if;
  checks := checks + 1;

  -- 11. Speedy: a season whose round 1 finishes early moves up, and round 2
  --     opens the moment voting closes.
  execute 'set local role authenticated';
  perform public.create_site_season(jsonb_build_object('key', 'season98', 'name', 'Rehearsal Speedy', 'point_budget', 3, 'max_per_track', 3,
    'timing', 'speedy', 'submit_days', 2, 'vote_days', 5, 'first_playlist_at', now() + interval '1 day',
    'rounds', jsonb_build_array(jsonb_build_object('name', 'S1'), jsonb_build_object('name', 'S2')),
    'players', jsonb_build_array(ca, cb)));
  execute 'reset role';
  select id into q1 from public.site_rounds where season_key = 'season98' and name = 'S1';
  select id into q2 from public.site_rounds where season_key = 'season98' and name = 'S2';
  -- now() doesn't move inside one run, and Speedy closes S1 at now(), which
  -- has to be after it opened: in real life it always is
  update public.site_rounds set opens_at = now() - interval '1 hour' where id = q1;
  execute 'set local role authenticated';
  perform public.submit_track(q1, 'youtube', 'aaaaaaaaaaa');
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  perform public.submit_track(q1, 'youtube', 'bbbbbbbbbbb');
  execute 'reset role';
  select * into rr from public.site_rounds where id = q1;
  if rr.closes_at <> now() or rr.closed_at <> now() or rr.voting_closes_at <> public.site_add_days(now() + interval '1 day', 5) - interval '1 day'
     or (select opens_at from public.site_rounds where id = q2) <> rr.voting_closes_at then
    raise exception 'Rehearsal FAILED: Speedy should close at the last track and move voting and round 2 up by the day saved';
  end if;
  checks := checks + 1;
  select o.submission_id into s1 from public.site_submission_owners o where o.round_id = q1 and o.user_id = a;
  select o.submission_id into s2 from public.site_submission_owners o where o.round_id = q1 and o.user_id = b;
  -- A votes (a comment on their own track, 3 points on B's)
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.cast_ballot(q1, jsonb_build_array(jsonb_build_object('submission', s1, 'points', 0, 'comment', 'mine'),
                                                   jsonb_build_object('submission', s2, 'points', 3)));
  execute 'reset role';
  if public.site_round_phase(q1) <> 'voting' then
    raise exception 'Rehearsal FAILED: voting closed before B had voted';
  end if;
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.cast_ballot(q1, jsonb_build_array(jsonb_build_object('submission', s1, 'points', 3)));
  execute 'reset role';
  if public.site_round_phase(q1) <> 'finished' or public.site_round_phase(q2) <> 'submitting'
     or (select opens_at from public.site_rounds where id = q2) <> now() then
    raise exception 'Rehearsal FAILED: Speedy should open round 2 the moment voting closes';
  end if;
  checks := checks + 1;

  -- 12. The reminders: a round opening in a season reaches its players
  --     only (round 3 is moved to have just opened). C was taken off the
  --     season, D put on it.
  insert into public.push_subscriptions (endpoint, user_id, p256dh, auth) values
    ('https://push.example.invalid/b', b, repeat('B', 87), repeat('b', 22)),
    ('https://push.example.invalid/c', c, repeat('C', 87), repeat('c', 22)),
    ('https://push.example.invalid/d', d, repeat('D', 87), repeat('d', 22));
  update public.site_rounds set opens_at = now() - interval '1 minute' where id = r3;
  create temp table claimed on commit drop as select * from public.reminders_claim(array['push']) where round_id = r3;
  if not exists (select 1 from claimed where user_id = b and kind = 'round_open') then
    raise exception 'Rehearsal FAILED: a player should hear their season''s round open';
  end if;
  checks := checks + 1;
  if exists (select 1 from claimed where user_id = c) then
    raise exception 'Rehearsal FAILED: someone taken off the season heard its round open';
  end if;
  checks := checks + 1;
  if not exists (select 1 from claimed where user_id = d) then
    raise exception 'Rehearsal FAILED: D, now playing, should hear it';
  end if;
  checks := checks + 1;

  -- 13. Steady never closes early: a steady season with one round, both in.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.create_site_season(jsonb_build_object('key', 'season97', 'name', 'Rehearsal Steady', 'timing', 'steady',
    'first_playlist_at', now() + interval '1 day', 'rounds', jsonb_build_array(jsonb_build_object('name', 'T1')),
    'players', jsonb_build_array(ca, cb)));
  execute 'reset role';
  select id into q3 from public.site_rounds where season_key = 'season97';
  execute 'set local role authenticated';
  perform public.submit_track(q3, 'youtube', 'ccccccccccc');
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  perform public.submit_track(q3, 'youtube', 'ddddddddddd');
  execute 'reset role';
  if public.site_round_phase(q3) <> 'submitting' then
    raise exception 'Rehearsal FAILED: a Steady round closed early';
  end if;
  checks := checks + 1;

  raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;
end $$;
