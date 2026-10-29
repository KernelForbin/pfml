-- A rehearsal of the export's Spectators, run by the real database and then
-- undone: nothing it does is kept. Run it in the Supabase SQL Editor after
-- supabase/migrations/2026-10-29_spectator_points.sql (README, Spectators'
-- podium points). It always ends in an error, on purpose, because an error
-- rolls everything back:
--
--   "Rehearsal passed: 3 checks held. Nothing was kept."  every rule held
--   "Rehearsal FAILED: ..."                              says which didn't
--
-- It plays the admin (A) and the first two members who are neither admin
-- nor commissioner (B and C), through one round of a made-up site season
-- (season99) worth 2 points a ballot: A and B are DJs and send a track, C
-- is a Spectator, all three vote, then voting closes. All of it is rolled
-- back.

do $$
declare
  a uuid; ca text;
  b uuid; cb text;
  c uuid; cc text;
  r uuid;
  sa uuid; sb uuid;
  ex jsonb;
  checks int := 0;
begin
  select user_id, competitor_id into a, ca from public.members where role = 'admin' order by created_at limit 1;
  select user_id, competitor_id into b, cb from public.members where role = 'member' order by created_at, user_id limit 1;
  select user_id, competitor_id into c, cc from public.members where role = 'member' order by created_at, user_id offset 1 limit 1;
  if a is null or c is null then raise exception 'Rehearsal FAILED: it needs the admin and two other members'; end if;

  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.create_site_season(jsonb_build_object('key', 'season99', 'name', 'Rehearsal Podium',
    'point_budget', 2, 'max_per_track', 2, 'first_playlist_at', now() + interval '1 day',
    'players', jsonb_build_array(jsonb_build_object('id', ca, 'role', 'dj'), jsonb_build_object('id', cb, 'role', 'dj'),
                                 jsonb_build_object('id', cc, 'role', 'spectator')),
    'rounds', jsonb_build_array(jsonb_build_object('name', 'Podium'))));
  execute 'reset role';
  select id into r from public.site_rounds where season_key = 'season99';

  execute 'set local role authenticated';
  perform public.submit_track(r, 'youtube', 'rehearsal0a');
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  perform public.submit_track(r, 'youtube', 'rehearsal0b');
  execute 'reset role';
  update public.site_rounds set closed_at = now() where id = r;
  select o.submission_id into sa from public.site_submission_owners o where o.round_id = r and o.user_id = a;
  select o.submission_id into sb from public.site_submission_owners o where o.round_id = r and o.user_id = b;

  execute 'set local role authenticated';
  perform public.cast_ballot(r, jsonb_build_array(jsonb_build_object('submission', sa, 'points', 2)));
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  perform public.cast_ballot(r, jsonb_build_array(jsonb_build_object('submission', sb, 'points', 2)));
  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  perform public.cast_ballot(r, jsonb_build_array(jsonb_build_object('submission', sa, 'points', 2)));
  execute 'reset role';
  update public.site_rounds set voting_closed_at = now() where id = r and voting_closed_at is null;
  if public.site_round_phase(r) <> 'finished' then raise exception 'Rehearsal FAILED: the round should be finished'; end if;

  -- 1. The export lists the round's Spectator, and only them.
  select e into ex from jsonb_array_elements(public.site_rounds_export()->'rounds') e where e->>'id' = r::text;
  if ex is null then raise exception 'Rehearsal FAILED: the finished round isn''t in the export'; end if;
  if ex->'spectators' <> jsonb_build_array(cc) then
    raise exception 'Rehearsal FAILED: the export''s spectators were %, not just C', ex->'spectators';
  end if;
  if not exists (select 1 from jsonb_array_elements(ex->'votes') v where v->>'voter' = cc and (v->>'points')::int = 2) then
    raise exception 'Rehearsal FAILED: the Spectator''s vote isn''t in the export';
  end if;
  checks := checks + 1;

  -- 2. Making C a DJ for the season afterwards doesn't rewrite the
  --    finished round: C stays its Spectator.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.set_site_season_roster('season99', jsonb_build_array(
    jsonb_build_object('id', ca, 'role', 'dj'), jsonb_build_object('id', cb, 'role', 'dj'), jsonb_build_object('id', cc, 'role', 'dj')));
  execute 'reset role';
  select e into ex from jsonb_array_elements(public.site_rounds_export()->'rounds') e where e->>'id' = r::text;
  if ex->'spectators' <> jsonb_build_array(cc) then
    raise exception 'Rehearsal FAILED: after the season change the round listed %', ex->'spectators';
  end if;
  checks := checks + 1;

  -- 3. A member still can't call the export.
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  begin
    perform public.site_rounds_export();
    raise exception 'Rehearsal FAILED: a member called the export';
  exception when insufficient_privilege then
    null;
  end;
  execute 'reset role';
  checks := checks + 1;

  raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;
end $$;
