# CLAUDE.md

Context for Claude Code sessions on this repo. This file loads automatically
at the start of every session. It isn't where architecture or feature docs
live, that's `README.md`, this is for things a fresh session would otherwise
have to be told by hand.

## Read first

- `README.md` — architecture, how `build.py` works, season pages, the
  Career Score formula, the taste index math, and the scoring model quirks
  that aren't obvious from the CSVs (fixed 16-point budget per voter per
  round, a 0-point vote row is a comment not a vote, self-voting is
  blocked).
- `CHANGELOG.md` — what's shipped, in order, and why.

## The site is members-only: data never goes in this repo

pfml.fun is behind Google sign-in, and the league data (the CSVs in
`data/`, the JSON in `site/data/`) is served from a private Supabase bucket
that only linked members can read. The repo is public, so:

- `data/` and `site/data/` are git-ignored. Never force-add them, and
  never commit a CSV, a season/career JSON, `daily_doubles.json` or `.env`.
  The deploy workflow fails if a JSON file or `data/` shows up in `site/`.
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

## No automated tests ship in this repo

Verification during development was done with disposable Node.js harnesses
(a mock DOM, no real browser) that were never committed, since they were
scratch tools, not deliverables. There's no test suite here right now. For
a nontrivial change to `app.js` or `style.css`, the fastest real check is:

```bash
python scripts/build.py
cd site && python -m http.server 8000
```

then actually open a season page and the career page in a browser and
click around (player selection on Standings, the trend chart legend, the
Career Score sort), rather than trusting a read-through of the diff. The
pages need a signed-in member to show anything, and they read data from
Supabase, not from local files. To check page code without signing in,
serve a scratch copy of `site/` with `auth.js` swapped for a stub that
defines `window.PFML` (`ready`, `loadJSON` reading local `data/`, and an
in-memory `api`); that's how Round results and the comment layer were tested. Keep such stubs
out of the repo.

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
JSON or `data/` folder is present. The custom domain (`pfml.fun`) is set in the repo's
Settings → Pages, not by the `site/CNAME` file, that file only matters if
this ever switches to branch-deploy. DNS is already configured at
Namecheap; nothing to redo there.
