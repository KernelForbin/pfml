/* PFML — front end.
   Loads the JSON that scripts/build.py generates from the Music League CSV
   exports and renders it. No framework, no build step, no Spotify API:
   every Spotify link is a plain open.spotify.com URL built from IDs
   already present in the export.

   Two page types share this file:
     - home page   (<body data-page="home">)   -> season cards + playlists
     - season page (<body data-page="season" data-season-key="seasonN">)
                                                 -> full season dashboard
   Both render a season nav in the top bar from data/index.json. */

(function () {
  "use strict";

  var DATA = "data";

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
  function plural(n, one, many) { return n === 1 ? one : (many || one + "s"); }

  function fetchJSON(url) {
    // Members-only: season data comes from the private Supabase bucket via
    // auth.js, not from a public file next to this page.
    if (window.PFML && window.PFML.loadJSON) {
      return window.PFML.loadJSON(url.replace(/^data\//, ""));
    }
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error(url + ": HTTP " + r.status);
      return r.json();
    });
  }

  /* ---- Spotify links -------------------------------------------------
     Track and playlist IDs are in the export, so those are exact links.
     Artist and album names are text only, with no IDs, so those go to a
     Spotify search scoped to the name. */

  function trackLink(id) { return id ? "https://open.spotify.com/track/" + id : null; }
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

    index.seasons.forEach(function (s) {
      var live = s.key === index.currentSeason;
      var a = el("a", "season-tab");
      a.href = s.key + ".html";
      a.setAttribute("aria-current", String(s.key === activeKey));
      a.innerHTML = (live ? '<span class="pip" aria-hidden="true"></span>' : "") + esc(s.label);
      if (live) a.title = "Season in progress";
      nav.appendChild(a);
    });

    var career = el("a", "season-tab");
    career.href = "career.html";
    career.textContent = "Career";
    career.setAttribute("aria-current", String(activeKey === "career"));
    nav.appendChild(career);
    syncScrollPadding();
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
  function syncScrollPadding() {
    var bar = document.querySelector(".topbar");
    if (bar) document.documentElement.style.scrollPaddingTop = (bar.offsetHeight + 12) + "px";
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
    a.href = s.key + ".html";

    var nameHtml = '<div class="season-card-name-wrap"><span class="season-card-name">' + esc(s.label) + "</span>" +
      (isLive ? '<span class="live-badge"><span class="pip" aria-hidden="true"></span>Live</span>' : "") + "</div>";

    var statLine = s.roundCount
      ? s.roundCount + " " + plural(s.roundCount, "round") + " &middot; " + s.songCount + " tracks &middot; " + s.playerCount + " players"
      : s.playerCount + " players &middot; not started yet";

    var roundLine = "";
    if (isLive && s.liveRound) {
      roundLine = '<div class="season-card-round">Round ' + s.liveRound.number + ": " + esc(s.liveRound.name) +
        '<span class="phase">' + esc(s.liveRound.phase) + " phase</span></div>";
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
    a.href = "career.html";
    a.innerHTML =
      '<div class="season-card-top"><div class="season-card-name-wrap"><span class="season-card-name">Career</span></div>' +
      '<span class="season-card-arrow">&rarr;</span></div>' +
      '<div class="season-card-stats">All-time standings across ' + played + " " + plural(played, "season") + "</div>" +
      '<div class="season-card-round">Career Score, every season side by side, all-time comment stats</div>';
    return a;
  }

  function playlistChip(item) {
    if (item.url) {
      var a = el("a", "pill pill-live");
      a.href = item.url; a.target = "_blank"; a.rel = "noopener";
      a.textContent = item.label;
      return a;
    }
    var span = el("span", "pill is-disabled");
    span.textContent = item.label + " — coming soon";
    return span;
  }

  function renderPlaylists(pl) {
    var host = $("playlists");
    if (!host) return;
    host.innerHTML = "";
    if (!pl) { host.appendChild(empty("Playlists haven't been added yet.")); return; }

    if (pl.leagueWide && pl.leagueWide.length) {
      var g0 = el("div", "playlist-group");
      g0.appendChild(el("h3", null, "League-wide"));
      var row0 = el("div", "playlist-row");
      pl.leagueWide.forEach(function (item) { row0.appendChild(playlistChip(item)); });
      g0.appendChild(row0);
      host.appendChild(g0);
    }
    (pl.seasons || []).forEach(function (group) {
      var g = el("div", "playlist-group");
      g.appendChild(el("h3", null, group.season));
      var row = el("div", "playlist-row");
      group.items.forEach(function (item) { row.appendChild(playlistChip(item)); });
      g.appendChild(row);
      host.appendChild(g);
    });
  }

  function initHome() {
    fetchJSON(DATA + "/index.json").then(function (index) {
      window.__pfmlIndex = index;
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
      return fetchJSON(DATA + "/playlists.json").catch(function () { return null; });
    }).then(renderPlaylists).catch(function (err) {
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
    clear.addEventListener("click", function (ev) { ev.preventDefault && ev.preventDefault(); clearSelected(); });
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
      row.addEventListener("click", function () { toggleSelected(p.id); });
      row.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault && ev.preventDefault(); toggleSelected(p.id); }
      });
      box.appendChild(row);
    });
    setBlock("standings", box);
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
      standing.points + " points &middot; " + standing.roundsWon + " round" + (standing.roundsWon === 1 ? "" : "s") +
      " won &middot; " + standing.podiums + " top-3 finishes" +
      (standing.dailyDouble
        ? "<br>includes +" + standing.dailyDouble.bonus + " Daily Double (" + esc(standing.dailyDouble.trackTitle) +
          ", " + esc(standing.dailyDouble.roundName) + ")"
        : "")));

    if (songs.length) {
      var best = songs.reduce(function (a, b) { return b.points > a.points ? b : a; });
      g.appendChild(tile("Best submission", extLink(trackLink(best.spotifyId), best.title),
        esc(best.artistText) + "<br>" + best.points + " points &middot; " + esc(best.roundName)));
    }
    if (songs.length >= 2) {
      var worst = songs.reduce(function (a, b) { return b.points < a.points ? b : a; });
      g.appendChild(tile("Weakest submission", extLink(trackLink(worst.spotifyId), worst.title),
        esc(worst.artistText) + "<br>" + worst.points + " points &middot; " + esc(worst.roundName)));
    }
    var contested = songs.filter(function (s) { return s.backers >= 3; });
    if (contested.length) {
      var divisive = contested.reduce(function (a, b) { return b.spread > a.spread ? b : a; });
      if (divisive.spread > 0) {
        g.appendChild(tile("Most divisive submission", extLink(trackLink(divisive.spotifyId), divisive.title),
          "&sigma; " + divisive.spread + " among voters who backed it &middot; " + esc(divisive.roundName)));
      }
    }

    var fansOf = tasteTo(d, id).slice().sort(function (a, b) { return b.index - a.index; });
    if (fansOf.length) {
      g.appendChild(tile("Biggest fan", esc(fansOf[0].voterName),
        "sends " + fansOf[0].index + "&times; their baseline share of points to " + esc(name)));
      if (fansOf.length >= 2) {
        var cold = fansOf[fansOf.length - 1];
        g.appendChild(tile("Hardest to win over", esc(cold.voterName),
          "only " + cold.index + "&times; their baseline share"));
      }
    }
    var favorsOf = tasteFrom(d, id).slice().sort(function (a, b) { return b.index - a.index; });
    if (favorsOf.length) {
      g.appendChild(tile("Favorite to vote for", esc(favorsOf[0].submitterName),
        esc(name) + " sends " + favorsOf[0].index + "&times; baseline their way"));
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
        row.innerHTML = '<div class="stand-rank">&mdash;</div><div><div class="stand-name">' + esc(r.name) +
          '</div></div><div class="stand-score"><span>no submissions yet</span></div>';
      } else {
        var overallRank = r.standing.tied ? "T" + r.standing.rank : "#" + r.standing.rank;
        var pct = Math.max(3, Math.round((r.standing.points / max) * 100));
        row.innerHTML =
          '<div class="stand-rank">' + overallRank + "</div>" +
          '<div><div class="stand-name">' + esc(r.name) + "</div>" +
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
        "Across " + consideredRounds + " round" + (consideredRounds === 1 ? "" : "s") +
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
          '<div class="stand-score"><span>round' + (tally[id] === 1 ? "" : "s") + ' won</span></div>';
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
        g.appendChild(tile(esc(nameOf(d, a)) + " &rarr; " + esc(nameOf(d, b)), ab.index + "&times; baseline",
          ab.points + " points across " + ab.chances + " chances to vote"));
      }
      if (ba) {
        g.appendChild(tile(esc(nameOf(d, b)) + " &rarr; " + esc(nameOf(d, a)), ba.index + "&times; baseline",
          ba.points + " points across " + ba.chances + " chances to vote"));
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
      titleEl.textContent = nameOf(d, selected[0]);
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
    var shown = ties.slice(0, 3).map(esc);
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
      g.appendChild(tile("Highest-scoring track", extLink(trackLink(h.topTrack.spotifyId), h.topTrack.title),
        esc(h.topTrack.artistText) + "<br>" + esc(h.topTrack.submitterName) + " &middot; " + h.topTrack.points +
        " points &middot; " + esc(h.topTrack.roundName), false, h.topTrack.tiedWith));
    }
    if (h.divisiveTrack) {
      g.appendChild(tile("Most divisive track", extLink(trackLink(h.divisiveTrack.spotifyId), h.divisiveTrack.title),
        esc(h.divisiveTrack.artistText) + "<br>widest spread between voters who backed it (&sigma; " +
        h.divisiveTrack.spread + "), from " + esc(h.divisiveTrack.submitterName), false, h.divisiveTrack.tiedWith));
    }
    if (h.closestRound) {
      g.appendChild(tile("Closest round", esc(h.closestRound.name),
        h.closestRound.margin === 0 ? "ended in a tie at the top" : "won by " + h.closestRound.margin + " " + plural(h.closestRound.margin, "point"), false, h.closestRound.tiedWith));
    }
    if (h.blowoutRound) {
      g.appendChild(tile("Biggest blowout", esc(h.blowoutRound.name),
        esc(h.blowoutRound.winner) + " won by " + h.blowoutRound.margin + " points with " + esc(h.blowoutRound.title), false, h.blowoutRound.tiedWith));
    }
    if (h.biggestFan) {
      g.appendChild(tile("Biggest fan", esc(h.biggestFan.voterName) + " &rarr; " + esc(h.biggestFan.submitterName),
        "sends " + h.biggestFan.index + "&times; their baseline share of points that way", false, h.biggestFan.tiedWith));
    }
    if (h.coldestShoulder) {
      g.appendChild(tile("Coldest shoulder", esc(h.coldestShoulder.voterName) + " &rarr; " + esc(h.coldestShoulder.submitterName),
        "only " + h.coldestShoulder.index + "&times; their baseline share", false, h.coldestShoulder.tiedWith));
    }
    if (h.boldestVoter) {
      g.appendChild(tile("Boldest voter", esc(h.boldestVoter.name),
        "biggest single bet averages " + h.boldestVoter.avgTopBet + " points, spread over just " + h.boldestVoter.avgTracksBacked + " tracks a round", false, h.boldestVoter.tiedWith));
    }
    if (h.hedgiestVoter) {
      g.appendChild(tile("Widest spreader", esc(h.hedgiestVoter.name),
        "backs " + h.hedgiestVoter.avgTracksBacked + " tracks a round, top bet averages only " + h.hedgiestVoter.avgTopBet, false, h.hedgiestVoter.tiedWith));
    }
    if (h.bestTastemaker) {
      g.appendChild(tile("Best read on the room", esc(h.bestTastemaker.name),
        "their top pick won the round " + Math.round(h.bestTastemaker.kingmakerRate * 100) + "% of the time (" +
        h.bestTastemaker.kingmakerHits + " of " + h.bestTastemaker.kingmakerRounds + ")", false, h.bestTastemaker.tiedWith));
    }
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

    var chipRow = el("div", "trend-chips");
    all.forEach(function (s) {
      var on = trendSelected.indexOf(s.id) !== -1;
      var b = el("button", "trend-chip" + (on ? " is-on" : ""));
      b.type = "button";
      b.innerHTML = '<span class="dot" style="background:' + s.color + '"></span>' + esc(s.name);
      b.addEventListener("click", function () { toggleTrend(s.id); });
      chipRow.appendChild(b);
    });
    legend.appendChild(chipRow);

    var controls = el("div", "trend-controls");
    var allBtn = el("button", "trend-control", "Select all");
    allBtn.type = "button";
    allBtn.addEventListener("click", function () { trendSelected = all.map(function (s) { return s.id; }); renderTrend(seasonData); });
    var clearBtn = el("button", "trend-control", "Clear");
    clearBtn.type = "button";
    clearBtn.addEventListener("click", function () { trendSelected = []; renderTrend(seasonData); });
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
    meta += " &middot; " + esc(s.submitterName);
    if (showRound) meta += " &middot; " + esc(s.roundName);
    row.innerHTML =
      '<div class="trk-pos">' + pos + "</div>" +
      '<div class="trk-body"><div class="trk-title">' + extLink(trackLink(s.spotifyId), s.title) +
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
    attachFilterTag(host, seasonData);
    if (!all.length) { host.appendChild(empty(selected.length ? "No tracks from this selection." : "No tracks submitted yet.")); return; }
    var top = all.slice().sort(function (a, b) { return b.points - a.points; }).slice(0, 20);
    var box = el("div", "framed");
    top.forEach(function (s, i) { box.appendChild(trackRow(s, i + 1, true)); });
    host.appendChild(box);
  }


  function renderRounds(d) {
    // The collapsible Results by round under the leaderboard: one card per
    // round, each linking to that round's own page (rounds.js).
    var host = $("rounds");
    if (!host || !window.PFMLRounds) return;
    window.PFMLRounds.renderList(host, d, {
      selected: selected.slice(),
      filterTag: function (h) { attachFilterTag(h, seasonData); }
    });
  }

  /* ---- taste matrix (filterable) ---- */

  function renderTasteRowList(title, rows, host) {
    var block = el("div");
    block.appendChild(el("h3", null, title));
    if (!rows.length) { block.appendChild(empty("Not enough voting history yet.")); host.appendChild(block); return; }
    var box = el("div", "framed");
    rows.forEach(function (r) {
      box.insertAdjacentHTML("beforeend",
        '<div class="vrow"><div class="vname">' + esc(r.label) + '</div><div class="num">' + r.index.toFixed(2) +
        '&times;</div><div class="num">' + r.points + ' pts</div><div class="num">' + r.chances + ' ch.</div></div>');
    });
    block.appendChild(box);
    host.appendChild(block);
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
      "Read a row as: this voter sends that submitter this much of their points, relative to spreading points evenly across every track they saw. " +
      "1.00 is neutral, 2.00 is twice their usual share, 0.50 is half. Self-votes are excluded, and a pair needs at least five chances to vote before it shows.";

    attachFilterTag(host, d);

    if (selected.length === 1) {
      var id = selected[0], name = nameOf(d, id);
      var out = tasteFrom(d, id).slice().sort(function (a, b) { return b.index - a.index; })
        .map(function (t) { return { label: t.submitterName, index: t.index, points: t.points, chances: t.chances }; });
      var into = tasteTo(d, id).slice().sort(function (a, b) { return b.index - a.index; })
        .map(function (t) { return { label: t.voterName, index: t.index, points: t.points, chances: t.chances }; });
      renderTasteRowList("How " + name + " rates everyone else", out, host);
      renderTasteRowList("How everyone else rates " + name, into, host);
      return;
    }

    var people = selected.length >= 2
      ? d.competitors.filter(function (p) { return selected.indexOf(p.id) !== -1; })
      : d.competitors;

    var byKey = {};
    d.taste.forEach(function (t) { byKey[t.voterId + "|" + t.submitterId] = t; });
    var vals = d.taste.map(function (t) { return t.index; });
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);

    var head = "<thead><tr><th class=\"corner\">Voter &darr; / Submitter &rarr;</th>";
    people.forEach(function (p) { head += "<th>" + esc(p.name) + "</th>"; });
    head += "</tr></thead>";

    var body = "<tbody>";
    people.forEach(function (voter) {
      body += "<tr><th>" + esc(voter.name) + "</th>";
      people.forEach(function (sub) {
        if (voter.id === sub.id) { body += '<td class="nil">&mdash;</td>'; return; }
        var t = byKey[voter.id + "|" + sub.id];
        if (!t) { body += '<td class="nil">&middot;</td>'; return; }
        var f = hi > lo ? (t.index - lo) / (hi - lo) : 0.5;
        var alpha = (0.06 + f * 0.62).toFixed(2);
        var dark = f > 0.62;
        body += '<td style="background:rgba(158,0,196,' + alpha + ')' + (dark ? ";color:#fff" : "") + '" title="' +
          esc(voter.name) + " gave " + esc(sub.name) + " " + t.points + " points over " + t.chances + ' chances">' +
          t.index.toFixed(2) + "</td>";
      });
      body += "</tr>";
    });
    body += "</tbody>";

    var table = el("table", "taste");
    table.innerHTML = head + body;
    var scroll = el("div", "taste-scroll");
    scroll.appendChild(table);
    host.appendChild(scroll);
    host.insertAdjacentHTML("beforeend",
      '<div class="legend"><span>' + lo.toFixed(2) + '</span><span class="ramp"></span><span>' + hi.toFixed(2) +
      "</span><span>darker means a bigger share of that voter's points</span></div>");
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
    var box = el("div", "framed");
    box.insertAdjacentHTML("beforeend",
      '<div class="vrow head"><div>Player</div><div class="num">Top bet</div><div class="num">Tracks backed</div><div class="num">Top pick won</div></div>');
    rows.forEach(function (v) {
      box.insertAdjacentHTML("beforeend",
        '<div class="vrow"><div class="vname">' + esc(v.name) + "</div>" +
        '<div class="num">' + v.avgTopBet.toFixed(1) + "</div>" +
        '<div class="num">' + v.avgTracksBacked.toFixed(1) + "</div>" +
        '<div class="num">' + Math.round(v.kingmakerRate * 100) + "%</div></div>");
    });
    host.appendChild(box);
  }

  /* ---- comments (filterable) ----
     Counts and superlatives, not a transcript. The one place raw comment
     text appears is the longest comment, where the text is the point.
     Everything here is a voter comment (votes.csv); a submitter's note on
     their own track is a different thing and gets its own line. */

  function pct(rate) { return Math.round(rate * 100) + "%"; }

  function commentQuote(c, label) {
    var meta = [];
    if (c.trackTitle) meta.push(extLink(trackLink(c.spotifyId), c.trackTitle));
    if (c.roundName) meta.push(esc(c.roundName));
    if (c.seasonLabel) meta.push(esc(c.seasonLabel));
    meta.push(c.words + " words");
    var box = el("div", "cmt-quote");
    box.innerHTML =
      '<p class="cmt-label">' + esc(label) + "</p>" +
      "<blockquote>" + esc(c.text) + "</blockquote>" +
      '<p class="cmt-src">' + (c.name ? "<b>" + esc(c.name) + "</b> &middot; " : "") +
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
        g.appendChild(tile("Most likely to say something", esc(summary.chattiest.name),
          pct(summary.chattiest.rate) + " of their votes carry a comment", false, summary.chattiest.tiedWith));
      }
      if (summary.quietest) {
        g.appendChild(tile("Least likely", esc(summary.quietest.name),
          pct(summary.quietest.rate) + " &middot; " + summary.quietest.comments + " comments", false, summary.quietest.tiedWith));
      }
      if (summary.wordiest) {
        g.appendChild(tile("Wordiest", esc(summary.wordiest.name),
          summary.wordiest.meanWords + " words per comment on average", false, summary.wordiest.tiedWith));
      }
      if (summary.tersest) {
        g.appendChild(tile("Tersest", esc(summary.tersest.name),
          summary.tersest.meanWords + " words per comment on average", false, summary.tersest.tiedWith));
      }
      if (summary.loudest) {
        g.appendChild(tile("Most SHOUTING", esc(summary.loudest.name),
          pct(summary.loudest.rate) + " of their comments have an all-caps word", false, summary.loudest.tiedWith));
      }
      if (summary.richestVocab) {
        g.appendChild(tile("Widest vocabulary", esc(summary.richestVocab.name),
          summary.richestVocab.richness.toFixed(2) + " unique words per word, measured over " +
          summary.richestVocab.sampleWords + "-word samples", false, summary.richestVocab.tiedWith));
      }
      if (summary.mostZeroPoint) {
        g.appendChild(tile("Most all-talk", esc(summary.mostZeroPoint.name),
          summary.mostZeroPoint.count + " comments awarding zero points", false, summary.mostZeroPoint.tiedWith));
      }
      if (summary.silentTreatment && summary.silentTreatment.comments === 0) {
        g.appendChild(tile("Silent treatment",
          esc(summary.silentTreatment.voterName) + " &rarr; " + esc(summary.silentTreatment.submitterName),
          "never commented on them in " + summary.silentTreatment.chances + " chances", false, summary.silentTreatment.tiedWith));
      } else if (summary.mostTalkedAt) {
        g.appendChild(tile("Most talked at",
          esc(summary.mostTalkedAt.voterName) + " &rarr; " + esc(summary.mostTalkedAt.submitterName),
          pct(summary.mostTalkedAt.rate) + " of their tracks got a comment", false, summary.mostTalkedAt.tiedWith));
      }
      host.appendChild(g);
    }

    var box = el("div", "framed");
    box.insertAdjacentHTML("beforeend",
      '<div class="crow head"><div>Player</div><div class="num">Comments</div>' +
      '<div class="num">Rate</div><div class="num">Avg words</div>' +
      '<div class="num">Median</div><div class="num">Zero-pt</div>' +
      '<div class="num">!</div><div class="num">?</div><div class="num">CAPS</div></div>');
    rows.forEach(function (c) {
      box.insertAdjacentHTML("beforeend",
        '<div class="crow"><div class="vname">' + esc(c.name) + "</div>" +
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

    var words = rows.filter(function (c) { return c.distinctiveWord; });
    if (words.length) {
      var wbox = el("div", "framed cmt-words");
      wbox.appendChild(el("h3", null, "Words they reach for more than anyone else"));
      var list = el("div", "cmt-word-row");
      words.forEach(function (c) {
        list.insertAdjacentHTML("beforeend",
          '<span class="cmt-word" title="' + esc(c.name) + " used it " + c.distinctiveWord.uses +
          " times, " + c.distinctiveWord.vsLeague + '&times; the league\'s rate">' +
          esc(c.name) + ' <b>&ldquo;' + esc(c.distinctiveWord.word) + '&rdquo;</b> &times;' +
          c.distinctiveWord.uses + '</span>');
      });
      wbox.appendChild(list);
      host.appendChild(wbox);
    }

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
          '<div class="nrow"><div class="vname">' + esc(n.name) + "</div>" +
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
            esc(c.name) + " <b>" + top.map(esc).join(", ") + "</b></span>");
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
    Promise.all([fetchJSON(DATA + "/index.json"), fetchJSON(DATA + "/" + key + ".json")])
      .then(function (res) {
        var index = res[0], d = res[1];
        seasonData = d;
        selected = [];
        trendSelected = d.standings.map(function (p) { return p.id; });
        trendMode = "standing";
        renderNav(index, key);
        document.title = "PFML - " + d.label;
        initStandingsFold();
        renderHero(d);
        renderStandings(d);
        renderFocus(d);
        renderHighlights(d);
        renderTrend(d);
        renderTopTracks(d);
        renderRounds(d);
        renderTaste(d);
        renderVoters(d);
        renderComments(d);
        renderArtists(d);
        renderJumpNav(d);
        scrollToHash();
      })
      .catch(function (err) {
        console.error(err);
        var t = $("heroTitle");
        if (t) t.textContent = "PFML";
        var l = $("heroLine");
        if (l) { l.hidden = false; l.textContent = "Season data didn't load. Check that site/data/*.json was built and deployed next to this page."; }
      });
  }

  /* =====================================================================
     CAREER PAGE
     ===================================================================== */

  var careerData = null;
  var careerSort = { field: "careerScore", dir: "desc" };

  function careerTile(label, valueHtml, metaHtml, ties) {
    var n = el("div", "hl");
    n.innerHTML = '<p class="hl-label">' + label + "</p>" +
      '<div class="hl-value">' + valueHtml + "</div>" +
      (metaHtml ? '<div class="hl-meta">' + metaHtml + "</div>" : "") + tieLine(ties);
    return n;
  }

  function renderCareerComments(c) {
    var section = document.getElementById("block-comments");
    var host = $("comments");
    if (!host) return;
    host.innerHTML = "";
    var s = c.commentSummary || {};
    var rows = c.commenters || [];
    if (!rows.length || !s.totalComments) { if (section) section.hidden = true; return; }
    if (section) section.hidden = false;

    var g = el("div", "hl-grid");
    if (s.mostTalkative) {
      g.appendChild(careerTile("Most talkative", esc(s.mostTalkative.name),
        pct(s.mostTalkative.rate) + " of their votes carry a comment &middot; " +
        s.mostTalkative.comments + " comments", s.mostTalkative.tiedWith));
    }
    if (s.mostTerse) {
      g.appendChild(careerTile("Most terse", esc(s.mostTerse.name),
        s.mostTerse.meanWords + " words per comment across " + s.mostTerse.comments, s.mostTerse.tiedWith));
    }
    if (s.wordiest) {
      g.appendChild(careerTile("Wordiest", esc(s.wordiest.name),
        s.wordiest.meanWords + " words per comment", s.wordiest.tiedWith));
    }
    if (s.quietest) {
      g.appendChild(careerTile("Quietest", esc(s.quietest.name),
        pct(s.quietest.rate) + " of their votes carry a comment", s.quietest.tiedWith));
    }
    if (s.silentTreatment && s.silentTreatment.comments === 0) {
      g.appendChild(careerTile("Biggest silent treatment",
        esc(s.silentTreatment.voterName) + " &rarr; " + esc(s.silentTreatment.submitterName),
        "never once commented, across " + s.silentTreatment.chances + " chances to", s.silentTreatment.tiedWith));
    }
    if (s.loudest) {
      g.appendChild(careerTile("Most SHOUTING", esc(s.loudest.name),
        pct(s.loudest.rate) + " of their comments have an all-caps word", s.loudest.tiedWith));
    }
    if (s.richestVocab) {
      g.appendChild(careerTile("Widest vocabulary", esc(s.richestVocab.name),
        s.richestVocab.richness.toFixed(2) + " unique words per word over " +
        s.richestVocab.sampleWords + "-word samples", s.richestVocab.tiedWith));
    }
    if (s.mostZeroPoint) {
      g.appendChild(careerTile("Most all-talk", esc(s.mostZeroPoint.name),
        s.mostZeroPoint.count + " comments awarding zero points", s.mostZeroPoint.tiedWith));
    }
    if (s.mostSubmitterNotes) {
      g.appendChild(careerTile("Most notes on their own picks", esc(s.mostSubmitterNotes.name),
        s.mostSubmitterNotes.notes + " of " + s.mostSubmitterNotes.submissions + " submissions", s.mostSubmitterNotes.tiedWith));
    }
    host.appendChild(g);

    var box = el("div", "framed");
    box.insertAdjacentHTML("beforeend",
      '<div class="crow head"><div>Player</div><div class="num">Comments</div>' +
      '<div class="num">Rate</div><div class="num">Avg words</div>' +
      '<div class="num">Median</div><div class="num">Zero-pt</div>' +
      '<div class="num">!</div><div class="num">?</div><div class="num">CAPS</div></div>');
    rows.forEach(function (p) {
      box.insertAdjacentHTML("beforeend",
        '<div class="crow"><div class="vname">' + esc(p.name) + "</div>" +
        '<div class="num">' + p.comments + "</div>" +
        '<div class="num">' + pct(p.commentRate) + "</div>" +
        '<div class="num">' + p.meanWords + "</div>" +
        '<div class="num">' + p.medianWords + "</div>" +
        '<div class="num">' + p.zeroPointComments + "</div>" +
        '<div class="num">' + pct(p.exclamationRate) + "</div>" +
        '<div class="num">' + pct(p.questionRate) + "</div>" +
        '<div class="num">' + pct(p.allCapsRate) + "</div></div>");
    });
    host.appendChild(box);

    if (s.longestComment) {
      host.appendChild(commentQuote(s.longestComment, "Longest comment ever written"));
    }

    var words = rows.filter(function (p) { return p.distinctiveWord; });
    if (words.length) {
      var wbox = el("div", "framed cmt-words");
      wbox.appendChild(el("h3", null, "Words they reach for more than anyone else"));
      var list = el("div", "cmt-word-row");
      words.forEach(function (p) {
        list.insertAdjacentHTML("beforeend",
          '<span class="cmt-word" title="' + esc(p.name) + " used it " + p.distinctiveWord.uses +
          " times, " + p.distinctiveWord.vsLeague + '&times; the league\'s rate">' +
          esc(p.name) + ' <b>&ldquo;' + esc(p.distinctiveWord.word) + '&rdquo;</b> &times;' +
          p.distinctiveWord.uses + '</span>');
      });
      wbox.appendChild(list);
      host.appendChild(wbox);
    }

    host.insertAdjacentHTML("beforeend",
      '<p class="block-note cmt-foot">' + s.totalComments + " comments, " +
      s.totalWords.toLocaleString() + " words" +
      (s.submitterNoteCount ? ", " + s.submitterNoteCount + " submitter notes" : "") +
      ". Rates over fewer than " + s.minCommentsForRates +
      " comments are left out of the superlatives above.</p>");
  }

  function renderCareerHighlights(c) {
    var h = c.highlights || {};
    var g = el("div", "hl-grid");
    if (h.topScore) g.appendChild(careerTile("Highest career score", esc(h.topScore.name), h.topScore.careerScore + " career score", h.topScore.tiedWith));
    if (h.mostWins) g.appendChild(careerTile("Most rounds won", esc(h.mostWins.name), h.mostWins.roundsWon + " round wins", h.mostWins.tiedWith));
    if (h.mostPodiums) g.appendChild(careerTile("Most podiums", esc(h.mostPodiums.name), h.mostPodiums.podiums + " top-3 finishes", h.mostPodiums.tiedWith));
    if (h.bestSingleSeason) g.appendChild(careerTile("Best single season", esc(h.bestSingleSeason.name), h.bestSingleSeason.points + " points in " + esc(h.bestSingleSeason.season), h.bestSingleSeason.tiedWith));
    setBlock("highlights", g);
  }

  function careerColumns(c) {
    var cols = [{ key: "name", label: "Player", align: "left" }];
    c.seasons.forEach(function (s) { cols.push({ key: s.key, label: s.label.replace("Season ", "S") }); });
    cols.push({ key: "totalPoints", label: "Total" });
    cols.push({ key: "roundsWon", label: "Won" });
    cols.push({ key: "podiums", label: "Top-3" });
    cols.push({ key: "careerScore", label: "Score" });
    return cols;
  }

  function careerFieldValue(p, key) {
    if (key === "name") return p.name;
    if (key === "totalPoints") return p.totalPoints;
    if (key === "roundsWon") return p.roundsWon;
    if (key === "podiums") return p.podiums;
    if (key === "careerScore") return p.careerScore;
    return (key in p.bySeason) ? p.bySeason[key] : null;
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
    host.innerHTML = "";
    if (!c.players.length) { host.appendChild(empty("No completed seasons yet.")); return; }

    var cols = careerColumns(c);
    var gridStyle = "grid-template-columns:1.6fr repeat(" + (cols.length - 1) + ",1fr);";

    var head = el("div", "vrow head career-head");
    head.setAttribute("style", gridStyle);
    cols.forEach(function (col) {
      var active = careerSort.field === col.key;
      var b = el("button", "career-sort-btn" + (active ? " is-active" : "") + (col.align === "left" ? " is-left" : ""));
      b.type = "button";
      b.innerHTML = esc(col.label) + (active ? '<span class="arrow">' + (careerSort.dir === "asc" ? " \u2191" : " \u2193") + "</span>" : "");
      b.addEventListener("click", function () { setCareerSort(col.key); });
      head.appendChild(b);
    });
    var box = el("div", "framed career-table");
    box.appendChild(head);

    var sorted = sortCareerPlayers(c.players, careerSort.field, careerSort.dir);
    sorted.forEach(function (p, i) {
      var row = el("div", "vrow" + (i === 0 && careerSort.field === "careerScore" && careerSort.dir === "desc" ? " is-leader" : ""));
      row.setAttribute("style", gridStyle);
      var rowHtml = '<div class="vname">' + esc(p.name) + "</div>";
      c.seasons.forEach(function (s) {
        var pts = p.bySeason[s.key];
        rowHtml += '<div class="num">' + (pts == null ? "&ndash;" : pts) + "</div>";
      });
      rowHtml += '<div class="num">' + p.totalPoints + "</div><div class=\"num\">" + p.roundsWon +
        '</div><div class="num">' + p.podiums + '</div><div class="num"><b>' + p.careerScore + "</b></div>";
      row.innerHTML = rowHtml;
      box.appendChild(row);
    });
    host.appendChild(box);
  }

  function initCareer() {
    Promise.all([fetchJSON(DATA + "/index.json"), fetchJSON(DATA + "/career.json")])
      .then(function (res) {
        var index = res[0], c = res[1];
        careerData = c;
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
          note.textContent = "Total points across every season played, plus " + f.winBonus +
            " for every round won and " + f.podiumBonus + " for every top-3 finish (a win counts as both). " +
            "Click any column to sort by it.";
        }
        renderCareerStandings(c);
      })
      .catch(function (err) {
        console.error(err);
        var l = $("heroLine");
        if (l) l.textContent = "Career data didn't load. Check that site/data/career.json was built and deployed next to this page.";
      });
  }


  /* ---- round page (round.html?s=<season key>&r=<round id>) ---- */

  function initRound() {
    var params = new URLSearchParams(location.search);
    var key = params.get("s") || "";
    var roundId = params.get("r") || "";
    var page = $("roundPage");
    if (!/^season\d+$/.test(key)) {
      page.innerHTML = '<section class="shell rp-head"><h1>Round not found</h1><p class="hero-line">This link is missing its season. <a href="./">Back to the home page</a>.</p></section>';
      return;
    }
    Promise.all([fetchJSON(DATA + "/index.json"), fetchJSON(DATA + "/" + key + ".json")])
      .then(function (res) {
        renderNav(res[0], key);
        window.PFMLRounds.renderRoundPage(res[1], roundId);
      })
      .catch(function (err) {
        console.error(err);
        page.innerHTML = '<section class="shell rp-head"><h1>Couldn’t load this round</h1><p class="hero-line">' + esc(err.message || err) + "</p></section>";
      });
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
    }
  }

  // Wait for auth.js to let a member in before touching any data.
  if (window.PFML && window.PFML.ready) window.PFML.ready.then(boot);
  else boot();
})();
