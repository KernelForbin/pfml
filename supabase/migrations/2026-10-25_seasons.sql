-- Seasons set up on the site (README, Seasons on the site). Run once in the
-- Supabase SQL Editor for the live project, after 2026-10-25_commissioner.sql.
-- Safe to re-run. supabase/schema.sql has the same at its end, for a fresh
-- install.
--
-- Commissioners, stage 2 (asked 2026-10-25): a commissioner sets up a season
-- in steps (details, voting rules, timing, rounds, players). Its rounds are
-- scheduled ahead and open on their own, and every season set up here votes
-- on pfml.fun (the user's call). Season 3, and every round that already
-- exists, are left as they are: a season set up here is Season 4 or later,
-- and no existing round can join one.
--
-- Two new tables. Members read them (granted here explicitly, ahead of
-- Supabase's 2026-10-30 change); only the functions below write them.
-- This also replaces site_round_phase, submit_track, cast_ballot,
-- reminders_claim, site_rounds_export and site_rounds_times_guard. In
-- schema.sql the earlier definitions stay above, as the earlier migrations
-- ran them, and these, at the end, are the ones that stand.

-- ---------------------------------------------------------------- seasons on the site

-- A season set up on the site, with the rules every one of its rounds gets.
-- The number starts at 4: Season 3 was the last played in Music League.
create table if not exists public.site_seasons (
  key           text primary key check (key ~ '^season[0-9]+$' and substring(key from 7)::int >= 4),
  name          text not null check (char_length(btrim(name)) between 1 and 60),
  description   text not null default '' check (char_length(description) <= 2000),
  point_budget  smallint not null default 19 check (point_budget between 1 and 100),
  max_per_track smallint not null default 5 check (max_per_track between 1 and 100),
  nonvoters_keep_points boolean not null default false,
  timing        text not null default 'steady' check (timing in ('steady', 'accelerated', 'speedy')),
  submit_days   smallint not null default 2 check (submit_days between 1 and 14),
  vote_days     smallint not null default 5 check (vote_days between 1 and 14),
  created_at    timestamptz not null default now(),
  check (max_per_track <= point_budget)
);

-- Who's playing a season set up on the site: only they submit, and
-- Accelerated and Speedy wait on them.
create table if not exists public.site_season_players (
  season_key    text not null references public.site_seasons (key) on delete cascade,
  competitor_id text not null references public.players (competitor_id),
  primary key (season_key, competitor_id)
);

alter table public.site_seasons        enable row level security;
alter table public.site_season_players enable row level security;
drop policy if exists "members read site seasons" on public.site_seasons;
create policy "members read site seasons" on public.site_seasons
  for select to authenticated using (public.is_member());
drop policy if exists "members read site season players" on public.site_season_players;
create policy "members read site season players" on public.site_season_players
  for select to authenticated using (public.is_member());
revoke all on table public.site_seasons from anon, authenticated;
revoke all on table public.site_season_players from anon, authenticated;
grant select on table public.site_seasons to authenticated;
grant select on table public.site_season_players to authenticated;

-- When a round opens for submissions. A round made before this opened when
-- it was made.
alter table public.site_rounds add column if not exists opens_at timestamptz;
update public.site_rounds set opens_at = least(created_at, closes_at - interval '1 minute') where opens_at is null;
alter table public.site_rounds alter column opens_at set default now();
alter table public.site_rounds alter column opens_at set not null;
alter table public.site_rounds drop constraint if exists site_rounds_opens_first;
alter table public.site_rounds add constraint site_rounds_opens_first check (opens_at < closes_at);
create index if not exists site_rounds_season_opens on public.site_rounds (season_key, opens_at);

-- Where a round is: 'upcoming' before it opens, then as before.
create or replace function public.site_round_phase(p_round uuid)
returns text language sql stable security definer set search_path = public as $$
  select case
    when now() < r.opens_at then 'upcoming'
    when r.closed_at is null and now() < r.closes_at then 'submitting'
    when not r.votes_on_site then 'closed'
    when r.voting_closed_at is null and now() < r.voting_closes_at then 'voting'
    else 'finished' end
    from public.site_rounds r where r.id = p_round;
$$;

-- A number of days later on the league's clock, so a deadline stays at the
-- same time of day in Eastern time across a daylight-saving change.
create or replace function public.site_add_days(p_at timestamptz, p_days int)
returns timestamptz language sql stable set search_path = public as $$
  select ((p_at at time zone 'America/New_York') + make_interval(days => p_days)) at time zone 'America/New_York';
$$;

-- Lays out a season's rounds that haven't opened, one after another in
-- their order: each opens when the round before it closes voting, takes the
-- season's days to submit, then its days to vote. Before any round has
-- opened, the first keeps its first-playlist time.
create or replace function public.site_season_reschedule(p_season text)
returns void language plpgsql security definer set search_path = public as $$
declare
  s public.site_seasons%rowtype;
  r record;
  prev_vote timestamptz;
  opens timestamptz;
  closes timestamptz;
begin
  select * into s from public.site_seasons where key = p_season;
  if not found then return; end if;
  select x.voting_closes_at into prev_vote from public.site_rounds x
   where x.season_key = p_season and x.opens_at <= now() order by x.opens_at desc limit 1;
  for r in select x.id, x.closes_at from public.site_rounds x
            where x.season_key = p_season and x.opens_at > now() order by x.opens_at, x.created_at, x.id loop
    if prev_vote is null then
      closes := r.closes_at;
      opens := greatest(now(), public.site_add_days(closes, -s.submit_days));
    else
      opens := greatest(now(), prev_vote);
      closes := public.site_add_days(opens, s.submit_days);
    end if;
    prev_vote := public.site_add_days(closes, s.vote_days);
    update public.site_rounds set opens_at = opens, closes_at = closes, voting_closes_at = prev_vote where id = r.id;
  end loop;
end;
$$;

-- Moves every round of a season that hasn't opened yet earlier by p_by
-- (Speedy: the time a finished phase saved).
create or replace function public.site_season_shift(p_season text, p_by interval)
returns void language sql security definer set search_path = public as $$
  update public.site_rounds
     set opens_at = greatest(now(), opens_at - p_by), closes_at = closes_at - p_by, voting_closes_at = voting_closes_at - p_by
   where season_key = p_season and opens_at > now();
$$;

-- Accelerated and Speedy: once everyone playing who has joined the site has
-- a track in, submissions close; once everyone with a track has voted,
-- voting closes. Speedy also moves the rest of the season up by the time
-- saved. Steady waits for the deadlines.
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
                    where p.season_key = s.key)
       or exists (select 1 from public.site_season_players p join public.members m on m.competitor_id = p.competitor_id
                   where p.season_key = s.key
                     and not exists (select 1 from public.site_submission_owners o where o.round_id = p_round and o.user_id = m.user_id)) then
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
                  and not exists (select 1 from public.site_votes v where v.round_id = p_round and v.user_id = o.user_id)) then
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

