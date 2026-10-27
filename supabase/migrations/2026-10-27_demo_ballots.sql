-- The round demo's practice ballot, kept in the database (README, Round
-- demo). Run once in the Supabase SQL Editor for the live project, after
-- 2026-10-27_ballot_drafts.sql. Safe to re-run. supabase/schema.sql has the
-- same before its storage section, for a fresh install.
--
-- Asked for 2026-10-27: comments made on the demo on a phone didn't show
-- on the computer, since the demo kept its practice ballot in the browser.
-- The demo copies a round voted in Music League (Round 7), which can't take
-- a real draft or ballot (save_ballot_draft and cast_ballot refuse any round
-- not voting here), so the practice ballot gets a table of its own: one row
-- per member, holding their practice draft and practice ballot for the
-- round the demo copies. It never touches site_votes or
-- site_ballot_drafts, so it counts for nothing, anywhere.
--
-- Row-level security on, no policies, no API grants: the three functions
-- are the only way in, and each reads or writes the caller's own row only.

-- ---------------------------------------------------------------- demo ballots

create table if not exists public.site_demo_ballots (
  user_id        uuid primary key references auth.users (id) on delete cascade,
  source_round   uuid not null references public.site_rounds (id) on delete cascade,
  draft          jsonb not null default '[]'::jsonb,
  draft_saved_at timestamptz,
  ballot         jsonb not null default '[]'::jsonb,   -- the practice ballot "submitted"
  check (jsonb_typeof(draft) = 'array' and jsonb_array_length(draft) <= 150),
  check (jsonb_typeof(ballot) = 'array' and jsonb_array_length(ballot) <= 150)
);

alter table public.site_demo_ballots enable row level security;
revoke all on table public.site_demo_ballots from anon, authenticated;

-- What's wrong with a practice ballot or draft, or null: an array of at
-- most 150 tracks of the round, each once, with whole points and a comment
-- of at most 2000 characters. The page holds the voting rules; this keeps
-- the row to what the demo can make. Stable, not pure: it reads the round.
create or replace function public.demo_ballot_problem(p_round uuid, p_ballot jsonb)
returns text language sql stable security definer set search_path = public as $$
  select case
    when jsonb_typeof(p_ballot) is distinct from 'array' or jsonb_array_length(p_ballot) > 150
      then 'The ballot doesn''t add up. Reload the page and try again.'
    when exists (select 1 from jsonb_array_elements(p_ballot) e
                  where jsonb_typeof(e) <> 'object'
                     or jsonb_typeof(e->'points') is distinct from 'number'
                     -- a case, so the cast only ever sees a number
                     or case when jsonb_typeof(e->'points') = 'number'
                             then (e->>'points')::numeric not between -100 and 100
                                  or (e->>'points')::numeric <> trunc((e->>'points')::numeric) end
                     or not exists (select 1 from public.site_submissions s
                                     where s.round_id = p_round and s.id::text = e->>'submission'))
      then 'The ballot doesn''t add up. Reload the page and try again.'
    when (select count(distinct e->>'submission') from jsonb_array_elements(p_ballot) e) <> jsonb_array_length(p_ballot)
      then 'The ballot doesn''t add up. Reload the page and try again.'
    when exists (select 1 from jsonb_array_elements(p_ballot) e where char_length(coalesce(e->>'comment', '')) > 2000)
      then 'A comment can be at most 2000 characters.'
  end;
$$;

-- Saves the caller's practice draft, or their practice ballot when
-- p_submit, for the round the demo copies; a different round than the one
-- kept starts afresh. Returns when it was saved.
create or replace function public.save_demo_ballot(p_round uuid, p_ballot jsonb, p_submit boolean)
returns timestamptz language plpgsql security definer set search_path = public as $$
declare
  uid uuid := auth.uid();
  problem text;
  clean jsonb;
  at timestamptz := clock_timestamp();
begin
  if not public.is_member() then
    raise exception 'Only league members can vote.';
  end if;
  if not exists (select 1 from public.site_rounds where id = p_round) then
    raise exception 'That round doesn''t exist.';
  end if;
  problem := public.demo_ballot_problem(p_round, p_ballot);
  if problem is not null then
    raise exception '%', problem;
  end if;
  select coalesce(jsonb_agg(jsonb_build_object('submission', e->>'submission', 'points', (e->>'points')::int,
                                               'comment', btrim(coalesce(e->>'comment', '')))), '[]'::jsonb)
    into clean
    from jsonb_array_elements(p_ballot) e;

  insert into public.site_demo_ballots (user_id, source_round) values (uid, p_round)
  on conflict (user_id) do nothing;
  update public.site_demo_ballots
     set draft = case when source_round = p_round then draft else '[]'::jsonb end,
         ballot = case when source_round = p_round then ballot else '[]'::jsonb end,
         draft_saved_at = case when source_round = p_round then draft_saved_at end,
         source_round = p_round
   where user_id = uid;
  if p_submit then
    update public.site_demo_ballots set ballot = clean, draft = clean, draft_saved_at = at where user_id = uid;
  else
    update public.site_demo_ballots set draft = clean, draft_saved_at = at where user_id = uid;
  end if;
  return at;
end;
$$;

-- The caller's practice draft and ballot for the round the demo copies:
-- no row when there's none.
create or replace function public.my_demo_ballot(p_round uuid)
returns table (draft jsonb, draft_saved_at timestamptz, ballot jsonb)
language sql stable security definer set search_path = public as $$
  select d.draft, d.draft_saved_at, d.ballot
    from public.site_demo_ballots d
   where d.user_id = auth.uid() and d.source_round = p_round and public.is_member();
$$;

revoke all on function public.demo_ballot_problem(uuid, jsonb) from public, anon, authenticated;
revoke all on function public.save_demo_ballot(uuid, jsonb, boolean) from public, anon;
grant execute on function public.save_demo_ballot(uuid, jsonb, boolean) to authenticated;
revoke all on function public.my_demo_ballot(uuid) from public, anon;
grant execute on function public.my_demo_ballot(uuid) to authenticated;
