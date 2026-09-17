# Changelog

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