-- Takes a submission, as before, and now: not before the round opens, only
-- from someone playing when the season was set up on the site, and, when
-- it's the last track in, closes submissions early (Accelerated, Speedy).
create or replace function public.submit_track(p_round uuid, p_platform text, p_track text)
returns text language plpgsql security definer set search_path = public as $$
declare
  uid uuid := auth.uid();
  r public.site_rounds%rowtype;
  mine uuid;
  new_tag text;
begin
  if not public.is_member() then
    raise exception 'Only league members can submit.';
  end if;
  select * into r from public.site_rounds where id = p_round for update;
  if not found then
    raise exception 'That round doesn''t exist.';
  end if;
  if now() < r.opens_at then
    raise exception 'This round hasn''t opened yet.';
  end if;
  if r.closed_at is not null or now() >= r.closes_at then
    raise exception 'Submissions for this round are closed.';
  end if;
  if exists (select 1 from public.site_seasons s where s.key = r.season_key)
     and not exists (select 1 from public.site_season_players p join public.members m on m.competitor_id = p.competitor_id
                      where p.season_key = r.season_key and m.user_id = uid) then
    raise exception 'You aren''t playing this season. Ask a commissioner to add you.';
  end if;
  if not ((p_platform = 'spotify'    and p_track ~ '^[A-Za-z0-9]{22}$') or
          (p_platform = 'youtube'    and p_track ~ '^[A-Za-z0-9_-]{11}$') or
          (p_platform = 'soundcloud' and p_track ~ '^[a-z0-9_-]{1,100}/[a-z0-9_-]{1,200}$')) then
    raise exception 'That isn''t a Spotify, YouTube or SoundCloud track the site can use.';
  end if;

  select o.submission_id into mine from public.site_submission_owners o
   where o.round_id = p_round and o.user_id = uid;

  if exists (select 1 from public.site_submissions s
              where s.round_id = p_round and s.platform = p_platform and s.track = p_track
                and s.id is distinct from mine) then
    raise exception 'Someone has already submitted that track this round.';
  end if;

  if mine is not null then
    update public.site_submissions set platform = p_platform, track = p_track
     where id = mine returning tag into new_tag;
    return new_tag;
  end if;

  if (select count(*) from public.site_submissions where round_id = p_round) >= 150 then
    raise exception 'This round is full.';
  end if;
  loop
    new_tag := substr('ABCDEFGHJKLMNPQRSTUVWXYZ', 1 + floor(random() * 24)::int, 1)
            || (2 + floor(random() * 8)::int)::text;
    exit when not exists (select 1 from public.site_submissions
                           where round_id = p_round and tag = new_tag);
  end loop;
  insert into public.site_submissions (round_id, tag, platform, track)
  values (p_round, new_tag, p_platform, p_track) returning id into mine;
  insert into public.site_submission_owners (submission_id, round_id, user_id)
  values (mine, p_round, uid);
  perform public.site_round_finish_early(p_round);
  return new_tag;
