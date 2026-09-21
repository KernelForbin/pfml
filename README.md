# PFML

Season tracker for our Music League games, built from Music League's own
CSV exports. Members only, at https://pfml.fun: you sign in with Google, and
your Google account is linked to your Music League player.

## How it works

Raw CSV exports go in `data/seasonN/` on your machine. `scripts/build.py`
turns them into JSON plus a static HTML page per season, and
`scripts/publish.py` uploads the JSON to a private Supabase storage bucket.
The pages themselves are static files on GitHub Pages, but they hold no
league data: after sign-in they download it from that bucket, which only
linked members can read. There is no Spotify API: every Spotify link is a
plain `open.spotify.com` URL built from IDs already present in the export.

**None of the league data is in this repo.** `data/` and `site/data/` are
git-ignored, and the deploy refuses to run if a JSON file or a `data/`
folder ever turns up in it. The repo's history was rewritten on
2026-09-21 to take out the CSVs and JSON older commits carried; see
Members only below.

```
data/season1/            raw Music League export (4 CSVs)       LOCAL ONLY
data/season2/                                                    (git-ignored)
data/season3/            ...plus daily_doubles.json
data/track_art.json      album art URLs, cached by publish.py, read by build.py
data/comment_sentiment.json   optional, written by enrich_comments.py, read
                              by build.py if present. Not required to build.
scripts/build.py         CSV -> JSON + season1.html, season2.html, ...
scripts/publish.py       build, then upload the JSON to Supabase (private)
scripts/invites.py       one-time invite links that link a Google account
                         to a player
scripts/supa.py          shared helper; reads the secret key from .env
supabase/schema.sql      tables, access rules and buckets; run once
tests/                   offline test suite (stdlib unittest, made-up data)
scripts/enrich_comments.py    standalone, run by hand, calls the Claude API.
                              Never run by build.py or by the Action.
site/                    everything GitHub Pages serves
  index.html             home page: season cards + playlists, pfml.fun
  career.html            cross-season standings, static, not templated
  season.template.html   template build.py fills in per season
  round.html             one round, full width: every track, vote and comment
  features.html          "What this site can do", public and standalone;
                         kept current with every visible change (CLAUDE.md)
  privacy.html           public privacy page
  rounds.js              the round cards on season pages and the round page,
                         with member votes, reactions and replies
  auth.js                the members-only gate, loaded by every page
  config.js              Supabase URL + publishable key (public by design)
  season1.html           generated, one page per season, own URL
  season2.html
  season3.html
  style.css
  app.js                 shared by the home page, career page, and every season page
  data/                  LOCAL ONLY (git-ignored), published to Supabase
    index.json           generated: season list + each leader
    career.json           generated: cross-season standings and highlights
    season1.json          generated
    season2.json
    season3.json
    playlists.json       hand-maintained, see below, NOT touched by build.py
  CNAME
```

`index.html` is the site's home page (`pfml.fun`): a card per season linking
to that season's own page, plus the playlists section. Each `seasonN.html`
is a full standings/rounds/stats dashboard for just that season, with its
own URL and its own `<title>` ("PFML - Season 1", etc.), generated fresh on
every build from `season.template.html`, so a new season gets a page with no
template edits needed. `career.html` is a fixed page (not per-season, so
not templated) that reads `career.json` for all-time standings.

## Tests

```bash
python -m unittest discover -s tests -v
```

Offline and stdlib-only, like the scripts. Every test builds its own tiny
made-up season in a temp directory (`tests/support.py`), so the suite never
reads the real exports or writes the real output. It covers the scoring
rules in `build.py` (zero-point rows are comments, shared places on ties,
the Daily Double and its failure modes, the blowout rule, album art, CRLF
handling, identical builds across hash seeds), the album-art lookup in
`publish.py` (backoff on 429, stopping early and keeping progress), and the
site's static contracts (the features page loads nothing but its fonts,
every page links to it, generated season pages match the template, no data
or secret keys are tracked). The deploy runs it before publishing.

