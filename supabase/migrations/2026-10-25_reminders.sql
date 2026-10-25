-- Reminders: app notifications now, email later (README, Reminders). Run
-- once in the Supabase SQL Editor for the live project, after
-- 2026-10-25_site_rounds_export.sql. Safe to re-run. supabase/schema.sql has
-- the same, for a fresh install. The timer that runs the sender every five
-- minutes is separate: supabase/setup/reminders_cron.sql, once the Edge
-- Function is deployed.
--
-- New tables are only reached through the security definer functions below,
-- so they get no API grants (the 2026-10-30 change), and grants are revoked
-- outright in case the project still hands them out.

-- ---------------------------------------------------------------- reminders

-- One row per phone or browser a member turned notifications on in: what
-- the push service needs to reach it. The endpoint belongs to whoever
-- turned it on last on that device.
create table if not exists public.push_subscriptions (
  endpoint   text primary key check (endpoint ~ '^https://' and char_length(endpoint) <= 1000),
  user_id    uuid not null references auth.users (id) on delete cascade,
  p256dh     text not null check (p256dh ~ '^[A-Za-z0-9_-]{80,100}$'),
  auth       text not null check (auth ~ '^[A-Za-z0-9_-]{16,32}$'),
  created_at timestamptz not null default now()
);
create index if not exists push_subscriptions_user on public.push_subscriptions (user_id);
alter table public.push_subscriptions enable row level security;
revoke all on table public.push_subscriptions from anon, authenticated;

-- Each member's choices: email (for when it's switched on), and which kinds
-- of notification they want, all on unless turned off. No row means all on.
create table if not exists public.reminder_settings (
  user_id  uuid primary key references auth.users (id) on delete cascade,
  email_on boolean not null default true
);
alter table public.reminder_settings add column if not exists round_open boolean not null default true;
alter table public.reminder_settings add column if not exists playlist_ready boolean not null default true;
alter table public.reminder_settings add column if not exists replies boolean not null default true;
alter table public.reminder_settings add column if not exists reactions boolean not null default true;
alter table public.reminder_settings add column if not exists voting boolean not null default true;
alter table public.reminder_settings enable row level security;
revoke all on table public.reminder_settings from anon, authenticated;

-- Every reminder sent, so none goes twice: claimed before it's sent.
create table if not exists public.reminders_sent (
  round_id uuid not null references public.site_rounds (id) on delete cascade,
  kind     text not null check (kind in ('round_open', 'playlist_ready',
                                         'vote_halfway', 'vote_5h', 'vote_2h', 'vote_1h')),
  user_id  uuid not null references auth.users (id) on delete cascade,
  channel  text not null check (channel in ('push', 'email')),
  sent_at  timestamptz not null default now(),
  primary key (round_id, kind, user_id, channel)
);
alter table public.reminders_sent enable row level security;
revoke all on table public.reminders_sent from anon, authenticated;

-- How far each member's inbox notifications have got: replies and
-- reactions after this have yet to be told.
create table if not exists public.inbox_notified (
  user_id uuid primary key references auth.users (id) on delete cascade,
  through timestamptz not null
);
alter table public.inbox_notified enable row level security;
revoke all on table public.inbox_notified from anon, authenticated;

-- A member turns notifications on (or again) on this device.
create or replace function public.save_push_subscription(p_endpoint text, p_p256dh text, p_auth text)
returns void language plpgsql security definer set search_path = public as $$
begin
  if not public.is_member() then
    raise exception 'Only league members can turn on notifications.';
  end if;
  insert into public.push_subscriptions (endpoint, user_id, p256dh, auth)
  values (p_endpoint, auth.uid(), p_p256dh, p_auth)
  on conflict (endpoint) do update
     set user_id = excluded.user_id, p256dh = excluded.p256dh, auth = excluded.auth, created_at = now();
  if (select count(*) from public.push_subscriptions where user_id = auth.uid()) > 10 then
    raise exception 'That''s more devices than notifications can go to. Turn them off on one you don''t use.';
  end if;
end;
$$;

-- A member turns notifications off on this device.
create or replace function public.remove_push_subscription(p_endpoint text)
returns void language sql security definer set search_path = public as $$
  delete from public.push_subscriptions where endpoint = p_endpoint and user_id = auth.uid();
$$;

-- The caller's own devices, for "Send me a test": nobody else's.
create or replace function public.my_push_subscriptions()
returns table (endpoint text, p256dh text, auth text)
language sql stable security definer set search_path = public as $$
  select s.endpoint, s.p256dh, s.auth from public.push_subscriptions s
   where s.user_id = auth.uid() and public.is_member();
$$;

-- Email reminders on or off, for the caller (the switch isn't on the site
-- until email is).
create or replace function public.set_email_reminders(p_on boolean)
returns void language plpgsql security definer set search_path = public as $$
begin
  if not public.is_member() then
    raise exception 'Only league members have reminders.';
  end if;
  insert into public.reminder_settings (user_id, email_on) values (auth.uid(), p_on)
  on conflict (user_id) do update set email_on = excluded.email_on;
end;
$$;

-- What's due now, claimed so no other run sends it: for the sender only
-- (send-reminders, with the secret key). p_channels is what the sender can
-- send ('push', and 'email' once it has an email key). Who gets what:
--   round_open      everyone, for a round opened in the last 6 hours (so one
--                   open before reminders existed isn't announced late)
--   playlist_ready  everyone, for playlists built in the last 12 hours
--   vote_*          a round voted on the site, during voting: only players
--                   with a track in it who haven't voted. Of halfway, 5, 2
--                   and 1 hour left, only the latest that's passed, and none
--                   from before voting opened, so a late run never sends a
--                   pile and a short window never says "5 hours" with 3 left.
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

-- A device the push service says is gone (404 or 410): the sender forgets it.
create or replace function public.forget_push_endpoint(p_endpoint text)
returns void language sql security definer set search_path = public as $$
  delete from public.push_subscriptions where endpoint = p_endpoint;
$$;

-- Email's unsubscribe link (later): turns email off for that member.
create or replace function public.email_reminders_off(p_user uuid)
returns void language sql security definer set search_path = public as $$
  insert into public.reminder_settings (user_id, email_on) values (p_user, false)
  on conflict (user_id) do update set email_on = false;
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

revoke all on function public.save_push_subscription(text, text, text) from public, anon;
grant execute on function public.save_push_subscription(text, text, text) to authenticated;
revoke all on function public.remove_push_subscription(text) from public, anon;
grant execute on function public.remove_push_subscription(text) to authenticated;
revoke all on function public.my_push_subscriptions() from public, anon;
grant execute on function public.my_push_subscriptions() to authenticated;
revoke all on function public.set_email_reminders(boolean) from public, anon;
grant execute on function public.set_email_reminders(boolean) to authenticated;
revoke all on function public.reminders_claim(text[]) from public, anon, authenticated;
grant execute on function public.reminders_claim(text[]) to service_role;
revoke all on function public.forget_push_endpoint(text) from public, anon, authenticated;
grant execute on function public.forget_push_endpoint(text) to service_role;
revoke all on function public.email_reminders_off(uuid) from public, anon, authenticated;
grant execute on function public.email_reminders_off(uuid) to service_role;
revoke all on function public.my_notification_choices() from public, anon;
grant execute on function public.my_notification_choices() to authenticated;
revoke all on function public.set_notification_choice(text, boolean) from public, anon;
grant execute on function public.set_notification_choice(text, boolean) to authenticated;
revoke all on function public.inbox_claim() from public, anon, authenticated;
grant execute on function public.inbox_claim() to service_role;
