-- A rehearsal of the voters' lounge, run by the real database and then
-- undone: nothing it does is kept. Run it in the Supabase SQL Editor after
-- supabase/migrations/2026-10-28_voters_lounge.sql (README, Voters'
-- lounge). It always ends in an error, on purpose, because an error rolls
-- everything back:
--
--   "Rehearsal passed: 13 checks held. Nothing was kept."  every rule held
--   "Rehearsal FAILED: ..."                               says which didn't
--
-- It plays the admin (A) and the first three members who are neither admin
-- nor commissioner (B, C and D), signed in as them and as the
-- 'authenticated' role, as the site would, through one round of a made-up
-- site season (season99) worth 2 points a ballot: all four send a track,
-- B, C and D vote, A doesn't, then voting closes. All of it is rolled back.

do $$
declare
  a uuid; ca text;
  b uuid; cb text;
  c uuid; cc text;
  d uuid; cd text;
  r uuid;
  ml uuid;
  sa uuid; sb uuid; sc uuid; sd uuid;
  st jsonb;
  alias_b text; alias_c text;
  mid bigint;
  n int;
  x record;
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
  perform public.create_site_season(jsonb_build_object('key', 'season99', 'name', 'Rehearsal Lounge',
    'point_budget', 2, 'max_per_track', 2, 'first_playlist_at', now() + interval '1 day',
    'rounds', jsonb_build_array(jsonb_build_object('name', 'L')), 'players', jsonb_build_array(ca, cb, cc, cd)));
  execute 'reset role';
  select id into r from public.site_rounds where season_key = 'season99';
  update public.site_rounds set opens_at = now() - interval '1 hour' where id = r;

  -- Everyone sends a track.
  execute 'set local role authenticated';
  perform public.submit_track(r, 'youtube', 'rehearsal0a');
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  perform public.submit_track(r, 'youtube', 'rehearsal0b');

  -- 1. No lounge while submissions are open.
  st := public.lounge_status(r, false);
  if st->>'phase' <> 'closed' or (st->>'open')::boolean then raise exception 'Rehearsal FAILED: a lounge while submitting: %', st; end if;
  begin
    perform public.lounge_post(r, false, 'Too early');
    raise exception 'Rehearsal FAILED: a message went in while submissions were open';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'The lounge is only open to people who have voted, while voting is open.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  perform public.submit_track(r, 'youtube', 'rehearsal0c');
  perform set_config('request.jwt.claim.sub', d::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', d, 'role', 'authenticated')::text, true);
  perform public.submit_track(r, 'youtube', 'rehearsal0d');
  execute 'reset role';

  update public.site_rounds set closed_at = now() where id = r;
  if public.site_round_phase(r) <> 'voting' then raise exception 'Rehearsal FAILED: the round should be voting'; end if;
  select o.submission_id into sa from public.site_submission_owners o where o.round_id = r and o.user_id = a;
  select o.submission_id into sb from public.site_submission_owners o where o.round_id = r and o.user_id = b;
  select o.submission_id into sc from public.site_submission_owners o where o.round_id = r and o.user_id = c;
  select o.submission_id into sd from public.site_submission_owners o where o.round_id = r and o.user_id = d;

  -- B and C vote: two voters, not yet enough.
  execute 'set local role authenticated';
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  perform public.cast_ballot(r, jsonb_build_array(jsonb_build_object('submission', sc, 'points', 2)));
  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  perform public.cast_ballot(r, jsonb_build_array(jsonb_build_object('submission', sb, 'points', 2)));

  -- 2. With two voters the lounge stays shut, even to them.
  st := public.lounge_status(r, false);
  if (st->>'open')::boolean or (st->>'voters')::int <> 2 or not (st->>'in')::boolean or st->>'alias' is not null then
    raise exception 'Rehearsal FAILED: with two voters the lounge should be shut: %', st;
  end if;
  select count(*) into n from public.lounge_messages(r, false);
  if n <> 0 then raise exception 'Rehearsal FAILED: a shut lounge could be read'; end if;
  begin
    perform public.lounge_post(r, false, 'Anyone?');
    raise exception 'Rehearsal FAILED: a message went in with two voters';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'The lounge is only open to people who have voted, while voting is open.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  -- D votes: three, and it opens.
  perform set_config('request.jwt.claim.sub', d::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', d, 'role', 'authenticated')::text, true);
  perform public.cast_ballot(r, jsonb_build_array(jsonb_build_object('submission', sb, 'points', 2)));

  -- 3. B is in, with an instrument, the same every time, and sends one
  --    message; a second inside 24 hours is refused.
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  st := public.lounge_status(r, false);
  alias_b := st->>'alias';
  if not (st->>'open')::boolean or alias_b is null or (st->>'voters')::int <> 3 then
    raise exception 'Rehearsal FAILED: with three voters B should be in: %', st;
  end if;
  if public.lounge_status(r, false)->>'alias' <> alias_b then raise exception 'Rehearsal FAILED: B''s instrument changed'; end if;
  if public.lounge_post(r, false, '  Hello, room.  ') < now() + interval '23 hours' then
    raise exception 'Rehearsal FAILED: the next message should be a day away';
  end if;
  begin
    perform public.lounge_post(r, false, 'And again');
    raise exception 'Rehearsal FAILED: a second message went in inside a day';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'One message every 24 hours.%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  if (public.lounge_status(r, false)->>'next_post_at') is null then raise exception 'Rehearsal FAILED: B''s status should say when the next can go'; end if;
  checks := checks + 1;

  -- 4. A, with a track but no ballot, isn't in: reads nothing, sends nothing.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  st := public.lounge_status(r, false);
  if (st->>'in')::boolean or not (st->>'eligible')::boolean or (st->>'open')::boolean or (st->>'messages')::int <> 1 then
    raise exception 'Rehearsal FAILED: A should be outside, told there''s one message: %', st;
  end if;
  select count(*) into n from public.lounge_messages(r, false);
  if n <> 0 then raise exception 'Rehearsal FAILED: someone outside read the lounge'; end if;
  begin
    perform public.lounge_post(r, false, 'Let me in');
    raise exception 'Rehearsal FAILED: someone who hasn''t voted sent a message';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'The lounge is only open to people who have voted, while voting is open.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  -- 5. C reads B's message under B's instrument, trimmed, not as theirs;
  --    B reads it as theirs. Nothing says who.
  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  select * into x from public.lounge_messages(r, false);
  if x.alias <> alias_b or x.body <> 'Hello, room.' or x.mine or x.removed then
    raise exception 'Rehearsal FAILED: C should read B''s message as B''s instrument: %', row_to_json(x);
  end if;
  mid := x.id;
  if exists (select 1 from information_schema.routines rt
               join information_schema.parameters p on p.specific_name = rt.specific_name
              where rt.routine_schema = 'public' and rt.routine_name in ('lounge_messages', 'lounge_status')
                and p.parameter_mode = 'OUT' and p.parameter_name in ('user_id', 'competitor_id', 'name')) then
    raise exception 'Rehearsal FAILED: a lounge function gives out who';
  end if;
  checks := checks + 1;

  -- 6. A message is 1 to 280 characters, trimmed.
  begin
    perform public.lounge_post(r, false, '   ');
    raise exception 'Rehearsal FAILED: an empty message went in';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'Write something first.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  begin
    perform public.lounge_post(r, false, repeat('x', 281));
    raise exception 'Rehearsal FAILED: a 281-character message went in';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'A message can be at most 280 characters.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  perform public.lounge_post(r, false, repeat('y', 280));
  checks := checks + 1;

  -- 7. Every chatter has their own instrument.
  alias_c := public.lounge_status(r, false)->>'alias';
  if alias_c = alias_b then raise exception 'Rehearsal FAILED: B and C got the same instrument'; end if;
  checks := checks + 1;

  -- 8. Reactions: as many as you like, once each kind, and they come off.
  perform public.lounge_react(mid, 'fire', true);
  perform public.lounge_react(mid, 'fire', true);
  perform public.lounge_react(mid, 'heart', true);
  perform set_config('request.jwt.claim.sub', d::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', d, 'role', 'authenticated')::text, true);
  perform public.lounge_react(mid, 'fire', true);
  select * into x from public.lounge_messages(r, false) m where m.id = mid;
  if (x.reactions->>'fire')::int <> 2 or (x.reactions->>'heart')::int <> 1 or x.my_reactions <> array['fire'] then
    raise exception 'Rehearsal FAILED: reactions should be fire 2, heart 1: %', row_to_json(x);
  end if;
  perform public.lounge_react(mid, 'fire', false);
  select * into x from public.lounge_messages(r, false) m where m.id = mid;
  if (x.reactions->>'fire')::int <> 1 then raise exception 'Rehearsal FAILED: a reaction didn''t come off'; end if;
  begin
    perform public.lounge_react(mid, 'skull', true);
    raise exception 'Rehearsal FAILED: a reaction outside the six went on';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'That reaction isn''t one of the six.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  -- 9. Only the admin removes one; it keeps its place without its words,
  --    and still counts toward B's day.
  begin
    perform public.lounge_remove(mid);
    raise exception 'Rehearsal FAILED: a member removed a message';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'Only the admin can remove a message.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  perform public.lounge_remove(mid);
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  select * into x from public.lounge_messages(r, false) m where m.id = mid;
  if not x.removed or x.body is not null or not x.mine then raise exception 'Rehearsal FAILED: a removed message should keep its place, without its words'; end if;
  begin
    perform public.lounge_post(r, false, 'Try again');
    raise exception 'Rehearsal FAILED: a removed message didn''t count toward the day';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'One message every 24 hours.%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  -- 10. The practice lounge is another room: none of this shows there.
  select count(*) into n from public.lounge_messages(r, true);
  if n <> 0 then raise exception 'Rehearsal FAILED: the real lounge showed in the practice one'; end if;
  checks := checks + 1;

  -- 11. A round voted in Music League, Round 7 among them, has no lounge.
  select id into ml from public.site_rounds where not votes_on_site order by created_at desc limit 1;
  if ml is not null then
    st := public.lounge_status(ml, false);
    if st->>'phase' <> 'closed' then raise exception 'Rehearsal FAILED: a Music League round has a lounge: %', st; end if;
    begin
      perform public.lounge_post(ml, false, 'Hello?');
      raise exception 'Rehearsal FAILED: a message went into a Music League round';
    exception when others then
      if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
      if sqlerrm <> 'The lounge is only open to people who have voted, while voting is open.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
    end;
  end if;
  checks := checks + 1;

  -- 12. Once voting closes it locks, and every member reads it, A included,
  --     still by instrument.
  execute 'reset role';
  update public.site_rounds set voting_closed_at = now() where id = r;
  execute 'set local role authenticated';
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  select count(*) into n from public.lounge_messages(r, false) m where m.alias in (alias_b, alias_c);
  if n <> 2 then raise exception 'Rehearsal FAILED: after voting every member should read the lounge (got % messages)', n; end if;
  perform set_config('request.jwt.claim.sub', d::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', d, 'role', 'authenticated')::text, true);
  begin
    perform public.lounge_post(r, false, 'After the close');
    raise exception 'Rehearsal FAILED: a message went in after voting closed';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm <> 'The lounge is only open to people who have voted, while voting is open.' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  -- 13. Nobody reads the tables, and a stranger can't call anything.
  begin
    perform 1 from public.site_lounge_messages;
    raise exception 'Rehearsal FAILED: a member read the messages table';
  exception when insufficient_privilege then
    null;
  end;
  begin
    perform 1 from public.site_lounge_aliases;
    raise exception 'Rehearsal FAILED: a member read the aliases';
  exception when insufficient_privilege then
    null;
  end;
  execute 'reset role';
  execute 'set local role anon';
  begin
    perform public.lounge_status(r, false);
    raise exception 'Rehearsal FAILED: a stranger could ask about the lounge';
  exception when insufficient_privilege then
    null;
  end;
  execute 'reset role';
  checks := checks + 1;

  raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;
end $$;
