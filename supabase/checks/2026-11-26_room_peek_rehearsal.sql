-- A rehearsal of Live now on Home, run by the real database and then
-- undone: nothing it does is kept. Run it in the Supabase SQL Editor after
-- supabase/migrations/2026-11-26_room_peek.sql (README, The live room). It
-- always ends in an error, on purpose, because an error rolls everything
-- back:
--
--   "Rehearsal passed: 7 checks held. Nothing was kept."  every rule held
--   "Rehearsal FAILED: ..."                              says which didn't
--
-- It plays the admin (A) and the first two members who are neither admin
-- nor commissioner (B and C), signed in as them and as the 'authenticated'
-- role, as the pages would. A and C are in the room; B only looks from
-- Home. It empties the room first (inside the same transaction, so that's
-- undone too), and where a check needs time to pass it moves a track's
-- start or someone's last sign of life back, as the database itself.

do $$
declare
  a uuid; ca text;
  b uuid; cb text;
  c uuid; cc text;
  st jsonb;
  t1 uuid;
  pid bigint;
  n int;
  checks int := 0;
begin
  select user_id, competitor_id into a, ca from public.members where role = 'admin' order by created_at limit 1;
  select user_id, competitor_id into b, cb from public.members where role = 'member' order by created_at, user_id limit 1;
  select user_id, competitor_id into c, cc from public.members where role = 'member' order by created_at, user_id offset 1 limit 1;
  if a is null or c is null then raise exception 'Rehearsal FAILED: it needs the admin and two other members'; end if;

  -- an empty room, and an empty library for A (all undone at the end)
  delete from public.room_djs;
  delete from public.room_presence;
  update public.room_state set play_id = null where id = 1;
  delete from public.room_tracks where user_id = a;

  -- 1. Nothing playing: Home shows nothing, and looking doesn't put B in
  --    the room.
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  if public.room_peek() is not null then
    raise exception 'Rehearsal FAILED: an empty room came back as %', public.room_peek();
  end if;
  execute 'reset role';
  if exists (select 1 from public.room_presence) then
    raise exception 'Rehearsal FAILED: looking from Home put someone in the room';
  end if;
  checks := checks + 1;

  -- 2. A comes in, queues a track and steps up. B, on Home, sees the track,
  --    A playing it, A on the decks and in the crowd, and isn't in it.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.room_here(null);
  t1 := public.room_library_add('youtube', 'rehearsal01', 'A One', 'Artist A', 200, true);
  perform public.room_step_up();
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  st := public.room_peek();
  if st->'play'->>'title' <> 'A One' or st->'play'->>'artist' <> 'Artist A' or st->'play'->>'dj' <> ca
     or st->'play'->>'track' <> 'rehearsal01' or (st->'play'->>'seconds')::int <> 200
     or st->'djs' <> jsonb_build_array(ca) or st->'crowd' <> jsonb_build_array(ca) or st->'now' is null then
    raise exception 'Rehearsal FAILED: Home saw the room as %', st;
  end if;
  execute 'reset role';
  select count(*) into n from public.room_presence where user_id = b;
  if n <> 0 then raise exception 'Rehearsal FAILED: looking from Home put B in the room'; end if;
  checks := checks + 1;

  -- 3. C comes in and says Awesome: Home counts it, and has C in the crowd.
  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.room_here(null);
  perform public.room_vote(1);
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  st := public.room_peek();
  if (st->'play'->>'awesome')::int <> 1 or (st->'play'->>'lame')::int <> 0
     or not (st->'crowd' ? cc) or jsonb_array_length(st->'crowd') <> 2 then
    raise exception 'Rehearsal FAILED: Home missed the vote or the crowd: %', st;
  end if;
  execute 'reset role';
  checks := checks + 1;

  -- 4. A goes quiet for 91 seconds (nobody's page has moved the room on
  --    yet): Home leaves A out of the decks and the crowd, while C's still
  --    there and the track still has time.
  update public.room_presence set last_seen = now() - interval '91 seconds' where user_id = a;
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  st := public.room_peek();
  if st is null or st->'djs' <> '[]'::jsonb or st->'crowd' <> jsonb_build_array(cc) then
    raise exception 'Rehearsal FAILED: Home kept someone who''d gone: %', st;
  end if;
  execute 'reset role';
  checks := checks + 1;

  -- 5. Everyone quiet: nobody's in the room, so Home shows nothing, though
  --    the track's time isn't up.
  update public.room_presence set last_seen = now() - interval '91 seconds';
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  if public.room_peek() is not null then
    raise exception 'Rehearsal FAILED: Home showed an empty room playing';
  end if;
  execute 'reset role';
  checks := checks + 1;

  -- 6. Everyone back, but the track's time is up and no page has moved the
  --    room on: Home shows nothing rather than a track that's over. Nor
  --    does looking move it on.
  update public.room_presence set last_seen = now();
  select play_id into pid from public.room_state where id = 1;
  update public.room_plays set started_at = now() - interval '201 seconds' where id = pid;
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  if public.room_peek() is not null then
    raise exception 'Rehearsal FAILED: Home showed a track whose time was up';
  end if;
  execute 'reset role';
  if (select play_id from public.room_state where id = 1) is distinct from pid
     or (select ended_at from public.room_plays where id = pid) is not null then
    raise exception 'Rehearsal FAILED: looking from Home moved the room on';
  end if;
  checks := checks + 1;

  -- 7. Someone signed in who isn't a member is told no, and a stranger
  --    can't call it at all.
  t1 := gen_random_uuid();
  perform set_config('request.jwt.claim.sub', t1::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', t1, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  begin
    perform public.room_peek();
    raise exception 'Rehearsal FAILED: someone who isn''t a member saw the room';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'Only league members can see the room.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  execute 'reset role';
  execute 'set local role anon';
  begin
    perform public.room_peek();
    raise exception 'Rehearsal FAILED: a stranger saw the room';
  exception when insufficient_privilege then
    null;
  end;
  execute 'reset role';
  checks := checks + 1;

  raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;
end
$$;
