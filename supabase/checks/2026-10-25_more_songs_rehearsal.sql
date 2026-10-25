-- A rehearsal of more songs a round and downvotes, run by the real database
-- and then undone: nothing it does is kept. Run it in the Supabase SQL Editor
-- after supabase/migrations/2026-10-25_more_songs.sql (README, More songs and
-- downvotes). It always ends in an error, on purpose, because an error rolls
-- everything back:
--
--   "Rehearsal passed: 16 checks held. Nothing was kept."  every rule held
--   "Rehearsal FAILED: ..."                               says which didn't
--
-- It plays the admin and the first two members who are neither admin nor
-- commissioner (B and C), signed in as them and as the 'authenticated' role,
-- as the site would, in two made-up seasons: season99 takes 2 songs a round
-- with 3 downvotes (at most 2 on one song) and 4 points (at most 3 on one);
-- season98 takes 1 song. Nobody is signed in as them and nothing reaches
-- them: all of it is rolled back.

do $$
declare
  a uuid; ca text;
  b uuid; cb text;
  c uuid; cc text;
  r1 uuid; r2 uuid; q1 uuid;
  a1 uuid; a2 uuid; b1 uuid; b2 uuid; c1 uuid; c2 uuid;
  tag1 text; tag2 text;
  rr record;
  n int;
  checks int := 0;
