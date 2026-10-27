-- A rehearsal of the round demo's practice ballot, run by the real
-- database and then undone: nothing it does is kept. Run it in the Supabase
-- SQL Editor after supabase/migrations/2026-10-27_demo_ballots.sql (README,
-- Round demo). It always ends in an error, on purpose, because an error
-- rolls everything back:
--
--   "Rehearsal passed: 9 checks held. Nothing was kept."  every rule held
--   "Rehearsal FAILED: ..."                              says which didn't
--
-- It plays two members, B and C (the first two who are neither admin nor
-- commissioner), signed in as them and as the 'authenticated' role, as the
-- site would, on the newest round that has tracks (Round 7 when it was
-- written), the way the demo does. A made-up site season (season99) gives
-- it a second round. All of it is rolled back.

do $$
declare
  a uuid; ca text;
  b uuid; cb text;
  c uuid; cc text;
  r uuid; r2 uuid;
  s1 uuid;
  row record;
  votes_before int; drafts_before int;
  n int;
  checks int := 0;
begin
  select user_id, competitor_id into a, ca from public.members where role = 'admin' order by created_at limit 1;
  select user_id, competitor_id into b, cb from public.members where role = 'member' order by created_at, user_id limit 1;
  select user_id, competitor_id into c, cc from public.members where role = 'member' order by created_at, user_id offset 1 limit 1;
  if a is null or c is null then raise exception 'Rehearsal FAILED: it needs the admin and two other members'; end if;
  select s.round_id into r from public.site_submissions s join public.site_rounds x on x.id = s.round_id
   order by x.closes_at desc limit 1;
  if r is null then raise exception 'Rehearsal FAILED: it needs a round with tracks'; end if;
  select id into s1 from public.site_submissions where round_id = r order by id limit 1;
  select count(*) into votes_before from public.site_votes;
  select count(*) into drafts_before from public.site_ballot_drafts;

  -- 1. B saves a practice draft, part of a ballot, and reads it back, trimmed.
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  if public.save_demo_ballot(r, jsonb_build_array(jsonb_build_object('submission', s1, 'points', 3, 'comment', '  From my phone  ')), false) is null then
    raise exception 'Rehearsal FAILED: saving should say when';
  end if;
  select * into row from public.my_demo_ballot(r);
  if row.draft <> jsonb_build_array(jsonb_build_object('submission', s1::text, 'points', 3, 'comment', 'From my phone'))
     or row.draft_saved_at is null or row.ballot <> '[]'::jsonb then
    raise exception 'Rehearsal FAILED: B should read back their draft, trimmed, and no ballot: % %', row.draft, row.ballot;
  end if;
  checks := checks + 1;

  -- 2. Saving again replaces it.
  perform public.save_demo_ballot(r, jsonb_build_array(jsonb_build_object('submission', s1, 'points', 4, 'comment', 'Changed on the computer')), false);
  select * into row from public.my_demo_ballot(r);
  if row.draft->0->>'comment' <> 'Changed on the computer' or jsonb_array_length(row.draft) <> 1 then
    raise exception 'Rehearsal FAILED: the second save should replace the first: %', row.draft;
  end if;
  checks := checks + 1;

  -- 3. Submitting keeps the practice ballot, and the draft with it.
  perform public.save_demo_ballot(r, jsonb_build_array(jsonb_build_object('submission', s1, 'points', 5, 'comment', '')), true);
  select * into row from public.my_demo_ballot(r);
  if row.ballot <> jsonb_build_array(jsonb_build_object('submission', s1::text, 'points', 5, 'comment', ''))
     or row.draft <> row.ballot then
    raise exception 'Rehearsal FAILED: a submit should keep the ballot and the draft: % %', row.ballot, row.draft;
  end if;
  checks := checks + 1;

  -- 4. What the demo can't make is refused: a track from another round,
  --    the same track twice, points that aren't a whole number, a long
  --    comment, and anything but a list.
  begin
    perform public.save_demo_ballot(r, jsonb_build_array(jsonb_build_object('submission', gen_random_uuid(), 'points', 1)), false);
    raise exception 'Rehearsal FAILED: a track from outside the round was taken';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'The ballot doesn''t add up. Reload the page and try again.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  begin
    perform public.save_demo_ballot(r, jsonb_build_array(jsonb_build_object('submission', s1, 'points', 1),
                                                         jsonb_build_object('submission', s1, 'points', 2)), false);
    raise exception 'Rehearsal FAILED: the same track twice was taken';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'The ballot doesn''t add up. Reload the page and try again.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  begin
    perform public.save_demo_ballot(r, jsonb_build_array(jsonb_build_object('submission', s1, 'points', 'lots')), false);
    raise exception 'Rehearsal FAILED: points that aren''t a number were taken';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'The ballot doesn''t add up. Reload the page and try again.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  begin
    perform public.save_demo_ballot(r, jsonb_build_array(jsonb_build_object('submission', s1, 'points', 1.5)), false);
    raise exception 'Rehearsal FAILED: half a point was taken';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'The ballot doesn''t add up. Reload the page and try again.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  begin
    perform public.save_demo_ballot(r, jsonb_build_array(jsonb_build_object('submission', s1, 'points', 0, 'comment', repeat('x', 2001))), false);
    raise exception 'Rehearsal FAILED: a 2001-character comment was taken';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'A comment can be at most 2000 characters.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  begin
    perform public.save_demo_ballot(r, '{"submission": 1}'::jsonb, false);
    raise exception 'Rehearsal FAILED: something that isn''t a list was taken';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'The ballot doesn''t add up. Reload the page and try again.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  -- 5. A refused save left the practice ballot as it was.
  select * into row from public.my_demo_ballot(r);
  if row.ballot->0->>'points' <> '5' then raise exception 'Rehearsal FAILED: a refused save changed it'; end if;
  checks := checks + 1;

  -- 6. C reads nothing of B's, and can't read the table.
  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  select count(*) into n from public.my_demo_ballot(r);
  if n <> 0 then raise exception 'Rehearsal FAILED: C read B''s practice ballot'; end if;
  begin
    perform 1 from public.site_demo_ballots;
    raise exception 'Rehearsal FAILED: a member read the practice table';
  exception when insufficient_privilege then
    null;
  end;
  execute 'reset role';
  checks := checks + 1;

  -- 7. A demo of a different round starts afresh.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.create_site_season(jsonb_build_object('key', 'season99', 'name', 'Rehearsal Demo',
    'first_playlist_at', now() + interval '1 day', 'rounds', jsonb_build_array(jsonb_build_object('name', 'X')),
    'players', jsonb_build_array(ca, cb, cc)));
  execute 'reset role';
  select id into r2 from public.site_rounds where season_key = 'season99';
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.save_demo_ballot(r2, '[]'::jsonb, false);
  select count(*) into n from public.my_demo_ballot(r);
  if n <> 0 then raise exception 'Rehearsal FAILED: the old round''s practice ballot should be gone'; end if;
  select * into row from public.my_demo_ballot(r2);
  if row.ballot <> '[]'::jsonb or row.draft <> '[]'::jsonb then
    raise exception 'Rehearsal FAILED: a new round''s demo should start empty';
  end if;
  execute 'reset role';
  checks := checks + 1;

  -- 8. None of it touched a real vote or a real draft.
  if (select count(*) from public.site_votes) <> votes_before
     or (select count(*) from public.site_ballot_drafts) <> drafts_before then
    raise exception 'Rehearsal FAILED: the practice ballot touched a real vote or draft';
  end if;
  checks := checks + 1;

  -- 9. A stranger can't save, read or see any of it.
  execute 'set local role anon';
  begin
    perform public.save_demo_ballot(r, '[]'::jsonb, false);
    raise exception 'Rehearsal FAILED: a stranger could save';
  exception when insufficient_privilege then
    null;
  end;
  begin
    perform 1 from public.site_demo_ballots;
    raise exception 'Rehearsal FAILED: a stranger could read the practice table';
  exception when insufficient_privilege then
    null;
  end;
  execute 'reset role';
  checks := checks + 1;

  raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;
end $$;
