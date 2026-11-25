/* ==========================================================
   PFML - the Commissioner page (/commissioner)

   Where the admin and the commissioners run the site's rounds: open one,
   change the open one (name, description, deadline, and voting's when it
   votes here), close it early, and rename or redescribe any earlier one.
   The admin also chooses who's a commissioner, sees the league status, and
   can delete an earlier round that was never really played.
   It took over the admin form the Submit page used to have (2026-10-25).
   Since 2026-11-25 it's in tabs (Now, Seasons, Announce, People, Log,
   More): the Now tab is now.js, Seasons is seasons.js, and the rest is
   here, with the activity log, scheduled and season-only announcements,
   and the admin's invite links.

   The database holds every rule (supabase/schema.sql, commissioners): only
   a commissioner can write a round, only the admin sets roles, and nobody
   signed in can reopen a deadline once it has passed. README, Commissioners.
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
  // now.js's in-page "are you sure?", or the browser's own if it didn't load
  function ask(anchor, text, yes) {
    return window.PFMLAsk ? window.PFMLAsk(anchor, text, yes) : Promise.resolve(window.confirm(text));
  }

  function role() { return PFML.member && PFML.member.role; }
  function isAdmin() { return role() === "admin"; }
  function isCommissioner() { return role() === "admin" || role() === "commissioner"; }

  // deletable: for the admin, round id -> how many tracks it holds, for each
  // round the database would let them delete (deletable_site_rounds)
  var state = { rounds: [], seasons: [], index: null, timer: 0, deletable: {} };

  function isOpen(r) { return PFML.roundPhase(r) === "submitting"; }
  // a season set up on the site runs its rounds from its own section
  // (seasons.js), not from the round form or the earlier rounds
  function inSiteSeason(r) { return state.seasons.some(function (s) { return s.key === r.season_key; }); }

  // voting.js (voting on the site, off until the user switches it on); a
  // stand-in that's always off if it didn't load
  function voting() {
    return window.PFMLVoting || { on: function () { return false; }, adminFields: function () { return ""; },
                                  readAdmin: function () { return { fields: {} }; }, adminPanel: function () { return null; } };
  }

  function seasonLabel(key) {
    var s = state.index && state.index.seasons.filter(function (x) { return x.key === key; })[0];
    return s ? s.label : "Season " + String(key).replace(/^season/, "");
  }

  function localInput(iso) {
    var d = new Date(iso), pad = function (n) { return (n < 10 ? "0" : "") + n; };
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) + "T" + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }

  // A write that matched no row: RLS hides the refusal, so say it here.
  function wrote(rows) {
    if (!rows || !rows.length) throw new Error("Only the admin or a commissioner can do that.");
    return rows;
  }

  function load() {
    clearTimeout(state.timer);
    // without the list the page still works; it just offers no Delete
    var deletable = isAdmin()
      ? api().deletableSiteRounds().catch(function (err) { console.error(err); return []; })
      : Promise.resolve([]);
    return Promise.all([api().siteRounds(), api().siteSeasons(), deletable]).then(function (res) {
      var rounds = res[0];
      state.seasons = res[1] || [];
      state.rounds = rounds || [];
      state.deletable = {};
      (res[2] || []).forEach(function (d) { state.deletable[d.round_id] = d.tracks; });
      // redraw when the open round's deadline passes, so its form goes, or
      // when the next scheduled round opens
      var open = state.rounds.filter(isOpen)[0];
      var next = state.rounds.filter(function (r) { return PFML.roundPhase(r) === "upcoming"; })
        .sort(function (a, b) { return Date.parse(a.opens_at) - Date.parse(b.opens_at); })[0];
      var until = open ? open.closes_at : next ? next.opens_at : null;
      if (until) {
        var ms = Date.parse(until) - Date.now() + 1500;
        if (ms < 2147483647) state.timer = setTimeout(load, ms);
      }
      render();
    }).catch(function (err) {
      console.error(err);
      $("cmLine").textContent = "Couldn’t load the rounds: " + errText(err);
    });
  }

  function render() {
    var open = state.rounds.filter(isOpen)[0] || null;
    $("cmLine").textContent = open && open.paused ? "“" + open.name + "” is open, and its season is paused."
      : open ? "“" + open.name + "” is open. Submissions close " + PFML.closes(open.closes_at).at + "."
      : "No round is open for submissions.";
    renderRoundForm(open);
    renderRounds(open);
    if (window.PFMLSeasons) {
      window.PFMLSeasons.render({ rounds: state.rounds, seasons: state.seasons, index: state.index, reload: load });
    }
    if (window.PFMLNow) window.PFMLNow.render({ rounds: state.rounds, seasons: state.seasons, reload: load });
    renderAnnouncements();
    if (isAdmin()) { renderPeople(); renderLeagueStatus(); }
    renderLog(false);
  }

  /* ---- the open round, or opening one ---- */

  function renderRoundForm(r) {
    // a round opened here is for a season played in Music League; a new
    // season is set up in Seasons, below, and its rounds come with it
    var seasons = state.index ? state.index.seasons.slice().reverse().filter(function (s) { return !inSiteSeason({ season_key: s.key }); }) : [];
    var options = seasons.map(function (s, i) {
      return '<option value="' + esc(s.key) + '"' + (i === 0 ? " selected" : "") + ">" + esc(s.label) + "</option>";
    }).join("");

    var box = $("cmRound");
    box.innerHTML =
      "<h2>" + (r ? "The open round" : "Open a round") + "</h2>" +
      '<form class="sub-admin-form" id="subAdminForm" novalidate>' +
        (r ? "" : '<label class="sub-label" for="subAdmSeason">Season</label><select class="sub-input" id="subAdmSeason">' + options + "</select>") +
        '<label class="sub-label" for="subAdmName">Round name</label>' +
        '<input class="sub-input" id="subAdmName" maxlength="120" placeholder="Round 7: Live Tracks" value="' + esc(r ? r.name : "") + '">' +
        '<label class="sub-label" for="subAdmPrompt">Description</label>' +
        '<textarea class="sub-input sub-textarea" id="subAdmPrompt" maxlength="2000" rows="3">' + esc(r ? r.prompt : "") + "</textarea>" +
        '<label class="sub-label" for="subAdmCloses">Submissions close (your time)</label>' +
        '<input class="sub-input" id="subAdmCloses" type="datetime-local" value="' + (r ? localInput(r.closes_at) : "") + '">' +
        (window.PFMLSeasons ? window.PFMLSeasons.ruleFields(r || {}, "subAdm") : "") +
        voting().adminFields(r) +
        '<p class="sub-msg" id="subAdmMsg" role="status" hidden></p>' +
        '<div class="sub-actions"><button type="submit" class="sub-btn">' + (r ? "Save changes" : "Open the round") + "</button>" +
          (r ? '<button type="button" class="sub-btn sub-btn-quiet" id="subAdmClose">Close submissions now</button>' : "") + "</div>" +
      "</form>";
    box.hidden = false;
    $("subAdminForm").addEventListener("submit", function (ev) { ev.preventDefault(); saveRound(r); });
    if (r) $("subAdmClose").addEventListener("click", function () { closeRound(r); });
    // a round voting here: its deadline, and closing voting early
    var votingRound = state.rounds.filter(function (x) { return voting().on(x) && PFML.roundPhase(x) === "voting"; })[0];
    var panel = votingRound && voting().adminPanel(votingRound, load, adminMsg);
    if (panel) box.insertBefore(panel, box.firstChild);
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
    if (window.PFMLSeasons) {
      var rules = window.PFMLSeasons.readRules($("subAdminForm"));
      if (rules.error) return adminMsg(rules.error);
      fields.services = rules.services;
      fields.repeat_rule = rules.repeat_rule;
    }
    var vote = voting().readAdmin(r, closesAt);
    if (vote.error) return adminMsg(vote.error);
    Object.keys(vote.fields).forEach(function (k) { fields[k] = vote.fields[k]; });
    var done = r ? api().updateSiteRound(r.id, fields) : api().openSiteRound(fields);
    done.then(wrote).then(load).catch(function (err) { adminMsg(errText(err)); });
  }

  function closeRound(r) {
    ask($("subAdmClose"), "Close submissions for “" + r.name + "” now? Members won't be able to submit or change their tracks.", "Close submissions")
      .then(function (yes) {
        if (!yes) return;
        api().updateSiteRound(r.id, { closed_at: new Date().toISOString() })
          .then(wrote).then(load).catch(function (err) { adminMsg(errText(err)); });
      });
  }

  /* ---- earlier rounds: name and description ---- */

  function phaseText(r) {
    var phase = PFML.roundPhase(r);
    if (phase === "upcoming") return "Opens " + PFML.closes(r.opens_at).at;
    if (!voting().on(r)) phase = "closed";
    if (phase === "voting") return "Voting until " + PFML.closes(r.voting_closes_at).at;
    if (phase === "finished") return "Voting closed";
    return "Submissions closed " + PFML.closes(r.closed_at || r.closes_at).at;
  }

  function renderRounds(open) {
    var rounds = state.rounds.filter(function (r) { return r !== open && !inSiteSeason(r); });
    $("cmRounds").hidden = !rounds.length;
    $("cmRoundList").innerHTML = rounds.map(function (r) {
      return '<details class="cm-round" data-round="' + esc(r.id) + '">' +
        '<summary><span class="cm-round-name">' + esc(r.name) + "</span>" +
          "<small>" + esc(seasonLabel(r.season_key)) + " · " + esc(phaseText(r)) + "</small></summary>" +
        '<form class="sub-admin-form cm-round-form" novalidate>' +
          '<label class="sub-label" for="cmName-' + esc(r.id) + '">Round name</label>' +
          '<input class="sub-input" id="cmName-' + esc(r.id) + '" name="name" maxlength="120" value="' + esc(r.name) + '">' +
          '<label class="sub-label" for="cmPrompt-' + esc(r.id) + '">Description</label>' +
          '<textarea class="sub-input sub-textarea" id="cmPrompt-' + esc(r.id) + '" name="prompt" maxlength="2000" rows="3">' + esc(r.prompt) + "</textarea>" +
          '<p class="sub-msg" role="status" hidden></p>' +
          '<div class="sub-actions"><button type="submit" class="sub-btn">Save</button>' +
            (r.id in state.deletable ? '<button type="button" class="sub-btn sub-btn-quiet cm-round-delete">Delete this round</button>' : "") +
          "</div>" +
        "</form></details>";
    }).join("");
  }

  // The admin deletes a round that was never really played: empty, or a
  // test. The database decides which (site_round_delete_problem) and refuses
  // the rest, Round 7 and every real round among them. No undo.
  function onRoundDelete(ev) {
    var b = ev.target.closest(".cm-round-delete");
    if (!b) return;
    var form = b.closest(".cm-round-form");
    var id = form.closest(".cm-round").getAttribute("data-round");
    var r = state.rounds.filter(function (x) { return x.id === id; })[0];
    var tracks = state.deletable[id] || 0;
    if (!r) return;
    ask(b, "Delete “" + r.name + "” for good? " +
        (tracks ? (tracks === 1 ? "Its 1 track goes" : "Its " + tracks + " tracks go") + " with it. " : "") +
        "This can’t be undone.", "Delete it").then(function (yes) {
      if (!yes) return;
      var msg = form.querySelector(".sub-msg");
      b.disabled = true;
      api().deleteSiteRound(id).then(load).catch(function (err) {
        b.disabled = false;
        msg.textContent = errText(err);
        msg.className = "sub-msg is-error";
        msg.hidden = false;
      });
    });
  }

  function onRoundSave(ev) {
    var form = ev.target.closest(".cm-round-form");
    if (!form) return;
    ev.preventDefault();
    var id = form.closest(".cm-round").getAttribute("data-round");
    var msg = form.querySelector(".sub-msg");
    var name = form.elements.name.value.trim(), prompt = form.elements.prompt.value.trim();
    function say(text, ok) { msg.textContent = text; msg.className = "sub-msg" + (ok ? " is-good" : " is-error"); msg.hidden = false; }
    if (!name) { say("Give the round a name."); return; }
    api().updateSiteRound(id, { name: name, prompt: prompt }).then(wrote).then(function () {
      state.rounds.forEach(function (r) { if (r.id === id) { r.name = name; r.prompt = prompt; } });
      form.closest(".cm-round").querySelector(".cm-round-name").textContent = name;
      say("Saved.", true);
    }).catch(function (err) { say(errText(err)); });
  }

  /* ---- announcements: a message to everyone, or to a season ---- */

  // Posted to Home for a week and pushed to everyone with notifications on
  // (send-reminders, announcements_claim): now, or at a set time; to the
  // whole league, or to one season's players. Its words can change after;
  // its time, until it goes out. Any commissioner can take one down.
  function annAt(a) { return Date.parse(a.send_at || a.created_at); }
  function annTime(t) {
    return new Date(t).toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }

  function renderAnnouncements() {
    var box = $("cmAnnounce");
    Promise.all([api().announcements(), api().people()]).then(function (res) {
      var people = res[1] || {};
      var seasons = state.seasons.slice().sort(function (a, b) { return b.key.localeCompare(a.key, undefined, { numeric: true }); });
      var nameOf = function (key) { var s = seasons.filter(function (x) { return x.key === key; })[0]; return s ? s.name : key; };
      var list = (res[0] || []).slice().sort(function (a, b) { return annAt(b) - annAt(a); });
      state.announcements = list;
      box.innerHTML = "<h2>Announcements</h2>" +
        '<p class="block-note">A message on Home for a week, and on the phone of everyone with notifications on.</p>' +
        '<form class="sub-admin-form" id="cmAnnounceForm" novalidate>' +
          '<label class="sub-label" for="cmAnnounceText">Your message</label>' +
          '<textarea class="sub-input sub-textarea" id="cmAnnounceText" maxlength="1000" rows="3"></textarea>' +
          '<fieldset class="cn-choice"><legend class="sub-label">When</legend>' +
            '<label><input type="radio" name="when" value="now" checked> Now</label>' +
            '<label><input type="radio" name="when" value="later"> Later</label>' +
            '<input class="sub-input" type="datetime-local" name="send_at" aria-label="Send at (your time)"></fieldset>' +
          (seasons.length ? '<fieldset class="cn-choice"><legend class="sub-label">Who</legend>' +
            '<label><input type="radio" name="who" value="" checked> The whole league</label>' +
            seasons.map(function (s) {
              return '<label><input type="radio" name="who" value="' + esc(s.key) + '"> ' + esc(s.name) + "\u2019s players</label>";
            }).join("") + "</fieldset>" : "") +
          '<p class="sub-msg" id="cmAnnounceMsg" role="status" hidden></p>' +
          '<div class="sub-actions"><button type="submit" class="sub-btn">Post it</button></div>' +
        "</form>" +
        (list.length ? '<ul class="cm-announce-list">' + list.map(function (a) {
          var later = annAt(a) > Date.now();
          return '<li data-ann="' + esc(a.id) + '"' + (later ? ' class="is-later"' : "") + "><p>" + esc(a.body) + "</p><small>" +
            esc(people[a.created_by] ? people[a.created_by].name : "A commissioner") + " \u00b7 " +
            (later ? "goes out " : "") + esc(annTime(annAt(a))) +
            (a.season_key ? " \u00b7 " + esc(nameOf(a.season_key)) + " only" : "") + (a.edited_at ? " \u00b7 edited" : "") + "</small>" +
            '<div class="sub-actions"><button type="button" class="sub-btn sub-btn-quiet sub-btn-small" data-ann-act="edit">Edit</button>' +
              '<button type="button" class="sub-btn sub-btn-quiet sub-btn-small" data-ann-act="down">Take down</button></div></li>';
        }).join("") + "</ul>" : "");
      box.hidden = false;
    }).catch(function (err) { console.error(err); });
  }

  function announceMsg(text, good) {
    var m = $("cmAnnounceMsg");
    m.textContent = text;
    m.className = "sub-msg" + (good ? " is-good" : " is-error");
    m.hidden = !text;
  }

  // the form's send time: null for now, or an error
  function sendAtOf(form) {
    var later = form.querySelector('input[name="when"]:checked');
    if (!later || later.value !== "later") return { at: null };
    var t = form.elements.send_at.value ? new Date(form.elements.send_at.value) : null;
    if (!t || isNaN(t) || t.getTime() <= Date.now()) return { error: "Pick a time in the future to send it." };
    return { at: t.toISOString() };
  }

  function onAnnounce(ev) {
    if (ev.type === "submit") {
      ev.preventDefault();
      var form = ev.target;
      if (form.id === "cmAnnounceForm") { postAnnouncement(form); return; }
      editAnnouncement(form);
      return;
    }
    var b = ev.target.closest("[data-ann-act]");
    if (!b) return;
    var item = b.closest("[data-ann]");
    var ann = (state.announcements || []).filter(function (x) { return x.id === item.getAttribute("data-ann"); })[0];
    if (!ann) return;
    if (b.getAttribute("data-ann-act") === "edit") {
      var open = item.querySelector("form");
      if (open) { open.remove(); return; }
      var later = annAt(ann) > Date.now();
      item.insertAdjacentHTML("beforeend", '<form class="sub-admin-form cm-ann-edit" novalidate>' +
        '<textarea class="sub-input sub-textarea" name="body" maxlength="1000" rows="3" aria-label="The message">' + esc(ann.body) + "</textarea>" +
        (later ? '<label class="sub-label" for="cmAnnAt-' + esc(ann.id) + '">Goes out (your time)</label>' +
          '<input class="sub-input" id="cmAnnAt-' + esc(ann.id) + '" type="datetime-local" name="send_at" value="' + esc(localInput(ann.send_at)) + '">'
          : '<p class="block-note">It has gone out, so only its words can change. Notifications already sent stay as they were.</p>') +
        '<p class="sub-msg is-error" role="status" hidden></p>' +
        '<div class="sub-actions"><button type="submit" class="sub-btn sub-btn-small">Save</button></div></form>');
      return;
    }
    ask(b, "Take this announcement down? It leaves Home; any notification already sent stays sent.", "Take it down").then(function (yes) {
      if (yes) api().deleteAnnouncement(ann.id).then(renderAnnouncements).catch(function (err) { announceMsg(errText(err)); });
    });
  }

  function postAnnouncement(form) {
    var text = $("cmAnnounceText").value.trim();
    if (!text) { announceMsg("Write a message first."); return; }
    var at = sendAtOf(form);
    if (at.error) { announceMsg(at.error); return; }
    var who = form.querySelector('input[name="who"]:checked');
    var season = who && who.value ? who.value : null;
    var to = season ? ((state.seasons.filter(function (s) { return s.key === season; })[0] || {}).name || "the season") + "\u2019s players" : "the whole league";
    ask(form.querySelector('button[type="submit"]'),
        at.at ? "Send this to " + to + " " + annTime(Date.parse(at.at)) + "?" : "Post this to " + to + " and notify them now?",
        at.at ? "Schedule it" : "Post it").then(function (yes) {
      if (!yes) return;
      api().postAnnouncement(text, at.at, season).then(renderAnnouncements).catch(function (err) { announceMsg(errText(err)); });
    });
  }

  function editAnnouncement(form) {
    var li = form.closest("[data-ann]");
    var a = (state.announcements || []).filter(function (x) { return x.id === li.getAttribute("data-ann"); })[0];
    var msg = form.querySelector(".sub-msg");
    var say = function (text) { msg.textContent = text; msg.hidden = false; };
    var body = form.elements.body.value.trim();
    if (!a) return;
    if (!body) { say("Write a message first."); return; }
    var at = a.send_at;
    if (form.elements.send_at && form.elements.send_at.value) {
      var t = new Date(form.elements.send_at.value);
      if (isNaN(t) || t.getTime() <= Date.now()) { say("Pick a time in the future to send it."); return; }
      at = t.toISOString();
    }
    api().editAnnouncement(a.id, body, at).then(renderAnnouncements).catch(function (err) { say(errText(err)); });
  }

  /* ---- the admin: who's a commissioner ---- */

  function renderPeople() {
    Promise.all([api().people(), api().memberRoles()]).then(function (res) {
      var names = {};
      Object.keys(res[0] || {}).forEach(function (u) { names[res[0][u].competitorId] = res[0][u].name; });
      var rows = (res[1] || []).map(function (m) { return { id: m.competitor_id, role: m.role, name: names[m.competitor_id] || "Member" }; })
        .sort(function (a, b) { return a.name.localeCompare(b.name); });
      $("cmPeopleList").innerHTML = rows.map(function (p) {
        if (p.role === "admin") {
          return '<div class="cm-person"><span>' + esc(p.name) + '</span><small>Admin, always a commissioner</small></div>';
        }
        return '<button type="button" class="cm-person acct-theme" data-player="' + esc(p.id) + '" role="switch" aria-checked="' +
          (p.role === "commissioner") + '" aria-label="' + esc(p.name) + ' is a commissioner"><span>' + esc(p.name) + '</span><span class="acct-switch" aria-hidden="true"></span></button>';
      }).join("");
      $("cmPeople").hidden = false;
    }).catch(function (err) {
      console.error(err);
      $("cmPeopleMsg").textContent = "Couldn’t load the members: " + errText(err);
      $("cmPeopleMsg").hidden = false;
      $("cmPeople").hidden = false;
    });
  }

  function onPersonClick(ev) {
    var b = ev.target.closest("[data-player]");
    if (!b) return;
    // the switch moves at once; it goes back if the save fails
    var on = b.getAttribute("aria-checked") !== "true";
    b.setAttribute("aria-checked", String(on));
    $("cmPeopleMsg").hidden = true;
    api().setCommissioner(b.getAttribute("data-player"), on).catch(function (err) {
      console.error(err);
      b.setAttribute("aria-checked", String(!on));
      $("cmPeopleMsg").textContent = "That didn’t save: " + errText(err);
      $("cmPeopleMsg").hidden = false;
    });
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
        parts.push("<li><b>Not joined the site</b> " + (out.length ? out.length + '<ul class="cn-invites">' + out.map(function (p) {
          var made = waiting[p.id];
          return '<li data-invite="' + esc(p.id) + '" data-name="' + esc(p.name) + '"><span>' + esc(p.name) + " <small>" + (made
            ? "link made " + esc(new Date(made).toLocaleDateString(undefined, { month: "short", day: "numeric" })) + ", not used yet"
            : "no link yet") + "</small></span>" +
            '<button type="button" class="sub-btn sub-btn-quiet sub-btn-small" data-act="invite">' + (made ? "Show the link" : "Make a link") + "</button></li>";
        }).join("") + "</ul>" : "everyone taking part has joined") + "</li>");
      }
      if (!parts.length) return;
      $("subAdmStatus").innerHTML = "<h3>League status</h3><ul>" + parts.join("") + "</ul>" +
        '<p class="block-note">An invite link ties whoever opens it, signed in with Google, to that player for good, and works once. ' +
        "Send each one privately, to the right person.</p>";
      $("cmStatus").hidden = false;
    });
  }

  // The admin makes (or shows again) a player's invite link, to copy or
  // share from a phone. The log notes it, never the link.
  function onInvite(ev) {
    var b = ev.target.closest('[data-act="invite"]');
    if (b) {
      var li = b.closest("[data-invite]");
      b.disabled = true;
      api().createInvite(li.getAttribute("data-invite")).then(function (code) {
        var link = "https://pfml.fun/?invite=" + encodeURIComponent(code);
        b.remove();
        li.insertAdjacentHTML("beforeend", '<div class="cn-invite-link"><input class="sub-input" readonly value="' + esc(link) +
          '" aria-label="Invite link for ' + esc(li.getAttribute("data-name")) + '">' +
          '<div class="sub-actions"><button type="button" class="sub-btn sub-btn-small" data-act="copy">Copy</button>' +
          (navigator.share ? '<button type="button" class="sub-btn sub-btn-quiet sub-btn-small" data-act="share">Share</button>' : "") + "</div></div>");
      }).catch(function (err) { b.disabled = false; b.textContent = errText(err); });
      return;
    }
    var c = ev.target.closest('[data-act="copy"], [data-act="share"]');
    if (!c) return;
    var box = c.closest(".cn-invite-link"), url = box.querySelector("input").value;
    if (c.getAttribute("data-act") === "share") {
      navigator.share({ title: "PFML", text: "Your link to join PFML. It works once.", url: url }).catch(function () {});
      return;
    }
    var done = navigator.clipboard ? navigator.clipboard.writeText(url) : Promise.reject(new Error("no clipboard"));
    done.then(function () { c.textContent = "Copied"; }, function () { box.querySelector("input").select(); c.textContent = "Selected: copy it"; });
  }

  /* ---- the activity log ---- */

  // Newest first, 50 at a time; "Show older" pages on. Drawn when its tab
  // is open, and again after any change while it is.
  var log = { last: null, loaded: false };
  function renderLog(more) {
    if (!more && currentTab() !== "log") { log.loaded = false; return; }
    if (typeof api().activityLog !== "function") return;
    api().activityLog(more ? log.last : null, 50).then(function (rows) {
      var html = rows.map(function (x) {
        return "<li><span>" + esc(x.action) + "</span><small>" + esc(x.who) + " · " +
          esc(new Date(x.at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })) + "</small></li>";
      }).join("");
      if (more) $("cmLogList").insertAdjacentHTML("beforeend", html);
      else $("cmLogList").innerHTML = html || '<li class="cn-log-empty">Nothing yet.</li>';
      if (rows.length) log.last = rows[rows.length - 1].id;
      log.loaded = true;
      $("cmLogMore").hidden = rows.length < 50;
      $("cmLogMsg").hidden = true;
      $("cmLog").hidden = false;
    }).catch(function (err) {
      $("cmLogMsg").textContent = "Couldn’t load the log: " + errText(err);
      $("cmLogMsg").hidden = false;
      $("cmLog").hidden = false;
    });
  }

  /* ---- tabs ---- */

  // The open tab is in the address (#seasons), so a reload or a link from
  // the Now tab lands on it. People is the admin's only.
  var TABS = ["now", "seasons", "announce", "people", "log", "more"];
  function currentTab() {
    var t = (location.hash || "").replace("#", "");
    if (t === "people" && !isAdmin()) t = "";
    return TABS.indexOf(t) !== -1 ? t : "now";
  }
  function showTab() {
    var t = currentTab();
    document.querySelector("main").setAttribute("data-tab", t);
    Array.prototype.forEach.call(document.querySelectorAll("#cmTabs [data-tab]"), function (a) {
      if (a.getAttribute("data-tab") === t) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    if (t === "log" && !log.loaded) renderLog(false);
  }

  /* ---- start ---- */

  function boot() {
    if (!isCommissioner()) {
      $("cmLine").textContent = "This page is for the league’s commissioners.";
      return;
    }
    $("cmRoundList").addEventListener("submit", onRoundSave);
    $("cmRoundList").addEventListener("click", onRoundDelete);
    $("cmPeopleList").addEventListener("click", onPersonClick);
    $("cmAnnounce").addEventListener("submit", onAnnounce);
    $("cmAnnounce").addEventListener("click", onAnnounce);
    $("subAdmStatus").addEventListener("click", onInvite);
    $("cmLogMore").addEventListener("click", function () { renderLog(true); });
    $("cmTabs").hidden = false;
    if (isAdmin()) document.querySelector('#cmTabs [data-tab="people"]').hidden = false;
    window.addEventListener("hashchange", function () { showTab(); window.scrollTo({ top: 0, behavior: "instant" }); });
    showTab();
    // season names for the round list and the season picker; the page
    // works without them
    PFML.loadJSON("index.json").then(function (index) { state.index = index; })
      .catch(function (err) { console.error(err); })
      .then(load);
  }

  PFML.ready.then(boot);
})();
