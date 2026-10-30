-- A rehearsal of hidden prompts and guesses, run by the real database and
-- then undone: nothing it does is kept. Run it in the Supabase SQL Editor
-- after supabase/migrations/2026-10-29_hidden_prompts.sql, its hotfix and
-- 2026-10-29_hidden_prompts_names.sql (README, Hidden prompts and guesses). It always ends in an error, on purpose, because an
-- error rolls everything back:
--
--   "Rehearsal passed: 13 checks held. Nothing was kept."  every rule held
--   "Rehearsal FAILED: ..."                               says which didn't
--
-- It plays the admin (A) and the first three members who are neither admin
-- nor commissioner (B, C and D), signed in as them and as the
-- 'authenticated' role, as the site would, through one round of a made-up
-- site season (season99) worth 2 points a ballot. A, B and C are DJs and D
-- is a Spectator; the round, "Secret Songs", hides its prompt and that B
-- wrote it. The grading is played as the Edge Function's secret key
-- ('service_role'), with a score written in by hand: Claude isn't called.
-- All of it is rolled back.

do $$
declare
  a uuid; ca text;
  b uuid; cb text;
  c uuid; cc text;
  d uuid; cd text;
  r uuid;
  sa uuid; sb uuid; sc uuid;
  tag_b text;
  gid uuid;
  st jsonb;
  ex jsonb;
  n int;
  g record;
  checks int := 0;
