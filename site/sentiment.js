/* ==========================================================
   PFML - Estimated League Sentiment

   How much will the league care that a track repeats something already
   submitted? A gauge from green (nobody minds) to red (they'll care),
   with the reasons: which kind of repeat it is, and where the earlier one
   was. Used on the repeat checker and the Submit page, for a track picked
   from search (title, artists and album known) or a Spotify link.

   The weights below are the user's call (2026-10-19) and are not shown on
   the site: members see the gauge, the verdict and the reasons, never the
   numbers. README, Repeat checker, has the reasoning.

   Compares against catalog.json (every track from every finished round)
   and index.json (which season is the current one).
   ========================================================== */

(function () {
  "use strict";

  // now: the earlier one was in the current season; past: an earlier season
  var RULES = {
    exact:        { now: 100, past: 100, says: "This exact recording has been submitted before" },
    version:      { now: 95, past: 90, says: "The same song by the same artist, in another version" },
    cover:        { now: 90, past: 80, says: "The same song by a different artist" },
    sameTitle:    { now: 50, past: 30, says: "A different artist’s song with the same one-word title (it may be a different song)" },
    artistAlbum:  { now: 85, past: 30, says: "The same artist, from the same album" },
    artistTwice:  { now: 85, past: 0, says: "An artist already submitted twice or more this season" },
    artistLast:   { now: 85, past: 0, says: "The same artist as the last round" },
    artist:       { now: 75, past: 20, says: "The same artist" },
    featured:     { now: 45, past: 10, says: "An artist who was a featured guest on one of them" }
  };

  // the verdict, from the highest weight among the reasons
  var LEVELS = [
    { min: 100, key: "exact", label: "Exact repeat" },
    { min: 90, key: "red", label: "The league will care" },
    { min: 75, key: "orange", label: "Expect some grumbling" },
    { min: 50, key: "amber", label: "People will notice" },
    { min: 25, key: "yellow", label: "A few might notice" },
    { min: 1, key: "lime", label: "Barely a blip" },
    { min: 0, key: "green", label: "Fresh: nothing like it before" }
  ];

  function fold(s) {
    return String(s == null ? "" : s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
      .replace(/&/g, " and ").replace(/[^a-z0-9]+/g, " ").trim();
  }

  // the song without the labels a service adds (" - 2011 Remaster", "(Live)",
  // "(feat. X)"), so versions of one song compare equal
  function songKey(title) {
    return fold(String(title || "").replace(/\s[-–—]\s.*$/, "").replace(/[\(\[][^\)\]]*[\)\]]/g, " "));
  }

  // Music League's export splits artists at commas, so "Earth, Wind & Fire"
  // arrives as "Earth" and "Wind & Fire". Every run of neighbouring pieces
  // counts as a name; the runs from the first piece are the lead artist.
  function names(pieces) {
    var all = {}, lead = {};
    for (var i = 0; i < pieces.length; i++) {
      for (var j = i; j < pieces.length && j < i + 4; j++) {
        var n = fold(pieces.slice(i, j + 1).join(", "));
        if (!n) continue;
        all[n] = true;
        if (i === 0) lead[n] = true;
      }
    }
    return { all: all, lead: lead };
  }

  var data = null;

  function load() {
    if (data) return Promise.resolve(data);
    return Promise.all([PFML.loadJSON("catalog.json"), PFML.loadJSON("index.json")]).then(function (res) {
      var cat = res[0], current = res[1].currentSeason;
      var lastRound = -1;
      cat.rounds.forEach(function (r, i) { if (r.season === current) lastRound = i; });
      data = {
        rounds: cat.rounds,
        lastRound: lastRound,
        current: current,
        tracks: cat.tracks.map(function (t) {
          return { t: t, song: songKey(t.title), album: fold(t.album), names: names(t.artists),
                   now: cat.rounds[t.round].season === current };
        })
      };
      return data;
    });
  }

  // The strongest kind of repeat between the picked track and one earlier
  // submission, or null.
  function kind(pick, p) {
    if (pick.spotifyId && pick.spotifyId === p.t.spotifyId) return "exact";
    var leadSame = Object.keys(pick.names.lead).some(function (n) { return p.names.lead[n]; });
    var shared = Object.keys(pick.names.all).some(function (n) { return p.names.all[n]; });
    if (pick.song && pick.song === p.song) {
      if (shared) return "version";
      return pick.song.indexOf(" ") === -1 ? "sameTitle" : "cover";
    }
    if (leadSame && pick.album && pick.album === p.album) return "artistAlbum";
    if (leadSame) return "artist";
    if (shared) return "featured";
    return null;
  }

  // pick: {spotifyId?, title, artists: [names or pieces], album?}. The
  // search answers with artists as one "A, B" line, which may split a name
  // that has a comma in it, so the picked track is read the same way as
  // the catalog: any run of neighbouring pieces is a name.
  function judge(pick) {
    var d = data;
    var me = {
      spotifyId: pick.spotifyId || "",
      song: songKey(pick.title),
      album: fold(pick.album),
      names: names(pick.artists || [])
    };
    var found = {};        // rule -> {weight, matches}
    function add(rule, when, p) {
      var w = RULES[rule][when];
      var f = found[rule] || (found[rule] = { rule: rule, weight: 0, matches: [] });
      f.weight = Math.max(f.weight, w);
      if (p) f.matches.push(p);
    }
    var leadThisSeason = 0, inLastRound = false;
    d.tracks.forEach(function (p) {
      var k = kind(me, p);
      if (!k) return;
      add(k, p.now ? "now" : "past", p);
      if ((k === "artist" || k === "artistAlbum" || k === "version" || k === "exact") && p.now) {
        leadThisSeason += 1;
        if (p.t.round === d.lastRound) inLastRound = true;
      }
    });
    if (leadThisSeason >= 2) add("artistTwice", "now", null);
    if (inLastRound) add("artistLast", "now", null);

    var reasons = Object.keys(found).map(function (k) { return found[k]; })
      .sort(function (a, b) { return b.weight - a.weight; });
    var score = reasons.length ? reasons[0].weight : 0;
    var level = LEVELS.filter(function (l) { return score >= l.min; })[0];
    return { score: score, level: level, reasons: reasons, exact: !!found.exact };
  }

  /* ---- the gauge ---- */

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function where(p) {
    var r = data.rounds[p.t.round];
    return '<a href="round?s=' + encodeURIComponent(r.season) + "&amp;r=" + encodeURIComponent(r.id) + '">' +
      esc(r.seasonLabel) + " · Round " + r.number + ": " + esc(r.name) + "</a> (" + esc(p.t.title) + ", by " + esc(p.t.submitterName) + ")";
  }

  var gradients = 0;

  // A half-dial, green on the left to red on the right, with a needle. The
  // score itself is never printed.
  function gaugeHtml(result) {
    var id = "sgGrad" + (++gradients);
    var a = Math.PI * (1 - Math.min(100, result.score) / 100);
    var x = (100 + 74 * Math.cos(a)).toFixed(1), y = (100 - 74 * Math.sin(a)).toFixed(1);
    var html =
      '<div class="sg sg-' + result.level.key + '">' +
        '<p class="sg-kicker">Estimated League Sentiment</p>' +
        '<svg class="sg-dial" viewBox="0 0 200 112" role="img" aria-label="Estimated League Sentiment: ' + esc(result.level.label) + '">' +
          '<defs><linearGradient id="' + id + '" x1="0" x2="1" y1="0" y2="0">' +
            '<stop offset="0" stop-color="#2E9E44"/><stop offset="0.45" stop-color="#E3B12C"/><stop offset="1" stop-color="#C62828"/>' +
          "</linearGradient></defs>" +
          '<path d="M14 100 A86 86 0 0 1 186 100" fill="none" stroke="url(#' + id + ')" stroke-width="16" stroke-linecap="round"/>' +
          '<line x1="100" y1="100" x2="' + x + '" y2="' + y + '" class="sg-needle"/>' +
          '<circle cx="100" cy="100" r="7" class="sg-hub"/>' +
        "</svg>" +
        '<p class="sg-label">' + esc(result.level.label) + "</p>";
    if (result.exact) {
      html += '<p class="sg-warning"><b>Exact repeat.</b> This very recording has been in a round already; ' +
        "the league will spot it straight away.</p>";
    }
    if (result.reasons.length) {
      html += '<ul class="sg-reasons">' + result.reasons.map(function (r) {
        var when = r.matches.length ? r.matches.some(function (p) { return p.now; }) ? " (this season)" : " (an earlier season)" : "";
        var list = r.matches.slice().sort(function (a, b) { return b.t.round - a.t.round; }).slice(0, 3).map(where).join("; ");
        var more = r.matches.length > 3 ? " and " + (r.matches.length - 3) + " more" : "";
        return "<li><b>" + esc(RULES[r.rule].says) + when + "</b>" + (list ? "<span>" + list + more + "</span>" : "") + "</li>";
      }).join("") + "</ul>";
    }
    return html + "</div>";
  }

  // A Spotify track the catalog already has, as a pick (for a pasted link,
  // where nothing else says what the track is), or null. After load().
  function known(spotifyId) {
    var hit = data && data.tracks.filter(function (p) { return p.t.spotifyId === spotifyId; })[0];
    return hit ? { spotifyId: spotifyId, title: hit.t.title, artists: hit.t.artists, album: hit.t.album } : null;
  }

  window.PFMLSentiment = { load: load, judge: judge, gaugeHtml: gaugeHtml, known: known };
})();
