# Changelog

## 2026-09-21 (follow-up 8)

- **A test suite, and a working agreement.** `tests/` (stdlib `unittest`,
  offline, made-up data) covers the build's scoring rules, the album-art
  lookup and the site's static contracts: 32 tests, plus one live Spotify
  test that runs only on request. Each test was shown to fail by breaking
  the code it protects in a scratch clone: 40 breaks, all caught, on two
  clean runs. The deploy now runs the suite first. CLAUDE.md's "no tests"
  section is replaced by the working agreement: test command, branch rule,
  files never to touch, verification and reporting standards, and the
  gotchas found while building this.

## 2026-09-21 (follow-up 7)

- **Career is back in the top bar**, after the seasons. Its Home page card
  stays.
- **Round links survive sign-in.** A signed-out member opening a round
  link used to land on "Round not found" after Google sign-in, because the
  return trip dropped `?s=...&r=...`. The rest of the link is now kept in
  the tab while they sign in and restored before the page loads. The
  features and privacy pages say so.
- **League data purged from git history.** Every commit was rewritten
  without `data/` and `site/data/` and force-pushed (`main` and
  `members-only`); the code at each point is unchanged. Commit ids before
  today changed.
- **Standings ties stay as shared places** (T1, T1, 3), decided; no
  tie-break by round wins.

## 2026-09-21 (follow-up 6)

- **"What this site can do"** at pfml.fun/features: a plain-language tour
  of every feature members can see or use, split into Season pages, Round
  pages and Home & Career (`?mode=` in the URL opens straight to one),
  with a key to the badges and colours. Public and standalone: no sign-in,
  no data, nothing loaded but the page and its fonts. Linked from every
  page's footer. CLAUDE.md now requires it to be updated alongside any
  visible feature change.
- **Privacy page correction**: it said a comments page remembered the last
  round you viewed. That page is gone and nothing like that is stored; it
  now says what the browser does keep (the sign-in session, and an invite
  code only until the account is linked).

## 2026-09-21 (follow-up 5)

- **Every round gets its own full-width page** (`round.html`), laid out
  like Music League's round view: a card per track with album art, its
  place, points and voter count, the submitter and their note, and every
  vote with its comment in full, where members vote, react and reply as
  before. The Round results pill on season pages now lists a card per
  round linking there, instead of expanding rounds and tracks inside the
  pill three levels deep. Rounds link to the previous and next round.
- **Album art** from Spotify's public oEmbed endpoint, looked up by
  `publish.py` for new tracks only and cached in `data/track_art.json`
  (git-ignored); the build stays offline. The privacy page now lists
  Spotify's image servers.

## 2026-09-21 (follow-up 4)

- **Ties are handled everywhere a winner is named.** Standings share
  places on equal points (T1, T1, 3); the Home page names every co-leader
  ("Tied for the lead: A & B"); the player focus card
  and comparison show shared places; and every superlative card lists who
  it's tied with, from the whole tied group rather than whichever entry
  `max()` hit first. That changes what the site says in 13 real places,
  among them Season 3's top track and boldest voter, Season 1's closest
  round and 4-way coldest shoulder, and an 8-way tie for most likely to
  comment in Season 3.
- **Biggest blowout is hidden until it means something**: only once a
  round has been won by a wider margin than the closest round. Season 3
  showed its winner "won by 0 points".

## 2026-09-21 (follow-up 3)

- **Round results replace the Comments page.** Under the leaderboard on
  every season page, a collapsed "Round results" pill opens to the season's
  rounds, and each round opens to every track with every vote (voter and
  points) and every comment, where members can vote, react and reply. It
  replaces both the standalone Comments page and the old Rounds section
  further down the page. The build now writes each song's scoring votes
  (`votes`: `[voter id, points]`) so the page can show every vote, not only
  the ones with a comment.
- **The top bar is Home and the seasons only.** Comments is gone (its
  content moved into Round results) and Career moved to a card on the Home
  page.

## Members-only site and comments page (branch: members-only)

- **The site is members-only.** Every page is behind Google sign-in, and a
  Google account only gets in once it's linked to a Music League player
  through a one-time invite link (`scripts/invites.py`). The gate is real:
  league data is no longer on the public site or in the public repo. It's
  published by `scripts/publish.py` to a private Supabase bucket that only
  linked members can read. `data/` and `site/data/` are git-ignored, and
  the deploy fails if either ever reappears. Commits from before this
  change still contain the old data.
- **Comments page** (`comments.html`): every vote comment, one round at a
  time, with member up/down votes, reactions and flat replies. Keyed by the
  existing comment id (round + track + voter), so everything stays attached
  across new exports. The build now writes that id onto each comment.
