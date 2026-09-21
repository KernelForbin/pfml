/* PFML — rounds.

   Two views:

   1. renderList(): on a season page, inside the collapsed "Round results"
      pill under the leaderboard, one card per round (newest first) that
      links to that round's own page.

   2. renderRoundPage(): round.html?s=<season key>&r=<round id>. The whole
      round on its own full-width page, modelled on how Music League itself
      shows a finished round: a card per track with its album art, place,
      points and voter count, who submitted it, then every voter's points
      and comment. Comments carry the member layer: up/down votes,
      reactions and replies.

   Track and vote data comes from the season JSON; album art is an optional
   "art" URL per track (cached by scripts/publish.py). The member layer
   comes from the comment_* tables through window.PFML.api (auth.js).
   Comments are keyed "<round id>|<spotify uri>|<voter id>", the id build.py
   writes on each one. */

(function () {
  "use strict";

  var REACT = { fire: "\uD83D\uDD25", laugh: "\uD83D\uDE02", hundred: "\uD83D\uDCAF",
                eyes: "\uD83D\uDC40", grimace: "\uD83D\uDE2C", heart: "\u2764\uFE0F" };
  var REACT_ORDER = ["fire", "laugh", "hundred", "eyes", "grimace", "heart"];

  var state = {
    host: null,            // element holding the round page's tracks
    names: {},             // competitor id -> name
    social: null,          // { votes, reactions, replies }, each grouped by comment id
    people: null,          // member user_id -> { name }
    threads: {},           // comment id -> reply thread open
    picker: null,          // comment id with the reaction picker open
    index: {},             // comment id -> vote row
    busy: false
  };

  /* ---- small helpers ---- */

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

  function ordinal(n) {
    var s = ["th", "st", "nd", "rd"], v = n % 100;
    return n + (s[(v - 20) % 10] || s[v] || s[0]);
  }

  function when(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    var mins = Math.round((Date.now() - d.getTime()) / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return mins + "m ago";
    if (mins < 60 * 24) return Math.round(mins / 60) + "h ago";
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }

  function dateOf(iso) {
    var d = new Date(iso);
    return isNaN(d.getTime()) ? "" : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  }

  function groupBy(rows) {
    var out = {};
    rows.forEach(function (r) { (out[r.comment_id] = out[r.comment_id] || []).push(r); });
    return out;
  }

  // Initials in a coloured circle, standing in for the profile photos
  // Music League has and the export doesn't. The colour is fixed per
  // player (from their id), so the same person always looks the same.
  function avatar(id, name) {
    var words = String(name || "?").trim().split(/\s+/);
    var initials = (words.length > 1 ? words[0][0] + words[words.length - 1][0] : String(name || "?").slice(0, 2)).toUpperCase();
    var h = 0;
    String(id || name).split("").forEach(function (c) { h = (h * 31 + c.charCodeAt(0)) % 360; });
    return '<span class="av" style="background:hsl(' + h + ',48%,42%)" aria-hidden="true">' + esc(initials) + "</span>";
  }

  function artHtml(url, cls) {
    return url
      ? '<img class="' + cls + '" src="' + esc(url) + '" alt="" loading="lazy" referrerpolicy="no-referrer">'
      : '<span class="' + cls + ' is-empty" aria-hidden="true">&#9835;</span>';
  }

  function winners(r) { return r.songs.filter(function (s) { return s.place === 1; }); }

  function roundStatus(r) {
    if (!r.songs.length) return "Prompt posted, no submissions yet";
    if (!r.hasVotingActivity) return "Submissions in, voting hasn\u2019t started";
    return null;
  }

  function roundCounts(r) {
    var votes = 0, comments = 0;
    r.songs.forEach(function (s) { votes += (s.votes || []).length; comments += (s.comments || []).length; });
    return { tracks: r.songs.length, votes: votes, comments: comments };
  }

  function roundUrl(seasonKey, roundId) {
    return "round.html?s=" + encodeURIComponent(seasonKey) + "&r=" + encodeURIComponent(roundId);
  }

  /* =====================================================================
     1. Season page: the list of rounds
     ===================================================================== */

  function renderList(host, d, opts) {
    opts = opts || {};
    var selected = opts.selected || [];
    host.innerHTML = "";
    if (opts.filterTag) opts.filterTag(host);

    var numbered = d.rounds.map(function (r, i) { return { r: r, n: i + 1 }; });
    var shown = !selected.length ? numbered : numbered.filter(function (x) {
      return x.r.songs.some(function (s) { return selected.indexOf(s.submitterId) !== -1; });
    });

    var count = document.getElementById("rrCount");
    if (count) count.textContent = selected.length ? shown.length + " of " + plural(d.rounds.length, "round") : plural(d.rounds.length, "round");

    if (!d.rounds.length) { host.insertAdjacentHTML("beforeend", '<div class="empty">No rounds posted yet this season.</div>'); return; }
    if (!shown.length) { host.insertAdjacentHTML("beforeend", '<div class="empty">No rounds involve this selection.</div>'); return; }

    host.insertAdjacentHTML("beforeend", '<div class="rl">' + shown.slice().reverse().map(function (x) {
      var r = x.r, status = roundStatus(r), c = roundCounts(r), top = winners(r);
      var sub = status ? esc(status)
        : top.length > 1 ? "Tied: " + top.map(function (s) { return "<b>" + esc(s.submitterName) + "</b>"; }).join(" &amp; ")
        : top.length ? "<b>" + esc(top[0].submitterName) + "</b> won with " + esc(top[0].title) : "";
      return '<a class="rl-card" href="' + roundUrl(d.key, r.id) + '">' +
        artHtml(top[0] && top[0].art, "rl-art") +
        '<span class="rl-text"><span class="rl-num">Round ' + x.n + (r.created ? " &middot; " + esc(dateOf(r.created)) : "") + "</span>" +
        '<span class="rl-name">' + esc(r.name) + "</span>" +
        (sub ? '<span class="rl-sub">' + sub + "</span>" : "") +
        (status ? "" : '<span class="rl-counts">' + plural(c.tracks, "track") + " &middot; " + plural(c.votes, "vote") + " &middot; " + plural(c.comments, "comment") + "</span>") +
        '</span><span class="rl-go" aria-hidden="true">&rarr;</span></a>';
    }).join("") + "</div>");
  }

  /* =====================================================================
     2. The round page
     ===================================================================== */

  /* ---- the voters on one track: every vote, then comment-only rows ---- */

  function voteRows(song) {
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

  function votesFor(id) {
    var rows = (state.social && state.social.votes[id]) || [];
    var up = 0, down = 0, mine = 0, uid = me();
    rows.forEach(function (v) { if (v.value > 0) up++; else down++; if (v.user_id === uid) mine = v.value; });
    return { up: up, down: down, score: up - down, mine: mine };
  }

  function reactionsFor(id) {
    var rows = (state.social && state.social.reactions[id]) || [];
    var uid = me(), by = {};
    rows.forEach(function (r) {
      var e = by[r.reaction] = by[r.reaction] || { count: 0, mine: false, who: [] };
      e.count++;
      if (r.user_id === uid) e.mine = true;
      e.who.push(memberName(r.user_id));
    });
    return by;
  }

  function repliesFor(id) { return (state.social && state.social.replies[id]) || []; }
  function memberName(uid) { return (state.people && state.people[uid] && state.people[uid].name) || "A member"; }

  function socialHtml(c) {
    if (!state.social) return "";
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

  /* ---- rendering ---- */

  function pointsLabel(p) {
    if (p > 0) return "+" + p;
    if (p < 0) return "\u2212" + Math.abs(p);
    return "0";
  }

  function voteHtml(row) {
    var c = row.comment;
    return '<div class="rp-vote' + (c ? " has-comment" : "") + '"' + (c ? ' data-id="' + esc(c.id) + '"' : "") + ">" +
      '<div class="rp-vote-head">' + avatar(row.voterId, row.name) +
      '<span class="rp-voter">' + esc(row.name) + "</span>" +
      '<span class="rp-pts' + (row.points === 0 ? " is-zero" : row.points < 0 ? " is-neg" : "") + '"' +
      (row.points === 0 ? ' title="Commented without giving points"' : "") + ">" + pointsLabel(row.points) + "</span></div>" +
      (c ? '<p class="rp-comment">' + esc(c.comment) + "</p>" + socialHtml(c) : "") +
      "</div>";
  }

  function placeBadge(s, tiedPlaces) {
    if (!s.place) return "";
    var tied = tiedPlaces[s.place] > 1;
    return '<span class="rp-place' + (s.place <= 3 ? " is-" + s.place : "") + '">' +
      (s.place === 1 ? "&#9733; " : "") + ordinal(s.place) + " place" + (tied ? " &middot; tie" : "") + "</span>";
  }

  function trackHtml(s, tiedPlaces) {
    var rows = voteRows(s);
    var voters = (s.votes || []).length;
    var title = s.spotifyId
      ? '<a href="https://open.spotify.com/track/' + esc(s.spotifyId) + '" target="_blank" rel="noopener">' + esc(s.title) + "</a>"
      : esc(s.title);
    return '<article class="rp-track" id="t-' + esc(s.spotifyId || s.title) + '">' +
      '<div class="rp-track-main">' + artHtml(s.art, "rp-art") +
        '<div class="rp-track-info">' + placeBadge(s, tiedPlaces) +
          '<h2 class="rp-title">' + title + "</h2>" +
          '<p class="rp-artist">' + esc(s.artistText) + "</p>" +
          (s.album ? '<p class="rp-album">' + esc(s.album) + "</p>" : "") +
        "</div>" +
        '<div class="rp-score"><b>' + pointsLabel(s.points) + "</b><span>" + plural(voters, "voter") + "</span></div>" +
      "</div>" +
      '<div class="rp-submitter">' + avatar(s.submitterId, s.submitterName) +
        "<span>Submitted by <b>" + esc(s.submitterName) + "</b></span>" +
        (s.dailyDouble ? '<span class="dd-badge">Daily Double +' + s.dailyDouble.bonus + "</span>" : "") + "</div>" +
      (s.note ? '<p class="rp-note"><span>Their note</span>' + esc(s.note) + "</p>" : "") +
      (rows.length ? '<div class="rp-votes">' + rows.map(voteHtml).join("") + "</div>"
                   : '<p class="rp-empty">No votes or comments on this one.</p>') +
      "</article>";
  }

  function navHtml(d, i, where) {
    var prev = d.rounds[i - 1], next = d.rounds[i + 1];
    return '<nav class="rp-nav rp-nav-' + where + '" aria-label="Other rounds">' +
      (prev ? '<a class="rp-nav-link" href="' + roundUrl(d.key, prev.id) + '">&larr; Round ' + i + '<span>' + esc(prev.name) + "</span></a>" : "<span></span>") +
      (next ? '<a class="rp-nav-link is-next" href="' + roundUrl(d.key, next.id) + '">Round ' + (i + 2) + ' &rarr;<span>' + esc(next.name) + "</span></a>" : "<span></span>") +
      "</nav>";
  }

  function renderTracks(r) {
    var songs = r.songs.slice().sort(function (a, b) { return (a.place || 99) - (b.place || 99); });
    var tiedPlaces = {};
    songs.forEach(function (s) { if (s.place) tiedPlaces[s.place] = (tiedPlaces[s.place] || 0) + 1; });
    state.index = {};
    state.host.innerHTML = songs.map(function (s) { return trackHtml(s, tiedPlaces); }).join("");
  }

  function renderRoundPage(d, roundId) {
    var page = document.getElementById("roundPage");
    var i = -1;
    for (var k = 0; k < d.rounds.length; k++) if (d.rounds[k].id === roundId) i = k;
    if (i === -1) {
      page.innerHTML = '<section class="shell rp-head"><a class="rp-back" href="' + esc(d.key) + '.html">&larr; ' + esc(d.label) + "</a>" +
        "<h1>Round not found</h1><p class=\"hero-line\">That round isn\u2019t in " + esc(d.label) + ". It may be from an older link.</p></section>";
      return;
    }
    var r = d.rounds[i], c = roundCounts(r), status = roundStatus(r), top = winners(r);
    state.names = {};
    (d.competitors || []).forEach(function (p) { state.names[p.id] = p.name; });
    document.title = "PFML - " + r.name;

    var winLine = status ? "" : top.length > 1
      ? "Tied at the top: " + top.map(function (s) { return "<b>" + esc(s.submitterName) + "</b>"; }).join(" &amp; ")
      : top.length ? "<b>" + esc(top[0].submitterName) + "</b> won it with " + esc(top[0].title) : "";

    page.innerHTML =
      '<section class="shell rp-head">' +
        '<a class="rp-back" href="' + esc(d.key) + '.html#block-rounds">&larr; ' + esc(d.label) + "</a>" +
        '<p class="rp-kicker">Round ' + (i + 1) + " of " + d.rounds.length + (r.created ? " &middot; " + esc(dateOf(r.created)) : "") + "</p>" +
        "<h1>" + esc(r.name) + "</h1>" +
        (r.description ? '<p class="rp-prompt">' + esc(r.description) + "</p>" : "") +
        (winLine ? '<p class="rp-winner">' + winLine + "</p>" : "") +
        '<div class="rp-meta">' +
          (status ? '<span class="rp-chip">' + esc(status) + "</span>"
                  : '<span class="rp-chip">' + plural(c.tracks, "track") + '</span><span class="rp-chip">' + plural(c.votes, "vote") +
                    '</span><span class="rp-chip">' + plural(c.comments, "comment") + "</span>") +
          (r.playlistUrl ? '<a class="pill" href="' + esc(r.playlistUrl) + '" target="_blank" rel="noopener">Round playlist &nearr;</a>' : "") +
        "</div>" + navHtml(d, i, "top") +
      "</section>" +
      '<section class="shell rp-body"><div id="rpTracks"></div></section>' +
      '<section class="shell rp-foot">' + navHtml(d, i, "bottom") + "</section>";

    state.host = document.getElementById("rpTracks");
    if (status) { state.host.innerHTML = '<p class="rp-empty">Nothing to show yet: ' + esc(status.toLowerCase()) + ".</p>"; return; }

    // Tracks and votes render straight away; the member layer fills in when
    // it arrives, so a slow connection still shows the round immediately.
    renderTracks(r);
    state.host.addEventListener("click", onClick);
    state.host.addEventListener("submit", onSubmit);
    if (!api()) return;
    Promise.all([api().people(), loadSocial(r.id)]).then(function (res) {
      state.people = res[0];
      renderTracks(r);
    }).catch(function (err) {
      state.host.insertAdjacentHTML("afterbegin",
        '<p class="rp-empty">Couldn\u2019t load member votes and replies: ' + esc(err && err.message ? err.message : err) + "</p>");
    });
    state.roundId = r.id;
  }

  function loadSocial(roundId) {
    return api().loadRound(roundId).then(function (res) {
      state.social = { votes: groupBy(res.votes), reactions: groupBy(res.reactions), replies: groupBy(res.replies) };
    });
  }

  /* ---- actions ---- */

  function rerenderVote(id) {
    var node = state.host.querySelector('.rp-vote[data-id="' + cssEscape(id) + '"]');
    var row = state.index[id];
    if (!node || !row) return;
    var wrap = document.createElement("div");
    wrap.innerHTML = voteHtml(row);
    node.replaceWith(wrap.firstChild);
  }

  // Takes a function, not a promise, so nothing is sent while an earlier
  // action is still saving, and a failure always tells the member.
  function refreshAfter(action, id) {
    if (state.busy) return;
    state.busy = true;
    Promise.resolve().then(action).then(function () { return loadSocial(state.roundId); })
      .then(function () { rerenderVote(id); })
      .catch(function (err) { alert("That didn\u2019t save: " + (err && err.message ? err.message : err)); })
      .then(function () { state.busy = false; });
  }

  function onClick(ev) {
    var btn = ev.target.closest("[data-act]");
    if (!btn || btn.tagName === "FORM") return;
    var card = btn.closest(".rp-vote[data-id]");
    if (!card || !state.social) return;
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
      rerenderVote(id);
    } else if (act === "thread") {
      state.threads[id] = !state.threads[id];
      rerenderVote(id);
      if (state.threads[id]) {
        var ta = state.host.querySelector('.rp-vote[data-id="' + cssEscape(id) + '"] textarea');
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
    var id = form.closest(".rp-vote[data-id]").getAttribute("data-id");
    var text = form.querySelector("textarea").value.trim();
    if (!text) return;
    state.threads[id] = true;
    refreshAfter(function () { return api().addReply(id, text); }, id);
  }

  window.PFMLRounds = { renderList: renderList, renderRoundPage: renderRoundPage, roundUrl: roundUrl };
})();
