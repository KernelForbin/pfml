-- A rehearsal of ballot drafts, run by the real database and then undone:
-- nothing it does is kept. Run it in the Supabase SQL Editor after
-- supabase/migrations/2026-10-27_ballot_drafts.sql (README, Voting on the
-- site, Drafts). It always ends in an error, on purpose, because an error
-- rolls everything back:
--
--   "Rehearsal passed: 11 checks held. Nothing was kept."  every rule held
--   "Rehearsal FAILED: ..."                               says which didn't
--
-- It plays the admin and the first two members who are neither admin nor
-- commissioner (B and C), signed in as them and as the 'authenticated' role,
-- as the site would, through one round of a made-up site season (season99):
-- B and C each send a track, the admin doesn't; then voting, then the
-- close. All of it is rolled back.

do $$
declare
  a uuid; ca text;
  b uuid; cb text;
  c uuid; cc text;
  r uuid;
  ml uuid;
  rr public.site_rounds%rowtype;
  sb uuid; sc uuid;
  tag_b text; tag_c text;
  d jsonb;
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
  perform public.create_site_season(jsonb_build_object('key', 'season99', 'name', 'Rehearsal Drafts',
    'first_playlist_at', now() + interval '1 day', 'rounds', jsonb_build_array(jsonb_build_object('name', 'D')),
    'players', jsonb_build_array(ca, cb, cc)));
  execute 'reset role';
  select id into r from public.site_rounds where season_key = 'season99';
  update public.site_rounds set opens_at = now() - interval '1 hour' where id = r;

  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  tag_b := public.submit_track(r, 'youtube', 'rehearsal0b');

  -- 1. No draft while submissions are open.
  begin
    perform public.save_ballot_draft(r, '[]'::jsonb);
    raise exception 'Rehearsal FAILED: a draft was saved while submissions were open';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'Voting for this round isn''t open.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  tag_c := public.submit_track(r, 'youtube', 'rehearsal0c');
  execute 'reset role';

  -- Submissions close: voting.
  update public.site_rounds set closed_at = now() where id = r;
  if public.site_round_phase(r) <> 'voting' then raise exception 'Rehearsal FAILED: the round should be voting'; end if;
  select * into rr from public.site_rounds where id = r;
  select id into sb from public.site_submissions where round_id = r and tag = tag_b;
  select id into sc from public.site_submissions where round_id = r and tag = tag_c;

  -- 2. B saves part of a ballot: a few points and a comment, far from all
  --    of them, and reads it back, trimmed.
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  if public.save_ballot_draft(r, jsonb_build_array(jsonb_build_object('submission', sc, 'points', 2, 'comment', '  Nice  '),
                                                   jsonb_build_object('submission', sb, 'points', 0, 'comment', 'Mine'))) is null then
    raise exception 'Rehearsal FAILED: saving a draft should say when';
  end if;
  select m.ballot into d from public.my_ballot_draft(r) m;
  if d is null or jsonb_array_length(d) <> 2
     or not d @> jsonb_build_array(jsonb_build_object('submission', sc, 'points', 2, 'comment', 'Nice'))
     or not d @> jsonb_build_array(jsonb_build_object('submission', sb, 'points', 0, 'comment', 'Mine')) then
    raise exception 'Rehearsal FAILED: B should read back their draft, trimmed: %', d;
  end if;
  checks := checks + 1;

  -- 3. Saving again replaces it, and an empty line is left out.
  perform public.save_ballot_draft(r, jsonb_build_array(jsonb_build_object('submission', sc, 'points', 3, 'comment', ''),
                                                        jsonb_build_object('submission', sb, 'points', 0, 'comment', '')));
  select m.ballot into d from public.my_ballot_draft(r) m;
  if d <> jsonb_build_array(jsonb_build_object('submission', sc, 'points', 3, 'comment', '')) then
    raise exception 'Rehearsal FAILED: the second save should replace the first: %', d;
  end if;
  execute 'reset role';
  if (select count(*) from public.site_ballot_drafts where round_id = r and user_id = b) <> 1 then
    raise exception 'Rehearsal FAILED: B should have one draft';
  end if;
  checks := checks + 1;

  -- 4. The rules still hold: not over a track's most, not on your own track,
  --    nothing from another round.
  execute 'set local role authenticated';
  begin
    perform public.save_ballot_draft(r, jsonb_build_array(jsonb_build_object('submission', sc, 'points', rr.max_per_track + 1, 'comment', '')));
    raise exception 'Rehearsal FAILED: a draft went over a track''s most';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'At most % points on one track.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  begin
    perform public.save_ballot_draft(r, jsonb_build_array(jsonb_build_object('submission', sb, 'points', 1, 'comment', '')));
    raise exception 'Rehearsal FAILED: a draft gave points to the voter''s own track';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'You can''t give points to your own track.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  begin
    perform public.save_ballot_draft(r, jsonb_build_array(jsonb_build_object('submission', gen_random_uuid(), 'points', 1, 'comment', '')));
    raise exception 'Rehearsal FAILED: a draft took a track from outside the round';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'The ballot doesn''t add up. Reload the page and try again.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  -- 5. A refused save leaves the last good draft as it was.
  select m.ballot into d from public.my_ballot_draft(r) m;
  if d <> jsonb_build_array(jsonb_build_object('submission', sc, 'points', 3, 'comment', '')) then
    raise exception 'Rehearsal FAILED: a refused save changed the draft: %', d;
  end if;
  checks := checks + 1;

  -- 6. C reads no draft: not B's, and they have none.
  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  select count(*) into n from public.my_ballot_draft(r);
  if n <> 0 then raise exception 'Rehearsal FAILED: C read a draft that isn''t theirs'; end if;
  begin
    perform 1 from public.site_ballot_drafts;
    raise exception 'Rehearsal FAILED: a member read the drafts table';
  exception when insufficient_privilege then
    null;
  end;
  checks := checks + 1;

  -- 7. The admin, with no track in the round, can't save one.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  begin
    perform public.save_ballot_draft(r, '[]'::jsonb);
    raise exception 'Rehearsal FAILED: a player with no track saved a draft';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'Only players with a track in this round can vote.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  -- 8. A draft never counts: B isn't among the voters, and has no votes.
  select count(*) into n from public.site_round_voters(r);
  if n <> 0 then raise exception 'Rehearsal FAILED: a draft counted as a vote'; end if;
  execute 'reset role';
  if exists (select 1 from public.site_votes where round_id = r) then
    raise exception 'Rehearsal FAILED: a draft wrote a vote';
  end if;
  checks := checks + 1;

  -- 9. A round voted in Music League, Round 7 among them, takes no draft.
  select id into ml from public.site_rounds where not votes_on_site order by created_at desc limit 1;
  if ml is not null then
    perform set_config('request.jwt.claim.sub', b::text, true);
    perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
    execute 'set local role authenticated';
    begin
      perform public.save_ballot_draft(ml, '[]'::jsonb);
      raise exception 'Rehearsal FAILED: a Music League round took a draft';
    exception when others then
      if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
      if sqlerrm <> 'Voting for this round isn''t open.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
    end;
    execute 'reset role';
  end if;
  checks := checks + 1;

  -- 10. Once voting closes, no saving and no reading back.
  update public.site_rounds set voting_closed_at = now() where id = r;
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  begin
    perform public.save_ballot_draft(r, '[]'::jsonb);
    raise exception 'Rehearsal FAILED: a draft was saved after voting closed';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'Voting for this round isn''t open.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  select count(*) into n from public.my_ballot_draft(r);
  if n <> 0 then raise exception 'Rehearsal FAILED: a draft was readable after voting closed'; end if;
  execute 'reset role';
  checks := checks + 1;

  -- 11. A stranger can't save, read or see any of it.
  execute 'set local role anon';
  begin
    perform public.save_ballot_draft(r, '[]'::jsonb);
    raise exception 'Rehearsal FAILED: a stranger could save a draft';
  exception when insufficient_privilege then
    null;
  end;
  begin
    perform 1 from public.site_ballot_drafts;
    raise exception 'Rehearsal FAILED: a stranger could read the drafts';
  exception when insufficient_privilege then
    null;
  end;
  execute 'reset role';
  checks := checks + 1;

  raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;
end $$;
