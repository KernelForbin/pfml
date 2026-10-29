-- A rehearsal of DJs, Spectators and prompters, run by the real database
-- and then undone: nothing it does is kept. Run it in the Supabase SQL
-- Editor after supabase/migrations/2026-10-29_season_roles.sql (README, DJs
-- and Spectators). It always ends in an error, on purpose, because an error
-- rolls everything back:
--
--   "Rehearsal passed: 12 checks held. Nothing was kept."  every rule held
--   "Rehearsal FAILED: ..."                               says which didn't
--
-- It plays the admin (A) and the first three members who are neither admin
-- nor commissioner (B, C and D), signed in as them and as the
-- 'authenticated' role, as the site would, through a made-up Accelerated
-- site season (season99) worth 2 points a ballot. A, B and C are DJs and D
-- is a Spectator; round 2 swaps C and D. All of it is rolled back.

do $$
declare
  a uuid; ca text;
  b uuid; cb text;
  c uuid; cc text;
  d uuid; cd text;
  r1 uuid; r2 uuid;
  sa uuid; sb uuid; sc uuid;
  st jsonb;
  n int;
  checks int := 0;
begin
  select user_id, competitor_id into a, ca from public.members where role = 'admin' order by created_at limit 1;
  select user_id, competitor_id into b, cb from public.members where role = 'member' order by created_at, user_id limit 1;
  select user_id, competitor_id into c, cc from public.members where role = 'member' order by created_at, user_id offset 1 limit 1;
  select user_id, competitor_id into d, cd from public.members where role = 'member' order by created_at, user_id offset 2 limit 1;
  if a is null or d is null then raise exception 'Rehearsal FAILED: it needs the admin and three other members'; end if;

  -- The admin sets the season up: D a Spectator; round 1 written by B and
  -- C together, round 2 by A, with C and D swapped.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.create_site_season(jsonb_build_object('key', 'season99', 'name', 'Rehearsal Roles', 'timing', 'accelerated',
    'point_budget', 2, 'max_per_track', 2, 'first_playlist_at', now() + interval '1 day',
    'players', jsonb_build_array(jsonb_build_object('id', ca, 'role', 'dj'), jsonb_build_object('id', cb, 'role', 'dj'),
                                 jsonb_build_object('id', cc, 'role', 'dj'), jsonb_build_object('id', cd, 'role', 'spectator')),
    'rounds', jsonb_build_array(
      jsonb_build_object('name', 'One', 'prompters', jsonb_build_array(cb, cc)),
      jsonb_build_object('name', 'Two', 'prompters', jsonb_build_array(ca),
                         'roles', jsonb_build_object(ca, 'dj', cb, 'dj', cc, 'spectator', cd, 'dj')))));
  execute 'reset role';
  select id into r1 from public.site_rounds where season_key = 'season99' and name = 'One';
  select id into r2 from public.site_rounds where season_key = 'season99' and name = 'Two';

  -- 1. The roles and prompters went in, and a round keeps only the roles
  --    that differ from the season's.
  if public.site_round_role(r1, cd) <> 'spectator' or public.site_round_role(r1, cc) <> 'dj'
     or public.site_round_role(r2, cd) <> 'dj' or public.site_round_role(r2, cc) <> 'spectator' then
    raise exception 'Rehearsal FAILED: the roles came out wrong';
  end if;
  select count(*) into n from public.site_round_roles where round_id = r2;
  if n <> 2 then raise exception 'Rehearsal FAILED: round 2 kept % roles, not the 2 that differ', n; end if;
  if (select array_agg(competitor_id order by competitor_id) from public.site_round_prompters where round_id = r1)
       <> (select array_agg(x order by x) from unnest(array[cb, cc]) x)
     or (select array_agg(competitor_id) from public.site_round_prompters where round_id = r2) <> array[ca] then
    raise exception 'Rehearsal FAILED: the prompters came out wrong';
  end if;
  checks := checks + 1;

  -- 2. A member reads the roster, the roles and the prompters.
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  select count(*) into n from public.site_round_roster(r1) x where (x.competitor_id = cd and x.role = 'spectator')
                                                                or (x.competitor_id in (ca, cb, cc) and x.role = 'dj');
  if n <> 4 then raise exception 'Rehearsal FAILED: the roster showed % of 4 players right', n; end if;
  select count(*) into n from public.site_round_prompters where round_id = r1;
  if n <> 2 then raise exception 'Rehearsal FAILED: a member read % prompters, not 2', n; end if;
  checks := checks + 1;

  -- 3. A Spectator can't send a track.
  perform set_config('request.jwt.claim.sub', d::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', d, 'role', 'authenticated')::text, true);
  begin
    perform public.submit_track(r1, 'youtube', 'rehearsal0d');
    raise exception 'Rehearsal FAILED: a Spectator sent a track';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'You''re a Spectator this round: you vote on the tracks, but don''t send one.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  -- 4. A sends a track, and then can't be made a Spectator in that round.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  perform public.submit_track(r1, 'youtube', 'rehearsal0a');
  begin
    perform public.set_site_round_people(r1, jsonb_build_object(ca, 'spectator'), null);
    raise exception 'Rehearsal FAILED: a DJ with a track became a Spectator';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like '% has already sent a track to this round, so stays a DJ in it.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  -- 5. A round needs 2 DJs, and only a commissioner changes one.
  begin
    perform public.set_site_round_people(r2, jsonb_build_object(ca, 'dj', cb, 'spectator', cc, 'spectator', cd, 'spectator'), null);
    raise exception 'Rehearsal FAILED: a round was left with one DJ';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> '"Two" needs at least 2 DJs.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  begin
    perform public.set_site_round_people(r2, null, jsonb_build_array('not-a-member'));
    raise exception 'Rehearsal FAILED: a prompter who isn''t a member went in';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'A prompter has to be a member who has joined the site.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  begin
    perform public.set_site_round_people(r2, null, jsonb_build_array(cb));
    raise exception 'Rehearsal FAILED: a member who isn''t a commissioner changed a round';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'Only the admin or a commissioner can change a round.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  -- 6. Accelerated closes submissions once the DJs are in, not waiting on
  --    the Spectator.
  perform public.submit_track(r1, 'youtube', 'rehearsal0b');
  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  perform public.submit_track(r1, 'youtube', 'rehearsal0c');
  execute 'reset role';
  if public.site_round_phase(r1) <> 'voting' then
    raise exception 'Rehearsal FAILED: submissions stayed open waiting on the Spectator (%)', public.site_round_phase(r1);
  end if;
  select o.submission_id into sa from public.site_submission_owners o where o.round_id = r1 and o.user_id = a;
  select o.submission_id into sb from public.site_submission_owners o where o.round_id = r1 and o.user_id = b;
  select o.submission_id into sc from public.site_submission_owners o where o.round_id = r1 and o.user_id = c;
  checks := checks + 1;

  -- 7. Roles are fixed once submissions close; who wrote the prompt isn't.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  begin
    perform public.set_site_round_people(r1, jsonb_build_object(cd, 'dj'), null);
    raise exception 'Rehearsal FAILED: a role changed after submissions closed';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'Roles can change only until submissions close.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  perform public.set_site_round_people(r1, null, jsonb_build_array(cb));
  if (select array_agg(competitor_id) from public.site_round_prompters where round_id = r1) <> array[cb] then
    raise exception 'Rehearsal FAILED: the prompters didn''t change after the close';
  end if;
  checks := checks + 1;

  -- 8. The Spectator saves a draft and votes, with no track of their own,
  --    and the lounge counts them as able to get in.
  perform set_config('request.jwt.claim.sub', d::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', d, 'role', 'authenticated')::text, true);
  perform public.save_ballot_draft(r1, jsonb_build_array(jsonb_build_object('submission', sa, 'points', 1)));
  st := public.lounge_status(r1, false);
  if not (st->>'eligible')::boolean then raise exception 'Rehearsal FAILED: the lounge turned the Spectator away: %', st; end if;
  checks := checks + 1;

  -- 9. Voting closes early only once the DJs and the Spectator have voted.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  perform public.cast_ballot(r1, jsonb_build_array(jsonb_build_object('submission', sb, 'points', 2)));
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  perform public.cast_ballot(r1, jsonb_build_array(jsonb_build_object('submission', sc, 'points', 2)));
  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  perform public.cast_ballot(r1, jsonb_build_array(jsonb_build_object('submission', sa, 'points', 2)));
  execute 'reset role';
  if public.site_round_phase(r1) <> 'voting' then
    raise exception 'Rehearsal FAILED: voting closed without the Spectator''s ballot';
  end if;
  execute 'set local role authenticated';
  perform set_config('request.jwt.claim.sub', d::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', d, 'role', 'authenticated')::text, true);
  perform public.cast_ballot(r1, jsonb_build_array(jsonb_build_object('submission', sa, 'points', 1),
                                                   jsonb_build_object('submission', sc, 'points', 1, 'comment', 'From the stands')));
  execute 'reset role';
  if public.site_round_phase(r1) <> 'finished' then
    raise exception 'Rehearsal FAILED: voting didn''t close once everyone had voted';
  end if;
  checks := checks + 1;

  -- 10. The results: three tracks, the Spectator's points counted.
  execute 'set local role authenticated';
  select count(*) into n from public.site_round_results(r1);
  if n <> 3 then raise exception 'Rehearsal FAILED: % results, not 3 tracks', n; end if;
  if (select x.points from public.site_round_results(r1) x where x.submission_id = sa) <> 3 then
    raise exception 'Rehearsal FAILED: A''s track should have 3 points, with the Spectator''s 1';
  end if;
  if not exists (select 1 from public.site_round_votes(r1) x where x.voter_id = cd and x.comment = 'From the stands') then
    raise exception 'Rehearsal FAILED: the Spectator''s vote isn''t in the results';
  end if;
  checks := checks + 1;

  -- 11. A season role change reaches the rounds not closed yet, never a
  --     finished one: D becomes a DJ and B a Spectator for the season.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  perform public.set_site_season_roster('season99', jsonb_build_array(
    jsonb_build_object('id', ca, 'role', 'dj'), jsonb_build_object('id', cb, 'role', 'spectator'),
    jsonb_build_object('id', cc, 'role', 'dj'), jsonb_build_object('id', cd, 'role', 'dj')));
  execute 'reset role';
  if public.site_round_role(r1, cd) <> 'spectator' or public.site_round_role(r1, cb) <> 'dj' then
    raise exception 'Rehearsal FAILED: the finished round''s roles changed';
  end if;
  if public.site_round_role(r2, cb) <> 'spectator' or public.site_round_role(r2, cd) <> 'dj' or public.site_round_role(r2, cc) <> 'spectator' then
    raise exception 'Rehearsal FAILED: round 2 should have B a Spectator, D a DJ and C still a Spectator';
  end if;
  if exists (select 1 from public.site_round_roles where round_id = r2 and competitor_id = cd) then
    raise exception 'Rehearsal FAILED: round 2 kept a role for D that now matches the season';
  end if;
  checks := checks + 1;

  -- 12. A stranger reads none of it and can't ask for a roster.
  execute 'set local role anon';
  begin
    perform 1 from public.site_round_roles;
    raise exception 'Rehearsal FAILED: a stranger read the round roles';
  exception when insufficient_privilege then
    null;
  end;
  begin
    perform 1 from public.site_round_prompters;
    raise exception 'Rehearsal FAILED: a stranger read the prompters';
  exception when insufficient_privilege then
    null;
  end;
  begin
    perform public.site_round_roster(r1);
    raise exception 'Rehearsal FAILED: a stranger could ask for a roster';
  exception when insufficient_privilege then
    null;
  end;
  execute 'reset role';
  checks := checks + 1;

  raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;
end $$;