end;
$$;

-- The caller's ballot, as before, and now, when it's the last one in,
-- closes voting early (Accelerated, Speedy).
create or replace function public.cast_ballot(p_round uuid, p_ballot jsonb)
returns void language plpgsql security definer set search_path = public as $$
declare
  uid uuid := auth.uid();
  r public.site_rounds%rowtype;
  mine uuid;
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
  select o.submission_id into mine from public.site_submission_owners o
   where o.round_id = p_round and o.user_id = uid;
  if mine is null then
    raise exception 'Only players with a track in this round can vote.';
  end if;
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

  problem := public.ballot_problem(r.point_budget, r.max_per_track, pts,
                                   array(select s = mine from unnest(sids) s));
  if problem is not null then
    raise exception '%', problem;
  end if;

  delete from public.site_votes where round_id = p_round and user_id = uid;
  insert into public.site_votes (round_id, submission_id, user_id, points, comment)
  select p_round, t.sid, uid, t.p, t.c
    from unnest(sids, pts, cmts) as t(sid, p, c)
   where t.p > 0 or t.c <> '';
  perform public.site_round_finish_early(p_round);
end;
$$;

-- The reminder finder, as before, and now: a round is announced when it
-- opens (not when it was made), and a round in a season set up on the site
-- only to the people playing it.
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
       and (not exists (select 1 from public.site_seasons s where s.key = r.season_key)
            or exists (select 1 from public.site_season_players p
                        where p.season_key = r.season_key and p.competitor_id = m.competitor_id))
    union all
    select r.id, 'playlist_ready', m.user_id
      from rounds r cross join public.members m
     where r.playlists_built_at is not null and r.playlists_built_at > now() - interval '12 hours'
    union all
    select r.id, k.kind, o.user_id
      from rounds r
      cross join lateral (
        select t.kind from (values
            ('vote_halfway', r.voting_opened + (r.voting_closes_at - r.voting_opened) / 2),
            ('vote_5h', r.voting_closes_at - interval '5 hours'),
            ('vote_2h', r.voting_closes_at - interval '2 hours'),
            ('vote_1h', r.voting_closes_at - interval '1 hour')) as t(kind, due)
         where t.due <= now() and t.due >= r.voting_opened
         order by t.due desc limit 1) k
      join public.site_submission_owners o on o.round_id = r.id
     where r.phase = 'voting'
       and not exists (select 1 from public.site_votes v where v.round_id = r.id and v.user_id = o.user_id)),
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

