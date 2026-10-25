-- More than one song a round, and downvotes (README, More songs and
-- downvotes). Run once in the Supabase SQL Editor for the live project, after
-- 2026-10-25_seasons.sql. Safe to re-run. supabase/schema.sql has the same at
-- its end, for a fresh install.
--
-- Commissioners, stage 3 (asked 2026-10-25). A season set up on the site
-- chooses how many songs each player sends a round (1 to 5) and how many
-- downvotes each voter may give (none, or up to 20, with a cap on one song).
-- Every round that already exists keeps 1 song and no downvotes, so nothing
-- about Season 3 or Round 7 changes. Downvotes are optional, up to the
-- limit; upvotes are spent in full, as before: measured from the Season 1
-- exports, every ballot spent all 16 upvotes and only 15 of 316 used any
-- downvotes, each time all 5.
--
-- No new table. It replaces submit_track, my_submission_described,
-- cast_ballot, site_round_results, site_round_finish_early,
-- site_rounds_voting_fixed, create_site_season, update_site_season and
-- add_site_season_round, and adds a ballot_problem that knows downvotes
-- (the old one stays for the record). In schema.sql the earlier
-- definitions stay above, as the earlier migrations ran them, and these,
-- at the end, are the ones that stand.

-- ---------------------------------------------------------------- more songs and downvotes

alter table public.site_seasons add column if not exists songs_per_round smallint not null default 1;
alter table public.site_seasons add column if not exists downvotes smallint not null default 0;
alter table public.site_seasons add column if not exists max_down_per_track smallint not null default 0;
alter table public.site_seasons drop constraint if exists site_seasons_more_songs;
alter table public.site_seasons add constraint site_seasons_more_songs check (
  songs_per_round between 1 and 5 and downvotes between 0 and 20 and max_down_per_track between 0 and downvotes);

alter table public.site_rounds add column if not exists songs_per_round smallint not null default 1;
alter table public.site_rounds add column if not exists downvotes smallint not null default 0;
alter table public.site_rounds add column if not exists max_down_per_track smallint not null default 0;
alter table public.site_rounds drop constraint if exists site_rounds_more_songs;
alter table public.site_rounds add constraint site_rounds_more_songs check (
  songs_per_round between 1 and 5 and downvotes between 0 and 20 and max_down_per_track between 0 and downvotes);

