/* PFML - guessing a hidden prompt (README, Hidden prompts and guesses).

   A round can hide its prompt, and who wrote it, from its Spectators until
   voting closes. While voting is open, a Spectator gets a box here, above
   the round's list, to guess the prompt from the tracks and to pick its
   writer from the round's DJs. The guess saves when they press Save and
   locks when they first submit their ballot (the voters' lounge, where DJs
   know the prompt, opens then).

   Once voting has closed, this asks the grade-guesses Edge Function to
   score any guess still without a score (Claude, 0 to 5), then redraws the
   results, where every guess shows with its points (voting.js). The
   database checks every rule again (save_prompt_guess). */
(function () {
  "use strict";

  var PFML = window.PFML;
  var MAX = 280;

  function $(id) { return document.getElementById(id); }
  function api() { return PFML.api; }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function errText(err) { return (err && err.message) || String(err); }

  var state = { host: null, round: null, djs: [], graded: {} };

  function hides(r) { return !!(r && r.votes_on_site && (r.hide_prompt || r.hide_prompter)); }
  function commissioner() { return !!PFML.member && (PFML.member.role === "admin" || PFML.member.role === "commissioner"); }
  function hide() { state.host.hidden = true; state.host.innerHTML = ""; }

  function render(host, r) {
    state.host = host;
    state.round = r;
    if (!hides(r)) { hide(); return; }
    var phase = PFML.roundPhase(r);
    if (phase === "finished") { gradeIfNeeded(r); hide(); return; }
    if (phase !== "voting") { hide(); return; }
    PFML.myRole(r).then(function (role) {
      if (state.round !== r) return;
      // the admin and commissioners know the prompt; DJs do too
      if (role !== "spectator" || commissioner()) { drawNote(r); return; }
      return Promise.all([api().myPromptGuess(r.id), PFML.roundRoster(r), PFML.seasonPlayers(r.season_key)]).then(function (res) {
        if (state.round !== r) return;
        var names = {};
        (res[2] || []).forEach(function (p) { names[p.id] = p.name; });
        state.djs = (res[1] || []).filter(function (x) { return x.role === "dj"; })
          .map(function (x) { return { id: x.id, name: names[x.id] || "Player" }; })
          .sort(function (a, b) { return a.name.localeCompare(b.name); });
        drawBox(r, res[0]);
      });
    }).catch(function (err) {
      console.error(err);
      host.innerHTML = '<p class="sub-msg is-error">Couldn’t load your guess: ' + esc(errText(err)) + "</p>";
      host.hidden = false;
    });
  }

  function what(r) {
    return r.hide_prompt && r.hide_prompter ? "its prompt and who wrote it" : r.hide_prompt ? "its prompt" : "who wrote its prompt";
  }

  // Everyone else in the round: the Spectators are guessing.
  function drawNote(r) {
    state.host.innerHTML = '<p class="block-note gs-note">This round hides ' + esc(what(r)) +
      " from its Spectators until voting closes. They’re guessing.</p>";
    state.host.hidden = false;
  }

  function drawBox(r, mine) {
    var locked = !!(mine && mine.locked);
    var guess = mine ? mine.guess || "" : "", picked = mine ? mine.prompter || "" : "";
    var head = "<h2>Guess the " + (r.hide_prompt ? "prompt" : "prompter") + "</h2>" +
      '<p class="block-note">This round hides ' + esc(what(r)) + " from Spectators until voting closes. " +
      (r.hide_prompt ? "Guess the prompt from the tracks: when voting closes, Claude scores how close you got, from 0 to 5. " : "") +
      (r.hide_prompter ? "Pick who wrote it for 3 more. " : "") +
      "Your guess locks when you submit your ballot.</p>";
    if (locked) {
      state.host.innerHTML = head + '<div class="gs-locked"><b>Your guess, locked</b>' +
        (r.hide_prompt ? "<p>" + (guess ? "“" + esc(guess) + "”" : "No guess at the prompt.") + "</p>" : "") +
        (r.hide_prompter ? "<p>Written by: " + esc(nameOf(picked) || "no pick") + "</p>" : "") + "</div>";
      state.host.hidden = false;
      return;
    }
    state.host.innerHTML = head + '<form class="sub-form gs-form" id="gsForm" novalidate>' +
      (r.hide_prompt ? '<label class="sub-label" for="gsGuess">The prompt, as you’d guess it</label>' +
        '<textarea class="sub-input sub-textarea" id="gsGuess" maxlength="' + MAX + '" rows="2" placeholder="Songs about…">' + esc(guess) + "</textarea>" +
        '<span class="gs-count" id="gsCount"></span>' : "") +
      (r.hide_prompter ? '<label class="sub-label" for="gsWho">Who wrote it?</label>' +
        '<select class="sub-input" id="gsWho"><option value="">Not sure</option>' + state.djs.map(function (d) {
          return '<option value="' + esc(d.id) + '"' + (d.id === picked ? " selected" : "") + ">" + esc(d.name) + "</option>";
        }).join("") + "</select>" : "") +
      '<div class="sub-actions"><button type="submit" class="sub-btn" id="gsSave">Save guess</button></div>' +
      '<p class="sub-msg" id="gsMsg" role="status" hidden></p></form>';
    state.host.hidden = false;
    count();
    $("gsForm").addEventListener("submit", save);
    if ($("gsGuess")) $("gsGuess").addEventListener("input", count);
  }

  function nameOf(id) {
    var d = state.djs.filter(function (x) { return x.id === id; })[0];
    return d ? d.name : "";
  }

  function count() {
    var box = $("gsGuess");
    if (box) $("gsCount").textContent = (MAX - box.value.length) + " left";
  }

  function say(text, good) {
    var m = $("gsMsg");
    m.textContent = text;
    m.className = "sub-msg" + (good ? " is-good" : " is-error");
    m.hidden = !text;
  }

  function save(ev) {
    ev.preventDefault();
    var r = state.round;
    var guess = $("gsGuess") ? $("gsGuess").value.trim() : "";
    var who = $("gsWho") ? $("gsWho").value : "";
    $("gsSave").disabled = true;
    api().savePromptGuess(r.id, guess, who || null).then(function () {
      say("Saved. You can change it until you submit your ballot.", true);
    }).catch(function (err) {
      say("Not saved: " + errText(err));
    }).then(function () { $("gsSave").disabled = false; });
  }

  // Once voting has closed: any guess still without a score is scored now,
  // once per page, and the results redrawn with it.
  function gradeIfNeeded(r) {
    if (!r.hide_prompt || state.graded[r.id]) return;
    state.graded[r.id] = true;
    api().roundGuesses(r.id).then(function (rows) {
      var waiting = (rows || []).some(function (g) { return g.score == null && g.guess; });
      if (!waiting) return;
      return api().gradeGuesses(r.id).then(function (res) {
        if (res && res.graded && window.PFMLVoting && $("rpVote")) window.PFMLVoting.render(r, $("rpVote"));
      });
    }).catch(function (err) { console.error(err); });
  }

  // a submitted ballot locks the guess: show it locked
  document.addEventListener("pfml:ballot-submitted", function () {
    if (state.host && state.round) render(state.host, state.round);
  });

  window.PFMLGuess = { render: render };
})();
