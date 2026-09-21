/* PFML — comments page.

   Every vote comment from the Music League export, one round at a time, with
   member up/down votes, reactions and replies on top. The comment text comes
   from the season JSON (private bucket); the social layer comes from the
   comment_* tables. Both are reached through window.PFML (auth.js), so this
   file never talks to Supabase directly and can be exercised with a stub.

   Votes show as a net score with an up/down breakdown on hover; reactions
   show who reacted on hover. Replies are flat, oldest first. */

(function () {
  "use strict";

  var REACT = { fire: "\uD83D\uDD25", laugh: "\uD83D\uDE02", hundred: "\uD83D\uDCAF",
                eyes: "\uD83D\uDC40", grimace: "\uD83D\uDE2C", heart: "\u2764\uFE0F" };
  var REACT_ORDER = ["fire", "laugh", "hundred", "eyes", "grimace", "heart"];
  var LAST_KEY = "pfml.comments.last";

  var state = {
    index: null,
    season: null,          // season JSON
    roundId: null,
    people: {},            // user_id -> { name }
    social: null,          // { votes: {id: [...]}, reactions: {...}, replies: {...} }
    open: {},              // comment id -> reply thread open
    picker: null,          // comment id with the reaction picker open
    busy: false
  };

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function plural(n, one, many) { return n + " " + (n === 1 ? one : (many || one + "s")); }
  function remember(v) { try { localStorage.setItem(LAST_KEY, JSON.stringify(v)); } catch (e) { /* optional */ } }
  function recall() { try { return JSON.parse(localStorage.getItem(LAST_KEY) || "null"); } catch (e) { return null; } }

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

  /* ---- selectors ---- */

  function playedSeasons() {
    return state.index.seasons.filter(function (s) { return s.roundCount > 0; });
  }

  function fillSeasons(preferKey) {
    var sel = $("cmSeason");
    var seasons = playedSeasons();
    sel.innerHTML = seasons.map(function (s) {
      return '<option value="' + esc(s.key) + '">' + esc(s.label) + "</option>";
    }).join("");
    var keys = seasons.map(function (s) { return s.key; });
    var pick = keys.indexOf(preferKey) !== -1 ? preferKey
      : (keys.indexOf(state.index.currentSeason) !== -1 ? state.index.currentSeason : keys[keys.length - 1]);
    sel.value = pick;
    return pick;
  }

  function roundsNewestFirst() {
    return state.season.rounds.slice().reverse();
  }

  function fillRounds(preferId) {
    var sel = $("cmRound");
    var rounds = roundsNewestFirst();
    var total = state.season.rounds.length;
    sel.innerHTML = rounds.map(function (r, i) {
      return '<option value="' + esc(r.id) + '">Round ' + (total - i) + ": " + esc(r.name) + "</option>";
    }).join("");
    var ids = rounds.map(function (r) { return r.id; });
    sel.value = ids.indexOf(preferId) !== -1 ? preferId : ids[0];
    return sel.value;
  }

  function currentRound() {
    for (var i = 0; i < state.season.rounds.length; i++) {
      if (state.season.rounds[i].id === state.roundId) return state.season.rounds[i];
    }
    return null;
  }

  /* ---- social summaries for one comment ---- */

  function votesFor(id) {
    var rows = (state.social && state.social.votes[id]) || [];
    var up = 0, down = 0, mine = 0, me = window.PFML.api.me();
    rows.forEach(function (v) {
      if (v.value > 0) up++; else down++;
      if (v.user_id === me) mine = v.value;
    });
    return { up: up, down: down, score: up - down, mine: mine };
  }

  function reactionsFor(id) {
    var rows = (state.social && state.social.reactions[id]) || [];
    var me = window.PFML.api.me();
    var by = {};
    rows.forEach(function (r) {
      var e = by[r.reaction] = by[r.reaction] || { count: 0, mine: false, who: [] };
      e.count++;
      if (r.user_id === me) e.mine = true;
      e.who.push(nameOf(r.user_id));
    });
    return by;
  }

  function repliesFor(id) {
    return (state.social && state.social.replies[id]) || [];
  }

  function nameOf(userId) {
    return (state.people[userId] && state.people[userId].name) || "A member";
  }

  /* ---- rendering ---- */

  function commentHtml(c, context) {
    var v = votesFor(c.id);
    var reacts = reactionsFor(c.id);
    var replies = repliesFor(c.id);
    var open = !!state.open[c.id];
    var me = window.PFML.api.me();
    var admin = window.PFML.member && window.PFML.member.role === "admin";

    var pts = c.points > 0 ? "gave " + plural(c.points, "point")
      : c.points < 0 ? "gave " + c.points + " points" : "comment only";

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
      thread = '<div class="cm-thread">' +
        replies.map(function (r) {
          var canDelete = r.user_id === me || admin;
          return '<div class="cm-reply"><div class="cm-reply-head"><b>' + esc(nameOf(r.user_id)) + "</b> &middot; " +
            esc(when(r.created_at)) +
            (canDelete ? ' &middot; <button type="button" class="cm-link" data-act="delete" data-reply="' + r.id + '">Delete</button>' : "") +
            '</div><div class="cm-reply-body">' + esc(r.body) + "</div></div>";
        }).join("") +
        '<form class="cm-form" data-act="reply">' +
        '<label class="cm-sr" for="r-' + esc(c.id) + '">Reply to ' + esc(c.voterName) + "</label>" +
        '<textarea id="r-' + esc(c.id) + '" maxlength="2000" placeholder="Reply to ' + esc(c.voterName) + '"></textarea>' +
        '<button type="submit" class="cm-send">Reply</button></form></div>';
    }

    return '<article class="cm" data-id="' + esc(c.id) + '">' +
      (context ? '<p class="cm-context">' + context + "</p>" : "") +
      '<div class="cm-head"><span class="cm-who">' + esc(c.voterName) + '</span><span class="cm-pts">' + pts + "</span></div>" +
      '<p class="cm-text">' + esc(c.comment) + "</p>" +
      '<div class="cm-bar">' +
        '<span class="cm-vote" title="' + v.up + " up, " + v.down + ' down">' +
          '<button type="button" data-act="vote" data-v="1" class="' + (v.mine > 0 ? "is-on" : "") + '" aria-label="Upvote" aria-pressed="' + (v.mine > 0) + '">&#9650;</button>' +
          '<span class="cm-score">' + v.score + "</span>" +
          '<button type="button" data-act="vote" data-v="-1" class="' + (v.mine < 0 ? "is-on" : "") + '" aria-label="Downvote" aria-pressed="' + (v.mine < 0) + '">&#9660;</button>' +
        "</span>" +
        chips +
        '<button type="button" class="cm-chip cm-add" data-act="picker" aria-label="Add a reaction">' +
          (state.picker === c.id ? "&times;" : "+&#9786;") + "</button>" +
        picker +
        '<button type="button" class="cm-link" data-act="thread">' +
          (open ? "Hide replies" : replies.length ? plural(replies.length, "reply", "replies") : "Reply") + "</button>" +
      "</div>" + thread + "</article>";
  }

  function trackLine(s) {
    var link = s.spotifyId ? '<a href="https://open.spotify.com/track/' + esc(s.spotifyId) + '" target="_blank" rel="noopener">' + esc(s.title) + "</a>" : esc(s.title);
    return link + " &middot; " + esc(s.artistText) + " &middot; submitted by " + esc(s.submitterName);
  }

  function renderRoundHead(r) {
    var n = r.songs.reduce(function (a, s) { return a + (s.comments || []).length; }, 0);
    $("cmRoundHead").innerHTML = '<div class="cm-round">' +
      "<h2>" + esc(r.name) + "</h2>" +
      (r.description ? '<p class="block-note">' + esc(r.description) + "</p>" : "") +
      '<p class="cm-round-meta">' + plural(n, "comment") + " on " + plural(r.songs.length, "track") +
      (r.playlistUrl ? ' &middot; <a href="' + esc(r.playlistUrl) + '" target="_blank" rel="noopener">Round playlist</a>' : "") +
      "</p></div>";
  }

  function render() {
    var r = currentRound();
    var host = $("cmList");
    if (!r) { host.innerHTML = '<div class="empty">No rounds yet.</div>'; return; }
    renderRoundHead(r);

    var sort = $("cmSort").value;
    var songs = r.songs.slice().sort(function (a, b) { return (a.place || 99) - (b.place || 99); });
    var withComments = songs.filter(function (s) { return (s.comments || []).length; });
    if (!withComments.length) { host.innerHTML = '<div class="empty">Nobody left a comment in this round.</div>'; return; }

    if (sort === "track") {
      host.innerHTML = withComments.map(function (s) {
        var comments = s.comments.slice().sort(function (a, b) { return b.points - a.points; });
        return '<section class="cm-track"><h3 class="cm-track-head"><span class="cm-place">#' + (s.place || "") + "</span> " +
          trackLine(s) + ' <span class="cm-track-pts">' + s.points + " pts</span></h3>" +
          '<div class="cm-list">' + comments.map(function (c) { return commentHtml(c, null); }).join("") + "</div></section>";
      }).join("");
      return;
    }

    var flat = [];
    withComments.forEach(function (s) { s.comments.forEach(function (c) { flat.push({ c: c, s: s }); }); });
    if (sort === "top") {
      flat.sort(function (a, b) {
        var va = votesFor(a.c.id), vb = votesFor(b.c.id);
        return vb.score - va.score || (vb.up + vb.down) - (va.up + va.down);
      });
    } else {
      flat.sort(function (a, b) { return repliesFor(b.c.id).length - repliesFor(a.c.id).length; });
    }
    host.innerHTML = '<div class="cm-list">' + flat.map(function (x) {
      return commentHtml(x.c, "on " + trackLine(x.s));
    }).join("") + "</div>";
  }

  function rerenderComment(id) {
    // Only the one comment changes, so the page doesn't jump around. The
    // sort order is left alone until the round is re-rendered, on purpose:
    // re-sorting under someone's cursor as they vote is disorienting.
    var node = document.querySelector('.cm[data-id="' + cssEscape(id) + '"]');
    if (!node) { render(); return; }
    var ctx = node.querySelector(".cm-context");
    var c = findComment(id);
    if (!c) return;
    var wrap = document.createElement("div");
    wrap.innerHTML = commentHtml(c.c, ctx ? ctx.innerHTML : null);
    node.replaceWith(wrap.firstChild);
  }

  function cssEscape(s) {
    return window.CSS && CSS.escape ? CSS.escape(s) : String(s).replace(/["\\]/g, "\\$&");
  }

  function findComment(id) {
    var r = currentRound();
    if (!r) return null;
    for (var i = 0; i < r.songs.length; i++) {
      var list = r.songs[i].comments || [];
      for (var j = 0; j < list.length; j++) if (list[j].id === id) return { c: list[j], s: r.songs[i] };
    }
    return null;
  }

  /* ---- loading ---- */

  function loadSocial() {
    return window.PFML.api.loadRound(state.roundId).then(function (res) {
      state.social = { votes: groupBy(res.votes), reactions: groupBy(res.reactions), replies: groupBy(res.replies) };
    });
  }

  function showError(err) {
    $("cmList").innerHTML = '<div class="empty">Couldn\'t load that: ' + esc(err && err.message ? err.message : err) + "</div>";
  }

  function selectRound(roundId) {
    state.roundId = roundId;
    state.open = {};
    state.picker = null;
    remember({ season: state.season.key, round: roundId });
    $("cmList").innerHTML = '<div class="empty">Loading comments.</div>';
    return loadSocial().then(render).catch(showError);
  }

  function selectSeason(key, preferRound) {
    return window.PFML.loadJSON(key + ".json").then(function (season) {
      state.season = season;
      return selectRound(fillRounds(preferRound));
    }).catch(showError);
  }

  /* ---- actions ---- */

  function refreshAfter(promise, id) {
    if (state.busy) return;
    state.busy = true;
    promise.then(loadSocial).then(function () { rerenderComment(id); })
      .catch(function (err) { alert("That didn't save: " + (err && err.message ? err.message : err)); })
      .then(function () { state.busy = false; });
  }

  function onClick(ev) {
    var btn = ev.target.closest("[data-act]");
    if (!btn || btn.tagName === "FORM") return;
    var card = btn.closest(".cm");
    if (!card) return;
    var id = card.getAttribute("data-id");
    var act = btn.getAttribute("data-act");

    if (act === "vote") {
      var want = parseInt(btn.getAttribute("data-v"), 10);
      var mine = votesFor(id).mine;
      refreshAfter(window.PFML.api.setVote(id, mine === want ? 0 : want), id);
    } else if (act === "react") {
      var key = btn.getAttribute("data-r");
      var on = reactionsFor(id)[key];
      state.picker = null;
      refreshAfter(window.PFML.api.toggleReaction(id, key, !(on && on.mine)), id);
    } else if (act === "picker") {
      state.picker = state.picker === id ? null : id;
      rerenderComment(id);
    } else if (act === "thread") {
      state.open[id] = !state.open[id];
      rerenderComment(id);
      if (state.open[id]) {
        var ta = document.querySelector('.cm[data-id="' + cssEscape(id) + '"] textarea');
        if (ta) ta.focus();
      }
    } else if (act === "delete") {
      if (!confirm("Delete this reply?")) return;
      refreshAfter(window.PFML.api.deleteReply(parseInt(btn.getAttribute("data-reply"), 10)), id);
    }
  }

  function onSubmit(ev) {
    var form = ev.target.closest('form[data-act="reply"]');
    if (!form) return;
    ev.preventDefault();
    var card = form.closest(".cm");
    var id = card.getAttribute("data-id");
    var text = form.querySelector("textarea").value.trim();
    if (!text) return;
    state.open[id] = true;
    refreshAfter(window.PFML.api.addReply(id, text), id);
  }

  /* ---- boot ---- */

  function start() {
    var last = recall() || {};
    Promise.all([window.PFML.loadJSON("index.json"), window.PFML.api.people()]).then(function (r) {
      state.index = r[0];
      state.people = r[1];
      var key = fillSeasons(last.season);
      if (!playedSeasons().length) { $("cmList").innerHTML = '<div class="empty">No rounds yet.</div>'; return; }
      return selectSeason(key, last.round);
    }).catch(showError);

    $("cmSeason").addEventListener("change", function (e) { selectSeason(e.target.value); });
    $("cmRound").addEventListener("change", function (e) { selectRound(e.target.value); });
    $("cmSort").addEventListener("change", render);
    $("cmList").addEventListener("click", onClick);
    $("cmList").addEventListener("submit", onSubmit);
  }

  if (window.PFML && window.PFML.ready) window.PFML.ready.then(start);
})();