`tests/test_live_spotify.py` calls Spotify's real endpoint and skips unless
`PFML_LIVE=1` is set. The browser JavaScript isn't covered by the suite
(there's no Node here); it's checked in a real browser, see CLAUDE.md.

## Members only

Every page is behind a Google sign-in, and a Google account only gets in
once it's linked to a Music League player. The gate isn't cosmetic: the
league data isn't on the public site at all, only in a private Supabase
bucket that the database lets linked members read and nobody else.

**Accounts and invites.** `members` pairs one Google account with one
player, one to one. The pairing is made by a one-time invite link:
`python scripts/invites.py` prints a `https://pfml.fun/?invite=...` link
for every player who isn't linked yet. Whoever opens a link and signs in
with Google becomes that player for good, and the link stops working, so
send each one privately to the right person. `--list` shows who has
joined; `--player "Name"` makes one link; `--admin "Name"` lets a linked
player delete anyone's replies. Google blocks sign-in inside some apps'
built-in browsers (Instagram, Facebook Messenger and similar): if someone's
link seems to do nothing, have them open it in Safari or Chrome.

**What's public and what isn't.** Public: the page shells (HTML, CSS, JS),
`site/config.js` (the Supabase URL and *publishable* key, which only allow
what the access rules allow), and `supabase/schema.sql`. Private: every
CSV, every season/career JSON, comments, votes, reactions and replies. The
Supabase *secret* key lives only in the git-ignored `.env` used by the
local scripts; it bypasses every access rule, so it never goes in the site
or in a commit.

**History.** Until 2026-09-21, commits from before the site went
members-only still carried the CSVs and built JSON. The history was
rewritten that day (`git filter-branch` removing `data/` and `site/data/`
from every commit, then a force-push), so no commit on GitHub holds league
data. Commit ids from before that date no longer match. Anyone with an
older clone should re-clone rather than pull. A full pre-rewrite backup is
kept outside the repo, locally, as a git bundle.

**One-time setup** (done once, recorded here for a rebuild from scratch):

1. Supabase: run `supabase/schema.sql` in the SQL Editor.
2. Google Cloud Console: create an OAuth client (type: Web application)
   with the authorized redirect URI
   `https://<project-ref>.supabase.co/auth/v1/callback`. Publish the
   OAuth consent screen (basic scopes need no Google review), otherwise
   only listed test users can sign in.
3. Supabase, Authentication > Sign In / Providers > Google: enable it and
   paste in the client ID and secret from step 2.
4. Supabase, Authentication > URL Configuration: Site URL
   `https://pfml.fun`; redirect URLs `https://pfml.fun/**` and
   `http://localhost:8000/**`.
5. `site/config.js`: the project URL and the publishable key.
6. `.env` (copy `.env.example`): the project URL and the secret key.
7. `python scripts/publish.py`, then `python scripts/invites.py`.

If signing in lands on `http://localhost:3000` (a dead page, with `?code=...`
in the address), step 4 didn't take: Supabase only returns people to an
address on its redirect list, and otherwise falls back to the Site URL,
whose default is `localhost:3000`. Fix the Site URL and the
`https://pfml.fun/**` entry and sign in again. Invite links aren't used up
by a failed return, so the same link works once it's fixed.

## Results by round, and the comments on them

On every season page, directly under Standings, **Results by round**,
collapsed by default. Standings folds the same way (see Season page
features). It's the most-used section, so even collapsed it's a
full-width card: the round count, the latest round and its winner, the
newest three winners' album art, and a Show all button. Open it for a card per round, newest first, with the
winning track's album art, the winner (or everyone tied for it) and the
counts. Every round in the export is listed, including one that so far only
has its prompt, which says so instead of showing results.

Each card opens that round on its own full-width page,
`round.html?s=season3&r=<round id>`, laid out like Music League's own round
view: the prompt, the winner and the round playlist up top, previous/next
round links, then a card per track in finishing order with its album art,
place (shared places marked as ties), points and voter count, who submitted
it and their note, and every vote cast on it (voter and points, biggest
first) with the comment that came with it in full. Rows that gave no points
are the comment-only votes, listed last.

**Album art** comes from Spotify's public oEmbed endpoint (no key or
account). `publish.py` looks up art only for tracks it hasn't seen before
and caches the image URLs in `data/track_art.json` (git-ignored), so
`build.py` stays offline and just copies each URL into the song's `art`.
Spotify rate limits bursts; when it does, the lookup stops early and the
next publish picks up the rest. A track with no art gets a placeholder. The
images themselves load from Spotify's image servers in the reader's
browser.

