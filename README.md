# PFML

Season tracker for our Music League games. Static site, GitHub Pages, built
from Music League's own CSV exports. Live at https://pfml.fun

## How it works

Raw CSV exports go in `data/seasonN/`. A Python script turns them into JSON
and a static HTML page per season, and the site reads that JSON. There is no
database, no backend, and no Spotify API: every Spotify link is a plain
`open.spotify.com` URL built from IDs already present in the export.

```
data/season1/            raw Music League export (4 CSVs)
data/season2/
data/season3/
scripts/build.py         CSV -> JSON + season1.html, season2.html, ...
site/                    everything GitHub Pages serves
  index.html             home page: season cards + playlists, pfml.fun
  season.template.html   template build.py fills in per season
  season1.html           generated, one page per season, own URL
  season2.html
  season3.html
  style.css
  app.js                 shared by the home page and every season page
  data/
    index.json           generated: season list + each leader
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
template edits needed.

## Adding a new export

1. Export the season from Music League.
2. Drop the four CSVs into `data/seasonN/`, overwriting the old ones. For a
   brand new season, make a new `data/seasonN/` folder; the build discovers
   season folders by name and orders them numerically, generates its JSON
   and its `seasonN.html` page, and adds it to the home page automatically.
3. Commit and push. The Action rebuilds everything and redeploys.

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
  so this is the best signal available, not a fact the CSV states.

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
`https://open.spotify.com/playlist/...` URL and it becomes a live link on
the next deploy. Adding a Season 4 group here is manual, since these are
curated meta-playlists you build yourself, not something derivable from the
CSV export the way round playlists are.

To preview locally before pushing:

```bash
python scripts/build.py
cd site && python -m http.server 8000
```

The site fetches JSON, so opening `index.html` from the filesystem will not
work. Use the local server.

A season with a `competitors.csv` and nothing else builds fine and renders
empty states throughout, which is how Season 3 looks until its first round
closes.

## Player focus and comparison

Click a name in the Standings on any season page to filter everything below
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
`build.py` already produces.

## Scoring model

These were verified against the real exports rather than assumed, and a few
of them are not obvious:

- Each voter gets a fixed 16-point budget per round. A handful of Season 1
  voter-rounds total 11 instead.
- A row in `votes.csv` with 0 points is a comment, not a vote. Every
  zero-point row in both seasons carries a comment. The build counts these
  as commentary and never as scoring.
- Self-voting is blocked. The only rows where voter equals submitter are
  zero-point comments on your own track.
- Season 1 allowed negative votes (35 of them, -5 to -1). Season 2 did not.

Because the budget is fixed, "average points given" measures nothing:
everyone gives exactly 16 a round. The voting stats measure *where* a voter
puts their 16 instead.

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

## Spotify links

Track and playlist IDs are in the export, so those links are exact. Artist
and album names appear in the export as text with no IDs, so those links go
to a Spotify search scoped to the name. See `searchLink()` in `app.js`; if
real IDs are ever added to the data, swap it for `/artist/{id}` and
`/album/{id}`.
