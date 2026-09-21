# Changelog

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
  an S3 column and three new players (David Simon, Easton Fong, Gary
  Nuzzi). Checked against the raw export before loading rather than
  assumed: every returning player kept the same competitor id and name
  (16 of 21), so the career join is safe; there are no self-votes with
  points, no negative votes, and every zero-point row carries a comment.
  Clavenna Vision and Scott Menke are on the roster but haven't
  submitted, so they have no standings or career entry yet. The round
  ended in a tie at the top (Dianna Hank and josh storm, 29 each), and
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
  every round surfaces that round's own reading (e.g. "Rick D — Pre-Show
  Party Bus: #2"), while hovering elsewhere on the line still shows the
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
