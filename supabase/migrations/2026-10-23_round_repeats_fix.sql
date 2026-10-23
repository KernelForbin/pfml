-- Fix for 2026-10-23_round_repeats.sql. Run once in the Supabase SQL Editor
-- for the live project, after it. Safe to re-run.
--
-- That migration's length limits were written as regex counts ({0,300},
-- {0,600}), and Postgres takes no count above 255: every fp_ok() call, and
-- any write to the two columns, fails with "invalid regular expression:
-- invalid repetition count(s)". Found 2026-10-23 by
-- tests/test_live_round_repeats.py on the live project, before any page used
-- it; the migration itself ran clean because a check on an empty column is
-- never evaluated. The limits are now char_length(); the regex only checks
-- the characters. 2026-10-23_round_repeats.sql and schema.sql were corrected
-- the same way, for a fresh install.

-- the two column checks, whatever Postgres named them
do $$
declare c record;
begin
  for c in select conname from pg_constraint
            where conrelid = 'public.site_submissions'::regclass and contype = 'c'
              and pg_get_constraintdef(oid) ~ 'fp_(song|text)'
  loop
    execute format('alter table public.site_submissions drop constraint %I', c.conname);
  end loop;
end $$;

alter table public.site_submissions add constraint site_submissions_fp_song_check
  check (char_length(fp_song) <= 300 and fp_song ~ '^[a-z0-9 ]*$');
alter table public.site_submissions add constraint site_submissions_fp_text_check
  check (char_length(fp_text) <= 600 and fp_text ~ '^[a-z0-9 ]*$');

create or replace function public.fp_ok(p_song text, p_names text[], p_text text)
returns boolean language sql immutable set search_path = public as $$
  select char_length(coalesce(p_song, '')) <= 300 and coalesce(p_song, '') ~ '^[a-z0-9 ]*$'
     and char_length(coalesce(p_text, '')) <= 600 and coalesce(p_text, '') ~ '^[a-z0-9 ]*$'
     and coalesce(cardinality(p_names), 0) <= 12
     and not exists (select 1 from unnest(coalesce(p_names, '{}'::text[])) n
                      where n is null or char_length(n) > 120 or n !~ '^[a-z0-9 ]+$');
$$;