Members can vote each comment up or down, add reactions, and reply. Each
comment is identified by the id the build uses everywhere,
`<round id>|<spotify uri>|<voter id>`, so votes and replies stay attached
across new exports. The vote rows come from the season JSON (`votes` on
each song: `[voter id, points]`, scoring votes only); the member votes,
reactions and replies live in Supabase tables and are fetched per round,
the first time that round is opened. Votes show as a net score with the
up/down split on hover. Everything members add is visible to every member,
including who voted which way, at the data level. Replies are flat (no
nested threads) and can be deleted by their author or an admin, not edited.

The list follows the Standings player selection: only rounds the selected
players submitted to are listed.

The top bar holds Home, the seasons, then Career. Career also has a card
on the Home page, next to the season cards.

A round link survives sign-in: Google returns people to the bare page
address (the one on Supabase's redirect list), so `auth.js` keeps the
rest of the link (`?s=...&r=...`) in this tab's sessionStorage and puts
it back once the session exists, before any page code runs.

## Season page features

- **Standings** and **Results by round** open the page, in that order,
  both collapsed by default into a full-width bar with a summary and a Show
  all button. Standings' bar shows the player count and everyone placed
  3rd or better with their points (ties share a place, so that can be more
  than three people; past four it shows three and "+N more"). Open it for
  the full clickable list.

- **Jump nav**: a second row in the sticky top bar links to each section on
  the page (Standings, Results, Numbers, Trend, Tracks, Taste, Voting,
  Comments, Artists). A section that's currently hidden (Numbers while a
  player filter is active, Comments on a season with no rounds yet, Trend
  until a season has at least two rounds) drops out of the jump nav too,
  so it never links to something that isn't there.
- **Player focus and comparison**: click a name in Standings to filter the
  rest of the page to them, click a second to compare instead, see below.
- **Comments**: a section after Voting style with per-player comment counts
  and style rates, the words each player reaches for more than anyone else,
  who never says anything to whom, and the season's longest comment in full.
  It follows the Standings player selection the same way Top Tracks and
  Voting style do; with a selection active the season-wide superlatives drop
  out (they are season-wide, so they stop meaning anything next to a single
  player) and the longest comment becomes that player's. A season with no
  rounds has no comments, so the section hides itself and leaves the jump
  nav, exactly like the trend chart. Definitions are under Comment metrics
  below.
- **Performance over time**: three metrics, left to right. **Standing over
  time** is the default: leaderboard position, #1 to last, after each
  round's points are counted (a tie shares a place; competition ranking,
  so the next distinct total skips accordingly, e.g. 1, 1, 3). Its axis
  draws inverted, #1 at the top since that's the best place to be, and
  it's scaled to the whole field regardless of which players are toggled
  on, so a filtered view of the middle of the pack doesn't get stretched
  to look like the top. **Performance vs field** is next: cumulative
  points captured so far, as a percentage of the cumulative *winning*
  score to that point, i.e. what a player would have if they'd won every
  round. 100% means never off the pace; a line that rises then falls is
  someone who started strong and lost ground, a shape raw cumulative
  totals can't produce (they only ever go up, so on a graph everyone's
  line looks like a similar upward slope regardless of how they're
  actually doing). **Cumulative points** is last, the plain raw numbers.
  Whichever mode is active, hovering a line names the player and the
  value at that point, a hit point at every round so it's the specific
  round under the cursor, not just a fixed value for the whole line. A
  line is also clickable, same effect as its legend chip: toggles that
  player out of the plotted set. The chart defaults to everyone (Select
  all) and follows the Standings player selection when one is active,
  clear the scoreboard selection and it goes back to everyone. You can
  still toggle individual players on the chart's own legend, or by
  clicking their line, independent of the scoreboard until the scoreboard
  selection changes again. Colors are assigned by season rank so a given
  player's color stays consistent across toggles.

## Adding a new export

1. Export the season from Music League.
2. Drop the four CSVs into `data/seasonN/`, overwriting the old ones. For a
   brand new season, make a new `data/seasonN/` folder; the build discovers
   season folders by name and orders them numerically, generates its JSON
   and its `seasonN.html` page, and adds it to the home page automatically.
3. **Season 3 only:** review the new round's submitter notes for Daily
   Double requests and record the decision in
   `data/season3/daily_doubles.json` (see Daily Double below). The build
   prints a warning for any round that hasn't been reviewed.
4. `python scripts/publish.py`. That builds and uploads, and the new data
   is live for members straight away; there's nothing to commit for data.
