/* ==========================================================
   PFML - seasons set up on the site, on the Commissioner page

   Setting one up, in the steps Music League uses (Details, Songs + Votes,
   Timing, Rounds, Players), and then running it: its details, rules and
   timing, its rounds (add, rename, reorder or remove one that hasn't
   opened), and who's playing. Every season set up here votes on pfml.fun
   (the user's call, 2026-10-25). commissioner.js loads the rounds and the
   seasons and hands them over (PFMLSeasons.render).

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

  var STEPS = ["Details", "Songs + Votes", "Timing", "Rounds", "Players"];
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

  function checklist(name, chosen) {
    return people.players.map(function (p) {
      return '<label class="cm-check"><input type="checkbox" name="' + name + '" value="' + esc(p.id) + '"' +
        (chosen.indexOf(p.id) !== -1 ? " checked" : "") + "><span>" + esc(p.name) + "</span>" +
        (p.joined ? "" : "<small>not on the site yet</small>") + "</label>";
    }).join("");
  }

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
    var players = (s.site_season_players || []).map(function (p) { return p.competitor_id; });
    return '<details class="cm-season" data-season="' + esc(s.key) + '">' +
      '<summary><span class="cm-round-name">' + esc(s.name) + "</span><small>" + esc(statusLine(s, rounds)) + " · " +
        players.length + " playing · " + esc(TIMING[s.timing].name) + "</small></summary>" +
      '<div class="cm-season-body">' +
        "<h3>Rounds</h3>" +
        '<ol class="cm-season-rounds">' + rounds.map(function (r, i) { return roundRow(r, i, rounds); }).join("") + "</ol>" +
        '<form class="sub-admin-form cm-add-round" data-act="add-round">' +
          '<label class="sub-label" for="cmAdd-' + esc(s.key) + '">Add a round at the end</label>' +
          '<input class="sub-input" id="cmAdd-' + esc(s.key) + '" name="name" maxlength="120" placeholder="Theme name">' +
          '<textarea class="sub-input sub-textarea" name="prompt" maxlength="2000" rows="2" placeholder="Theme description" aria-label="Theme description"></textarea>' +
          '<div class="sub-actions"><button type="submit" class="sub-btn sub-btn-quiet">Add round</button></div>' +
        "</form>" +
        "<h3>Settings</h3>" +
        '<form class="sub-admin-form" data-act="settings">' + settingsFields(s, "cmSet-" + s.key) +
          '<p class="block-note">Rules reach every round whose submissions haven’t closed. Songs a round, and days to submit and vote, reach the rounds that haven’t opened.</p>' +
          '<div class="sub-actions"><button type="submit" class="sub-btn">Save settings</button></div>' +
        "</form>" +
        "<h3>Players</h3>" +
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
      '<div class="cm-season-round-head"><span><b>' + (i + 1) + ". " + esc(r.name) + "</b><small>" + esc(dates) + "</small></span>" +
        (upcoming ? '<span class="cm-move">' +
          '<button type="button" class="cm-icon" data-act="up" aria-label="Move ' + esc(r.name) + ' earlier"' + (canUp ? "" : " disabled") + ">↑</button>" +
          '<button type="button" class="cm-icon" data-act="down" aria-label="Move ' + esc(r.name) + ' later"' + (canDown ? "" : " disabled") + ">↓</button>" +
          '<button type="button" class="cm-icon" data-act="remove" aria-label="Remove ' + esc(r.name) + '">✕</button></span>' : "") +
      "</div>" +
      '<details class="cm-season-edit"><summary>Edit name and description</summary>' +
        '<form class="sub-admin-form" data-act="rename">' +
          '<input class="sub-input" name="name" maxlength="120" value="' + esc(r.name) + '" aria-label="Round name">' +
          '<textarea class="sub-input sub-textarea" name="prompt" maxlength="2000" rows="2" aria-label="Description">' + esc(r.prompt) + "</textarea>" +
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
        "A player who doesn’t vote, when that costs them, keeps only their downvotes.</p>";
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
    var f = form.elements, v = readVotes(f);
    return { name: f.name.value.trim(), description: f.description.value.trim(), songs_per_round: v.songs_per_round,
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

  // the Players box of each open season, once the players are in
  function fillPlayers() {
    var boxes = document.querySelectorAll("[data-players]");
    if (!boxes.length) return;
    loadPeople().then(function () {
      Array.prototype.forEach.call(boxes, function (box) {
        var s = ctx.seasons.filter(function (x) { return x.key === box.getAttribute("data-players"); })[0];
        box.innerHTML = checklist("player", (s.site_season_players || []).map(function (p) { return p.competitor_id; }));
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
                             first_date: "", first_time: "20:00", rounds: [],
                             players: (current && current.activePlayers || []).map(function (p) { return p.id; }) } };
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
    } else if (step === 3) {
      body = '<ol class="cm-new-rounds">' + d.rounds.map(function (r, i) {
          return '<li data-i="' + i + '"><div class="cm-season-round-head"><b>' + (i + 1) + ". " + esc(r.name) + "</b>" +
            '<span class="cm-move"><button type="button" class="cm-icon" data-act="w-up" aria-label="Move ' + esc(r.name) + ' earlier"' + (i ? "" : " disabled") + ">↑</button>" +
            '<button type="button" class="cm-icon" data-act="w-down" aria-label="Move ' + esc(r.name) + ' later"' + (i < d.rounds.length - 1 ? "" : " disabled") + ">↓</button>" +
            '<button type="button" class="cm-icon" data-act="w-remove" aria-label="Remove ' + esc(r.name) + '">✕</button></span></div>' +
            (r.prompt ? "<p>" + esc(r.prompt) + "</p>" : "") + "</li>";
        }).join("") + "</ol>" +
        '<label class="sub-label" for="cmNew-rname">Add round</label>' +
        '<input class="sub-input" id="cmNew-rname" maxlength="120" placeholder="Theme name">' +
        '<textarea class="sub-input sub-textarea" id="cmNew-rprompt" maxlength="2000" rows="2" placeholder="Theme description" aria-label="Theme description"></textarea>' +
        '<div class="sub-actions"><button type="button" class="sub-btn sub-btn-quiet" data-act="w-add">Add round</button></div>' +
        '<p class="block-note">Round 1’s submissions close at the first playlist. Each round after it opens when the one before closes voting.</p>' +
        '<div class="cm-pair"><span><label class="sub-label" for="cmNew-date">Date of the first playlist</label>' +
          '<input class="sub-input" id="cmNew-date" name="first_date" type="date" value="' + esc(d.first_date) + '"></span>' +
        '<span><label class="sub-label" for="cmNew-time">Time (your time)</label>' +
          '<input class="sub-input" id="cmNew-time" name="first_time" type="time" value="' + esc(d.first_time) + '"></span></div>' +
        previewHtml(d);
    } else {
      body = '<p class="block-note"><span id="cmNewCount">' + d.players.length + "</span> playing. Only they can submit, and Accelerated and Speedy wait on the ones who’ve joined the site.</p>" +
        '<div class="sub-actions"><button type="button" class="sub-btn sub-btn-quiet" data-act="w-all">Everyone</button>' +
          '<button type="button" class="sub-btn sub-btn-quiet" data-act="w-none">No one</button></div>' +
        '<div class="cm-checks">' + checklist("player", d.players) + "</div>" + summaryHtml(d);
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
    return '<div class="cm-sched"><h4>Ready to create</h4><ul>' +
      "<li>" + esc(d.name) + ", " + d.rounds.length + (d.rounds.length === 1 ? " round" : " rounds") + "</li>" +
      "<li>" + d.songs_per_round + (d.songs_per_round === 1 ? " song" : " songs") + " from each player a round</li>" +
      "<li>" + d.point_budget + " points to give, " + (d.max_per_track >= d.point_budget ? "no limit on one song" : "at most " + d.max_per_track + " on one song") +
        ", " + (d.downvotes ? d.downvotes + (d.downvotes === 1 ? " downvote" : " downvotes") +
          (d.max_down_per_track >= d.downvotes ? "" : ", at most " + d.max_down_per_track + " on one song") : "no downvotes") +
        ", " + (d.nonvoters_keep_points ? "no penalty for not voting" : "a player who doesn’t vote keeps only their downvotes") + "</li>" +
      "<li>" + esc(TIMING[d.timing].name) + ": " + days(d.submit_days) + " to submit, " + days(d.vote_days) + " to vote</li>" +
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
        var v = readVotes(f);
        Object.keys(v).forEach(function (k) { d[k] = v[k]; });
      }
      if (f.submit_days) {
        d.timing = (form.querySelector('input[name="timing"]:checked') || {}).value || "steady";
        d.submit_days = +f.submit_days.value;
        d.vote_days = +f.vote_days.value;
      }
    } else if (wizard.step === 3) {
      d.first_date = f.first_date.value;
      d.first_time = f.first_time.value;
      if (!d.rounds.length) return "Add at least one round.";
      var first = firstClose(d);
      if (!first) return "Pick the date and time of the first playlist.";
      if (first.getTime() <= Date.now()) return "The first playlist has to be in the future.";
    } else {
      d.players = Array.prototype.filter.call(form.querySelectorAll('input[name="player"]'), function (b) { return b.checked; })
        .map(function (b) { return b.value; });
      if (d.players.length < 2) return "Pick at least 2 players.";
    }
    return null;
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
    var first = firstClose(d);
    if (!d.rounds.length || !first || first.getTime() <= Date.now()) {
      wizard.step = 3; drawWizard(); wizardMsg(d.rounds.length ? "Pick a first playlist in the future." : "Add at least one round."); return;
    }
    var p = { key: d.key, name: d.name, description: d.description, point_budget: d.point_budget, max_per_track: d.max_per_track,
              nonvoters_keep_points: d.nonvoters_keep_points, timing: d.timing, submit_days: d.submit_days, vote_days: d.vote_days,
              songs_per_round: d.songs_per_round, downvotes: d.downvotes, max_down_per_track: d.max_down_per_track,
              first_playlist_at: first.toISOString(), rounds: d.rounds, players: d.players };
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
      d.rounds.push({ name: name, prompt: $("cmNew-rprompt").value.trim() });
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
  // choices (they depend on the points), the schedule preview, the count
  function onWizardInput(ev) {
    var t = ev && ev.target;
    var form = t ? t.closest("form") : $("cmWizardForm");
    if (!form) return;
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
    if (wizard.step === 3 && t && (t.name === "first_date" || t.name === "first_time")) {
      readStep();
      $("cmSched").outerHTML = previewHtml(wizard.d);
    }
    if (wizard.step === 4) {
      readStep();
      $("cmNewCount").textContent = wizard.d.players.length;
    }
  }

  function onSubmit(ev) {
    // the setup's form never submits itself (Enter in a field would reload
    // the page and lose the setup); Enter in a round's name adds the round
    if (ev.target.id === "cmWizardForm") {
      ev.preventDefault();
      if (wizard && wizard.step === 3 && document.activeElement && document.activeElement.id === "cmNew-rname") onWizardClick("w-add", null);
      return;
    }
    var form = ev.target.closest("form[data-act]");
    if (!form) return;
    ev.preventDefault();
    var act = form.getAttribute("data-act");
    var key = form.closest(".cm-season").getAttribute("data-season");
    var done;
    if (act === "settings") {
      var s = readSettings(form);
      if (!s.name) { panelMsg(form, "Give the season a name."); return; }
      done = api().updateSiteSeason(key, s);
    } else if (act === "add-round") {
      var name = form.elements.name.value.trim();
      if (!name) { panelMsg(form, "Give the round a name."); return; }
      done = api().addSiteSeasonRound(key, name, form.elements.prompt.value.trim());
    } else if (act === "rename") {
      var id = form.closest("[data-round]").getAttribute("data-round");
      var n = form.elements.name.value.trim();
      if (!n) { panelMsg(form, "Give the round a name."); return; }
      done = api().updateSiteRound(id, { name: n, prompt: form.elements.prompt.value.trim() }).then(function (rows) {
        if (!rows || !rows.length) throw new Error("Only the admin or a commissioner can do that.");
      });
    } else if (act === "players") {
      var ids = Array.prototype.filter.call(form.querySelectorAll('input[name="player"]'), function (b) { return b.checked; })
        .map(function (b) { return b.value; });
      if (ids.length < 2) { panelMsg(form, "Pick at least 2 players."); return; }
      done = api().setSiteSeasonPlayers(key, ids);
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

  window.PFMLSeasons = { render: render, schedule: schedule };
})();
