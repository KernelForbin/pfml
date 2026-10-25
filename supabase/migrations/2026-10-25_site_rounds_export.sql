-- Site-voted rounds into the season stats (README, Site rounds in the
-- stats). Run once in the Supabase SQL Editor for the live project, after
-- 2026-10-25_site_voting.sql. Safe to re-run. supabase/schema.sql has the
-- same, for a fresh install. No new table, so the 2026-10-30 grant change
-- doesn't apply.
--
-- scripts/publish.py calls this with the secret key and writes what it gets
-- into data/<season>/site_rounds.json, which build.py reads next to Music
-- League's CSVs. It hands over a round only once its voting has closed, so
-- who sent which track can't leave the database any earlier, whatever a
-- script does. Nobody signed in can call it: members see results through
-- site_round_results() and site_round_votes(), on the same condition.

-- ---------------------------------------------------------------- site rounds in the stats

create or replace function public.site_rounds_export()
returns jsonb language sql stable security definer set search_path = public as $$
  select jsonb_build_object(
    'rounds', coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', r.id, 'season_key', r.season_key, 'name', r.name, 'prompt', r.prompt,
        'created_at', r.created_at, 'voting_ended_at', coalesce(r.voting_closed_at, r.voting_closes_at),
        'spotify_playlist', r.spotify_playlist, 'point_budget', r.point_budget,
        'nonvoters_keep_points', r.nonvoters_keep_points,
        'submissions', coalesce((
          select jsonb_agg(jsonb_build_object(
            'id', s.id, 'tag', s.tag, 'platform', s.platform, 'track', s.track,
            'title', s.title, 'artist', s.artist, 'spotify_match', s.spotify_match,
            'position', s.position, 'submitter', m.competitor_id) order by s.tag)
            from public.site_submissions s
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
      ) order by r.created_at)
        from public.site_rounds r
       where r.votes_on_site and public.site_round_phase(r.id) = 'finished'), '[]'::jsonb),
    'players', coalesce((select jsonb_object_agg(p.competitor_id, p.name) from public.players p), '{}'::jsonb));
$$;

revoke all on function public.site_rounds_export() from public, anon, authenticated;
grant execute on function public.site_rounds_export() to service_role;
