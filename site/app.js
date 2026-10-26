/* PFML — front end.
   Loads the JSON that scripts/build.py generates from the Music League CSV
   exports and renders it. No framework, no build step, no Spotify API:
   every Spotify link is a plain open.spotify.com URL built from IDs
   already present in the export.

   Page types sharing this file:
     - home page    (<body data-page="home">)   -> season cards + playlists
     - season page  (<body data-page="season" data-season-key="seasonN">)
                                                  -> full season dashboard
     - career, round and profile pages (data-page="career" | "round" | "profile")
   All render a season nav in the top bar from index.json.

   Every page that loads this loads auth.js and account.js first (and
   rounds.js, on season and round pages), so window.PFML is always there:
   data comes from PFML.loadJSON, the private bucket, never a public file. */

(function () {
  "use strict";

  var PFML = window.PFML;

  function $(id) { return document.getElementById(id); }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function el(tag, cls, html) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  }

  function setBlock(id, node) {
    var host = $(id);
    if (!host) return;
    host.innerHTML = "";
    host.appendChild(node);
  }

  function empty(msg) { return el("div", "empty", esc(msg)); }

  // A person's name as a quiet link to their profile (.plink: same colour
  // and weight as the text around it). Most of the data only carries the
  // name, so ids come from whatever the page loaded (knowPeople); names
  // were checked to be unique across every season. Falls back to plain
  // text for a name it can't place.
  var profileIds = {};
  function knowPeople(list) {
    (list || []).forEach(function (p) { if (p && p.name && p.id && !profileIds[p.name]) profileIds[p.name] = p.id; });
  }
  function who(name, id) {
    id = id || profileIds[name];
    if (!id) return esc(name);
    return '<a class="plink" href="profile?p=' + encodeURIComponent(id) + '">' + esc(name) + "</a>";
  }
  // The noun alone, for "3 " + plural(3, "round"). (rounds.js's counted()
  // includes the number.)
  function plural(n, one, many) { return n === 1 ? one : (many || one + "s"); }

  /* ---- Spotify links -------------------------------------------------
     Track and playlist IDs are in the export, so those are exact links.
     Artist and album names are text only, with no IDs, so those go to a
     Spotify search scoped to the name. */

  // where the track was submitted: Spotify, or YouTube/SoundCloud for a
  // round voted on the site (PFML.songUrl, account.js)
  function trackLink(t) { return PFML.songUrl(t); }
  function searchLink(q) { return "https://open.spotify.com/search/" + encodeURIComponent(q); }

  function extLink(href, text, cls) {
    if (!href) return esc(text);
    return '<a href="' + esc(href) + '" target="_blank" rel="noopener"' +
      (cls ? ' class="' + cls + '"' : "") + ">" + esc(text) + "</a>";
  }

  function artistLinks(list, fallbackText) {
    var arr = (list && list.length) ? list : (fallbackText ? [fallbackText] : []);
    return arr.map(function (a) { return extLink(searchLink(a), a); }).join(", ");
  }

  /* ---- shared top-bar season nav ---- */

  function renderNav(index, activeKey) {
    var nav = $("seasonTabs");
    if (!nav) return;
    nav.innerHTML = "";
    var home = el("a", "season-tab");
    home.href = "./";
    home.textContent = "Home";
    home.setAttribute("aria-current", String(!activeKey));
    nav.appendChild(home);
    nav.appendChild(seasonPicker(index, activeKey));

    var career = el("a", "season-tab");
    career.href = "career";
    career.textContent = "All-Time";
    career.setAttribute("aria-current", String(activeKey === "career"));
    nav.appendChild(career);
    syncScrollPadding();
  }

  // Every season in one pill: it names the season you're on, or the one in
  // progress anywhere else, and opens a list of all of them, newest first.
  function seasonPicker(index, activeKey) {
    var onSeason = index.seasons.some(function (s) { return s.key === activeKey; });
    var shownKey = onSeason ? activeKey : index.currentSeason;
    var shown = index.seasons.filter(function (s) { return s.key === shownKey; })[0] || index.seasons[index.seasons.length - 1];
    var pip = '<span class="pip" aria-hidden="true"></span>';

    var wrap = el("div", "season-pick");
    var btn = el("button", "season-tab season-pick-btn");
    btn.type = "button";
    btn.id = "seasonPickBtn";
    btn.setAttribute("aria-expanded", "false");
    btn.setAttribute("aria-controls", "seasonMenu");
    btn.setAttribute("aria-current", String(onSeason));
    btn.innerHTML = (shown && shown.key === index.currentSeason ? pip : "") + esc(shown ? shown.label : "Seasons") +
      '<svg class="season-caret" viewBox="0 0 12 12" width="10" height="10" aria-hidden="true" focusable="false">' +
      '<path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';

    var menu = el("div", "season-menu");
    menu.id = "seasonMenu";
    menu.hidden = true;
    menu.innerHTML = index.seasons.slice().reverse().map(function (s) {
      var live = s.key === index.currentSeason;
      return '<a class="season-menu-item" href="' + esc(s.key) + '" aria-current="' + (s.key === activeKey) + '">' +
        (live ? pip : '<span class="pip-gap" aria-hidden="true"></span>') + "<span>" + esc(s.label) + "</span>" +
        (live ? '<small>In progress</small>' : "") + "</a>";
    }).join("");

    function setOpen(open) {
      menu.hidden = !open;
      btn.setAttribute("aria-expanded", String(open));
    }
    btn.addEventListener("click", function () { setOpen(menu.hidden); });
    document.addEventListener("click", function (ev) {
      if (!menu.hidden && ev.target.closest && !ev.target.closest(".season-pick")) setOpen(false);
    });
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && !menu.hidden) { setOpen(false); btn.focus(); }
    });
    wrap.appendChild(btn);
    wrap.appendChild(menu);
    return wrap;
  }

  var JUMP_SECTIONS = [
    ["block-standings", "Standings"],
    ["block-rounds", "Results"],
    ["block-highlights", "Numbers"],
    ["block-trend", "Trend"],
    ["block-tracks", "Tracks"],
    ["block-taste", "Taste"],
    ["block-voters", "Voting"],
    ["block-comments", "Comments"],
    ["block-artists", "Artists"],
  ];

  function renderJumpNav(d) {
    var nav = $("jumpNav");
    if (!nav) return;
    nav.innerHTML = "";
    if (!d.rounds.length) { nav.hidden = true; syncScrollPadding(); return; }
    nav.hidden = false;
    JUMP_SECTIONS.forEach(function (pair) {
      var id = pair[0], label = pair[1];
      var section = document.getElementById(id);
      if (!section || section.hidden) return;
      var a = el("a", "jump-link", esc(label));
      a.href = "#" + id;
      nav.appendChild(a);
    });
    syncScrollPadding();
  }

  // The sticky top bar is roughly 100px tall on a desktop but about 180px
  // on a phone, where the season tabs and jump links wrap. No fixed CSS
  // offset fits both, so a #section link landed its section under the bar:
  // measured at 418px wide, 154px of the 188px Results by round bar was
  // hidden. Keep the scroll padding equal to the bar's real height.
  // The round page's pinned track bar (.rp-pin) sits just under the top
  // bar, so it needs the same real height: --topbar-h.
  function syncScrollPadding() {
    var bar = document.querySelector(".topbar");
    if (!bar) return;
    document.documentElement.style.scrollPaddingTop = (bar.offsetHeight + 12) + "px";
    document.documentElement.style.setProperty("--topbar-h", bar.offsetHeight + "px");
  }
  window.addEventListener("resize", syncScrollPadding);

  // The browser jumps to a #section on load, before the data has filled
  // the page in above it, so the target ends up in the wrong place. Jump
  // again once the page is rendered.
  function scrollToHash() {
    var target = location.hash && document.getElementById(location.hash.slice(1));
    if (target) target.scrollIntoView({ block: "start", behavior: "instant" });
  }

  /* =====================================================================
     HOME PAGE
     ===================================================================== */

  function fmtDate(iso) {
    if (!iso) return null;
    var d = new Date(iso);
    if (isNaN(d.getTime())) return null;
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  }

  function seasonCard(s, isLive) {
    var a = el("a", "season-card" + (isLive ? " is-live" : ""));
    a.href = s.key;

    var nameHtml = '<div class="season-card-name-wrap"><span class="season-card-name">' + esc(s.label) + "</span>" +
      (isLive ? '<span class="live-badge"><span class="pip" aria-hidden="true"></span>Live</span>' : "") + "</div>";

    var statLine = s.roundCount
      ? s.roundCount + " " + plural(s.roundCount, "round") + " &middot; " + s.songCount + " tracks &middot; " + s.playerCount + " players"
      : s.playerCount + " players &middot; not started yet";

    var roundLine = "";
    // The export only ever holds finished rounds (see build.py), so the
    // latest one is complete and the next is underway. Which phase that
    // next round is in isn't in the data, so the card doesn't say.
    if (isLive && s.liveRound) {
      roundLine = '<div class="season-card-round">Round ' + s.liveRound.number + ": " + esc(s.liveRound.name) +
        '<span class="phase">Complete</span></div>' +
        '<div class="season-card-round">Round ' + (s.liveRound.number + 1) + " underway</div>";
    }
    var startedLine = "";
    if (isLive && s.startedAt) {
      var d = fmtDate(s.startedAt);
      if (d) startedLine = '<div class="season-card-round">Started ' + d + "</div>";
    }

    var leaderHtml = "";
    if (s.leaderName) {
      var leaders = (s.leaderNames && s.leaderNames.length) ? s.leaderNames : [s.leaderName];
      var label = isLive ? (leaders.length > 1 ? "Tied for the lead" : "Leading")
                         : (leaders.length > 1 ? "Joint winners" : "Winner");
      leaderHtml = '<div class="season-card-leader"><span class="lbl">' + label + '</span>' +
        '<div class="val">' + joinNames(leaders) + ' <span class="pts">' + s.leaderPoints + ' pts</span></div></div>';
    }

    a.innerHTML =
      '<div class="season-card-top">' + nameHtml + '<span class="season-card-arrow">&rarr;</span></div>' +
      '<div class="season-card-stats">' + statLine + "</div>" + roundLine + startedLine + leaderHtml;
    return a;
  }

  // Career is also the last tab in the top bar; the card here gives it a
  // one-line summary next to the season cards.
  function careerCard(index) {
    var played = index.seasons.filter(function (s) { return s.roundCount > 0; }).length;
    var a = el("a", "season-card season-card-career");
    a.href = "career";
    a.innerHTML =
      '<div class="season-card-top"><div class="season-card-name-wrap"><span class="season-card-name">All-Time</span></div>' +
      '<span class="season-card-arrow">&rarr;</span></div>' +
      '<div class="season-card-stats">All-time standings across ' + played + " " + plural(played, "season") + "</div>" +
      '<div class="season-card-round">Career Score, League Highlights, all-time comment stats</div>';
    return a;
  }

  // Drawn icons (not a brand logo): a medal for podium playlists, a stack
  // of records for everything submitted.
  var PLAYLIST_ICONS = {
    podium: '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false"><circle cx="12" cy="15" r="5.5" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M8.5 3.5 11 9.6M15.5 3.5 13 9.6M10.6 15l1-1v4" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    all: '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false"><circle cx="10" cy="13" r="7" fill="none" stroke="currentColor" stroke-width="1.7"/><circle cx="10" cy="13" r="1.8" fill="currentColor"/><path d="M14.5 5.6A7 7 0 0 1 20.8 13" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>'
  };

  // "47 min", "4 hr 43 min"; an estimate (a playlist past the 100 tracks
  // publish.py can time) is rounded to the hour and says so.
  function runTime(ms, exact) {
    var mins = Math.round(ms / 60000);
    if (!exact) return "about " + Math.max(1, Math.round(mins / 60)) + " hr";
    if (mins < 60) return mins + " min";
    return Math.floor(mins / 60) + " hr" + (mins % 60 ? " " + (mins % 60) + " min" : "");
  }

  // Two parts, so a phone can stack them rather than wrap mid-phrase.
  function playlistStatsParts(st) {
    return [st.tracks.toLocaleString("en-US") + " " + plural(st.tracks, "track"), runTime(st.durationMs, st.exact)];
  }

  // One playlist as a tile: which group it belongs to, its name without
  // the "PFML - S1 - " prefix every label repeats, its size (from
  // playlist_stats.json, keyed by playlist id, when publish.py could get
  // it), and where it goes. The ↗ in the corner marks it as leaving the
  // site for Spotify; the full words are in its aria-label.
  function playlistTile(item, group, stats) {
    var name = String(item.label || "").replace(/^PFML\s*-\s*(S\d+\s*-\s*)?/i, "");
    var icon = /podium/i.test(item.label) ? PLAYLIST_ICONS.podium : PLAYLIST_ICONS.all;
    // https only: the data comes from the storage bucket, and a swapped file
    // mustn't be able to plant a javascript: link (README, Members only)
    var url = /^https:\/\//i.test(item.url || "") ? item.url : "";
    var idm = /playlist\/([A-Za-z0-9]+)/.exec(url);
    var st = idm && stats && stats[idm[1]];
    var inner = '<span class="pl-top"><span class="pl-icon">' + icon + "</span>" +
        (url ? '<span class="pl-out" aria-hidden="true">&nearr;</span>' : "") + "</span>" +
      '<span class="pl-kicker">' + esc(group) + "</span>" +
      '<span class="pl-name">' + esc(name) + "</span>" +
      '<span class="pl-cta">' + (!url ? "Coming soon" : !st ? "Open in Spotify" :
        playlistStatsParts(st).map(function (x) { return '<span class="pl-stat">' + x + "</span>"; }).join("")) + "</span>";
    if (!url) {
      var soon = el("div", "pl-tile is-soon", inner);
      soon.setAttribute("aria-label", item.label + ", coming soon");
      return soon;
    }
    var a = el("a", "pl-tile", inner);
    a.href = url; a.target = "_blank"; a.rel = "noopener";
    a.setAttribute("aria-label", item.label + (st ? ", " + playlistStatsParts(st).join(", ") : "") + ", opens in Spotify");
    return a;
  }

  // League-wide first, then seasons newest first, like the season menu.
  function renderPlaylists(pl, stats) {
    var host = $("playlists");
    if (!host) return;
    host.innerHTML = "";
    if (!pl) { host.appendChild(empty("Playlists haven't been added yet.")); return; }
    var grid = el("div", "pl-grid");
    (pl.leagueWide || []).forEach(function (item) { grid.appendChild(playlistTile(item, "League-wide", stats)); });
    (pl.seasons || []).slice().reverse().forEach(function (group) {
      group.items.forEach(function (item) { grid.appendChild(playlistTile(item, group.season, stats)); });
    });
    host.appendChild(grid);
  }

  // The commissioners' announcements from the last week, newest first, up
  // to three (README, Commissioner extras). Without the table yet, nothing.
  var ANNOUNCE_DAYS = 7;
  function renderAnnouncements() {
    var box = $("announceBox");
    if (!box || typeof PFML.api.announcements !== "function") return;
    Promise.all([PFML.api.announcements(), PFML.api.people()]).then(function (res) {
      var since = Date.now() - ANNOUNCE_DAYS * 864e5;
      var list = (res[0] || []).filter(function (a) { return Date.parse(a.created_at) > since; }).slice(0, 3);
      if (!list.length) return;
      var people = res[1] || {};
      box.innerHTML = list.map(function (a) {
        var who = people[a.created_by] ? people[a.created_by].name : "A commissioner";
        return '<article class="announce-card"><p class="announce-kicker">From the commissioners</p>' +
          '<p class="announce-body">' + esc(a.body) + "</p>" +
          '<p class="announce-who">' + esc(who) + " \u00b7 " +
            esc(new Date(a.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })) + "</p></article>";
      }).join("");
      box.hidden = false;
    }).catch(function (err) { console.error(err); });
  }

  // A round open for submissions on the site gets a banner on the home
  // page. Without the tables (a database the migration hasn't reached) it
  // just doesn't show.
  function renderSubmitBanner() {
    var box = $("submitBanner");
    if (!box) return;
    PFML.api.siteRounds().then(function (rounds) {
      var open = (rounds || []).filter(function (r) { return PFML.roundPhase(r) === "submitting"; })[0];
      if (!open) { votingBanner(rounds || []); return; }
      var closes = PFML.closes(open.closes_at);
      box.innerHTML = '<a class="sub-banner-link" href="submit"><span class="sub-banner-kicker">Open for submissions</span>' +
        "<b>" + esc(open.name) + '</b><span class="sub-banner-count" id="submitBannerCount"></span>' +
        '<span class="sub-banner-when">Closes ' + esc(closes.at) + " \u00b7 " + esc(closes.left) + "</span>" +
        '<span class="sub-banner-mine" id="submitBannerMine"></span>' +
        '<span class="sub-banner-go" id="submitBannerGo">Submit your track \u2192</span></a>';
      box.hidden = false;
      bannerCount(open);
      bannerMine(open);
    }).catch(function (err) { console.error(err); });
  }

  // A round voting on the site (README, Voting on the site), only while the
  // switch in account.js is on: when voting closes, and whether the reader's
  // ballot is in. Only players with a track in the round vote.
  function votingBanner(rounds) {
    if (!PFML.siteVoting) return;
    var r = rounds.filter(function (x) { return PFML.roundPhase(x) === "voting"; })[0];
    if (!r) return;
    var closes = PFML.closes(r.voting_closes_at);
    $("submitBanner").innerHTML = '<a class="sub-banner-link" href="submit"><span class="sub-banner-kicker">Voting is open</span>' +
      "<b>" + esc(r.name) + "</b>" +
      '<span class="sub-banner-when">Voting closes ' + esc(closes.at) + " · " + esc(closes.left) + "</span>" +
      '<span class="sub-banner-mine" id="submitBannerMine"></span>' +
      '<span class="sub-banner-go" id="submitBannerGo">Listen and vote →</span></a>';
    $("submitBanner").hidden = false;
    Promise.all([PFML.api.mySubmissions(r.id), PFML.api.myBallot(r.id)]).then(function (res) {
      if (!res[0].length) { $("submitBannerGo").textContent = "Listen to the round →"; return; }
      var voted = res[1] && res[1].length;
      $("submitBannerMine").textContent = voted ? "✓ Your ballot is in" : "You haven't voted yet";
      $("submitBannerMine").classList.toggle("is-in", !!voted);
      if (voted) $("submitBannerGo").textContent = "Change your ballot →";
    }).catch(function (err) { console.error(err); });
  }

  // Whether the reader has a track in: their own submission only, the one
  // thing anyone can ask about themselves (my_submission).
  function bannerMine(round) {
    // a round can take more than one song from each player: in once all
    // of theirs are
    var n = round.songs_per_round || 1;
    PFML.api.mySubmissions(round.id).then(function (mine) {
      var all = mine.length >= n;
      $("submitBannerMine").textContent = all ? "\u2713 You're in"
        : mine.length ? mine.length + " of your " + n + " tracks in" : "You haven't submitted yet";
      $("submitBannerMine").classList.toggle("is-in", all);
      if (mine.length) $("submitBannerGo").textContent = (all ? (n === 1 ? "Change your track" : "Change your tracks") : "Send your next track") + " \u2192";
    }).catch(function (err) { console.error(err); });
  }

  // "7/20 submitted": players with a track in, out of the players taking
  // part this season (index.json activePlayers, built from the latest
  // finished round). Who, never which track; the Submit page shows names.
  function bannerCount(round) {
    if (typeof PFML.api.roundSubmitters !== "function") return;
    Promise.all([PFML.seasonPlayers(round.season_key), PFML.api.roundSubmitters(round.id)]).then(function (res) {
      var players = res[0];
      if (!players || !players.length) return;
      // a player is in once all of the round's songs from them are
      var sent = {}, n = round.songs_per_round || 1;
      (res[1] || []).forEach(function (id) { sent[id] = (sent[id] || 0) + 1; });
      var done = players.filter(function (p) { return sent[p.id] >= n; }).length;
      $("submitBannerCount").textContent = done + "/" + players.length + " submitted";
    }).catch(function (err) { console.error(err); });
  }

  // From the vault (vault.json, build.build_vault): one past round winner at
  // random each visit, with its note and the comment from whoever backed it
  // most. The section stays hidden if the file isn't there.
  function renderVault() {
    PFML.loadJSON("vault.json").then(function (v) {
      var list = (v && v.winners) || [];
      if (!list.length) return;
      var w = list[Math.floor(Math.random() * list.length)];
      var c = w.comment;
      $("vaultCard").innerHTML = '<article class="vault-card">' +
        (w.art ? '<img class="vault-art" src="' + esc(w.art) + '" alt="" width="96" height="96" loading="lazy">' : "") +
        '<div class="vault-text">' +
          '<p class="vault-where"><a href="round?s=' + encodeURIComponent(w.seasonKey) + "&r=" + encodeURIComponent(w.roundId) + '">' +
            esc(w.seasonLabel) + ", Round " + w.roundNumber + ": " + esc(w.roundName) + "</a></p>" +
          "<h3>" + esc(w.title) + "</h3>" +
          '<p class="vault-by">' + esc(w.artistText) + ' &middot; won with ' + w.points + ' pts, sent by <a href="' + profileUrl(w.submitterId) + '">' + esc(w.submitterName) + "</a></p>" +
          (w.note ? '<p class="vault-note">“' + esc(w.note) + "” <small>" + esc(w.submitterName) + "</small></p>" : "") +
          (c ? '<p class="vault-comment">“' + esc(c.comment) + "” <small>" + esc(c.voterName) + "</small>" + PFML.translationHtml(c.translation) + "</p>" : "") +
          (PFML.songUrl(w) ? '<a class="pill" href="' + esc(PFML.songUrl(w)) + '" target="_blank" rel="noopener">Play on ' + PFML.songService(w) + " &nearr;</a>" : "") +
        "</div></article>";
      $("block-vault").hidden = false;
    }).catch(function (err) { console.error(err); });
  }

  // The newest line in the features page's "New in the last 30 days" box (a test
  // keeps the two equal). The features page records the newest date it
  // showed in this browser; Home's button says New until that catches up.
  var FEATURES_UPDATED = "2026-10-26";
  var FEATURES_SEEN_KEY = "pfml.featuresSeen";

  function renderFeaturesButton() {
    var seen = null;
    try { seen = localStorage.getItem(FEATURES_SEEN_KEY) || ""; } catch (e) { return; }   // can't remember: don't nag
    var recent = Date.parse(FEATURES_UPDATED + "T12:00:00Z") >= Date.now() - 30 * 24 * 60 * 60 * 1000;
    var unseen = recent && seen < FEATURES_UPDATED;
    $("featuresNew").hidden = !unseen;
    $("featuresBtn").setAttribute("aria-label", "What's new on the site" + (unseen ? ", new features since your last look" : ""));
  }

  function initHome() {
    renderFeaturesButton();
    renderSubmitBanner();
    renderAnnouncements();
    renderVault();
    PFML.loadJSON("index.json").then(function (index) {
      renderNav(index, null);
      var grid = el("div", "season-grid");
      if (!index.seasons.length) {
        setBlock("seasonCards", empty("No seasons yet."));
      } else {
        index.seasons.slice().reverse().forEach(function (s) {
          var isLive = s.key === index.currentSeason && s.roundCount > 0;
          grid.appendChild(seasonCard(s, isLive));
        });
        grid.appendChild(careerCard(index));
        setBlock("seasonCards", grid);
      }
      // Stats are optional: without them the tiles just say "Open in Spotify".
      return Promise.all([
        PFML.loadJSON("playlists.json").catch(function () { return null; }),
        PFML.loadJSON("playlist_stats.json").catch(function () { return null; })
      ]);
    }).then(function (res) { renderPlaylists(res[0], res[1]); }).catch(function (err) {
      console.error(err);
      setBlock("seasonCards", empty("Couldn't load season data."));
    });
  }

  /* =====================================================================
     SEASON PAGE
     ===================================================================== */

  /* ---- player selection state (season pages only) ---- */

  var selected = [];      // ordered array of competitor ids, click order
  var seasonData = null;

  function isSelected(id) { return selected.indexOf(id) !== -1; }

  function toggleSelected(id) {
    var i = selected.indexOf(id);
    if (i === -1) selected.push(id); else selected.splice(i, 1);
    rerenderFiltered();
  }

  function clearSelected() {
    selected = [];
    rerenderFiltered();
  }

  function rerenderFiltered() {
    if (!seasonData) return;
    renderStandings(seasonData);
    renderFocus(seasonData);
    renderHighlights(seasonData);
    trendSelected = selected.length ? selected.slice() : seasonData.standings.map(function (p) { return p.id; });
    trendGroupsOn = [];
    renderTrend(seasonData);
    renderTopTracks(seasonData);
    renderRounds(seasonData);
    renderTaste(seasonData);
    renderVoters(seasonData);
    renderComments(seasonData);
    renderArtists(seasonData);
    renderJumpNav(seasonData);
  }

  function nameOf(d, id) {
    for (var i = 0; i < d.competitors.length; i++) if (d.competitors[i].id === id) return d.competitors[i].name;
    return "Unknown";
  }

  function selectedNamesHtml(d) {
    return selected.map(function (id) { return "<b>" + esc(nameOf(d, id)) + "</b>"; }).join(", ");
  }

  function attachFilterTag(host, d) {
    if (!selected.length) return;
    var tag = el("p", "filter-tag");
    tag.innerHTML = "Filtered to " + selectedNamesHtml(d) + ". ";
    var clear = el("a", "filter-tag-clear", "Clear");
    clear.href = "#";
    clear.addEventListener("click", function (ev) { ev.preventDefault(); clearSelected(); });
    tag.appendChild(clear);
    host.appendChild(tag);
  }

  /* ---- Daily Double (Season 3 rule) ----
     A submitter's one doubled track per season. The bonus is in their
     total; the line says how much of it came from the Daily Double and
     from which track and round, so the total never looks unexplained. */

  function dailyDoubleLine(p) {
    var dd = p && p.dailyDouble;
    if (!dd) return "";
    return '<div class="stand-dd"><span class="dd-badge">Daily Double</span>+' + dd.bonus +
      " pts &middot; " + esc(dd.trackTitle) + " &middot; " + esc(dd.roundName) + "</div>";
  }

  /* ---- standings (clickable) ---- */

  // The collapsed Standings bar: player count and everyone placed 3rd or
  // better. Ties share a place, so that can be more than three people
  // (Season 3 opened with two tied for 1st); past four it shows three and
  // says how many more, so a big tie can't flood the bar.
  function renderStandingsSummary(d) {
    var count = $("standCount"), top = $("standTop");
    if (count) {
      count.textContent = d.standings.length
        ? d.standings.length + " " + plural(d.standings.length, "player") + " · after " +
          d.rounds.length + " " + plural(d.rounds.length, "round")
        : "No standings yet";
    }
    if (!top) return;
    var podium = d.standings.filter(function (p) { return p.rank <= 3; });
    var shown = podium.length > 4 ? podium.slice(0, 3) : podium;
    top.innerHTML = shown.map(function (p) {
      return '<span class="stand-top-chip is-' + p.rank + '"' + (p.tied ? ' title="Tied on points"' : "") + ">" +
        '<span class="pl">' + placeLabel(p) + '</span><span class="nm">' + esc(p.name) + '</span><span class="pt">' + p.points + "</span></span>";
    }).join("") + (podium.length > shown.length
      ? '<span class="stand-top-more">+' + (podium.length - shown.length) + " more</span>" : "");
  }

  // The filters in use, in the Standings bar so they show open or closed:
  // tap a name to take it off, or Clear all.
  function renderStandingsFilters(d) {
    var host = $("standFilters");
    if (!host) return;
    host.innerHTML = "";
    host.hidden = !selected.length;
    if (!selected.length) return;
    host.appendChild(el("span", "stand-filters-label", "Filtered to"));
    selected.forEach(function (id) {
      var name = nameOf(d, id);
      var chip = el("button", "stand-filter",
        '<span class="nm">' + esc(name) + '</span><span class="x" aria-hidden="true">&times;</span>');
      chip.type = "button";
      chip.setAttribute("aria-label", "Remove " + name + " from the filter");
      // Stop here: removing a filter re-renders this row, detaching the
      // button before the click reaches the bar, so the bar could no longer
      // tell it came from a filter and would fold the section.
      chip.addEventListener("click", function (ev) { ev.stopPropagation(); toggleSelected(id); });
      host.appendChild(chip);
    });
    var clear = el("button", "stand-filters-clear", "Clear all");
    clear.type = "button";
    clear.addEventListener("click", function (ev) { ev.stopPropagation(); clearSelected(); });
    host.appendChild(clear);
  }

  // Standings opens and closes from its bar. Its filter buttons live in
  // that bar too, so clicks on them are left out of the toggle.
  function initStandingsFold() {
    var fold = $("standFold"), bar = $("standBar"), btn = $("standToggle"), panel = $("standPanel");
    if (!fold || !bar || !btn || !panel) return;
    bar.addEventListener("click", function (ev) {
      if (ev.target.closest && ev.target.closest("#standFilters")) return;
      var open = panel.hidden;
      panel.hidden = !open;
      fold.classList.toggle("is-open", open);
      btn.setAttribute("aria-expanded", String(open));
    });
  }

  function renderStandings(d) {
    renderStandingsSummary(d);
    renderStandingsFilters(d);
    if (!d.standings.length) { setBlock("standings", empty("No submissions yet. Standings appear once the first round closes.")); return; }
    var max = Math.max.apply(null, d.standings.map(function (p) { return p.points; }).concat([1]));
    var box = el("div", "framed");
    d.standings.forEach(function (p, i) {
      var pct = Math.max(3, Math.round((p.points / max) * 100));
      var on = isSelected(p.id);
      var row = el("div", "stand-row is-clickable" + (on ? " is-selected" : ""));
      row.setAttribute("data-id", p.id);
      row.setAttribute("role", "button");
      row.setAttribute("tabindex", "0");
      row.setAttribute("aria-pressed", String(on));
      row.title = on ? "Click to remove " + p.name + " from comparison" : "Click to compare " + p.name;
      row.innerHTML =
        '<div class="stand-rank' + (p.rank <= 3 ? " is-" + p.rank : "") + '"' + (p.tied ? ' title="Tied on points"' : "") + ">" + placeLabel(p) + "</div>" +
        '<div><div class="stand-name">' + esc(p.name) + "</div>" +
        '<div class="bar"><i style="width:' + pct + '%"></i></div>' + dailyDoubleLine(p) + "</div>" +
        '<div class="stand-score"><b>' + p.points + "</b><span>" +
        p.avgPerSubmission + " avg &middot; " + p.roundsWon + " won &middot; " + p.podiums + " top-3</span></div>";
      row.addEventListener("click", function () { toggleFromStandings(p.id, row); });
      row.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); toggleFromStandings(p.id, row); }
      });
      box.appendChild(row);
    });
    setBlock("standings", box);
  }

  // A tap on a name re-renders the page, and the "Filtered to" row in the
  // bar above the list grows or shrinks, so the list moved under the
  // finger: measured at 375px with scroll anchoring off (as on Safari,
  // which has none), the tapped name jumped 99px on the first tap and 68px
  // when the chips wrapped. Chrome's scroll anchoring hid it. Put the
  // tapped row back where it was, whichever browser it is.
  function toggleFromStandings(id, row) {
    var before = row.getBoundingClientRect().top;
    toggleSelected(id);
    var now = document.querySelector('#standings .stand-row[data-id="' + cssEscape(id) + '"]');
    if (!now) return;
    var moved = now.getBoundingClientRect().top - before;
    // instant: the page has scroll-behavior: smooth, and a smooth scroll
    // would visibly slide the list back instead of never moving it
    if (Math.abs(moved) >= 1) window.scrollBy({ top: moved, behavior: "instant" });
  }

  function cssEscape(s) {
    return window.CSS && CSS.escape ? CSS.escape(s) : String(s).replace(/["\\]/g, "\\$&");
  }

  /* ---- player focus / comparison panel ---- */

  function songsBy(d, id) {
    var out = [];
    d.rounds.forEach(function (r) { r.songs.forEach(function (s) { if (s.submitterId === id) out.push(s); }); });
    return out;
  }

  function tasteTo(d, id) { return d.taste.filter(function (t) { return t.submitterId === id; }); }
  function tasteFrom(d, id) { return d.taste.filter(function (t) { return t.voterId === id; }); }
  function tastePair(d, voterId, submitterId) {
    for (var i = 0; i < d.taste.length; i++) {
      var t = d.taste[i];
      if (t.voterId === voterId && t.submitterId === submitterId) return t;
    }
    return null;
  }

  function renderFocusIndividual(d, id, host) {
    var name = nameOf(d, id);
    var standing = null;
    for (var i = 0; i < d.standings.length; i++) if (d.standings[i].id === id) { standing = d.standings[i]; break; }

    if (!standing) {
      host.appendChild(empty(name + " hasn't submitted anything yet this season."));
      return;
    }

    var rank = (standing.tied ? "Tied #" : "#") + standing.rank;
    var songs = songsBy(d, id);
    var g = el("div", "hl-grid");

    g.appendChild(tile("Season standing", rank + " of " + d.standings.length,
      standing.points + " points &middot; " + standing.roundsWon + " " + plural(standing.roundsWon, "round") +
      " won &middot; " + standing.podiums + " top-3 finishes" +
      (standing.dailyDouble
        ? "<br>includes +" + standing.dailyDouble.bonus + " Daily Double (" + esc(standing.dailyDouble.trackTitle) +
          ", " + esc(standing.dailyDouble.roundName) + ")"
        : "")));

    if (songs.length) {
      var best = songs.reduce(function (a, b) { return b.points > a.points ? b : a; });
      g.appendChild(tile("Best submission", extLink(trackLink(best), best.title),
        esc(best.artistText) + "<br>" + best.points + " points &middot; " + esc(best.roundName)));
    }
    if (songs.length >= 2) {
      var worst = songs.reduce(function (a, b) { return b.points < a.points ? b : a; });
      g.appendChild(tile("Weakest submission", extLink(trackLink(worst), worst.title),
        esc(worst.artistText) + "<br>" + worst.points + " points &middot; " + esc(worst.roundName)));
    }
    var contested = songs.filter(function (s) { return s.backers >= 3; });
    if (contested.length) {
      var divisive = contested.reduce(function (a, b) { return b.spread > a.spread ? b : a; });
      if (divisive.spread > 0) {
        g.appendChild(tile("Most divisive submission", extLink(trackLink(divisive), divisive.title),
          "&sigma; " + divisive.spread + " among voters who backed it &middot; " + esc(divisive.roundName)));
      }
    }

    var fansOf = tasteTo(d, id).slice().sort(byPerRound);
    if (fansOf.length) {
      g.appendChild(tile("Biggest fan", who(fansOf[0].voterName, fansOf[0].voterId),
        "gives " + esc(name) + "&rsquo;s songs " + aRound(fansOf[0].perRound) + evenSplit(d)));
      if (fansOf.length >= 2) {
        var cold = fansOf[fansOf.length - 1];
        g.appendChild(tile("Hardest to win over", who(cold.voterName, cold.voterId),
          "only " + aRound(cold.perRound) + evenSplit(d)));
      }
    }
    var favorsOf = tasteFrom(d, id).slice().sort(byPerRound);
    if (favorsOf.length) {
      g.appendChild(tile("Favorite to vote for", who(favorsOf[0].submitterName, favorsOf[0].submitterId),
        esc(name) + " gives their songs " + aRound(favorsOf[0].perRound) + evenSplit(d)));
    }

    var voter = null;
    for (var j = 0; j < d.voters.length; j++) if (d.voters[j].id === id) { voter = d.voters[j]; break; }
    if (voter) {
      g.appendChild(tile("Voting style", voter.avgTopBet.toFixed(1) + " pt top bet",
        "backs " + voter.avgTracksBacked.toFixed(1) + " tracks a round &middot; top pick wins " +
        Math.round(voter.kingmakerRate * 100) + "% of the time"));
    }

    host.appendChild(g);
  }

  function renderFocusGroup(d, ids, host) {
    // comparison rows, ranked by season-wide points
    var rows = ids.map(function (id) {
      var standing = null;
      for (var i = 0; i < d.standings.length; i++) if (d.standings[i].id === id) { standing = d.standings[i]; break; }
      return { id: id, name: nameOf(d, id), standing: standing };
    }).sort(function (a, b) { return (b.standing ? b.standing.points : -1) - (a.standing ? a.standing.points : -1); });

    var max = Math.max.apply(null, rows.map(function (r) { return r.standing ? r.standing.points : 0; }).concat([1]));
    var box = el("div", "framed");
    rows.forEach(function (r) {
      var row = el("div", "stand-row");
      if (!r.standing) {
        row.innerHTML = '<div class="stand-rank">&mdash;</div><div><div class="stand-name">' + who(r.name, r.id) +
          '</div></div><div class="stand-score"><span>no submissions yet</span></div>';
      } else {
        var overallRank = r.standing.tied ? "T" + r.standing.rank : "#" + r.standing.rank;
        var pct = Math.max(3, Math.round((r.standing.points / max) * 100));
        row.innerHTML =
          '<div class="stand-rank">' + overallRank + "</div>" +
          '<div><div class="stand-name">' + who(r.name, r.id) + "</div>" +
          '<div class="bar"><i style="width:' + pct + '%"></i></div>' + dailyDoubleLine(r.standing) + "</div>" +
          '<div class="stand-score"><b>' + r.standing.points + "</b><span>" +
          r.standing.avgPerSubmission + " avg &middot; " + r.standing.roundsWon + " won &middot; " +
          r.standing.podiums + " top-3</span></div>";
      }
      box.appendChild(row);
    });
    host.appendChild(box);

    // head-to-head: among rounds where 2+ of the selected submitted, who placed best
    var idSet = {};
    ids.forEach(function (id) { idSet[id] = true; });
    var tally = {};
    ids.forEach(function (id) { tally[id] = 0; });
    var ties = 0, consideredRounds = 0;
    d.rounds.forEach(function (r) {
      var subset = r.songs.filter(function (s) { return idSet[s.submitterId]; });
      if (subset.length < 2) return;
      consideredRounds++;
      var bestPlace = Math.min.apply(null, subset.map(function (s) { return s.place; }));
      var winners = subset.filter(function (s) { return s.place === bestPlace; });
      if (winners.length === 1) tally[winners[0].submitterId]++;
      else ties++;
    });

    if (consideredRounds) {
      var title = el("h3", null, "Head-to-head");
      var note = el("p", "block-note",
        "Across " + consideredRounds + " " + plural(consideredRounds, "round") +
        " where at least two of them submitted, whoever placed best takes the point." +
        (ties ? " " + ties + " ended tied between them." : ""));
      host.appendChild(title);
      host.appendChild(note);
      var tbox = el("div", "framed");
      var ordered = ids.slice().sort(function (a, b) { return tally[b] - tally[a]; });
      var maxT = Math.max.apply(null, ordered.map(function (id) { return tally[id]; }).concat([1]));
      ordered.forEach(function (id) {
        var pct = Math.max(3, Math.round((tally[id] / maxT) * 100));
        var row = el("div", "stand-row");
        row.innerHTML =
          '<div class="stand-rank">' + tally[id] + "</div>" +
          '<div><div class="stand-name">' + esc(nameOf(d, id)) + "</div>" +
          '<div class="bar"><i style="width:' + pct + '%"></i></div></div>' +
          '<div class="stand-score"><span>' + plural(tally[id], "round") + ' won</span></div>';
        tbox.appendChild(row);
      });
      host.appendChild(tbox);
    }

    // mutual taste, only clean to show for exactly two
    if (ids.length === 2) {
      var a = ids[0], b = ids[1];
      var ab = tastePair(d, a, b), ba = tastePair(d, b, a);
      var g = el("div", "hl-grid focus-grid-spaced");
      if (ab) {
        g.appendChild(tile(esc(nameOf(d, a)) + " &rarr; " + esc(nameOf(d, b)), aRound(ab.perRound),
          ab.points + " " + plural(ab.points, "point") + " over " + ab.chances + " rounds" + evenSplit(d)));
      }
      if (ba) {
        g.appendChild(tile(esc(nameOf(d, b)) + " &rarr; " + esc(nameOf(d, a)), aRound(ba.perRound),
          ba.points + " " + plural(ba.points, "point") + " over " + ba.chances + " rounds" + evenSplit(d)));
      }
      if (!ab && !ba) {
        g.appendChild(tile("Mutual taste", "Not enough data", "needs a few more rounds of head-to-head voting history"));
      }
      host.appendChild(g);
    }
  }

  function renderFocus(d) {
    var section = document.getElementById("block-focus");
    if (!section) return;
    if (!selected.length) { section.hidden = true; return; }
    section.hidden = false;

    var titleEl = $("focusTitle");
    var noteEl = $("focusNote");
    if (selected.length === 1) {
      titleEl.innerHTML = who(nameOf(d, selected[0]), selected[0]);
      noteEl.textContent = "Stats scoped to just this player.";
    } else {
      titleEl.textContent = "Comparing " + selected.length + " players";
      noteEl.textContent = "Everything below compares only these players against each other.";
    }

    var host = $("focus");
    host.innerHTML = "";

    var chips = el("div", "focus-chips");
    selected.forEach(function (id) {
      var chip = el("button", "pill focus-chip");
      chip.type = "button";
      chip.innerHTML = esc(nameOf(d, id)) + " &times;";
      chip.addEventListener("click", function () { toggleSelected(id); });
      chips.appendChild(chip);
    });
    if (selected.length > 1) {
      var clearBtn = el("button", "focus-clear-all");
      clearBtn.type = "button";
      clearBtn.textContent = "Clear all";
      clearBtn.addEventListener("click", clearSelected);
      chips.appendChild(clearBtn);
    }
    host.appendChild(chips);

    if (selected.length === 1) renderFocusIndividual(d, selected[0], host);
    else renderFocusGroup(d, selected, host);
  }

  /* ---- highlights (season-wide, unfiltered) ---- */

  // Superlatives can be shared. build.py names the first of a tie (in a
  // stable order) and lists the rest in "tiedWith"; this is the line that
  // says so. Long ties are cut to three names, with the rest on hover.
  function tieLine(ties) {
    if (!ties || !ties.length) return "";
    var shown = ties.slice(0, 3).map(function (n) { return who(n); });
    var more = ties.length - shown.length;
    var list = more > 0
      ? shown.join(", ") + " and " + more + " more"
      : (shown.length > 1 ? shown.slice(0, -1).join(", ") + " and " + shown[shown.length - 1] : shown[0]);
    return '<div class="hl-tie"' + (more > 0 ? ' title="' + ties.map(esc).join(", ") + '"' : "") +
      ">Tied with " + list + "</div>";
  }

  function joinNames(names) {
    names = (names || []).map(esc);
    if (names.length < 2) return names[0] || "";
    return names.slice(0, -1).join(", ") + " &amp; " + names[names.length - 1];
  }

  // Tastemaker, on a season page and All-Time alike: whose biggest vote of
  // a round most often went to the round's winner (build.py's
  // bestTastemaker, from each voter's kingmakerHits / kingmakerRounds).
  function tastemakerTile(t) {
    return tile("Tastemaker", who(t.name), "their biggest vote went to the winner in " + t.kingmakerHits + " of " +
      t.kingmakerRounds + " rounds (" + pct(t.kingmakerRate) + ")", false, t.tiedWith);
  }

  // Standings places: equal points share one, shown as "T1".
  function placeLabel(p) { return (p.tied ? "T" : "") + p.rank; }

  function tile(label, valueHtml, metaHtml, big, ties) {
    var n = el("div", "hl");
    n.innerHTML = '<p class="hl-label">' + label + "</p>" +
      '<div class="hl-value' + (big ? " hl-big" : "") + '">' + valueHtml + "</div>" +
      (metaHtml ? '<div class="hl-meta">' + metaHtml + "</div>" : "") + tieLine(ties);
    return n;
  }

  function renderHighlights(d) {
    var section = document.getElementById("block-highlights");
    if (selected.length) { if (section) section.hidden = true; return; }
    if (section) section.hidden = false;
    var h = d.highlights || {};
    if (!d.rounds.length) { setBlock("highlights", empty("Highlights need at least one closed round.")); return; }
    var g = el("div", "hl-grid");

    if (h.topTrack) {
      g.appendChild(tile("Highest-scoring track", extLink(trackLink(h.topTrack), h.topTrack.title),
        esc(h.topTrack.artistText) + "<br>" + who(h.topTrack.submitterName) + " &middot; " + h.topTrack.points +
        " points &middot; " + esc(h.topTrack.roundName), false, h.topTrack.tiedWith));
    }
    if (h.divisiveTrack) {
      g.appendChild(tile("Most divisive track", extLink(trackLink(h.divisiveTrack), h.divisiveTrack.title),
        esc(h.divisiveTrack.artistText) + "<br>widest spread between voters who backed it (&sigma; " +
        h.divisiveTrack.spread + "), from " + who(h.divisiveTrack.submitterName), false, h.divisiveTrack.tiedWith));
    }
    if (h.closestRound) {
      g.appendChild(tile("Closest round", esc(h.closestRound.name),
        h.closestRound.margin === 0 ? "ended in a tie at the top" : "won by " + h.closestRound.margin + " " + plural(h.closestRound.margin, "point"), false, h.closestRound.tiedWith));
    }
    if (h.blowoutRound) {
      g.appendChild(tile("Biggest blowout", esc(h.blowoutRound.name),
        who(h.blowoutRound.winner) + " won by " + h.blowoutRound.margin + " points with " + esc(h.blowoutRound.title), false, h.blowoutRound.tiedWith));
    }
    if (h.biggestFan) {
      g.appendChild(tile("Biggest fan", who(h.biggestFan.voterName) + " &rarr; " + who(h.biggestFan.submitterName),
        "gives their songs " + aRound(h.biggestFan.perRound) + evenSplit(d), false, h.biggestFan.tiedWith));
    }
    if (h.coldestShoulder) {
      g.appendChild(tile("Coldest shoulder", who(h.coldestShoulder.voterName) + " &rarr; " + who(h.coldestShoulder.submitterName),
        "gives their songs only " + aRound(h.coldestShoulder.perRound) + evenSplit(d), false, h.coldestShoulder.tiedWith));
    }
    if (h.boldestVoter) {
      g.appendChild(tile("Boldest voter", who(h.boldestVoter.name),
        "biggest single bet averages " + h.boldestVoter.avgTopBet + " points, spread over just " + h.boldestVoter.avgTracksBacked + " tracks a round", false, h.boldestVoter.tiedWith));
    }
    if (h.hedgiestVoter) {
      g.appendChild(tile("Widest spreader", who(h.hedgiestVoter.name),
        "backs " + h.hedgiestVoter.avgTracksBacked + " tracks a round, top bet averages only " + h.hedgiestVoter.avgTopBet, false, h.hedgiestVoter.tiedWith));
    }
    if (h.bestTastemaker) g.appendChild(tastemakerTile(h.bestTastemaker));
    if (typeof h.shutOutCount === "number") {
      g.appendChild(tile("Shut out", String(h.shutOutCount), "tracks finished the season on zero points or worse", true));
    }
    if (h.downvotes) {
      g.appendChild(tile("Downvotes cast", String(h.downvotes), "negative votes were enabled this season", true));
    }
    setBlock("highlights", g);
  }

  /* ---- points-over-time trend chart ---- */

  var trendSelected = [];
  var trendMode = "standing"; // "standing" (default), "ratio", or "points"
  var trendGroupsOn = [];     // keys of the group toggles that are on

  // The group toggles above the player chips. build.py works out who's in
  // each (trend_groups, from the places the standing view draws), so they
  // stay the same whichever view is showing. [key, label, what it means,
  // how a player's figure reads]
  var TREND_GROUPS = [
    ["you", "You", "Just you", null],
    ["front", "Front of the pack", "The top 3 places on the leaderboard now, ties included",
      function (v) { return "#" + v; }],
    ["back", "Back of the pack", "The bottom 3 places on the leaderboard now, ties included",
      function (v) { return "#" + v; }],
    ["rises", "Biggest rises", "Most places climbed since round 1",
      function (v) { return "up " + v + " " + plural(v, "place"); }],
    ["falls", "Biggest falls", "Most places dropped since round 1",
      function (v) { return "down " + v + " " + plural(v, "place"); }],
    ["volatile", "Most volatile", "Most places moved a round, on average",
      function (v) { return v + " " + plural(v, "place") + " a round"; }],
    ["steady", "Steadiest", "Fewest places moved a round, on average",
      function (v) { return v + " " + plural(v, "place") + " a round"; }],
    ["leaders", "Been #1", "Everyone who has led the season after a round",
      function (v) { return v + " " + plural(v, "round") + " at #1"; }]
  ];

  function trendGroupList(d) {
    var found = {};
    (d.trendGroups || []).forEach(function (g) { found[g.key] = g.players; });
    var me = PFML.member.competitorId;
    if (d.standings.some(function (p) { return p.id === me; })) found.you = [{ id: me }];
    return TREND_GROUPS.filter(function (g) { return found[g[0]]; }).map(function (g) {
      return { key: g[0], label: g[1], help: g[2], figure: g[3], players: found[g[0]] };
    });
  }

  function toggleTrendGroup(key, groups) {
    var i = trendGroupsOn.indexOf(key);
    if (i === -1) trendGroupsOn.push(key); else trendGroupsOn.splice(i, 1);
    // Everyone in any group that's on; with none on, back to everyone.
    var ids = [];
    groups.forEach(function (g) {
      if (trendGroupsOn.indexOf(g.key) === -1) return;
      g.players.forEach(function (p) { if (ids.indexOf(p.id) === -1) ids.push(p.id); });
    });
    trendSelected = trendGroupsOn.length ? ids : seasonData.standings.map(function (p) { return p.id; });
    renderTrend(seasonData);
  }

  function trendColor(i) {
    var hue = (i * 137.508) % 360;
    return "hsl(" + hue.toFixed(1) + ", 68%, 42%)";
  }

  function computeTrendSeries(d, mode) {
    // one entry per player who has a standings entry (submitted at least
    // once), ordered by final season points so color/legend order is
    // stable regardless of what's currently toggled on.
    //
    // mode "points": raw cumulative points. Nearly everyone trends up
    // together, since points only accumulate, so this is bad at showing
    // who's actually winning at a given moment.
    //
    // mode "ratio": cumulative points captured as a percentage of the
    // cumulative winning score, i.e. what a player would have if they won
    // every round so far. Rounds already come sorted with songs[0] as that
    // round's winner. A player who wins every round sits at 100%; someone
    // coasting sits low; someone who started strong and faded shows a
    // rising-then-falling line, which raw cumulative totals can't show
    // because they never go down.
    //
    // mode "standing": leaderboard position after each round's points are
    // added in, by cumulative points (competition ranking: a tie shares
    // the same place and the next distinct total skips accordingly, e.g.
    // 1, 1, 3, rather than manufacturing a tiebreak). Rank 1 is best, so
    // the chart draws it inverted, low at the top.
    var ids = d.standings.map(function (p) { return p.id; });
    var cum = {};
    ids.forEach(function (id) { cum[id] = 0; });
    var cumWinScore = 0;
    var series = {};
    ids.forEach(function (id) { series[id] = []; });

    d.rounds.forEach(function (r) {
      var earned = {};
      r.songs.forEach(function (s) {
        var bonus = s.dailyDouble ? s.dailyDouble.bonus : 0;   // counts toward totals, not the round's own score
        earned[s.submitterId] = (earned[s.submitterId] || 0) + s.points + bonus;
      });
      var winScore = r.songs.length ? r.songs[0].points : 0;
      cumWinScore += winScore;
      ids.forEach(function (id) { cum[id] += earned[id] || 0; });

      if (mode === "standing") {
        var order = ids.slice().sort(function (a, b) { return cum[b] - cum[a]; });
        var rankOf = {};
        order.forEach(function (id, i) {
          rankOf[id] = (i > 0 && cum[order[i - 1]] === cum[id]) ? rankOf[order[i - 1]] : i + 1;
        });
        ids.forEach(function (id) { series[id].push(rankOf[id]); });
      } else {
        ids.forEach(function (id) {
          series[id].push(mode === "ratio" ? (cumWinScore > 0 ? (cum[id] / cumWinScore) * 100 : 0) : cum[id]);
        });
      }
    });

    return ids.map(function (id, i) {
      return { id: id, name: nameOf(d, id), color: trendColor(i), values: series[id] };
    });
  }

  function toggleTrend(id) {
    var i = trendSelected.indexOf(id);
    if (i === -1) trendSelected.push(id); else trendSelected.splice(i, 1);
    trendGroupsOn = [];   // a hand-picked set is no longer any group's
    renderTrend(seasonData);
  }

  function trendValueLabel(mode, v) {
    if (mode === "ratio") return v.toFixed(1) + "%";
    if (mode === "standing") return "#" + v;
    return v + " pts";
  }

  function buildLineChartSVG(series, roundNames, mode, fieldSize) {
    var W = 760, H = 320, padL = 44, padR = 16, padT = 16, padB = 30;
    var plotW = W - padL - padR, plotH = H - padT - padB;
    var percent = mode === "ratio";
    var standing = mode === "standing";
    var roundCount = roundNames.length;

    var lo, hi;
    if (standing) {
      // The axis is the whole field's rank range, 1..fieldSize, not just
      // whichever players are toggled on: a filtered view of the middle
      // of the pack shouldn't stretch to fill 1..k and look like the top.
      lo = 1; hi = Math.max(fieldSize || 1, 1);
    } else {
      var allVals = [0];
      series.forEach(function (s) { s.values.forEach(function (v) { allVals.push(v); }); });
      lo = Math.min.apply(null, allVals); hi = Math.max.apply(null, allVals);
      if (percent) hi = Math.max(hi, 100); // keep 100% on the axis even if nobody's hit it yet
    }
    if (lo === hi) { hi = lo + 1; }
    if (!standing) {
      var pad = (hi - lo) * 0.08;
      lo -= pad; hi += pad;
    }

    function x(i) { return padL + (roundCount <= 1 ? 0 : (i / (roundCount - 1)) * plotW); }
    // Rank 1 is best, so standing draws inverted: low value at the top.
    function y(v) {
      var t = (v - lo) / (hi - lo);
      return standing ? (padT + t * plotH) : (padT + plotH - t * plotH);
    }

    var svg = '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="' +
      (percent ? "Performance versus field by round" : standing ? "Leaderboard standing by round" : "Cumulative points by round") + '">';

    // gridlines + y labels
    if (standing) {
      var rankStep = Math.max(1, Math.round(hi / 6));
      for (var rr = 1; rr <= hi; rr += rankStep) {
        var yy2 = y(rr);
        svg += '<line x1="' + padL + '" x2="' + (W - padR) + '" y1="' + yy2.toFixed(1) + '" y2="' + yy2.toFixed(1) + '" class="chart-grid" />';
        svg += '<text x="' + (padL - 8) + '" y="' + (yy2 + 4).toFixed(1) + '" class="chart-axis-y" text-anchor="end">#' + rr + "</text>";
      }
      if ((hi - 1) % rankStep !== 0) {
        var yLast = y(hi);
        svg += '<line x1="' + padL + '" x2="' + (W - padR) + '" y1="' + yLast.toFixed(1) + '" y2="' + yLast.toFixed(1) + '" class="chart-grid" />';
        svg += '<text x="' + (padL - 8) + '" y="' + (yLast + 4).toFixed(1) + '" class="chart-axis-y" text-anchor="end">#' + hi + "</text>";
      }
    } else {
      var ticks = 4;
      for (var t = 0; t <= ticks; t++) {
        var val = lo + (hi - lo) * (t / ticks);
        var yy = y(val);
        svg += '<line x1="' + padL + '" x2="' + (W - padR) + '" y1="' + yy.toFixed(1) + '" y2="' + yy.toFixed(1) + '" class="chart-grid" />';
        var label = percent ? Math.round(val) + "%" : Math.round(val);
        svg += '<text x="' + (padL - 8) + '" y="' + (yy + 4).toFixed(1) + '" class="chart-axis-y" text-anchor="end">' + label + "</text>";
      }
    }

    // x labels
    var xStep = roundCount > 14 ? 2 : 1;
    for (var i = 0; i < roundCount; i += xStep) {
      svg += '<text x="' + x(i).toFixed(1) + '" y="' + (H - 8) + '" class="chart-axis-x" text-anchor="middle">' + (i + 1) + "</text>";
    }

    series.forEach(function (s) {
      var idAttr = esc(String(s.id));
      var pts = s.values.map(function (v, i) { return x(i).toFixed(1) + "," + y(v).toFixed(1); }).join(" ");
      var lastI = s.values.length - 1;
      var lastLabel = trendValueLabel(mode, s.values[lastI]);

      svg += '<g class="trend-series">';
      // Wide, invisible stroke so the line is easy to hover and click
      // anywhere along its length, not just exactly on the 2.5px path.
      svg += '<polyline points="' + pts + '" fill="none" stroke="transparent" stroke-width="14" ' +
        'stroke-linejoin="round" stroke-linecap="round" class="trend-line-hit" data-trend-id="' + idAttr +
        '"><title>' + esc(s.name) + ": " + lastLabel + "</title></polyline>";
      svg += '<polyline points="' + pts + '" fill="none" stroke="' + s.color + '" stroke-width="2.5" ' +
        'stroke-linejoin="round" stroke-linecap="round" class="trend-line-visible" style="pointer-events:none" />';
      // One hit point per round, so hovering near a point (rather than
      // between two of them) names that specific round and its value.
      s.values.forEach(function (v, i) {
        var roundLabel = roundNames[i] || ("Round " + (i + 1));
        svg += '<circle cx="' + x(i).toFixed(1) + '" cy="' + y(v).toFixed(1) + '" r="7" fill="transparent" ' +
          'class="trend-point-hit" data-trend-id="' + idAttr + '"><title>' + esc(s.name) + " — " +
          esc(roundLabel) + ": " + trendValueLabel(mode, v) + "</title></circle>";
      });
      svg += '<circle cx="' + x(lastI).toFixed(1) + '" cy="' + y(s.values[lastI]).toFixed(1) + '" r="3.5" fill="' + s.color + '" style="pointer-events:none" />';
      svg += "</g>";
    });

    svg += "</svg>";
    return svg;
  }

  function setTrendMode(mode) {
    if (trendMode === mode) return;
    trendMode = mode;
    renderTrend(seasonData);
  }

  function renderTrend(d) {
    var section = document.getElementById("block-trend");
    // A trend needs at least two points. With a single round every line is
    // one dot, so the chart is a column of dots on its left edge over a big
    // empty plot: correct, but it reads as broken. Hidden until round two,
    // and its jump-nav link drops out with it.
    if (d.rounds.length < 2 || !d.standings.length) { if (section) section.hidden = true; return; }
    if (section) section.hidden = false;

    var all = computeTrendSeries(d, trendMode);

    var legend = $("trendLegend");
    legend.innerHTML = "";

    var modeRow = el("div", "chart-mode");
    [["standing", "Standing over time"], ["ratio", "Performance vs field"], ["points", "Cumulative points"]].forEach(function (pair) {
      var b = el("button", trendMode === pair[0] ? "is-active" : "", esc(pair[1]));
      b.type = "button";
      b.setAttribute("aria-pressed", String(trendMode === pair[0]));
      b.addEventListener("click", function () { setTrendMode(pair[0]); });
      modeRow.appendChild(b);
    });
    legend.appendChild(modeRow);

    if (trendMode === "ratio") {
      legend.appendChild(el("p", "block-note chart-mode-note",
        "Cumulative points captured so far, as a percentage of what a player would have if they'd won every round to date. 100% means never off the pace; a falling line means someone who started strong is losing ground."));
    } else if (trendMode === "standing") {
      legend.appendChild(el("p", "block-note chart-mode-note",
        "Each player's place on the leaderboard once that round's points are added in. #1 is the season leader at that point; a tie shares a place. The axis runs #1 at the top, so a rising line is climbing the standings and a falling line is slipping."));
    }

    var groups = trendGroupList(d);
    if (groups.length) {
      var groupRow = el("div", "trend-groups");
      groupRow.setAttribute("role", "group");
      groupRow.setAttribute("aria-label", "Show a group");
      groups.forEach(function (g) {
        var on = trendGroupsOn.indexOf(g.key) !== -1;
        var b = el("button", "trend-group" + (on ? " is-on" : ""), esc(g.label));
        b.type = "button";
        b.title = g.help;
        b.setAttribute("aria-pressed", String(on));
        b.addEventListener("click", function () { toggleTrendGroup(g.key, groups); });
        groupRow.appendChild(b);
      });
      legend.appendChild(groupRow);
      // Who each group that's on holds, and why, since the chips below
      // only show who's on.
      var lines = groups.filter(function (g) { return g.figure && trendGroupsOn.indexOf(g.key) !== -1; });
      if (lines.length) {
        var why = el("div", "block-note trend-group-why");
        lines.forEach(function (g) {
          why.appendChild(el("p", "", "<strong>" + esc(g.label) + ":</strong> " + g.players.map(function (p) {
            return esc(nameOf(d, p.id)) + " (" + esc(g.figure(p.value)) + ")";
          }).join(", ")));
        });
        legend.appendChild(why);
      }
    }

    var chipRow = el("div", "trend-chips");
    all.forEach(function (s) {
      var on = trendSelected.indexOf(s.id) !== -1;
      var b = el("button", "trend-chip" + (on ? " is-on" : ""));
      b.type = "button";
      b.setAttribute("aria-pressed", String(on));
      b.innerHTML = '<span class="dot" style="background:' + s.color + '"></span>' + esc(s.name);
      b.addEventListener("click", function () { toggleTrend(s.id); });
      chipRow.appendChild(b);
    });
    legend.appendChild(chipRow);

    var controls = el("div", "trend-controls");
    var allBtn = el("button", "trend-control", "Select all");
    allBtn.type = "button";
    allBtn.addEventListener("click", function () {
      trendSelected = all.map(function (s) { return s.id; });
      trendGroupsOn = [];
      renderTrend(seasonData);
    });
    var clearBtn = el("button", "trend-control", "Clear");
    clearBtn.type = "button";
    clearBtn.addEventListener("click", function () { trendSelected = []; trendGroupsOn = []; renderTrend(seasonData); });
    controls.appendChild(allBtn);
    controls.appendChild(clearBtn);
    legend.appendChild(controls);

    var chartHost = $("trendChart");
    var shown = all.filter(function (s) { return trendSelected.indexOf(s.id) !== -1; });
    if (!shown.length) {
      chartHost.innerHTML = "";
      chartHost.appendChild(empty("Pick at least one player above to plot."));
      return;
    }
    var roundNames = d.rounds.map(function (r) { return r.name; });
    chartHost.innerHTML = '<div class="chart-frame">' + buildLineChartSVG(shown, roundNames, trendMode, all.length) + "</div>";
    // The chart is built as a markup string, so wire up click-to-filter
    // after the fact: same toggleTrend() the legend chips use, just
    // triggered from the line (its wide invisible hit-stroke) or one of
    // its per-round points instead of the chip.
    Array.prototype.forEach.call(chartHost.querySelectorAll("[data-trend-id]"), function (node) {
      node.addEventListener("click", function () { toggleTrend(node.getAttribute("data-trend-id")); });
    });
  }

  /* ---- tracks / rounds (filterable) ---- */

  function trackRow(s, pos, showRound, highlightSet) {
    var hl = highlightSet && highlightSet[s.submitterId];
    var row = el("div", "trk" + (hl ? " trk-hl" : ""));
    var meta = artistLinks(s.artists, s.artistText);
    if (s.album) meta += " &middot; " + extLink(searchLink(s.album), s.album);
    meta += " &middot; " + who(s.submitterName, s.submitterId);
    if (showRound) meta += " &middot; " + esc(s.roundName);
    row.innerHTML =
      '<div class="trk-pos">' + pos + "</div>" +
      '<div class="trk-body"><div class="trk-title">' + extLink(trackLink(s), s.title) +
      (s.dailyDouble ? ' <span class="dd-badge" title="Counts twice toward ' + esc(s.submitterName) +
        '&#39;s season total: +' + s.dailyDouble.bonus + ' pts">Daily Double</span>' : "") + "</div>" +
      '<div class="trk-meta">' + meta + "</div></div>" +
      '<div class="trk-pts">' + s.points + " <small>pts</small></div>";
    return row;
  }

  function renderTopTracks(d) {
    var all = [];
    d.rounds.forEach(function (r) { all = all.concat(r.songs); });
    if (selected.length) {
      var idSet = {};
      selected.forEach(function (id) { idSet[id] = true; });
      all = all.filter(function (s) { return idSet[s.submitterId]; });
    }
    var host = $("topTracks");
    host.innerHTML = "";
    attachFilterTag(host, d);
    if (!all.length) { host.appendChild(empty(selected.length ? "No tracks from this selection." : "No tracks submitted yet.")); return; }
    var top = all.slice().sort(function (a, b) { return b.points - a.points; }).slice(0, 20);
    var box = el("div", "framed");
    top.forEach(function (s, i) { box.appendChild(trackRow(s, i + 1, true)); });
    host.appendChild(box);
  }

  function renderRounds(d) {
    // The collapsible Results by round under the leaderboard: one card per
    // round, each linking to that round's own page (rounds.js).
    window.PFMLRounds.renderList($("rounds"), d, {
      selected: selected.slice(),
      filterTag: function (h) { attachFilterTag(h, d); }
    });
  }

  /* ---- taste matrix (filterable) ---- */

  // Taste in the league's own units: the points a voter gives someone's
  // songs a round, against an even split of about 1 (tasteEvenSplit).
  function aRound(n) { return n.toFixed(1) + " points a round"; }
  function evenSplit(d) {
    return d.tasteEvenSplit == null ? "" : " (an even split is " + d.tasteEvenSplit.toFixed(1) + ")";
  }
  function byPerRound(a, b) { return b.perRound - a.perRound || b.points - a.points; }

  // A taste list: rows of { label, cells }, under a header row. `firstCol`
  // heads the names (whose songs, or who's voting); `cols` the numbers,
  // TASTE_COLS unless given. On a phone the fourth column is dropped.
  var TASTE_COLS = ["Points a round", "Points", "Rounds"];
  function tasteCells(t) { return [t.perRound.toFixed(1), t.points, t.chances]; }

  function renderTasteRowList(title, rows, host, firstCol, cols, cls) {
    var block = el("div", cls || null);
    block.appendChild(el("h3", null, title));
    if (!rows.length) { block.appendChild(empty("Not enough voting history yet.")); host.appendChild(block); return; }
    var box = el("div", "framed");
    box.insertAdjacentHTML("beforeend", '<div class="vrow head"><div>' + esc(firstCol) + "</div>" +
      (cols || TASTE_COLS).map(function (c) { return '<div class="num">' + esc(c) + "</div>"; }).join("") + "</div>");
    rows.forEach(function (r) {
      box.insertAdjacentHTML("beforeend", '<div class="vrow"><div class="vname">' + esc(r.label) + "</div>" +
        r.cells.map(function (c) { return '<div class="num">' + esc(c) + "</div>"; }).join("") + "</div>");
    });
    block.appendChild(box);
    host.appendChild(block);
  }

  // One player's two ranked lists: how they rate everyone else, and how
  // everyone else rates them. "You" for the signed-in member.
  function renderTasteLists(d, id, host) {
    var you = id === PFML.member.competitorId, name = esc(nameOf(d, id));
    var out = tasteFrom(d, id).slice().sort(byPerRound)
      .map(function (t) { return { label: t.submitterName, cells: tasteCells(t) }; });
    var into = tasteTo(d, id).slice().sort(byPerRound)
      .map(function (t) { return { label: t.voterName, cells: tasteCells(t) }; });
    renderTasteRowList(you ? "How you rate everyone else" : "How " + name + " rates everyone else", out, host, "Player");
    renderTasteRowList(you ? "How everyone else rates you" : "How everyone else rates " + name, into, host, "Voter");
  }

  // The league's five strongest, five coldest and five most lopsided
  // pairings: the grid's extremes as short lists, so a phone gets the big
  // picture without the grid. Ties: the strongest on more points, the
  // coldest on more chances (a zero over more rounds says more), then by
  // name.
  function renderTastePairs(d, host) {
    var label = function (t) { return t.voterName + " \u2192 " + t.submitterName; };
    var strongest = d.taste.slice().sort(function (a, b) { return b.perRound - a.perRound || b.points - a.points || label(a).localeCompare(label(b)); });
    var coldest = d.taste.slice().sort(function (a, b) { return a.perRound - b.perRound || b.chances - a.chances || label(a).localeCompare(label(b)); });
    var row = function (t) { return { label: label(t), cells: tasteCells(t) }; };
    var wrap = el("div", "taste-pairs");
    renderTasteRowList("Strongest pairings", strongest.slice(0, 5).map(row), wrap, "Voter \u2192 player");
    renderTasteRowList("Coldest pairings", coldest.slice(0, 5).map(row), wrap, "Voter \u2192 player");
    renderTasteRowList("Most lopsided pairings", lopsidedPairs(d).slice(0, 5).map(function (x) {
      return { label: label(x.gives), cells: [x.gives.perRound.toFixed(1), x.back.perRound.toFixed(1), x.gap.toFixed(1)] };
    }), wrap, "Gives \u2192 gets back", ["Gives a round", "Gets back", "Gap"], "taste-lopsided");
    host.appendChild(wrap);
  }

  // Who gives someone's songs far more a round than that person gives
  // back. Each pair once, from the side that gives more, and only where
  // both directions have had enough rounds to show; a pair that gives each
  // other the same isn't lopsided at all. The gap is worked out from the
  // two figures as shown (one decimal, as every taste list shows them), so
  // the row always adds up: unrounded, 1.15 and 0.35 showed as 1.1 and 0.4
  // with a gap of 0.8. Biggest gap first, then the one giving more.
  function lopsidedPairs(d) {
    var shown = function (n) { return +n.toFixed(1); };
    var byKey = {};
    d.taste.forEach(function (t) { byKey[t.voterId + "|" + t.submitterId] = t; });
    var out = [];
    d.taste.forEach(function (t) {
      var back = byKey[t.submitterId + "|" + t.voterId];
      if (!back) return;
      var gives = shown(t.perRound), gets = shown(back.perRound);
      if (gives > gets) out.push({ gives: t, back: back, gap: Math.round((gives - gets) * 10) / 10 });
    });
    return out.sort(function (a, b) {
      return b.gap - a.gap || b.gives.perRound - a.gives.perRound ||
        (a.gives.voterName + a.gives.submitterName).localeCompare(b.gives.voterName + b.gives.submitterName);
    });
  }

  // Phones get one player's lists instead of the grid, which is about six
  // screens wide there (measured: one column visible at a time). It opens
  // on the signed-in member, with a menu for anyone else.
  var tasteFocus = null;
  function renderTastePhone(d, people, host) {
    var ids = people.map(function (p) { return p.id; });
    var me = PFML.member.competitorId;
    if (ids.indexOf(tasteFocus) === -1) {
      var leader = d.standings.filter(function (p) { return ids.indexOf(p.id) !== -1; })[0];
      tasteFocus = ids.indexOf(me) !== -1 ? me : (leader ? leader.id : ids[0]);
    }
    var wrap = el("div", "taste-phone");
    var sorted = people.slice().sort(function (a, b) { return a.name.localeCompare(b.name); });
    wrap.innerHTML = '<label class="cm-sr" for="tastePick">Show another player</label>' +
      '<div class="rp-jump taste-pick"><select id="tastePick" class="rp-jump-select">' + sorted.map(function (p) {
        return '<option value="' + esc(p.id) + '"' + (p.id === tasteFocus ? " selected" : "") + ">" +
          esc(p.name) + (p.id === me ? " (you)" : "") + "</option>";
      }).join("") + "</select></div>";
    wrap.querySelector("select").addEventListener("change", function (ev) {
      tasteFocus = ev.target.value;
      renderTaste(seasonData);
    });
    renderTasteLists(d, tasteFocus, wrap);
    host.appendChild(wrap);
  }

  function renderTasteGrid(d, people, host, phoneToo) {
    var byKey = {};
    d.taste.forEach(function (t) { byKey[t.voterId + "|" + t.submitterId] = t; });
    var vals = d.taste.map(function (t) { return t.perRound; });
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);

    var head = "<thead><tr><th class=\"corner\">Voter &darr; / Submitter &rarr;</th>";
    people.forEach(function (p) { head += "<th>" + who(p.name, p.id) + "</th>"; });
    head += "</tr></thead>";

    var body = "<tbody>";
    people.forEach(function (voter) {
      body += "<tr><th>" + who(voter.name, voter.id) + "</th>";
      people.forEach(function (sub) {
        if (voter.id === sub.id) { body += '<td class="nil">&mdash;</td>'; return; }
        var t = byKey[voter.id + "|" + sub.id];
        if (!t) { body += '<td class="nil">&middot;</td>'; return; }
        var f = hi > lo ? (t.perRound - lo) / (hi - lo) : 0.5;
        var alpha = (0.06 + f * 0.62).toFixed(2);
        var dark = f > 0.62;
        body += '<td style="background:rgba(158,0,196,' + alpha + ')' + (dark ? ";color:#fff" : "") + '" title="' +
          esc(voter.name) + " gave " + esc(sub.name) + "&rsquo;s songs " + t.points + " " + plural(t.points, "point") + " over " + t.chances + ' rounds">' +
          t.perRound.toFixed(1) + "</td>";
      });
      body += "</tr>";
    });
    body += "</tbody>";

    // the grid and its legend, together; on a phone only for a few
    // players picked in Standings, where it's small enough to read
    var wrap = el("div", "taste-grid" + (phoneToo ? "" : " is-wide-only"));
    var table = el("table", "taste");
    table.innerHTML = head + body;
    var scroll = el("div", "taste-scroll");
    scroll.appendChild(table);
    wrap.appendChild(scroll);
    wrap.insertAdjacentHTML("beforeend",
      '<div class="legend"><span>' + lo.toFixed(1) + '</span><span class="ramp"></span><span>' + hi.toFixed(1) +
      "</span><span>points a round: darker means more</span></div>");
    host.appendChild(wrap);
  }

  function renderTaste(d) {
    var note = $("tasteNote");
    var host = $("taste");
    host.innerHTML = "";

    if (!d.taste.length) {
      if (note) note.textContent = "";
      host.appendChild(empty("Needs a few rounds of voting history before this says anything."));
      return;
    }
    if (note) note.textContent =
      "How many points a voter gives someone's songs each round, on average. Everyone spends the same " + d.pointBudget +
      " points a round, so an even split is about " + d.tasteEvenSplit.toFixed(1) + ": above that, they're a fan; below it, not so much. " +
      "A pair shows once they've had " + d.tasteMinChances + " rounds together.";

    attachFilterTag(host, d);

    if (selected.length === 1) { renderTasteLists(d, selected[0], host); return; }

    // Only players with at least one pair to show. Anyone else, who hasn't
    // played or hasn't played enough rounds yet, would be a blank row and
    // column, so they're named below instead.
    var inTaste = {};
    d.taste.forEach(function (t) { inTaste[t.voterId] = inTaste[t.submitterId] = true; });
    var pool = selected.length ? d.competitors.filter(function (p) { return selected.indexOf(p.id) !== -1; }) : d.competitors;
    var people = pool.filter(function (p) { return inTaste[p.id]; });
    var waiting = pool.filter(function (p) { return !inTaste[p.id]; });

    if (!selected.length) {
      renderTastePhone(d, people, host);
      renderTastePairs(d, host);
    }
    if (people.length) renderTasteGrid(d, people, host, selected.length > 0);
    if (waiting.length) {
      host.appendChild(el("p", "block-note taste-waiting",
        "Not shown until they've played enough rounds: " + waiting.map(function (p) { return esc(p.name); }).join(", ") + "."));
    }
  }

  /* ---- voters / artists (filterable) ---- */

  function renderVoters(d) {
    var host = $("voters");
    host.innerHTML = "";
    // The budget isn't the same number every season (16 in Seasons 1 and 2,
    // 19 in Season 3), so the copy takes it from the data instead of
    // hard-coding one. Without it the template's neutral wording stands.
    var note = $("votersNote");
    if (note && d.pointBudget) {
      note.textContent = "Everyone spends the same " + d.pointBudget +
        " points a round, so what separates voters is where they put them: a few big bets, or a point on everything.";
    }
    attachFilterTag(host, d);
    var rows = selected.length ? d.voters.filter(function (v) { return selected.indexOf(v.id) !== -1; }) : d.voters;
    if (!rows.length) { host.appendChild(empty(selected.length ? "No votes from this selection." : "No votes cast yet.")); return; }
    var box = el("div", "framed table-wide voters-box");
    box.insertAdjacentHTML("beforeend",
      '<div class="vrow head"><div>Player</div><div class="num">Top bet</div><div class="num">Tracks backed</div><div class="num">Top pick won</div></div>');
    rows.forEach(function (v) {
      box.insertAdjacentHTML("beforeend",
        '<div class="vrow"><div class="vname">' + who(v.name, v.id) + "</div>" +
        '<div class="num">' + v.avgTopBet.toFixed(1) + "</div>" +
        '<div class="num">' + v.avgTracksBacked.toFixed(1) + "</div>" +
        '<div class="num">' + Math.round(v.kingmakerRate * 100) + "%</div></div>");
    });
    host.appendChild(tableHint());
    host.appendChild(box);
  }

  /* ---- comments (filterable) ----
     Counts and superlatives, not a transcript. The one place raw comment
     text appears is the longest comment, where the text is the point.
     Everything here is a voter comment (votes.csv); a submitter's note on
     their own track is a different thing and gets its own line. */

  function pct(rate) { return Math.round(rate * 100) + "%"; }

  // Each player's distinctive word (build.py's distinctive_word), for a
  // season's comments or All-Time's. Nothing when nobody has one yet.
  function renderDistinctiveWords(rows, host) {
    var words = rows.filter(function (c) { return c.distinctiveWord; });
    if (!words.length) return;
    var wbox = el("div", "framed cmt-words");
    wbox.appendChild(el("h3", null, "Words they reach for more than anyone else"));
    var list = el("div", "cmt-word-row");
    words.forEach(function (c) {
      list.insertAdjacentHTML("beforeend",
        '<span class="cmt-word" title="' + esc(c.name) + " used it " + c.distinctiveWord.uses +
        " times, " + c.distinctiveWord.vsLeague + '&times; the league\'s rate">' +
        who(c.name, c.id) + ' <b>&ldquo;' + esc(c.distinctiveWord.word) + '&rdquo;</b> &times;' +
        c.distinctiveWord.uses + '</span>');
    });
    wbox.appendChild(list);
    host.appendChild(wbox);
  }

  function commentQuote(c, label, stats) {
    var meta = [];
    if (c.trackTitle) meta.push(extLink(trackLink(c), c.trackTitle));
    if (c.roundName) meta.push(esc(c.roundName));
    if (c.seasonLabel) meta.push(esc(c.seasonLabel));
    (stats || [c.words + " words"]).forEach(function (s) { meta.push(esc(s)); });
    var box = el("div", "cmt-quote");
    box.innerHTML =
      '<p class="cmt-label">' + esc(label) + "</p>" +
      // the translation sits inside the quote, so a long one clips with it
      "<blockquote>" + esc(c.text) + PFML.translationHtml(c.translation) + "</blockquote>" +
      '<p class="cmt-src">' + (c.name ? "<b>" + who(c.name) + "</b> &middot; " : "") +
      meta.join(" &middot; ") + "</p>";
    return box;
  }

  function renderComments(d) {
    var section = document.getElementById("block-comments");
    var host = $("comments");
    if (!host) return;
    host.innerHTML = "";

    var summary = d.commentSummary || {};
    var all = d.commenters || [];
    // A season with no rounds has no votes and so no comments. Hide the
    // whole section rather than showing a grid of zeroes, same as the
    // trend chart does, and the jump nav drops it automatically.
    if (!all.length || !summary.totalComments) {
      if (section) section.hidden = true;
      return;
    }
    if (section) section.hidden = false;

    attachFilterTag(host, d);

    var rows = selected.length
      ? all.filter(function (c) { return selected.indexOf(c.id) !== -1; })
      : all;
    if (!rows.length) {
      host.appendChild(empty("No comments from this selection."));
      return;
    }

    // Superlatives are season-wide, so they only make sense unfiltered.
    // With a player selected the table below is already about them.
    if (!selected.length) {
      var g = el("div", "hl-grid");
      if (summary.chattiest) {
        g.appendChild(tile("Most likely to say something", who(summary.chattiest.name),
          pct(summary.chattiest.rate) + " of their votes carry a comment", false, summary.chattiest.tiedWith));
      }
      if (summary.quietest) {
        g.appendChild(tile("Least likely", who(summary.quietest.name),
          pct(summary.quietest.rate) + " &middot; " + summary.quietest.comments + " comments", false, summary.quietest.tiedWith));
      }
      if (summary.wordiest) {
        g.appendChild(tile("Wordiest", who(summary.wordiest.name),
          summary.wordiest.meanWords + " words per comment on average", false, summary.wordiest.tiedWith));
      }
      if (summary.tersest) {
        g.appendChild(tile("Tersest", who(summary.tersest.name),
          summary.tersest.meanWords + " words per comment on average", false, summary.tersest.tiedWith));
      }
      if (summary.loudest) {
        g.appendChild(tile("Most SHOUTING", who(summary.loudest.name),
          pct(summary.loudest.rate) + " of their comments have an all-caps word", false, summary.loudest.tiedWith));
      }
      if (summary.richestVocab) {
        g.appendChild(tile("Widest vocabulary", who(summary.richestVocab.name),
          summary.richestVocab.richness.toFixed(2) + " unique words per word, measured over " +
          summary.richestVocab.sampleWords + "-word samples", false, summary.richestVocab.tiedWith));
      }
      if (summary.mostZeroPoint) {
        g.appendChild(tile("Most all-talk", who(summary.mostZeroPoint.name),
          summary.mostZeroPoint.count + " comments awarding zero points", false, summary.mostZeroPoint.tiedWith));
      }
      if (summary.silentTreatment && summary.silentTreatment.comments === 0) {
        g.appendChild(tile("Silent treatment",
          who(summary.silentTreatment.voterName) + " &rarr; " + who(summary.silentTreatment.submitterName),
          "never commented on them in " + summary.silentTreatment.chances + " chances", false, summary.silentTreatment.tiedWith));
      } else if (summary.mostTalkedAt) {
        g.appendChild(tile("Most talked at",
          who(summary.mostTalkedAt.voterName) + " &rarr; " + who(summary.mostTalkedAt.submitterName),
          pct(summary.mostTalkedAt.rate) + " of their tracks got a comment", false, summary.mostTalkedAt.tiedWith));
      }
      host.appendChild(g);
    }

    host.appendChild(tableHint());
    var box = el("div", "framed table-wide cmt-table-box cmt-table");
    box.insertAdjacentHTML("beforeend",
      '<div class="crow head"><div>Player</div><div class="num">Comments</div>' +
      '<div class="num">Rate</div><div class="num">Avg words</div>' +
      '<div class="num">Median</div><div class="num">Zero-pt</div>' +
      '<div class="num">!</div><div class="num">?</div><div class="num">CAPS</div></div>');
    rows.forEach(function (c) {
      box.insertAdjacentHTML("beforeend",
        '<div class="crow"><div class="vname">' + who(c.name, c.id) + "</div>" +
        '<div class="num">' + c.comments + "</div>" +
        '<div class="num">' + pct(c.commentRate) + "</div>" +
        '<div class="num">' + c.meanWords + "</div>" +
        '<div class="num">' + c.medianWords + "</div>" +
        '<div class="num">' + c.zeroPointComments + "</div>" +
        '<div class="num">' + pct(c.exclamationRate) + "</div>" +
        '<div class="num">' + pct(c.questionRate) + "</div>" +
        '<div class="num">' + pct(c.allCapsRate) + "</div></div>");
    });
    host.appendChild(box);

    renderDistinctiveWords(rows, host);

    // The longest comment, in full, because the length is the point. When
    // a player is selected it's theirs; otherwise it's the season's.
    var longest = null;
    var longestLabel = "Longest comment of the season";
    if (selected.length && rows.length) {
      // whoever in the current selection wrote the longest one
      var withLongest = rows.filter(function (c) { return c.longest; });
      if (withLongest.length) {
        var pick = withLongest.reduce(function (a, b) {
          return b.longest.words > a.longest.words ? b : a;
        });
        longest = Object.keys(pick.longest).reduce(function (o, k) {
          o[k] = pick.longest[k]; return o;
        }, {});
        longest.name = pick.name;
        longestLabel = selected.length === 1
          ? "Their longest comment"
          : "Longest comment in this comparison";
      }
    } else if (summary.longestComment) {
      longest = summary.longestComment;
    }
    if (longest) host.appendChild(commentQuote(longest, longestLabel));

    var notes = d.submitterNotes || [];
    if (selected.length) {
      notes = notes.filter(function (n) { return selected.indexOf(n.id) !== -1; });
    }
    if (notes.length) {
      var nbox = el("div", "framed cmt-notes");
      nbox.appendChild(el("h3", null, "Notes on their own submissions"));
      nbox.insertAdjacentHTML("beforeend",
        '<p class="block-note">A different thing from a vote comment: this is the submitter ' +
        'explaining their own pick, and it is much rarer.</p>' +
        '<div class="nrow head"><div>Player</div><div class="num">Notes</div>' +
        '<div class="num">Of their subs</div></div>');
      notes.slice(0, 12).forEach(function (n) {
        nbox.insertAdjacentHTML("beforeend",
          '<div class="nrow"><div class="vname">' + who(n.name, n.id) + "</div>" +
          '<div class="num">' + n.notes + " of " + n.submissions + "</div>" +
          '<div class="num">' + pct(n.noteRate) + "</div></div>");
      });
      host.appendChild(nbox);
    }

    if (summary.hasSentiment) {
      var withSent = rows.filter(function (c) { return c.sentiment; });
      if (withSent.length) {
        var sbox = el("div", "framed cmt-words");
        sbox.appendChild(el("h3", null, "Tone"));
        sbox.insertAdjacentHTML("beforeend",
          '<p class="block-note">Labels from scripts/enrich_comments.py, over the ' +
          'comments it has actually classified. Unlabelled comments are not counted.</p>');
        var srow = el("div", "cmt-word-row");
        withSent.forEach(function (c) {
          var top = Object.keys(c.sentiment.counts).sort(function (a, b) {
            return c.sentiment.counts[b] - c.sentiment.counts[a];
          }).slice(0, 3);
          srow.insertAdjacentHTML("beforeend",
            '<span class="cmt-word" title="' + c.sentiment.labelled + ' comments labelled">' +
            who(c.name, c.id) + " <b>" + top.map(esc).join(", ") + "</b></span>");
        });
        sbox.appendChild(srow);
        host.appendChild(sbox);
      }
    }

    var foot = [];
    foot.push(summary.totalComments + " comments, " + summary.totalWords.toLocaleString() + " words");
    if (summary.submitterNoteCount) foot.push(summary.submitterNoteCount + " submitter notes");
    if (summary.commentOnlyVotes) foot.push(summary.commentOnlyVotes + " comment-only votes (zero points awarded)");
    host.insertAdjacentHTML("beforeend", '<p class="block-note cmt-foot">' + foot.join(" &middot; ") +
      ". Rates over fewer than " + summary.minCommentsForRates +
      " comments are left out of the superlatives above.</p>");
  }

  function countArtists(songs) {
    var counts = {};
    songs.forEach(function (s) {
      var names = (s.artists && s.artists.length) ? s.artists : (s.artistText ? [s.artistText] : []);
      names.forEach(function (a) {
        if (!a) return;
        if (!counts[a]) counts[a] = { name: a, count: 0, points: 0 };
        counts[a].count++;
        counts[a].points += s.points;
      });
    });
    return Object.keys(counts).map(function (k) { return counts[k]; });
  }

  function renderArtists(d) {
    var host = $("artists");
    host.innerHTML = "";
    attachFilterTag(host, d);

    var list;
    if (selected.length) {
      var songs = [];
      selected.forEach(function (id) { songs = songs.concat(songsBy(d, id)); });
      list = countArtists(songs).filter(function (a) { return a.count > 1; })
        .sort(function (a, b) { return b.count - a.count || b.points - a.points; });
    } else {
      list = (d.highlights && d.highlights.repeatArtists) || [];
    }
    if (!list.length) { host.appendChild(empty("No artist has been submitted more than once" + (selected.length ? " by this selection" : "") + " yet.")); return; }
    var g = el("div", "art-grid");
    list.forEach(function (a) {
      g.insertAdjacentHTML("beforeend",
        '<a class="art" href="' + esc(searchLink(a.name)) + '" target="_blank" rel="noopener">' + esc(a.name) + " <b>&times;" + a.count + "</b></a>");
    });
    host.appendChild(g);
  }

  /* ---- hero (season-wide, unfiltered) ---- */

  // The page leads with Standings: the title, then straight into it. The
  // line under the title (and the stat cards that used to follow it) went
  // at the members' request; the line now only speaks up when there's
  // nothing below it yet, or while loading or failing.
  function renderHero(d) {
    $("heroTitle").textContent = d.label;
    var line = $("heroLine");
    line.hidden = d.rounds.length > 0;
    line.textContent = d.rounds.length ? ""
      : d.competitors.length + " players are signed up. No rounds have been posted yet, so the boards below fill in as results come through.";
  }

  function initSeason(key) {
    Promise.all([PFML.loadJSON("index.json"), PFML.loadJSON(key + ".json")])
      .then(function (res) {
        var index = res[0], d = res[1];
        seasonData = d;
        knowPeople(d.competitors);
        renderNav(index, key);
        document.title = "PFML - " + d.label;
        initStandingsFold();
        renderHero(d);
        // nobody selected yet, so this draws every section for the whole
        // field, with every player on the trend chart
        rerenderFiltered();
        scrollToHash();
      })
      .catch(function (err) {
        console.error(err);
        var t = $("heroTitle");
        if (t) t.textContent = "PFML";
        var l = $("heroLine");
        if (l) { l.hidden = false; l.textContent = "Season data didn't load. Try reloading the page."; }
      });
  }

  /* =====================================================================
     CAREER PAGE
     ===================================================================== */

  var careerData = null;
  var careerSort = { field: "careerScore", dir: "desc" };

  function careerTile(label, valueHtml, metaHtml, ties) { return tile(label, valueHtml, metaHtml, false, ties); }

  function renderCareerComments(c) {
    var section = document.getElementById("block-comments");
    var host = $("comments");
    if (!host) return;
    host.innerHTML = "";
    var s = c.commentSummary || {};
    var rows = c.commenters || [];
    if (!rows.length || !s.totalComments) { if (section) section.hidden = true; return; }
    if (section) section.hidden = false;

    // Two per row on a phone (.hl-pair): 8 awards, four even rows.
    var g = el("div", "hl-grid hl-pair");
    if (s.mostTalkative) {
      g.appendChild(careerTile("Most talkative", who(s.mostTalkative.name),
        pct(s.mostTalkative.rate) + " of their votes carry a comment &middot; " +
        s.mostTalkative.comments + " comments", s.mostTalkative.tiedWith));
    }
    if (s.mostTerse) {
      g.appendChild(careerTile("Most terse", who(s.mostTerse.name),
        s.mostTerse.meanWords + " words per comment across " + s.mostTerse.comments, s.mostTerse.tiedWith));
    }
    if (s.wordiest) {
      g.appendChild(careerTile("Wordiest", who(s.wordiest.name),
        s.wordiest.meanWords + " words per comment", s.wordiest.tiedWith));
    }
    if (s.quietest) {
      g.appendChild(careerTile("Quietest", who(s.quietest.name),
        pct(s.quietest.rate) + " of their votes carry a comment", s.quietest.tiedWith));
    }
    if (s.silentTreatment && s.silentTreatment.comments === 0) {
      g.appendChild(careerTile("Biggest silent treatment",
        who(s.silentTreatment.voterName) + " &rarr; " + who(s.silentTreatment.submitterName),
        "never once commented, across " + s.silentTreatment.chances + " chances to", s.silentTreatment.tiedWith));
    }
    if (s.loudest) {
      g.appendChild(careerTile("Most SHOUTING", who(s.loudest.name),
        pct(s.loudest.rate) + " of their comments have an all-caps word", s.loudest.tiedWith));
    }
    if (s.richestVocab) {
      g.appendChild(careerTile("Widest vocabulary", who(s.richestVocab.name),
        s.richestVocab.richness.toFixed(2) + " unique words per word over " +
        s.richestVocab.sampleWords + "-word samples", s.richestVocab.tiedWith));
    }
    if (s.mostSubmitterNotes) {
      g.appendChild(careerTile("Most notes on their own picks", who(s.mostSubmitterNotes.name),
        s.mostSubmitterNotes.notes + " of " + s.mostSubmitterNotes.submissions + " submissions", s.mostSubmitterNotes.tiedWith));
    }
    // Titles from comment_sentiment.json (labels by Claude, via
    // scripts/enrich_comments.py): only there once that's been run. Four,
    // so the grid stays in even rows.
    var titles = (s.sentimentAwards && s.sentimentAwards.titles) || {};
    [["classClown", "Class clown", "funny or witty"], ["sweetheart", "Sweetheart", "heartfelt or appreciative"],
     ["grump", "Resident grump", "angry or mean"], ["hotTakeArtist", "Hot-take artist", "a hot take"]].forEach(function (x) {
      var t = titles[x[0]];
      if (t) g.appendChild(careerTile(x[1], who(t.name), pct(t.rate) + " of their comments " + x[2], t.tiedWith));
    });
    host.appendChild(g);

    host.appendChild(tableHint(true));
    var tableHost = el("div", "cmt-table");
    tableHost.id = "careerCommentTable";
    host.appendChild(tableHost);
    renderCareerCommentTable(rows);

    renderQuoteAwards(s, host);
    renderDistinctiveWords(rows, host);

    host.insertAdjacentHTML("beforeend",
      '<p class="block-note cmt-foot">' + s.totalComments + " comments, " +
      s.totalWords.toLocaleString() + " words" +
      (s.submitterNoteCount ? ", " + s.submitterNoteCount + " submitter notes" : "") +
      ". Rates over fewer than " + s.minCommentsForRates +
      " comments are left out of the superlatives above.</p>");
  }

  // At phone widths the wide tables (All-Time, and a season's Voting and
  // Comments) scroll sideways inside their box (.table-wide) rather than
  // dropping columns; this says so, on phones only.
  function tableHint(sortable) {
    return el("p", "table-hint", "Swipe the table sideways for every column." + (sortable ? " Tap a heading to sort." : ""));
  }

  // The all-time comment table, sortable by any column like All-time
  // standings: tap a heading to sort by it, again to flip the order.
  var COMMENT_COLUMNS = [
    { key: "name", label: "Player", left: true },
    { key: "comments", label: "Comments" },
    { key: "commentRate", label: "Rate", pct: true },
    { key: "meanWords", label: "Avg words" },
    { key: "medianWords", label: "Median" },
    { key: "zeroPointComments", label: "Zero-pt" },
    { key: "exclamationRate", label: "!", title: "Share of comments with an exclamation mark", pct: true },
    { key: "questionRate", label: "?", title: "Share of comments with a question mark", pct: true },
    { key: "allCapsRate", label: "CAPS", title: "Share of comments with an all-caps word", pct: true }
  ];
  var commentSort = { field: "comments", dir: "desc" };

  // Single comments that stand out, all-time (quoteAwards in career.json,
  // counted from the text by build.py), as a grid of quote cards. Long
  // quotes start clipped with a "Read all" toggle, so one 200-word comment
  // doesn't push the rest off screen.
  function renderQuoteAwards(s, host) {
    var q = s.quoteAwards || {};
    function pts(c) { return c.points + " " + plural(c.points, "point") + " given"; }
    function counted(c) { return c.count + " " + c.unit; }
    var cards = [
      [s.longestComment, "Longest comment ever written", function (c) { return [c.words + " words"]; }],
      [q.shortest, "Shortest review", function (c) { return [c.words + " " + plural(c.words, "word"), pts(c)]; }],
      [q.loudest, "Loudest comment", function (c) { return [counted(c)]; }],
      [q.mostExcited, "Most excited", function (c) { return [counted(c)]; }],
      [q.mostQuestions, "Most questions", function (c) { return [counted(c)]; }],
      [q.mostEmoji, "Most emoji", function (c) { return [counted(c)]; }],
      [q.mostWordsForZero, "Most words for zero points", function (c) { return [c.words + " words", "0 points given"]; }]
    ];
    // Judged by Claude from comment_sentiment.json, when it exists.
    var sq = (s.sentimentAwards && s.sentimentAwards.quotes) || {};
    var judged = [
      [sq.funniest, "Funniest comment"], [sq.wittiest, "Wittiest comment"], [sq.angriest, "Angriest comment"],
      [sq.meanest, "Meanest comment"], [sq.mostHeartfelt, "Most heartfelt comment"], [sq.hottestTake, "Hottest take"]
    ].filter(function (x) { return x[0]; });
    judged.forEach(function (x) { cards.push([x[0], x[1], function () { return ["judged by Claude"]; }]); });
    cards = cards.filter(function (x) { return x[0]; });
    if (!cards.length) return;
    var wrap = el("div", "quote-awards");
    wrap.appendChild(el("h3", null, "Comment awards"));
    if (judged.length) {
      wrap.appendChild(el("p", "block-note quote-note",
        "Funniest, meanest and the rest are judged by an AI model (Claude) reading each comment, so treat them as a bit of fun. The others are counted from the text."));
    }
    var grid = el("div", "quote-grid");
    cards.forEach(function (x) { grid.appendChild(commentQuote(x[0], x[1], x[2](x[0]))); });
    wrap.appendChild(grid);
    host.appendChild(wrap);
    Array.prototype.forEach.call(grid.querySelectorAll("blockquote"), function (bq) {
      // clip first, then measure: unclipped, a quote is always exactly as
      // tall as its text, so it could never look too long
      bq.classList.add("is-clipped");
      if (bq.scrollHeight <= bq.clientHeight + 2) { bq.classList.remove("is-clipped"); return; }
      var more = el("button", "quote-more", "Read all");
      more.type = "button";
      more.setAttribute("aria-expanded", "false");
      more.addEventListener("click", function () {
        var open = bq.classList.toggle("is-open");
        more.textContent = open ? "Show less" : "Read all";
        more.setAttribute("aria-expanded", String(open));
      });
      bq.insertAdjacentElement("afterend", more);
    });
  }

  function renderCareerCommentTable(rows) {
    var host = $("careerCommentTable");
    if (!host) return;
    var f = commentSort.field, asc = commentSort.dir === "asc";
    var sorted = rows.slice().sort(function (a, b) {
      if (f === "name") return asc ? a.name.localeCompare(b.name) : b.name.localeCompare(a.name);
      var av = a[f] == null ? -Infinity : a[f], bv = b[f] == null ? -Infinity : b[f];
      return (asc ? av - bv : bv - av) || a.name.localeCompare(b.name);
    });
    var box = el("div", "framed table-wide cmt-table-box");
    var head = el("div", "crow head");
    COMMENT_COLUMNS.forEach(function (col) {
      var active = f === col.key;
      var b = el("button", "sort-btn" + (active ? " is-active" : "") + (col.left ? " is-left" : ""));
      b.type = "button";
      if (col.title) b.title = col.title;
      b.setAttribute("aria-label", "Sort by " + (col.title || col.label));
      b.innerHTML = esc(col.label) + (active ? '<span class="arrow">' + (asc ? " ↑" : " ↓") + "</span>" : "");
      b.addEventListener("click", function () {
        if (commentSort.field === col.key) commentSort.dir = commentSort.dir === "desc" ? "asc" : "desc";
        else { commentSort.field = col.key; commentSort.dir = col.key === "name" ? "asc" : "desc"; }
        renderCareerCommentTable(rows);
      });
      head.appendChild(b);
    });
    box.appendChild(head);
    sorted.forEach(function (p) {
      box.insertAdjacentHTML("beforeend", '<div class="crow"><div class="vname">' + who(p.name, p.id) + "</div>" +
        COMMENT_COLUMNS.slice(1).map(function (col) {
          return '<div class="num">' + (col.pct ? pct(p[col.key]) : p[col.key]) + "</div>";
        }).join("") + "</div>");
    });
    // keep the sideways scroll where it was across a re-sort
    var old = host.querySelector(".table-wide"), x = old ? old.scrollLeft : 0;
    host.innerHTML = "";
    host.appendChild(box);
    box.scrollLeft = x;
  }

  function renderCareerHighlights(c) {
    var h = c.highlights || {};
    var g = el("div", "hl-grid hl-pair");
    if (h.topScore) g.appendChild(careerTile("Highest career score", who(h.topScore.name), Math.round(h.topScore.careerScore) + " career score", h.topScore.tiedWith));
    if (h.mostWins) g.appendChild(careerTile("Most rounds won", who(h.mostWins.name), h.mostWins.roundsWon + " round wins", h.mostWins.tiedWith));
    if (h.mostPodiums) g.appendChild(careerTile("Most podiums", who(h.mostPodiums.name), h.mostPodiums.podiums + " top-3 finishes", h.mostPodiums.tiedWith));
    if (h.bestSingleSeason) g.appendChild(careerTile("Best single season", who(h.bestSingleSeason.name), h.bestSingleSeason.points + " points in " + esc(h.bestSingleSeason.season), h.bestSingleSeason.tiedWith));
    if (h.bestTastemaker) g.appendChild(tastemakerTile(h.bestTastemaker));
    setBlock("highlights", g);
  }

  // Columns that add up to the Score, left to right: Score = Avg season +
  // Round Podium Pts + Season Podium Pts. Rounds says why a short career can
  // rank high, and who hasn't played enough to be scored yet.
  var CAREER_COLUMNS = [
    { key: "name", label: "Player", left: true },
    { key: "careerScore", label: "Score" },
    { key: "avgSeason", label: "Avg season" },
    { key: "roundBonus", label: "Round Podium Pts" },
    { key: "seasonBonus", label: "Season Podium Pts" },
    { key: "rounds", label: "Rounds" }
  ];

  // Unscored players (too few rounds) have no score parts: null, so they
  // sink to the bottom of any sort rather than topping "Avg season" on the
  // strength of one round.
  function careerFieldValue(p, key) {
    if (key === "name") return p.name;
    if (key === "rounds") return p.rounds;
    if (!p.rated) return null;
    return p[key];
  }

  function careerRowHtml(p) {
    var f = p.roundFinishes || {};
    var dash = '<div class="num">&ndash;</div>';
    var html = '<div class="vname">' + who(p.name, p.id) + "</div>";
    if (!p.rated) {
      return html + dash + dash + dash + dash +
        '<div class="num">' + p.rounds + '<small class="cs-sub">needs ' + careerData.careerScoreFormula.minRounds + "</small></div>";
    }
    var podiums = (p.seasonPodiums || []).map(function (s) { return ordinal(s.place) + " " + s.label.replace("Season ", "S"); }).join(", ");
    return html +
      '<div class="num"><b>' + Math.round(p.careerScore) + "</b></div>" +
      '<div class="num">' + Math.round(p.avgSeason) + "</div>" +
      '<div class="num">' + p.roundBonus + '<small class="cs-sub" title="1st / 2nd / 3rd in a round">' +
        (f.first || 0) + "/" + (f.second || 0) + "/" + (f.third || 0) + "</small></div>" +
      '<div class="num">' + p.seasonBonus + (podiums ? '<small class="cs-sub">' + esc(podiums) + "</small>" : "") + "</div>" +
      '<div class="num">' + p.rounds + "</div>";
  }

  function sortCareerPlayers(players, field, dir) {
    var arr = players.slice();
    arr.sort(function (a, b) {
      var av = careerFieldValue(a, field), bv = careerFieldValue(b, field);
      if (av == null && bv == null) return 0;
      if (av == null) return 1;   // no data for this season sinks to the bottom regardless of direction
      if (bv == null) return -1;
      if (field === "name") return dir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
      return dir === "asc" ? av - bv : bv - av;
    });
    return arr;
  }

  function setCareerSort(field) {
    if (careerSort.field === field) {
      careerSort.dir = careerSort.dir === "desc" ? "asc" : "desc";
    } else {
      careerSort.field = field;
      careerSort.dir = field === "name" ? "asc" : "desc";
    }
    renderCareerStandings(careerData);
  }

  function renderCareerStandings(c) {
    var host = $("standings");
    // keep the sideways scroll where it was across a re-sort
    var old = host.querySelector(".table-wide"), x = old ? old.scrollLeft : 0;
    host.innerHTML = "";
    if (!c.players.length) { host.appendChild(empty("No completed seasons yet.")); return; }

    var gridStyle = "grid-template-columns:1.6fr repeat(" + (CAREER_COLUMNS.length - 1) + ",1fr);";

    var head = el("div", "vrow head career-head");
    head.setAttribute("style", gridStyle);
    CAREER_COLUMNS.forEach(function (col) {
      var active = careerSort.field === col.key;
      var b = el("button", "career-sort-btn" + (active ? " is-active" : "") + (col.left ? " is-left" : ""));
      b.type = "button";
      b.innerHTML = esc(col.label) + (active ? '<span class="arrow">' + (careerSort.dir === "asc" ? " \u2191" : " \u2193") + "</span>" : "");
      b.addEventListener("click", function () { setCareerSort(col.key); });
      head.appendChild(b);
    });
    var box = el("div", "framed career-table table-wide");
    box.appendChild(head);

    var sorted = sortCareerPlayers(c.players, careerSort.field, careerSort.dir);
    sorted.forEach(function (p, i) {
      var row = el("div", "vrow" + (i === 0 && careerSort.field === "careerScore" && careerSort.dir === "desc" ? " is-leader" : ""));
      row.setAttribute("style", gridStyle);
      row.innerHTML = careerRowHtml(p);
      box.appendChild(row);
    });
    host.appendChild(tableHint(true));
    host.appendChild(box);
    box.scrollLeft = x;
  }

  function initCareer() {
    Promise.all([PFML.loadJSON("index.json"), PFML.loadJSON("career.json")])
      .then(function (res) {
        var index = res[0], c = res[1];
        careerData = c;
        knowPeople(c.players);
        renderNav(index, "career");
        var line = c.seasons.length
          ? "Combined standings across " + c.seasons.length + " played " + plural(c.seasons.length, "season") + ": " +
            c.seasons.map(function (s) { return s.label; }).join(", ") + "."
          : "No seasons have finished a round yet.";
        $("heroLine").textContent = line;
        renderCareerHighlights(c);
        renderCareerComments(c);
        var note = $("standingsNote");
        if (note && c.careerScoreFormula) {
          var f = c.careerScoreFormula;
          note.textContent = "Score = Avg season + Round Podium Pts + Season Podium Pts. Avg season is points per round played \u00d7 " +
            f.perRoundScale + ", a typical season's worth, so missed rounds don't count against anyone. Round Podium Pts: " +
            f.roundBonus.join("/") + " for each 1st/2nd/3rd in a round. Season Podium Pts: " + f.seasonBonus.join("/") +
            " for finishing a season 1st/2nd/3rd (once it's over). Scored after " + f.minRounds +
            " rounds played. Tap any column to sort by it.";
        }
        renderCareerStandings(c);
      })
      .catch(function (err) {
        console.error(err);
        var l = $("heroLine");
        if (l) l.textContent = "All-Time data didn't load. Try reloading the page.";
      });
  }

  /* ---- profile page (profile?p=<competitor id>; yours without ?p) ----
     Totals and comment stats come from career.json, the rest (season
     finishes, best tracks, fans) from profiles.json, both built by
     scripts/build.py; the reaction tally is live from Supabase. */

  function ordinal(n) {
    var s = ["th", "st", "nd", "rd"], v = n % 100;
    return n + (s[(v - 20) % 10] || s[v] || s[0]);
  }

  function profileUrl(id) { return "profile?p=" + encodeURIComponent(id); }

  // Career Score rank with ties, the way Standings shares places, among
  // scored players only. null for someone with too few rounds to score.
  function careerRank(players, p) {
    if (!p.rated) return null;
    var rated = players.filter(function (x) { return x.rated; });
    var above = rated.filter(function (x) { return x.careerScore > p.careerScore; }).length;
    var tied = rated.filter(function (x) { return x.careerScore === p.careerScore; }).length > 1;
    return { rank: above + 1, tied: tied, of: rated.length };
  }

  // The Career Score as the sum the All-Time table shows in columns:
  // Score = Avg season + Round Podium Pts + Season Podium Pts.
  function scoreParts(c, p) {
    var box = el("div", "pf-parts");
    var f = c.careerScoreFormula || {};
    if (!p.rated) {
      box.innerHTML = '<p class="pf-parts-none">Career Score starts after ' + f.minRounds + " rounds played. " +
        esc(p.name) + " has played " + p.rounds + ".</p>";
      return box;
    }
    var rf = p.roundFinishes || {};
    var podiums = (p.seasonPodiums || []).map(function (s) { return ordinal(s.place) + " in " + s.label; }).join(", ");
    function part(value, label, sub) {
      return '<span class="pf-part"><b>' + value + "</b><span>" + label + "</span>" + (sub ? "<small>" + esc(sub) + "</small>" : "") + "</span>";
    }
    box.innerHTML = '<p class="pf-parts-title">How the Career Score adds up</p><div class="pf-parts-row">' +
      part(Math.round(p.careerScore), "Career Score") + '<span class="pf-op">=</span>' +
      part(Math.round(p.avgSeason), "Avg season", (p.totalPoints / p.rounds).toFixed(1) + " a round \u00d7 " + f.perRoundScale) + '<span class="pf-op">+</span>' +
      part(p.roundBonus, "Round Podium Pts", (rf.first || 0) + " 1st, " + (rf.second || 0) + " 2nd, " + (rf.third || 0) + " 3rd") + '<span class="pf-op">+</span>' +
      part(p.seasonBonus, "Season Podium Pts", podiums || "none yet") + "</div>";
    return box;
  }

  function rankLine(c, p, r) {
    return r ? (r.tied ? "Tied " : "") + ordinal(r.rank) + " of " + r.of + " scored players"
             : "Scored after " + c.careerScoreFormula.minRounds + " rounds: " + p.rounds + " so far";
  }

  function renderProfileSwitch(c, id, myId) {
    var host = $("pfSwitch");
    if (!host) return;
    var people = c.players.slice().sort(function (a, b) { return a.name.localeCompare(b.name); });
    host.innerHTML = '<label class="cm-sr" for="pfPick">Show another player</label>' +
      // In .rp-jump, like the round page's menu, for its ▾ and its width.
      '<div class="rp-jump"><select id="pfPick" class="rp-jump-select">' + people.map(function (p) {
        return '<option value="' + esc(p.id) + '"' + (p.id === id ? " selected" : "") + ">" +
          esc(p.name) + (p.id === myId ? " (you)" : "") + "</option>";
      }).join("") + "</select></div>";
    $("pfPick").addEventListener("change", function () {
      var v = $("pfPick").value;
      if (v && v !== id) location.href = profileUrl(v);
    });
  }

  function renderProfileCareer(c, p, prof) {
    // Six tiles: two rows of three, or three rows of two on a phone (.pf-tiles).
    var g = el("div", "hl-grid hl-pair pf-tiles");
    var r = careerRank(c.players, p);
    g.appendChild(careerTile("Career Score", p.rated ? String(Math.round(p.careerScore)) : "&ndash;", rankLine(c, p, r)));
    g.appendChild(careerTile("Total points", String(p.totalPoints),
      p.seasonsPlayed + " " + plural(p.seasonsPlayed, "season") + ", " + p.avgPointsPerSeason + " a season"));
    g.appendChild(careerTile("Rounds won", String(p.roundsWon),
      p.submissions ? pct(p.roundsWon / p.submissions) + " of their tracks" : ""));
    // Consistency, where Rounds won only counts the very top: how often a
    // track of theirs finished in its round's top three.
    g.appendChild(careerTile("Top-3 rate", p.submissions ? pct(p.podiums / p.submissions) : "&ndash;",
      p.podiums + " of " + p.submissions + " " + plural(p.submissions, "track") + " in a round’s top 3"));
    g.appendChild(careerTile("Tracks submitted", String(p.submissions),
      p.submissions ? (Math.round(p.totalPoints / p.submissions * 10) / 10) + " points a track" : ""));
    if (prof) g.appendChild(careerTile("Points given", String(prof.pointsGiven), "to other players’ tracks"));
    setBlock("pfCareer", g);
    $("pfCareer").appendChild(scoreParts(c, p));
  }

  function renderProfileSeasons(prof) {
    var host = $("pfSeasons");
    host.innerHTML = "";
    var seasons = (prof && prof.seasons) || [];
    if (!seasons.length) { host.appendChild(empty("No finished rounds yet.")); return; }
    var grid = "grid-template-columns:1.4fr 1.2fr repeat(3,1fr);";
    var box = el("div", "framed career-table pf-seasons");
    var head = el("div", "vrow head");
    head.setAttribute("style", grid);
    head.innerHTML = "<div>Season</div><div>Finish</div><div class=\"num\">Points</div><div class=\"num\">Won</div><div class=\"num\">Top-3</div>";
    box.appendChild(head);
    seasons.forEach(function (s) {
      var row = el("div", "vrow" + (s.rank === 1 ? " is-leader" : ""));
      row.setAttribute("style", grid);
      row.innerHTML = '<div class="vname"><a href="' + esc(s.key) + '">' + esc(s.label) + "</a></div>" +
        "<div>" + (s.tied ? "T" : "") + ordinal(s.rank) + ' <small class="pf-of">of ' + s.field + "</small></div>" +
        '<div class="num"><b>' + s.points + '</b></div><div class="num">' + s.roundsWon + '</div><div class="num">' + s.podiums + "</div>";
      box.appendChild(row);
    });
    host.appendChild(box);
  }

  function renderProfileTracks(prof) {
    var host = $("pfTracks");
    host.innerHTML = "";
    var tracks = (prof && prof.bestTracks) || [];
    if (!tracks.length) { host.appendChild(empty("No tracks submitted yet.")); return; }
    var list = el("div", "rl");
    list.innerHTML = tracks.map(function (t) {
      // the same address rounds.js's roundUrl() builds; profile.html doesn't load rounds.js
      var href = "round?s=" + encodeURIComponent(t.seasonKey) + "&r=" + encodeURIComponent(t.roundId);
      var art = t.art ? '<img class="rl-art" src="' + esc(t.art) + '" alt="" loading="lazy" referrerpolicy="no-referrer">'
                      : '<span class="rl-art is-empty" aria-hidden="true">&#9835;</span>';
      return '<a class="rl-card" href="' + href + '">' + art +
        '<span class="rl-text"><span class="rl-num">' + esc(t.seasonLabel) + " &middot; Round " + t.roundNumber + " &middot; " + esc(t.roundName) + "</span>" +
        '<span class="rl-name">' + esc(t.title) + "</span>" +
        '<span class="rl-sub">' + esc(t.artistText) + "</span>" +
        '<span class="rl-counts">' + t.points + " points" + (t.place ? " &middot; " + ordinal(t.place) + " place" : "") + "</span>" +
        '</span><span class="rl-go" aria-hidden="true">&rarr;</span></a>';
    }).join("");
    host.appendChild(list);
  }

  // value: what goes on the right of each name (points, by default)
  function peopleList(title, people, note, value) {
    value = value || function (x) { return x.points + " <small>pts</small>"; };
    var col = el("div", "pf-people");
    col.innerHTML = "<h3>" + esc(title) + "</h3>" + (people.length ? "<ol>" + people.map(function (x) {
      return '<li><a href="' + profileUrl(x.id) + '">' + PFML.avatar(x.id, x.name) + "<span>" + esc(x.name) + "</span></a>" +
        "<b>" + value(x) + "</b></li>";
    }).join("") + "</ol>" : '<p class="pf-none">' + esc(note) + "</p>");
    return col;
  }

  function renderProfileFans(prof, name) {
    var host = $("pfFans");
    host.innerHTML = "";
    var wrap = el("div", "pf-fans");
    wrap.appendChild(peopleList("Biggest fans", (prof && prof.fans) || [], "Nobody has voted for " + name + " yet."));
    wrap.appendChild(peopleList("Their favourites", (prof && prof.favorites) || [], name + " hasn’t voted yet."));
    // build.taste_twins: who backs the same songs more than usual, ranked;
    // the correlation itself is modest, so no percentage
    wrap.appendChild(peopleList("Votes most like them", (prof && prof.tasteTwins) || [],
      "Not enough rounds voted alongside anyone yet.",
      function (x) { return "<small>over " + x.rounds + " rounds</small>"; }));
    host.appendChild(wrap);
  }

  function renderProfileComments(cm, id) {
    var host = $("pfComments");
    host.innerHTML = "";
    if (!cm || !cm.comments) { host.appendChild(empty("No vote comments yet.")); return; }
    var g = el("div", "hl-grid hl-pair");
    g.appendChild(careerTile("Comments left", String(cm.comments),
      cm.commentRate != null ? "on " + pct(cm.commentRate) + " of their votes" : ""));
    g.appendChild(careerTile("Average length", cm.meanWords + " words", "median " + cm.medianWords));
    if (cm.distinctiveWord) {
      g.appendChild(careerTile("Signature word", "“" + esc(cm.distinctiveWord.word) + "”",
        "used " + cm.distinctiveWord.uses + " times, " + cm.distinctiveWord.vsLeague + "× the league’s rate"));
    }
    var reacts = careerTile("Reactions on their comments", "&hellip;", "");
    reacts.id = "pfReacts";
    g.appendChild(reacts);
    host.appendChild(g);
    if (cm.longest) host.appendChild(commentQuote(cm.longest, "Longest comment"));
    fillProfileReactions(id);
  }

  // Live from Supabase, leaving out any they left on their own comments.
  function fillProfileReactions(id) {
    var tile = $("pfReacts");
    Promise.all([PFML.api.reactionsOn(id), PFML.api.people()]).then(function (res) {
      var counts = Object.create(null), total = 0;   // keyed by member-written text
      res[0].forEach(function (r) {
        var member = res[1][r.user_id];
        if (member && member.competitorId === id) return;
        counts[r.reaction] = (counts[r.reaction] || 0) + 1;
        total++;
      });
      var top = Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a] || (a < b ? -1 : 1); }).slice(0, 5);
      tile.querySelector(".hl-value").textContent = String(total);
      var meta = top.map(function (k) { return PFML.reactionGlyph(k) + " " + counts[k]; }).join("  ");
      tile.insertAdjacentHTML("beforeend", '<div class="hl-meta pf-reacts">' + esc(meta || "none yet") + "</div>");
    }).catch(function () { tile.hidden = true; });
  }

  function initProfile() {
    var myId = PFML.member.competitorId;
    var id = new URLSearchParams(location.search).get("p") || myId;
    Promise.all([
      PFML.loadJSON("index.json"),
      PFML.loadJSON("career.json"),
      // null if not published yet: the page still shows what career.json has
      PFML.loadJSON("profiles.json").catch(function () { return null; })
    ]).then(function (res) {
      var c = res[1], profiles = res[2];
      knowPeople(c.players);
      renderNav(res[0], "profile");
      var p = c.players.filter(function (x) { return x.id === id; })[0];
      var prof = profiles && profiles.players[id];
      var cm = (c.commenters || []).filter(function (x) { return x.id === id; })[0];
      renderProfileSwitch(c, id, myId);
      if (!p) {
        $("pfId").innerHTML = "<h1>Player not found</h1>";
        $("heroLine").textContent = "That player isn’t in any finished season. Pick someone from the list.";
        Array.prototype.forEach.call(document.querySelectorAll("main .block"), function (s) { s.hidden = true; });
        return;
      }
      document.title = "PFML - " + p.name;
      $("pfId").innerHTML = PFML.avatar(p.id, p.name, "pf-av") + "<h1>" + esc(p.name) + "</h1>";
      var r = careerRank(c.players, p);
      $("heroLine").textContent = (p.id === myId ? "Your profile. " : "") +
        (r ? (r.tied ? "Tied " : "") + ordinal(r.rank) + " of " + r.of + " by Career Score" : "Not scored yet (" + p.rounds + " of " + c.careerScoreFormula.minRounds + " rounds)") +
        ", across " + p.seasonsPlayed + " " + plural(p.seasonsPlayed, "season") + ".";
      renderProfileCareer(c, p, prof);
      renderProfileSeasons(prof);
      renderProfileTracks(prof);
      renderProfileFans(prof, p.name);
      renderProfileComments(cm, p.id);
      if (!profiles) {
        ["block-seasons", "block-tracks", "block-fans"].forEach(function (s) { $(s).hidden = true; });
      }
    }).catch(function (err) {
      console.error(err);
      $("heroLine").textContent = "The profile didn’t load: " + (err.message || err);
    });
  }

  /* ---- round page (round?s=<season key>&r=<round id>, or round?site=<site round id>) ---- */

  // A round's page: its stats (rounds.js) once it's in them, and, when it
  // was also run on the site, its listening section (listen.js). A site
  // round is reached by round?site=<id> from the moment it closes; once
  // it's in the stats, that shows the stats page too, and the stats page
  // finds it the same way (PFMLListen.statsIndex). README, Listening on the
  // round page.
  function initRound() {
    var params = new URLSearchParams(location.search);
    var key = params.get("s") || "";
    var roundId = params.get("r") || "";
    var siteId = params.get("site") || (window.PFMLDemo && window.PFMLDemo.round) || "";
    var page = $("roundPage");
    function failed(err) {
      console.error(err);
      page.innerHTML = '<section class="shell rp-head"><h1>Couldn’t load this round</h1><p class="hero-line">' + esc(err.message || err) + "</p></section>";
    }
    if (!siteId && !/^season\d+$/.test(key)) {
      page.innerHTML = '<section class="shell rp-head"><h1>Round not found</h1><p class="hero-line">This link is missing its season. <a href="./">Back to the home page</a>.</p></section>';
      return;
    }
    // the site's rounds are a bonus here: without them it's the stats alone
    var siteRounds = PFML.api.siteRounds().catch(function (err) { console.error(err); return []; });

    if (siteId) {
      Promise.all([PFML.loadJSON("index.json"), siteRounds]).then(function (res) {
        var index = res[0], site = (res[1] || []).filter(function (x) { return x.id === siteId; })[0];
        if (!site) {
          page.innerHTML = '<section class="shell rp-head"><h1>Round not found</h1><p class="hero-line">That round isn’t on the site. <a href="./">Back to the home page</a>.</p></section>';
          return;
        }
        renderNav(index, site.season_key);
        var listed = (index.seasons || []).filter(function (x) { return x.key === site.season_key; })[0];
        return PFML.loadJSON(site.season_key + ".json").catch(function () { return null; }).then(function (d) {
          var i = d ? window.PFMLListen.statsIndex(d.rounds, site) : -1;
          if (i >= 0) window.PFMLRounds.renderRoundPage(d, d.rounds[i].id);
          else window.PFMLRounds.renderSiteRoundPage(site, listed ? listed.label : "Season " + String(site.season_key).replace(/^season/, ""));
          window.PFMLListen.render($("rpListen"), site);
        });
      }).catch(failed);
      return;
    }

    Promise.all([PFML.loadJSON("index.json"), PFML.loadJSON(key + ".json"), siteRounds])
      .then(function (res) {
        var d = res[1];
        renderNav(res[0], key);
        window.PFMLRounds.renderRoundPage(d, roundId);
        var i = -1;
        d.rounds.forEach(function (r, k) { if (r.id === roundId) i = k; });
        var site = i >= 0 && (res[2] || []).filter(function (x) {
          return x.season_key === key && window.PFMLListen.statsIndex(d.rounds, x) === i;
        })[0];
        if (site && $("rpListen")) window.PFMLListen.render($("rpListen"), site);
      })
      .catch(failed);
  }

  /* ---- boot ---- */

  function boot() {
    var page = document.body.getAttribute("data-page");
    if (page === "home") {
      initHome();
    } else if (page === "season") {
      initSeason(document.body.getAttribute("data-season-key"));
    } else if (page === "career") {
      initCareer();
    } else if (page === "round") {
      initRound();
    } else if (page === "profile") {
      initProfile();
    } else if (page === "submit" || page === "repeats" || page === "commissioner") {
      // the page itself is submit.js's, repeats.js's or commissioner.js's;
      // this only fills the header
      PFML.loadJSON("index.json")
        .then(function (index) { renderNav(index, page); })
        .catch(function (err) { console.error(err); });
    }
  }

  // Wait for auth.js to let a member in before touching any data.
  PFML.ready.then(boot);
})();
