-- Commissioner tools (asked 2026-11-25; README, Commissioner tools): pausing
-- a season, the Now panel's deadline buttons and nudges, sitting a round
-- out, the activity log, a round's own number of days, prompt rotation,
-- scheduled and season-only announcements, and invite links from the page.
-- Run it in the Supabase SQL Editor, then the rehearsal,
-- supabase/checks/2026-11-25_commissioner_tools_rehearsal.sql. The code
-- that uses it ships only after both.
--
-- It replaces site_rounds_times_guard, site_season_reschedule,
-- site_season_shift, site_round_finish_early, reminders_claim,
-- announcements_claim, post_announcement, move_site_season_round and
-- site_rounds_list: their definitions earlier in schema.sql are what the
-- earlier migrations ran, and these, last, are the ones that stand.

-- ---------------------------------------------------------------- helpers

-- "Tue, Dec 2, 8:00 PM Eastern": the league's own clock, for messages the
-- database writes (it doesn't know the reader's time zone).
create or replace function public.site_when(p_at timestamptz)
returns text language sql stable set search_path = public as $$
  select to_char(p_at at time zone 'America/New_York', 'FMDy, FMMon FMDD, FMHH12:MI AM') || ' Eastern';
$$;

-- A round as members may see it named: "Round 3" while its prompt is
-- hidden from some of them, its name otherwise.
create or replace function public.site_round_label(p_round uuid)
returns text language sql stable security definer set search_path = public as $$
  select case when r.hide_prompt and public.site_round_phase(r.id) <> 'finished'
              then public.site_round_public_name(r.id)
              else public.site_round_public_name(r.id) || ': ' || r.name end
    from public.site_rounds r where r.id = p_round;
$$;

-- Changes made on the database's own account (an early close, a pause
-- moving deadlines, a whole season set up at once) mark the transaction
-- quiet, so the activity log's triggers don't record each row they touch.
create or replace function public.site_quiet()
returns void language sql set search_path = public as $$
  select set_config('pfml.quiet', 'on', true);
$$;

create or replace function public.site_is_quiet()
returns boolean language sql stable set search_path = public as $$
  select coalesce(current_setting('pfml.quiet', true), '') = 'on';
$$;

-- ---------------------------------------------------------------- activity log

-- What the commissioners did, newest first on the Commissioner page. actor
-- null is the site itself (a scheduled pause starting, say). Nobody reads
-- the table directly: site_activity_list() hands it to commissioners.
create table if not exists public.site_activity (
  id         bigint generated always as identity primary key,
  at         timestamptz not null default now(),
  actor      uuid references auth.users (id) on delete set null,
  action     text not null check (char_length(action) between 1 and 300),
  season_key text,
  round_id   uuid
);
create index if not exists site_activity_at on public.site_activity (at desc, id desc);
alter table public.site_activity enable row level security;
revoke all on table public.site_activity from anon, authenticated;

-- One line in the log. The same line twice in one transaction is kept once.
create or replace function public.site_log(p_action text, p_season text, p_round uuid, p_actor uuid)
returns void language plpgsql security definer set search_path = public as $$
begin
  if exists (select 1 from public.site_activity a
              where a.at = now() and a.actor is not distinct from p_actor and a.action = left(p_action, 300)) then
    return;
  end if;
  insert into public.site_activity (actor, action, season_key, round_id)
  values (p_actor, left(p_action, 300), p_season, p_round);
end;
$$;

-- A commissioner's change through a trigger: only when a signed-in
-- commissioner made it, and the transaction isn't quiet.
create or replace function public.site_log_by_commissioner(p_action text, p_season text, p_round uuid)
returns void language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null or public.site_is_quiet() or not public.is_commissioner() then
    return;
  end if;
  perform public.site_log(p_action, p_season, p_round, auth.uid());
end;
$$;

create or replace function public.site_rounds_logged()
returns trigger language plpgsql security definer set search_path = public as $$
declare
  label text;
begin
  if tg_op = 'DELETE' then
    perform public.site_log_by_commissioner('Removed the round "' || old.name || '"', old.season_key, null);
    return null;
  end if;
  label := '"' || new.name || '"';
  if tg_op = 'INSERT' then
    perform public.site_log_by_commissioner('Added the round ' || label, new.season_key, new.id);
    return null;
  end if;
  if new.name is distinct from old.name or new.prompt is distinct from old.prompt then
    perform public.site_log_by_commissioner('Edited the name or prompt of ' || label, new.season_key, new.id);
  end if;
  if new.closed_at is distinct from old.closed_at and new.closed_at is not null then
    perform public.site_log_by_commissioner('Closed submissions early in ' || label, new.season_key, new.id);
  elsif new.closes_at is distinct from old.closes_at then
    perform public.site_log_by_commissioner('Moved ' || label || '''s submission deadline to ' || public.site_when(new.closes_at),
                                            new.season_key, new.id);
  end if;
  if new.voting_closed_at is distinct from old.voting_closed_at and new.voting_closed_at is not null then
    perform public.site_log_by_commissioner('Closed voting early in ' || label, new.season_key, new.id);
  elsif new.voting_closes_at is distinct from old.voting_closes_at and new.voting_closes_at is not null then
    perform public.site_log_by_commissioner('Moved ' || label || '''s voting deadline to ' || public.site_when(new.voting_closes_at),
                                            new.season_key, new.id);
  end if;
  if (new.point_budget, new.max_per_track, new.nonvoters_keep_points, new.songs_per_round, new.downvotes,
      new.max_down_per_track, new.services, new.repeat_rule, new.hide_prompt, new.hide_prompter, new.votes_on_site)
     is distinct from
     (old.point_budget, old.max_per_track, old.nonvoters_keep_points, old.songs_per_round, old.downvotes,
      old.max_down_per_track, old.services, old.repeat_rule, old.hide_prompt, old.hide_prompter, old.votes_on_site) then
    perform public.site_log_by_commissioner('Changed the rules of ' || label, new.season_key, new.id);
  end if;
  return null;
end;
$$;
drop trigger if exists site_rounds_logged on public.site_rounds;
create trigger site_rounds_logged after insert or update or delete on public.site_rounds
  for each row execute function public.site_rounds_logged();

-- A season set up or changed: logged once, and what it does to its rounds
-- after that (laying them out, copying its rules) stays quiet. Only the
-- commissioners' functions write seasons, so this logs even in a quiet
-- transaction.
create or replace function public.site_seasons_logged()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is not null and public.is_commissioner() then
    perform public.site_log(case when tg_op = 'INSERT' then 'Set up the season "' else 'Changed the settings of "' end
                            || new.name || '"', new.key, null, auth.uid());
  end if;
  perform public.site_quiet();
  return null;
end;
$$;
drop trigger if exists site_seasons_logged on public.site_seasons;
create trigger site_seasons_logged after insert or update on public.site_seasons
  for each row execute function public.site_seasons_logged();

create or replace function public.site_season_players_logged()
returns trigger language plpgsql security definer set search_path = public as $$
declare
  k text := coalesce(new.season_key, old.season_key);
begin
  perform public.site_log_by_commissioner('Changed who''s playing in "' || (select s.name from public.site_seasons s where s.key = k) || '"',
                                          k, null);
  return null;
end;
$$;
drop trigger if exists site_season_players_logged on public.site_season_players;
create trigger site_season_players_logged after insert or update or delete on public.site_season_players
  for each row execute function public.site_season_players_logged();

create or replace function public.site_round_people_logged()
returns trigger language plpgsql security definer set search_path = public as $$
declare
  rid uuid := coalesce(new.round_id, old.round_id);
  r public.site_rounds%rowtype;
begin
  select * into r from public.site_rounds where id = rid;
  if found then
    perform public.site_log_by_commissioner(
      case when tg_table_name = 'site_round_prompters' then 'Changed who wrote the prompt of "' else 'Changed the DJs and Spectators of "' end
      || r.name || '"', r.season_key, rid);
  end if;
  return null;
end;
$$;
drop trigger if exists site_round_roles_logged on public.site_round_roles;
create trigger site_round_roles_logged after insert or update or delete on public.site_round_roles
  for each row execute function public.site_round_people_logged();
drop trigger if exists site_round_prompters_logged on public.site_round_prompters;
create trigger site_round_prompters_logged after insert or update or delete on public.site_round_prompters
  for each row execute function public.site_round_people_logged();

create or replace function public.site_members_logged()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  if new.role is distinct from old.role then
    perform public.site_log_by_commissioner(
      'Made ' || (select p.name from public.players p where p.competitor_id = new.competitor_id)
      || case when new.role = 'commissioner' then ' a commissioner' else ' a member again' end, null, null);
  end if;
  return null;
end;
$$;
drop trigger if exists site_members_logged on public.members;
create trigger site_members_logged after update of role on public.members
  for each row execute function public.site_members_logged();

create or replace function public.site_players_logged()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  perform public.site_log_by_commissioner('Added ' || new.name || ' to the league', null, null);
  return null;
end;
$$;
drop trigger if exists site_players_logged on public.players;
create trigger site_players_logged after insert on public.players
  for each row execute function public.site_players_logged();

-- The log for the Commissioner page, newest first, a page at a time
-- (p_before: the last id of the page before).
create or replace function public.site_activity_list(p_before bigint, p_limit int)
returns table (id bigint, at timestamptz, who text, action text)
language plpgsql stable security definer set search_path = public as $$
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can read the activity log.';
  end if;
  return query
    select a.id, a.at,
           case when a.actor is null then 'The site'
                else coalesce((select p.name from public.members m join public.players p on p.competitor_id = m.competitor_id
                                where m.user_id = a.actor), 'A former commissioner') end,
           a.action
      from public.site_activity a
     where p_before is null or a.id < p_before
     order by a.id desc
     limit least(greatest(coalesce(p_limit, 50), 1), 200);
