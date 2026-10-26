-- Each track's length, album and year, shown on the round page (README,
-- Listening on the round page). Run once in the Supabase SQL Editor for the
-- live project, after 2026-10-25_note_toggle.sql. Safe to re-run.
-- supabase/schema.sql has the same at its end, for a fresh install.
--
-- Asked for 2026-10-26. scripts/round_playlists.py looks every track up when
-- it builds a round's playlists and now keeps what it finds: the submitted
-- track's own length, and the album and year from Spotify. It writes them
-- with the secret key, like the titles; members read them through the
-- existing "closed round" policy. No new table. Nothing here says who
-- submitted anything.

-- ---------------------------------------------------------------- track details

alter table public.site_submissions add column if not exists seconds integer
  check (seconds between 1 and 86400);
alter table public.site_submissions add column if not exists album text
  check (char_length(album) <= 300);
alter table public.site_submissions add column if not exists year smallint
  check (year between 1000 and 2100);
