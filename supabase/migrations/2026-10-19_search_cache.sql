-- Search on the Submit page (README, Submissions on the site, Searching).
-- Run once in the Supabase SQL Editor. Safe to re-run. supabase/schema.sql
-- has the same, for a fresh install.
--
-- The search-tracks Edge Function keeps YouTube answers here for a week,
-- so a repeated search doesn't spend YouTube's 100-a-day allowance. It
-- holds the service, the search text and the day: never who searched,
-- which next to a submission could give the submitter away. Row level
-- security on and no policies: only the function's secret key reads or
-- writes it.

create table if not exists public.search_cache (
  service   text not null check (service in ('spotify', 'youtube')),
  query     text not null check (char_length(query) between 1 and 120),
  results   jsonb not null,
  cached_on date not null default current_date,
  primary key (service, query)
);

alter table public.search_cache enable row level security;   -- no policies: secret key only
