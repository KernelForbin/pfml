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
  check (char_length(fp_song) <= 300 and fp_song ~ '^[a-z0-9 ]*$');
alter table public.site_submissions add column if not exists fp_names text[]
  check (cardinality(fp_names) <= 12);
alter table public.site_submissions add column if not exists fp_text text
  check (char_length(fp_text) <= 600 and fp_text ~ '^[a-z0-9 ]*$');
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
  select char_length(coalesce(p_song, '')) <= 300 and coalesce(p_song, '') ~ '^[a-z0-9 ]*$'
     and char_length(coalesce(p_text, '')) <= 600 and coalesce(p_text, '') ~ '^[a-z0-9 ]*$'
     and coalesce(cardinality(p_names), 0) <= 12
     and not exists (select 1 from unnest(coalesce(p_names, '{}'::text[])) n
                      where n is null or char_length(n) > 120 or n !~ '^[a-z0-9 ]+$');
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

-- Who has submitted to a round: player ids only, never which track.
-- supabase/migrations/2026-10-23_round_submitters.sql adds the same to
-- the live project. README, Submissions on the site, Who's in.
create or replace function public.site_round_submitters(p_round uuid)
returns setof text language sql stable security definer set search_path = public as $$
  select m.competitor_id
    from public.site_submission_owners o
    join public.members m on m.user_id = o.user_id
   where o.round_id = p_round and public.is_member()
   order by m.competitor_id;
$$;

revoke all on function public.site_round_submitters(uuid) from public, anon;
grant execute on function public.site_round_submitters(uuid) to authenticated;

-- The admin's view of unused invite links: who has one and when it was
-- made, never the link. supabase/migrations/2026-10-24_admin_invite_status.sql
-- adds the same to the live project. README, Admin status.
create or replace function public.admin_invite_status()
returns table (competitor_id text, made_at timestamptz)
language plpgsql stable security definer set search_path = public as $$
begin
  if not public.is_admin() then
    raise exception 'Only the admin can see invite status.';
  end if;
  return query
    select i.competitor_id, max(i.created_at)
      from public.invites i
     where i.claimed_by is null
     group by i.competitor_id
     order by i.competitor_id;
end;
$$;

revoke all on function public.admin_invite_status() from public, anon;
grant execute on function public.admin_invite_status() to authenticated;

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

-- ---------------------------------------------------------------- voting on the site
-- supabase/migrations/2026-10-25_site_voting.sql adds the same to the live
-- project. README, Voting on the site.

