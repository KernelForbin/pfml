-- A submitter's note: hidden until the results unless they choose to show
-- it while people vote (README, Commissioner extras, Notes). Run once in the
-- Supabase SQL Editor for the live project, after
-- 2026-10-25_delete_round.sql. Safe to re-run. supabase/schema.sql has the
-- same at its end, for a fresh install.
--
-- Asked for 2026-10-25: a switch on each note, "Show it to voters while they
-- vote", off by default. Off, the note shows only once voting has closed,
-- with the submitter's name. On, voters see it with the track, without the
-- name, while they vote.
--
-- Rows of site_submissions are readable by every member once a round
-- closes (they're the ballot), so a note there can't be hidden during voting
-- by the page alone: anyone could ask for the column. So notes move to a
-- table of their own, site_submission_notes, whose row-level rule shows a
-- note only when it may be seen, and the old column goes. The new table is
-- granted explicitly (Supabase's 2026-10-30 change). It replaces
-- my_submission, set_submission_note (now with the switch) and
-- site_rounds_export.

-- ---------------------------------------------------------------- notes shown when chosen

create table if not exists public.site_submission_notes (
  submission_id uuid primary key references public.site_submissions (id) on delete cascade,
  round_id      uuid not null references public.site_rounds (id) on delete cascade,
  note          text not null check (char_length(note) between 1 and 1000),
  in_voting     boolean not null default false   -- shown to voters while they vote
);
create index if not exists site_submission_notes_round on public.site_submission_notes (round_id);

alter table public.site_submission_notes enable row level security;
drop policy if exists "members read the notes they may see" on public.site_submission_notes;
create policy "members read the notes they may see" on public.site_submission_notes
  for select to authenticated using (
    public.is_member() and (
      public.site_round_phase(round_id) = 'finished'
      or (in_voting and public.site_round_phase(round_id) = 'voting')));
revoke all on table public.site_submission_notes from anon, authenticated;
grant select on table public.site_submission_notes to authenticated;

-- Any note already written moves over (hidden until the results, the new
-- default), and the old column goes, so it can't be read during voting.
do $$
begin
  if exists (select 1 from information_schema.columns
              where table_schema = 'public' and table_name = 'site_submissions' and column_name = 'note') then
    insert into public.site_submission_notes (submission_id, round_id, note)
    select id, round_id, btrim(note) from public.site_submissions where btrim(note) <> ''
    on conflict (submission_id) do nothing;
    alter table public.site_submissions drop column note;
  end if;
end $$;

-- The caller's own tracks for a round, with their notes and the switch.
drop function if exists public.my_submission(uuid);
create or replace function public.my_submission(p_round uuid)
returns table (tag text, platform text, track text, note text, note_in_voting boolean)
language sql stable security definer set search_path = public as $$
  select s.tag, s.platform, s.track, coalesce(n.note, ''), coalesce(n.in_voting, false)
    from public.site_submissions s
    join public.site_submission_owners o on o.submission_id = s.id
    left join public.site_submission_notes n on n.submission_id = s.id
   where o.round_id = p_round and o.user_id = auth.uid()
   order by s.tag;
$$;

-- The note on one of the caller's own tracks, and whether voters see it
-- while they vote, while submissions are open, in a round voted on the site.
-- An empty note clears it. Someone else's tag changes nothing.
drop function if exists public.set_submission_note(uuid, text, text);
create or replace function public.set_submission_note(p_round uuid, p_tag text, p_note text, p_in_voting boolean)
returns void language plpgsql security definer set search_path = public as $$
declare
  sid uuid;
  body text := btrim(coalesce(p_note, ''));
begin
  if not public.is_member() then
    raise exception 'Only league members can submit.';
  end if;
  if not exists (select 1 from public.site_rounds where id = p_round and votes_on_site) then
    raise exception 'Notes are for rounds voted on the site.';
  end if;
  if exists (select 1 from public.site_rounds
              where id = p_round and (closed_at is not null or now() >= closes_at)) then
    raise exception 'Submissions for this round are closed.';
  end if;
  if char_length(body) > 1000 then
    raise exception 'A note can be at most 1000 characters.';
  end if;
  select s.id into sid
    from public.site_submissions s
    join public.site_submission_owners o on o.submission_id = s.id
   where o.round_id = p_round and o.user_id = auth.uid() and s.tag = p_tag;
  if sid is null then
    return;
  end if;
  if body = '' then
    delete from public.site_submission_notes where submission_id = sid;
  else
    insert into public.site_submission_notes (submission_id, round_id, note, in_voting)
    values (sid, p_round, body, coalesce(p_in_voting, false))
    on conflict (submission_id) do update set note = excluded.note, in_voting = excluded.in_voting;
  end if;
end;
$$;

-- What publish.py fetches once a round's voting has closed, now with each
-- track's note from its new table (the build shows it as Music League's
-- submitter comment).
create or replace function public.site_rounds_export()
returns jsonb language sql stable security definer set search_path = public as $$
  select jsonb_build_object(
    'rounds', coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', r.id, 'season_key', r.season_key, 'name', r.name, 'prompt', r.prompt,
        'created_at', r.opens_at, 'voting_ended_at', coalesce(r.voting_closed_at, r.voting_closes_at),
        'spotify_playlist', r.spotify_playlist, 'point_budget', r.point_budget,
        'nonvoters_keep_points', r.nonvoters_keep_points,
        'submissions', coalesce((
          select jsonb_agg(jsonb_build_object(
            'id', s.id, 'tag', s.tag, 'platform', s.platform, 'track', s.track,
            'title', s.title, 'artist', s.artist, 'spotify_match', s.spotify_match,
            'position', s.position, 'note', coalesce(n.note, ''), 'submitter', m.competitor_id) order by s.tag)
            from public.site_submissions s
            left join public.site_submission_notes n on n.submission_id = s.id
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
      ) order by r.opens_at, r.created_at)
        from public.site_rounds r
       where r.votes_on_site and public.site_round_phase(r.id) = 'finished'), '[]'::jsonb),
    'players', coalesce((select jsonb_object_agg(p.competitor_id, p.name) from public.players p), '{}'::jsonb),
    'seasons', coalesce((select jsonb_object_agg(s.key, s.name) from public.site_seasons s), '{}'::jsonb));
$$;

revoke all on function public.my_submission(uuid) from public, anon;
grant execute on function public.my_submission(uuid) to authenticated;
revoke all on function public.set_submission_note(uuid, text, text, boolean) from public, anon;
grant execute on function public.set_submission_note(uuid, text, text, boolean) to authenticated;
revoke all on function public.site_rounds_export() from public, anon, authenticated;
grant execute on function public.site_rounds_export() to service_role;
