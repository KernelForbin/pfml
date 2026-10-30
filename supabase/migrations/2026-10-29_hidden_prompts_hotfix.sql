-- Hotfix for 2026-10-29_hidden_prompts.sql (README, Hidden prompts and
-- guesses). Run once in the Supabase SQL Editor, straight away. Safe to
-- re-run.
--
-- Found 2026-10-29 by the rehearsal's own error ("permission denied for
-- function site_hides_from"): a row-level security policy runs with the
-- reader's own rights, so a function a policy calls must be executable by
-- them. The policies on site_round_prompters and site_submission_notes call
-- site_hides_from(), which the migration had kept from members, so every
-- member's read of those tables failed. It answers only whether a round
-- hides something from an account, which members' pages work out anyway.
--
-- And the pages on pfml.fun still read round names and prompts straight
-- from site_rounds until the new pages ship, so members get those two
-- columns back for now. 2026-10-29_hidden_prompts_names.sql takes them away
-- again, once the pages that read through site_rounds_list() are live.

grant execute on function public.site_hides_from(uuid, uuid, text) to authenticated;
grant select (name, prompt) on table public.site_rounds to authenticated;
