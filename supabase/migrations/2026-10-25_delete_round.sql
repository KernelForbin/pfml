-- Deleting a round from the Commissioner page (README, Deleting a round).
-- Run once in the Supabase SQL Editor for the live project, after
-- 2026-10-25_extras.sql. Safe to re-run. supabase/schema.sql has the same at
-- its end, for a fresh install.
--
-- Asked for 2026-10-25, after four test rounds from 2026-10-18/19 had to be
-- deleted by hand in the SQL Editor. The user's call: the admin only, and
-- only a round that was never really played. No new table. The admin's old
-- direct delete policy goes, so these functions are the one way to delete a
-- round: that policy would have deleted any round, the real Round 7 too.

-- ---------------------------------------------------------------- deleting a round

drop policy if exists "admin deletes site rounds" on public.site_rounds;

-- Why a round can't be deleted, or null when it can. One rule for the list
-- and the delete. A round the league really played never qualifies: one
-- voted on the site, one in a season set up on the site (Seasons removes
-- those), one still taking tracks, one with playlists, or one more than one
-- player sent tracks to. What's left is an empty round or a test.
create or replace function public.site_round_delete_problem(p_round uuid)
returns text language sql stable security definer set search_path = public as $$
  select case
    when r.id is null then 'That round doesn''t exist.'
    when r.votes_on_site or exists (select 1 from public.site_seasons s where s.key = r.season_key)
      then 'A round in a season played on the site is removed under Seasons, before it opens.'
    when r.closed_at is null and r.closes_at > now()
      then 'This round is still taking tracks. Close it first.'
    when r.playlists_built_at is not null or r.spotify_playlist is not null or r.youtube_playlist is not null
      then 'This round has playlists, so it was played. It can''t be deleted.'
    when (select count(distinct o.user_id) from public.site_submission_owners o where o.round_id = r.id) > 1
      then 'More than one player sent tracks to this round, so it was played. It can''t be deleted.'
    when exists (select 1 from public.site_votes v where v.round_id = r.id)
      then 'This round has votes, so it was played. It can''t be deleted.'
  end
  from (select 1) one
  left join public.site_rounds r on r.id = p_round;
$$;

-- For the admin's Commissioner page: the rounds that can be deleted, with
-- how many tracks each would take with it.
create or replace function public.deletable_site_rounds()
returns table (round_id uuid, tracks int)
language plpgsql stable security definer set search_path = public as $$
begin
  if not public.is_admin() then
    raise exception 'Only the admin can delete a round.';
  end if;
  return query
    select r.id, (select count(*)::int from public.site_submissions s where s.round_id = r.id)
      from public.site_rounds r
     where public.site_round_delete_problem(r.id) is null;
end;
$$;

-- The admin deletes one. The round is locked first, so nothing changes it
-- between the check and the delete. Its tracks and anything else tied to it
-- go with it (on delete cascade). Returns its name.
create or replace function public.delete_site_round(p_round uuid)
returns text language plpgsql security definer set search_path = public as $$
declare
  problem text;
  gone text;
begin
  if not public.is_admin() then
    raise exception 'Only the admin can delete a round.';
  end if;
  perform 1 from public.site_rounds where id = p_round for update;
  problem := public.site_round_delete_problem(p_round);
  if problem is not null then
    raise exception '%', problem;
  end if;
  delete from public.site_rounds where id = p_round returning name into gone;
  return gone;
end;
$$;

revoke all on function public.site_round_delete_problem(uuid) from public, anon, authenticated;
revoke all on function public.deletable_site_rounds() from public, anon;
grant execute on function public.deletable_site_rounds() to authenticated;
revoke all on function public.delete_site_round(uuid) from public, anon;
grant execute on function public.delete_site_round(uuid) to authenticated;
