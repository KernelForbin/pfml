# Changelog

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
