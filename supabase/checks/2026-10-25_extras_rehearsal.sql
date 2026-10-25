-- A rehearsal of the commissioner extras (allowed services, submitter
-- notes, the repeat rule, announcements), run by the real database and then
-- undone: nothing it does is kept. Run it in the Supabase SQL Editor after
-- supabase/migrations/2026-10-25_extras.sql (README, Commissioner extras).
-- It always ends in an error, on purpose, because an error rolls everything
-- back:
--
--   "Rehearsal passed: 16 checks held. Nothing was kept."  every rule held
--   "Rehearsal FAILED: ..."                               says which didn't
--
-- It plays the admin and the first two members who are neither admin nor
-- commissioner (B and C), signed in as them and as the 'authenticated' role,
-- as the site would, in made-up seasons (season97 to season99), a made-up
-- Season 3 round and a made-up announcement, with made-up devices
-- (https://push.example.invalid/...). Nothing is sent: claiming only
-- records. All of it is rolled back.

do $$
declare
  a uuid; ca text;
  b uuid; cb text;
  c uuid; cc text;
  r_yt uuid; r_song uuid; r_artist uuid; r_ml uuid;
  tag_a text;
  aid uuid;
  n int;
  ex jsonb;
  checks int := 0;
begin
  select user_id, competitor_id into a, ca from public.members where role = 'admin' order by created_at limit 1;
  select user_id, competitor_id into b, cb from public.members where role = 'member' order by created_at, user_id limit 1;
  select user_id, competitor_id into c, cc from public.members where role = 'member' order by created_at, user_id offset 1 limit 1;
  if a is null or c is null then raise exception 'Rehearsal FAILED: it needs the admin and two other members'; end if;

  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.create_site_season(jsonb_build_object('key', 'season99', 'name', 'Rehearsal YouTube Only',
    'services', jsonb_build_array('youtube'), 'first_playlist_at', now() + interval '1 day',
    'rounds', jsonb_build_array(jsonb_build_object('name', 'YT')), 'players', jsonb_build_array(ca, cb, cc)));
  perform public.create_site_season(jsonb_build_object('key', 'season98', 'name', 'Rehearsal Block Song',
    'repeat_rule', 'block_song', 'first_playlist_at', now() + interval '1 day',
    'rounds', jsonb_build_array(jsonb_build_object('name', 'SONG')), 'players', jsonb_build_array(ca, cb, cc)));
  perform public.create_site_season(jsonb_build_object('key', 'season97', 'name', 'Rehearsal Block Artist',
    'repeat_rule', 'block_artist', 'first_playlist_at', now() + interval '1 day',
    'rounds', jsonb_build_array(jsonb_build_object('name', 'ARTIST')), 'players', jsonb_build_array(ca, cb, cc)));
  execute 'reset role';
  select id into r_yt from public.site_rounds where season_key = 'season99';
  select id into r_song from public.site_rounds where season_key = 'season98';
  select id into r_artist from public.site_rounds where season_key = 'season97';

  -- 1. Services: a YouTube-only round refuses Spotify, takes YouTube.
  execute 'set local role authenticated';
  begin
    perform public.submit_track(r_yt, 'spotify', repeat('A', 22));
    raise exception 'Rehearsal FAILED: a Spotify track went into a YouTube-only round';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'This round takes YouTube tracks only.%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;
  tag_a := public.submit_track(r_yt, 'youtube', 'yyyyyyyyyy1');
  if tag_a is null then raise exception 'Rehearsal FAILED: the YouTube track didn''t go in'; end if;
  checks := checks + 1;

  -- 2. A round that blocks repeats takes tracks only with their description.
  begin
    perform public.submit_track(r_song, 'youtube', 'ssssssssss1');
    raise exception 'Rehearsal FAILED: a track went into a blocking round without its description';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'This round checks repeats as a track goes in.%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;
  perform public.submit_described(r_song, 'youtube', 'ssssssssss1', 'shining star', array['earth wind and fire'], '');
  perform public.submit_described(r_artist, 'youtube', 'aaaaaaaaaa1', 'shining star', array['earth wind and fire'], '');
  execute 'reset role';
  if not exists (select 1 from public.site_submissions where round_id = r_song and fp_song = 'shining star'
                   and fp_for = platform || ':' || track) then
    raise exception 'Rehearsal FAILED: the description wasn''t saved with the track';
  end if;
  checks := checks + 1;

  -- 3. B: the same song (another upload) is refused where songs are
  --    blocked; the same artist with another song isn't, there; both are
  --    refused where artists are blocked.
  perform set_config('request.jwt.claim.sub', b::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', b, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  begin
    perform public.submit_described(r_song, 'youtube', 'ssssssssss2', 'shining star', array['earth wind and fire'], '');
    raise exception 'Rehearsal FAILED: the same song went into a round that blocks it';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'This round doesn''t take a song that''s already in it.%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;
  perform public.submit_described(r_song, 'youtube', 'ssssssssss3', 'september', array['earth wind and fire'], '');
  checks := checks + 1;
  begin
    perform public.submit_described(r_artist, 'youtube', 'aaaaaaaaaa2', 'september', array['earth wind and fire'], '');
    raise exception 'Rehearsal FAILED: the same artist went into a round that blocks it';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'This round doesn''t take an artist who''s already in it.%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  checks := checks + 1;

  -- 4. The warning round (YouTube only, the default rule) takes the same
  --    song: it only warns.
  perform public.submit_described(r_yt, 'youtube', 'yyyyyyyyyy2', 'shining star', array['earth wind and fire'], '');
  checks := checks + 1;

  -- 5. Notes: B's own, while open; not on A's track; not too long.
  select tag into tag_a from public.my_submission(r_yt) limit 1;
  perform public.set_submission_note(r_yt, tag_a, '  Heard this live once.  ');
  begin
    perform public.set_submission_note(r_yt, tag_a, repeat('x', 1001));
    raise exception 'Rehearsal FAILED: a 1001-character note went in';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
  end;
  execute 'reset role';
  if (select note from public.site_submissions where round_id = r_yt and tag = tag_a) <> 'Heard this live once.' then
    raise exception 'Rehearsal FAILED: B''s note wasn''t saved, trimmed';
  end if;
  checks := checks + 1;
  perform set_config('request.jwt.claim.sub', c::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', c, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.set_submission_note(r_yt, tag_a, 'Not mine to write');
  execute 'reset role';
  if (select note from public.site_submissions where round_id = r_yt and tag = tag_a) <> 'Heard this live once.' then
    raise exception 'Rehearsal FAILED: C changed B''s note';
  end if;
  checks := checks + 1;

  -- 6. No notes in a round voted in Music League.
  insert into public.site_rounds (season_key, name, closes_at) values ('season3', 'Rehearsal ML round', now() + interval '1 day')
  returning id into r_ml;
  execute 'set local role authenticated';
  begin
    perform public.set_submission_note(r_ml, 'A2', 'hi');
    raise exception 'Rehearsal FAILED: a note went on a round voted in Music League';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
    if sqlerrm not like 'Notes are for rounds voted on the site.%' then raise exception 'Rehearsal FAILED: got "%"', sqlerrm; end if;
  end;
  execute 'reset role';
  checks := checks + 1;

  -- 7. The export carries a finished round's notes.
  update public.site_rounds set closed_at = now(), voting_closed_at = now() where id = r_yt;
  ex := public.site_rounds_export();
  if not exists (select 1 from jsonb_array_elements(ex->'rounds') x, jsonb_array_elements(x->'submissions') s
                  where x->>'id' = r_yt::text and s->>'note' = 'Heard this live once.') then
    raise exception 'Rehearsal FAILED: the export should carry the note';
  end if;
  checks := checks + 1;

  -- 8. Announcements: a member can't post; the admin can; the sender finds
  --    it once, for everyone with a device who wants it; it can come down.
  execute 'set local role authenticated';
  begin
    perform public.post_announcement('From a member');
    raise exception 'Rehearsal FAILED: a member posted an announcement';
  exception when others then
    if sqlerrm like 'Rehearsal FAILED%' then raise; end if;
  end;
  checks := checks + 1;
  -- C turns announcements off
  perform public.set_notification_choice('announcements', false);
  if (select announcements from public.my_notification_choices()) then
    raise exception 'Rehearsal FAILED: C''s announcements switch didn''t turn off';
  end if;
  execute 'reset role';
  checks := checks + 1;
  insert into public.push_subscriptions (endpoint, user_id, p256dh, auth) values
    ('https://push.example.invalid/b', b, repeat('B', 87), repeat('b', 22)),
    ('https://push.example.invalid/c', c, repeat('C', 87), repeat('c', 22));
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  aid := public.post_announcement('  Season 4 starts Monday.  ');
  execute 'reset role';
  create temp table told on commit drop as select * from public.announcements_claim() x where x.announcement_id = aid;
  if not exists (select 1 from told where user_id = b and body = 'Season 4 starts Monday.')
     or exists (select 1 from told where user_id = c)
     or exists (select 1 from public.announcements_claim() x where x.announcement_id = aid) then
    raise exception 'Rehearsal FAILED: the announcement should reach B (not C, who turned it off), once';
  end if;
  checks := checks + 1;
  execute 'set local role authenticated';
  perform public.delete_announcement(aid);
  execute 'reset role';
  if exists (select 1 from public.site_announcements where id = aid) then
    raise exception 'Rehearsal FAILED: the announcement didn''t come down';
  end if;
  checks := checks + 1;

  raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;
end $$;
