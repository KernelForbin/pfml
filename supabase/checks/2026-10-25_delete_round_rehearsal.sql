-- A rehearsal of deleting a round, run by the real database and then undone:
-- nothing it does is kept. Run it in the Supabase SQL Editor after
-- supabase/migrations/2026-10-25_delete_round.sql (README, Deleting a round).
-- It always ends in an error, on purpose, because an error rolls everything
-- back:
--
--   "Rehearsal passed: 8 checks held. Nothing was kept."   every rule held
--   "Rehearsal FAILED: ..."                               says which didn't
--
-- It plays the admin and the first two members who are neither admin nor
-- commissioner (B and C), signed in as them and as the 'authenticated' role,
-- as the site would, with made-up Season 3 rounds and a made-up site season
-- (season99). It also asks about every round that was already there, the
-- real Round 7 among them, and tries to delete each; all of it is rolled
-- back whatever happens.

do $$
declare
  a uuid;
  b uuid;
  c uuid; cc text;
  r_open uuid; r_empty uuid; r_one uuid; r_two uuid; r_list uuid; r_site uuid;
  real_rounds uuid[];
  x uuid;
  n int;
  checks int := 0;
begin
  select user_id into a from public.members where role = 'admin' order by created_at limit 1;
  select user_id into b from public.members where role = 'member' order by created_at, user_id limit 1;
  select user_id, competitor_id into c, cc from public.members where role = 'member' order by created_at, user_id offset 1 limit 1;
  if a is null or c is null then raise exception 'Rehearsal FAILED: it needs the admin and two other members'; end if;
  select array_agg(id) into real_rounds from public.site_rounds;

  insert into public.site_rounds (season_key, name, closes_at) values ('season3', 'Rehearsal open', now() + interval '1 day')
  returning id into r_open;
  insert into public.site_rounds (season_key, name, closes_at) values ('season3', 'Rehearsal empty', now() + interval '1 day')
  returning id into r_empty;
  insert into public.site_rounds (season_key, name, closes_at) values ('season3', 'Rehearsal one player', now() + interval '1 day')
  returning id into r_one;
  insert into public.site_rounds (season_key, name, closes_at) values ('season3', 'Rehearsal two players', now() + interval '1 day')
  returning id into r_two;
  insert into public.site_rounds (season_key, name, closes_at) values ('season3', 'Rehearsal playlists', now() + interval '1 day')
  returning id into r_list;

  -- B sends a track to three rounds, C to one of them.
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.submit_track(r_one, 'youtube', 'rehearsal01');
  perform public.submit_track(r_two, 'youtube', 'rehearsal02');
  perform public.submit_track(r_list, 'youtube', 'rehearsal03');

  -- 1. A member can't list or delete.
  begin
    perform public.deletable_site_rounds();
    raise exception 'Rehearsal FAILED: a member listed the deletable rounds';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'Only the admin can delete a round.%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;
  begin
    perform public.delete_site_round(r_empty);
    raise exception 'Rehearsal FAILED: a member deleted a round';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'Only the admin can delete a round.%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  perform public.submit_track(r_two, 'youtube', 'rehearsal04');
  execute 'reset role';

  -- Everything but the open one closes; one gets playlists.
  update public.site_rounds set closed_at = now() where id in (r_empty, r_one, r_two, r_list);
  update public.site_rounds set playlists_built_at = now() where id = r_list;
  -- A season set up on the site, with its round.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.create_site_season(jsonb_build_object('key', 'season99', 'name', 'Rehearsal Season',
    'first_playlist_at', now() + interval '1 day', 'rounds', jsonb_build_array(jsonb_build_object('name', 'S')),
    'players', jsonb_build_array(cc, (select competitor_id from public.members where user_id = b))));
  select id into r_site from public.site_rounds where season_key = 'season99';

  -- 2. The admin's list: the empty round (no tracks) and B's alone (1 track),
  --    nothing else.
  if (select count(*) from public.deletable_site_rounds() d where d.round_id = r_empty and d.tracks = 0) <> 1
     or (select count(*) from public.deletable_site_rounds() d where d.round_id = r_one and d.tracks = 1) <> 1 then
    raise exception 'Rehearsal FAILED: the empty round and the one-player round should be listed';
  end if;
  checks := checks + 1;
  if exists (select 1 from public.deletable_site_rounds() d
              where d.round_id in (r_open, r_two, r_list, r_site) or d.round_id = any(real_rounds)) then
    raise exception 'Rehearsal FAILED: a round that can''t be deleted was listed';
  end if;
  checks := checks + 1;

  -- 3. Each one that can't be deleted says why.
  foreach x in array array[r_open, r_two, r_list, r_site] loop
    begin
      perform public.delete_site_round(x);
      raise exception 'Rehearsal FAILED: a round that should stay was deleted';
    exception when others then
      if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
      if not (sqlerrm like 'This round is still taking tracks.%' and x = r_open
              or sqlerrm like 'More than one player sent tracks%' and x = r_two
              or sqlerrm like 'This round has playlists%' and x = r_list
              or sqlerrm like 'A round in a season played on the site%' and x = r_site) then
        raise exception 'Rehearsal FAILED: got "%"', sqlerrm;
      end if;
    end;
  end loop;
  checks := checks + 1;

  -- 4. Every round that was already there stays, the real Round 7 among them.
  foreach x in array coalesce(real_rounds, '{}') loop
    begin
      perform public.delete_site_round(x);
      raise exception 'Rehearsal FAILED: a real round was deleted';
    exception when others then
      if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    end;
  end loop;
  execute 'reset role';
  if (select count(*) from public.site_rounds where id = any(real_rounds)) <> coalesce(cardinality(real_rounds), 0) then
    raise exception 'Rehearsal FAILED: a real round is gone';
  end if;
  checks := checks + 1;

  -- 5. The admin can't go around the functions: no direct delete.
  execute 'set local role authenticated';
  delete from public.site_rounds where id = r_empty;
  execute 'reset role';
  if not exists (select 1 from public.site_rounds where id = r_empty) then
    raise exception 'Rehearsal FAILED: a direct delete went through';
  end if;
  checks := checks + 1;

  -- 6. The admin deletes the empty round and B's, and B's track goes too.
  execute 'set local role authenticated';
  if public.delete_site_round(r_empty) <> 'Rehearsal empty' or public.delete_site_round(r_one) <> 'Rehearsal one player' then
    raise exception 'Rehearsal FAILED: the delete should return the round''s name';
  end if;
  execute 'reset role';
  select count(*) into n from public.site_rounds where id in (r_empty, r_one);
  if n <> 0 or exists (select 1 from public.site_submissions where round_id = r_one) then
    raise exception 'Rehearsal FAILED: the rounds or B''s track are still there';
  end if;
  checks := checks + 1;

  raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;
end $$;
