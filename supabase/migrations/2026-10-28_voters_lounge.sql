-- The voters' lounge (README, Voters' lounge). Run once in the Supabase SQL
-- Editor for the live project, after 2026-10-27_demo_ballots.sql. Safe to
-- re-run. supabase/schema.sql has the same before its storage section, for
-- a fresh install.
--
-- Asked for 2026-10-28: a room where only the people who have submitted
-- their ballot can chat, while voting is open, anonymously. The user's
-- calls: one message per person every 24 hours, 280 characters at most,
-- chatters never named, and when voting closes the lounge locks and stays
-- readable under the results.
--
-- Each chatter gets an instrument name for the round (Kazoo, Theremin...),
-- the same all round, assigned at random and never tied to them anywhere a
-- member can read. The lounge opens once 3 people have voted, so "anonymous"
-- never means "obviously the one person who's voted". Emoji reactions are
-- unlimited.
--
-- practice: the round demo's practice lounge (round-demo.js), for the round
-- the demo copies. In it, "has voted" means a practice ballot submitted
-- (site_demo_ballots), it opens with 1 voter, and a message every 10
-- minutes, so it can be tried. It never mixes with a real lounge.
--
-- Three tables, row-level security on, no policies, no API grants: the
-- functions are the only way in, and none of them gives out who wrote what.

-- ---------------------------------------------------------------- voters' lounge

create table if not exists public.site_lounge_aliases (
  round_id  uuid not null references public.site_rounds (id) on delete cascade,
  practice  boolean not null,
  user_id   uuid not null references auth.users (id) on delete cascade,
  alias     smallint not null check (alias >= 0),
  primary key (round_id, practice, user_id),
  unique (round_id, practice, alias)
);

create table if not exists public.site_lounge_messages (
  id          bigint generated always as identity primary key,
  round_id    uuid not null references public.site_rounds (id) on delete cascade,
  practice    boolean not null,
  user_id     uuid not null references auth.users (id) on delete cascade,
  body        text not null check (char_length(body) between 1 and 280),
  created_at  timestamptz not null default now(),
  removed_at  timestamptz                   -- taken down by the admin; still counts toward the limit
);
create index if not exists site_lounge_messages_room on public.site_lounge_messages (round_id, practice, created_at);
create index if not exists site_lounge_messages_writer on public.site_lounge_messages (round_id, practice, user_id, created_at desc);

create table if not exists public.site_lounge_reactions (
  message_id  bigint not null references public.site_lounge_messages (id) on delete cascade,
  user_id     uuid not null references auth.users (id) on delete cascade,
  reaction    text not null check (reaction in ('fire', 'laugh', 'hundred', 'eyes', 'heart', 'grimace')),
  primary key (message_id, user_id, reaction)
);

alter table public.site_lounge_aliases enable row level security;
alter table public.site_lounge_messages enable row level security;
alter table public.site_lounge_reactions enable row level security;
revoke all on table public.site_lounge_aliases from anon, authenticated;
revoke all on table public.site_lounge_messages from anon, authenticated;
revoke all on table public.site_lounge_reactions from anon, authenticated;

-- An alias's name: an instrument, and a number after the 48th.
create or replace function public.lounge_alias_name(p_alias int)
returns text language sql immutable set search_path = public as $$
  select (array['Kazoo', 'Theremin', 'Cowbell', 'Banjo', 'Ukulele', 'Tuba', 'Oboe', 'Bassoon',
                'Harmonica', 'Glockenspiel', 'Accordion', 'Bagpipes', 'Didgeridoo', 'Mandolin', 'Sitar', 'Marimba',
                'Xylophone', 'Tambourine', 'Triangle', 'Bongo', 'Cello', 'Viola', 'Harp', 'Piccolo',
                'Clarinet', 'Trombone', 'Sousaphone', 'Synth', 'Keytar', 'Melodica', 'Ocarina', 'Recorder',
                'Vibraphone', 'Timpani', 'Castanets', 'Maracas', 'Washboard', 'Fiddle', 'Lute', 'Zither',
                'Dulcimer', 'Bouzouki', 'Steel Drum', 'Conga', 'Cajon', 'Flugelhorn', 'Euphonium', 'Harpsichord'])[p_alias % 48 + 1]
         || case when p_alias >= 48 then ' ' || (p_alias / 48 + 1)::text else '' end;
$$;

