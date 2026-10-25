/* PFML — members-only gate.

   Every page loads this before app.js. Nothing on the page shows, and no
   season data is fetched, until the visitor is signed in with Google AND
   that Google account is linked to a Music League player (a "member").
   The season JSON itself lives in a private Supabase bucket that only
   members can read, so this gate isn't just cosmetic: a visitor who gets
   around it still gets no data.

   Linking happens once, through an invite link (?invite=CODE) made by
   scripts/invites.py. The code is kept in localStorage across the Google
   round trip, then claimed with the claim_invite() database function.

   Exposes window.PFML:
     ready     Promise, resolves with the member once they're let in
     member    { competitorId, name, role } after ready
     loadJSON  (name) -> Promise of parsed JSON from the private bucket
     api       the comment votes / reactions / replies operations, and the
               inbox's queries
     signOut   ()
   The header's account menu and inbox live in account.js, which also adds
   the display helpers the page scripts share (avatar, reactionGlyph, when).
   Every members-only page loads auth.js, then account.js, then its page
   scripts, so those can rely on all of this being there. */

(function () {
  "use strict";

  // Addresses never show a .html ending: GitHub Pages serves /career from
  // career.html (measured, query strings included), so an old bookmark to
  // career.html still loads and the address bar is quietly tidied to
  // /career, keeping ?query and #hash. First thing on the page, so the
  // sign-in return path and invite handling below only ever see the clean
  // address. The same lines sit inline in features.html and privacy.html.
  if (/\.html$/i.test(location.pathname)) {
    history.replaceState(history.state, "",
      location.pathname.replace(/\.html$/i, "").replace(/\/index$/i, "/") + location.search + location.hash);
  }

  var cfg = window.PFML_CONFIG || {};
  var INVITE_KEY = "pfml.invite";
  var BUCKET = "league-data";

  var sessionUserId = null;   // set before any auth event fires; see start()
  var inviteInMemory = null;  // the invite, when localStorage won't hold it

  var resolveReady;
  var PFML = window.PFML = {
    ready: new Promise(function (r) { resolveReady = r; }),
    member: null,
    loadJSON: null,
    api: null,
    signOut: null
  };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* ---- the gate card ---- */

  var gate = document.createElement("div");
  gate.id = "gate";
  document.body.appendChild(gate);

  function showGate(title, bodyHtml, actions) {
    document.body.classList.remove("auth-checking");
    document.body.classList.add("gated");
    gate.hidden = false;
    gate.innerHTML =
      '<div class="gate-card">' +
      '<div class="gate-mark">PFML</div>' +
      "<h1>" + esc(title) + "</h1>" + bodyHtml +
      '<div class="gate-actions"></div>' +
      // The only thing a signed-out visitor can see, so the privacy
      // policy is linked here as well as in the page footers.
      '<p class="gate-links"><a href="privacy">Privacy and Security</a> &middot; <a href="features">Site features</a></p></div>';
    var row = gate.querySelector(".gate-actions");
    (actions || []).forEach(function (a) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = a.primary ? "gate-btn is-primary" : "gate-btn";
      b.textContent = a.label;
      b.addEventListener("click", a.onClick);
      row.appendChild(b);
    });
  }

  function openSite() {
    document.body.classList.remove("gated", "auth-checking");
    gate.hidden = true;
    gate.innerHTML = "";
  }

  // Members moving between pages used to see the "Signing you in" card on
  // every load, because the check (saved session, then a membership
  // lookup) runs before anything shows. When this browser already holds a
  // saved sign-in, show the page's own shell with a thin loading bar
  // instead; the page still has no data until the check lets them in, and
  // if it fails, the usual card replaces it. The key is supabase-js's
  // default, sb-<project ref>-auth-token (read from the pinned 2.116.0).
  function hasSavedSession() {
    try {
      var ref = new URL(cfg.supabaseUrl).hostname.split(".")[0];
      return !!localStorage.getItem("sb-" + ref + "-auth-token");
    } catch (e) {
      return false;
    }
  }

  function showChecking() {
    document.body.classList.remove("gated");
    document.body.classList.add("auth-checking");
    gate.hidden = true;
    gate.innerHTML = "";
  }

  /* ---- invite code, kept across the Google redirect ---- */

  function stashInviteFromUrl() {
    var params = new URLSearchParams(location.search);
    var code = params.get("invite");
    if (!code) return;
    try { localStorage.setItem(INVITE_KEY, code); } catch (e) { /* private mode: claimed below from memory */ }
    inviteInMemory = code;
    // Take it out of the address bar, so it isn't copied or bookmarked and
    // reused. It's one-time anyway, but no need to leave it lying around.
    params.delete("invite");
    var rest = params.toString();
    history.replaceState(null, "", location.pathname + (rest ? "?" + rest : "") + location.hash);
  }
  function pendingInvite() {
    try { return localStorage.getItem(INVITE_KEY) || inviteInMemory; }
    catch (e) { return inviteInMemory; }
  }
  function clearInvite() {
    inviteInMemory = null;
    try { localStorage.removeItem(INVITE_KEY); } catch (e) { /* nothing to clear */ }
  }

  stashInviteFromUrl();

  if (!cfg.supabaseUrl || !cfg.supabasePublishableKey) {
    showGate("Almost ready",
      "<p>The members-only login isn't configured yet. site/config.js needs the Supabase project URL and publishable key.</p>");
    return;
  }
  if (!window.supabase || !window.supabase.createClient) {
    showGate("Couldn't load sign-in",
      "<p>The sign-in library didn't load. Check your connection and reload.</p>",
      [{ label: "Reload", primary: true, onClick: function () { location.reload(); } }]);
    return;
  }

  var client = window.supabase.createClient(cfg.supabaseUrl, cfg.supabasePublishableKey, {
    auth: { flowType: "pkce", persistSession: true, autoRefreshToken: true, detectSessionInUrl: true }
  });

  /* ---- where to land after sign-in ----
     Google sends people back to the bare page (location.pathname), the
     address Supabase's redirect list is known to accept, so a round link's
     ?s=...&r=... would be lost on the way. Keep it for this tab instead and
     put it back once the session exists, before any page code runs. */

  var RETURN_KEY = "pfml.return";

  function stashReturn() {
    var rest = location.search + location.hash;
    if (!rest) return;
    try { sessionStorage.setItem(RETURN_KEY, JSON.stringify({ path: location.pathname, rest: rest })); } catch (e) { /* no storage: lands on the bare page */ }
  }
  function restoreReturn() {
    var saved = null;
    try { saved = JSON.parse(sessionStorage.getItem(RETURN_KEY) || "null"); sessionStorage.removeItem(RETURN_KEY); } catch (e) { return; }
    if (!saved || saved.path !== location.pathname || typeof saved.rest !== "string") return;
    if (location.search || location.hash) return;   // the address already says where to go
    history.replaceState(null, "", location.pathname + saved.rest);
  }

  // prompt=select_account: Google shows its account picker every time,
  // rather than quietly reusing the account the browser last signed in
  // with, so someone who picked the wrong one can pick again (asked for
  // 2026-10-24). Supabase passes it on to Google (measured that day: the
  // authorize redirect carries it to accounts.google.com).
  function signIn() {
    stashReturn();
    client.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: location.origin + location.pathname, queryParams: { prompt: "select_account" } }
    }).then(function (res) {
      if (res.error) showGate("Sign-in didn't start", "<p>" + esc(res.error.message) + "</p>",
        [{ label: "Try again", primary: true, onClick: signIn }]);
    });
  }

  PFML.signOut = function () {
    client.auth.signOut().then(function () { location.reload(); });
  };

  // Signed in with the wrong Google account: leave this site's session and
  // go straight back to Google's account picker. A pending invite stays
  // (it's kept apart from the session), so it's claimed by the account
  // picked next.
  function useAnotherAccount() {
    client.auth.signOut().then(signIn, signIn);
  }

  function membership(userId) {
    return client.from("members")
      .select("competitor_id, role, players(name)")
      .eq("user_id", userId)
      .maybeSingle()
      .then(function (res) {
        if (res.error) throw res.error;
        if (!res.data) return null;
        return {
          competitorId: res.data.competitor_id,
          role: res.data.role,
          name: res.data.players ? res.data.players.name : "Member"
        };
      });
  }

  function showSignIn() {
    var invited = !!pendingInvite();
    showGate(invited ? "You're invited" : "Members only",
      invited
        ? "<p>Sign in with Google to link your account to your Music League player. You only do this once.</p>"
        : "<p>This is the private site for our Music League. Sign in with the Google account you linked when you joined.</p>" +
          '<p class="gate-fine">New here? You need a personal invite link from the league organizer.</p>',
      [{ label: "Sign in with Google", primary: true, onClick: signIn }]);
  }

  function showNotLinked(user) {
    showGate("Not linked to a player yet",
      "<p>You're signed in as <b>" + esc(user.email || "a Google account") + "</b>, but that account isn't linked to anyone in the league.</p>" +
      "<p>Open the personal invite link the league organizer sent you, and sign in with this same Google account. " +
      "If you meant to use a different Google account, pick it here.</p>",
      [{ label: "Use a different Google account", primary: true, onClick: useAnotherAccount },
       { label: "Sign out", onClick: PFML.signOut }]);
  }

  // The header's account menu and inbox are account.js, which waits on
  // PFML.ready like the page code does.
  function letIn(member) {
    PFML.member = member;
    openSite();
    resolveReady(member);
  }

  function start() {
    // An invite still gets the card: linking an account is a real step.
    if (hasSavedSession() && !pendingInvite()) showChecking();
    else showGate("Signing you in", "<p>One moment.</p>");
    client.auth.getSession().then(function (res) {
      var session = res.data && res.data.session;
      if (!session) { showSignIn(); return; }
      var user = session.user;
      sessionUserId = user.id;
      restoreReturn();
      return membership(user.id).then(function (member) {
        var code = pendingInvite();
        if (member) { if (code) clearInvite(); letIn(member); return; }
        if (!code) { showNotLinked(user); return; }
        showGate("Linking your account", "<p>One moment.</p>");
        return client.rpc("claim_invite", { invite_code: code }).then(function (claim) {
          clearInvite();
          if (claim.error) {
            showGate("That invite didn't work",
              "<p>" + esc(claim.error.message) + "</p>" +
              "<p>Ask the league organizer for a fresh link.</p>",
              [{ label: "Use a different Google account", primary: true, onClick: useAnotherAccount },
               { label: "Sign out", onClick: PFML.signOut }]);
            return;
          }
          return membership(user.id).then(function (m) { if (m) letIn(m); else showNotLinked(user); });
        });
      });
    }).catch(function (err) {
      showGate("Something went wrong signing in", "<p>" + esc(err && err.message ? err.message : err) + "</p>",
        [{ label: "Reload", primary: true, onClick: function () { location.reload(); } },
         { label: "Sign out", onClick: PFML.signOut }]);
    });
  }

  /* ---- data: the season JSON, from the private bucket ---- */

  var jsonCache = {};
  PFML.loadJSON = function (name) {
    if (!jsonCache[name]) {
      jsonCache[name] = client.storage.from(BUCKET).download(name).then(function (res) {
        if (res.error) throw new Error(name + ": " + res.error.message);
        return res.data.text();
      }).then(function (text) { return JSON.parse(text); })
        .catch(function (err) { delete jsonCache[name]; throw err; });   // a later call can retry
    }
    return jsonCache[name];
  };

  /* ---- comments: votes, reactions, replies ----
     Everything is keyed by the comment id build.py writes into the season
     JSON: "<round id>|<spotify uri>|<voter id>". A round's worth is loaded
     with one prefix match per table. */

  function must(res) { if (res.error) throw new Error(res.error.message); return res.data; }

  var peopleCache = null;   // asked for by both the page and the inbox; once per load is plenty

  PFML.api = {
    people: function () {
      if (peopleCache) return peopleCache;
      return peopleCache = Promise.all([
        client.from("members").select("user_id, competitor_id").then(must),
        client.from("players").select("competitor_id, name").then(must)
      ]).then(function (r) {
        var names = {};
        r[1].forEach(function (p) { names[p.competitor_id] = p.name; });
        var byUser = {};
        r[0].forEach(function (m) { byUser[m.user_id] = { competitorId: m.competitor_id, name: names[m.competitor_id] || "Member" }; });
        return byUser;
      }).catch(function (err) { peopleCache = null; throw err; });
    },
    loadRound: function (roundId) {
      var prefix = roundId + "|%";
      return Promise.all([
        client.from("comment_votes").select("comment_id, user_id, value").like("comment_id", prefix).then(must),
        client.from("comment_reactions").select("comment_id, user_id, reaction").like("comment_id", prefix).then(must),
        client.from("comment_replies").select("id, comment_id, user_id, body, created_at")
          .like("comment_id", prefix).order("created_at", { ascending: true }).then(must)
      ]).then(function (r) { return { votes: r[0], reactions: r[1], replies: r[2] }; });
    },
    setVote: function (commentId, value) {
      var uid = currentUserId();
      if (!value) {
        return client.from("comment_votes").delete().eq("comment_id", commentId).eq("user_id", uid).then(must);
      }
      return client.from("comment_votes").upsert({ comment_id: commentId, user_id: uid, value: value }).then(must);
    },
    toggleReaction: function (commentId, reaction, on) {
      var uid = currentUserId();
      if (on) return client.from("comment_reactions").insert({ comment_id: commentId, user_id: uid, reaction: reaction }).then(must);
      return client.from("comment_reactions").delete()
        .eq("comment_id", commentId).eq("user_id", uid).eq("reaction", reaction).then(must);
    },
    addReply: function (commentId, body) {
      return client.from("comment_replies").insert({ comment_id: commentId, user_id: currentUserId(), body: body }).then(must);
    },
    deleteReply: function (id) {
      return client.from("comment_replies").delete().eq("id", id).then(must);
    },
    // Reactions and replies other members left on this player's own vote
    // comments, newest first. A comment id ends "|<voter id>", so a suffix
    // match finds every comment they wrote, across every round and season.
    // `limit` of each: the inbox shows that many in all, so it never needs more.
    inbox: function (competitorId, limit) {
      var suffix = "%|" + competitorId, uid = currentUserId();
      return Promise.all([
        client.from("comment_reactions").select("comment_id, user_id, reaction, created_at")
          .like("comment_id", suffix).neq("user_id", uid).order("created_at", { ascending: false }).limit(limit).then(must),
        client.from("comment_replies").select("id, comment_id, user_id, body, created_at")
          .like("comment_id", suffix).neq("user_id", uid).order("created_at", { ascending: false }).limit(limit).then(must)
      ]).then(function (r) { return { reactions: r[0], replies: r[1] }; });
    },
    // When this member last opened their inbox (null before the first
    // time). Asked for on its own, not as part of the sign-in lookup, so a
    // database without the column yet breaks only the "new" count, never
    // signing in.
    inboxSeenAt: function () {
      return client.from("members").select("inbox_seen_at").eq("user_id", currentUserId()).maybeSingle()
        .then(must).then(function (row) { return row ? row.inbox_seen_at : null; });
    },
    markInboxSeen: function () {
      return client.rpc("mark_inbox_seen").then(must);
    },
    // Every reaction on this player's comments, for the profile page's
    // tally (which leaves out any they left on their own).
    reactionsOn: function (competitorId) {
      return client.from("comment_reactions").select("comment_id, user_id, reaction")
        .like("comment_id", "%|" + competitorId).then(must);
    },
    // ---- submitting on the site (README, Submissions on the site) ----
    // Rounds opened on the site, newest first.
    siteRounds: function () {
      // newest opening first; a season set up on the site lays its rounds
      // out ahead, so there can be many not opened yet
      return client.from("site_rounds").select("id, season_key, name, prompt, opens_at, closes_at, closed_at, created_at, spotify_playlist, youtube_playlist, " +
          "votes_on_site, voting_closes_at, voting_closed_at, point_budget, max_per_track, nonvoters_keep_points")
        .order("opens_at", { ascending: false }).limit(100).then(must);
    },
    // The caller's own track for a round, or null. Nothing else on the
    // site can tell whose track is whose.
    mySubmission: function (roundId) {
      return client.rpc("my_submission", { p_round: roundId }).then(must)
        .then(function (rows) { return rows && rows.length ? rows[0] : null; });
    },
    // Resolves to the submission's tag (the same one again on a change).
    submitTrack: function (roundId, platform, track) {
      return client.rpc("submit_track", { p_round: roundId, p_platform: platform, p_track: track }).then(must);
    },
    withdrawSubmission: function (roundId) {
      return client.rpc("withdraw_submission", { p_round: roundId }).then(must);
    },
    submissionCount: function (roundId) {
      return client.rpc("site_submission_count", { p_round: roundId }).then(must);
    },
    // A pick's fingerprint (folded song, artist names, free text; see
    // submit.js), saved for the caller's own track so later picks can be
    // checked against it, and the check itself: which kinds of repeat a
    // pick would be in the round, never which track or whose.
    describeSubmission: function (roundId, platform, track, fp) {
      return client.rpc("describe_submission", { p_round: roundId, p_platform: platform, p_track: track,
        p_song: fp.song, p_names: fp.names, p_text: fp.text }).then(must);
    },
    // The admin's league panel: players with an unused invite link and when
    // it was made (never the link), and when the data was last published
    // (the time index.json was uploaded to the members-only bucket).
    adminInviteStatus: function () {
      return client.rpc("admin_invite_status").then(must);
    },
    dataPublishedAt: function () {
      return client.storage.from("league-data").list("", { limit: 100 }).then(must).then(function (files) {
        var index = (files || []).filter(function (f) { return f.name === "index.json"; })[0];
        return index ? index.updated_at || index.created_at || null : null;
      });
    },
    // The player ids of everyone with a track in the round, in id order:
    // who, never which track (the user's call, 2026-10-23).
    roundSubmitters: function (roundId) {
      return client.rpc("site_round_submitters", { p_round: roundId }).then(must);
    },
    mySubmissionDescribed: function (roundId) {
      return client.rpc("my_submission_described", { p_round: roundId }).then(must);
    },
    roundRepeats: function (roundId, platform, track, fp) {
      return client.rpc("round_repeats", { p_round: roundId, p_platform: platform, p_track: track,
        p_song: fp.song, p_names: fp.names, p_text: fp.text }).then(must);
    },
    // Readable only once the round has closed (row level security).
    roundSubmissions: function (roundId) {
      return client.from("site_submissions").select("id, tag, platform, track, position, title, artist, spotify_match, youtube_match").eq("round_id", roundId).then(must);
    },
    // Voting on the site (README, Voting on the site). The caller's ballot:
    // [{submission, points, comment}], replacing any earlier one, while
    // voting is open; the database checks every rule again.
    castBallot: function (roundId, ballot) {
      return client.rpc("cast_ballot", { p_round: roundId, p_ballot: ballot }).then(must);
    },
    myBallot: function (roundId) {
      return client.rpc("my_ballot", { p_round: roundId }).then(must);
    },
    // Player ids of everyone who has voted: who, never how.
    roundVoters: function (roundId) {
      return client.rpc("site_round_voters", { p_round: roundId }).then(must);
    },
    // Only once voting has closed: each track's submitter and score, and
    // every vote and comment with who gave it. Empty before.
    roundResults: function (roundId) {
      return client.rpc("site_round_results", { p_round: roundId }).then(must);
    },
    roundVotes: function (roundId) {
      return client.rpc("site_round_votes", { p_round: roundId }).then(must);
    },
    // Track search on the Submit page, through the search-tracks Edge
    // Function (supabase/functions/), which holds the services' keys.
    // Resolves to {results: [...]} or {error: "quota" | ...}.
    searchTracks: function (service, q) {
      return client.functions.invoke("search-tracks", { body: { service: service, q: q } }).then(function (res) {
        if (res.error) throw res.error;
        return res.data;
      });
    },
    // Notifications on this device (README, Reminders): where the push
    // service can reach it, kept with the member's account; and a test,
    // sent by the send-reminders Edge Function to the caller's own devices.
    savePushSubscription: function (endpoint, p256dh, auth) {
      return client.rpc("save_push_subscription", { p_endpoint: endpoint, p_p256dh: p256dh, p_auth: auth }).then(must);
    },
    removePushSubscription: function (endpoint) {
      return client.rpc("remove_push_subscription", { p_endpoint: endpoint }).then(must);
    },
    // Which kinds of notification this member wants: one row, all true
    // unless they turned some off; and one switch at a time.
    myNotificationChoices: function () {
      return client.rpc("my_notification_choices").then(must);
    },
    setNotificationChoice: function (kind, on) {
      return client.rpc("set_notification_choice", { p_kind: kind, p_on: on }).then(must);
    },
    testPush: function () {
      return client.functions.invoke("send-reminders", { body: { test: true } }).then(function (res) {
        if (res.error) throw res.error;
        return res.data;
      });
    },
    // Admin only (row level security): open a round, or change one.
    openSiteRound: function (fields) {
      return client.from("site_rounds").insert(fields).select("id").then(must);
    },
    updateSiteRound: function (roundId, fields) {
      return client.from("site_rounds").update(fields).eq("id", roundId).select("id").then(must);
    },
    // Seasons set up on the site (README, Seasons on the site), with who's
    // playing each.
    siteSeasons: function () {
      return client.from("site_seasons").select("key, name, description, point_budget, max_per_track, nonvoters_keep_points, " +
          "timing, submit_days, vote_days, created_at, site_season_players(competitor_id)")
        .order("key").then(must);
    },
    // Who's playing a season set up on the site, by name; [] for any other.
    seasonRoster: function (seasonKey) {
      return client.from("site_season_players").select("competitor_id, players(name)").eq("season_key", seasonKey).then(must)
        .then(function (rows) {
          return (rows || []).map(function (r) { return { id: r.competitor_id, name: r.players ? r.players.name : "Player" }; })
            .sort(function (a, b) { return a.name.localeCompare(b.name); });
        });
    },
    // Every player the league has had, joined the site or not.
    allPlayers: function () {
      return client.from("players").select("competitor_id, name").then(must);
    },
    createSiteSeason: function (season) {
      return client.rpc("create_site_season", { p: season }).then(must);
    },
    updateSiteSeason: function (key, fields) {
      return client.rpc("update_site_season", { p_key: key, p: fields }).then(must);
    },
    addSiteSeasonRound: function (key, name, prompt) {
      return client.rpc("add_site_season_round", { p_key: key, p_name: name, p_prompt: prompt }).then(must);
    },
    moveSiteSeasonRound: function (roundId, earlier) {
      return client.rpc("move_site_season_round", { p_round: roundId, p_earlier: earlier }).then(must);
    },
    removeSiteSeasonRound: function (roundId) {
      return client.rpc("remove_site_season_round", { p_round: roundId }).then(must);
    },
    setSiteSeasonPlayers: function (key, ids) {
      return client.rpc("set_site_season_players", { p_key: key, p_players: ids }).then(must);
    },
    // Each member's role, for the admin's Commissioners list.
    memberRoles: function () {
      return client.from("members").select("competitor_id, role").then(must);
    },
    // The admin makes a member a commissioner, or a member again.
    setCommissioner: function (competitorId, on) {
      return client.rpc("set_commissioner", { p_competitor: competitorId, p_on: on }).then(must);
    },
    me: function () { return currentUserId(); }
  };

  function currentUserId() { return sessionUserId; }
  client.auth.onAuthStateChange(function (_event, session) {
    sessionUserId = session && session.user ? session.user.id : null;
  });

  start();
})();