-- Finished rounds voted here, for publish.py, as before, and now: each
-- round dated by when it opened (a season's rounds are all made at once),
-- in that order, and the names of the seasons set up on the site.
create or replace function public.site_rounds_export()
returns jsonb language sql stable security definer set search_path = public as $$
  select jsonb_build_object(
    'rounds', coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', r.id, 'season_key', r.season_key, 'name', r.name, 'prompt', r.prompt,
        'created_at', r.opens_at, 'voting_ended_at', coalesce(r.voting_closed_at, r.voting_closes_at),
        'spotify_playlist', r.spotify_playlist, 'point_budget', r.point_budget,
        'nonvoters_keep_points', r.nonvoters_keep_points,
        'submissions', coalesce((
          select jsonb_agg(jsonb_build_object(
            'id', s.id, 'tag', s.tag, 'platform', s.platform, 'track', s.track,
            'title', s.title, 'artist', s.artist, 'spotify_match', s.spotify_match,
            'position', s.position, 'submitter', m.competitor_id) order by s.tag)
            from public.site_submissions s
            left join public.site_submission_owners o on o.submission_id = s.id
            left join public.members m on m.user_id = o.user_id
           where s.round_id = r.id), '[]'::jsonb),
        'votes', coalesce((
          select jsonb_agg(jsonb_build_object(
            'submission', v.submission_id, 'voter', m.competitor_id, 'points', v.points,
            'comment', v.comment, 'cast_at', v.cast_at) order by v.submission_id, m.competitor_id)
            from public.site_votes v
            join public.members m on m.user_id = v.user_id
           where v.round_id = r.id), '[]'::jsonb)
      ) order by r.opens_at, r.created_at)
        from public.site_rounds r
       where r.votes_on_site and public.site_round_phase(r.id) = 'finished'), '[]'::jsonb),
    'players', coalesce((select jsonb_object_agg(p.competitor_id, p.name) from public.players p), '{}'::jsonb),
    'seasons', coalesce((select jsonb_object_agg(s.key, s.name) from public.site_seasons s), '{}'::jsonb));
$$;

-- The deadline guard, as before, and now: a round's opening time can't
-- change once it has opened, or move into the past; a round can't be added
-- to, or moved into or out of, a season set up on the site except through
-- the functions below; and a round made by hand opens when it's made and
-- votes in Music League.
create or replace function public.site_rounds_times_guard()
returns trigger language plpgsql set search_path = public as $$
declare
  started boolean;
  subs_closed boolean;
  votes_closed boolean;
begin
  if current_user <> 'authenticated' then
    return new;
  end if;
  if tg_op = 'INSERT' then
    if exists (select 1 from public.site_seasons s where s.key = new.season_key) then
      raise exception 'Add a round to this season from its section on the Commissioner page.';
    end if;
    if new.votes_on_site then
      raise exception 'Only a season set up on the site votes on the site.';
    end if;
    if new.closes_at <= now() then
      raise exception 'The closing time has to be in the future.';
    end if;
    new.opens_at := now();
    new.closed_at := null;
    new.voting_closed_at := null;
    return new;
  end if;

  started := now() >= old.opens_at;
  if new.opens_at is distinct from old.opens_at then
    if started then
      raise exception 'This round has opened, so its opening time can''t change.';
    end if;
    if new.opens_at <= now() then
      raise exception 'The opening time has to be in the future.';
    end if;
  end if;
  if new.season_key is distinct from old.season_key
     and exists (select 1 from public.site_seasons s where s.key in (old.season_key, new.season_key)) then
    raise exception 'A round can''t move into or out of a season set up on the site.';
  end if;

  subs_closed := old.closed_at is not null or now() >= old.closes_at;
  if subs_closed and (new.closes_at is distinct from old.closes_at or new.closed_at is distinct from old.closed_at) then
    raise exception 'Submissions for this round have closed, so its deadline can''t change.';
  end if;
  if subs_closed and new.season_key is distinct from old.season_key then
    raise exception 'A round can''t move to another season once submissions have closed.';
  end if;
  if new.closes_at is distinct from old.closes_at and new.closes_at <= now() then
    raise exception 'The closing time has to be in the future.';
  end if;
  if new.closed_at is distinct from old.closed_at then
    if not started then
      raise exception 'This round hasn''t opened yet.';
    end if;
    new.closed_at := now();
  end if;

  votes_closed := old.voting_closed_at is not null or (old.voting_closes_at is not null and now() >= old.voting_closes_at);
  if votes_closed and (new.voting_closes_at is distinct from old.voting_closes_at
                       or new.voting_closed_at is distinct from old.voting_closed_at) then
    raise exception 'Voting for this round has closed, so its deadline can''t change.';
  end if;
  if new.voting_closes_at is distinct from old.voting_closes_at and new.voting_closes_at <= now() then
    raise exception 'The voting deadline has to be in the future.';
  end if;
  if new.voting_closed_at is distinct from old.voting_closed_at then
    if subs_closed is false then
      raise exception 'Voting can''t close before submissions do.';
    end if;
    new.voting_closed_at := now();
  end if;
  return new;
end;
$$;

-- ---------------------------------------------------------------- what commissioners call

