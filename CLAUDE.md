# CLAUDE.md

Context for Claude Code sessions on this repo. This file loads automatically
at the start of every session. It isn't where architecture or feature docs
live, that's `README.md`, this is for things a fresh session would otherwise
have to be told by hand.

## Read first

- `README.md` — architecture, how `build.py` works, season pages, the
  Career Score formula, the taste (points a round) math, and the scoring model quirks
  that aren't obvious from the CSVs (a fixed point budget per voter per
  round, 16 in Seasons 1-2 and 19 in Season 3; a 0-point vote row is a
  comment, not a vote; self-voting is blocked).
- `CHANGELOG.md` — what's shipped, in order, and why.

## The site is members-only: data never goes in this repo

pfml.fun is behind Google sign-in, and the league data (the CSVs in
`data/`, the JSON in `site/data/`) is served from a private Supabase bucket
that only linked members can read. The repo is public, so:

- `data/` and `site/data/` are git-ignored. Never force-add them, and
  never commit a CSV, a season/career JSON, `daily_doubles.json` or `.env`.
  The deploy workflow fails if a JSON, CSV or `.env*` file shows up in
  `site/`, or a `data/` folder in the repo.
- Publish data with `python scripts/publish.py` (builds, then uploads).
  Data changes need no commit; only a new `site/seasonN.html` does.
- The Supabase secret key lives only in the git-ignored `.env`. It bypasses
  every access rule. Don't print it, don't paste it anywhere, don't put it
  in `site/config.js` (that file holds the *publishable* key, which is
  public by design).
- Invite links (`python scripts/invites.py`) each link a Google account to
  a player permanently. Hand them to the user to send privately; don't
  send them anywhere yourself.

See README, Members only, for the setup and the access model.

## Before you push, check this

`git init` once ran in a parent folder (`Downloads`) instead of inside the
`pfml` project folder, so a push briefly carried two unrelated personal
projects into the public PFML repo on GitHub. The repo was deleted and
recreated, the stray `.git` is gone (2026-09-17), and this clone lives in
its own folder, `code/pfml`, well outside `Downloads`. Nothing stops it
recurring, so keep the habits:

- `git remote -v` — confirm origin is `https://github.com/KernelForbin/pfml.git`
- `git status` — confirm the changed files are only inside this project,
  nothing from a parent directory
- Run git commands from inside the `pfml` folder itself, never a level
  above it
- Never run `git init` anywhere but the project folder you mean to track

## Music League exports hold finished rounds only

A round in song submission or voting is not in the export at all: no round
row, no submissions, no votes. Measured 2026-09-21 against a real export
taken mid-round (details in README, The "live" season). So never infer a
round's phase from the export, and expect a new round to appear only once
it's over. An earlier "Voting phase" label on the Home page was built on
the opposite assumption, never checked, and was wrong for every season.

## "Update the data": fetching the export yourself

The user may ask for this from a phone (Remote Control), with nobody at
the keyboard, so it has to run without a click anywhere. Measured
2026-09-23 against the real league:

1. Claude in Chrome drives the user's own Chrome, which is signed in to
   Music League; the built-in browser pane is not, and Claude must never
   sign in for them. If no Chrome is connected, stop and say so.
   Two Chromes are usually connected here and only one is signed in, so a
   "Login with Spotify" page means the wrong one is selected, not that the
   session expired: `list_connected_browsers`, then `select_browser` on
   the other, before telling the user anything is wrong (it happened
   2026-09-23).
2. The league is `https://app.musicleague.com/l/<league id>/` (Season 3:
   `7cc28873ea734191a181253aa87b887d`). Clicking ⋯ → Export Data did
   nothing measurable; navigating the tab straight to `<league>/-/data`
   starts the download.
