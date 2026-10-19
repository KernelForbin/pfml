/* ==========================================================
   PFML - submitting a track on the site (/submit)

   The open round's prompt and deadline; a box to paste a Spotify,
   YouTube or SoundCloud link, previewed in that service's own player
   before it's sent. Voting stays in Music League. Once the round closes,
   everyone sees the list of tracks, never who sent which; a tag like Q7
   labels each one.

   All the database rules live in supabase/schema.sql: the page can't
   see whose track is whose, and neither can the admin. README,
   Submissions on the site.
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

  /* ---- reading a pasted link ---- */

  var SPOTIFY_ID = /^[A-Za-z0-9]{22}$/;
  var YOUTUBE_ID = /^[A-Za-z0-9_-]{11}$/;
  var SOUNDCLOUD_PART = /^[a-z0-9_-]+$/;
  // second path parts that are SoundCloud pages, not tracks
  var SOUNDCLOUD_PAGES = ["sets", "tracks", "albums", "likes", "reposts", "popular-tracks", "followers", "following", "comments"];
  var NAMES = { spotify: "Spotify", youtube: "YouTube", soundcloud: "SoundCloud" };

  function shortLink(service) {
    return "Short " + service + " share links can't be read here. Open it in your browser and copy the full address instead.";
  }

  // { platform, track } for a track the site can use, { error } for
  // anything else, null for an empty box. The track is what the database
  // stores: a Spotify track id, a YouTube video id, or "user/track" on
  // SoundCloud. schema.sql checks the same shapes again.
  function parseLink(raw) {
    var text = String(raw || "").trim();
    if (!text) return null;
    var m = /^spotify:track:([A-Za-z0-9]{22})$/.exec(text);
    if (m) return { platform: "spotify", track: m[1] };
    if (/^spotify:/i.test(text)) return { error: "That Spotify link isn't a track. Open the track itself and share that." };
    if (!/^[a-z]+:\/\//i.test(text)) text = "https://" + text;
    var u;
    try { u = new URL(text); } catch (e) { return { error: "That doesn't look like a link." }; }
    var host = u.hostname.toLowerCase().replace(/^(www\.|m\.)/, "");
    var parts = u.pathname.split("/").filter(Boolean);

    if (host === "open.spotify.com" || host === "play.spotify.com") {
      if (parts[0] && /^intl-/i.test(parts[0])) parts.shift();
      if (parts[0] === "track" && SPOTIFY_ID.test(parts[1] || "")) return { platform: "spotify", track: parts[1] };
      if (["album", "playlist", "artist", "episode", "show"].indexOf(parts[0]) !== -1) {
        return { error: "That's a Spotify " + parts[0] + " link. Open the track itself and share that." };
      }
      return { error: "That Spotify link doesn't point at a track." };
    }
    if (host === "spotify.link" || host === "spoti.fi") return { error: shortLink("Spotify") };

    if (host === "youtube.com" || host === "music.youtube.com" || host === "youtube-nocookie.com") {
      var id = u.searchParams.get("v");
      if (!id && ["shorts", "embed", "live", "v"].indexOf(parts[0]) !== -1) id = parts[1];
      if (id && YOUTUBE_ID.test(id)) return { platform: "youtube", track: id };
      if (u.searchParams.get("list")) return { error: "That's a YouTube playlist. Open the one video and share that." };
      return { error: "That YouTube link doesn't point at a video." };
    }
    if (host === "youtu.be") {
      if (YOUTUBE_ID.test(parts[0] || "")) return { platform: "youtube", track: parts[0] };
      return { error: "That YouTube link doesn't point at a video." };
    }

    if (host === "soundcloud.com") {
      var user = (parts[0] || "").toLowerCase(), slug = (parts[1] || "").toLowerCase();
      if (slug === "sets") return { error: "That's a SoundCloud playlist. Open the one track and share that." };
      if (parts.length > 2 && slug && SOUNDCLOUD_PAGES.indexOf(slug) === -1) {
        return { error: "That looks like a private SoundCloud link. Only public tracks can go in the playlists." };
      }
      if (parts.length === 2 && SOUNDCLOUD_PART.test(user) && SOUNDCLOUD_PART.test(slug) &&
          SOUNDCLOUD_PAGES.indexOf(slug) === -1 && user.length <= 100 && slug.length <= 200) {
        return { platform: "soundcloud", track: user + "/" + slug };
      }
      return { error: "That SoundCloud link doesn't point at a track." };
    }
    if (host === "on.soundcloud.com") return { error: shortLink("SoundCloud") };

    return { error: "Paste a link from Spotify, YouTube or SoundCloud." };
  }

  function trackUrl(sub) {
    if (sub.platform === "spotify") return "https://open.spotify.com/track/" + sub.track;
    if (sub.platform === "youtube") return "https://www.youtube.com/watch?v=" + sub.track;
    return "https://soundcloud.com/" + sub.track;
  }

  // The service's own player, so the submitter can check it's the right
  // recording. Loaded only when a link is pasted or a track is opened.
  function embedHtml(sub) {
    var t = encodeURIComponent(sub.track);
    if (sub.platform === "spotify") {
      return '<iframe class="sub-frame" src="https://open.spotify.com/embed/track/' + t + '" height="152" loading="lazy" ' +
        'allow="clipboard-write; encrypted-media; fullscreen; picture-in-picture" title="Spotify player"></iframe>';
    }
    if (sub.platform === "youtube") {
      return '<div class="sub-frame-video"><iframe src="https://www.youtube-nocookie.com/embed/' + t + '" loading="lazy" ' +
        'allow="clipboard-write; encrypted-media; picture-in-picture" allowfullscreen title="YouTube player"></iframe></div>';
    }
    return '<iframe class="sub-frame" src="https://w.soundcloud.com/player/?url=' +
      encodeURIComponent("https://soundcloud.com/" + sub.track) + '&amp;visual=false&amp;show_comments=false" height="166" ' +
      'loading="lazy" allow="encrypted-media" title="SoundCloud player"></iframe>';
  }

  /* ---- the round ---- */

  var state = { rounds: [], round: null, mine: null, index: null, pasted: null, changing: false, timer: 0,
                service: "spotify", pickFrom: null, results: null, asked: null };

  function isOpen(r) { return !r.closed_at && Date.now() < Date.parse(r.closes_at); }

  function seasonLabel(key) {
    var s = state.index && state.index.seasons.filter(function (x) { return x.key === key; })[0];
    return s ? s.label : "Season " + String(key).replace(/^season/, "");
  }

  function when(iso) {
    return new Date(iso).toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }
  function fromNow(iso) {
    var mins = Math.round((Date.parse(iso) - Date.now()) / 60000);
    if (mins < 1) return "any moment now";
    if (mins < 60) return "in " + mins + " min";
    var hrs = Math.round(mins / 60);
    if (hrs < 36) return "in " + hrs + (hrs === 1 ? " hour" : " hours");
    var days = Math.round(hrs / 24);
    return "in " + days + " days";
  }

  function load() {
    clearTimeout(state.timer);
    // Inside the chain, so any failure lands in the catch below and says
    // so, instead of the page sitting at "Loading the round." for good.
    return Promise.resolve().then(function () {
      // a browser still holding an auth.js from before the Submit page
      if (typeof api().siteRounds !== "function") {
        throw new Error("part of the site is still the version from before an update. Reload the page.");
      }
      return api().siteRounds();
    }).then(function (rounds) {
      state.rounds = rounds || [];
      state.round = state.rounds.filter(isOpen)[0] || state.rounds[0] || null;
      var r = state.round;
      // reload when the deadline passes, so the page closes with the round
      if (r && isOpen(r)) {
        var ms = Date.parse(r.closes_at) - Date.now() + 1500;
        if (ms < 2147483647) state.timer = setTimeout(load, ms);
      }
      return r ? api().mySubmission(r.id) : null;
    }).then(function (mine) {
      state.mine = mine;
      state.changing = false;
      render();
    }).catch(function (err) {
      console.error(err);
      $("subLine").textContent = "Couldn’t load the round: " + errText(err);
    });
  }

  function render() {
    var r = state.round;
    ["subRound", "subMine", "subForm", "subList"].forEach(function (id) { $(id).hidden = true; });
    renderAdmin();
    if (!r) {
      $("subLine").textContent = "No round is open for submissions on the site yet.";
      return;
    }
    var open = isOpen(r);
    $("subLine").textContent = open
      ? "Submissions close " + when(r.closes_at) + " (" + fromNow(r.closes_at) + ")."
      : "Submissions for this round are closed.";

    var box = $("subRound");
    box.innerHTML = '<div class="sub-round-card">' +
      '<p class="sub-season">' + esc(seasonLabel(r.season_key)) + "</p>" +
      "<h2>" + esc(r.name) + "</h2>" +
      (r.prompt ? '<p class="sub-prompt">' + esc(r.prompt) + "</p>" : "") +
      '<p class="sub-count" id="subCount"></p></div>';
    box.hidden = false;
    api().submissionCount(r.id).then(function (n) {
      if (typeof n === "number") $("subCount").textContent = n + (n === 1 ? " track" : " tracks") + (open ? " in so far." : " in all.");
    }).catch(function (err) { console.error(err); });

    if (state.mine) renderMine(open);
    if (open && (!state.mine || state.changing)) renderForm();
    if (!open) renderList();
  }

  function renderMine(open) {
    var m = state.mine;
    $("subMineEmbed").innerHTML = embedHtml(m) +
      '<p class="sub-link"><a href="' + esc(trackUrl(m)) + '" target="_blank" rel="noopener">Open on ' + NAMES[m.platform] + "</a></p>";
    $("subMineActions").hidden = !open || state.changing;
    $("subMine").hidden = false;
  }

  function renderForm() {
    $("subFormTitle").textContent = state.mine ? "Change your track" : "Your pick";
    $("subCancel").hidden = !state.mine;
    $("subSend").textContent = state.mine ? "Use this track instead" : "Submit";
    $("subForm").hidden = false;
    $("subSend").disabled = !state.pasted;
  }

  function showMsg(text, kind) {
    var msg = $("subMsg");
    msg.textContent = text || "";
    msg.className = "sub-msg" + (kind ? " is-" + kind : "");
    msg.hidden = !text;
  }

  /* ---- picking a track: a pasted link, or a search result ---- */

  // The box takes either: a link is read as it's typed; anything else is
  // words to search for, on Enter or the Search button.
  function looksLikeLink(text) {
    return /^(?:[a-z]+:\/\/|spotify:|www\.|(?:open|play)\.spotify\.com|spotify\.link|spoti\.fi|youtu\.be|(?:m\.|music\.)?youtube\.com|(?:m\.|on\.)?soundcloud\.com)/i
      .test(String(text).trim());
  }

  // The chosen track, from either, previewed in its own player. The player
  // is redrawn only when the choice changes, so typing around a good link
  // doesn't reload it.
  var shownKey = "";
  function setPick(p, about) {
    state.pasted = p;
    var key = p ? p.platform + ":" + p.track : "";
    if (key !== shownKey) {
      $("subPreview").innerHTML = p ? embedHtml(p) : "";
      shownKey = key;
      gaugeFor(p, about);
    }
    $("subSend").disabled = !p;
  }

  // Estimated League Sentiment (sentiment.js) for the picked track: from
  // what the search said it is, or, for a pasted link, from the catalog
  // (a Spotify track submitted before) or, through sentiment.js, the
  // service's own oEmbed.
  var gaugeKey = "";
  function gaugeFor(p, about) {
    $("subGauge").innerHTML = "";
    gaugeKey = p ? p.platform + ":" + p.track : "";
    if (!p) return;
    var key = gaugeKey;
    PFMLSentiment.load().then(function () {
      if (about) return about;
      if (p.platform === "spotify" && PFMLSentiment.known(p.track)) return PFMLSentiment.known(p.track);
      return PFMLSentiment.aboutLink(p.platform, p.track);
    }).then(function (pick) {
      if (gaugeKey !== key || !pick) return;      // picked something else meanwhile, or nothing known
      $("subGauge").innerHTML = PFMLSentiment.gaugeHtml(PFMLSentiment.judge(pick));
    }).catch(function (err) { console.error(err); });
  }

  // What a search result is, for the gauge. Spotify says. A YouTube video's
  // title may read "Artist - Song" or "Song - Artist" ("Righteously - Anna
  // Ash" is the latter, measured 2026-10-19), so its whole title and channel
  // go in as free text and the channel stands in as the artist.
  function aboutResult(service, r) {
    if (service === "spotify") {
      return { spotifyId: r.id, title: r.title, artists: String(r.artist || "").split(", "), album: r.album };
    }
    return { title: r.title, artists: [r.artist], text: r.title + " " + r.artist };
  }

  var CHECK = "Check the player shows the right recording, then submit.";

  function onType() {
    var text = $("subLink").value;
    if (looksLikeLink(text)) {
      clearResults();
      var p = parseLink(text);
      state.pickFrom = "link";
      setPick(p && !p.error ? p : null);
      if (p && p.error) showMsg(p.error, "error");
      else if (p) showMsg(CHECK, "");
    } else if (state.pickFrom === "link") {
      // was a link, now words: that link no longer counts
      state.pickFrom = null;
      setPick(null);
      showMsg("");
    }
  }

  function resetPicker() {
    $("subLink").value = "";
    clearResults();
    state.pickFrom = null;
    setPick(null);
    showMsg("");
  }

  // Searching each service's own site, for SoundCloud (no search here yet)
  // and for when search here isn't working or YouTube's allowance is spent.
  var SEARCH_SITES = {
    spotify: function (q) { return "https://open.spotify.com/search/" + encodeURIComponent(q); },
    youtube: function (q) { return "https://www.youtube.com/results?search_query=" + encodeURIComponent(q); },
    soundcloud: function (q) { return "https://soundcloud.com/search/sounds?q=" + encodeURIComponent(q); }
  };

  function linkOut(svc, q, text) {
    clearResults();
    var msg = $("subMsg");
    msg.className = "sub-msg";
    msg.innerHTML = esc(text) + ' <a href="' + esc(SEARCH_SITES[svc](q)) + '" target="_blank" rel="noopener">Search on ' +
      NAMES[svc] + " ↗</a>";
    msg.hidden = false;
  }

  // Through supabase/functions/search-tracks, which holds the services'
  // keys and answers members only.
  function search() {
    var q = $("subLink").value.trim(), svc = state.service;
    if (!q || looksLikeLink(q)) return;
    if (svc === "soundcloud") {
      linkOut(svc, q, "SoundCloud is searched on SoundCloud itself: find the track, copy its link and paste it here.");
      return;
    }
    var asked = svc + "|" + q;
    state.asked = asked;
    showMsg("Searching " + NAMES[svc] + "…", "");
    api().searchTracks(svc, q).then(function (res) {
      if (state.asked !== asked) return;              // a newer search is under way
      if (res && res.error === "quota") {
        linkOut(svc, q, "YouTube searching here is used up for today. Search on YouTube, copy the video's link and paste it here.");
        return;
      }
      if (!res || res.error) throw new Error((res && res.error) || "no answer");
      showResults(svc, res.results || []);
    }).catch(function (err) {
      console.error(err);
      if (state.asked !== asked) return;
      linkOut(svc, q, "Search isn’t working right now. Search on " + NAMES[svc] + ", copy the link and paste it here.");
    });
  }

  function length(s) {
    return s ? Math.floor(s / 60) + ":" + (s % 60 < 10 ? "0" : "") + (s % 60) : "";
  }

  function showResults(svc, results) {
    if (!results.length) {
      clearResults();
      showMsg("Nothing found on " + NAMES[svc] + ". Try other words, or paste a link.", "");
      return;
    }
    state.results = { service: svc, items: results };
    showMsg("Pick one to hear it.", "");
    $("subResults").innerHTML = results.map(function (r, i) {
      return '<li><button type="button" class="sub-result" data-i="' + i + '" aria-pressed="false">' +
        (r.image ? '<img src="' + esc(r.image) + '" alt="" width="44" height="44" loading="lazy">' : '<span class="sub-result-noart"></span>') +
        '<span class="sub-result-text"><b>' + esc(r.title) + "</b><small>" + esc(r.artist) +
        (r.seconds ? " · " + length(r.seconds) : "") + "</small></span></button></li>";
    }).join("");
    $("subResults").hidden = false;
  }

  function clearResults() {
    state.results = null;
    $("subResults").innerHTML = "";
    $("subResults").hidden = true;
  }

  function pickResult(ev) {
    var b = ev.target.closest(".sub-result");
    if (!b || !state.results) return;
    $("subResults").querySelectorAll(".sub-result").forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
    state.pickFrom = "search";
    var r = state.results.items[+b.dataset.i];
    setPick({ platform: state.results.service, track: r.id }, aboutResult(state.results.service, r));
    showMsg(CHECK, "");
  }

  function setService(svc) {
    state.service = svc;
    $("subServices").querySelectorAll(".sub-svc").forEach(function (b) {
      b.setAttribute("aria-checked", String(b.getAttribute("data-svc") === svc));
    });
    $("subLinkLabel").textContent = svc === "soundcloud"
      ? "Paste a SoundCloud link, or search on SoundCloud"
      : "Search " + NAMES[svc] + ", or paste a link";
    $("subSearch").textContent = svc === "soundcloud" ? "Search on SoundCloud ↗" : "Search";
    if (state.pickFrom === "search") { state.pickFrom = null; setPick(null); }
    clearResults();
    showMsg("");
  }

  function send(ev) {
    ev.preventDefault();
    var r = state.round, p = state.pasted;
    if (!r || !p) return;
    $("subSend").disabled = true;
    showMsg("Sending…", "");
    api().submitTrack(r.id, p.platform, p.track).then(function (tag) {
      state.mine = { tag: tag, platform: p.platform, track: p.track };
      state.changing = false;
      resetPicker();
      render();
      $("subMine").scrollIntoView({ behavior: "smooth", block: "start" });
    }).catch(function (err) {
      showMsg(errText(err), "error");
      $("subSend").disabled = false;
    });
  }

  function withdraw() {
    if (!window.confirm("Withdraw your track? You can submit again while the round is open.")) return;
    api().withdrawSubmission(state.round.id).then(function () {
      state.mine = null;
      render();
    }).catch(function (err) { window.alert(errText(err)); });
  }

  /* ---- a closed round: every track, nobody's name ---- */

  // Built by scripts/round_playlists.py once the round has closed: the
  // shuffled order, titles, each track's copy on the other service, and the
  // two playlists. Before that, the list is by tag with no titles.
  function playlistButtons(r) {
    var out = [];
    if (r.spotify_playlist) {
      out.push('<a class="sub-btn sub-play sub-play-spotify" href="https://open.spotify.com/playlist/' +
        encodeURIComponent(r.spotify_playlist) + '" target="_blank" rel="noopener">Play on Spotify</a>');
    }
    if (r.youtube_playlist) {
      out.push('<a class="sub-btn sub-play sub-play-youtube" href="https://www.youtube.com/playlist?list=' +
        encodeURIComponent(r.youtube_playlist) + '" target="_blank" rel="noopener">Play on YouTube</a>');
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

  function renderList() {
    var r = state.round;
    var built = !!(r.spotify_playlist || r.youtube_playlist);
    $("subPlaylists").innerHTML = built
      ? '<p class="sub-play-note">The whole round, shuffled, in one tap. Same order in both apps; ' +
        "they keep playing with your phone locked (YouTube needs Premium for that).</p>" +
        '<div class="sub-actions">' + playlistButtons(r) + "</div>"
      : "";
    $("subPlaylists").hidden = !built;
    $("subListNote").textContent = built
      ? "In playlist order. Tap a track to play the round from there."
      : "Sorted by tag until the playlists are built. Tap a track to play the round from there.";
    $("subPlayer").innerHTML = "";
    $("subTracks").innerHTML = '<li class="sub-empty">Loading\u2026</li>';
    $("subList").hidden = false;
    api().roundSubmissions(r.id).then(function (rows) {
      rows = (rows || []).slice().sort(function (a, b) {
        if (a.position && b.position) return a.position - b.position;
        return a.tag < b.tag ? -1 : 1;
      });
      if (!rows.length) { $("subTracks").innerHTML = '<li class="sub-empty">No tracks were submitted.</li>'; return; }
      $("subTracks").innerHTML = rows.map(function (s, i) {
        var name = s.title
          ? '<span class="sub-track-name"><b>' + esc(s.title) + "</b>" + (s.artist ? "<small>" + esc(s.artist) + "</small>" : "") + "</span>"
          : '<span class="sub-track-where">' + NAMES[s.platform] + "</span>";
        return '<li class="sub-track">' +
          '<button type="button" class="sub-track-btn" data-i="' + i + '" aria-current="false">' +
            (s.position ? '<span class="sub-pos">' + s.position + "</span>" : "") +
            '<span class="sub-tag sub-tag-sm">' + esc(s.tag) + "</span>" + name + "</button>" +
          gapNote(s) +
          '<a class="sub-track-open" href="' + esc(trackUrl(s)) + '" target="_blank" rel="noopener">Open on ' + NAMES[s.platform] + "</a></li>";
      }).join("");
      // the round player (player.js) plays them all in this order; the list
      // marks the one playing, and a tap starts the round from that track
      var items = $("subTracks").querySelectorAll(".sub-track");
      var player = window.PFMLPlayer.mount($("subPlayer"), rows, function (playing) {
        items.forEach(function (li, i) {
          li.classList.toggle("is-playing", i === playing);
          li.querySelector(".sub-track-btn").setAttribute("aria-current", String(i === playing));
        });
      });
      $("subTracks").onclick = function (ev) {
        var b = ev.target.closest(".sub-track-btn");
        if (b) player.playAt(+b.dataset.i);
      };
    }).catch(function (err) {
      $("subTracks").innerHTML = '<li class="sub-empty">Couldn\u2019t load the tracks: ' + esc(errText(err)) + "</li>";
    });
  }

  /* ---- admin: open, edit and close a round ---- */

  function localInput(iso) {
    var d = new Date(iso), pad = function (n) { return (n < 10 ? "0" : "") + n; };
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) + "T" + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }

  function renderAdmin() {
    var me = PFML.member;
    if (!me || me.role !== "admin") { $("subAdmin").hidden = true; return; }
    var r = state.round && isOpen(state.round) ? state.round : null;
    var seasons = state.index ? state.index.seasons.slice().reverse() : [];
    var current = state.index ? state.index.currentSeason : "";
    var options = seasons.map(function (s) {
      return '<option value="' + esc(s.key) + '"' + (s.key === current ? " selected" : "") + ">" + esc(s.label) + "</option>";
    }).join("");
    var nextNum = seasons.length ? Math.max.apply(null, seasons.map(function (s) { return +String(s.key).replace(/\D/g, "") || 0; })) + 1 : 1;
    options += '<option value="season' + nextNum + '">Season ' + nextNum + " (new)</option>";

    $("subAdminBody").innerHTML =
      "<h3>" + (r ? "The open round" : "Open a round") + "</h3>" +
      '<form class="sub-admin-form" id="subAdminForm" novalidate>' +
        (r ? "" : '<label class="sub-label" for="subAdmSeason">Season</label><select class="sub-input" id="subAdmSeason">' + options + "</select>") +
        '<label class="sub-label" for="subAdmName">Round name</label>' +
        '<input class="sub-input" id="subAdmName" maxlength="120" placeholder="Round 7: Live Tracks" value="' + esc(r ? r.name : "") + '">' +
        '<label class="sub-label" for="subAdmPrompt">Prompt</label>' +
        '<textarea class="sub-input sub-textarea" id="subAdmPrompt" maxlength="2000" rows="3">' + esc(r ? r.prompt : "") + "</textarea>" +
        '<label class="sub-label" for="subAdmCloses">Submissions close (your time)</label>' +
        '<input class="sub-input" id="subAdmCloses" type="datetime-local" value="' + (r ? localInput(r.closes_at) : "") + '">' +
        '<p class="sub-msg" id="subAdmMsg" role="status" hidden></p>' +
        '<div class="sub-actions"><button type="submit" class="sub-btn">' + (r ? "Save changes" : "Open the round") + "</button>" +
          (r ? '<button type="button" class="sub-btn sub-btn-quiet" id="subAdmClose">Close submissions now</button>' : "") + "</div>" +
      "</form>";
    $("subAdmin").hidden = false;
    $("subAdminForm").addEventListener("submit", function (ev) { ev.preventDefault(); saveRound(r); });
    if (r) $("subAdmClose").addEventListener("click", function () { closeRound(r); });
  }

  function adminMsg(text) { var m = $("subAdmMsg"); m.textContent = text; m.className = "sub-msg is-error"; m.hidden = !text; }

  function saveRound(r) {
    var name = $("subAdmName").value.trim(), prompt = $("subAdmPrompt").value.trim(), closes = $("subAdmCloses").value;
    var closesAt = closes ? new Date(closes) : null;
    if (!name) return adminMsg("Give the round a name.");
    if (!closesAt || isNaN(closesAt)) return adminMsg("Pick when submissions close.");
    if (closesAt.getTime() <= Date.now()) return adminMsg("The closing time has to be in the future.");
    var fields = { name: name, prompt: prompt, closes_at: closesAt.toISOString() };
    if (!r) fields.season_key = $("subAdmSeason").value;
    var done = r ? api().updateSiteRound(r.id, fields) : api().openSiteRound(fields);
    done.then(function (rows) {
      if (!rows || !rows.length) throw new Error("Only the admin can do that.");
      return load();
    }).catch(function (err) { adminMsg(errText(err)); });
  }

  function closeRound(r) {
    if (!window.confirm("Close submissions for “" + r.name + "” now? Members won't be able to submit or change their tracks.")) return;
    api().updateSiteRound(r.id, { closed_at: new Date().toISOString() }).then(function (rows) {
      if (!rows || !rows.length) throw new Error("Only the admin can do that.");
      return load();
    }).catch(function (err) { adminMsg(errText(err)); });
  }

  /* ---- start ---- */

  function boot() {
    $("subLink").addEventListener("input", onType);
    $("subLink").addEventListener("keydown", function (ev) {
      // Enter searches; it never sends a track by surprise
      if (ev.key === "Enter") { ev.preventDefault(); search(); }
    });
    $("subSearch").addEventListener("click", search);
    $("subServices").addEventListener("click", function (ev) {
      var b = ev.target.closest(".sub-svc");
      if (b) setService(b.getAttribute("data-svc"));
    });
    $("subResults").addEventListener("click", pickResult);
    setService(state.service);
    $("subFormEl").addEventListener("submit", send);
    $("subChange").addEventListener("click", function () {
      state.changing = true;
      render();
      $("subLink").focus();
    });
    $("subCancel").addEventListener("click", function () {
      state.changing = false;
      resetPicker();
      render();
    });
    $("subWithdraw").addEventListener("click", withdraw);
    // season names for the round card and the admin's picker; the page
    // works without them
    PFML.loadJSON("index.json").then(function (index) { state.index = index; })
      .catch(function (err) { console.error(err); })
      .then(load);
  }

  PFML.ready.then(boot);
})();
