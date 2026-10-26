/* ==========================================================
   PFML - listening to a round (the round page)

   A closed site round's tracks, for everyone, with nobody's name: the
   round player (player.js) and every track in the round's order, each
   with a play button, then the round's Spotify and YouTube playlists for
   anyone who'd rather listen in the app.
   Moved here from the Submit page 2026-10-26 (the user's call), so a round
   keeps its listening for good, not only until the next round opens.

   The round page (app.js initRound) draws it into its listening section:
   round?site=<site round id>, or a round's stats page once it's in the
   stats (statsIndex says which site round that is). README, Listening on
   the round page.
   ========================================================== */

(function () {
  "use strict";

  var NAMES = { spotify: "Spotify", youtube: "YouTube", soundcloud: "SoundCloud" };

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function errText(err) { return (err && err.message) || String(err); }

  function trackUrl(sub) {
    if (sub.platform === "spotify") return "https://open.spotify.com/track/" + sub.track;
    if (sub.platform === "youtube") return "https://www.youtube.com/watch?v=" + sub.track;
    return "https://soundcloud.com/" + sub.track;
  }

  // Which of a season's stats rounds a site round is, or -1: the same id (a
  // season played on the site), or, for a round voted in Music League, the
  // season's Nth round when the site round is named "Round N…", as Season 3's
  // are from Round 7 (the stats keep Music League's own round ids).
  function statsIndex(statsRounds, site) {
    for (var i = 0; i < statsRounds.length; i++) if (statsRounds[i].id === site.id) return i;
    var m = !site.votes_on_site && /^Round (\d+)\b/.exec(site.name || "");
    var n = m ? +m[1] : 0;
    return n >= 1 && n <= statsRounds.length ? n - 1 : -1;
  }

  // Built by scripts/round_playlists.py once the round has closed: the
  // shuffled order, titles, each track's copy on the other service, and the
  // two playlists. Before that, the list has no titles.
  function playlistButtons(r) {
    var out = [];
    if (r.spotify_playlist) {
      out.push('<a class="sub-btn sub-play sub-play-spotify" href="https://open.spotify.com/playlist/' +
        encodeURIComponent(r.spotify_playlist) + '" target="_blank" rel="noopener">Open in Spotify</a>');
    }
    if (r.youtube_playlist) {
      out.push('<a class="sub-btn sub-play sub-play-youtube" href="https://www.youtube.com/playlist?list=' +
        encodeURIComponent(r.youtube_playlist) + '" target="_blank" rel="noopener">Open in YouTube</a>');
    }
    return out.join("");
  }

  // "Not on Spotify" / "Not on YouTube", for a track the playlist skips
  function gapNote(s) {
    if (!s.position) return "";
    var missing = [];
    if (!s.spotify_match) missing.push("Spotify");
    if (!s.youtube_match) missing.push("YouTube");
    return missing.length ? '<span class="sub-gap">Not on ' + missing.join(" or ") + "</span>" : "";
  }

  // Draws the listening section into `host` for the site round `r`.
  function render(host, r) {
    var phase = PFML.roundPhase(r);
    if (phase === "upcoming" || phase === "submitting") {
      host.innerHTML = "<h2>Listen</h2>" +
        '<p class="block-note">The tracks show here once submissions close. Until then nobody can see them, the admin included.</p>';
      host.hidden = false;
      return;
    }
    // Playing here comes first, and the apps' playlists after the list,
    // marked as leaving the site: their buttons at the top read as the way
    // to listen, and people left the page for YouTube (the user's call,
    // 2026-10-26).
    var built = !!(r.spotify_playlist || r.youtube_playlist);
    var apps = r.spotify_playlist && r.youtube_playlist ? "the Spotify or YouTube app"
      : r.youtube_playlist ? "the YouTube app" : "the Spotify app";
    host.innerHTML = "<h2>Listen</h2>" +
      '<p class="ln-lead">Play the round here: tap any track below and it plays on from there.</p>' +
      '<div class="rp" id="lnPlayer"></div>' +
      '<div class="sub-order" id="lnOrder" hidden>' +
        '<button type="button" class="sub-btn sub-btn-quiet" id="lnShuffle">Shuffle</button>' +
        '<button type="button" class="sub-btn sub-btn-quiet" id="lnOriginal" hidden>Original order</button>' +
      "</div>" +
      '<p class="block-note" id="lnListNote"></p>' +
      '<ol class="sub-tracks" id="lnTracks"><li class="sub-empty">Loading…</li></ol>' +
      (built
        ? '<div class="sub-playlists ln-apps"><p class="sub-play-note"><b>Prefer an app?</b> The whole round as a playlist in ' +
          apps + ", in the same order as the list.</p>" +
          '<div class="sub-actions">' + playlistButtons(r) + "</div></div>"
        : "");
    host.hidden = false;
    PFML.api.roundSubmissions(r.id).then(function (rows) {
      // the round's one shuffle, the same for everyone from the close, and
      // the order the playlists keep (PFML.roundOrder, account.js)
      rows = PFML.roundOrder(r.id, rows || []);
      if (!rows.length) { $("lnTracks").innerHTML = '<li class="sub-empty">No tracks were submitted.</li>'; return; }
      // the round player (player.js) plays them top to bottom; the list
      // marks the one playing, a tap on another starts the round from that
      // track, and a tap on the one playing pauses or resumes it
      var list = { original: rows, order: rows, player: null, built: built };
      list.player = window.PFMLPlayer.mount($("lnPlayer"), rows, function (playing, paused) { markPlaying(playing, paused); });
      $("lnTracks").onclick = function (ev) {
        var b = ev.target.closest(".sub-track-btn");
        if (!b) return;
        var i = +b.dataset.i;
        if (list.player.playing() === list.order[i]) list.player.togglePause();
        else list.player.playAt(i);
      };
      $("lnShuffle").onclick = function () { reorder(list, shuffled(list)); };
      $("lnOriginal").onclick = function () { reorder(list, list.original); };
      $("lnOrder").hidden = rows.length < 2;
      drawTracks(list);
    }).catch(function (err) {
      $("lnTracks").innerHTML = '<li class="sub-empty">Couldn’t load the tracks: ' + esc(errText(err)) + "</li>";
    });
  }

  // The list in its current order, numbered top to bottom: the order the
  // player goes in.
  function drawTracks(list) {
    var mixed = list.order !== list.original;
    $("lnListNote").textContent = mixed
      ? "Shuffled for you: the player goes top to bottom. Original order puts it back the way everyone first saw it; " +
        "the Spotify and YouTube playlists keep that order."
      : (list.built ? "The round’s order, the same for everyone and the same as the playlists. "
                    : "The round’s order, shuffled once when submissions closed and the same for everyone. ") +
        "Tap a track to play the round from there.";
    $("lnOriginal").hidden = !mixed;
    $("lnTracks").innerHTML = list.order.map(function (s, i) {
      var name = s.title
        ? '<span class="sub-track-name"><b>' + esc(s.title) + "</b>" + (s.artist ? "<small>" + esc(s.artist) + "</small>" : "") + "</span>"
        : '<span class="sub-track-where">' + NAMES[s.platform] + "</span>";
      var label = s.title ? s.title + (s.artist ? " – " + s.artist : "") : "track " + (i + 1) + " on " + NAMES[s.platform];
      return '<li class="sub-track">' +
        '<button type="button" class="sub-track-btn" data-i="' + i + '" data-label="' + esc(label) + '" ' +
          'aria-label="Play ' + esc(label) + '" aria-current="false">' +
          '<span class="sub-pos">' + (i + 1) + "</span>" +
          '<span class="sub-track-play" aria-hidden="true">' + PLAY_ICON + "</span>" + name + "</button>" +
        gapNote(s) +
        (s.note ? '<p class="sub-track-note">' + esc(s.note) + "</p>" : "") +
        '<a class="sub-track-open" href="' + esc(trackUrl(s)) + '" target="_blank" rel="noopener">Open on ' + NAMES[s.platform] + "</a></li>";
    }).join("");
    var playing = list.player.playing();
    markPlaying(playing ? list.order.indexOf(playing) : -1, list.player.paused());
  }

  // Play on every track, pause on the one playing (play again while it's
  // paused); the one playing is outlined either way.
  var PLAY_ICON = '<svg viewBox="0 0 24 24"><path d="M8 5.5v13l11-6.5z"/></svg>';
  var PAUSE_ICON = '<svg viewBox="0 0 24 24"><path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z"/></svg>';
  function markPlaying(playing, paused) {
    $("lnTracks").querySelectorAll(".sub-track").forEach(function (li, i) {
      var on = i === playing, sounding = on && !paused;
      var b = li.querySelector(".sub-track-btn");
      li.classList.toggle("is-playing", on);
      b.setAttribute("aria-current", String(on));
      b.setAttribute("aria-label", (sounding ? "Pause " : "Play ") + b.getAttribute("data-label"));
      li.querySelector(".sub-track-play").innerHTML = sounding ? PAUSE_ICON : PLAY_ICON;
    });
  }

  // A fresh shuffle for this reader only, never saved. A track that's
  // playing goes to the top and keeps playing, so everything below it is
  // still to come.
  function shuffled(list) {
    var playing = list.player.playing();
    var rest = list.order.filter(function (s) { return s !== playing; });
    for (var tries = 0; tries < 5; tries++) {
      for (var i = rest.length - 1; i > 0; i--) {
        var j = Math.floor(Math.random() * (i + 1)), t = rest[i];
        rest[i] = rest[j];
        rest[j] = t;
      }
      var next = playing ? [playing].concat(rest) : rest.slice();
      // a shuffle that lands on the same order would look like a dead button
      if (next.some(function (s, k) { return s !== list.order[k]; })) return next;
    }
    return next;
  }

  function reorder(list, order) {
    list.order = order;
    list.player.setOrder(order);
    drawTracks(list);
  }

  window.PFMLListen = { render: render, statsIndex: statsIndex };
})();