3. Chrome may hold the file as an unnamed `.tmp` in the user's Downloads,
   waiting for a Keep/Save click that lives in Chrome's own UI, not the
   page, so it can't be clicked from here. That doesn't matter: the file
   is already complete on disk. Take the newest file in Downloads written
   after the navigation, wait for its size to settle, and check it opens
   as a zip holding competitors.csv, rounds.csv, submissions.csv and
   votes.csv before using it.
   Delete that download at the end of every run, whether or not it held
   anything new: the user asked for it (2026-09-23), since these pile up
   as unnamed `.tmp` files they never see. Delete only the one file this
   run downloaded and checked, after the copy into `data/` (or after
   finding it identical), and never anything else in Downloads.
4. Compare with `data/seasonN/` before copying. A fresh export whose four
   CSVs are byte-identical means no new finished round (the export leaves
   out a round until it's over), so copy nothing and say so.
5. When it does differ: copy the four CSVs in, do the Daily Double review
   and the translation check below for each new round, then run
   `python scripts/publish.py`, and report what changed. The user gave a standing go-ahead (2026-09-23)
   for the publish inside this flow, so it needs no separate ask; it
   uploads data only. Pushing the repo still does.
6. Close the tab afterwards and delete any scratch copy.

## Building a closed site round's playlists

When a round on the Submit page has closed: `python scripts/round_playlists.py
--dry-run` first, and show the user the report: every track, what matched
where, and any match it was unsure of (with its link). Ask before using
`--accept` or setting a match by hand in `data/playlist_overrides.json`
(local, git-ignored). Then run it for real, which builds both playlists
on the user's own Spotify and YouTube accounts. That writes to their
accounts and to the database, so it needs their go-ahead each time. Never
read `site_submission_owners`; the script doesn't, and a test holds it.
README, Submissions on the site.

Listening to a closed round (its playlists, list and player) is on the
round's own page, `round?site=<id>`, for good, not on the Submit page
(README, Listening on the round page). On an iPhone the page can't play
track to track and Spotify only previews (measured 2026-10-26), so a phone
plays the YouTube copies in one ready-made player; the apps' playlists sit
below the list, marked as leaving the site. To try it, and the ballot,
use pfml.fun/round?demo=1 (`site/round-demo.js`; README, Round demo): the
newest closed round's real tracks, read from the database when the page
loads, as if that round voted here. Never put track data in the file
(the repo is public), and never let it send a real ballot or draft: its
practice ballot goes to `site_demo_ballots` only (README, Round demo).

## Season 3: review every new export for Daily Double requests

Season 3 has a Daily Double rule: once per season, a submitter can ask in
their own submission note to have that track's points doubled toward their
total. Whenever the user uploads a new Season 3 export, before building:

1. Read the submitter notes (`submissions.csv` "Comment") for the new
   round(s). Judge intent: a request, not a mention of the prop or a joke.
   When a note is genuinely ambiguous, ask the user rather than guess.
2. Record the outcome in `data/season3/daily_doubles.json`: add the round
   to `reviewedRounds` even when nothing was found, and add any request to
   `requests` as `accepted`, or as `rejected` with a reason (a second
   request from the same person is rejected). This file is local-only
   (git-ignored); `publish.py` backs it up with the exports.
3. Run `python scripts/publish.py` to build and publish.
4. Tell the user what you found, including "no requests this round".

The build applies only what the file says. It warns about unreviewed rounds
and refuses to build on malformed entries. See README, Daily Double.

## Translate comments that aren't in English

The user asked (2026-10-11) for every comment or note not in English to
show its English underneath. The build can't translate (offline, no API
key), so each new round gets a translation check, alongside the Daily
Double review:

1. Read the new round's vote comments (`votes.csv` "Comment") and
   submitter notes (`submissions.csv` "Comment"), all of them. Translate
   any written wholly or mainly in another language, mock languages
   included (label those honestly, e.g. "mock Norwegian"). Names, song
   titles and a stray foreign word in an English comment don't count.
   Theme rounds are where they turn up: Round 4 (Nordic) had 22 at once.
   A round voted on the site has its notes in
   `data/<season>/site_rounds.json` instead ("note" on each submission,
   "comment" on each vote). The build turns them into the same rows, so
   the keys are the same, with `build.site_uri(platform, track)` as the
   uri.
