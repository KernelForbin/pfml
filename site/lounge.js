/* ==========================================================
   PFML - the voters' lounge (the round page)

   Asked for 2026-10-28: a room where only the people who have submitted
   their ballot can chat while voting is open, anonymously. Each chatter is
   an instrument for the round (Kazoo, Theremin...), the same all round,
   and nobody, the admin included, can see who's who. The user's calls:
   one message per person every 24 hours, 280 characters, never named,
   and when voting closes it locks and stays readable under the results.
   Reactions are unlimited, so the room stays lively between messages.

   The database holds every rule (lounge_status, lounge_post and the rest,
   supabase/schema.sql), and gives out aliases, never writers. The round
   demo's stand-in round carries practice: true, which uses its practice
   lounge instead (round-demo.js). README, Voters' lounge.
   ========================================================== */

(function () {
  "use strict";

  var MAX = 280;
  var LIVE_MS = 6000;     // new messages and reactions, while the lounge is open and on screen
  var DOOR_MS = 30000;    // the door, so it opens as the third voter votes
  var REACTIONS = ["fire", "laugh", "hundred", "eyes", "heart", "grimace"];

  function $(id) { return document.getElementById(id); }
  function api() { return PFML.api; }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function errText(err) { return (err && err.message) || String(err); }

  var state = { host: null, round: null, practice: false, status: null, messages: [], timer: 0, ticking: 0, sending: false,
                drawn: "", compose: "" };

  // Draws the lounge into `host` for the site round `r`, and keeps it live.
  function render(host, r) {
    state.host = host;
    state.round = r;
    state.practice = !!r.practice;
    host.addEventListener("click", onClick);
    host.addEventListener("input", onInput);
    // a ballot just submitted opens the door (voting.js)
    document.addEventListener("pfml:ballot-submitted", function () { refresh(); });
    document.addEventListener("visibilitychange", function () { if (document.visibilityState === "visible") refresh(); });
    refresh();
  }

  function refresh() {
    clearTimeout(state.timer);
    var r = state.round;
    return api().loungeStatus(r.id, state.practice).then(function (st) {
      state.status = st;
      if (!st || (st.phase !== "voting" && st.phase !== "finished")) { hide(); return; }
      if (st.open || st.phase === "finished") {
        return api().loungeMessages(r.id, state.practice).then(function (rows) {
          state.messages = rows || [];
          if (st.phase === "finished" && !state.messages.length) { hide(); return; }
          drawRoom();
        });
      }
      drawDoor();
    }).catch(function (err) {
      console.error(err);
    }).then(function () {
      var st = state.status;
      // live while the room is open; the door checks less often; a finished
      // lounge doesn't change
      if (st && st.phase === "voting") state.timer = setTimeout(tick, st.open ? LIVE_MS : DOOR_MS);
    });
  }

  function tick() {
    if (document.visibilityState !== "visible") { state.timer = setTimeout(tick, LIVE_MS); return; }
    refresh();
  }

  function hide() {
    state.host.hidden = true;
    state.host.innerHTML = "";
  }

  // Before you're in: why not yet, and what's waiting.
  function drawDoor() {
    var st = state.status;
    var inside = st.messages ? " " + st.messages + (st.messages === 1 ? " message" : " messages") + " so far." : "";
    var line = !st.eligible
      ? "For this round’s voters only, while voting is open." + inside
      : !st.in
        ? "Submit your ballot to get in." + (st.voters ? " " + st.voters + (st.voters === 1 ? " person has" : " people have") + " voted so far." : "") + inside
        : "It opens once " + st.needed + " people have voted (" + st.voters + " so far), so nobody’s the only one in it.";
    state.host.innerHTML = head() + '<div class="lg-door"><span class="lg-door-icon" aria-hidden="true">' + LOCK + "</span><p>" + esc(line) + "</p></div>";
    state.host.hidden = false;
  }

  function head() {
    return '<div class="lg-head"><h2>Voters’ lounge</h2>' + (state.practice ? '<span class="lg-practice">Practice</span>' : "") + "</div>";
  }

  // The room: who you are here, the messages, and the box to write in.
  // Each part is drawn again only when what it shows has changed, so the
  // check every few seconds never moves the reader's place or cursor, or
  // touches what they're typing.
  function drawRoom() {
    var st = state.status, open = st.phase === "voting";
    if (!$("lgRoom")) {
      state.host.innerHTML = head() +
        '<div id="lgRoom">' +
          '<p class="block-note lg-intro" id="lgIntro"></p>' +
          '<ol class="lg-list" id="lgList" aria-live="polite"></ol>' +
          '<div class="lg-compose" id="lgCompose"></div>' +
        "</div>";
      state.host.hidden = false;
      state.drawn = "";
      state.compose = "";
    }
    $("lgIntro").innerHTML = open
      ? "You’re <b>" + esc(st.alias) + "</b> in here. Everyone’s an instrument, and nobody can see who’s who, the admin included. " +
        "Keep it that way: no saying which track is yours. One message every " + gapText(st.gap_minutes) + ", " + MAX +
        " characters; reactions as often as you like."
      : "From the lounge, while voting was open. Everyone was an instrument, and still is.";
    // the minute too, so "5m ago" moves on
    var list = $("lgList"), shown = JSON.stringify([open, Math.floor(Date.now() / 60000), state.messages]);
    if (shown !== state.drawn) {
      // keep the reader at the bottom if they were there
      var atBottom = !state.drawn || list.scrollHeight - list.scrollTop - list.clientHeight < 40;
      list.innerHTML = state.messages.length
        ? state.messages.map(messageHtml).join("")
        : '<li class="lg-empty">Nobody’s said anything yet. Go first?</li>';
      state.drawn = shown;
      if (atBottom) list.scrollTop = list.scrollHeight;
    }
    var next = open && st.next_post_at ? Date.parse(st.next_post_at) : 0;
    var mode = !open ? "none" : next > Date.now() ? "wait:" + next : "box";
    if (mode !== state.compose) {
      state.compose = mode;
      drawCompose(mode, next);
    }
  }

  function messageHtml(m) {
    var admin = PFML.member && PFML.member.role === "admin";
    var open = state.status.phase === "voting";
    var counts = m.reactions || {}, mine = m.my_reactions || [];
    var reacts = m.removed ? "" : '<div class="lg-reacts">' + REACTIONS.map(function (k) {
      var n = counts[k] || 0, on = mine.indexOf(k) !== -1;
      if (!open && !n) return "";
      return '<button type="button" class="lg-react' + (on ? " is-on" : "") + (n ? "" : " is-zero") + '" data-react="' + k + '" data-id="' + m.id + '"' +
        (open ? "" : " disabled") + ' aria-pressed="' + on + '" aria-label="' + k + (n ? ", " + n : "") + '">' +
        '<span aria-hidden="true">' + PFML.reactionGlyph(k) + "</span>" + (n ? "<b>" + n + "</b>" : "") + "</button>";
    }).join("") + "</div>";
    return '<li class="lg-msg' + (m.mine ? " is-mine" : "") + '">' +
      PFML.avatar("lounge:" + m.alias, m.alias) +
      '<div class="lg-msg-body">' +
        '<p class="lg-who"><b>' + esc(m.alias) + "</b>" + (m.mine ? '<span class="lg-you">You</span>' : "") +
          '<span class="lg-when">' + esc(PFML.when(m.created_at)) + "</span>" +
          (admin && open && !m.removed ? '<button type="button" class="lg-remove" data-remove="' + m.id + '">Remove</button>' : "") + "</p>" +
        (m.removed ? '<p class="lg-text lg-removed">Removed by the admin.</p>' : '<p class="lg-text">' + esc(m.body) + "</p>") +
        reacts +
      "</div></li>";
  }

  // The box to write in, or when the next message can go.
  function drawCompose(mode, next) {
    var box = $("lgCompose");
    clearInterval(state.ticking);
    if (mode === "none") { box.innerHTML = ""; return; }
    if (mode !== "box") {
      box.innerHTML = '<p class="lg-wait" id="lgWait"></p>';
      var show = function () {
        var left = next - Date.now();
        if (left <= 0) { clearInterval(state.ticking); refresh(); return; }
        $("lgWait").textContent = "Your next message can go in " + leftText(left) + ". Reactions are open any time.";
      };
      show();
      state.ticking = setInterval(show, 30000);
      return;
    }
    box.innerHTML = '<textarea class="sub-input lg-text-in" id="lgText" rows="2" maxlength="' + MAX + '" ' +
        'placeholder="Say something to the room" aria-label="Your message to the lounge"></textarea>' +
      '<div class="lg-send-row"><span class="lg-count" id="lgCount"></span>' +
        '<button type="button" class="sub-btn" id="lgSend">Send</button></div>' +
      '<p class="sub-msg" id="lgMsg" role="status" hidden></p>';
    count();
  }

  function count() {
    var t = $("lgText");
    if (!t) return;
    var left = MAX - t.value.length;
    $("lgCount").textContent = left + " left · one message every " + gapText(state.status.gap_minutes);
    $("lgSend").disabled = !t.value.trim() || state.sending;
  }

  function onInput(ev) { if (ev.target.id === "lgText") count(); }

  function onClick(ev) {
    var b = ev.target.closest("button");
    if (!b) return;
    if (b.id === "lgSend") return send();
    if (b.hasAttribute("data-react")) return react(b);
    if (b.hasAttribute("data-remove")) return remove(b);
  }

  function send() {
    var t = $("lgText"), text = t.value.trim();
    if (!text || state.sending) return;
    state.sending = true;
    count();
    api().loungePost(state.round.id, state.practice, text).then(function () {
      t.value = "";
      return refresh();
    }).catch(function (err) {
      var m = $("lgMsg");
      if (m) { m.textContent = errText(err); m.className = "sub-msg is-error"; m.hidden = false; }
    }).then(function () { state.sending = false; count(); });
  }

  // A reaction shows at once, then the room catches up.
  function react(b) {
    var id = +b.getAttribute("data-id"), k = b.getAttribute("data-react"), on = b.getAttribute("aria-pressed") !== "true";
    var m = state.messages.filter(function (x) { return x.id === id; })[0];
    if (!m) return;
    m.reactions = m.reactions || {};
    m.my_reactions = m.my_reactions || [];
    m.reactions[k] = Math.max(0, (m.reactions[k] || 0) + (on ? 1 : -1));
    m.my_reactions = on ? m.my_reactions.concat([k]) : m.my_reactions.filter(function (x) { return x !== k; });
    drawRoom();
    api().loungeReact(id, k, on).catch(function (err) { console.error(err); }).then(refresh);
  }

  function remove(b) {
    if (!window.confirm("Remove this message from the lounge? Everyone sees it was removed, and nobody sees who wrote it.")) return;
    api().loungeRemove(+b.getAttribute("data-remove")).catch(function (err) { window.alert(errText(err)); }).then(refresh);
  }

  function gapText(minutes) {
    return minutes >= 60 ? (minutes / 60) + " hours" : minutes + " minutes";
  }

  function leftText(ms) {
    var mins = Math.ceil(ms / 60000), h = Math.floor(mins / 60), m = mins % 60;
    return h ? h + "h " + m + "m" : m + "m";
  }

  var LOCK = '<svg viewBox="0 0 24 24" width="22" height="22"><rect x="5" y="11" width="14" height="9" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/>' +
    '<path d="M8 11V8a4 4 0 0 1 8 0v3" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';

  window.PFMLLounge = { render: render };
})();
