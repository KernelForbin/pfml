-- A rehearsal of commissioners, run by the real database and then undone:
-- nothing it does is kept. Run it in the Supabase SQL Editor after
-- supabase/migrations/2026-10-25_commissioner.sql (README, Commissioners).
-- It always ends in an error, on purpose, because an error rolls everything
-- back:
--
--   "Rehearsal passed: 15 checks held. Nothing was kept."  every rule held
--   "Rehearsal FAILED: ..."                               says which didn't
--
-- It plays the admin and the first member who is neither admin nor
-- commissioner, as the site would: signed in as them (the same auth.uid())
-- and as the 'authenticated' role, so the row-level rules and the deadline
-- guard apply exactly as they do to the page. Nobody is signed in as them
-- and nothing reaches them. The rounds it makes are in a made-up season
-- (season99), and every change, the role included, is rolled back.

do $$
declare
  a uuid; ca text;
  b uuid; cb text;
  rid uuid; vid uuid;
  checks int := 0;
  n int;
  t timestamptz;
begin
  select user_id, competitor_id into a, ca from public.members where role = 'admin' order by created_at limit 1;
  select user_id, competitor_id into b, cb from public.members where role = 'member' order by created_at, user_id limit 1;
  if a is null or b is null then raise exception 'Rehearsal FAILED: it needs the admin and one other member'; end if;
  insert into public.site_rounds (season_key, name, closes_at) values ('season99', 'Rehearsal round', now() + interval '2 days')
  returning id into rid;

  -- 1. A member isn't a commissioner: can't open, change or close a round,
  --    or make anyone a commissioner.
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  if public.is_commissioner() then raise exception 'Rehearsal FAILED: a member counts as a commissioner'; end if;
  checks := checks + 1;
  begin
    insert into public.site_rounds (season_key, name, closes_at) values ('season99', 'Sneaky', now() + interval '1 day');
    raise exception 'Rehearsal FAILED: a member opened a round';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
  end;
  update public.site_rounds set name = 'Renamed by a member' where id = rid;
  get diagnostics n = row_count;
  if n <> 0 then raise exception 'Rehearsal FAILED: a member renamed a round'; end if;
  checks := checks + 1;
  begin
    perform public.set_commissioner(cb, true);
    raise exception 'Rehearsal FAILED: a member made themselves a commissioner';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'Only the admin can choose commissioners.%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;
  execute 'reset role';

  -- 2. The admin makes B a commissioner; never their own row, never someone
  --    who hasn't joined.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.set_commissioner(cb, true);
  begin
    perform public.set_commissioner(ca, false);
    raise exception 'Rehearsal FAILED: the admin stopped being a commissioner';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'The admin is always a commissioner.%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  begin
    perform public.set_commissioner('not-a-player', true);
    raise exception 'Rehearsal FAILED: a stranger''s id was accepted';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
  end;
  execute 'reset role';
  if (select role from public.members where user_id = b) <> 'commissioner' then
    raise exception 'Rehearsal FAILED: B didn''t become a commissioner';
  end if;
  checks := checks + 1;

  -- 3. B, a commissioner now, runs a round like the admin can.
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  if not public.is_commissioner() then raise exception 'Rehearsal FAILED: B isn''t a commissioner'; end if;
  begin
    insert into public.site_rounds (season_key, name, closes_at) values ('season99', 'In the past', now() - interval '1 hour');
    raise exception 'Rehearsal FAILED: a round opened already closed';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'The closing time has to be in the future.%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;
  update public.site_rounds set name = 'Renamed', prompt = 'New description', closes_at = now() + interval '3 days' where id = rid;
  get diagnostics n = row_count;
  if n <> 1 then raise exception 'Rehearsal FAILED: a commissioner couldn''t change the open round'; end if;
  checks := checks + 1;
  begin
    update public.site_rounds set closes_at = now() - interval '1 minute' where id = rid;
    raise exception 'Rehearsal FAILED: a deadline moved into the past';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
  end;
  checks := checks + 1;
  -- closing early takes the database's clock, whatever the browser sends
  update public.site_rounds set closed_at = '2000-01-01' where id = rid;
  select closed_at into t from public.site_rounds where id = rid;
  if t is distinct from now() then raise exception 'Rehearsal FAILED: closed_at kept the browser''s time (%)', t; end if;
  checks := checks + 1;
  begin
    update public.site_rounds set closed_at = null where id = rid;
    raise exception 'Rehearsal FAILED: a closed round reopened';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'Submissions for this round have closed%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  begin
    update public.site_rounds set closes_at = now() + interval '5 days' where id = rid;
    raise exception 'Rehearsal FAILED: a closed round''s deadline moved';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
  end;
  begin
    update public.site_rounds set season_key = 'season98' where id = rid;
    raise exception 'Rehearsal FAILED: a closed round moved season';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
  end;
  checks := checks + 1;
  update public.site_rounds set name = 'Renamed after closing', prompt = '' where id = rid;
  get diagnostics n = row_count;
  if n <> 1 then raise exception 'Rehearsal FAILED: a closed round couldn''t be renamed'; end if;
  checks := checks + 1;
  delete from public.site_rounds where id = rid;
  get diagnostics n = row_count;
  if n <> 0 then raise exception 'Rehearsal FAILED: a commissioner deleted a round (only the admin can)'; end if;
  checks := checks + 1;
  execute 'reset role';

  -- 4. Voting's deadline, on a round that votes here: open while voting is.
  insert into public.site_rounds (season_key, name, closes_at, votes_on_site, voting_closes_at)
  values ('season99', 'Rehearsal voting', now() + interval '1 day', true, now() + interval '3 days') returning id into vid;
  -- the SQL Editor isn't held to the guard: put the round into voting
  update public.site_rounds set closes_at = now() - interval '1 hour' where id = vid;
  if (select closes_at from public.site_rounds where id = vid) >= now() then
    raise exception 'Rehearsal FAILED: the guard held the SQL Editor too';
  end if;
  checks := checks + 1;
  execute 'set local role authenticated';
  begin
    update public.site_rounds set voting_closes_at = now() - interval '1 minute' where id = vid;
    raise exception 'Rehearsal FAILED: the voting deadline moved into the past';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
  end;
  update public.site_rounds set voting_closes_at = now() + interval '4 days' where id = vid;
  get diagnostics n = row_count;
  if n <> 1 then raise exception 'Rehearsal FAILED: a commissioner couldn''t move the voting deadline'; end if;
  checks := checks + 1;
  update public.site_rounds set voting_closed_at = '2000-01-01' where id = vid;
  begin
    update public.site_rounds set voting_closed_at = null where id = vid;
    raise exception 'Rehearsal FAILED: voting reopened';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'Voting for this round has closed%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  execute 'reset role';
  if (select voting_closed_at from public.site_rounds where id = vid) is distinct from now() then
    raise exception 'Rehearsal FAILED: voting_closed_at kept the browser''s time';
  end if;
  checks := checks + 1;

  -- 5. The admin takes it back: B is a member again, and can't write.
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.set_commissioner(cb, false);
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  update public.site_rounds set name = 'After demotion' where id = vid;
  get diagnostics n = row_count;
  execute 'reset role';
  if n <> 0 or (select role from public.members where user_id = b) <> 'member' then
    raise exception 'Rehearsal FAILED: B kept a commissioner''s powers';
  end if;
  checks := checks + 1;

  raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;
end $$;
