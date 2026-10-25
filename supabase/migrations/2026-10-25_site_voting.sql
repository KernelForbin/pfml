-- Voting on the site (README, Voting on the site). Run once in the Supabase
-- SQL Editor for the live project, after 2026-10-24_admin_invite_status.sql.
-- Safe to re-run. supabase/schema.sql has the same, for a fresh install.
--
-- Built 2026-10-25 and switched off: nothing here changes a round that
-- already exists. A round has site voting only if it was opened with
-- votes_on_site, and the trigger refuses to turn that on (or off) later, so
-- Round 7, and every round before it, can never get it. The Submit page's
-- switch (PFML.siteVoting in account.js) stays off until the user says.
--
-- The new table, site_votes, is only reached through the security definer
-- functions below, so it gets no API grants (the 2026-10-30 change), and
-- they're revoked outright in case the project still hands them out.

-- ---------------------------------------------------------------- voting on the site

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
