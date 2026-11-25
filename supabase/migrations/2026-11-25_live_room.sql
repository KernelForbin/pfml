-- The live room (asked 2026-11-25; README, The live room): one room at
-- /tt where members take turns DJing a track each, live, from YouTube or
-- SoundCloud, with a crowd, votes and a chat that keeps its history. Run it
-- in the Supabase SQL Editor, then the rehearsal,
-- supabase/checks/2026-11-25_live_room_rehearsal.sql. The page ships only
-- after both.
--
-- The database is the room: what's playing and since when, whose turn is
-- next, who's here. Pages ask room_here() for all of it, every few seconds
-- and whenever room_state changes (which they hear through Realtime). No
-- timer runs it: whoever asks next moves it along.

-- ---------------------------------------------------------------- tables

-- A member's own tracks: their library, and, for the ones with a place
-- (queue_pos), their queue, top first. Only the functions below touch it.
create table if not exists public.room_tracks (
  id        uuid primary key default gen_random_uuid(),
  user_id   uuid not null references auth.users (id) on delete cascade,
  platform  text not null check (platform in ('youtube', 'soundcloud')),
  track     text not null check (
    (platform = 'youtube'    and track ~ '^[A-Za-z0-9_-]{11}$') or
    (platform = 'soundcloud' and track ~ '^[a-z0-9_-]{1,100}/[a-z0-9_-]{1,200}$')),
  title     text not null check (char_length(btrim(title)) between 1 and 300),
  artist    text not null default '' check (char_length(artist) <= 200),
  seconds   int check (seconds between 1 and 3600),      -- null: not measured yet
  queue_pos int,
  added_at  timestamptz not null default now(),
  unique (user_id, platform, track)
);
create index if not exists room_tracks_queue on public.room_tracks (user_id, queue_pos);

-- Every track the room has played, the one playing included (ended_at
-- null). It keeps its own copy of the track, so a DJ changing their library
-- changes nothing here.
create table if not exists public.room_plays (
  id           bigint generated always as identity primary key,
  user_id      uuid references auth.users (id) on delete set null,
  platform     text not null,
  track        text not null,
  title        text not null,
  artist       text not null default '',
  seconds      int,                       -- null until a player has measured it
  length_known boolean not null default false,
  started_at   timestamptz not null default now(),
  ended_at     timestamptz,
  skipped_by   uuid references auth.users (id) on delete set null
);
create index if not exists room_plays_recent on public.room_plays (id desc);

-- The one room. version goes up whenever anything members see changes;
-- pages listen for that. last_seq is the turn that played last, so the
-- rotation knows who's next.
create table if not exists public.room_state (
  id         smallint primary key default 1 check (id = 1),
  version    bigint not null default 0,
  chat_epoch int not null default 0,      -- goes up when a message is removed, so pages reload the chat
  play_id    bigint references public.room_plays (id) on delete set null,
  last_seq   bigint not null default 0
);
insert into public.room_state (id) values (1) on conflict (id) do nothing;

-- Who's on the decks, in the order they stepped up (seq).
create table if not exists public.room_djs (
  user_id   uuid primary key references auth.users (id) on delete cascade,
  seq       bigint generated always as identity,
  joined_at timestamptz not null default now()
);

-- Who's in the room: a page says so every 20 seconds, and 90 seconds of
-- silence means they've gone.
create table if not exists public.room_presence (
  user_id   uuid primary key references auth.users (id) on delete cascade,
  last_seen timestamptz not null default now()
);