-- Which rounds vote here, when voting closes, and their rules. The default
-- rules are Season 3's, measured from the exports 2026-10-25: 19 points, at
-- most 5 on one track, every point spent; a submitter who doesn't vote
-- scores 0 (the user's call, 2026-10-25; Music League let them keep it).
alter table public.site_rounds add column if not exists votes_on_site boolean not null default false;
alter table public.site_rounds add column if not exists voting_closes_at timestamptz;
alter table public.site_rounds add column if not exists voting_closed_at timestamptz;   -- the admin closed it early
alter table public.site_rounds add column if not exists point_budget smallint not null default 19
  check (point_budget between 1 and 100);
alter table public.site_rounds add column if not exists max_per_track smallint not null default 5
  check (max_per_track between 1 and 100);
alter table public.site_rounds add column if not exists nonvoters_keep_points boolean not null default false;

alter table public.site_rounds drop constraint if exists site_rounds_voting_shape;
alter table public.site_rounds add constraint site_rounds_voting_shape check (
  max_per_track <= point_budget
  and votes_on_site = (voting_closes_at is not null)
  and (voting_closes_at is null or voting_closes_at > closes_at));

-- Site voting is chosen when a round is opened and never changes after; the
-- rules can change only while submissions are still open.
create or replace function public.site_rounds_voting_fixed()
returns trigger language plpgsql set search_path = public as $$
begin
  if new.votes_on_site is distinct from old.votes_on_site then
    raise exception 'Voting on the site is chosen when a round is opened, and can''t be changed after.';
  end if;
  if (new.point_budget, new.max_per_track, new.nonvoters_keep_points)
       is distinct from (old.point_budget, old.max_per_track, old.nonvoters_keep_points)
     and (old.closed_at is not null or now() >= old.closes_at) then
    raise exception 'The voting rules can''t change once submissions have closed.';
  end if;
  return new;
end;
$$;

drop trigger if exists site_rounds_voting_fixed on public.site_rounds;
create trigger site_rounds_voting_fixed before update on public.site_rounds
  for each row execute function public.site_rounds_voting_fixed();

-- One row per track a voter gave points or a comment to. No policies: the
-- functions below are the only way in, and nobody reads anyone's votes
-- until voting has closed.
create table if not exists public.site_votes (
  round_id      uuid not null references public.site_rounds (id) on delete cascade,
  submission_id uuid not null references public.site_submissions (id) on delete cascade,
  user_id       uuid not null references auth.users (id) on delete cascade,
  points        smallint not null check (points between 0 and 100),
  comment       text not null default '' check (char_length(comment) <= 2000),
  cast_at       timestamptz not null default now(),
  primary key (submission_id, user_id),
  check (points > 0 or char_length(btrim(comment)) > 0)
);
create index if not exists site_votes_round on public.site_votes (round_id, user_id);

alter table public.site_votes enable row level security;
revoke all on table public.site_votes from anon, authenticated;

-- Where a round is: 'submitting', then 'voting' and 'finished' for a round
-- that votes here, or 'closed' for one that votes in Music League.
create or replace function public.site_round_phase(p_round uuid)
returns text language sql stable security definer set search_path = public as $$
  select case
    when r.closed_at is null and now() < r.closes_at then 'submitting'
    when not r.votes_on_site then 'closed'
    when r.voting_closed_at is null and now() < r.voting_closes_at then 'voting'
    else 'finished' end
    from public.site_rounds r where r.id = p_round;
$$;

-- What's wrong with a ballot, or null when it's fine: the points on each
-- track, and whether each is the voter's own. Pure, so
-- tests/test_live_voting.py runs it against the real database.
create or replace function public.ballot_problem(p_budget int, p_max int, p_points int[], p_own boolean[])
returns text language sql immutable set search_path = public as $$
  select case
    when coalesce(cardinality(p_points), 0) <> coalesce(cardinality(p_own), 0)
      then 'The ballot doesn''t add up. Reload the page and try again.'
    when exists (select 1 from unnest(p_points) p where p is null or p < 0)
      then 'Points can''t be negative.'
    when exists (select 1 from unnest(p_points) p where p > p_max)
      then format('At most %s points on one track.', p_max)
    when exists (select 1 from unnest(p_points, p_own) as t(p, own) where own and p > 0)
      then 'You can''t give points to your own track.'
    when coalesce((select sum(p) from unnest(p_points) p), 0) <> p_budget
      then format('Spend exactly %s points. This ballot has %s.', p_budget,
                  coalesce((select sum(p) from unnest(p_points) p), 0))
  end;
$$;

-- The caller's ballot, replacing any earlier one, while voting is open:
-- [{"submission": "<id>", "points": 3, "comment": "..."}]. Only someone
-- with a track in the round votes; a comment can go on any track, their own
-- included, with or without points.
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
end;
$$;

-- The caller's own ballot, to change it while voting is open.
create or replace function public.my_ballot(p_round uuid)
returns table (submission_id uuid, points smallint, comment text)
language sql stable security definer set search_path = public as $$
  select v.submission_id, v.points, v.comment
    from public.site_votes v
   where v.round_id = p_round and v.user_id = auth.uid() and public.is_member();
$$;

-- Who has voted: player ids only, never how.
create or replace function public.site_round_voters(p_round uuid)
returns setof text language sql stable security definer set search_path = public as $$
  select distinct m.competitor_id
    from public.site_votes v
    join public.members m on m.user_id = v.user_id
   where v.round_id = p_round and public.is_member()
   order by m.competitor_id;
$$;

-- Once voting has closed, and only then: every track's submitter and
-- score. points is what counts; earned is what voters gave it, which a
-- submitter who didn't vote loses unless the round says otherwise.
create or replace function public.site_round_results(p_round uuid)
returns table (submission_id uuid, competitor_id text, points int, earned int, voted boolean)
language sql stable security definer set search_path = public as $$
  select s.id, m.competitor_id,
         case when exists (select 1 from public.site_votes v where v.round_id = p_round and v.user_id = o.user_id)
                   or r.nonvoters_keep_points
              then coalesce(t.total, 0) else 0 end,
         coalesce(t.total, 0),
         exists (select 1 from public.site_votes v where v.round_id = p_round and v.user_id = o.user_id)
    from public.site_submissions s
    join public.site_rounds r on r.id = s.round_id
    left join public.site_submission_owners o on o.submission_id = s.id
    left join public.members m on m.user_id = o.user_id
    left join (select v.submission_id, sum(v.points)::int as total
                 from public.site_votes v where v.round_id = p_round
                group by v.submission_id) t on t.submission_id = s.id
   where s.round_id = p_round and public.is_member()
     and public.site_round_phase(p_round) = 'finished';
$$;

-- Once voting has closed: every vote and comment, with who gave it.
create or replace function public.site_round_votes(p_round uuid)
returns table (submission_id uuid, voter_id text, points smallint, comment text)
language sql stable security definer set search_path = public as $$
  select v.submission_id, m.competitor_id, v.points, v.comment
    from public.site_votes v
    join public.members m on m.user_id = v.user_id
   where v.round_id = p_round and public.is_member()
     and public.site_round_phase(p_round) = 'finished'
   order by v.submission_id, v.points desc, m.competitor_id;
$$;

revoke all on function public.site_rounds_voting_fixed() from public, anon, authenticated;
revoke all on function public.ballot_problem(int, int, int[], boolean[]) from public, anon, authenticated;
revoke all on function public.site_round_phase(uuid) from public, anon;
grant execute on function public.site_round_phase(uuid) to authenticated;
revoke all on function public.cast_ballot(uuid, jsonb) from public, anon;
grant execute on function public.cast_ballot(uuid, jsonb) to authenticated;
revoke all on function public.my_ballot(uuid) from public, anon;
grant execute on function public.my_ballot(uuid) to authenticated;
revoke all on function public.site_round_voters(uuid) from public, anon;
grant execute on function public.site_round_voters(uuid) to authenticated;
revoke all on function public.site_round_results(uuid) from public, anon;
grant execute on function public.site_round_results(uuid) to authenticated;
revoke all on function public.site_round_votes(uuid) from public, anon;
grant execute on function public.site_round_votes(uuid) to authenticated;

-- ---------------------------------------------------------------- site rounds in the stats
-- supabase/migrations/2026-10-25_site_rounds_export.sql adds the same to the
-- live project. README, Site rounds in the stats.

create or replace function public.site_rounds_export()
returns jsonb language sql stable security definer set search_path = public as $$
  select jsonb_build_object(
    'rounds', coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', r.id, 'season_key', r.season_key, 'name', r.name, 'prompt', r.prompt,
        'created_at', r.created_at, 'voting_ended_at', coalesce(r.voting_closed_at, r.voting_closes_at),
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
      ) order by r.created_at)
        from public.site_rounds r
       where r.votes_on_site and public.site_round_phase(r.id) = 'finished'), '[]'::jsonb),
    'players', coalesce((select jsonb_object_agg(p.competitor_id, p.name) from public.players p), '{}'::jsonb));
