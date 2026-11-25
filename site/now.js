/* ==========================================================
   PFML - the Commissioner page's Now tab (commissioner.js draws the rest)

   What needs a commissioner, at a glance, for each season set up on the
   site: what's waiting on them (players asking to sit a round out, a
   prompt to approve, a round about to open with no prompt, DJs who can't
   send a track because they haven't joined, playlists to build), the
   round that's open and who it's still waiting on, with one-tap +1 hour,
   +1 day, Close now and Nudge, and pausing the season.

   The database holds every rule (supabase/schema.sql, commissioner
   tools): who may do what, the pause's clock, the six hours between
   nudges, and that nobody sees whose track is whose. README, Commissioner
   tools.
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
  function when(iso) { return PFML.closes(iso).at; }
  function isAdmin() { return PFML.member && PFML.member.role === "admin"; }

  var NUDGE_GAP_MS = 6 * 3600 * 1000;     // nudge_round's wait between nudges
  var SOON_MS = 3 * 864e5;                // a round opening this soon needs its prompt

  var ctx = { rounds: [], seasons: [], reload: function () {} };
  var data = null;    // what the last render loaded: pauses, turns, names, status, nudges
  var said = null;    // {key, text}: what the next redraw says went through

  /* ---- asking first, on the page itself ---- */

  // An in-page "are you sure?" under a row of buttons, instead of the
  // browser's own box (which an iPhone shows away from what it's about).
  // Resolves true for yes. The row it asks about is hidden meanwhile.
  function ask(anchor, text, yes) {
    return new Promise(function (resolve) {
      // a button in a row of buttons hides the row; one on its own (a
      // round's ✕) hides itself, and asks under its round's heading
      var row = anchor.closest(".sub-actions") || anchor;
      var spot = anchor.closest(".sub-actions") || anchor.closest(".cm-season-round-head") || anchor;
      var old = spot.parentNode.querySelector(".cn-ask");
      if (old) old.remove();
      var box = document.createElement("div");
      box.className = "cn-ask";
      box.setAttribute("role", "alertdialog");
      box.innerHTML = "<p>" + esc(text) + '</p><div class="sub-actions"><button type="button" class="sub-btn" data-ask="yes">' + esc(yes) +
        '</button><button type="button" class="sub-btn sub-btn-quiet" data-ask="no">Cancel</button></div>';
      row.hidden = true;
      spot.insertAdjacentElement("afterend", box);
      box.querySelector('[data-ask="yes"]').focus();
      box.addEventListener("click", function (ev) {
        var b = ev.target.closest("[data-ask]");
        if (!b) return;
        box.remove();
        row.hidden = false;
        resolve(b.getAttribute("data-ask") === "yes");
      });
    });
  }

  /* ---- loading ---- */

  function seasonRounds(key) {
    return ctx.rounds.filter(function (r) { return r.season_key === key; })
      .sort(function (a, b) { return Date.parse(a.opens_at) - Date.parse(b.opens_at); });
  }
  function liveRound(key) {
    return seasonRounds(key).filter(function (r) { var p = PFML.roundPhase(r); return p === "submitting" || p === "voting"; })[0] || null;
  }
  // a season still to be played: a round open or to come, or a pause set
  function running(s, pauses) {
    return seasonRounds(s.key).some(function (r) { return PFML.roundPhase(r) !== "finished"; }) ||
      pauses.some(function (p) { return p.season_key === s.key; });
  }

  function soft(p, fallback) { return p.catch(function (err) { console.error(err); return fallback; }); }

  function render(c) {
    ctx = c;
    var box = $("cmNow");
    if (!box) return;
    box.hidden = false;
    if (typeof api().pauses !== "function") { box.innerHTML = ""; return; }
    var lives = ctx.seasons.map(function (s) { return liveRound(s.key); }).filter(Boolean);
    Promise.all([
      soft(api().pauses(), []),
      soft(api().promptTurns(), []),
      soft(api().people(), {}),
      Promise.all(lives.map(function (r) { return soft(api().roundStatus(r.id), []); })),
      Promise.all(lives.map(function (r) { return soft(api().lastNudge(r.id), null); }))
    ]).then(function (res) {
      var names = {};
      Object.keys(res[2] || {}).forEach(function (u) { names[res[2][u].competitorId] = res[2][u].name; });
      data = { pauses: res[0], turns: res[1], names: names, status: {}, nudged: {} };
      lives.forEach(function (r, i) { data.status[r.id] = res[3][i]; data.nudged[r.id] = res[4][i]; });
      draw();
    });
  }

  /* ---- drawing ---- */

  function draw() {
    var box = $("cmNow");
    var seasons = ctx.seasons.filter(function (s) { return running(s, data.pauses); })
      .sort(function (a, b) { return a.key.localeCompare(b.key, undefined, { numeric: true }); });
    var needs = attention(seasons);
    // the tab's own message first, so one not about a season lands here
    box.innerHTML = "<h2>Now</h2>" + '<p class="sub-msg" id="cnMsg" role="status" hidden></p>' +
      (needs.length ? '<div class="cn-needs"><h3>Needs you</h3><ul>' + needs.join("") + "</ul></div>"
                    : '<p class="block-note cn-calm">Nothing needs you right now.</p>') +
      (seasons.length ? seasons.map(seasonHtml).join("")
        : '<p class="block-note">No season is running on the site. Set one up under <a href="#seasons">Seasons</a>.</p>');
    if (said) {
      var where = said.key && box.querySelector('[data-season="' + said.key + '"]');
      msgIn(where || $("cnMsg"), said.text, true);
      said = null;
    }
  }

  function nameOf(id) { return data.names[id] || "A player"; }

  // Everything waiting on a commissioner, most pressing first.
  function attention(seasons) {
    var out = [];
    var keys = seasons.map(function (s) { return s.key; });
    // players asking to sit a round out
    ctx.rounds.filter(function (r) { return keys.indexOf(r.season_key) !== -1 && PFML.roundPhase(r) !== "finished"; })
      .forEach(function (r) {
        (r.site_round_sitouts || []).filter(function (x) { return x.status === "asked"; }).forEach(function (x) {
          out.push('<li class="cn-need" data-round="' + esc(r.id) + '" data-player="' + esc(x.competitor_id) + '">' +
            "<span><b>" + esc(nameOf(x.competitor_id)) + "</b> asked to sit out <b>" + esc(r.name) + "</b>.</span>" +
            '<span class="sub-actions"><button type="button" class="sub-btn sub-btn-small" data-act="sit-yes">Yes</button>' +
            '<button type="button" class="sub-btn sub-btn-quiet sub-btn-small" data-act="sit-no">No</button></span></li>');
        });
      });
    // prompts sent by a round's winner, and turns still to write
    data.turns.forEach(function (t) {
      if (t.status === "sent") {
        out.push('<li class="cn-need cn-turn" data-turn="' + esc(t.round_id) + '"><span><b>' + esc(t.writers.join(" and ")) +
          "</b> sent the prompt for " + esc(t.round_label) + " (opens " + esc(when(t.opens_at)) + "). Edit it if you like, then approve it.</span>" +
          '<input class="sub-input" name="name" maxlength="120" value="' + esc(t.name) + '" aria-label="Round name">' +
          '<textarea class="sub-input sub-textarea" name="prompt" maxlength="2000" rows="3" aria-label="The prompt">' + esc(t.prompt) + "</textarea>" +
          '<span class="sub-actions"><button type="button" class="sub-btn sub-btn-small" data-act="turn-yes">Approve</button>' +
          '<button type="button" class="sub-btn sub-btn-quiet sub-btn-small" data-act="turn-drop">Drop the turn</button></span></li>');
      } else {
        out.push('<li class="cn-need" data-turn="' + esc(t.round_id) + '"><span>Waiting on <b>' + esc(t.writers.join(" and ")) +
          "</b> to write the prompt for " + esc(t.round_label) + " (they won " + esc(t.from_round_name) + "; it opens " + esc(when(t.opens_at)) + ").</span>" +
          '<span class="sub-actions"><button type="button" class="sub-btn sub-btn-quiet sub-btn-small" data-act="turn-drop">Drop the turn</button></span></li>');
      }
    });
    var turnFor = {};
    data.turns.forEach(function (t) { turnFor[t.round_id] = true; });
    seasons.forEach(function (s) {
      // a round about to open without a prompt
      seasonRounds(s.key).forEach(function (r) {
        if (PFML.roundPhase(r) === "upcoming" && !r.prompt && !turnFor[r.id] && Date.parse(r.opens_at) - Date.now() < SOON_MS) {
          out.push('<li class="cn-need"><span><b>' + esc(r.name) + "</b> opens " + esc(when(r.opens_at)) +
            ' and has no prompt yet. Write it under <a href="#seasons">Seasons</a>.</span></li>');
        }
      });
      // DJs who can't send a track: they haven't joined the site
      var live = liveRound(s.key);
      var rows = live ? data.status[live.id] || [] : [];
      var away = rows.filter(function (p) { return !p.joined && p.role === "dj" && p.sitting !== "approved"; });
      if (live && PFML.roundPhase(live) === "submitting" && away.length) {
        out.push('<li class="cn-need"><span>' + away.length + (away.length === 1 ? " DJ hasn’t" : " DJs haven’t") +
          " joined the site, so can’t send a track to " + esc(live.name) + ": " + esc(away.map(function (p) { return p.name; }).join(", ")) + "." +
          (isAdmin() ? ' Make their invite links under <a href="#people">People</a>.' : " The admin can send them invite links.") + "</span></li>");
      }
      // the admin builds a closed round's playlists, on the computer
      if (isAdmin()) {
        seasonRounds(s.key).forEach(function (r) {
          var p = PFML.roundPhase(r);
          if ((p === "voting" || p === "finished") && !r.playlists_built_at && Date.parse(r.closed_at || r.closes_at) > Date.now() - 14 * 864e5) {
            out.push('<li class="cn-need"><span>' + esc(r.name) + "’s playlists aren’t built yet: " +
              "<code>python scripts/round_playlists.py</code> on the computer.</span></li>");
          }
        });
      }
    });
    return out;
  }

  function pauseFor(key) { return data.pauses.filter(function (p) { return p.season_key === key; })[0] || null; }

  function seasonHtml(s) {
    var rounds = seasonRounds(s.key), live = liveRound(s.key), p = pauseFor(s.key);
    var next = rounds.filter(function (r) { return PFML.roundPhase(r) === "upcoming"; })[0];
    var line = live ? "Round " + (rounds.indexOf(live) + 1) + " of " + rounds.length
      : next ? (rounds.indexOf(next) ? "Next: round " + (rounds.indexOf(next) + 1) + " of " + rounds.length : "Starts " + when(next.opens_at))
      : "Finished";
    return '<article class="cn-season" data-season="' + esc(s.key) + '">' +
      '<header class="cn-season-head"><h3>' + esc(s.name) + "</h3><span>" + esc(line) + "</span></header>" +
      pauseHtml(s, p, rounds) +
      (live ? roundHtml(live, rounds, p) : next ? '<p class="block-note">No round is open. ' + esc(next.name) + " opens " + esc(when(next.opens_at)) + ".</p>" : "") +
      '<p class="sub-msg" role="status" hidden></p></article>';
  }

  /* ---- the pause ---- */

  function localInput(iso) {
    if (!iso) return "";
    var d = new Date(iso), pad = function (n) { return (n < 10 ? "0" : "") + n; };
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) + "T" + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }

  function untilText(p) { return p.resume_at ? "until " + when(p.resume_at) : "until a commissioner resumes it"; }

  function pauseHtml(s, p, rounds) {
    if (p && p.state === "paused") {
      return '<div class="cn-pause is-on"><p><b>Paused</b> since ' + esc(when(p.started_at || p.starts_at)) + ", " + esc(untilText(p)) + ". " +
          "Nothing can be sent or voted on; every deadline moves later by the pause.</p>" +
        '<div class="sub-actions"><button type="button" class="sub-btn" data-act="resume">Resume now</button>' +
          '<button type="button" class="sub-btn sub-btn-quiet" data-act="resume-time">Change when it resumes</button></div>' +
        resumeForm(p) + "</div>";
    }
    if (p) {
      return '<div class="cn-pause is-set"><p><b>A pause is set:</b> ' +
          esc(p.after_round_label ? "once " + p.after_round_label + " finishes voting" : "from " + when(p.starts_at)) + ", " + esc(untilText(p)) + ".</p>" +
        '<div class="sub-actions"><button type="button" class="sub-btn sub-btn-quiet" data-act="resume-time">Change when it resumes</button>' +
          '<button type="button" class="sub-btn sub-btn-quiet" data-act="cancel-pause">Cancel the pause</button></div>' +
        resumeForm(p) + "</div>";
    }
    var left = rounds.filter(function (r) { return PFML.roundPhase(r) !== "finished"; });
    return '<details class="cn-pause"><summary>Pause the season</summary>' +
      '<form class="sub-admin-form" data-act="pause" novalidate>' +
        '<p class="block-note">While it’s paused, nobody can send, change or take out a track, or submit a ballot. ' +
          "Drafts, comments and the voters’ lounge still work, and no reminders go out. The clock stops: the round that’s open gets back the time it had left, " +
          "and every deadline after it moves later by the pause, in whole days, so each keeps its time of day.</p>" +
        '<fieldset class="cn-choice"><legend class="sub-label">When</legend>' +
          '<label><input type="radio" name="start" value="now" checked> Now</label>' +
          '<label><input type="radio" name="start" value="at"> At a set time</label>' +
          '<input class="sub-input" type="datetime-local" name="starts_at" aria-label="Pause at (your time)">' +
          (left.length ? '<label><input type="radio" name="start" value="after"> Once a round finishes voting</label>' +
            '<select class="sub-input" name="after_round" aria-label="Which round">' + left.map(function (r) {
              return '<option value="' + esc(r.id) + '">' + esc("Round " + (rounds.indexOf(r) + 1) + ": " + r.name + " (voting closes " + when(r.voting_closes_at) + ")") + "</option>";
            }).join("") + "</select>" : "") +
        "</fieldset>" +
        '<fieldset class="cn-choice"><legend class="sub-label">Until</legend>' +
          '<label><input type="radio" name="until" value="hand" checked> A commissioner resumes it</label>' +
          '<label><input type="radio" name="until" value="at"> A set time</label>' +
          '<input class="sub-input" type="datetime-local" name="resume_at" aria-label="Resume at (your time)">' +
        "</fieldset>" +
        '<label class="sub-label" for="cnNote-' + esc(s.key) + '">A note for everyone (optional)</label>' +
        '<textarea class="sub-input sub-textarea" id="cnNote-' + esc(s.key) + '" name="note" maxlength="300" rows="2" placeholder="Happy holidays! Back after New Year’s."></textarea>' +
        '<p class="block-note">Starting it posts an announcement to the season’s players, and so does resuming.</p>' +
        '<div class="sub-actions"><button type="submit" class="sub-btn">Pause</button></div>' +
      "</form></details>";
  }

  function resumeForm(p) {
    return '<form class="sub-admin-form cn-resume-form" data-act="set-resume" hidden novalidate>' +
      '<fieldset class="cn-choice"><legend class="sub-label">Resume</legend>' +
        '<label><input type="radio" name="until" value="hand"' + (p.resume_at ? "" : " checked") + "> When a commissioner resumes it</label>" +
        '<label><input type="radio" name="until" value="at"' + (p.resume_at ? " checked" : "") + "> At a set time</label>" +
        '<input class="sub-input" type="datetime-local" name="resume_at" value="' + esc(localInput(p.resume_at)) + '" aria-label="Resume at (your time)">' +
      "</fieldset>" +
      '<div class="sub-actions"><button type="submit" class="sub-btn">Save</button></div></form>';
  }

  /* ---- the open round ---- */

  // Who a round is waiting on, from site_round_status: while it takes
  // tracks, its DJs; while it takes votes, everyone with a track and its
  // Spectators. Sitting out and not joined are their own groups.
  function standing(r, rows) {
    var phase = PFML.roundPhase(r), songs = r.songs_per_round || 1;
    var g = { in: [], out: [], away: [], sitting: [] };
    rows.forEach(function (p) {
      if (p.sitting === "approved") { g.sitting.push(p); return; }
      if (phase === "submitting") {
        if (p.role !== "dj") return;
        if (!p.joined) g.away.push(p);
        else if (p.tracks >= songs) g.in.push(p);
        else g.out.push(p.tracks ? { name: p.name + " (" + p.tracks + " of " + songs + ")" } : p);
      } else {
        if (!(p.tracks > 0 || p.role === "spectator")) return;
        if (!p.joined) g.away.push(p);
        else if (p.voted) g.in.push(p);
        else g.out.push(p);
      }
    });
    return g;
  }

  function chips(title, list, cls) {
    if (!list.length) return "";
    return '<div class="cn-group"><span class="cn-group-title">' + esc(title) + " · " + list.length + "</span>" +
      '<span class="cn-chips">' + list.map(function (p) { return '<span class="cn-chip ' + cls + '">' + esc(p.name) + "</span>"; }).join("") + "</span></div>";
  }

  function roundHtml(r, rounds, p) {
    var phase = PFML.roundPhase(r), taking = phase === "submitting";
    var deadline = taking ? r.closes_at : r.voting_closes_at;
    var g = standing(r, data.status[r.id] || []);
    var total = g.in.length + g.out.length + g.away.length;
    var paused = !!(p && p.state === "paused");
    var last = data.nudged[r.id] ? Date.parse(data.nudged[r.id]) : 0;
    var wait = last && Date.now() - last < NUDGE_GAP_MS;
    return '<div class="cn-round" data-round="' + esc(r.id) + '">' +
      '<p class="cn-kicker">Round ' + (rounds.indexOf(r) + 1) + " · " + (taking ? "Taking tracks" : "Taking votes") + "</p>" +
      "<h4>" + esc(r.name) + "</h4>" +
      '<p class="cn-deadline">' + (paused ? "Paused. " + esc(p.resume_at ? (taking ? "Submissions" : "Voting") + " then close " + when(deadline) + "." : "Its deadline is set when the season resumes.")
        : (taking ? "Submissions close " : "Voting closes ") + esc(when(deadline)) + " · " + esc(PFML.closes(deadline).left)) + "</p>" +
      '<div class="cn-meter" role="img" aria-label="' + g.in.length + " of " + total + (taking ? " in" : " voted") + '">' +
        "<b>" + g.in.length + "/" + total + "</b> " + (taking ? "in" : "voted") +
        '<span class="cn-bar"><span style="width:' + (total ? Math.round(100 * g.in.length / total) : 0) + '%"></span></span></div>' +
      chips(taking ? "Still to send" : "Still to vote", g.out, "is-out") +
      chips(taking ? "In" : "Voted", g.in, "is-in") +
      chips("Sitting out", g.sitting, "is-sitting") +
      chips("Haven’t joined the site", g.away, "is-away") +
      (paused ? "" : '<div class="sub-actions cn-actions">' +
        '<button type="button" class="sub-btn sub-btn-quiet" data-act="hour">+1 hour</button>' +
        '<button type="button" class="sub-btn sub-btn-quiet" data-act="day">+1 day</button>' +
        '<button type="button" class="sub-btn sub-btn-quiet" data-act="close">' + (taking ? "Close submissions now" : "Close voting now") + "</button>" +
        '<button type="button" class="sub-btn" data-act="nudge"' + (g.out.length && !wait ? "" : " disabled") + ">" +
          (g.out.length ? "Nudge " + g.out.length : "Everyone’s in") + "</button></div>" +
        (wait ? '<p class="block-note cn-nudged">Nudged ' + esc(when(new Date(last).toISOString())) + ". You can nudge again from " +
          esc(when(new Date(last + NUDGE_GAP_MS).toISOString())) + ".</p>"
              : '<p class="block-note cn-nudged">A nudge is a notification to everyone still out: “Still waiting on your ' + (taking ? "track" : "vote") + "”.</p>")) +
      "</div>";
  }

  /* ---- doing ---- */

  function msgIn(el, text, good) {
    var m = el.id === "cnMsg" ? el : (el.closest(".cn-season") || $("cmNow")).querySelector(".sub-msg");
    if (!m) return;
    m.textContent = text;
    m.className = "sub-msg" + (good ? " is-good" : " is-error");
    m.hidden = !text;
  }

  // A change, then the page reloaded; the redraw says it went through, in
  // the season it was about (draw() shows `said`).
  function after(el, done, okText) {
    var key = el.closest("[data-season]") && el.closest("[data-season]").getAttribute("data-season");
    return done.then(function () {
      said = okText ? { key: key, text: okText } : null;
      return ctx.reload();
    }).catch(function (err) { msgIn(el, errText(err)); });
  }

  function roundOf(el) {
    var id = el.closest("[data-round]") && el.closest("[data-round]").getAttribute("data-round");
    return ctx.rounds.filter(function (r) { return r.id === id; })[0] || null;
  }

  function seasonOf(el) {
    var key = el.closest("[data-season]") && el.closest("[data-season]").getAttribute("data-season");
    return ctx.seasons.filter(function (s) { return s.key === key; })[0] || null;
  }

  function onClick(ev) {
    var b = ev.target.closest("button[data-act]");
    if (!b) return;
    var act = b.getAttribute("data-act"), r = roundOf(b), s = seasonOf(b);
    if (act === "hour" || act === "day") {
      b.disabled = true;
      after(b, api().extendSiteRound(r.id, act === "hour" ? 1 : null, act === "day" ? 1 : null),
            (act === "hour" ? "An hour" : "A day") + " added to " + r.name + ".");
      return;
    }
    if (act === "close") {
      var taking = PFML.roundPhase(r) === "submitting";
      ask(b, taking ? "Close submissions for “" + r.name + "” now? Nobody can send or change a track after this."
                    : "Close voting for “" + r.name + "” now? Ballots not in by now don’t count.", taking ? "Close submissions" : "Close voting")
        .then(function (yes) {
          if (!yes) return;
          after(b, api().updateSiteRound(r.id, taking ? { closed_at: new Date().toISOString() } : { voting_closed_at: new Date().toISOString() }),
                taking ? "Submissions closed." : "Voting closed.");
        });
      return;
    }
    if (act === "nudge") {
      ask(b, "Send everyone still out a notification now? You can nudge this round again in 6 hours.", "Nudge them").then(function (yes) {
        if (!yes) return;
        b.disabled = true;
        api().nudgeRound(r.id).then(function (n) {
          return after(b, Promise.resolve(), "Nudged " + n + (n === 1 ? " player." : " players."));
        }).catch(function (err) { b.disabled = false; msgIn(b, errText(err)); });
      });
      return;
    }
    if (act === "resume") {
      ask(b, "Resume " + s.name + " now? Its deadlines settle at the time the pause really took, and everyone gets an announcement.", "Resume")
        .then(function (yes) { if (yes) after(b, api().resumeSeason(s.key), s.name + " is back on."); });
      return;
    }
    if (act === "cancel-pause") {
      ask(b, "Cancel the pause you set for " + s.name + "? Nothing has changed yet.", "Cancel the pause")
        .then(function (yes) { if (yes) after(b, api().resumeSeason(s.key), "The pause is cancelled."); });
      return;
    }
    if (act === "resume-time") {
      var form = b.closest(".cn-pause").querySelector(".cn-resume-form");
      form.hidden = !form.hidden;
      return;
    }
    var li = b.closest("li");
    if (act === "sit-yes" || act === "sit-no") {
      b.disabled = true;
      after(b, api().decideSitOut(li.getAttribute("data-round"), li.getAttribute("data-player"), act === "sit-yes"),
            act === "sit-yes" ? "They’re sitting it out." : "They’re playing after all.");
      return;
    }
    if (act === "turn-yes") {
      var name = li.querySelector('[name="name"]').value.trim(), prompt = li.querySelector('[name="prompt"]').value.trim();
      if (!name || !prompt) { msgIn(b, "The round needs a name and a prompt."); return; }
      b.disabled = true;
      after(b, api().decidePromptTurn(li.getAttribute("data-turn"), name, prompt), "Approved: it’s the round’s name and prompt now.");
      return;
    }
    if (act === "turn-drop") {
      ask(b, "Drop this turn? Whoever won keeps nothing to write, and you write this round’s prompt yourself under Seasons.", "Drop it")
        .then(function (yes) { if (yes) after(b, api().decidePromptTurn(li.getAttribute("data-turn"), null, null), "Dropped."); });
    }
  }

  function readTime(form, name) {
    var v = form.elements[name] && form.elements[name].value;
    var t = v ? new Date(v) : null;
    return t && !isNaN(t) ? t : null;
  }

  function onSubmit(ev) {
    var form = ev.target.closest("form[data-act]");
    if (!form) return;
    ev.preventDefault();
    var s = seasonOf(form);
    var untilAt = form.querySelector('input[name="until"]:checked').value === "at";
    var resume = untilAt ? readTime(form, "resume_at") : null;
    if (untilAt && (!resume || resume.getTime() <= Date.now())) { msgIn(form, "Pick a resume time in the future."); return; }
    if (form.getAttribute("data-act") === "set-resume") {
      after(form, api().setPauseResume(s.key, resume ? resume.toISOString() : null),
            resume ? "It resumes " + when(resume.toISOString()) + "." : "It stays paused until a commissioner resumes it.");
      return;
    }
    var start = form.querySelector('input[name="start"]:checked').value;
    var startsAt = start === "at" ? readTime(form, "starts_at") : null;
    if (start === "at" && (!startsAt || startsAt.getTime() <= Date.now())) { msgIn(form, "Pick a time in the future to pause at."); return; }
    var afterRound = start === "after" ? form.elements.after_round.value : null;
    var note = form.elements.note.value.trim();
    var btn = form.querySelector('button[type="submit"]');
    var text = start === "now" ? "Pause " + s.name + " now, " + (resume ? "until " + when(resume.toISOString()) : "until a commissioner resumes it") + "? Everyone in it gets an announcement."
      : "Set the pause for " + s.name + "? It starts on its own" + (resume ? " and ends " + when(resume.toISOString()) : "") + ".";
    ask(btn, text, start === "now" ? "Pause now" : "Set the pause").then(function (yes) {
      if (!yes) return;
      after(form, api().pauseSeason(s.key, startsAt ? startsAt.toISOString() : null, afterRound, resume ? resume.toISOString() : null, note),
            start === "now" ? s.name + " is paused." : "The pause is set.");
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var box = $("cmNow");
    if (!box) return;
    box.addEventListener("click", onClick);
    box.addEventListener("submit", onSubmit);
  });

  window.PFMLNow = { render: render };
  window.PFMLAsk = ask;
})();
