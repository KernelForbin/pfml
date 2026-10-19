-- The round playlists (README, Submissions on the site, stage 2).
-- Run once in the Supabase SQL Editor for the live project, after
-- 2026-10-18_site_submissions.sql. Safe to re-run. supabase/schema.sql has
-- the same columns, for a fresh install.
--
-- scripts/round_playlists.py writes these with the secret key once a round
-- has closed: the shuffled order, what each track is, its copy on the other
-- service, and the two playlists. Members read them through the existing
-- "closed round" policy. Nothing here says who submitted anything.

alter table public.site_rounds add column if not exists spotify_playlist text
  check (spotify_playlist ~ '^[A-Za-z0-9]{22}$');
alter table public.site_rounds add column if not exists youtube_playlist text
  check (youtube_playlist ~ '^[A-Za-z0-9_-]{10,64}$');
alter table public.site_rounds add column if not exists playlists_built_at timestamptz;

alter table public.site_submissions add column if not exists position integer
  check (position between 1 and 150);
alter table public.site_submissions add column if not exists title text
  check (char_length(title) <= 300);
alter table public.site_submissions add column if not exists artist text
  check (char_length(artist) <= 300);
alter table public.site_submissions add column if not exists spotify_match text
  check (spotify_match ~ '^[A-Za-z0-9]{22}$');
alter table public.site_submissions add column if not exists youtube_match text
  check (youtube_match ~ '^[A-Za-z0-9_-]{11}$');