2. Add each to `data/translations.json` (local-only, git-ignored, backed
   up by `publish.py`): comments under `comments`, keyed by
   `build.comment_id(round id, spotify uri, voter id)`; notes under
   `notes`, keyed `"<round id>|<spotify uri>"`. Each entry is `from`
   (the language), `original` (the exact text, as `build.read_csv` gives
   it, stripped) and `text` (the English). Match by exact text in a
   script, never by retyping ids. The build skips an entry whose
   `original` no longer matches and names any id that matches nothing.
3. Tell the user what was translated, showing the original and the English.

See README, Translations.

## Keep the features page true

`site/features.html` (pfml.fun/features) is a plain-language tour of what
members can see and do, linked from Site features in the initials menu, Home's
What's new button and the sign-in card (not the footers, since 2026-10-25).
**Any change that adds, removes or visibly alters a feature updates that
page in the same change.** Every sentence on it has to be true of the code
as it ships.

Scope rule, so it never turns into a changelog: it lists only features
that are current, working and noticeable to an ordinary member, things
they see on screen or do themselves. No bug fixes, refactors, performance
work, data pipeline or backend changes, admin-only powers, or anything not
shipped yet. The test: would a regular member notice if this disappeared?
If not, it stays off.

**New in the last 30 days**, the box at its top: a major new feature that
members will notice also gets a line there, newest first, with
`data-shipped` set to its CHANGELOG heading's date (a test checks the date
is a real heading). Lines drop off on their own after 30 days, by the
reader's clock. Don't prune them by hand, and leave out fixes and small
tweaks. Move `FEATURES_UPDATED` in `app.js` to the newest line's date too:
that's what puts New on Home's What's new button (a test checks they match).

**How it's built**, the box at its bottom, is the one exception to the
scope rule (the user's call, 2026-10-25): built with Claude Opus 5.5, and
build stats that every deploy counts and writes into its own copy
(`scripts/stamp_build_stats.py`; README, Build stats). Never type the
numbers into the page: the repo's copy keeps its dashes, and the script
refuses a page missing one. Prompts and SQL queries stay off (not
countable; the user said no to "prompts since today").

It's standalone on purpose: public, no sign-in, no `style.css`, no
`app.js`, no data, nothing loaded but itself and its fonts. Its colour
tokens, light and dark, are copied from `style.css`, so a palette change
there updates them too (a test compares both).

## Voting on the site: on, for seasons set up on the site

Built 2026-10-25 so the league can eventually leave the Music League app,
and switched on the same day with seasons set up on the site
(`SITE_VOTING` in `account.js`, pinned by a test with the pages that say
so). Only a round in such a season votes here, on its round page, inside
the round's own track list: play, points and comment in one row, as it
plays (the user's call, 2026-10-26; README, Voting in the round's list).
Points and comments save on their own as a draft, to the member's account
(`site_ballot_drafts`), and only Submit, with every point given, counts
(README, Drafts). A draft must never reach `site_votes` or anything that
counts votes. The voters' lounge (README, Voters' lounge) is anonymous for
good: no lounge function may ever give out who wrote a message, the admin
included, and it never opens below 3 voters.
Players in a season set up on the site are DJs or Spectators (2026-10-29;
README, DJs and Spectators): a Spectator votes and comments but never
sends a track, and a round outside such a season (Round 7 and before)
has no roles, everyone a DJ. Spectators earn podium points (3/2/1 per
point given to a round's 1st/2nd/3rd; `PODIUM_POINTS` in `build.py` and
`account.js` must match). Hiding the prompt from Spectators and guessing
it were asked about and not built, the user's call.
Try changes there on pfml.fun/round?demo=1, since no round votes here
yet. Never let it reach Round 7,
Season 3 or any round already open: the database refuses a round opened by
hand that asks to, and refuses to change it later. README, Voting on the
site.

