-- Hidden prompts and guesses (README, Hidden prompts and guesses). Run once
-- in the Supabase SQL Editor for the live project, after
-- 2026-10-29_spectator_points.sql. Safe to re-run. supabase/schema.sql has
-- the same before its storage section, for a fresh install.
--
-- Asked for 2026-10-29: a round can hide its prompt, and who wrote it, from
-- its Spectators until voting closes. Spectators then guess the prompt from
-- the playlist, and pick its writer from the round's DJs. The user's calls:
-- Claude grades each prompt guess 0-5 once voting closes (the grade-guesses
-- Edge Function; a commissioner can change a score), the right writer is
-- worth 3, and a guess locks when its Spectator first submits their ballot.
--
-- Hiding the prompt hides the round's name too, since the name is the
-- theme: from the table (members now read names and prompts only through
-- site_rounds_list()), the notifications, a note shown while voting, and
-- who wrote it. The admin and commissioners always see it.

-- ---------------------------------------------------------------- hidden prompts and guesses

-- Whether a round hides its prompt (and name, which is the theme) and who
-- wrote it from its Spectators until voting closes. Set when the round is
-- made or edited, and fixed once its submissions close.
alter table public.site_rounds add column if not exists hide_prompt boolean not null default false;
alter table public.site_rounds add column if not exists hide_prompter boolean not null default false;

create or replace function public.site_rounds_hiding_fixed()
returns trigger language plpgsql set search_path = public as $$
begin
  if (new.hide_prompt, new.hide_prompter) is distinct from (old.hide_prompt, old.hide_prompter)
     and public.site_round_phase(old.id) not in ('upcoming', 'submitting') then
    raise exception 'What a round hides from Spectators can change only until submissions close.';
  end if;
  return new;
end;
$$;
drop trigger if exists site_rounds_hiding_fixed on public.site_rounds;
create trigger site_rounds_hiding_fixed before update on public.site_rounds
  for each row execute function public.site_rounds_hiding_fixed();

-- Whether a round hides its prompt ('prompt') or its prompter ('prompter')
-- from this account right now: a Spectator in it, not the admin or a
-- commissioner (who set it up), until voting closes.
create or replace function public.site_hides_from(p_round uuid, p_user uuid, p_what text)
returns boolean language sql stable security definer set search_path = public as $$
  select coalesce((
    select (case p_what when 'prompt' then r.hide_prompt when 'prompter' then r.hide_prompter else false end)
           and public.site_round_phase(r.id) <> 'finished'
           and public.site_user_role(r.id, p_user) = 'spectator'
           and not exists (select 1 from public.members m where m.user_id = p_user and m.role in ('commissioner', 'admin'))
      from public.site_rounds r where r.id = p_round), false);
$$;

-- "Round 3": a round's place in its season, for when its name is hidden.
create or replace function public.site_round_public_name(p_round uuid)
returns text language sql stable security definer set search_path = public as $$
  select 'Round ' || (select count(*) from public.site_rounds x
                       where x.season_key = r.season_key and (x.opens_at, x.id) <= (r.opens_at, r.id))
    from public.site_rounds r where r.id = p_round;
$$;

-- Members no longer read a round's name and prompt straight from the
-- table: site_rounds_list() hands them out, hidden where they should be.
-- Every other column stays readable as before. A column added to
-- site_rounds later needs adding here too (tests/test_prompt_guesses.py).
revoke select on table public.site_rounds from anon, authenticated;
grant select (id, season_key, closes_at, closed_at, created_at, spotify_playlist, youtube_playlist, playlists_built_at,
              votes_on_site, voting_closes_at, voting_closed_at, point_budget, max_per_track, nonvoters_keep_points,
              opens_at, songs_per_round, downvotes, max_down_per_track, services, repeat_rule, hide_prompt, hide_prompter)
  on table public.site_rounds to authenticated;

