-- A rehearsal of who gets which reminder, run by the real database and then
-- undone: nothing it does is kept. Run it in the Supabase SQL Editor after
-- supabase/migrations/2026-10-25_reminders.sql (README, Reminders). It
-- always ends in an error, on purpose, because an error rolls everything
-- back:
--
--   "Rehearsal passed: 12 checks held. Nothing was kept."  every rule held
--   "Rehearsal FAILED: ..."                               says which didn't
--
-- It makes made-up rounds and gives the first three members to join made-up
-- devices (https://push.example.invalid/...), then asks reminders_claim()
-- what's due. Nothing is sent: claiming only records. All of it is rolled
-- back, the records included.

do $$
declare
  a uuid; b uuid; c uuid;
  r_open uuid; r_old uuid; r_voting uuid; r_half uuid;
  sa uuid; sb uuid;
  checks int := 0;
  n int;
begin
  select user_id into a from public.members order by created_at, user_id limit 1;
  select user_id into b from public.members order by created_at, user_id offset 1 limit 1;
  select user_id into c from public.members order by created_at, user_id offset 2 limit 1;
  if c is null then raise exception 'Rehearsal FAILED: it needs at least three members'; end if;

  -- A and B have a device each; C has none
  insert into public.push_subscriptions (endpoint, user_id, p256dh, auth) values
    ('https://push.example.invalid/a', a, repeat('A', 87), repeat('a', 22)),
    ('https://push.example.invalid/b', b, repeat('B', 87), repeat('b', 22));

  -- 1. A round opened just now is announced to A and B, once.
  insert into public.site_rounds (season_key, name, closes_at) values ('season99', 'Rehearsal open', now() + interval '2 days')
  returning id into r_open;
  -- a round opened before reminders existed (7 hours ago) isn't
  insert into public.site_rounds (season_key, name, closes_at, created_at)
  values ('season99', 'Rehearsal old', now() + interval '2 days', now() - interval '7 hours') returning id into r_old;
  create temp table claimed on commit drop as select * from public.reminders_claim(array['push']);
  if (select count(*) from claimed where round_id = r_open and kind = 'round_open') <> 2
     or exists (select 1 from claimed where round_id = r_open and user_id = c) then
    raise exception 'Rehearsal FAILED: a new round should reach A and B (they have devices) and not C';
  end if;
  checks := checks + 1;
  if exists (select 1 from claimed where round_id = r_old) then
    raise exception 'Rehearsal FAILED: a round opened 7 hours ago was announced';
  end if;
  checks := checks + 1;
  if (select count(*) from claimed where round_id = r_open and subscriptions is not null
        and jsonb_array_length(subscriptions) = 1 and channel = 'push') <> 2 then
    raise exception 'Rehearsal FAILED: each push claim should carry the member''s one device';
  end if;
  checks := checks + 1;
  if exists (select 1 from public.reminders_claim(array['push']) where round_id = r_open) then
    raise exception 'Rehearsal FAILED: the second run announced the round again';
  end if;
  checks := checks + 1;

  -- 2. Playlists built: everyone with a device hears, once.
  update public.site_rounds set playlists_built_at = now() where id = r_old;
  if (select count(*) from public.reminders_claim(array['push']) where round_id = r_old and kind = 'playlist_ready') <> 2 then
    raise exception 'Rehearsal FAILED: a new playlist should reach A and B';
  end if;
  checks := checks + 1;

  -- 3. Voting: only submitters who haven't voted, and only the latest
  --    reminder due. This round's voting opened 10 hours ago and closes in
  --    50 minutes, so halfway, 5 hours and 2 hours have all passed: only
  --    "1 hour" goes, to A. B has voted; C has no track in it.
  insert into public.site_rounds (season_key, name, closes_at, votes_on_site, voting_closes_at)
  values ('season99', 'Rehearsal voting', now() - interval '10 hours', true, now() + interval '50 minutes')
  returning id into r_voting;
  insert into public.site_submissions (round_id, tag, platform, track) values (r_voting, 'A2', 'youtube', 'aaaaaaaaaaa') returning id into sa;
  insert into public.site_submissions (round_id, tag, platform, track) values (r_voting, 'B3', 'youtube', 'bbbbbbbbbbb') returning id into sb;
  insert into public.site_submission_owners (submission_id, round_id, user_id) values (sa, r_voting, a), (sb, r_voting, b);
  insert into public.site_votes (round_id, submission_id, user_id, points) values (r_voting, sa, b, 19);
  create temp table voting on commit drop as
    select * from public.reminders_claim(array['push']) where round_id = r_voting;
  if (select count(*) from voting) <> 1 or not exists (select 1 from voting where user_id = a and kind = 'vote_1h') then
    raise exception 'Rehearsal FAILED: only A (no ballot yet) should get "1 hour left", and nothing else';
  end if;
  checks := checks + 1;
  if exists (select 1 from public.reminders_claim(array['push']) where round_id = r_voting) then
    raise exception 'Rehearsal FAILED: the second run sent a voting reminder again';
  end if;
  checks := checks + 1;

  -- 4. Halfway alone: voting opened 12 hours ago and closes in 10.
  insert into public.site_rounds (season_key, name, closes_at, votes_on_site, voting_closes_at)
  values ('season99', 'Rehearsal halfway', now() - interval '12 hours', true, now() + interval '10 hours')
  returning id into r_half;
  insert into public.site_submissions (round_id, tag, platform, track) values (r_half, 'C4', 'youtube', 'ccccccccccc') returning id into sa;
  insert into public.site_submission_owners (submission_id, round_id, user_id) values (sa, r_half, a);
  select count(*) into n from public.reminders_claim(array['push']) where round_id = r_half and user_id = a and kind = 'vote_halfway';
  if n <> 1 then raise exception 'Rehearsal FAILED: halfway should be the one due (got %)', n; end if;
  checks := checks + 1;

  -- 5. A device that's gone is forgotten.
  perform public.forget_push_endpoint('https://push.example.invalid/b');
  if exists (select 1 from public.push_subscriptions where endpoint = 'https://push.example.invalid/b') then
    raise exception 'Rehearsal FAILED: forget_push_endpoint left the device';
  end if;
  checks := checks + 1;

  -- 6. Email, for later: everyone with an address, except someone who
  --    turned it off; push-only runs never claim email.
  if exists (select 1 from claimed where channel = 'email') then
    raise exception 'Rehearsal FAILED: a push-only run claimed email';
  end if;
  checks := checks + 1;
  perform public.email_reminders_off(c);
  create temp table emails on commit drop as
    select * from public.reminders_claim(array['email']) where round_id = r_open;
  if exists (select 1 from emails where user_id = c) or not exists (select 1 from emails where user_id = a and email is not null) then
    raise exception 'Rehearsal FAILED: email should reach A (with the address) and not C, who turned it off';
  end if;
  checks := checks + 1;

  -- 7. Nothing at all with no channel.
  if exists (select 1 from public.reminders_claim(array[]::text[])) then
    raise exception 'Rehearsal FAILED: a run with no channel claimed something';
  end if;
  checks := checks + 1;

  raise exception 'Rehearsal passed: % checks held. Nothing was kept.', checks;
end $$;