$$;

revoke all on function public.site_rounds_export() from public, anon, authenticated;
grant execute on function public.site_rounds_export() to service_role;

-- ---------------------------------------------------------------- reminders
-- supabase/migrations/2026-10-25_reminders.sql adds the same to the live
-- project. README, Reminders.

-- One row per phone or browser a member turned notifications on in: what
-- the push service needs to reach it. The endpoint belongs to whoever
-- turned it on last on that device.
create table if not exists public.push_subscriptions (
  endpoint   text primary key check (endpoint ~ '^https://' and char_length(endpoint) <= 1000),
  user_id    uuid not null references auth.users (id) on delete cascade,
  p256dh     text not null check (p256dh ~ '^[A-Za-z0-9_-]{80,100}$'),
  auth       text not null check (auth ~ '^[A-Za-z0-9_-]{16,32}$'),
  created_at timestamptz not null default now()
);
create index if not exists push_subscriptions_user on public.push_subscriptions (user_id);
alter table public.push_subscriptions enable row level security;
revoke all on table public.push_subscriptions from anon, authenticated;

-- Email reminders, for when they're switched on: on unless the member turns
-- them off. No row means on.
create table if not exists public.reminder_settings (
  user_id  uuid primary key references auth.users (id) on delete cascade,
  email_on boolean not null default true
);
alter table public.reminder_settings enable row level security;
revoke all on table public.reminder_settings from anon, authenticated;

-- Every reminder sent, so none goes twice: claimed before it's sent.
create table if not exists public.reminders_sent (
  round_id uuid not null references public.site_rounds (id) on delete cascade,
  kind     text not null check (kind in ('round_open', 'playlist_ready',
                                         'vote_halfway', 'vote_5h', 'vote_2h', 'vote_1h')),
  user_id  uuid not null references auth.users (id) on delete cascade,
  channel  text not null check (channel in ('push', 'email')),
  sent_at  timestamptz not null default now(),
  primary key (round_id, kind, user_id, channel)
);
alter table public.reminders_sent enable row level security;
revoke all on table public.reminders_sent from anon, authenticated;