A finished site-voted round reaches the stats through `publish.py`, which
fetches it from `site_rounds_export()` (secret key only; it returns a round
only once its voting has closed) into `data/<season>/site_rounds.json`. So
"update the data" picks site rounds up too, and a publish is all a finished
site round needs. Never read `site_submission_owners` or `site_votes`
directly from a script: the export function is the one door, and it holds
the "only after voting closes" rule. README, Site rounds in the stats.

## Reminders

App notifications are built and set up (README, Reminders): the function
is deployed with its secrets, and the five-minute timer runs as `pg_cron`
job 1. Email is built but on hold. The user's calls (2026-10-25):

- **Now:** new round, playlist ready.
- **With voting:** halfway, 5h, 2h, 1h, only to players who haven't voted.
- **Email:** later, once they set up Resend and the DNS.
- **The bell** (2026-10-25): notifications live in a bell beside the inbox,
  not the initials menu, with a switch per kind. Replies and reactions on
  a member's own comments notify too (`inbox_claim`).

Rules for the work:

- **Order:** push the code only after the migration has run and
  `send-reminders` is deployed. The daily security check probes every
  function in `schema.sql` and every Edge Function as a stranger, and would
  fail on missing ones.
- **The two secrets** (`REMINDERS_SECRET`, `VAPID_PRIVATE_JWK`): generate
  them with OpenSSL and put them straight on the clipboard for the user to
  paste into Supabase. Never print them, write them to a file in the repo,
  or put them in a message. Only the VAPID public key goes in `config.js`.
- **Going live** is setting `vapidPublicKey`, and the privacy and features
  pages have to cover notifications in the same change (a test holds it).
- **The browser pane** can't run service workers or show notifications.
  Check the panel there with the browser's push objects faked in the page,
  and the real thing on a phone. Click with real clicks, not `.click()`
  from a script: a real click lets promises settle between listeners,
  which is how the bell's closing bug (README, Reminders) showed, and a
  scripted `.click()` runs every listener first.

## Commissioners

Asked for 2026-10-25 (README, Commissioners). The admin makes members
commissioners from the Commissioner page; never write a player's name into
the repo to do it (the user's first pick was named in chat, and that's
where it stays). All four stages are live: 1 (the role and the page), 2
(seasons on the site), 3 (more songs and downvotes) and 4, the extras
(README, Commissioner extras). A stage that changes a function a live test
covers reruns that live test too: stage 3 changed `my_submission_described`
and its live test sat stale until stage 4. The user's calls, in order, each
its own change with its own migration and rehearsal:

- **Stage 2, seasons:**
  - the season setup in steps (Details, Songs + Votes, Timing, Rounds,
    Players);
  - rounds scheduled ahead;
  - Steady, Accelerated and Speedy timing (early close is automatic);
  - a Manage season page.
  - **Every new season votes on pfml.fun**, so creating the first one is
    when `SITE_VOTING` goes on, with the README's switch-on checklist.
    Never Round 7 or any Season 3 round.
- **Stage 3:** more than one song a round, and downvotes, through
  submitting, ballots, results and the stats.
- **Stage 4, the extras:** allowed services per round, submitter notes (no
  Daily Double on the site), a repeat rule per round (off, warn, block),
  and announcements pushed to everyone. A block checks **this round
  only**, not the league's history (the user's call).
- **Deleting a round** (2026-10-25): the admin only, and only a round
  nobody really played (README, Deleting a round). Keep the "one player at
  most" rule: without it the real Round 7 would qualify between its close
  and its playlists. To delete anything else, the user runs SQL by hand
  after seeing what goes.
- **Playlists stay manual:** `round_playlists.py` with the user's
  go-ahead each time. The user's account tokens stay in `.env`, never in
  Supabase.

## The daily security check

`.github/workflows/security-check.yml` runs `scripts/security_check.py`
every morning; a clean run redeploys, and the privacy page shows when it
last passed (README, Security check). When it fails, read the run's
summary. A new Supabase advisory needs a judgment on whether it touches
PFML, then a line in `scripts/security_reviewed.txt` (id, date, why).
Supabase publishes some advisories only on its own repos, not in GitHub's
global database, and a 30-day review once missed a critical Storage one
that way (2026-10-24), so read those repos too when rechecking by hand. A
full review by hand also updates the card's "Full review" date and its
wording, and every claim on it has to stay true.

