-- DJs, Spectators and prompters (README, DJs and Spectators). Run once in
-- the Supabase SQL Editor for the live project, after
-- 2026-10-28_voters_lounge.sql. Safe to re-run. supabase/schema.sql has the
-- same before its storage section, for a fresh install.
--
-- Asked for 2026-10-29: everyone playing a season set up on the site is a
-- DJ (sends tracks and votes, as today) or a Spectator (votes and comments
-- on every track, never sends one). The role is set for the season and can
-- be changed for any round, while that round still takes tracks; everyone
-- starts each round with their season role. A DJ who has already sent a
-- track to a round stays a DJ in it. And each round can name who wrote its
-- prompt: one member or several, when they wrote it together.
--
-- Not built (the user's call, 2026-10-29): hiding the prompt from
-- Spectators, guessing it, and Spectator points.
--
-- A round opened by hand, outside a season set up on the site (Round 7 and
-- every round before it), has no roles: everyone is a DJ there, as before.

-- ---------------------------------------------------------------- DJs and Spectators

alter table public.site_season_players
  add column if not exists role text not null default 'dj' check (role in ('dj', 'spectator'));

-- A round's own roles, where they differ from the season's.
create table if not exists public.site_round_roles (
  round_id      uuid not null references public.site_rounds (id) on delete cascade,
  competitor_id text not null references public.players (competitor_id),
  role          text not null check (role in ('dj', 'spectator')),
  primary key (round_id, competitor_id)
);

-- Who wrote a round's prompt.
create table if not exists public.site_round_prompters (
  round_id      uuid not null references public.site_rounds (id) on delete cascade,
  competitor_id text not null references public.players (competitor_id),
  primary key (round_id, competitor_id)
);

-- Members read both, as they read who's playing a season; only the
-- functions below write them.
alter table public.site_round_roles     enable row level security;
alter table public.site_round_prompters enable row level security;
drop policy if exists "members read site round roles" on public.site_round_roles;
create policy "members read site round roles" on public.site_round_roles
  for select to authenticated using (public.is_member());
drop policy if exists "members read site round prompters" on public.site_round_prompters;
create policy "members read site round prompters" on public.site_round_prompters
  for select to authenticated using (public.is_member());
revoke all on table public.site_round_roles from anon, authenticated;
revoke all on table public.site_round_prompters from anon, authenticated;
grant select on table public.site_round_roles to authenticated;
grant select on table public.site_round_prompters to authenticated;

-- A player's role in a round: 'dj' or 'spectator', or null when they aren't
-- playing its season. 'dj' for everyone in a round outside a season set up
-- on the site, as before roles.
create or replace function public.site_round_role(p_round uuid, p_competitor text)
returns text language sql stable security definer set search_path = public as $$
  select case
    when not exists (select 1 from public.site_rounds r join public.site_seasons s on s.key = r.season_key
                      where r.id = p_round) then 'dj'
    else (select coalesce(x.role, p.role)
            from public.site_rounds r
            join public.site_season_players p on p.season_key = r.season_key and p.competitor_id = p_competitor
            left join public.site_round_roles x on x.round_id = r.id and x.competitor_id = p_competitor
           where r.id = p_round) end;
$$;

-- The same, for a signed-in account.
create or replace function public.site_user_role(p_round uuid, p_user uuid)
returns text language sql stable security definer set search_path = public as $$
  select public.site_round_role(p_round, (select m.competitor_id from public.members m where m.user_id = p_user));
$$;

-- How many DJs a round has: a round needs 2, or nobody could vote.
create or replace function public.site_round_dj_count(p_round uuid)
returns int language sql stable security definer set search_path = public as $$
  select count(*)::int
    from public.site_rounds r
    join public.site_season_players p on p.season_key = r.season_key
   where r.id = p_round and public.site_round_role(r.id, p.competitor_id) = 'dj';
$$;

-- Everyone playing a round and their role in it, and whether they've
-- joined the site. Empty for a round outside a season set up on the site.
create or replace function public.site_round_roster(p_round uuid)
returns table (competitor_id text, role text, joined boolean)
language sql stable security definer set search_path = public as $$
  select p.competitor_id, coalesce(x.role, p.role),
         exists (select 1 from public.members m where m.competitor_id = p.competitor_id)
    from public.site_rounds r
    join public.site_season_players p on p.season_key = r.season_key
    left join public.site_round_roles x on x.round_id = r.id and x.competitor_id = p.competitor_id
   where r.id = p_round and public.is_member()
   order by p.competitor_id;
$$;

-- Sets a round's roles and its prompters, without asking who may: the
-- functions below ask. p_roles is every player's role for the round
-- ({competitor id: 'dj' | 'spectator'}), and only the ones that differ from
-- the season are kept, so a later change to the season still reaches the
-- rest. p_prompters is a list of member ids. Either one null leaves that
-- part as it is.
create or replace function public.site_round_people_apply(p_round uuid, p_roles jsonb, p_prompters jsonb)
returns void language plpgsql security definer set search_path = public as $$
declare
  r public.site_rounds%rowtype;
  who text;
begin
  select * into r from public.site_rounds where id = p_round;
  if not found then
    raise exception 'That round doesn''t exist.';
  end if;
  if p_roles is not null then
    if jsonb_typeof(p_roles) is distinct from 'object'
       or exists (select 1 from jsonb_each(p_roles) e
                   where jsonb_typeof(e.value) is distinct from 'string' or e.value #>> '{}' not in ('dj', 'spectator')) then
      raise exception 'The roles don''t add up. Reload the page and try again.';
    end if;
    if exists (select 1 from jsonb_object_keys(p_roles) k
                where not exists (select 1 from public.site_season_players p
                                   where p.season_key = r.season_key and p.competitor_id = k)) then
      raise exception 'Only players in this season can have a role in its rounds.';
    end if;
    select pl.name into who
      from jsonb_each_text(p_roles) e
      join public.members m on m.competitor_id = e.key
      join public.players pl on pl.competitor_id = e.key
     where e.value = 'spectator'
       and exists (select 1 from public.site_submission_owners o where o.round_id = p_round and o.user_id = m.user_id)
     limit 1;
    if who is not null then
      raise exception '% has already sent a track to this round, so stays a DJ in it.', who;
    end if;
    delete from public.site_round_roles where round_id = p_round;
    insert into public.site_round_roles (round_id, competitor_id, role)
    select p_round, e.key, e.value
      from jsonb_each_text(p_roles) e
      join public.site_season_players p on p.season_key = r.season_key and p.competitor_id = e.key
     where e.value <> p.role;
    if public.site_round_dj_count(p_round) < 2 then
      raise exception '"%" needs at least 2 DJs.', r.name;
    end if;
  end if;
  if p_prompters is not null then
    if jsonb_typeof(p_prompters) is distinct from 'array' or jsonb_array_length(p_prompters) > 10
       or exists (select 1 from jsonb_array_elements(p_prompters) e where jsonb_typeof(e) is distinct from 'string') then
      raise exception 'The prompters don''t add up. Reload the page and try again.';
    end if;
    if exists (select 1 from jsonb_array_elements_text(p_prompters) x
                where not exists (select 1 from public.members m where m.competitor_id = x)) then
      raise exception 'A prompter has to be a member who has joined the site.';
    end if;
    delete from public.site_round_prompters where round_id = p_round;
    insert into public.site_round_prompters (round_id, competitor_id)
    select distinct p_round, x from jsonb_array_elements_text(p_prompters) x;
  end if;
end;
$$;

-- A round's roles and prompters, from the Commissioner page. Roles can
-- change while the round still takes tracks; who wrote the prompt, any
-- time.
create or replace function public.set_site_round_people(p_round uuid, p_roles jsonb, p_prompters jsonb)
returns void language plpgsql security definer set search_path = public as $$
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can change a round.';
  end if;
  if not exists (select 1 from public.site_rounds r join public.site_seasons s on s.key = r.season_key
                  where r.id = p_round) then
    raise exception 'Only a round in a season set up on the site has DJs, Spectators and prompters.';
  end if;
  if p_roles is not null and public.site_round_phase(p_round) not in ('upcoming', 'submitting') then
    raise exception 'Roles can change only until submissions close.';
  end if;
  perform public.site_round_people_apply(p_round, p_roles, p_prompters);
end;
$$;

-- Who's playing a season and each one's role, replaced as a whole
-- (p_players: [{id, role}]). A role change reaches the rounds still taking
-- tracks or not open yet, never one whose submissions have closed, and a
-- DJ who has a track in a round stays a DJ in it. A round's own roles stay.
create or replace function public.set_site_season_roster(p_key text, p_players jsonb)
returns void language plpgsql security definer set search_path = public as $$
declare
  bad text;
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can choose who''s playing.';
  end if;
  if not exists (select 1 from public.site_seasons where key = p_key) then
    raise exception 'That season doesn''t exist.';
  end if;
  if jsonb_typeof(p_players) is distinct from 'array'
     or exists (select 1 from jsonb_array_elements(p_players) e
                 where jsonb_typeof(e) is distinct from 'object' or coalesce(e->>'id', '') = ''
                    or coalesce(e->>'role', '') not in ('dj', 'spectator')) then
    raise exception 'The players don''t add up. Reload the page and try again.';
  end if;
  if (select count(distinct e->>'id') from jsonb_array_elements(p_players) e where e->>'role' = 'dj') < 2 then
    raise exception 'A season needs at least 2 DJs.';
  end if;

  -- what a round has already settled keeps its role: rounds whose
  -- submissions have closed, and a DJ with a track in an open one
  insert into public.site_round_roles (round_id, competitor_id, role)
  select r.id, p.competitor_id, p.role
    from public.site_rounds r
    join public.site_season_players p on p.season_key = r.season_key
    join jsonb_array_elements(p_players) e on e->>'id' = p.competitor_id and e->>'role' <> p.role
   where r.season_key = p_key
     and (public.site_round_phase(r.id) not in ('upcoming', 'submitting')
          or exists (select 1 from public.site_submission_owners o join public.members m on m.user_id = o.user_id
                      where o.round_id = r.id and m.competitor_id = p.competitor_id))
  on conflict (round_id, competitor_id) do nothing;

  delete from public.site_season_players
   where season_key = p_key and competitor_id not in (select e->>'id' from jsonb_array_elements(p_players) e);
  insert into public.site_season_players (season_key, competitor_id, role)
  select distinct on (e->>'id') p_key, e->>'id', e->>'role' from jsonb_array_elements(p_players) e
  on conflict (season_key, competitor_id) do update set role = excluded.role;
  -- a round's own role that now matches the season's is no longer different
  delete from public.site_round_roles x
   using public.site_rounds r, public.site_season_players p
   where x.round_id = r.id and r.season_key = p_key and public.site_round_phase(r.id) in ('upcoming', 'submitting')
     and p.season_key = p_key and p.competitor_id = x.competitor_id and p.role = x.role;

  select r.name into bad from public.site_rounds r
   where r.season_key = p_key and public.site_round_phase(r.id) in ('upcoming', 'submitting')
     and public.site_round_dj_count(r.id) < 2
   order by r.opens_at limit 1;
  if bad is not null then
    raise exception '"%" would have fewer than 2 DJs. Change its roles first.', bad;
  end if;
end;
$$;

-- A Spectator never sends a track: the one door every submission goes
-- through (submit_track, and submit_described through it).
create or replace function public.site_owner_is_dj()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  if public.site_user_role(new.round_id, new.user_id) = 'spectator' then
    raise exception 'You''re a Spectator this round: you vote on the tracks, but don''t send one.';
  end if;
  return new;
end;
$$;
drop trigger if exists site_owner_is_dj on public.site_submission_owners;
create trigger site_owner_is_dj before insert on public.site_submission_owners
  for each row execute function public.site_owner_is_dj();

-- Sets up a season, as before, and now: each player can be a DJ or a
-- Spectator (players: [{id, role}], or plain ids for DJs), and each round
-- can carry its own roles and its prompters ({roles, prompters}).
create or replace function public.create_site_season(p jsonb)
returns text language plpgsql security definer set search_path = public as $$
declare
  k text := p->>'key';
  s public.site_seasons%rowtype;
  first_close timestamptz;
  item jsonb;
  opens timestamptz;
  closes timestamptz;
  rid uuid;
  n int := 0;
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can set up a season.';
  end if;
  if k is null or k !~ '^season[0-9]+$' or substring(k from 7)::int < 4 then
    raise exception 'A season set up on the site is Season 4 or later.';
  end if;
  if exists (select 1 from public.site_seasons x where x.key = k)
     or exists (select 1 from public.site_rounds x where x.season_key = k) then
    raise exception 'That season already exists.';
  end if;
  if jsonb_typeof(p->'rounds') is distinct from 'array' or jsonb_array_length(p->'rounds') not between 1 and 40 then
    raise exception 'A season needs between 1 and 40 rounds.';
  end if;
  if jsonb_typeof(p->'players') is distinct from 'array'
     or exists (select 1 from jsonb_array_elements(p->'players') e
                 where not (jsonb_typeof(e) = 'string'
                            or (jsonb_typeof(e) = 'object' and coalesce(e->>'id', '') <> ''
                                and coalesce(e->>'role', 'dj') in ('dj', 'spectator')))) then
    raise exception 'The players don''t add up. Reload the page and try again.';
  end if;
  if (select count(distinct coalesce(e->>'id', e #>> '{}')) from jsonb_array_elements(p->'players') e
       where jsonb_typeof(e) = 'string' or coalesce(e->>'role', 'dj') = 'dj') < 2 then
    raise exception 'A season needs at least 2 DJs.';
  end if;
  if btrim(coalesce(p->>'name', '')) = '' then
    raise exception 'Give the season a name.';
  end if;
  if exists (select 1 from jsonb_array_elements(p->'rounds') e where btrim(coalesce(e->>'name', '')) = '') then
    raise exception 'Every round needs a name.';
  end if;
  first_close := (p->>'first_playlist_at')::timestamptz;
  if first_close is null or first_close <= now() then
    raise exception 'The first playlist has to be in the future.';
  end if;

  insert into public.site_seasons (key, name, description, point_budget, max_per_track, nonvoters_keep_points,
                                   timing, submit_days, vote_days, songs_per_round, downvotes, max_down_per_track,
                                   services, repeat_rule)
  values (k, btrim(coalesce(p->>'name', '')), btrim(coalesce(p->>'description', '')),
          coalesce((p->>'point_budget')::smallint, 19), coalesce((p->>'max_per_track')::smallint, 5),
          coalesce((p->>'nonvoters_keep_points')::boolean, false), coalesce(p->>'timing', 'steady'),
          coalesce((p->>'submit_days')::smallint, 2), coalesce((p->>'vote_days')::smallint, 5),
          coalesce((p->>'songs_per_round')::smallint, 1), coalesce((p->>'downvotes')::smallint, 0),
          coalesce((p->>'max_down_per_track')::smallint, 0),
          coalesce((select array_agg(x) from jsonb_array_elements_text(p->'services') x), '{spotify,youtube,soundcloud}'),
          coalesce(p->>'repeat_rule', 'warn'))
  returning * into s;
  insert into public.site_season_players (season_key, competitor_id, role)
  select distinct on (x.id) k, x.id, x.role
    from (select coalesce(e->>'id', e #>> '{}') as id,
                 case when jsonb_typeof(e) = 'object' then coalesce(e->>'role', 'dj') else 'dj' end as role
            from jsonb_array_elements(p->'players') e) x;

  for item in select e from jsonb_array_elements(p->'rounds') e loop
    n := n + 1;
    if n = 1 then
      closes := first_close;
      opens := greatest(now(), public.site_add_days(closes, -s.submit_days));
    else
      opens := public.site_add_days(closes, s.vote_days);
      closes := public.site_add_days(opens, s.submit_days);
    end if;
    insert into public.site_rounds (season_key, name, prompt, opens_at, closes_at, votes_on_site, voting_closes_at,
                                    point_budget, max_per_track, nonvoters_keep_points,
                                    songs_per_round, downvotes, max_down_per_track, services, repeat_rule)
    values (k, btrim(coalesce(item->>'name', '')), btrim(coalesce(item->>'prompt', '')), opens, closes, true,
            public.site_add_days(closes, s.vote_days), s.point_budget, s.max_per_track, s.nonvoters_keep_points,
            s.songs_per_round, s.downvotes, s.max_down_per_track, s.services, s.repeat_rule)
    returning id into rid;
    perform public.site_round_people_apply(rid, item->'roles', item->'prompters');
  end loop;
  return k;
end;
$$;

-- The caller's ballot, as before, and now: a Spectator votes too, with no
-- track of their own.
create or replace function public.cast_ballot(p_round uuid, p_ballot jsonb)
returns void language plpgsql security definer set search_path = public as $$
declare
  uid uuid := auth.uid();
  r public.site_rounds%rowtype;
  mine uuid[];
  sids uuid[];
  pts int[];
  cmts text[];
  problem text;
begin
  if not public.is_member() then
    raise exception 'Only league members can vote.';
  end if;
  select * into r from public.site_rounds where id = p_round;
  if not found then
    raise exception 'That round doesn''t exist.';
  end if;
  if public.site_round_phase(p_round) <> 'voting' then
    raise exception 'Voting for this round isn''t open.';
  end if;
  select array_agg(o.submission_id) into mine from public.site_submission_owners o
   where o.round_id = p_round and o.user_id = uid;
  if mine is null and public.site_user_role(p_round, uid) is distinct from 'spectator' then
    raise exception 'Only players with a track in this round, and its Spectators, can vote.';
  end if;
  mine := coalesce(mine, '{}');
  if jsonb_typeof(p_ballot) is distinct from 'array' or jsonb_array_length(p_ballot) > 150 then
    raise exception 'The ballot doesn''t add up. Reload the page and try again.';
  end if;

  select coalesce(array_agg((e->>'submission')::uuid), '{}'),
         coalesce(array_agg((e->>'points')::int), '{}'),
         coalesce(array_agg(coalesce(btrim(e->>'comment'), '')), '{}')
    into sids, pts, cmts
    from jsonb_array_elements(p_ballot) e;

  if exists (select 1 from unnest(sids) s
              where s is null or not exists (select 1 from public.site_submissions x
                                              where x.id = s and x.round_id = p_round))
     or (select count(distinct s) from unnest(sids) s) <> cardinality(sids) then
    raise exception 'The ballot doesn''t add up. Reload the page and try again.';
  end if;
  if exists (select 1 from unnest(cmts) c where char_length(c) > 2000) then
    raise exception 'A comment can be at most 2000 characters.';
  end if;

  problem := public.ballot_problem(r.point_budget, r.max_per_track, r.downvotes, r.max_down_per_track, pts,
                                   array(select s = any(mine) from unnest(sids) s));
  if problem is not null then
    raise exception '%', problem;
  end if;

  delete from public.site_votes where round_id = p_round and user_id = uid;
  insert into public.site_votes (round_id, submission_id, user_id, points, comment)
  select p_round, t.sid, uid, t.p, t.c
    from unnest(sids, pts, cmts) as t(sid, p, c)
   where t.p <> 0 or t.c <> '';
  perform public.site_round_finish_early(p_round);
end;
$$;

-- Saves the caller's draft, as before, and now a Spectator's too.
create or replace function public.save_ballot_draft(p_round uuid, p_ballot jsonb)
returns timestamptz language plpgsql security definer set search_path = public as $$
declare
  uid uuid := auth.uid();
  r public.site_rounds%rowtype;
  mine uuid[];
  sids uuid[];
  pts int[];
  cmts text[];
  problem text;
  at timestamptz := clock_timestamp();
begin
  if not public.is_member() then
    raise exception 'Only league members can vote.';
  end if;
  select * into r from public.site_rounds where id = p_round;
  if not found then
    raise exception 'That round doesn''t exist.';
  end if;
  if public.site_round_phase(p_round) is distinct from 'voting' then
    raise exception 'Voting for this round isn''t open.';
  end if;
  select array_agg(o.submission_id) into mine from public.site_submission_owners o
   where o.round_id = p_round and o.user_id = uid;
  if mine is null and public.site_user_role(p_round, uid) is distinct from 'spectator' then
    raise exception 'Only players with a track in this round, and its Spectators, can vote.';
  end if;
  mine := coalesce(mine, '{}');
  if jsonb_typeof(p_ballot) is distinct from 'array' or jsonb_array_length(p_ballot) > 150 then
    raise exception 'The ballot doesn''t add up. Reload the page and try again.';
  end if;

  select coalesce(array_agg((e->>'submission')::uuid), '{}'),
         coalesce(array_agg((e->>'points')::int), '{}'),
         coalesce(array_agg(coalesce(btrim(e->>'comment'), '')), '{}')
    into sids, pts, cmts
    from jsonb_array_elements(p_ballot) e;

  if exists (select 1 from unnest(sids) s
              where s is null or not exists (select 1 from public.site_submissions x
                                              where x.id = s and x.round_id = p_round))
     or (select count(distinct s) from unnest(sids) s) <> cardinality(sids) then
    raise exception 'The ballot doesn''t add up. Reload the page and try again.';
  end if;
  if exists (select 1 from unnest(cmts) c where char_length(c) > 2000) then
    raise exception 'A comment can be at most 2000 characters.';
  end if;

  problem := public.draft_problem(r.point_budget, r.max_per_track, r.downvotes, r.max_down_per_track, pts,
                                  array(select s = any(mine) from unnest(sids) s));
  if problem is not null then
    raise exception '%', problem;
  end if;

  insert into public.site_ballot_drafts (round_id, user_id, ballot, saved_at)
  values (p_round, uid,
          (select coalesce(jsonb_agg(jsonb_build_object('submission', t.sid, 'points', t.p, 'comment', t.c)), '[]'::jsonb)
             from unnest(sids, pts, cmts) as t(sid, p, c)
            where t.p <> 0 or t.c <> ''),
          at)
  on conflict (round_id, user_id) do update set ballot = excluded.ballot, saved_at = excluded.saved_at;
  return at;
end;
$$;

-- Accelerated and Speedy, as before, and now: submissions close once every
-- DJ who has joined the site has all of the round's songs in, and voting
-- once every DJ with a track and every Spectator who has joined has voted.
create or replace function public.site_round_finish_early(p_round uuid)
returns void language plpgsql security definer set search_path = public as $$
declare
  r public.site_rounds%rowtype;
  s public.site_seasons%rowtype;
  saved interval;
begin
  select * into r from public.site_rounds where id = p_round for update;
  select * into s from public.site_seasons where key = r.season_key;
  if not found or s.timing = 'steady' then return; end if;
  if public.site_round_phase(p_round) = 'submitting' then
    if not exists (select 1 from public.site_season_players p join public.members m on m.competitor_id = p.competitor_id
                    where p.season_key = s.key and public.site_round_role(p_round, p.competitor_id) = 'dj')
       or exists (select 1 from public.site_season_players p join public.members m on m.competitor_id = p.competitor_id
                   where p.season_key = s.key and public.site_round_role(p_round, p.competitor_id) = 'dj'
                     and (select count(*) from public.site_submission_owners o
                           where o.round_id = p_round and o.user_id = m.user_id) < r.songs_per_round) then
      return;
    end if;
    saved := r.closes_at - now();
    update public.site_rounds set closed_at = now() where id = p_round;
    if s.timing = 'speedy' then
      -- voting keeps its full length, so its deadline must not fall before
      -- the old submission deadline: that deadline becomes now too
      update public.site_rounds set closes_at = now(), voting_closes_at = voting_closes_at - saved where id = p_round;
      perform public.site_season_shift(s.key, saved);
    end if;
  elsif public.site_round_phase(p_round) = 'voting' then
    if exists (select 1 from public.site_submission_owners o
                where o.round_id = p_round
                  and not exists (select 1 from public.site_votes v where v.round_id = p_round and v.user_id = o.user_id))
       or exists (select 1 from public.site_season_players p join public.members m on m.competitor_id = p.competitor_id
                   where p.season_key = s.key and public.site_round_role(p_round, p.competitor_id) = 'spectator'
                     and not exists (select 1 from public.site_votes v where v.round_id = p_round and v.user_id = m.user_id)) then
      return;
    end if;
    saved := r.voting_closes_at - now();
    update public.site_rounds set voting_closed_at = now() where id = p_round;
    if s.timing = 'speedy' then
      perform public.site_season_shift(s.key, saved);
    end if;
  end if;
end;
$$;

-- The reminder finder, as before, and now: "a round is open, send your
-- track" goes to its DJs only, and the voting reminders to its Spectators
-- who haven't voted, as well as to everyone with a track who hasn't.
create or replace function public.reminders_claim(p_channels text[])
returns table (round_id uuid, kind text, user_id uuid, channel text, round_name text,
               closes_at timestamptz, email text, subscriptions jsonb)
language sql security definer set search_path = public as $$
  with rounds as (
    select r.*, public.site_round_phase(r.id) as phase,
           coalesce(r.closed_at, r.closes_at) as voting_opened
      from public.site_rounds r),
  targets as (
    select r.id as round_id, 'round_open'::text as kind, m.user_id
      from rounds r cross join public.members m
     where r.phase = 'submitting' and r.opens_at > now() - interval '6 hours'
       and public.site_round_role(r.id, m.competitor_id) = 'dj'
    union all
    select r.id, 'playlist_ready', m.user_id
      from rounds r cross join public.members m
     where r.playlists_built_at is not null and r.playlists_built_at > now() - interval '12 hours'
    union all
    select r.id, k.kind, w.user_id
      from rounds r
      cross join lateral (
        select t.kind from (values
            ('vote_halfway', r.voting_opened + (r.voting_closes_at - r.voting_opened) / 2),
            ('vote_5h', r.voting_closes_at - interval '5 hours'),
            ('vote_2h', r.voting_closes_at - interval '2 hours'),
            ('vote_1h', r.voting_closes_at - interval '1 hour')) as t(kind, due)
         where t.due <= now() and t.due >= r.voting_opened
         order by t.due desc limit 1) k
      join (select o.round_id, o.user_id from public.site_submission_owners o
            union
            select x.id, m.user_id from public.site_rounds x
              join public.site_season_players p on p.season_key = x.season_key
              join public.members m on m.competitor_id = p.competitor_id
             where public.site_round_role(x.id, p.competitor_id) = 'spectator') w on w.round_id = r.id
     where r.phase = 'voting'
       and not exists (select 1 from public.site_votes v where v.round_id = r.id and v.user_id = w.user_id)),
  -- only the kinds the member wants (all, unless they turned one off)
  chosen as (
    select t.* from targets t
     where coalesce((select case when t.kind = 'round_open' then rs.round_open
                                 when t.kind = 'playlist_ready' then rs.playlist_ready
                                 else rs.voting end
                       from public.reminder_settings rs where rs.user_id = t.user_id), true)),
  wanted as (
    select t.round_id, t.kind, t.user_id, 'push'::text as channel from chosen t
     where 'push' = any(p_channels)
       and exists (select 1 from public.push_subscriptions s where s.user_id = t.user_id)
    union all
    select t.round_id, t.kind, t.user_id, 'email' from chosen t
     where 'email' = any(p_channels)
       and coalesce((select rs.email_on from public.reminder_settings rs where rs.user_id = t.user_id), true)
       and exists (select 1 from auth.users u where u.id = t.user_id and u.email is not null)),
  claimed as (
    insert into public.reminders_sent (round_id, kind, user_id, channel)
    select w.round_id, w.kind, w.user_id, w.channel from wanted w
    on conflict do nothing
    returning reminders_sent.round_id, reminders_sent.kind, reminders_sent.user_id, reminders_sent.channel)
  select c.round_id, c.kind, c.user_id, c.channel, r.name,
         case when c.kind like 'vote%' then r.voting_closes_at else r.closes_at end,
         case when c.channel = 'email' then (select u.email from auth.users u where u.id = c.user_id) end,
         case when c.channel = 'push' then (
           select coalesce(jsonb_agg(jsonb_build_object('endpoint', s.endpoint, 'p256dh', s.p256dh, 'auth', s.auth)), '[]'::jsonb)
             from public.push_subscriptions s where s.user_id = c.user_id) end
    from claimed c join public.site_rounds r on r.id = c.round_id;
$$;

-- Where the caller stands in a lounge, as before, and now a Spectator
-- could get in too.
create or replace function public.lounge_state(p_round uuid, p_practice boolean)
returns table (phase text, voters int, is_in boolean, eligible boolean, needed int)
language sql stable security definer set search_path = public as $$
  select
    case when p_practice then 'voting'
         when not r.votes_on_site then 'closed'
         else coalesce(nullif(public.site_round_phase(r.id), 'submitting'), 'closed') end,
    case when p_practice
         then (select count(*)::int from public.site_demo_ballots d
                where d.source_round = r.id and jsonb_array_length(d.ballot) > 0)
         else (select count(distinct v.user_id)::int from public.site_votes v where v.round_id = r.id) end,
    case when p_practice
         then exists (select 1 from public.site_demo_ballots d
                       where d.user_id = auth.uid() and d.source_round = r.id and jsonb_array_length(d.ballot) > 0)
         else exists (select 1 from public.site_votes v where v.round_id = r.id and v.user_id = auth.uid()) end,
    case when p_practice then public.is_member()
         else exists (select 1 from public.site_submission_owners o where o.round_id = r.id and o.user_id = auth.uid())
              or public.site_user_role(r.id, auth.uid()) = 'spectator' end,
    case when p_practice then 1 else 3 end
    from public.site_rounds r
   where r.id = p_round and public.is_member();
$$;

revoke all on function public.site_round_role(uuid, text) from public, anon, authenticated;
revoke all on function public.site_user_role(uuid, uuid) from public, anon, authenticated;
revoke all on function public.site_round_dj_count(uuid) from public, anon, authenticated;
revoke all on function public.site_round_people_apply(uuid, jsonb, jsonb) from public, anon, authenticated;
revoke all on function public.site_owner_is_dj() from public, anon, authenticated;
revoke all on function public.site_round_roster(uuid) from public, anon;
grant execute on function public.site_round_roster(uuid) to authenticated;
revoke all on function public.set_site_round_people(uuid, jsonb, jsonb) from public, anon;
grant execute on function public.set_site_round_people(uuid, jsonb, jsonb) to authenticated;
revoke all on function public.set_site_season_roster(text, jsonb) from public, anon;
grant execute on function public.set_site_season_roster(text, jsonb) to authenticated;
