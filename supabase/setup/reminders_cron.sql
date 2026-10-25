-- The five-minute timer that sends reminders (README, Reminders). Run once in
-- the Supabase SQL Editor, after:
--   1. supabase/migrations/2026-10-25_reminders.sql
--   2. Database > Extensions: pg_cron and pg_net turned on
--   3. the send-reminders Edge Function deployed, with its secrets
--
-- PASTE_THE_REMINDERS_SECRET stands for the function's REMINDERS_SECRET: the
-- copy Claude puts on your clipboard has it filled in. It goes into Vault, so
-- it's never in this file, the repo or the job's text.
--
-- To stop the timer: select cron.unschedule('pfml-reminders');

select vault.create_secret('PASTE_THE_REMINDERS_SECRET', 'reminders_secret', 'send-reminders: the timer''s shared secret');

select cron.schedule('pfml-reminders', '*/5 * * * *', $job$
  select net.http_post(
    url := 'https://usdyarwpvsxkkwqibdpt.supabase.co/functions/v1/send-reminders',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'x-reminders-secret', (select decrypted_secret from vault.decrypted_secrets where name = 'reminders_secret')),
    body := '{}'::jsonb,
    timeout_milliseconds := 30000);
$job$);