-- The rounds for the pages, newest opening first, the latest 100, with who
-- wrote each and its own roles. For a Spectator in a round that hides
-- them: "Round 3" for the name, no prompt, no prompters, and
-- prompt_hidden / prompter_hidden saying so.
create or replace function public.site_rounds_list()
returns jsonb language sql stable security definer set search_path = public as $$
  select coalesce(jsonb_agg(x.row order by x.opens_at desc), '[]'::jsonb)
    from (
      select r.opens_at, jsonb_build_object(
        'id', r.id, 'season_key', r.season_key,
        'name', case when h.prompt then public.site_round_public_name(r.id) else r.name end,
        'prompt', case when h.prompt then '' else r.prompt end,
        'prompt_hidden', h.prompt, 'prompter_hidden', h.prompter,
        'hide_prompt', r.hide_prompt, 'hide_prompter', r.hide_prompter,
        'opens_at', r.opens_at, 'closes_at', r.closes_at, 'closed_at', r.closed_at, 'created_at', r.created_at,
        'spotify_playlist', r.spotify_playlist, 'youtube_playlist', r.youtube_playlist,
        'votes_on_site', r.votes_on_site, 'voting_closes_at', r.voting_closes_at, 'voting_closed_at', r.voting_closed_at,
        'point_budget', r.point_budget, 'max_per_track', r.max_per_track, 'nonvoters_keep_points', r.nonvoters_keep_points,
        'songs_per_round', r.songs_per_round, 'downvotes', r.downvotes, 'max_down_per_track', r.max_down_per_track,
        'services', r.services, 'repeat_rule', r.repeat_rule,
        'site_round_prompters', case when h.prompter then '[]'::jsonb else coalesce((
          select jsonb_agg(jsonb_build_object('competitor_id', p.competitor_id) order by p.competitor_id)
            from public.site_round_prompters p where p.round_id = r.id), '[]'::jsonb) end,
        'site_round_roles', coalesce((
          select jsonb_agg(jsonb_build_object('competitor_id', o.competitor_id, 'role', o.role) order by o.competitor_id)
            from public.site_round_roles o where o.round_id = r.id), '[]'::jsonb)) as row
        from (select * from public.site_rounds order by opens_at desc limit 100) r
        cross join lateral (select public.site_hides_from(r.id, auth.uid(), 'prompt') as prompt,
                                   public.site_hides_from(r.id, auth.uid(), 'prompter') as prompter) h
       where public.is_member()) x;
$$;

-- Who wrote a round's prompt stays hidden from its Spectators too, when it
-- says so.
drop policy if exists "members read site round prompters" on public.site_round_prompters;
create policy "members read site round prompters" on public.site_round_prompters
  for select to authenticated using (public.is_member() and not public.site_hides_from(round_id, auth.uid(), 'prompter'));

-- A note shown while people vote could give a hidden prompt away, so a
-- Spectator sees notes only once voting has closed in such a round.
drop policy if exists "members read the notes they may see" on public.site_submission_notes;
create policy "members read the notes they may see" on public.site_submission_notes
  for select to authenticated using (
    public.is_member() and (
      public.site_round_phase(round_id) = 'finished'
      or (in_voting and public.site_round_phase(round_id) = 'voting'
          and not public.site_hides_from(round_id, auth.uid(), 'prompt'))));

-- A Spectator's guess at a hidden prompt, and at who wrote it, one per
-- round. score is the prompt guess's 0-5, from Claude when voting closes
-- (the grade-guesses Edge Function) or a commissioner; blank guesses score
-- 0 on their own. Who guessed what shows to members once voting closes.
create table if not exists public.site_prompt_guesses (
  id                 uuid primary key default gen_random_uuid(),
  round_id           uuid not null references public.site_rounds (id) on delete cascade,
  user_id            uuid not null references auth.users (id) on delete cascade,
  guess              text not null default '' check (char_length(guess) <= 280),
  prompter           text references public.players (competitor_id),
  saved_at           timestamptz not null default now(),
  score              smallint check (score between 0 and 5),
  reason             text check (char_length(reason) <= 300),
  graded_by          text check (graded_by in ('claude', 'commissioner', 'blank')),
  grading_started_at timestamptz,
  unique (round_id, user_id)
);
alter table public.site_prompt_guesses enable row level security;
revoke all on table public.site_prompt_guesses from anon, authenticated;