begin
  select user_id, competitor_id into a, ca from public.members where role = 'admin' order by created_at limit 1;
  select user_id, competitor_id into b, cb from public.members where role = 'member' order by created_at, user_id limit 1;
  select user_id, competitor_id into c, cc from public.members where role = 'member' order by created_at, user_id offset 1 limit 1;
  select user_id, competitor_id into d, cd from public.members where role = 'member' order by created_at, user_id offset 2 limit 1;
  if a is null or d is null then raise exception 'Rehearsal FAILED: it needs the admin and three other members'; end if;

  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.create_site_season(jsonb_build_object('key', 'season99', 'name', 'Rehearsal Hidden',
    'point_budget', 2, 'max_per_track', 2, 'first_playlist_at', now() + interval '1 day',
    'players', jsonb_build_array(jsonb_build_object('id', ca, 'role', 'dj'), jsonb_build_object('id', cb, 'role', 'dj'),
                                 jsonb_build_object('id', cc, 'role', 'dj'), jsonb_build_object('id', cd, 'role', 'spectator')),
    'rounds', jsonb_build_array(jsonb_build_object('name', 'Secret Songs', 'prompt', 'Songs about keeping a secret.',
                                                   'prompters', jsonb_build_array(cb), 'hide_prompt', true, 'hide_prompter', true))));
  execute 'reset role';
  select id into r from public.site_rounds where season_key = 'season99';

  -- 1. The Spectator gets "Round 1", no prompt and no writer; a DJ and the
  --    admin get the real ones.
  perform set_config('request.jwt.claim.sub', d::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', d, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  select e into st from jsonb_array_elements(public.site_rounds_list()) e where e->>'id' = r::text;
  if st->>'name' <> 'Round 1' or st->>'prompt' <> '' or not (st->>'prompt_hidden')::boolean
     or jsonb_array_length(st->'site_round_prompters') <> 0 then
    raise exception 'Rehearsal FAILED: the Spectator saw %', st;
  end if;
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  select e into st from jsonb_array_elements(public.site_rounds_list()) e where e->>'id' = r::text;
  if st->>'name' <> 'Secret Songs' or (st->>'prompt_hidden')::boolean or jsonb_array_length(st->'site_round_prompters') <> 1 then
    raise exception 'Rehearsal FAILED: a DJ saw %', st;
  end if;
  checks := checks + 1;

  -- 2. Nobody reads a name or prompt straight from the table; the rest of
  --    the round still reads.
  perform set_config('request.jwt.claim.sub', d::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', d, 'role', 'authenticated')::text, true);
  begin
    perform name from public.site_rounds where id = r;
    raise exception 'Rehearsal FAILED: a member read a round''s name from the table';
  exception when insufficient_privilege then
    null;
  end;
  select count(*) into n from public.site_rounds where id = r and hide_prompt;
  if n <> 1 then raise exception 'Rehearsal FAILED: the round''s other columns didn''t read'; end if;
  checks := checks + 1;

  -- 3. Who wrote it stays out of the Spectator's reach in its own table.
  select count(*) into n from public.site_round_prompters where round_id = r;
  if n <> 0 then raise exception 'Rehearsal FAILED: the Spectator read who wrote it'; end if;
  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  select count(*) into n from public.site_round_prompters where round_id = r;
  if n <> 1 then raise exception 'Rehearsal FAILED: a DJ couldn''t read who wrote it'; end if;
  checks := checks + 1;

  -- 4. No guess before voting opens, and never from a DJ.
  perform set_config('request.jwt.claim.sub', d::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', d, 'role', 'authenticated')::text, true);
  begin
    perform public.save_prompt_guess(r, 'Too early', null);
    raise exception 'Rehearsal FAILED: a guess went in while submissions were open';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'Guesses go in while voting is open.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  begin
    perform public.save_prompt_guess(r, 'I know it', null);
    raise exception 'Rehearsal FAILED: a DJ guessed';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'Only this round''s Spectators guess.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  -- The DJs send their tracks; B adds a note shown while people vote.
  perform public.submit_track(r, 'youtube', 'rehearsal0c');
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  perform public.submit_track(r, 'youtube', 'rehearsal0a');
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  tag_b := public.submit_track(r, 'youtube', 'rehearsal0b');
  perform public.set_submission_note(r, tag_b, 'This one is about secrets.', true);
  execute 'reset role';
  update public.site_rounds set closed_at = now() where id = r;
  select o.submission_id into sa from public.site_submission_owners o where o.round_id = r and o.user_id = a;
  select o.submission_id into sb from public.site_submission_owners o where o.round_id = r and o.user_id = b;
  select o.submission_id into sc from public.site_submission_owners o where o.round_id = r and o.user_id = c;

  -- 5. What's hidden is fixed once submissions close.
  begin
    update public.site_rounds set hide_prompt = false where id = r;
    raise exception 'Rehearsal FAILED: the round stopped hiding after the close';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'What a round hides from Spectators can change only until submissions close.' then
      raise exception 'Rehearsal FAILED: got "%"', sqlerrm;
    end if;
  end;
  checks := checks + 1;

  -- 6. While voting, the note is kept from the Spectator, not from a DJ.
  execute 'set local role authenticated';
  perform set_config('request.jwt.claim.sub', d::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', d, 'role', 'authenticated')::text, true);
  select count(*) into n from public.site_submission_notes where round_id = r;
  if n <> 0 then raise exception 'Rehearsal FAILED: the Spectator read a note while voting'; end if;
  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  select count(*) into n from public.site_submission_notes where round_id = r;
  if n <> 1 then raise exception 'Rehearsal FAILED: a DJ couldn''t read the note while voting'; end if;
  checks := checks + 1;

  -- 7. The Spectator guesses: the writer must be one of the round's DJs,
  --    and a guess is at most 280 characters.
  perform set_config('request.jwt.claim.sub', d::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', d, 'role', 'authenticated')::text, true);
  begin
    perform public.save_prompt_guess(r, 'Songs about secrets', cd);
    raise exception 'Rehearsal FAILED: a Spectator was picked as the writer';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'Pick one of this round''s DJs.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  begin
    perform public.save_prompt_guess(r, repeat('x', 281), null);
    raise exception 'Rehearsal FAILED: a 281-character guess went in';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'A guess can be at most 280 characters.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  perform public.save_prompt_guess(r, '  Songs about secrets  ', cb);
  select * into g from public.my_prompt_guess(r);
  if g.guess <> 'Songs about secrets' or g.prompter <> cb or g.locked or g.score is not null then
    raise exception 'Rehearsal FAILED: the saved guess read back as %', row_to_json(g);
  end if;
  checks := checks + 1;

  -- 8. Submitting a ballot locks it.
  perform public.cast_ballot(r, jsonb_build_array(jsonb_build_object('submission', sa, 'points', 1),
                                                  jsonb_build_object('submission', sb, 'points', 1)));
  begin
    perform public.save_prompt_guess(r, 'Changed my mind', cb);
    raise exception 'Rehearsal FAILED: a guess changed after the ballot went in';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'Your guess locked when you submitted your ballot.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  if not (select locked from public.my_prompt_guess(r)) then raise exception 'Rehearsal FAILED: the guess didn''t read as locked'; end if;
  checks := checks + 1;

  -- The DJs vote; voting closes.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  perform public.cast_ballot(r, jsonb_build_array(jsonb_build_object('submission', sb, 'points', 2)));
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  perform public.cast_ballot(r, jsonb_build_array(jsonb_build_object('submission', sc, 'points', 2)));
  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  perform public.cast_ballot(r, jsonb_build_array(jsonb_build_object('submission', sa, 'points', 2)));
  execute 'reset role';
  update public.site_rounds set voting_closed_at = now() where id = r and voting_closed_at is null;
  if public.site_round_phase(r) <> 'finished' then raise exception 'Rehearsal FAILED: the round should be finished'; end if;

  -- 9. Once voting has closed the Spectator sees it all, and the guesses
  --    show, with the right writer picked.
  perform set_config('request.jwt.claim.sub', d::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', d, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  select e into st from jsonb_array_elements(public.site_rounds_list()) e where e->>'id' = r::text;
  if st->>'name' <> 'Secret Songs' or (st->>'prompt_hidden')::boolean then raise exception 'Rehearsal FAILED: still hidden after the close: %', st; end if;
  select * into g from public.site_round_guesses(r);
  if g.competitor_id <> cd or not g.prompter_correct or g.score is not null then
    raise exception 'Rehearsal FAILED: the guesses read as %', row_to_json(g);
  end if;
  gid := g.guess_id;
  begin
    perform public.prompt_guesses_claim(r);
    raise exception 'Rehearsal FAILED: a member called the grader''s claim';
  exception when insufficient_privilege then
    null;
  end;
  execute 'reset role';
  checks := checks + 1;

  -- 10. The grader claims the guess once, and its score goes in once.
  execute 'set local role service_role';
  st := public.prompt_guesses_claim(r);
  if st->>'prompt' <> 'Songs about keeping a secret.' or jsonb_array_length(st->'guesses') <> 1 then
    raise exception 'Rehearsal FAILED: the claim was %', st;
  end if;
  if jsonb_array_length(public.prompt_guesses_claim(r)->'guesses') <> 0 then raise exception 'Rehearsal FAILED: a guess was claimed twice'; end if;
  begin
    perform public.prompt_guesses_grade(jsonb_build_array(jsonb_build_object('id', gid, 'score', 7, 'reason', 'x')));
    raise exception 'Rehearsal FAILED: a score of 7 went in';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'Scores are whole numbers from 0 to 5.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  if public.prompt_guesses_grade(jsonb_build_array(jsonb_build_object('id', gid, 'score', 4, 'reason', 'Right idea.'))) <> 1
     or public.prompt_guesses_grade(jsonb_build_array(jsonb_build_object('id', gid, 'score', 1, 'reason', 'Again.'))) <> 0 then
    raise exception 'Rehearsal FAILED: the score went in other than once';
  end if;
  execute 'reset role';
  checks := checks + 1;

  -- 11. A commissioner can change it; a member can't.
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  begin
    perform public.set_prompt_guess_score(gid, 5);
    raise exception 'Rehearsal FAILED: a member changed a score';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'Only the admin or a commissioner can change a score.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  perform public.set_prompt_guess_score(gid, 3);
  execute 'reset role';
  if (select score from public.site_prompt_guesses where id = gid) <> 3
     or (select graded_by from public.site_prompt_guesses where id = gid) <> 'commissioner' then
    raise exception 'Rehearsal FAILED: the commissioner''s score didn''t stick';
  end if;
  checks := checks + 1;

  -- 12. The export carries what was hidden and the guess, for the stats.
  select e into ex from jsonb_array_elements(public.site_rounds_export()->'rounds') e where e->>'id' = r::text;
  if not (ex->>'hide_prompt')::boolean or not (ex->>'hide_prompter')::boolean
     or ex->'guesses'->0->>'spectator' <> cd or (ex->'guesses'->0->>'score')::int <> 3
     or not (ex->'guesses'->0->>'prompter_correct')::boolean then
    raise exception 'Rehearsal FAILED: the export carried %', ex->'guesses';
  end if;
  checks := checks + 1;

  -- 13. A stranger gets nothing.
  execute 'set local role anon';
  begin
    perform public.site_rounds_list();
    raise exception 'Rehearsal FAILED: a stranger listed the rounds';
  exception when insufficient_privilege then
    null;
  end;
  begin
    perform 1 from public.site_prompt_guesses;
    raise exception 'Rehearsal FAILED: a stranger read the guesses';
  exception when insufficient_privilege then
    null;
  end;
  execute 'reset role';
  checks := checks + 1;

  raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;
end $$;