-- Where the caller stands in a lounge: the round's phase ('voting',
-- 'finished', or 'closed' for anything else), how many have voted, whether
-- the caller has (is_in), and whether they could have (a track in the
-- round; anyone, in the practice lounge).
create or replace function public.lounge_state(p_round uuid, p_practice boolean)
returns table (phase text, voters int, is_in boolean, eligible boolean, needed int)
language sql stable security definer set search_path = public as $$
  select
    case when p_practice then 'voting'
         when not r.votes_on_site then 'closed'
         else coalesce(nullif(public.site_round_phase(r.id), 'submitting'), 'closed') end,
    case when p_practice
         then (select count(*)::int from public.site_demo_ballots d
                where d.source_round = r.id and jsonb_array_length(d.ballot) > 0)
         else (select count(distinct v.user_id)::int from public.site_votes v where v.round_id = r.id) end,
    case when p_practice
         then exists (select 1 from public.site_demo_ballots d
                       where d.user_id = auth.uid() and d.source_round = r.id and jsonb_array_length(d.ballot) > 0)
         else exists (select 1 from public.site_votes v where v.round_id = r.id and v.user_id = auth.uid()) end,
    case when p_practice then public.is_member()
         else exists (select 1 from public.site_submission_owners o where o.round_id = r.id and o.user_id = auth.uid()) end,
    case when p_practice then 1 else 3 end
    from public.site_rounds r
   where r.id = p_round and public.is_member();
$$;

-- Whether the caller may read, and write (post or react), in a lounge:
-- read and write while voting is open, once they've voted and enough have;
-- read only, every member, once voting has closed (not the practice one).
create or replace function public.lounge_can(p_round uuid, p_practice boolean, p_write boolean)
returns boolean language sql stable security definer set search_path = public as $$
  select coalesce((
    select (s.phase = 'voting' and s.is_in and s.voters >= s.needed)
        or (not p_write and not p_practice and s.phase = 'finished')
      from public.lounge_state(p_round, p_practice) s), false);
$$;

-- The caller's alias in a lounge, given at random from the ones still free
-- the first time it's asked for.
create or replace function public.lounge_alias(p_round uuid, p_practice boolean)
returns text language plpgsql security definer set search_path = public as $$
declare
  uid uuid := auth.uid();
  got int;
  tries int := 0;
begin
  select a.alias into got from public.site_lounge_aliases a
   where a.round_id = p_round and a.practice = p_practice and a.user_id = uid;
  while got is null and tries < 5 loop
    tries := tries + 1;
    begin
      insert into public.site_lounge_aliases (round_id, practice, user_id, alias)
      select p_round, p_practice, uid,
             coalesce((select i from generate_series(0, 47) i
                        where i not in (select a.alias from public.site_lounge_aliases a
                                         where a.round_id = p_round and a.practice = p_practice)
                        order by random() limit 1),
                      (select max(a.alias) + 1 from public.site_lounge_aliases a
                        where a.round_id = p_round and a.practice = p_practice))
      returning alias into got;
    exception when unique_violation then
      -- someone took the same one at the same moment, or it's ours already
      select a.alias into got from public.site_lounge_aliases a
       where a.round_id = p_round and a.practice = p_practice and a.user_id = uid;
    end;
  end loop;
  return public.lounge_alias_name(got);
end;
$$;

-- How long between one person's messages.
create or replace function public.lounge_gap(p_practice boolean)
returns interval language sql immutable set search_path = public as $$
  select case when p_practice then interval '10 minutes' else interval '24 hours' end;
$$;

-- Everything the page needs to draw the lounge's door, or the lounge.
create or replace function public.lounge_status(p_round uuid, p_practice boolean)
returns jsonb language plpgsql security definer set search_path = public as $$
declare
  s record;
  open boolean;
  last_at timestamptz;
begin
  select * into s from public.lounge_state(p_round, p_practice);
  if not found then
    return null;
  end if;
  open := s.phase = 'voting' and s.is_in and s.voters >= s.needed;
  select max(m.created_at) into last_at from public.site_lounge_messages m
   where m.round_id = p_round and m.practice = p_practice and m.user_id = auth.uid();
  return jsonb_build_object(
    'phase', s.phase, 'voters', s.voters, 'needed', s.needed, 'in', s.is_in, 'eligible', s.eligible,
    'open', open,
    'alias', case when open then public.lounge_alias(p_round, p_practice) end,
    'next_post_at', case when last_at is not null and last_at + public.lounge_gap(p_practice) > now()
                         then last_at + public.lounge_gap(p_practice) end,
    'gap_minutes', extract(epoch from public.lounge_gap(p_practice))::int / 60,
    'messages', (select count(*) from public.site_lounge_messages m
                  where m.round_id = p_round and m.practice = p_practice and m.removed_at is null));
end;
$$;

-- The lounge's messages, oldest first, for a caller who may read it: each
-- with its alias, never its writer; whether it's the caller's own; and its
-- reactions. A removed one keeps its place, without its words.
create or replace function public.lounge_messages(p_round uuid, p_practice boolean)
returns table (id bigint, alias text, body text, created_at timestamptz, mine boolean, removed boolean,
               reactions jsonb, my_reactions text[])
