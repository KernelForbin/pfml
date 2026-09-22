-- Run once, by hand, in the live project's SQL Editor
-- (https://supabase.com/dashboard -> the PFML project -> SQL Editor).
-- schema.sql is only for a brand new project ("run once" at setup); this
-- is for the project that's already running, whose comment_reactions
-- table still has the old constraint. Needed before the round page's
-- searchable emoji picker (anything beyond the original 6 quick
-- reactions) will save: without it, Supabase rejects every new reaction
-- value with a check-constraint error.
--
-- What it does: comment_reactions.reaction was `check (reaction in
-- ('fire', 'laugh', 'hundred', 'eyes', 'grimace', 'heart'))`. This finds
-- that constraint by definition (not by a guessed name) and replaces it
-- with a length check, since the column now also holds whichever emoji
-- character a member picked. Existing rows (all 6 old names, 1-8
-- characters) already satisfy it; nothing is deleted or changed.
--
-- Safe to run more than once: the DROP step only runs if a matching
-- constraint is still there, but a second run will fail on the ADD step
-- ("already exists") once the first has succeeded -- that failure means
-- it's already done, not that anything went wrong.

do $$
declare
  con text;
begin
  select conname into con
    from pg_constraint
    where conrelid = 'public.comment_reactions'::regclass
      and contype = 'c'
      and pg_get_constraintdef(oid) ilike '%reaction%';
  if con is not null then
    execute format('alter table public.comment_reactions drop constraint %I', con);
  end if;
end $$;

alter table public.comment_reactions
  add constraint comment_reactions_reaction_check
  check (char_length(reaction) between 1 and 32);
