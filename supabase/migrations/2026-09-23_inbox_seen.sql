-- Run once, by hand, in the live project's SQL Editor
-- (https://supabase.com/dashboard -> the PFML project -> SQL Editor).
-- Needed before the header's inbox can tell new from already-seen: without
-- it the inbox still lists reactions and replies, but can't show a count
-- of new ones or remember that you've looked.
--
-- What it does: adds members.inbox_seen_at (when this member last opened
-- their inbox; empty until the first time) and mark_inbox_seen(), which
-- sets it to now() for the signed-in member only. members has no UPDATE
-- policy on purpose (a member mustn't be able to change their role or
-- player), so the function is security definer and touches only
-- inbox_seen_at on the caller's own row. Nothing existing is changed.
--
-- Safe to run more than once.

alter table public.members add column if not exists inbox_seen_at timestamptz;

create or replace function public.mark_inbox_seen()
returns timestamptz language sql security definer set search_path = public as $$
  update public.members set inbox_seen_at = now() where user_id = auth.uid() returning inbox_seen_at;
$$;

revoke all on function public.mark_inbox_seen() from public, anon;
grant execute on function public.mark_inbox_seen() to authenticated;