5. Only if the build created or changed a `site/seasonN.html` page (a new
   season), commit and push that page so GitHub Pages serves it.

## The "live" season on the home page

The home page marks whichever season is last by number as the current one.
If it has at least one round, its card shows a LIVE badge, the round it's
on, a phase, and a start date. All of that comes from inference, not a
field Music League's export states outright, worth knowing before you trust
it blindly:

- **Started** is the `Created` timestamp of that season's first round.
- **Round N** is just "however many rounds exist so far," on the assumption
  the most recently created one is the one currently in play.
- **Phase** (Song Selection vs. Voting) is guessed from whether anyone has
  a row in `votes.csv` for that round yet, since a voter only appears there
  once voting has opened, even a zero-point comment-only vote counts. There
  is no field in the export for phase or for submission/voting deadlines,
  so this is the best signal available, not a fact the CSV states. It
  never moves past "Voting" on its own: a round where everyone has voted
  looks identical in the export to one still taking votes, so a finished
  round keeps reading "Voting" until the next round appears.

A season with zero rounds in its CSVs (a freshly created `data/seasonN/`
with only `competitors.csv`) shows "not started yet" instead, no LIVE badge,
no guessed round or phase, since there is nothing to infer from.

## Playlists on the home page

`site/data/playlists.json` is the one file in `site/data/` that `build.py`
never touches, it's yours to edit directly. It holds the league-wide and
per-season playlist links shown on the home page. Each entry looks like:

```json
{ "label": "PFML - S1 - All Submissions", "url": null }
```

`url: null` renders as a "coming soon" chip with no link. Fill in a real
`https://open.spotify.com/playlist/...` URL and it becomes a live link the
next time you run `scripts/publish.py`. The file is git-ignored like the
rest of `site/data/`, and publish uploads it with the other data. Adding a Season 4 group here is manual, since these are
curated meta-playlists you build yourself, not something derivable from the
CSV export the way round playlists are.

To preview locally before publishing or pushing:

```bash
python scripts/build.py
cd site && python -m http.server 8000
```

then open `http://localhost:8000` and sign in as usual (localhost is on the
sign-in allowlist, see Members only). The local pages still read the data
from Supabase, not from your local `site/data/`, so a data change shows
up locally only after `publish.py`. Opening `index.html` from the
filesystem will not work.

A season with a `competitors.csv` and nothing else builds fine and renders
empty states throughout, which is how Season 3 looked before its first
round was exported.

A season with exactly one round renders too, minus whatever needs more
history: the trend chart stays hidden until there are two rounds (with one,
every line is a single dot and the chart is a column of dots over an empty
plot), and the taste and comment matrices stay empty until a pair reaches
its 5-chance minimum, which takes five rounds.

## Player focus and comparison

Open Standings on any season page and click a name to filter everything below
(top tracks, rounds, taste matrix, voters, artists) to just that person, and
a Player Focus panel appears with stats scoped to them: best and weakest
submission, most divisive submission, biggest fan, hardest to win over,
favorite to vote for, voting style.

Click a second name to compare instead of filter: the panel switches to a
side-by-side standings comparison, a head-to-head tally (whoever placed
best in each round both submitted to), and, for exactly two people, their
mutual taste index in both directions. Select a third, fourth, etc. and the
comparison table and head-to-head tally extend to the whole group; the
two-way mutual taste tiles only make sense for a pair, so they drop out
once a third person joins.

Everything here is computed client-side in `app.js` from data already in
`seasonN.json`, no extra build step and no new fields needed beyond what
`build.py` already produces. The "season in numbers" block hides itself
while a filter is active (it's a season-wide summary, not a per-player one,
so it stops making sense to show it between player-specific panels), and
its jump-nav link disappears along with it.

## Career page

`career.json`, built once per `build.py` run from all seasons' standings,
joins players across seasons by competitor id. This relies on Music
League reusing the same id for the same person across separate CSV
exports, which was checked against the real data (13 people who played
all 3 seasons, zero id/name mismatches) rather than assumed. A season
with zero rounds contributes nothing, since nobody has a standings entry
in it yet. If a name ever looks wrong on the Career page for someone who
changed their Music League display name between seasons, that's the
join taking the first name it saw for that id; `build_career()` in
`build.py` is where to change that if it comes up.

