-- The extras: allowed services, submitter notes, a repeat rule and
-- announcements (README, Commissioner extras). Run once in the Supabase SQL
-- Editor for the live project, after 2026-10-25_more_songs.sql. Safe to
-- re-run. supabase/schema.sql has the same at its end, for a fresh install.
--
-- Commissioners, stage 4 (asked 2026-10-25). Every round that already
-- exists keeps what it has today: every service, no note, the in-round
-- repeat warning (no blocking). One new table, site_announcements: members
-- read it (granted here explicitly, ahead of Supabase's 2026-10-30 change);
-- only the functions write it. It replaces submit_track,
-- site_rounds_export, my_submission, my_notification_choices, set_notification_choice,
-- create_site_season, update_site_season and add_site_season_round; in
-- schema.sql the earlier definitions stay above, as the earlier migrations
-- ran them, and these, at the end, are the ones that stand.

-- ---------------------------------------------------------------- commissioner extras

-- Which services a round takes, and what it does about a repeat within it:
-- 'off' (no warning), 'warn' (as before), 'block_song' (refuse the same
-- song) or 'block_artist' (refuse the same artist too).
alter table public.site_seasons add column if not exists services text[] not null default '{spotify,youtube,soundcloud}';
alter table public.site_seasons add column if not exists repeat_rule text not null default 'warn';
alter table public.site_seasons drop constraint if exists site_seasons_extras;
alter table public.site_seasons add constraint site_seasons_extras check (
  cardinality(services) between 1 and 3 and services <@ array['spotify', 'youtube', 'soundcloud']
  and repeat_rule in ('off', 'warn', 'block_song', 'block_artist'));
alter table public.site_rounds add column if not exists services text[] not null default '{spotify,youtube,soundcloud}';
alter table public.site_rounds add column if not exists repeat_rule text not null default 'warn';
alter table public.site_rounds drop constraint if exists site_rounds_extras;
alter table public.site_rounds add constraint site_rounds_extras check (
  cardinality(services) between 1 and 3 and services <@ array['spotify', 'youtube', 'soundcloud']
  and repeat_rule in ('off', 'warn', 'block_song', 'block_artist'));

-- A submitter's note on their track, in a round voted on the site. It
-- shows with the tracks once submissions close, as the track does, and is
-- named with it once voting closes.
alter table public.site_submissions add column if not exists note text not null default '';
alter table public.site_submissions drop constraint if exists site_submissions_note_length;
alter table public.site_submissions add constraint site_submissions_note_length check (char_length(note) <= 1000);

-- Messages from the commissioners, pushed to everyone who has
-- notifications on, and on Home for a week.
create table if not exists public.site_announcements (
  id         uuid primary key default gen_random_uuid(),
  body       text not null check (char_length(btrim(body)) between 1 and 1000),
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  pushed_at  timestamptz
);
alter table public.site_announcements enable row level security;
drop policy if exists "members read announcements" on public.site_announcements;
create policy "members read announcements" on public.site_announcements
  for select to authenticated using (public.is_member());
revoke all on table public.site_announcements from anon, authenticated;
grant select on table public.site_announcements to authenticated;

alter table public.reminder_settings add column if not exists announcements boolean not null default true;

-- Takes a submission, as before, and now: only from a service the round
-- takes, and, in a round that blocks repeats, only through
-- submit_described, which checks the track against the round first.
create or replace function public.submit_track(p_round uuid, p_platform text, p_track text)
returns text language plpgsql security definer set search_path = public as $$
declare
  uid uuid := auth.uid();
  r public.site_rounds%rowtype;
  mine uuid;
  have int;
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
  if not (p_platform = any(r.services)) then
    raise exception 'This round takes % tracks only.',
      (select string_agg(case x when 'spotify' then 'Spotify' when 'youtube' then 'YouTube' else 'SoundCloud' end, ' and ')
         from unnest(r.services) x);
  end if;
  if r.repeat_rule in ('block_song', 'block_artist') and current_setting('pfml.checked_round', true) is distinct from p_round::text then
    raise exception 'This round checks repeats as a track goes in. Reload the page and send it again.';
  end if;

  select count(*) into have from public.site_submission_owners o where o.round_id = p_round and o.user_id = uid;
  -- one song a round: sending again swaps it
  if r.songs_per_round = 1 and have > 0 then
    select o.submission_id into mine from public.site_submission_owners o
     where o.round_id = p_round and o.user_id = uid limit 1;
  end if;

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

  if have >= r.songs_per_round then
    raise exception 'You''ve sent all % of your tracks for this round. Remove one to send another.', r.songs_per_round;
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

-- Takes a submission with its description (the repeat check's fingerprint,
-- worked out on the page), checking it against the tracks already in the
-- round first when the round blocks repeats: the same song (the exact
-- track, another version, or the same song) for 'block_song', and the same
-- artist too for 'block_artist'. The caller's track a send would swap
-- doesn't count. Then saves the description with the track.
create or replace function public.submit_described(p_round uuid, p_platform text, p_track text,
                                                   p_song text, p_names text[], p_text text)
returns text language plpgsql security definer set search_path = public as $$
declare
  uid uuid := auth.uid();
  r public.site_rounds%rowtype;
  kinds text[];
  new_tag text;
begin
  if not public.is_member() then
    raise exception 'Only league members can submit.';
  end if;
  if not public.fp_ok(p_song, p_names, p_text) then
    raise exception 'That description of the track can''t be used.';
  end if;
  -- one at a time per round, so two of the same can't both get past the check
  select * into r from public.site_rounds where id = p_round for update;
  if not found then
    raise exception 'That round doesn''t exist.';
  end if;
  if r.repeat_rule in ('block_song', 'block_artist') then
    select coalesce(array_agg(distinct x.kind) filter (where x.kind is not null), '{}'::text[]) into kinds
      from (select public.fp_kind(p_platform, p_track, coalesce(p_song, ''), coalesce(p_names, '{}'::text[]), coalesce(p_text, ''),
                                  s.platform, s.track,
                                  case when d.described then s.fp_song else '' end,
                                  case when d.described then s.fp_names else '{}'::text[] end,
                                  case when d.described then s.fp_text else '' end) as kind
              from public.site_submissions s
              cross join lateral (select s.fp_for is not distinct from s.platform || ':' || s.track as described) d
             where s.round_id = p_round
               and not (r.songs_per_round = 1 and exists (select 1 from public.site_submission_owners o
                                                           where o.submission_id = s.id and o.user_id = uid))) x;
    if kinds && array['track', 'version', 'song'] then
      raise exception 'This round doesn''t take a song that''s already in it.';
    end if;
    if r.repeat_rule = 'block_artist' and kinds && array['artist'] then
      raise exception 'This round doesn''t take an artist who''s already in it.';
    end if;
  end if;
  perform set_config('pfml.checked_round', p_round::text, true);
  new_tag := public.submit_track(p_round, p_platform, p_track);
  perform set_config('pfml.checked_round', '', true);
  update public.site_submissions s
     set fp_song = coalesce(p_song, ''), fp_names = coalesce(p_names, '{}'::text[]),
         fp_text = coalesce(p_text, ''), fp_for = s.platform || ':' || s.track
    from public.site_submission_owners o
   where o.submission_id = s.id and o.round_id = p_round and o.user_id = uid and s.tag = new_tag;
  return new_tag;
end;
$$;

-- The caller's own tracks for a round, with their notes.
drop function if exists public.my_submission(uuid);
create or replace function public.my_submission(p_round uuid)
returns table (tag text, platform text, track text, note text)
language sql stable security definer set search_path = public as $$
  select s.tag, s.platform, s.track, s.note
    from public.site_submissions s
    join public.site_submission_owners o on o.submission_id = s.id
   where o.round_id = p_round and o.user_id = auth.uid()
   order by s.tag;
$$;

-- The note on one of the caller's own tracks, while submissions are open,
-- in a round voted on the site.
create or replace function public.set_submission_note(p_round uuid, p_tag text, p_note text)
returns void language plpgsql security definer set search_path = public as $$
begin
  if not public.is_member() then
    raise exception 'Only league members can submit.';
  end if;
  if not exists (select 1 from public.site_rounds where id = p_round and votes_on_site) then
    raise exception 'Notes are for rounds voted on the site.';
  end if;
  if exists (select 1 from public.site_rounds
              where id = p_round and (closed_at is not null or now() >= closes_at)) then
    raise exception 'Submissions for this round are closed.';
  end if;
  if char_length(coalesce(p_note, '')) > 1000 then
    raise exception 'A note can be at most 1000 characters.';
  end if;
  update public.site_submissions s set note = btrim(coalesce(p_note, ''))
    from public.site_submission_owners o
   where o.submission_id = s.id and o.round_id = p_round and o.user_id = auth.uid() and s.tag = p_tag;
end;
$$;

-- A commissioner's announcement, and taking one down.
create or replace function public.post_announcement(p_body text)
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
  insert into public.site_announcements (body, created_by) values (btrim(p_body), auth.uid()) returning id into aid;
  return aid;
end;
$$;

create or replace function public.delete_announcement(p_id uuid)
returns void language plpgsql security definer set search_path = public as $$
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can take an announcement down.';
  end if;
  delete from public.site_announcements where id = p_id;
end;
$$;

-- For the sender only: announcements not pushed yet (from the last day),
-- each with every member who has a device and wants announcements, and
-- marked pushed in the same step, so none goes twice.
create or replace function public.announcements_claim()
returns table (announcement_id uuid, body text, author text, user_id uuid, subscriptions jsonb)
language plpgsql security definer set search_path = public as $$
#variable_conflict use_column
begin
  perform pg_advisory_xact_lock(hashtext('pfml.announcements_claim'));
  return query
  with fresh as (
    update public.site_announcements a set pushed_at = now()
     where a.pushed_at is null and a.created_at > now() - interval '1 day'
    returning a.id, a.body, a.created_by)
  select f.id, f.body,
         coalesce((select p.name from public.members am join public.players p on p.competitor_id = am.competitor_id
                    where am.user_id = f.created_by), 'A commissioner'),
         m.user_id,
         (select coalesce(jsonb_agg(jsonb_build_object('endpoint', s.endpoint, 'p256dh', s.p256dh, 'auth', s.auth)), '[]'::jsonb)
            from public.push_subscriptions s where s.user_id = m.user_id)
    from fresh f cross join public.members m
   where exists (select 1 from public.push_subscriptions s where s.user_id = m.user_id)
     and coalesce((select rs.announcements from public.reminder_settings rs where rs.user_id = m.user_id), true);
end;
$$;

-- The caller's notification choices, now with announcements.
drop function if exists public.my_notification_choices();
create or replace function public.my_notification_choices()
returns table (round_open boolean, playlist_ready boolean, replies boolean, reactions boolean, voting boolean,
               announcements boolean)
language sql stable security definer set search_path = public as $$
  select coalesce(s.round_open, true), coalesce(s.playlist_ready, true), coalesce(s.replies, true),
         coalesce(s.reactions, true), coalesce(s.voting, true), coalesce(s.announcements, true)
    from (select 1) one
    left join public.reminder_settings s on s.user_id = auth.uid()
   where public.is_member();
$$;

create or replace function public.set_notification_choice(p_kind text, p_on boolean)
returns void language plpgsql security definer set search_path = public as $$
begin
  if not public.is_member() then
    raise exception 'Only league members have notifications.';
  end if;
  if p_kind is null or p_kind not in ('round_open', 'playlist_ready', 'replies', 'reactions', 'voting', 'announcements') or p_on is null then
    raise exception 'That isn''t a notification you can turn on or off.';
  end if;
  insert into public.reminder_settings (user_id) values (auth.uid()) on conflict (user_id) do nothing;
  execute format('update public.reminder_settings set %I = $1 where user_id = $2', p_kind) using p_on, auth.uid();
end;
$$;

-- Sets up a season, as before, and now with services and repeat_rule,
-- which every round gets.
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
                                    point_budget, max_per_track, nonvoters_keep_points,
                                    songs_per_round, downvotes, max_down_per_track, services, repeat_rule)
    values (k, btrim(coalesce(item->>'name', '')), btrim(coalesce(item->>'prompt', '')), opens, closes, true,
            public.site_add_days(closes, s.vote_days), s.point_budget, s.max_per_track, s.nonvoters_keep_points,
            s.songs_per_round, s.downvotes, s.max_down_per_track, s.services, s.repeat_rule);
  end loop;
  return k;
