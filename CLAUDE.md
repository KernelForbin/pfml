# CLAUDE.md

Context for Claude Code sessions on this repo. This file loads automatically
at the start of every session. It isn't where architecture or feature docs
live, that's `README.md`, this is for things a fresh session would otherwise
have to be told by hand.

## Read first

- `README.md` — architecture, how `build.py` works, season pages, the
  Career Score formula, the taste index math, and the scoring model quirks
  that aren't obvious from the CSVs (a fixed point budget per voter per
  round, 16 in Seasons 1-2 and 19 in Season 3, a 0-point vote row is a comment not a vote, self-voting is
  blocked).
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
recreated to fix it.

That stray repo is gone as of 2026-09-17: the `.git` in the home folder was
deleted, after its history was bundled and the two trees that survived only
inside it were extracted back to `Downloads`. This clone now lives in its
own folder, `code/pfml`, well outside `Downloads`. So the hazard is fixed,
not just documented, but nothing stops it recurring, so keep the habits:

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

## Keep the features page true

`site/features.html` (pfml.fun/features) is a plain-language tour of what
members can see and do, linked from the footer of every members-only page. **Any change that
adds, removes or visibly alters a feature updates that page in the same
change.** Every sentence on it has to be true of the code as it ships.

Scope rule, so it never turns into a changelog: it lists only features
that are current, working and noticeable to an ordinary member, things
they see on screen or do themselves. No bug fixes, refactors, performance
work, data pipeline or backend changes, admin-only powers, or anything not
shipped yet. The test: would a regular member notice if this disappeared?
If not, it stays off.

It's standalone on purpose: public, no sign-in, no `style.css`, no
`app.js`, no data, nothing loaded but itself and its fonts. Its colour
tokens are copied from `style.css`, so a palette change there updates them
too.

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
  Spotify pages, so also when tiles lose their numbers), and `-p test_live_emoji_data.py` whenever
  `scripts/update_emoji_data.py` or its pinned version changes (it also
  checks the committed `site/emoji-data.js` is what that version builds).
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
  - `supabase/schema.sql`, which is applied to the live database by hand.
    A change to a table the live project already has needs a migration in
    `supabase/migrations/` as well, which the user runs in the SQL Editor:
    Claude can't, and has no access to the live database or its keys. Code
    that depends on it waits to ship until the user confirms it's run.
    Before reading or writing the reaction column, note that the original 6
    reactions are stored by name, not as emoji, on purpose (README,
    Reactions).
- Deploys by: push to `main` -> GitHub Actions -> GitHub Pages (pages
  only). Data goes separately, by `python scripts/publish.py` to Supabase.
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
`gh run list` can return the previous run for a moment after a push, so
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
waiting on it, make that the bolded last line of the reply.

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
stays blank. For the header (`account.js`) and profiles the stub's `api`
also needs `people`, `inbox`, `inboxSeenAt`, `markInboxSeen` and
`reactionsOn`, and the scratch copy needs `profiles.json` and
`lookup.json`: generate them there with `build.build_profiles` /
`build.build_lookup` from the season JSON, rather than running `build.py`,
which would rewrite `site/data/`. The browser caches `app.js` and friends between edits, so a
fix can look like it did nothing: refetch with `fetch(url, {cache:
"reload"})`, or check `performance` entries, before trusting a
before/after comparison.
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
pins all of this. The custom domain (`pfml.fun`) is set in the repo's
Settings → Pages, not by the `site/CNAME` file, that file only matters if
this ever switches to branch-deploy. DNS is already configured at
Namecheap; nothing to redo there.