-- A member turns notifications on (or again) on this device.
create or replace function public.save_push_subscription(p_endpoint text, p_p256dh text, p_auth text)
returns void language plpgsql security definer set search_path = public as $$
begin
  if not public.is_member() then
    raise exception 'Only league members can turn on notifications.';
  end if;
  insert into public.push_subscriptions (endpoint, user_id, p256dh, auth)
  values (p_endpoint, auth.uid(), p_p256dh, p_auth)
  on conflict (endpoint) do update
     set user_id = excluded.user_id, p256dh = excluded.p256dh, auth = excluded.auth, created_at = now();
  if (select count(*) from public.push_subscriptions where user_id = auth.uid()) > 10 then
    raise exception 'That''s more devices than notifications can go to. Turn them off on one you don''t use.';
  end if;
end;
$$;

-- A member turns notifications off on this device.
create or replace function public.remove_push_subscription(p_endpoint text)
returns void language sql security definer set search_path = public as $$
  delete from public.push_subscriptions where endpoint = p_endpoint and user_id = auth.uid();
$$;

-- The caller's own devices, for "Send me a test": nobody else's.
create or replace function public.my_push_subscriptions()
returns table (endpoint text, p256dh text, auth text)
language sql stable security definer set search_path = public as $$
  select s.endpoint, s.p256dh, s.auth from public.push_subscriptions s
   where s.user_id = auth.uid() and public.is_member();
$$;

-- Email reminders on or off, for the caller (the switch isn't on the site
-- until email is).
create or replace function public.set_email_reminders(p_on boolean)
returns void language plpgsql security definer set search_path = public as $$
begin
  if not public.is_member() then
    raise exception 'Only league members have reminders.';
  end if;
  insert into public.reminder_settings (user_id, email_on) values (auth.uid(), p_on)
  on conflict (user_id) do update set email_on = excluded.email_on;
end;
$$;

-- What's due now, claimed so no other run sends it: for the sender only
-- (send-reminders, with the secret key). p_channels is what the sender can
-- send ('push', and 'email' once it has an email key). Who gets what:
--   round_open      everyone, for a round opened in the last 6 hours (so one
--                   open before reminders existed isn't announced late)
--   playlist_ready  everyone, for playlists built in the last 12 hours
--   vote_*          a round voted on the site, during voting: only players
--                   with a track in it who haven't voted. Of halfway, 5, 2
--                   and 1 hour left, only the latest that's passed, and none
--                   from before voting opened, so a late run never sends a
--                   pile and a short window never says "5 hours" with 3 left.
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
     where r.phase = 'submitting' and r.created_at > now() - interval '6 hours'
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
  wanted as (
    select t.round_id, t.kind, t.user_id, 'push'::text as channel from targets t
     where 'push' = any(p_channels)
       and exists (select 1 from public.push_subscriptions s where s.user_id = t.user_id)
    union all
    select t.round_id, t.kind, t.user_id, 'email' from targets t
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

-- A device the push service says is gone (404 or 410): the sender forgets it.
create or replace function public.forget_push_endpoint(p_endpoint text)
returns void language sql security definer set search_path = public as $$
  delete from public.push_subscriptions where endpoint = p_endpoint;
$$;

-- Email's unsubscribe link (later): turns email off for that member.
create or replace function public.email_reminders_off(p_user uuid)
returns void language sql security definer set search_path = public as $$
  insert into public.reminder_settings (user_id, email_on) values (p_user, false)
  on conflict (user_id) do update set email_on = false;
$$;

revoke all on function public.save_push_subscription(text, text, text) from public, anon;
grant execute on function public.save_push_subscription(text, text, text) to authenticated;
revoke all on function public.remove_push_subscription(text) from public, anon;
grant execute on function public.remove_push_subscription(text) to authenticated;
revoke all on function public.my_push_subscriptions() from public, anon;
grant execute on function public.my_push_subscriptions() to authenticated;
revoke all on function public.set_email_reminders(boolean) from public, anon;
grant execute on function public.set_email_reminders(boolean) to authenticated;
revoke all on function public.reminders_claim(text[]) from public, anon, authenticated;
grant execute on function public.reminders_claim(text[]) to service_role;
revoke all on function public.forget_push_endpoint(text) from public, anon, authenticated;
grant execute on function public.forget_push_endpoint(text) to service_role;
revoke all on function public.email_reminders_off(uuid) from public, anon, authenticated;
grant execute on function public.email_reminders_off(uuid) to service_role;

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
