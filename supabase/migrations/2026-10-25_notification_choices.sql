-- Notification choices and inbox notifications (README, Reminders). Run
-- once in the Supabase SQL Editor for the live project, after
-- 2026-10-25_reminders.sql. Safe to re-run. supabase/schema.sql, and
-- 2026-10-25_reminders.sql itself for a fresh install, have the same.
--
-- The bell in the top bar (asked for 2026-10-25) lets each member turn each
-- kind of notification on or off, and adds replies and reactions on their
-- own comments. One new table, reached only through the functions below,
-- so no API grants (the 2026-10-30 change), and they're revoked outright.

-- ---------------------------------------------------------------- notification choices

alter table public.reminder_settings add column if not exists round_open boolean not null default true;
alter table public.reminder_settings add column if not exists playlist_ready boolean not null default true;
alter table public.reminder_settings add column if not exists replies boolean not null default true;
alter table public.reminder_settings add column if not exists reactions boolean not null default true;
alter table public.reminder_settings add column if not exists voting boolean not null default true;
-- How far each member's inbox notifications have got: replies and
-- reactions after this have yet to be told.
create table if not exists public.inbox_notified (
  user_id uuid primary key references auth.users (id) on delete cascade,
  through timestamptz not null
);
alter table public.inbox_notified enable row level security;
revoke all on table public.inbox_notified from anon, authenticated;

-- The reminder finder again, now leaving out kinds a member turned off.
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
     where r.phase = 'submitting' and r.created_at > now() - interval '6 hours'
    union all
    select r.id, 'playlist_ready', m.user_id
      from rounds r cross join public.members m
     where r.playlists_built_at is not null and r.playlists_built_at > now() - interval '12 hours'
    union all
    select r.id, k.kind, o.user_id
      from rounds r
      cross join lateral (
        select t.kind from (values
            ('vote_halfway', r.voting_opened + (r.voting_closes_at - r.voting_opened) / 2),
            ('vote_5h', r.voting_closes_at - interval '5 hours'),
            ('vote_2h', r.voting_closes_at - interval '2 hours'),
            ('vote_1h', r.voting_closes_at - interval '1 hour')) as t(kind, due)
         where t.due <= now() and t.due >= r.voting_opened
         order by t.due desc limit 1) k
      join public.site_submission_owners o on o.round_id = r.id
     where r.phase = 'voting'
       and not exists (select 1 from public.site_votes v where v.round_id = r.id and v.user_id = o.user_id)),
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
  select c.round_id, c.kind, c.user_id, c.channel, r.name,
         case when c.kind like 'vote%' then r.voting_closes_at else r.closes_at end,
         case when c.channel = 'email' then (select u.email from auth.users u where u.id = c.user_id) end,
         case when c.channel = 'push' then (
           select coalesce(jsonb_agg(jsonb_build_object('endpoint', s.endpoint, 'p256dh', s.p256dh, 'auth', s.auth)), '[]'::jsonb)
             from public.push_subscriptions s where s.user_id = c.user_id) end
    from claimed c join public.site_rounds r on r.id = c.round_id;
$$;

-- The caller's choices, for the bell's switches.
create or replace function public.my_notification_choices()
returns table (round_open boolean, playlist_ready boolean, replies boolean, reactions boolean, voting boolean)
language sql stable security definer set search_path = public as $$
  select coalesce(s.round_open, true), coalesce(s.playlist_ready, true), coalesce(s.replies, true),
         coalesce(s.reactions, true), coalesce(s.voting, true)
    from (select 1) one
    left join public.reminder_settings s on s.user_id = auth.uid()
   where public.is_member();
$$;

