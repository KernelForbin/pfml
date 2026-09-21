/* PFML — Round results, on every season page.

   A collapsed "Round results" pill under the leaderboard. Open it for the
   season's rounds, newest first; open a round for every track with every
   vote cast on it, and the comments that came with them. Comments can be
   voted on, reacted to and replied to by members.

   Every round in the export is listed, including one that so far only has
   its prompt: that shows the prompt and says voting hasn't started.

   The track and vote data comes from the season JSON. The member layer
   (comment votes, reactions, replies) comes from the comment_* tables via
   window.PFML.api in auth.js, loaded per round the first time that round
   is opened. Comments are keyed by "<round id>|<spotify uri>|<voter id>",
   the id build.py writes onto each one.

   app.js calls PFMLRounds.render() whenever the season or the Standings
   player selection changes. Which rounds and reply threads are open, and
   the social data already loaded, survive those re-renders. */

(function () {
  "use strict";

  var REACT = { fire: "\uD83D\uDD25", laugh: "\uD83D\uDE02", hundred: "\uD83D\uDCAF",
                eyes: "\uD83D\uDC40", grimace: "\uD83D\uDE2C", heart: "\u2764\uFE0F" };
  var REACT_ORDER = ["fire", "laugh", "hundred", "eyes", "grimace", "heart"];

  var state = {
    host: null,
    d: null,               // season JSON
    names: {},             // competitor id -> name
    selected: [],          // Standings player filter
    open: {},              // round id -> expanded
    social: {},            // round id -> { votes, reactions, replies }, each grouped by comment id
    people: null,          // member user_id -> { name }
    threads: {},           // comment id -> reply thread open
    picker: null,          // comment id with the reaction picker open
    index: {},             // comment id -> ballot row
    busy: false
  };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function plural(n, one, many) { return n + " " + (n === 1 ? one : (many || one + "s")); }
  function api() { return window.PFML && window.PFML.api; }
  function me() { return api() ? api().me() : null; }
  function isAdmin() { return !!(window.PFML && window.PFML.member && window.PFML.member.role === "admin"); }
  function cssEscape(s) { return window.CSS && CSS.escape ? CSS.escape(s) : String(s).replace(/["\\]/g, "\\$&"); }

  function when(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    var mins = Math.round((Date.now() - d.getTime()) / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return mins + "m ago";
    if (mins < 60 * 24) return Math.round(mins / 60) + "h ago";
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }

  function groupBy(rows) {
    var out = {};
    rows.forEach(function (r) { (out[r.comment_id] = out[r.comment_id] || []).push(r); });
    return out;
  }

  function roundIdOf(commentId) { return String(commentId).split("|")[0]; }

  /* ---- the ballots on one track: every vote, plus comment-only rows ---- */

  function ballots(song) {
    var byVoter = {};
    (song.comments || []).forEach(function (c) { byVoter[c.voterId] = c; });
    var seen = {};
    var rows = (song.votes || []).map(function (v) {
      seen[v[0]] = true;
      return { voterId: v[0], name: state.names[v[0]] || (byVoter[v[0]] && byVoter[v[0]].voterName) || "Unknown",
               points: v[1], comment: byVoter[v[0]] || null };
    });
    (song.comments || []).forEach(function (c) {
      if (!seen[c.voterId]) rows.push({ voterId: c.voterId, name: c.voterName, points: 0, comment: c });
    });
    rows.sort(function (a, b) {
      if ((a.points === 0) !== (b.points === 0)) return a.points === 0 ? 1 : -1;   // comment-only last
      return b.points - a.points || a.name.localeCompare(b.name);
    });
    rows.forEach(function (row) { if (row.comment) state.index[row.comment.id] = row; });
    return rows;
  }

  /* ---- member layer for one comment ---- */

  function socialOf(commentId) { return state.social[roundIdOf(commentId)] || null; }

  function votesFor(id) {
    var soc = socialOf(id);
    var rows = (soc && soc.votes[id]) || [];
    var up = 0, down = 0, mine = 0, uid = me();
    rows.forEach(function (v) { if (v.value > 0) up++; else down++; if (v.user_id === uid) mine = v.value; });
    return { up: up, down: down, score: up - down, mine: mine };
  }

  function reactionsFor(id) {
    var soc = socialOf(id);
    var rows = (soc && soc.reactions[id]) || [];
    var uid = me(), by = {};
    rows.forEach(function (r) {
      var e = by[r.reaction] = by[r.reaction] || { count: 0, mine: false, who: [] };
      e.count++;
      if (r.user_id === uid) e.mine = true;
      e.who.push(memberName(r.user_id));
    });
    return by;
  }

  function repliesFor(id) {
    var soc = socialOf(id);
    return (soc && soc.replies[id]) || [];
  }

  function memberName(userId) {
    return (state.people && state.people[userId] && state.people[userId].name) || "A member";
  }

  /* ---- rendering ---- */

  function pointsLabel(p) {
    if (p > 0) return "+" + p;
    if (p < 0) return "\u2212" + Math.abs(p);
    return "comment";
  }

  function socialHtml(c) {
    if (!state.social[roundIdOf(c.id)]) return "";
    var v = votesFor(c.id), reacts = reactionsFor(c.id), replies = repliesFor(c.id);
    var open = !!state.threads[c.id], uid = me(), admin = isAdmin();

    var chips = REACT_ORDER.filter(function (k) { return reacts[k]; }).map(function (k) {
      var r = reacts[k];
      return '<button type="button" class="cm-chip' + (r.mine ? " is-on" : "") + '" data-act="react" data-r="' + k +
        '" title="' + esc(r.who.join(", ")) + '" aria-pressed="' + r.mine + '">' + REACT[k] + " " + r.count + "</button>";
    }).join("");
    var picker = state.picker === c.id
      ? '<span class="cm-picker">' + REACT_ORDER.map(function (k) {
          var on = reacts[k] && reacts[k].mine;
          return '<button type="button" class="cm-pick' + (on ? " is-on" : "") + '" data-act="react" data-r="' + k +
            '" aria-label="' + k + '">' + REACT[k] + "</button>";
        }).join("") + "</span>"
      : "";

    var thread = "";
    if (open) {
      thread = '<div class="cm-thread">' + replies.map(function (r) {
        var canDelete = r.user_id === uid || admin;
        return '<div class="cm-reply"><div class="cm-reply-head"><b>' + esc(memberName(r.user_id)) + "</b> &middot; " +
          esc(when(r.created_at)) +
          (canDelete ? ' &middot; <button type="button" class="cm-link" data-act="delete" data-reply="' + r.id + '">Delete</button>' : "") +
          '</div><div class="cm-reply-body">' + esc(r.body) + "</div></div>";
      }).join("") +
        '<form class="cm-form" data-act="reply">' +
        '<label class="cm-sr" for="r-' + esc(c.id) + '">Reply to ' + esc(c.voterName) + "</label>" +
        '<textarea id="r-' + esc(c.id) + '" maxlength="2000" placeholder="Reply to ' + esc(c.voterName) + '"></textarea>' +
        '<button type="submit" class="cm-send">Reply</button></form></div>';
    }

    return '<div class="cm-bar">' +
      '<span class="cm-vote" title="' + v.up + " up, " + v.down + ' down">' +
        '<button type="button" data-act="vote" data-v="1" class="' + (v.mine > 0 ? "is-on" : "") + '" aria-label="Upvote" aria-pressed="' + (v.mine > 0) + '">&#9650;</button>' +
        '<span class="cm-score">' + v.score + "</span>" +
        '<button type="button" data-act="vote" data-v="-1" class="' + (v.mine < 0 ? "is-on" : "") + '" aria-label="Downvote" aria-pressed="' + (v.mine < 0) + '">&#9660;</button>' +
      "</span>" + chips +
      '<button type="button" class="cm-chip cm-add" data-act="picker" aria-label="Add a reaction">' +
        (state.picker === c.id ? "&times;" : "+&#9786;") + "</button>" + picker +
      '<button type="button" class="cm-link" data-act="thread">' +
        (open ? "Hide replies" : replies.length ? plural(replies.length, "reply", "replies") : "Reply") + "</button>" +
      "</div>" + thread;
  }

  function ballotHtml(row) {
    var hl = state.selected.indexOf(row.voterId) !== -1;
    var c = row.comment;
    return '<div class="rr-ballot' + (hl ? " is-hl" : "") + (c ? " has-comment" : "") + '"' +
      (c ? ' data-id="' + esc(c.id) + '"' : "") + ">" +
      '<div class="rr-ballot-head"><span class="rr-voter">' + esc(row.name) + "</span>" +
      '<span class="rr-pts' + (row.points === 0 ? " is-zero" : row.points < 0 ? " is-neg" : "") + '">' +
      pointsLabel(row.points) + "</span></div>" +
      (c ? '<p class="cm-text">' + esc(c.comment) + "</p>" + socialHtml(c) : "") +
      "</div>";
  }

  function trackHtml(s) {
    var hl = state.selected.indexOf(s.submitterId) !== -1;
    var link = s.spotifyId
      ? '<a href="https://open.spotify.com/track/' + esc(s.spotifyId) + '" target="_blank" rel="noopener">' + esc(s.title) + "</a>"
      : esc(s.title);
    var rows = ballots(s);
    var voteCount = (s.votes || []).length;
    var commentCount = (s.comments || []).length;
    return '<section class="rr-track' + (hl ? " is-hl" : "") + '">' +
      '<div class="rr-track-head"><span class="rr-place">#' + (s.place || "") + "</span>" +
      '<div class="rr-track-info"><div class="rr-track-title">' + link +
      (s.dailyDouble ? ' <span class="dd-badge">Daily Double</span>' : "") + "</div>" +
      '<div class="rr-track-meta">' + esc(s.artistText) + " &middot; submitted by <b>" + esc(s.submitterName) + "</b>" +
      " &middot; " + plural(voteCount, "vote") + (commentCount ? " &middot; " + plural(commentCount, "comment") : "") + "</div></div>" +
      '<span class="rr-track-pts">' + s.points + " <small>pts</small></span></div>" +
      (s.note ? '<p class="rr-note"><span>Submitter\u2019s note</span>' + esc(s.note) + "</p>" : "") +
      (rows.length ? '<div class="rr-ballots">' + rows.map(ballotHtml).join("") + "</div>"
                   : '<p class="rr-none">No votes or comments on this one.</p>') +
      "</section>";
  }

  function winnersLine(r) {
    var top = r.songs.filter(function (s) { return s.place === 1; });
    if (!top.length) return "";
    if (top.length === 1) return "<b>" + esc(top[0].submitterName) + "</b> took it with " + esc(top[0].title);
    return "tie at the top: " + top.map(function (s) { return "<b>" + esc(s.submitterName) + "</b>"; }).join(" &amp; ");
  }

  function roundStatus(r) {
    if (!r.songs.length) return "prompt posted, no submissions yet";
    if (!r.hasVotingActivity) return "submissions in, voting hasn\u2019t started";
    return null;
  }

  function summaryHtml(r, number) {
    var status = roundStatus(r);
    var votes = 0, comments = 0;
    r.songs.forEach(function (s) { votes += (s.votes || []).length; comments += (s.comments || []).length; });
    var sub = status ? esc(status) : winnersLine(r);
    var counts = status ? "" : plural(r.songs.length, "track") + " &middot; " + plural(votes, "vote") + " &middot; " + plural(comments, "comment");
    return '<span><span class="round-title">Round ' + number + ": " + esc(r.name) + "</span>" +
      (sub ? ' <span class="round-sub">&mdash; ' + sub + "</span>" : "") +
      (counts ? '<span class="rr-counts">' + counts + "</span>" : "") + "</span>" +
      '<span class="round-open">' + (state.open[r.id] ? "Hide" : "Open") + "</span>";
  }

  function bodyHtml(r) {
    var head = (r.description ? '<p class="round-desc">' + esc(r.description) + "</p>" : "") +
      (r.playlistUrl ? '<a class="pill" href="' + esc(r.playlistUrl) + '" target="_blank" rel="noopener">Open the round playlist &nearr;</a>' : "");
    var status = roundStatus(r);
    if (status) return head + '<p class="rr-none">Nothing to show yet: ' + esc(status) + ".</p>";
    if (!state.social[r.id]) return head + '<p class="rr-none">Loading votes and comments\u2026</p>';
    var songs = r.songs.slice().sort(function (a, b) { return (a.place || 99) - (b.place || 99); });
    return head + '<div class="rr-tracks">' + songs.map(trackHtml).join("") + "</div>";
  }

  function roundNode(id) {
    return state.host ? state.host.querySelector('.round[data-round="' + cssEscape(id) + '"]') : null;
  }

  function renderRoundBody(r) {
    var det = roundNode(r.id);
    if (!det) return;
    det.querySelector(".round-body").innerHTML = bodyHtml(r);
  }

  /* ---- loading ---- */

  function loadPeople() {
    if (state.people || !api()) return Promise.resolve();
    return api().people().then(function (p) { state.people = p; });
  }

  function loadSocial(roundId) {
    if (!api()) return Promise.resolve();
    return api().loadRound(roundId).then(function (res) {
      state.social[roundId] = { votes: groupBy(res.votes), reactions: groupBy(res.reactions), replies: groupBy(res.replies) };
    });
  }

  function openRound(r) {
    if (roundStatus(r) || state.social[r.id]) { renderRoundBody(r); return; }
    renderRoundBody(r);   // "Loading..."
    Promise.all([loadPeople(), loadSocial(r.id)]).then(function () { renderRoundBody(r); })
      .catch(function (err) {
        var det = roundNode(r.id);
        if (det) det.querySelector(".round-body").insertAdjacentHTML("beforeend",
          '<p class="rr-none">Couldn\u2019t load member votes and replies: ' + esc(err && err.message ? err.message : err) + "</p>");
      });
  }

  /* ---- actions ---- */

  function rerenderBallot(id) {
    var node = state.host.querySelector('.rr-ballot[data-id="' + cssEscape(id) + '"]');
    var row = state.index[id];
    if (!node || !row) return;
    var wrap = document.createElement("div");
    wrap.innerHTML = ballotHtml(row);
    node.replaceWith(wrap.firstChild);
  }

  // Takes a function, not a promise, so nothing is sent while an earlier
  // action is still saving, and a failure always tells the member.
  function refreshAfter(action, id) {
    if (state.busy) return;
    state.busy = true;
    Promise.resolve().then(action).then(function () { return loadSocial(roundIdOf(id)); })
      .then(function () { rerenderBallot(id); })
      .catch(function (err) { alert("That didn\u2019t save: " + (err && err.message ? err.message : err)); })
      .then(function () { state.busy = false; });
  }

  function onClick(ev) {
    var btn = ev.target.closest("[data-act]");
    if (!btn || btn.tagName === "FORM") return;
    var card = btn.closest(".rr-ballot[data-id]");
    if (!card) return;
    var id = card.getAttribute("data-id");
    var act = btn.getAttribute("data-act");

    if (act === "vote") {
      var want = parseInt(btn.getAttribute("data-v"), 10);
      var mine = votesFor(id).mine;
      refreshAfter(function () { return api().setVote(id, mine === want ? 0 : want); }, id);
    } else if (act === "react") {
      var key = btn.getAttribute("data-r");
      var on = reactionsFor(id)[key];
      state.picker = null;
      refreshAfter(function () { return api().toggleReaction(id, key, !(on && on.mine)); }, id);
    } else if (act === "picker") {
      state.picker = state.picker === id ? null : id;
      rerenderBallot(id);
    } else if (act === "thread") {
      state.threads[id] = !state.threads[id];
      rerenderBallot(id);
      if (state.threads[id]) {
        var ta = state.host.querySelector('.rr-ballot[data-id="' + cssEscape(id) + '"] textarea');
        if (ta) ta.focus();
      }
    } else if (act === "delete") {
      if (!confirm("Delete this reply?")) return;
      var replyId = parseInt(btn.getAttribute("data-reply"), 10);
      refreshAfter(function () { return api().deleteReply(replyId); }, id);
    }
  }

  function onSubmit(ev) {
    var form = ev.target.closest('form[data-act="reply"]');
    if (!form) return;
    ev.preventDefault();
    var id = form.closest(".rr-ballot[data-id]").getAttribute("data-id");
    var text = form.querySelector("textarea").value.trim();
    if (!text) return;
    state.threads[id] = true;
    refreshAfter(function () { return api().addReply(id, text); }, id);
  }

  /* ---- entry point ---- */

  function render(host, d, opts) {
    opts = opts || {};
    if (state.d && state.d.key !== d.key) { state.open = {}; state.social = {}; state.threads = {}; state.picker = null; }
    state.host = host;
    state.d = d;
    state.selected = opts.selected || [];
    state.names = {};
    (d.competitors || []).forEach(function (c) { state.names[c.id] = c.name; });

    if (!host.__rrBound) {
      host.addEventListener("click", onClick);
      host.addEventListener("submit", onSubmit);
      host.__rrBound = true;
    }

    host.innerHTML = "";
    if (opts.filterTag) opts.filterTag(host);

    var numbered = d.rounds.map(function (r, i) { return { r: r, n: i + 1 }; });
    var shown = numbered;
    if (state.selected.length) {
      shown = numbered.filter(function (x) {
        return x.r.songs.some(function (s) { return state.selected.indexOf(s.submitterId) !== -1; });
      });
    }

    var count = document.getElementById("rrCount");
    if (count) {
      count.textContent = state.selected.length
        ? shown.length + " of " + plural(d.rounds.length, "round")
        : plural(d.rounds.length, "round");
    }

    if (!d.rounds.length) { host.insertAdjacentHTML("beforeend", '<div class="empty">No rounds posted yet this season.</div>'); return; }
    if (!shown.length) { host.insertAdjacentHTML("beforeend", '<div class="empty">No rounds involve this selection.</div>'); return; }

    var list = document.createElement("div");
    list.className = "rounds-list";
    shown.slice().reverse().forEach(function (x) {
      var r = x.r;
      var det = document.createElement("details");
      det.className = "round";
      det.setAttribute("data-round", r.id);
      det.innerHTML = "<summary>" + summaryHtml(r, x.n) + '</summary><div class="round-body"></div>';
      if (state.open[r.id]) det.open = true;
      det.addEventListener("toggle", function () {
        state.open[r.id] = det.open;
        det.querySelector(".round-open").textContent = det.open ? "Hide" : "Open";
        if (det.open) openRound(r);
      });
      list.appendChild(det);
    });
    host.appendChild(list);

    // re-render any round that was already open (selection changed, etc.)
    shown.forEach(function (x) { if (state.open[x.r.id]) openRound(x.r); });
  }

  window.PFMLRounds = { render: render };
})();
