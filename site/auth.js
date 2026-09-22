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
     api       the comment votes / reactions / replies operations
     signOut   () */

(function () {
  "use strict";

  var cfg = window.PFML_CONFIG || {};
  var INVITE_KEY = "pfml.invite";
  var BUCKET = "league-data";

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
      '<div class="gate-actions"></div></div>';
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
    PFML._inviteInMemory = code;
    // Take it out of the address bar, so it isn't copied or bookmarked and
    // reused. It's one-time anyway, but no need to leave it lying around.
    params.delete("invite");
    var rest = params.toString();
    history.replaceState(null, "", location.pathname + (rest ? "?" + rest : "") + location.hash);
  }
  function pendingInvite() {
    try { return localStorage.getItem(INVITE_KEY) || PFML._inviteInMemory || null; }
    catch (e) { return PFML._inviteInMemory || null; }
  }
  function clearInvite() {
    PFML._inviteInMemory = null;
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
  PFML.client = client;

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

  function signIn() {
    stashReturn();
    client.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: location.origin + location.pathname }
    }).then(function (res) {
      if (res.error) showGate("Sign-in didn't start", "<p>" + esc(res.error.message) + "</p>",
        [{ label: "Try again", primary: true, onClick: signIn }]);
    });
  }

  PFML.signOut = function () {
    client.auth.signOut().then(function () { location.reload(); });
  };

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
      "If you used a different Google account before, sign out and use that one.</p>",
      [{ label: "Sign out", onClick: PFML.signOut }]);
  }

  function addWhoAmI(member) {
    var bar = document.querySelector(".topbar-inner");
    if (!bar || bar.querySelector(".whoami")) return;
    var box = document.createElement("div");
    box.className = "whoami";
    box.innerHTML = '<span class="whoami-name">' + esc(member.name) + "</span>";
    var out = document.createElement("button");
    out.type = "button";
    out.className = "whoami-out";
    out.textContent = "Sign out";
    out.addEventListener("click", PFML.signOut);
    box.appendChild(out);
    bar.appendChild(box);
  }

  function letIn(member) {
    PFML.member = member;
    openSite();
    addWhoAmI(member);
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
      sessionUserId = user.id;   // the API needs it before any auth event fires
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
              [{ label: "Sign out", onClick: PFML.signOut }]);
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
      }).then(function (text) { return JSON.parse(text); });
    }
    return jsonCache[name];
  };

  /* ---- comments: votes, reactions, replies ----
     Everything is keyed by the comment id build.py writes into the season
     JSON: "<round id>|<spotify uri>|<voter id>". A round's worth is loaded
     with one prefix match per table. */

  function must(res) { if (res.error) throw new Error(res.error.message); return res.data; }

  PFML.api = {
    people: function () {
      return Promise.all([
        client.from("members").select("user_id, competitor_id").then(must),
        client.from("players").select("competitor_id, name").then(must)
      ]).then(function (r) {
        var names = {};
        r[1].forEach(function (p) { names[p.competitor_id] = p.name; });
        var byUser = {};
        r[0].forEach(function (m) { byUser[m.user_id] = { competitorId: m.competitor_id, name: names[m.competitor_id] || "Member" }; });
        return byUser;
      });
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
    me: function () { return currentUserId(); }
  };

  var sessionUserId = null;
  function currentUserId() { return sessionUserId; }
  client.auth.onAuthStateChange(function (_event, session) {
    sessionUserId = session && session.user ? session.user.id : null;
  });

  start();
})();
