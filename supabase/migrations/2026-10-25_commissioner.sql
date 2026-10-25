-- Commissioners (README, Commissioners). Run once in the Supabase SQL Editor
-- for the live project, after 2026-10-25_notification_choices.sql. Safe to
-- re-run. supabase/schema.sql has the same, for a fresh install.
--
-- Asked for 2026-10-25: a commissioner runs the league's rounds (opens
-- them, edits them, moves and closes deadlines) alongside the admin, who
-- always counts as one. Only the admin makes someone a commissioner, and
-- only the admin deletes a round. No new table, so no grants to think about.

-- ---------------------------------------------------------------- commissioners

alter table public.members drop constraint if exists members_role_check;
alter table public.members add constraint members_role_check check (role in ('member', 'commissioner', 'admin'));

-- The admin or a commissioner: who may open and edit site rounds.
create or replace function public.is_commissioner()
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.members where user_id = auth.uid() and role in ('commissioner', 'admin'));
$$;

-- The admin makes a member a commissioner, or a member again. Never the
-- admin's own row, and only someone who has joined the site.
create or replace function public.set_commissioner(p_competitor text, p_on boolean)
returns void language plpgsql security definer set search_path = public as $$
declare
  current_role_ text;
begin
  if not public.is_admin() then
    raise exception 'Only the admin can choose commissioners.';
  end if;
  if p_on is null then
    raise exception 'Say whether they''re a commissioner.';
  end if;
  select role into current_role_ from public.members where competitor_id = p_competitor;
  if current_role_ is null then
    raise exception 'That player hasn''t joined the site.';
  end if;
  if current_role_ = 'admin' then
    raise exception 'The admin is always a commissioner.';
  end if;
  update public.members set role = case when p_on then 'commissioner' else 'member' end
   where competitor_id = p_competitor;
end;
$$;

drop policy if exists "admin opens site rounds" on public.site_rounds;
drop policy if exists "commissioners open site rounds" on public.site_rounds;
create policy "commissioners open site rounds" on public.site_rounds
  for insert to authenticated with check (public.is_commissioner());
drop policy if exists "admin edits site rounds" on public.site_rounds;
drop policy if exists "commissioners edit site rounds" on public.site_rounds;
create policy "commissioners edit site rounds" on public.site_rounds
  for update to authenticated using (public.is_commissioner()) with check (public.is_commissioner());

-- What anyone signed in (the admin included) can't do to a round's times:
-- reopen submissions or voting once they've closed, move a deadline into
-- the past, or move a closed round to another season. Closing early takes
-- the database's clock, not the browser's. Scripts and the SQL Editor (not
-- the 'authenticated' role) are left alone, so a mistake can still be fixed
-- by hand.
create or replace function public.site_rounds_times_guard()
returns trigger language plpgsql set search_path = public as $$
declare
  subs_closed boolean;
  votes_closed boolean;
begin
  if current_user <> 'authenticated' then
    return new;
  end if;
  if tg_op = 'INSERT' then
    if new.closes_at <= now() then
      raise exception 'The closing time has to be in the future.';
    end if;
    new.closed_at := null;
    new.voting_closed_at := null;
    return new;
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

drop trigger if exists site_rounds_times_guard on public.site_rounds;
create trigger site_rounds_times_guard before insert or update on public.site_rounds
  for each row execute function public.site_rounds_times_guard();

revoke all on function public.is_commissioner() from public, anon;
grant execute on function public.is_commissioner() to authenticated;
revoke all on function public.set_commissioner(text, boolean) from public, anon;
grant execute on function public.set_commissioner(text, boolean) to authenticated;