-- A player may now have several tracks in a round (up to its
-- songs_per_round, which submit_track holds); the index keeps finding them
-- quick. The one-per-player rule was written without a name, so it's found
-- by what it is (the table's only unique constraint) rather than a guessed
-- name, which would miss silently.
do $$
declare c record;
begin
  for c in select conname from pg_constraint
            where conrelid = 'public.site_submission_owners'::regclass and contype = 'u' loop
    execute format('alter table public.site_submission_owners drop constraint %I', c.conname);
  end loop;
end $$;
create index if not exists site_submission_owners_round_user on public.site_submission_owners (round_id, user_id);

-- A vote can be a downvote now; a row is still either points or a comment.
-- Its checks were written without names too: all of them go, by kind, and
-- come back named, the comment's length included.
do $$
declare c record;
begin
  for c in select conname from pg_constraint
            where conrelid = 'public.site_votes'::regclass and contype = 'c' loop
    execute format('alter table public.site_votes drop constraint %I', c.conname);
  end loop;
end $$;
alter table public.site_votes add constraint site_votes_points_range check (points between -20 and 100);
alter table public.site_votes add constraint site_votes_comment_length check (char_length(comment) <= 2000);
alter table public.site_votes add constraint site_votes_points_or_comment check (points <> 0 or char_length(btrim(comment)) > 0);

-- The rules, as before, plus: how many songs a round takes can't change
-- once it has opened, and the downvotes freeze with the other voting rules
-- when submissions close.
create or replace function public.site_rounds_voting_fixed()
returns trigger language plpgsql set search_path = public as $$
begin
  if new.votes_on_site is distinct from old.votes_on_site then
    raise exception 'Voting on the site is chosen when a round is opened, and can''t be changed after.';
  end if;
  if (new.point_budget, new.max_per_track, new.nonvoters_keep_points, new.downvotes, new.max_down_per_track)
       is distinct from (old.point_budget, old.max_per_track, old.nonvoters_keep_points, old.downvotes, old.max_down_per_track)
     and (old.closed_at is not null or now() >= old.closes_at) then
    raise exception 'The voting rules can''t change once submissions have closed.';
  end if;
  if new.songs_per_round is distinct from old.songs_per_round and now() >= old.opens_at then
    raise exception 'How many songs a round takes can''t change once it has opened.';
  end if;
  return new;
end;
$$;

-- What's wrong with a ballot, or null when it's fine, now with downvotes:
-- every upvote spent, downvotes optional up to their limit, each song held
-- to its caps, nothing on your own. Pure, so tests/test_live_voting.py runs
-- it against the real database.
create or replace function public.ballot_problem(p_budget int, p_max int, p_down int, p_down_max int,
                                                 p_points int[], p_own boolean[])
returns text language sql immutable set search_path = public as $$
  select case
    when coalesce(cardinality(p_points), 0) <> coalesce(cardinality(p_own), 0)
      then 'The ballot doesn''t add up. Reload the page and try again.'
    when exists (select 1 from unnest(p_points) p where p is null)
      then 'The ballot doesn''t add up. Reload the page and try again.'
    when exists (select 1 from unnest(p_points) p where p < 0) and coalesce(p_down, 0) = 0
      then 'This round has no downvotes.'
    when exists (select 1 from unnest(p_points) p where p > p_max)
      then format('At most %s points on one track.', p_max)
    when exists (select 1 from unnest(p_points) p where p < -p_down_max)
      then format('At most %s downvotes on one track.', p_down_max)
    when exists (select 1 from unnest(p_points, p_own) as t(p, own) where own and p <> 0)
      then 'You can''t give points to your own track.'
    when coalesce((select sum(p) from unnest(p_points) p where p > 0), 0) <> p_budget
      then format('Spend exactly %s points. This ballot has %s.', p_budget,
                  coalesce((select sum(p) from unnest(p_points) p where p > 0), 0))
    when coalesce((select -sum(p) from unnest(p_points) p where p < 0), 0) > p_down
      then format('At most %s downvotes in all. This ballot has %s.', p_down,
                  coalesce((select -sum(p) from unnest(p_points) p where p < 0), 0))
  end;
$$;

-- Takes a submission, as before, and now up to the round's songs_per_round
-- from each player. With one song a round, sending another still swaps it
-- (the tag stays); with more, a player removes one (withdraw_track) to
-- send another. Closes submissions early once every player has all theirs
-- in (Accelerated, Speedy).
create or replace function public.submit_track(p_round uuid, p_platform text, p_track text)
returns text language plpgsql security definer set search_path = public as $$
declare
  uid uuid := auth.uid();
  r public.site_rounds%rowtype;
  mine uuid;
  have int;
  new_tag text;
begin
  if not public.is_member() then
    raise exception 'Only league members can submit.';
  end if;
  select * into r from public.site_rounds where id = p_round for update;
  if not found then
    raise exception 'That round doesn''t exist.';
  end if;
  if now() < r.opens_at then
    raise exception 'This round hasn''t opened yet.';
  end if;
  if r.closed_at is not null or now() >= r.closes_at then
    raise exception 'Submissions for this round are closed.';
  end if;
  if exists (select 1 from public.site_seasons s where s.key = r.season_key)
     and not exists (select 1 from public.site_season_players p join public.members m on m.competitor_id = p.competitor_id
                      where p.season_key = r.season_key and m.user_id = uid) then
    raise exception 'You aren''t playing this season. Ask a commissioner to add you.';
  end if;
  if not ((p_platform = 'spotify'    and p_track ~ '^[A-Za-z0-9]{22}$') or
          (p_platform = 'youtube'    and p_track ~ '^[A-Za-z0-9_-]{11}$') or
          (p_platform = 'soundcloud' and p_track ~ '^[a-z0-9_-]{1,100}/[a-z0-9_-]{1,200}$')) then
    raise exception 'That isn''t a Spotify, YouTube or SoundCloud track the site can use.';
  end if;

  select count(*) into have from public.site_submission_owners o where o.round_id = p_round and o.user_id = uid;
  -- one song a round: sending again swaps it
  if r.songs_per_round = 1 and have > 0 then
    select o.submission_id into mine from public.site_submission_owners o
     where o.round_id = p_round and o.user_id = uid limit 1;
  end if;

  if exists (select 1 from public.site_submissions s
              where s.round_id = p_round and s.platform = p_platform and s.track = p_track
                and s.id is distinct from mine) then
    raise exception 'Someone has already submitted that track this round.';
  end if;

  if mine is not null then
    update public.site_submissions set platform = p_platform, track = p_track
     where id = mine returning tag into new_tag;
    return new_tag;
  end if;

  if have >= r.songs_per_round then
    raise exception 'You''ve sent all % of your tracks for this round. Remove one to send another.', r.songs_per_round;
  end if;
  if (select count(*) from public.site_submissions where round_id = p_round) >= 150 then
    raise exception 'This round is full.';
  end if;
  loop
    new_tag := substr('ABCDEFGHJKLMNPQRSTUVWXYZ', 1 + floor(random() * 24)::int, 1)
            || (2 + floor(random() * 8)::int)::text;
    exit when not exists (select 1 from public.site_submissions
                           where round_id = p_round and tag = new_tag);
  end loop;
  insert into public.site_submissions (round_id, tag, platform, track)
  values (p_round, new_tag, p_platform, p_track) returning id into mine;
  insert into public.site_submission_owners (submission_id, round_id, user_id)
  values (mine, p_round, uid);
  perform public.site_round_finish_early(p_round);
  return new_tag;
end;
$$;

-- Takes one of the caller's own tracks back, by its tag, while the round is
-- still open.
create or replace function public.withdraw_track(p_round uuid, p_tag text)
returns void language plpgsql security definer set search_path = public as $$
begin
  if exists (select 1 from public.site_rounds
              where id = p_round and (closed_at is not null or now() >= closes_at)) then
    raise exception 'Submissions for this round are closed.';
  end if;
  delete from public.site_submissions s
   using public.site_submission_owners o
   where o.submission_id = s.id and o.round_id = p_round and o.user_id = auth.uid() and s.tag = p_tag;
end;
$$;

-- Whether every one of the caller's tracks in a round has its description
-- (the repeat check's fingerprint).
create or replace function public.my_submission_described(p_round uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select not exists (select 1 from public.site_submissions s
                       join public.site_submission_owners o on o.submission_id = s.id
                      where o.round_id = p_round and o.user_id = auth.uid()
                        and s.fp_for is distinct from s.platform || ':' || s.track);
$$;

-- The caller's ballot, as before, and now: none of their tracks takes
-- points, and the round's downvotes are allowed.
create or replace function public.cast_ballot(p_round uuid, p_ballot jsonb)
returns void language plpgsql security definer set search_path = public as $$
declare
  uid uuid := auth.uid();
  r public.site_rounds%rowtype;
  mine uuid[];
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
  select array_agg(o.submission_id) into mine from public.site_submission_owners o
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

  problem := public.ballot_problem(r.point_budget, r.max_per_track, r.downvotes, r.max_down_per_track, pts,
                                   array(select s = any(mine) from unnest(sids) s));
  if problem is not null then
    raise exception '%', problem;
  end if;

  delete from public.site_votes where round_id = p_round and user_id = uid;
  insert into public.site_votes (round_id, submission_id, user_id, points, comment)
  select p_round, t.sid, uid, t.p, t.c
    from unnest(sids, pts, cmts) as t(sid, p, c)
   where t.p <> 0 or t.c <> '';
  perform public.site_round_finish_early(p_round);
end;
$$;

-- The results, as before, and now: a submitter who didn't vote keeps only
-- the downvotes their track got, as Music League does (when the round says
-- not voting costs them).
create or replace function public.site_round_results(p_round uuid)
returns table (submission_id uuid, competitor_id text, points int, earned int, voted boolean)
language sql stable security definer set search_path = public as $$
  select s.id, m.competitor_id,
         case when exists (select 1 from public.site_votes v where v.round_id = p_round and v.user_id = o.user_id)
                   or r.nonvoters_keep_points
              then coalesce(t.total, 0) else coalesce(t.down, 0) end,
         coalesce(t.total, 0),
         exists (select 1 from public.site_votes v where v.round_id = p_round and v.user_id = o.user_id)
    from public.site_submissions s
    join public.site_rounds r on r.id = s.round_id
    left join public.site_submission_owners o on o.submission_id = s.id
    left join public.members m on m.user_id = o.user_id
    left join (select v.submission_id, sum(v.points)::int as total, sum(least(v.points, 0))::int as down
                 from public.site_votes v where v.round_id = p_round
                group by v.submission_id) t on t.submission_id = s.id
   where s.round_id = p_round and public.is_member()
     and public.site_round_phase(p_round) = 'finished';
$$;

-- Accelerated and Speedy, as before, and now: submissions close once every
-- player who has joined the site has all of the round's songs in.
create or replace function public.site_round_finish_early(p_round uuid)
returns void language plpgsql security definer set search_path = public as $$
declare
  r public.site_rounds%rowtype;
  s public.site_seasons%rowtype;
  saved interval;
begin
  select * into r from public.site_rounds where id = p_round for update;
  select * into s from public.site_seasons where key = r.season_key;
  if not found or s.timing = 'steady' then return; end if;
  if public.site_round_phase(p_round) = 'submitting' then
    if not exists (select 1 from public.site_season_players p join public.members m on m.competitor_id = p.competitor_id
                    where p.season_key = s.key)
       or exists (select 1 from public.site_season_players p join public.members m on m.competitor_id = p.competitor_id
                   where p.season_key = s.key
                     and (select count(*) from public.site_submission_owners o
                           where o.round_id = p_round and o.user_id = m.user_id) < r.songs_per_round) then
      return;
    end if;
    saved := r.closes_at - now();
    update public.site_rounds set closed_at = now() where id = p_round;
    if s.timing = 'speedy' then
      -- voting keeps its full length, so its deadline must not fall before
      -- the old submission deadline: that deadline becomes now too
      update public.site_rounds set closes_at = now(), voting_closes_at = voting_closes_at - saved where id = p_round;
      perform public.site_season_shift(s.key, saved);
    end if;
  elsif public.site_round_phase(p_round) = 'voting' then
    if exists (select 1 from public.site_submission_owners o
                where o.round_id = p_round
                  and not exists (select 1 from public.site_votes v where v.round_id = p_round and v.user_id = o.user_id)) then
      return;
    end if;
    saved := r.voting_closes_at - now();
    update public.site_rounds set voting_closed_at = now() where id = p_round;
    if s.timing = 'speedy' then
      perform public.site_season_shift(s.key, saved);
    end if;
  end if;
end;
$$;

-- Sets up a season, as before, and now with songs_per_round, downvotes and
-- max_down_per_track, which every round gets.
create or replace function public.create_site_season(p jsonb)
returns text language plpgsql security definer set search_path = public as $$
declare
  k text := p->>'key';
  s public.site_seasons%rowtype;
  first_close timestamptz;
  item jsonb;
  opens timestamptz;
  closes timestamptz;
  n int := 0;
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can set up a season.';
  end if;
  if k is null or k !~ '^season[0-9]+$' or substring(k from 7)::int < 4 then
    raise exception 'A season set up on the site is Season 4 or later.';
  end if;
  if exists (select 1 from public.site_seasons x where x.key = k)
     or exists (select 1 from public.site_rounds x where x.season_key = k) then
    raise exception 'That season already exists.';
  end if;
  if jsonb_typeof(p->'rounds') is distinct from 'array' or jsonb_array_length(p->'rounds') not between 1 and 40 then
    raise exception 'A season needs between 1 and 40 rounds.';
  end if;
  if jsonb_typeof(p->'players') is distinct from 'array' or jsonb_array_length(p->'players') < 2 then
    raise exception 'A season needs at least 2 players.';
  end if;
  if btrim(coalesce(p->>'name', '')) = '' then
    raise exception 'Give the season a name.';
  end if;
  if exists (select 1 from jsonb_array_elements(p->'rounds') e where btrim(coalesce(e->>'name', '')) = '') then
    raise exception 'Every round needs a name.';
  end if;
  first_close := (p->>'first_playlist_at')::timestamptz;
  if first_close is null or first_close <= now() then
    raise exception 'The first playlist has to be in the future.';
  end if;

  insert into public.site_seasons (key, name, description, point_budget, max_per_track, nonvoters_keep_points,
                                   timing, submit_days, vote_days, songs_per_round, downvotes, max_down_per_track)
  values (k, btrim(coalesce(p->>'name', '')), btrim(coalesce(p->>'description', '')),
          coalesce((p->>'point_budget')::smallint, 19), coalesce((p->>'max_per_track')::smallint, 5),
          coalesce((p->>'nonvoters_keep_points')::boolean, false), coalesce(p->>'timing', 'steady'),
          coalesce((p->>'submit_days')::smallint, 2), coalesce((p->>'vote_days')::smallint, 5),
          coalesce((p->>'songs_per_round')::smallint, 1), coalesce((p->>'downvotes')::smallint, 0),
          coalesce((p->>'max_down_per_track')::smallint, 0))
  returning * into s;
  insert into public.site_season_players (season_key, competitor_id)
  select distinct k, x from jsonb_array_elements_text(p->'players') x;

  for item in select e from jsonb_array_elements(p->'rounds') e loop
    n := n + 1;
    if n = 1 then
      closes := first_close;
      opens := greatest(now(), public.site_add_days(closes, -s.submit_days));
    else
      opens := public.site_add_days(closes, s.vote_days);
      closes := public.site_add_days(opens, s.submit_days);
    end if;
    insert into public.site_rounds (season_key, name, prompt, opens_at, closes_at, votes_on_site, voting_closes_at,
                                    point_budget, max_per_track, nonvoters_keep_points,
                                    songs_per_round, downvotes, max_down_per_track)
    values (k, btrim(coalesce(item->>'name', '')), btrim(coalesce(item->>'prompt', '')), opens, closes, true,
            public.site_add_days(closes, s.vote_days), s.point_budget, s.max_per_track, s.nonvoters_keep_points,
            s.songs_per_round, s.downvotes, s.max_down_per_track);
  end loop;
  return k;
end;
$$;

-- Changes a season, as before, and now: downvotes reach every round whose
-- submissions haven't closed, with the other rules; songs a round reach
-- only rounds that haven't opened.
create or replace function public.update_site_season(p_key text, p jsonb)
returns void language plpgsql security definer set search_path = public as $$
declare
  s public.site_seasons%rowtype;
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can change a season.';
  end if;
  update public.site_seasons set
    name = btrim(coalesce(p->>'name', name)),
    description = btrim(coalesce(p->>'description', description)),
    point_budget = coalesce((p->>'point_budget')::smallint, point_budget),
    max_per_track = coalesce((p->>'max_per_track')::smallint, max_per_track),
    nonvoters_keep_points = coalesce((p->>'nonvoters_keep_points')::boolean, nonvoters_keep_points),
    timing = coalesce(p->>'timing', timing),
    submit_days = coalesce((p->>'submit_days')::smallint, submit_days),
    vote_days = coalesce((p->>'vote_days')::smallint, vote_days),
    songs_per_round = coalesce((p->>'songs_per_round')::smallint, songs_per_round),
    downvotes = coalesce((p->>'downvotes')::smallint, downvotes),
    max_down_per_track = coalesce((p->>'max_down_per_track')::smallint, max_down_per_track)
   where key = p_key
  returning * into s;
  if not found then
    raise exception 'That season doesn''t exist.';
  end if;
  update public.site_rounds set point_budget = s.point_budget, max_per_track = s.max_per_track,
                                nonvoters_keep_points = s.nonvoters_keep_points,
                                downvotes = s.downvotes, max_down_per_track = s.max_down_per_track
   where season_key = p_key and closed_at is null and now() < closes_at;
  update public.site_rounds set songs_per_round = s.songs_per_round
   where season_key = p_key and now() < opens_at;
  perform public.site_season_reschedule(p_key);
end;
$$;

-- Adds a round at the end of a season, as before, with the season's songs
-- a round and downvotes.
create or replace function public.add_site_season_round(p_key text, p_name text, p_prompt text)
returns uuid language plpgsql security definer set search_path = public as $$
declare
  s public.site_seasons%rowtype;
  last_vote timestamptz;
  opens timestamptz;
  closes timestamptz;
  rid uuid;
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can add a round.';
  end if;
  select * into s from public.site_seasons where key = p_key;
  if not found then
    raise exception 'That season doesn''t exist.';
  end if;
  if btrim(coalesce(p_name, '')) = '' then
    raise exception 'Give the round a name.';
  end if;
  if (select count(*) from public.site_rounds where season_key = p_key) >= 40 then
    raise exception 'A season can have at most 40 rounds.';
  end if;
  select max(voting_closes_at) into last_vote from public.site_rounds where season_key = p_key;
  opens := greatest(now(), coalesce(last_vote, now()));
  closes := public.site_add_days(opens, s.submit_days);
  insert into public.site_rounds (season_key, name, prompt, opens_at, closes_at, votes_on_site, voting_closes_at,
                                  point_budget, max_per_track, nonvoters_keep_points,
                                  songs_per_round, downvotes, max_down_per_track)
  values (p_key, btrim(coalesce(p_name, '')), btrim(coalesce(p_prompt, '')), opens, closes, true,
          public.site_add_days(closes, s.vote_days), s.point_budget, s.max_per_track, s.nonvoters_keep_points,
          s.songs_per_round, s.downvotes, s.max_down_per_track)
  returning id into rid;
  return rid;
end;
$$;

revoke all on function public.ballot_problem(int, int, int, int, int[], boolean[]) from public, anon, authenticated;
revoke all on function public.withdraw_track(uuid, text) from public, anon;
grant execute on function public.withdraw_track(uuid, text) to authenticated;
