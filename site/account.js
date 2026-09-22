/* PFML — the header's account corner, on every members-only page.

   Two buttons at the right of the top bar, once auth.js has let a member in:

   - Inbox (a tray icon, with a count of new items): reactions and replies
     other members have left on your own vote comments, newest first, each
     linking to that comment on its round page. "New" means since you last
     opened the inbox, which is stored in Supabase (members.inbox_seen_at,
     set by mark_inbox_seen()) so it's the same on every device.
   - Your initials, in the same coloured circle as on the round pages,
     opening a menu with My profile and Sign out.

   Round and track names for inbox items come from data/lookup.json (a few
   tens of KB, built by scripts/build.py), fetched only when the inbox is
   first opened. Also exposes PFML.avatar and PFML.reactionGlyph for the
   profile page. */

(function () {
  "use strict";

  var PFML = window.PFML;
  if (!PFML || !PFML.ready) return;

  // Same as rounds.js: the original 6 reactions are stored by name.
  var LEGACY_REACT = { fire: "\uD83D\uDD25", laugh: "\uD83D\uDE02", hundred: "\uD83D\uDCAF",
                        eyes: "\uD83D\uDC40", grimace: "\uD83D\uDE2C", heart: "\u2764\uFE0F" };
  function reactionGlyph(key) { return LEGACY_REACT[key] || key; }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // Same initials and colour as rounds.js's avatar(), so a person looks
  // the same in the header, the inbox and on a round page.
  function avatar(id, name, cls) {
    var words = String(name || "?").trim().split(/\s+/);
    var initials = (words.length > 1 ? words[0][0] + words[words.length - 1][0] : String(name || "?").slice(0, 2)).toUpperCase();
    var h = 0;
    String(id || name).split("").forEach(function (c) { h = (h * 31 + c.charCodeAt(0)) % 360; });
    return '<span class="av' + (cls ? " " + cls : "") + '" style="background:hsl(' + h + ',48%,42%)" aria-hidden="true">' + esc(initials) + "</span>";
  }

  PFML.avatar = avatar;
  PFML.reactionGlyph = reactionGlyph;

  function when(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    var mins = Math.round((Date.now() - d.getTime()) / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return mins + "m ago";
    if (mins < 60 * 24) return Math.round(mins / 60) + "h ago";
    if (mins < 60 * 24 * 7) return Math.round(mins / (60 * 24)) + "d ago";
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }

  // A tray with a notch: an inbox, drawn rather than an emoji character,
  // so it's the same flat icon on every device (see ADD_REACTION_ICON).
  var INBOX_ICON =
    '<svg class="acct-icon" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">' +
    '<path d="M4 13.5 6.3 5.8A2 2 0 0 1 8.2 4.4h7.6a2 2 0 0 1 1.9 1.4L20 13.5V18a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>' +
    '<path d="M4 13.5h4.6l1.2 2.2h4.4l1.2-2.2H20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>' +
    "</svg>";

  var REFRESH_MS = 60 * 1000;

  var state = {
    member: null,
    items: null,          // newest first: { kind, commentId, userId, at, reaction | body }
    seenAt: undefined,    // ISO string, null (never opened), or undefined (couldn't tell)
    fetchedAt: 0,
    open: null,           // "menu" | "inbox" | null
    context: null         // Promise of { people, lookup } for rendering items
  };

  function $(id) { return document.getElementById(id); }
  function api() { return PFML.api; }

  /* ---- building the corner ---- */

  function build(member) {
    var bar = document.querySelector(".topbar-inner");
    if (!bar || bar.querySelector(".acct")) return;
    state.member = member;
    var box = document.createElement("div");
    box.className = "acct";
    box.innerHTML =
      '<button type="button" class="acct-btn acct-inbox-btn" id="acctInboxBtn" aria-haspopup="true" aria-expanded="false" aria-controls="acctInbox" aria-label="Inbox">' +
        INBOX_ICON + '<span class="acct-badge" id="acctBadge" hidden></span></button>' +
      '<button type="button" class="acct-btn acct-me-btn" id="acctMeBtn" aria-haspopup="true" aria-expanded="false" aria-controls="acctMenu" ' +
        'aria-label="Account menu for ' + esc(member.name) + '" title="' + esc(member.name) + '">' + avatar(member.competitorId, member.name) + "</button>" +
      '<div class="acct-pop acct-menu" id="acctMenu" hidden>' +
        '<div class="acct-menu-head">' + avatar(member.competitorId, member.name) +
          '<span><b>' + esc(member.name) + "</b><small>Signed in</small></span></div>" +
        '<a class="acct-item" href="profile.html">My profile</a>' +
        '<button type="button" class="acct-item" id="acctSignOut">Sign out</button>' +
      "</div>" +
      '<div class="acct-pop acct-inbox" id="acctInbox" hidden role="region" aria-label="Inbox">' +
        '<div class="acct-inbox-head"><b>Inbox</b><span>Reactions and replies to your comments</span></div>' +
        '<div class="acct-inbox-list" id="acctInboxList"><p class="acct-empty">Loading…</p></div>' +
      "</div>";
    bar.appendChild(box);

    $("acctInboxBtn").addEventListener("click", function () { toggle("inbox"); });
    $("acctMeBtn").addEventListener("click", function () { toggle("menu"); });
    $("acctSignOut").addEventListener("click", function () { if (PFML.signOut) PFML.signOut(); });
    document.addEventListener("click", closeFromOutside);
    document.addEventListener("keydown", closeOnEscape);
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible" && Date.now() - state.fetchedAt > REFRESH_MS) refresh();
    });
    refresh();
  }

  /* ---- open / close ---- */

  function toggle(which) {
    if (state.open === which) { close(); return; }
    close(true);
    state.open = which;
    var btn = which === "inbox" ? $("acctInboxBtn") : $("acctMeBtn");
    var pop = which === "inbox" ? $("acctInbox") : $("acctMenu");
    btn.setAttribute("aria-expanded", "true");
    pop.hidden = false;
    if (which === "inbox") openInbox();
  }

  function close(quiet) {
    if (!state.open) return;
    var btn = state.open === "inbox" ? $("acctInboxBtn") : $("acctMeBtn");
    var pop = state.open === "inbox" ? $("acctInbox") : $("acctMenu");
    btn.setAttribute("aria-expanded", "false");
    pop.hidden = true;
    state.open = null;
    if (!quiet) btn.focus();
  }

  function closeFromOutside(ev) {
    if (!state.open || !ev.target.closest) return;
    if (ev.target.closest(".acct")) return;
    close(true);
  }

  function closeOnEscape(ev) {
    if (ev.key === "Escape" && state.open) close();
  }

  /* ---- the inbox ---- */

  function refresh() {
    if (!api() || !api().inbox) return;
    state.fetchedAt = Date.now();
    Promise.all([
      api().inbox(state.member.competitorId),
      // undefined when the database can't say (the migration adding
      // inbox_seen_at not run yet): the list still works, just no count
      api().inboxSeenAt().catch(function () { return undefined; })
    ]).then(function (res) {
      var items = res[0].reactions.map(function (r) {
        return { kind: "reaction", commentId: r.comment_id, userId: r.user_id, at: r.created_at, reaction: r.reaction };
      }).concat(res[0].replies.map(function (r) {
        return { kind: "reply", commentId: r.comment_id, userId: r.user_id, at: r.created_at, body: r.body };
      }));
      items.sort(function (a, b) { return a.at < b.at ? 1 : a.at > b.at ? -1 : 0; });
      state.items = items.slice(0, 40);
      state.seenAt = res[1];
      renderBadge();
      if (state.open === "inbox") renderList();
    }).catch(function (err) {
      state.items = state.items || [];
      if (state.open === "inbox") renderList(err);
    });
  }

  function isNew(item) {
    if (state.seenAt === undefined) return false;
    return state.seenAt === null || Date.parse(item.at) > Date.parse(state.seenAt);
  }

  function renderBadge() {
    var badge = $("acctBadge"), btn = $("acctInboxBtn");
    if (!badge) return;
    var n = (state.items || []).filter(isNew).length;
    badge.textContent = n > 9 ? "9+" : String(n);
    badge.hidden = !n;
    btn.setAttribute("aria-label", n ? "Inbox, " + n + " new" : "Inbox");
  }

  function context() {
    if (!state.context) {
      state.context = Promise.all([
        api().people().catch(function () { return {}; }),
        PFML.loadJSON("lookup.json").catch(function () { return { rounds: {} }; })
      ]).then(function (res) { return { people: res[0], lookup: res[1] }; });
    }
    return state.context;
  }

  function openInbox() {
    if (state.items) renderList();
    // Everything listed now counts as seen: the badge clears, but the
    // open list keeps its "new" marks until it's opened again.
    if (state.seenAt !== undefined && (state.items || []).some(isNew)) {
      api().markInboxSeen().then(function (seenAt) {
        state.seenAt = seenAt || new Date().toISOString();
        renderBadge();
      }).catch(function () { /* keeps the count; tries again next open */ });
    }
  }

  function itemHtml(item, ctx, fresh) {
    var person = ctx.people[item.userId] || { name: "A member" };
    var parts = item.commentId.split("|");
    var round = ctx.lookup.rounds && ctx.lookup.rounds[parts[0]];
    var track = round && round.tracks[parts[1]];
    var on = track ? " on <i>" + esc(track) + "</i>" : "";
    var text = item.kind === "reaction"
      ? "<b>" + esc(person.name) + "</b> reacted " + '<span class="acct-emoji">' + esc(reactionGlyph(item.reaction)) + "</span> to your comment" + on
      : "<b>" + esc(person.name) + "</b> replied to your comment" + on + ': <span class="acct-quote">“' + esc(item.body) + "”</span>";
    var meta = (round ? esc(round.seasonLabel) + " &middot; Round " + round.number + " &middot; " : "") + esc(when(item.at));
    var inner = avatar(person.competitorId, person.name) +
      '<span class="acct-note-text">' + text + '<span class="acct-note-meta">' + meta + "</span></span>";
    var cls = "acct-note" + (fresh ? " is-new" : "");
    if (!round) return '<div class="' + cls + '">' + inner + "</div>";
    var href = "round.html?s=" + encodeURIComponent(round.season) + "&r=" + encodeURIComponent(parts[0]) +
      "&c=" + encodeURIComponent(item.commentId) + (item.kind === "reply" ? "&thread=1" : "");
    return '<a class="' + cls + '" href="' + href + '">' + inner + "</a>";
  }

  function renderList(err) {
    var list = $("acctInboxList");
    if (!list) return;
    if (err && !(state.items || []).length) {
      list.innerHTML = '<p class="acct-empty">Couldn’t load your inbox: ' + esc(err.message || err) + "</p>";
      return;
    }
    var items = state.items || [];
    if (!items.length) {
      list.innerHTML = '<p class="acct-empty">Nothing yet. When someone reacts to or replies to one of your vote comments, it shows up here.</p>';
      return;
    }
    // Which were new when this list was opened, before marking them seen.
    var fresh = items.map(isNew);
    context().then(function (ctx) {
      list.innerHTML = items.map(function (item, i) { return itemHtml(item, ctx, fresh[i]); }).join("");
    });
  }

  PFML.ready.then(build);
})();