begin
  select user_id, competitor_id into a, ca from public.members where role = 'admin' order by created_at limit 1;
  select user_id, competitor_id into b, cb from public.members where role = 'member' order by created_at, user_id limit 1;
  select user_id, competitor_id into c, cc from public.members where role = 'member' order by created_at, user_id offset 1 limit 1;
  if a is null or c is null then raise exception 'Rehearsal FAILED: it needs the admin and two other members'; end if;

  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.create_site_season(jsonb_build_object('key', 'season99', 'name', 'Rehearsal Two Songs', 'timing', 'accelerated',
    'songs_per_round', 2, 'downvotes', 3, 'max_down_per_track', 2, 'point_budget', 4, 'max_per_track', 3,
    'first_playlist_at', now() + interval '1 day',
    'rounds', jsonb_build_array(jsonb_build_object('name', 'R1'), jsonb_build_object('name', 'R2')),
    'players', jsonb_build_array(ca, cb, cc)));
  execute 'reset role';
  select id into r1 from public.site_rounds where season_key = 'season99' and name = 'R1';
  select id into r2 from public.site_rounds where season_key = 'season99' and name = 'R2';

  -- 1. Two songs each, not three.
  execute 'set local role authenticated';
  tag1 := public.submit_track(r1, 'spotify', repeat('A', 22));
  tag2 := public.submit_track(r1, 'spotify', repeat('B', 22));
  begin
    perform public.submit_track(r1, 'spotify', repeat('C', 22));
    raise exception 'Rehearsal FAILED: a third song went in';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'You''ve sent all 2 of your tracks for this round.%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  -- 2. The same track twice is still refused, yours included.
  begin
    perform public.withdraw_track(r1, tag2);
    perform public.submit_track(r1, 'spotify', repeat('A', 22));
    raise exception 'Rehearsal FAILED: the same track went in twice';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'Someone has already submitted that track this round.%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  -- 3. Taking one back by its tag makes room for another (the failed try
  --    above undid its own withdrawal, so take it back again).
  perform public.withdraw_track(r1, tag2);
  perform public.submit_track(r1, 'youtube', 'aaaaaaaaaa2');
  execute 'reset role';
  select count(*) into n from public.site_submission_owners where round_id = r1 and user_id = a;
  if n <> 2 or exists (select 1 from public.site_submissions where round_id = r1 and tag = tag2 and platform = 'spotify') then
    raise exception 'Rehearsal FAILED: A should have the first track and the YouTube one (got % tracks)', n;
  end if;
  checks := checks + 1;

  -- 4. Accelerated waits for every song from every player.
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.submit_track(r1, 'youtube', 'bbbbbbbbbb1');
  perform public.submit_track(r1, 'youtube', 'bbbbbbbbbb2');
  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  perform public.submit_track(r1, 'youtube', 'cccccccccc1');
  if public.site_round_phase(r1) <> 'submitting' then
    raise exception 'Rehearsal FAILED: the round closed with one of C''s songs still to come';
  end if;
  perform public.submit_track(r1, 'youtube', 'cccccccccc2');
  execute 'reset role';
  if public.site_round_phase(r1) <> 'voting' then
    raise exception 'Rehearsal FAILED: the round should close once all six songs are in';
  end if;
  checks := checks + 1;

  select o.submission_id into a1 from public.site_submission_owners o join public.site_submissions s on s.id = o.submission_id
   where o.round_id = r1 and o.user_id = a and s.platform = 'spotify';
  select o.submission_id into a2 from public.site_submission_owners o join public.site_submissions s on s.id = o.submission_id
   where o.round_id = r1 and o.user_id = a and s.platform = 'youtube';
  select o.submission_id into b1 from public.site_submission_owners o join public.site_submissions s on s.id = o.submission_id
   where o.round_id = r1 and s.track = 'bbbbbbbbbb1';
  select o.submission_id into b2 from public.site_submission_owners o join public.site_submissions s on s.id = o.submission_id
   where o.round_id = r1 and s.track = 'bbbbbbbbbb2';
  select o.submission_id into c1 from public.site_submission_owners o join public.site_submissions s on s.id = o.submission_id
   where o.round_id = r1 and s.track = 'cccccccccc1';
  select o.submission_id into c2 from public.site_submission_owners o join public.site_submissions s on s.id = o.submission_id
   where o.round_id = r1 and s.track = 'cccccccccc2';

  -- 5-8. A's bad ballots: points on their own second track, a downvote too
  --      big for one song, too many downvotes, not every upvote spent.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  begin
    perform public.cast_ballot(r1, jsonb_build_array(jsonb_build_object('submission', a2, 'points', 1),
                                                     jsonb_build_object('submission', b1, 'points', 3)));
    raise exception 'Rehearsal FAILED: points went on the voter''s own second track';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'You can''t give points to your own track.%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;
  begin
    perform public.cast_ballot(r1, jsonb_build_array(jsonb_build_object('submission', b1, 'points', 3), jsonb_build_object('submission', b2, 'points', 1),
                                                     jsonb_build_object('submission', c1, 'points', -3)));
    raise exception 'Rehearsal FAILED: 3 downvotes went on one song';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'At most 2 downvotes on one track.%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;
  begin
    perform public.cast_ballot(r1, jsonb_build_array(jsonb_build_object('submission', b1, 'points', 3), jsonb_build_object('submission', b2, 'points', 1),
                                                     jsonb_build_object('submission', c1, 'points', -2), jsonb_build_object('submission', c2, 'points', -2)));
    raise exception 'Rehearsal FAILED: 4 downvotes went in, of 3';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'At most 3 downvotes in all.%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;
  begin
    perform public.cast_ballot(r1, jsonb_build_array(jsonb_build_object('submission', b1, 'points', 3), jsonb_build_object('submission', c1, 'points', -2)));
    raise exception 'Rehearsal FAILED: a ballot with an upvote left over went in';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'Spend exactly 4 points.%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  -- 9. A's good ballot, with a downvote on C's first song.
  perform public.cast_ballot(r1, jsonb_build_array(jsonb_build_object('submission', b1, 'points', 3), jsonb_build_object('submission', b2, 'points', 1),
                                                   jsonb_build_object('submission', c1, 'points', -2)));
  execute 'reset role';
  if (select points from public.site_votes where submission_id = c1 and user_id = a) <> -2 then
    raise exception 'Rehearsal FAILED: the downvote wasn''t kept';
  end if;
  checks := checks + 1;

  -- 10. B's ballot needs no downvotes; C hasn't voted, so voting stays open.
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.cast_ballot(r1, jsonb_build_array(jsonb_build_object('submission', c1, 'points', 3), jsonb_build_object('submission', a1, 'points', 1)));
  execute 'reset role';
  if public.site_round_phase(r1) <> 'voting' then
    raise exception 'Rehearsal FAILED: voting closed with C still to vote';
  end if;
  checks := checks + 1;

  -- 11. C never votes: at the close, C's first song keeps only its downvote
  --     (-2), though voters gave it 1 in all.
  update public.site_rounds set voting_closed_at = now() where id = r1;
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  select * into rr from public.site_round_results(r1) x where x.submission_id = c1;
  execute 'reset role';
  if rr.points <> -2 or rr.earned <> 1 or rr.voted then
    raise exception 'Rehearsal FAILED: C''s song should score -2 of the 1 it earned (got %, %)', rr.points, rr.earned;
  end if;
  checks := checks + 1;

  -- 12. A vote row holds down to -20, no lower.
  begin
    insert into public.site_votes (round_id, submission_id, user_id, points) values (r1, c2, b, -21);
    raise exception 'Rehearsal FAILED: a vote of -21 went in';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like '%site_votes_points_range%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  -- 13. Taking a track back once submissions have closed is refused.
  execute 'set local role authenticated';
  begin
    perform public.withdraw_track(r1, tag1);
    raise exception 'Rehearsal FAILED: a track was taken back after the close';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
  end;
  checks := checks + 1;

  -- 14. Songs a round: a season's change reaches round 2 (not opened), not
  --     round 1; and once a round has opened, nobody can change it.
  perform public.update_site_season('season99', '{"songs_per_round": 3}'::jsonb);
  execute 'reset role';
  if (select songs_per_round from public.site_rounds where id = r1) <> 2 or (select songs_per_round from public.site_rounds where id = r2) <> 3 then
    raise exception 'Rehearsal FAILED: the change should reach round 2 only';
  end if;
  checks := checks + 1;
  begin
    update public.site_rounds set songs_per_round = 1 where id = r1;
    raise exception 'Rehearsal FAILED: an opened round''s songs changed';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'How many songs a round takes can''t change once it has opened.%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  -- 15. One song a round still swaps: same tag, still one track.
  execute 'set local role authenticated';
  perform public.create_site_season(jsonb_build_object('key', 'season98', 'name', 'Rehearsal One Song',
    'first_playlist_at', now() + interval '1 day', 'rounds', jsonb_build_array(jsonb_build_object('name', 'Q1')),
    'players', jsonb_build_array(ca, cb)));
  execute 'reset role';
  select id into q1 from public.site_rounds where season_key = 'season98';
  execute 'set local role authenticated';
  tag1 := public.submit_track(q1, 'youtube', 'qqqqqqqqqq1');
  tag2 := public.submit_track(q1, 'youtube', 'qqqqqqqqqq2');
  execute 'reset role';
  if tag1 <> tag2 or (select count(*) from public.site_submission_owners where round_id = q1 and user_id = a) <> 1
     or not exists (select 1 from public.site_submissions where round_id = q1 and track = 'qqqqqqqqqq2') then
    raise exception 'Rehearsal FAILED: with one song a round, sending again should swap it';
  end if;
  checks := checks + 1;

  raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;
end $$;
