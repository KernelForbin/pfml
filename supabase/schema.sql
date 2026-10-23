-- PFML members-only backend. Run once in the Supabase dashboard:
-- SQL Editor > New query > paste this whole file > Run.
-- Safe to re-run: every statement is create-if-missing or replace.
--
-- What it sets up:
--   players          every Music League competitor (id + name), written by
--                    scripts/publish.py from the exports
--   members          which Google account is which player, one to one, and
--                    when they last opened their inbox
--   invites          one-time links that create that pairing
--   comment_votes    up/down votes on Music League vote comments
--   comment_reactions
--   comment_replies  replies to Music League vote comments
--   site_rounds, site_submissions, site_submission_owners
--                    rounds open for submissions on the site, the
--                    tracks, and (readable by nobody) who sent which
--   search_cache     the Submit page's YouTube search answers (no policies)
--   two private storage buckets: league-data (the site's JSON, readable by
--   members only) and league-exports (raw CSV backups, no client access)
--
-- Comments are identified by the id build.py already computes for every vote
-- comment: "<round id>|<spotify uri>|<voter id>". Nothing here copies the
-- comment text; it lives in the season JSON in league-data.
--
-- Access model: every table has row level security on. A signed-in Google
-- account that hasn't claimed an invite can see nothing but its own
-- membership row (which doesn't exist yet). The secret key used by
-- scripts/publish.py and scripts/invites.py bypasses these rules, so it must
-- never be put in the site.

-- ---------------------------------------------------------------- tables

create table if not exists public.players (
  competitor_id text primary key,
  name          text not null
);

create table if not exists public.members (
  user_id       uuid primary key references auth.users (id) on delete cascade,
  competitor_id text not null unique references public.players (competitor_id),
  role          text not null default 'member' check (role in ('member', 'admin')),
  created_at    timestamptz not null default now(),
  inbox_seen_at timestamptz                -- last time they opened the header inbox
);
-- For a project set up before inbox_seen_at existed (the create above
-- skips an existing table); supabase/migrations/2026-09-23_inbox_seen.sql
-- does the same for the live project.
alter table public.members add column if not exists inbox_seen_at timestamptz;

create table if not exists public.invites (
  code          text primary key,
  competitor_id text not null references public.players (competitor_id),
  created_at    timestamptz not null default now(),
  claimed_by    uuid references auth.users (id) on delete set null,
  claimed_at    timestamptz
);

create table if not exists public.comment_votes (
  comment_id text not null,
  user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
  value      smallint not null check (value in (-1, 1)),
  created_at timestamptz not null default now(),
  primary key (comment_id, user_id)
);

-- The original 6 quick reactions are stored by name ('fire', 'heart', ...);
-- anything picked from the round page's searchable emoji picker is stored
-- as the emoji character itself (site/emoji-data.js has ~1,900 of them),
-- so the bound below is a length limit, not a fixed list. A project set up
-- from this file gets that straight away; an existing one needs the
-- migration in supabase/migrations/ that widens this same constraint.
create table if not exists public.comment_reactions (
  comment_id text not null,
  user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
  reaction   text not null check (char_length(reaction) between 1 and 32),
  created_at timestamptz not null default now(),
  primary key (comment_id, user_id, reaction)
);

create table if not exists public.comment_replies (
  id         bigint generated always as identity primary key,
  comment_id text not null,
  user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
  body       text not null check (char_length(btrim(body)) between 1 and 2000),
  created_at timestamptz not null default now()
);

-- The site loads one round at a time with comment_id LIKE '<round id>|%'.
create index if not exists comment_votes_prefix     on public.comment_votes     (comment_id text_pattern_ops);
create index if not exists comment_reactions_prefix on public.comment_reactions (comment_id text_pattern_ops);
create index if not exists comment_replies_prefix   on public.comment_replies   (comment_id text_pattern_ops);

-- ---------------------------------------------------------------- helpers
-- security definer so they can read members regardless of the caller's
-- own row-level access; search_path pinned so they can't be hijacked.

create or replace function public.is_member()
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.members where user_id = auth.uid());
$$;

