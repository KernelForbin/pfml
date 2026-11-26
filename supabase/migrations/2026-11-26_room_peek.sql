-- Live now on Home (asked 2026-11-26; README, The live room): while
-- someone's DJing, Home shows what's playing, who's on the decks and who's
-- in the crowd. Run once in the Supabase SQL Editor, after
-- 2026-11-25_live_room.sql. The same as the block in schema.sql.

-- What Home shows of the room: the time on the database's clock, what's
-- playing, the decks in turn order and the crowd, or null when nothing is.
-- Looking doesn't put the caller in the room, and it moves nothing along
-- (room_here does that for the pages in the room), so it leaves out what
-- room_advance would clear: anyone silent for 90 seconds, a track whose
-- time is up, and a room nobody's in.
create or replace function public.room_peek()
returns jsonb language plpgsql stable security definer set search_path = public as $$
declare
  p public.room_plays%rowtype;
begin
  if not public.is_member() then
    raise exception 'Only league members can see the room.';
  end if;
  select pl.* into p
    from public.room_state s join public.room_plays pl on pl.id = s.play_id
   where s.id = 1 and now() < pl.started_at + make_interval(secs => coalesce(pl.seconds, 600));
  if not found or not exists (select 1 from public.room_presence where last_seen > now() - interval '90 seconds') then
    return null;
  end if;
  return jsonb_build_object(
    'now', now(),
    'play', jsonb_build_object(
      'dj', public.room_who(p.user_id), 'platform', p.platform, 'track', p.track,
      'title', p.title, 'artist', p.artist, 'seconds', p.seconds, 'started_at', p.started_at,
      'awesome', (select count(*) from public.room_votes v where v.play_id = p.id and v.vote = 1),
      'lame', (select count(*) from public.room_votes v where v.play_id = p.id and v.vote = -1)),
    'djs', coalesce((select jsonb_agg(public.room_who(d.user_id) order by d.seq)
                       from public.room_djs d join public.room_presence x on x.user_id = d.user_id
                      where x.last_seen > now() - interval '90 seconds'), '[]'::jsonb),
    'crowd', coalesce((select jsonb_agg(public.room_who(x.user_id) order by public.room_who(x.user_id))
                         from public.room_presence x
                        where x.last_seen > now() - interval '90 seconds'), '[]'::jsonb));
end;
$$;

revoke all on function public.room_peek() from public, anon;
grant execute on function public.room_peek() to authenticated;
