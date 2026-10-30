-- Someone new (README, Someone new). Run once in the Supabase SQL Editor for
-- the live project, after 2026-10-29_hidden_prompts_names.sql. Safe to
-- re-run. supabase/schema.sql has the same before its storage section, for
-- a fresh install.
--
-- Asked for 2026-10-29: room for people who never played in Music League,
-- such as someone joining only to vote as a Spectator. Until now the players
-- table held only Music League's competitors (publish.py fills it), so a
-- newcomer couldn't be picked for a season or sent an invite. The admin or
-- a commissioner now adds them by name; scripts/invites.py then makes their
-- link like anyone else's. Their id starts "site" so it can never be
-- mistaken for a Music League one, and publish.py, which only adds and
-- updates Music League's players, leaves them be.

-- ---------------------------------------------------------------- someone new

create or replace function public.add_player(p_name text)
returns text language plpgsql security definer set search_path = public as $$
declare
  body text := regexp_replace(btrim(coalesce(p_name, '')), '\s+', ' ', 'g');
  cid text;
begin
  if not public.is_commissioner() then
    raise exception 'Only the admin or a commissioner can add someone.';
  end if;
  if char_length(body) not between 1 and 60 then
    raise exception 'A name is 1 to 60 characters.';
  end if;
  -- invites.py finds a player by name, so two can't share one
  if exists (select 1 from public.players p where lower(p.name) = lower(body)) then
    raise exception 'There''s already a player called %.', body;
  end if;
  cid := 'site' || replace(gen_random_uuid()::text, '-', '');
  insert into public.players (competitor_id, name) values (cid, body);
  return cid;
end;
$$;

revoke all on function public.add_player(text) from public, anon;
grant execute on function public.add_player(text) to authenticated;