create table if not exists public.room_votes (
  play_id bigint not null references public.room_plays (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  vote    smallint not null check (vote in (1, -1)),
  primary key (play_id, user_id)
);

-- The chat, kept for good, so anyone coming in can read back.
create table if not exists public.room_messages (
  id         bigint generated always as identity primary key,
  user_id    uuid references auth.users (id) on delete set null,
  body       text not null check (char_length(btrim(body)) between 1 and 280),
  created_at timestamptz not null default now(),
  removed_at timestamptz,
  removed_by uuid references auth.users (id) on delete set null
);
create index if not exists room_messages_user on public.room_messages (user_id, created_at desc);

alter table public.room_tracks   enable row level security;
alter table public.room_plays    enable row level security;
alter table public.room_state    enable row level security;
alter table public.room_djs      enable row level security;
alter table public.room_presence enable row level security;
alter table public.room_votes    enable row level security;
alter table public.room_messages enable row level security;
revoke all on table public.room_tracks   from anon, authenticated;
revoke all on table public.room_plays    from anon, authenticated;
revoke all on table public.room_state    from anon, authenticated;
revoke all on table public.room_djs      from anon, authenticated;
revoke all on table public.room_presence from anon, authenticated;
revoke all on table public.room_votes    from anon, authenticated;
revoke all on table public.room_messages from anon, authenticated;

-- Members read room_state, and nothing else directly: it's the one row
-- pages listen to (Realtime tells a page only about rows it may read), and
-- it says only that something changed.
drop policy if exists "members read the room" on public.room_state;
create policy "members read the room" on public.room_state
  for select to authenticated using (public.is_member());
grant select on table public.room_state to authenticated;

-- Realtime sends changes of the tables in this publication. A database
-- without it (a local one) just goes without; pages fall back to asking
-- every few seconds.
do $realtime$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime')
     and not exists (select 1 from pg_publication_tables
                      where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'room_state') then
    alter publication supabase_realtime add table public.room_state;
  end if;
end
$realtime$;

-- ---------------------------------------------------------------- inner workings

create or replace function public.room_bump()
returns void language sql security definer set search_path = public as $$
  update public.room_state set version = version + 1 where id = 1;
$$;

-- A member's player id, for the pages (which know members by it).
create or replace function public.room_who(p_user uuid)
returns text language sql stable security definer set search_path = public as $$
  select m.competitor_id from public.members m where m.user_id = p_user;
$$;

-- Marks the caller as here now. True when they weren't a moment ago.
create or replace function public.room_touch()
returns boolean language plpgsql security definer set search_path = public as $$
declare
  fresh boolean;
begin
  fresh := not exists (select 1 from public.room_presence where user_id = auth.uid());
  insert into public.room_presence (user_id, last_seen) values (auth.uid(), now())
  on conflict (user_id) do update set last_seen = now();
  return fresh;
end;
$$;

-- Starts the next DJ's top track; with nobody on the decks, the room goes
-- quiet. The caller holds room_state's row. A DJ whose turn comes with an
-- empty queue is off the decks. The track that starts moves to the bottom
-- of its DJ's queue (the user's call, 2026-11-25), so a queue never runs
-- dry by being played.
create or replace function public.room_start_next()
returns void language plpgsql security definer set search_path = public as $$
declare
  last bigint;
  d public.room_djs%rowtype;
  t public.room_tracks%rowtype;
  pid bigint;
begin
  select last_seq into last from public.room_state where id = 1;
  loop
    select * into d from public.room_djs where seq > last order by seq limit 1;
    if not found then
      select * into d from public.room_djs order by seq limit 1;
    end if;
    if not found then
      update public.room_state set play_id = null where id = 1;
      return;
    end if;
    select * into t from public.room_tracks
     where user_id = d.user_id and queue_pos is not null order by queue_pos, added_at limit 1;
    if not found then
      delete from public.room_djs where user_id = d.user_id;
      continue;
    end if;
    insert into public.room_plays (user_id, platform, track, title, artist, seconds, length_known)
    values (d.user_id, t.platform, t.track, t.title, t.artist, t.seconds, t.seconds is not null)
    returning id into pid;
    update public.room_tracks
       set queue_pos = (select coalesce(max(x.queue_pos), 0) + 1 from public.room_tracks x where x.user_id = d.user_id)
     where id = t.id;
    update public.room_state set play_id = pid, last_seq = d.seq where id = 1;
    return;
  end loop;
end;
$$;

-- Moves the room along, when there's something to move: a track whose
-- time is up ends and the next DJ's starts; anyone silent for 90 seconds
-- has left the room and the decks. A track of unknown length gets 10
-- minutes until a player measures it. Looks first, and takes the room's
-- lock only when there's work.
create or replace function public.room_advance()
returns void language plpgsql security definer set search_path = public as $$
declare
  s public.room_state%rowtype;
  p public.room_plays%rowtype;
