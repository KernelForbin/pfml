/* ==========================================================
   PFML - the round player (stage 3 of submissions on the site)

   One Play button that plays a closed round straight through, track after
   track, whichever service each is on: Spotify, YouTube or SoundCloud, each
   in its own official player, driven through that player's API:
     Spotify    open.spotify.com/embed/iframe-api/v1 (EmbedController)
     YouTube    www.youtube.com/iframe_api (YT.Player, nocookie host)
     SoundCloud w.soundcloud.com/player/api.js (SC.Widget)
   Each script loads only when someone presses Play.

   One service's player is kept from track to track while the service stays
   the same (a player that has already started is the likeliest to be
   allowed to start the next), and swapped when it changes.

   For a screen that's on. A phone stops it when it locks, and a browser may
   refuse to start the next track without a tap (Spotify's docs say Safari
   does), so if a track hasn't started within a few seconds a big "Tap to
   play next" button appears. The round playlists are the way to listen with
   the phone locked. Spotify plays full tracks only to someone signed in to
   Spotify in that browser (30-second previews otherwise), so the source
   picker can swap in each track's YouTube copy.

   README, Submissions on the site, stage 3.
   ========================================================== */

(function () {
  "use strict";

  var SCRIPTS = {
    spotify: "https://open.spotify.com/embed/iframe-api/v1",
    youtube: "https://www.youtube.com/iframe_api",
    soundcloud: "https://w.soundcloud.com/player/api.js"
  };
  var NAMES = { spotify: "Spotify", youtube: "YouTube", soundcloud: "SoundCloud" };
  var STALL_MS = 6000;          // how long a track gets to start before "Tap to play next"
  var PHONE_HINT_MS = 2500;     // on a phone, before "Tap ▶ on the video"
  var PREF_KEY = "pfml-player-source";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* ---- loading each service's script, once, when first needed ---- */

  var loading = {};
  function loadScript(name) {
    if (loading[name]) return loading[name];
    loading[name] = new Promise(function (resolve, reject) {
      if (name === "youtube") {
        if (window.YT && window.YT.Player) return resolve(window.YT);
        var prev = window.onYouTubeIframeAPIReady;
        window.onYouTubeIframeAPIReady = function () { if (prev) prev(); resolve(window.YT); };
      } else if (name === "spotify") {
        window.onSpotifyIframeApiReady = function (api) { resolve(api); };
      }
      var s = document.createElement("script");
      s.src = SCRIPTS[name];
      s.async = true;
      s.onerror = function () { delete loading[name]; reject(new Error(NAMES[name] + "'s player didn't load")); };
      if (name === "soundcloud") s.onload = function () { resolve(window.SC); };
      document.head.appendChild(s);
    });
    return loading[name];
  }

  /* ---- one adapter per service: load(id), play(), pause(), destroy() ----
     Each calls hooks.playing() once its track is actually playing,
     hooks.paused(bool) as that changes, hooks.ended() when the track
     finishes, and hooks.failed() when it can't play at all. */

  function spotifyAdapter(stage, hooks) {
    var ctrl = null, ready = null, uri = null, endedFor = null, lastPos = 0;
    function make(api) {
      return new Promise(function (resolve) {
        var host = document.createElement("div");
        stage.appendChild(host);
        api.createController(host, { uri: uri, width: "100%", height: 152 }, function (c) {
          ctrl = c;
          c.addListener("playback_update", function (e) {
            var d = e.data || {};
            if (d.playingURI && d.playingURI !== uri) return;      // the track before, still reporting
            if (!d.isPaused && d.position > 0) hooks.playing();
            hooks.paused(!!d.isPaused);
            // the end: the position reaches the duration, or it stops having
            // just been there (it can jump back to 0 as it stops)
            var atEnd = d.duration > 0 && d.position >= d.duration - 800;
            var stoppedAtEnd = d.isPaused && d.duration > 0 && lastPos >= d.duration - 1500;
            if ((atEnd || stoppedAtEnd) && endedFor !== uri) { endedFor = uri; hooks.ended(); }
            lastPos = d.position || 0;
          });
          resolve(c);
        });
      });
    }
    return {
      load: function (id) {
        uri = "spotify:track:" + id; endedFor = null; lastPos = 0;
        if (!ready) ready = loadScript("spotify").then(make);
        else ready = ready.then(function (c) { c.loadUri(uri); return c; });
        return ready.then(function (c) { c.play(); });
      },
      play: function () { if (ctrl) ctrl.resume(); },
      pause: function () { if (ctrl) ctrl.pause(); },
      destroy: function () { if (ctrl) { try { ctrl.destroy(); } catch (e) { /* already gone */ } } stage.innerHTML = ""; }
    };
  }

  function youtubeAdapter(stage, hooks) {
    var player = null, ready = null;
    // `cueOnly`: made ahead of the first tap, holding a track without
    // playing it (cue, below)
    function make(YT, id, cueOnly) {
      return new Promise(function (resolve) {
        var box = document.createElement("div");
        box.className = "rp-video";
        var host = document.createElement("div");
        box.appendChild(host);
        stage.appendChild(box);
        new YT.Player(host, {
          host: "https://www.youtube-nocookie.com",
          videoId: id,
          playerVars: { autoplay: cueOnly ? 0 : 1, playsinline: 1, rel: 0 },
          events: {
            onReady: function (e) { player = e.target; if (!cueOnly) player.playVideo(); resolve(player); },
            onStateChange: function (e) {
              if (e.data === YT.PlayerState.PLAYING) { hooks.playing(); hooks.paused(false); }
              else if (e.data === YT.PlayerState.PAUSED) hooks.paused(true);
              else if (e.data === YT.PlayerState.ENDED) hooks.ended();
            },
            // 100 removed, 101/150 the owner doesn't allow embedding
            onError: function () { hooks.failed(); }
          }
        });
      });
    }
    return {
      // A player that's ready is told straight away, inside the tap that
      // asked, not a step later: an iPhone lets a page start sound only
      // from a tap (README, Listening on the round page).
      load: function (id) {
        if (player) { player.loadVideoById(id); ready = Promise.resolve(player); }
        else if (!ready) ready = loadScript("youtube").then(function (YT) { return make(YT, id); });
        else ready = ready.then(function (p) { p.loadVideoById(id); return p; });
        return ready;
      },
      // A phone makes the player before anyone taps, with the first track
      // waiting in it, so the first tap finds it ready (player.js mount).
      cue: function (id) {
        if (!ready) ready = loadScript("youtube").then(function (YT) { return make(YT, id, true); });
      },
      play: function () { if (player) player.playVideo(); },
      pause: function () { if (player) player.pauseVideo(); },
      destroy: function () { if (player) { try { player.destroy(); } catch (e) { /* already gone */ } } stage.innerHTML = ""; }
    };
  }

  function soundcloudAdapter(stage, hooks) {
    var widget = null, ready = null;
    var OPTIONS = { auto_play: true, visual: false, show_comments: false };
    function make(SC, path) {
      return new Promise(function (resolve) {
        var frame = document.createElement("iframe");
        frame.className = "sub-frame";
        frame.height = "166";
        frame.allow = "autoplay; encrypted-media";
        frame.title = "SoundCloud player";
        frame.src = "https://w.soundcloud.com/player/?url=" + encodeURIComponent("https://soundcloud.com/" + path) +
          "&auto_play=true&visual=false&show_comments=false";
        stage.appendChild(frame);
        widget = SC.Widget(frame);
        var E = SC.Widget.Events;
        widget.bind(E.READY, function () { widget.play(); resolve(widget); });
        widget.bind(E.PLAY, function () { hooks.playing(); hooks.paused(false); });
        widget.bind(E.PAUSE, function () { hooks.paused(true); });
        widget.bind(E.FINISH, function () { hooks.ended(); });
        widget.bind(E.ERROR, function () { hooks.failed(); });
      });
    }
    return {
      load: function (path) {
        if (!ready) ready = loadScript("soundcloud").then(function (SC) { return make(SC, path); });
        else ready = ready.then(function (w) { w.load("https://soundcloud.com/" + path, OPTIONS); return w; });
        return ready;
      },
      play: function () { if (widget) widget.play(); },
      pause: function () { if (widget) widget.pause(); },
      destroy: function () { stage.innerHTML = ""; widget = null; }
    };
  }

  var ADAPTERS = { spotify: spotifyAdapter, youtube: youtubeAdapter, soundcloud: soundcloudAdapter };

  /* ---- which copy of a track to play ---- */

  // "submitted": each track as it was submitted. "youtube"/"spotify": that
  // service's copy where the playlists step found one, else as submitted.
  function sourceFor(t, pref) {
    if (pref === "youtube" && t.youtube_match) return { platform: "youtube", id: t.youtube_match };
    if (pref === "spotify" && t.spotify_match) return { platform: "spotify", id: t.spotify_match };
    return { platform: t.platform, id: t.track };
  }

  // A phone starts on the YouTube copies: Spotify's player plays only
  // 30-second previews there, signed in or not (measured on an iPhone,
  // 2026-10-26), and the copies (round_playlists.py) are the exact track or
  // the closest one. A choice made in the picker is kept, as ever.
  function readPref() {
    var saved = null;
    try { saved = localStorage.getItem(PREF_KEY); } catch (e) { /* no storage: the default */ }
    return saved || (isPhone() ? "youtube" : "submitted");
  }
  function isPhone() {
    return !!(window.matchMedia && window.matchMedia("(hover: none) and (pointer: coarse)").matches);
  }
  function writePref(v) {
    try { localStorage.setItem(PREF_KEY, v); } catch (e) { /* no storage: lasts for this page */ }
  }

  /* ---- the player ---- */

  // `box` is an empty element; `tracks` are in play order, each with
  // platform, track and (once the playlists are built) title, artist,
  // spotify_match and youtube_match. `onTrack(i, paused)` hears which one is
  // playing (-1 when stopped) and whether it's paused, so the list can mark
  // it and show play or pause on it.
  function mount(box, tracks, onTrack) {
    var hasMatches = tracks.some(function (t) { return t.spotify_match || t.youtube_match; });
    box.innerHTML =
      '<div class="rp-bar">' +
        '<button type="button" class="sub-btn rp-start" data-rp="start">Play the round</button>' +
        '<div class="rp-controls" hidden>' +
          '<button type="button" class="rp-btn" data-rp="prev" aria-label="Previous track">⏮</button>' +
          '<button type="button" class="rp-btn rp-toggle" data-rp="toggle" aria-label="Pause">⏸</button>' +
          '<button type="button" class="rp-btn" data-rp="next" aria-label="Next track">⏭</button>' +
        "</div>" +
        (hasMatches
          ? '<label class="rp-pref">Play <select data-rp="pref">' +
              '<option value="submitted">each track as submitted</option>' +
              '<option value="youtube">YouTube copies where there is one</option>' +
              '<option value="spotify">Spotify copies where there is one</option>' +
            "</select></label>"
          : "") +
      "</div>" +
      '<p class="rp-now" aria-live="polite" hidden></p>' +
      '<p class="rp-hint" hidden>Tap ▶ on the video to start it. After that the round plays on by itself.</p>' +
      '<div class="rp-stage-wrap" hidden><div class="rp-stage"></div>' +
        '<button type="button" class="rp-tap" data-rp="tap" hidden>Tap to play next</button></div>' +
      '<p class="rp-note">Keeps going while this page is open and the screen is on.</p>';

    var q = function (sel) { return box.querySelector(sel); };
    var stage = q(".rp-stage"), tap = q(".rp-tap"), now = q(".rp-now"), toggle = q(".rp-toggle"), hint = q(".rp-hint");
    var pref = readPref(), sel = q('[data-rp="pref"]');
    if (sel) sel.value = pref;
    var adapters = {}, active = null, index = -1, stallTimer = 0, isPaused = false;
    var phone = isPhone();

    var hooks = {
      playing: function () { clearTimeout(stallTimer); tap.hidden = true; hint.hidden = true; },
      paused: function (p) {
        // Spotify says it many times a second; the list hears only a change
        var changed = p !== isPaused;
        setPaused(p);
        if (changed && onTrack && index >= 0) onTrack(index, p);
      },
      ended: function () { if (index >= 0) go(index + 1, true); },
      failed: function () {
        if (index < 0) return;
        var failedAt = index;
        now.textContent = "Couldn’t play track " + (failedAt + 1) + " here; skipping it.";
        setTimeout(function () { if (index === failedAt) go(failedAt + 1, true); }, 1500);
      }
    };

    function setPaused(p) {
      isPaused = p;
      toggle.textContent = p ? "▶" : "⏸";
      toggle.setAttribute("aria-label", p ? "Play" : "Pause");
    }

    function togglePause() {
      if (!active) return;
      if (isPaused) active.play(); else active.pause();
    }

    function go(i, automatic) {
      clearTimeout(stallTimer);
      if (i < 0) i = 0;
      if (i >= tracks.length) { stop("That’s the whole round."); return; }
      index = i;
      setPaused(false);                         // a new track is meant to play
      var t = tracks[i], src = sourceFor(t, pref);
      // one live player at a time: a change of service removes the other
      Object.keys(adapters).forEach(function (k) {
        if (k !== src.platform) { adapters[k].destroy(); delete adapters[k]; }
      });
      active = adapters[src.platform] || (adapters[src.platform] = ADAPTERS[src.platform](stage, hooks));
      tap.hidden = true;
      q(".rp-stage-wrap").hidden = false;
      q(".rp-controls").hidden = false;
      q(".rp-start").hidden = true;
      now.hidden = false;
      showNow(i, src);
      if (onTrack) onTrack(i, false);
      hint.hidden = true;
      active.load(src.id).catch(function (err) { console.error(err); hooks.failed(); });
      // A browser that won't start it without a tap gets a big button. A
      // phone gets a line saying to tap the video itself instead, sooner: its
      // own play button is the tap an iPhone counts, and the big button
      // would cover it (measured on an iPhone, 2026-10-26).
      stallTimer = phone
        ? setTimeout(function () { hint.hidden = false; }, PHONE_HINT_MS)
        : setTimeout(function () { tap.hidden = false; }, automatic ? STALL_MS : STALL_MS * 2);
    }

    // A phone makes its YouTube player now, hidden, with the first track
    // waiting, so a tap on the list or on Play the round can start it within
    // that tap, which an iPhone needs (adapters' cue and load).
    var first = tracks.length ? sourceFor(tracks[0], pref) : null;
    if (phone && first && first.platform === "youtube") {
      active = adapters.youtube = ADAPTERS.youtube(stage, hooks);
      active.cue(first.id);
    }

    function showNow(i, src) {
      var t = tracks[i];
      now.innerHTML = "<b>" + (i + 1) + " of " + tracks.length + "</b>" +
        (t.title ? " · " + esc(t.title) + (t.artist ? " – " + esc(t.artist) : "") : "") +
        ' <span class="rp-from">on ' + NAMES[src.platform] + "</span>";
    }

    // A new play order (the list's Shuffle and Original order buttons). The
    // track that's playing keeps playing, and Next carries on down the new
    // order from wherever it now sits.
    function setOrder(list) {
      var playing = index >= 0 ? tracks[index] : null;
      tracks = list;
      if (!playing) return;
      index = tracks.indexOf(playing);
      showNow(index, sourceFor(playing, pref));
      if (onTrack) onTrack(index, isPaused);
    }

    function stop(message) {
      clearTimeout(stallTimer);
      Object.keys(adapters).forEach(function (k) { adapters[k].destroy(); delete adapters[k]; });
      active = null; index = -1;
      q(".rp-stage-wrap").hidden = true;
      q(".rp-controls").hidden = true;
      var start = q(".rp-start");
      start.hidden = false;
      start.textContent = "Play the round again";
      now.textContent = message;
      if (onTrack) onTrack(-1, false);
    }

    box.addEventListener("click", function (ev) {
      var b = ev.target.closest("[data-rp]");
      if (!b) return;
      var what = b.getAttribute("data-rp");
      if (what === "start") go(0, false);
      else if (what === "next") go(index + 1, false);
      else if (what === "prev") go(index - 1, false);
      else if (what === "tap") { tap.hidden = true; if (active) active.play(); }
      else if (what === "toggle") togglePause();
    });
    if (sel) sel.addEventListener("change", function () {
      pref = sel.value;
      writePref(pref);
      if (index >= 0) go(index, false);        // replay this track from the chosen copy
    });

    return { playAt: function (i) { go(i, false); }, setOrder: setOrder, togglePause: togglePause,
             playing: function () { return index >= 0 ? tracks[index] : null; },
             paused: function () { return isPaused; } };
  }

  window.PFMLPlayer = { mount: mount };
})();