language sql stable security definer set search_path = public as $$
  select m.id, public.lounge_alias_name(a.alias),
         case when m.removed_at is null then m.body end,
         m.created_at, m.user_id = auth.uid(), m.removed_at is not null,
         coalesce((select jsonb_object_agg(t.reaction, t.n)
                     from (select x.reaction, count(*) as n from public.site_lounge_reactions x
                            where x.message_id = m.id group by x.reaction) t), '{}'::jsonb),
         coalesce((select array_agg(x.reaction order by x.reaction) from public.site_lounge_reactions x
                    where x.message_id = m.id and x.user_id = auth.uid()), '{}')
    from public.site_lounge_messages m
    left join public.site_lounge_aliases a
      on a.round_id = m.round_id and a.practice = m.practice and a.user_id = m.user_id
   where m.round_id = p_round and m.practice = p_practice
     and public.lounge_can(p_round, p_practice, false)
   order by m.created_at, m.id;
$$;

-- Sends a message: 1 to 280 characters, one every 24 hours (10 minutes in
-- the practice lounge), a removed one included. Returns when the next can go.
create or replace function public.lounge_post(p_round uuid, p_practice boolean, p_body text)
returns timestamptz language plpgsql security definer set search_path = public as $$
declare
  uid uuid := auth.uid();
  body text := btrim(coalesce(p_body, ''));
  last_at timestamptz;
  at timestamptz := now();
begin
  if not public.lounge_can(p_round, p_practice, true) then
    raise exception 'The lounge is only open to people who have voted, while voting is open.';
  end if;
  if char_length(body) = 0 then
    raise exception 'Write something first.';
  end if;
  if char_length(body) > 280 then
    raise exception 'A message can be at most 280 characters.';
  end if;
  -- one at a time per writer, so two taps can't both get in
  perform pg_advisory_xact_lock(hashtext('lounge:' || p_round::text || ':' || p_practice::text || ':' || uid::text));
  select max(m.created_at) into last_at from public.site_lounge_messages m
   where m.round_id = p_round and m.practice = p_practice and m.user_id = uid;
  if last_at is not null and last_at + public.lounge_gap(p_practice) > at then
    raise exception 'One message every %. The lounge shows when your next one can go.',
      case when p_practice then '10 minutes' else '24 hours' end;
  end if;
  perform public.lounge_alias(p_round, p_practice);
  insert into public.site_lounge_messages (round_id, practice, user_id, body, created_at)
  values (p_round, p_practice, uid, body, at);
  return at + public.lounge_gap(p_practice);
end;
$$;

-- A reaction on a message, or taking it back: anyone who may write in its
-- lounge, as often as they like.
create or replace function public.lounge_react(p_message bigint, p_reaction text, p_on boolean)
returns void language plpgsql security definer set search_path = public as $$
declare
  m public.site_lounge_messages%rowtype;
begin
  select * into m from public.site_lounge_messages where id = p_message;
  if not found or m.removed_at is not null then
    raise exception 'That message isn''t there any more.';
  end if;
  if not public.lounge_can(m.round_id, m.practice, true) then
    raise exception 'The lounge is only open to people who have voted, while voting is open.';
  end if;
  if p_reaction not in ('fire', 'laugh', 'hundred', 'eyes', 'heart', 'grimace') then
    raise exception 'That reaction isn''t one of the six.';
  end if;
  if p_on then
    insert into public.site_lounge_reactions (message_id, user_id, reaction)
    values (p_message, auth.uid(), p_reaction) on conflict do nothing;
  else
    delete from public.site_lounge_reactions
     where message_id = p_message and user_id = auth.uid() and reaction = p_reaction;
  end if;
end;
$$;

-- The admin takes a message down, without learning who wrote it.
create or replace function public.lounge_remove(p_message bigint)
returns void language plpgsql security definer set search_path = public as $$
begin
  if not public.is_admin() then
    raise exception 'Only the admin can remove a message.';
  end if;
  update public.site_lounge_messages set removed_at = now() where id = p_message and removed_at is null;
end;
$$;

revoke all on function public.lounge_alias_name(int) from public, anon, authenticated;
revoke all on function public.lounge_state(uuid, boolean) from public, anon, authenticated;
revoke all on function public.lounge_can(uuid, boolean, boolean) from public, anon, authenticated;
revoke all on function public.lounge_alias(uuid, boolean) from public, anon, authenticated;
revoke all on function public.lounge_gap(boolean) from public, anon, authenticated;
revoke all on function public.lounge_status(uuid, boolean) from public, anon;
grant execute on function public.lounge_status(uuid, boolean) to authenticated;
revoke all on function public.lounge_messages(uuid, boolean) from public, anon;
grant execute on function public.lounge_messages(uuid, boolean) to authenticated;
revoke all on function public.lounge_post(uuid, boolean, text) from public, anon;
grant execute on function public.lounge_post(uuid, boolean, text) to authenticated;
revoke all on function public.lounge_react(bigint, text, boolean) from public, anon;
grant execute on function public.lounge_react(bigint, text, boolean) to authenticated;
revoke all on function public.lounge_remove(bigint) from public, anon;
grant execute on function public.lounge_remove(bigint) to authenticated;
