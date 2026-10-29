/* ==========================================================
   PFML - seasons set up on the site, on the Commissioner page

   Setting one up, in steps (Details, Songs + Votes, Timing, Players,
   Rounds), and then running it: its details, rules and timing, its rounds
   (add, rename, reorder or remove one that hasn't opened), and who's
   playing. Every season set up here votes on pfml.fun (the user's call,
   2026-10-25). commissioner.js loads the rounds and the seasons and hands
   them over (PFMLSeasons.render).

   Everyone playing is a DJ (sends tracks and votes) or a Spectator (votes
   only), for the season, and any round can change that while it still
   takes tracks; a round can also name who wrote its prompt (asked
   2026-10-29; README, DJs and Spectators). Players comes before Rounds so
   each round starts from everyone's season role.

   The database lays the rounds out and holds every rule (supabase/schema.sql,
   seasons on the site); the schedule shown before a season is created is a
   preview, worked out the same way. README, Seasons on the site.
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

  var STEPS = ["Details", "Songs + Votes", "Timing", "Players", "Rounds"];
  var PLAYERS_STEP = 3, ROUNDS_STEP = 4;
  var ROLES = [["dj", "DJ"], ["spectator", "Spectator"]];
  var TIMING = {
    steady: { name: "Steady", lines: ["Every deadline holds, even when everyone's done early.", "Rounds open and close on schedule."],
              useful: "you want the same rhythm every week." },
    accelerated: { name: "Accelerated", lines: ["Submissions close as soon as everyone playing has a track in, and voting as soon as everyone has voted.",
                                                 "The next round still opens at its scheduled time."],
                   useful: "you want playlists and results as soon as possible, on a steady schedule." },
    speedy: { name: "Speedy", lines: ["Like Accelerated, and the next round opens as soon as voting closes.",
                                      "The rest of the season moves up by the time saved."],
              useful: "your league is quick and wants to keep moving." }
  };

  var ctx = { rounds: [], seasons: [], index: null, reload: function () {} };
  var wizard = null;          // the season being set up, or null
  var people = null;          // { players: [{id, name, joined}] }, loaded once

  /* ---- shared bits ---- */

  function options(values, chosen, label) {
    return values.map(function (v) {
      return '<option value="' + esc(v) + '"' + (String(v) === String(chosen) ? " selected" : "") + ">" + esc(label ? label(v) : v) + "</option>";
    }).join("");
  }
  function range(a, b) { var out = []; for (var i = a; i <= b; i++) out.push(i); return out; }
  function days(n) { return n + (n === 1 ? " day" : " days"); }

  // "No limit" stores the budget itself, the most a track could get anyway
  function maxOptions(budget, max) {
    var picked = max >= budget ? "none" : max;
    return '<option value="none"' + (picked === "none" ? " selected" : "") + ">No limit</option>" +
      options(range(1, Math.min(10, budget - 1)), picked, function (n) { return n + (n === 1 ? " point" : " points"); });
  }

  // Downvotes on one song: "No per-song limit" stores all of them; with no
  // downvotes at all, there's nothing to choose.
  function downMaxOptions(down, max) {
    if (!down) return '<option value="0">No downvotes</option>';
    var picked = max >= down ? "none" : max;
    return '<option value="none"' + (picked === "none" ? " selected" : "") + ">No per-song limit</option>" +
      options(range(1, Math.min(5, down - 1)), picked, function (n) { return n + (n === 1 ? " downvote" : " downvotes"); });
  }

  // Which services a round takes and what it does about a repeat already in
  // it, for a season, a round in it, or a round opened on its own
  // (commissioner.js uses these too: PFMLSeasons.ruleFields, readRules).
  var SERVICES = [["spotify", "Spotify"], ["youtube", "YouTube"], ["soundcloud", "SoundCloud"]];
  var RULES = [["off", "Off: no repeat check"], ["warn", "Warn about a repeat"], ["block_song", "Block the same song"],
               ["block_artist", "Block the same song or artist"]];
  function ruleFields(s, id) {
    var services = s.services || ["spotify", "youtube", "soundcloud"];
    return '<fieldset class="cm-checks-box"><legend class="sub-label">Services allowed</legend><div class="cm-services">' +
      SERVICES.map(function (x) {
        return '<label class="cm-check"><input type="checkbox" name="services" value="' + x[0] + '"' +
          (services.indexOf(x[0]) !== -1 ? " checked" : "") + "><span>" + x[1] + "</span></label>";
      }).join("") + "</div></fieldset>" +
      '<label class="sub-label" for="' + id + '-repeat">Repeats within a round</label>' +
      '<select class="sub-input" id="' + id + '-repeat" name="repeat_rule">' +
        RULES.map(function (x) { return '<option value="' + x[0] + '"' + (x[0] === (s.repeat_rule || "warn") ? " selected" : "") + ">" + x[1] + "</option>"; }).join("") +
      "</select>";
  }
  // { services, repeat_rule }, or { error } when no service is ticked
  function readRules(form) {
    var services = Array.prototype.filter.call(form.querySelectorAll('input[name="services"]'), function (b) { return b.checked; })
      .map(function (b) { return b.value; });
    if (!services.length) return { error: "Tick at least one service." };
    return { services: services, repeat_rule: form.elements.repeat_rule.value };
  }

  // The Songs + Votes settings a form holds now.
  function readVotes(f) {
    var budget = +f.point_budget.value, down = +f.downvotes.value;
    return { songs_per_round: +f.songs_per_round.value, point_budget: budget,
             max_per_track: f.max_per_track.value === "none" ? budget : Math.min(+f.max_per_track.value, budget),
             downvotes: down,
             max_down_per_track: !down ? 0 : f.max_down_per_track.value === "none" ? down : Math.min(+f.max_down_per_track.value, down),
             nonvoters_keep_points: f.nonvoters_keep_points.value === "true" };
  }

  function seasonRounds(key) {
    return ctx.rounds.filter(function (r) { return r.season_key === key; })
      .sort(function (a, b) { return Date.parse(a.opens_at) - Date.parse(b.opens_at); });
  }

  function nextKey() {
    var nums = (ctx.index ? ctx.index.seasons : []).concat(ctx.seasons).map(function (s) { return +String(s.key).replace(/\D/g, "") || 0; });
    return "season" + Math.max(4, Math.max.apply(null, nums.concat([0])) + 1);
  }

  function loadPeople() {
    if (people) return Promise.resolve(people);
    return Promise.all([api().allPlayers(), api().people()]).then(function (res) {
      var joined = {};
      Object.keys(res[1] || {}).forEach(function (u) { joined[res[1][u].competitorId] = true; });
      people = { players: (res[0] || []).map(function (p) { return { id: p.competitor_id, name: p.name, joined: !!joined[p.competitor_id] }; })
        .sort(function (a, b) { return a.name.localeCompare(b.name); }) };
      return people;
    });
  }

  // The schedule the database will lay out (create_site_season): round 1's
  // submissions close at the first playlist, each round opens when the one
  // before closes voting. Local days, so it shows the same times of day.
  function addDays(d, n) { var x = new Date(d.getTime()); x.setDate(x.getDate() + n); return x; }
  function schedule(firstClose, count, submitDays, voteDays) {
    var out = [], closes = firstClose, opens;
    for (var i = 0; i < count; i++) {
      if (i === 0) opens = new Date(Math.max(Date.now(), addDays(closes, -submitDays).getTime()));
      else { opens = addDays(closes, voteDays); closes = addDays(opens, submitDays); }
      out.push({ opens: opens, closes: closes, voting: addDays(closes, voteDays) });
    }
    return out;
  }

  // seasonRole, in a round's roles: the role it starts from
  function roleSelect(name, role, label, seasonRole) {
    return '<select class="sub-input cm-role" name="' + name + '" aria-label="' + esc(label) + '"' +
      (seasonRole ? ' data-season="' + seasonRole + '"' : "") + ">" +
      ROLES.map(function (x) { return '<option value="' + x[0] + '"' + (x[0] === role ? " selected" : "") + ">" + x[1] + "</option>"; }).join("") +
      "</select>";
  }

  // Who's playing, ticked, each with their role for the season (roles:
  // {id: "spectator"}; DJ otherwise).
  function checklist(chosen, roles) {
    return people.players.map(function (p) {
      return '<div class="cm-player"><label class="cm-check"><input type="checkbox" name="player" value="' + esc(p.id) + '"' +
        (chosen.indexOf(p.id) !== -1 ? " checked" : "") + "><span>" + esc(p.name) + "</span>" +
        (p.joined ? "" : "<small>not on the site yet</small>") + "</label>" +
        roleSelect("role-" + p.id, roles[p.id] || "dj", p.name + "’s role") + "</div>";
    }).join("");
  }

  // [{id, role}] for every ticked player in a form
  function readRoster(form) {
    return Array.prototype.filter.call(form.querySelectorAll('input[name="player"]'), function (b) { return b.checked; })
      .map(function (b) { return { id: b.value, role: form.elements["role-" + b.value].value }; });
  }
  function rosterLine(list) {
    var dj = list.filter(function (p) { return p.role === "dj"; }).length, sp = list.length - dj;
    return list.length + " playing: " + dj + (dj === 1 ? " DJ" : " DJs") + ", " + sp + (sp === 1 ? " Spectator" : " Spectators");
  }
  function nameOf(id) {
    var p = people.players.filter(function (x) { return x.id === id; })[0];
    return p ? p.name : "a player";
  }
  function names(ids) {
    var list = ids.map(nameOf).sort();
    return list.length < 2 ? list.join("") : list.slice(0, -1).join(", ") + " and " + list[list.length - 1];
  }

  // Who wrote a round's prompt: any members who've joined the site, more
  // than one when they wrote it together.
  function promptersField(chosen) {
    return '<details class="cm-people-pick"><summary>Prompt by: <span data-sum="prompters">' + esc(chosen.length ? names(chosen) : "nobody named") + "</span></summary>" +
      '<div class="cm-checks">' + people.players.filter(function (p) { return p.joined; }).map(function (p) {
        return '<label class="cm-check"><input type="checkbox" name="prompter" value="' + esc(p.id) + '"' +
          (chosen.indexOf(p.id) !== -1 ? " checked" : "") + "><span>" + esc(p.name) + "</span></label>";
      }).join("") + "</div></details>";
  }
  function readPrompters(form) {
    return Array.prototype.filter.call(form.querySelectorAll('input[name="prompter"]'), function (b) { return b.checked; })
      .map(function (b) { return b.value; });
  }

  // A round's roles: everyone playing, starting from their season role
  // (season: [{id, role}]; own: {id: role} where the round differs).
  function rolesField(season, own) {
    var changed = changedRoles(season, own);
    return '<details class="cm-people-pick"><summary>Roles this round: <span data-sum="roles">' + esc(rolesSummary(changed)) + "</span></summary>" +
      '<p class="block-note">Everyone starts with their season role. A DJ who has sent a track stays a DJ.</p>' +
      '<div class="cm-checks">' + season.slice().sort(function (a, b) { return nameOf(a.id).localeCompare(nameOf(b.id)); }).map(function (p) {
        return '<div class="cm-player cm-player-role"><span>' + esc(nameOf(p.id)) + "</span>" +
          roleSelect("rrole-" + p.id, own[p.id] || p.role, nameOf(p.id) + "’s role this round", p.role) + "</div>";
      }).join("") + "</div></details>";
  }
  // {id: role} for the players whose role this round isn't their season's
  function changedRoles(season, own) {
    var out = {};
    season.forEach(function (p) { if (own[p.id] && own[p.id] !== p.role) out[p.id] = own[p.id]; });
    return out;
  }
  function rolesSummary(changed) {
    var ids = Object.keys(changed);
    if (!ids.length) return "everyone’s season role";
    var sp = ids.filter(function (id) { return changed[id] === "spectator"; }), dj = ids.filter(function (id) { return changed[id] === "dj"; });
    return (sp.length ? names(sp) + (sp.length === 1 ? " a Spectator" : " Spectators") : "") + (sp.length && dj.length ? "; " : "") +
      (dj.length ? names(dj) + (dj.length === 1 ? " a DJ" : " DJs") : "");
  }
  // {id: role} from a round's roles field, only where it isn't the season's
  // (form: a form, or the roles' own <details>, which has no .elements)
  function readRoundRoles(form, season) {
    var own = {};
    season.forEach(function (p) { var el = form.querySelector('select[name="rrole-' + p.id + '"]'); if (el) own[p.id] = el.value; });
    return changedRoles(season, own);
  }
  // Every player's role for the round, as the database takes it
  function fullRoles(season, changed) {
    var out = {};
    season.forEach(function (p) { out[p.id] = changed[p.id] || p.role; });
    return out;
  }
  function seasonRoster(s) {
    return (s.site_season_players || []).map(function (p) { return { id: p.competitor_id, role: p.role || "dj" }; });
  }
  function ownRoles(r) {
    var own = {};
    (r.site_round_roles || []).forEach(function (x) { own[x.competitor_id] = x.role; });
    return own;
  }
  function prompterIds(r) { return (r.site_round_prompters || []).map(function (x) { return x.competitor_id; }); }

  /* ---- render ---- */

  function render(c) {
    ctx = c;
    var box = $("cmSeasons");
    box.hidden = false;
    var list = ctx.seasons.slice().sort(function (a, b) { return b.key.localeCompare(a.key, undefined, { numeric: true }); });
    box.innerHTML = "<h2>Seasons</h2>" +
      '<p class="block-note">A season set up here runs on pfml.fun from start to finish: submitting, voting and results. ' +
      "Its rounds open on their own, on schedule.</p>" +
      list.map(seasonPanel).join("") +
      (wizard ? '<div class="cm-wizard" id="cmWizard"></div>'
              : '<div class="sub-actions"><button type="button" class="sub-btn" data-act="new">Set up a new season</button></div>') +
      '<p class="sub-msg" id="cmSeasonsMsg" role="status" hidden></p>';
    if (wizard) drawWizard();
  }

  function say(text, good) {
    var m = $("cmSeasonsMsg");
    m.textContent = text;
    m.className = "sub-msg" + (good ? " is-good" : " is-error");
    m.hidden = !text;
  }

  /* ---- a season: where it is, and running it ---- */

  function statusLine(s, rounds) {
    var live = rounds.filter(function (r) { var p = PFML.roundPhase(r); return p === "submitting" || p === "voting"; })[0];
    var next = rounds.filter(function (r) { return PFML.roundPhase(r) === "upcoming"; })[0];
    if (live) {
      var n = rounds.indexOf(live) + 1;
      return "Round " + n + " of " + rounds.length + " · " + (PFML.roundPhase(live) === "submitting"
        ? "submissions close " + when(live.closes_at) : "voting closes " + when(live.voting_closes_at));
    }
    if (next) return (rounds.indexOf(next) ? "Next: round " + (rounds.indexOf(next) + 1) + " opens " : "Starts ") + when(next.opens_at);
    return rounds.length ? "Finished" : "No rounds yet";
  }

  function seasonPanel(s) {
    var rounds = seasonRounds(s.key);
    return '<details class="cm-season" data-season="' + esc(s.key) + '">' +
      '<summary><span class="cm-round-name">' + esc(s.name) + "</span><small>" + esc(statusLine(s, rounds)) + " · " +
        esc(rosterLine(seasonRoster(s))) + " · " + esc(TIMING[s.timing].name) + "</small></summary>" +
      '<div class="cm-season-body">' +
        "<h3>Rounds</h3>" +
        '<ol class="cm-season-rounds">' + rounds.map(function (r, i) { return roundRow(r, i, rounds); }).join("") + "</ol>" +
        '<form class="sub-admin-form cm-add-round" data-act="add-round">' +
          '<label class="sub-label" for="cmAdd-' + esc(s.key) + '">Add a round at the end</label>' +
          '<input class="sub-input" id="cmAdd-' + esc(s.key) + '" name="name" maxlength="120" placeholder="Theme name">' +
          '<textarea class="sub-input sub-textarea" name="prompt" maxlength="2000" rows="2" placeholder="Theme description" aria-label="Theme description"></textarea>' +
          '<div data-fill="new-round"></div>' +
          '<div class="sub-actions"><button type="submit" class="sub-btn sub-btn-quiet">Add round</button></div>' +
        "</form>" +
        "<h3>Settings</h3>" +
        '<form class="sub-admin-form" data-act="settings">' + settingsFields(s, "cmSet-" + s.key) +
          '<p class="block-note">Rules reach every round whose submissions haven’t closed. Songs a round, and days to submit and vote, reach the rounds that haven’t opened.</p>' +
          '<div class="sub-actions"><button type="submit" class="sub-btn">Save settings</button></div>' +
        "</form>" +
        "<h3>Players</h3>" +
        '<p class="block-note">DJs send tracks and vote; Spectators vote and comment on every track, and never send one. ' +
          "A change reaches the rounds still taking tracks, and the ones to come; a DJ with a track in a round stays a DJ in it.</p>" +
        '<form class="sub-admin-form" data-act="players"><div class="cm-checks" data-players="' + esc(s.key) + '">' +
          '<p class="block-note">Loading the players.</p></div>' +
          '<div class="sub-actions"><button type="submit" class="sub-btn sub-btn-quiet">Save players</button></div></form>' +
        '<p class="sub-msg" role="status" hidden></p>' +
      "</div></details>";
  }

  function roundRow(r, i, rounds) {
    var phase = PFML.roundPhase(r), upcoming = phase === "upcoming";
    var dates = upcoming ? "Opens " + when(r.opens_at) + " · submissions close " + when(r.closes_at)
      : phase === "submitting" ? "Submissions close " + when(r.closes_at)
      : phase === "voting" ? "Voting closes " + when(r.voting_closes_at)
      : "Finished " + when(r.voting_closed_at || r.voting_closes_at);
    var canUp = upcoming && i > 0 && PFML.roundPhase(rounds[i - 1]) === "upcoming";
    var canDown = upcoming && i < rounds.length - 1;
    return '<li class="cm-season-round" data-round="' + esc(r.id) + '">' +
      '<div class="cm-season-round-head"><span><b>' + (i + 1) + ". " + esc(r.name) + "</b><small>" + esc(dates) + "</small>" +
        '<small data-people-round="' + esc(r.id) + '"></small></span>' +
        (upcoming ? '<span class="cm-move">' +
          '<button type="button" class="cm-icon" data-act="up" aria-label="Move ' + esc(r.name) + ' earlier"' + (canUp ? "" : " disabled") + ">↑</button>" +
          '<button type="button" class="cm-icon" data-act="down" aria-label="Move ' + esc(r.name) + ' later"' + (canDown ? "" : " disabled") + ">↓</button>" +
          '<button type="button" class="cm-icon" data-act="remove" aria-label="Remove ' + esc(r.name) + '">✕</button></span>' : "") +
      "</div>" +
      '<details class="cm-season-edit"><summary>Edit this round</summary>' +
        '<form class="sub-admin-form" data-act="rename">' +
          '<input class="sub-input" name="name" maxlength="120" value="' + esc(r.name) + '" aria-label="Round name">' +
          '<textarea class="sub-input sub-textarea" name="prompt" maxlength="2000" rows="2" aria-label="Description">' + esc(r.prompt) + "</textarea>" +
          (upcoming || phase === "submitting" ? ruleFields(r, "cmR-" + r.id) : "") +
          // who wrote the prompt, any time; roles while it takes tracks
          '<div data-fill="round" data-roles="' + (upcoming || phase === "submitting" ? "1" : "") + '"></div>' +
          '<div class="sub-actions"><button type="submit" class="sub-btn sub-btn-quiet">Save</button></div>' +
        "</form></details></li>";
  }

  // The rules and timing, for setting up and for changing a season.
  function settingsFields(s, id) {
    return '<label class="sub-label" for="' + id + '-name">Season name</label>' +
      '<input class="sub-input" id="' + id + '-name" name="name" maxlength="60" value="' + esc(s.name) + '">' +
      '<label class="sub-label" for="' + id + '-desc">Description</label>' +
      '<textarea class="sub-input sub-textarea" id="' + id + '-desc" name="description" maxlength="2000" rows="2">' + esc(s.description) + "</textarea>" +
      votesFields(s, id) + timingFields(s, id);
  }

  function votesFields(s, id) {
    return '<label class="sub-label" for="' + id + '-songs">Songs each player sends a round</label>' +
      '<select class="sub-input" id="' + id + '-songs" name="songs_per_round">' +
        options(range(1, 5), s.songs_per_round || 1, function (n) { return n + (n === 1 ? " song" : " songs"); }) + "</select>" +
      '<label class="sub-label" for="' + id + '-budget">Points each voter gives</label>' +
      '<select class="sub-input" id="' + id + '-budget" name="point_budget">' + options(range(5, 30), s.point_budget) + "</select>" +
      '<label class="sub-label" for="' + id + '-max">Most points on one song</label>' +
      '<select class="sub-input" id="' + id + '-max" name="max_per_track">' + maxOptions(s.point_budget, s.max_per_track) + "</select>" +
      '<label class="sub-label" for="' + id + '-keep">A penalty for not voting?</label>' +
      '<select class="sub-input" id="' + id + '-keep" name="nonvoters_keep_points">' +
        '<option value="false"' + (s.nonvoters_keep_points ? "" : " selected") + ">Yes, their upvotes don’t count</option>" +
        '<option value="true"' + (s.nonvoters_keep_points ? " selected" : "") + ">No, they keep their points</option></select>" +
      '<label class="sub-label" for="' + id + '-down">Downvotes each voter may give</label>' +
      '<select class="sub-input" id="' + id + '-down" name="downvotes">' +
        '<option value="0"' + (s.downvotes ? "" : " selected") + ">No downvotes</option>" +
        options(range(1, 10), s.downvotes, function (n) { return n + (n === 1 ? " downvote" : " downvotes"); }) + "</select>" +
      '<label class="sub-label" for="' + id + '-downmax">Most downvotes on one song</label>' +
      '<select class="sub-input" id="' + id + '-downmax" name="max_down_per_track">' + downMaxOptions(s.downvotes, s.max_down_per_track) + "</select>" +
      '<p class="block-note">Every point has to be spent; downvotes are optional, up to the limit. Nobody votes for their own song. ' +
        "A player who doesn’t vote, when that costs them, keeps only their downvotes.</p>" +
      ruleFields(s, id);
  }

  function timingFields(s, id) {
    var t = TIMING[s.timing];
    return '<fieldset class="cm-seg-box"><legend class="sub-label">How deadlines behave</legend><div class="cm-seg" role="radiogroup">' +
      Object.keys(TIMING).map(function (k) {
        return '<label class="cm-seg-opt"><input type="radio" name="timing" value="' + k + '"' + (k === s.timing ? " checked" : "") + ">" +
          "<span>" + esc(TIMING[k].name) + "</span></label>";
      }).join("") + "</div>" +
      '<div class="cm-seg-about" data-about="timing"><b>' + esc(t.name) + "</b><ul>" + t.lines.map(function (l) { return "<li>" + esc(l) + "</li>"; }).join("") +
        "</ul><p>Useful if " + esc(t.useful) + "</p></div></fieldset>" +
      '<div class="cm-pair"><span><label class="sub-label" for="' + id + '-sd">Days to submit</label>' +
        '<select class="sub-input" id="' + id + '-sd" name="submit_days">' + options(range(1, 7), s.submit_days, days) + "</select></span>" +
      '<span><label class="sub-label" for="' + id + '-vd">Days to vote</label>' +
        '<select class="sub-input" id="' + id + '-vd" name="vote_days">' + options(range(1, 7), s.vote_days, days) + "</select></span></div>";
  }

  // The settings a form holds now.
  function readSettings(form) {
    var f = form.elements, v = readVotes(f), rules = readRules(form);
    return { error: rules.error, services: rules.services, repeat_rule: rules.repeat_rule,
             name: f.name.value.trim(), description: f.description.value.trim(), songs_per_round: v.songs_per_round,
             point_budget: v.point_budget, max_per_track: v.max_per_track, downvotes: v.downvotes,
             max_down_per_track: v.max_down_per_track, nonvoters_keep_points: v.nonvoters_keep_points,
             timing: (form.querySelector('input[name="timing"]:checked') || {}).value || "steady",
             submit_days: +f.submit_days.value, vote_days: +f.vote_days.value };
  }

  function panelMsg(el, text, good) {
    var m = el.closest(".cm-season").querySelector(".cm-season-body > .sub-msg");
    m.textContent = text;
    m.className = "sub-msg" + (good ? " is-good" : " is-error");
    m.hidden = !text;
  }

  // The parts of each open season that need names, once the players are
  // in: its Players box, and each round's prompters and roles.
  function fillPlayers() {
    var seasons = document.querySelectorAll(".cm-season[open]");
    if (!seasons.length) return;
    loadPeople().then(function () {
      Array.prototype.forEach.call(seasons, function (panel) {
        var s = ctx.seasons.filter(function (x) { return x.key === panel.getAttribute("data-season"); })[0];
        if (!s) return;
        var roster = seasonRoster(s), roles = {};
        roster.forEach(function (p) { if (p.role !== "dj") roles[p.id] = p.role; });
        var box = panel.querySelector("[data-players]");
        if (box && !box.querySelector("input")) {
          box.innerHTML = checklist(roster.map(function (p) { return p.id; }), roles);
          box.insertAdjacentHTML("afterend", '<p class="block-note" data-sum="roster">' + esc(rosterLine(roster)) + "</p>");
        }
        var add = panel.querySelector('[data-fill="new-round"]');
        if (add && !add.innerHTML) add.innerHTML = promptersField([]) + rolesField(roster, {});
        Array.prototype.forEach.call(panel.querySelectorAll("[data-round]"), function (li) {
          var r = ctx.rounds.filter(function (x) { return x.id === li.getAttribute("data-round"); })[0];
          if (!r) return;
          var line = [];
          if (prompterIds(r).length) line.push("Prompt by " + names(prompterIds(r)));
          var changed = changedRoles(roster, ownRoles(r));
          if (Object.keys(changed).length) line.push(rolesSummary(changed));
          li.querySelector("[data-people-round]").textContent = line.join(" · ");
          var fill = li.querySelector('[data-fill="round"]');
          if (fill && !fill.innerHTML) {
            fill.innerHTML = promptersField(prompterIds(r)) + (fill.getAttribute("data-roles") ? rolesField(roster, ownRoles(r)) : "");
          }
        });
      });
    }).catch(function (err) { console.error(err); });
  }

  /* ---- setting one up ---- */

  function startWizard() {
    var current = ctx.index && ctx.index.seasons.filter(function (s) { return s.key === ctx.index.currentSeason; })[0];
    var key = nextKey();
    wizard = { step: 0, d: { key: key, name: "Season " + key.replace(/\D/g, ""), description: "", point_budget: 19, max_per_track: 5,
                             nonvoters_keep_points: false, timing: "steady", submit_days: 2, vote_days: 5,
                             songs_per_round: 1, downvotes: 0, max_down_per_track: 0,
                             services: ["spotify", "youtube", "soundcloud"], repeat_rule: "warn",
                             first_date: "", first_time: "20:00", rounds: [],
                             players: (current && current.activePlayers || []).map(function (p) { return p.id; }),
                             // {id: "spectator"} for the season's Spectators; DJ otherwise
                             roles: {} } };
    loadPeople().then(function () { render(ctx); showWizard(); },
                      function (err) { wizard = null; say("Couldn’t load the players: " + errText(err)); });
  }

  // the setup's top, just under the sticky top bar (two rows on a phone),
  // so the steps aren't hidden behind it
  function showWizard() {
    var bar = document.querySelector(".topbar");
    var top = $("cmWizard").getBoundingClientRect().top + window.pageYOffset - (bar ? bar.getBoundingClientRect().height : 0) - 12;
    window.scrollTo({ top: Math.max(0, top), behavior: "instant" });
  }

  function drawWizard() {
    var d = wizard.d, step = wizard.step, id = "cmNew";
    var body;
    if (step === 0) {
      body = '<label class="sub-label" for="cmNew-name">Season name</label>' +
        '<input class="sub-input" id="cmNew-name" name="name" maxlength="60" value="' + esc(d.name) + '">' +
        '<label class="sub-label" for="cmNew-desc">Description</label>' +
        '<textarea class="sub-input sub-textarea" id="cmNew-desc" name="description" maxlength="2000" rows="3">' + esc(d.description) + "</textarea>";
    } else if (step === 1) {
      body = votesFields(d, id);
    } else if (step === 2) {
      body = timingFields(d, id);
    } else if (step === PLAYERS_STEP) {
      body = '<p class="block-note">Tick who’s playing. <b>DJs</b> send tracks and vote; <b>Spectators</b> vote and comment on every track, ' +
          "and never send one. Each round can change anyone’s role, in the next step.</p>" +
        '<p class="block-note" id="cmNewCount">' + esc(rosterLine(wizardRoster(d))) + ". Only DJs submit, and Accelerated and Speedy wait on the ones who’ve joined the site.</p>" +
        '<div class="sub-actions"><button type="button" class="sub-btn sub-btn-quiet" data-act="w-all">Everyone</button>' +
          '<button type="button" class="sub-btn sub-btn-quiet" data-act="w-none">No one</button></div>' +
        '<div class="cm-checks">' + checklist(d.players, d.roles) + "</div>";
    } else {
      var roster = wizardRoster(d);
      body = '<ol class="cm-new-rounds">' + d.rounds.map(function (r, i) {
          var about = [];
          if (r.prompters.length) about.push("Prompt by " + names(r.prompters));
          var changed = changedRoles(roster, r.roles);
          if (Object.keys(changed).length) about.push(rolesSummary(changed));
          return '<li data-i="' + i + '"><div class="cm-season-round-head"><b>' + (i + 1) + ". " + esc(r.name) + "</b>" +
            '<span class="cm-move"><button type="button" class="cm-icon" data-act="w-up" aria-label="Move ' + esc(r.name) + ' earlier"' + (i ? "" : " disabled") + ">↑</button>" +
            '<button type="button" class="cm-icon" data-act="w-down" aria-label="Move ' + esc(r.name) + ' later"' + (i < d.rounds.length - 1 ? "" : " disabled") + ">↓</button>" +
            '<button type="button" class="cm-icon" data-act="w-remove" aria-label="Remove ' + esc(r.name) + '">✕</button></span></div>' +
            (r.prompt ? "<p>" + esc(r.prompt) + "</p>" : "") +
            (about.length ? "<p>" + esc(about.join(" · ")) + "</p>" : "") + "</li>";
        }).join("") + "</ol>" +
        '<label class="sub-label" for="cmNew-rname">Add round</label>' +
        '<input class="sub-input" id="cmNew-rname" maxlength="120" placeholder="Theme name">' +
        '<textarea class="sub-input sub-textarea" id="cmNew-rprompt" maxlength="2000" rows="2" placeholder="Theme description" aria-label="Theme description"></textarea>' +
        '<div id="cmNew-rpeople">' + promptersField([]) + rolesField(roster, {}) + "</div>" +
        '<div class="sub-actions"><button type="button" class="sub-btn sub-btn-quiet" data-act="w-add">Add round</button></div>' +
        '<p class="block-note">Round 1’s submissions close at the first playlist. Each round after it opens when the one before closes voting.</p>' +
        '<div class="cm-pair"><span><label class="sub-label" for="cmNew-date">Date of the first playlist</label>' +
          '<input class="sub-input" id="cmNew-date" name="first_date" type="date" value="' + esc(d.first_date) + '"></span>' +
        '<span><label class="sub-label" for="cmNew-time">Time (your time)</label>' +
          '<input class="sub-input" id="cmNew-time" name="first_time" type="time" value="' + esc(d.first_time) + '"></span></div>' +
        previewHtml(d) + summaryHtml(d);
    }
    $("cmWizard").innerHTML = "<h3>Set up " + esc(d.name || "a new season") + "</h3>" +
      '<ol class="cm-steps">' + STEPS.map(function (s, i) {
        return '<li><button type="button" data-act="w-step" data-step="' + i + '"' + (i === step ? ' aria-current="step"' : "") + ">" +
          '<span class="cm-step-n">' + (i + 1) + "</span>" + esc(s) + "</button></li>";
      }).join("") + "</ol>" +
      '<form class="sub-admin-form cm-wizard-form" id="cmWizardForm" novalidate>' + body + "</form>" +
      '<p class="sub-msg is-error" id="cmWizardMsg" role="status" hidden></p>' +
      '<div class="sub-actions cm-wizard-nav">' +
        '<button type="button" class="sub-btn sub-btn-quiet" data-act="' + (step ? "w-back" : "w-cancel") + '">' + (step ? "Back" : "Cancel") + "</button>" +
        (step < STEPS.length - 1 ? '<button type="button" class="sub-btn" data-act="w-next">Next</button>'
                                 : '<button type="button" class="sub-btn" data-act="w-create">Create the season</button>') + "</div>";
  }

  function firstClose(d) {
    if (!d.first_date || !d.first_time) return null;
    var t = new Date(d.first_date + "T" + d.first_time);
    return isNaN(t) ? null : t;
  }

  function previewHtml(d) {
    var first = firstClose(d);
    if (!first || !d.rounds.length) return '<div class="cm-sched" id="cmSched"></div>';
    var rows = schedule(first, d.rounds.length, d.submit_days, d.vote_days);
    return '<div class="cm-sched" id="cmSched"><h4>The schedule</h4><ol>' + rows.map(function (x, i) {
      return "<li><b>" + esc(d.rounds[i].name) + "</b><span>Opens " + esc(when(x.opens.toISOString())) +
        " · submissions close " + esc(when(x.closes.toISOString())) + " · voting closes " + esc(when(x.voting.toISOString())) + "</span></li>";
    }).join("") + "</ol></div>";
  }

  function summaryHtml(d) {
    var first = firstClose(d);
    return '<div class="cm-sched" id="cmSum"><h4>Ready to create</h4><ul>' +
      "<li>" + esc(d.name) + ", " + d.rounds.length + (d.rounds.length === 1 ? " round" : " rounds") + "</li>" +
      "<li>" + d.songs_per_round + (d.songs_per_round === 1 ? " song" : " songs") + " from each player a round</li>" +
      "<li>" + d.point_budget + " points to give, " + (d.max_per_track >= d.point_budget ? "no limit on one song" : "at most " + d.max_per_track + " on one song") +
        ", " + (d.downvotes ? d.downvotes + (d.downvotes === 1 ? " downvote" : " downvotes") +
          (d.max_down_per_track >= d.downvotes ? "" : ", at most " + d.max_down_per_track + " on one song") : "no downvotes") +
        ", " + (d.nonvoters_keep_points ? "no penalty for not voting" : "a player who doesn’t vote keeps only their downvotes") + "</li>" +
      "<li>" + d.services.map(function (x) { return SERVICES.filter(function (y) { return y[0] === x; })[0][1]; }).join(", ") +
        "; repeats within a round: " + RULES.filter(function (x) { return x[0] === d.repeat_rule; })[0][1].toLowerCase() + "</li>" +
      "<li>" + esc(TIMING[d.timing].name) + ": " + days(d.submit_days) + " to submit, " + days(d.vote_days) + " to vote</li>" +
      "<li>" + esc(rosterLine(wizardRoster(d))) + "</li>" +
      "<li>" + (first ? "First playlist " + esc(when(first.toISOString())) : "No first playlist yet") + "</li>" +
      "<li>Voting on pfml.fun, results shown when voting closes</li></ul></div>";
  }

  // Keeps what's on the form in the draft, and says what's missing, if
  // anything, before leaving a step.
  function readStep() {
    var d = wizard.d, form = $("cmWizardForm");
    if (!form) return null;
    var f = form.elements;
    if (wizard.step === 0) {
      d.name = f.name.value.trim();
      d.description = f.description.value.trim();
      if (!d.name) return "Give the season a name.";
    } else if (wizard.step === 1 || wizard.step === 2) {
      if (f.point_budget) {
        var v = readVotes(f), rules = readRules(form);
        Object.keys(v).forEach(function (k) { d[k] = v[k]; });
        if (rules.error) return rules.error;
        d.services = rules.services;
        d.repeat_rule = rules.repeat_rule;
      }
      if (f.submit_days) {
        d.timing = (form.querySelector('input[name="timing"]:checked') || {}).value || "steady";
        d.submit_days = +f.submit_days.value;
        d.vote_days = +f.vote_days.value;
      }
    } else if (wizard.step === PLAYERS_STEP) {
      // every row's role is kept, ticked or not, so ticking someone again
      // brings their choice back
      people.players.forEach(function (p) {
        var el = f["role-" + p.id];
        if (el && el.value === "spectator") d.roles[p.id] = "spectator"; else delete d.roles[p.id];
      });
      d.players = readRoster(form).map(function (p) { return p.id; });
      return rosterProblem(wizardRoster(d));
    } else {
      d.first_date = f.first_date.value;
      d.first_time = f.first_time.value;
      if (!d.rounds.length) return "Add at least one round.";
      var first = firstClose(d);
      if (!first) return "Pick the date and time of the first playlist.";
      if (first.getTime() <= Date.now()) return "The first playlist has to be in the future.";
    }
    return null;
  }

  // [{id, role}] for the players picked so far
  function wizardRoster(d) {
    return d.players.map(function (id) { return { id: id, role: d.roles[id] || "dj" }; });
  }
  // what the database would refuse about a roster, or null
  function rosterProblem(list) {
    return list.filter(function (p) { return p.role === "dj"; }).length < 2 ? "Pick at least 2 DJs: they send the tracks." : null;
  }
  // a round's own roles, as the database takes them: only for the players
  // still picked, and only when any differ from their season role
  function roundForCreate(r, roster) {
    var out = { name: r.name, prompt: r.prompt, prompters: r.prompters };
    var changed = changedRoles(roster, r.roles);
    if (Object.keys(changed).length) out.roles = fullRoles(roster, changed);
    return out;
  }

  function wizardMsg(text) { var m = $("cmWizardMsg"); m.textContent = text || ""; m.hidden = !text; }

  function goStep(n) {
    var problem = readStep();
    // going back never needs the step to be complete
    if (problem && n > wizard.step) { wizardMsg(problem); return; }
    wizard.step = n;
    drawWizard();
    showWizard();
  }

  function create() {
    var problem = readStep();
    if (problem) { wizardMsg(problem); return; }
    var d = wizard.d;
    // every step has to be complete, whichever order they were visited in
    if (!d.name) { wizard.step = 0; drawWizard(); wizardMsg("Give the season a name."); return; }
    var roster = wizardRoster(d);
    if (rosterProblem(roster)) { wizard.step = PLAYERS_STEP; drawWizard(); wizardMsg(rosterProblem(roster)); return; }
    var first = firstClose(d);
    if (!d.rounds.length || !first || first.getTime() <= Date.now()) {
      wizard.step = ROUNDS_STEP; drawWizard(); wizardMsg(d.rounds.length ? "Pick a first playlist in the future." : "Add at least one round."); return;
    }
    var p = { key: d.key, name: d.name, description: d.description, point_budget: d.point_budget, max_per_track: d.max_per_track,
              nonvoters_keep_points: d.nonvoters_keep_points, timing: d.timing, submit_days: d.submit_days, vote_days: d.vote_days,
              songs_per_round: d.songs_per_round, downvotes: d.downvotes, max_down_per_track: d.max_down_per_track,
              services: d.services, repeat_rule: d.repeat_rule, first_playlist_at: first.toISOString(),
              rounds: d.rounds.map(function (r) { return roundForCreate(r, roster); }), players: roster };
    if (!window.confirm("Create " + d.name + " with " + d.rounds.length + (d.rounds.length === 1 ? " round" : " rounds") +
                        "? Its first round opens " + (schedule(first, 1, d.submit_days, d.vote_days)[0].opens.getTime() <= Date.now() + 60000 ? "straight away" : "on schedule") + ".")) return;
    api().createSiteSeason(p).then(function () {
      var name = d.name;
      wizard = null;
      return Promise.resolve(ctx.reload()).then(function () { say(name + " is set up.", true); });
    }).catch(function (err) { wizardMsg(errText(err)); });
  }

  /* ---- events ---- */

  function onClick(ev) {
    var b = ev.target.closest("[data-act]");
    if (!b || b.tagName === "FORM") return;
    var act = b.getAttribute("data-act");
    if (act === "new") { say(""); startWizard(); return; }
    if (act.indexOf("w-") === 0) { onWizardClick(act, b); return; }
    var li = b.closest("[data-round]");
    if (!li) return;
    var id = li.getAttribute("data-round");
    var name = li.querySelector("b").textContent;
    var done;
    if (act === "up" || act === "down") done = api().moveSiteSeasonRound(id, act === "up");
    else if (act === "remove") {
      if (!window.confirm("Remove " + name + "? It hasn’t opened, so nobody has a track in it.")) return;
      done = api().removeSiteSeasonRound(id);
    } else return;
    b.disabled = true;
    var key = li.closest(".cm-season").getAttribute("data-season");
    done.then(function () { return ctx.reload(); }).then(function () { reopen(key, ""); })
      .catch(function (err) { panelMsg(li, errText(err)); b.disabled = false; });
  }

  // The redraw after a change closes every season; open this one again,
  // with its players, and say so.
  function reopen(key, text) {
    var again = document.querySelector('.cm-season[data-season="' + key + '"]');
    if (!again) return;
    again.open = true;
    fillPlayers();
    if (text) panelMsg(again.querySelector(".cm-season-body"), text, true);
  }

  function onWizardClick(act, b) {
    var d = wizard && wizard.d;
    if (!d) return;
    if (act === "w-cancel") { if (window.confirm("Stop setting up this season? Nothing has been saved.")) { wizard = null; render(ctx); } return; }
    if (act === "w-next") { goStep(wizard.step + 1); return; }
    if (act === "w-back") { goStep(wizard.step - 1); return; }
    if (act === "w-step") { goStep(+b.getAttribute("data-step")); return; }
    if (act === "w-create") { create(); return; }
    if (act === "w-all" || act === "w-none") {
      Array.prototype.forEach.call(document.querySelectorAll('#cmWizardForm input[name="player"]'), function (x) { x.checked = act === "w-all"; });
      onWizardInput();
      return;
    }
    readStep();
    if (act === "w-add") {
      var name = $("cmNew-rname").value.trim();
      if (!name) { wizardMsg("Give the round a name."); return; }
      var form = $("cmWizardForm"), roster = wizardRoster(d), roles = readRoundRoles(form, roster);
      if (rosterProblem(roster.map(function (p) { return { id: p.id, role: roles[p.id] || p.role }; }))) {
        wizardMsg("A round needs at least 2 DJs: they send the tracks.");
        return;
      }
      d.rounds.push({ name: name, prompt: $("cmNew-rprompt").value.trim(), prompters: readPrompters(form), roles: roles });
    } else {
      var i = +b.closest("[data-i]").getAttribute("data-i");
      if (act === "w-remove") d.rounds.splice(i, 1);
      else {
        var j = act === "w-up" ? i - 1 : i + 1;
        var t = d.rounds[i]; d.rounds[i] = d.rounds[j]; d.rounds[j] = t;
      }
    }
    drawWizard();
    if (act === "w-add") $("cmNew-rname").focus();
  }

  // live parts of a form: the timing explanation, the "most on one song"
  // choices (they depend on the points), the schedule preview, the count,
  // and what a round's prompters and roles say when folded
  function onWizardInput(ev) {
    var t = ev && ev.target;
    var form = t ? t.closest("form") : $("cmWizardForm");
    if (!form) return;
    var pick = t && t.closest(".cm-people-pick");
    if (pick && t.name === "prompter") {
      var chosen = readPrompters(pick);
      pick.querySelector('[data-sum="prompters"]').textContent = chosen.length ? names(chosen) : "nobody named";
    }
    if (pick && /^rrole-/.test(t.name || "")) {
      var season = Array.prototype.map.call(pick.querySelectorAll("select.cm-role"), function (el) {
        return { id: el.name.slice(6), role: el.getAttribute("data-season") || "dj" };
      });
      pick.querySelector('[data-sum="roles"]').textContent = rolesSummary(readRoundRoles(pick, season));
    }
    if (form.getAttribute("data-act") === "players") {
      var sum = form.querySelector('[data-sum="roster"]');
      if (sum) sum.textContent = rosterLine(readRoster(form));
    }
    if (t && t.name === "timing") {
      var about = form.querySelector('[data-about="timing"]'), k = TIMING[t.value];
      about.innerHTML = "<b>" + esc(k.name) + "</b><ul>" + k.lines.map(function (l) { return "<li>" + esc(l) + "</li>"; }).join("") +
        "</ul><p>Useful if " + esc(k.useful) + "</p>";
    }
    if (t && t.name === "point_budget") {
      var budget = +t.value, max = form.elements.max_per_track;
      max.innerHTML = maxOptions(budget, max.value === "none" ? budget : Math.min(+max.value, budget));
    }
    if (t && t.name === "downvotes") {
      var down = +t.value, dmax = form.elements.max_down_per_track;
      dmax.innerHTML = downMaxOptions(down, dmax.value === "none" || dmax.value === "0" ? down : Math.min(+dmax.value, down));
    }
    if (form.id !== "cmWizardForm") return;
    if (wizard.step === ROUNDS_STEP && t && (t.name === "first_date" || t.name === "first_time")) {
      readStep();
      $("cmSched").outerHTML = previewHtml(wizard.d);
      // the summary shares this step, so its first playlist follows too
      $("cmSum").outerHTML = summaryHtml(wizard.d);
    }
    if (wizard.step === PLAYERS_STEP) {
      readStep();
      $("cmNewCount").textContent = rosterLine(wizardRoster(wizard.d)) + ". Only DJs submit, and Accelerated and Speedy wait on the ones who’ve joined the site.";
    }
  }

  function onSubmit(ev) {
    // the setup's form never submits itself (Enter in a field would reload
    // the page and lose the setup); Enter in a round's name adds the round
    if (ev.target.id === "cmWizardForm") {
      ev.preventDefault();
      if (wizard && wizard.step === ROUNDS_STEP && document.activeElement && document.activeElement.id === "cmNew-rname") onWizardClick("w-add", null);
      return;
    }
    var form = ev.target.closest("form[data-act]");
    if (!form) return;
    ev.preventDefault();
    var act = form.getAttribute("data-act");
    var key = form.closest(".cm-season").getAttribute("data-season");
    var season = ctx.seasons.filter(function (x) { return x.key === key; })[0];
    var roster = season ? seasonRoster(season) : [];
    var done;
    if (act === "settings") {
      var s = readSettings(form);
      if (!s.name) { panelMsg(form, "Give the season a name."); return; }
      if (s.error) { panelMsg(form, s.error); return; }
      delete s.error;
      done = api().updateSiteSeason(key, s);
    } else if (act === "add-round") {
      var name = form.elements.name.value.trim();
      if (!name) { panelMsg(form, "Give the round a name."); return; }
      // its prompters and roles go in once the round exists; the names are
      // in the form only once the players have loaded
      var named = form.querySelector('[data-fill="new-round"] .cm-people-pick');
      var prompters = named ? readPrompters(form) : [];
      var changed = named ? readRoundRoles(form, roster) : {};
      done = api().addSiteSeasonRound(key, name, form.elements.prompt.value.trim()).then(function (rid) {
        if (!prompters.length && !Object.keys(changed).length) return;
        return api().setSiteRoundPeople(rid, Object.keys(changed).length ? fullRoles(roster, changed) : null, prompters.length ? prompters : null)
          .catch(function (err) { throw new Error("The round was added, but its prompters and roles weren’t: " + errText(err)); });
      });
    } else if (act === "rename") {
      var id = form.closest("[data-round]").getAttribute("data-round");
      var n = form.elements.name.value.trim();
      if (!n) { panelMsg(form, "Give the round a name."); return; }
      var fields = { name: n, prompt: form.elements.prompt.value.trim() };
      // a round still taking tracks can change its services and repeat rule
      if (form.elements.repeat_rule) {
        var rules = readRules(form);
        if (rules.error) { panelMsg(form, rules.error); return; }
        fields.services = rules.services;
        fields.repeat_rule = rules.repeat_rule;
      }
      // who wrote the prompt, and the round's roles while it takes tracks
      var hasPeople = !!form.querySelector('[data-fill="round"] .cm-people-pick');
      var roles = hasPeople && form.querySelector("select.cm-role") ? fullRoles(roster, readRoundRoles(form, roster)) : null;
      var who = hasPeople ? readPrompters(form) : null;
      done = api().updateSiteRound(id, fields).then(function (rows) {
        if (!rows || !rows.length) throw new Error("Only the admin or a commissioner can do that.");
        if (hasPeople) return api().setSiteRoundPeople(id, roles, who);
      });
    } else if (act === "players") {
      var list = readRoster(form);
      if (rosterProblem(list)) { panelMsg(form, rosterProblem(list)); return; }
      done = api().setSiteSeasonRoster(key, list);
    } else return;
    var panel = form.closest(".cm-season");
    done.then(function () { return ctx.reload(); }).then(function () { reopen(key, "Saved."); })
      .catch(function (err) { panelMsg(panel.querySelector(".cm-season-body"), "That didn’t save: " + errText(err)); });
  }

  function onToggle(ev) {
    if (ev.target.classList && ev.target.classList.contains("cm-season") && ev.target.open) fillPlayers();
  }

  document.addEventListener("DOMContentLoaded", function () {
    var box = $("cmSeasons");
    if (!box) return;
    box.addEventListener("click", onClick);
    box.addEventListener("input", onWizardInput);
    box.addEventListener("change", onWizardInput);
    box.addEventListener("submit", onSubmit);
    box.addEventListener("toggle", onToggle, true);
  });

  window.PFMLSeasons = { render: render, schedule: schedule, ruleFields: ruleFields, readRules: readRules };
})();
