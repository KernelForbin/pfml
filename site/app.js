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
  }

  var JUMP_SECTIONS = [
    ["block-standings", "Standings"],
    ["block-highlights", "Numbers"],
    ["block-trend", "Trend"],
    ["block-tracks", "Tracks"],
    ["block-rounds", "Rounds"],
    ["block-taste", "Taste"],
    ["block-voters", "Voting"],
    ["block-artists", "Artists"],
  ];

  function renderJumpNav(d) {
    var nav = $("jumpNav");
    if (!nav) return;
    nav.innerHTML = "";
    if (!d.rounds.length) { nav.hidden = true; return; }
    nav.hidden = false;
    JUMP_SECTIONS.forEach(function (pair) {
      var id = pair[0], label = pair[1];
      var section = document.getElementById(id);
      if (!section || section.hidden) return;
      var a = el("a", "jump-link", esc(label));
      a.href = "#" + id;
      nav.appendChild(a);
    });
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
      var label = isLive ? "Leading" : "Winner";
      leaderHtml = '<div class="season-card-leader"><span class="lbl">' + label + '</span>' +
        '<div class="val">' + esc(s.leaderName) + ' <span class="pts">' + s.leaderPoints + ' pts</span></div></div>';
    }

    a.innerHTML =
      '<div class="season-card-top">' + nameHtml + '<span class="season-card-arrow">&rarr;</span></div>' +
      '<div class="season-card-stats">' + statLine + "</div>" + roundLine + startedLine + leaderHtml;
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
    renderTopTracks(seasonData);
    renderRounds(seasonData);
    renderTaste(seasonData);
    renderVoters(seasonData);
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

  /* ---- standings (clickable) ---- */

  function renderStandings(d) {
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
        '<div class="stand-rank">' + (i + 1) + "</div>" +
        '<div><div class="stand-name">' + esc(p.name) + "</div>" +
        '<div class="bar"><i style="width:' + pct + '%"></i></div></div>' +
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

    var rank = d.standings.indexOf(standing) + 1;
    var songs = songsBy(d, id);
    var g = el("div", "hl-grid");

    g.appendChild(tile("Season standing", "#" + rank + " of " + d.standings.length,
      standing.points + " points &middot; " + standing.roundsWon + " round" + (standing.roundsWon === 1 ? "" : "s") +
      " won &middot; " + standing.podiums + " top-3 finishes"));

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
        var overallRank = d.standings.indexOf(r.standing) + 1;
        var pct = Math.max(3, Math.round((r.standing.points / max) * 100));
        row.innerHTML =
          '<div class="stand-rank">#' + overallRank + "</div>" +
          '<div><div class="stand-name">' + esc(r.name) + "</div>" +
          '<div class="bar"><i style="width:' + pct + '%"></i></div></div>' +
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

  function tile(label, valueHtml, metaHtml, big) {
    var n = el("div", "hl");
    n.innerHTML = '<p class="hl-label">' + label + "</p>" +
      '<div class="hl-value' + (big ? " hl-big" : "") + '">' + valueHtml + "</div>" +
      (metaHtml ? '<div class="hl-meta">' + metaHtml + "</div>" : "");
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
        " points &middot; " + esc(h.topTrack.roundName)));
    }
    if (h.divisiveTrack) {
      g.appendChild(tile("Most divisive track", extLink(trackLink(h.divisiveTrack.spotifyId), h.divisiveTrack.title),
        esc(h.divisiveTrack.artistText) + "<br>widest spread between voters who backed it (&sigma; " +
        h.divisiveTrack.spread + "), from " + esc(h.divisiveTrack.submitterName)));
    }
    if (h.closestRound) {
      g.appendChild(tile("Closest round", esc(h.closestRound.name),
        h.closestRound.margin === 0 ? "ended in a tie at the top" : "won by " + h.closestRound.margin + " " + plural(h.closestRound.margin, "point")));
    }
    if (h.blowoutRound) {
      g.appendChild(tile("Biggest blowout", esc(h.blowoutRound.name),
        esc(h.blowoutRound.winner) + " won by " + h.blowoutRound.margin + " points with " + esc(h.blowoutRound.title)));
    }
    if (h.biggestFan) {
      g.appendChild(tile("Biggest fan", esc(h.biggestFan.voterName) + " &rarr; " + esc(h.biggestFan.submitterName),
        "sends " + h.biggestFan.index + "&times; their baseline share of points that way"));
    }
    if (h.coldestShoulder) {
      g.appendChild(tile("Coldest shoulder", esc(h.coldestShoulder.voterName) + " &rarr; " + esc(h.coldestShoulder.submitterName),
        "only " + h.coldestShoulder.index + "&times; their baseline share"));
    }
    if (h.boldestVoter) {
      g.appendChild(tile("Boldest voter", esc(h.boldestVoter.name),
        "biggest single bet averages " + h.boldestVoter.avgTopBet + " points, spread over just " + h.boldestVoter.avgTracksBacked + " tracks a round"));
    }
    if (h.hedgiestVoter) {
      g.appendChild(tile("Widest spreader", esc(h.hedgiestVoter.name),
        "backs " + h.hedgiestVoter.avgTracksBacked + " tracks a round, top bet averages only " + h.hedgiestVoter.avgTopBet));
    }
    if (h.bestTastemaker) {
      g.appendChild(tile("Best read on the room", esc(h.bestTastemaker.name),
        "their top pick won the round " + Math.round(h.bestTastemaker.kingmakerRate * 100) + "% of the time (" +
        h.bestTastemaker.kingmakerHits + " of " + h.bestTastemaker.kingmakerRounds + ")"));
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

  function trendColor(i) {
    var hue = (i * 137.508) % 360;
    return "hsl(" + hue.toFixed(1) + ", 68%, 42%)";
  }

  function computeTrendSeries(d) {
    // one entry per player who has a standings entry (submitted at least
    // once), ordered by final season points so color/legend order is
    // stable regardless of what's currently toggled on
    var ids = d.standings.map(function (p) { return p.id; });
    var cum = {};
    ids.forEach(function (id) { cum[id] = 0; });
    var series = {};
    ids.forEach(function (id) { series[id] = []; });

    d.rounds.forEach(function (r) {
      var earned = {};
      r.songs.forEach(function (s) { earned[s.submitterId] = (earned[s.submitterId] || 0) + s.points; });
      ids.forEach(function (id) {
        cum[id] += earned[id] || 0;
        series[id].push(cum[id]);
      });
    });

    return ids.map(function (id, i) {
      return { id: id, name: nameOf(d, id), color: trendColor(i), points: series[id] };
    });
  }

  function toggleTrend(id) {
    var i = trendSelected.indexOf(id);
    if (i === -1) trendSelected.push(id); else trendSelected.splice(i, 1);
    renderTrend(seasonData);
  }

  function buildLineChartSVG(series, roundCount) {
    var W = 760, H = 320, padL = 44, padR = 16, padT = 16, padB = 30;
    var plotW = W - padL - padR, plotH = H - padT - padB;

    var allVals = [0];
    series.forEach(function (s) { s.points.forEach(function (v) { allVals.push(v); }); });
    var lo = Math.min.apply(null, allVals), hi = Math.max.apply(null, allVals);
    if (lo === hi) { hi = lo + 1; }
    var pad = (hi - lo) * 0.08;
    lo -= pad; hi += pad;

    function x(i) { return padL + (roundCount <= 1 ? 0 : (i / (roundCount - 1)) * plotW); }
    function y(v) { return padT + plotH - ((v - lo) / (hi - lo)) * plotH; }

    var svg = '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Cumulative points by round">';

    // gridlines + y labels
    var ticks = 4;
    for (var t = 0; t <= ticks; t++) {
      var val = lo + (hi - lo) * (t / ticks);
      var yy = y(val);
      svg += '<line x1="' + padL + '" x2="' + (W - padR) + '" y1="' + yy.toFixed(1) + '" y2="' + yy.toFixed(1) + '" class="chart-grid" />';
      svg += '<text x="' + (padL - 8) + '" y="' + (yy + 4).toFixed(1) + '" class="chart-axis-y" text-anchor="end">' + Math.round(val) + "</text>";
    }

    // x labels
    var xStep = roundCount > 14 ? 2 : 1;
    for (var i = 0; i < roundCount; i += xStep) {
      svg += '<text x="' + x(i).toFixed(1) + '" y="' + (H - 8) + '" class="chart-axis-x" text-anchor="middle">' + (i + 1) + "</text>";
    }

    series.forEach(function (s) {
      var pts = s.points.map(function (v, i) { return x(i).toFixed(1) + "," + y(v).toFixed(1); }).join(" ");
      svg += '<polyline points="' + pts + '" fill="none" stroke="' + s.color + '" stroke-width="2.5" ' +
        'stroke-linejoin="round" stroke-linecap="round"><title>' + esc(s.name) + ": " +
        s.points[s.points.length - 1] + " pts</title></polyline>";
      var lastI = s.points.length - 1;
      svg += '<circle cx="' + x(lastI).toFixed(1) + '" cy="' + y(s.points[lastI]).toFixed(1) + '" r="3.5" fill="' + s.color + '" />';
    });

    svg += "</svg>";
    return svg;
  }

  function renderTrend(d) {
    var section = document.getElementById("block-trend");
    if (!d.rounds.length || !d.standings.length) { if (section) section.hidden = true; return; }
    if (section) section.hidden = false;

    var all = computeTrendSeries(d);

    var legend = $("trendLegend");
    legend.innerHTML = "";
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
    chartHost.innerHTML = '<div class="chart-frame">' + buildLineChartSVG(shown, d.rounds.length) + "</div>";
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
      '<div class="trk-body"><div class="trk-title">' + extLink(trackLink(s.spotifyId), s.title) + "</div>" +
      '<div class="trk-meta">' + meta + "</div></div>" +
      '<div class="trk-pts">' + s.points + " <small>pts</small></div>";
    return row;
  }

  var trackSort = "points-desc";
  var TRACK_SORTS = [
    ["points-desc", "Top scoring"],
    ["points-asc", "Lowest scoring"],
    ["az", "A\u2013Z"],
    ["recent", "Most recent"],
  ];

  function renderTracksSort() {
    var host = $("tracksSort");
    if (!host) return;
    host.innerHTML = "";
    TRACK_SORTS.forEach(function (pair) {
      var mode = pair[0], label = pair[1];
      var b = el("button", "sort-pill" + (trackSort === mode ? " is-active" : ""), esc(label));
      b.type = "button";
      b.addEventListener("click", function () {
        if (trackSort === mode) return;
        trackSort = mode;
        renderTracksSort();
        renderTopTracks(seasonData);
      });
      host.appendChild(b);
    });
  }

  function renderTopTracks(d) {
    var all = [];
    d.rounds.forEach(function (r, ri) { r.songs.forEach(function (s) { all.push(s); s.__roundIndex = ri; }); });
    if (selected.length) {
      var idSet = {};
      selected.forEach(function (id) { idSet[id] = true; });
      all = all.filter(function (s) { return idSet[s.submitterId]; });
    }
    var host = $("topTracks");
    host.innerHTML = "";
    attachFilterTag(host, seasonData);
    if (!all.length) { host.appendChild(empty(selected.length ? "No tracks from this selection." : "No tracks submitted yet.")); return; }

    var list = all.slice();
    var capped = true;
    if (trackSort === "points-desc") {
      list.sort(function (a, b) { return b.points - a.points; });
    } else if (trackSort === "points-asc") {
      list.sort(function (a, b) { return a.points - b.points; });
    } else if (trackSort === "az") {
      list.sort(function (a, b) { return a.title.localeCompare(b.title); });
      capped = false;
    } else if (trackSort === "recent") {
      list.sort(function (a, b) { return b.__roundIndex - a.__roundIndex || b.points - a.points; });
      capped = false;
    }
    var shown = capped ? list.slice(0, 20) : list;

    var note = el("p", "block-note",
      capped ? "Showing " + shown.length + " of " + list.length + " tracks." : "Showing all " + list.length + " tracks.");
    host.appendChild(note);
    var box = el("div", "framed");
    shown.forEach(function (s, i) { box.appendChild(trackRow(s, i + 1, true)); });
    host.appendChild(box);
  }

  function renderRounds(d) {
    var host = $("rounds");
    host.innerHTML = "";
    attachFilterTag(host, seasonData);

    var idSet = null;
    if (selected.length) { idSet = {}; selected.forEach(function (id) { idSet[id] = true; }); }
    var rounds = d.rounds;
    if (idSet) rounds = rounds.filter(function (r) { return r.songs.some(function (s) { return idSet[s.submitterId]; }); });

    if (!d.rounds.length) { host.appendChild(empty("No rounds posted yet this season.")); return; }
    if (!rounds.length) { host.appendChild(empty("No rounds involve this selection.")); return; }

    var wrap = el("div", "rounds-list");
    rounds.slice().reverse().forEach(function (r) {
      var det = el("details", "round");
      var win = r.songs[0];
      var sum = el("summary");
      sum.innerHTML =
        '<span><span class="round-title">' + esc(r.name) + "</span>" +
        (win ? ' <span class="round-sub">&mdash; <b>' + esc(win.submitterName) + "</b> took it with " + esc(win.title) + "</span>" : "") + "</span>" +
        '<span class="round-open">' + r.songs.length + " " + plural(r.songs.length, "track") + " &darr;</span>";
      det.appendChild(sum);

      var body = el("div", "round-body");
      var bodyHtml = "";
      if (r.description) bodyHtml += '<p class="round-desc">' + esc(r.description) + "</p>";
      body.innerHTML = bodyHtml;
      if (r.playlistUrl) {
        body.insertAdjacentHTML("beforeend",
          '<a class="pill" href="' + esc(r.playlistUrl) + '" target="_blank" rel="noopener">Open the round playlist &nearr;</a>');
      }
      var list = el("div", "inner-list");
      r.songs.forEach(function (s, i) { list.appendChild(trackRow(s, s.place || i + 1, false, idSet)); });
      body.appendChild(list);
      det.appendChild(body);
      wrap.appendChild(det);
    });
    host.appendChild(wrap);
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

  function renderHero(d) {
    $("heroTitle").textContent = d.label;
    var h = d.highlights || {};
    var rounds = d.rounds.length;

    $("heroLine").textContent = rounds
      ? rounds + " " + plural(rounds, "round") + ", " + d.songCount + " tracks, " +
        d.scoringVoteCount + " scoring votes from " + d.competitors.length + " players."
      : d.competitors.length + " players are signed up. No rounds have been posted yet, so the boards below fill in as results come through.";

    var stats = [
      ["Rounds", rounds],
      ["Tracks", d.songCount],
      ["Players", d.competitors.length],
      ["Artists", h.uniqueArtists || 0],
      ["Scoring votes", h.scoringVotes || 0],
    ];
    var dl = $("scoreline");
    dl.innerHTML = "";
    stats.forEach(function (s) {
      var wrap = el("div");
      wrap.appendChild(el("dt", null, esc(s[0])));
      wrap.appendChild(el("dd", null, esc(s[1])));
      dl.appendChild(wrap);
    });
  }

  function initSeason(key) {
    Promise.all([fetchJSON(DATA + "/index.json"), fetchJSON(DATA + "/" + key + ".json")])
      .then(function (res) {
        var index = res[0], d = res[1];
        seasonData = d;
        selected = [];
        trendSelected = d.standings.slice(0, 3).map(function (p) { return p.id; });
        trackSort = "points-desc";
        renderNav(index, key);
        document.title = "PFML - " + d.label;
        renderHero(d);
        renderStandings(d);
        renderFocus(d);
        renderHighlights(d);
        renderTrend(d);
        renderTracksSort();
        renderTopTracks(d);
        renderRounds(d);
        renderTaste(d);
        renderVoters(d);
        renderArtists(d);
        renderJumpNav(d);
      })
      .catch(function (err) {
        console.error(err);
        var t = $("heroTitle");
        if (t) t.textContent = "PFML";
        var l = $("heroLine");
        if (l) l.textContent = "Season data didn't load. Check that site/data/*.json was built and deployed next to this page.";
      });
  }

  /* =====================================================================
     CAREER PAGE
     ===================================================================== */

  function careerTile(label, valueHtml, metaHtml) {
    var n = el("div", "hl");
    n.innerHTML = '<p class="hl-label">' + label + "</p>" +
      '<div class="hl-value">' + valueHtml + "</div>" +
      (metaHtml ? '<div class="hl-meta">' + metaHtml + "</div>" : "");
    return n;
  }

  function renderCareerHighlights(c) {
    var h = c.highlights || {};
    var g = el("div", "hl-grid");
    if (h.mostPoints) g.appendChild(careerTile("Most career points", esc(h.mostPoints.name), h.mostPoints.points + " points total"));
    if (h.mostWins) g.appendChild(careerTile("Most rounds won", esc(h.mostWins.name), h.mostWins.roundsWon + " round wins"));
    if (h.mostPodiums) g.appendChild(careerTile("Most podiums", esc(h.mostPodiums.name), h.mostPodiums.podiums + " top-3 finishes"));
    if (h.mostSeasons) g.appendChild(careerTile("Most seasons played", esc(h.mostSeasons.name), h.mostSeasons.seasonsPlayed + " seasons"));
    if (h.bestSingleSeason) g.appendChild(careerTile("Best single season", esc(h.bestSingleSeason.name), h.bestSingleSeason.points + " points in " + esc(h.bestSingleSeason.season)));
    setBlock("highlights", g);
  }

  function renderCareerStandings(c) {
    var host = $("standings");
    host.innerHTML = "";
    if (!c.players.length) { host.appendChild(empty("No completed seasons yet.")); return; }

    var colCount = c.seasons.length + 3; // seasons + total + won + top-3
    var gridStyle = "grid-template-columns:1.6fr repeat(" + colCount + ",1fr);";

    var head = el("div", "vrow head");
    head.setAttribute("style", gridStyle);
    var headHtml = "<div>Player</div>";
    c.seasons.forEach(function (s) { headHtml += '<div class="num">' + esc(s.label.replace("Season ", "S")) + "</div>"; });
    headHtml += '<div class="num">Total</div><div class="num">Won</div><div class="num">Top-3</div>';
    head.innerHTML = headHtml;
    var box = el("div", "framed career-table");
    box.appendChild(head);

    c.players.forEach(function (p, i) {
      var row = el("div", "vrow" + (i === 0 ? " is-leader" : ""));
      row.setAttribute("style", gridStyle);
      var rowHtml = '<div class="vname">' + (i + 1) + ". " + esc(p.name) + "</div>";
      c.seasons.forEach(function (s) {
        var pts = p.bySeason[s.key];
        rowHtml += '<div class="num">' + (pts == null ? "&ndash;" : pts) + "</div>";
      });
      rowHtml += '<div class="num"><b>' + p.totalPoints + "</b></div><div class=\"num\">" + p.roundsWon +
        '</div><div class="num">' + p.podiums + "</div>";
      row.innerHTML = rowHtml;
      box.appendChild(row);
    });
    host.appendChild(box);
  }

  function initCareer() {
    Promise.all([fetchJSON(DATA + "/index.json"), fetchJSON(DATA + "/career.json")])
      .then(function (res) {
        var index = res[0], c = res[1];
        renderNav(index, "career");
        var line = c.seasons.length
          ? "Combined standings across " + c.seasons.length + " played " + plural(c.seasons.length, "season") + ": " +
            c.seasons.map(function (s) { return s.label; }).join(", ") + "."
          : "No seasons have finished a round yet.";
        $("heroLine").textContent = line;
        renderCareerHighlights(c);
        renderCareerStandings(c);
      })
      .catch(function (err) {
        console.error(err);
        var l = $("heroLine");
        if (l) l.textContent = "Career data didn't load. Check that site/data/career.json was built and deployed next to this page.";
      });
  }

  /* ---- boot ---- */

  var page = document.body.getAttribute("data-page");
  if (page === "home") {
    initHome();
  } else if (page === "season") {
    initSeason(document.body.getAttribute("data-season-key"));
  } else if (page === "career") {
    initCareer();
  }
})();
