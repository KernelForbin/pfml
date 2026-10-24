-- Who has submitted to a site round (README, Submissions on the site, Who's
-- in). Run once in the Supabase SQL Editor for the live project, after
-- 2026-10-23_round_repeats_fix.sql. Safe to re-run. supabase/schema.sql has
-- the same, for a fresh install. No new table, so the 2026-10-30 grant
-- change doesn't apply.
--
-- The Submit page and the Home banner show "x/20 submitted", and the Submit
-- page shows who has and who hasn't, with avatars (the user's call,
-- 2026-10-23, knowing a member could pair this with the repeat warning to
-- guess roughly what someone sent). It says who has a track in, never which
-- track: player ids only, in id order, so not even the order they sent them.

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
