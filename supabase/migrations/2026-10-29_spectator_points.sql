-- Spectators' podium points (README, Spectators' podium points). Run once
-- in the Supabase SQL Editor for the live project, after
-- 2026-10-29_season_roles.sql. Safe to re-run. supabase/schema.sql has
-- the same before its storage section, for a fresh install.
--
-- Asked for 2026-10-29: a Spectator earns points for backing the
-- podium: 3 for each point they gave a round's winner, 2 for 2nd
-- place, 1 for 3rd. The stats build scores it (build.py,
-- PODIUM_POINTS) and the round's results show it; the database only
-- has to say who was a Spectator in each finished round, so the
-- export publish.py reads now carries that. Nothing else changes.

-- ---------------------------------------------------------------- Spectators' podium points

-- Finished rounds voted here, for publish.py, as before, and now: each
-- round's Spectators, by player id.
create or replace function public.site_rounds_export()
returns jsonb language sql stable security definer set search_path = public as $$
  select jsonb_build_object(
    'rounds', coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', r.id, 'season_key', r.season_key, 'name', r.name, 'prompt', r.prompt,
        'created_at', r.opens_at, 'voting_ended_at', coalesce(r.voting_closed_at, r.voting_closes_at),
        'spotify_playlist', r.spotify_playlist, 'point_budget', r.point_budget,
        'nonvoters_keep_points', r.nonvoters_keep_points,
        -- who voted without a track (README, Spectators' podium points)
        'spectators', coalesce((
          select jsonb_agg(p.competitor_id order by p.competitor_id)
            from public.site_season_players p
           where p.season_key = r.season_key
             and public.site_round_role(r.id, p.competitor_id) = 'spectator'), '[]'::jsonb),
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
