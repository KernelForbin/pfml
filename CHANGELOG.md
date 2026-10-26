# Changelog

## 2026-10-26 (follow-up 6): playing here first, the apps' playlists after

- **The listening section now leads with playing on the site:** "Play the
  round here: tap any track below and it plays on from there", then the
  player and the list.
- **The apps' playlists moved below the list,** under "Prefer an app?",
  with Open in Spotify / Open in YouTube. Their buttons at the top read as
  the way to listen and sent people off the site (the user's call).
- **No promise about a locked phone** above them any more.
- **Verified:**
  - the suite passes (790), with 4 breaks in a scratch clone, all caught;
  - on the demo at 375, light and dark: the new order, no sideways
    scroll, and contrast 13.6:1 or better.

## 2026-10-26 (follow-up 5): a Listening demo link for the admin

- **In the initials menu, admin only:** Listening demo, opening
  pfml.fun/round?demo=1, so the demo can be tried from the app installed on
  a phone, which has no address bar. Commissioners and members don't see it.
- **Verified:**
  - the suite passes (790), with 3 breaks in a scratch clone, all caught;
  - in a browser, measured on screen: shown for the admin and opens the
    demo; hidden for a commissioner and a member.

## 2026-10-26 (follow-up 4): the first tap on a phone, on the list

- **Measured on the user's iPhone:** with every track on YouTube, only the
  first track needed an extra tap, on YouTube's own player. After that the
  round played on by itself.
- **A phone now has its YouTube player ready before the first tap,** with
  the first track waiting. A tap on the list starts that player inside the
  tap, which is what iOS needs.
- **If it still doesn't start,** a phone gets "Tap ▶ on the video to start
  it" after 2.5 seconds, instead of the cover that hid YouTube's own
  button.
- **Verified:**
  - the suite passes (788), with 7 breaks in a scratch clone, all caught;
  - in the browser's phone view: the player is waiting before any tap, and
    a list tap plays through it.
- **Measured after it shipped:** on the user's iPhone, a tap on a track in
  the list starts it straight away, and the round plays on by itself.
- **The note under the player** now says only "Keeps going while this page
  is open and the screen is on." The user's call: "with the phone locked,
  use the playlists" didn't hold, and the Spotify sign-in line went too.
  The features page dropped the same locked-phone claim.

## 2026-10-26 (follow-up 3): the demo round, built like a real one, with a public YouTube playlist

- **The demo's copies and order come from `round_playlists.py`'s own
  matcher and shuffle**, as a real round's would: all 5 YouTube copies
  were "sure", and one changed from the hand-picked list.
- **A public YouTube playlist, "PFML listening demo", on the user's
  account** (their call), with all 10 in the round's order. It's linked
  as Play on YouTube on pfml.fun/round?demo=1, to share and play off the
  site.
- **The playlist note fits the playlists a round has:** with only
  YouTube's, it says "same order as the list below".
- **Verified:**
  - the suite passes, with 5 breaks in a scratch clone, all caught;
  - the playlist's public page, without signing in, lists all 10 in order;
  - in a browser: the demo's list in the playlist's order, one Play on
    YouTube button, and a phone starting on YouTube copies.

## 2026-10-26 (follow-up 2): listening moves to the round page

- **The user's call:** a closed round's playlists, track list and player
  live on the round's own page, for good. They used to be on the Submit
  page, and only until the next round opened.
- **`round?site=<id>`** works from the moment submissions close. Once the
  round is in the stats, the same link shows its stats page with the
  listening section on top, and so does the stats page's own link.
- **A Music League round is matched to its stats round by number:** "Round
  7: …" on the site is the season's 7th round. A season played on the site
  matches by id.
- **The Submit page:** shows "Listen to this round" once its round closes.
- **The demo moved to `round?demo=1`.**
- **Measured on an iPhone** (Safari and Chrome, signed in to Spotify): no
  playing on to the next track by itself, a YouTube track needs a tap on
  YouTube's own player, and Spotify plays previews only. So the playlists
  come first, and the features page says the iPhone may need a tap per track.
- **A phone starts the player on the YouTube copies** (the user's call):
  each Spotify track plays its YouTube copy, the exact track or the closest
  one, found when the playlists are built. A choice made in the Play menu
  is kept.
- **Verified:**
  - the suite passes, with 16 breaks in a scratch clone, all caught;
  - in a browser with a stand-in and a local copy of the real Season 3
    stats, at 375 and 1280, light and dark: each kind of round page, the
    Submit page's link, the demo, and play and pause from the list.

## 2026-10-26 (follow-up 1): play buttons on a round's tracks, no tags

- **No submission tags** (A1, B3) on a closed round's track list or in the
  player's "now playing" line. Members don't need them.
- **A play button on each track:** tap one to play the round from there,
  and tap the one playing to pause or resume it. It shows pause only while
  its track is sounding, and stays in step with the player's own buttons.
- **Verified:**
  - the suite passes, with 15 breaks in a scratch clone, all caught;
  - in a browser on the listening demo, at 375 and 1280, light and dark:
    play, pause and resume from the list, a jump from YouTube to Spotify,
    a pause from the player's button, and Shuffle while paused.

## 2026-10-26: a listening demo for trying the round player on a phone

- **pfml.fun/submit?demo=1:** the real Submit page with a stand-in closed
  round of 10 tracks (5 sent from Spotify, 5 from YouTube, each under 5
  minutes, each with its copy on the other service), so the round player
  can be tried on a phone, screen locked included.
- **Nothing reaches the database:** `listen-demo.js` answers the round
  and its tracks itself, and any call naming the demo round. Without
  `?demo=1` it does nothing.
- **Not league data:** the tracks were picked at random from Spotify and
  checked against the league's catalog. None was ever submitted to the
  league.
- **Verified:**
  - the suite passes (766), with 12 breaks in a scratch clone, all caught;
  - in a browser: the real round without `?demo=1`, the demo with it, Play
    working at 375, and no call naming the demo round got through.

## 2026-10-25 (follow-up 16): a note's switch, shown while voting or only after

- **The user's call:** each note has a switch, "Show it to voters while
  they vote", off by default. Off, the note shows only once the results
  are posted, with the submitter's name. On, voters see it with the track
  while they vote, without the name.
- **The database holds it:** notes move to their own table,
  `site_submission_notes`, whose row rule shows a note during voting only
  if its switch is on, and every note once voting closes. The old note
  column on the tracks is dropped, since any member can read a round's
  tracks once submissions close.
- **The Submit page:** the switch under the note box and in each Edit your
  note, and a line on each of Your tracks saying when its note shows. The
  privacy and features pages say the same.
- **Set up the same day:** the user ran the migration, then the rehearsal
  ("Rehearsal passed: 10 checks held"). The live checks pass: strangers
  are refused the notes table and the note function, a track no longer
  has a note column, and the old three-argument call is gone.
- **Verified:**
  - the suite passes, with 27 breaks in a scratch clone, all caught (one
    got through at first, and the tests were tightened);
  - in a browser with a stand-in, at 375 and 1280, light and dark: the
    switch starts off, flips, goes with the track when it's sent, saves
    from the edit box, survives a reload, and the picker resets to off.

## 2026-10-25 (follow-up 15): the admin can delete a round nobody played

- **Four test rounds** from 2026-10-18/19 ("Round 7: Live Tracks" 1 to 4)
  were deleted by hand in the SQL Editor (the user ran it; it returned
  those four, and the real Round 7 was untouched).
- **A Delete button** on the Commissioner page, for the admin only (the
  user's call). It shows only on a round that was never really played: one
  voted in Music League, closed, with no playlists, no votes on the site,
  and tracks from one player at most. Real rounds like Round 7 never
  qualify, and the database refuses them whatever the page does.
- **No direct delete any more:** the admin's direct delete policy is
  dropped, so `delete_site_round` is the only way to delete a round.
- **Set up the same day:** the user ran the migration, then the rehearsal
  ("Rehearsal passed: 8 checks held"). The live checks pass: strangers are
  refused, the secret key isn't the admin, and no round there now
  qualifies.
- **Verified:**
  - the suite passes (742), with 19 breaks in a scratch clone, all caught
    (one got through at first, and the test was tightened);
  - in a browser with a stand-in, at 375 and 1280, light and dark.

## 2026-10-25 (follow-up 14): notes, announcements, services and the repeat rule (commissioners, stage 4)

- **Allowed services:** a season or round can take any of Spotify, YouTube
  and SoundCloud. The Submit page shows only those, and the database
  refuses the rest.
- **The repeat rule:** off, warn (as before), or block a song or an artist
  already in the round (this round only, the user's call). A blocked
  track can't be sent, from the page or around it.
- **Submitter notes:** in rounds voted on the site, a note with each
  track, shown on the ballot and in the results, editable while
  submissions are open. They reach the stats like Music League's.
- **Announcements:** a commissioner posts one from the Commissioner page;
  it shows on Home for 7 days and is pushed once to everyone with
  Announcements on in the bell.
- **No Daily Double on the site** (the user's call).
- **Every existing round:** keeps all three services and the warning.
- **Set up the same day:** the user ran the migration, then the rehearsal
  ("Rehearsal passed: 16 checks held"), and redeployed `send-reminders`.
  The live checks pass: strangers are refused the five new functions and
  the announcements table, only a commissioner posts, and every round kept
  all three services and the warning.
- **A live test that was stale since stage 3:** `my_submission_described`
  answers true for a caller with no tracks since more songs a round; the
  live repeats test still expected false and wasn't rerun then. The
  database was right (the page asks only when the reader has tracks); the
  test is fixed.
- **Verified:**
  - the suite passes (695 before the rebase onto today's other changes,
    728 after), with 45 breaks in a scratch clone, all caught;
  - in a browser with a stand-in, at 375 and 1280, light and dark. Three
    problems were found and fixed there (README, Commissioner extras).
## 2026-10-25 (follow-up 13): how it's built, on the features page

- **At the bottom of the features page:** built with Claude Opus 5.5, in
  Claude Code, and the commits, lines of code, tests run on every deploy,
  deploys, daily security checks run, and the lines in the README,
  CLAUDE.md and the changelog.
- **Counted at every deploy** (`stamp_build_stats.py`), in the deploy's
  copy only, so they're never stale and need no commit. The build job now
  checks out the whole history, for the commit count.
- **Left out** (the user's call): prompts and Claude's steps, since only
  today's session is still on disk, and SQL queries, which nothing records.
- **Verified:**
  - the suite passes (705), with 18 breaks in a scratch clone, all caught
    (three got through at first, and the tests were tightened);
  - a copy stamped with today's numbers, in a browser at 375 and 1280,
    light and dark: nothing scrolls sideways, and the labels and numbers
    read at 5.9:1 or better.

## 2026-10-25 (follow-up 12): groups on the trend chart

- **Group toggles** above the Performance over time chart's player chips:
  You, Front of the pack, Back of the pack, Biggest rises, Biggest falls,
  Most volatile, Steadiest and Been #1. Each picks whoever meets it (3,
  plus ties), more than one adds them together, and a line says who's in
  each and why.
- **Worked out by the build** (`trend_groups`, into the season file), from
  the same places the chart draws, so they're unit-tested.
- **Needs a publish** for the groups to appear: until the season files are
  rebuilt, the chart shows only You.
- **Verified:**
  - the suite passes (692), with 30 breaks in a scratch clone, all caught
    (three got through at first, and the tests were tightened);
  - in a browser with a stand-in, at 375 and 1280, light and dark: groups
    add together, a hand pick or Clear turns them off, the last one off
    shows everyone, and every figure matched the chart's own point labels.

## 2026-10-25 (follow-up 11): more songs a round, and downvotes (commissioners, stage 3)

- **More songs:** a season set up on the site can ask for 1 to 5 songs
  from each player a round. The Submit page lists your tracks, each with
  Remove. Who's in, the Home banner and Accelerated count a player in once
  all theirs are.
- **Downvotes:** up to 20, with a cap on one song. They're optional, as in
  Season 1's exports (15 of 316 ballots used them), and upvotes are still
  spent in full. A non-voter keeps only their downvotes.
- **Every existing round:** keeps 1 song and no downvotes.
- **The stats build:** handles more than one song a round. Rounds won,
  podiums and finishes count once a round per player, and the career and
  taste count rounds, not tracks. Today's output is byte-for-byte
  unchanged.
- **Set up the same day:** the user ran the migration, then the rehearsal
  ("Rehearsal passed: 16 checks held"). The live checks pass, the new
  ballot rule's eight downvote cases among them.
- **Verified:**
  - the suite passes (672), with 41 breaks in a scratch clone, all caught;
  - in a browser with a stand-in, at 375 and 1280, light and dark. Three
    problems were found and fixed there (README, More songs and
    downvotes).

## 2026-10-25 (follow-up 10): seasons on the site (commissioners, stage 2)

- **Set up a season:** a commissioner sets one up in five steps (Details,
  Songs + Votes, Timing, Rounds, Players), with a schedule preview. Its
  rounds open on their own: each when the one before closes voting.
- **Timing:**
  - Steady holds every deadline.
  - Accelerated closes a round as soon as everyone's in or has voted.
  - Speedy also moves the rest of the season up.
- **Run it:** each season has a section to rename, add, reorder and remove
  rounds, change its settings, and choose its players.
- **Voting on the site is on:** every season set up here votes on
  pfml.fun (the user's call). Season 3 and every round before still vote
  in Music League; the database holds that. The privacy page, the footers
  and the features page say so.
- **Members:**
  - the Submit page waits for a round to open, with Coming up below;
  - "x/N submitted" counts the season's players;
  - a round is announced when it opens, to its players.
- **Set up the same day:** the user ran the migration, then the rehearsal
  ("Rehearsal passed: 24 checks held"). The live checks pass: strangers
  are refused the eight new functions and both tables, only a commissioner
  sets up a season, and every live round has an opening time before its
  deadline.
- **Verified:**
  - the suite passes (647), with 57 breaks in a scratch clone, all caught;
  - in a browser with a stand-in following the same rules, at 375 and
    1280, light and dark. Six problems were found and fixed there (README,
    Seasons on the site).

## 2026-10-25 (follow-up 9): commissioners, stage 1

- **A Commissioner role:** the admin can make any member a commissioner,
  from the site, so no player's name goes in this public repo. A commissioner runs rounds like the admin; the admin
  always counts as one.
- **The Commissioner page** (`/commissioner`), linked in the initials menu
  for them only:
  - the round form, moved here from the Submit page;
  - renaming and redescribing earlier rounds;
  - for the admin, the Commissioners switches and League status.
- **A deadline guard in the database:** nobody signed in, the admin
  included, can reopen a closed deadline or move one into the past. Closing
  early uses the database's clock.
- **The pages:** "Nobody, the admin and commissioners included, can see who
  submitted which track" on the Submit and features pages.
- **Set up the same day:** the user ran the migration, then the rehearsal
  ("Rehearsal passed: 15 checks held"). The live checks pass: both new
  functions refuse a stranger, and `set_commissioner` refuses even the
  secret key.
- **Verified:**
  - the suite passes; 31 breaks in a scratch clone, all caught;
  - in a browser with a stand-in following the same rules, at 375 and 1280,
    light and dark, as the admin, a commissioner and a member.

## 2026-10-25 (follow-up 8): the notifications bell, with replies and reactions

- **A bell in the top bar**, just left of the inbox, replaces Notifications
  in the initials menu, so members see it as soon as a page loads (the
  user's ask). It shows a slash while this device has them off.
- **A switch for each kind:** a new round, a playlist ready, replies to
  your comments, reactions to your comments, and (once voting on the site
  is on) voting closing before you've voted. The choices are the member's,
  stored in `reminder_settings`, and the same on every device.
- **Replies and reactions notify:** `inbox_claim()` finds what the inbox
  would show since each member's mark, one summary per member a run; a tap
  opens the inbox.
- **A bug found in the browser:** opening the bell redrew its icon before
  the click-outside handler ran, which then closed the panel at once. It
  now checks the click's path from when it began. Regression test.
- **Set up the same day:** the user ran the migration, then the rehearsal
  ("Rehearsal passed: 12 checks held"), and redeployed `send-reminders`
  with JWT verification still off. Live, read-only: the three new functions
  answered a stranger 401. Then pushed (d9c757d); the live files matched
  the commit, and the bell showed on the user's iPhone in the installed
  app.
- **Verified:** the suite passes, each new assertion break-checked in a
  scratch clone (34 breaks, all caught). In a browser at 375 and 1280,
  light and dark, with the push objects and the api faked: the top bar fits
  at 375, switches save and go back on failure, the device switch swaps the
  icon, `?inbox=1` opens the inbox. Not yet seen: a real reply or reaction
  notification on a phone.

## 2026-10-25 (follow-up 7): notifications switched on

- **Notifications are on:** Notifications in the menu under your initials
  turns them on for that phone or browser, for new rounds and new
  playlists. On iPhone it works in the installed app.
- **The setup was done in order**, each step measured (README, Reminders):
  - the migration, then its rehearsal ("12 checks held");
  - `pg_cron` and `pg_net` turned on;
  - `send-reminders` deployed with JWT verification off and its two
    secrets, which were made with OpenSSL, passed by clipboard, and never
    shown or stored;
  - the timer, as `pg_cron` job 1.
- **A fix found on the way:** the deployed function answered 500 to a
  forged unsubscribe link before its secret was set. It now refuses with
  401, with a test.
- **The pages:**
  - the privacy page has a Notifications section (what's kept, who carries
    the message, how to turn it off), and says where the background script
    lives;
  - the features page has the item and a What's new line, and Home's
    What's new says New.
- **Verified:** the suite passes, including the guard that the privacy and
  features pages cover notifications once the key is set. Live, read-only:
  every new function refuses a stranger, the function refuses anyone
  without the secret, and a call as the timer answered
  `{"claimed":0,"sent":0}`. Then on a real phone: the user's iPhone, in
  the installed app, turned notifications on and the test arrived, through
  Apple's push service. It took a full close and reopen of the app first,
  to drop the page it was still showing from before the deploy.

## 2026-10-25 (follow-up 6): reminders, built and waiting on setup

- **App notifications,** asked for 2026-10-25:
  - new round open and playlist available, now;
  - voting at halfway, 5, 2 and 1 hour left, only to players who haven't
    voted, dormant until voting is switched on.
- **Email is built but on hold** (the user's call): it waits for a Resend
  account and DNS records for pfml.fun. Until then the sender never asks
  for it.
- **Nothing shows yet.** The Notifications item stays hidden until the push
  key is set up, which needs the user's migration, the Edge Function
  deployed with its secrets, and the five-minute timer. README, Reminders,
  has the order.
- **Built:**
  - **On the phone:** `sw.js`, which only shows notifications, and the
    Notifications panel: turn on or off per device, send a test, the
    iPhone and blocked cases.
  - **Database:** three tables and seven functions, in
    `supabase/migrations/2026-10-25_reminders.sql`.
  - **Sender:** `supabase/functions/send-reminders/index.ts`, one file with
    no libraries, its push encryption done with WebCrypto.
  - **Setup and checks:** the timer's setup SQL, a rehearsal script that
    rolls back, and a live test.
- **Verified:** the suite passes, with 26 new tests, break-checked (19
  breaks, all caught). The push encryption, run in a browser exactly as it
  stands in `index.ts`, matched RFC 8291's worked example byte for byte,
  and a fresh message decrypted back. In a browser, with the browser's push
  objects faked: the panel's turn-on order, test and turn-off, the iPhone
  and blocked messages, and nothing shown without the key. `sw.js`'s logic
  was checked with fakes too. Not run anywhere real yet: the browser pane
  allows no service workers, so the first real test is a phone after setup.
## 2026-10-25 (follow-up 5): a splash screen for the installed app

- **Opening PFML from the home screen shows a short splash**, design B of
  the four shown: the record turning on the dark, PFML in lavender
  underneath. It covers the moment sign-in takes, then fades.
- **When:** only in the installed app (never a browser tab), once per
  opening.
- **How long:** it lifts as soon as sign-in is done, but stays at least
  0.6s so it never flickers, and never past 2s.
- **Android's own splash** comes from the manifest, so its background
  colour is now the same dark and the two run together. With reduced
  motion on, it's the same screen without the animation.
- The features page mentions it, and the privacy page lists the "already
  shown" note it keeps until the app closes.
- **Verified:** the suite passes, with 5 new tests, break-checked (7
  breaks, all caught). In a browser at phone width, against a stand-in with
  the "installed" check forced in a scratch copy:
  - sign-in taking 1.2s: it faded when sign-in finished;
  - instant sign-in: it held to 0.61s;
  - sign-in never finishing: it faded at 2.0s;
  - a second visit: it didn't show;
  - the status bar went dark and came back purple;
  - the splash filled the screen, centred.

  Not checked on a real phone.

## 2026-10-25 (follow-up 4): rounds voted on the site count in the stats

- **A round voted on pfml.fun now counts in the season pages and every
  stat**, like one from Music League's export: standings, places, voter
  stats, comments, profiles, the vault and the repeat checker. Nothing
  shows yet, since voting is still switched off.
- **How:** a new database function, `site_rounds_export()`, hands
  `publish.py` (secret key only) each site round whose voting has closed,
  and never one before. `publish.py` saves them to
  `data/<season>/site_rounds.json`, and `build.py` reads them next to the
  CSVs as rows of the same shape. Waiting on the user:
  `supabase/migrations/2026-10-25_site_rounds_export.sql`.
- **Tracks off Spotify** link to where they were submitted (YouTube or
  SoundCloud), through one helper every page uses. The Spotify copy, where
  the playlists step found one, gives album art and repeat checks.
- **A submitter who didn't vote scores 0** for the round, and the round
  page says why.
- **Two fixes found on the way:** the build would have read a SoundCloud
  key as a Spotify id. And "backed the winner" compared Spotify ids, so two
  tracks with no Spotify copy would have counted as the same one.
- **Verified:** the suite passes, with 26 new tests, break-checked (18
  breaks; one got through and its test was tightened). With no site
  rounds, the real data builds byte for byte as before. In a browser,
  against a build of a made-up season with a site round:
  - the round page links each track to its own service and explains the 0;
  - the standings count the round;
  - the repeat checker links a SoundCloud pick to SoundCloud;
  - no console errors from the site's own code.

## 2026-10-25 (follow-up 3): voting on the site, built and switched off

- **Voting on pfml.fun, for a later round, not Round 7.** The user wants the
  whole league on pfml.fun eventually, without the Music League app; this
  builds voting and leaves it off. Members see nothing of it.
- **Round 7 can never get it.** A round votes here only if it was opened
  that way, and a database trigger refuses to change that afterwards, so
  every round that exists today votes in Music League for good.
- **The user's calls:** who submitted what is revealed when voting closes,
  as in Music League. Rules are Season 3's as measured from the exports (19
  points, at most 5 on a track, all spent, no negatives, only submitters
  vote, none for yourself, comments allowed anywhere), set per round. A
  submitter who doesn't vote scores 0.
- **Built:** the ballot on the Submit page; who has voted; the results with
  every vote and comment; a Home banner; and for the admin, the voting
  fields when opening a round, then the deadline and an early close. One
  switch in `account.js` keeps all of it off.
- **Waiting on the user:** `supabase/migrations/2026-10-25_site_voting.sql`,
  then `supabase/checks/2026-10-25_site_voting_rehearsal.sql`, which plays
  a whole round in the real database as three members and rolls itself
  back. The page code reads the new columns, so it ships only after the
  migration has run.
- **Not built yet:** a round voted here doesn't reach the season pages or
  stats (`build.py` reads Music League's CSVs). That's the next piece.
- **Verified:** the suite passes, with 25 new tests (the rules as text, the
  switch, Round 7's guard, the wiring), break-checked (17 breaks, all
  caught). A live test runs the ballot rules in the real database once the
  migration is in. In a browser, against a stand-in that follows the same
  rules, at 375px and 1280px, light and dark:
  - the ballot: the cap per track, every point spent, a comment on your
    own track, a saved ballot coming back, someone without a track;
  - the results: ties, non-voters at 0, a comment with HTML shown as text;
  - the admin's fields and checks, the panel and closing early;
  - the Home banner;
  - and all of it gone with the switch off.
## 2026-10-25 (follow-up 2): one shuffle for every closed round, and Shuffle on the page

- **The order a closed round's tracks appear in is one shuffle, the same
  for everyone, from the moment submissions close.** It comes from a hash
  of the round and each track, so nothing about who sent what, or when,
  can show in it. The playlists keep exactly that order. Before, the page
  listed tracks by tag until the playlists were built, and the playlist
  script then shuffled afresh, so the order changed under people.
- **Shuffle** on the Submit page mixes the list up for that listener alone,
  never saved, and the round player follows it top to bottom (numbered in
  play order). A track that's playing moves to the top and keeps playing.
  **Original order** puts back the round's shuffle.
- **Verified:** the suite passes, with 9 new tests, break-checked (12
  breaks, all caught). The page's hash gives the same four values as the
  playlist script's, checked in a browser. In a browser against a stand-in
  closed round:
  - the starting order matches the script's;
  - Shuffle and Original order work;
  - shuffling mid-track keeps it playing at the top ("1 of 4", same
    player), and Next follows the new order;
  - with the playlists built, the saved order holds;
  - at 375px and 1280px, light and dark, nothing scrolls sideways.

## 2026-10-25: Privacy and Security, Site features in the menu, the crossword retired

- **The privacy page is now "Privacy and Security"**, in its title and in
  every footer and the sign-in card. Its security card drops the "1 problem
  found and fixed" badge and the point about the reaction fix, which isn't
  what the card is for. "Stored in your browser" no longer mentions the
  crossword.
- **"What this site can do" leaves the footers** and becomes **Site
  features** in the menu under your initials (and on the sign-in card,
  which has no menu). Home's What's new button still goes there too.
- **The footer line is accurate again:** the old one said every Spotify
  link was a plain open.spotify.com link with no account involved, written
  before the round player and Submit page. It now says results come from
  Music League's exports, comment votes, reactions, replies and track
  submissions happen here, and the site is members only.
- **The Round 7 hint crossword is gone** (`/round7hint2`): its page,
  `crossword.js`, its styles and dark-mode rule, its tests and docs. A
  browser that played it keeps its saved progress under `pfml-xw-round7hint2`
  until the site data is cleared; nothing reads it.
- **Verified:** the suite passes, with 2 new tests (features is in the
  menu and in no footer; nothing on the site refers to the crossword),
  break-checked. Season pages rebuilt from the template, `site/data`
  byte-identical before and after. Checked at 375px and 1280px, light and
  dark.

## 2026-10-24 (follow-up 11): a daily security check, and a correction

- **Correction:** the security card shipped an hour earlier said none of the
  last 30 days' problems affected PFML. A recheck found one that had: on
  October 14, Supabase published a critical Storage flaw (GHSA-8rrf-w776-x75g)
  letting a stranger upload or overwrite files, private buckets included.
  It's only on Supabase's own repo, which the first pass didn't read. Live
  Storage is 1.80.2, the fixed version, and every file in both private
  buckets matched the local copies byte for byte. The card now says so.
- **Playlist links from the data become links only when they're `https`**
  (round pages and Home's tiles), since that data lives in the bucket the
  flaw could write to. All 54 current links already are.
- **A daily security check** (GitHub Actions, 11:17 UTC,
  `scripts/security_check.py`):
  - advisories affecting the exact versions the site runs
  - Supabase's own new advisories (all 123 of its repos), which wait for a
    person
  - live Storage and Auth versions against Supabase's advisory ranges
  - the outside test, built from `schema.sql`
  
  A clean run redeploys, and the privacy page shows when it last passed, in
  the reader's own time. Run against today's data it passes; with an empty
  reviewed list and Storage faked at 1.80.1, it flagged all five recent
  Supabase advisories and the October 14 range.
- **Verified:** the suite passes, with 26 new tests (the check against a
  made-up world, the stamp, the workflows, the link guard), break-checked
  (17 breaks; one got through because `strptime` refuses the same input,
  so it changed nothing). The live test (`test_live_security_check.py`)
  passes.

## 2026-10-24 (follow-up 10): a security check, posted on the Privacy page

- **A Security check card on the Privacy page**, in plain language: what
  was checked, the date, and what members can do themselves. The page also
  now lists the choices the site remembers in the browser (dark mode, the
  newest feature seen, Get the app, the player's source).
- **What was checked:** the last 30 days of advisories for Supabase, GitHub
  Actions, supabase-js and browsers (none apply to PFML); a read-only probe
  of the live project as a stranger with only the public key (0 rows from
  all 10 tables, writes and members-only functions refused, storage
  closed, the search function refused); and a review of every place the
  pages build HTML (everything escaped).
- **One problem, fixed:** a reaction is any 1-32 characters, and one named
  `constructor` or `__proto__`, stored from a member's browser console,
  matched `Object`'s own property, threw, and blanked votes, reactions and
  replies on that round for everyone (`__proto__` also set
  `Object.prototype.count`). The counters now have no prototype, and
  `reactionGlyph` reads only its own keys. Reproduced in Chrome before the
  fix and checked after it.
- **Verified:** the suite passes, with 2 new tests (the reaction fix, and
  the card keeping a "Last checked" date near the top), break-checked (4
  breaks). The card was checked at 375px and 1280px in light
  and dark, with no sideways scroll.

## 2026-10-24 (follow-up 9): Get the app

- **A "Get the app" button in the top bar on phones**, and **Add to home
  screen** in the initials menu. On Android, Chrome's own install prompt
  appears in one tap. On iPhone, a short dialog shows where to tap (Share,
  then Add to Home Screen). Inside Instagram's or Messenger's browser, it
  says to open the site in Safari or Chrome first. The top-bar button goes
  away after one tap, and neither shows once PFML is running from the home
  screen.
- **Two catches before shipping:** the menu item's `hidden` attribute lost
  to `.acct-item`'s `display: block`, so it would have shown inside the
  installed app. And a dark-mode rule placed mid-file would have quietly
  exempted the rest of the stylesheet from the dark-mode checks, so a new
  test keeps every dark rule in the block at the end.
- **Verified:** the suite passes, with 6 new tests, break-checked (7 breaks;
  one got through at first and its test was tightened). In a browser: the
  button on the top row at 375px and 320px with no sideways scroll; the
  Android steps; Chrome's prompt used directly when offered; the iPhone and
  in-app steps in dark mode; nothing offered when running as the installed
  app; menu item only on desktop. Not verified on a real phone.

## 2026-10-24 (follow-up 8): a new icon

- **The icon is now a dark record on the purple tile**, with three grooves
  catching lavender light and a purple label carrying a white P. The user
  chose it from three rounds of options ("g3"). It replaces the plain white
  P, in the browser tab of every page and on phone home screens.
- **One source:** `scripts/make_icons.py` holds the shapes, writes the tab
  icon into every page, and draws the PNGs from the same shapes. The
  grooves are true circles around the record's centre, so the tab icon and
  the PNGs agree exactly (the sketch's third groove was slightly off).
- **Verified:** the suite passes, with 2 new tests (every page carries
  exactly the script's icon; the drawing checked point by point) and the
  PNG test kept, break-checked (4 breaks). In a browser, the tab icon
  (SVG) and the home-screen PNG were compared side by side at 160px and
  32px, and they match.
- A phone that already added PFML to its home screen keeps the old icon
  until it's removed and added again.

## 2026-10-24 (follow-up 7): choosing the Google account

- **The bug:** sign in with the wrong Google account and the site says it
  isn't linked, with no way back. Signing out and in again reused the same
  Google account without asking, because Google remembers the last one.
- **Google now asks every time:** sign-in sends `prompt=select_account`, so
  Google shows its account picker. Measured: supabase-js 2.116.0 puts it on
  the authorize address, and Supabase passes it to accounts.google.com
  (without it, nothing reached Google).
- **The not-linked and failed-invite cards lead with "Use a different
  Google account"**, which signs out of the site and goes straight to the
  picker. Sign out is still there.
- Also corrected on the features page: the account menu's list now includes
  Dark mode.
- **Verified:** the suite passes, with 3 new tests, break-checked (3
  breaks). In a browser, the real `auth.js` ran against a fake Supabase
  client signed in with an unlinked account: the card offered the new
  button first, and one tap signed out and started Google sign-in with the
  picker. Not verified: Google's picker on a phone, since that needs a real
  sign-in.

## 2026-10-24 (follow-up 6): no Copy recap button

- **The round recap's Copy recap button is gone** (the user's call), along
  with the plain-text version of each line it copied. The recap itself
  stays: winner and margin, most talked about, broadest support, biggest
  bet. The features page no longer mentions copying.
- **Verified:** the suite passes, with a test that no copy button, clipboard
  call or text version is left (break-checked: putting the button back
  fails it). On a real round page in a browser, the recap shows the same
  four lines with no button, at 375px with no sideways scroll.

## 2026-10-24 (follow-up 5): dark mode becomes a switch; a purple round banner

- **Dark mode is now a choice, light by default.** It first shipped
  following the device's setting, so a phone set to dark got the dark site
  unasked. Now the Dark mode switch in the account menu turns it on, and
  the choice is remembered in that browser. A line at the top of every
  page puts it back before the page paints, so there's no light flash.
  The features and privacy pages follow it too.
- **The open-round banner on Home is purple, not black and lime green**
  (the user's call): the brand purple to a deeper one, white text, the
  count as a soft pill, and Submit as an outlined button. It's the same in
  both modes, with white text at least 5.1:1 against both ends of the
  purple.
- **Verified:** the suite passes, with 5 new tests and the dark-mode tests
  reworked, all break-checked (9 breaks). In a browser on a device set to
  dark: light by default, the switch turning it dark and back, and the
  choice holding on Home, a round, features and privacy. The banner was
  checked in light and dark at 375px with no sideways scroll.

## 2026-10-24 (follow-up 4): a What's new button on Home

- **"What's new on the site" is the first thing on Home**, linking to the
  features page. It says **New** when the newest feature there is newer
  than what this browser last saw on that page, and only within the 30
  days the page lists.
- **Remembered per browser:** visiting the features page stores the newest
  date it showed (`pfml.featuresSeen` in localStorage). That needs no
  database change, but a new phone or the home-screen app (its own
  storage) starts at New. Where storage is blocked, the badge stays off
  rather than nag.
- **Verified:** the suite passes, with 3 new tests (Home's date matches the
  newest line, the page records what Home reads, the button comes first),
  break-checked (6 breaks). In a browser: New on a first visit, gone after
  opening the features page, back for someone who last looked on Oct 19;
  light and dark at 375px with no sideways scroll.

## 2026-10-24 (follow-up 3): "New in the last 30 days" on the features page

- **The features page opens with what's new:** a highlighted box under the
  title listing the major features from the last 30 days, newest first,
  each with its date. Twelve today, from translations (Oct 11) to dark mode.
- **It keeps itself current:** each line carries its CHANGELOG date, and a
  few lines of inline script hide anything older than 30 days by the
  reader's clock, then the box once nothing is left. Without JavaScript
  every line shows. Member-visible features only, as the page's rule says.
- **Verified:** the suite passes, with 4 new tests: the box's place, every
  date being a real CHANGELOG heading and the list newest first, the
  30-day script, and no admin-only items. All were break-checked (7
  breaks). In a browser with the clock moved: 12 items today, 10 on Nov
  12, 5 on Nov 23, and the box gone by Dec 20. Contrast is over 4.5:1 in
  light and dark, with no sideways scroll at 375px or 1280px.

## 2026-10-24 (follow-up 2): dark mode

- **The site goes dark when the device is set to dark.** Only the colour
  tokens change; light mode is exactly as before (a test holds every new
  token to its old value).
- **Purple text gets its own token**, because the brand purple reads at
  only 2.9:1 on the dark page. The purple fill behind white text stays the
  brand colour.
- **Found by measuring, not by eye:** the gold, silver and bronze place
  badges went to light-on-gold (1.4 to 2.4) and the features page's Daily
  Double badge to 1.02. Both are now dark text in both modes.
- The crossword keeps its light, printed grid; video frames are black.
- **Verified:** the suite passes, with 9 new tests. The contrast test
  recomputes every important pair from the CSS in both modes, and all
  were break-checked (11 breaks). In a browser, every visible piece of text
  on 10 pages, plus the Submit page with a pick, was measured in dark and
  light. Nothing was under 4.5:1 except the avatar initials, the same in
  both modes. No sideways scroll at 375px.

## 2026-10-24 (follow-up): taste twins, From the vault, round recaps

- **Votes most like them** on every profile: the three players whose
  voting is closest. It compares which songs each backs more than their own
  average, round by round, and lists them with the rounds shared, not a
  percentage. The first try (plain cosine) made one wide-spreading voter
  everyone's twin; measured on the real league and replaced. The new
  measure independently paired the two players who share a surname.
- **From the vault** on Home: a past round winner at random each visit,
  with the note and the comment from whoever backed it most.
- **A recap on every round page**: the winner and margin, the most talked
  about, the broadest support and the biggest single vote, with Copy
  recap for the group chat.
- **Found in the browser:** the third profile list pushed a phone page 46px
  wide (a long name next to "over 46 rounds"); fixed, with a test.
- Needs a publish: `profiles.json` gets the twins, and `vault.json` is new.
- **Verified:** the suite passes, with 13 new tests (taste twins and the
  vault run on made-up seasons), all break-checked (15 breaks). In a
  browser on the real data: Round 6's recap matched the export (Gunslinger
  by 1 over Ma Baker), the vault card, profiles at 375px and 1280px.

## 2026-10-24: Add to Home Screen, a fuller Home banner, admin status

- **Add to Home Screen:** a web app manifest and PNG icons (the favicon's
  purple P, drawn by `scripts/make_icons.py`), so PFML opens full screen
  from a phone's home screen. Sign-in inside it on an iPhone still needs a
  real test (README, Add to Home Screen).
- **The Home banner says when the round closes** ("Closes Sun, Oct 25,
  7:00 PM · in 23 hours") **and whether you're in** ("✓ You're in" and
  "Change your track", or "You haven't submitted yet"). It uses one
  deadline wording, now shared with the Submit page.
- **Admin status on the Submit page:** when the data was last published,
  the latest finished round, and who hasn't joined the site, with whether
  an invite link is waiting for them (never the link itself). Needs
  `supabase/migrations/2026-10-24_admin_invite_status.sql`.
- **Verified:** the suite passes, with 16 new tests, all break-checked (16
  breaks). In a browser against a stand-in: the banner both ways, the
  manifest and every icon loading at its size, the admin panel for the
  admin only; 375px with no sideways scroll.

## 2026-10-23 (follow-up): who's in, x/20

- **"7/20 submitted"** on the Home banner and the Submit page, and a Who's
  in section listing who has submitted and who's pending, with avatars
  linking to profiles. Never which track is whose. Players who haven't
  joined the site are marked "not joined yet".
- **The 20 are the players taking part:** everyone with a track in the
  season's latest finished round, now `activePlayers` in `index.json`. That
  was exactly Round 6's 20. Needs a publish to reach the site.
- **The user's calls:** show names, knowing a member could pair them with
  the repeat warning to guess roughly what someone sent; and everyone now
  submits on the site as well as in Music League. The new database function
  returns player ids only, in id order, not the order they were sent.
  Needs `supabase/migrations/2026-10-23_round_submitters.sql`.
- **Verified:** the suite passes, with 11 new tests, all break-checked (12
  breaks). In a browser, against a stand-in with the real 20 names: the
  count, both groups, the not-joined marks, an extra submitter, the closed
  wording, the Home banner, and the picker still on the first phone screen;
  375px and 1280px with no sideways scroll.

## 2026-10-23: the Submit page spots repeats within the open round

- **Before you send a pick, the Submit page says if it repeats something
  already in this round:** the exact track, the same song by the same
  artist, the same song title by another artist, a song with the same
  title, or the same artist with another song. It never says which track,
  or whose. Asked for the day Round 7 (Live Tracks) opened on the site.
- **How it stays anonymous:** tracks are still unread until the close.
  Each submission keeps a fingerprint (song and artist names as plain
  words, plus a video's title and channel), and a new database function
  answers with the kinds only, leaving out the caller's own track. Needs
  `supabase/migrations/2026-10-23_round_repeats.sql`.
- **YouTube picks are named through Spotify**, because a video's title
  doesn't say which part is the artist and the channel is often a session
  (KEXP, BBC). Measured on 22 real live-video titles: 20 named correctly,
  nearly all on the first search; the rest fall back to the title text.
- **The gauge counts this round too**, so it no longer reads "Fresh"
  under an "Already in this round" warning. Each kind counts as the matching
  repeat this season, at the weights already set.
- **Found by the live test, before members used it:** Postgres rejects regex
  counts above 255, and the length limits were written as `{0,300}` and
  `{0,600}`, so every check would have failed. The migration had run
  clean, because a check on an empty column is never evaluated.
  `2026-10-23_round_repeats_fix.sql` repairs the live project, and a new
  test catches any count over 255.
- **Limits:** only tracks sent on the site are checked, not picks made only
  in Music League. Asking about a pick does tell a member whether that song
  or artist is already in.
- **Verified:** the suite passes, with 19 new tests (15 break-checked) and
  one updated (break-checked). A new live test (`test_live_round_repeats.py`)
  runs the matching rules on the real database once the migration is in.
  In a browser, against a stand-in that follows the database's rules and
  real Spotify and YouTube lookups: all five kinds, nothing, the caller's
  own track left out, a stale fingerprint ignored, the fingerprint saved on
  submit and on a later visit, and a failed check hiding quietly; 375px and
  1280px with no sideways scroll.

## 2026-10-22: supabase-js pinned by hash, and the new-table grant rule

- **Every members-only page now loads supabase-js with an `integrity`
  hash** (sha384, with `crossorigin="anonymous"`). The library runs with
  the member's session, so a tampered copy on jsDelivr could have acted as
  them. Now the browser refuses any file that doesn't match. This came out
  of a check against the week's security news (PHP php2shell, Python TLS
  and tarfile fixes, Linux PwnEscape, Node Brotli, the LiteLLM backdoor,
  GhostAction): none of them reached the site, and this was the one
  hardening step worth taking.
- **Recorded Supabase's 2026-10-30 change:** new tables get no API grants
  by default, so a future migration that creates a table states its
  grants (README, Members only; CLAUDE.md).
- **Verified:** the hash was measured three ways (jsDelivr's file, the npm
  tarball, and jsDelivr's API), and all agreed. The suite passes, with a
  new test that pins the tag on every page and a new live test
  (`test_live_cdn.py`) that checks the real file and its CORS header. Both
  were break-checked. The pages were checked in a browser: supabase-js
  loads and sign-in starts at 375px and 1280px.

## 2026-10-19 (follow-up 9): YouTube links on the repeat checker

- **Paste a YouTube link into the repeat checker** (youtube.com,
  music.youtube.com, youtu.be or shorts) and it names the video ("On
  YouTube: Righteously - Anna Ash (Anna Ash)") and shows its gauge,
  instead of searching the link's words. A video YouTube won't describe
  (private or removed) says so.
- The link lookup now lives once, in `sentiment.js`, for both pages.
- **Found while checking against real uploads:** YouTube's oEmbed names
  auto-generated channels "Artist - Topic", which hid "same artist" (Anna
  Ash's "Player" from "Anna Ash - Topic" said Fresh). The " - Topic" is now
  dropped, on both pages.
- The video's name now shows above the gauge.
- **Verified:** suite passing, with 3 new gauge tests and 3 updated. In a
  browser against the real catalog and YouTube: the official, fan and
  Topic uploads, a different song with the same title, a dead video, a
  link in the address, word searches, the Submit page's pasted links,
  375px.

## 2026-10-19 (follow-up 8): the gauge spots a repeat on another service

- **The bug, reproduced against the real YouTube:** submitting Anna Ash's
  "Righteously" (Season 1, from Spotify) as a YouTube pick said Fresh.
  Her own upload is titled "Righteously - Anna Ash", song first, and the
  Submit page split YouTube titles as "Artist - Song", so "Righteously"
  became the artist.
- **Now a YouTube or SoundCloud pick is free text.** A past track counts
  when its title and one of its artists both appear in it, in any order.
  It's flagged high: "Looks like the same song by the same artist, on
  another service (it can't be confirmed identical)". A multi-word title
  with no artist in sight gets a lower "same title, artist unclear".
- **Pasted links now get a gauge too**, from the catalog or the service's
  own oEmbed. All three services answer browsers on pfml.fun; measured.
- **Checked against the real uploads:**
  - "The league will care": the official one, a fan upload, the karaoke
    version, and pasted links.
  - "A few might notice": Lucinda Williams' different song with the same
    one-word title.
  - "Barely a blip": Anna Ash's other song.
- **Verified:** suite passing, gauge tests updated for the new behaviour
  plus 5 new ones. In a browser against the real catalog and the real
  oEmbed services.

## 2026-10-19 (follow-up 7): the repeat checker's example

- The search box's example is now a Season 1 track (Lee Oskar, "Feelin'
  Happy", Round 1). The old example was never submitted and could have
  hinted at a pick for a round in progress. The same names in the
  README, two code comments and an earlier CHANGELOG entry are swapped
  for Season 1 examples too. They remain in the repo's history.

## 2026-10-19 (follow-up 6): Estimated League Sentiment

- **A gauge, green to red, for how much the league will care about a
  repeat**, with a verdict and the reasons, each linking to the earlier
  submission. An exact repeat gets an extra warning. No number is ever
  shown.
- **On the repeat checker:** a list of Spotify matches under the box ("How
  will the league feel about it?"); pick the exact track for its gauge.
  **On the Submit page:** the gauge appears for the track you pick, from
  search or a pasted Spotify link the catalog knows.
- It weighs exact repeats, other versions, covers, one-word titles, same
  artist and album, an artist twice this season or in the last round, the
  same artist, and featured guests, each by this season or an earlier one.
  The weights are the user's and stay off the site and out of the docs;
  they live in `site/sentiment.js`.
- The search function now returns each Spotify track's album, for the
  album rule. That needs the function redeployed.
- **Verified:** suite passing, with 11 new tests (the score is never
  printed, an exact repeat warns, commas in names, wiring); 15 deliberate
  breaks, each caught. In a browser
  against the real catalog, every rule scored as designed, including the
  "twice this season" rule, tested by briefly making Season 2 current in
  a scratch copy. The pages: the pick list, the gauge at 375px, Spotify
  and YouTube results, and pasted links, known and unknown.

## 2026-10-19 (follow-up 5): the repeat checker, /repeats

- **Has it been submitted before?** One box takes an artist, song or
  album and answers as you type, with every past submission that matches,
  grouped by Artist, Song and Album, newest first. Each match shows its
  round (linked), who submitted it, and its place. A Spotify link checks
  that exact recording, other versions of the song, and more by the
  artist. The search stays in the address, for sharing. It's in the
  initials menu and linked from the Submit page.
- **`catalog.json`**, new from `build.py`, holds every track from every
  round: 733 tracks from 45 rounds, about 200 KB. It's searched on the
  device, so the season files are never fetched. It covers finished
  rounds only.
- **Found while checking against the real data:** the export separates
  artists with commas, so Earth, Wind & Fire (submitted once) arrived as
  "Earth" and "Wind & Fire", and searching its name found nothing. The
  checker now searches the whole artist line too. The same split affects
  other artist counts on the site; that isn't fixed here.
- **Verified:** suite passing, with 11 new tests (the catalog, the
  every-field-is-read contract, the page's wiring, the comma regression);
  12 deliberate breaks, each caught. In a browser against the real
  catalog: Steely Dan 3, Rasputin 1, a never-submitted artist 0 and the Grateful Dead
  results all match the raw exports; accents, "&"/"and", Spotify links,
  the address prefill, and a phone at 375px.

## 2026-10-19 (follow-up 4): search on the Submit page

- **Search instead of a link:** three buttons pick Spotify, YouTube or
  SoundCloud. Type the song and press Enter (or Search) to get up to 10
  results with artwork; tap one to hear it, then submit. A pasted link
  still works in the same box, on any service. Enter only ever searches.
- **SoundCloud** opens SoundCloud's own search in a new tab for now.
  In-page search needs a SoundCloud app, and whether new ones are still
  accepted is unconfirmed.
- **`supabase/functions/search-tracks`**, a small Supabase Edge Function,
  holds the keys and answers signed-in members only, from pfml.fun only.
  - Spotify search uses the playlists' Spotify app, logging in as the app
    rather than a person. Measured: 10 results with artwork, and 11 refused.
  - YouTube search uses a second Google project's key, so it can't use up
    the playlist builder's 100 searches a day. Answers are kept a week.
    When the allowance runs out, the page links to YouTube's own search.
  - It never stores who searched (`search_cache`: service, text and day,
    no policies).
- **Waiting on the user:** the second Google project's API key, deploying
  the function from the dashboard with its secrets, and the
  `search_cache` migration. README, Searching, has the steps. Not pushed
  until then.
- **Verified:** suite passing, 15 new tests; 18 deliberate breaks, each
  caught. In a browser, against a stand-in for the function: search,
  pick, switching service, pasting a link, the quota and failure
  link-outs, nothing found, SoundCloud's link-out, and submitting; fits at
  375px. The function itself is unrun until deployed (no Deno here).

## 2026-10-19 (follow-up 3): no more "put your tag in Music League"

- Voting stays in Music League as usual, and nobody needs to link a site
  submission to their Music League entry (decided today). So the Submit
  page no longer shows the big tag with "put it in your placeholder's
  note". The features page and the playlists' descriptions no longer
  mention it either. The tag stays only as a small label on the track
  list (and in the playlists' "Not on Spotify: Q7" notes).
- **Verified:** suite passing, with one new test that no page or
  playlist asks for it, shown to fail when the wording comes back. In a
  browser, the "Your track" view reads cleanly with no tag anywhere.

## 2026-10-19 (follow-up 2): site rounds, stage 3: the round player

- **Play the round** on a closed round's Submit page plays every track in
  order, moving from Spotify to YouTube to SoundCloud by itself, each in
  its own official player (`site/player.js`). Previous, pause and next;
  tap a track in the list to play from there. Once matches exist, a picker
  plays YouTube or Spotify copies where there are any. That's the way to
  hear full tracks without being signed in to Spotify in the browser.
- **For a screen that's on.** A phone stops it when it locks (the
  playlists cover that), and the page says so. A browser that won't
  start the next track without a tap gets a full-size **Tap to play
  next** button after 6 seconds. A track that can't play is skipped.
- The list's own per-track players are gone: the round player replaces
  them.
- **Measured in Chromium with real embeds:** one click and the round ran
  by itself, YouTube to Spotify (preview) to SoundCloud. Every control
  worked. A missing video was skipped. The tap button appeared when
  YouTube was made to refuse. Fits at 375px. Not measured: Safari on an
  iPhone.
- **Verified:** suite 311 passing with 11 new tests (wiring, the three
  official script URLs and that only player.js loads them, nocookie
  YouTube, the fallback, skipping, one player at a time, the source
  fallback, safe storage, hidden rules); 12 deliberate breaks, each caught.

## 2026-10-19 (follow-up): site rounds, stage 2: the round playlists

- **`scripts/round_playlists.py`** turns a closed site round into a Spotify
  playlist and an unlisted YouTube playlist, shuffled once, in the same
  order. Each track is looked up on its own service and searched for on
  the other. A match goes in only when title, artist and length (within 3
  seconds) agree, and live has to match live. Anything less is left out and
  listed, for `--accept` or a hand-set match. `--dry-run` reports and writes
  nothing. Re-running keeps the order and updates the same two playlists.
  It never reads who submitted what.
- **`scripts/connect_accounts.py`**: a one-time browser sign-in for each
  service that saves a long-lived token in `.env`, never printed.
- **The Submit page**, once a round is built: Play on Spotify and Play on
  YouTube buttons, the tracks in playlist order with title and artist, and
  "Not on Spotify" where a playlist skips one.
- **Accounts:** the user's own Spotify (Premium) and Google accounts.
  Playlists are link-only (decided today).
- **Read from Spotify's and Google's docs, 2026-10-19:**
  - Spotify's February 2026 API changes: new playlist endpoints, search
    capped at 10 results, Premium required for a Development Mode app's
    owner.
  - YouTube: a 100-a-day search allowance, and 50 units per playlist item.
  - Google: Testing-mode sign-ins expire in 7 days, so the Google app gets
    published.
  - Measured: SoundCloud oEmbed works without an account.
- **Measured once the accounts were connected:** the live test passes for
  all three services. A trial on 9 real tracks matched 8 correctly (live
  to live, within a second). The 9th, PSY's music video, is 34s longer
  than the song and was rightly left out. The trial also caught a duo
  credited on Spotify ("Gil Scott-Heron, Brian Jackson") failing against
  a channel named for one of them, now fixed: any credited name counts.
- **Not yet measured:** whether a non-owner can open a non-public Spotify
  playlist by its link. The first real round checks it.
- **Waiting on:**
  - `supabase/migrations/2026-10-19_round_playlists.sql`, run in the SQL
    Editor, before this ships (the page reads the new columns).
  - The two app registrations and sign-ins (README walks through them).
- **Verified:** suite 299 passing (7 live tests skipped), with 33 new offline tests: matching, order,
  overrides, the exact Spotify and YouTube calls (fakes), a full build and
  rebuild with fakes, dry run, never touching the owners table, and the
  schema. A live read-only test skips until the keys exist; its SoundCloud
  part passes now. In a browser, against a stand-in: the built and unbuilt
  views at 375 and 1280px. The phone check caught small tags drawn at full
  size and titles squeezed beside the gap marker; both fixed. 24 deliberate
  breaks in a scratch clone, each caught.

## 2026-10-19: a deploy no longer leaves pages running old scripts

- **What happened:** straight after the Submit page shipped, it sat at
  "Loading the round." with an empty top bar. GitHub Pages tells browsers
  to keep every file for 10 minutes (`max-age=600`, measured), and a
  browser that had `auth.js` and `app.js` from an earlier visit ran the new
  page with them: the old `auth.js` has none of the Submit page's calls, and
  the old `app.js` doesn't fill the Submit page's header. Reproduced with
  the new page and the previous `app.js`/`auth.js` api: same screen.
- **Fix, for every page:** the deploy stamps each page's own scripts and
  stylesheet with the commit (`app.js?v=…`), so a page always loads the
  scripts it was built with. Pages ignores the query (measured). The repo's
  files are unchanged; only the deploy's copy is stamped
  (`scripts/stamp_assets.py`).
- **And on the Submit page:** a failure while loading now shows a message
  (with "Reload the page" for this case) instead of hanging.
- **Verified:** suite 263 passing (4 new); 6 deliberate breaks, each
  caught after one fix (the order test was finding the script's name in a
  comment, not the step). The stale case checked in a browser: it now
  says to reload.

## 2026-10-18 (follow-up): submitting tracks on the site, stage 1

- **The plan**, agreed today: members submit their real track on pfml.fun
  (Spotify, YouTube or SoundCloud) and still enter a placeholder in Music
  League, where voting stays. When submissions close, the round is
  shuffled once and built as a Spotify playlist and a YouTube playlist in
  the same order, each track matched to its copy on the other service
  (stage 2), so everyone can listen in the app they use, screen locked.
  A web page can't do that: YouTube's embedded player stops when the
  screen locks, phones won't start the next track in the background, and
  Spotify's web player doesn't run in phone browsers. A mixed player on the
  round page comes in stage 3, for desktop and screen-on listening. A
  track on only one service is allowed, with a gap in the other playlist.
- **Stage 1, this change:** the Submit page (`/submit`), reached from a
  Home page banner while a round is open and from the initials menu. Paste
  a link, check it in the service's own player, submit, get a tag (like
  Q7) for the Music League note. Change or withdraw until the deadline.
  After it, everyone sees and plays the list. The admin opens, edits and
  closes rounds on the same page.
- **Anonymous, even to the admin:** tracks are stored with no name or
  time; who sent which sits in a table nothing signed in can read. Only a
  deliberate lookup with the secret key could join them (agreed as enough).
- **Measured:** song.link's public API answers `401
  PUBLIC_API_ACCESS_DEPRECATED`, so stage 2 will match tracks itself.
- **Waiting on:** `supabase/migrations/2026-10-18_site_submissions.sql`,
  run in the SQL Editor, before this ships. Until then the Home banner just
  doesn't show.
- Privacy page: submissions, the services' players on the Submit page, and
  the crossword's saved progress (which it should already have said).
  Features page: a Submit your track card.
- **Verified:** suite 259 passing (18 new in `tests/test_submissions.py`:
  the anonymity rules, schema and migration agreeing, the link shapes
  matching the database's, every rpc existing, the page wiring). In a
  browser against a stand-in following the database's rules: 22 link
  shapes, open/edit/close as admin, submit, change (same tag), a duplicate
  refused, withdraw, the closed list playing in place, the Home banner,
  no admin panel for a member; no overflow at 375 or 1280px. 28
  deliberate breaks in a scratch clone, each caught; the first run let a
  withdraw-after-the-deadline slip through (the test saw the check but not
  that it refuses), so each check is now pinned to its `raise`. Not run
  against Postgres; there's none here.

## 2026-10-18: the Round 7 hint crossword, /round7hint2

- **A playable, members-only 15x15 crossword** at pfml.fun/round7hint2:
  4-Across L4LM ("Kunj conglomerate"), 5-Down 4NONBLONDES, with GONG and
  SOLO crossing it, as asked; 84 entries, every one clued. Plays like a
  newspaper app: pick a square, pick again to turn, type to fill; arrows,
  Tab and Space on a computer, the page's own keyboard on a touch screen
  (docked under the grid, 123 key for the 4). Check and Reveal by square,
  word or puzzle; Pause; Clear; a clock. Progress stays in the browser.
- The brief's grid couldn't be filled (four 15-letter downs), so the black
  squares were redrawn, symmetric, with the four requested answers where
  they were. The row between L4LM and GONG can only be vowel-N-vowel-vowel,
  so 15-Across is UNAU (a sloth). README, Round 7 hint crossword, has the
  rest, including that the answers sit in public page code, lightly
  scrambled.
- Not on the features page, on purpose: it's a hint.
- **Verified:** suite 241 passing (10 new in `tests/test_crossword.py`,
  plus the page joins the member-page checks); 18 deliberate breaks in a
  scratch clone, each caught. In a browser with a sign-in stub: typing,
  auto-advance, direction switching, check, reveal, pause, clear and
  saved progress; at 375x812 the grid and keyboard dock fit one screen,
  and at 375, 768 and 1280px nothing scrolls sideways.

## 2026-10-12: Tastemaker, all-time and per season

- **New All-Time award, Tastemaker:** whose biggest vote of a round most
  often went to the round's winner, over every season. It's josh storm:
  23 of the 44 rounds he voted in (52%). Ten rounds voted to qualify, as
  for the Career Score; without a minimum, 3 of 4 rounds (75%) would top
  it. At the same rate, more rounds wins.
- **The season award of the same thing is called Tastemaker too** (it was
  Best read on the room), with the same wording: Season 1 Dianna Hank, 9
  of 16 rounds (56%); Season 2 josh storm, 14 of 20 (70%). A season's
  needs 5 rounds voted, so Season 3's appears after Round 5. One tile
  draws both.
- League Highlights is five tiles now, so its last row holds one.
- **Verified:** suite 231 passing (5 new tests; one existing test's
  hand-made season was missing the voters list every real season has).
  In a browser at 375px and 1280px: the tile reads as above on All-Time
  and both finished seasons, no overflow.

## 2026-10-11 (follow-up 5): most lopsided pairings

- **A third list beside strongest and coldest: who gives someone's songs
  far more than they get back.** Each pair once, from the side giving more:
  Gives a round · Gets back · Gap (the gap drops on a phone, like Rounds).
  Season 3 is led by Memo → Rick D, 3.3 a round with 0.3 back. Full width
  under the other two on a desktop; stacked on a phone.
- The gap is the difference of the two figures as shown, so every row adds
  up. The first browser check caught Season 2 reading "1.1 | 0.4 | 0.8":
  each number had been rounded on its own.
- The taste lists take their columns as a parameter now (the old header and
  cells were fixed), so the lopsided list reuses the same component.
- **Verified:** suite 226 passing (3 new tests). In a browser at 375px and
  1280px on all three seasons: rows add up and run biggest gap first, the
  layout is right at each width, nothing clipped or overflowing.

## 2026-10-11 (follow-up 4): taste in points a round

- **Taste reads in points now, not "1.97×".** Members didn't follow the
  ratio, even with the note. The number is the points a voter gives
  someone's songs each round, on average: "Memo gives Rick D's songs 3.3
  points a round (an even split is 1.0)". Every voter spends the same
  points a round across nearly the same songs, so this compares fairly as
  it stands; an even split comes out near 1 in every season.
- **The lists have column headers**: Player (or Voter) · Points a round ·
  Points · Rounds (Rounds hidden on a phone, as before).
- Everywhere the × was: the lists, the grid and its legend, the strongest
  and coldest pairings, Biggest fan and Coldest shoulder, and the focus
  panel's fan and comparison tiles. The section note explains it in one
  line from the season's own numbers.
- Measured on the real data first: the new number picks the same top five
  pairs and the same Biggest fan and Coldest shoulder in every season. The
  one visible difference is honest ties (Season 1's coldest shoulder now
  says "tied with 3 more": four pairs gave exactly 0.5 a round).
- **Verified:** suite 223 passing (7 new tests; the seventh added when a
  break-check showed the first six would miss Biggest fan being ranked by
  total points instead). In a browser: on a phone,
  headers fit and nothing is cut off or overflows; on a desktop, the
  19-player grid shows one-decimal values and the legend in points;
  one-player and two-player focus tiles read in points; no × left on the
  page apart from the remove-filter buttons.

## 2026-10-11 (follow-up 3): Who likes whose taste, on a phone

- **On a phone, the section opens on you**: how you rate everyone else,
  and how everyone else rates you, as two ranked lists, with a menu to see
  anyone else's. The grid stays on wider screens. Measured at 375px, it was
  2,070px wide, about six screens, with one column visible at a time.
- **The league's five strongest and five coldest pairings**, on every
  screen: side by side on a desktop, stacked on a phone.
- **No blank rows**: players with no pair to show yet (Clavenna Vision
  hasn't played; Scott Menke needs one more round) are named under the
  section instead of filling a row and a column with dots.
- Picking players in Standings works as before: one shows their lists,
  several show a grid of just them, which fits a phone.
- **Verified:** suite 216 passing (5 new tests, two updated to follow the
  code). In a browser on Season 3: at 375px the grid is hidden, your lists
  and the pairings show stacked, and the menu switches player; at 1280px
  the 19-player grid shows with the pairings side by side; one and two
  Standings picks behave as above; no horizontal overflow or clipped names
  at either width.

## 2026-10-11 (follow-up 2): the song stays pinned while you read its comments

- **On a round page, the song being commented on stays in view.** Once a
  track's header scrolls away, a slim bar with its art, title, artist and
  points pins under the top bar while its comments scroll past, and the
  next track's bar takes over when its comments start. A bar rather than
  the whole header, which is about 160px: a third of a phone screen.
- It never moves the page: the bar's wrapper is 0px tall, so showing it
  only overlays. The cards now clip with `overflow: clip` instead of
  `hidden`, which kept anything inside them from sticking.
- **Verified:** suite 211 passing (5 new tests). In a browser at 375px and
  1280px on Round 4: no bar at the top of the page; in a song's comments
  its bar sits exactly under the top bar (107px down on a phone, 63px on
  a desktop); at the next song's header neither shows; in its comments the
  next one does; 0px of layout shift with scroll anchoring off, as on
  Safari; and as a card ends its bar is cut off at the card's edge rather
  than spilling into the gap (screenshot).

## 2026-10-11 (follow-up): taste after four rounds

- **"Who likes whose taste" shows a pair after 4 rounds, down from 5**, so
  Season 3's fills in now rather than after Round 5. A pair gets one chance
  per round they both play: 342 of Season 3's 380 pairs have 4. The other
  38 involve a player who sat out Round 1, and join after Round 5. Season
  3's numbers also gain Biggest fan and Coldest shoulder, which come from
  the same matrix. Seasons 1 and 2 are unchanged (measured: every pair
  there already had 5 or more).
- Silent treatment and Most talked at keep their own minimum of 5; they
  had shared the number in the code, and only the taste matrix was asked
  for.
- The section's note said "five chances" in words; it now reads the
  number from the season file (`tasteMinChances`).
- **Verified:** suite 206 passing (3 new tests, each failing on its own
  break). Built from the real data at 5 and at 4: only Season 3's taste
  and those two highlights differ.

## 2026-10-11: translations

- **Comments and notes in another language show their English
  underneath**, labelled "Translated from Icelandic" (or whichever
  language), inside the comment's own box, original first. On the round
  page, and in any longest-comment or quote card the comment turns up in.
  Asked for after Season 3's Nordic round, where one member wrote 18
  comments in Icelandic and one in Dutch, another wrote two mock-Nordic
  jokes, and a submitter note was in Swedish. Two older ones too: one
  Spanish, one Portuguese. 24 in all, every season checked.
- **Kept by hand, like the Daily Double**, in `data/translations.json`
  (local-only, backed up by `publish.py`): the build has no network or API
  key. Each entry stores the exact text it was made from, and the build
  shows it only while the comment still says that, so a translation can't
  land under the wrong comment; it names any id that matches nothing.
  Translating a new round's non-English comments is now a step in
  "Update the data" (CLAUDE.md), alongside the Daily Double review.
- The three copies of "a comment as a card" in `build.py` (a season's
  longest, the career longest, the quote awards) are one function,
  `comment_card()`, so the translation is added in one place.
- **Verified:** suite 203 passing (8 new tests); each fails on its own
  break in a scratch clone (11 breaks). The real-data build attaches all
  24 and is otherwise identical to a build without them (+2.3 KB on Season
  3). In a browser, Round 4 shows all 22 of its translations, the note's
  "Their note" label styling stays off its translation, and the page has
  no horizontal overflow at 375px or 1280px.

## 2026-10-05 (follow-up 2): code review

- **Members download about 118 KB less** (4.1% of the data files). Each
  finished season's file carried the whole comment matrix, about 46 KB
  that no page shows (only Silent treatment and Most talked at come from
  it, and they're still worked out in the build), plus about 20 smaller
  fields nothing read: `topVote`, `playlistId`, `voterCount`,
  `submissionCount`, `emojiRate`, `uniqueWords`, the raw `vocabRichness`,
  `voteRows`, `chars`, `trackArtist`, `defaultSeason`, `totalSeasons`,
  `bySeason` and a few running totals the build never used. Rebuilt from
  the real exports and compared with the published files, every one is
  identical apart from those keys: no number on the site moves. A new test
  builds a made-up league with something in every section and fails if
  the build writes a field no page reads (a short list of working values
  and the Daily Double record stays, each with its reason).
- **One copy of the shared display helpers.** The initials avatar, the
  reaction glyphs and the "3h ago" times live in `account.js` only;
  `rounds.js` had its own copies, kept in step by tests, and its time had
  drifted anyway: a reply a few days old read as a date on its round page
  but "3d ago" in the inbox. Both now say "2d ago" up to a week, then the
  date. That's the one thing a member could notice.
- **Dead code out:** `PFML.mediaUrl` (the clip was its only user),
  `PFML.client`, the unused `PFMLRounds.roundUrl` export, and every check
  in `app.js`, `rounds.js` and `account.js` for scripts that always load
  first (a test pins that load order now, including `rounds.js`). The
  inbox limit is passed by `account.js` rather than being 40 in two files.
  `app.js` had the "Words they reach for" block twice and its season
  render list twice; each is one now. `rounds.js`'s `plural()`, which
  includes the number unlike `app.js`'s, is renamed `counted()`.
- **Python:** the season-folder scan is one function, `build.season_folders()`,
  where build, publish and enrich_comments each had a copy.
  `enrich_comments.py` takes its labels, comment ids and CSV reader from
  `build.py` instead of keeping copies (its CSV reader had lost the CRLF
  fix). The point budget is its own function, with tests. Stale docstrings
  ("both seasons", "Season 2 did not") fixed.
- **Docs:** README sections back where they belong (the top bar, links
  surviving sign-in, local preview, partly played seasons), the file tree,
  test coverage and comment metrics brought up to date. Ten CHANGELOG
  headings dated 2026-09-22 and 2026-09-23 were work committed on the
  evening of 2026-09-21; relabelled from git history as 2026-09-21
  follow-ups 14 to 23, with the undated members-only entry dated. CLAUDE.md:
  a page stub must now set `PFML.member` and load the real `account.js`.
- **Repo:** a stray `.env - Copy.example` (byte-identical to the template,
  git-ignored, no secret in it) and ten fully merged local branches
  (bundled outside the repo first). `viewer-invites` stays, parked.
- **Verified:** suite 194 passing (6 tests retired with what they pinned,
  9 added); each new test fails on its own break in a scratch clone (11
  breaks). In a browser against the new real-data build: Home, Seasons 1
  and 3 (filtering, comparing), a round page (votes, both kinds of stored
  reaction, replies, the picker and its search), All-Time (sorting) and
  profiles, at 375px and 1280px, with no horizontal overflow and no script
  errors.

## 2026-10-05 (follow-up): deploy timeouts, and a correction

- **Job timeouts go 10 → 30 minutes; the tight bounds move to the steps**
  (5 minutes on the test suite, 10 on the Pages call). A step's clock
  starts when the step runs rather than when it is queued, so this is real
  hang protection; the job numbers are just slack. These jobs finish in
  about 12 seconds when a runner is free.
- **Correction: this does not stop a runner shortage cancelling a deploy,
  which is why it was originally made.** A queued job is cancelled at
  about 15 minutes regardless of `timeout-minutes`. Measured during the
  2026-10-05 Actions outage, zero steps executed both times: the build
  cancelled at 15m02s on `timeout-minutes: 10`, then the deploy cancelled
  at 15m02s on `30`. So that limit is GitHub's, not the job clock, and the
  only remedy during an outage is to re-run afterwards.
- `DeployWorkflow` gained two tests, so nobody tightens the job numbers
  back down to "match" the runtime, and the step bounds stay.

## 2026-10-05: the round clip is gone

- **The site opens on Home again.** The temporary clip gate from
  2026-09-28 is out, as the league organizer asked: `site/watch.html`, the
  check at the top of `auth.js`, the `.watch-*` and `.season-tab.is-locked`
  rules, the clip's line on the features page, and the README section that
  described it. The two media files were deleted from the `league-data`
  bucket, so the clip is nowhere any more.
- `PFML.mediaUrl()` stays. It's general (signed reads of the private
  bucket, which is the only place media can live, since anything under
  `site/` is public) and keeps its own tests.
- Members who watched the clip still have `pfml.clipWatched` in
  localStorage. Nothing reads it now, so it's harmless.

## 2026-09-28 (follow-up): watch the clip to get in

- **Every members-only page now sends people to `/watch`** until the clip
  has played to the end, not just the home page: the check sits at the top
  of `auth.js`, so a bookmark straight to `/season3` bounces too.
- **Home and Season 3 are greyed-out text until it finishes**, with
  "Watch the clip to the end to carry on into the site." under the video;
  they turn into real links when it ends, and the page remembers
  (`pfml.clipWatched` in localStorage), so it's once per browser.
- **No scrubber**: the video has no native controls, so there's nothing to
  drag to the last second. Tap the picture to pause, and a thin bar shows
  progress.
- A soft lock, by design: clearing site data or another browser walks past
  it. A browser that refuses storage is let through rather than trapped,
  and a clip that fails to load unlocks the site rather than shutting
  members out.

## 2026-09-28: the round's clip on the home page (temporary)

- **`pfml.fun/` opens on `/watch`**, a page that plays one video for the
  current round, with Home and Season 3 at the top. Home comes back as
  `/?stay=1`, remembered for that tab, so nothing bounces afterwards. The
  redirect sits in `index.html`'s `<head>`, so the home page never flashes
  first, and a browser with no storage keeps the home page.
- **The clip is members-only, not on the public site.** It's in the
  private `league-data` bucket (`media/s3r2-clip.mp4`, plus a poster
  frame), reached through a new `PFML.mediaUrl()` that hands the page a
  signed URL good for an hour, so it streams and seeks. 78MB of 1080p was
  re-encoded to 11MB: Supabase refuses uploads over 50MB, and members
  watch on phones.
- It waits for a tap. Browsers don't allow sound until someone interacts
  with the page, so a Play button sits over the poster frame.
- Temporary by design: every piece is marked `TEMPORARY`, and README, "The
  round clip (temporary)", lists what to delete.

## 2026-09-22 (follow-up 12): playlist sizes on the Home page

- **Each playlist tile shows its track count and running time** ("99
  tracks · 7 hr 55 min"), stacked on phones. "Open in Spotify" gave way
  to a small &nearr; in the tile's corner; screen readers still hear
  "opens in Spotify". `publish.py` looks the numbers up from Spotify's
  public playlist and embed pages (no key) into
  `site/data/playlist_stats.json`. The embed lists only 100 tracks, so the
  three larger playlists (316 to 648 tracks) show an estimate, "about
  21 hr"; the other five are exact.
- **Season 2 All Submissions** now links to the new playlist (319 tracks).

## 2026-09-22 (follow-up 11): Privacy link, reply drafts

- **Privacy is linked everywhere.** Every page's footer now reads "What
  this site can do · Privacy", and the sign-in card (the only thing a
  signed-out visitor sees; footers are hidden until sign-in) links
  Privacy and the features page. The privacy page gets a footer linking
  back. Checked with the real `auth.js` and a signed-out fake session at
  375px and 1280px.
- **A half-typed reply survives.** Voting, reacting or opening the picker
  on a comment redraws it, which used to replace the reply box with an
  empty one. The draft is now kept per comment and written back, with
  focus and cursor restored, and dropped only once the reply saves; a
  failed send keeps it. Checked in a browser at 375px: vote, reaction and
  failed send each kept a draft (including multi-line text and markup,
  which stays text), and a successful send cleared it.

## 2026-09-22 (follow-up 10): Daily Double checks, sentiment backup

- **Daily Double file is checked before it's used.** Only an exact
  `"accepted"` was applied, so `"Accepted"` or a missing decision dropped
  the bonus without a word, and a missing field or a wrongly shaped file
  crashed with a traceback. Now any decision other than `accepted` or
  `rejected`, an accepted request without its round id, Spotify URI or
  submitter id, or a file of the wrong shape stops the build with a
  message naming the entry. The real Season 3 file passes, and the build
  on the real data gives the same JSON and the same log as before.
- **`publish.py` backs up `data/comment_sentiment.json`** (paid for per
  labelling run) **and `data/track_art.json`** to the private exports
  bucket, alongside the season exports, when they exist.

## 2026-09-22 (follow-up 9): deploy workflow

- **Permissions:** the workflow is read-only by default; only the deploy
  job (which runs no repo code) can write Pages or mint a token. The job
  that runs the tests had both.
- **Actions updated and pinned to commits:** checkout v7.0.1,
  upload-pages-artifact v5.0.0, deploy-pages v5.0.1, plus setup-python
  v7.0.0 so the tests run on Python 3.12 rather than whatever the runner
  ships. Release notes read for each major jump; the one that applies,
  upload-pages-artifact leaving out dotfiles, only drops `.nojekyll`, which
  Actions deploys don't use. configure-pages removed: plain HTML doesn't
  use its output, and it needed Pages access in the test job.
- **Guard** now also refuses CSV and `.env*` files in `site/` (was JSON and
  `data/` only). Checked by running the guard script on a clean copy of
  `site/` (passes) and with a stray `.env.local` or CSV (blocked).
- A new push no longer cancels a deploy in progress; both jobs time out
  after 10 minutes.

## 2026-09-22 (follow-up 8): review pass

A full review of the site, scripts and docs; the low-risk fixes, each with
a test shown to fail without it. Every page was checked at 375px and
1280px on a signed-in local copy (no horizontal overflow, no script errors).

- **Reactions are escaped when drawn.** A reaction is free text in the
  database (1-32 characters), and the round page wrote it into the page
  unescaped, so a member could have stored markup that ran for everyone
  opening that round. The inbox and profile already escaped it. The
  season page's "How X rates everyone else" headings now escape the name
  too.
- **The reaction picker no longer gets stuck open.** Tapping a reaction on
  another comment, or a save that failed, left the open picker on screen
  with its button stuck on close. A tap outside closes it without jumping
  focus (and the page) back to its button.
- **Inbox badge:** opening the inbox before its first load finished left
  the count up; a refresh already in flight when the inbox was opened
  could bring it back.
- **Phones:** the round and profile player menus are 16px on phones (iOS
  zoomed the page when they were tapped); the profile's menu gets the ▾
  the round page's has; hover looks on toggles and cards (vote arrows,
  reaction chips, sort headings, trend chips, pills, cards) apply only on
  devices that really hover, so they don't stick after a tap; the round
  page's playlist pill lines up with the count chips beside it; reduced
  motion covers every card that lifts.
- **Tidying:** the old Comments page's unused CSS and the unused `.n`
  class removed; the red is a `--neg` token, as on the features page;
  `careerTile` reuses `tile`; `api.people()` is fetched once per page, and
  a failed data download can be retried; dead code (`window.__pfmlIndex`,
  an unreachable branch on profiles, an unused import and constant, a
  misspelled key renamed after the fact) removed; error messages no longer
  point members at `site/data/`; `aria-pressed` on the trend buttons;
  `aria-haspopup` removed where the popup isn't a menu. The build's JSON
  on the real data is identical before and after (compared parsed).
- **`enrich_comments.py`:** `--force` kept only the labels from its own
  run, so `--force --season season2` would have wiped every other season's
  paid-for labels; it now starts from the stored file and replaces only
  what it re-labels. An unreadable labels file stops the run instead of
  being overwritten. The batch run no longer says Ctrl-C is safe (the batch
  keeps running and is billed, but its results aren't saved).
- **Docs:** player names out of the CHANGELOG; the README no longer says no
  commit on GitHub holds league data (old commits still load by id,
  re-checked today); the All-Time page's section, the sort note, the Tests
  section, the point budget (16, then 19 in Season 3) and a duplicated
  paragraph corrected; the features page's "tap a name" line said it opens
  the profile (it opens the player focus panel).

## 2026-09-22 (follow-up 7)

- **No .html in any address.** Every link is clean (`/career`, `/season1`,
  `/round?s=...`, `/profile?p=...`, `/` for home); GitHub Pages serves them
  from the same files, query strings included (measured on pfml.fun). Old
  `.html` bookmarks still work, and the page then tidies its own address
  bar, keeping the query and any `#section`.
- **`scripts/serve.py`** previews the site locally with clean addresses
  (Python's plain `http.server` can't), replacing it in the README.

## 2026-09-22 (follow-up 6)

- **Features page opens with a short summary** of the whole site (season
  pages, round pages, All-Time, profiles, inbox, home, signing in), then
  "Tap a section below for the details" above the three section pills.

## 2026-09-22 (follow-up 5)

- **All-time standings columns renamed** "Round Podium Pts" and "Season
  Podium Pts" (were "Round finishes" and "Season podiums"); the note above
  the table and the profile's score breakdown use the same names.

## 2026-09-22 (follow-up 4)

- **All-Time page order**: League Highlights, then All-time standings, then
  Comments, all-time (standings used to come last). The note under the
  standings, shown while the page loads, now describes the Career Score
  rather than the old total-points formula.

## 2026-09-22 (follow-up 3)

- **All 8 playlists are live**: All Podium Tracks, S2 Podium Tracks, S3 All
  Submissions and S3 Podium Tracks added (`site/data/playlists.json`,
  which goes live with `publish.py`).
- **Playlists as tiles** on the home page instead of a row of chips: an
  icon, the group (League-wide, then seasons newest first), the name and
  "Open in Spotify". Four across, a season's pair per row on phones.
- **Fixed: the initials in the account menu sat top-left.** A rule meant
  for the name beside it (`.acct-menu-head span`) also matched the avatar,
  a span, and made it a column. Now scoped to the name.

## 2026-09-22 (follow-up 2)

- **Sentiment script, ready to run** (`scripts/enrich_comments.py`, not
  run yet). Labels are now funny, witty, angry, mean, heartfelt, hot_take,
  appreciative, storytelling and analytical, each with a strength of 1-3,
  so single comments can be crowned. The build turns them into six "judged
  by Claude" quote cards and four player titles on the All-Time page, which
  appear only once `data/comment_sentiment.json` exists. Steps: run
  `--estimate` to see the cost, run it, then `publish.py`.

## 2026-09-22 (follow-up)

- **Comment awards on the All-Time page**, next to the longest comment
  ever written: shortest review, loudest, most excited, most questions,
  most emoji and most words for zero points, each a quote card with the
  comment itself. Counted from the text alone (no AI). Long quotes start
  clipped with a Read all toggle.
- **Profiles show how the Career Score adds up**: Score = Avg season +
  Round finishes + Season podiums, with each part's working.
- **Docs: the sentiment section said to commit `comment_sentiment.json`**
  to make labels live, which predates the members-only setup; it now says
  to run `publish.py`.

## 2026-09-22

- **New Career Score**, chosen by the league after comparing options on
  the real data: 20 x points per round played, plus 3/2/1 for each
  1st/2nd/3rd in a round, plus 6/4/2 for a finished season's podium;
  scored after 10 rounds played. Replaces total points + 10 per round win
  + 5 per podium, which punished missed seasons. A season's podium counts
  once a newer season exists (Seasons 1 and 2 now). Top of the table:
  four players between 375 and 403.
- **All-time standings columns show the score's parts**: Score (now second),
  Avg season, Round finishes (with 1st/2nd/3rd counts), Season podiums
  (with which seasons), Rounds. The per-season points and total moved off
  this table (profiles show them). Players under 10 rounds are listed last
  with "needs 10". The note, profile rank (among scored players) and the
  "Highest career score" highlight follow the new formula.

## 2026-09-21 (follow-up 23)

- **Season page tables scroll sideways on phones too.** Voting style and
  the comment table keep every column (they used to drop one and four),
  names pinned on the left, with the "swipe sideways" line. The comment
  tables' number columns are now at least 72px, because the COMMENTS
  heading (71px) ran into the next column at 56px, on All-Time as well.
  The season comment table also gets the standard space under its awards.

## 2026-09-21 (follow-up 22)

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

## 2026-09-21 (follow-up 21)

- **Names link to profiles almost everywhere**, looking exactly as before:
  season highlights and comment awards (including "Tied with" lines), top
  tracks, the taste table, the voting and comment tables, signature words,
  quotes, the focus panel, and the All-Time highlights, awards and tables.
  Standings rows and the collapsed Standings bar stay as they are (they're
  tap targets already); tapping a row puts the name, as a link, at the top
  of the focus panel.

## 2026-09-21 (follow-up 20)

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

## 2026-09-21 (follow-up 19)

- **Profile tiles fit phones.** The six Career tiles sit three rows of two
  on a phone (smaller boxes, measured 163px wide at 390px, nothing
  overflowing) and stay two rows of three on desktop. The new sixth tile
  is **Top-3 rate**: the share of their tracks that finished in a round's
  top three, so consistency shows, not just wins. Rounds won now shows its
  share of their tracks instead of the podium count.

## 2026-09-21 (follow-up 18)

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

## 2026-09-21 (follow-up 17)

- **Emoji search didn't filter at all.** It set `hidden` on non-matching
  buttons, but the buttons' own CSS `display: inline-grid` beats the
  `hidden` attribute, so nothing ever disappeared (measured: "pizza" left
  1,907 buttons marked hidden and all 1,908 on screen). On desktop only the
  category headings vanished, which looked like partial filtering; on iOS
  it looked like nothing happened. The earlier check counted the attribute,
  not what was displayed, so it passed wrongly.
- **The picker was slow to open.** Correction to follow-up 16: "about 9ms"
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

## 2026-09-21 (follow-up 16)

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

## 2026-09-21 (follow-up 15)

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

## 2026-09-21 (follow-up 14)

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

## 2026-09-21: members-only site and comments page (branch members-only, merged)

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