-- Sets up a season: its rules, who's playing, and its rounds, laid out one
-- after another from the first playlist (when round 1's submissions close).
-- p: {key, name, description, point_budget, max_per_track,
-- nonvoters_keep_points, timing, submit_days, vote_days, first_playlist_at,
-- rounds: [{name, prompt}], players: [competitor id]}.
create or replace function public.create_site_season(p jsonb)
returns text language plpgsql security definer set search_path = public as $$
declare
  k text := p->>'key';
  s public.site_seasons%rowtype;
  first_close timestamptz;
  item jsonb;
  opens timestamptz;
  closes timestamptz;
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
  if jsonb_typeof(p->'players') is distinct from 'array' or jsonb_array_length(p->'players') < 2 then
    raise exception 'A season needs at least 2 players.';
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
                                   timing, submit_days, vote_days)
  values (k, btrim(coalesce(p->>'name', '')), btrim(coalesce(p->>'description', '')),
          coalesce((p->>'point_budget')::smallint, 19), coalesce((p->>'max_per_track')::smallint, 5),
          coalesce((p->>'nonvoters_keep_points')::boolean, false), coalesce(p->>'timing', 'steady'),
          coalesce((p->>'submit_days')::smallint, 2), coalesce((p->>'vote_days')::smallint, 5))
  returning * into s;
  insert into public.site_season_players (season_key, competitor_id)
  select distinct k, x from jsonb_array_elements_text(p->'players') x;

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
                                    point_budget, max_per_track, nonvoters_keep_points)
    values (k, btrim(coalesce(item->>'name', '')), btrim(coalesce(item->>'prompt', '')), opens, closes, true,
            public.site_add_days(closes, s.vote_days), s.point_budget, s.max_per_track, s.nonvoters_keep_points);
  end loop;
  return k;
end;
$$;

-- Changes a season's details, rules or timing. Rules reach every round
-- whose submissions haven't closed; days and order reach the rounds that
-- haven't opened, which are laid out again.
create or replace function public.update_site_season(p_key text, p jsonb)
returns void language plpgsql security definer set search_path = public as $$
declare
  s public.site_seasons%rowtype;
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can change a season.';
  end if;
  update public.site_seasons set
    name = btrim(coalesce(p->>'name', name)),
    description = btrim(coalesce(p->>'description', description)),
    point_budget = coalesce((p->>'point_budget')::smallint, point_budget),
    max_per_track = coalesce((p->>'max_per_track')::smallint, max_per_track),
    nonvoters_keep_points = coalesce((p->>'nonvoters_keep_points')::boolean, nonvoters_keep_points),
    timing = coalesce(p->>'timing', timing),
    submit_days = coalesce((p->>'submit_days')::smallint, submit_days),
    vote_days = coalesce((p->>'vote_days')::smallint, vote_days)
   where key = p_key
  returning * into s;
  if not found then
    raise exception 'That season doesn''t exist.';
  end if;
  update public.site_rounds set point_budget = s.point_budget, max_per_track = s.max_per_track,
                                nonvoters_keep_points = s.nonvoters_keep_points
   where season_key = p_key and closed_at is null and now() < closes_at;
  perform public.site_season_reschedule(p_key);
end;
$$;

-- Adds a round at the end of a season.
create or replace function public.add_site_season_round(p_key text, p_name text, p_prompt text)
returns uuid language plpgsql security definer set search_path = public as $$
declare
  s public.site_seasons%rowtype;
  last_vote timestamptz;
  opens timestamptz;
  closes timestamptz;
  rid uuid;
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can add a round.';
  end if;
  select * into s from public.site_seasons where key = p_key;
  if not found then
    raise exception 'That season doesn''t exist.';
  end if;
  if btrim(coalesce(p_name, '')) = '' then
    raise exception 'Give the round a name.';
  end if;
  if (select count(*) from public.site_rounds where season_key = p_key) >= 40 then
    raise exception 'A season can have at most 40 rounds.';
  end if;
  select max(voting_closes_at) into last_vote from public.site_rounds where season_key = p_key;
  opens := greatest(now(), coalesce(last_vote, now()));
  closes := public.site_add_days(opens, s.submit_days);
  insert into public.site_rounds (season_key, name, prompt, opens_at, closes_at, votes_on_site, voting_closes_at,
                                  point_budget, max_per_track, nonvoters_keep_points)
  values (p_key, btrim(coalesce(p_name, '')), btrim(coalesce(p_prompt, '')), opens, closes, true,
          public.site_add_days(closes, s.vote_days), s.point_budget, s.max_per_track, s.nonvoters_keep_points)
  returning id into rid;
  return rid;
