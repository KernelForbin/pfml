# PFML

Season tracker for our Music League games. Static site, GitHub Pages, built
from Music League's own CSV exports. Live at https://pfml.fun

## How it works

Raw CSV exports go in `data/seasonN/`. A Python script turns them into JSON,
and the site reads that JSON. There is no database, no backend, and no
Spotify API: every Spotify link is a plain `open.spotify.com` URL built from
IDs already present in the export.

```
data/season1/        raw Music League export (4 CSVs)
data/season2/
data/season3/
scripts/build.py     CSV -> JSON, standard library only
site/                everything GitHub Pages serves
  index.html
  style.css
  app.js
  data/*.json        generated, committed for convenience
  CNAME
```

## Adding a new export

1. Export the season from Music League.
2. Drop the four CSVs into `data/seasonN/`, overwriting the old ones. For a
   brand new season, make a new `data/seasonN/` folder; the build discovers
   season folders by name and orders them numerically, so nothing else needs
   editing.
3. Commit and push. The Action rebuilds the JSON and redeploys.

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