## Dark mode: colours go through tokens

Dark mode is a choice, light by default whatever the device says: the Dark
mode switch in the account menu sets `<html data-theme="dark">`, and every
page's `<head>` restores it before painting (README, Dark mode). A new page
needs that head line too (a test checks every page). Any new style uses
the tokens, never a literal light colour: `--magenta-text`
for purple text (`--magenta` is the fill behind white text, too dark to
read as text on a dark page), `--card` rather than `#fff`, `--inverse` and
`--on-inverse` for a surface meant to stay dark, `--on-metal` for text on
gold, silver or bronze. `tests/test_dark_mode.py` recomputes the contrast of
each pair from the CSS and refuses a hard-coded light background. Check a
visual change with the browser's dark scheme too (`resize_window` takes
`colorScheme`), measuring contrast rather than eyeballing it.

## Working agreement

These standards apply to every change. Anything reported as "done and
verified" has to be both.

**Project specifics**
- Test command: `python -m unittest discover -s tests -v` (stdlib only,
  offline, about 3 seconds). The deploy runs it too, and a failure blocks
  the deploy.
- Live tests (network): `PFML_LIVE=1 python -m unittest discover -s tests
  -p test_live_spotify.py -v` whenever the album-art or playlist-stats
  lookup in `publish.py` changes (the playlist one reads undocumented
  Spotify pages, so also when tiles lose their numbers), and
  `-p test_live_emoji_data.py` whenever `scripts/update_emoji_data.py` or
  its pinned version changes (it also checks the committed
  `site/emoji-data.js` is what that version builds), and
  `-p test_live_playlists.py` whenever `scripts/round_playlists.py`'s
  lookups or matching change (read-only; Spotify and YouTube parts need
  their keys in `.env` and skip without them), and `-p test_live_cdn.py`
  whenever the supabase-js version or its integrity hash changes (a wrong
  hash blanks every page), and `-p test_live_round_repeats.py` whenever
  `fp_kind()` or the round-check functions change (read-only; the only
  place that SQL actually runs before members use it), and
  `-p test_live_security_check.py` whenever `scripts/security_check.py`
  changes (needs `GH_TOKEN=$(gh auth token)` too, for GitHub's rate limit),
  and `-p test_live_reminders.py` whenever the reminder functions or
  `send-reminders` change (read-only),
  and `-p test_live_voters_lounge.py` whenever the lounge functions change
  (read-only; the full flow is `supabase/checks/2026-10-28_voters_lounge_rehearsal.sql`),
  and `-p test_live_season_roles.py` whenever the DJ and Spectator functions
  change (read-only; the full flow is `supabase/checks/2026-10-29_season_roles_rehearsal.sql`),
  and `-p test_live_demo_ballots.py` whenever the demo's practice-ballot
  functions change (read-only; the full flow is
  `supabase/checks/2026-10-27_demo_ballots_rehearsal.sql`),
  and `-p test_live_ballot_drafts.py` whenever the draft functions change
  (read-only; the full flow is `supabase/checks/2026-10-27_ballot_drafts_rehearsal.sql`),
  and `-p test_live_voting.py` whenever the voting functions change
  (read-only; the full round is `supabase/checks/2026-10-25_site_voting_rehearsal.sql`,
  which only the user can run, in the SQL Editor).
  Note: `python -m unittest tests.test_x` does not work here, since
  `tests/` isn't a package on the path; use `discover`.
- Main branch: `main`. Work on a branch; don't merge or push to `main`
  without the user's go-ahead. Pushing `main` deploys the site.
- Never modify without explicit instruction:
  - `data/` (the real exports) and `site/data/` (built output)
  - `.env`
  - `data/season3/daily_doubles.json`, except through the Daily Double
    review above
  - `site/seasonN.html`, which are generated: edit `season.template.html`
    and run `scripts/build.py`
  - `site/emoji-data.js`, which is generated: change
    `scripts/update_emoji_data.py` and run it
  - `site/icon-*.png` and every page's `<link rel="icon">` (the site's
    icon), which `scripts/make_icons.py` draws and writes: change the
    script, run it, then `scripts/build.py` for the season pages
  - `supabase/schema.sql`, which is applied to the live database by hand.
    A change to a table the live project already has needs a migration in
    `supabase/migrations/` as well, which the user runs in the SQL Editor:
    Claude can't, and has no access to the live database or its keys. Code
    that depends on it waits to ship until the user confirms it's run.
    Before reading or writing the reaction column, note that the original 6
    reactions are stored by name, not as emoji, on purpose (README,
    Reactions).
    From 2026-10-30 Supabase gives a new table no API grants by default,
    so a migration that creates a table must `grant` what the site needs
    explicitly, and nothing for tables only reached through security
    definer functions (README, Members only).