end;
$$;

-- ---------------------------------------------------------------- notifications to one member

-- A push to one member, sent by the send-reminders timer through
-- announcements_claim (so the Edge Function needs no change): a nudge, a
-- sit-out answer, a prompt to write. Nobody reads these but the claim.
create table if not exists public.site_push_notices (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users (id) on delete cascade,
  kind       text not null check (kind in ('nudge_submit', 'nudge_vote', 'sitout', 'rotation')),
  author     text not null check (char_length(author) between 1 and 80),
  body       text not null check (char_length(body) between 1 and 1000),
  created_at timestamptz not null default now(),
  pushed_at  timestamptz
);
create index if not exists site_push_notices_waiting on public.site_push_notices (created_at) where pushed_at is null;
alter table public.site_push_notices enable row level security;
revoke all on table public.site_push_notices from anon, authenticated;

-- The name a notice is from: the member who caused it, or the site.
create or replace function public.site_author(p_user uuid)
returns text language sql stable security definer set search_path = public as $$
  select coalesce((select p.name from public.members m join public.players p on p.competitor_id = m.competitor_id
                    where m.user_id = p_user), 'PFML');
$$;

create or replace function public.site_notify(p_user uuid, p_kind text, p_author text, p_body text)
returns void language sql security definer set search_path = public as $$
  insert into public.site_push_notices (user_id, kind, author, body)
  select p_user, p_kind, left(p_author, 80), left(p_body, 1000) where p_user is not null;
$$;

create or replace function public.site_notify_commissioners(p_kind text, p_author text, p_body text)
returns void language sql security definer set search_path = public as $$
  insert into public.site_push_notices (user_id, kind, author, body)
  select m.user_id, p_kind, left(p_author, 80), left(p_body, 1000)
    from public.members m where m.role in ('commissioner', 'admin');
$$;

-- ---------------------------------------------------------------- a round's own days

-- A round can take more (or fewer) days than its season's to submit and to
-- vote: a holiday round, say. Null is the season's.
alter table public.site_rounds add column if not exists submit_days smallint check (submit_days between 1 and 14);
alter table public.site_rounds add column if not exists vote_days smallint check (vote_days between 1 and 14);
grant select (submit_days, vote_days) on table public.site_rounds to authenticated;

-- ---------------------------------------------------------------- sitting a round out

-- A player who asked to sit a round out, and whether a commissioner said
-- yes. Sitting out: no track expected, Accelerated and Speedy don't wait
-- for them, and no reminders or nudges. Members see who (the roster says
-- so); only the functions below write.
create table if not exists public.site_round_sitouts (
  round_id      uuid not null references public.site_rounds (id) on delete cascade,
  competitor_id text not null references public.players (competitor_id),
  status        text not null default 'asked' check (status in ('asked', 'approved')),
  asked_at      timestamptz not null default now(),
  decided_at    timestamptz,
  decided_by    uuid references auth.users (id) on delete set null,
  primary key (round_id, competitor_id)
);
alter table public.site_round_sitouts enable row level security;
drop policy if exists "members read sit-outs" on public.site_round_sitouts;
create policy "members read sit-outs" on public.site_round_sitouts
  for select to authenticated using (public.is_member());
revoke all on table public.site_round_sitouts from anon, authenticated;
grant select (round_id, competitor_id, status, asked_at) on table public.site_round_sitouts to authenticated;

create or replace function public.site_sitting_out(p_round uuid, p_competitor text)
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.site_round_sitouts x
                  where x.round_id = p_round and x.competitor_id = p_competitor and x.status = 'approved');
$$;

-- ---------------------------------------------------------------- pausing a season

-- A season's pause: now, at a set time, or once a round's voting closes;
-- until a set time, or until a commissioner resumes it. One open at a time
-- per season. While it's on, time stops: when it starts, every deadline
-- still ahead moves out by the pause (whole days, so each keeps its time of
-- day: hold_days; a year when there's no resume time yet), and when it
-- ends they settle at the length it really took, rounded up to whole days,
-- so the round that was open gets back at least the time it had left.
create table if not exists public.site_season_pauses (
  id          uuid primary key default gen_random_uuid(),
  season_key  text not null references public.site_seasons (key) on delete cascade,
  starts_at   timestamptz,
  after_round uuid references public.site_rounds (id) on delete cascade,
  resume_at   timestamptz,
  note        text not null default '' check (char_length(note) <= 300),
  started_at  timestamptz,
  hold_days   int,
  ended_at    timestamptz,
  created_by  uuid references auth.users (id) on delete set null,
  created_at  timestamptz not null default now(),
  check (starts_at is not null or after_round is not null),
  check (starts_at is null or after_round is null)
);
create unique index if not exists site_season_pauses_one_open on public.site_season_pauses (season_key) where ended_at is null;
alter table public.site_season_pauses enable row level security;
revoke all on table public.site_season_pauses from anon, authenticated;

-- Whole days on the league's clock from p_from to at least p_to.
create or replace function public.site_days_until(p_from timestamptz, p_to timestamptz)
returns int language plpgsql stable set search_path = public as $$
declare
  n int;
begin
  if p_to <= p_from then
    return 0;
  end if;
  n := greatest(floor(extract(epoch from (p_to - p_from)) / 86400)::int - 1, 0);
  while public.site_add_days(p_from, n) < p_to loop
    n := n + 1;
  end loop;
  return n;
end;
$$;

-- Whether a season is paused now: a pause that has started, or one whose
-- time has come that the timer hasn't started yet (it runs every minute).
create or replace function public.site_season_paused(p_season text)
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.site_season_pauses p
                  where p.season_key = p_season and p.ended_at is null
                    and (p.started_at is not null or p.starts_at <= now()
                         or (p.after_round is not null and public.site_round_phase(p.after_round) = 'finished')));
$$;

create or replace function public.site_round_paused(p_round uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select coalesce((select public.site_season_paused(r.season_key) from public.site_rounds r where r.id = p_round), false);
$$;

-- Moves a season's deadlines after p_from by p_days (earlier when
-- negative): a round not open by then, and every deadline still ahead.
create or replace function public.site_pause_move(p_season text, p_from timestamptz, p_days int)
returns void language plpgsql security definer set search_path = public as $$
begin
  if p_days = 0 then
    return;
  end if;
  perform public.site_quiet();
  update public.site_rounds set
    opens_at = case when opens_at >= p_from then public.site_add_days(opens_at, p_days) else opens_at end,
    closes_at = case when closed_at is null and closes_at > p_from then public.site_add_days(closes_at, p_days) else closes_at end,
    voting_closes_at = case when voting_closed_at is null and voting_closes_at > p_from
                            then public.site_add_days(voting_closes_at, p_days) else voting_closes_at end
   where season_key = p_season;
end;
$$;

-- The announcement a pause makes when it starts, changes or ends: from the
-- commissioner who set it, to the season's players.
create or replace function public.site_pause_announce(p_pause uuid, p_what text)
returns void language plpgsql security definer set search_path = public as $$
declare
  p public.site_season_pauses%rowtype;
  s_name text;
  body text;
  r public.site_rounds%rowtype;
  phase text;
begin
  select * into p from public.site_season_pauses where id = p_pause;
  select name into s_name from public.site_seasons where key = p.season_key;
  if p_what = 'ended' then
    body := s_name || ' is back on.';
    select * into r from public.site_rounds x
     where x.season_key = p.season_key and public.site_round_phase(x.id) in ('submitting', 'voting')
     order by x.opens_at limit 1;
    if found then
      phase := public.site_round_phase(r.id);
      body := body || ' ' || public.site_round_label(r.id)
              || case when phase = 'submitting' then ' takes tracks until ' || public.site_when(r.closes_at)
                      else ' takes votes until ' || public.site_when(r.voting_closes_at) end || '.';
    end if;
  else
    body := s_name || ' is paused '
            || case when p.resume_at is null then 'until the commissioners resume it'
                    else 'until ' || public.site_when(p.resume_at) end
            || '. Nothing can be submitted or voted on until then, and every deadline moves later by the pause.'
            || case when p_what = 'changed' then ' (The resume time changed.)' else '' end;
    if p.note <> '' then
      body := body || E'\n\n' || p.note;
    end if;
  end if;
  perform public.site_quiet();
  insert into public.site_announcements (body, created_by, season_key) values (left(body, 1000), p.created_by, p.season_key);
end;
$$;

-- Starts a pause at p_at: time stops there.
create or replace function public.site_pause_begin(p_pause uuid, p_at timestamptz, p_actor uuid)
returns void language plpgsql security definer set search_path = public as $$
declare
  p public.site_season_pauses%rowtype;
  h int;
begin
  select * into p from public.site_season_pauses where id = p_pause for update;
  if not found or p.started_at is not null or p.ended_at is not null then
    return;
  end if;
  h := case when p.resume_at is null then 365 else public.site_days_until(p_at, p.resume_at) end;
  update public.site_season_pauses set started_at = p_at, hold_days = h where id = p_pause;
  perform public.site_pause_move(p.season_key, p_at, h);
  perform public.site_pause_announce(p_pause, 'started');
  if p_actor is null then
    perform public.site_log('The scheduled pause of "' || (select name from public.site_seasons where key = p.season_key)
                            || '" started', p.season_key, null, null);
  end if;
