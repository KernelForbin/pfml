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
git-ignored, and the deploy refuses to run if a JSON, CSV or `.env*` file
turns up in `site/`, or a `data/` folder in the repo. The repo's history
was rewritten on 2026-09-21 to take out the CSVs and JSON older commits
carried, though GitHub still serves the old commits by id until the repo is
recreated; see Members only below.

```
data/season1/            raw Music League export (4 CSVs)       LOCAL ONLY
data/season2/                                                    (git-ignored)
data/season3/            ...plus daily_doubles.json
data/track_art.json      album art URLs, cached by publish.py, read by build.py
data/comment_sentiment.json   optional, written by enrich_comments.py, read
                              by build.py if present. Not required to build.
data/translations.json   English for comments and notes in another language;
                         hand-kept, read by build.py if present
scripts/build.py         CSV -> JSON + season1.html, season2.html, ...
scripts/publish.py       build, then upload the JSON to Supabase (private)
scripts/invites.py       one-time invite links that link a Google account
                         to a player
scripts/supa.py          shared helper; reads the secret key from .env
scripts/serve.py         local preview that resolves /career to career.html,
                         like GitHub Pages
scripts/update_emoji_data.py  regenerates site/emoji-data.js from Unicode's
                              emoji list; run by hand, rarely
scripts/enrich_comments.py    run by hand, calls the Claude API. Never run
                              by build.py or by the Action.
scripts/security_check.py     the daily security check (security-check.yml);
                              scripts/security_reviewed.txt lists the Supabase
                              advisories already judged
scripts/stamp_check_time.py   at deploy, puts the last clean check's time on
                              the privacy page
supabase/schema.sql      tables, access rules and buckets; run once
supabase/migrations/     one-off changes to the live project, run by hand in
                         the SQL Editor (schema.sql already includes them)
supabase/checks/         scripts the user runs in the SQL Editor to rehearse
                         a change for real; they roll themselves back
supabase/setup/          one-off setup the user runs in the SQL Editor (the
                         reminders timer); secrets are filled in at the time,
                         never stored here
supabase/functions/      Edge Functions, deployed by hand from the dashboard:
                         search-tracks, send-reminders
tests/                   offline test suite (stdlib unittest, made-up data)
site/                    everything GitHub Pages serves
  index.html             home page: season cards + playlists, pfml.fun
  career.html            cross-season standings, static, not templated
  season.template.html   template build.py fills in per season
  round.html             one round, full width: every track, vote and comment
  profile.html           one player's profile (?p=<competitor id>; yours without it)
  features.html          "What this site can do", public and standalone;
                         kept current with every visible change (CLAUDE.md).
                         Opens with "New in the last 30 days": each item dated
                         by its CHANGELOG entry, and an inline script hides
                         items older than 30 days, then the box itself.
                         Home's What's new button links here and says New
                         until this browser has opened the page since the
                         newest line (FEATURES_UPDATED in app.js; the page
                         stores pfml.featuresSeen in localStorage)
  privacy.html           public Privacy and Security page
  rounds.js              the round cards on season pages and the round page,
                         with member votes, reactions and replies
  voting.js              voting on the site: the ballot and results on the
                         Submit page; built and switched off (README, Voting
                         on the site)
  sw.js                  the service worker: shows notifications, nothing
                         else (no caching); README, Reminders
  emoji-data.js          generated by scripts/update_emoji_data.py, committed;
                         the reaction picker's searchable emoji (round.html only)
  auth.js                the members-only gate, loaded by every page
  account.js             the header's inbox and initials menu (My profile,
                         Sign out), loaded by every members-only page; also
                         the one copy of the avatar, reaction-glyph and
                         "3h ago" helpers the other pages share
  config.js              Supabase URL + publishable key (public by design)
  season1.html           generated, one page per season, own URL
  season2.html
  season3.html
  style.css
  app.js                 shared by the home, career, profile, round and season pages
  data/                  LOCAL ONLY (git-ignored), published to Supabase
    index.json           generated: season list + each leader
    career.json           generated: cross-season standings and highlights
    profiles.json         generated: per-player seasons, best tracks, fans
    lookup.json           generated: round id -> season, number, name, track
                          titles, for the inbox
    season1.json          generated
    season2.json
    season3.json
    playlists.json       hand-maintained, see below, NOT touched by build.py
    playlist_stats.json  written by publish.py: each playlist's size
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
the point budget, the Daily Double and its failure modes, the blowout rule,
album art, CRLF handling, season folders in numeric order, identical builds
across hash seeds), and that every field the build writes is read by a page
(members download these files, so dead weight is caught). In `publish.py`:
the album-art lookup (backoff on 429, stopping early and keeping progress),
the playlist-size parsing, and what gets backed up. Then the site's static
contracts (the features page loads nothing but its fonts, every page links
to it, the scripts load in the order they depend on, generated season pages
match the template, no `.html` links, the local preview server, no data or
secret keys are tracked), the deploy workflow,
the profile and inbox data,
the database schema and migrations, the committed emoji data, and the parts
of `enrich_comments.py` that decide what gets stored. The deploy runs it
before publishing.

The live tests skip unless `PFML_LIVE=1` is set:
`tests/test_live_spotify.py` calls Spotify's real oEmbed endpoint and
playlist pages, `tests/test_live_emoji_data.py` checks the committed
`site/emoji-data.js` is what its pinned version builds,
`tests/test_live_playlists.py` checks the round-playlist lookups, and
`tests/test_live_cdn.py` checks jsDelivr still serves the supabase-js file
the pages' integrity hash describes, and `tests/test_live_round_repeats.py`
runs the round-repeat rules on the real database. The browser
JavaScript isn't covered by the suite (there's no Node here); it's checked
in a real browser, see CLAUDE.md.

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

**The one outside script is pinned by hash.** supabase-js comes from
jsDelivr and runs on every signed-in page with the member's session, so a
tampered copy on the CDN could act as them. Each page's tag pins version
2.116.0 and carries an `integrity` hash (with `crossorigin="anonymous"`,
which the hash needs), and a browser refuses any file that doesn't match.
The hash was measured on 2026-10-22, and jsDelivr's file, the npm tarball's
copy and jsDelivr's own API hash all agreed. To change the version, compute
the new file's `sha384` and update every page's tag and the
`SUPABASE_JS_*` constants in `tests/test_site.py` together. Then run the
live test `test_live_cdn.py`, which fetches the real file and checks the
hash and the CORS header. A wrong hash leaves every page stuck before
sign-in.

**New tables need explicit grants.** From 2026-10-30, Supabase stops
granting `anon`/`authenticated`/`service_role` access to new tables in
`public` by default. A table created after that date returns "permission
denied" through the API until a `grant` says otherwise, even with row level
security policies in place. Tables that already exist keep their grants.
Any migration that creates a table therefore needs to state its grants
alongside its policies. Grant only what the site reads or writes, and grant
nothing to tables kept behind security definer functions, such as
`site_submission_owners` and `search_cache`.

**History.** Until 2026-09-21, commits from before the site went
members-only still carried the CSVs and built JSON. The history was
rewritten that day (`git filter-branch` removing `data/` and `site/data/`
from every commit, then a force-push), so no branch holds league data.
GitHub still serves the old commits by their ids (checked 2026-09-22: a
raw URL for a pre-rewrite commit's CSV still loaded) until the repo is
deleted and recreated, which is pending. Commit ids from before that date
no longer match. Anyone with an older clone should re-clone rather than
pull. A full pre-rewrite backup is kept outside the repo, locally, as a git
bundle.

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

**Moving between pages.** Every page load checks the session and looks up
the membership before any data loads. When the browser already holds a
saved sign-in (supabase-js's `sb-<project ref>-auth-token` in
localStorage), the page shows its own layout straight away, with a thin
loading bar along the top, while that check runs. The "Signing you in"
card only appears for a first visit or an invite link. If the check fails
(expired session, account not linked), the usual card replaces the page.
The page's data still loads only after the check lets the member in.

If signing in lands on `http://localhost:3000` (a dead page, with `?code=...`
in the address), step 4 didn't take: Supabase only returns people to an
address on its redirect list, and otherwise falls back to the Site URL,
whose default is `localhost:3000`. Fix the Site URL and the
`https://pfml.fun/**` entry and sign in again. Invite links aren't used up
by a failed return, so the same link works once it's fixed.

**Google always asks which account.** Sign-in passes `prompt=select_account`
(`signIn` in `auth.js`), so Google shows its account picker every time.
Without it, Google quietly reused the account the browser last signed in
with, so someone who picked the wrong account had no way back: signing out of
the site and in again landed on the same account and the same "not linked"
card. The not-linked card and the failed-invite card now lead with **Use a
different Google account**, which signs out of the site and goes straight to
the picker. A pending invite is kept apart from the session, so it's claimed
by the account picked next. Measured 2026-10-24: supabase-js 2.116.0 puts
the parameter on the `/auth/v1/authorize` address, and Supabase's redirect
carries it to accounts.google.com.

**Links survive sign-in.** Google returns people to the bare page address
(the one on Supabase's redirect list), so `auth.js` keeps the rest of the
link (`?s=...&r=...`) in this tab's sessionStorage and puts it back once
the session exists, before any page code runs.

**Clean addresses.** No address on the site ends in `.html`: links go to
`/career`, `/season1`, `/round?s=...&r=...`, `/profile?p=...`, and home is
`/`. GitHub Pages serves each of those from the matching `.html` file,
query strings included (measured on pfml.fun, 2026-09-22), so the files
keep their names. An old `.html` address, from a bookmark, still loads, and
the page tidies its own address bar (`history.replaceState`, keeping
`?query` and `#hash`; `/index.html` becomes `/`). That runs first thing in
`auth.js`, before sign-in reads or stores the address, and inline in the
two standalone pages, `features.html` and `privacy.html`. A test fails if
any page builds a link ending in `.html`. Python's plain `http.server`
doesn't resolve clean paths; `scripts/serve.py` does, for local previews.

The privacy page ("Privacy and Security") is linked from every page's
footer and from the sign-in card itself (`showGate` in `auth.js`), since a
signed-out visitor sees only that card; the footers are hidden until
sign-in. Its own footer links back to the site. The features page is
linked from Site features in the initials menu and Home's What's new
button, and from the sign-in card, since a signed-out visitor has no menu;
it left the footers on 2026-10-25.

### Security check

Near the privacy page's top, a **Security check** card gives members a
plain-language summary, with two times: the last full review (by hand,
in the card's wording) and when the daily check last passed (stamped at
deploy). Keep each claim on it true.

**The 2026-10-24 full review** covered security advisories from the
previous 30 days for Supabase, GitHub Actions, supabase-js and browsers; a
read-only probe of the live project with only the public key (every table
returned 0 rows, writes and members-only functions were refused, storage
listed nothing, and the search function said "members only"); and a review
of every place the pages put text into HTML (all escaped). That review
found the reaction-name problem under Reactions, which was fixed.

The first pass missed one advisory, which a recheck the same evening
caught. Supabase Storage GHSA-8rrf-w776-x75g (critical, published
2026-10-14) let a stranger upload or overwrite files, in private buckets
too, through signed resumable-upload routes, up to Storage 1.80.1. It's
published only on Supabase's own repo: it isn't in GitHub's global advisory
database, and NVD's "supabase" keyword mostly finds other apps (22 of 24
CVEs in four months, measured 2026-10-24). Live Storage reported 1.80.2,
the fixed version (`/storage/v1/version`). Every object in both buckets was
read back with the secret key and matched the local copies byte for byte,
all written by the publish at 00:56 UTC on 2026-10-25, with no files
`publish.py` doesn't send. Whether anything was swapped before Supabase
patched the project can't be known, and that publish would have overwritten
it. Since the bucket's data reaches the page, playlist links from it now
become links only when they're `https`.