end;
$$;

-- Changes a season, as before, and now: services and the repeat rule reach
-- every round whose submissions haven't closed.
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
    vote_days = coalesce((p->>'vote_days')::smallint, vote_days),
    songs_per_round = coalesce((p->>'songs_per_round')::smallint, songs_per_round),
    downvotes = coalesce((p->>'downvotes')::smallint, downvotes),
    max_down_per_track = coalesce((p->>'max_down_per_track')::smallint, max_down_per_track),
    services = coalesce((select array_agg(x) from jsonb_array_elements_text(p->'services') x), services),
    repeat_rule = coalesce(p->>'repeat_rule', repeat_rule)
   where key = p_key
  returning * into s;
  if not found then
    raise exception 'That season doesn''t exist.';
  end if;
  update public.site_rounds set point_budget = s.point_budget, max_per_track = s.max_per_track,
                                nonvoters_keep_points = s.nonvoters_keep_points,
                                downvotes = s.downvotes, max_down_per_track = s.max_down_per_track,
                                services = s.services, repeat_rule = s.repeat_rule
   where season_key = p_key and closed_at is null and now() < closes_at;
  update public.site_rounds set songs_per_round = s.songs_per_round
   where season_key = p_key and now() < opens_at;
  perform public.site_season_reschedule(p_key);
