/* ==========================================================
   PFML - the live room (/tt)

   One room where members take turns DJing a track each, live, from
   YouTube or SoundCloud. Everyone hears the same track at the same moment:
   the database says what's playing and since when on its own clock
   (room_here), and each page keeps its player at that second. The decks
   show the DJs in turn order, the crowd everyone else who's here, and the
   chat keeps its history.

   The database holds every rule (supabase/schema.sql, the live room):
   whose turn it is, when a track is over, who may skip (only the DJ
   playing, the admin or a commissioner), and who's still here. This page
   asks it every 20 seconds, and at once whenever the room changes (it
   hears that through Realtime; without it, every 4 seconds).

   A browser starts sound only from a tap, so nothing plays until Tune in.
   A phone stops it when it locks. README, The live room.
   ========================================================== */

(function () {
  "use strict";

  function $(id) { return document.getElementById(id); }
  function api() { return PFML.api; }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function errText(err) { return (err && err.message) || String(err); }

  var HEARTBEAT_MS = 20000;     // "I'm here"; the database drops anyone silent for 90 seconds
  var POLL_MS = 4000;           // how often to ask while Realtime isn't connected
  var DRIFT_S = 3;              // a player this far from the room's clock is moved back to it
  var START_GRACE_MS = 4500;    // how long a player gets to start before the page asks for a tap
  var VOLUME_KEY = "pfml.roomVolume";
  var SCRIPTS = { youtube: "https://www.youtube.com/iframe_api", soundcloud: "https://w.soundcloud.com/player/api.js" };

  var me = null;                // my player id
  var st = null;                // the room, as room_here() last gave it
  var offset = 0;               // the database's clock minus this device's, in ms
  var names = {};               // player id -> name, for everyone who has joined
  var msgs = [], lastMsg = 0, chatEpoch = null;
  var library = [];             // my tracks; the queued ones have queue_pos
  var tab = "queue";
  var tuned = false;            // has this page been tapped to play sound
  var needTap = false;          // a player that should be playing isn't: ask for a tap
  var live = false;             // is Realtime connected
  var busy = false, again = false, beat = 0, endTimer = 0;
  var drawn = {};               // what each part last drew, so a heartbeat redraws nothing
  var lengthSent = {}, failed = {}, skipSent = {};

  function isCommish() { return PFML.member.role === "admin" || PFML.member.role === "commissioner"; }
  function isAdmin() { return PFML.member.role === "admin"; }
  function nameOf(id) { return names[id] || "A member"; }
  function clock(s) {
    s = Math.max(0, Math.round(s));
    return Math.floor(s / 60) + ":" + (s % 60 < 10 ? "0" : "") + (s % 60);
  }

  /* ---- the room's clock ---- */

  // how far into the playing track the room is, in seconds
  function position() {
    if (!st || !st.play) return 0;
    return Math.max(0, (Date.now() + offset - Date.parse(st.play.started_at)) / 1000);
  }

  /* ---- asking the database ---- */

  function refresh() {
    if (busy) { again = true; return; }
    busy = true;
    var sentAt = Date.now();
    api().roomHere(chatEpoch === null ? null : lastMsg).then(function (state) {
      // the database's time landed about halfway through the round trip
      offset = Date.parse(state.now) - (sentAt + Date.now()) / 2;
      apply(state);
    }).catch(function (err) {
      console.error(err);
      $("ttLine").textContent = "Couldn’t reach the room: " + errText(err);
    }).then(function () {
      busy = false;
      if (again) { again = false; refresh(); }
    });
  }

  function schedule() {
    clearInterval(beat);
    beat = setInterval(refresh, live ? HEARTBEAT_MS : POLL_MS);
  }

  function apply(state) {
    var before = st && st.play ? st.play.id : null;
    st = state;
    // a removed message: read the whole chat again
    if (chatEpoch !== null && state.chat_epoch !== chatEpoch) {
      chatEpoch = null; msgs = []; lastMsg = 0;
      again = true;
    } else {
      chatEpoch = state.chat_epoch;
      addMessages(state.messages || []);
    }
    // someone new to the site since the page loaded
    var everyone = (state.crowd || []).concat(state.djs || [], state.play ? [state.play.dj] : []);
    if (everyone.some(function (id) { return id && !names[id]; })) loadNames();

    $("ttRoom").hidden = false;
    $("ttMine").hidden = false;
    $("ttLine").textContent = state.play
      ? nameOf(state.play.dj) + " is playing “" + state.play.title + "”."
      : state.djs.length ? "Between tracks." : "The room is quiet. Step up and play something.";
    drawStage();
    drawDecks();
    drawCrowd();
    // when this track's time is up, ask at once: that's what starts the next
    clearTimeout(endTimer);
    if (state.play) {
      var left = (state.play.seconds || 600) - position();
      endTimer = setTimeout(refresh, Math.max(500, left * 1000 + 400));
    }
    var now = state.play ? state.play.id : null;
    if (now !== before) {
      needTap = false;
      loadRecent();
      // my track just started: it moved to the bottom of my queue
      if (state.play && state.play.dj === me) loadLibrary();
    }
    sync();
  }

  function loadNames() {
    return api().people().then(function (people) {
      Object.keys(people || {}).forEach(function (u) { names[people[u].competitorId] = people[u].name; });
      drawn = {};
      if (st) { drawStage(); drawDecks(); drawCrowd(); drawChat(true); }
    }).catch(function (err) { console.error(err); });
  }

  /* ---- the players: one per service, made once and kept ---- */

  var loading = {};
  function loadScript(name) {
    if (loading[name]) return loading[name];
    loading[name] = new Promise(function (resolve, reject) {
      if (name === "youtube") {
        if (window.YT && window.YT.Player) return resolve(window.YT);
        var prev = window.onYouTubeIframeAPIReady;
        window.onYouTubeIframeAPIReady = function () { if (prev) prev(); resolve(window.YT); };
      }
      var s = document.createElement("script");
      s.src = SCRIPTS[name];
      s.async = true;
      s.onerror = function () { delete loading[name]; reject(new Error("a player didn't load")); };
      if (name === "soundcloud") s.onload = function () { resolve(window.SC); };
      document.head.appendChild(s);
    });
    return loading[name];
  }

  function volume() {
    var v = 80;
    try { v = +(localStorage.getItem(VOLUME_KEY) || 80); } catch (e) { /* no storage: 80 */ }
    return isNaN(v) ? 80 : Math.min(100, Math.max(0, v));
  }
  function setVolume(v) {
    try { localStorage.setItem(VOLUME_KEY, String(v)); } catch (e) { /* lasts for this page */ }
    if (yt.player) yt.player.setVolume(v);
    if (sc.widget) sc.widget.setVolume(v);
  }

  // loaded: the play id each player holds; since: when it was told to
  // start, for the grace before asking for a tap
  var yt = { player: null, making: false, loaded: null, since: 0 };
  var sc = { widget: null, making: false, loaded: null, since: 0, playing: false };

  function makeYoutube(play) {
    yt.making = true;
    yt.loaded = play.id;
    yt.since = Date.now();
    loadScript("youtube").then(function (YT) {
      new YT.Player($("ttYtHost"), {
        host: "https://www.youtube-nocookie.com",
        videoId: play.track,
        // no controls: the room keeps everyone at the same second. A player
        // made before the first tap only cues its track (an iPhone starts
        // sound only inside a tap, and only in a player that already exists).
        playerVars: { autoplay: tuned ? 1 : 0, playsinline: 1, rel: 0, controls: 0, disablekb: 1, start: Math.floor(position()) },
        events: {
          onReady: function (e) {
            yt.player = e.target;
            yt.making = false;
            yt.player.setVolume(volume());
            sync();
          },
          onStateChange: function (e) {
            // paused by a tap on the video, or by the phone: ask for a tap
            if (e.data === YT.PlayerState.PAUSED && tuned && st && st.play && st.play.platform === "youtube" && yt.loaded === st.play.id) {
              needTap = true;
              drawActs();
            }
            if (e.data === YT.PlayerState.PLAYING) { needTap = false; drawActs(); measure(); }
          },
          // 100: gone. 101, 150: its owner doesn't let other sites play it.
          onError: function (e) { playerFailed(yt.loaded, e.data === 100 || e.data === 101 || e.data === 150); }
        }
      });
    }).catch(function (err) { yt.making = false; console.error(err); playerFailed(play.id, false); });
  }

  function makeSoundcloud(play) {
    sc.making = true;
    sc.loaded = play.id;
    sc.since = Date.now();
    loadScript("soundcloud").then(function (SC) {
      var frame = document.createElement("iframe");
      frame.className = "sub-frame";
      frame.height = "166";
      frame.allow = "autoplay; encrypted-media";
      frame.title = "SoundCloud player";
      frame.src = "https://w.soundcloud.com/player/?url=" + encodeURIComponent("https://soundcloud.com/" + play.track) +
        "&auto_play=" + (tuned ? "true" : "false") + "&visual=false&show_comments=false";
      $("ttSc").appendChild(frame);
      var widget = SC.Widget(frame), E = SC.Widget.Events;
      widget.bind(E.READY, function () {
        sc.widget = widget;
        sc.making = false;
        widget.setVolume(volume());
        sync();
      });
      widget.bind(E.PLAY, function () {
        sc.playing = true;
        needTap = false;
        drawActs();
        // it starts from the top: move it to the room's second
        if (st && st.play && st.play.platform === "soundcloud" && position() > DRIFT_S) widget.seekTo(position() * 1000);
        measure();
      });
      widget.bind(E.PAUSE, function () {
        sc.playing = false;
        if (tuned && st && st.play && st.play.platform === "soundcloud" && sc.loaded === st.play.id) { needTap = true; drawActs(); }
      });
      widget.bind(E.FINISH, function () { sc.playing = false; });
      widget.bind(E.ERROR, function () { playerFailed(sc.loaded, true); });
    }).catch(function (err) { sc.making = false; console.error(err); playerFailed(play.id, false); });
  }

  // A track that won't play. When it can't play anywhere and it's mine,
  // the room moves on by itself; otherwise the page says so.
  function playerFailed(playId, everywhere) {
    if (!st || !st.play || st.play.id !== playId) return;
    failed[playId] = true;
    drawStage();
    if (everywhere && st.play.dj === me && !skipSent[playId]) {
      skipSent[playId] = true;
      api().roomSkip().then(refresh, function (err) { console.error(err); });
    }
  }

  // A pasted link comes with no length: the DJ's player measures it (or
  // anyone's, once the DJ has gone) and tells the room, once.
  function measure() {
    var play = st && st.play;
    if (!play || play.length_known || lengthSent[play.id]) return;
    if (play.dj !== me && st.crowd.indexOf(play.dj) !== -1) return;
    function send(seconds) {
      seconds = Math.round(seconds);
      if (!(seconds >= 1) || lengthSent[play.id]) return;
      lengthSent[play.id] = true;
      api().roomSetLength(play.id, Math.min(seconds, 3600)).then(refresh, function (err) { console.error(err); });
    }
    if (play.platform === "youtube" && yt.player && yt.loaded === play.id) send(yt.player.getDuration());
    if (play.platform === "soundcloud" && sc.widget && sc.loaded === play.id) sc.widget.getDuration(function (ms) { send(ms / 1000); });
  }

  // Makes what the players are doing match the room: the right track, at
  // the room's second, playing if this page is tuned in. Safe to call any
  // time; it's called on every answer from the database and every few
  // seconds between.
  function sync() {
    var play = st && st.play;
    $("ttYt").hidden = !(play && play.platform === "youtube");
    $("ttSc").hidden = !(play && play.platform === "soundcloud");
    $("ttIdle").hidden = !!play;
    if (!play || play.platform !== "youtube") { if (yt.player && yt.loaded) { yt.player.pauseVideo(); yt.loaded = null; } }
    if (!play || play.platform !== "soundcloud") { if (sc.widget && sc.loaded) { sc.widget.pause(); sc.loaded = null; sc.playing = false; } }
    if (!play) return;
    var pos = position(), stalled = false;

    if (play.platform === "youtube") {
      if (!yt.player) { if (!yt.making) makeYoutube(play); return; }
      if (yt.loaded !== play.id) {
        yt.loaded = play.id;
        yt.since = Date.now();
        if (tuned) yt.player.loadVideoById({ videoId: play.track, startSeconds: pos });
        else yt.player.cueVideoById({ videoId: play.track, startSeconds: pos });
        return;
      }
      if (!tuned) return;
      var state = yt.player.getPlayerState();       // 1 playing, 3 buffering, 0 ended
      if (state === 1) {
        if (Math.abs(yt.player.getCurrentTime() - pos) > DRIFT_S) yt.player.seekTo(pos, true);
        measure();
      } else if (state !== 3 && state !== 0 && Date.now() - yt.since > START_GRACE_MS) stalled = true;
    } else {
      if (!sc.widget) { if (!sc.making) makeSoundcloud(play); return; }
      if (sc.loaded !== play.id) {
        sc.loaded = play.id;
        sc.since = Date.now();
        sc.playing = false;
        sc.widget.load("https://soundcloud.com/" + play.track, { auto_play: tuned, visual: false, show_comments: false });
        return;
      }
      if (!tuned) return;
      if (sc.playing) {
        measure();
        sc.widget.getPosition(function (ms) {
          if (st && st.play && st.play.id === play.id && Math.abs(ms / 1000 - position()) > DRIFT_S) sc.widget.seekTo(position() * 1000);
        });
      } else if (Date.now() - sc.since > START_GRACE_MS && pos < (play.seconds || 600) - 2) stalled = true;
    }
    if (stalled && !needTap && !failed[play.id]) { needTap = true; drawActs(); }
  }

  // Tune in (or back in): inside the tap itself, tell the player that
  // already exists to play, which is what a phone needs.
  function tuneIn() {
    tuned = true;
    needTap = false;
    var play = st && st.play;
    if (play && play.platform === "youtube" && yt.player && yt.loaded === play.id) {
      yt.since = Date.now();
      yt.player.seekTo(position(), true);
      yt.player.playVideo();
    } else if (play && play.platform === "soundcloud" && sc.widget && sc.loaded === play.id) {
      sc.since = Date.now();
      sc.widget.play();
    }
    drawActs();
    sync();
  }

  function tuneOut() {
    tuned = false;
    needTap = false;
    if (yt.player) yt.player.pauseVideo();
    if (sc.widget) sc.widget.pause();
    drawActs();
  }

  /* ---- drawing ---- */

  // draws `html` into `el` only when it differs from what's there
  function draw(key, el, html) {
    if (drawn[key] === html) return;
    drawn[key] = html;
    el.innerHTML = html;
  }

  function drawStage() {
    var play = st.play;
    if (!play) {
      draw("now", $("ttNow"), "");
      $("ttBar").hidden = true;
      $("ttNote").hidden = true;
    } else {
      draw("now", $("ttNow"),
        '<p class="tt-kicker">Now playing · ' + (play.platform === "youtube" ? "YouTube" : "SoundCloud") + "</p>" +
        '<h2 class="tt-title">' + esc(play.title) + "</h2>" +
        '<p class="tt-by">' + (play.artist ? esc(play.artist) + " · " : "") + "played by <b>" + esc(nameOf(play.dj)) + "</b>" +
          ' <span class="tt-time" id="ttTime"></span></p>');
      $("ttBar").hidden = false;
      $("ttNote").textContent = failed[play.id]
        ? "This track won’t play here." + (play.dj === me ? " It’s being skipped." : " Its DJ, the admin or a commissioner can skip it.")
        : "";
      $("ttNote").hidden = !failed[play.id];
    }
    drawActs();
    tick();
  }

  function drawActs() {
    var play = st && st.play, html = "";
    var phone = !!(window.matchMedia && window.matchMedia("(hover: none) and (pointer: coarse)").matches);
    if (!tuned || needTap) {
      html += '<button type="button" class="sub-btn tt-tune" data-act="tune">' + (tuned ? "Tap to hear the room" : "Tune in") + "</button>" +
        (needTap && phone && play && play.platform === "youtube" ? '<p class="tt-hint">Still quiet? Tap ▶ on the video itself.</p>' : "");
    }
    if (play && play.dj !== me) {
      html += '<button type="button" class="sub-btn sub-btn-quiet tt-vote" data-act="awesome" aria-pressed="' + (play.my_vote === 1) + '">Awesome <b>' + play.awesome.length + "</b></button>" +
        '<button type="button" class="sub-btn sub-btn-quiet tt-vote" data-act="lame" aria-pressed="' + (play.my_vote === -1) + '">Lame <b>' + play.lame + "</b></button>";
    } else if (play) {
      html += '<span class="tt-tally">Awesome <b>' + play.awesome.length + "</b> · Lame <b>" + play.lame + "</b></span>";
    }
    // only the DJ playing, the admin or a commissioner (the database holds it)
    if (play && (play.dj === me || isCommish())) {
      html += '<button type="button" class="sub-btn sub-btn-quiet" data-act="skip">' + (play.dj === me ? "Skip my track" : "Skip this track") + "</button>";
    }
    if (tuned) {
      html += '<label class="tt-volume">Volume <input type="range" min="0" max="100" step="5" value="' + volume() + '" id="ttVolume"></label>' +
        '<button type="button" class="sub-btn sub-btn-quiet" data-act="tuneout">Tune out</button>';
    }
    draw("acts", $("ttActs"), html);
  }

  function tick() {
    var play = st && st.play;
    if (!play) return;
    var pos = position(), len = play.seconds;
    $("ttBarFill").style.width = (len ? Math.min(100, 100 * pos / len) : 0) + "%";
    var t = $("ttTime");
    if (t) t.textContent = len ? clock(Math.min(pos, len)) + " / " + clock(len) : clock(pos);
  }

  function person(id, cls, extra) {
    return '<li class="tt-person' + (cls ? " " + cls : "") + '" data-id="' + esc(id) + '">' +
      '<a href="profile?p=' + encodeURIComponent(id) + '" title="' + esc(nameOf(id)) + '">' + PFML.avatar(id, nameOf(id)) + "</a>" +
      '<span class="tt-person-name">' + esc(nameOf(id)) + (id === me ? " (you)" : "") + "</span>" + (extra || "") + "</li>";
  }

  function drawDecks() {
    var djs = st.djs || [], playing = st.play ? st.play.dj : null;
    var mine = djs.indexOf(me) !== -1;
    var bob = st.play ? st.play.awesome : [];
    draw("decks", $("ttDecks"), djs.length ? djs.map(function (id, i) {
      return person(id, (id === playing ? "is-playing" : "") + (bob.indexOf(id) !== -1 ? " is-bobbing" : ""),
        '<span class="tt-turn">' + (id === playing ? "Playing" : "Turn " + (i + 1)) + "</span>" +
        (isCommish() && id !== me ? '<button type="button" class="cm-icon tt-off" data-act="off" aria-label="Take ' + esc(nameOf(id)) + ' off the decks">✕</button>' : ""));
    }).join("") : '<li class="tt-empty">Nobody yet.</li>');
    var queued = library.filter(function (t) { return t.queue_pos != null; }).length;
    draw("deckbtn", $("ttDeckBtn"), mine
      ? '<button type="button" class="sub-btn sub-btn-quiet sub-btn-small" data-act="down">Step down</button>'
      : '<button type="button" class="sub-btn sub-btn-small" data-act="up"' + (queued ? "" : " disabled") + ">Step up to DJ</button>" +
        (queued ? "" : '<small class="tt-need">Queue a track first, below.</small>'));
  }

  function drawCrowd() {
    var djs = st.djs || [], bob = st.play ? st.play.awesome : [];
    var crowd = (st.crowd || []).filter(function (id) { return djs.indexOf(id) === -1; });
    draw("crowd", $("ttCrowd"), crowd.length ? crowd.map(function (id) {
      return person(id, bob.indexOf(id) !== -1 ? "is-bobbing" : "");
    }).join("") : '<li class="tt-empty">' + (djs.length ? "Everyone here is on the decks." : "Nobody’s here yet.") + "</li>");
    $("ttCrowdCount").textContent = (st.crowd || []).length + " here";
  }

  /* ---- the chat ---- */

  function addMessages(list) {
    var fresh = list.filter(function (m) { return m.id > lastMsg; });
    if (!fresh.length && msgs.length) return;
    msgs = msgs.concat(fresh).slice(-400);
    if (msgs.length) lastMsg = msgs[msgs.length - 1].id;
    drawChat(false);
  }

  function drawChat(force) {
    var box = $("ttMsgs");
    // stay at the bottom unless the reader has scrolled up to read back
    var atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 60;
    var html = msgs.length ? msgs.map(function (m) {
      return '<li class="tt-msg" data-id="' + m.id + '">' + PFML.avatar(m.who, nameOf(m.who)) +
        '<div><p class="tt-msg-head"><b>' + esc(nameOf(m.who)) + "</b> <small>" + esc(PFML.when(m.at)) + "</small>" +
        (m.who === me || isAdmin() ? ' <button type="button" class="tt-msg-del" data-act="unsay" aria-label="Remove this message">Remove</button>' : "") +
        '</p><p class="tt-msg-body">' + esc(m.body) + "</p></div></li>";
    }).join("") : '<li class="tt-empty">No messages yet. Say hello.</li>';
    if (force) delete drawn.chat;
    draw("chat", box, html);
    if (atBottom) box.scrollTop = box.scrollHeight;
  }

  function say(ev) {
    ev.preventDefault();
    var input = $("ttSayText"), text = input.value.trim(), msg = $("ttSayMsg");
    if (!text) return;
    msg.hidden = true;
    input.value = "";
    api().roomSay(text).then(refresh, function (err) {
      input.value = text;
      msg.textContent = errText(err);
      msg.hidden = false;
    });
  }

  /* ---- your music: the queue, the library, adding ---- */

  function mineMsg(text, good) {
    var m = $("ttMineMsg");
    m.textContent = text;
    m.className = "sub-msg" + (good ? " is-good" : " is-error");
    m.hidden = !text;
  }

  function loadLibrary() {
    return api().roomLibrary().then(function (rows) {
      library = rows;
      drawMine();
      if (st) { delete drawn.deckbtn; drawDecks(); }
    }).catch(function (err) { console.error(err); mineMsg("Couldn’t load your music: " + errText(err)); });
  }

  function thumb(t) {
    // YouTube's own thumbnail for the video; SoundCloud has none to ask for
    return t.platform === "youtube"
      ? '<img class="tt-thumb" src="https://i.ytimg.com/vi/' + encodeURIComponent(t.track) + '/default.jpg" alt="" width="60" height="45" loading="lazy">'
      : '<span class="tt-thumb tt-thumb-none" aria-hidden="true">♫</span>';
  }
  // `place`: where it sits in the queue (1 is next), when it's there
  function trackText(t, place) {
    return '<span class="tt-track"><b>' + esc(t.title) + "</b><small>" + (t.artist ? esc(t.artist) + " · " : "") +
      (t.platform === "youtube" ? "YouTube" : "SoundCloud") + (t.seconds ? " · " + clock(t.seconds) : "") +
      (place ? ' · <span class="tt-queued">' + (place === 1 ? "next in your queue" : "#" + place + " in your queue") + "</span>" : "") +
      "</small></span>";
  }

  // The library is every track you've saved, and only Delete takes one out.
  // The queue is the ones from it you'll play, in order: queuing and
  // unqueuing leave the library alone, and a track gets into the queue only
  // from the library (the user's call, 2026-11-25). In the database a queued
  // track is a library track with a place (queue_pos).
  function drawMine() {
    var queue = library.filter(function (t) { return t.queue_pos != null; });
    var all = library.slice().sort(function (a, b) {
      return a.title.localeCompare(b.title, undefined, { sensitivity: "base" }) || a.artist.localeCompare(b.artist);
    });
    Array.prototype.forEach.call($("ttTabs").querySelectorAll("button"), function (b) {
      var on = b.getAttribute("data-tab") === tab;
      b.setAttribute("aria-pressed", String(on));
      if (b.getAttribute("data-tab") === "queue") b.textContent = "Queue (" + queue.length + ")";
      if (b.getAttribute("data-tab") === "library") b.textContent = "Library (" + all.length + ")";
    });
    $("ttQueue").hidden = tab !== "queue";
    $("ttLibrary").hidden = tab !== "library";
    $("ttAdd").hidden = tab !== "add";
    $("ttQueue").innerHTML = queue.length ? queue.map(function (t, i) {
      return '<li class="tt-item" data-id="' + esc(t.id) + '">' + thumb(t) + trackText(t) + '<span class="tt-item-acts">' +
        '<button type="button" class="cm-icon" data-act="q-up" aria-label="Move ' + esc(t.title) + ' up"' + (i ? "" : " disabled") + ">↑</button>" +
        '<button type="button" class="cm-icon" data-act="q-down" aria-label="Move ' + esc(t.title) + ' down"' + (i < queue.length - 1 ? "" : " disabled") + ">↓</button>" +
        '<button type="button" class="sub-btn sub-btn-quiet sub-btn-small" data-act="q-top"' + (i ? "" : " disabled") + ">Top</button>" +
        '<button type="button" class="sub-btn sub-btn-quiet sub-btn-small" data-act="unqueue">Remove from queue</button></span></li>';
    }).join("") : '<li class="tt-empty">' + (all.length ? "Your queue is empty. Queue tracks from your library."
                                                         : "Your queue is empty. Add a track to your library, then queue it from there.") + "</li>";
    $("ttLibrary").innerHTML = all.length ? all.map(function (t) {
      var place = t.queue_pos != null ? queue.indexOf(t) + 1 : 0;
      return '<li class="tt-item" data-id="' + esc(t.id) + '">' + thumb(t) + trackText(t, place) + '<span class="tt-item-acts">' +
        (place ? '<button type="button" class="sub-btn sub-btn-quiet sub-btn-small" data-act="unqueue">Remove from queue</button>'
               : '<button type="button" class="sub-btn sub-btn-small" data-act="queue">Queue</button>') +
        '<button type="button" class="sub-btn sub-btn-quiet sub-btn-small" data-act="delete">Delete</button></span></li>';
    }).join("") : '<li class="tt-empty">Nothing saved yet. Add a track, or Save one from Recently played.</li>';
    if (tab === "add") drawResults();
  }

  function queueIds() {
    return library.filter(function (t) { return t.queue_pos != null; }).map(function (t) { return t.id; });
  }

  // The library's own copy of a track, if it has one.
  function saved(t) {
    return library.filter(function (x) { return x.platform === t.platform && x.track === t.track; })[0] || null;
  }

  function onMine(ev) {
    var t = ev.target.closest("#ttTabs button");
    if (t) { tab = t.getAttribute("data-tab"); mineMsg(""); drawMine(); return; }
    var b = ev.target.closest("button[data-act]");
    if (!b) return;
    var act = b.getAttribute("data-act"), li = b.closest("[data-id], [data-i]");
    if (act === "add") { addResult(+li.getAttribute("data-i"), b); return; }
    var id = li.getAttribute("data-id");
    // a search result already in the library acts on its library copy
    if (!id && li.hasAttribute("data-i")) { var mine = saved(results[+li.getAttribute("data-i")]); id = mine && mine.id; }
    if (!id) return;
    var ids = queueIds(), i = ids.indexOf(id), done;
    if (act === "q-up" || act === "q-down") {
      var j = act === "q-up" ? i - 1 : i + 1;
      ids[i] = ids[j]; ids[j] = id;
      done = api().roomQueueSet(ids);
    } else if (act === "q-top") { ids.splice(i, 1); ids.unshift(id); done = api().roomQueueSet(ids); }
    else if (act === "unqueue") { ids.splice(i, 1); done = api().roomQueueSet(ids); }
    else if (act === "queue") { if (i === -1) ids.push(id); done = api().roomQueueSet(ids); }
    else if (act === "delete") {
      // asks once, on the button itself: Delete takes it out of the library
      // for good, and out of the queue with it
      if (b.getAttribute("data-armed") !== "1") {
        b.setAttribute("data-armed", "1");
        b.textContent = "Delete for good?";
        setTimeout(function () { if (b.isConnected) { b.removeAttribute("data-armed"); b.textContent = "Delete"; } }, 4000);
        return;
      }
      done = api().roomLibraryRemove(id);
    } else return;
    b.disabled = true;
    mineMsg("");
    done.then(loadLibrary).catch(function (err) { b.disabled = false; mineMsg(errText(err)); });
  }

  // { platform, track } for a YouTube video or a SoundCloud track, { error }
  // for any other link, null for words to search for. The same shapes the
  // database checks (the Submit page reads links the same way).
  function parseLink(raw) {
    var text = String(raw || "").trim();
    if (!/^(https?:\/\/|www\.|m\.|youtu\.be\/|youtube\.com\/|soundcloud\.com\/|music\.youtube\.com\/)/i.test(text)) return null;
    if (!/^[a-z]+:\/\//i.test(text)) text = "https://" + text;
    var u;
    try { u = new URL(text); } catch (e) { return { error: "That doesn’t look like a link." }; }
    var host = u.hostname.toLowerCase().replace(/^(www\.|m\.)/, "");
    var parts = u.pathname.split("/").filter(Boolean);
    if (host === "youtube.com" || host === "music.youtube.com" || host === "youtube-nocookie.com" || host === "youtu.be") {
      var id = host === "youtu.be" ? parts[0] : u.searchParams.get("v");
      if (!id && ["shorts", "embed", "live", "v"].indexOf(parts[0]) !== -1) id = parts[1];
      if (id && /^[A-Za-z0-9_-]{11}$/.test(id)) return { platform: "youtube", track: id };
      return { error: "That YouTube link doesn’t point at one video." };
    }
    if (host === "soundcloud.com") {
      var user = (parts[0] || "").toLowerCase(), slug = (parts[1] || "").toLowerCase();
      if (parts.length === 2 && slug !== "sets" && /^[a-z0-9_-]{1,100}$/.test(user) && /^[a-z0-9_-]{1,200}$/.test(slug)) {
        return { platform: "soundcloud", track: user + "/" + slug };
      }
      return { error: "That SoundCloud link doesn’t point at one public track." };
    }
    if (host === "on.soundcloud.com") return { error: "Short SoundCloud links can’t be read here. Open it and copy the full address." };
    return { error: "The room plays YouTube and SoundCloud. Paste a link from one of them." };
  }

  // A result goes into the library first; once it's there, it can be
  // queued from the same row, as from the library.
  var results = [];
  function drawResults() {
    $("ttResults").innerHTML = results.map(function (t, i) {
      var mine = saved(t);
      return '<li class="tt-item" data-i="' + i + '">' + thumb(t) + trackText(mine || t, mine && mine.queue_pos != null ? queueIds().indexOf(mine.id) + 1 : 0) +
        '<span class="tt-item-acts">' +
        (!mine ? '<button type="button" class="sub-btn sub-btn-small" data-act="add">Add to library</button>'
          : '<span class="tt-in">In your library</span>' + (mine.queue_pos != null ? ""
            : '<button type="button" class="sub-btn sub-btn-quiet sub-btn-small" data-act="queue">Queue</button>')) +
        "</span></li>";
    }).join("");
  }

  function find(ev) {
    ev.preventDefault();
    var q = $("ttAddText").value.trim();
    if (!q) return;
    results = [];
    drawResults();
    var link = parseLink(q);
    if (link && link.error) { mineMsg(link.error); return; }
    if (link) {
      mineMsg("Reading that link…", true);
      PFMLSentiment.aboutLink(link.platform, link.track).then(function (about) {
        if (!about) { mineMsg("Couldn’t read that link. Check it opens, and that the track is public."); return; }
        results = [{ platform: link.platform, track: link.track, title: about.title, artist: about.author, seconds: null }];
        mineMsg("");
        drawResults();
      });
      return;
    }
    mineMsg("Searching YouTube…", true);
    api().searchTracks("youtube", q).then(function (res) {
      if (res && res.error === "quota") { mineMsg("YouTube searching here is used up for today. Find it on YouTube and paste its link."); return; }
      if (!res || res.error) throw new Error((res && res.error) || "no answer");
      results = (res.results || []).map(function (r) {
        return { platform: "youtube", track: r.id, title: r.title, artist: r.artist, seconds: r.seconds };
      });
      mineMsg(results.length ? "" : "Nothing found. Try other words, or paste a link.");
      drawResults();
    }).catch(function (err) {
      console.error(err);
      mineMsg("Search isn’t working right now. Find it on YouTube and paste its link.");
    });
  }

  function addResult(i, b) {
    var t = results[i];
    if (!t) return;
    b.disabled = true;
    api().roomLibraryAdd(t, false).then(function () {
      mineMsg("“" + t.title + "” is in your library.", true);
      return loadLibrary();
    }).catch(function (err) { b.disabled = false; mineMsg(errText(err)); });
  }

  /* ---- recently played ---- */

  var recent = [];
  function loadRecent() {
    api().roomRecent().then(function (rows) {
      recent = rows;
      $("ttRecent").hidden = !rows.length;
      $("ttRecentList").innerHTML = rows.map(function (t, i) {
        return '<li class="tt-item" data-i="' + i + '">' + thumb(t) +
          '<span class="tt-track"><b>' + esc(t.title) + "</b><small>" + (t.artist ? esc(t.artist) + " · " : "") + "played by " + esc(nameOf(t.dj)) +
          " · Awesome " + t.awesome + (t.lame ? " · Lame " + t.lame : "") + (t.skipped ? " · skipped" : "") + "</small></span>" +
          '<span class="tt-item-acts"><button type="button" class="sub-btn sub-btn-quiet sub-btn-small" data-act="keep">Save</button></span></li>';
      }).join("");
    }).catch(function (err) { console.error(err); });
  }

  function onRecent(ev) {
    var b = ev.target.closest('[data-act="keep"]');
    if (!b) return;
    var t = recent[+b.closest("[data-i]").getAttribute("data-i")];
    b.disabled = true;
    api().roomLibraryAdd(t, false).then(function () { b.textContent = "Saved"; return loadLibrary(); })
      .catch(function (err) { b.disabled = false; b.textContent = errText(err); });
  }

  /* ---- the room's buttons ---- */

  function deckMsg(text) { $("ttDeckMsg").textContent = text; $("ttDeckMsg").hidden = !text; }

  function onRoom(ev) {
    var b = ev.target.closest("button[data-act]");
    if (!b) return;
    var act = b.getAttribute("data-act"), done;
    if (act === "tune") { tuneIn(); return; }
    if (act === "tuneout") { tuneOut(); return; }
    if (act === "unsay") { done = api().roomRemoveMessage(+b.closest("[data-id]").getAttribute("data-id")); }
    else if (act === "awesome" || act === "lame") {
      var v = act === "awesome" ? 1 : -1;
      done = api().roomVote(st.play.my_vote === v ? 0 : v);
    } else if (act === "skip") done = api().roomSkip();
    else if (act === "up") done = api().roomStepUp();
    else if (act === "down") done = api().roomStepDown();
    else if (act === "off") done = api().roomRemoveDj(b.closest("[data-id]").getAttribute("data-id"));
    else return;
    b.disabled = true;
    deckMsg("");
    done.then(refresh).catch(function (err) {
      b.disabled = false;
      deckMsg(errText(err));
    });
  }

  /* ---- start ---- */

  function boot() {
    me = PFML.member.competitorId;
    names[me] = PFML.member.name;
    $("ttRoom").addEventListener("click", onRoom);
    $("ttRoom").addEventListener("input", function (ev) { if (ev.target.id === "ttVolume") setVolume(+ev.target.value); });
    $("ttSay").addEventListener("submit", say);
    $("ttMine").addEventListener("click", onMine);
    $("ttAddForm").addEventListener("submit", find);
    $("ttRecent").addEventListener("click", onRecent);
    // a browser still holding an auth.js from before the room
    if (typeof api().roomHere !== "function") {
      $("ttLine").textContent = "Part of the site is still the version from before an update. Reload the page.";
      return;
    }
    loadNames().then(refresh);
    loadLibrary();
    api().roomWatch(refresh, function (on) { live = on; schedule(); });
    schedule();
    setInterval(tick, 500);
    setInterval(sync, 5000);
    // back from another tab or app: catch up at once
    document.addEventListener("visibilitychange", function () { if (!document.hidden) refresh(); });
    window.addEventListener("pageshow", function (ev) { if (ev.persisted) refresh(); });
    // leaving: off the decks and out of the crowd now, not in 90 seconds
    window.addEventListener("pagehide", function () { try { api().roomLeave(); } catch (e) { /* the database notices anyway */ } });
  }

  PFML.ready.then(boot);
})();
