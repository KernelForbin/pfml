/* PFML — the header's account corner, on every members-only page.

   Buttons at the right of the top bar, once auth.js has let a member in:

   - The bell (once notifications are set up): this device's notifications
     switch and a switch for each kind (README, Reminders).
   - Inbox (a tray icon, with a count of new items): reactions and replies
     other members have left on your own vote comments, newest first, each
     linking to that comment on its round page. "New" means since you last
     opened the inbox, which is stored in Supabase (members.inbox_seen_at,
     set by mark_inbox_seen()) so it's the same on every device.
   - Your initials, in the same coloured circle as on the round pages,
     opening a menu: Submit a track, Repeat checker, My profile, Site
     features, Add to home screen, Dark mode and Sign out.

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
  // own keys only: "constructor" stored as a reaction is its own text
  function reactionGlyph(key) { return Object.prototype.hasOwnProperty.call(LEGACY_REACT, key) ? LEGACY_REACT[key] : key; }

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

  // A closed round's order: one shuffle, the same for everyone, and the same
  // as the round playlists (round_order in scripts/round_playlists.py). Each
  // track's place comes from an FNV-1a hash of "<round id>|<platform>|<track>":
  // nothing about who sent it or when goes in, so the order gives neither
  // away (the user's call, 2026-10-25). Once the playlists are built, their
  // saved positions are the order, and they're this same shuffle.
  function shuffleKey(roundId, s) {
    var bytes = new TextEncoder().encode(roundId + "|" + s.platform + "|" + s.track), h = 0x811c9dc5;
    for (var i = 0; i < bytes.length; i++) h = Math.imul(h ^ bytes[i], 0x01000193) >>> 0;
    return h;
  }
  function roundOrder(roundId, rows) {
    if (rows.length && rows.every(function (s) { return s.position; })) {
      return rows.slice().sort(function (a, b) { return a.position - b.position; });
    }
    return rows.map(function (s) { return { s: s, k: shuffleKey(roundId, s) }; }).sort(function (a, b) {
      return a.k - b.k || (a.s.platform < b.s.platform ? -1 : a.s.platform > b.s.platform ? 1 : a.s.track < b.s.track ? -1 : 1);
    }).map(function (x) { return x.s; });
  }

  // Voting on the site (README, Voting on the site): built 2026-10-25, off
  // until the user switched it on with seasons set up on the site (the
  // user's call, 2026-10-25: every such season votes here). Only a round in
  // one of those seasons votes here; Season 3 and every round before stays
  // in Music League, and the database holds that (site_rounds_times_guard).
  var SITE_VOTING = true;

  // Where a site round is, the same as site_round_phase() in the database:
  // "upcoming" before it opens (a season set up on the site schedules its
  // rounds ahead), "submitting", then "voting" and "finished" for a round
  // that votes here, or "closed" for one that votes in Music League.
  function roundPhase(r) {
    var now = Date.now();
    if (r.opens_at && now < Date.parse(r.opens_at)) return "upcoming";
    if (!r.closed_at && now < Date.parse(r.closes_at)) return "submitting";
    if (!r.votes_on_site) return "closed";
    if (!r.voting_closed_at && now < Date.parse(r.voting_closes_at)) return "voting";
    return "finished";
  }

  // Who's playing a season: who was picked when it was set up on the site
  // (site_season_players), else everyone with a track in its latest
  // finished round (index.json). Null when neither says.
  function seasonPlayers(seasonKey) {
    var api_ = PFML.api;
    var roster = typeof api_.seasonRoster === "function"
      ? api_.seasonRoster(seasonKey).catch(function (err) { console.error(err); return []; })
      : Promise.resolve([]);
    return roster.then(function (list) {
      if (list && list.length) return list;
      return PFML.loadJSON("index.json").then(function (index) {
        var s = index.seasons.filter(function (x) { return x.key === seasonKey; })[0];
        return s && s.activePlayers && s.activePlayers.length ? s.activePlayers : null;
      });
    });
  }

  // DJs and Spectators (README, DJs and Spectators): everyone playing a
  // round, [{id, role, joined}], or null for a round outside a season set up
  // on the site, where everyone is a DJ as before.
  function roundRoster(r) {
    if (!r || typeof PFML.api.roundRoster !== "function") return Promise.resolve(null);
    return PFML.api.roundRoster(r.id).then(function (rows) {
      return rows && rows.length ? rows.map(function (x) { return { id: x.competitor_id, role: x.role, joined: x.joined }; }) : null;
    });
  }
  // The reader's role in a round: "dj", "spectator", or null when they
  // aren't playing its season.
  function myRole(r) {
    return roundRoster(r).then(function (list) {
      if (!list) return "dj";
      var me = PFML.member && list.filter(function (x) { return x.id === PFML.member.competitorId; })[0];
      return me ? me.role : null;
    });
  }
  // Who sends tracks to a round: seasonPlayers', less the round's
  // Spectators.
  function roundDJs(r) {
    return Promise.all([roundRoster(r), seasonPlayers(r.season_key)]).then(function (res) {
      if (!res[0] || !res[1]) return res[1];
      var dj = {};
      res[0].forEach(function (x) { if (x.role === "dj") dj[x.id] = true; });
      return res[1].filter(function (p) { return dj[p.id]; });
    });
  }
  // Spectators' podium points (README, Spectators' podium points): each
  // point a Spectator gave a track that finished 1st earns 3, 2nd 2, 3rd 1,
  // places shared on a tie. The same rule as build.py's PODIUM_POINTS.
  var PODIUM_POINTS = { 1: 3, 2: 2, 3: 1 };
  // [{id, score}] for a round's Spectators, from each track's place
  // ({submission id: place}) and every vote ([{submission_id, voter_id,
  // points}]); 0 for a Spectator who didn't vote.
  function podiumScores(places, votes, spectatorIds) {
    return spectatorIds.map(function (id) {
      var score = 0;
      votes.forEach(function (v) {
        if (v.voter_id === id && v.points > 0) score += v.points * (PODIUM_POINTS[places[v.submission_id]] || 0);
      });
      return { id: id, score: score };
    });
  }
  // Picking who wrote a hidden prompt (README, Hidden prompts and guesses);
  // build.py's PROMPTER_POINTS.
  var PROMPTER_POINTS = 3;

  // The list, biggest first: [{id, name, score}], and the rule under it. In
  // a round that hid its prompt or prompter, each also carries podium,
  // guessScore (0-5, null until graded), prompterPoints, and what they
  // guessed (guess, prompterName, reason); score is then the total.
  // scoreSelect(x) can add a commissioner's control to a guess.
  function podiumHtml(list, opts) {
    opts = opts || {};
    var guessing = list.some(function (x) { return x.podium != null; });
    var rows = list.slice().sort(function (a, b) { return b.score - a.score || a.name.localeCompare(b.name); });
    return '<div class="pod-box"><h3>' + (guessing ? "Spectators’ points" : "Spectators’ podium points") + "</h3>" +
      '<p class="block-note">Each point a Spectator gave the winner earned 3, 2nd place 2 and 3rd place 1.' +
        (guessing ? " A guess at the hidden prompt earned 0 to 5, scored by Claude, and picking who wrote it " + PROMPTER_POINTS + "." : "") + "</p>" +
      '<ol class="pod-list' + (guessing ? " pod-guesses" : "") + '">' + rows.map(function (x) {
        var parts = guessing ? '<small class="pod-parts">' + x.podium + " podium" +
          (x.guessScore != null || x.guess ? " · " + (x.guessScore == null ? "guess not scored yet" : x.guessScore + " guess") : "") +
          (x.prompterPoints != null ? " · " + x.prompterPoints + " prompter" : "") + "</small>" : "";
        var said = guessing && (x.guess || x.prompterName) ? '<span class="pod-guess">' +
          (x.guess ? "“" + esc(x.guess) + "”" : "") + (x.prompterName ? (x.guess ? " · " : "") + "picked " + esc(x.prompterName) : "") +
          (x.reason ? '<small>' + esc(x.reason) + "</small>" : "") + "</span>" : "";
        return "<li>" + avatar(x.id, x.name) + '<span class="pod-name">' + esc(x.name) + parts + said +
          (opts.scoreSelect ? opts.scoreSelect(x) : "") + "</span><b>" + x.score +
          '</b><small>' + (x.score === 1 ? "pt" : "pts") + "</small></li>";
      }).join("") + "</ol></div>";
  }

  // "Prompt by Ann and Ben", or "" when the round names nobody.
  function promptBy(r) {
    var ids = ((r && r.site_round_prompters) || []).map(function (p) { return p.competitor_id; });
    if (!ids.length) return Promise.resolve("");
    return PFML.api.people().then(function (people) {
      var names = {};
      Object.keys(people || {}).forEach(function (u) { names[people[u].competitorId] = people[u].name; });
      var list = ids.map(function (id) { return names[id] || "a member"; }).sort();
      return "Prompt by " + (list.length < 2 ? list[0] : list.slice(0, -1).join(", ") + " and " + list[list.length - 1]);
    });
  }

  // Where a track lives, to link it: where it was submitted (a round voted
  // on the site carries `link` for a YouTube or SoundCloud pick; README,
  // Site rounds in the stats), else Spotify. Null when there's neither.
  var LINK_SERVICES = { youtube: "YouTube", soundcloud: "SoundCloud" };
  function songUrl(t) {
    var link = t && t.link;
    if (link && link.platform === "youtube") return "https://www.youtube.com/watch?v=" + encodeURIComponent(link.id);
    if (link && link.platform === "soundcloud") {
      return "https://soundcloud.com/" + String(link.id).split("/").map(encodeURIComponent).join("/");
    }
    return t && t.spotifyId ? "https://open.spotify.com/track/" + encodeURIComponent(t.spotifyId) : null;
  }
  function songService(t) { return (t && t.link && LINK_SERVICES[t.link.platform]) || "Spotify"; }

  // The installed app's splash (README, Splash screen): index.html shows it
  // when PFML opens from the home screen, once per opening. It lifts once
  // sign-in is done, but not before SPLASH_MIN_MS from the page's start, so
  // it never just flickers, and by SPLASH_MAX_MS whatever happens: a
  // signed-out visitor's sign-in card is waiting under it.
  var SPLASH_MIN_MS = 600, SPLASH_MAX_MS = 2000;
  (function splash() {
    var el = document.getElementById("splash");
    if (!el || !document.documentElement.classList.contains("app-splash")) return;
    try { sessionStorage.setItem("pfml.splashSeen", "1"); } catch (e) { /* it shows again next time; no harm */ }
    var lifted = false;
    function lift() {
      if (lifted) return;
      lifted = true;
      el.classList.add("is-out");
      var meta = document.querySelector('meta[name="theme-color"]');
      if (meta && meta.getAttribute("data-was")) meta.content = meta.getAttribute("data-was");
      setTimeout(function () { document.documentElement.classList.remove("app-splash"); }, 350);
    }
    PFML.ready.then(function () { setTimeout(lift, Math.max(0, SPLASH_MIN_MS - performance.now())); });
    setTimeout(lift, Math.max(0, SPLASH_MAX_MS - performance.now()));
  })();

  PFML.avatar = avatar;
  PFML.roundOrder = roundOrder;
  PFML.songUrl = songUrl;
  PFML.songService = songService;
  PFML.reactionGlyph = reactionGlyph;
  PFML.when = when;
  PFML.translationHtml = translationHtml;
  PFML.closes = closes;
  PFML.siteVoting = SITE_VOTING;
  PFML.roundPhase = roundPhase;
  PFML.seasonPlayers = seasonPlayers;
  PFML.roundRoster = roundRoster;
  PFML.myRole = myRole;
  PFML.roundDJs = roundDJs;
  PFML.promptBy = promptBy;
  PFML.podiumScores = podiumScores;
  PFML.podiumHtml = podiumHtml;
  PFML.PROMPTER_POINTS = PROMPTER_POINTS;

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
    open: null,           // "menu" | "inbox" | "bell" | null
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

  /* ---- notifications (README, Reminders) ----
     Each phone or browser turns them on for itself: sw.js shows them, and
     the database keeps where the push service can reach this device
     (save_push_subscription). Hidden until the push key is set up
     (vapidPublicKey in config.js). On iPhone they only work in the installed
     app, so in Safari the panel says how to get it. */

  function pushKey() { return (window.PFML_CONFIG && window.PFML_CONFIG.vapidPublicKey) || ""; }
  function pushSupported() { return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window; }

  function keyBytes(b64) {
    var s = atob(b64.replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from(s, function (c) { return c.charCodeAt(0); });
  }

  function currentSubscription() {
    if (!pushSupported()) return Promise.resolve(null);
    return navigator.serviceWorker.getRegistration().then(function (reg) { return reg ? reg.pushManager.getSubscription() : null; });
  }

  // "ios-browser", "unsupported", "blocked", "off" or "on", for this device
  function notificationsState() {
    if (platform() === "ios" && !isApp()) return Promise.resolve("ios-browser");
    if (!pushSupported()) return Promise.resolve("unsupported");
    if (Notification.permission === "denied") return Promise.resolve("blocked");
    return currentSubscription().then(function (sub) { return sub ? "on" : "off"; });
  }

  function turnOnNotifications() {
    return Notification.requestPermission().then(function (perm) {
      if (perm !== "granted") throw new Error(perm === "denied" ? "blocked" : "not allowed");
      return navigator.serviceWorker.register("sw.js");
    }).then(function () { return navigator.serviceWorker.ready; }).then(function (reg) {
      return reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(pushKey()) });
    }).then(function (sub) {
      var j = sub.toJSON();
      return api().savePushSubscription(j.endpoint, j.keys.p256dh, j.keys.auth);
    });
  }

  function turnOffNotifications() {
    return currentSubscription().then(function (sub) {
      if (!sub) return null;
      var endpoint = sub.endpoint;
      return sub.unsubscribe().then(function () { return api().removePushSubscription(endpoint); });
    });
  }

  /* The bell, beside the inbox (asked for 2026-10-25): where anyone sees it
     as soon as a page loads. It opens this device's switch and one switch
     for each kind of notification, which are the member's own and apply to
     every device they turn on (my_notification_choices). */

  // drawn like the inbox tray; with a slash while this device has them off,
  // so the top bar shows the state at a glance
  var BELL_PATHS =
    '<path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.6 1.8H4.4z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>' +
    '<path d="M10 20.4a2.1 2.1 0 0 0 4 0" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>';
  var BELL_ICON = '<svg class="acct-icon" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">' +
    BELL_PATHS + "</svg>";
  var BELL_OFF_ICON = '<svg class="acct-icon" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">' +
    BELL_PATHS + '<path d="M4 4l16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>';

  // In the order the bell lists them. Voting's shows only once voting on the
  // site is switched on (PFML.siteVoting); until then it would never fire.
  var CHOICES = [
    ["round_open", "A new round opens"],
    ["playlist_ready", "A round's playlist is ready"],
    ["replies", "Replies to your comments"],
    ["reactions", "Reactions to your comments"],
    ["voting", "Voting closes and you haven't voted"],
    ["announcements", "Announcements from the commissioners"]
  ];

  var DEVICE_TEXT = {
    "ios-browser": "On iPhone, notifications work in the installed app. Add PFML to your home screen, open it from there, " +
      "and turn them on here.",
    unsupported: "This browser can't show notifications. On a phone, use Chrome on Android, or the installed app on iPhone.",
    blocked: "Notifications are blocked for PFML in this browser's settings. Allow them there, then come back here."
  };

  function setBellIcon(on) {
    var b = $("acctBellBtn");
    if (!b || b.getAttribute("data-on") === String(on)) return;
    b.setAttribute("data-on", String(on));
    b.innerHTML = on ? BELL_ICON : BELL_OFF_ICON;
    b.setAttribute("aria-label", on ? "Notifications: on for this device" : "Notifications: off for this device");
  }

  function renderBell(note) {
    var here = platform() === "desktop" ? "this browser" : "this phone";
    Promise.all([notificationsState(), api().myNotificationChoices().catch(function (err) { console.error(err); return null; })])
      .then(function (res) {
        var st = res[0], choices = res[1] && res[1][0];
        setBellIcon(st === "on");
        var device = DEVICE_TEXT[st]
          ? '<p class="acct-bell-note">' + DEVICE_TEXT[st] + "</p>" +
            (st === "ios-browser" ? '<button type="button" class="acct-bell-link" data-bell="how">Show me how</button>' : "")
          : '<button type="button" class="acct-item acct-theme acct-bell-device" data-bell="device" role="switch" aria-checked="' +
            (st === "on") + '">Notifications on ' + here + '<span class="acct-switch" aria-hidden="true"></span></button>';
        var list = choices ? CHOICES.filter(function (c) { return c[0] !== "voting" || PFML.siteVoting; }).map(function (c) {
          return '<button type="button" class="acct-item acct-theme" data-choice="' + c[0] + '" role="switch" aria-checked="' +
            !!choices[c[0]] + '">' + esc(c[1]) + '<span class="acct-switch" aria-hidden="true"></span></button>';
        }).join("") : '<p class="acct-bell-note">Your choices couldn’t load. Try again in a moment.</p>';
        $("acctBell").innerHTML =
          '<div class="acct-inbox-head"><b>Notifications</b><span>' + (st === "on" ? "On for " + here : "Off for " + here) + "</span></div>" +
          device +
          '<p class="acct-bell-sub">Tell me when</p>' + list +
          '<p class="acct-bell-note">These go to every phone or browser you turn notifications on.</p>' +
          (st === "on" ? '<button type="button" class="acct-bell-link" data-bell="test">Send me a test</button>' : "") +
          '<p class="acct-bell-msg" role="status"' + (note ? "" : " hidden") + ">" + esc(note || "") + "</p>";
      });
  }

  function onBellClick(ev) {
    var b = ev.target.closest("[data-bell], [data-choice]");
    if (!b) return;
    var kind = b.getAttribute("data-choice");
    if (kind) {
      // the switch moves at once; it goes back if the save fails
      var on = b.getAttribute("aria-checked") !== "true";
      b.setAttribute("aria-checked", String(on));
      api().setNotificationChoice(kind, on).catch(function (err) {
        console.error(err);
        b.setAttribute("aria-checked", String(!on));
        renderBell("That didn’t save: " + ((err && err.message) || err));
      });
      return;
    }
    var what = b.getAttribute("data-bell");
    b.disabled = true;
    if (what === "how") { close(true); showInstallHelp("ios"); return; }
    var done = what === "device"
      ? (b.getAttribute("aria-checked") === "true"
        ? turnOffNotifications().then(function () { return "Turned off for this device."; })
        : turnOnNotifications().then(function () { return "Turned on."; }))
      : api().testPush().then(function (r) { return r && r.sent ? "Sent. It should arrive in a moment." : "Nothing was sent. Try turning them off and on again."; });
    done.then(renderBell, function (err) {
      console.error(err);
      renderBell(err && err.message === "blocked" ? "" : "That didn’t work: " + ((err && err.message) || err));
    });
  }

  function build(member) {
    var bar = document.querySelector(".topbar-inner");
    if (!bar || bar.querySelector(".acct")) return;
    state.member = member;
    var box = document.createElement("div");
    box.className = "acct";
    box.innerHTML =
      '<button type="button" class="acct-get" id="acctGet" hidden>Get the app</button>' +
      '<button type="button" class="acct-btn acct-bell-btn" id="acctBellBtn" aria-expanded="false" aria-controls="acctBell" ' +
        'aria-label="Notifications" hidden>' + BELL_OFF_ICON + "</button>" +
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
        '<a class="acct-item" href="features">Site features</a>' +
        '<a class="acct-item" href="commissioner" id="acctCommish" hidden>Commissioner</a>' +
        // the admin's way into the round demo from the installed app,
        // which has no address bar (README, Round demo)
        '<a class="acct-item" href="round?demo=1" id="acctDemo" hidden>Round demo</a>' +
        '<button type="button" class="acct-item" id="acctInstall" hidden>Add to home screen</button>' +
        '<button type="button" class="acct-item acct-theme" id="acctTheme" role="switch" aria-checked="' + isDark() + '">' +
          'Dark mode<span class="acct-switch" aria-hidden="true"></span></button>' +
        '<button type="button" class="acct-item" id="acctSignOut">Sign out</button>' +
      "</div>" +
      '<div class="acct-pop acct-inbox" id="acctInbox" hidden role="region" aria-label="Inbox">' +
        '<div class="acct-inbox-head"><b>Inbox</b><span>Reactions and replies to your comments</span></div>' +
        '<div class="acct-inbox-list" id="acctInboxList"><p class="acct-empty">Loading…</p></div>' +
      "</div>" +
      '<div class="acct-pop acct-bell" id="acctBell" hidden role="region" aria-label="Notifications"></div>';
    bar.appendChild(box);

    $("acctInboxBtn").addEventListener("click", function () { toggle("inbox"); });
    $("acctMeBtn").addEventListener("click", function () { toggle("menu"); });
    $("acctSignOut").addEventListener("click", function () { PFML.signOut(); });
    $("acctTheme").addEventListener("click", function () { setDark(!isDark()); });
    $("acctCommish").hidden = member.role !== "admin" && member.role !== "commissioner";
    $("acctDemo").hidden = member.role !== "admin";
    $("acctGet").addEventListener("click", addToHomeScreen);
    $("acctInstall").addEventListener("click", addToHomeScreen);
    // the bell, once the push key is set up (config.js)
    $("acctBellBtn").hidden = !pushKey();
    $("acctBellBtn").addEventListener("click", function () { toggle("bell"); });
    $("acctBell").addEventListener("click", onBellClick);
    if (pushKey()) notificationsState().then(function (st) { setBellIcon(st === "on"); });
    showInstallControls();
    document.addEventListener("click", closeFromOutside);
    document.addEventListener("keydown", closeOnEscape);
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible" && Date.now() - state.fetchedAt > REFRESH_MS) refresh();
    });
    refresh();
    // a reply or reaction notification opens the inbox (?inbox=1); the
    // address is tidied so a reload doesn't open it again
    if (/(^|&)inbox=1(&|$)/.test(location.search.slice(1))) {
      history.replaceState(history.state, "", location.pathname +
        location.search.replace(/([?&])inbox=1(&|$)/, function (m, a, b) { return b ? a : ""; }) + location.hash);
      toggle("inbox");
    }
  }

  /* ---- open / close ---- */

  // which pop-up goes with which button
  var POPS = { inbox: ["acctInboxBtn", "acctInbox"], menu: ["acctMeBtn", "acctMenu"], bell: ["acctBellBtn", "acctBell"] };

  function toggle(which) {
    if (state.open === which) { close(); return; }
    close(true);
    state.open = which;
    var btn = $(POPS[which][0]), pop = $(POPS[which][1]);
    btn.setAttribute("aria-expanded", "true");
    pop.hidden = false;
    if (which === "inbox") openInbox();
    if (which === "bell") renderBell();
  }

  function close(quiet) {
    if (!state.open) return;
    var btn = $(POPS[state.open][0]), pop = $(POPS[state.open][1]);
    btn.setAttribute("aria-expanded", "false");
    pop.hidden = true;
    state.open = null;
    if (!quiet) btn.focus();
  }

  // The path as it was when the click began: a pop-up can redraw what was
  // clicked before this runs (the bell redraws its icon), and a detached
  // target has no .acct above it any more.
  function closeFromOutside(ev) {
    if (!state.open) return;
    var path = ev.composedPath ? ev.composedPath() : [ev.target];
    if (path.some(function (el) { return el.classList && el.classList.contains("acct"); })) return;
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