begin
  select * into s from public.room_state where id = 1;
  select * into p from public.room_plays where id = s.play_id;
  if not exists (select 1 from public.room_presence where last_seen <= now() - interval '90 seconds')
     and ((s.play_id is not null and now() < p.started_at + make_interval(secs => coalesce(p.seconds, 600)))
          or (s.play_id is null and not exists (select 1 from public.room_djs))) then
    return;
  end if;

  select * into s from public.room_state where id = 1 for update;
  delete from public.room_presence where last_seen <= now() - interval '90 seconds';
  delete from public.room_djs d where not exists (select 1 from public.room_presence x where x.user_id = d.user_id);
  if s.play_id is not null then
    select * into p from public.room_plays where id = s.play_id;
    if now() >= p.started_at + make_interval(secs => coalesce(p.seconds, 600)) then
      update public.room_plays set ended_at = p.started_at + make_interval(secs => coalesce(p.seconds, 600)) where id = p.id;
      update public.room_state set play_id = null where id = 1;
      s.play_id := null;
    end if;
  end if;
  if s.play_id is null then
    perform public.room_start_next();
  end if;
  perform public.room_bump();
end;
$$;

-- ---------------------------------------------------------------- what the page calls

-- "I'm here", and everything the room page shows: the time on the
-- database's clock (pages sync their players to it), what's playing, the
-- decks in turn order, the crowd, and the chat: the last 200 messages, or
-- (p_after) only the ones after that id.
create or replace function public.room_here(p_after bigint)
returns jsonb language plpgsql security definer set search_path = public as $$
declare
  uid uuid := auth.uid();
  fresh boolean;
  s public.room_state%rowtype;
  p public.room_plays%rowtype;
begin
  if not public.is_member() then
    raise exception 'Only league members can come into the room.';
  end if;
  fresh := public.room_touch();
  perform public.room_advance();
  if fresh then
    perform public.room_bump();
  end if;
  select * into s from public.room_state where id = 1;
  select * into p from public.room_plays where id = s.play_id;
  return jsonb_build_object(
    'now', now(),
    'version', s.version,
    'chat_epoch', s.chat_epoch,
    'play', case when p.id is null then null else jsonb_build_object(
      'id', p.id, 'dj', public.room_who(p.user_id), 'platform', p.platform, 'track', p.track,
      'title', p.title, 'artist', p.artist, 'seconds', p.seconds, 'length_known', p.length_known,
      'started_at', p.started_at,
      'awesome', coalesce((select jsonb_agg(public.room_who(v.user_id) order by public.room_who(v.user_id))
                             from public.room_votes v where v.play_id = p.id and v.vote = 1), '[]'::jsonb),
      'lame', (select count(*) from public.room_votes v where v.play_id = p.id and v.vote = -1),
      'my_vote', coalesce((select v.vote from public.room_votes v where v.play_id = p.id and v.user_id = uid), 0)) end,
    'djs', coalesce((select jsonb_agg(public.room_who(d.user_id) order by d.seq) from public.room_djs d), '[]'::jsonb),
    'crowd', coalesce((select jsonb_agg(public.room_who(x.user_id) order by public.room_who(x.user_id))
                         from public.room_presence x), '[]'::jsonb),
    'messages', coalesce((
      select jsonb_agg(jsonb_build_object('id', m.id, 'who', public.room_who(m.user_id), 'body', m.body, 'at', m.created_at)
                       order by m.id)
        from (select * from public.room_messages x
               where x.removed_at is null and (p_after is null or x.id > p_after)
               order by x.id desc limit 200) m), '[]'::jsonb));
end;
$$;

