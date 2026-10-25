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
      describeIfMissing(state.round, mine);
    }).catch(function (err) {
      console.error(err);
      $("subLine").textContent = "Couldn’t load the round: " + errText(err);
    });
  }

  function render() {
    var r = state.round;
    ["subRound", "subMine", "subForm", "subWhoBox", "subList"].forEach(function (id) { $(id).hidden = true; });
    renderAdmin();
    if (!r) {
      $("subLine").textContent = "No round is open for submissions on the site yet.";
      return;
    }
    var open = isOpen(r);
    $("subLine").textContent = open
      ? "Submissions close " + PFML.closes(r.closes_at).at + " (" + PFML.closes(r.closes_at).left + ")."
      : "Submissions for this round are closed.";

    var box = $("subRound");
    box.innerHTML = '<div class="sub-round-card">' +
      '<p class="sub-season">' + esc(seasonLabel(r.season_key)) + "</p>" +
      "<h2>" + esc(r.name) + "</h2>" +
      (r.prompt ? '<p class="sub-prompt">' + esc(r.prompt) + "</p>" : "") +
      '<p class="sub-count" id="subCount"></p></div>';
    box.hidden = false;
    renderWho(r, open);

    if (state.mine) renderMine(open);
    if (open && (!state.mine || state.changing)) renderForm();
    if (!open) renderList();
  }

  /* ---- who's in: x/20 submitted, and who hasn't ---- */

  // The players taking part this season: everyone with a track in its
  // latest finished round (build.py, index.json). Null for a season the
  // index doesn't have yet.
  function activePlayers(seasonKey) {
    var s = state.index && state.index.seasons.filter(function (x) { return x.key === seasonKey; })[0];
    return s && s.activePlayers && s.activePlayers.length ? s.activePlayers : null;
  }

  // Who has a track in, by player, never which track (site_round_submitters;
  // the user's call, 2026-10-23). A player who hasn't joined the site can't
  // submit there, so they're marked as such. Without the player list, or
  // before the database has the function, it falls back to a track count.
  function renderWho(r, open) {
    var players = activePlayers(r.season_key);
    if (!players || typeof api().roundSubmitters !== "function") { trackCount(r, open); return; }
    Promise.all([api().roundSubmitters(r.id), api().people()]).then(function (res) {
      if (state.round !== r) return;
      var sent = {}, linked = {}, names = {}, eligible = {};
      (res[0] || []).forEach(function (id) { sent[id] = true; });
      Object.keys(res[1] || {}).forEach(function (u) { linked[res[1][u].competitorId] = true; names[res[1][u].competitorId] = res[1][u].name; });
      players.forEach(function (p) { eligible[p.id] = true; });
      var done = players.filter(function (p) { return sent[p.id]; });
      var pending = players.filter(function (p) { return !sent[p.id]; });
      // someone who sat out the last round can still send one
      var extra = (res[0] || []).filter(function (id) { return !eligible[id]; })
        .map(function (id) { return { id: id, name: names[id] || "Member" }; });
      $("subCount").innerHTML = "<b>" + done.length + "/" + players.length + "</b> submitted" +
        (extra.length ? " (and " + extra.length + " more)" : "") + (open ? "" : ", final") +
        ' &middot; <a href="#subWhoBox">See who</a>';
      // its own section, below the picker, so twenty names don't push the
      // form off a phone screen
      $("subWho").innerHTML =
        whoGroup("sent", "Submitted", done.concat(extra), linked, "Nobody yet.") +
        whoGroup("pending", open ? "Pending" : "Didn’t submit", pending, linked, open ? "Everyone’s in!" : "");
      $("subWhoBox").hidden = false;
    }).catch(function (err) { console.error(err); trackCount(r, open); });
  }

  function whoGroup(kind, title, list, linked, none) {
    if (!list.length && !none) return "";
    return '<div class="sub-who-group sub-who-' + kind + '"><h3>' + esc(title) + " <span>" + list.length + "</span></h3>" +
      (list.length ? "<ul>" + list.map(function (p) {
        return '<li><a href="profile?p=' + encodeURIComponent(p.id) + '">' + PFML.avatar(p.id, p.name) + "<span>" + esc(p.name) + "</span>" +
          (linked[p.id] ? "" : '<small class="sub-not-joined">not joined yet</small>') + "</a></li>";
      }).join("") + "</ul>" : '<p class="sub-who-none">' + esc(none) + "</p>") + "</div>";
  }

  function trackCount(r, open) {
    api().submissionCount(r.id).then(function (n) {
      if (typeof n === "number") $("subCount").textContent = n + (n === 1 ? " track" : " tracks") + (open ? " in so far." : " in all.");
    }).catch(function (err) { console.error(err); });
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
  var gauge = { pick: null, found: null };      // what the gauge knows about the current pick
  function gaugeFor(p, about) {
    $("subGauge").innerHTML = "";
    showRepeats(null);
    state.fp = null;
    gauge = { pick: null, found: null };
    gaugeKey = p ? p.platform + ":" + p.track : "";
    if (!p) return;
    var key = gaugeKey;
    var known = about ? PFMLSentiment.load().then(function () { return about; }) : aboutPick(p);
    // the round check runs whether or not the service says what the track is
    state.fp = { key: key, promise: known.catch(function () { return null; }).then(function (pick) { return fingerprint(p, pick); }) };
    checkRound(p, key);
    known.then(function (pick) {
      if (gaugeKey !== key || !pick) return;      // picked something else meanwhile, or nothing known
      gauge.pick = pick;
      drawGauge();
    }).catch(function (err) { console.error(err); });
  }

  // Past rounds, from the catalog, and this round, from the round check:
  // whichever has answered so far
  function drawGauge() {
    var result = gauge.pick ? PFMLSentiment.judge(gauge.pick) : null;
    if (gauge.found && gauge.found.length) result = PFMLSentiment.withRound(result, gauge.found);
    $("subGauge").innerHTML = result ? PFMLSentiment.gaugeHtml(result) : "";
  }

  // What a pasted link is: a Spotify track the catalog already has, or the
  // service's own oEmbed. Null when nothing says.
  function aboutPick(p) {
    return PFMLSentiment.load().then(function () {
      if (p.platform === "spotify" && PFMLSentiment.known(p.track)) return PFMLSentiment.known(p.track);
      return PFMLSentiment.aboutLink(p.platform, p.track);
    });
  }

  /* ---- repeats within this round ---- */

  // Nobody can read the round's tracks before it closes, so the page can't
  // compare them itself. Each submission keeps a fingerprint instead (the
  // song and artist names, folded the way the gauge folds them, and for a
  // YouTube or SoundCloud pick its title and channel as free text), and the
  // database's round_repeats() says which kinds of repeat a pick would be:
  // kinds only, never which track or whose. README, Submissions on the site.

  // Words a live video's title carries that a Spotify search can't use
  var NOT_IN_SONGS = /\b(live|official|video|audio|lyrics?|hd|4k|remaster(ed)?|performance|full|watch|tv|19\d\d|20\d\d)\b/gi;

  function spotifyQueries(title) {
    var base = String(title || "").replace(/[\(\[][^\)\]]*[\)\]]/g, " ");
    var out = [];
    [base, base.split("|")[0], base.split(/\s[-–—|]\s/).slice(0, 2).join(" - ")].forEach(function (part) {
      var q = part.replace(/["“”|:\-–—]/g, " ").replace(NOT_IN_SONGS, " ").replace(/\s+/g, " ").trim();
      if (q && out.indexOf(q) === -1) out.push(q);
    });
    return out;
  }

  function hasWords(hay, needle) { return !!needle && (" " + hay + " ").indexOf(" " + needle + " ") !== -1; }

  // A video's title doesn't say which part is the artist ("Righteously -
  // Anna Ash" is song first), so Spotify names the song: the first result
  // whose title and one of whose artists both appear in the free text.
  // Measured 2026-10-23 on 22 real live-video titles: 20 named, nearly all on
  // the first search; the other two fall back to the free text alone.
  function nameFromSpotify(text, title) {
    var S = PFMLSentiment, words = S.fold(text), queries = spotifyQueries(title);
    function next(i) {
      if (i >= queries.length) return null;
      return api().searchTracks("spotify", queries[i]).then(function (res) {
        var hit = ((res && res.results) || []).filter(function (r) {
          return hasWords(words, S.songKey(r.title)) &&
            S.nameList(String(r.artist || "").split(", ")).some(function (n) { return hasWords(words, n); });
        })[0];
        return hit || next(i + 1);
      });
    }
    return Promise.resolve().then(function () { return next(0); }).catch(function (err) { console.error(err); return null; });
  }

  // song, names and text, folded to the plain lowercase words the database
  // takes; each artist on its own first, then the runs a comma may have
  // split ("Earth, Wind & Fire")
  function fpOf(title, artists, text) {
    var S = PFMLSentiment;
    var names = artists.map(S.fold).concat(S.nameList(artists)).filter(function (n, i, all) {
      return n && all.indexOf(n) === i;
    }).slice(0, 12).map(function (n) { return n.slice(0, 120).trim(); });
    return { song: S.songKey(title).slice(0, 300), names: names, text: S.fold(text).slice(0, 600) };
  }

  // The fingerprint for a pick, from what's known about it (null: nothing).
  function fingerprint(p, about) {
    if (!about) return fpOf("", [], "");
    if (p.platform === "spotify") {
      if (about.artists && about.artists.length) return fpOf(about.title, about.artists, "");
      // a pasted link the catalog doesn't have: Spotify's oEmbed names no
      // artist, so find the very track by searching its title
      return api().searchTracks("spotify", about.title).then(function (res) {
        var hit = ((res && res.results) || []).filter(function (r) { return r.id === p.track; })[0];
        return hit ? fpOf(about.title, String(hit.artist || "").split(", "), "") : fpOf(about.title, [], about.title);
      }).catch(function () { return fpOf(about.title, [], about.title); });
    }
    var text = about.text || about.title || "";
    return nameFromSpotify(text, about.title).then(function (hit) {
      return hit ? fpOf(hit.title, String(hit.artist || "").split(", "), text) : fpOf("", [], text);
    });
  }

  var REPEAT_KINDS = [
    ["track", "This exact track. The site won’t take it twice."],
    ["version", "The same song by the same artist."],
    ["song", "The same song title, by another artist (maybe a cover)."],
    ["title", "A song with the same title (it may be a different song)."],
    ["artist", "The same artist, with a different song."]
  ];

  function checkRound(p, key) {
    var r = state.round;
    if (!r || !isOpen(r) || typeof api().roundRepeats !== "function") return;
    showRepeats("checking");
    state.fp.promise.then(function (fp) {
      if (gaugeKey !== key) return null;
      return api().roundRepeats(r.id, p.platform, p.track, fp);
    }).then(function (found) {
      if (gaugeKey !== key || !found) return;
      showRepeats(found);
      gauge.found = found;
      return PFMLSentiment.load().then(function () { if (gaugeKey === key) drawGauge(); });
    }).catch(function (err) {
      console.error(err);
      if (gaugeKey === key) showRepeats(null);
    });
  }

  // null hides the box; "checking"; or the kinds round_repeats() found
  function showRepeats(found) {
    var box = $("subRepeats");
    if (!found) { box.hidden = true; box.innerHTML = ""; return; }
    if (found === "checking") {
      box.className = "sub-repeats is-checking";
      box.innerHTML = "<p>Checking this round…</p>";
    } else if (!found.length) {
      box.className = "sub-repeats is-clear";
      box.innerHTML = "<p>Nothing like it among the tracks sent here so far.</p>";
    } else {
      box.className = "sub-repeats is-found";
      box.innerHTML = '<p class="sub-rep-head">Already in this round</p><ul class="sub-rep-list">' +
        REPEAT_KINDS.filter(function (k) { return found.indexOf(k[0]) !== -1; })
          .map(function (k) { return "<li>" + esc(k[1]) + "</li>"; }).join("") + "</ul>" +
        '<p class="sub-rep-note">Nobody can see whose, or which. Only tracks sent on this site are checked.</p>';
    }
    box.hidden = false;
  }

  function fingerprintOf(p) {
    return aboutPick(p).catch(function () { return null; }).then(function (pick) { return fingerprint(p, pick); });
  }

  // Saves the fingerprint of the caller's own track, so picks after it are
  // checked against it. Best effort: the submission stands either way.
  function describe(r, p, fpPromise) {
    if (typeof api().describeSubmission !== "function") return;
    fpPromise.then(function (fp) {
      return api().describeSubmission(r.id, p.platform, p.track, fp);
    }).catch(function (err) { console.error(err); });
  }

  // A track sent before the round check existed, or from a page that was out
  // of date, has no fingerprint yet: its owner's next visit adds one.
  function describeIfMissing(r, mine) {
    if (!r || !mine || !isOpen(r) || typeof api().mySubmissionDescribed !== "function") return;
    api().mySubmissionDescribed(r.id).then(function (done) {
      if (done === false) describe(r, mine, fingerprintOf(mine));
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
    var key = p.platform + ":" + p.track;
    var fp = state.fp && state.fp.key === key ? state.fp.promise : fingerprintOf(p);
    api().submitTrack(r.id, p.platform, p.track).then(function (tag) {
      describe(r, p, fp);
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
      "</form>" +
      '<div class="sub-admin-status" id="subAdmStatus"></div>';
    $("subAdmin").hidden = false;
    renderLeagueStatus();
    $("subAdminForm").addEventListener("submit", function (ev) { ev.preventDefault(); saveRound(r); });
    if (r) $("subAdmClose").addEventListener("click", function () { closeRound(r); });
  }

  // The admin's league panel: when the data was last published and the
  // latest finished round in it, and the players taking part who haven't
  // joined the site, with whether an invite link is waiting for them (never
  // the link itself: scripts/invites.py prints that). Each part shows on
  // its own; one that can't load is left out.
  function renderLeagueStatus() {
    var api_ = api();
    if (typeof api_.adminInviteStatus !== "function") return;
    var season = state.index && state.index.seasons.filter(function (s) { return s.key === state.index.currentSeason; })[0];
    var players = season && season.activePlayers || [];
    function soft(p) { return p.catch(function (err) { console.error(err); return null; }); }
    Promise.all([soft(api_.dataPublishedAt()), soft(api_.people()), soft(api_.adminInviteStatus())]).then(function (res) {
      var parts = [];
      if (res[0]) {
        parts.push("<li><b>Data published</b> " + esc(new Date(res[0]).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })) +
          (season && season.liveRound ? " · latest finished round: " + esc(season.label) + ", Round " + season.liveRound.number + ", " + esc(season.liveRound.name) : "") + "</li>");
      }
      if (res[1] && res[2] && players.length) {
        var linked = {}, waiting = {};
        Object.keys(res[1]).forEach(function (u) { linked[res[1][u].competitorId] = true; });
        res[2].forEach(function (row) { waiting[row.competitor_id] = row.made_at; });
        var out = players.filter(function (p) { return !linked[p.id]; });
        parts.push("<li><b>Not joined the site</b> " + (out.length ? out.length + "<ul>" + out.map(function (p) {
          var made = waiting[p.id];
          return "<li>" + esc(p.name) + " <small>" + (made
            ? "link made " + esc(new Date(made).toLocaleDateString(undefined, { month: "short", day: "numeric" })) + ", not used yet"
            : "no link yet") + "</small></li>";
        }).join("") + "</ul>" : "everyone taking part has joined") + "</li>");
      }
      if (!parts.length) return;
      $("subAdmStatus").innerHTML = "<h3>League status</h3><ul>" + parts.join("") + "</ul>" +
        '<p class="block-note">Make or reprint someone’s link: <code>python scripts/invites.py --player "Name"</code></p>';
    });
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