- Deploys by: push to `main` -> GitHub Actions -> GitHub Pages (pages
  only). Data goes separately, by `python scripts/publish.py` to Supabase.
  The search Edge Function (`supabase/functions/search-tracks/`) goes
  separately too: the user redeploys it from the Supabase dashboard
  (README, Searching), so a change to it ships only then. Say so.
- Docs to keep current: CLAUDE.md, README.md, CHANGELOG.md, and
  `site/features.html` for anything a member can see.

**Before changing anything:** run the full suite and note the result;
report any failure that was already there, and don't work around it.
Read the code and the docs that describe it. Follow their conventions.

**Establish the cause with evidence.** Reproduce a bug, or capture the
real response, before fixing it. When behaviour depends on an outside
system (Spotify, Supabase, GitHub Pages path rules), check the real thing
and write down what was measured and when.

**Tests**
- Every behaviour change ships with a test that fails without it. A bug
  fix gets a regression test.
- Test behaviour, not wording: the features page's copy is meant to
  change, so its tests cover what it loads, the mode switch wiring, and
  the links.
- Tests never touch real data. `tests/support.py` builds made-up seasons
  in a temp directory and points `build.py`/`publish.py` there.
- Where a fake can't prove it, add a separate, labelled live test that
  skips unless asked for (see `test_live_spotify.py`).
- **Prove each new test can fail:** break the code it protects in a
  scratch clone, never the working tree, and confirm the test fails. When
  doing this in a loop, set `PYTHONDONTWRITEBYTECODE=1` and clear
  `__pycache__` between breaks. Gotcha, it happened: two breaks that left
  `build.py` the same size, written in the same second, made Python reuse
  the previous break's cached bytecode, and a test that works looked like
  it let a break through.
