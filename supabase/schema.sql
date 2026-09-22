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