-- Saves the caller's guess while voting is open: a Spectator in a round
-- that hides something, not a commissioner, and only until they first
-- submit their ballot (the voters' lounge, where DJs know the prompt, opens
-- then). An empty guess and no prompter clears it.
create or replace function public.save_prompt_guess(p_round uuid, p_guess text, p_prompter text)
returns void language plpgsql security definer set search_path = public as $$
declare
  uid uuid := auth.uid();
  r public.site_rounds%rowtype;
  body text := btrim(coalesce(p_guess, ''));
begin
  if not public.is_member() then
    raise exception 'Only league members can guess.';
  end if;
  select * into r from public.site_rounds where id = p_round;
  if not found then
    raise exception 'That round doesn''t exist.';
  end if;
  if not (r.hide_prompt or r.hide_prompter) then
    raise exception 'This round has nothing hidden to guess.';
  end if;
  if public.site_user_role(p_round, uid) is distinct from 'spectator' then
    raise exception 'Only this round''s Spectators guess.';
  end if;
  if exists (select 1 from public.members m where m.user_id = uid and m.role in ('commissioner', 'admin')) then
    raise exception 'The admin and commissioners can see the prompt, so they don''t guess.';
  end if;
  if public.site_round_phase(p_round) is distinct from 'voting' then
    raise exception 'Guesses go in while voting is open.';
  end if;
  if exists (select 1 from public.site_votes v where v.round_id = p_round and v.user_id = uid) then
    raise exception 'Your guess locked when you submitted your ballot.';
  end if;
  if char_length(body) > 280 then
    raise exception 'A guess can be at most 280 characters.';
  end if;
  if body <> '' and not r.hide_prompt then
    raise exception 'This round shows its prompt.';
  end if;
  if p_prompter is not null then
    if not r.hide_prompter then
      raise exception 'This round shows who wrote its prompt.';
    end if;
    if public.site_round_role(p_round, p_prompter) is distinct from 'dj' then
      raise exception 'Pick one of this round''s DJs.';
    end if;
  end if;
  insert into public.site_prompt_guesses (round_id, user_id, guess, prompter, saved_at)
  values (p_round, uid, body, p_prompter, now())
  on conflict (round_id, user_id) do update set guess = excluded.guess, prompter = excluded.prompter, saved_at = excluded.saved_at;
end;
$$;

-- The caller's own guess, whether it has locked, and its score once
-- voting has closed.
create or replace function public.my_prompt_guess(p_round uuid)
returns table (guess text, prompter text, locked boolean, score smallint, reason text)
language sql stable security definer set search_path = public as $$
  select g.guess, g.prompter,
         exists (select 1 from public.site_votes v where v.round_id = p_round and v.user_id = auth.uid()),
         case when public.site_round_phase(p_round) = 'finished' then g.score end,
         case when public.site_round_phase(p_round) = 'finished' then g.reason end
    from public.site_prompt_guesses g
   where g.round_id = p_round and g.user_id = auth.uid() and public.is_member();
$$;

-- Once voting has closed: every guess, who made it, its score and whether
-- they picked one of the prompt's writers.
create or replace function public.site_round_guesses(p_round uuid)
returns table (guess_id uuid, competitor_id text, guess text, prompter text, score smallint, reason text,
               graded_by text, prompter_correct boolean)
language sql stable security definer set search_path = public as $$
  select g.id, m.competitor_id, g.guess, g.prompter, g.score, g.reason, g.graded_by,
         g.prompter is not null and exists (select 1 from public.site_round_prompters p
                                             where p.round_id = g.round_id and p.competitor_id = g.prompter)
    from public.site_prompt_guesses g
    join public.members m on m.user_id = g.user_id
   where g.round_id = p_round and public.is_member() and public.site_round_phase(p_round) = 'finished'
   order by m.competitor_id;
$$;

-- For the grade-guesses Edge Function only (its secret key): once voting
-- has closed in a round that hid its prompt, the prompt and the guesses
-- still to grade, claimed for 10 minutes so two calls don't grade one
-- twice. A blank guess scores 0 here, without asking anyone.
create or replace function public.prompt_guesses_claim(p_round uuid)
returns jsonb language plpgsql security definer set search_path = public as $$
declare
  r public.site_rounds%rowtype;
  out jsonb;