- Not covered by the suite: the browser JavaScript (`app.js`, `rounds.js`,
  `auth.js`, `account.js`, the features page's switch at runtime). There's no Node here
  to run it. Check those in a real browser, as below.

**Verify against reality before calling it done:** rerun the full suite
at the end. Exercise anything members see in a real browser at phone
(375px) and desktop widths, and measure layout claims (for example
`scrollWidth` against `innerWidth`) rather than eyeballing a screenshot.
After a deploy, fetch the live files and compare them with the commit.
The live pages have `?v=<first 12 of the sha>` on their own scripts and
stylesheet (Deploy, below), so strip that before comparing an `.html`,
and check the stamp is this commit's. `gh run list` can return the previous run for a moment after a push, so
match the run to the commit's sha before watching it.

**Testing on a phone viewport:** Chrome's scroll anchoring quietly hides
layout shifts that Safari (no scroll anchoring) shows. Measure with
`document.documentElement.style.overflowAnchor = "none"` too. The page has
`scroll-behavior: smooth`, so a corrective `scrollBy`/`scrollTo` needs
`behavior: "instant"`, or it slides instead of holding still. On touch
screens `:hover` sticks to whatever a finger touched, so hover styling on
tappable lists belongs inside `@media (hover: hover)`. Resize the viewport
*after* the tab has a page loaded; resizing a blank tab silently fails.
If the app window is minimized, the page reports `innerWidth` 0 and
screenshots time out; load the page in an `<iframe>` of fixed width (375
or 1280px) and measure inside that instead.

**Measure what's on screen, not what the code set.** Setting the `hidden`
attribute does nothing to an element whose CSS gives it a `display`
value; the author rule wins. The emoji search shipped like that, and the
check counted `el.hidden` rather than `getComputedStyle(el).display` or
a non-zero `getBoundingClientRect()`, so it passed. Likewise, time
rendering with a forced layout (`getBoundingClientRect()` after the
change), not just the script: 9ms of script was about a second of layout.

**Break-checks need a passing baseline:** run the suite in the scratch copy
before breaking anything. If a test already fails there, every break looks
"caught". That happened once, when the CSS test helper tripped on a
comment, and the results were only trusted after a rerun.

**Editing files from a script:** backslashes and quotes get mangled when
file content passes through a shell heredoc into a Python string. It
happened four times in one session: CSS `\25BE` became a control
character, a regex `\b` became a backspace, a `\(` warned, and escaped
quotes split a call's arguments. Use the Edit tool, or a script file with
raw strings, for anything containing backslashes or quotes. The suite's
control-character test catches the CSS case.

**Code:** match the surrounding code. Comments say why. Keep changes to
what was asked; flag anything else. Remove code your change makes dead.
Anything that writes, pushes or deletes gets the plainest control flow.

**Safety:** secrets never appear in code, commits, logs or messages (the
suite checks tracked files for Supabase secret keys; still look at the
diff before committing). Treat external input as untrusted. Before
anything hard to undo (force-push, deleting branches or files, rewriting
history), show what would be lost and the evidence that it's safe; keep a
backup bundle outside the repo. Stop background servers and delete
scratch copies when done.

**Docs:** record decisions, measurements and gotchas in the same change,
and fix any doc the change makes wrong.

**Commits and shipping:** messages say why, and how it was verified. No
merge, push to `main`, deploy or publish without the user's go-ahead; when
waiting on it, make that the bolded last line of the reply. One standing
exception (2026-09-23): "update the data" carries its own go-ahead to
publish, as described in "Update the data" above.

**Reporting back:** decisions needed come first. Then what changed, how it
was verified, and anything assumed, skipped or unverified. State failures
plainly, and correct earlier mistakes plainly.

### Checking page code in a browser

The pages need a signed-in member to show anything, and they read data
from Supabase, not from local files. To check page code without signing
in, serve a scratch copy of `site/` with `auth.js` swapped for a stub that
defines `window.PFML` (`ready`, `loadJSON` reading local `data/`, and an
in-memory `api`); that's how Results by round and the comment layer were
tested. To test `auth.js` itself, load it with a fake
`window.supabase.createClient`, which is how the sign-in return path was
checked. Keep stubs and copied data out of the repo, and delete them after.
A page stub must also remove the `gated` class from `<body>`, or the page
stays blank. It must set `PFML.member` (`{ competitorId, name, role }`)
before `ready` resolves, and the page must still load the real
`account.js` after it: `app.js` and `rounds.js` use `PFML.member`,
`PFML.avatar`, `PFML.reactionGlyph` and `PFML.when` without checking for
them, because on the real site `auth.js` and `account.js` always load
first (a test pins that order). For the header and profiles the stub's
`api` also needs `people`, `inbox`, `inboxSeenAt`, `markInboxSeen` and
`reactionsOn`, and the scratch copy needs `profiles.json` and
`lookup.json`: generate them there with `build.build_profiles` /
`build.build_lookup` from the season JSON, rather than running `build.py`,
which would rewrite `site/data/`. The Home page and the Submit page also
call `siteRounds`; the Submit page needs the rest of the site-round calls
in `auth.js` too, and a stub for them should follow the database's rules
(closed rounds refuse writes, nobody reads tracks before the close, one
track per member), or it proves nothing. The browser caches `app.js` and friends
between edits, so a fix can look like it did nothing: refetch with
`fetch(url, {cache: "reload"})`, or check `performance` entries, before
trusting a before/after comparison.
Every link on the site is a clean address (`/career`, `/round?s=...`),
never `.html` (README, Clean addresses); GitHub Pages resolves them, and a
test fails if a page builds a `.html` link. Python's plain `http.server`
doesn't resolve them, so serve local copies with `python scripts/serve.py`
(or its `CleanUrlHandler` for a scratch folder), or every link 404s.

## Working style for this project

- Lead with the answer or the change, then explain. Skip preamble.
- If something in the data or a request doesn't add up, say so plainly
  before proceeding rather than quietly working around it.
- Verify claims about the data against the actual CSVs or generated JSON
  instead of assuming. This project has already had two cases where an
  assumption would've been wrong: Season 3's "1 round posted" turned out
  to be 0 rounds in the actual export, and competitor ID stability across
  seasons was checked against the real data (not assumed) before the
  Career page was built on top of it.
- No filler, no "let me know if you have any other questions" closers.

## Deploy

GitHub Pages via Actions (`.github/workflows/deploy.yml`), not
branch-deploy. The workflow deploys only the page files; it no longer
builds data (there is none in the repo), and it refuses to deploy if any
JSON, CSV or `.env*` file is in `site/`, or a `data/` folder in the repo.
It runs the test suite first (on a pinned Python), and a failing test
stops the deploy. Only the deploy job has Pages and token permissions;
the job that runs the tests is read-only. Actions are pinned to commit
SHAs with the release tag in a comment: to update one, look up the new
tag's commit (`gh api repos/<owner>/<action>/commits/<tag> --jq .sha`),
read its release notes, and change both. `upload-pages-artifact` leaves
out dotfiles, so `site/.nojekyll` isn't uploaded; that's fine, since an
Actions deploy never runs Jekyll. A new push waits for a deploy in
progress rather than cancelling it. `tests/test_site.py` (DeployWorkflow)
pins all of this.

**Browsers keep every file for 10 minutes** (Pages sends
`Cache-Control: max-age=600`, measured 2026-10-19), so right after a
deploy a new page can run with an old cached `app.js` or `auth.js`. It
did: the Submit page sat at "Loading the round." with an empty top bar.
The build job now runs `scripts/stamp_assets.py` after the tests, giving
every page's own scripts and stylesheet `?v=<commit>` in its checkout (the
repo's files stay unstamped; Pages ignores the query, measured). A page
then always asks for the files it was built with. A new script or
stylesheet needs nothing extra, as long as it's linked by a plain local
name like `src="x.js"`.

Timeouts are lopsided: 30 minutes on each job, 5 on the test step and 10
on the Pages call. The job numbers are slack, not protection, and the real
hang protection is per-step, where the clock starts when the step runs
rather than when it is queued. These jobs finish in about 12 seconds when
a runner is free, so don't tighten the job numbers to "match" the runtime.

**A queued job is cancelled after about 15 minutes no matter what
`timeout-minutes` says, and nothing in this repo can change that.**
Measured 2026-10-05, during a GitHub Actions outage: the build job was
cancelled at 15m02s with zero steps executed on `timeout-minutes: 10`,
and the deploy job was cancelled at 15m02s with zero steps executed on
`timeout-minutes: 30`. Identical to the second. So that cancellation is
GitHub's own limit on waiting for a runner, not the job clock. The first
of those two runs was misdiagnosed as a `timeout-minutes` problem and the
numbers were raised to fix it; the second run disproved that. Raising them
again will not help. During a runner shortage the only option is to re-run
once Actions is healthy (`gh run rerun <id> --failed` re-runs just the
failed job and reuses the build's artifact).

The custom domain (`pfml.fun`) is set in the repo's
Settings → Pages, not by the `site/CNAME` file, that file only matters if
this ever switches to branch-deploy. DNS is already configured at
Namecheap; nothing to redo there.