create or replace function public.is_admin()
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.members where user_id = auth.uid() and role = 'admin');
$$;

-- Links the signed-in Google account to the invite's player. One use per
-- invite, one player per account, one account per player.
create or replace function public.claim_invite(invite_code text)
returns text language plpgsql security definer set search_path = public as $$
declare
  inv public.invites%rowtype;
  uid uuid := auth.uid();
  existing text;
begin
  if uid is null then
    raise exception 'Sign in first.';
  end if;

  select competitor_id into existing from public.members where user_id = uid;
  if found then
    return existing;               -- already linked; the invite is left alone
  end if;

  select * into inv from public.invites where code = invite_code for update;
  if not found then
    raise exception 'That invite link isn''t valid. Check you copied all of it.';
  end if;
  if inv.claimed_by is not null then
    raise exception 'That invite link has already been used.';
  end if;
  if exists (select 1 from public.members where competitor_id = inv.competitor_id) then
    raise exception 'That player is already linked to a different Google account.';
  end if;

  insert into public.members (user_id, competitor_id) values (uid, inv.competitor_id);
  update public.invites set claimed_by = uid, claimed_at = now() where code = invite_code;
  return inv.competitor_id;
end;
$$;

-- The inbox's "seen up to here" mark. members has no UPDATE policy (a
-- member mustn't change their own role or player), so this is the one way
-- in, and it only ever touches inbox_seen_at on the caller's own row.
create or replace function public.mark_inbox_seen()
returns timestamptz language sql security definer set search_path = public as $$
  update public.members set inbox_seen_at = now() where user_id = auth.uid() returning inbox_seen_at;
$$;

revoke all on function public.mark_inbox_seen() from public, anon;
grant execute on function public.mark_inbox_seen() to authenticated;
revoke all on function public.claim_invite(text) from public, anon;
grant execute on function public.claim_invite(text) to authenticated;
grant execute on function public.is_member() to authenticated;
grant execute on function public.is_admin() to authenticated;

-- ---------------------------------------------------------------- row level security

alter table public.players           enable row level security;
alter table public.members           enable row level security;
alter table public.invites           enable row level security;   -- no policies: secret key only
alter table public.comment_votes     enable row level security;
alter table public.comment_reactions enable row level security;
alter table public.comment_replies   enable row level security;

drop policy if exists "members read players" on public.players;
create policy "members read players" on public.players
  for select to authenticated using (public.is_member());

drop policy if exists "read own or all as member" on public.members;
create policy "read own or all as member" on public.members
  for select to authenticated using (user_id = auth.uid() or public.is_member());

-- votes
drop policy if exists "members read votes" on public.comment_votes;
create policy "members read votes" on public.comment_votes
  for select to authenticated using (public.is_member());
drop policy if exists "members vote as themselves" on public.comment_votes;
create policy "members vote as themselves" on public.comment_votes
  for insert to authenticated with check (public.is_member() and user_id = auth.uid());
drop policy if exists "members change own vote" on public.comment_votes;
create policy "members change own vote" on public.comment_votes
  for update to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid() and public.is_member());
drop policy if exists "members remove own vote" on public.comment_votes;
create policy "members remove own vote" on public.comment_votes
  for delete to authenticated using (user_id = auth.uid());

-- reactions
drop policy if exists "members read reactions" on public.comment_reactions;
create policy "members read reactions" on public.comment_reactions
  for select to authenticated using (public.is_member());
drop policy if exists "members react as themselves" on public.comment_reactions;
create policy "members react as themselves" on public.comment_reactions
  for insert to authenticated with check (public.is_member() and user_id = auth.uid());
drop policy if exists "members remove own reaction" on public.comment_reactions;
create policy "members remove own reaction" on public.comment_reactions
  for delete to authenticated using (user_id = auth.uid());

