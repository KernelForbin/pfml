# Changelog

## 2026-09-22

- **New Career Score**, chosen by the league after comparing options on
  the real data: 20 x points per round played, plus 3/2/1 for each
  1st/2nd/3rd in a round, plus 6/4/2 for a finished season's podium;
  scored after 10 rounds played. Replaces total points + 10 per round win
  + 5 per podium, which punished missed seasons. A season's podium counts
  once a newer season exists (Seasons 1 and 2 now). Top of the table:
  Rick D 403, Kris Brinker 394, Justin Mendelsohn 376, josh storm 375.
- **All-time standings columns show the score's parts**: Score (now second),
  Avg season, Round finishes (with 1st/2nd/3rd counts), Season podiums
  (with which seasons), Rounds. The per-season points and total moved off
  this table (profiles show them). Players under 10 rounds are listed last
  with "needs 10". The note, profile rank (among scored players) and the
  "Highest career score" highlight follow the new formula.

## 2026-09-23 (follow-up 5)

- **Season page tables scroll sideways on phones too.** Voting style and
  the comment table keep every column (they used to drop one and four),
  names pinned on the left, with the "swipe sideways" line. The comment
  tables' number columns are now at least 72px, because the COMMENTS
  heading (71px) ran into the next column at 56px, on All-Time as well.
  The season comment table also gets the standard space under its awards.

## 2026-09-23 (follow-up 4)

- **All-Time tables on phones.** All-time standings and the comment table
  keep every column and scroll sideways inside their box, with names
  pinned on the left and a "swipe sideways" line on phones. Measured at
  390px: 600px and 700px wide in a 333px box, nothing cut off.
- **Fixed: Season 3 was hidden from All-time standings on phones**, and
  "Won" from a profile's Season by season. A phone rule meant for the
  season Voting table hid the 4th column of every such table; it's now
  scoped to that one table, as is the comment table's column trimming.
- **The all-time comment table sorts by any column**, like the standings
  (starts by comments, most first).
- **Standard spacing** between the comment awards and that table.

## 2026-09-23 (follow-up 3)

- **Names link to profiles almost everywhere**, looking exactly as before:
  season highlights and comment awards (including "Tied with" lines), top
  tracks, the taste table, the voting and comment tables, signature words,
  quotes, the focus panel, and the All-Time highlights, awards and tables.
  Standings rows and the collapsed Standings bar stay as they are (they're
  tap targets already); tapping a row puts the name, as a link, at the top
  of the focus panel.

## 2026-09-23 (follow-up 2)

- **Top bar: Home | Season ▾ | All-Time.** One season button replaces a tab
  per season: it names the season you're on (or the one in progress) and
  lists every season newest first. "Career" is now **All-Time**; its page
  is titled All-Time League Stats, and Career highlights are **League
  Highlights**.
- **Tiles two per row on phones** for a profile's Comments, and the
  All-Time page's League Highlights and comment awards (`.hl-pair`). On
  desktop those grids are four across, so they come out in even rows.
- **Most all-talk dropped** from the All-Time comment awards, leaving 8
  (season pages keep it).
- **Replies redone.** The underlined "Reply" text is a pill with a speech
  bubble and the reply count. Replies are chat bubbles with avatars; the
  composer is a rounded box that grows as you type, with a round send
  button, disabled until there's text; Ctrl/Cmd+Enter sends. 16px text so
  iOS doesn't zoom.
- **Names link to profiles** on round pages (voters, submitters, the
  winner line, reply authors), looking exactly as before.

## 2026-09-23 (follow-up)

- **Profile tiles fit phones.** The six Career tiles sit three rows of two
  on a phone (smaller boxes, measured 163px wide at 390px, nothing
  overflowing) and stay two rows of three on desktop. The new sixth tile
  is **Top-3 rate**: the share of their tracks that finished in a round's
  top three, so consistency shows, not just wins. Rounds won now shows its
  share of their tracks instead of the podium count.

## 2026-09-23

- **Inbox.** A tray icon at the top right of every members-only page
  lists reactions and replies other members leave on your vote comments,
  with a count of what's new since you last opened it. Each item opens the
  round page scrolled to that comment (replies open for a reply). "Seen"
  is stored in Supabase (`members.inbox_seen_at`, set only through
  `mark_inbox_seen()`), so it carries across devices; needs
  `supabase/migrations/2026-09-23_inbox_seen.sql`. Without it the list
  still works, just with no count: the column is never read by sign-in.
