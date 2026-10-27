-- Ballot drafts: a voter's points and comments saved as they go, before
-- the ballot is whole (README, Voting on the site, Drafts). Run once in the
-- Supabase SQL Editor for the live project, after
-- 2026-10-26_track_details.sql. Safe to re-run. supabase/schema.sql has the
-- same before its storage section, for a fresh install.
--
-- Asked for 2026-10-27: points and comments save on their own as a member
-- gives them, so leaving the page loses nothing, and they follow the member
-- between their phone and their computer. Save keeps their place; Submit,
-- only once every point is given, is what counts (cast_ballot, unchanged).
-- A draft never counts: it isn't in site_votes, so it isn't in the voted
-- count, the results, the reminders or the stats.
--
-- The table has row-level security on, no policies and no API grants, so
-- the two functions are the only way in: a member reads and writes their
-- own draft, nobody else's, and only while the round's voting is open.

-- ---------------------------------------------------------------- ballot drafts

create table if not exists public.site_ballot_drafts (
  round_id   uuid not null references public.site_rounds (id) on delete cascade,
  user_id    uuid not null references auth.users (id) on delete cascade,
  ballot     jsonb not null,            -- [{submission, points, comment}], as cast_ballot takes it
  saved_at   timestamptz not null default now(),
  primary key (round_id, user_id)
);

alter table public.site_ballot_drafts enable row level security;
revoke all on table public.site_ballot_drafts from anon, authenticated;

-- What's wrong with a ballot that isn't finished yet, or null when it's
-- fine: ballot_problem's rules, except that it may have fewer points than
-- the budget, never more. Pure, so tests/test_live_ballot_drafts.py runs it
-- against the real database.
create or replace function public.draft_problem(p_budget int, p_max int, p_down int, p_down_max int,
                                                p_points int[], p_own boolean[])
returns text language sql immutable set search_path = public as $$
  select case
    when coalesce(cardinality(p_points), 0) <> coalesce(cardinality(p_own), 0)
      then 'The ballot doesn''t add up. Reload the page and try again.'
    when exists (select 1 from unnest(p_points) p where p is null)
      then 'The ballot doesn''t add up. Reload the page and try again.'
    when exists (select 1 from unnest(p_points) p where p < 0) and coalesce(p_down, 0) = 0
      then 'This round has no downvotes.'
    when exists (select 1 from unnest(p_points) p where p > p_max)
      then format('At most %s points on one track.', p_max)
    when exists (select 1 from unnest(p_points) p where p < -p_down_max)
      then format('At most %s downvotes on one track.', p_down_max)
    when exists (select 1 from unnest(p_points, p_own) as t(p, own) where own and p <> 0)
      then 'You can''t give points to your own track.'
    when coalesce((select sum(p) from unnest(p_points) p where p > 0), 0) > p_budget
      then format('At most %s points in all. This ballot has %s.', p_budget,
                  coalesce((select sum(p) from unnest(p_points) p where p > 0), 0))
    when coalesce((select -sum(p) from unnest(p_points) p where p < 0), 0) > p_down
      then format('At most %s downvotes in all. This ballot has %s.', p_down,
                  coalesce((select -sum(p) from unnest(p_points) p where p < 0), 0))
  end;
$$;

-- Saves the caller's draft for a round, replacing any earlier one, while
-- its voting is open; only a player with a track in it. The same checks as
-- cast_ballot but for the total. Returns when it was saved.
create or replace function public.save_ballot_draft(p_round uuid, p_ballot jsonb)
returns timestamptz language plpgsql security definer set search_path = public as $$
declare
  uid uuid := auth.uid();
  r public.site_rounds%rowtype;
  mine uuid[];
  sids uuid[];
  pts int[];
  cmts text[];
  problem text;
  at timestamptz := clock_timestamp();
begin
  if not public.is_member() then
    raise exception 'Only league members can vote.';
  end if;
  select * into r from public.site_rounds where id = p_round;
  if not found then
    raise exception 'That round doesn''t exist.';
  end if;
  if public.site_round_phase(p_round) is distinct from 'voting' then
    raise exception 'Voting for this round isn''t open.';
  end if;
  select array_agg(o.submission_id) into mine from public.site_submission_owners o
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

  problem := public.draft_problem(r.point_budget, r.max_per_track, r.downvotes, r.max_down_per_track, pts,
                                  array(select s = any(mine) from unnest(sids) s));
  if problem is not null then
    raise exception '%', problem;
  end if;

  insert into public.site_ballot_drafts (round_id, user_id, ballot, saved_at)
  values (p_round, uid,
          (select coalesce(jsonb_agg(jsonb_build_object('submission', t.sid, 'points', t.p, 'comment', t.c)), '[]'::jsonb)
             from unnest(sids, pts, cmts) as t(sid, p, c)
            where t.p <> 0 or t.c <> ''),
          at)
  on conflict (round_id, user_id) do update set ballot = excluded.ballot, saved_at = excluded.saved_at;
  return at;
end;
$$;

-- The caller's own draft for a round, while its voting is open: no row
-- when there's none.
create or replace function public.my_ballot_draft(p_round uuid)
returns table (ballot jsonb, saved_at timestamptz)
language sql stable security definer set search_path = public as $$
  select d.ballot, d.saved_at
    from public.site_ballot_drafts d
   where d.round_id = p_round and d.user_id = auth.uid() and public.is_member()
     and public.site_round_phase(p_round) = 'voting';
$$;

revoke all on function public.draft_problem(int, int, int, int, int[], boolean[]) from public, anon, authenticated;
revoke all on function public.save_ballot_draft(uuid, jsonb) from public, anon;
grant execute on function public.save_ballot_draft(uuid, jsonb) to authenticated;
revoke all on function public.my_ballot_draft(uuid) from public, anon;
grant execute on function public.my_ballot_draft(uuid) to authenticated;
