/* PFML - voting on the site (README, Voting on the site).

   Built 2026-10-25 and off until the user switches it on (PFML.siteVoting
   in account.js). For a round opened with site voting, the Submit page hands
   this the round once submissions close:

   - While voting is open, the ballot: points on other players' tracks, at
     most max_per_track on one and every point of point_budget spent, and a
     comment on any track, your own included. Only players with a track in
     the round vote, and they can change their ballot until voting closes.
   - After, the results: every track's submitter and score, and every vote
     and comment with who gave it. A submitter who didn't vote scores 0
     unless the round says otherwise (the user's call, 2026-10-25).

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

  // The Submit page's order: playlist order once built, by tag before.
  function ordered(rows) {
    return rows.slice().sort(function (a, b) {
      if (a.position && b.position) return a.position - b.position;
      return a.tag < b.tag ? -1 : 1;
    });
  }

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

  var state = { round: null, rows: [], mineTag: null, points: {}, comments: {}, dirty: false };

  /* ---- the Submit page's voting section ---- */

  // r: the round; mine: the reader's own submission ({tag, ...}) or null.
  function render(r, mine) {
    var host = $("subVote");
    var phase = on(r) ? PFML.roundPhase(r) : "";
    if (phase !== "voting" && phase !== "finished") { host.hidden = true; host.innerHTML = ""; return; }
    state.round = r;
    state.mineTag = mine ? mine.tag : null;
    host.innerHTML = '<p class="block-note">Loading the voting…</p>';
    host.hidden = false;
    var loads = [api().roundSubmissions(r.id), api().people()];
    if (phase === "voting") {
      loads.push(state.mineTag ? api().myBallot(r.id) : Promise.resolve([]), api().roundVoters(r.id), api().roundSubmitters(r.id));
    } else {
      loads.push(api().roundResults(r.id), api().roundVotes(r.id));
    }
    Promise.all(loads).then(function (res) {
      if (state.round !== r) return;
      state.rows = ordered(res[0] || []);
      var names = namesOf(res[1]);
      if (phase === "voting") renderBallot(r, res[2] || [], res[3] || [], res[4] || [], names);
      else renderResults(r, res[2] || [], res[3] || [], names);
    }).catch(function (err) {
      console.error(err);
      host.innerHTML = '<p class="sub-msg is-error">Couldn’t load the voting: ' + esc(errText(err)) + "</p>";
    });
  }

  // "8/12 voted", and who hasn't yet: who, never how.
  function votedLine(voters, submitters, names) {
    var done = {};
    voters.forEach(function (id) { done[id] = true; });
    var waiting = submitters.filter(function (id) { return !done[id]; });
    return '<p class="vt-count"><b>' + voters.length + "/" + submitters.length + "</b> voted" +
      (waiting.length ? '<span class="vt-waiting">Still to vote: ' +
        waiting.map(function (id) { return esc(names[id] || "a member"); }).join(", ") + "</span>" : "") + "</p>";
  }

  function renderBallot(r, saved, voters, submitters, names) {
    var host = $("subVote");
    var closes = PFML.closes(r.voting_closes_at);
    if (!state.mineTag) {
      host.innerHTML = "<h2>Voting</h2>" +
        '<p class="block-note">Only players with a track in this round vote. Voting closes ' + esc(closes.at) +
        " (" + esc(closes.left) + "); the results show here after.</p>" + votedLine(voters, submitters, names);
      return;
    }
    state.points = {};
    state.comments = {};
    state.dirty = false;
    saved.forEach(function (v) {
      state.points[v.submission_id] = v.points;
      state.comments[v.submission_id] = v.comment || "";
    });
    host.innerHTML = "<h2>Your ballot</h2>" +
      '<p class="block-note">Give ' + r.point_budget + " points across the other tracks, at most " + r.max_per_track +
      " on one. Add a comment on any track, yours too. You can change your ballot until voting closes, " +
      esc(closes.at) + " (" + esc(closes.left) + ").</p>" +
      (r.nonvoters_keep_points ? "" : '<p class="block-note vt-rule">Players who don’t vote score 0 for this round.</p>') +
      votedLine(voters, submitters, names) +
      '<ol class="vt-list">' + state.rows.map(ballotRow).join("") + "</ol>" +
      '<div class="vt-bar"><span class="vt-left" id="vtLeft" aria-live="polite"></span>' +
        '<button type="button" class="sub-btn" id="vtSave">' + (saved.length ? "Update ballot" : "Save ballot") + "</button></div>" +
      '<p class="sub-msg" id="vtMsg" role="status" hidden></p>';
    host.onclick = onBallotClick;
    host.oninput = onBallotInput;
    $("vtSave").addEventListener("click", save);
    refreshBallot();
  }

  function ballotRow(s) {
    var own = s.tag === state.mineTag;
    var pts = state.points[s.id] || 0;
    var comment = state.comments[s.id] || "";
    var title = s.title || ((NAMES[s.platform] || "") + " track");
    return '<li class="vt-row' + (own ? " is-own" : "") + '" data-id="' + esc(s.id) + '">' +
      '<div class="vt-main">' +
        (s.position ? '<span class="sub-pos">' + s.position + "</span>" : "") + trackLabel(s) +
        (own ? '<span class="vt-own">Your track</span>'
             : '<span class="vt-step">' +
                 '<button type="button" class="vt-step-btn" data-act="minus" aria-label="One point less for ' + esc(title) + '">−</button>' +
                 '<output class="vt-pts" aria-label="Points for ' + esc(title) + '">' + pts + "</output>" +
                 '<button type="button" class="vt-step-btn" data-act="plus" aria-label="One point more for ' + esc(title) + '">+</button>' +
               "</span>") +
      "</div>" +
      '<button type="button" class="vt-comment-btn" data-act="comment" aria-expanded="' + !!comment + '">' + (comment ? "Comment" : "Add a comment") + "</button>" +
      '<textarea class="sub-input vt-comment" maxlength="2000" rows="2" aria-label="Your comment on ' + esc(title) + '"' +
        (comment ? "" : " hidden") + ">" + esc(comment) + "</textarea>" +
    "</li>";
  }

  function spent() {
    return Object.keys(state.points).reduce(function (sum, id) { return sum + (state.points[id] || 0); }, 0);
  }

  // The running total, the +/- buttons each allow, and Save only once every
  // point is placed (the same rule cast_ballot holds).
  function refreshBallot() {
    var r = state.round, left = r.point_budget - spent();
    $("vtLeft").innerHTML = left > 0 ? "<b>" + left + "</b> of " + r.point_budget + " points left"
      : left === 0 ? "All " + r.point_budget + " points given" : "<b>" + (-left) + "</b> too many";
    $("vtLeft").classList.toggle("is-done", left === 0);
    $("subVote").querySelectorAll(".vt-row").forEach(function (li) {
      var id = li.getAttribute("data-id"), pts = state.points[id] || 0;
      var out = li.querySelector(".vt-pts");
      if (!out) return;
      out.textContent = pts;
      li.classList.toggle("has-points", pts > 0);
      li.querySelector('[data-act="minus"]').disabled = pts <= 0;
      li.querySelector('[data-act="plus"]').disabled = pts >= r.max_per_track || left <= 0;
    });
    $("vtSave").disabled = left !== 0;
  }

  function onBallotClick(ev) {
    var b = ev.target.closest("button[data-act]");
    if (!b) return;
    var li = b.closest(".vt-row"), id = li.getAttribute("data-id"), act = b.getAttribute("data-act");
    if (act === "comment") {
      var box = li.querySelector(".vt-comment");
      box.hidden = !box.hidden;
      b.setAttribute("aria-expanded", String(!box.hidden));
      b.textContent = box.hidden && !box.value.trim() ? "Add a comment" : "Comment";
      if (!box.hidden) box.focus();
      return;
    }
    var pts = state.points[id] || 0;
    state.points[id] = Math.max(0, Math.min(state.round.max_per_track, pts + (act === "plus" ? 1 : -1)));
    changed();
    refreshBallot();
  }

  function onBallotInput(ev) {
    if (!ev.target.classList.contains("vt-comment")) return;
    state.comments[ev.target.closest(".vt-row").getAttribute("data-id")] = ev.target.value;
    changed();
  }

  function changed() {
    state.dirty = true;
    $("vtMsg").hidden = true;
  }

  function message(text, kind) {
    var m = $("vtMsg");
    m.textContent = text;
    m.className = "sub-msg" + (kind ? " is-" + kind : "");
    m.hidden = !text;
  }

  function save() {
    var r = state.round;
    var ballot = state.rows.map(function (s) {
      return { submission: s.id, points: s.tag === state.mineTag ? 0 : (state.points[s.id] || 0),
               comment: (state.comments[s.id] || "").trim() };
    }).filter(function (v) { return v.points > 0 || v.comment; });
    $("vtSave").disabled = true;
    api().castBallot(r.id, ballot).then(function () {
      state.dirty = false;
      $("vtSave").textContent = "Update ballot";
      message("Ballot saved. You can change it until voting closes.", "good");
      return Promise.all([api().roundVoters(r.id), api().roundSubmitters(r.id), api().people()]).then(function (res) {
        var line = $("subVote").querySelector(".vt-count");
        if (line) line.outerHTML = votedLine(res[0] || [], res[1] || [], namesOf(res[2]));
      });
    }).catch(function (err) {
      message(errText(err), "error");
    }).then(refreshBallot);
  }

  /* ---- results, once voting has closed ---- */

  function renderResults(r, results, votes, names) {
    var host = $("subVote");
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
      ? '<p class="vt-note">Didn’t vote, so it scores 0' + (res.earned ? " (voters gave it " + res.earned + ")" : "") + ".</p>" : "";
    return '<li class="vt-res' + (rank === 1 ? " is-first" : "") + '"><details>' +
      "<summary>" +
        '<span class="vt-rank">' + rank + "</span>" +
        '<span class="vt-res-track">' + trackLabel(item.s) + who(res.competitor_id, names) + "</span>" +
        '<span class="vt-score"><b>' + res.points + "</b> " + (res.points === 1 ? "pt" : "pts") + "</span>" +
      "</summary>" + note +
      (votes.length ? '<ul class="vt-votes">' + votes.map(function (v) {
        return '<li><span class="vt-vote-who">' + who(v.voter_id, names) +
          (v.points ? '<span class="vt-vote-pts">+' + v.points + "</span>" : "") + "</span>" +
          (v.comment ? '<p class="vt-vote-comment">' + esc(v.comment) + "</p>" : "") + "</li>";
      }).join("") + "</ul>" : '<p class="vt-note">No votes.</p>') +
    "</details></li>";
  }

  /* ---- the admin's fields and panel ---- */

  function localInput(iso) {
    var d = new Date(iso), pad = function (n) { return (n < 10 ? "0" : "") + n; };
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) + "T" + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }

  // In the admin's round form. A new round can be opened to vote here; an
  // open one that votes here can change its deadline and rules until
  // submissions close. One that votes in Music League can never be
  // switched (the database refuses), so it gets nothing.
  function adminFields(r) {
    if (!PFML.siteVoting || (r && !r.votes_on_site)) return "";
    var budget = r ? r.point_budget : 19, max = r ? r.max_per_track : 5, keep = r ? r.nonvoters_keep_points : false;
    return '<fieldset class="vt-admin">' +
      (r ? "<legend>Votes on pfml.fun</legend>"
         : '<label class="vt-check"><input type="checkbox" id="vtAdmOn"> Vote on pfml.fun, not Music League</label>' +
           '<p class="block-note">Chosen now and fixed: a round can’t switch later.</p>') +
      '<div class="vt-admin-body" id="vtAdmBody"' + (r ? "" : " hidden") + ">" +
        '<label class="sub-label" for="vtAdmCloses">Voting closes (your time)</label>' +
        '<input class="sub-input" id="vtAdmCloses" type="datetime-local" value="' + (r ? localInput(r.voting_closes_at) : "") + '">' +
        '<label class="sub-label" for="vtAdmBudget">Points each voter gives</label>' +
        '<input class="sub-input vt-num" id="vtAdmBudget" type="number" min="1" max="100" value="' + budget + '">' +
        '<label class="sub-label" for="vtAdmMax">Most points on one track</label>' +
        '<input class="sub-input vt-num" id="vtAdmMax" type="number" min="1" max="100" value="' + max + '">' +
        '<label class="vt-check"><input type="checkbox" id="vtAdmKeep"' + (keep ? " checked" : "") + "> Players who don’t vote keep their points</label>" +
      "</div></fieldset>";
  }

  function wireAdmin() {
    var box = $("vtAdmOn");
    if (box) box.addEventListener("change", function () { $("vtAdmBody").hidden = !box.checked; });
  }

  // The voting fields to save with the round, or a message saying what's
  // wrong. closesAt: when submissions close, as the form has it.
  function readAdmin(r, closesAt) {
    if (!$("vtAdmBody") || (!r && !$("vtAdmOn").checked)) return { fields: {} };
    var votingCloses = $("vtAdmCloses").value ? new Date($("vtAdmCloses").value) : null;
    var budget = +$("vtAdmBudget").value, max = +$("vtAdmMax").value;
    if (!votingCloses || isNaN(votingCloses)) return { error: "Pick when voting closes." };
    if (votingCloses <= closesAt) return { error: "Voting has to close after submissions do." };
    if (!(budget >= 1 && budget <= 100 && budget % 1 === 0)) return { error: "Points each voter gives: a whole number from 1 to 100." };
    if (!(max >= 1 && max <= budget && max % 1 === 0)) return { error: "Most points on one track: a whole number from 1 up to the points each voter gives." };
    var fields = { voting_closes_at: votingCloses.toISOString(), point_budget: budget, max_per_track: max,
                   nonvoters_keep_points: $("vtAdmKeep").checked };
    if (!r) fields.votes_on_site = true;
    return { fields: fields };
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

  window.PFMLVoting = { on: on, render: render, adminFields: adminFields, wireAdmin: wireAdmin,
                        readAdmin: readAdmin, adminPanel: adminPanel };
})();
