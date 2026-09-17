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
      var a = el("a", "pill");
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

  function renderStandings(d) {
    if (!d.standings.length) { setBlock("standings", empty("No submissions yet. Standings appear once the first round closes.")); return; }
    var max = Math.max.apply(null, d.standings.map(function (p) { return p.points; }).concat([1]));
    var box = el("div", "framed");
    d.standings.forEach(function (p, i) {
      var pct = Math.max(3, Math.round((p.points / max) * 100));
      var row = el("div", "stand-row");
      row.innerHTML =
        '<div class="stand-rank">' + (i + 1) + "</div>" +
        '<div><div class="stand-name">' + esc(p.name) + "</div>" +
        '<div class="bar"><i style="width:' + pct + '%"></i></div></div>' +
        '<div class="stand-score"><b>' + p.points + "</b><span>" +
        p.avgPerSubmission + " avg &middot; " + p.roundsWon + " won &middot; " + p.podiums + " top-3</span></div>";
      box.appendChild(row);
    });
    setBlock("standings", box);
  }

  function tile(label, valueHtml, metaHtml, big) {
    var n = el("div", "hl");
    n.innerHTML = '<p class="hl-label">' + label + "</p>" +
      '<div class="hl-value' + (big ? " hl-big" : "") + '">' + valueHtml + "</div>" +
      (metaHtml ? '<div class="hl-meta">' + metaHtml + "</div>" : "");
    return n;
  }

  function renderHighlights(d) {
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

  function trackRow(s, pos, showRound) {
    var row = el("div", "trk");
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

  function renderTopTracks(d) {
    var all = [];
    d.rounds.forEach(function (r) { all = all.concat(r.songs); });
    if (!all.length) { setBlock("topTracks", empty("No tracks submitted yet.")); return; }
    var top = all.slice().sort(function (a, b) { return b.points - a.points; }).slice(0, 20);
    var box = el("div", "framed");
    top.forEach(function (s, i) { box.appendChild(trackRow(s, i + 1, true)); });
    setBlock("topTracks", box);
  }

  function renderRounds(d) {
    if (!d.rounds.length) { setBlock("rounds", empty("No rounds posted yet this season.")); return; }
    var wrap = el("div", "rounds-list");
    d.rounds.slice().reverse().forEach(function (r) {
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
      r.songs.forEach(function (s, i) { list.appendChild(trackRow(s, s.place || i + 1, false)); });
      body.appendChild(list);
      det.appendChild(body);
      wrap.appendChild(det);
    });
    setBlock("rounds", wrap);
  }

  function renderTaste(d) {
    var note = $("tasteNote");
    if (!d.taste.length) {
      if (note) note.textContent = "";
      setBlock("taste", empty("Needs a few rounds of voting history before this says anything."));
      return;
    }
    if (note) note.textContent =
      "Read a row as: this voter sends that submitter this much of their points, relative to spreading points evenly across every track they saw. " +
      "1.00 is neutral, 2.00 is twice their usual share, 0.50 is half. Self-votes are excluded, and a pair needs at least five chances to vote before it shows.";

    var people = d.competitors;
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

    var host = $("taste");
    host.innerHTML = "";
    host.appendChild(scroll);
    host.insertAdjacentHTML("beforeend",
      '<div class="legend"><span>' + lo.toFixed(2) + '</span><span class="ramp"></span><span>' + hi.toFixed(2) +
      "</span><span>darker means a bigger share of that voter's points</span></div>");
  }

  function renderVoters(d) {
    if (!d.voters.length) { setBlock("voters", empty("No votes cast yet.")); return; }
    var box = el("div", "framed");
    box.insertAdjacentHTML("beforeend",
      '<div class="vrow head"><div>Player</div><div class="num">Top bet</div><div class="num">Tracks backed</div><div class="num">Top pick won</div></div>');
    d.voters.forEach(function (v) {
      box.insertAdjacentHTML("beforeend",
        '<div class="vrow"><div class="vname">' + esc(v.name) + "</div>" +
        '<div class="num">' + v.avgTopBet.toFixed(1) + "</div>" +
        '<div class="num">' + v.avgTracksBacked.toFixed(1) + "</div>" +
        '<div class="num">' + Math.round(v.kingmakerRate * 100) + "%</div></div>");
    });
    setBlock("voters", box);
  }

  function renderArtists(d) {
    var list = (d.highlights && d.highlights.repeatArtists) || [];
    if (!list.length) { setBlock("artists", empty("No artist has been submitted more than once yet.")); return; }
    var g = el("div", "art-grid");
    list.forEach(function (a) {
      g.insertAdjacentHTML("beforeend",
        '<a class="art" href="' + esc(searchLink(a.name)) + '" target="_blank" rel="noopener">' + esc(a.name) + " <b>&times;" + a.count + "</b></a>");
    });
    setBlock("artists", g);
  }

  function initSeason(key) {
    Promise.all([fetchJSON(DATA + "/index.json"), fetchJSON(DATA + "/" + key + ".json")])
      .then(function (res) {
        var index = res[0], d = res[1];
        renderNav(index, key);
        document.title = "PFML - " + d.label;
        renderHero(d);
        renderStandings(d);
        renderHighlights(d);
        renderTopTracks(d);
        renderRounds(d);
        renderTaste(d);
        renderVoters(d);
        renderArtists(d);
      })
      .catch(function (err) {
        console.error(err);
        var t = $("heroTitle");
        if (t) t.textContent = "PFML";
        var l = $("heroLine");
        if (l) l.textContent = "Season data didn't load. Check that site/data/*.json was built and deployed next to this page.";
      });
  }

  /* ---- boot ---- */

  var page = document.body.getAttribute("data-page");
  if (page === "home") {
    initHome();
  } else if (page === "season") {
    initSeason(document.body.getAttribute("data-season-key"));
  }
})();
