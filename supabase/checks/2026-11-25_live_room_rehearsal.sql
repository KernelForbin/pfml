-- A rehearsal of the live room, run by the real database and then undone:
-- nothing it does is kept. Run it in the Supabase SQL Editor after
-- supabase/migrations/2026-11-25_live_room.sql (README, The live room). It
-- always ends in an error, on purpose, because an error rolls everything
-- back:
--
--   "Rehearsal passed: 14 checks held. Nothing was kept."  every rule held
--   "Rehearsal FAILED: ..."                               says which didn't
--
-- It plays the admin (A) and the first three members who are neither admin
-- nor commissioner (B, C and D), signed in as them and as the
-- 'authenticated' role, as the page would. It empties the room first
-- (inside the same transaction, so that's undone too), and where a check
-- needs time to pass it moves a track's start or someone's last sign of
-- life back, as the database itself. Anyone in the real room meanwhile
-- just waits a second.

do $$
declare
  a uuid; ca text;
  b uuid; cb text;
  c uuid; cc text;
  d uuid; cd text;
  st jsonb;
  tb1 uuid; tb2 uuid; tc1 uuid;
  pid bigint; mid bigint;
  v bigint;
  n int;
  checks int := 0;
begin
  select user_id, competitor_id into a, ca from public.members where role = 'admin' order by created_at limit 1;
  select user_id, competitor_id into b, cb from public.members where role = 'member' order by created_at, user_id limit 1;
  select user_id, competitor_id into c, cc from public.members where role = 'member' order by created_at, user_id offset 1 limit 1;
  select user_id, competitor_id into d, cd from public.members where role = 'member' order by created_at, user_id offset 2 limit 1;
  if a is null or d is null then raise exception 'Rehearsal FAILED: it needs the admin and three other members'; end if;

  -- an empty room, and empty libraries for the four (all undone at the end)
  delete from public.room_djs;
  delete from public.room_presence;
  update public.room_state set play_id = null where id = 1;
  delete from public.room_tracks where user_id in (a, b, c, d);

  -- 1. Coming in: B is in the crowd, nothing plays, and the chat reads back.
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  st := public.room_here(null);
  if st->'play' <> 'null'::jsonb or not (st->'crowd' ? cb) or jsonb_array_length(st->'djs') <> 0 then
    raise exception 'Rehearsal FAILED: an empty room came back as %', st;
  end if;
  checks := checks + 1;

  -- 2. B can't step up with an empty queue; a library track isn't a queue.
  tb1 := public.room_library_add('youtube', 'rehearsal01', 'B One', 'Artist B', 200, false);
  begin
    perform public.room_step_up();
    raise exception 'Rehearsal FAILED: B stepped up with an empty queue';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'Put a track in your queue first.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  -- 3. B queues two tracks (the second a pasted SoundCloud link, with no
  --    length), steps up, and the first starts. It moves to the bottom of
  --    B's queue.
  tb2 := public.room_library_add('soundcloud', 'rehearsal/b-two', 'B Two', 'Artist B', null, true);
  perform public.room_queue_set(array[tb1, tb2]);
  perform public.room_step_up();
  st := public.room_here(null);
  if st->'play'->>'title' <> 'B One' or st->'play'->>'dj' <> cb or st->'djs' <> jsonb_build_array(cb) then
    raise exception 'Rehearsal FAILED: B''s first track didn''t start: %', st->'play';
  end if;
  if (select array_agg(x.title order by x.queue_pos) from public.room_library() x where x.queue_pos is not null) <> array['B Two', 'B One'] then
    raise exception 'Rehearsal FAILED: the played track didn''t move to the bottom of the queue';
  end if;
  pid := (st->'play'->>'id')::bigint;
  checks := checks + 1;

  -- 4. C comes in, queues a track and steps up: second in the rotation.
  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  tc1 := public.room_library_add('youtube', 'rehearsal02', 'C One', 'Artist C', 180, true);
  perform public.room_here(null);
  perform public.room_step_up();
  st := public.room_here(null);
  if st->'djs' <> jsonb_build_array(cb, cc) or st->'play'->>'title' <> 'B One' then
    raise exception 'Rehearsal FAILED: C didn''t join the rotation behind B';
  end if;
  checks := checks + 1;

  -- 5. Votes: C says Awesome, D (just listening) says Lame, B can't vote
  --    on their own track, and a Lame skips nothing.
  perform public.room_vote(1);
  perform set_config('request.jwt.claim.sub', d::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', d, 'role', 'authenticated')::text, true);
  perform public.room_here(null);
  perform public.room_vote(-1);
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  begin
    perform public.room_vote(1);
    raise exception 'Rehearsal FAILED: B voted on their own track';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'You can''t vote on your own track.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  st := public.room_here(null);
  if st->'play'->'awesome' <> jsonb_build_array(cc) or (st->'play'->>'lame')::int <> 1 or (st->'play'->>'id')::bigint <> pid then
    raise exception 'Rehearsal FAILED: the votes came out wrong, or a Lame skipped the track';
  end if;
  checks := checks + 1;

  -- 6. Skipping: D can't, C (a DJ, but not the one playing) can't.
  perform set_config('request.jwt.claim.sub', d::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', d, 'role', 'authenticated')::text, true);
  begin
    perform public.room_skip();
    raise exception 'Rehearsal FAILED: someone in the crowd skipped a track';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'Only the DJ playing, the admin or a commissioner can skip a track.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  begin
    perform public.room_skip();
    raise exception 'Rehearsal FAILED: another DJ skipped the track';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'Only the DJ playing, the admin or a commissioner can skip a track.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  -- 7. B's track runs out (its start moved back past its 200 seconds): the
  --    next call starts C's, one track each.
  execute 'reset role';
  update public.room_plays set started_at = now() - interval '201 seconds' where id = pid;
  perform set_config('request.jwt.claim.sub', d::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', d, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  st := public.room_here(null);
  if st->'play'->>'title' <> 'C One' or st->'play'->>'dj' <> cc then
    raise exception 'Rehearsal FAILED: C''s track didn''t follow B''s: %', st->'play';
  end if;
  checks := checks + 1;

  -- 8. C skips their own track, and the rotation comes back to B, whose
  --    next track is the SoundCloud one, length unknown.
  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  perform public.room_skip();
  st := public.room_here(null);
  if st->'play'->>'title' <> 'B Two' or (st->'play'->>'length_known')::boolean or st->'play'->'seconds' <> 'null'::jsonb then
    raise exception 'Rehearsal FAILED: the rotation didn''t come back to B''s second track: %', st->'play';
  end if;
  pid := (st->'play'->>'id')::bigint;
  checks := checks + 1;

  -- 9. Its length: C's page can't set it while B is here; B's can, once.
  perform public.room_set_length(pid, 5);
  if public.room_here(null)->'play'->'seconds' <> 'null'::jsonb then
    raise exception 'Rehearsal FAILED: someone else set the length of the DJ''s track';
  end if;
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  perform public.room_set_length(pid, 240);
  perform public.room_set_length(pid, 5);
  if (public.room_here(null)->'play'->>'seconds')::int <> 240
     or (select x.seconds from public.room_library() x where x.id = tb2) <> 240 then
    raise exception 'Rehearsal FAILED: the DJ''s measured length didn''t stick';
  end if;
  checks := checks + 1;

  -- 10. The admin skips B's track; it's C's turn again.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  perform public.room_here(null);
  perform public.room_skip();
  st := public.room_here(null);
  if st->'play'->>'dj' <> cc then raise exception 'Rehearsal FAILED: the admin''s skip didn''t move on to C'; end if;
  checks := checks + 1;

  -- 11. The admin takes C off the decks (B can't). C's track plays on, and
  --     when it ends only B is left to play.
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  begin
    perform public.room_remove_dj(cc);
    raise exception 'Rehearsal FAILED: a member took a DJ off the decks';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'Only the admin or a commissioner can take someone off the decks.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  perform public.room_remove_dj(cc);
  st := public.room_here(null);
  if st->'djs' <> jsonb_build_array(cb) or st->'play'->>'dj' <> cc then
    raise exception 'Rehearsal FAILED: taking C off the decks came out wrong';
  end if;
  checks := checks + 1;

  -- 12. B goes quiet for 90 seconds: off the decks and out of the crowd.
  --     When C's track ends, nobody's left, and the room goes silent.
  execute 'reset role';
  update public.room_presence set last_seen = now() - interval '91 seconds' where user_id = b;
  update public.room_plays set started_at = now() - interval '1 hour' where id = (select play_id from public.room_state where id = 1);
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  select version into v from public.room_state where id = 1;
  st := public.room_here(null);
  if st->'play' <> 'null'::jsonb or jsonb_array_length(st->'djs') <> 0 or (st->'crowd' ? cb) then
    raise exception 'Rehearsal FAILED: the room didn''t empty: %', st;
  end if;
  if (st->>'version')::bigint <= v then raise exception 'Rehearsal FAILED: the room changed without saying so'; end if;
  if (select count(*) from public.room_recent() x where x.title in ('B One', 'C One', 'B Two')) < 3 then
    raise exception 'Rehearsal FAILED: Recently played is missing tracks';
  end if;
  checks := checks + 1;

  -- 13. The chat: B's message is there for D coming in later; a blank or
  --     long one is refused; C can't remove B's, the admin can, and it's
  --     gone for everyone.
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  mid := public.room_say('  rehearsal: hello room  ');
  begin
    perform public.room_say(repeat('x', 281));
    raise exception 'Rehearsal FAILED: a 281-character message went in';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'A message is 1 to 280 characters.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  perform set_config('request.jwt.claim.sub', d::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', d, 'role', 'authenticated')::text, true);
  st := public.room_here(null);
  if not exists (select 1 from jsonb_array_elements(st->'messages') m
                  where (m->>'id')::bigint = mid and m->>'body' = 'rehearsal: hello room' and m->>'who' = cb) then
    raise exception 'Rehearsal FAILED: the chat didn''t keep B''s message for D';
  end if;
  if jsonb_array_length(public.room_here(mid)->'messages') <> 0 then
    raise exception 'Rehearsal FAILED: asking for messages after the last one returned some';
  end if;
  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  begin
    perform public.room_remove_message(mid);
    raise exception 'Rehearsal FAILED: C removed B''s message';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'Only its writer or the admin can remove a message.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  n := (public.room_here(null)->>'chat_epoch')::int;
  perform public.room_remove_message(mid);
  st := public.room_here(null);
  if (st->>'chat_epoch')::int <> n + 1
     or exists (select 1 from jsonb_array_elements(st->'messages') m where (m->>'id')::bigint = mid) then
    raise exception 'Rehearsal FAILED: the removed message is still there';
  end if;
  checks := checks + 1;

  -- 14. Nobody reads the room's tables but the one row pages listen to,
  --     and a stranger reads and calls nothing.
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  if (select count(*) from public.room_state) <> 1 then raise exception 'Rehearsal FAILED: a member can''t read the room''s row'; end if;
  begin
    perform 1 from public.room_tracks;
    raise exception 'Rehearsal FAILED: a member read everyone''s libraries';
  exception when insufficient_privilege then
    null;
  end;
  begin
    perform 1 from public.room_messages;
    raise exception 'Rehearsal FAILED: a member read the chat''s table';
  exception when insufficient_privilege then
    null;
  end;
  execute 'reset role';
  execute 'set local role anon';
  begin
    perform 1 from public.room_state;
    raise exception 'Rehearsal FAILED: a stranger read the room';
  exception when insufficient_privilege then
    null;
  end;
  begin
    perform public.room_here(null);
    raise exception 'Rehearsal FAILED: a stranger came into the room';
  exception when insufficient_privilege then
    null;
  end;
  execute 'reset role';
  checks := checks + 1;

  raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;
end $$;