`career.html` also carries an all-time Comments section: the same
per-player table aggregated across every season played, plus career
superlatives (most talkative, most terse, wordiest, quietest, biggest
silent treatment, widest vocabulary, most all-talk, most notes on their
own picks) and the longest comment anyone has ever written, with the
season it came from.

Two of those numbers cannot be recombined from the per-season summaries
and are recomputed from the raw comments instead: a career median
words-per-comment is the median over all of someone's comments, not the
mean of their per-season medians, and career vocabulary richness needs the
union of the words they used, not a sum of per-season unique counts. So
`build_season()` hands `build_career()` the raw corpus in memory
(`build_career_comments()`), deliberately not through `seasonN.json` —
shipping every raw comment length per player per season would bloat a file
the site downloads, for data no page reads.

The all-time standings table is sortable by clicking any column header,
including the season-by-season point columns; click again to flip the
direction. Someone who hasn't played a season sorts to the bottom of that
column regardless of direction, rather than sorting as a zero.

### Career Score

Default sort is Career Score, not raw total points. The formula:

```
Career Score = Total Points + 10 x Rounds Won + 5 x Podium Finishes
```

Podium finishes include the win itself, so a round win adds both bonuses:
+15 on top of the points that round actually scored. The 10 and 5 aren't
arbitrary: across the real data, a round winner scores about 10 points
above the field average (26.0 vs 15.8 in Season 1, 25.6 vs 15.7 in Season
2), and a podium finisher scores about 7-8 points above average. The
weights round those measured premiums to clean numbers. Raw points alone
rewards volume; this rewards actually winning and placing on top of that,
which is why the ranking can differ from a plain points sort, someone with
fewer total points but more wins can outrank someone who racked up points
without ever taking a round. `WIN_BONUS` and `PODIUM_BONUS` are the two
constants to change in `build.py` if the weighting should shift.

## Scoring model

These were verified against the real exports rather than assumed, and a few
of them are not obvious:

- Each voter gets a fixed point budget per round, but not the same one
  every season: 16 in Seasons 1 and 2, 19 in Season 3. The build reads it
  from the votes (`pointBudget`, the most common per-voter round total)
  rather than assuming it, and the Voting style copy shows each season's
  real number. A handful of Season 1 voter-rounds total 11 instead.
- A row in `votes.csv` with 0 points is a comment, not a vote. Every
  zero-point row in all three seasons carries a comment. The build counts
  these as commentary and never as scoring.
- Self-voting is blocked. The only rows where voter equals submitter are
  zero-point comments on your own track.
- Season 1 allowed negative votes (35 of them, -5 to -1). Seasons 2 and 3
  did not.

Because the budget is fixed, "average points given" measures nothing:
everyone gives exactly the same budget a round. The voting stats measure
*where* a voter puts their points instead.

## Daily Double (Season 3)

Season 3 adds a rule: once per season, a submitter can ask, in their own
note on a submission (`submissions.csv` "Comment"), to have that track's
points doubled toward their season total. A second request from the same
person is disregarded.