**The daily check** (`.github/workflows/security-check.yml`, 11:17 UTC)
runs `scripts/security_check.py`, which fails when:

- an advisory in GitHub's database affects the exact version of
  supabase-js, a package it bundles, or a pinned action (reviewed or malware)
- live Storage or Auth (they report their versions) sits inside the range
  of one of Supabase's own advisories for it
- any Supabase repo, or PostgREST, published an advisory since the last
  clean run that isn't listed in `scripts/security_reviewed.txt`
- the outside test reaches anything: a row of any table in `schema.sql`, a
  write to a table with an insert policy (each attempt breaks a check
  constraint, so it can't land even if a policy let it through), a function
  other than `is_member`/`is_admin` (which answer a stranger `false`), a
  bucket's files, or an Edge Function

A clean run triggers the deploy (`workflow_run`), and every deploy looks
up the latest clean run and writes its time into the deploy's copy of the
privacy page (`scripts/stamp_check_time.py`), so no commit is needed. The
page shows it in the reader's own time. A failed run deploys nothing, so
the page keeps its last clean time, and GitHub emails the failure to the
account that last changed the schedule.

When it fails: read the run's summary. For a new Supabase advisory, judge
whether it touches PFML and add a line to `scripts/security_reviewed.txt`
(id, date, why), then push. Listing an advisory never quiets the version
check: a live service inside its range keeps failing until Supabase patches
it. GitHub turns off scheduled workflows in a public repo after 60 days with
no commits, and the card's time would then show its age; re-enable it under
Actions.

## Results by round, and the comments on them

**Recap** (top of each round page, `recapLines` in `rounds.js`). It's worked
out from the round's own data, with nothing extra built:
- **Winner:** the winning track, who sent it, its points and the margin to
  second, or the tie.
- **Most talked about:** the track with the most comments, when at least two.
- **Broadest support:** the track with points from the most voters, "16 of
  18".
- **Biggest bet:** the largest single vote.

A tie goes to the higher-placed track. A round without results shows none.
It first shipped with a Copy recap button, which put a plain-text version
on the clipboard; the user had it removed on 2026-10-24.

On every season page, directly under Standings, **Results by round**,
collapsed by default. Standings folds the same way (see Season page
features). It's the most-used section, so even collapsed it's a
full-width card: the round count, the latest round and its winner, the
newest three winners' album art, and a Show all button. Open it for a card per round, newest first, with the
winning track's album art, the winner (or everyone tied for it) and the
counts. Every round in the export is listed, including one that so far only
has its prompt, which says so instead of showing results. The list follows
the Standings player selection: only rounds the selected players submitted
to are listed.

Each card opens that round on its own full-width page,
`round?s=season3&r=<round id>`, laid out like Music League's own round
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

A vote, reaction or picker on a comment redraws that comment, reply box
included. A reply being typed survives it: the text is kept per comment
in `state.drafts` in `rounds.js` and written back, with focus and the
cursor restored, and it's dropped only once the reply saves (a failed
send keeps it). Drafts live in the page only; leaving the page loses them.

A dropdown at the top of every round page jumps to any other round in that
season, alongside the previous/next links.

**The song stays in view.** Once a track's own header has scrolled up
under the top bar, a slim bar with its art, title, artist and points stays
pinned there while its votes and comments scroll past, until the card ends
and the next track's bar takes over (`pinHtml` / `updatePins` in
`rounds.js`, `.rp-pin` in `style.css`). Not the whole header: that's about
160px, a third of a phone screen under a 107px top bar. The bar's wrapper
is sticky and 0px tall, and the bar is shown by a class, so showing and
hiding it never moves the page (measured: 0px with scroll anchoring off).
It sits at `--topbar-h`, the top bar's real height, which `app.js` keeps
current alongside the scroll padding. Two things it depends on: the card
uses `overflow: clip`, since `overflow: hidden` makes the card a scroll
container and nothing inside it can stick (Safari before 16 lacks clip, so
there the bar just never appears); and the bar takes no taps and is hidden
from screen readers, because it only repeats the header.

Each voter's name and points row sits on a faint magenta gradient running
the card's full width, so voters read as separate blocks.