end;
$$;

-- Ends a pause at p_at: deadlines settle at the pause's real length.
create or replace function public.site_pause_end(p_pause uuid, p_at timestamptz, p_actor uuid)
returns void language plpgsql security definer set search_path = public as $$
declare
  p public.site_season_pauses%rowtype;
  n int;
begin
  select * into p from public.site_season_pauses where id = p_pause for update;
  if not found or p.ended_at is not null or p.started_at is null then
    return;
  end if;
  n := public.site_days_until(p.started_at, greatest(p_at, p.started_at));
  perform public.site_pause_move(p.season_key, p.started_at, n - p.hold_days);
  update public.site_season_pauses set ended_at = greatest(p_at, p.started_at), hold_days = n where id = p_pause;
  perform public.site_pause_announce(p_pause, 'ended');
  if p_actor is null then
    perform public.site_log('"' || (select name from public.site_seasons where key = p.season_key)
                            || '" resumed at its set time', p.season_key, null, null);
  end if;
end;
$$;

-- ---------------------------------------------------------------- prompt rotation

-- Round N's winner writes Round N+2's prompt (Season 3's rule), in a
-- season that turns it on. A commissioner approves it before it shows.
alter table public.site_seasons add column if not exists prompt_rotation boolean not null default false;

-- One row per finished round in such a season: whose turn it gave and for
-- which round (status 'none' when there was nothing to give).
create table if not exists public.site_prompt_turns (
  id          uuid primary key default gen_random_uuid(),
  from_round  uuid not null unique references public.site_rounds (id) on delete cascade,
  round_id    uuid unique references public.site_rounds (id) on delete cascade,
  writers     text[] not null default '{}',
  status      text not null default 'waiting' check (status in ('waiting', 'sent', 'approved', 'none')),
  name        text not null default '' check (char_length(name) <= 120),
  prompt      text not null default '' check (char_length(prompt) <= 2000),
  sent_at     timestamptz,
  decided_at  timestamptz,
  decided_by  uuid references auth.users (id) on delete set null,
  created_at  timestamptz not null default now()
);
alter table public.site_prompt_turns enable row level security;
revoke all on table public.site_prompt_turns from anon, authenticated;

-- A finished round's winners: the owners of its top-scoring track (more
-- than one on a tie), by the points that count. None when nothing scored.
create or replace function public.site_round_winners(p_round uuid)
returns text[] language sql stable security definer set search_path = public as $$
  with t as (
    select m.competitor_id,
           case when r.nonvoters_keep_points
                     or exists (select 1 from public.site_votes v where v.round_id = p_round and v.user_id = o.user_id)
                then coalesce((select sum(v.points) from public.site_votes v where v.submission_id = s.id), 0)
                else coalesce((select sum(least(v.points, 0)) from public.site_votes v where v.submission_id = s.id), 0) end as pts
      from public.site_submissions s
      join public.site_rounds r on r.id = s.round_id
      join public.site_submission_owners o on o.submission_id = s.id
      join public.members m on m.user_id = o.user_id
     where s.round_id = p_round)
  select coalesce(array_agg(distinct t.competitor_id order by t.competitor_id), '{}')
    from t where t.pts > 0 and t.pts = (select max(pts) from t);
$$;

-- Gives out the turns for rounds that have finished since the last run.
create or replace function public.site_rotation_tick()
returns void language plpgsql security definer set search_path = public as $$
declare
  x record;
  target uuid;
  who text[];
  label text;
begin
  for x in select r.id, r.season_key, r.opens_at, r.name
             from public.site_rounds r join public.site_seasons s on s.key = r.season_key
            where s.prompt_rotation and public.site_round_phase(r.id) = 'finished'
              and not exists (select 1 from public.site_prompt_turns t where t.from_round = r.id) loop
    select y.id into target from public.site_rounds y
     where y.season_key = x.season_key and (y.opens_at, y.id) > (x.opens_at, x.id)
     order by y.opens_at, y.id offset 1 limit 1;
    who := public.site_round_winners(x.id);
    if target is null or cardinality(who) = 0 or public.site_round_phase(target) <> 'upcoming'
       or exists (select 1 from public.site_prompt_turns t where t.round_id = target) then
      insert into public.site_prompt_turns (from_round, round_id, writers, status) values (x.id, null, '{}', 'none');
      continue;
    end if;
    insert into public.site_prompt_turns (from_round, round_id, writers) values (x.id, target, who);
    label := public.site_round_public_name(target);
    insert into public.site_push_notices (user_id, kind, author, body)
    select m.user_id, 'rotation', 'PFML',
           'You won "' || x.name || '", so you write the prompt for ' || label
           || '. It opens ' || public.site_when((select opens_at from public.site_rounds where id = target))
           || '. Write it on Home.'
      from public.members m where m.competitor_id = any(who);
  end loop;
end;
$$;

-- The caller's turns to write a prompt, while the round hasn't opened.
create or replace function public.my_prompt_turns()
returns table (round_id uuid, round_label text, opens_at timestamptz, from_round_name text, status text,
               name text, prompt text, writers text[])
language sql stable security definer set search_path = public as $$
  select t.round_id, public.site_round_public_name(t.round_id), r.opens_at, f.name, t.status, t.name, t.prompt,
         array(select p.name from public.players p where p.competitor_id = any(t.writers) order by p.name)
    from public.site_prompt_turns t
    join public.site_rounds r on r.id = t.round_id
    join public.site_rounds f on f.id = t.from_round
    join public.members m on m.user_id = auth.uid()
   where m.competitor_id = any(t.writers) and t.status in ('waiting', 'sent')
     and public.site_round_phase(t.round_id) = 'upcoming'
   order by r.opens_at;
$$;

-- A writer sends their prompt for a commissioner to approve. Any writer of
-- a tied turn can, and send again to change it until it's approved.
create or replace function public.send_prompt_turn(p_round uuid, p_name text, p_prompt text)
returns void language plpgsql security definer set search_path = public as $$
declare
  t public.site_prompt_turns%rowtype;
  me text;
begin
  select competitor_id into me from public.members where user_id = auth.uid();
  select * into t from public.site_prompt_turns where round_id = p_round for update;
  if me is null or not found or not (me = any(t.writers)) then
    raise exception 'It isn''t your turn to write this round''s prompt.';
  end if;
  if t.status not in ('waiting', 'sent') or public.site_round_phase(p_round) <> 'upcoming' then
    raise exception 'This prompt can''t change any more.';
  end if;
  if char_length(btrim(coalesce(p_name, ''))) not between 1 and 120 then
    raise exception 'Give the round a name, up to 120 characters.';
  end if;
  if char_length(btrim(coalesce(p_prompt, ''))) not between 1 and 2000 then
    raise exception 'Write the prompt, up to 2000 characters.';
  end if;
  update public.site_prompt_turns set status = 'sent', name = btrim(p_name), prompt = btrim(p_prompt), sent_at = now()
   where id = t.id;
  perform public.site_notify_commissioners('rotation', public.site_author(auth.uid()),
    'Sent the prompt for ' || public.site_round_public_name(p_round) || ': "' || btrim(p_name)
    || '". Approve it on the Commissioner page.');
end;
$$;

-- The commissioners' list of turns not settled yet.
create or replace function public.site_prompt_turns_list()
returns table (round_id uuid, round_label text, opens_at timestamptz, from_round_name text, status text,
               name text, prompt text, writers text[], sent_at timestamptz)
language plpgsql stable security definer set search_path = public as $$
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can see prompt turns.';
  end if;
  return query
    select t.round_id, public.site_round_public_name(t.round_id), r.opens_at, f.name, t.status, t.name, t.prompt,
           array(select p.name from public.players p where p.competitor_id = any(t.writers) order by p.name), t.sent_at
      from public.site_prompt_turns t
      join public.site_rounds r on r.id = t.round_id
      join public.site_rounds f on f.id = t.from_round
     where t.status in ('waiting', 'sent') and public.site_round_phase(t.round_id) = 'upcoming'
     order by r.opens_at;
end;
$$;

-- A commissioner approves a sent prompt (edited if they like): it becomes
-- the round's name and prompt, and its writers the round's prompters. Or
-- drops the turn (p_name null), to write the prompt some other way.
create or replace function public.decide_prompt_turn(p_round uuid, p_name text, p_prompt text)
returns void language plpgsql security definer set search_path = public as $$
declare
  t public.site_prompt_turns%rowtype;
  label text;
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can approve a prompt.';
  end if;
  select * into t from public.site_prompt_turns where round_id = p_round for update;
  if not found or t.status not in ('waiting', 'sent') then
    raise exception 'There''s no prompt waiting for this round.';
  end if;
  label := public.site_round_public_name(p_round);
  if p_name is null then
    update public.site_prompt_turns set status = 'none', decided_at = now(), decided_by = auth.uid() where id = t.id;
    perform public.site_log('Dropped the prompt turn for ' || label, null, p_round, auth.uid());
    return;
  end if;
  if public.site_round_phase(p_round) <> 'upcoming' then
    raise exception 'This round has opened, so its prompt is set.';
  end if;
  if char_length(btrim(p_name)) not between 1 and 120 or char_length(btrim(coalesce(p_prompt, ''))) not between 1 and 2000 then
    raise exception 'A round needs a name (up to 120 characters) and a prompt (up to 2000).';
  end if;
  perform public.site_quiet();
  update public.site_rounds set name = btrim(p_name), prompt = btrim(p_prompt) where id = p_round;
  perform public.site_round_people_apply(p_round, null, to_jsonb(t.writers));
  update public.site_prompt_turns set status = 'approved', name = btrim(p_name), prompt = btrim(p_prompt),
         decided_at = now(), decided_by = auth.uid() where id = t.id;
  perform public.site_log('Approved the prompt for ' || label || ': "' || btrim(p_name) || '"', null, p_round, auth.uid());
  insert into public.site_push_notices (user_id, kind, author, body)
  select m.user_id, 'rotation', public.site_author(auth.uid()),
         'Your prompt for ' || label || ' is in: "' || btrim(p_name) || '".'
    from public.members m where m.competitor_id = any(t.writers);