-- replies: members read all, write as themselves, delete their own; an
-- admin can delete anyone's (moderation). No editing, to keep it simple.
drop policy if exists "members read replies" on public.comment_replies;
create policy "members read replies" on public.comment_replies
  for select to authenticated using (public.is_member());
drop policy if exists "members reply as themselves" on public.comment_replies;
create policy "members reply as themselves" on public.comment_replies
  for insert to authenticated with check (public.is_member() and user_id = auth.uid());
drop policy if exists "delete own reply or any as admin" on public.comment_replies;
create policy "delete own reply or any as admin" on public.comment_replies
  for delete to authenticated using (user_id = auth.uid() or public.is_admin());

-- ---------------------------------------------------------------- submissions on the site
-- The league's real tracks for a round, submitted on pfml.fun; voting stays
-- in Music League. Anonymous even to the admin: a submission row holds no
-- user and no time, and site_submission_owners (who sent which) has no
-- policies at all. supabase/migrations/2026-10-18_site_submissions.sql adds
-- the same to the live project. README, Submissions on the site.

create table if not exists public.site_rounds (
  id         uuid primary key default gen_random_uuid(),
  season_key text not null check (season_key ~ '^season[0-9]+$'),
  name       text not null check (char_length(btrim(name)) between 1 and 120),
  prompt     text not null default '' check (char_length(prompt) <= 2000),
  closes_at  timestamptz not null,
  closed_at  timestamptz,                  -- set when the admin closes it early
  created_at timestamptz not null default now()
);

create table if not exists public.site_submissions (
  id       uuid primary key default gen_random_uuid(),
  round_id uuid not null references public.site_rounds (id) on delete cascade,
  tag      text not null check (tag ~ '^[A-HJ-NP-Z][2-9]$'),
  platform text not null check (platform in ('spotify', 'youtube', 'soundcloud')),
  track    text not null check (
    (platform = 'spotify'    and track ~ '^[A-Za-z0-9]{22}$') or
    (platform = 'youtube'    and track ~ '^[A-Za-z0-9_-]{11}$') or
    (platform = 'soundcloud' and track ~ '^[a-z0-9_-]{1,100}/[a-z0-9_-]{1,200}$')),
  unique (round_id, tag),
  unique (round_id, platform, track)
);

create table if not exists public.site_submission_owners (
  submission_id uuid primary key references public.site_submissions (id) on delete cascade,
  round_id      uuid not null references public.site_rounds (id) on delete cascade,
  user_id       uuid not null references auth.users (id) on delete cascade,
  unique (round_id, user_id)               -- one track per member per round
);

-- Takes a submission, or swaps the track on the caller's existing one (the
-- tag stays, so their Music League note stays right). The round row is
-- locked first, so two submissions at once can't draw the same tag.
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
  if r.closed_at is not null or now() >= r.closes_at then
    raise exception 'Submissions for this round are closed.';
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
  return new_tag;
end;
$$;

-- The caller's own submission for a round, if any: the only way anyone
-- sees which track is theirs.
create or replace function public.my_submission(p_round uuid)
returns table (tag text, platform text, track text)
language sql stable security definer set search_path = public as $$
  select s.tag, s.platform, s.track
    from public.site_submissions s
    join public.site_submission_owners o on o.submission_id = s.id
   where o.round_id = p_round and o.user_id = auth.uid();
$$;

-- Takes the caller's own submission back, while the round is still open.
create or replace function public.withdraw_submission(p_round uuid)
returns void language plpgsql security definer set search_path = public as $$
begin
  if exists (select 1 from public.site_rounds
              where id = p_round and (closed_at is not null or now() >= closes_at)) then
    raise exception 'Submissions for this round are closed.';
  end if;
  delete from public.site_submissions s
   using public.site_submission_owners o
   where o.submission_id = s.id and o.round_id = p_round and o.user_id = auth.uid();
end;
$$;