begin
  select * into r from public.site_rounds where id = p_round;
  if not found or not r.hide_prompt or public.site_round_phase(p_round) <> 'finished' then
    return null;
  end if;
  update public.site_prompt_guesses set score = 0, graded_by = 'blank'
   where round_id = p_round and score is null and guess = '';
  with claimed as (
    update public.site_prompt_guesses set grading_started_at = now()
     where round_id = p_round and score is null
       and (grading_started_at is null or grading_started_at < now() - interval '10 minutes')
    returning id, guess)
  select jsonb_build_object('name', r.name, 'prompt', r.prompt,
                            'guesses', coalesce((select jsonb_agg(jsonb_build_object('id', c.id, 'guess', c.guess)) from claimed c), '[]'::jsonb))
    into out;
  return out;
end;
$$;

-- For the grade-guesses Edge Function only: the scores, [{id, score,
-- reason}]. A guess already scored keeps its score.
create or replace function public.prompt_guesses_grade(p_grades jsonb)
returns int language plpgsql security definer set search_path = public as $$
declare
  n int;
begin
  if jsonb_typeof(p_grades) is distinct from 'array'
     or exists (select 1 from jsonb_array_elements(p_grades) e
                 where jsonb_typeof(e->'score') is distinct from 'number' or (e->>'score')::numeric not in (0, 1, 2, 3, 4, 5)) then
    raise exception 'Scores are whole numbers from 0 to 5.';
  end if;
  update public.site_prompt_guesses g
     set score = (e->>'score')::smallint, reason = left(coalesce(e->>'reason', ''), 300), graded_by = 'claude'
    from jsonb_array_elements(p_grades) e
   where g.id = (e->>'id')::uuid and g.score is null;
  get diagnostics n = row_count;
  return n;
end;
$$;

-- A commissioner sets a guess's score by hand, once voting has closed.
create or replace function public.set_prompt_guess_score(p_guess uuid, p_score int)
returns void language plpgsql security definer set search_path = public as $$
declare
  rid uuid;
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can change a score.';
  end if;
  if p_score is null or p_score not between 0 and 5 then
    raise exception 'A score is from 0 to 5.';
  end if;
  select round_id into rid from public.site_prompt_guesses where id = p_guess;
  if rid is null then
    raise exception 'That guess doesn''t exist.';
  end if;
  if public.site_round_phase(rid) <> 'finished' then
    raise exception 'Scores are set once voting has closed.';
  end if;
  update public.site_prompt_guesses set score = p_score, graded_by = 'commissioner' where id = p_guess;
end;
$$;