-- Leaving: off the decks and out of the crowd at once (a page says so as
-- it closes; one that can't is noticed after 90 seconds).
create or replace function public.room_leave()
returns void language plpgsql security definer set search_path = public as $$
begin
  delete from public.room_djs where user_id = auth.uid();
  delete from public.room_presence where user_id = auth.uid();
  if found then
    perform public.room_bump();
  end if;
end;
$$;

-- Stepping up to DJ: onto the end of the rotation. It needs a track in
-- the caller's queue. With nobody playing, theirs starts.
create or replace function public.room_step_up()
returns void language plpgsql security definer set search_path = public as $$
begin
  if not public.is_member() then
    raise exception 'Only league members can DJ.';
  end if;
  if not exists (select 1 from public.room_tracks where user_id = auth.uid() and queue_pos is not null) then
    raise exception 'Put a track in your queue first.';
  end if;
  perform public.room_touch();
  insert into public.room_djs (user_id) values (auth.uid()) on conflict (user_id) do nothing;
  perform public.room_advance();
  perform public.room_bump();
end;
$$;

-- Stepping down. A track of theirs that's playing plays on to its end.
create or replace function public.room_step_down()
returns void language plpgsql security definer set search_path = public as $$
begin
  delete from public.room_djs where user_id = auth.uid();
  if found then
    perform public.room_bump();
  end if;
end;
$$;

-- Skipping what's playing: only the DJ playing it, the admin or a
-- commissioner (the user's call, 2026-11-25: Lame votes never skip).
create or replace function public.room_skip()
returns void language plpgsql security definer set search_path = public as $$
declare
  s public.room_state%rowtype;
  p public.room_plays%rowtype;
begin
  if not public.is_member() then
    raise exception 'Only league members can do that.';
  end if;
  select * into s from public.room_state where id = 1 for update;
  select * into p from public.room_plays where id = s.play_id;
  if not found then
    raise exception 'Nothing is playing.';
  end if;
  if p.user_id is distinct from auth.uid() and not public.is_commissioner() then
    raise exception 'Only the DJ playing, the admin or a commissioner can skip a track.';
  end if;
  update public.room_plays set ended_at = now(), skipped_by = auth.uid() where id = p.id;
  update public.room_state set play_id = null where id = 1;
  if p.user_id is distinct from auth.uid() then
    perform public.site_log('Skipped "' || left(p.title, 80) || '" in the live room', null, null, auth.uid());
  end if;
  perform public.room_start_next();
  perform public.room_bump();
end;
$$;

-- The admin or a commissioner takes someone off the decks.
create or replace function public.room_remove_dj(p_competitor text)
returns void language plpgsql security definer set search_path = public as $$
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can take someone off the decks.';
  end if;
  delete from public.room_djs where user_id = (select m.user_id from public.members m where m.competitor_id = p_competitor);
  if found then
    perform public.site_log('Took ' || (select pl.name from public.players pl where pl.competitor_id = p_competitor)
                            || ' off the decks in the live room', null, null, auth.uid());
    perform public.room_bump();
  end if;
end;
$$;

-- Awesome (1), Lame (-1), or taking it back (0), on what's playing. Never
-- on your own track. It skips nothing.
create or replace function public.room_vote(p_vote int)
returns void language plpgsql security definer set search_path = public as $$
declare
  p public.room_plays%rowtype;
begin
  if not public.is_member() then
    raise exception 'Only league members can vote.';
  end if;
  if p_vote is null or p_vote not in (1, 0, -1) then
    raise exception 'That isn''t a vote.';
  end if;
  select pl.* into p from public.room_state s join public.room_plays pl on pl.id = s.play_id where s.id = 1;
  if not found then
    raise exception 'Nothing is playing.';
  end if;
  if p.user_id = auth.uid() then
    raise exception 'You can''t vote on your own track.';
  end if;
  if p_vote = 0 then
    delete from public.room_votes where play_id = p.id and user_id = auth.uid();
  else
    insert into public.room_votes (play_id, user_id, vote) values (p.id, auth.uid(), p_vote)
    on conflict (play_id, user_id) do update set vote = excluded.vote;
  end if;
  perform public.room_bump();
end;
$$;

-- A player measured the playing track's real length (a pasted link comes
-- with none). Only while it's unknown, and from the DJ's own page, or
-- anyone's once the DJ has left. Their library remembers it.
create or replace function public.room_set_length(p_play bigint, p_seconds int)
returns void language plpgsql security definer set search_path = public as $$
declare
  p public.room_plays%rowtype;
begin
  if not public.is_member() then
    raise exception 'Only league members can do that.';
  end if;
  if p_seconds is null or p_seconds not between 1 and 3600 then
    raise exception 'A track runs from a second to an hour.';
  end if;
  select pl.* into p from public.room_state s join public.room_plays pl on pl.id = s.play_id where s.id = 1 and pl.id = p_play;
  if not found or p.length_known then
    return;
  end if;
  if p.user_id is distinct from auth.uid()
     and exists (select 1 from public.room_presence x where x.user_id = p.user_id) then
    return;
  end if;
  update public.room_plays set seconds = p_seconds, length_known = true where id = p.id;
  update public.room_tracks set seconds = p_seconds
   where user_id = p.user_id and platform = p.platform and track = p.track and seconds is null;
  perform public.room_bump();
end;
$$;

-- A chat message: up to 280 characters, and at most 20 a minute each.
create or replace function public.room_say(p_body text)
returns bigint language plpgsql security definer set search_path = public as $$
declare
  mid bigint;
begin
  if not public.is_member() then
    raise exception 'Only league members can chat.';
  end if;
  if char_length(btrim(coalesce(p_body, ''))) not between 1 and 280 then
    raise exception 'A message is 1 to 280 characters.';
  end if;
  if (select count(*) from public.room_messages
       where user_id = auth.uid() and created_at > now() - interval '1 minute') >= 20 then
    raise exception 'That''s a lot of messages. Give it a minute.';
  end if;
  insert into public.room_messages (user_id, body) values (auth.uid(), btrim(p_body)) returning id into mid;
  perform public.room_bump();
  return mid;
end;
$$;

-- Removing a message: its writer, or the admin.
create or replace function public.room_remove_message(p_id bigint)
returns void language plpgsql security definer set search_path = public as $$
declare
  m public.room_messages%rowtype;
begin
  select * into m from public.room_messages where id = p_id and removed_at is null;
  if not found then
    return;
  end if;
  if m.user_id is distinct from auth.uid() and not public.is_admin() then
    raise exception 'Only its writer or the admin can remove a message.';
  end if;
  update public.room_messages set removed_at = now(), removed_by = auth.uid() where id = p_id;
  if m.user_id is distinct from auth.uid() then
    perform public.site_log('Removed a message in the live room', null, null, auth.uid());
  end if;
  update public.room_state set chat_epoch = chat_epoch + 1 where id = 1;
  perform public.room_bump();
end;
$$;

-- The last 20 tracks the room finished, newest first, for Recently played.
create or replace function public.room_recent()
returns table (id bigint, dj text, platform text, track text, title text, artist text, seconds int,
               started_at timestamptz, awesome int, lame int, skipped boolean)
language sql stable security definer set search_path = public as $$
  select p.id, public.room_who(p.user_id), p.platform, p.track, p.title, p.artist, p.seconds, p.started_at,
         (select count(*)::int from public.room_votes v where v.play_id = p.id and v.vote = 1),
         (select count(*)::int from public.room_votes v where v.play_id = p.id and v.vote = -1),
         p.skipped_by is not null
    from public.room_plays p
   where p.ended_at is not null and public.is_member()
   order by p.id desc limit 20;
$$;

-- ---- a member's library and queue

create or replace function public.room_library()
returns table (id uuid, platform text, track text, title text, artist text, seconds int, queue_pos int)
language sql stable security definer set search_path = public as $$
  select t.id, t.platform, t.track, t.title, t.artist, t.seconds, t.queue_pos
    from public.room_tracks t
   where t.user_id = auth.uid() and public.is_member()
   order by t.queue_pos nulls last, t.added_at desc;
$$;

-- Adds a track to the caller's library (up to 500), and, with p_queue, to
-- the bottom of their queue. One already there keeps its place.
create or replace function public.room_library_add(p_platform text, p_track text, p_title text, p_artist text,
                                                   p_seconds int, p_queue boolean)
returns uuid language plpgsql security definer set search_path = public as $$
declare
  tid uuid;
begin
  if not public.is_member() then
    raise exception 'Only league members have a library.';
  end if;
  if p_platform is null or p_platform not in ('youtube', 'soundcloud') then
    raise exception 'The room plays YouTube and SoundCloud.';
  end if;
  if (p_platform = 'youtube' and coalesce(p_track, '') !~ '^[A-Za-z0-9_-]{11}$')
     or (p_platform = 'soundcloud' and coalesce(p_track, '') !~ '^[a-z0-9_-]{1,100}/[a-z0-9_-]{1,200}$') then
    raise exception 'That isn''t a track the room can play.';
  end if;
  if char_length(btrim(coalesce(p_title, ''))) not between 1 and 300 then
    raise exception 'The track needs a title.';
  end if;
  if (select count(*) from public.room_tracks where user_id = auth.uid()) >= 500
     and not exists (select 1 from public.room_tracks where user_id = auth.uid() and platform = p_platform and track = p_track) then
    raise exception 'A library holds 500 tracks. Remove one first.';
  end if;
  insert into public.room_tracks (user_id, platform, track, title, artist, seconds)
  values (auth.uid(), p_platform, p_track, btrim(p_title), left(btrim(coalesce(p_artist, '')), 200),
          case when p_seconds between 1 and 3600 then p_seconds end)
  on conflict (user_id, platform, track) do update set title = excluded.title, artist = excluded.artist,
     seconds = coalesce(excluded.seconds, public.room_tracks.seconds)
  returning id into tid;
  if coalesce(p_queue, false) then
    update public.room_tracks
       set queue_pos = (select coalesce(max(x.queue_pos), 0) + 1 from public.room_tracks x where x.user_id = auth.uid())
     where id = tid and queue_pos is null;
  end if;
  return tid;
end;
$$;

create or replace function public.room_library_remove(p_id uuid)
returns void language sql security definer set search_path = public as $$
  delete from public.room_tracks where id = p_id and user_id = auth.uid();
$$;

-- The caller's queue, as a whole, top first: these tracks of theirs in
-- this order, and every other track of theirs back in the library.
create or replace function public.room_queue_set(p_ids uuid[])
returns void language plpgsql security definer set search_path = public as $$
begin
  if not public.is_member() then
    raise exception 'Only league members have a queue.';
  end if;
  if p_ids is null or cardinality(p_ids) > 500 then
    raise exception 'The queue doesn''t add up. Reload the page and try again.';
  end if;
  update public.room_tracks set queue_pos = null
   where user_id = auth.uid() and queue_pos is not null and not (id = any(p_ids));
  update public.room_tracks t set queue_pos = x.ord
    from unnest(p_ids) with ordinality as x(id, ord)
   where t.id = x.id and t.user_id = auth.uid();
end;
$$;

-- ---------------------------------------------------------------- who can call what

revoke all on function public.room_bump() from public, anon, authenticated;
revoke all on function public.room_who(uuid) from public, anon, authenticated;
revoke all on function public.room_touch() from public, anon, authenticated;
revoke all on function public.room_start_next() from public, anon, authenticated;
revoke all on function public.room_advance() from public, anon, authenticated;

revoke all on function public.room_here(bigint) from public, anon;
grant execute on function public.room_here(bigint) to authenticated;
revoke all on function public.room_leave() from public, anon;
grant execute on function public.room_leave() to authenticated;
revoke all on function public.room_step_up() from public, anon;
grant execute on function public.room_step_up() to authenticated;
revoke all on function public.room_step_down() from public, anon;
grant execute on function public.room_step_down() to authenticated;
revoke all on function public.room_skip() from public, anon;
grant execute on function public.room_skip() to authenticated;
revoke all on function public.room_remove_dj(text) from public, anon;
grant execute on function public.room_remove_dj(text) to authenticated;
revoke all on function public.room_vote(int) from public, anon;
grant execute on function public.room_vote(int) to authenticated;
revoke all on function public.room_set_length(bigint, int) from public, anon;
grant execute on function public.room_set_length(bigint, int) to authenticated;
revoke all on function public.room_say(text) from public, anon;
grant execute on function public.room_say(text) to authenticated;
revoke all on function public.room_remove_message(bigint) from public, anon;
grant execute on function public.room_remove_message(bigint) to authenticated;
revoke all on function public.room_recent() from public, anon;
grant execute on function public.room_recent() to authenticated;
revoke all on function public.room_library() from public, anon;
grant execute on function public.room_library() to authenticated;
revoke all on function public.room_library_add(text, text, text, text, int, boolean) from public, anon;
grant execute on function public.room_library_add(text, text, text, text, int, boolean) to authenticated;
revoke all on function public.room_library_remove(uuid) from public, anon;
grant execute on function public.room_library_remove(uuid) to authenticated;
revoke all on function public.room_queue_set(uuid[]) from public, anon;
grant execute on function public.room_queue_set(uuid[]) to authenticated;