- Supabase schema, access rules and buckets in `supabase/schema.sql`.
  The build is still stdlib-only, and so are the new scripts.

## 2026-09-21 (follow-up 2)

- **Builds are now deterministic.** Each round's voters were iterated as a
  Python set, whose order changes with the per-process hash seed, so every
  build wrote the taste list in a different order, and where several pairs
  tied (Season 1's Coldest shoulder is a 4-way tie at 0.46) which one
  showed depended on that order. Voters are now iterated sorted. Checked
  by building repeatedly under different forced hash seeds: every output
  file is byte-identical. The tied highlights resolve to the same pairs
  the live site shows today, so nothing visible changes.
- **Builds now match across Windows and Linux.** Git stores the CSVs with
  LF line endings, but a Windows checkout converts Seasons 1 and 2 to CRLF,
  and the build kept line breaks inside quoted comments as-is, so a local
  Windows build wrote multi-line comments with CRLF while the Linux runner
  that deploys the site wrote LF. The build now normalises line breaks
  inside CSV cells to LF when it reads them. A Windows build now matches the
  live site file for file. This corrects the 2026-09-17 JSON refresh
  (`4ddbd18`), which blamed the CRLF on the Music League export: it came
  from the Windows checkout. The live site was never affected, since the
  deploy always rebuilds on Linux.

## 2026-09-21 (follow-up)

- **Daily Double (Season 3).** A submitter can ask, once per season, in
  their note on a submission, to have that track's points doubled toward
  their season total. Requests are judged by reading the notes, not
  keyword-matched, and recorded in `data/season3/daily_doubles.json`; the
  build applies only accepted decisions. The standings row shows the bonus
  with its track and round, the player focus tile repeats it, and the
  doubled track carries a badge in the round's results. It feeds the
  season total, the charts and the Career page; the round's own placings,
  wins, podiums and the per-submission average stay vote-only. The build
  refuses a malformed file, a request that matches no submission, or two
  requests on one track, and warns about rounds nobody has reviewed yet.
  Round 1 (New Heat) reviewed: 4 notes, no requests.

## 2026-09-21

- **Season 3, round 1 loaded** (New Heat: 19 tracks, 317 vote rows, 246
  comments, 4 submitter notes). Season 3 is now the live season on the
  home page and counts as a played season on the Career page, which gains
  an S3 column and three new players. Checked against the raw export before loading rather than
  assumed: every returning player kept the same competitor id and name
  (16 of 21), so the career join is safe; there are no self-votes with
  points, no negative votes, and every zero-point row carries a comment.
  Two players are on the roster but haven't
  submitted, so they have no standings or career entry yet. The round
  ended in a two-way tie at the top, and
  both are credited with the win.
- **The point budget is per season, not always 16.** Every Season 3 voter
  spends exactly 19, against 16 in Seasons 1 and 2. The Voting style copy
  hard-coded 16, which would have been wrong on the Season 3 page, so the
  build now reads the budget from the votes (`pointBudget`, the most
  common per-voter round total) and the page shows each season's real
  number. README and the build docstring updated to match.
- **The trend chart is hidden until a season has two rounds.** With one
  round every line is a single dot, so the chart was a column of dots on
  its left edge over an empty plot: correct, but it looked broken. It and
  its jump-nav link come back at round two.

## 2026-09-17 (follow-up 5)

- **Comment stats, season and career.** A new Comments section on every
  season page (after Voting style, in the jump nav) and an all-time one on
  the Career page. Per player: comments left, comment rate, mean and median
  words, zero-point comments, exclamation / question / ALL-CAPS / emoji
  rates, vocabulary richness, and the word they reach for more than anyone
  else. Plus a directed comment matrix — who says something to whom, out of
  the chances they had — sharing the taste matrix's denominator and its
  5-chance minimum, which is where "silent treatment" comes from. The
  season section follows the Standings player selection exactly like Top
  Tracks and Voting style; a season with no rounds hides it, so Season 3
  still renders clean.
- **Vocabulary richness is a chunked (mean segmental) type-token ratio,
  not a raw unique/total.** The raw ratio falls as a corpus grows, so
  ranking on it mostly ranks who wrote least: on this data it put the
  player with 813 words first and the player with 13,549 last, almost
  perfectly inverted. It's now measured on 500-word chunks and averaged so
  everyone is compared over the same amount of text. The raw number is
  still in the JSON for reference; nothing ranks on it.
- **Submitter notes are counted separately from vote comments.** A note on
  your own submission is a different act from reacting to someone else's,
  and much rarer (60 of 316 submissions in Season 1 against 2,194 vote
  comments), so mixing them would have quietly distorted every rate.
- **`scripts/enrich_comments.py`** — a standalone local tool that labels
  comments *witty / funny / rude / appreciative / storytelling /
  analytical* via the Claude API. Nothing automatic runs it: not
  `build.py`, not the Action, which has no API key and must never need
  one. It writes `data/comment_sentiment.json`; `build.py` merges that
  file if it exists and builds exactly as before if it doesn't. Labels are
  never inferred at build time, and an unrecognised label is dropped
  rather than rendered. `--estimate` prints a measured cost before
  anything is spent; re-runs only pay for comments that aren't already
  labelled. Still stdlib-only for the build and dependency-free for the
  site — the SDK is a local-only install for that one script.

## 2026-09-17 (follow-up 4)

- **Standing over time is now the default Performance over time metric**,
  and leftmost of the three (Performance vs field, then Cumulative
  points).
- **Chart lines are now clickable**, same effect as clicking a player's
  legend chip: toggles them out of the plotted set. Each line has a wide
  invisible hit area so it's easy to click without landing exactly on
  the 2.5px stroke.
- **Hovering a line now names the player and shows the value at that
  point**, not just a fixed tooltip on the whole line: a hit point at
  every round surfaces that round's own reading (e.g. "Player — Round name: #2"), while hovering elsewhere on the line still shows the
  player and their final value.

## 2026-09-17 (follow-up 3)

- **Points over time is now Performance over time**, and has a third
  metric: Standing over time, leaderboard position (#1 to last) after
  each round's points are counted. Ties share a place, with the next
  distinct total skipping accordingly (competition ranking: 1, 1, 3, not
  a manufactured tiebreak). The chart draws #1 at the top since it's the
  best place to be, and the axis always spans the full field regardless
  of which players are toggled on, so a filtered view of the middle of
  the pack isn't stretched to look like the top.

## 2026-09-17 (follow-up 2)

- **Points over time has a new default metric: Performance vs field.**
  Raw cumulative points only ever climb, so every player's line looked
  like a similar upward slope, it couldn't show anyone actually fading.
  The new default is cumulative points captured so far as a percentage of
  the cumulative *winning* score, i.e. what a player would have if they'd
  won every round to date. 100% means never off the pace; a line that
  rises then falls shows someone who started strong and lost ground. A
  toggle switches to the old raw Cumulative points view if you want it.

## 2026-09-17 (follow-up)

- **Removed Top Tracks sorting.** Back to a plain top-20-by-points list.
- **Points-over-time chart now defaults to Select All**, and follows the
  Standings player selection when one is active (clear the Standings
  selection and it goes back to everyone). You can still adjust the
  chart's own legend afterward; it only re-syncs when the Standings
  selection itself changes.
- **Removed "Most seasons played" from Career highlights** — with most of
  the roster having played every season, it wasn't distinguishing anyone.
- **Added Career Score**, a new column on the Career page and the new
  default sort: total points + 10 per round won + 5 per podium finish
  (podiums include the win, so a win is worth +15 total). The 10/5
  weighting is grounded in the real per-round data, not picked at random,
  see the README's Career Score section for the numbers behind it.
- **Career all-time standings table is now sortable** by clicking any
  column header, including each season's point column and the new Career
  Score column. Click again to flip direction.

## 2026-09-17

- **Career page** (`career.html`, linked from the top nav on every page):
  all-time standings across every played season, joined by competitor id.
  Highlights for most career points, most wins, most podiums, most seasons
  played, and best single season.
- **Jump-to-section nav** on season pages: a second row in the sticky top
  bar links to Standings, Numbers, Trend, Tracks, Rounds, Taste, Voting,
  and Artists. Hidden sections (Numbers while filtered, Trend on a season
  with no rounds) drop out of it automatically.
- **"The season in numbers" now hides while a player filter is active.**
  It's a season-wide summary and was sitting awkwardly between two
  player-specific panels (Player Focus above it, filtered Top Tracks
  below it) once you'd selected someone.
- **Sort controls on Top Tracks**: Top scoring (default), Lowest scoring,
  A–Z, Most recent. The two ranked sorts stay capped at 20; A–Z and Most
  recent show everything, since capping an alphabetical or chronological
  list at an arbitrary 20 doesn't mean anything.
- **Points-over-time chart** on season pages: cumulative points after each
  round, one line per player. Toggle players from the chip legend below
  the chart, or use Select all / Clear. Starts on the top 3 finishers so
  it isn't 16 overlapping lines on first load.