end;
$$;

-- Turns rotation on or off for a season.
create or replace function public.set_site_season_rotation(p_key text, p_on boolean)
returns void language plpgsql security definer set search_path = public as $$
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can change a season.';
  end if;
  if p_on is null or not exists (select 1 from public.site_seasons where key = p_key) then
    raise exception 'That season doesn''t exist.';
  end if;
  -- rounds that finished before it was on don't hand out turns
  if p_on then
    insert into public.site_prompt_turns (from_round, round_id, writers, status)
    select r.id, null, '{}', 'none' from public.site_rounds r
     where r.season_key = p_key and public.site_round_phase(r.id) = 'finished'
    on conflict (from_round) do nothing;
  end if;
  update public.site_seasons set prompt_rotation = p_on where key = p_key;
end;
$$;

-- ---------------------------------------------------------------- the timer

-- Run every minute (pg_cron, below) and by the pause functions: starts
-- pauses whose time has come, ends those due to end, and hands out prompt
-- turns. Safe to run twice at once.
create or replace function public.site_pause_tick()
returns void language plpgsql security definer set search_path = public as $$
declare
  p record;
  at timestamptz;
begin
  perform pg_advisory_xact_lock(hashtext('pfml.site_pause_tick'));
  for p in select x.id, x.starts_at, x.after_round from public.site_season_pauses x
            where x.ended_at is null and x.started_at is null
              and (x.starts_at <= now()
                   or (x.after_round is not null and public.site_round_phase(x.after_round) = 'finished')) loop
    if p.starts_at is not null then
      at := p.starts_at;
    else
      select coalesce(r.voting_closed_at, r.voting_closes_at) into at from public.site_rounds r where r.id = p.after_round;
    end if;
    perform public.site_pause_begin(p.id, least(coalesce(at, now()), now()), null);
  end loop;
  for p in select x.id, x.resume_at from public.site_season_pauses x
            where x.ended_at is null and x.started_at is not null and x.resume_at <= now() loop
    perform public.site_pause_end(p.id, p.resume_at, null);
  end loop;
  perform public.site_rotation_tick();
end;
$$;

-- ---------------------------------------------------------------- what commissioners call

-- Pauses a season: now (both null), at p_starts_at, or once p_after_round's
-- voting closes; until p_resume_at, or (null) until resumed.
create or replace function public.pause_season(p_key text, p_starts_at timestamptz, p_after_round uuid,
                                               p_resume_at timestamptz, p_note text)
returns uuid language plpgsql security definer set search_path = public as $$
declare
  s public.site_seasons%rowtype;
  ar public.site_rounds%rowtype;
  begins timestamptz;
  pid uuid;
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can pause a season.';
  end if;
  select * into s from public.site_seasons where key = p_key;
  if not found then
    raise exception 'That season doesn''t exist.';
  end if;
  perform public.site_pause_tick();
  if exists (select 1 from public.site_season_pauses where season_key = p_key and ended_at is null) then
    raise exception 'This season already has a pause. Change or end that one first.';
  end if;
  if p_starts_at is not null and p_after_round is not null then
    raise exception 'Pick one: a time, or after a round''s voting.';
  end if;
  if char_length(coalesce(p_note, '')) > 300 then
    raise exception 'The note can be at most 300 characters.';
  end if;
  if p_after_round is not null then
    select * into ar from public.site_rounds where id = p_after_round;
    if not found or ar.season_key <> p_key then
      raise exception 'That round isn''t in this season.';
    end if;
    if public.site_round_phase(ar.id) = 'finished' then
      raise exception 'That round''s voting has already closed.';
    end if;
    begins := ar.voting_closes_at;
  else
    begins := greatest(coalesce(p_starts_at, now()), now());
    if begins > now() + interval '365 days' then
      raise exception 'A pause can be scheduled up to a year ahead.';
    end if;
  end if;
  if p_resume_at is not null and (p_resume_at <= begins or p_resume_at <= now() + interval '1 minute') then
    raise exception 'The league has to resume after the pause starts.';
  end if;
  if p_resume_at is not null and p_resume_at > begins + interval '365 days' then
    raise exception 'A pause can last up to a year.';
  end if;
  insert into public.site_season_pauses (season_key, starts_at, after_round, resume_at, note, created_by)
  values (p_key, case when p_after_round is null then begins end, p_after_round, p_resume_at, btrim(coalesce(p_note, '')), auth.uid())
  returning id into pid;
  if p_after_round is null and begins <= now() then
    perform public.site_log('Paused "' || s.name || '" '
                            || case when p_resume_at is null then 'until resumed' else 'until ' || public.site_when(p_resume_at) end,
                            p_key, null, auth.uid());
    perform public.site_pause_begin(pid, now(), auth.uid());
  else
    perform public.site_log('Scheduled a pause of "' || s.name || '" '
                            || case when p_after_round is null then 'from ' || public.site_when(begins)
                                    else 'after "' || ar.name || '" finishes voting' end
                            || case when p_resume_at is null then ', until resumed' else ', until ' || public.site_when(p_resume_at) end,
                            p_key, null, auth.uid());
  end if;
  return pid;
end;
$$;

-- Changes when a season's pause ends (null: until resumed by hand).
create or replace function public.set_pause_resume(p_key text, p_resume_at timestamptz)
returns void language plpgsql security definer set search_path = public as $$
declare
  p public.site_season_pauses%rowtype;
  h int;
  begins timestamptz;
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can change a pause.';
  end if;
  perform public.site_pause_tick();
  select * into p from public.site_season_pauses where season_key = p_key and ended_at is null for update;
  if not found then
    raise exception 'This season isn''t paused.';
  end if;
  begins := coalesce(p.started_at, p.starts_at,
                     (select voting_closes_at from public.site_rounds where id = p.after_round), now());
  if p_resume_at is not null and (p_resume_at <= greatest(begins, now() + interval '1 minute')) then
    raise exception 'The league has to resume after the pause starts, and in the future.';
  end if;
  if p_resume_at is not null and p_resume_at > begins + interval '365 days' then
    raise exception 'A pause can last up to a year.';
  end if;
  update public.site_season_pauses set resume_at = p_resume_at where id = p.id;
  if p.started_at is not null then
    h := case when p_resume_at is null then 365 else public.site_days_until(p.started_at, p_resume_at) end;
    perform public.site_pause_move(p.season_key, p.started_at, h - p.hold_days);
    update public.site_season_pauses set hold_days = h where id = p.id;
    perform public.site_pause_announce(p.id, 'changed');
  end if;
  perform public.site_log('Set "' || (select name from public.site_seasons where key = p_key) || '" to resume '
                          || case when p_resume_at is null then 'when resumed by hand' else public.site_when(p_resume_at) end,
                          p_key, null, auth.uid());
end;
$$;

-- Resumes a paused season now, or cancels a pause that hasn't started.
create or replace function public.resume_season(p_key text)
returns void language plpgsql security definer set search_path = public as $$
declare
  p public.site_season_pauses%rowtype;
  s_name text;
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can resume a season.';
  end if;
  perform public.site_pause_tick();
  select * into p from public.site_season_pauses where season_key = p_key and ended_at is null for update;
  if not found then
    raise exception 'This season isn''t paused.';
  end if;
  select name into s_name from public.site_seasons where key = p_key;
  if p.started_at is null then
    delete from public.site_season_pauses where id = p.id;
    perform public.site_log('Cancelled the scheduled pause of "' || s_name || '"', p_key, null, auth.uid());
    return;
  end if;
  perform public.site_log('Resumed "' || s_name || '"', p_key, null, auth.uid());
  perform public.site_pause_end(p.id, now(), auth.uid());
end;
$$;

