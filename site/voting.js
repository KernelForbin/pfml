/* PFML - voting on the site (README, Voting on the site).

   Built 2026-10-25, on for seasons set up on the site (PFML.siteVoting in
   account.js). A round that votes here votes on its round page, once
   submissions close (on the Submit page until 2026-10-26):

   - While voting is open, the ballot, inside the round's track list
     (listen.js asks ballot() for it): points on other players' tracks, at
     most max_per_track on one and every point of point_budget spent, and a
     comment on any track, your own included, each in the track's own row.
     Players with a track in the round vote, and its Spectators, who have
     none (README, DJs and Spectators); they can change their ballot until
     voting closes.
   - After, the results (render(), below the list): every track's submitter
     and score, and every vote and comment with who gave it. A submitter who
     didn't vote scores 0 unless the round says otherwise (the user's call,
     2026-10-25).

   It also gives the admin's form its voting fields, and the voting panel
   (change the deadline, close voting now). The database checks every rule
   again (cast_ballot and the site_rounds trigger, supabase/schema.sql), so
   nothing here is trusted. */
(function () {
  "use strict";

  var PFML = window.PFML;
  var NAMES = { spotify: "Spotify", youtube: "YouTube", soundcloud: "SoundCloud" };

  function $(id) { return document.getElementById(id); }
  function api() { return PFML.api; }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function errText(err) { return (err && err.message) || String(err); }

  // Whether this round votes here, with the switch on. Off, a round that
  // votes here looks like any closed round: tracks, no ballot.
  function on(r) { return !!(PFML.siteVoting && r && r.votes_on_site); }

  // Title and artist once the playlists are built; before, the service and
  // the tag, which the track list above shows too
  function trackLabel(s) {
    return s.title
      ? '<span class="vt-name"><b>' + esc(s.title) + "</b>" + (s.artist ? "<small>" + esc(s.artist) + "</small>" : "") + "</span>"
      : '<span class="vt-name"><b>' + esc(NAMES[s.platform] || "A") + " track</b><small>Tag " + esc(s.tag) + "</small></span>";
  }

  // competitor id -> name, from the signed-up members (people())
  function namesOf(people) {
    var out = {};
    Object.keys(people || {}).forEach(function (u) { out[people[u].competitorId] = people[u].name; });
    return out;
  }

  function who(id, names) {
    if (!id) return '<span class="vt-who">A former member</span>';
    return '<a class="vt-who" href="profile?p=' + encodeURIComponent(id) + '">' + PFML.avatar(id, names[id] || "Member") +
      "<span>" + esc(names[id] || "Member") + "</span></a>";
  }

  var state = { round: null, host: null, parts: null, rows: [], mineTags: [], names: {}, spectators: [], points: {}, comments: {},
                savedJson: "[]", savedAt: 0, submittedJson: null, timer: 0, firstChange: 0, saving: null, again: false, failed: "" };

  // Drafts save on their own (asked 2026-10-27): DRAFT_MS after the last
  // point or keystroke, and at least every DRAFT_MAX_MS while someone keeps
  // typing, so a save is never far behind; at once when the page is hidden
  // or left. Each change also goes into this browser's storage first, so
  // even a save that never reached the database isn't lost. A failed save
  // tries again after RETRY_MS. What another device saved comes in when
  // the page is shown or focused again, and every SYNC_MS while it's open,
  // since neither event fires for a page left open on screen, or a window
  // that's only moved behind another (found 2026-10-27: a comment typed on
  // the computer didn't reach the phone's open page).
  var DRAFT_MS = 800, DRAFT_MAX_MS = 4000, RETRY_MS = 10000, SYNC_MS = 15000;

  /* ---- the ballot, in the round's track list (listen.js) ---- */

  // Voting happens in the round's own list on its round page (the user's
  // call, 2026-10-26): each track plays, takes points and takes a comment in
  // the same row, and Shuffle reorders the ballot with the play order.
  // rows: the round's tracks; parts: what listen.js keeps for it, {head,
  // list, bar, redraw}: the rules and who has voted above the list, the
  // list, the points left with Save and Submit below it, and a way to
  // redraw the list. Resolves to what listen.js draws into each track's row
  // (controls beside the track, comment under it) and refresh, to call after
  // each draw; or to null when the reader has no track in the round and so
  // no ballot.
  //
  // Two things are kept: the draft, saved as the reader goes (Save, or on
  // its own), and the ballot they Submit once every point is given, which
  // is the one that counts (cast_ballot). The page opens on the draft, the
  // same on every device; on this browser's own copy instead when that's
  // newer, since it never reached the database.
  function ballot(r, rows, parts) {
    state.round = r;
    state.rows = rows;
    state.parts = parts;
    state.points = {};
    state.comments = {};
    return Promise.all([api().mySubmissions(r.id), api().people(), api().roundVoters(r.id), api().roundSubmitters(r.id),
                        PFML.roundRoster(r)]).then(function (res) {
      var mine = res[0] || [], voters = res[2] || [], submitters = res[3] || [];
      var closes = PFML.closes(r.voting_closes_at);
      state.mineTags = mine.map(function (m) { return m.tag; });
      state.names = namesOf(res[1]);
      // the Spectators who've joined vote too, with no track of their own
      var roster = res[4] || [];
      state.spectators = roster.filter(function (x) { return x.role === "spectator" && x.joined; }).map(function (x) { return x.id; });
      submitters = submitters.concat(state.spectators);
      var spectator = !!PFML.member && state.spectators.indexOf(PFML.member.competitorId) !== -1;
      if (!mine.length && !spectator) {
        parts.head.innerHTML = '<p class="block-note">Only players with a track in this round' + (roster.length ? ", and its Spectators," : "") +
          " vote. Voting closes " + esc(closes.at) +
          " (" + esc(closes.left) + "); the results show here after.</p>" + votedLine(voters, submitters, state.names);
        return null;
      }
      return Promise.all([api().myBallot(r.id), api().myBallotDraft(r.id)]).then(function (saved) {
        var submitted = saved[0] || [], draft = saved[1];
        apply(submitted);
        state.submittedJson = submitted.length ? json() : null;
        if (draft) apply(draft.ballot || []);
        // what the database has: the draft, or else the submitted ballot
        state.savedJson = json();
        state.savedAt = draft ? Date.parse(draft.saved_at) || 0 : 0;
        var local = readLocal();
        if (local && local.at > state.savedAt) apply(local.ballot || []);
        else if (local) clearLocal();
        parts.head.innerHTML = (spectator && !mine.length ? '<p class="block-note vt-rule"><b>You’re a Spectator this round:</b> ' +
            "no track of your own, so every track is yours to vote on.</p>" : "") +
          '<p class="block-note">Give ' + r.point_budget + " points across the " + (mine.length ? "other " : "") + "tracks, at most " + r.max_per_track +
          " on one, right in the list as they play." + (r.downvotes ? " You can also give up to " + r.downvotes +
            (r.downvotes === 1 ? " downvote" : " downvotes") + ", at most " + r.max_down_per_track +
            " on one: they’re optional, and press − below 0 to give them." : "") +
          " Comment on any track" + (mine.length ? ", yours too" : "") + ". Everything saves as you go, on every device you sign in on; " +
          "it counts once you Submit, with every point given. You can change it until voting closes, " +
          esc(closes.at) + " (" + esc(closes.left) + ").</p>" +
          // the penalty is on a track, so it's nothing to a Spectator
          (r.nonvoters_keep_points || !mine.length ? "" : '<p class="block-note vt-rule">Players who don’t submit a ballot score ' +
            (r.downvotes ? "only the downvotes they got" : "0") + " for this round.</p>") +
          votedLine(voters, submitters, state.names);
        // the status in the bar, since the bar stays over the list
        parts.bar.innerHTML = '<div class="vt-bar"><span class="vt-left" id="vtLeft" aria-live="polite"></span>' +
            '<span class="vt-bar-btns"><button type="button" class="sub-btn sub-btn-quiet" id="vtSave">Save</button>' +
            '<button type="button" class="sub-btn" id="vtSubmit">Submit</button></span>' +
            '<span class="sub-msg" id="vtMsg" role="status"></span></div>';
        parts.bar.hidden = false;
        parts.list.addEventListener("click", onBallotClick);
        parts.list.addEventListener("input", onBallotInput);
        $("vtSave").addEventListener("click", function () { saveDraft(); });
        $("vtSubmit").addEventListener("click", submit);
        // leaving or hiding the page saves at once; coming back picks up
        // what another device saved meanwhile
        document.addEventListener("visibilitychange", function () {
          if (document.visibilityState === "hidden") flush();
          else sync();
        });
        window.addEventListener("pagehide", flush);
        window.addEventListener("focus", sync);
        setInterval(function () { if (document.visibilityState === "visible") sync(); }, SYNC_MS);
        if (json() !== state.savedJson) schedule();
        return { controls: controls, comment: commentHtml, refresh: refreshBallot };
      });
    });
  }

  function own(s) { return state.mineTags.indexOf(s.tag) !== -1; }

  // The ballot as it stands, as cast_ballot and save_ballot_draft take it:
  // in the round's order, only the tracks with points or a comment.
  function entries() {
    return state.rows.map(function (s) {
      return { submission: s.id, points: own(s) ? 0 : (state.points[s.id] || 0), comment: (state.comments[s.id] || "").trim() };
    }).filter(function (v) { return v.points !== 0 || v.comment; });
  }
  function json() { return JSON.stringify(entries()); }

  // A ballot or draft from the database (submission or submission_id) into
  // the page's points and comments, replacing what was there.
  function apply(list) {
    state.points = {};
    state.comments = {};
    list.forEach(function (v) {
      var id = v.submission || v.submission_id;
      state.points[id] = v.points || 0;
      state.comments[id] = v.comment || "";
    });
  }

  // This browser's copy of changes not yet saved, for this round and reader.
  function localKey() {
    return "pfml.ballot." + state.round.id + "." + ((PFML.member && PFML.member.competitorId) || "");
  }
  function readLocal() {
    try { return JSON.parse(localStorage.getItem(localKey()) || "null"); } catch (e) { return null; }
  }
  function writeLocal() {
    try { localStorage.setItem(localKey(), JSON.stringify({ ballot: entries(), at: Date.now() })); } catch (e) { /* private mode: the database save still runs */ }
  }
  function clearLocal() {
    try { localStorage.removeItem(localKey()); } catch (e) { /* nothing kept */ }
  }

  // A save soon: DRAFT_MS after this change, but no later than DRAFT_MAX_MS
  // after the first change not yet saved.
  function schedule() {
    var now = Date.now();
    if (!state.firstChange) state.firstChange = now;
    clearTimeout(state.timer);
    state.timer = setTimeout(saveDraft, Math.max(0, Math.min(DRAFT_MS, state.firstChange + DRAFT_MAX_MS - now)));
  }

  function flush() { if (json() !== state.savedJson || state.timer) saveDraft(); }

  // Saves the draft now, unless the database already has it. One save at a
  // time; a change made during one is saved right after it.
  function saveDraft() {
    clearTimeout(state.timer);
    state.timer = 0;
    state.firstChange = 0;
    if (state.saving) { state.again = true; return state.saving; }
    var body = entries(), text = JSON.stringify(body);
    if (text === state.savedJson) { status(); return Promise.resolve(); }
    status("Saving…");
    state.saving = api().saveBallotDraft(state.round.id, body).then(function (at) {
      state.savedJson = text;
      state.savedAt = Date.parse(at) || Date.now();
      state.failed = "";
      if (json() === text) clearLocal();
    }, function (err) {
      console.error(err);
      state.failed = errText(err);
      // the database refusing it (a rule, or voting closed) won't change by
      // waiting; anything else, such as no connection, gets another try
      if (!(err && err.code === "P0001")) state.timer = setTimeout(saveDraft, RETRY_MS);
    }).then(function () {
      state.saving = null;
      if (state.again) { state.again = false; return saveDraft(); }
      refreshBallot();
    });
    return state.saving;
  }

  // What another device saved since this one last did, when this one has
  // nothing of its own waiting.
  function sync() {
    if (state.saving || state.timer || json() !== state.savedJson) return;
    Promise.all([api().myBallot(state.round.id), api().myBallotDraft(state.round.id)]).then(function (saved) {
      var draft = saved[1], before = json(), submittedBefore = state.submittedJson;
      if (state.saving || state.timer || before !== state.savedJson) return;
      apply(saved[0] || []);
      state.submittedJson = (saved[0] || []).length ? json() : null;
      var newer = draft && (Date.parse(draft.saved_at) || 0) > state.savedAt;
      apply(newer ? draft.ballot || [] : JSON.parse(state.savedJson));
      if (newer) {
        state.savedJson = json();
        state.savedAt = Date.parse(draft.saved_at) || 0;
      }
      // a redraw only when the ballot changed, so a check that finds
      // nothing new never takes the reader out of a comment box
      if (json() !== before) redrawKeepingFocus();
      else if (state.submittedJson !== submittedBefore) refreshBallot();
    }).catch(function (err) { console.error(err); });
  }

  // The list drawn again with what came in, and the cursor back in the
  // comment box it was in.
  function redrawKeepingFocus() {
    var el = document.activeElement, li = el && el.classList && el.classList.contains("vt-comment") && el.closest(".sub-track");
    var id = li && li.getAttribute("data-id");
    state.parts.redraw();
    var box = id && state.parts.list.querySelector('.sub-track[data-id="' + id + '"] .vt-comment');
    if (box) { box.focus(); box.setSelectionRange(box.value.length, box.value.length); }
  }

  // The bar's line: where the ballot stands.
  function status(text) {
    var kind = "";
    if (!text) {
      var current = json();
      if (state.failed) { text = "Not saved: " + state.failed; kind = "error"; }
      else if (current !== state.savedJson || state.timer) text = "Saving…";
      else if (state.submittedJson === null && current === "[]") text = "Your points and comments save as you go.";
      else if (state.submittedJson === null) text = "Saved. It counts once you Submit, with every point given.";
      else if (current === state.submittedJson) { text = "Submitted. You can change it until voting closes."; kind = "good"; }
      else text = "Saved. Submit again for these changes to count.";
    }
    var m = $("vtMsg");
    m.textContent = text;
    m.className = "sub-msg" + (kind ? " is-" + kind : "");
  }

  // Beside the track: the points, or "Your track" on the reader's own.
  function controls(s) {
    if (own(s)) return '<span class="vt-own">Your track</span>';
    var title = s.title || ((NAMES[s.platform] || "") + " track");
    return '<span class="vt-step">' +
        '<button type="button" class="vt-step-btn" data-act="minus" aria-label="One point less for ' + esc(title) + '">−</button>' +
        '<output class="vt-pts" aria-label="Points for ' + esc(title) + '">' + (state.points[s.id] || 0) + "</output>" +
        '<button type="button" class="vt-step-btn" data-act="plus" aria-label="One point more for ' + esc(title) + '">+</button>' +
      "</span>";
  }

  // Under it: the comment box, open and ready to type in (the user's call,
  // 2026-10-27), holding what's kept for the track, so a redraw keeps it.
  function commentHtml(s) {
    var title = s.title || ((NAMES[s.platform] || "") + " track");
    return '<div class="vt-comment-box"><textarea class="sub-input vt-comment" maxlength="2000" rows="2" ' +
      'placeholder="Add a comment (optional)" aria-label="Your comment on ' + esc(title) + '">' +
      esc(state.comments[s.id] || "") + "</textarea></div>";
  }

  // "8/12 voted", and who hasn't yet: who, never how.
  function votedLine(voters, submitters, names) {
    var done = {};
    voters.forEach(function (id) { done[id] = true; });
    // one id per track: each submitter once
    submitters = submitters.filter(function (id, i) { return submitters.indexOf(id) === i; });
    var waiting = submitters.filter(function (id) { return !done[id]; });
    return '<p class="vt-count"><b>' + voters.length + "/" + submitters.length + "</b> voted" +
      (waiting.length ? '<span class="vt-waiting">Still to vote: ' +
        waiting.map(function (id) { return esc(names[id] || "a member"); }).join(", ") + "</span>" : "") + "</p>";
  }

  // Upvotes given, and downvotes given (as a positive number).
  function spent() {
    return Object.keys(state.points).reduce(function (sum, id) { return sum + Math.max(state.points[id] || 0, 0); }, 0);
  }
  function downs() {
    return Object.keys(state.points).reduce(function (sum, id) { return sum - Math.min(state.points[id] || 0, 0); }, 0);
  }

  // The running total, the +/- buttons each allow, the status, and Submit
  // only once every upvote is placed, with downvotes optional up to their
  // limit (the same rules cast_ballot holds), and something new to submit.
  function refreshBallot() {
    var r = state.round, left = r.point_budget - spent(), down = downs(), downLeft = (r.downvotes || 0) - down;
    // short, to fit beside Save and Submit on a phone
    $("vtLeft").innerHTML = (left > 0 ? "<b>" + left + "</b> " + (left === 1 ? "point" : "points") + " left"
      : left === 0 ? "All " + r.point_budget + " points given" : "<b>" + (-left) + "</b> too many") +
      (r.downvotes ? '<span class="vt-down-left">' + down + " of " + r.downvotes + " downvotes</span>" : "");
    $("vtLeft").classList.toggle("is-done", left === 0);
    state.parts.list.querySelectorAll(".sub-track[data-id]").forEach(function (li) {
      var id = li.getAttribute("data-id"), pts = state.points[id] || 0;
      var out = li.querySelector(".vt-pts");
      if (!out) return;
      out.textContent = pts < 0 ? "−" + (-pts) : pts;
      li.classList.toggle("has-points", pts > 0);
      li.classList.toggle("has-down", pts < 0);
      li.querySelector('[data-act="minus"]').disabled = pts <= 0 && (pts <= -(r.max_down_per_track || 0) || downLeft <= 0);
      li.querySelector('[data-act="plus"]').disabled = pts >= r.max_per_track || (pts >= 0 && left <= 0);
    });
    var unchanged = state.submittedJson !== null && json() === state.submittedJson;
    $("vtSubmit").disabled = left !== 0 || downLeft < 0 || unchanged;
    $("vtSubmit").textContent = state.submittedJson === null ? "Submit" : unchanged ? "Submitted" : "Submit changes";
    status();
  }

  function onBallotClick(ev) {
    var b = ev.target.closest("button[data-act]");
    if (!b) return;
    var id = b.closest(".sub-track").getAttribute("data-id"), act = b.getAttribute("data-act");
    var pts = state.points[id] || 0, r = state.round;
    // below 0 only in a round with downvotes
    state.points[id] = Math.max(-(r.max_down_per_track || 0), Math.min(r.max_per_track, pts + (act === "plus" ? 1 : -1)));
    changed();
  }

  function onBallotInput(ev) {
    if (!ev.target.classList.contains("vt-comment")) return;
    state.comments[ev.target.closest(".sub-track").getAttribute("data-id")] = ev.target.value;
    changed();
  }

  // Every point and keystroke: kept in this browser at once, saved soon.
  function changed() {
    state.failed = "";
    writeLocal();
    schedule();
    refreshBallot();
  }

  // The ballot that counts: every point given (Submit is off until then).
  // The draft follows it, so every device opens on what was submitted.
  function submit() {
    var r = state.round, body = entries(), text = JSON.stringify(body);
    $("vtSubmit").disabled = true;
    status("Submitting…");
    api().castBallot(r.id, body).then(function () {
      state.submittedJson = text;
      // the voters' lounge opens to a voter (lounge.js)
      document.dispatchEvent(new CustomEvent("pfml:ballot-submitted"));
      return saveDraft();
    }).then(function () {
      return Promise.all([api().roundVoters(r.id), api().roundSubmitters(r.id), api().people()]).then(function (res) {
        var line = state.parts.head.querySelector(".vt-count");
        if (line) line.outerHTML = votedLine(res[0] || [], (res[1] || []).concat(state.spectators), namesOf(res[2]));
      });
    }).then(refreshBallot, function (err) {
      refreshBallot();
      status("Not submitted: " + errText(err));
      $("vtMsg").className = "sub-msg is-error";
    });
  }

  /* ---- results, once voting has closed ---- */

  // Below the round page's listening, in its own section (host): every
  // track by score, with who sent it and every vote.
  function render(r, host) {
    state.host = host;
    if (!on(r) || PFML.roundPhase(r) !== "finished") { host.hidden = true; host.innerHTML = ""; return; }
    state.round = r;
    host.innerHTML = '<p class="block-note">Loading the results…</p>';
    host.hidden = false;
    Promise.all([api().roundSubmissions(r.id), api().people(), api().roundResults(r.id), api().roundVotes(r.id)]).then(function (res) {
      if (state.round !== r) return;
      state.rows = PFML.roundOrder(r.id, res[0] || []);
      renderResults(r, res[2] || [], res[3] || [], namesOf(res[1]));
    }).catch(function (err) {
      console.error(err);
      host.innerHTML = '<p class="sub-msg is-error">Couldn’t load the results: ' + esc(errText(err)) + "</p>";
    });
  }

  function renderResults(r, results, votes, names) {
    var host = state.host;
    if (!results.length) {
      host.innerHTML = '<h2>Results</h2><p class="block-note">The results show here once voting has closed.</p>';
      return;
    }
    var byId = {}, votesBy = {};
    results.forEach(function (x) { byId[x.submission_id] = x; });
    votes.forEach(function (v) { (votesBy[v.submission_id] = votesBy[v.submission_id] || []).push(v); });
    var list = state.rows.map(function (s) {
      return { s: s, res: byId[s.id] || { points: 0, earned: 0, voted: false, competitor_id: null } };
    }).sort(function (a, b) {
      return b.res.points - a.res.points || b.res.earned - a.res.earned || (a.s.tag < b.s.tag ? -1 : 1);
    });
    var ended = new Date(r.voting_closed_at || r.voting_closes_at).toLocaleDateString(undefined, { month: "long", day: "numeric" });
    host.innerHTML = "<h2>Results</h2>" +
      '<p class="block-note">Voting closed ' + esc(ended) + ". Every track, who sent it, and every vote; tap a track for its votes.</p>" +
      '<ol class="vt-results">' + list.map(function (item) {
        var rank = 1 + list.filter(function (o) { return o.res.points > item.res.points; }).length;
        return resultRow(r, item, rank, votesBy[item.s.id] || [], names);
      }).join("") + "</ol>";
  }

  function resultRow(r, item, rank, votes, names) {
    var res = item.res;
    var note = !res.voted && !r.nonvoters_keep_points
      ? '<p class="vt-note">Didn’t vote, so ' + (r.downvotes ? "only its downvotes count" : "it scores 0") +
        (res.earned !== res.points ? " (voters gave it " + res.earned + ")" : "") + ".</p>" : "";
    return '<li class="vt-res' + (rank === 1 ? " is-first" : "") + '"><details>' +
      "<summary>" +
        '<span class="vt-rank">' + rank + "</span>" +
        '<span class="vt-res-track">' + trackLabel(item.s) + who(res.competitor_id, names) + "</span>" +
        '<span class="vt-score"><b>' + (res.points < 0 ? "−" + (-res.points) : res.points) + "</b> " + (res.points === 1 ? "pt" : "pts") + "</span>" +
      "</summary>" + (item.s.note ? '<p class="vt-track-note">' + esc(item.s.note) + "</p>" : "") + note +
      (votes.length ? '<ul class="vt-votes">' + votes.map(function (v) {
        return '<li><span class="vt-vote-who">' + who(v.voter_id, names) +
          (v.points ? '<span class="vt-vote-pts' + (v.points < 0 ? " is-down" : "") + '">' + (v.points > 0 ? "+" + v.points : "−" + (-v.points)) + "</span>" : "") + "</span>" +
          (v.comment ? '<p class="vt-vote-comment">' + esc(v.comment) + "</p>" : "") + "</li>";
      }).join("") + "</ul>" : '<p class="vt-note">No votes.</p>') +
    "</details></li>";
  }

  /* ---- the admin's fields and panel ---- */

  function localInput(iso) {
    var d = new Date(iso), pad = function (n) { return (n < 10 ? "0" : "") + n; };
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) + "T" + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }

  // In the Commissioner page's round form: an open round that votes here
  // can change its voting deadline and rules until submissions close. A
  // round votes here only as part of a season set up on the site (the
  // user's call, 2026-10-25), so a round opened from this form never does,
  // and one that votes in Music League can never be switched (the database
  // refuses both).
  function adminFields(r) {
    if (!PFML.siteVoting || !r || !r.votes_on_site) return "";
    return '<fieldset class="vt-admin"><legend>Votes on pfml.fun</legend>' +
      '<div class="vt-admin-body" id="vtAdmBody">' +
        '<label class="sub-label" for="vtAdmCloses">Voting closes (your time)</label>' +
        '<input class="sub-input" id="vtAdmCloses" type="datetime-local" value="' + localInput(r.voting_closes_at) + '">' +
        '<label class="sub-label" for="vtAdmBudget">Points each voter gives</label>' +
        '<input class="sub-input vt-num" id="vtAdmBudget" type="number" min="1" max="100" value="' + r.point_budget + '">' +
        '<label class="sub-label" for="vtAdmMax">Most points on one track</label>' +
        '<input class="sub-input vt-num" id="vtAdmMax" type="number" min="1" max="100" value="' + r.max_per_track + '">' +
        '<label class="sub-label" for="vtAdmDown">Downvotes each voter may give (0 for none)</label>' +
        '<input class="sub-input vt-num" id="vtAdmDown" type="number" min="0" max="20" value="' + (r.downvotes || 0) + '">' +
        '<label class="sub-label" for="vtAdmDownMax">Most downvotes on one track</label>' +
        '<input class="sub-input vt-num" id="vtAdmDownMax" type="number" min="0" max="20" value="' + (r.max_down_per_track || 0) + '">' +
        '<label class="vt-check"><input type="checkbox" id="vtAdmKeep"' + (r.nonvoters_keep_points ? " checked" : "") + "> Players who don’t vote keep their points</label>" +
      "</div></fieldset>";
  }

  // The voting fields to save with the round, or a message saying what's
  // wrong. closesAt: when submissions close, as the form has it.
  function readAdmin(r, closesAt) {
    if (!$("vtAdmBody") || !r) return { fields: {} };
    var votingCloses = $("vtAdmCloses").value ? new Date($("vtAdmCloses").value) : null;
    var budget = +$("vtAdmBudget").value, max = +$("vtAdmMax").value;
    var down = +$("vtAdmDown").value, downMax = +$("vtAdmDownMax").value;
    if (!votingCloses || isNaN(votingCloses)) return { error: "Pick when voting closes." };
    if (votingCloses <= closesAt) return { error: "Voting has to close after submissions do." };
    if (!(budget >= 1 && budget <= 100 && budget % 1 === 0)) return { error: "Points each voter gives: a whole number from 1 to 100." };
    if (!(max >= 1 && max <= budget && max % 1 === 0)) return { error: "Most points on one track: a whole number from 1 up to the points each voter gives." };
    if (!(down >= 0 && down <= 20 && down % 1 === 0)) return { error: "Downvotes: a whole number from 0 to 20." };
    // no downvotes means none on a track either; otherwise 1 up to all of them
    if (!down) downMax = 0;
    else if (!(downMax >= 1 && downMax <= down && downMax % 1 === 0)) return { error: "Most downvotes on one track: a whole number from 1 up to the downvotes." };
    return { fields: { voting_closes_at: votingCloses.toISOString(), point_budget: budget, max_per_track: max,
                       nonvoters_keep_points: $("vtAdmKeep").checked, downvotes: down, max_down_per_track: downMax } };
  }

  // For a round in voting: move the deadline, or close voting now.
  function adminPanel(r, done, fail) {
    if (!on(r) || PFML.roundPhase(r) !== "voting") return null;
    var box = document.createElement("div");
    box.className = "vt-admin-panel";
    box.innerHTML = "<h3>Voting: " + esc(r.name) + "</h3>" +
      '<label class="sub-label" for="vtAdmMove">Voting closes (your time)</label>' +
      '<input class="sub-input" id="vtAdmMove" type="datetime-local" value="' + localInput(r.voting_closes_at) + '">' +
      '<div class="sub-actions"><button type="button" class="sub-btn" id="vtAdmMoveSave">Save the deadline</button>' +
        '<button type="button" class="sub-btn sub-btn-quiet" id="vtAdmStop">Close voting now</button></div>';
    box.querySelector("#vtAdmMoveSave").addEventListener("click", function () {
      var at = box.querySelector("#vtAdmMove").value ? new Date(box.querySelector("#vtAdmMove").value) : null;
      if (!at || isNaN(at) || at.getTime() <= Date.now()) { fail("The new deadline has to be in the future."); return; }
      api().updateSiteRound(r.id, { voting_closes_at: at.toISOString() }).then(done, function (err) { fail(errText(err)); });
    });
    box.querySelector("#vtAdmStop").addEventListener("click", function () {
      if (!window.confirm("Close voting for “" + r.name + "” now? The results show straight away, with who sent each track.")) return;
      api().updateSiteRound(r.id, { voting_closed_at: new Date().toISOString() }).then(done, function (err) { fail(errText(err)); });
    });
    return box;
  }

  window.PFMLVoting = { on: on, ballot: ballot, render: render, adminFields: adminFields, readAdmin: readAdmin, adminPanel: adminPanel };
})();