-- One of the caller's switches; only these five names, so the column name
-- in the update can only ever be one of them.
create or replace function public.set_notification_choice(p_kind text, p_on boolean)
returns void language plpgsql security definer set search_path = public as $$
begin
  if not public.is_member() then
    raise exception 'Only league members have notifications.';
  end if;
  if p_kind is null or p_kind not in ('round_open', 'playlist_ready', 'replies', 'reactions', 'voting') or p_on is null then
    raise exception 'That isn''t a notification you can turn on or off.';
  end if;
  insert into public.reminder_settings (user_id) values (auth.uid()) on conflict (user_id) do nothing;
  execute format('update public.reminder_settings set %I = $1 where user_id = $2', p_kind) using p_on, auth.uid();
end;
$$;

-- New replies and reactions on members' own comments (what their inbox
-- shows: a comment id ends with the commenter's player id), for the sender
-- only: one summary per member with a device, push only. Counted from when
-- they first turned a device on and never from more than a day back, so
-- turning on doesn't bring a flood; their own replies and reactions don't
-- count; each kind only if they want it. Runs one at a time (the lock), and
-- moves everyone's mark to now, so nothing is told twice.
create or replace function public.inbox_claim()
returns table (user_id uuid, replies int, reactions int, last_kind text, last_actor text, last_text text,
               subscriptions jsonb)
language plpgsql security definer set search_path = public as $$
#variable_conflict use_column
declare
  cutoff timestamptz := now();
begin
  perform pg_advisory_xact_lock(hashtext('pfml.inbox_claim'));
  return query
  with eligible as (
    select m.user_id, m.competitor_id,
           greatest(coalesce(n.through, (select min(s.created_at) from public.push_subscriptions s where s.user_id = m.user_id)),
                    cutoff - interval '1 day') as since,
           coalesce(rs.replies, true) as want_replies,
           coalesce(rs.reactions, true) as want_reactions
      from public.members m
      left join public.inbox_notified n on n.user_id = m.user_id
      left join public.reminder_settings rs on rs.user_id = m.user_id
     where exists (select 1 from public.push_subscriptions s where s.user_id = m.user_id)),
  items as (
    select e.user_id, 'reply'::text as kind, r.user_id as actor, r.body as body, r.created_at
      from eligible e
      join public.comment_replies r on split_part(r.comment_id, '|', 3) = e.competitor_id
     where e.want_replies and r.user_id <> e.user_id and r.created_at > e.since and r.created_at <= cutoff
    union all
    select e.user_id, 'reaction', x.user_id, x.reaction, x.created_at
      from eligible e
      join public.comment_reactions x on split_part(x.comment_id, '|', 3) = e.competitor_id
     where e.want_reactions and x.user_id <> e.user_id and x.created_at > e.since and x.created_at <= cutoff),
  latest as (
    select distinct on (i.user_id) i.user_id, i.kind, i.actor, i.body
      from items i order by i.user_id, i.created_at desc)
  select i.user_id,
         (count(*) filter (where i.kind = 'reply'))::int,
         (count(*) filter (where i.kind = 'reaction'))::int,
         l.kind,
         coalesce((select p.name from public.members am join public.players p on p.competitor_id = am.competitor_id
                    where am.user_id = l.actor), 'A member'),
         left(l.body, 140),
         (select coalesce(jsonb_agg(jsonb_build_object('endpoint', s.endpoint, 'p256dh', s.p256dh, 'auth', s.auth)), '[]'::jsonb)
            from public.push_subscriptions s where s.user_id = i.user_id)
    from items i join latest l on l.user_id = i.user_id
   group by i.user_id, l.kind, l.actor, l.body;

  insert into public.inbox_notified (user_id, through)
  select distinct s.user_id, cutoff from public.push_subscriptions s
  on conflict (user_id) do update set through = excluded.through;
end;
$$;

revoke all on function public.my_notification_choices() from public, anon;
grant execute on function public.my_notification_choices() to authenticated;
revoke all on function public.set_notification_choice(text, boolean) from public, anon;
grant execute on function public.set_notification_choice(text, boolean) to authenticated;
revoke all on function public.inbox_claim() from public, anon, authenticated;
grant execute on function public.inbox_claim() to service_role;