end;
$$;

-- Adds a round at the end of a season, as before, with the season's
-- services and repeat rule.
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
                                  point_budget, max_per_track, nonvoters_keep_points,
                                  songs_per_round, downvotes, max_down_per_track, services, repeat_rule)
  values (p_key, btrim(coalesce(p_name, '')), btrim(coalesce(p_prompt, '')), opens, closes, true,
          public.site_add_days(closes, s.vote_days), s.point_budget, s.max_per_track, s.nonvoters_keep_points,
          s.songs_per_round, s.downvotes, s.max_down_per_track, s.services, s.repeat_rule)
  returning id into rid;
  return rid;
end;
$$;

-- Finished rounds voted here, for publish.py, as before, and now with each
-- track's note (the build shows it as Music League's submitter comment).
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
            'position', s.position, 'note', s.note, 'submitter', m.competitor_id) order by s.tag)
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

revoke all on function public.my_submission(uuid) from public, anon;
grant execute on function public.my_submission(uuid) to authenticated;
revoke all on function public.submit_described(uuid, text, text, text, text[], text) from public, anon;
grant execute on function public.submit_described(uuid, text, text, text, text[], text) to authenticated;
revoke all on function public.set_submission_note(uuid, text, text) from public, anon;
grant execute on function public.set_submission_note(uuid, text, text) to authenticated;
revoke all on function public.post_announcement(text) from public, anon;
grant execute on function public.post_announcement(text) to authenticated;
revoke all on function public.delete_announcement(uuid) from public, anon;
grant execute on function public.delete_announcement(uuid) to authenticated;
revoke all on function public.announcements_claim() from public, anon, authenticated;
grant execute on function public.announcements_claim() to service_role;
revoke all on function public.my_notification_choices() from public, anon;
grant execute on function public.my_notification_choices() to authenticated;
