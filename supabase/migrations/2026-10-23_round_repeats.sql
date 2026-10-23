-- Repeats within an open round (README, Submissions on the site, Repeats
-- in this round). Run once in the Supabase SQL Editor for the live project,
-- after 2026-10-19_round_playlists.sql. Safe to re-run. supabase/schema.sql
-- has the same, for a fresh install.
--
-- The Submit page warns when a pick repeats one already in the round: the
-- exact track, the same song by the same artist, the same song by someone
-- else, a song with the same title, or the same artist. Tracks stay unread
-- until the round closes, so the page can't compare them itself. Instead
-- each submission keeps a fingerprint (its song title and artist names,
-- folded to plain lowercase words, and for a YouTube or SoundCloud pick the
-- video's title and channel), and round_repeats() answers which kinds of
-- repeat a pick would be: kinds only, never which track or whose.
-- fp_for names the track the fingerprint was made for, so one left behind
-- by a swap from an out-of-date page is ignored, not misread.
-- No new table, so the 2026-10-30 grant change doesn't apply.

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
