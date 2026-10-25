-- A full rehearsal of voting on the site, run by the real database and then
-- undone: nothing it does is kept. Run it in the Supabase SQL Editor after
-- supabase/migrations/2026-10-25_site_voting.sql (README, Voting on the
-- site). It always ends in an error, on purpose, because an error rolls
-- everything back:
--
--   "Rehearsal passed: 25 checks held. Nothing was kept."  every rule held
--   "Rehearsal FAILED: ..."                               says which didn't
--
-- (24 checks if there are only three members: one needs a fourth.)
--
-- It plays the first three members to join (the functions see the same
-- auth.uid() they will for real). Nobody is signed in as them and nothing
-- reaches them: the round, tracks and ballots it makes are all rolled back.
-- The two helpers below are temporary, gone when the editor's session ends.

create or replace function pg_temp.as_member(u uuid) returns void language plpgsql as $f$
begin
  perform set_config('request.jwt.claim.sub', coalesce(u::text, ''), true);
  perform set_config('request.jwt.claims', json_build_object('sub', u, 'role', 'authenticated')::text, true);
end $f$;

-- Runs q and passes only if it fails with a message like pattern.
create or replace function pg_temp.expect_error(q text, pattern text) returns void language plpgsql as $f$
begin
  execute q;
  raise exception 'Rehearsal FAILED: expected an error like "%" from: %', pattern, q;
exception when others then
  if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
  if sqlerrm not like pattern then
    raise exception 'Rehearsal FAILED: expected "%", got "%" from: %', pattern, sqlerrm, q;
  end if;
end $f$;

do $$
declare
  a uuid; b uuid; c uuid; d uuid;
  last_round uuid;
  rid uuid;
  sa uuid; sb uuid; sc uuid;
  n int;
  checks int := 0;
  r record;