- **Account menu.** Your name and Sign out in the top bar are replaced by
  your initials bubble (as on the round pages), opening My profile and
  Sign out. New `site/account.js`, loaded by every members-only page.
- **Profiles** (`profile.html`). Career Score and rank, totals, each
  season's finish, five best tracks, biggest fans and favourites, comment
  stats and longest comment, and reactions received. Career standings
  names link to them; a dropdown switches player.
- **Build: `profiles.json` and `lookup.json`.** Per-player extras for
  profiles, and a round-to-season/track index for the inbox (the season
  files are ~1MB each; these are ~50KB). Both published by `publish.py`
  like the rest.

## 2026-09-22 (follow-up 3)

- **Emoji search didn't filter at all.** It set `hidden` on non-matching
  buttons, but the buttons' own CSS `display: inline-grid` beats the
  `hidden` attribute, so nothing ever disappeared (measured: "pizza" left
  1,907 buttons marked hidden and all 1,908 on screen). On desktop only the
  category headings vanished, which looked like partial filtering; on iOS
  it looked like nothing happened. The earlier check counted the attribute,
  not what was displayed, so it passed wrongly.
- **The picker was slow to open.** Correction to follow-up 2: "about 9ms"
  timed only the script building the HTML. The browser then had to lay out
  all 1,908 buttons, which took about a second on a desktop the first time.
- **Reaction picker rebuilt.** Tapping add now shows only the 6 quick
  reactions and **More**. More opens a search box, 9 category tabs and a
  grid that draws one category, or only the search matches (ranked: whole
  name, then whole words, then word starts, then anywhere; top 150), first
  screenful immediately and the rest a moment later. Measured in desktop
  Chrome: quick row 10ms, More 7ms, a category tab 4ms, a keystroke 1-22ms.
  The 6 quick ones are findable in More under their old names too
  ("laugh" finds 😂) and still store the old name. Only the grid is redrawn
  while typing, so the box keeps focus. On a phone More is a fixed-height
  bottom sheet, lifted above the iOS keyboard via `visualViewport`; the
  search box is 16px so iOS doesn't zoom the page into it; the keyboard
  isn't raised automatically on a touch screen.
- **Voter names on a faint magenta band.** On a round page, each voter's
  name and points sit on a subtle full-width magenta gradient, so it's
  clear where one voter's comment ends and the next begins.

## 2026-09-22 (follow-up 2)

- **"Standings" is now "Season Standings"** on season pages, so it reads
  apart from Career's "All-time standings". The jump-bar link stays
  "Standings", as "Results" is short for "Results by round".
- **Jump to any round from a dropdown** at the top of every round page,
  alongside the previous/next links.
- **Reactions: a flat add-reaction icon, and every emoji.** The trigger was
  the character "+☺", which each device drew with its own emoji font: flat
  on desktop, a full-colour yellow face on phones. It's now a drawn outline
  icon. The picker keeps the 6 one-tap reactions and adds a search box over
  1,908 more emoji (Unicode's full list, from `unicode-emoji-json` 0.9.0,
  vendored as `site/emoji-data.js` by `scripts/update_emoji_data.py`). The
  6 keep their stored names, so reactions from before still count
  together with new ones; everything else is stored as the emoji itself.
  On a phone the picker is a bottom sheet. It first covered its own close
  button (measured at 375px: the add-reaction button sat under the sheet),
  so it now has its own close button and closes on an outside tap or on
  Escape. Opening it renders all 1,908 buttons in about 9ms.
- **Database: `comment_reactions.reaction` was limited to the 6 names.**
  `schema.sql` now bounds its length instead. The live project needs the
  one-off `supabase/migrations/2026-09-22_widen_comment_reactions.sql`,
  run by hand in the SQL Editor. It finds the old constraint by its
  definition rather than a guessed name.

## 2026-09-22 (follow-up)

- **Tapping names in Standings no longer shifts the list on a phone.**
  Measured on the live site at 375px with scroll anchoring off (Safari
  has none): the tapped name jumped 99px on the first tap and 68px when
  the filter chips wrapped, because the "Filtered to" row grows in the bar
  above the list. Chrome's scroll anchoring hid it. Now the tapped row is
  put back where it was, whichever browser it is. On a phone the chips are
  one swipeable line with Clear all first, so the bar grows once (86px to
  124px) and then holds, however many names are picked. Re-measured: 0px
  of movement on every tap.