-- How many tracks are in, for anyone in the league: a number, never who.
create or replace function public.site_submission_count(p_round uuid)
returns integer language sql stable security definer set search_path = public as $$
  select case when public.is_member()
              then (select count(*)::int from public.site_submissions where round_id = p_round)
         end;
$$;

revoke all on function public.submit_track(uuid, text, text) from public, anon;
grant execute on function public.submit_track(uuid, text, text) to authenticated;
revoke all on function public.my_submission(uuid) from public, anon;
grant execute on function public.my_submission(uuid) to authenticated;
revoke all on function public.withdraw_submission(uuid) from public, anon;
grant execute on function public.withdraw_submission(uuid) to authenticated;
revoke all on function public.site_submission_count(uuid) from public, anon;
grant execute on function public.site_submission_count(uuid) to authenticated;

alter table public.site_rounds            enable row level security;
alter table public.site_submissions       enable row level security;
alter table public.site_submission_owners enable row level security;   -- no policies: secret key only

-- Rounds: every member reads them; only the admin opens, edits or closes one.
drop policy if exists "members read site rounds" on public.site_rounds;
create policy "members read site rounds" on public.site_rounds
  for select to authenticated using (public.is_member());
drop policy if exists "admin opens site rounds" on public.site_rounds;
create policy "admin opens site rounds" on public.site_rounds
  for insert to authenticated with check (public.is_admin());
drop policy if exists "admin edits site rounds" on public.site_rounds;
create policy "admin edits site rounds" on public.site_rounds
  for update to authenticated using (public.is_admin()) with check (public.is_admin());
drop policy if exists "admin deletes site rounds" on public.site_rounds;
create policy "admin deletes site rounds" on public.site_rounds
  for delete to authenticated using (public.is_admin());

-- Submissions: nobody, the admin included, reads any until the round has
-- closed; then every member reads them all. No insert, update or delete
-- policies: the functions above are the only way to write.
drop policy if exists "members read a closed round's submissions" on public.site_submissions;
create policy "members read a closed round's submissions" on public.site_submissions
  for select to authenticated using (
    public.is_member() and exists (
      select 1 from public.site_rounds r
       where r.id = round_id and (r.closed_at is not null or now() >= r.closes_at)));

-- Written by scripts/round_playlists.py once a round has closed (the
-- shuffled order, what each track is, its copy on the other service, the
-- playlists); supabase/migrations/2026-10-19_round_playlists.sql adds the
-- same to the live project.
alter table public.site_rounds add column if not exists spotify_playlist text
  check (spotify_playlist ~ '^[A-Za-z0-9]{22}$');
alter table public.site_rounds add column if not exists youtube_playlist text
  check (youtube_playlist ~ '^[A-Za-z0-9_-]{10,64}$');
alter table public.site_rounds add column if not exists playlists_built_at timestamptz;

alter table public.site_submissions add column if not exists position integer
  check (position between 1 and 150);
alter table public.site_submissions add column if not exists title text
  check (char_length(title) <= 300);
alter table public.site_submissions add column if not exists artist text
  check (char_length(artist) <= 300);
alter table public.site_submissions add column if not exists spotify_match text
  check (spotify_match ~ '^[A-Za-z0-9]{22}$');
alter table public.site_submissions add column if not exists youtube_match text
  check (youtube_match ~ '^[A-Za-z0-9_-]{11}$');

-- Repeats within an open round: each submission's fingerprint and the
-- functions that compare a pick against the round without showing it.
-- supabase/migrations/2026-10-23_round_repeats.sql adds the same to the
-- live project. README, Submissions on the site, Repeats in this round.
alter table public.site_submissions add column if not exists fp_song text
  check (fp_song ~ '^[a-z0-9 ]{0,300}$');
alter table public.site_submissions add column if not exists fp_names text[]
  check (cardinality(fp_names) <= 12);
alter table public.site_submissions add column if not exists fp_text text
  check (fp_text ~ '^[a-z0-9 ]{0,600}$');
