-- A rehearsal of the note switch, run by the real database and then undone:
-- nothing it does is kept. Run it in the Supabase SQL Editor after
-- supabase/migrations/2026-10-25_note_toggle.sql (README, Commissioner
-- extras, Notes). It always ends in an error, on purpose, because an error
-- rolls everything back:
--
--   "Rehearsal passed: 10 checks held. Nothing was kept."  every rule held
--   "Rehearsal FAILED: ..."                               says which didn't
--
-- It plays the admin and the first two members who are neither admin nor
-- commissioner (B and C), signed in as them and as the 'authenticated' role,
-- as the site would, through one round of a made-up site season (season99):
-- open, voting, finished. B's note stays hidden until the results; C shows
-- theirs while people vote. All of it is rolled back.

do $$
declare
  a uuid; ca text;
  b uuid; cb text;
  c uuid; cc text;
  r uuid;
  who uuid;
  tag_b text; tag_c text;
  n int;
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
  perform public.create_site_season(jsonb_build_object('key', 'season99', 'name', 'Rehearsal Notes',
    'first_playlist_at', now() + interval '1 day', 'rounds', jsonb_build_array(jsonb_build_object('name', 'N')),
    'players', jsonb_build_array(ca, cb, cc)));
  execute 'reset role';
  select id into r from public.site_rounds where season_key = 'season99';
  update public.site_rounds set opens_at = now() - interval '1 hour' where id = r;

  -- B sends a track with a note, switch off; C with a note, switch on.
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  tag_b := public.submit_track(r, 'youtube', 'rehearsal0b');
  perform public.set_submission_note(r, tag_b, '  Hidden until the results.  ', false);

  -- 1. B reads their own note and its switch.
  if not exists (select 1 from public.my_submission(r) m
                  where m.tag = tag_b and m.note = 'Hidden until the results.' and not m.note_in_voting) then
    raise exception 'Rehearsal FAILED: B should read their note, trimmed, switch off';
  end if;
  checks := checks + 1;

  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  tag_c := public.submit_track(r, 'youtube', 'rehearsal0c');
  perform public.set_submission_note(r, tag_c, 'Shown while you vote.', false);
  perform public.set_submission_note(r, tag_c, 'Shown while you vote.', true);

  -- 2. While submissions are open nobody reads any note, not even C.
  select count(*) into n from public.site_submission_notes where round_id = r;
  if n <> 0 then raise exception 'Rehearsal FAILED: a note was readable while submissions were open'; end if;
  checks := checks + 1;
  execute 'reset role';

  -- 3. Changing the switch updates the note, not a second one.
  if (select count(*) from public.site_submission_notes where round_id = r) <> 2
     or not (select n2.in_voting from public.site_submission_notes n2
               join public.site_submissions s on s.id = n2.submission_id
              where s.round_id = r and s.tag = tag_c) then
    raise exception 'Rehearsal FAILED: C''s switch should be on, on the one note';
  end if;
  checks := checks + 1;

  -- 4. An empty note clears it; B writes theirs again.
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.set_submission_note(r, tag_b, '   ', true);
  execute 'reset role';
  if exists (select 1 from public.site_submission_notes n2 join public.site_submissions s on s.id = n2.submission_id
              where s.round_id = r and s.tag = tag_b) then
    raise exception 'Rehearsal FAILED: an empty note should clear it';
  end if;
  checks := checks + 1;
  execute 'set local role authenticated';
  perform public.set_submission_note(r, tag_b, 'Hidden until the results.', false);
  execute 'reset role';

  -- Submissions close: voting.
  update public.site_rounds set closed_at = now() where id = r;
  if public.site_round_phase(r) <> 'voting' then raise exception 'Rehearsal FAILED: the round should be voting'; end if;

  -- 5. During voting, B, C and the admin read C's note and not B's.
  foreach who in array array[a, b, c] loop
    perform set_config('request.jwt.claim.sub', who::text, true);
    perform set_config('request.jwt.claims', json_build_object('sub', who, 'role', 'authenticated')::text, true);
    execute 'set local role authenticated';
    if (select count(*) from public.site_submission_notes where round_id = r) <> 1
       or not exists (select 1 from public.site_submission_notes where round_id = r and note = 'Shown while you vote.') then
      raise exception 'Rehearsal FAILED: during voting only the note switched on should show';
    end if;
    execute 'reset role';
  end loop;
  checks := checks + 1;

  -- 6. After the close nobody changes a note.
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  begin
    perform public.set_submission_note(r, tag_b, 'Too late', true);
    raise exception 'Rehearsal FAILED: a note changed after submissions closed';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'Submissions for this round are closed.%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  -- 7. Once voting closes, every note shows.
  execute 'reset role';
  update public.site_rounds set voting_closed_at = now() where id = r;
  execute 'set local role authenticated';
  if (select count(*) from public.site_submission_notes where round_id = r) <> 2 then
    raise exception 'Rehearsal FAILED: after the results every note should show';
  end if;
  checks := checks + 1;
  execute 'reset role';

  -- 8. The export carries both.
  ex := public.site_rounds_export();
  select count(*) into n from jsonb_array_elements(ex->'rounds') x, jsonb_array_elements(x->'submissions') s
   where x->>'id' = r::text and s->>'note' in ('Hidden until the results.', 'Shown while you vote.');
  if n <> 2 then raise exception 'Rehearsal FAILED: the export should carry both notes'; end if;
  checks := checks + 1;

  -- 9. A stranger reads nothing.
  execute 'set local role anon';
  begin
    perform 1 from public.site_submission_notes;
    raise exception 'Rehearsal FAILED: a stranger could read the notes';
  exception when insufficient_privilege then
    null;
  end;
  execute 'reset role';
  checks := checks + 1;

  -- 10. The old column is gone, so no note can be read off a track.
  if exists (select 1 from information_schema.columns
              where table_schema = 'public' and table_name = 'site_submissions' and column_name = 'note') then
    raise exception 'Rehearsal FAILED: site_submissions still has a note column';
  end if;
  checks := checks + 1;

  raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;
end $$;