- **No more purple names while scrolling on a phone.** The row hover
  highlight applied on touch screens, where `:hover` sticks to whatever a
  finger touched, including the start of a scroll. Hover effects on the
  Standings rows, the section bars and the filter chips now apply only on
  devices with a real hover (`@media (hover: hover)`), and the grey tap
  flash is off on them.

## 2026-09-22

- **No "Signing you in" card when you're already signed in.** `auth.js`
  showed that card on every page load while it checked the session and
  membership. With a saved sign-in in the browser, the page now shows its
  own layout at once, with a thin magenta loading bar along the top, until
  the check lets the member in. First visits and invite links still get
  the card, and a failed check (expired, not linked) still ends on it.
  Checked in a browser against the real `auth.js`, with a fake Supabase
  client delayed 1.2s: the old code showed the card to a signed-in
  member, the new code shows the page and the bar; the expired, not-linked
  and invite cases end where they did before.

## 2026-09-21 (follow-up 13)

- **The Home page no longer says the live round is in "Voting".** It
  called the latest round's phase "Voting" because the round had votes.
  Checked against real exports: Music League's export contains only
  finished rounds. `export (3).zip`, taken while Season 2's last round was
  being played, didn't have that round at all, and its other 19 rounds
  matched the final votes exactly. So every exported round has votes, the
  label always said Voting (finished seasons too), and the export can't
  tell which phase an unfinished round is in. The card now says "Round 1:
  New Heat · Complete" and "Round 2 underway". The build no longer writes
  a guessed `phase`. A test pins that. CLAUDE.md and README record the
  measurement.

## 2026-09-21 (follow-up 12)

- **Season pages lead with Standings.** The summary line and the five stat
  cards under the title are gone (members' request). The build stops
  writing the two fields only those cards read (`highlights.uniqueArtists`,
  `highlights.scoringVotes`); they drop out of the data on the next
  publish.
- **Podium places are gold, silver and bronze**, not the acid green: the
  Standings bar's top three, the Standings list's places 1-3 (new), the
  leader's points bar, and a round's 1st/2nd/3rd badges. Ties share the
  colour. Acid stays for the live season and the Daily Double only. Tests
  pin every placement badge to the medal colours, and check the features
  page's copied colour tokens still match `style.css`.

## 2026-09-21 (follow-up 11)

- **The Standings bar shows which players the page is filtered to**, open
  or closed: a "Filtered to" row with a chip per player (tap to drop them)
  and Clear all. Standings now opens with a real toggle button instead of
  a `<details>`, since its bar holds buttons. A bug found and fixed on the
  way: removing a filter re-rendered the row and detached the tapped chip
  before the click reached the bar, so the bar folded open. Reproduced in
  a browser without the fix, then stopped at the chip.

## 2026-09-21 (follow-up 10)

- **Standings folds like Results by round.** Both now open the season page
  as full-width collapsed bars with a Show all button. Collapsed, Standings
  shows the player count and everyone placed 3rd or better with their
  points (shared places as T1; past four names it shows three and "+N
  more"). Open, it's the same clickable list for focusing and comparing
  players. The two bars share one set of styles (`fold-*`, renamed from the
  results-only `rr-*`).

## 2026-09-21 (follow-up 9)

- **"Round results" is now "Results by round", and it's hard to miss.**
  It's the section people use most, so even collapsed it's a full-width
  card with a magenta edge, as large as a section heading: the round count,
  the latest round and who won it (or who tied), the newest three winners'
  album art, and a "Show all" button. It follows the Standings filter
  (count and preview included). Tests pin it directly under Standings and
  check the bar contains everything `rounds.js` fills in.
- **Jump links no longer land under the header.** Every `#section` link
  (the jump bar, and the round page's link back to the results) scrolled
  its section up behind the sticky top bar. On a phone that header is about
  180px tall, and 154px of the 188px results bar was hidden (measured at
  418px wide). The scroll offset now follows the header's real height, and
  a season page re-jumps to the linked section once its data has loaded.
- A new test rejects control characters in site files, after an edit
  briefly turned the arrow's CSS escape into one (caught in the browser
  before it shipped).

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
