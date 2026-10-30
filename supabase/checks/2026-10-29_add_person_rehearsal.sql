-- A rehearsal of adding someone new, run by the real database and then
-- undone: nothing it does is kept. Run it in the Supabase SQL Editor after
-- supabase/migrations/2026-10-29_add_person.sql (README, Someone new). It
-- always ends in an error, on purpose, because an error rolls everything
-- back:
--
--   "Rehearsal passed: 5 checks held. Nothing was kept."  every rule held
--   "Rehearsal FAILED: ..."                              says which didn't
--
-- It plays the admin (A) and the first member who is neither admin nor
-- commissioner (B), signed in as them and as the 'authenticated' role, as
-- the site would. All of it is rolled back.

do $$
declare
  a uuid; ca text;
  b uuid; cb text;
  newcomer text;
  n int;
  checks int := 0;
begin
  select user_id, competitor_id into a, ca from public.members where role = 'admin' order by created_at limit 1;
  select user_id, competitor_id into b, cb from public.members where role = 'member' order by created_at, user_id limit 1;
  if a is null or b is null then raise exception 'Rehearsal FAILED: it needs the admin and another member'; end if;

  -- 1. A member who isn't a commissioner can't add anyone.
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  begin
    perform public.add_player('Rehearsal Newcomer');
    raise exception 'Rehearsal FAILED: a member added someone';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'Only the admin or a commissioner can add someone.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  -- 2. The admin adds them, spaces tidied, with a "site" id.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  newcomer := public.add_player('  Rehearsal   Newcomer ');
  execute 'reset role';
  if newcomer !~ '^site[0-9a-f]{32}$' or (select name from public.players where competitor_id = newcomer) <> 'Rehearsal Newcomer' then
    raise exception 'Rehearsal FAILED: added as % / %', newcomer, (select name from public.players where competitor_id = newcomer);
  end if;
  checks := checks + 1;

  -- 3. Not twice under one name (invites.py finds people by name), and not
  --    with no name.
  execute 'set local role authenticated';
  begin
    perform public.add_player('rehearsal newcomer');
    raise exception 'Rehearsal FAILED: a second player had the same name';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'There''s already a player called rehearsal newcomer.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  begin
    perform public.add_player('   ');
    raise exception 'Rehearsal FAILED: someone with no name was added';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'A name is 1 to 60 characters.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  -- 4. They can play a season straight away, as a Spectator.
  perform public.create_site_season(jsonb_build_object('key', 'season99', 'name', 'Rehearsal Newcomer',
    'first_playlist_at', now() + interval '1 day',
    'players', jsonb_build_array(jsonb_build_object('id', ca, 'role', 'dj'), jsonb_build_object('id', cb, 'role', 'dj'),
                                 jsonb_build_object('id', newcomer, 'role', 'spectator')),
    'rounds', jsonb_build_array(jsonb_build_object('name', 'One'))));
  execute 'reset role';
  if public.site_round_role((select id from public.site_rounds where season_key = 'season99'), newcomer) <> 'spectator' then
    raise exception 'Rehearsal FAILED: the newcomer isn''t the round''s Spectator';
  end if;
  checks := checks + 1;

  -- 5. A stranger can't call it.
  execute 'set local role anon';
  begin
    perform public.add_player('Stranger');
    raise exception 'Rehearsal FAILED: a stranger added someone';
  exception when insufficient_privilege then
    null;
  end;
  execute 'reset role';
  checks := checks + 1;

  raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;
end $$;