begin
  select user_id into a from public.members order by created_at, user_id limit 1;
  select user_id into b from public.members order by created_at, user_id offset 1 limit 1;
  select user_id into c from public.members order by created_at, user_id offset 2 limit 1;
  select user_id into d from public.members order by created_at, user_id offset 3 limit 1;
  if c is null then raise exception 'Rehearsal FAILED: it needs at least three members'; end if;

  -- 1. A round that already exists (the latest: Round 7) can't get site voting.
  select id into last_round from public.site_rounds where not votes_on_site order by created_at desc limit 1;
  if last_round is not null then
    perform pg_temp.expect_error(format(
      'update public.site_rounds set votes_on_site = true, voting_closes_at = closes_at + interval ''2 days'' where id = %L', last_round),
      'Voting on the site is chosen when a round is opened%');
    checks := checks + 1;
  end if;

  -- 2. A new round that votes here, submitting first.
  insert into public.site_rounds (season_key, name, prompt, closes_at, votes_on_site, voting_closes_at)
  values ('season99', 'Rehearsal', '', now() + interval '1 day', true, now() + interval '2 days')
  returning id into rid;
  if public.site_round_phase(rid) <> 'submitting' then raise exception 'Rehearsal FAILED: a new round isn''t submitting'; end if;
  checks := checks + 1;
  if (select point_budget from public.site_rounds where id = rid) <> 19
     or (select max_per_track from public.site_rounds where id = rid) <> 5
     or (select nonvoters_keep_points from public.site_rounds where id = rid) then
    raise exception 'Rehearsal FAILED: the default rules aren''t 19, 5 and non-voters score 0';
  end if;
  checks := checks + 1;

  -- 3. Three tracks in, one each.
  perform pg_temp.as_member(a); perform public.submit_track(rid, 'spotify', 'AAAAAAAAAAAAAAAAAAAAAA');
  perform pg_temp.as_member(b); perform public.submit_track(rid, 'spotify', 'BBBBBBBBBBBBBBBBBBBBBB');
  perform pg_temp.as_member(c); perform public.submit_track(rid, 'spotify', 'CCCCCCCCCCCCCCCCCCCCCC');
  select o.submission_id into sa from public.site_submission_owners o where o.round_id = rid and o.user_id = a;
  select o.submission_id into sb from public.site_submission_owners o where o.round_id = rid and o.user_id = b;
  select o.submission_id into sc from public.site_submission_owners o where o.round_id = rid and o.user_id = c;
  if sa is null or sb is null or sc is null then raise exception 'Rehearsal FAILED: the three tracks didn''t go in'; end if;
  checks := checks + 1;

  -- 4. Nobody votes while submissions are open.
  perform pg_temp.as_member(a);
  perform pg_temp.expect_error(format('select public.cast_ballot(%L, %L::jsonb)', rid,
    json_build_array(json_build_object('submission', sb, 'points', 19))), 'Voting for this round isn''t open%');
  checks := checks + 1;

  -- 5. The rules can change while submissions are open (3 players can't
  --    spend 19 at 5 a track, so the rehearsal plays 4 points, 3 a track).
  update public.site_rounds set point_budget = 4, max_per_track = 3 where id = rid;
  checks := checks + 1;

  -- 6. Submissions close: voting opens, and the rules are fixed.
  update public.site_rounds set closed_at = now() where id = rid;
  if public.site_round_phase(rid) <> 'voting' then raise exception 'Rehearsal FAILED: closing submissions didn''t open voting'; end if;
  checks := checks + 1;
  perform pg_temp.expect_error(format('update public.site_rounds set point_budget = 5 where id = %L', rid),
    'The voting rules can''t change once submissions have closed%');
  checks := checks + 1;
  perform pg_temp.expect_error(format('update public.site_rounds set votes_on_site = false, voting_closes_at = null where id = %L', rid),
    'Voting on the site is chosen when a round is opened%');
  checks := checks + 1;

  -- 7. Ballots that break a rule are refused.
  perform pg_temp.as_member(a);
  perform pg_temp.expect_error(format('select public.cast_ballot(%L, %L::jsonb)', rid,
    json_build_array(json_build_object('submission', sa, 'points', 2), json_build_object('submission', sb, 'points', 2))),
    'You can''t give points to your own track%');
  checks := checks + 1;
  perform pg_temp.expect_error(format('select public.cast_ballot(%L, %L::jsonb)', rid,
    json_build_array(json_build_object('submission', sb, 'points', 4))), 'At most 3 points on one track%');
  checks := checks + 1;
  perform pg_temp.expect_error(format('select public.cast_ballot(%L, %L::jsonb)', rid,
    json_build_array(json_build_object('submission', sb, 'points', 3), json_build_object('submission', sc, 'points', 3))),
    'Spend exactly 4 points. This ballot has 6%');
  checks := checks + 1;
  perform pg_temp.expect_error(format('select public.cast_ballot(%L, %L::jsonb)', rid,
    json_build_array(json_build_object('submission', sb, 'points', 5), json_build_object('submission', sc, 'points', -1))),
    'Points can''t be negative%');
  checks := checks + 1;
  perform pg_temp.expect_error(format('select public.cast_ballot(%L, %L::jsonb)', rid,
    json_build_array(json_build_object('submission', sb, 'points', 2), json_build_object('submission', sb, 'points', 2))),
    'The ballot doesn''t add up%');
  checks := checks + 1;
  perform pg_temp.expect_error(format('select public.cast_ballot(%L, %L::jsonb)', rid,
    json_build_array(json_build_object('submission', gen_random_uuid(), 'points', 4))), 'The ballot doesn''t add up%');
  checks := checks + 1;
  if d is not null then
    perform pg_temp.as_member(d);
    perform pg_temp.expect_error(format('select public.cast_ballot(%L, %L::jsonb)', rid,
      json_build_array(json_build_object('submission', sa, 'points', 4))), 'Only players with a track in this round can vote%');
    checks := checks + 1;
  end if;
  perform pg_temp.as_member(null);
  perform pg_temp.expect_error(format('select public.cast_ballot(%L, %L::jsonb)', rid,
    json_build_array(json_build_object('submission', sa, 'points', 4))), 'Only league members can vote%');
  checks := checks + 1;

  -- 8. Good ballots: A gives 3 and 1 and comments on their own track; B
  --    votes, then changes their ballot; C doesn't vote.
  perform pg_temp.as_member(a);
  perform public.cast_ballot(rid, json_build_array(
    json_build_object('submission', sb, 'points', 3, 'comment', 'great'),
    json_build_object('submission', sc, 'points', 1),
    json_build_object('submission', sa, 'points', 0, 'comment', 'mine, sorry')));
  if (select count(*) from public.my_ballot(rid)) <> 3 then raise exception 'Rehearsal FAILED: A''s ballot isn''t 3 rows'; end if;
  checks := checks + 1;
  perform pg_temp.as_member(b);
  perform public.cast_ballot(rid, json_build_array(json_build_object('submission', sa, 'points', 2), json_build_object('submission', sc, 'points', 2)));
  perform public.cast_ballot(rid, json_build_array(json_build_object('submission', sa, 'points', 1), json_build_object('submission', sc, 'points', 3)));
  if (select count(*) from public.my_ballot(rid)) <> 2 or (select sum(points) from public.my_ballot(rid)) <> 4 then
    raise exception 'Rehearsal FAILED: B''s second ballot didn''t replace the first';
  end if;
  checks := checks + 1;
  if (select count(*) from public.site_round_voters(rid)) <> 2 then raise exception 'Rehearsal FAILED: voters isn''t A and B'; end if;
  checks := checks + 1;
  if (select count(*) from public.site_round_results(rid)) <> 0 or (select count(*) from public.site_round_votes(rid)) <> 0 then
    raise exception 'Rehearsal FAILED: results or votes showed before voting closed';
  end if;
  checks := checks + 1;

  -- 9. Voting closes: no more ballots, and the results show.
  update public.site_rounds set voting_closed_at = now() where id = rid;
  if public.site_round_phase(rid) <> 'finished' then raise exception 'Rehearsal FAILED: closing voting didn''t finish the round'; end if;
  checks := checks + 1;
  perform pg_temp.expect_error(format('select public.cast_ballot(%L, %L::jsonb)', rid,
    json_build_array(json_build_object('submission', sa, 'points', 4))), 'Voting for this round isn''t open%');
  checks := checks + 1;
  for r in select * from public.site_round_results(rid) loop
    if r.submission_id = sa and not (r.points = 1 and r.earned = 1 and r.voted) then
      raise exception 'Rehearsal FAILED: A''s track should score 1 (got %, earned %)', r.points, r.earned;
    elsif r.submission_id = sb and not (r.points = 3 and r.earned = 3 and r.voted) then
      raise exception 'Rehearsal FAILED: B''s track should score 3 (got %, earned %)', r.points, r.earned;
    elsif r.submission_id = sc and not (r.points = 0 and r.earned = 4 and not r.voted) then
      raise exception 'Rehearsal FAILED: C didn''t vote, so their track should score 0 of the 4 it earned (got %, earned %)', r.points, r.earned;
    end if;
  end loop;
  if (select count(distinct competitor_id) from public.site_round_results(rid)) <> 3 then
    raise exception 'Rehearsal FAILED: the results don''t name all three submitters';
  end if;
  checks := checks + 1;
  if (select count(*) from public.site_round_votes(rid)) <> 5 then
    raise exception 'Rehearsal FAILED: expected 5 vote rows (A: 2 votes and a comment, B: 2 votes)';
  end if;
  checks := checks + 1;

  raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;
end $$;