**Decisions are recorded, not detected.** A note can mention the prop
without invoking it ("no daily double this week", a joke about someone
else's), so whether a note is a request is a judgement about intent. The
build never parses notes for it. Each round's notes are read when that
round's export arrives, and the outcome goes in
`data/season3/daily_doubles.json`, a hand-maintained file that
Music League exports never touch:

- `reviewedRounds`: one entry per round whose notes have been checked,
  including rounds with no requests, so "reviewed, nothing found" is
  distinguishable from "never looked". The build warns about any round
  missing from this list.
- `requests`: one entry per note that reads as a request, with the round
  id, Spotify URI, submitter id, the note, `decision` (`accepted` or
  `rejected`) and a reason. Only `accepted` entries affect scores.

**What it changes.** The track's points count twice toward the
submitter's season total: a track that earned 23 adds 46, and the
standings row shows the +23 with the track and round it came from. The
bonus flows everywhere the season total does: standings order, the home
page leader, the Standing over time and Cumulative points charts, and the
Career page's season column, total and Career Score.

**What it doesn't.** The track's own score is still what the votes gave
it, so the round's placings, round wins, podiums, Top tracks and the
per-submission average are all unaffected. Doubling is literal: a track
that scored 0 adds nothing, and the Daily Double is still used up.

**Safety checks.** Rounds are applied in the order they were created, so
if two accepted requests from one person ever made it into the file, the
earlier round counts and the later one is ignored with a printed reason.
The build refuses to run, rather than quietly dropping a bonus, if the file
is unreadable, if an accepted request doesn't match a real submission, or
if two accepted requests point at the same track. A request whose
submitter doesn't match the track's submitter is ignored with a warning.

Seasons without a `daily_doubles.json` file (Seasons 1 and 2) don't use
the rule at all.

## Ties

Ties are real in this data (Season 3's first round ended with two players
level on 29), so nothing that names a winner picks one silently:

- **Standings** go by points, and equal points share a place, shown as
  `T1`, `T1`, `3` (competition ranking, the same rule rounds and the
  Standing over time chart use). Rounds won orders people within a shared
  place but doesn't break the tie.
- **Rounds**: tracks level on points share a finishing place, and every
  track in first place is credited with a round win (and so a podium, and
  the Career Score bonuses for both).
- **Home page**: a season whose top spot is shared says "Tied for the
  lead" (or "Joint winners" once it's over) and names everyone in it
  (`leaderNames` in `index.json`).
- **Every superlative** (season in numbers, comment superlatives, career
  highlights) is computed with `best_of()` in `build.py`, which returns the
  whole group tied for the best value rather than whichever one `max()`
  met first. The card names the first of the group, in a fixed order
  (alphabetical for people and tracks, earliest first for rounds), and a
  "Tied with ..." line names the rest (`tiedWith` in the JSON). A long tie
  shows three names and "and N more", with the full list on hover.
  "Silent treatment" and "Most talked at" rank on the comment rate and then
  the number of chances, so a tie there means both are equal.
- **Biggest blowout** only appears once some round was won by a wider
  margin than the closest round. With one round, or every round won by the
  same margin, it would repeat the closest round, and after a tie it read
  "won by 0 points".

## Derived metrics

**Taste index** — the share of a voter's points that went to one submitter,
divided by the share you would expect if they spread points evenly across
every track they saw. 1.00 is neutral, 2.00 is twice their baseline. Self-
votes are excluded and a pair needs at least 5 chances to vote before it is
shown, so one lucky round does not read as a lifelong grudge.

**Top bet** — the average size of a voter's single largest bet in a round.
High means they concentrate, low means they spread.

**Tracks backed** — how many tracks a voter puts at least one point on per
round. The other half of the same picture.

**Top pick won** — how often the track a voter gave their most points to
went on to win the round.

**Divisive track** — the widest standard deviation of points among the
voters who actually backed it, limited to tracks with at least 3 backers.

## Comment metrics

Two different things live in the export and the build keeps them apart:

- **Vote comments** come from the `Comment` column of `votes.csv`: what a
  voter said about someone else's track. 2,194 of 3,879 vote rows in
  Season 1, 3,057 of 4,189 in Season 2.
- **Submitter notes** come from the `Comment` column of
  `submissions.csv`: the submitter explaining their own pick. Far rarer
  (60 of 316 submissions in Season 1, 36 of 318 in Season 2) and a
  different act, so they are never mixed into the vote-comment numbers.

Every zero-point vote row carries a comment, and the build treats those as
commentary and never as scoring (see the Scoring model above). That is why
someone can have a low vote total and a high comment count: **zero-pt** in
the table counts exactly those, comments that awarded nothing.

**A word**, everywhere a word is counted, is a run of letters and
apostrophes (`comment_words()` in `build.py`). "don't" is one word; "2024"
and a bare "..." are none. For the stopword filter and for the distinctive
word, words are also lowercased with apostrophes stripped, so "Don't",
"don't" and "dont" are the same word.

**Comment rate** — the share of a player's vote rows carrying a comment.
The denominator is every row they filed, including the zero-point rows
that exist only to carry a comment.

**Style rates** (exclamation, question, ALL-CAPS, emoji) — the share of a
player's comments containing *at least one*, not an average count per
comment. One comment shouting "YES!!!!!!!!" would drag a per-comment
average into nonsense; "what fraction of their comments do this" is robust
to it and is what the page claims. An ALL-CAPS word means three or more
letters, all uppercase, so "I", "a" and "OK" don't count as shouting.

**Vocabulary richness** — mean segmental type-token ratio: unique words
divided by total words, measured on consecutive fixed 500-word chunks and
averaged, not computed over a player's whole corpus at once.

This one needs the explanation. A raw unique/total ratio falls as a body
of text grows, because you run out of new words to use, so comparing it
between players mostly ranks them by how little they wrote. In this
league's real data that inversion is nearly total: on a raw ratio the top
of the ranking is the player with 813 words and the bottom is the player
with 13,549. Chunking fixes the denominator so everyone is compared over
the same amount of text. Anyone with fewer than 500 words is left out of
the comparison rather than given a flattering number. `vocabRichness` in
the JSON is still the raw ratio, kept for reference; nothing ranks on it,
and `vocabRichnessSampled` is what the page shows. `VOCAB_SAMPLE_WORDS`
in `build.py` is the chunk size.

**Distinctive word** — the same share-versus-baseline shape as the taste
index, applied to vocabulary: the player's share of a word divided by the
league's share of that word. A word must appear at least 3 times for that
player to qualify, so a one-off can't win on a denominator of one, and
stopwords are removed first. The stopword list is hand-written in
`build.py` (`STOPWORDS`), deliberately small and dependency-free. It
covers English function words plus the handful that dominate *every*
Music League comment ("song", "track", "love") and would otherwise be the
answer for all 16 players, telling you nothing about any of them.

**Comment matrix** — how often a voter comments on a given submitter's
tracks, out of the chances they had to. It shares the taste matrix's
denominator exactly (one "chance" is one of that submitter's tracks the
voter could have voted on, self-votes excluded) and its minimum-sample
guard: a pair needs at least 5 chances before it counts, so one round
can't read as a habit. **Silent treatment** is the pair with the lowest
comment rate over the most chances: the person you have had every
opportunity to say something to and never have.

**Longest comment** — ranked by word count, with character count as the
tiebreak. The text is shown in full, because the length is the point; it
is the only place the page prints a comment verbatim.

Superlatives and rate-based stats require at least `MIN_COMMENTS_FOR_RATES`
(10) comments. Below that a single exclamation mark reads as a 33%
exclamation rate, so those players appear in the table but are not
eligible to win anything.

### Comment sentiment (optional, and not part of the build)

`scripts/enrich_comments.py` is a standalone local tool that labels each
vote comment with any mix of *witty, funny, rude, appreciative,
storytelling, analytical*, plus a one-line rationale. It is the only thing
in this repo that calls an API and it costs money to run.

**Nothing automatic ever runs it.** `build.py` does not call it, and
neither does the GitHub Action — the deploy has no API key and must never
need one. The script's only output is `data/comment_sentiment.json`;
`build.py` reads that file if it exists and merges the labels in, and if
it is absent the build behaves exactly as it did before and the site omits
every sentiment-based stat. Labels are never inferred at build time, and a
label outside the known set is dropped rather than rendered.

```bash
pip install anthropic          # local only; build.py stays stdlib-only
export ANTHROPIC_API_KEY=sk-ant-...

python scripts/enrich_comments.py --estimate   # measured cost, no API call
python scripts/enrich_comments.py --dry-run    # prints what would be sent
python scripts/enrich_comments.py              # label what isn't labelled yet
```

**Cost.** Run `--estimate` first: it counts real tokens with
`messages.count_tokens` against the real prompt and prints a dollar figure
for both the batch and standard paths, rather than guessing. It defaults
to the Batch API, which is half price and usually finishes well inside an
hour; `--sync` sends requests one at a time at full price if you want to
watch it work. The per-MTok prices used for the estimate are constants at
the top of the script — check the pricing page if they look stale.

**Re-running after a new export.** Labels are keyed by a stable comment id
(round id + spotify URI + voter id), computed the same way in both
scripts. A re-run only sends comments that aren't already in the file, so
adding a season costs only that season. `--force` re-labels everything,
and `--season seasonN` restricts it to one season.

**Commit the JSON if you want the labels live.** The Action runs
`build.py` on a clean checkout, so it can only see
`data/comment_sentiment.json` if that file is committed. It is safe to
delete at any time: the next build just drops the sentiment stats.

## Spotify links

Track and playlist IDs are in the export, so those links are exact. Artist
and album names appear in the export as text with no IDs, so those links go
to a Spotify search scoped to the name. See `searchLink()` in `app.js`; if
real IDs are ever added to the data, swap it for `/artist/{id}` and
`/album/{id}`.