end;
$$;

-- Swaps a round that hasn't opened with the one before or after it (also
-- not opened), then lays the season out again.
create or replace function public.move_site_season_round(p_round uuid, p_earlier boolean)
returns void language plpgsql security definer set search_path = public as $$
declare
  r public.site_rounds%rowtype;
  o public.site_rounds%rowtype;
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can reorder rounds.';
  end if;
  select * into r from public.site_rounds where id = p_round;
  if not found or not exists (select 1 from public.site_seasons s where s.key = r.season_key) then
    raise exception 'That round isn''t in a season set up on the site.';
  end if;
  if now() >= r.opens_at then
    raise exception 'Only a round that hasn''t opened can move.';
  end if;
  if p_earlier then
    select * into o from public.site_rounds x where x.season_key = r.season_key and x.opens_at < r.opens_at
     order by x.opens_at desc limit 1;
  else
    select * into o from public.site_rounds x where x.season_key = r.season_key and x.opens_at > r.opens_at
     order by x.opens_at limit 1;
  end if;
  if not found or now() >= o.opens_at then
    raise exception 'That round can''t move that way.';
  end if;
  update public.site_rounds set opens_at = o.opens_at, closes_at = o.closes_at, voting_closes_at = o.voting_closes_at
   where id = r.id;
  update public.site_rounds set opens_at = r.opens_at, closes_at = r.closes_at, voting_closes_at = r.voting_closes_at
   where id = o.id;
  perform public.site_season_reschedule(r.season_key);
end;
$$;

-- Removes a round that hasn't opened (so it has no tracks), then lays the
-- season out again.
create or replace function public.remove_site_season_round(p_round uuid)
returns void language plpgsql security definer set search_path = public as $$
declare
  r public.site_rounds%rowtype;
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can remove a round.';
  end if;
  select * into r from public.site_rounds where id = p_round;
  if not found or not exists (select 1 from public.site_seasons s where s.key = r.season_key) then
    raise exception 'That round isn''t in a season set up on the site.';
  end if;
  if now() >= r.opens_at then
    raise exception 'A round that has opened can''t be removed.';
  end if;
  delete from public.site_rounds where id = p_round;
  perform public.site_season_reschedule(r.season_key);
end;
$$;

-- Who's playing a season, replaced as a whole.
create or replace function public.set_site_season_players(p_key text, p_players text[])
returns void language plpgsql security definer set search_path = public as $$
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can choose who''s playing.';
  end if;
  if not exists (select 1 from public.site_seasons where key = p_key) then
    raise exception 'That season doesn''t exist.';
  end if;
  if coalesce(cardinality(p_players), 0) < 2 then
    raise exception 'A season needs at least 2 players.';
  end if;
  delete from public.site_season_players where season_key = p_key and competitor_id <> all(p_players);
  insert into public.site_season_players (season_key, competitor_id)
  select distinct p_key, x from unnest(p_players) x
  on conflict do nothing;
end;
$$;

revoke all on function public.site_add_days(timestamptz, int) from public, anon, authenticated;
revoke all on function public.site_season_reschedule(text) from public, anon, authenticated;
revoke all on function public.site_season_shift(text, interval) from public, anon, authenticated;
revoke all on function public.site_round_finish_early(uuid) from public, anon, authenticated;
revoke all on function public.create_site_season(jsonb) from public, anon;
grant execute on function public.create_site_season(jsonb) to authenticated;
revoke all on function public.update_site_season(text, jsonb) from public, anon;
grant execute on function public.update_site_season(text, jsonb) to authenticated;
revoke all on function public.add_site_season_round(text, text, text) from public, anon;
grant execute on function public.add_site_season_round(text, text, text) to authenticated;
revoke all on function public.move_site_season_round(uuid, boolean) from public, anon;
grant execute on function public.move_site_season_round(uuid, boolean) to authenticated;
revoke all on function public.remove_site_season_round(uuid) from public, anon;
grant execute on function public.remove_site_season_round(uuid) to authenticated;
revoke all on function public.set_site_season_players(text, text[]) from public, anon;
grant execute on function public.set_site_season_players(text, text[]) to authenticated;