**Reactions.** The "add a reaction" button (a drawn outline icon, not a
smiley character, which phones render as a full-colour yellow face) opens
just the original 6 as a one-tap row, plus **More**. More opens a panel
over the rest of Unicode's emoji (1,908): a search box, 9 category tabs
(Unicode's groups) and a grid. The grid only ever holds one category or
the search matches (`fillEmojiGrid` in `rounds.js`), never all 1,908:
laying those out took about a second the first time. Search is by name,
ranked whole name, whole words, word starts, then anywhere, shortest name
first within a rank, capped at 150. Typing redraws only the grid, so the
box keeps focus. The 6 are also in More, under their Unicode names plus
their stored name ("laugh" finds 😂). On a phone More is a bottom sheet with
its own close button, kept above the iOS keyboard via `visualViewport`;
tapping outside or pressing Escape also closes it. Don't filter it by
setting `hidden` on buttons: any CSS `display` rule on them beats the
attribute, which is exactly how the first search silently did nothing.

Storage: the original 6 are stored by name (`fire`, `laugh`, `hundred`,
`eyes`, `grimace`, `heart`), which is what every reaction added before the
picker used, so old and new reactions of those 6 count together. Anything
else is stored as the emoji character itself. The data comes from
`site/emoji-data.js` (a plain script, deferred, loaded by `round.html`
only), generated from the `unicode-emoji-json` package, pinned at 0.9.0,
by `scripts/update_emoji_data.py`. It leaves the 6 out, so none of them can
end up stored two ways. The database had allowed only those 6 names; the
column is now length-bounded instead (`supabase/migrations/2026-09-22_widen_comment_reactions.sql`
for the live project, already folded into `schema.sql` for a new one).
Until that migration has been run, any reaction outside the 6 fails to
save.

Because the column takes any 1-32 characters, a member can store a
reaction named `constructor` or `__proto__` from the browser console. The
page counts reactions by name, so those counters are made with
`Object.create(null)` (`reactionsFor` in `rounds.js`, the profile tally in
`app.js`), and `reactionGlyph` looks up only its own keys. Before that, such
a reaction found `Object`'s own property, threw, and blanked votes,
reactions and replies on the round for everyone. Found in the 2026-10-24
security check and reproduced in Chrome first.

## Season page features

- The page is the title, then straight into Standings: no summary line or
  stat cards (the line under the title only appears while loading, on an
  error, or for a season with no rounds yet). Podium places are gold,
  silver and bronze everywhere a 1st/2nd/3rd shows (the Standings bar, the
  Standings list, a round's place badges); ties share the colour. Text on
  them measures 9.4:1, 11.3:1 and 6.5:1 contrast.
- **Standings** and **Results by round** open the page, in that order,
  both collapsed by default into a full-width bar with a summary and a Show
  all button. Standings' bar shows the player count and everyone placed
  3rd or better with their points (ties share a place, so that can be more
  than three people; past four it shows three and "+N more"). Open it for
  the full clickable list. While players are picked, the bar also shows a
  "Filtered to" row, open or closed: tap a name to drop it, or Clear all.
  Standings is a bar plus a real toggle button rather than a `<details>`,
  because its bar holds buttons, and a button inside a `<summary>` would
  also fold the section (and reads badly in screen readers).

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
4. Translate any new comment or note that isn't in English into
   `data/translations.json` (see Translations below).
5. `python scripts/publish.py`. That builds and uploads, and the new data
   is live for members straight away; there's nothing to commit for data.
6. Only if the build created or changed a `site/seasonN.html` page (a new
   season), commit and push that page so GitHub Pages serves it.

A season with a `competitors.csv` and nothing else builds fine and renders
empty states throughout, which is how Season 3 looked before its first
round was exported.

A season with exactly one round renders too, minus whatever needs more
history: the trend chart stays hidden until there are two rounds (with one,
every line is a single dot and the chart is a column of dots over an empty
plot). A pair of players gets one chance per round they both play, so the
taste matrix (and Biggest fan, Coldest shoulder) stays empty until four
rounds, and Silent treatment and Most talked at until five; someone who
missed a round is a round later.

## Dark mode

Dark mode is a choice, and light is the default whatever the device is set
to (the user's call, 2026-10-24; it first shipped following the device
setting). The **Dark mode** switch in the account menu (`setDark` in
`account.js`) sets `<html data-theme="dark">` and stores `pfml.theme` in
the browser. A line at the top of every page's `<head>`, before any
stylesheet, puts it back before the page paints, so a dark page never
flashes light, and the features and privacy pages follow the same choice.
It's per browser, like the What's new badge. Dark mode redefines the colour
tokens under `:root[data-theme="dark"]` at the end of `style.css`; nothing
else in the stylesheet changes. A few new
tokens name what used to be hard-coded:
- **`--magenta-text`** is purple as text. In light mode it equals `--magenta`;
  in dark it's a lighter purple, because the brand purple reads at only 2.9:1
  on the dark page. `--magenta` stays the fill behind white text, which is
  6.5:1 in both modes.
- **`--inverse` and `--on-inverse`** are surfaces that stay dark on purpose:
  the Home banner, table header rows and the Daily Double badge.
- **`--on-metal`** is the text on gold, silver and bronze place badges, which
  is dark in both modes.
- **`--topbar`, `--glass` and `--edge`** replace the see-through light fills
  and dashed borders.

In light mode every token equals what the rules used before, and a test
holds that, so light mode looks exactly as it did.

Contrast was measured on 2026-10-24 in a browser, for every visible piece of
text on Home, a season, All-Time, a round, a profile, Submit (with a pick,
the round warning and the gauge), the repeat checker,
features and privacy, in both modes. Body text is 15.8:1, muted 7.4, links
9.4, purple text 5.8. The only items under 4.5:1 are the avatar initials
(white on each player's own colour, about 3:1). They're the same in light
mode, and were left as they are. The first pass had found the place badges
(light text on gold, 1.4 to 2.4) and the Daily Double badge on the
features page (1.02), which led to `--on-metal`.

Video frames are black. The gauge's
verdict colours and the red and green round-check boxes have dark versions.
`features.html` carries the same dark tokens, and a test compares them.

## Add to Home Screen

`site/manifest.webmanifest` lets a phone put PFML on its home screen and
open it full screen, like an app (`display: standalone`), with the
site's icon. Every members-only page links it, plus an
`apple-touch-icon`. features and privacy stay standalone and don't. The
file isn't named `.json`, so the deploy's guard against league data doesn't
catch it.

### Splash screen

Opening the installed app shows a short splash: design B, chosen
2026-10-25 from four. The record turns on the dark (`#16111A`), with PFML
in lavender underneath.

- **When:** only when PFML runs from the home screen, checked by
  `display-mode: standalone` (Android) or `navigator.standalone` (iPhone),
  and once per opening (`pfml.splashSeen` in sessionStorage, which an iPhone
  or Android clears when the app is closed). A browser tab never shows it.
  It's on Home only, the page the app opens on (`start_url`).
- **How:** a line in `index.html`'s `<head>` sets `html.app-splash` before
  anything paints and turns the status bar (`theme-color`) the same dark. The
  `#splash` block is the first thing in the body; the gate rule lets it show
  while everything else waits for sign-in, since it holds only the logo.
- **Lifting it:** `account.js` lifts it once sign-in is done, but not before
  0.6s from the page's start so it never just flickers, and by 2s whatever
  happens, since a signed-out visitor's sign-in card is under it. It fades
  for 0.3s and gives the status bar its purple back.
  Measured in a browser against a stand-in, with the "installed" check
  forced in a scratch copy:

  | Sign-in took | Splash faded at |
  | --- | --- |
  | 1.2s | when sign-in finished (1.85s into the page) |
  | instantly | 0.61s, the minimum |
  | never | 2.0s, the cap |
  | a second visit | never shown |
- **Android** draws its own splash from the manifest before the page loads
  (the icon on `background_color`), so `background_color` is the same dark
  and the two run together. An Android phone that installed PFML earlier
  picks up the new colour when Chrome next refreshes the app, which can
  take a day. iPhone has no splash of its own here.
- **Reduced motion:** the same screen, without the animation.

**The icon** is a dark record on the purple tile: three of its grooves
catch lavender light, and the label is purple with a white P. It was chosen
on 2026-10-24 from three rounds of options ("g3"), replacing a plain white P.
`scripts/make_icons.py` is its one source. It holds the shapes, writes the
browser-tab icon (an inline SVG in each page's `<link rel="icon">`), and
draws the PNGs from the same shapes, stdlib only, because iOS takes no SVG
icon. There's a 180 pixel PNG for iOS, 192 and 512 pixel ones for Android,
and a 512 "maskable" one that the launcher crops to its own shape. Change
the script, run it, then run `scripts/build.py` so the season pages pick up
the tab icon from the template. Tests check that every page carries exactly
the script's SVG and that the committed PNG is what it draws. A phone that
added PFML to its home screen before a change keeps the old icon until it's
removed and added again.

**Getting people to add it.** On phones, a **Get the app** button sits in
the top bar (`account.js`) until it's been tapped once, and **Add to home
screen** stays in the initials menu. Neither shows once the site is running
from the home screen (`display-mode: standalone`, or `navigator.standalone`
on iOS). What the tap does depends on the device:
- **Android Chrome** offers its own install prompt (`beforeinstallprompt`,
  caught as soon as `account.js` loads, since it fires once and early), so
  one tap installs.
- **iOS** has no such prompt, so a small dialog shows the steps: Share, then
  Add to Home Screen.
- **Apps' built-in browsers** (Instagram, Messenger) can't add a site to the
  home screen at all, so the dialog says to open pfml.fun in Safari or
  Chrome. Their user agents also say iPhone or Android, so they're checked
  first.
- **Desktop** gets the menu item only, with browser-install steps.

Measured 2026-10-24 in a browser: the button fits on the top row beside
the inbox and initials at 375px and 320px. `.acct-item` needed an explicit
`[hidden] { display: none }`, or the menu item would have shown inside the
installed app too (the emoji search lesson, in CLAUDE.md).

**Unverified on an iPhone:** a home-screen web app on iOS keeps its own
storage, separate from Safari, so members sign in once inside it. Google
sign-in in that mode has been unreliable on some iOS versions. If it fails,
change `display` to `browser`: the icon then opens normal Safari, already
signed in, without the full-screen look.

## Previewing locally

```bash
python scripts/build.py
python scripts/serve.py
```

then open `http://localhost:8000` and sign in as usual (localhost is on the
sign-in allowlist, see Members only). The local pages still read the data
from Supabase, not from your local `site/data/`, so a data change shows
up locally only after `publish.py`. Opening `index.html` from the
filesystem will not work. To check page code without signing in, see
CLAUDE.md, Checking page code in a browser.

## The "live" season on the home page

The home page marks whichever season is last by number as the current one.
If it has at least one round, its card shows a LIVE badge, the latest
round marked Complete, "Round N+1 underway", and a start date.

**Music League's export only contains finished rounds.** A round in song
submission or voting isn't in it at all: no round row, no submissions, no
votes. Measured on 2026-09-21 against `export (3).zip`, which was taken
while Season 2's last round was being played. That round was missing
entirely, and all 19 rounds the export did hold had exactly the votes of
the final export. So:

- **Started** is the `Created` timestamp of that season's first round.
- **Round N · Complete** is the latest round in the export. It's always
  finished.
- **Round N+1 underway** is inferred: the season is the current one, so the
  next round is assumed to be in play. Whether it's in song submission or
  voting isn't in the export, so the card doesn't say. And the export
  doesn't say how many rounds a season has, so after a season's final
  round the card would still say the next one is underway, until a newer
  season is added.
- This used to show a "Voting phase" guessed from whether a round had votes.
  Every round in an export has votes, so it always said Voting, even for
  finished seasons.

A season with zero rounds in its CSVs (a freshly created `data/seasonN/`
with only `competitors.csv`) shows "not started yet" instead, no LIVE badge,
and no round line.

## From the vault

A Home section between the season cards and the playlists. It shows one
past round winner at random on each visit: its round (linked), track,
artist and points, who sent it (linked to their profile), their note, and the
comment from whoever gave it the most points (the longest, on a tie), with
its English if it was translated. It also has a Play on Spotify link. The
data is `vault.json` (`build_vault`), every round's winner, with a tie for
first listing each, about 40 KB. Without the file the section stays hidden.

## Playlists on the home page

`site/data/playlists.json` is the one file in `site/data/` that `build.py`
never touches, it's yours to edit directly. It holds the league-wide and
per-season playlist links shown on the home page. Each entry looks like:

```json
{ "label": "PFML - S1 - All Submissions", "url": null }
```

Each entry is a tile on the home page (league-wide first, then seasons
newest first), its name with the repeated "PFML - S1 - " prefix dropped.
`url: null` renders as a dashed "Coming soon" tile with no link. Fill in a real
`https://open.spotify.com/playlist/...` URL and it becomes a live link the
next time you run `scripts/publish.py`. The file is git-ignored like the
rest of `site/data/`, and publish uploads it with the other data. Adding a
Season 4 group here is manual, since these are curated meta-playlists you
build yourself, not something derivable from the CSV export the way round
playlists are.

**Track count and running time.** Each tile shows its playlist's size
("319 tracks · about 21 hr"; stacked on a phone). `publish.py` looks them
up after the build (`refresh_playlist_stats()`) and writes
`site/data/playlist_stats.json`, keyed by playlist id; the page shows
"Open in Spotify" instead for any playlist missing from it. There's no
key, and no documented API: measured 2026-09-22, the public playlist page
carries the full count in `<meta name="music:song_count">`, and the embed
page (`/embed/playlist/<id>`) lists each track's duration in its
`__NEXT_DATA__` JSON, but only the first 100 tracks, whatever `?offset=`
says. So a playlist of up to 100 tracks gets its exact time; a longer one
gets the first 100's average times the count, rounded to the hour and
shown as "about". Exact times for those would need Spotify's Web API and a
developer key. A failed lookup keeps the last good numbers, and
`tests/test_live_spotify.py` checks both pages still carry what's parsed.
A playlist's numbers change only when you next publish.

## Player focus and comparison

Open Standings on any season page and click a name to filter everything below
(top tracks, rounds, taste matrix, voters, artists) to just that person, and
a Player Focus panel appears with stats scoped to them: best and weakest
submission, most divisive submission, biggest fan, hardest to win over,
favorite to vote for, voting style.

Click a second name to compare instead of filter: the panel switches to a
side-by-side standings comparison, a head-to-head tally (whoever placed
best in each round both submitted to), and, for exactly two people, the
points a round each gives the other's songs. Select a third, fourth, etc. and the
comparison table and head-to-head tally extend to the whole group; the
two-way mutual taste tiles only make sense for a pair, so they drop out
once a third person joins.

Everything here is computed client-side in `app.js` from data already in
`seasonN.json`, no extra build step and no new fields needed beyond what
`build.py` already produces. The "season in numbers" block hides itself
while a filter is active (it's a season-wide summary, not a per-player one,
so it stops making sense to show it between player-specific panels), and
its jump-nav link disappears along with it.

## All-Time page (career.html)

Titled All-Time League Stats, and shown as All-Time in the top bar. Both of its tables (standings and
comments), and a season page's Voting and Comments tables, keep every
column on a phone and scroll sideways inside their box (`.table-wide`), with the Player column pinned (`position: sticky`,
opaque) and a "swipe sideways" line shown on phones only. The one phone rule
still trimming columns is for the Taste section's short lists, and is
scoped away from these tables: one written for the
season Voting table used to hide every `.vrow`'s 4th cell, which here was
Season 3 (and "Won" on a profile's seasons).

`career.json`, built once per `build.py` run from all seasons' standings,
joins players across seasons by competitor id. This relies on Music
League reusing the same id for the same person across separate CSV
exports, which was checked against the real data (13 people who played
all 3 seasons, zero id/name mismatches) rather than assumed. A season
with zero rounds contributes nothing, since nobody has a standings entry
in it yet. If a name ever looks wrong on the All-Time page for someone who
changed their Music League display name between seasons, that's the
join taking the first name it saw for that id; `build_career()` in
`build.py` is where to change that if it comes up.

**Comment awards** (`quoteAwards` in `career.json`, `quote_awards()` in
`build.py`): single all-time comments picked from the text alone, shown as
quote cards with the longest comment: shortest review (fewest words, then
the biggest vote, then fewest letters), loudest (most ALL-CAPS words),
most excited (most `!`), most questions (most `?`), most emoji (a skin
tone isn't counted as a second emoji) and most words for zero points. Ties
go to the shorter comment, then the comment id, so a re-build picks the
same one. A count award needs at least 3 to appear. Long quotes start
clipped with a Read all toggle; the page clips before it measures, since
an unclipped quote never looks too tall (the first version had it the other
way round and clipped nothing).

`career.html` also carries an all-time Comments section: the same
per-player table aggregated across every season played (sortable by any
column, like the standings: `renderCareerCommentTable`), plus career
superlatives (most talkative, most terse, wordiest, quietest, biggest
silent treatment, most SHOUTING, widest vocabulary, most notes on their
own picks: eight, so they fill even rows of two or four; most all-talk
was dropped here, though season pages keep it) and the longest comment anyone has ever written, with the
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

The all-time standings table is sortable by clicking any column header;
click again to flip the direction. Players under 10 rounds have no score
or score parts (`careerFieldValue` returns null), so they sort to the
bottom of those columns in either direction, rather than sorting as a
zero.

### Career Score

Default sort. Chosen by the league on 2026-09-22 after comparing options
against the real data:

```
Score = Avg season + Round Podium Pts + Season Podium Pts
  Avg season      = 20 x points per round played
  Round Podium Pts  = 3 per 1st, 2 per 2nd, 1 per 3rd place in a round
  Season Podium Pts  = 6 / 4 / 2 for finishing a finished season 1st / 2nd / 3rd
Scored only after 10 rounds played.
```

Why each piece:

- **An average, not a total.** The old score (total points + 10 per round
  won + 5 per podium) punished anyone who missed a season. "Rounds" is
  tracks submitted, one per round played; points include any Daily Double
  bonus, as the season totals do. The x20 makes it read as a typical
  20-round season's worth.
- **Per round, not per season.** Dividing by seasons played counted Season
  3, one round in, as a whole season, so sitting it out *raised* your score
  (measured: a Season-1-only player jumped from 15th to 1st).
- **10-round minimum.** One round of 23 points would otherwise average 460
  and top the table. Unscored players are listed last with "needs 10", and
  have no score parts to sort by, so they can't top "Avg season" either.
- **A season's podium counts once a newer season exists.** The export never
  says a season is over (CLAUDE.md), and the newest season may be a round
  in. Seasons 1 and 2 count now; Season 3 will when Season 4 starts.
- **Ties share places**, in rounds and in seasons, and both get the bonus.
- **The bonuses are deliberately small** at these weights: round finishes
  add 3-27 and season podiums 0-6 on the real data, under 10% of anyone's
  score, so they mostly break near-ties. Considered and not taken: a higher
  minimum (30 rounds kept a one-season player out of the top 3) and
  shrinking averages toward the league mean (didn't move the one-season
  player, and lifted short weak careers).

The table's columns are the pieces, so each row adds up: Score, Avg
season, Round Podium Pts (with the 1st/2nd/3rd counts), Season Podium Pts
(with which seasons), Rounds. `PER_ROUND_SCALE`, `ROUND_BONUS`,
`SEASON_BONUS` and `MIN_SCORED_ROUNDS` in `build.py` are the knobs; the
note above the table and the profile read them from `careerScoreFormula`
in `career.json`, so they follow any change. A profile's Career Score
ranks among scored players only, and the profile shows the same sum under
its tiles (Score = Avg season + Round Podium Pts + Season Podium Pts, with each
part's working).

## The top bar, profiles and the inbox

**Top bar.** Home, one season button, then All-Time (the Career page,
`career.html`, titled All-Time League Stats). The season button names the
season being viewed, or the one in progress on any other page, and opens
a list of every season, newest first (`seasonPicker` in `app.js`). All-Time
also has a card on the Home page, next to the season cards.

**Account menu.** `account.js` adds two buttons to the right of the top bar
on every members-only page once `auth.js` lets a member in: the inbox, and
the member's initials in a coloured circle. The initials open a menu with
My profile and Sign out. At phone widths the corner stays on the wordmark's
row and the season tabs take the row below.

`account.js` is also the one home of three helpers the other pages share,
so a person, a reaction and a time look the same everywhere: `PFML.avatar`
(the initials circle, its colour fixed per player id), `PFML.reactionGlyph`
(the 6 stored names to their emoji; see Reactions) and `PFML.when` ("3h ago", "2d
ago", then a date after a week). Since then it has also taken
`PFML.translationHtml` (the English under a comment in another language)
and `PFML.closes` (a deadline as "Sun, Oct 25, 7:00 PM" and "in 2 days",
for the Home banner and the Submit page). They used to be copied into `rounds.js`,
where the time had drifted to a date after one day. Every members-only page
loads `auth.js`, then `account.js`, then its page scripts, and a test
checks that order, since the page scripts use these without checking.

**Inbox.** Reactions and replies other members left on the signed-in
member's own vote comments, newest first, 40 at most. A comment id ends
`|<voter id>`, so one suffix match per table (`api.inbox` in `auth.js`)
finds every comment they wrote, in every round; their own reactions are
left out. Round and track names come from `lookup.json` (about 45KB,
fetched the first time the inbox opens) rather than the ~1MB season files.
Each item links to `round?s=...&r=...&c=<comment id>` (plus
`&thread=1` for a reply), which scrolls to that comment, marks it briefly
and opens its replies.

"New" means created after `members.inbox_seen_at`, stored in Supabase so
it's the same on a phone and a laptop. Opening the inbox calls
`mark_inbox_seen()`, a security-definer function that sets it on the
caller's own row only: `members` deliberately has no UPDATE policy, since
a member who could update their own row could make themselves admin. The
column comes from `supabase/migrations/2026-09-23_inbox_seen.sql`. It's read
by its own query, never by the sign-in lookup, so a database without it
loses only the count; signing in and the list still work. The count
refreshes on page load, and when the tab comes back after a minute away.

**Profiles.** `profile?p=<competitor id>`, the signed-in member's own
without `?p`. Six Career tiles (Career Score, ranked with ties; total
points; rounds won; top-3 rate, the share of their tracks that finished in
a round's top three; tracks submitted; points given) sit two rows of three,
or three rows of two at phone widths (`.pf-tiles`). Totals and comment
stats come from `career.json`; each season's finish, the five best tracks (newest first
on equal points), the three biggest fans (most points given to this
player) and favourites (most points this player gave), all summed over
every season, come from `profiles.json` (`build_profiles` in `build.py`).
A third list, **Votes most like them** (`tasteTwins`, `taste_twins` in
`build.py`), names the three players whose voting is closest. In each round
both voted in, take each one's points over the songs neither of them sent,
less their own average for that round, which shows the songs they backed
more than usual. The match is the correlation of those, pooled over every
shared round, discounted for few rounds (× rounds / (rounds + 10)), with at
least 5 rounds and only a positive match counting. Measured on the real
league 2026-10-24: the plain cosine of points made one player who spreads
small points widely everyone's twin, and centring each round removed that.
It also paired the two players who share a surname, over 46 rounds, so the
measure tracks something real. The correlations are modest (the best is
about 0.3), so the page shows the order and the rounds shared, not a
percentage. `.pf-people` has `min-width: 0`, or a long name in the third
list pushed the page 46px wider than a phone.
The count of reactions their comments have had is live from Supabase,
leaving out any they left on their own. A dropdown switches player. Names link to profiles almost everywhere they
appear, styled exactly like the text they replace (`.plink`):
`personLink` in `rounds.js` on round pages, `who()` in `app.js` on season,
All-Time and profile pages. Most season and career data carries names
only, so `who()` resolves them through ids gathered from the page's own
data (`knowPeople`); names were checked to be unique across all seasons
(23 names, none shared), and an unknown name stays plain text. Not linked
on purpose: Standings rows and the collapsed Standings bar (both are tap
targets already; the focus panel's title links instead), buttons (filter
and focus chips, trend legend) and cards that are links themselves. If `profiles.json` hasn't
been published yet, the page shows what `career.json` has and hides the
rest.

## Repeat checker (/repeats)

Has an artist, song or album been submitted before? Members type into one
box and the page answers as they type: "Yes: 3 past submissions match", in
groups for Artist, Song and Album, newest first. Each match shows the
round (a link to its round page), who submitted it, and its place. A
Spotify track link checks for that exact recording, other versions of
the song, and more by the same artist. A YouTube link (youtube.com,
music.youtube.com, youtu.be, shorts) is looked up through YouTube's oEmbed
instead of searched as words: the page names the video and shows its
gauge. An "Artist - Topic" channel counts as the artist (measured
2026-10-19: oEmbed gives "Lucinda Williams - Topic"). The search sits in the address
(`/repeats?q=steely%20dan`), so it can be shared. It's reached from the
initials menu and the Submit page.

**Estimated League Sentiment.** A gauge, green to red, for how much the
league will care about a repeat. It's shown for a picked track: on the
repeat checker, from a list of Spotify matches under the box ("How will
the league feel about it?"), and on the Submit page, for a search result
or any pasted link. A pasted link is looked up in the catalog (a Spotify
track submitted before) or, failing that, in its service's own oEmbed:
YouTube and SoundCloud give the title and channel, Spotify the title only.
All three answer browsers on pfml.fun (measured 2026-10-19). It shows a
verdict ("Barely a blip" through "The league will care", and "Exact
repeat" with an extra warning) and the reasons, each with the earlier
submission. It never shows a number.

The kinds of repeat it weighs, each by this season or an earlier one:
- the exact recording;
- the same song by the same artist in another version;
- from YouTube or SoundCloud, the same song by the same artist on another
  service. It can't be confirmed to be the identical recording, so it
  warns as high as another version;
- a cover;
- a multi-word title matching, with the artist unclear;
- a different artist's song with the same one-word title (maybe not the
  same song);
- the same artist and album;
- an artist already submitted twice this season, or in the last round;
- the same artist;
- an artist who was a featured guest.

**YouTube titles can't be split reliably** (measured 2026-10-19). Anna
Ash's own upload of a Season 1 track is titled "Righteously - Anna Ash",
song first. Splitting it at the dash made "Righteously" the artist, and
the gauge said Fresh. So a YouTube or SoundCloud pick, or a pasted
link's oEmbed, goes in as free text: a past track counts when its title
and one of its artists both appear in it, in any order. A one-word
title on its own is too common to count. On a tie the gauge says
"another service", not "another version". Checked against the real
uploads: the official one, a fan upload, the karaoke version and
pasted links all warn high; Lucinda Williams' different "Righteously"
only notes the shared one-word title.

The verdict follows the strongest. **The weights are the user's (decided
2026-10-19) and are kept off the site and out of these docs on purpose.**
They live only in `site/sentiment.js`, which is public in this repo like
all page code. Comparisons use `catalog.json` plus `index.json`'s current
season. Names are matched as runs of neighbouring pieces, because the
export (and the search's "A, B" artist line) can split a name at a comma.
The album rule needs the search function's `album` field, added
2026-10-19, which ships only when the function is redeployed. Every rule
was checked in a browser against the real catalog.

**Data:** `catalog.json`, written by `build.py` (`build_catalog`) with the
rest and uploaded by `publish.py`. It holds every track from every round,
with title, artists, album, round, submitter, place, Spotify id and art:
733 tracks from 45 rounds, about 200 KB (58 KB compressed) on 2026-10-19.
It's searched on the device, so the ~1MB season files are never fetched.
It only covers **finished rounds**, since Music League's export leaves a
round out until it's over; the page's footer says so.

**Matching:** every word typed has to start a word of the artist, song or
album, so "pick" finds Dick's Picks and "feelin happy" finds Feelin' Happy.
Accents and "&" don't matter ("lubke" finds Lübke). A song is compared
without its version labels (" - 2011 Remaster", "(Live)"), so any version
counts as the song. No fuzzy spelling: "birelli" doesn't find Biréli.

**Gotcha, measured 2026-10-19:** the export separates a track's artists
with commas, so "Earth, Wind & Fire" arrives as two artists, "Earth" and
"Wind & Fire", and its name found nothing. The checker now also searches
the whole artist line. The same split affects anything else that counts
artists, such as Repeat artists on season pages, and isn't fixed there.

## Submissions on the site (/submit)

From Season 3 Round 7 the league can submit its real tracks on pfml.fun:
Spotify, YouTube or SoundCloud. Voting stays in Music League, as usual;
nobody is asked to link a site submission to their Music League entry
(decided 2026-10-19). Voting on the site is built but switched off (Voting
on the site, below). Stage 1 collects the tracks; stage 2 builds a Spotify
and a YouTube playlist in one shuffled order; stage 3 adds a player on the
page that plays the round through, across services (both below). The plan and its reasons are in the 2026-10-18
CHANGELOG entry.

**How a round runs.** The admin opens a round on the Submit page (season,
name, prompt, closing time) and can edit it or close it early there. A
banner on the Home page and a Submit a track link in the initials menu
lead to it. A member pastes a link, checks it in the service's own player,
and submits. Each submission gets a **tag** (a letter and a digit, like
Q7) that labels it on the list and in the playlists' gap notes. Members
were first meant to copy it into a Music League note so voters could
match the two, but that was dropped (2026-10-19), so the page no longer
mentions it. One track per member per round, and the
same track can't go in twice. At the deadline (or when the admin closes
it) the page shows every track, playable in place, in the round's one
shuffle; once the playlists are built, with titles and two Play buttons,
in the same order.

**The order** (the user's calls, 2026-10-25). From the moment a round
closes, everyone sees the same shuffle, and the playlists keep it:

- **How it's made:** each track's place is an FNV-1a hash of
  `<round id>|<platform>|<track>`, worked out the same way by the page
  (`PFML.roundOrder` in `account.js`) and the playlist script
  (`round_order` in `round_playlists.py`).
- **What it isn't:** nothing about who sent a track, or when, goes in, so
  the order can't hint at either. Before this, the page listed tracks by
  tag until the playlists were built, and the script then shuffled afresh,
  so the order changed under people.
- **Kept:** the order is saved as `position` when the playlists are built,
  and it's the same order.
- **Checked twice:** a test pins the hash's values in Python and the page's
  code, and the same values were checked in a browser.

**Shuffle** reorders the list for the reader alone, never saved, and the
player follows it top to bottom, numbered in play order. A track that's
playing moves to the top and keeps playing, so everything below is still
to come. **Original order** puts back the round's shuffle. The Spotify and
YouTube playlists always keep the round's order.

**Anonymous, even to the admin.** `site_submissions` holds the round, tag,
platform and track, with no user and no time. Who sent which is in
`site_submission_owners`, which has row level security on and no policies,
so nothing signed in can read it. Every write goes through four security
definer functions (`submit_track`, `my_submission`, `withdraw_submission`,
`site_submission_count`). Those that touch owners match on `auth.uid()`,
so a member only ever learns which track is their own. The one exception
is `site_round_submitters`, which says *who* has a track in, never which
(Who's in, below). Nobody reads submissions before the round closes, the
admin included; after, members read them all. An open round also tells
members what kind of repeat a pick would be (Repeats in this round,
below). The secret key in `.env` bypasses all of this, so a
deliberate lookup in Supabase could still join the two tables: agreed as
anonymous enough (2026-10-18).

**Links.** `submit.js` reads a pasted link into what the database stores:
a Spotify track id, a YouTube video id, or `user/track` on SoundCloud.
It takes open.spotify.com (with or without `intl-xx`), `spotify:track:`,
youtube.com (`watch`, `shorts`, `live`, `embed`), music.youtube.com,
youtu.be and soundcloud.com, with any tracking query on the end. It turns
away albums, playlists, channels, private SoundCloud links and the short
share links (`spotify.link`, `on.soundcloud.com`), which can't be read
without following them, with a message saying what to paste instead.
`submit_track` checks the same shapes again, and so does the table.
YouTube previews use `youtube-nocookie.com`.

**SoundCloud** is accepted; a SoundCloud track only makes the playlists if
it also has a copy on Spotify or YouTube, and the page says so. SoundCloud's
oEmbed gives a title and artist but no length, so a SoundCloud match is
never "sure" on its own: it always comes up for `--accept`.

**Measured:** song.link's public API, the obvious way to match a track
across services, answers `401 PUBLIC_API_ACCESS_DEPRECATED` (2026-10-18),
so stage 2 matches tracks itself.

**Database:** `supabase/migrations/2026-10-18_site_submissions.sql`, the
same blocks as `schema.sql`. Nothing here was run against Postgres before
it shipped (there's none on this machine); `tests/test_submissions.py`
pins the rules as text, and the page was checked in a browser against a
stand-in that follows them.

### The Home banner

While a round is open, the Home banner shows its name, "x/20 submitted"
(Who's in, below), when it closes ("Closes Sun, Oct 25, 7:00 PM · in 2
days", in the reader's own time zone), and whether the reader has a track
in: "✓ You're in", with the button reading "Change your track", or "You
haven't submitted yet". That last part asks only about the reader's own
submission (`my_submission`). The deadline wording is `PFML.closes` in
`account.js`, shared with the Submit page.

### Admin status

Below the round form, the admin sees a League status panel. It shows when
the data was last published (the upload time of `index.json` in the bucket,
which members can list) and the latest finished round in it. It also lists
the players taking part who haven't joined the site, each with "link made
Oct 23, not used yet" or "no link yet". The invites table has no policies, so that comes from
`admin_invite_status()`, admin only, which returns who has an unused link
and when it was made, never the link itself; `scripts/invites.py --player
"Name"` prints it. Migration:
`supabase/migrations/2026-10-24_admin_invite_status.sql`.

### Who's in

The Submit page shows "**7/20** submitted", and a Who's in section lists
who has submitted and who's pending, as avatar chips linking to profiles.
The Home banner shows the same count. Asked for 2026-10-23, along with the
user's calls:
- **Names are shown, knowing the trade-off.** A member could watch someone
  appear as submitted, then use the repeat warning to test artists and
  guess roughly what they sent. `site_round_submitters()` returns player ids
  only, in id order, so it doesn't even reveal the order people sent them.
- **The 20 are the players taking part:** `activePlayers` in `index.json`,
  everyone with a track in the current season's latest finished round
  (`build.active_players`). That was exactly the 20 the user named
  (Round 6's players; Clavenna Vision sat it out). Anyone who submits from
  outside the list still shows, as "(and 1 more)". A new export updates the
  list; `index.json` needs a publish for a change to reach the site.
- **Players who haven't joined the site are marked "not joined yet"**,
  since they can't submit there. On 2026-10-23 that was Asa, Dustin James,
  Jacob Diskin and Scott Menke.
- **Everyone submits on the site from now on**, as well as in Music League,
  so pending really means pending. Round 7's prompt only asked YouTube
  picks to come here; the user is telling the league.

The list has its own section below the picker; inside the round card,
twenty names pushed the form off a phone screen. The page falls back to the
plain track count when `index.json` has no `activePlayers` or the database
doesn't have the function yet. Migration:
`supabase/migrations/2026-10-23_round_submitters.sql`.

### Repeats in this round

The Submit page warns, before you send, when a pick repeats one already in
the open round (asked for 2026-10-23). The warning names the kind of
repeat: the exact track (which `submit_track` refuses anyway), the same
song by the same artist, the same song title by another artist, a song with
the same title where the artist isn't clear or the title is one word, or
the same artist with another song. It never says which track or whose.
The box sits above the Estimated League Sentiment gauge, and the gauge
counts what it found too (the user's call, 2026-10-23), so it can't read
"Fresh" under an "Already in this round" warning. Each kind counts as the
matching repeat this season, at the weights already set: the exact track
as exact, same song and artist as version, same title by another artist as
cover, a title alone as title-only, the same artist as artist. The reason
line says "(already in this round)", with no link, since the check never
says which track.

**How, without reading the round.** Tracks stay unread until the close, so
the page can't compare them. Each submission keeps a **fingerprint**
instead (`fp_song`, `fp_names`, `fp_text` on `site_submissions`): the song
title and the artist names, folded to plain lowercase words the way the
gauge folds them (`sentiment.js`), plus, for a YouTube or SoundCloud pick,
its title and channel as free text. `round_repeats()` compares a pick's
fingerprint with every other submission in the round, using `fp_kind()`,
and returns the kinds only. It leaves out the caller's own track. The page
saves the fingerprint with `describe_submission()` right after a submit.
A track sent before this existed, or from an out-of-date page, gets its
fingerprint on its owner's next visit (`my_submission_described()`).
`fp_for` records which track a fingerprint was made for, so one left over
after a swap is ignored rather than misread.

**Naming a video.** A video's title doesn't say which part is the artist
("Righteously - Anna Ash" is song first), and the channel often isn't the
artist at all (KEXP, BBC, Austin City Limits). So the page asks Spotify:
it searches the title, minus brackets and words like "live", "official"
and years, and keeps the first result whose title and one of whose artists
both appear in the video's title and channel. Measured 2026-10-23 on 22
real live-video titles: 20 named, nearly all on the first search; the two
misses ("Lake Street Dive Plays … On a Boston Sidewalk") fall back to the
free text. A channel never stands in for the artist, since two KEXP
sessions would otherwise count as the same artist. A Spotify link the
catalog doesn't know is found by searching its title for the very track,
because Spotify's oEmbed gives no artist.

**Limits.** Only tracks sent on this site are checked; picks sent only in
Music League aren't visible here (the export leaves out a round until it's
over). Asking about a pick tells a member whether that song or artist is
already in the round, so someone determined could probe for what's been
submitted, though never who sent it. That's what the feature is for.
`fp_ok()` takes plain lowercase words only, within the column limits.

**Postgres takes no regex count above 255.** The first version of the
migration wrote the limits as `{0,300}` and `{0,600}`. It ran clean on the
live project, because a check on an empty column is never evaluated, but
every `fp_ok()` call failed with "invalid repetition count(s)". The live
test found this on 2026-10-23, before any page used it. Lengths now go in
`char_length()`, and the regex only checks the characters.
`2026-10-23_round_repeats_fix.sql` repairs the live project, and a test
fails if any SQL file uses a count over 255.

**Database:** `supabase/migrations/2026-10-23_round_repeats.sql` (since
corrected) and then `2026-10-23_round_repeats_fix.sql`, the same lines as
`schema.sql`; no new table, so the 2026-10-30 grant change doesn't apply. `fp_kind()` is pure, so `tests/test_live_round_repeats.py` runs its
rules against the real database with the secret key once the migration is
in. It also checks that `round_repeats` and `describe_submission` refuse
anyone who isn't a member.

### Searching

The Submit page's box takes words as well as links. Three buttons pick the
service; Enter or Search looks the words up there and lists up to 10
results (artwork, title, artist, length); tapping one previews it like a
pasted link. A link pasted in the same box still works on any service.
Enter only ever searches; it never sends a track.

- **Spotify** search uses the Spotify app's own login (client credentials,
  no user): measured 2026-10-19, it answers, returns 10 results with
  64px artwork, and refuses 11.
- **YouTube** search uses an API key from a **second Google project**
  ("PFML search"), so its own 100-searches-a-day allowance can never eat
  the playlist builder's. Answers are kept for a week in `search_cache`,
  so a repeated search is free. When the day's allowance is used up, the
  page says so and links to YouTube's own search instead.
- **SoundCloud** has no search here yet: its button opens SoundCloud's
  search in a new tab, to copy a link back. In-page search needs a
  registered SoundCloud app, and whether SoundCloud still accepts new ones
  is unconfirmed (2026-10-19; the user is checking soundcloud.com/you/apps).

**`supabase/functions/search-tracks/index.ts`** does the searching (the
keys can't be in page code). It answers only signed-in members: it asks
the database `is_member()` with the caller's own sign-in, which also proves
the sign-in is genuine. It answers only pfml.fun (and the local preview).
It never stores who searched, because "searched Feelin' Happy" next to a
name could give a submitter away: `search_cache` holds the service, the
text and the day, and has no policies. It's plain `fetch`, with no
libraries.

**Deploying it is by hand** (Claude has no access to the Supabase
account). Changing the function means redeploying it:
1. Supabase dashboard, Edge Functions, Deploy a new function, Via Editor.
   Name it exactly `search-tracks`, paste `index.ts`, and Deploy.
2. In the function's settings, turn **Verify JWT off**. The function
   checks membership itself, and the gateway's own check can reject
   sign-ins made with the newer signing keys.
3. Edge Functions, Secrets: `SPOTIFY_CLIENT_ID` and
   `SPOTIFY_CLIENT_SECRET` (the same values as in `.env`), and
   `YOUTUBE_SEARCH_KEY`.
4. `YOUTUBE_SEARCH_KEY`: console.cloud.google.com, New project "PFML
   search", enable YouTube Data API v3, then Credentials, Create
   credentials, API key. Restrict the key to the YouTube Data API v3. No
   sign-in screen is needed.
5. Run `supabase/migrations/2026-10-19_search_cache.sql` in the SQL
   Editor. Without it, search still works, just with no cache.

### Stage 2: the round playlists

Once a round closes, `python scripts/round_playlists.py` builds it as a
Spotify playlist and an unlisted YouTube playlist, in one shuffled order,
so everyone can play the whole round in one tap in the app they use, with
the phone locked. It's local, like `publish.py` (the keys are in `.env`),
and it never reads who submitted what.

    python scripts/round_playlists.py --dry-run       # look everything up, write nothing
    python scripts/round_playlists.py                 # build the newest closed round
    python scripts/round_playlists.py --accept B4     # take a match it was unsure of
    python scripts/round_playlists.py --round <id>    # rebuild a round (same order, same playlists)

What it does: saves the round's one shuffle, the order its page has shown
since the close (later runs keep it; The order, above); looks
each track up on its own service; searches the other service for the same
recording and compares title, artist and length; fills both playlists in
order, skipping a track with no copy; and saves the order, titles, matches
and playlist ids, which the Submit page then shows.

**Matching never guesses.** A candidate is "sure" when the cleaned titles
agree, the artist matches, and the lengths are within 3 seconds; "unsure"
when the title is close and the length within 20 (a music video with an
intro, say). Sure matches go in; unsure ones are left out and printed with a
link, for `--accept TAG` or a hand-set match. Version words have to agree
on both sides (live, cover, remix, acoustic, demo, instrumental, session
and a few more), so a live take never stands in for the studio one.
Remaster, single, mono and edit labels don't count as a different version.
By hand: `data/playlist_overrides.json` (local, git-ignored, like
translations), `{"<round id>": {"Q7": {"spotify": "<link or id>", "youtube":
null}}}`, where null means "no copy, leave the gap".

**Measured or read, 2026-10-19:**
- **Spotify** changed its API in February 2026. Playlists are now created
  with `POST /me/playlists` and filled with `PUT /playlists/{id}/items`;
  the old `/users/{id}/playlists` and `/tracks` paths are gone. Search
  returns at most 10 results, and the batch track lookup is gone (one
  call per track). A new Development Mode app works only while its owner
  has Premium, and allows 5 users; the script is the only user. Read from
  Spotify's changelog and migration guide.
- **YouTube** search has its own allowance of 100 calls a day. Adding or
  removing a playlist item costs 50 of the 10,000 daily units, so a
  20-track round costs about 2,000. From Google's quota table.
- **Google sign-ins** from an app left in "Testing" expire after 7 days, so
  the app gets published (below).
- **SoundCloud's** oEmbed answers without any account; measured.
- **Matching on real tracks** (measured 2026-10-19, after the accounts
  were connected): 8 of 9 matched correctly, mostly to "Artist - Topic"
  uploads within a second. A live Grateful Dead take matched its live
  upload. PSY's music video (34s longer than the song) was rightly left
  out. A duo credit on Spotify has to match a channel named for either
  artist, which the first trial got wrong.
- **Not yet measured:** whether members who don't own it can open a
  Spotify playlist that isn't public by its link. Check on the first real
  round. If they can't, make it public in `Spotify.create_playlist`.

**Setting up the accounts (once).** These are your own accounts (decided
2026-10-19). Put the ids and secrets in `.env` yourself: never in chat,
never in a commit.

*Spotify:*
1. developer.spotify.com/dashboard, Create app. Name it "PFML playlists".
   Under Redirect URIs, add exactly `http://127.0.0.1:8888/callback`.
   Under APIs used, tick Web API. Save.
2. In the app's Settings, copy the Client ID and Client secret into
   `.env` as `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`.
3. Run `python scripts/connect_accounts.py spotify`, sign in, and Agree.
   It saves `SPOTIFY_REFRESH_TOKEN` in `.env`.

*YouTube (Google):*
1. console.cloud.google.com, New project, "PFML playlists".
2. APIs & Services, Library, "YouTube Data API v3", Enable.
3. Google Auth Platform (OAuth consent screen): External; app name "PFML
   playlists"; your email. Under Data access, add the scope
   `.../auth/youtube`. Under Audience, **Publish app** (In production), so
   the sign-in doesn't expire every 7 days. It stays unverified, which
   is fine for one user: Google shows a warning screen at sign-in.
4. Clients, Create client, type **Desktop app**. Copy the Client ID and
   secret into `.env` as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.
5. Run `python scripts/connect_accounts.py youtube`. At "Google hasn't
   verified this app" choose Advanced, then Go to PFML playlists, then
   Continue. It saves `YOUTUBE_REFRESH_TOKEN` in `.env`.

Then `PFML_LIVE=1 python -m unittest discover -s tests -p
test_live_playlists.py -v` checks the lookups work against the real
services; it only reads. If the script ever says a sign-in failed, run
`connect_accounts.py` for that service again.

**Database:** `supabase/migrations/2026-10-19_round_playlists.sql` adds
the columns (`position`, `title`, `artist`, `spotify_match`,
`youtube_match` on submissions; the two playlist ids and when they were
built on rounds). None says who or when anything was submitted, and a test
holds that.

### Stage 3: the round player

A closed round's Submit page has **Play the round**. It plays every track
in the list's order, top to bottom (the round's shuffle, or the reader's
own after Shuffle), each in its own
service's official player, moving on by itself across Spotify, YouTube and
SoundCloud. There are Previous, Pause and Next buttons, and tapping a
track in the list plays the round from there. Once the playlists step has
found copies, a picker plays YouTube (or Spotify) copies where there are
any: the way to hear full tracks without being signed in to Spotify in the
browser, which otherwise gives 30-second previews. The choice is kept in
that browser only.

`site/player.js` drives each service through its own API, loaded only
when someone presses Play: Spotify's iFrame API (EmbedController;
`playback_update` carries the position, length and which track it's
about), YouTube's IFrame API on the nocookie host (the ENDED state), and
SoundCloud's Widget API (FINISH). A service's player is kept from track to
track while the service stays the same, since a player that's already
playing is likeliest to be allowed to start the next. Only one plays at a
time. A track that can't play (removed, not embeddable) is noted and
skipped. If a track hasn't started 6 seconds after the last one ended (12
after a button press), a full-size **Tap to play next** button covers the
player, for browsers that won't start one without a tap; Spotify's docs
say Safari is one.

**For a screen that's on.** It stops when a phone locks; the playlists
are for that, and the page says so.

**Measured 2026-10-19, in Chromium with real embeds** (a 19-second YouTube
video, a Spotify track as its 30-second preview, a SoundCloud track):
- One real click started it, and each track moved on to the next by
  itself: YouTube ended at 0:20 and Spotify started, Spotify's preview
  ended and SoundCloud started.
- Pause/resume, previous, next, the YouTube-copies picker (it replays
  the current track from YouTube), jumping from the list, and the end of
  the round ("That's the whole round.") all worked.
- A video id that doesn't exist was reported and skipped.
- The tap button was checked by making YouTube refuse to start: it
  appeared and covered the player. A real autoplay block couldn't be
  produced here, since Chromium had already let the site play sound.
- Phone width (375px): fits, nothing scrolls sideways.
- **Not measured:** Safari on an iPhone, where a tap per track may be
  needed; the button is there for exactly that.

## Voting on the site (built, switched off)

The league means to run everything on pfml.fun eventually, with no
Music League app. Voting is the next piece. It was built on 2026-10-25
and is **off**: members see nothing of it. The user's calls that day:

- **It must never touch Round 7.** A round votes here only if it was
  *opened* that way (`site_rounds.votes_on_site`, default false). The
  `site_rounds_voting_fixed` trigger refuses to change it afterwards, either
  way, so Round 7 and every round before it vote in Music League for good.
- **Who submitted what is revealed when voting closes**, like Music League.
  Until then a round that votes here is as anonymous as any other, the
  admin included.
- **Season 3's rules, set per round**, measured from the exports
  2026-10-25. Every one of the 115 Season 3 ballots spent exactly 19
  points. No single vote went above 5 in any season. Negatives stopped
  after Season 1. Only players who submitted ever voted. So the defaults
  are 19 points, at most 5 on a track, all of them spent, no negatives,
  only submitters vote, and nobody votes for themselves. A comment can go
  on any track, your own included, with or without points; 0-point
  comments are common in the exports. **A submitter who doesn't vote
  scores 0.** That's the user's call: Music League let the 10 who skipped
  voting in Seasons 2 and 3 keep their points. The admin can change any of
  these when opening a round, and they freeze when submissions close.

**The switch.** `var SITE_VOTING = false;` in `account.js` (`PFML.siteVoting`).
Off, the admin's form has no voting fields. The Submit page shows no
ballot or results, and Home no voting banner, even for a round that votes
here. Such a round then looks like any closed one. Only the admin could
make one while it's off, outside the page. A test fails if the switch
flips. That's on purpose: switching it on changes what the site promises.

**How a round runs, once it's on.** The admin ticks "Vote on pfml.fun"
when opening a round and sets when voting closes (after submissions) and
the rules. When submissions close, the Submit page keeps the track list
and player, and under it each submitter gets a ballot:

- **The ballot:** − and + on every other track, a running "7 of 19 points
  left" bar that stays in view, and an optional comment on any track.
- **Saving:** Save works once every point is placed. They can change the
  ballot until voting closes.
- **Others:** anyone without a track sees "Only players with a track in this
  round vote". Everyone sees "8/12 voted" and who still hasn't: who, never
  how.
- **The banner:** Home's says "Voting is open", with the deadline, and
  whether the reader's ballot is in.
- **The admin:** can move the deadline or close voting early.
- **After voting closes:** the Results show every track's submitter and
  score, ranked, ties sharing a place. Tap a track for each voter's points
  and comment. A non-voter's track shows "Didn't vote, so it scores 0
  (voters gave it 15)".

**Database** (`supabase/migrations/2026-10-25_site_voting.sql`, the same
block in `schema.sql`):

- **The round's columns:** `site_rounds` gains `votes_on_site`,
  `voting_closes_at`, `voting_closed_at`, `point_budget`, `max_per_track`
  and `nonvoters_keep_points`. A constraint ties them together: a voting
  deadline exactly when it votes here, after submissions, and the cap no
  bigger than the budget.
- **`site_votes`:** one row per track a voter gave points or a comment to.
  RLS is on with no policies, and the API grants are revoked, so the
  functions are the only way in.
- **`site_round_phase()`:** submitting, voting, finished, or "closed" for a
  Music League round. `PFML.roundPhase` is the same in the page, and a
  test keeps them alike.
- **`cast_ballot()`:** checks the caller is a member with a track, that
  voting is open, and that every track is in the round once. Then the
  rules, through `ballot_problem()`, which is pure. Then it replaces the
  caller's ballot.
- **During voting:** `my_ballot()` is the caller's own;
  `site_round_voters()` gives player ids only.
- **Only once voting has closed:** `site_round_results()` (submitter,
  points, earned, voted) and `site_round_votes()` (every vote and comment,
  with who).

**Checked against the real database** (there's no Postgres here):

- **`tests/test_live_voting.py`:** runs `ballot_problem` with the secret
  key, and confirms a stranger can't call any of it. Read-only.
- **`supabase/checks/2026-10-25_site_voting_rehearsal.sql`:** the user
  runs it in the SQL Editor. It plays a whole round as three real members
  and ends by raising an error on purpose, which rolls everything back.
  "Rehearsal passed: 25 checks held" means every rule above held: Round 7
  refusing, submitting, eight bad ballots refused, good ones and a changed
  one, nothing showing before the close, and the non-voter's 0.
- **The pages:** checked in a browser against a stand-in that follows the
  same rules, with the switch on in that copy only. At 375 and 1280px,
  light and dark: the ballot, someone without a track, the results, the
  admin's fields and panel, and the Home banner. Then with the switch off,
  where all of it was gone.

**Switching it on** needs the migration run (and the rehearsal passed),
then, in one change:

- `SITE_VOTING = true` and the test that pins it.
- The privacy page and the Submit page's footer: "stored without your
  name" and "nobody can see who submitted which track" become "until
  voting closes" for a round that votes here.
- The footers on Home, All-Time, profiles and the season pages ("Results
  come from the league's Music League exports") and the round page's
  ("Built from Music League's CSV export"): results can come from pfml.fun
  too.
- The features page, with a What's new line.
- Telling the league.

**Not built yet:** no reminders to vote; the page is still titled "Submit
a track" during voting; and the site has no submitter note, so no Daily
Double request (Season 3 asks for it in the note) can be made in a round
voted here. Results reach the stats (Site rounds in the stats, below).

## Site rounds in the stats

A round voted on pfml.fun counts in the season pages and every stat,
exactly like a round from Music League's export (built 2026-10-25, ahead of
voting being switched on):

- **Getting it out of the database.** `site_rounds_export()`
  (`supabase/migrations/2026-10-25_site_rounds_export.sql`) returns every
  round voted here whose voting has closed, whole: tracks with their
  submitters, every vote and comment, and the players' names. It hands
  over nothing else, so who sent what can't leave the database before the
  close, whatever a script does. Only the secret key can call it.
- **Saving it.** `publish.py` calls it first, before anything else, and
  writes each season's rounds to `data/<season>/site_rounds.json`
  (local-only like the rest of `data/`; backed up with the exports). It
  makes the season folder if a season is played only on the site. A
  season whose file the database no longer backs keeps it, with a warning.
  A dry run fetches too when the keys are there.
- **Building it.** `build.site_season_rows()` turns the file into rows
  shaped like Music League's CSVs and `build_season` adds them to the
  export's, so standings, places, voter stats, comments, profiles, the
  vault and the repeat checker all count them with no special cases.
  With no file, the build is byte for byte what it was (measured on the
  real data, 2026-10-25).
- **Tracks off Spotify.** A site track is keyed `<platform>:track:<id>` in
  place of a Spotify URI (`build.site_uri`); `track_id` reads only
  `spotify:` keys, so a SoundCloud path is never taken for a Spotify id.
  Its `spotifyId` is its own for a Spotify pick, or the Spotify copy the
  playlists step found (album art, repeat checks), or none. A YouTube or
  SoundCloud pick also carries `link`, which follows it into highlights,
  comment cards, profiles, the vault and the catalog; every page links a
  track through `PFML.songUrl` (`account.js`), which goes to where it was
  submitted, then Spotify. Comment ids and `lookup.json` use the site key.
- **A submitter who didn't vote** (when the round says that costs them):
  the track scores 0, places on 0, and adds 0 to the standings; it keeps
  `forfeit.earned`, and the round page says "Didn't vote, so it scored 0
  (voters gave it 6)". The votes on it still show and still count in the
  voters' own stats.
- **Kingmaker** (who backed the winner) compares the build's own track
  keys, not Spotify ids: two site tracks with no Spotify copy would both
  have none and look like one track.
- **A track the playlists step never named** gets "YouTube track B3" and a
  warning in the build.

**Checked:** `tests/test_site_results.py` (a made-up season with a Music
League round and a site round), break-checked; and in a browser against a
build of that made-up season: the round page links each track to its own
service and explains the 0, the season standings count the round, and the
repeat checker links a SoundCloud pick to SoundCloud.

## Reminders

Reminders reach members on their phones (built and set up 2026-10-25; the
setup steps below were all done that day). Email is built too but dormant:
the user put it on hold, and it needs a Resend account and DNS records for
pfml.fun first. The user's calls that day:

| Reminder | Who | When |
| --- | --- | --- |
| New round open | everyone | within 5 minutes of the round opening |
| Playlist available | everyone | within 5 minutes of the playlists step |
| Voting at halfway, 5 hours, 2 hours, 1 hour left | only players with a track in the round who haven't voted | dormant until voting is on: only rounds voted on the site get them |
| Replies and reactions on your comments | the commenter | within 5 minutes, one summary a run (added with the bell, below) |

**The bell** (asked for 2026-10-25): a bell in the top bar, just left of
the inbox, where anyone sees it as soon as a page loads. It replaced the
Notifications item in the initials menu. Its icon has a slash while this
device has notifications off. It opens:

- **This device's switch:** turns notifications on or off for this phone or
  browser (below). On iPhone in Safari, and where they're blocked or
  unsupported, it says why instead, with Show me how on iPhone.
- **Tell me when:** a switch for each kind, the member's own and the same
  on every device they turn on: a new round opens, a round's playlist is
  ready, replies to your comments, reactions to your comments, and (once
  voting on the site is switched on, `PFML.siteVoting`) voting closes and
  you haven't voted. They're columns of `reminder_settings`, all on unless
  turned off; `my_notification_choices()` reads them and
  `set_notification_choice(kind, on)` sets one, refusing any name but those
  five. A switch moves at once and goes back if the save fails.
- **Send me a test**, while this device is on.

`reminders_claim` leaves out a kind the member turned off. The panel shares
the inbox's open and close rules (one pop-up at a time, Escape, a click
outside). **Gotcha, found in the browser:** opening the bell redraws its
icon, and with the answers already in hand that happened in a microtask
before the page's click-outside handler ran. The handler then saw a
detached target, decided the click was outside, and closed the panel at
once. It now checks `composedPath()`, the path as it was when the click
began, and the icon is only redrawn when it changes.

**Replies and reactions** (`inbox_claim()`, sender only): what the inbox
shows, as a notification. A comment's id ends with the commenter's player
id, so a reply or reaction on a comment id ending in a member's id is on
their comment; their own don't count.

- **One per member per run:** "Pat replied to your comment" with the reply,
  "Pat reacted 🔥 to your comment", or "New on your comments: 2 replies and
  1 reaction" with who was latest. A tap opens the inbox (`?inbox=1`, then
  taken out of the address).
- **Nothing twice, no flood:** `inbox_notified` keeps each member's mark;
  each run counts what's after it and moves it to the run's start, under a
  lock so two runs can't both count the same items. A member's first mark
  is when they first turned on a device, and nothing older than a day
  counts, so turning on doesn't bring a pile.
- **Only members with a device**, and each kind only if they want it.

**On the phone.** The bell's device switch turns them on for that phone or
browser:

- **Turning on:** it asks for permission, registers `sw.js`, subscribes
  with the public push key (`vapidPublicKey` in `config.js`), and saves
  where the push service reaches the device (`save_push_subscription`).
  Send me a test sends one to the member's own devices; Turn off removes
  it.
- **iPhone:** web notifications only work in the installed app (iOS
  16.4+), so in Safari the panel says to add PFML to the home screen
  first. If permission is blocked, it says where to allow it.
- **`sw.js`** only shows notifications: no caching, no fetch handler. A tap
  opens the page the reminder is about, and only ever on this site.
- **Hidden until set up:** the bell stays hidden while
  `vapidPublicKey` is empty. A test requires the privacy and features
  pages to cover notifications once it isn't.

**Sending** (`supabase/functions/send-reminders/index.ts`, one file, no
libraries, deployed from the dashboard with JWT verification off). A
`pg_cron` job (`supabase/setup/reminders_cron.sql`) calls it every five
minutes through `pg_net`, with a shared secret kept in Vault. It calls
`reminders_claim(channels)`:

- **Recording first:** the claim records each due reminder in
  `reminders_sent` before anything is sent, so two runs can't send one
  twice.
- **What's due:** a round opened in the last 6 hours (so one already open
  isn't announced late), playlists built in the last 12, and for a round in
  voting the latest of halfway, 5, 2 or 1 hour that has passed, never one
  from before voting opened. A late run sends one reminder, not a pile, and
  a short voting window never says "5 hours left" with 3 to go.
- **Gone devices:** a device the push service says is gone (404, 410) is
  forgotten.

**The function's other two callers:** a member's test (with their own
sign-in, so only their own devices), and email's signed unsubscribe link.
Everyone else gets 401.

**Push encryption** is WebCrypto alone: RFC 8291 (aes128gcm) and RFC 8292
(VAPID, ES256, signed for the push service's origin, 12 hours). The block
between `index.ts`'s webpush markers is plain JavaScript, so it was taken
out as it stands and run in a browser against RFC 8291's worked example
(Section 5, Appendix A), on 2026-10-25:

- the message body matched byte for byte;
- a fresh message decrypted back with the receiver's key;
- the VAPID signature verified with its public key.

The file has `// @ts-nocheck` because of that untyped block.

**Tables:** `push_subscriptions` (the device's endpoint and keys, per
member), `reminder_settings` (email and each kind on or off; no row means
all on), `reminders_sent` and `inbox_notified`. They're reached only
through the functions, with no policies and no grants. Members call
`save_push_subscription`, `remove_push_subscription`,
`my_push_subscriptions`, `set_email_reminders`, `my_notification_choices`
and `set_notification_choice`; only the secret key calls
`reminders_claim`, `inbox_claim`, `forget_push_endpoint` and
`email_reminders_off`.

**Email, when it's switched on:**

- **Secrets:** `RESEND_API_KEY` and `REMINDERS_FROM` are added to the
  function. Without them it never asks for email at all.
- **Each email:** carries a signed unsubscribe link and a
  `List-Unsubscribe` header.
- **Pages:** the menu gets an email switch (`set_email_reminders` is ready
  for it), and the privacy page says what's sent and to which address.

**Setup, in this order:** the code can't go live before the database and
the function exist. The daily security check calls every function in
`schema.sql` and every Edge Function as a stranger, so it would fail.

1. Run `supabase/migrations/2026-10-25_reminders.sql`.
2. Run `supabase/checks/2026-10-25_reminders_rehearsal.sql`. It should say
   "Rehearsal passed: 12 checks held".
3. Turn on `pg_cron` and `pg_net` (Database, Extensions).
4. Deploy `send-reminders` from the dashboard, with JWT verification off.
   Add its secrets: `REMINDERS_SECRET` and `VAPID_PRIVATE_JWK`, which
   Claude generates and puts on the clipboard, never in a file, message or
   log.
5. Run `supabase/setup/reminders_cron.sql`, with the secret filled in. Claude
   puts that copy on the clipboard.
6. Set `vapidPublicKey` in `config.js`, and update the privacy and features
   pages. Push, then turn notifications on and send a test from a phone.

**Done on 2026-10-25, measured at each step:**

1. **The rehearsal** said "12 checks held".
2. **Read-only checks:** a stranger was refused by all seven new functions,
   and a claim with no channel claimed nothing.
3. **The keys:** both secrets were made with OpenSSL and went to the
   clipboard one at a time, never shown. The scratch copy was deleted once
   they were in Supabase.
4. **The first deploy** answered 500 to a forged unsubscribe link while
   `REMINDERS_SECRET` wasn't set yet, because signing with an empty key
   throws. Fixed to refuse (401), with a test.
5. **After redeploying:** strangers got 401 on every path, and a call with
   the secret answered `{"claimed":0,"sent":0}`. So both secrets were read,
   and the claim reached the database with nobody subscribed yet.
6. **The timer** is `pg_cron` job 1, `pfml-reminders`.

If a secret is ever lost, make new ones. Replace both function secrets,
then the Vault secret:
`select vault.update_secret((select id from vault.secrets where name = 'reminders_secret'), '<new>');`.
A new push key also means a new `vapidPublicKey`, and every device has to
turn notifications on again.

**Checked:**

- **Tests:** `tests/test_reminders.py` (the rules as text), break-checked;
  `tests/test_live_reminders.py` against the live project.
- **In a browser:** the Notifications panel, with the browser's push
  objects faked inside the page:
  - turning on asks, registers `sw.js`, subscribes with the 65-byte key,
    then saves the device;
  - the test and Turn off work;
  - the iPhone and blocked messages show;
  - nothing shows without the key.
- **`sw.js`'s own code**, with `self`, `registration` and `clients` faked:
  it shows the message, opens or moves to the page, keeps a foreign link
  on pfml.fun, and copes with a message that isn't JSON.
- **Not possible here:** the browser pane allows no service workers at all
  (a one-line worker failed too), and it blocks notifications. So the real
  end-to-end check is a phone after setup.
- **On a real phone, 2026-10-25:** the user's iPhone, in the installed app,
  turned notifications on and Send me a test arrived. The database then
  held one device, on Apple's push service (`web.push.apple.com`), so
  Apple accepted the WebCrypto encryption and VAPID signature.
  - **Gotcha:** right after the deploy, the menu had no Notifications.
    The installed app kept showing the page it already had (and Pages lets
    phones keep files for 10 minutes). Fully closing the app and reopening
    it brought the new version.

**The bell, setup** (after the steps above):

1. Run `supabase/migrations/2026-10-25_notification_choices.sql`.
2. Run `supabase/checks/2026-10-25_notification_choices_rehearsal.sql`. It
   should say "Rehearsal passed: 12 checks held". It plays three members
   with no device yet, so a real phone never comes into it.
3. Redeploy `send-reminders` with the new `index.ts` (JWT verification
   stays off). Until then the timer sends reminders but no reply or
   reaction notices.
4. Push the pages.

**The bell, checked:** `tests/test_reminders.py` (TheBell,
InboxNotifications), each assertion break-checked in a scratch clone. In a
browser at 375 and 1280 wide, light and dark, with the push objects and
the api faked: the top bar still fits at 375 with Get the app, the bell,
the inbox and the initials; the panel opens, a switch saves, a failed save
goes back with a message, turning the device on swaps the icon and shows
Send me a test, the voting switch shows only with `PFML.siteVoting`, the
iPhone message and Show me how work, and `?inbox=1` opens the inbox and
leaves the address without it. The panel's text measured 5.3:1 contrast
or more in both themes.

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
All-Time page's Career Score (through points per round).

**What it doesn't.** The track's own score is still what the votes gave
it, so the round's placings, round wins, podiums, Top tracks and the
per-submission average are all unaffected. Doubling is literal: a track
that scored 0 adds nothing, and the Daily Double is still used up.

**Safety checks.** Rounds are applied in the order they were created, so
if two accepted requests from one person ever made it into the file, the
earlier round counts and the later one is ignored with a printed reason.
The build refuses to run, rather than quietly dropping a bonus, if the file
is unreadable or the wrong shape (an object whose `requests` and
`reviewedRounds` are lists of objects, each reviewed round with a
`roundId`), if a request's `decision` isn't exactly `accepted` or
`rejected` (so `"Accepted"` stops the build rather than being skipped), if
an accepted request lacks its `roundId`, `spotifyUri` or `submitterId`, if
an accepted request doesn't match a real submission, or if two accepted
requests point at the same track. The message names the entry
(`requests[2]`). A request whose
submitter doesn't match the track's submitter is ignored with a warning.

**Checking a publish.** The season file's `dailyDouble` records what the
build did: the Daily Doubles applied (`used`), and how many rounds have
been reviewed and which haven't (`reviewedRounds`, `unreviewedRounds`).
The page reads only the per-player and per-track entries, but this is the
quickest way to confirm a new round's review landed.

Seasons without a `daily_doubles.json` file (Seasons 1 and 2) don't use
the rule at all.

## Translations

A vote comment or submitter note written in another language shows the
original first, then its English underneath, labelled "Translated from
Icelandic" (or whichever language), inside the same box: on the round
page, and in the longest-comment and quote cards wherever that comment
turns up. Mock languages count too ("Løpe Løpe Rudølf" is labelled as mock
Norwegian). Names, song titles and the odd foreign word inside an English
comment don't.

**Kept by hand, like the Daily Double.** The build has no network and no
API key, so nothing translates at build time. Translations are written when
a round's export arrives (CLAUDE.md, Update the data) into
`data/translations.json`, local-only and backed up by `publish.py`:

```json
{
  "comments": { "<round id>|<spotify uri>|<voter id>":
                { "from": "Icelandic", "original": "Stutt og gott", "text": "Short and sweet" } },
  "notes":    { "<round id>|<spotify uri>":
                { "from": "Swedish", "original": "...", "text": "..." } }
}
```

Comments use the same id as everything else (`comment_id()` in
`build.py`); a note has no id of its own, so it's keyed by its track.
`original` is the exact text the translation was made from: the build shows
a translation only while the comment still says that, so an edited export
or a mistyped id never puts someone else's English under a comment. It
prints a warning for a translation whose text no longer matches, or whose
id matches nothing, and skips a broken entry or file rather than stopping
(unlike the Daily Double, nothing here changes a score).

First done 2026-10-11, over every season: 24 items, all but two from
Season 3's Nordic round (Icelandic, Swedish, Dutch and two mock-Nordic
jokes), plus one Spanish and one Portuguese comment from earlier rounds.
Found by reading Round 4 in full and screening the rest for comments made
mostly of words the league doesn't otherwise use, then reading every hit.

## Ties

Ties are real in this data (Season 3's first round ended with two players
level on 29), so nothing that names a winner picks one silently:

- **Standings** go by points, and equal points share a place, shown as
  `T1`, `T1`, `3` (competition ranking, the same rule rounds and the
  Standing over time chart use). Rounds won orders people within a shared
  place but doesn't break the tie.
- **Rounds**: tracks level on points share a finishing place, and every
  track in first place is credited with a round win (and so a podium, and
  the Career Score's round-finish bonus).
- **Home page**: a season whose top spot is shared says "Tied for the
  lead" (or "Joint winners" once it's over) and names everyone in it
  (`leaderNames` in `index.json`).
- **Every superlative** (season in numbers, comment superlatives, League
  Highlights) is computed with `best_of()` in `build.py`, which returns the
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

**Taste: points a round** — how many points a voter gave one submitter's
songs, divided by the rounds they could have voted on them (`perRound`).
Because every voter spends the same fixed budget a round across nearly the
same songs, this compares fairly between voters as it stands, in the
league's own units; an even split comes out near 1 (`tasteEvenSplit`: all
points given over all chances, 1.08, 1.07 and 1.01 in Seasons 1-3), so 3.3
is a big fan and 0.0 never gave them a point. Self-votes are excluded and a
pair needs at least 4 chances to vote (one per round) before it is shown,
so one lucky round does not read as a lifelong grudge.

It replaced a **taste index** on 2026-10-11: the voter's share of points
to that submitter over the share an even spread would give, shown as
"1.97×". Members didn't follow it, even with the note. Measured on the real
data before switching: both measures picked the same top five pairs and
the same Biggest fan and Coldest shoulder in every season. The visible
difference is honest ties: in Season 1 four pairs gave exactly 0.5 a round
over 20 rounds, which the ratio's decimals had split. It was 5 until 2026-10-11, when the league asked to see Season 3's
after four rounds rather than five; at 4 nothing in Seasons 1 and 2 changed
(every pair there had at least 5). `MIN_PAIR_OPPORTUNITIES` in `build.py`
sets it, and the page's note reads it from the season file.

**How the section shows it** (`renderTaste` in `app.js`). On a wide screen,
the full grid. On a phone it isn't usable: measured at 375px, 21 players
made it 2,070px wide, about six screens, with one column visible at a time
beside the pinned names. So a phone gets one player's two ranked lists
instead (how they rate everyone, how everyone rates them), opening on the
signed-in member as "you", with a menu for anyone else. Everyone also gets
the league's five strongest and five coldest pairings (side by side, or
stacked on a phone); coldest ties go to the pair with more chances, since a
zero over more rounds says more. Under them, the five most lopsided
(`lopsidedPairs`): who gives someone's songs far more a round than they get
back, each pair once from the bigger giver, and only where both directions
show. Its gap is the difference of the two figures as displayed (one
decimal), so a row always adds up: rounded apart, 1.15 and 0.35 showed as
1.1 and 0.4 with a gap of 0.8. Pick one player in Standings and both
widths show their lists; pick several and both show a grid of just them,
small enough for a phone. A player with no pair to show yet (hasn't played,
or not enough rounds together) is named under it rather than drawn as a
blank row and column.

**Top bet** — the average size of a voter's single largest bet in a round.
High means they concentrate, low means they spread.

**Tracks backed** — how many tracks a voter puts at least one point on per
round. The other half of the same picture.

**Top pick won** — how often the track a voter gave their most points to
went on to win the round (a tie for their top pick, or for the win, counts).
Its award is **Tastemaker**, on a season page (5 rounds voted to qualify,
`MIN_TASTEMAKER_ROUNDS`) and on All-Time, summed over every season (10
rounds, `MIN_SCORED_ROUNDS`, as the Career Score: without a minimum, 3 of
4 rounds at 75% topped it). Both read "23 of 44 rounds (52%)", from one
tile (`tastemakerTile`); at the same rate, more rounds wins. The season
award was called Best read on the room until 2026-10-12.

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

**Style rates** (exclamation, question, ALL-CAPS) — the share of a
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
the comparison rather than given a flattering number. Only the chunked
figure is written (`vocabRichnessSampled`); the raw ratio used to sit next
to it "for reference", but nothing read it, so it went. `VOCAB_SAMPLE_WORDS`
in `build.py` is the chunk size.

**Distinctive word** — a share-versus-baseline ratio, applied to
vocabulary: the player's share of a word divided by the league's share of
that word. A word must appear at least 3 times for that
player to qualify, so a one-off can't win on a denominator of one, and
stopwords are removed first. The stopword list is hand-written in
`build.py` (`STOPWORDS`), deliberately small and dependency-free. It
covers English function words plus the handful that dominate *every*
Music League comment ("song", "track", "love") and would otherwise be the
answer for every player, telling you nothing about any of them.

**Comment matrix** — how often a voter comments on a given submitter's
tracks, out of the chances they had to. It shares the taste matrix's
denominator exactly (one "chance" is one of that submitter's tracks the
voter could have voted on, self-votes excluded), but keeps its own minimum:
a pair needs at least 5 chances before it counts, so one round can't read
as a habit (`MIN_COMMENT_PAIR_OPPORTUNITIES`; it stayed at 5 when the
taste matrix's came down to 4). **Silent treatment** is the pair with the lowest
comment rate over the most chances: the person you have had every
opportunity to say something to and never have. The build works the matrix
out only for that and Most talked at; the matrix itself isn't written to
the season file, since no page shows it (it was about 46KB of each
finished season's download).

**Longest comment** — ranked by word count, with character count as the
tiebreak. The text is shown in full, because the length is the point; it
is the only place the page prints a comment verbatim.

Superlatives and rate-based stats require at least `MIN_COMMENTS_FOR_RATES`
(10) comments. Below that a single exclamation mark reads as a 33%
exclamation rate, so those players appear in the table but are not
eligible to win anything.

### Comment sentiment (optional, and not part of the build)

`scripts/enrich_comments.py` is a standalone local tool that labels each
vote comment with any mix of *funny, witty, angry, mean, heartfelt,
hot_take, appreciative, storytelling, analytical*, each with a strength
from 1 (a touch) to 3 (the whole point of the comment), plus a one-line
rationale. It is the only thing in this repo that calls an API and it
costs money to run. It has not been run yet (checked 2026-10-05).

**What the labels unlock** (all absent until the file exists, so the site
looks exactly as without it): on the All-Time page, six quote cards judged
by the labels (funniest, wittiest, angriest, meanest, most heartfelt,
hottest take: the highest strength wins, ties to the shorter comment,
except heartfelt, which goes to the longer), under a line saying they're
judged by Claude; and four player titles among the award tiles (class
clown, sweetheart, resident grump, hot-take artist: the highest share of a
player's comments carrying those labels, 10 comments minimum).
`sentiment_awards()` in `build.py`. The first version's labels had no
strengths and a *rude* label; a file in that shape still loads (strength
1, *rude* dropped). The label list lives in `build.py`
(`SENTIMENT_LABELS`), and the script takes it from there, along with
`comment_id()`, the CSV reader and the season-folder scan; it used to keep
its own copies, and its CSV reader had already drifted.

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

python scripts/enrich_comments.py --estimate   # measured cost; counts tokens, labels nothing
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
adding a season costs only that season. `--force` re-labels everything in
the run, and `--season seasonN` restricts it to one season; labels outside
the run are kept either way (an earlier version of `--force` started from
an empty file and wiped them). An unreadable labels file stops the script
rather than being overwritten. Let a batch run finish: after Ctrl-C the
batch still runs and is billed, but its results aren't saved.

**Going live.** `data/` is never committed (the site is members-only), so
the labels reach the site the way all data does: run the script, then
`python scripts/publish.py`, which builds locally, where it can read
`data/comment_sentiment.json`, and uploads. (An earlier version of this
section said to commit the file; that predates the members-only setup.)
Deleting the file breaks nothing: the next build just drops the
sentiment stats. `publish.py` backs it up to the private
`league-exports` bucket with the season exports (as it does
`track_art.json`), so a lost laptop doesn't mean paying to relabel. Sending the comments to the API sends every member's
vote comments to Anthropic, so it's the league organizer's decision.

## Spotify links

Track and playlist IDs are in the export, so those links are exact. Artist
and album names appear in the export as text with no IDs, so those links go
to a Spotify search scoped to the name. See `searchLink()` in `app.js`; if
real IDs are ever added to the data, swap it for `/artist/{id}` and
`/album/{id}`.
