/* ==========================================================
   PFML - the repeat checker (/repeats)

   Has an artist, song or album been submitted before? Searches every
   track from every finished round (catalog.json, built by
   scripts/build.py), on the device, as you type. Also takes a Spotify
   track link, for "this exact recording". README, Repeat checker.
   ========================================================== */

(function () {
  "use strict";

  function $(id) { return document.getElementById(id); }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* ---- comparing text ---- */

  // lower case, accents off, & as "and", punctuation as spaces
  function fold(s) {
    return String(s == null ? "" : s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
      .replace(/&/g, " and ").replace(/[^a-z0-9]+/g, " ").trim();
  }

  function words(s) { return fold(s).split(" ").filter(Boolean); }

  // The song itself, without the labels a service adds: "Shining Star -
  // 2011 Remaster" and "Distant Lover (Live)" are Shining Star and Distant
  // Lover, so a repeat of the song shows whichever version it was.
  function songOf(title) {
    return String(title || "").replace(/\s[-–—]\s.*$/, "").replace(/[\(\[][^\)\]]*[\)\]]/g, " ");
  }

  // Every query word starts some word of the field, so "osk" finds
  // Lee Oskar and "feelin happy" finds Feelin' Happy.
  function matches(fieldWords, query) {
    return query.every(function (q) {
      return fieldWords.some(function (w) { return w.indexOf(q) === 0; });
    });
  }

  var SPOTIFY_TRACK = /(?:open\.spotify\.com\/(?:intl-[a-z-]+\/)?track\/|spotify:track:)([A-Za-z0-9]{22})/;

  /* ---- the catalog ---- */

  var rounds = [], tracks = [], roundSize = [];

  function prepare(cat) {
    rounds = cat.rounds;
    roundSize = rounds.map(function () { return 0; });
    tracks = cat.tracks.map(function (t, i) {
      roundSize[t.round] += 1;
      return {
        i: i, t: t,
        // each artist, and the whole line too: Music League's export separates
        // artists with commas, so "Earth, Wind & Fire" arrives as "Earth" and
        // "Wind & Fire", and only the whole line still says the band's name
        artistWords: t.artists.map(words).concat([words(t.artists.join(" "))]),
        songWords: words(songOf(t.title)),
        albumWords: words(t.album)
      };
    });
  }

  function ordinal(n) {
    var s = ["th", "st", "nd", "rd"], v = n % 100;
    return n + (s[(v - 20) % 10] || s[v] || s[0]);
  }

  function row(x) {
    var t = x.t, r = rounds[t.round];
    var where = "round?s=" + encodeURIComponent(r.season) + "&r=" + encodeURIComponent(r.id);
    return '<li class="rc-row">' +
      (t.art ? '<img class="rc-art" src="' + esc(t.art) + '" alt="" width="48" height="48" loading="lazy">' : '<span class="rc-art"></span>') +
      '<span class="rc-text"><b>' + esc(t.title) + "</b>" +
        "<span>" + esc(t.artists.join(", ")) + (t.album ? " · " + esc(t.album) : "") + "</span>" +
        '<span class="rc-where"><a href="' + esc(where) + '">' + esc(r.seasonLabel) + " · Round " + r.number + ": " + esc(r.name) + "</a>" +
        " · by " + esc(t.submitterName) +
        (t.place ? " · " + ordinal(t.place) + " of " + roundSize[t.round] : "") + "</span></span>" +
      '<a class="rc-play" href="https://open.spotify.com/track/' + encodeURIComponent(t.spotifyId) +
        '" target="_blank" rel="noopener" aria-label="Open ' + esc(t.title) + ' on Spotify">↗</a></li>';
  }

  function group(title, list) {
    if (!list.length) return "";
    return '<section class="rc-group"><h2>' + title + ' <span class="rc-count">' + list.length + "</span></h2>" +
      '<ul class="rc-list">' + list.map(row).join("") + "</ul></section>";
  }

  // newest first
  function newest(a, b) { return b.t.round - a.t.round || a.i - b.i; }

  function search(raw) {
    var text = String(raw || "").trim();
    var link = SPOTIFY_TRACK.exec(text);
    var html = "", total = 0, seen = {};
    function count(list) { list.forEach(function (x) { seen[x.i] = true; }); }

    if (link) {
      var exact = tracks.filter(function (x) { return x.t.spotifyId === link[1]; }).sort(newest);
      if (!exact.length) {
        $("rcVerdict").textContent = "That exact recording hasn’t been submitted in a finished round. " +
          "Type its name to check the song or artist too.";
        $("rcResults").innerHTML = "";
        return;
      }
      // and every other version of the song, and the artist's other tracks
      var first = exact[0].t;
      html += group("This exact recording", exact);
      count(exact);
      var song = words(songOf(first.title)), artist = words(first.artists[0]);
      var sameSong = tracks.filter(function (x) { return !seen[x.i] && matches(x.songWords, song) && x.songWords.length === song.length; }).sort(newest);
      html += group("The same song, another version", sameSong);
      count(sameSong);
      var sameArtist = tracks.filter(function (x) {
        return !seen[x.i] && x.artistWords.some(function (a) { return a.join(" ") === artist.join(" "); });
      }).sort(newest);
      html += group("More by " + esc(first.artists[0]), sameArtist);
      count(sameArtist);
    } else {
      var q = words(text);
      if (!q.length || text.length < 2) {
        $("rcVerdict").textContent = "";
        $("rcResults").innerHTML = "";
        return;
      }
      var byArtist = tracks.filter(function (x) { return x.artistWords.some(function (a) { return matches(a, q); }); }).sort(newest);
      var bySong = tracks.filter(function (x) { return matches(x.songWords, q); }).sort(newest);
      var byAlbum = tracks.filter(function (x) { return matches(x.albumWords, q); }).sort(newest);
      html += group("Artist", byArtist) + group("Song", bySong) + group("Album", byAlbum);
      [byArtist, bySong, byAlbum].forEach(count);
    }
    total = Object.keys(seen).length;
    $("rcVerdict").textContent = total
      ? (total === 1 ? "Yes: 1 past submission matches." : "Yes: " + total + " past submissions match.")
      : "No match in " + tracks.length + " tracks from " + rounds.length + " finished rounds.";
    $("rcVerdict").className = "rc-verdict" + (total ? " is-found" : " is-clear");
    $("rcResults").innerHTML = html;
  }

  /* ---- the gauge: pick the exact track on Spotify ---- */

  // Spotify's matches for the words typed (through the search-tracks Edge
  // Function), so the gauge knows exactly which track is meant.
  var asked = "", picks = [];

  function spotifyPicks(text) {
    asked = text;
    if (text.length < 3 || SPOTIFY_TRACK.test(text)) { $("rcPick").hidden = true; return; }
    PFML.api.searchTracks("spotify", text).then(function (res) {
      if (asked !== text) return;                 // a newer search is under way
      picks = ((res && res.results) || []).slice(0, 5);
      if (!picks.length) { $("rcPick").hidden = true; return; }
      $("rcSpotify").innerHTML = picks.map(function (r, i) {
        return '<li><button type="button" class="sub-result" data-i="' + i + '" aria-pressed="false">' +
          (r.image ? '<img src="' + esc(r.image) + '" alt="" width="44" height="44" loading="lazy">' : '<span class="sub-result-noart"></span>') +
          '<span class="sub-result-text"><b>' + esc(r.title) + "</b><small>" + esc(r.artist) +
          (r.album ? " · " + esc(r.album) : "") + "</small></span></button></li>";
      }).join("");
      $("rcPick").hidden = false;
    }).catch(function (err) {
      // search is a help here, not the point: the checker still works
      console.error(err);
      $("rcPick").hidden = true;
    });
  }

  function showGauge(pick) {
    PFMLSentiment.load().then(function () {
      $("rcGauge").innerHTML = PFMLSentiment.gaugeHtml(PFMLSentiment.judge(pick));
    }).catch(function (err) { console.error(err); });
  }

  function onPick(ev) {
    var b = ev.target.closest(".sub-result");
    if (!b) return;
    $("rcSpotify").querySelectorAll(".sub-result").forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
    var r = picks[+b.dataset.i];
    showGauge({ spotifyId: r.id, title: r.title, artists: String(r.artist).split(", "), album: r.album });
  }

  // a pasted link the catalog knows is judged straight away
  function gaugeForLink(text) {
    var link = SPOTIFY_TRACK.exec(text);
    var known = link && tracks.filter(function (x) { return x.t.spotifyId === link[1]; })[0];
    if (known) showGauge({ spotifyId: known.t.spotifyId, title: known.t.title, artists: known.t.artists, album: known.t.album });
  }

  /* ---- start ---- */

  function remember(q) {
    // the search in the address, so it can be shared or reloaded
    var url = location.pathname + (q ? "?q=" + encodeURIComponent(q) : "") + location.hash;
    try { history.replaceState(history.state, "", url); } catch (e) { /* not worth failing over */ }
  }

  function boot() {
    PFML.loadJSON("catalog.json").then(function (cat) {
      prepare(cat);
      $("rcLine").textContent = "Has it been submitted before? Searches " + tracks.length + " tracks from " +
        rounds.length + " finished rounds, every season.";
      var box = $("rcQuery"), timer = 0;
      box.disabled = false;
      var spotifyTimer = 0;
      $("rcSpotify").addEventListener("click", onPick);
      box.addEventListener("input", function () {
        clearTimeout(timer);
        clearTimeout(spotifyTimer);
        $("rcGauge").innerHTML = "";
        var text = box.value.trim();
        timer = setTimeout(function () { search(box.value); remember(text); gaugeForLink(text); }, 120);
        spotifyTimer = setTimeout(function () { spotifyPicks(text); }, 450);
      });
      var start = new URLSearchParams(location.search).get("q");
      if (start) { box.value = start; search(start); gaugeForLink(start.trim()); spotifyPicks(start.trim()); }
      if (window.matchMedia("(pointer: fine)").matches) box.focus();
    }).catch(function (err) {
      console.error(err);
      $("rcLine").textContent = "Couldn’t load the past rounds: " + ((err && err.message) || err);
    });
  }

  PFML.ready.then(boot);
})();
