-- Invite status for the admin's league panel on the Submit page (README,
-- Submissions on the site, Admin status). Run once in the Supabase SQL
-- Editor for the live project, after 2026-10-23_round_submitters.sql. Safe
-- to re-run. supabase/schema.sql has the same, for a fresh install. No new
-- table, so the 2026-10-30 grant change doesn't apply.
--
-- invites has no policies (secret key only), so the panel can't read it.
-- This tells the admin, and nobody else, which players have a link made
-- and not used yet, and when it was made: never the link itself, which
-- scripts/invites.py prints for the admin to send privately.

create or replace function public.admin_invite_status()
returns table (competitor_id text, made_at timestamptz)
language plpgsql stable security definer set search_path = public as $$
begin
  if not public.is_admin() then
    raise exception 'Only the admin can see invite status.';
  end if;
  return query
    select i.competitor_id, max(i.created_at)
      from public.invites i
     where i.claimed_by is null
     group by i.competitor_id
     order by i.competitor_id;
end;
$$;

revoke all on function public.admin_invite_status() from public, anon;
grant execute on function public.admin_invite_status() to authenticated;