-- The pauses members see (Home's strip): each season's open pause, started
-- or not.
create or replace function public.site_pauses()
returns table (season_key text, season_name text, state text, starts_at timestamptz, after_round_label text,
               resume_at timestamptz, started_at timestamptz, note text)
language sql stable security definer set search_path = public as $$
  select p.season_key, s.name,
         case when public.site_season_paused(p.season_key) then 'paused' else 'scheduled' end,
         coalesce(p.starts_at, (select r.voting_closes_at from public.site_rounds r where r.id = p.after_round)),
         case when p.after_round is not null then public.site_round_label(p.after_round) end,
         p.resume_at, p.started_at, p.note
    from public.site_season_pauses p
    join public.site_seasons s on s.key = p.season_key
   where p.ended_at is null and public.is_member()
   order by s.key;
$$;

-- More time for the round that's open: the deadline it's working to
-- moves out by p_hours, or p_days on the league's clock, and so does
-- everything after it in the season.
create or replace function public.extend_site_round(p_round uuid, p_hours int, p_days int)
returns timestamptz language plpgsql security definer set search_path = public as $$
declare
  r public.site_rounds%rowtype;
  phase text;
  later timestamptz;
  moved timestamptz;
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can move a deadline.';
  end if;
  if coalesce(p_hours, 0) < 0 or coalesce(p_days, 0) < 0 or (coalesce(p_hours, 0) = 0) = (coalesce(p_days, 0) = 0)
     or p_hours > 72 or p_days > 14 then
    raise exception 'Add 1 to 72 hours, or 1 to 14 days.';
  end if;
  select * into r from public.site_rounds where id = p_round for update;
  if not found then
    raise exception 'That round doesn''t exist.';
  end if;
  if public.site_round_paused(p_round) then
    raise exception 'The league is paused. Resume it before changing a deadline.';
  end if;
  phase := public.site_round_phase(p_round);
  if phase not in ('submitting', 'voting') then
    raise exception 'Only a round taking tracks or votes has a deadline to move.';
  end if;
  later := case when phase = 'submitting' then r.closes_at else r.voting_closes_at end;
  perform public.site_quiet();
  update public.site_rounds x set
    opens_at = case when x.id <> p_round and x.opens_at >= later
                    then case when p_days > 0 then public.site_add_days(x.opens_at, p_days) else x.opens_at + make_interval(hours => p_hours) end
                    else x.opens_at end,
    closes_at = case when x.closed_at is null and x.closes_at >= later
                     then case when p_days > 0 then public.site_add_days(x.closes_at, p_days) else x.closes_at + make_interval(hours => p_hours) end
                     else x.closes_at end,
    voting_closes_at = case when x.voting_closed_at is null and x.voting_closes_at >= later
                            then case when p_days > 0 then public.site_add_days(x.voting_closes_at, p_days)
                                      else x.voting_closes_at + make_interval(hours => p_hours) end
                            else x.voting_closes_at end
   where x.id = p_round or (r.season_key is not null and x.season_key = r.season_key
                            and exists (select 1 from public.site_seasons s where s.key = r.season_key));
  select case when phase = 'submitting' then closes_at else voting_closes_at end into moved from public.site_rounds where id = p_round;
  perform public.site_log('Gave "' || r.name || '" '
                          || case when p_days > 0 then p_days || case when p_days = 1 then ' more day' else ' more days' end
                                  else p_hours || case when p_hours = 1 then ' more hour' else ' more hours' end end
                          || ' to ' || case when phase = 'submitting' then 'submit' else 'vote' end
                          || ', until ' || public.site_when(moved), r.season_key, p_round, auth.uid());
  return moved;
end;
$$;

-- Everyone playing a round and where they stand, for the Now panel: their
-- role, whether they've joined the site, how many tracks they've sent (never
-- which), whether they've voted, and whether they're sitting it out.
create or replace function public.site_round_status(p_round uuid)
returns table (competitor_id text, name text, role text, joined boolean, tracks int, voted boolean, sitting text)
language plpgsql stable security definer set search_path = public as $$
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can see who''s in.';
  end if;
  return query
    select p.competitor_id, pl.name, public.site_round_role(p_round, p.competitor_id), m.user_id is not null,
           (select count(*)::int from public.site_submission_owners o where o.round_id = p_round and o.user_id = m.user_id),
           exists (select 1 from public.site_votes v where v.round_id = p_round and v.user_id = m.user_id),
           (select x.status from public.site_round_sitouts x where x.round_id = p_round and x.competitor_id = p.competitor_id)
      from public.site_rounds r
      join public.site_season_players p on p.season_key = r.season_key
      join public.players pl on pl.competitor_id = p.competitor_id
      left join public.members m on m.competitor_id = p.competitor_id
     where r.id = p_round
     order by pl.name;
end;
$$;

-- Who a round is still waiting on, by member: DJs short of tracks while it
-- takes them, and while it takes votes, everyone with a track and every
-- Spectator who hasn't voted. Never anyone sitting it out.
create or replace function public.site_round_waiting(p_round uuid)
returns table (competitor_id text, user_id uuid)
language sql stable security definer set search_path = public as $$
  select p.competitor_id, m.user_id
    from public.site_rounds r
    join public.site_season_players p on p.season_key = r.season_key
    join public.members m on m.competitor_id = p.competitor_id
   where r.id = p_round and not public.site_sitting_out(p_round, p.competitor_id)
     and case public.site_round_phase(p_round)
           when 'submitting' then public.site_round_role(p_round, p.competitor_id) = 'dj'
             and (select count(*) from public.site_submission_owners o where o.round_id = p_round and o.user_id = m.user_id)
                 < r.songs_per_round
           when 'voting' then (public.site_round_role(p_round, p.competitor_id) = 'spectator'
                               or exists (select 1 from public.site_submission_owners o where o.round_id = p_round and o.user_id = m.user_id))
             and not exists (select 1 from public.site_votes v where v.round_id = p_round and v.user_id = m.user_id)
           else false end;
$$;

-- Records when a round was nudged, for the wait between nudges.
create table if not exists public.site_nudges (
  id       bigint generated always as identity primary key,
  round_id uuid not null references public.site_rounds (id) on delete cascade,
  phase    text not null check (phase in ('submitting', 'voting')),
  at       timestamptz not null default now(),
  by_user  uuid references auth.users (id) on delete set null,
  sent     int not null default 0
);
create index if not exists site_nudges_round on public.site_nudges (round_id, at desc);
alter table public.site_nudges enable row level security;
revoke all on table public.site_nudges from anon, authenticated;

-- Pushes "still waiting on you" to everyone the round is waiting on, at
-- most once every 6 hours a round. Returns how many it went to.
create or replace function public.nudge_round(p_round uuid)
returns int language plpgsql security definer set search_path = public as $$
declare
  r public.site_rounds%rowtype;
  phase text;
  last timestamptz;
  n int;
  label text;
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can nudge.';
  end if;
  select * into r from public.site_rounds where id = p_round;
  if not found or not exists (select 1 from public.site_seasons s where s.key = r.season_key) then
    raise exception 'Only a round in a season set up on the site can be nudged.';
  end if;
  if public.site_round_paused(p_round) then
    raise exception 'The league is paused, so there''s nothing to nudge about.';
  end if;
  phase := public.site_round_phase(p_round);
  if phase not in ('submitting', 'voting') then
    raise exception 'This round isn''t taking tracks or votes.';
  end if;
  select max(x.at) into last from public.site_nudges x where x.round_id = p_round;
  if last > now() - interval '6 hours' then
    raise exception 'This round was nudged less than 6 hours ago. You can nudge again from %.', public.site_when(last + interval '6 hours');
  end if;
  label := public.site_round_label(p_round);
  insert into public.site_push_notices (user_id, kind, author, body)
  select w.user_id, case when phase = 'submitting' then 'nudge_submit' else 'nudge_vote' end, public.site_author(auth.uid()),
         case when phase = 'submitting'
              then 'Still waiting on your track for ' || label || '. Submissions close ' || public.site_when(r.closes_at) || '.'
              else 'Still waiting on your vote in ' || label || '. Voting closes ' || public.site_when(r.voting_closes_at) || '.' end
    from public.site_round_waiting(p_round) w;
  get diagnostics n = row_count;
  if n = 0 then
    raise exception 'Nobody to nudge: everyone''s in.';
  end if;
  insert into public.site_nudges (round_id, phase, by_user, sent) values (p_round, phase, auth.uid(), n);
  perform public.site_log('Nudged ' || n || case when n = 1 then ' player' else ' players' end
                          || case when phase = 'submitting' then ' to send tracks to "' else ' to vote in "' end || r.name || '"',
                          r.season_key, p_round, auth.uid());
  return n;
end;
$$;

-- When a round was last nudged (for the Now panel's button).
create or replace function public.site_round_last_nudge(p_round uuid)
returns timestamptz language plpgsql stable security definer set search_path = public as $$
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can see nudges.';
  end if;
  return (select max(x.at) from public.site_nudges x where x.round_id = p_round);
end;
$$;

-- A player asks to sit a round out (p_on), or takes the ask back (or the
-- yes, while it still matters). A DJ can until submissions close, with no
-- track in; a Spectator until voting does.
create or replace function public.ask_sit_out(p_round uuid, p_on boolean)
returns text language plpgsql security definer set search_path = public as $$
declare
  me text;
  r public.site_rounds%rowtype;
  phase text;
  role text;
begin
  select competitor_id into me from public.members where user_id = auth.uid();
  if me is null then
    raise exception 'Only league members can sit a round out.';
  end if;
  select * into r from public.site_rounds where id = p_round;
  if not found or not exists (select 1 from public.site_season_players p where p.season_key = r.season_key and p.competitor_id = me) then
    raise exception 'You''re not playing in this round''s season.';
  end if;
  phase := public.site_round_phase(p_round);
  role := public.site_round_role(p_round, me);
  if phase not in ('upcoming', 'submitting') and not (role = 'spectator' and phase = 'voting') then
    raise exception 'It''s too late to change that for this round.';
  end if;
  if not p_on then
    delete from public.site_round_sitouts where round_id = p_round and competitor_id = me;
    return null;
  end if;
  if exists (select 1 from public.site_submission_owners o where o.round_id = p_round and o.user_id = auth.uid()) then
    raise exception 'Take your track out first, then ask to sit the round out.';
  end if;
  if exists (select 1 from public.site_round_sitouts where round_id = p_round and competitor_id = me) then
    return (select status from public.site_round_sitouts where round_id = p_round and competitor_id = me);
  end if;
  insert into public.site_round_sitouts (round_id, competitor_id) values (p_round, me);
  perform public.site_notify_commissioners('sitout', public.site_author(auth.uid()),
    'Asked to sit out ' || public.site_round_label(p_round) || '. Say yes or no on the Commissioner page.');
  return 'asked';
end;
$$;

-- A commissioner says yes (or sets it without an ask) or no.
create or replace function public.decide_sit_out(p_round uuid, p_competitor text, p_approve boolean)
returns void language plpgsql security definer set search_path = public as $$
declare
  r public.site_rounds%rowtype;
  who uuid;
  had text;
  pname text;
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can answer that.';
  end if;
  select * into r from public.site_rounds where id = p_round;
  if not found or not exists (select 1 from public.site_season_players p where p.season_key = r.season_key and p.competitor_id = p_competitor) then
    raise exception 'That player isn''t in this round''s season.';
  end if;
  select user_id into who from public.members where competitor_id = p_competitor;
  select name into pname from public.players where competitor_id = p_competitor;
  select status into had from public.site_round_sitouts where round_id = p_round and competitor_id = p_competitor;
  if p_approve then
    if public.site_round_phase(p_round) not in ('upcoming', 'submitting', 'voting') then
      raise exception 'This round has finished.';
    end if;
    if exists (select 1 from public.site_submission_owners o where o.round_id = p_round and o.user_id = who) then
      raise exception '% has a track in this round, so can''t sit it out.', pname;
    end if;
    insert into public.site_round_sitouts (round_id, competitor_id, status, decided_at, decided_by)
    values (p_round, p_competitor, 'approved', now(), auth.uid())
    on conflict (round_id, competitor_id) do update set status = 'approved', decided_at = now(), decided_by = auth.uid();
    perform public.site_log(pname || ' sits out "' || r.name || '"', r.season_key, p_round, auth.uid());
    perform public.site_notify(who, 'sitout', public.site_author(auth.uid()),
      'You''re sitting out ' || public.site_round_label(p_round) || '. No track needed, and no reminders for it.');
    perform public.site_round_finish_early(p_round);
  else
    delete from public.site_round_sitouts where round_id = p_round and competitor_id = p_competitor;
    if had is not null then
      perform public.site_log(case when had = 'asked' then 'Said no to ' || pname || ' sitting out "' else 'Put ' || pname || ' back in "' end
                              || r.name || '"', r.season_key, p_round, auth.uid());
      perform public.site_notify(who, 'sitout', public.site_author(auth.uid()),
        case when had = 'asked' then 'You''re playing ' || public.site_round_label(p_round) || ' after all: a commissioner said no to sitting it out.'
             else 'You''re back in ' || public.site_round_label(p_round) || '.' end);
    end if;
  end if;
end;
$$;

-- A round's own days, while it hasn't opened (null: the season's).
create or replace function public.set_site_round_days(p_round uuid, p_submit int, p_vote int)
returns void language plpgsql security definer set search_path = public as $$
declare
  r public.site_rounds%rowtype;
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can change a round.';
  end if;
  select * into r from public.site_rounds where id = p_round;
  if not found or not exists (select 1 from public.site_seasons s where s.key = r.season_key) then
    raise exception 'That round isn''t in a season set up on the site.';
  end if;
  if public.site_round_phase(p_round) <> 'upcoming' then
    raise exception 'Only a round that hasn''t opened can change its days. Use the Now panel for the open round.';
  end if;
  if (p_submit is not null and p_submit not between 1 and 14) or (p_vote is not null and p_vote not between 1 and 14) then
    raise exception 'A round takes 1 to 14 days to submit and 1 to 14 to vote.';
  end if;
  update public.site_rounds set submit_days = p_submit, vote_days = p_vote where id = p_round;
  perform public.site_season_reschedule(r.season_key);
  perform public.site_log('Set "' || r.name || '" to '
                          || coalesce(p_submit::text, 'the season''s') || ' days to submit and '
                          || coalesce(p_vote::text, 'the season''s') || ' to vote', r.season_key, p_round, auth.uid());
end;
$$;

-- An invite link for a player who hasn't joined (the admin only): the
-- unused one they already have, or a new one. The page builds
-- https://pfml.fun/?invite=<code> from it.
create or replace function public.create_invite(p_competitor text)
returns text language plpgsql security definer set search_path = public as $$
declare
  code_ text;
  pname text;
begin
  if not public.is_admin() then
    raise exception 'Only the admin can make invite links.';
  end if;
  select name into pname from public.players where competitor_id = p_competitor;
  if pname is null then
    raise exception 'That player doesn''t exist.';
  end if;
  if exists (select 1 from public.members where competitor_id = p_competitor) then
    raise exception '% has already joined.', pname;
  end if;
  select i.code into code_ from public.invites i
   where i.competitor_id = p_competitor and i.claimed_by is null order by i.created_at desc limit 1;
  if code_ is null then
    code_ := replace(gen_random_uuid()::text, '-', '');
    insert into public.invites (code, competitor_id) values (code_, p_competitor);
    perform public.site_log('Made an invite link for ' || pname, null, null, auth.uid());
  end if;
  return code_;
end;
$$;

-- ---------------------------------------------------------------- announcements, scheduled and to one season

alter table public.site_announcements add column if not exists send_at timestamptz;
alter table public.site_announcements add column if not exists season_key text references public.site_seasons (key) on delete cascade;
alter table public.site_announcements add column if not exists edited_at timestamptz;

-- Members see an announcement once its time has come, and one meant for a
-- season only if they play in it. Commissioners see them all.
drop policy if exists "members read announcements" on public.site_announcements;
create policy "members read announcements" on public.site_announcements
  for select to authenticated using (
    public.is_member() and (
      public.is_commissioner()
      or ((send_at is null or send_at <= now())
          and (season_key is null
               or exists (select 1 from public.site_season_players p join public.members m on m.competitor_id = p.competitor_id
                           where p.season_key = site_announcements.season_key and m.user_id = auth.uid())))));

create or replace function public.site_announcements_logged()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  perform public.site_log_by_commissioner(
    case tg_op when 'INSERT' then case when new.send_at is not null then 'Scheduled an announcement for ' || public.site_when(new.send_at)
                                       else 'Posted an announcement' end
               when 'UPDATE' then 'Edited an announcement'
               else 'Took down an announcement' end, coalesce(new.season_key, old.season_key), null);
  return null;
end;
$$;
drop trigger if exists site_announcements_logged on public.site_announcements;
create trigger site_announcements_logged after insert or update of body, send_at or delete on public.site_announcements
  for each row execute function public.site_announcements_logged();

drop function if exists public.post_announcement(text);
create or replace function public.post_announcement(p_body text, p_send_at timestamptz default null, p_season text default null)
returns uuid language plpgsql security definer set search_path = public as $$
declare
  aid uuid;
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can post an announcement.';
  end if;
  if char_length(btrim(coalesce(p_body, ''))) not between 1 and 1000 then
    raise exception 'An announcement is 1 to 1000 characters.';
  end if;
  if p_send_at is not null and (p_send_at <= now() or p_send_at > now() + interval '60 days') then
    raise exception 'Schedule it for later, up to 60 days ahead.';
  end if;
  if p_season is not null and not exists (select 1 from public.site_seasons where key = p_season) then
    raise exception 'That season doesn''t exist.';
  end if;
  insert into public.site_announcements (body, created_by, send_at, season_key)
  values (btrim(p_body), auth.uid(), p_send_at, p_season) returning id into aid;
  return aid;
end;
$$;

-- Changes an announcement's words, and its time while it hasn't gone out.
-- One that has gone out isn't pushed again.
create or replace function public.edit_announcement(p_id uuid, p_body text, p_send_at timestamptz)
returns void language plpgsql security definer set search_path = public as $$
declare
  a public.site_announcements%rowtype;
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can edit an announcement.';
  end if;
  select * into a from public.site_announcements where id = p_id for update;
  if not found then
    raise exception 'That announcement is gone.';
  end if;
  if char_length(btrim(coalesce(p_body, ''))) not between 1 and 1000 then
    raise exception 'An announcement is 1 to 1000 characters.';
  end if;
  if a.pushed_at is not null or coalesce(a.send_at, a.created_at) <= now() then
    if p_send_at is distinct from a.send_at then
      raise exception 'It has gone out already, so only its words can change.';
    end if;
  elsif p_send_at is not null and (p_send_at <= now() or p_send_at > now() + interval '60 days') then
    raise exception 'Schedule it for later, up to 60 days ahead.';
  end if;
  update public.site_announcements set body = btrim(p_body), send_at = p_send_at,
         edited_at = case when coalesce(a.send_at, a.created_at) <= now() then now() else edited_at end
   where id = p_id;
end;
$$;

-- For the sender: announcements whose time has come (in the last day) and
-- not pushed yet, to every member who wants them (a season's only to its
-- players and the commissioners), and the one-member notices; each marked
-- pushed in the same step, so none goes twice.
create or replace function public.announcements_claim()
returns table (announcement_id uuid, body text, author text, user_id uuid, subscriptions jsonb)
language plpgsql security definer set search_path = public as $$
#variable_conflict use_column
begin
  perform pg_advisory_xact_lock(hashtext('pfml.announcements_claim'));
  return query
  with fresh as (
    update public.site_announcements a set pushed_at = now()
     where a.pushed_at is null and coalesce(a.send_at, a.created_at) <= now()
       and coalesce(a.send_at, a.created_at) > now() - interval '1 day'
    returning a.id, a.body, a.created_by, a.season_key),
  notes as (
    update public.site_push_notices n set pushed_at = now()
     where n.pushed_at is null and n.created_at > now() - interval '1 day'
    returning n.id, n.body, n.author, n.user_id, n.kind)
  select f.id, f.body,
         coalesce((select p.name from public.members am join public.players p on p.competitor_id = am.competitor_id
                    where am.user_id = f.created_by), 'A commissioner'),
         m.user_id,
         (select coalesce(jsonb_agg(jsonb_build_object('endpoint', s.endpoint, 'p256dh', s.p256dh, 'auth', s.auth)), '[]'::jsonb)
            from public.push_subscriptions s where s.user_id = m.user_id)
    from fresh f cross join public.members m
   where exists (select 1 from public.push_subscriptions s where s.user_id = m.user_id)
     and coalesce((select rs.announcements from public.reminder_settings rs where rs.user_id = m.user_id), true)
     and (f.season_key is null or m.role in ('commissioner', 'admin')
          or exists (select 1 from public.site_season_players sp where sp.season_key = f.season_key and sp.competitor_id = m.competitor_id))
  union all
  select n.id, n.body, n.author, n.user_id,
         (select coalesce(jsonb_agg(jsonb_build_object('endpoint', s.endpoint, 'p256dh', s.p256dh, 'auth', s.auth)), '[]'::jsonb)
            from public.push_subscriptions s where s.user_id = n.user_id)
    from notes n
   where exists (select 1 from public.push_subscriptions s where s.user_id = n.user_id)
     and coalesce((select case n.kind when 'nudge_submit' then rs.round_open when 'nudge_vote' then rs.voting else rs.announcements end
                     from public.reminder_settings rs where rs.user_id = n.user_id), true);
end;
$$;

-- ---------------------------------------------------------------- the season's clock, pause-aware

-- No track or ballot goes in, out or changes while a season is paused, by
-- whatever function (scripts and the SQL Editor, signed in as nobody, are
-- left alone). And a player sitting a round out sends no track to it.
create or replace function public.site_writes_allowed()
returns trigger language plpgsql security definer set search_path = public as $$
declare
  rid uuid;
begin
  if tg_op = 'DELETE' then rid := old.round_id; else rid := new.round_id; end if;
  if auth.uid() is not null and public.site_round_paused(rid) then
    raise exception 'The league is paused, so tracks and votes can''t go in until it resumes.';
  end if;
  if tg_op = 'DELETE' then return old; end if;
  return new;
end;
$$;
drop trigger if exists site_submissions_paused on public.site_submissions;
create trigger site_submissions_paused before insert or update or delete on public.site_submissions
  for each row execute function public.site_writes_allowed();
drop trigger if exists site_votes_paused on public.site_votes;
create trigger site_votes_paused before insert or update or delete on public.site_votes
  for each row execute function public.site_writes_allowed();

create or replace function public.site_owner_not_sitting_out()
returns trigger language plpgsql security definer set search_path = public as $$
declare
  me text;
begin
  select competitor_id into me from public.members where user_id = new.user_id;
  if public.site_sitting_out(new.round_id, me) then
    raise exception 'You''re sitting this round out. Take that back on the Submit page first.';
  end if;
  -- sending a track takes back an ask that hasn't been answered
  delete from public.site_round_sitouts where round_id = new.round_id and competitor_id = me and status = 'asked';
  return new;
end;
$$;
drop trigger if exists site_owner_not_sitting_out on public.site_submission_owners;
create trigger site_owner_not_sitting_out before insert on public.site_submission_owners
  for each row execute function public.site_owner_not_sitting_out();

-- The times guard, as before, and now: nobody signed in moves a deadline
-- while the season is paused.
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

  if (new.opens_at, new.closes_at, new.closed_at, new.voting_closes_at, new.voting_closed_at)
     is distinct from (old.opens_at, old.closes_at, old.closed_at, old.voting_closes_at, old.voting_closed_at)
     and public.site_season_paused(old.season_key) then
    raise exception 'The league is paused. Resume it before changing a deadline.';
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

-- Lays out a season's rounds that haven't opened, as before, and now: each
-- with its own days when it has them, and, while the season is paused,
-- none opening before the pause's held end.
create or replace function public.site_season_reschedule(p_season text)
returns void language plpgsql security definer set search_path = public as $$
declare
  s public.site_seasons%rowtype;
  r record;
  prev_vote timestamptz;
  opens timestamptz;
  closes timestamptz;
  held timestamptz;
begin
  select * into s from public.site_seasons where key = p_season;
  if not found then return; end if;
  perform public.site_quiet();
  select public.site_add_days(p.started_at, p.hold_days) into held from public.site_season_pauses p
   where p.season_key = p_season and p.ended_at is null and p.started_at is not null;
  select x.voting_closes_at into prev_vote from public.site_rounds x
   where x.season_key = p_season and x.opens_at <= now() order by x.opens_at desc limit 1;
  for r in select x.id, x.closes_at, coalesce(x.submit_days, s.submit_days) as sd, coalesce(x.vote_days, s.vote_days) as vd
             from public.site_rounds x
            where x.season_key = p_season and x.opens_at > now() order by x.opens_at, x.created_at, x.id loop
    if prev_vote is null then
      closes := r.closes_at;
      opens := greatest(now(), public.site_add_days(closes, -r.sd));
    else
      opens := greatest(now(), prev_vote, held);
      closes := public.site_add_days(opens, r.sd);
    end if;
    prev_vote := public.site_add_days(closes, r.vd);
    update public.site_rounds set opens_at = opens, closes_at = closes, voting_closes_at = prev_vote where id = r.id;
  end loop;
end;
$$;

-- Speedy's shift, as before, made quietly.
create or replace function public.site_season_shift(p_season text, p_by interval)
returns void language plpgsql security definer set search_path = public as $$
begin
  perform public.site_quiet();
  update public.site_rounds
     set opens_at = greatest(now(), opens_at - p_by), closes_at = closes_at - p_by, voting_closes_at = voting_closes_at - p_by
   where season_key = p_season and opens_at > now();
end;
$$;

-- Accelerated and Speedy, as before, and now: never while the season is
-- paused, and never waiting on someone sitting the round out.
create or replace function public.site_round_finish_early(p_round uuid)
returns void language plpgsql security definer set search_path = public as $$
declare
  r public.site_rounds%rowtype;
  s public.site_seasons%rowtype;
  saved interval;
begin
  select * into r from public.site_rounds where id = p_round for update;
  select * into s from public.site_seasons where key = r.season_key;
  if not found or s.timing = 'steady' or public.site_season_paused(s.key) then return; end if;
  perform public.site_quiet();
  if public.site_round_phase(p_round) = 'submitting' then
    if not exists (select 1 from public.site_season_players p join public.members m on m.competitor_id = p.competitor_id
                    where p.season_key = s.key and public.site_round_role(p_round, p.competitor_id) = 'dj'
                      and not public.site_sitting_out(p_round, p.competitor_id))
       or exists (select 1 from public.site_season_players p join public.members m on m.competitor_id = p.competitor_id
                   where p.season_key = s.key and public.site_round_role(p_round, p.competitor_id) = 'dj'
                     and not public.site_sitting_out(p_round, p.competitor_id)
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
                     and not public.site_sitting_out(p_round, p.competitor_id)
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

-- The reminder finder, as before, and now: nothing for a paused season,
-- and nothing to anyone sitting the round out.
create or replace function public.reminders_claim(p_channels text[])
returns table (round_id uuid, kind text, user_id uuid, channel text, round_name text,
               closes_at timestamptz, email text, subscriptions jsonb)
language sql security definer set search_path = public as $$
  with rounds as (
    select r.*, public.site_round_phase(r.id) as phase,
           coalesce(r.closed_at, r.closes_at) as voting_opened
      from public.site_rounds r
     where not public.site_season_paused(r.season_key)),
  targets as (
    select r.id as round_id, 'round_open'::text as kind, m.user_id
      from rounds r cross join public.members m
     where r.phase = 'submitting' and r.opens_at > now() - interval '6 hours'
       and public.site_round_role(r.id, m.competitor_id) = 'dj'
       and not public.site_sitting_out(r.id, m.competitor_id)
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
             where public.site_round_role(x.id, p.competitor_id) = 'spectator'
               and not public.site_sitting_out(x.id, p.competitor_id)) w on w.round_id = r.id
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
  select c.round_id, c.kind, c.user_id, c.channel,
         case when public.site_hides_from(c.round_id, c.user_id, 'prompt')
              then coalesce((select s.name || ', ' from public.site_seasons s where s.key = r.season_key), '')
                   || public.site_round_public_name(r.id)
              else r.name end,
         case when c.kind like 'vote%' then r.voting_closes_at else r.closes_at end,
         case when c.channel = 'email' then (select u.email from auth.users u where u.id = c.user_id) end,
         case when c.channel = 'push' then (
           select coalesce(jsonb_agg(jsonb_build_object('endpoint', s.endpoint, 'p256dh', s.p256dh, 'auth', s.auth)), '[]'::jsonb)
             from public.push_subscriptions s where s.user_id = c.user_id) end
    from claimed c join public.site_rounds r on r.id = c.round_id;
$$;

-- Reorders a round that hasn't opened, as before, and now logged.
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
  perform public.site_log('Moved "' || r.name || '" ' || case when p_earlier then 'earlier' else 'later' end,
                          r.season_key, p_round, auth.uid());
  perform public.site_quiet();
  update public.site_rounds set opens_at = o.opens_at, closes_at = o.closes_at, voting_closes_at = o.voting_closes_at
   where id = r.id;
  update public.site_rounds set opens_at = r.opens_at, closes_at = r.closes_at, voting_closes_at = r.voting_closes_at
   where id = o.id;
  perform public.site_season_reschedule(r.season_key);
end;
$$;

-- The rounds for the pages, as before, and now: whether the round's season
-- is paused and until when, the round's own days, and who's sitting it out.
create or replace function public.site_rounds_list()
returns jsonb language sql stable security definer set search_path = public as $$
  select coalesce(jsonb_agg(x.row order by x.opens_at desc), '[]'::jsonb)
    from (
      select r.opens_at, jsonb_build_object(
        'id', r.id, 'season_key', r.season_key,
        'name', case when h.prompt then public.site_round_public_name(r.id) else r.name end,
        'prompt', case when h.prompt then '' else r.prompt end,
        'prompt_hidden', h.prompt, 'prompter_hidden', h.prompter,
        'hide_prompt', r.hide_prompt, 'hide_prompter', r.hide_prompter,
        'opens_at', r.opens_at, 'closes_at', r.closes_at, 'closed_at', r.closed_at, 'created_at', r.created_at,
        'spotify_playlist', r.spotify_playlist, 'youtube_playlist', r.youtube_playlist,
        'votes_on_site', r.votes_on_site, 'voting_closes_at', r.voting_closes_at, 'voting_closed_at', r.voting_closed_at,
        'point_budget', r.point_budget, 'max_per_track', r.max_per_track, 'nonvoters_keep_points', r.nonvoters_keep_points,
        'songs_per_round', r.songs_per_round, 'downvotes', r.downvotes, 'max_down_per_track', r.max_down_per_track,
        'services', r.services, 'repeat_rule', r.repeat_rule,
        'submit_days', r.submit_days, 'vote_days', r.vote_days,
        'paused', public.site_season_paused(r.season_key),
        'paused_until', (select p.resume_at from public.site_season_pauses p
                          where p.season_key = r.season_key and p.ended_at is null),
        'site_round_sitouts', coalesce((
          select jsonb_agg(jsonb_build_object('competitor_id', o.competitor_id, 'status', o.status) order by o.competitor_id)
            from public.site_round_sitouts o where o.round_id = r.id), '[]'::jsonb),
        'site_round_prompters', case when h.prompter then '[]'::jsonb else coalesce((
          select jsonb_agg(jsonb_build_object('competitor_id', p.competitor_id) order by p.competitor_id)
            from public.site_round_prompters p where p.round_id = r.id), '[]'::jsonb) end,
        'site_round_roles', coalesce((
          select jsonb_agg(jsonb_build_object('competitor_id', o.competitor_id, 'role', o.role) order by o.competitor_id)
            from public.site_round_roles o where o.round_id = r.id), '[]'::jsonb)) as row
        from (select * from public.site_rounds order by opens_at desc limit 100) r
        cross join lateral (select public.site_hides_from(r.id, auth.uid(), 'prompt') as prompt,
                                   public.site_hides_from(r.id, auth.uid(), 'prompter') as prompter) h
       where public.is_member()) x;
$$;

-- ---------------------------------------------------------------- who can call what

-- inner workings: no one calls them directly
revoke all on function public.site_when(timestamptz) from public, anon, authenticated;
revoke all on function public.site_round_label(uuid) from public, anon, authenticated;
revoke all on function public.site_quiet() from public, anon, authenticated;
revoke all on function public.site_is_quiet() from public, anon, authenticated;
revoke all on function public.site_log(text, text, uuid, uuid) from public, anon, authenticated;
revoke all on function public.site_log_by_commissioner(text, text, uuid) from public, anon, authenticated;
revoke all on function public.site_rounds_logged() from public, anon, authenticated;
revoke all on function public.site_seasons_logged() from public, anon, authenticated;
revoke all on function public.site_season_players_logged() from public, anon, authenticated;
revoke all on function public.site_round_people_logged() from public, anon, authenticated;
revoke all on function public.site_members_logged() from public, anon, authenticated;
revoke all on function public.site_players_logged() from public, anon, authenticated;
revoke all on function public.site_announcements_logged() from public, anon, authenticated;
revoke all on function public.site_author(uuid) from public, anon, authenticated;
revoke all on function public.site_notify(uuid, text, text, text) from public, anon, authenticated;
revoke all on function public.site_notify_commissioners(text, text, text) from public, anon, authenticated;
revoke all on function public.site_sitting_out(uuid, text) from public, anon, authenticated;
revoke all on function public.site_days_until(timestamptz, timestamptz) from public, anon, authenticated;
revoke all on function public.site_pause_move(text, timestamptz, int) from public, anon, authenticated;
revoke all on function public.site_pause_announce(uuid, text) from public, anon, authenticated;
revoke all on function public.site_pause_begin(uuid, timestamptz, uuid) from public, anon, authenticated;
revoke all on function public.site_pause_end(uuid, timestamptz, uuid) from public, anon, authenticated;
revoke all on function public.site_round_winners(uuid) from public, anon, authenticated;
revoke all on function public.site_rotation_tick() from public, anon, authenticated;
revoke all on function public.site_pause_tick() from public, anon, authenticated;
revoke all on function public.site_round_waiting(uuid) from public, anon, authenticated;
revoke all on function public.site_writes_allowed() from public, anon, authenticated;
revoke all on function public.site_owner_not_sitting_out() from public, anon, authenticated;
revoke all on function public.site_season_reschedule(text) from public, anon, authenticated;
revoke all on function public.site_season_shift(text, interval) from public, anon, authenticated;
revoke all on function public.site_round_finish_early(uuid) from public, anon, authenticated;
revoke all on function public.reminders_claim(text[]) from public, anon, authenticated;
revoke all on function public.announcements_claim() from public, anon, authenticated;

-- what the pages call (each checks who's asking)
-- whether a season is paused is no secret, and the times guard (which
-- runs as the member) asks it
revoke all on function public.site_season_paused(text) from public, anon;
grant execute on function public.site_season_paused(text) to authenticated;
revoke all on function public.site_round_paused(uuid) from public, anon;
grant execute on function public.site_round_paused(uuid) to authenticated;
revoke all on function public.site_activity_list(bigint, int) from public, anon;
grant execute on function public.site_activity_list(bigint, int) to authenticated;
revoke all on function public.my_prompt_turns() from public, anon;
grant execute on function public.my_prompt_turns() to authenticated;
revoke all on function public.send_prompt_turn(uuid, text, text) from public, anon;
grant execute on function public.send_prompt_turn(uuid, text, text) to authenticated;
revoke all on function public.site_prompt_turns_list() from public, anon;
grant execute on function public.site_prompt_turns_list() to authenticated;
revoke all on function public.decide_prompt_turn(uuid, text, text) from public, anon;
grant execute on function public.decide_prompt_turn(uuid, text, text) to authenticated;
revoke all on function public.set_site_season_rotation(text, boolean) from public, anon;
grant execute on function public.set_site_season_rotation(text, boolean) to authenticated;
revoke all on function public.pause_season(text, timestamptz, uuid, timestamptz, text) from public, anon;
grant execute on function public.pause_season(text, timestamptz, uuid, timestamptz, text) to authenticated;
revoke all on function public.set_pause_resume(text, timestamptz) from public, anon;
grant execute on function public.set_pause_resume(text, timestamptz) to authenticated;
revoke all on function public.resume_season(text) from public, anon;
grant execute on function public.resume_season(text) to authenticated;
revoke all on function public.site_pauses() from public, anon;
grant execute on function public.site_pauses() to authenticated;
revoke all on function public.extend_site_round(uuid, int, int) from public, anon;
grant execute on function public.extend_site_round(uuid, int, int) to authenticated;
revoke all on function public.site_round_status(uuid) from public, anon;
grant execute on function public.site_round_status(uuid) to authenticated;
revoke all on function public.nudge_round(uuid) from public, anon;
grant execute on function public.nudge_round(uuid) to authenticated;
revoke all on function public.site_round_last_nudge(uuid) from public, anon;
grant execute on function public.site_round_last_nudge(uuid) to authenticated;
revoke all on function public.ask_sit_out(uuid, boolean) from public, anon;
grant execute on function public.ask_sit_out(uuid, boolean) to authenticated;
revoke all on function public.decide_sit_out(uuid, text, boolean) from public, anon;
grant execute on function public.decide_sit_out(uuid, text, boolean) to authenticated;
revoke all on function public.set_site_round_days(uuid, int, int) from public, anon;
grant execute on function public.set_site_round_days(uuid, int, int) to authenticated;
revoke all on function public.create_invite(text) from public, anon;
grant execute on function public.create_invite(text) to authenticated;
revoke all on function public.post_announcement(text, timestamptz, text) from public, anon;
grant execute on function public.post_announcement(text, timestamptz, text) to authenticated;
revoke all on function public.edit_announcement(uuid, text, timestamptz) from public, anon;
grant execute on function public.edit_announcement(uuid, text, timestamptz) to authenticated;
revoke all on function public.move_site_season_round(uuid, boolean) from public, anon;
grant execute on function public.move_site_season_round(uuid, boolean) to authenticated;
revoke all on function public.site_rounds_list() from public, anon;
grant execute on function public.site_rounds_list() to authenticated;

-- The minute timer for pauses and prompt turns (pg_cron is on: the
-- reminders' five-minute timer runs on it). To stop it:
-- select cron.unschedule('pfml-pauses');
do $cron$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    perform cron.schedule('pfml-pauses', '* * * * *', 'select public.site_pause_tick()');
  end if;
end
$cron$;
