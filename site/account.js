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
   first opened.

   Also the one home of the display helpers the pages share, so a person,
   a reaction, a time and a translation look the same in the header, on a
   round page, on a profile and in a quote card: PFML.avatar,
   PFML.reactionGlyph, PFML.when and PFML.translationHtml. Every
   members-only page loads this right after auth.js and before rounds.js
   and app.js. */

(function () {
  "use strict";

  var PFML = window.PFML;

  // The 6 reactions PFML has offered since the feature shipped are stored
  // by these names, not as the emoji: comment_reactions rows already in
  // Supabase use these exact values (README, Reactions). Anything else is
  // stored as the emoji character itself, so it is its own glyph.
  var LEGACY_REACT = { fire: "\uD83D\uDD25", laugh: "\uD83D\uDE02", hundred: "\uD83D\uDCAF",
                        eyes: "\uD83D\uDC40", grimace: "\uD83D\uDE2C", heart: "\u2764\uFE0F" };
  function reactionGlyph(key) { return LEGACY_REACT[key] || key; }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // Initials in a coloured circle, standing in for the profile photos
  // Music League has and the export doesn't. The colour is fixed per
  // player (from their id), so the same person always looks the same.
  function avatar(id, name, cls) {
    var words = String(name || "?").trim().split(/\s+/);
    var initials = (words.length > 1 ? words[0][0] + words[words.length - 1][0] : String(name || "?").slice(0, 2)).toUpperCase();
    var h = 0;
    String(id || name).split("").forEach(function (c) { h = (h * 31 + c.charCodeAt(0)) % 360; });
    return '<span class="av' + (cls ? " " + cls : "") + '" style="background:hsl(' + h + ',48%,42%)" aria-hidden="true">' + esc(initials) + "</span>";
  }

  // "just now", "5m ago", "3h ago", "2d ago", then a date after a week.
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

  // The English under a comment or note written in another language
  // (data/translations.json, attached by build.py), labelled as a
  // translation. Goes inside the comment's own element; <small> and <b>,
  // not spans, so the note's label styling (.rp-note span) stays off it.
  function translationHtml(tr) {
    if (!tr) return "";
    return '<small class="tr"><b class="tr-label">Translated from ' + esc(tr.from) + "</b>" + esc(tr.text) + "</small>";
  }

  // A deadline, both ways: "Sun, Oct 25, 7:00 PM" in the reader's own time
  // zone, and "in 2 days". The Submit page and the Home banner say it alike.
  function closes(iso) {
    var at = new Date(iso).toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
    var mins = Math.round((Date.parse(iso) - Date.now()) / 60000);
    var left;
    if (mins < 1) left = "any moment now";
    else if (mins < 60) left = "in " + mins + " min";
    else if (Math.round(mins / 60) < 36) left = "in " + Math.round(mins / 60) + (Math.round(mins / 60) === 1 ? " hour" : " hours");
    else left = "in " + Math.round(mins / 60 / 24) + " days";
    return { at: at, left: left };
  }

  PFML.avatar = avatar;
  PFML.reactionGlyph = reactionGlyph;
  PFML.when = when;
  PFML.translationHtml = translationHtml;
  PFML.closes = closes;

  // A tray with a notch: an inbox, drawn rather than an emoji character,
  // so it's the same flat icon on every device (see ADD_REACTION_ICON).
  var INBOX_ICON =
    '<svg class="acct-icon" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">' +
    '<path d="M4 13.5 6.3 5.8A2 2 0 0 1 8.2 4.4h7.6a2 2 0 0 1 1.9 1.4L20 13.5V18a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>' +
    '<path d="M4 13.5h4.6l1.2 2.2h4.4l1.2-2.2H20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>' +
    "</svg>";

  var REFRESH_MS = 60 * 1000;
  var INBOX_SIZE = 40;      // items shown, newest first

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

  /* ---- dark mode: a choice, light by default ---- */

  // <html data-theme="dark"> switches style.css's colour tokens. The line
  // at the top of every page's <head> reads THEME_KEY back before the page
  // paints, so a dark page never flashes light first; the features and
  // privacy pages follow the same choice.
  var THEME_KEY = "pfml.theme";

  function isDark() { return document.documentElement.getAttribute("data-theme") === "dark"; }

  function setDark(on) {
    if (on) document.documentElement.setAttribute("data-theme", "dark");
    else document.documentElement.removeAttribute("data-theme");
    try { localStorage.setItem(THEME_KEY, on ? "dark" : "light"); } catch (e) { /* private mode: this page only */ }
    var sw = $("acctTheme");
    if (sw) sw.setAttribute("aria-checked", String(on));
  }

  /* ---- add to home screen ---- */

  // A "Get the app" button in the top bar on phones, until it's been tapped
  // once (then it lives in the initials menu) or the site is already running
  // from the home screen. Android's Chrome hands over its own install prompt
  // (beforeinstallprompt), so one tap installs; iOS has no such thing, so it
  // shows how: Share, then Add to Home Screen. Apps' built-in browsers
  // (Instagram, Messenger) can't add to the home screen at all.
  var INSTALL_SEEN_KEY = "pfml.installSeen";
  var installEvent = null;

  window.addEventListener("beforeinstallprompt", function (ev) {
    ev.preventDefault();
    installEvent = ev;
    showInstallControls();
  });
  window.addEventListener("appinstalled", function () {
    installEvent = null;
    showInstallControls();
  });

  function isApp() {
    return (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) || navigator.standalone === true;
  }

  function platform() {
    var ua = navigator.userAgent || "";
    if (/FBAN|FBAV|Instagram|Messenger|Snapchat|TikTok|Line\//i.test(ua)) return "inapp";
    if (/iPhone|iPad|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)) return "ios";
    if (/Android/.test(ua)) return "android";
    return "desktop";
  }

  function installSeen() {
    try { return localStorage.getItem(INSTALL_SEEN_KEY) === "1"; } catch (e) { return false; }
  }

  function showInstallControls() {
    var get = $("acctGet"), item = $("acctInstall");
    if (get) get.hidden = isApp() || platform() === "desktop" || installSeen();
    if (item) item.hidden = isApp();
  }

  var SHARE_ICON =
    '<svg viewBox="0 0 24 24" width="18" height="18" aria-label="the Share button" role="img">' +
    '<path d="M12 3v12M8 7l4-4 4 4M6 11H5a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-8a1 1 0 0 0-1-1h-1" ' +
    'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  var INSTALL_STEPS = {
    ios: "<ol><li>Tap " + SHARE_ICON + " Share, at the bottom of Safari (the top on an iPad).</li>" +
      "<li>Scroll down and tap <b>Add to Home Screen</b>.</li><li>Tap <b>Add</b>.</li></ol>",
    android: "<ol><li>Tap the <b>&#8942;</b> menu at the top right of Chrome.</li>" +
      "<li>Tap <b>Add to Home screen</b> or <b>Install app</b>.</li><li>Tap <b>Install</b> or <b>Add</b>.</li></ol>",
    inapp: "<p>This app's built-in browser can't add websites to your home screen. Open <b>pfml.fun</b> in Safari " +
      "(iPhone) or Chrome (Android), then tap your initials and <b>Add to home screen</b>.</p>",
    desktop: "<p>In Chrome or Edge, use the install button at the right of the address bar, or <b>Install</b> in the " +
      "browser's menu. In Safari on a Mac, choose <b>File</b>, then <b>Add to Dock</b>.</p>"
  };

  function showInstallHelp(which) {
    var dialog = $("acctInstallHelp");
    if (!dialog) {
      dialog = document.createElement("dialog");
      dialog.id = "acctInstallHelp";
      dialog.className = "acct-install";
      document.body.appendChild(dialog);
    }
    dialog.innerHTML = "<h2>Put PFML on your home screen</h2>" + INSTALL_STEPS[which || platform()] +
      '<p class="acct-install-note">It opens full screen, like an app. You sign in once inside it.</p>' +
      '<form method="dialog"><button class="acct-install-done">Got it</button></form>';
    if (dialog.showModal) dialog.showModal(); else dialog.setAttribute("open", "");
  }

  function addToHomeScreen() {
    try { localStorage.setItem(INSTALL_SEEN_KEY, "1"); } catch (e) { /* private mode: the button stays */ }
    close(true);
    showInstallControls();
    if (installEvent) {
      var ev = installEvent;
      ev.prompt();
      if (ev.userChoice) ev.userChoice.then(function () { installEvent = null; showInstallControls(); });
      return;
    }
    showInstallHelp();
  }

  PFML.showInstallHelp = showInstallHelp;

  function build(member) {
    var bar = document.querySelector(".topbar-inner");
    if (!bar || bar.querySelector(".acct")) return;
    state.member = member;
    var box = document.createElement("div");
    box.className = "acct";
    box.innerHTML =
      '<button type="button" class="acct-get" id="acctGet" hidden>Get the app</button>' +
      '<button type="button" class="acct-btn acct-inbox-btn" id="acctInboxBtn" aria-expanded="false" aria-controls="acctInbox" aria-label="Inbox">' +
        INBOX_ICON + '<span class="acct-badge" id="acctBadge" hidden></span></button>' +
      '<button type="button" class="acct-btn acct-me-btn" id="acctMeBtn" aria-expanded="false" aria-controls="acctMenu" ' +
        'aria-label="Account menu for ' + esc(member.name) + '" title="' + esc(member.name) + '">' + avatar(member.competitorId, member.name) + "</button>" +
      '<div class="acct-pop acct-menu" id="acctMenu" hidden>' +
        '<div class="acct-menu-head">' + avatar(member.competitorId, member.name) +
          '<span class="acct-menu-who"><b>' + esc(member.name) + "</b><small>Signed in</small></span></div>" +
        '<a class="acct-item" href="submit">Submit a track</a>' +
        '<a class="acct-item" href="repeats">Repeat checker</a>' +
        '<a class="acct-item" href="profile">My profile</a>' +
        '<button type="button" class="acct-item" id="acctInstall" hidden>Add to home screen</button>' +
        '<button type="button" class="acct-item acct-theme" id="acctTheme" role="switch" aria-checked="' + isDark() + '">' +
          'Dark mode<span class="acct-switch" aria-hidden="true"></span></button>' +
        '<button type="button" class="acct-item" id="acctSignOut">Sign out</button>' +
      "</div>" +
      '<div class="acct-pop acct-inbox" id="acctInbox" hidden role="region" aria-label="Inbox">' +
        '<div class="acct-inbox-head"><b>Inbox</b><span>Reactions and replies to your comments</span></div>' +
        '<div class="acct-inbox-list" id="acctInboxList"><p class="acct-empty">Loading…</p></div>' +
      "</div>";
    bar.appendChild(box);

    $("acctInboxBtn").addEventListener("click", function () { toggle("inbox"); });
    $("acctMeBtn").addEventListener("click", function () { toggle("menu"); });
    $("acctSignOut").addEventListener("click", function () { PFML.signOut(); });
    $("acctTheme").addEventListener("click", function () { setDark(!isDark()); });
    $("acctGet").addEventListener("click", addToHomeScreen);
    $("acctInstall").addEventListener("click", addToHomeScreen);
    showInstallControls();
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
    state.fetchedAt = Date.now();
    Promise.all([
      api().inbox(state.member.competitorId, INBOX_SIZE),
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
      state.items = items.slice(0, INBOX_SIZE);
      // Keep the later time: a refresh that started before the inbox was
      // opened (and marked seen) mustn't bring the old count back.
      var seen = res[1];
      if (seen && state.seenAt && Date.parse(state.seenAt) > Date.parse(seen)) seen = state.seenAt;
      state.seenAt = seen;
      renderBadge();
      // openInbox, not just renderList: opened before this first load
      // landed, it has had nothing to mark seen yet.
      if (state.open === "inbox") openInbox();
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
    var href = "round?s=" + encodeURIComponent(round.season) + "&r=" + encodeURIComponent(parts[0]) +
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