alter table public.site_submissions add column if not exists fp_for text
  check (char_length(fp_for) <= 320);

-- whether the words of `needle` appear together, in order, in `hay`
create or replace function public.fp_has(hay text, needle text)
returns boolean language sql immutable set search_path = public as $$
  select coalesce(needle, '') <> '' and coalesce(hay, '') <> ''
     and position(' ' || needle || ' ' in ' ' || hay || ' ') > 0;
$$;

-- An artist's name found in free text on its own. A short one-word name
-- ("low", "yes") turns up in too many titles to count.
create or replace function public.fp_name_in(hay text, name text)
returns boolean language sql immutable set search_path = public as $$
  select (char_length(name) >= 4 or position(' ' in name) > 0) and public.fp_has(hay, name);
$$;

create or replace function public.fp_ok(p_song text, p_names text[], p_text text)
returns boolean language sql immutable set search_path = public as $$
  select coalesce(p_song, '') ~ '^[a-z0-9 ]{0,300}$'
     and coalesce(p_text, '') ~ '^[a-z0-9 ]{0,600}$'
     and coalesce(cardinality(p_names), 0) <= 12
     and not exists (select 1 from unnest(coalesce(p_names, '{}'::text[])) n
                      where n is null or n !~ '^[a-z0-9 ]{1,120}$');
$$;

-- Saves the fingerprint for the caller's own submission, while the round is
-- open, and only if it's for the track they have in now.
create or replace function public.describe_submission(p_round uuid, p_platform text, p_track text,
                                                      p_song text, p_names text[], p_text text)
returns void language plpgsql security definer set search_path = public as $$
begin
  if not public.is_member() then
    raise exception 'Only league members can submit.';
  end if;
  if exists (select 1 from public.site_rounds
              where id = p_round and (closed_at is not null or now() >= closes_at)) then
    raise exception 'Submissions for this round are closed.';
  end if;
  if not public.fp_ok(p_song, p_names, p_text) then
    raise exception 'That description of the track can''t be used.';
  end if;
  update public.site_submissions s
     set fp_song = coalesce(p_song, ''), fp_names = coalesce(p_names, '{}'::text[]),
         fp_text = coalesce(p_text, ''), fp_for = s.platform || ':' || s.track
    from public.site_submission_owners o
   where o.submission_id = s.id and o.round_id = p_round and o.user_id = auth.uid()
     and s.platform = p_platform and s.track = p_track;
end;
$$;

-- Whether the caller's own track has its fingerprint (a pick sent before
-- this existed, or from an out-of-date page, doesn't yet).
create or replace function public.my_submission_described(p_round uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.site_submissions s
                   join public.site_submission_owners o on o.submission_id = s.id
                  where o.round_id = p_round and o.user_id = auth.uid()
                    and s.fp_for = s.platform || ':' || s.track);
$$;