-- Sets up a season, as before, and now: each round can hide its prompt
-- and its prompter from Spectators ({hide_prompt, hide_prompter}).
create or replace function public.create_site_season(p jsonb)
returns text language plpgsql security definer set search_path = public as $$
declare
  k text := p->>'key';
  s public.site_seasons%rowtype;
  first_close timestamptz;
  item jsonb;
  opens timestamptz;
  closes timestamptz;
  rid uuid;
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
  if jsonb_typeof(p->'players') is distinct from 'array'
     or exists (select 1 from jsonb_array_elements(p->'players') e
                 where not (jsonb_typeof(e) = 'string'
                            or (jsonb_typeof(e) = 'object' and coalesce(e->>'id', '') <> ''
                                and coalesce(e->>'role', 'dj') in ('dj', 'spectator')))) then
    raise exception 'The players don''t add up. Reload the page and try again.';
  end if;
  if (select count(distinct coalesce(e->>'id', e #>> '{}')) from jsonb_array_elements(p->'players') e
       where jsonb_typeof(e) = 'string' or coalesce(e->>'role', 'dj') = 'dj') < 2 then
    raise exception 'A season needs at least 2 DJs.';
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
                                   timing, submit_days, vote_days, songs_per_round, downvotes, max_down_per_track,
                                   services, repeat_rule)
  values (k, btrim(coalesce(p->>'name', '')), btrim(coalesce(p->>'description', '')),
          coalesce((p->>'point_budget')::smallint, 19), coalesce((p->>'max_per_track')::smallint, 5),
          coalesce((p->>'nonvoters_keep_points')::boolean, false), coalesce(p->>'timing', 'steady'),
          coalesce((p->>'submit_days')::smallint, 2), coalesce((p->>'vote_days')::smallint, 5),
          coalesce((p->>'songs_per_round')::smallint, 1), coalesce((p->>'downvotes')::smallint, 0),
          coalesce((p->>'max_down_per_track')::smallint, 0),
          coalesce((select array_agg(x) from jsonb_array_elements_text(p->'services') x), '{spotify,youtube,soundcloud}'),
          coalesce(p->>'repeat_rule', 'warn'))
  returning * into s;
  insert into public.site_season_players (season_key, competitor_id, role)
  select distinct on (x.id) k, x.id, x.role
    from (select coalesce(e->>'id', e #>> '{}') as id,
                 case when jsonb_typeof(e) = 'object' then coalesce(e->>'role', 'dj') else 'dj' end as role
            from jsonb_array_elements(p->'players') e) x;

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
                                    songs_per_round, downvotes, max_down_per_track, services, repeat_rule,
                                    hide_prompt, hide_prompter)
    values (k, btrim(coalesce(item->>'name', '')), btrim(coalesce(item->>'prompt', '')), opens, closes, true,
            public.site_add_days(closes, s.vote_days), s.point_budget, s.max_per_track, s.nonvoters_keep_points,
            s.songs_per_round, s.downvotes, s.max_down_per_track, s.services, s.repeat_rule,
            coalesce((item->>'hide_prompt')::boolean, false), coalesce((item->>'hide_prompter')::boolean, false))
    returning id into rid;
    perform public.site_round_people_apply(rid, item->'roles', item->'prompters');
  end loop;
  return k;
end;
$$;

-- The reminder finder, as before, and now: a Spectator in a round that
-- hides its prompt gets "Season 4, Round 3" for its name.
create or replace function public.reminders_claim(p_channels text[])
returns table (round_id uuid, kind text, user_id uuid, channel text, round_name text,
               closes_at timestamptz, email text, subscriptions jsonb)
language sql security definer set search_path = public as $$
  with rounds as (
    select r.*, public.site_round_phase(r.id) as phase,
           coalesce(r.closed_at, r.closes_at) as voting_opened
      from public.site_rounds r),
  targets as (
    select r.id as round_id, 'round_open'::text as kind, m.user_id
      from rounds r cross join public.members m
     where r.phase = 'submitting' and r.opens_at > now() - interval '6 hours'
       and public.site_round_role(r.id, m.competitor_id) = 'dj'
    union all
    select r.id, 'playlist_ready', m.user_id
      from rounds r cross join public.members m
     where r.playlists_built_at is not null and r.playlists_built_at > now() - interval '12 hours'
    union all
    select r.id, k.kind, w.user_id
      from rounds r
      cross join lateral (
        select t.kind from (values
            ('vote_halfway', r.voting_opened + (r.voting_closes_at - r.voting_opened) / 2),
            ('vote_5h', r.voting_closes_at - interval '5 hours'),
            ('vote_2h', r.voting_closes_at - interval '2 hours'),
            ('vote_1h', r.voting_closes_at - interval '1 hour')) as t(kind, due)
         where t.due <= now() and t.due >= r.voting_opened
         order by t.due desc limit 1) k
      join (select o.round_id, o.user_id from public.site_submission_owners o
            union
            select x.id, m.user_id from public.site_rounds x
              join public.site_season_players p on p.season_key = x.season_key
              join public.members m on m.competitor_id = p.competitor_id
             where public.site_round_role(x.id, p.competitor_id) = 'spectator') w on w.round_id = r.id
     where r.phase = 'voting'
       and not exists (select 1 from public.site_votes v where v.round_id = r.id and v.user_id = w.user_id)),
  -- only the kinds the member wants (all, unless they turned one off)
  chosen as (
    select t.* from targets t
     where coalesce((select case when t.kind = 'round_open' then rs.round_open
                                 when t.kind = 'playlist_ready' then rs.playlist_ready
                                 else rs.voting end
                       from public.reminder_settings rs where rs.user_id = t.user_id), true)),
  wanted as (
    select t.round_id, t.kind, t.user_id, 'push'::text as channel from chosen t
     where 'push' = any(p_channels)
       and exists (select 1 from public.push_subscriptions s where s.user_id = t.user_id)
    union all
    select t.round_id, t.kind, t.user_id, 'email' from chosen t
     where 'email' = any(p_channels)
       and coalesce((select rs.email_on from public.reminder_settings rs where rs.user_id = t.user_id), true)
       and exists (select 1 from auth.users u where u.id = t.user_id and u.email is not null)),
  claimed as (
    insert into public.reminders_sent (round_id, kind, user_id, channel)
    select w.round_id, w.kind, w.user_id, w.channel from wanted w
    on conflict do nothing
    returning reminders_sent.round_id, reminders_sent.kind, reminders_sent.user_id, reminders_sent.channel)
  select c.round_id, c.kind, c.user_id, c.channel,
         case when public.site_hides_from(c.round_id, c.user_id, 'prompt')
              then coalesce((select s.name || ', ' from public.site_seasons s where s.key = r.season_key), '')
                   || public.site_round_public_name(r.id)
              else r.name end,
         case when c.kind like 'vote%' then r.voting_closes_at else r.closes_at end,
         case when c.channel = 'email' then (select u.email from auth.users u where u.id = c.user_id) end,
         case when c.channel = 'push' then (
           select coalesce(jsonb_agg(jsonb_build_object('endpoint', s.endpoint, 'p256dh', s.p256dh, 'auth', s.auth)), '[]'::jsonb)
             from public.push_subscriptions s where s.user_id = c.user_id) end
    from claimed c join public.site_rounds r on r.id = c.round_id;
$$;

-- Finished rounds voted here, for publish.py, as before, and now: what
-- each hid from its Spectators, and their guesses.
create or replace function public.site_rounds_export()
returns jsonb language sql stable security definer set search_path = public as $$
  select jsonb_build_object(
    'rounds', coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', r.id, 'season_key', r.season_key, 'name', r.name, 'prompt', r.prompt,
        'created_at', r.opens_at, 'voting_ended_at', coalesce(r.voting_closed_at, r.voting_closes_at),
        'spotify_playlist', r.spotify_playlist, 'point_budget', r.point_budget,
        'nonvoters_keep_points', r.nonvoters_keep_points,
        'hide_prompt', r.hide_prompt, 'hide_prompter', r.hide_prompter,
        -- the Spectators' guesses (README, Hidden prompts and guesses)
        'guesses', coalesce((
          select jsonb_agg(jsonb_build_object(
            'spectator', m.competitor_id, 'guess', g.guess, 'prompter', g.prompter, 'score', g.score,
            'prompter_correct', g.prompter is not null and exists (
              select 1 from public.site_round_prompters p where p.round_id = r.id and p.competitor_id = g.prompter))
            order by m.competitor_id)
            from public.site_prompt_guesses g
            join public.members m on m.user_id = g.user_id
           where g.round_id = r.id), '[]'::jsonb),
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

revoke all on function public.site_rounds_hiding_fixed() from public, anon, authenticated;
-- the policies above call it, and a policy runs with the reader's own
-- rights, so members must be able to run it (found 2026-10-29)
revoke all on function public.site_hides_from(uuid, uuid, text) from public, anon;
grant execute on function public.site_hides_from(uuid, uuid, text) to authenticated;
revoke all on function public.site_round_public_name(uuid) from public, anon, authenticated;
revoke all on function public.site_rounds_list() from public, anon;
grant execute on function public.site_rounds_list() to authenticated;
revoke all on function public.save_prompt_guess(uuid, text, text) from public, anon;
grant execute on function public.save_prompt_guess(uuid, text, text) to authenticated;
revoke all on function public.my_prompt_guess(uuid) from public, anon;
grant execute on function public.my_prompt_guess(uuid) to authenticated;
revoke all on function public.site_round_guesses(uuid) from public, anon;
grant execute on function public.site_round_guesses(uuid) to authenticated;
revoke all on function public.set_prompt_guess_score(uuid, int) from public, anon;
grant execute on function public.set_prompt_guess_score(uuid, int) to authenticated;
revoke all on function public.prompt_guesses_claim(uuid) from public, anon, authenticated;
grant execute on function public.prompt_guesses_claim(uuid) to service_role;
revoke all on function public.prompt_guesses_grade(jsonb) from public, anon, authenticated;
grant execute on function public.prompt_guesses_grade(jsonb) to service_role;
