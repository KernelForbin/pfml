-- Submissions on pfml.fun (README, Submissions on the site).
-- Run once in the Supabase SQL Editor for the live project. Safe to re-run.
-- supabase/schema.sql has the same blocks, for a fresh install.
--
-- The league submits its real tracks (Spotify, YouTube or SoundCloud) on the
-- site, and still enters a placeholder in Music League, where voting stays.
-- Each submission gets a tag (like Q7); the submitter puts it in their Music
-- League note, so voters can match placeholders to tracks.
--
-- Anonymous even to the admin: a submission row holds no user and no time.
-- Who sent it is in site_submission_owners, which has row level security on
-- and no policies, so nothing signed in can read it; only the secret key can.
-- Every write goes through the functions below.

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