-- The strongest kind of repeat between a pick (m_) and one submission (o_),
-- or null: track (the very same), version (same song, same artist), song
-- (same song, another artist), title (same title, but the artist isn't
-- known or it's a one-word title), artist. A title or an artist found in
-- the other's free text counts too. Pure, so it can be tried on its own.
create or replace function public.fp_kind(m_platform text, m_track text, m_song text, m_names text[], m_text text,
                                          o_platform text, o_track text, o_song text, o_names text[], o_text text)
returns text language sql immutable set search_path = public as $$
  select case
    when o_platform = m_platform and o_track = m_track then 'track'
    when (m_song <> '' and m_song = o_song and m_names && o_names)
      or (public.fp_has(m_text, o_song) and exists (select 1 from unnest(o_names) n where public.fp_has(m_text, n)))
      or (public.fp_has(o_text, m_song) and exists (select 1 from unnest(m_names) n where public.fp_has(o_text, n)))
      then 'version'
    when m_song <> '' and m_song = o_song and position(' ' in m_song) > 0
      and cardinality(m_names) > 0 and cardinality(o_names) > 0
      then 'song'
    when (m_song <> '' and m_song = o_song)
      or (position(' ' in o_song) > 0 and public.fp_has(m_text, o_song))
      or (position(' ' in m_song) > 0 and public.fp_has(o_text, m_song))
      then 'title'
    when m_names && o_names
      or exists (select 1 from unnest(o_names) n where public.fp_name_in(m_text, n))
      or exists (select 1 from unnest(m_names) n where public.fp_name_in(o_text, n))
      then 'artist'
  end;
$$;

-- Which kinds of repeat a pick would be in this round. Each other
-- submission counts once, as its strongest kind; one without a fingerprint
-- for its current track can only match as the very same track. The
-- caller's own submission is left out. Kinds only: never which, or whose.
create or replace function public.round_repeats(p_round uuid, p_platform text, p_track text,
                                                p_song text, p_names text[], p_text text)
returns text[] language plpgsql stable security definer set search_path = public as $$
declare
  found text[];
begin
  if not public.is_member() then
    raise exception 'Only league members can check a round.';
  end if;
  if not public.fp_ok(p_song, p_names, p_text) then
    raise exception 'That description of the track can''t be used.';
  end if;
  select coalesce(array_agg(distinct x.kind) filter (where x.kind is not null), '{}'::text[]) into found
    from (select public.fp_kind(p_platform, p_track, coalesce(p_song, ''), coalesce(p_names, '{}'::text[]), coalesce(p_text, ''),
                                s.platform, s.track,
                                case when d.described then s.fp_song else '' end,
                                case when d.described then s.fp_names else '{}'::text[] end,
                                case when d.described then s.fp_text else '' end) as kind
            from public.site_submissions s
            cross join lateral (select s.fp_for is not distinct from s.platform || ':' || s.track as described) d
           where s.round_id = p_round
             and not exists (select 1 from public.site_submission_owners o
                              where o.submission_id = s.id and o.user_id = auth.uid())) x;
  return found;
end;
$$;

revoke all on function public.fp_has(text, text) from public, anon;
revoke all on function public.fp_name_in(text, text) from public, anon;
revoke all on function public.fp_ok(text, text[], text) from public, anon;
revoke all on function public.fp_kind(text, text, text, text[], text, text, text, text, text[], text) from public, anon;
revoke all on function public.describe_submission(uuid, text, text, text, text[], text) from public, anon;
grant execute on function public.describe_submission(uuid, text, text, text, text[], text) to authenticated;
revoke all on function public.my_submission_described(uuid) from public, anon;
grant execute on function public.my_submission_described(uuid) to authenticated;
revoke all on function public.round_repeats(uuid, text, text, text, text[], text) from public, anon;
grant execute on function public.round_repeats(uuid, text, text, text, text[], text) to authenticated;

-- Search answers kept by the search-tracks Edge Function (YouTube's, for a
-- week). Service, text and day only, never who searched; no policies.
-- supabase/migrations/2026-10-19_search_cache.sql adds it to the live project.
create table if not exists public.search_cache (
  service   text not null check (service in ('spotify', 'youtube')),
  query     text not null check (char_length(query) between 1 and 120),
  results   jsonb not null,
  cached_on date not null default current_date,
  primary key (service, query)
);

alter table public.search_cache enable row level security;   -- no policies: secret key only

-- ---------------------------------------------------------------- storage

insert into storage.buckets (id, name, public)
values ('league-data', 'league-data', false)
on conflict (id) do update set public = false;

insert into storage.buckets (id, name, public)
values ('league-exports', 'league-exports', false)
on conflict (id) do update set public = false;

-- Members can read the site's JSON. Nobody can write through the site;
-- scripts/publish.py writes with the secret key. league-exports has no
-- policy at all, so only the secret key can touch it.
drop policy if exists "members read league data" on storage.objects;
create policy "members read league data" on storage.objects
  for select to authenticated using (bucket_id = 'league-data' and public.is_member());
