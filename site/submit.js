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

  function isOpen(r) { return PFML.roundPhase(r) === "submitting"; }
  // how many tracks a round takes from each player (a season set up on the
  // site can ask for more than one)
  function songsOf(r) { return (r && r.songs_per_round) || 1; }
  // the services a round takes (all three unless it says), and what it does
  // about a repeat already in it: off, warn, block_song or block_artist
  function servicesOf(r) { return r && r.services && r.services.length ? r.services : ["spotify", "youtube", "soundcloud"]; }
  function onlyText(r) { return servicesOf(r).map(function (s) { return NAMES[s]; }).join(" and "); }
  function ruleOf(r) { return (r && r.repeat_rule) || "warn"; }
  // the kinds of repeat a round's rule refuses
  function blockedBy(found) {
    var rule = ruleOf(state.round);
    var kinds = rule === "block_artist" ? ["track", "version", "song", "artist"] : rule === "block_song" ? ["track", "version", "song"] : [];
    return found.filter(function (k) { return kinds.indexOf(k) !== -1; });
  }

  // voting.js (voting on the site, off until the user switches it on); a
  // stand-in that's always off if it didn't load
  function voting() {
    return window.PFMLVoting || { on: function () { return false; }, render: function () {} };
  }

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
      // a round scheduled ahead isn't the page's round until it opens
      var started = state.rounds.filter(function (x) { return PFML.roundPhase(x) !== "upcoming"; });
      state.upcoming = state.rounds.filter(function (x) { return PFML.roundPhase(x) === "upcoming"; })
        .sort(function (a, b) { return Date.parse(a.opens_at) - Date.parse(b.opens_at); });
      state.round = started.filter(isOpen)[0] || started[0] || null;
      var r = state.round;
      // reload when the deadline passes, so the page closes with the round
      // (or, for a round voting here, with its voting), or when the next
      // round opens
      var until = r && isOpen(r) ? r.closes_at
        : r && voting().on(r) && PFML.roundPhase(r) === "voting" ? r.voting_closes_at
        : state.upcoming.length ? state.upcoming[0].opens_at : null;
      if (until) {
        var ms = Date.parse(until) - Date.now() + 1500;
        if (ms < 2147483647) state.timer = setTimeout(load, ms);
      }
      return r ? api().mySubmissions(r.id) : [];
    }).then(function (mine) {
      state.mine = mine || [];
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
    ["subRound", "subMine", "subForm", "subWhoBox", "subListen", "subVote"].forEach(function (id) { $(id).hidden = true; });
    // the round form is on the Commissioner page now
    $("subCommish").hidden = !PFML.member || (PFML.member.role !== "admin" && PFML.member.role !== "commissioner");
    renderNext();
    if (!r) {
      $("subLine").textContent = state.upcoming.length
        ? "No round is open yet. “" + state.upcoming[0].name + "” opens " + PFML.closes(state.upcoming[0].opens_at).at + "."
        : "No round is open for submissions on the site yet.";
      return;
    }
    var open = isOpen(r);
    var phase = voting().on(r) ? PFML.roundPhase(r) : "";
    $("subLine").textContent = open
      ? "Submissions close " + PFML.closes(r.closes_at).at + " (" + PFML.closes(r.closes_at).left + ")."
      : phase === "voting" ? "Voting is open. It closes " + PFML.closes(r.voting_closes_at).at + " (" + PFML.closes(r.voting_closes_at).left + ")."
      : phase === "finished" ? "Voting is over. The results are below."
      : "Submissions for this round are closed.";
    // a round voting here names its submitters once voting closes
    document.querySelector(".sub-anon").textContent = voting().on(r)
      ? "Nobody, the admin and commissioners included, can see who submitted which track until voting closes. Then the results show everyone’s tracks and votes."
      : "Nobody, the admin and commissioners included, can see who submitted which track.";

    var box = $("subRound");
    box.innerHTML = '<div class="sub-round-card">' +
      '<p class="sub-season">' + esc(seasonLabel(r.season_key)) + "</p>" +
      "<h2>" + esc(r.name) + "</h2>" +
      (r.prompt ? '<p class="sub-prompt">' + esc(r.prompt) + "</p>" : "") +
      '<p class="sub-count" id="subCount"></p></div>';
    box.hidden = false;
    renderWho(r, open);

    if (state.mine.length) renderMine(open);
    if (open && (state.mine.length < songsOf(r) || state.changing)) renderForm();
    if (!open) {
      // listening is on the round's own page (listen.js), for good
      $("subListenLink").href = "round?site=" + encodeURIComponent(r.id);
      $("subListen").hidden = false;
      voting().render(r, state.mine);
    }
  }

  /* ---- coming up: rounds a season set up on the site has scheduled ---- */

  function renderNext() {
    var list = state.upcoming || [];
    $("subNext").hidden = !list.length;
    $("subNextList").innerHTML = list.map(function (x) {
      return '<li><b>' + esc(x.name) + "</b><span>Opens " + esc(PFML.closes(x.opens_at).at) + "</span>" +
        (x.prompt ? "<p>" + esc(x.prompt) + "</p>" : "") + "</li>";
    }).join("");
  }

  /* ---- who's in: x/20 submitted, and who hasn't ---- */

  // Who has a track in, by player, never which track (site_round_submitters;
  // the user's call, 2026-10-23). A player who hasn't joined the site can't
  // submit there, so they're marked as such. Without the player list, or
  // before the database has the function, it falls back to a track count.
  // The players are PFML.seasonPlayers': who was picked for a season set up
  // on the site, else everyone with a track in the season's latest finished
  // round.
  function renderWho(r, open) {
    if (typeof api().roundSubmitters !== "function") { trackCount(r, open); return; }
    Promise.all([api().roundSubmitters(r.id), api().people(), PFML.seasonPlayers(r.season_key)]).then(function (res) {
      if (state.round !== r) return;
      var players = res[2];
      if (!players) { trackCount(r, open); return; }
      // one id per track: a player is in once all of the round's songs
      // from them are, and pending with how many so far until then
      var sent = {}, linked = {}, names = {}, eligible = {}, n = songsOf(r);
      (res[0] || []).forEach(function (id) { sent[id] = (sent[id] || 0) + 1; });
      Object.keys(res[1] || {}).forEach(function (u) { linked[res[1][u].competitorId] = true; names[res[1][u].competitorId] = res[1][u].name; });
      players.forEach(function (p) { eligible[p.id] = true; });
      var done = players.filter(function (p) { return sent[p.id] >= n; });
      var pending = players.filter(function (p) { return !(sent[p.id] >= n); }).map(function (p) {
        return sent[p.id] ? { id: p.id, name: p.name, note: sent[p.id] + " of " + n } : p;
      });
      // someone who sat out the last round can still send one
      var extra = Object.keys(sent).filter(function (id) { return !eligible[id]; })
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
          (linked[p.id] ? "" : '<small class="sub-not-joined">not joined yet</small>') +
          (p.note ? '<small class="sub-not-joined">' + esc(p.note) + "</small>" : "") + "</a></li>";
      }).join("") + "</ul>" : '<p class="sub-who-none">' + esc(none) + "</p>") + "</div>";
  }

  function trackCount(r, open) {
    api().submissionCount(r.id).then(function (n) {
      if (typeof n === "number") $("subCount").textContent = n + (n === 1 ? " track" : " tracks") + (open ? " in so far." : " in all.");
    }).catch(function (err) { console.error(err); });
  }

  // A note's switch: on, voters see it with the track, without the name,
  // while they vote; off (the default), it shows only once the results are
  // posted, with the name. The database holds it (site_submission_notes).
  var NOTE_WHEN = {
    "true": "On: voters see it with your track, without your name, while they vote.",
    "false": "Off: it shows once the results are posted, with your name."
  };
  function noteSwitchHtml(on) {
    return '<button type="button" class="sub-note-switch" role="switch" aria-checked="' + !!on + '">' +
      '<span class="sub-note-switch-text"><b>Show it to voters while they vote</b><small>' + NOTE_WHEN[!!on] + "</small></span>" +
      '<span class="acct-switch" aria-hidden="true"></span></button>';
  }
  function flipNoteSwitch(b) {
    var on = b.getAttribute("aria-checked") !== "true";
    b.setAttribute("aria-checked", String(on));
    b.querySelector("small").textContent = NOTE_WHEN[on];
  }
  function noteSwitchOn(b) { return !!b && b.getAttribute("aria-checked") === "true"; }

  // One track: Change and Withdraw, as ever. More than one a round: each
  // with its own Remove, and the picker below until all are in.
  function renderMine(open) {
    var n = songsOf(state.round), list = state.mine;
    $("subMineTitle").textContent = n === 1 ? "Your track" : "Your tracks";
    // what can still change only while it can
    $("subMineNote").textContent = !open ? (n === 1 ? "Your track in this round." : "Your " + list.length + " tracks in this round.")
      : n === 1 ? "It’s in. You can change or withdraw it until submissions close."
      : list.length + " of " + n + " in. You can remove one and send another until submissions close.";
    var notes = !!(state.round && state.round.votes_on_site);
    $("subMineEmbed").innerHTML = list.map(function (m) {
      return '<div class="sub-mine-item">' + embedHtml(m) +
        '<p class="sub-link"><a href="' + esc(trackUrl(m)) + '" target="_blank" rel="noopener">Open on ' + NAMES[m.platform] + "</a>" +
        (n > 1 && open ? '<button type="button" class="sub-btn sub-btn-quiet sub-remove" data-tag="' + esc(m.tag) + '">Remove</button>' : "") +
        "</p>" +
        (m.note ? '<p class="sub-mine-note">' + esc(m.note) + "</p>" +
          '<p class="sub-note-when">' + (m.note_in_voting ? "Voters see it while they vote." : "It shows once the results are posted.") + "</p>" : "") +
        (notes && open ? '<details class="sub-note-edit"><summary>' + (m.note ? "Edit your note" : "Add a note") + "</summary>" +
          '<textarea class="sub-input sub-textarea" maxlength="1000" rows="2" aria-label="Your note on this track">' + esc(m.note || "") + "</textarea>" +
          noteSwitchHtml(m.note_in_voting) +
          '<button type="button" class="sub-btn sub-btn-quiet sub-note-save" data-tag="' + esc(m.tag) + '">Save note</button></details>' : "") +
        "</div>";
    }).join("");
    $("subMineActions").hidden = n > 1 || !open || state.changing;
    $("subMine").hidden = false;
  }

  function renderForm() {
    var n = songsOf(state.round), have = state.mine.length, swapping = n === 1 && have > 0;
    // only the services the round takes
    var allowed = servicesOf(state.round);
    $("subServices").querySelectorAll(".sub-svc").forEach(function (b) { b.hidden = allowed.indexOf(b.getAttribute("data-svc")) === -1; });
    if (allowed.indexOf(state.service) === -1) setService(allowed[0]);
    $("subOnly").hidden = allowed.length === 3;
    $("subOnly").innerHTML = "<b>This round takes " + esc(onlyText(state.round)) + " tracks only.</b>";
    // a note, in a round voted on the site
    $("subNoteBox").hidden = !(state.round && state.round.votes_on_site);
    $("subFormTitle").textContent = swapping ? "Change your track" : n > 1 ? "Your pick, " + (have + 1) + " of " + n : "Your pick";
    $("subCancel").hidden = !swapping;
    $("subSend").textContent = swapping ? "Use this track instead" : "Submit";
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
    // a service this round doesn't take
    if (p && state.round && servicesOf(state.round).indexOf(p.platform) === -1) {
      showMsg("This round takes " + onlyText(state.round) + " tracks only.", "error");
      p = null;
    }
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
    // a round can turn the check off
    if (!r || !isOpen(r) || ruleOf(r) === "off" || typeof api().roundRepeats !== "function") return;
    showRepeats("checking");
    state.fp.promise.then(function (fp) {
      if (gaugeKey !== key) return null;
      return api().roundRepeats(r.id, p.platform, p.track, fp);
    }).then(function (found) {
      if (gaugeKey !== key || !found) return;
      showRepeats(found);
      gauge.found = found;
      // the gauge failing to load mustn't hide what the round check found
      // (a blocked repeat would leave Send off with no reason given)
      return PFMLSentiment.load().then(function () { if (gaugeKey === key) drawGauge(); }, function (err) { console.error(err); });
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
      // a round that blocks this kind of repeat won't take it
      var blocked = blockedBy(found);
      box.className = "sub-repeats is-found" + (blocked.length ? " is-blocked" : "");
      box.innerHTML = '<p class="sub-rep-head">Already in this round</p><ul class="sub-rep-list">' +
        REPEAT_KINDS.filter(function (k) { return found.indexOf(k[0]) !== -1; })
          .map(function (k) { return "<li>" + esc(k[1]) + "</li>"; }).join("") + "</ul>" +
        (blocked.length
          ? '<p class="sub-rep-note"><b>This round doesn’t take ' + (blocked.length === 1 && blocked[0] === "artist" ? "an artist who’s" : "a song that’s") +
            " already in it.</b> Pick another.</p>"
          : '<p class="sub-rep-note">Nobody can see whose, or which. Only tracks sent on this site are checked.</p>');
      if (blocked.length) $("subSend").disabled = true;
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
    if (!r || !mine.length || !isOpen(r) || typeof api().mySubmissionDescribed !== "function") return;
    // false while any of the reader's tracks has no description
    api().mySubmissionDescribed(r.id).then(function (done) {
      if (done === false) mine.forEach(function (m) { describe(r, m, fingerprintOf(m)); });
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
      // a link the round takes (setPick says why when it doesn't)
      else if (p && state.pasted) showMsg(CHECK, "");
    } else if (state.pickFrom === "link") {
      // was a link, now words: that link no longer counts
      state.pickFrom = null;
      setPick(null);
      showMsg("");
    }
  }

  function resetPicker() {
    $("subLink").value = "";
    $("subNote").value = "";
    $("subNoteSwitch").innerHTML = noteSwitchHtml(false);
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
    var note = r.votes_on_site ? $("subNote").value.trim() : "";
    var inVoting = noteSwitchOn($("subNoteSwitch").querySelector(".sub-note-switch"));
    // a round that blocks repeats checks the track as it goes in, so it
    // goes with its description; any other sends it, then describes it
    var blocking = ruleOf(r).indexOf("block") === 0 && typeof api().submitDescribed === "function";
    var sending = blocking
      ? fp.then(function (f) { return api().submitDescribed(r.id, p.platform, p.track, f || { song: "", names: [], text: "" }); })
      : api().submitTrack(r.id, p.platform, p.track);
    sending.then(function (tag) {
      if (!blocking) describe(r, p, fp);
      if (note) api().setSubmissionNote(r.id, tag, note, inVoting).catch(function (err) { console.error(err); });
      var entry = { tag: tag, platform: p.platform, track: p.track, note: note, note_in_voting: !!note && inVoting };
      // one song a round swaps it (the tag stays); more add to the list
      state.mine = songsOf(r) === 1 ? [entry] : state.mine.concat([entry]);
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
      state.mine = [];
      render();
    }).catch(function (err) { window.alert(errText(err)); });
  }

  // Saving a note on one of the reader's tracks.
  function saveNote(b) {
    var tag = b.getAttribute("data-tag"), text = b.parentNode.querySelector("textarea").value.trim();
    var inVoting = noteSwitchOn(b.parentNode.querySelector(".sub-note-switch"));
    b.disabled = true;
    api().setSubmissionNote(state.round.id, tag, text, inVoting).then(function () {
      state.mine.forEach(function (m) { if (m.tag === tag) { m.note = text; m.note_in_voting = !!text && inVoting; } });
      render();
    }).catch(function (err) { b.disabled = false; window.alert(errText(err)); });
  }

  // One of several tracks, by its tag; or a note's switch, or a note to save.
  function removeTrack(ev) {
    var flip = ev.target.closest(".sub-note-switch");
    if (flip) { flipNoteSwitch(flip); return; }
    var save = ev.target.closest(".sub-note-save");
    if (save) { saveNote(save); return; }
    var b = ev.target.closest(".sub-remove");
    if (!b) return;
    var tag = b.getAttribute("data-tag");
    if (!window.confirm("Remove this track? You can send another while the round is open.")) return;
    b.disabled = true;
    api().withdrawTrack(state.round.id, tag).then(function () {
      state.mine = state.mine.filter(function (m) { return m.tag !== tag; });
      render();
    }).catch(function (err) { b.disabled = false; window.alert(errText(err)); });
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
    $("subMineEmbed").addEventListener("click", removeTrack);
    $("subNoteSwitch").innerHTML = noteSwitchHtml(false);
    $("subNoteSwitch").addEventListener("click", function (ev) {
      var b = ev.target.closest(".sub-note-switch");
      if (b) flipNoteSwitch(b);
    });
    // season names for the round card; the page works without them
    PFML.loadJSON("index.json").then(function (index) { state.index = index; })
      .catch(function (err) { console.error(err); })
      .then(load);
  }

  PFML.ready.then(boot);
})();
