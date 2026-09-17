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

## Before you push, check this

Earlier in this project, `git init` accidentally ran in a parent folder
(`Downloads`) instead of inside the actual `pfml` project folder, so a push
briefly carried two unrelated personal projects into the public PFML repo
on GitHub. The repo was deleted and recreated to fix it. Before any push:

- `git remote -v` — confirm origin is `https://github.com/KernelForbin/pfml.git`
- `git status` — confirm the changed files are only inside this project,
  nothing from a parent directory
- Run git commands from inside the `pfml` folder itself, never a level
  above it

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
Career Score sort), rather than trusting a read-through of the diff.

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
branch-deploy. The custom domain (`pfml.fun`) is set in the repo's
Settings → Pages, not by the `site/CNAME` file, that file only matters if
this ever switches to branch-deploy. DNS is already configured at
Namecheap; nothing to redo there.
