/* ==========================================================
   PFML - submitting a track on the site (/submit)

   The open round's prompt and deadline; a box to paste a Spotify,
   YouTube or SoundCloud link, previewed in that service's own player
   before it's sent; then the member's tag, which goes in the note of
   their Music League placeholder (voting stays there). Once the round
   closes, everyone sees the list of tracks, never who sent which.

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

  var state = { rounds: [], round: null, mine: null, index: null, pasted: null, changing: false, timer: 0 };

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
    $("subTag").textContent = m.tag;
    $("subTagInline").textContent = m.tag;
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
    showPasted();
  }

  function showMsg(text, kind) {
    var msg = $("subMsg");
    msg.textContent = text || "";
    msg.className = "sub-msg" + (kind ? " is-" + kind : "");
    msg.hidden = !text;
  }

  // Redraws the preview only when the pasted track changes, so typing
  // around a good link doesn't reload the player.
  var shownKey = "";
  function showPasted() {
    var p = parseLink($("subLink").value);
    state.pasted = p && !p.error ? p : null;
    var key = state.pasted ? state.pasted.platform + ":" + state.pasted.track : "";
    if (key !== shownKey) {
      $("subPreview").innerHTML = state.pasted ? embedHtml(state.pasted) : "";
      shownKey = key;
    }
    if (p && p.error) showMsg(p.error, "error");
    else if (state.pasted) showMsg("Check the player shows the right recording, then submit.", "");
    else showMsg("");
    $("subSend").disabled = !state.pasted;
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
      $("subLink").value = "";
      showPasted();
      render();
      $("subMine").scrollIntoView({ behavior: "smooth", block: "start" });
    }).catch(function (err) {
      showMsg(errText(err), "error");
      $("subSend").disabled = false;
    });
  }

  function withdraw() {
    if (!window.confirm("Withdraw your track? You can submit again while the round is open, but you'll get a new tag.")) return;
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
      ? "In playlist order. Tap a track to play it here."
      : "Sorted by tag until the playlists are built. Tap a track to play it here.";
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
          '<button type="button" class="sub-track-btn" data-i="' + i + '" aria-expanded="false">' +
            (s.position ? '<span class="sub-pos">' + s.position + "</span>" : "") +
            '<span class="sub-tag sub-tag-sm">' + esc(s.tag) + "</span>" + name + "</button>" +
          gapNote(s) +
          '<a class="sub-track-open" href="' + esc(trackUrl(s)) + '" target="_blank" rel="noopener">Open on ' + NAMES[s.platform] + "</a>" +
          '<div class="sub-embed" hidden></div></li>';
      }).join("");
      $("subTracks").onclick = function (ev) {
        var b = ev.target.closest(".sub-track-btn");
        if (!b) return;
        var holder = b.parentNode.querySelector(".sub-embed");
        var opening = holder.hidden;
        if (opening && !holder.innerHTML) holder.innerHTML = embedHtml(rows[+b.dataset.i]);
        holder.hidden = !opening;
        b.setAttribute("aria-expanded", String(opening));
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
    $("subLink").addEventListener("input", showPasted);
    $("subFormEl").addEventListener("submit", send);
    $("subChange").addEventListener("click", function () {
      state.changing = true;
      render();
      $("subLink").focus();
    });
    $("subCancel").addEventListener("click", function () {
      state.changing = false;
      $("subLink").value = "";
      showPasted();
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
