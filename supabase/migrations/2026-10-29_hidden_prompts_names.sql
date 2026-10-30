-- The last step of hidden prompts (README, Hidden prompts and guesses). Run
-- once in the Supabase SQL Editor, only after the pages that read rounds
-- through site_rounds_list() are live on pfml.fun (the hidden-prompts
-- push). Safe to re-run.
--
-- 2026-10-29_hidden_prompts_hotfix.sql gave members back the names and
-- prompts of rounds while the old pages still read them from the table.
-- Once the new pages are live nothing on the site reads them that way, so
-- this takes them away again: a Spectator can then learn a hidden prompt
-- only when voting closes.

revoke select (name, prompt) on table public.site_rounds from authenticated;
