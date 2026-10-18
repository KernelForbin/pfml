/* ==========================================================
   PFML - the Round 7 hint crossword (/round7hint2)

   A 15x15 puzzle that plays like a newspaper app: pick a square,
   pick it again to switch direction, type to fill. On a touch screen
   it brings its own keyboard (the phone's would cover the grid); on a
   computer the real keyboard drives it, arrows and Tab included.

   Progress and time are kept in this browser only (localStorage), so
   a solver can close the tab and come back. Nothing is sent anywhere.
   ========================================================== */

(function () {
  "use strict";

  var SIZE = 15;
  var STORE = "pfml-xw-round7hint2";

  // The answers, row by row, "#" for a black square. Reversed and
  // base64'd so a glance at the source doesn't solve it; this is a
  // speed bump, not a lock (the page code is public).
  var SOLUTION = "V0VOI0FET1MjVE5FVEFQRVJPI0tFUlQjU09HSU1BTlVSI1NEQVIjRUlEREFMS0NJUyNBVEFEI1NFRUxGIyMjVEFFI1BBU0EjIyMjU1RTSUVIVCNTRVZFRUxTRU9SI1NHVUQjREVHR0VMVENBVCNOT0xZTiNBUklMRVNPSVRPI09MT1MjRVJJTUFSR09SUCNTTEVQU09HIyMjI05XQVkjQlJPIyMjWVNOQVQjU0dFTiNDSUhDQUxMRUFQI0dOT0cjVE9OTExJUkhTI1VBTlUjTk9ZU0VLQVdBI01MNEwjQVBT";

  var CLUES = {
    across: {
      1: "Place for a mud bath",
      4: "Kunj conglomerate",
      8: "Comes to",
      14: "Over there, poetically",
      15: "Two-toed sloth",
      16: "Piercingly high-pitched",
      17: "“Wayne’s World” punchline word",
      18: "Instrument struck with a mallet",
      19: "Saffron rice dish from Valencia",
      20: "Stylish, or Nile Rodgers’s band",
      22: "Darkroom strips, for short",
      24: "Yellow-flowered herb",
      25: "Sphere",
      27: "Sign of boredom",
      29: "Matthew, Mark, Luke and John",
      33: "Concert handout",
      38: "Wrath",
      39: "Guitarist’s moment in the spotlight",
      41: "Serving no practical purpose",
      42: "Pre-euro Italian money",
      44: "Classical guitar string material",
      46: "Diplomat’s asset",
      47: "Four-___ friend",
      49: "Udders",
      51: "Fish eggs",
      52: "Record jackets",
      54: "Believers in God",
      56: "“Right now!,” on a memo",
      58: "Dig in",
      59: "Runs away",
      63: "What a spreadsheet holds",
      65: "Ill, or in slang, awesome",
      69: "Young Scottish boy",
      71: "Radiation dose units",
      73: "Sprint",
      74: "Friends, in Spanish",
      75: "Long hike",
      76: "Mined rock",
      77: "Inventor’s protection",
      78: "Pop",
      79: "Fresh"
    },
    down: {
      1: "Lip-___ (fake singing)",
      2: "A. A. Milne’s bear",
      3: "Against",
      4: "Haul with effort",
      5: "Band behind 1993’s “What’s Up?”",
      6: "Bowling alley strip",
      7: "Hot and humid",
      8: "Cleopatra’s snake",
      9: "And so on, informally",
      10: "Length times width",
      11: "Pottery oven",
      12: "Building extensions",
      13: "Totally kill it, in slang",
      21: "Officer",
      23: "Maple tree fluid",
      26: "Hi-___ (sharp image)",
      28: "Stubbornly misguided",
      29: "Fish breathing organs",
      30: "Bay window",
      31: "Twill suit fabric",
      32: "___ and the Family Stone",
      34: "“Scram!”",
      35: "Stadium crowd sounds",
      36: "Dressy neckwear",
      37: "Doles (out)",
      40: "Like vintage vinyl",
      43: "Era",
      45: "Not in",
      48: "Dodge",
      50: "The Mediterranean, for one",
      53: "Blue",
      55: "“___ My Party” (Lesley Gore hit)",
      57: "Harmony singers’ lines",
      59: "Wing motion",
      60: "Tibetan monk",
      61: "Revise",
      62: "U2 guitarist, with “The”",
      64: "Root in poi",
      66: "Golf club or appliance",
      67: "Robert Smith’s band, with “The”",
      68: "Was aware of",
      70: "Superlative suffix",
      72: "Upbeat Jamaican music genre"
    }
  };

  function $(id) { return document.getElementById(id); }

  /* ---- the puzzle's shape, worked out from the answers ---- */

  var answer = atob(SOLUTION).split("").reverse().join("");
  var cells = [];          // index r*SIZE+c -> { r, c, ans, num, words: {across, down} } or null
  var words = [];          // { dir, num, clue, cells: [index...] }

  function buildModel() {
    var r, c, n = 0;
    for (r = 0; r < SIZE; r++) {
      for (c = 0; c < SIZE; c++) {
        var ch = answer.charAt(r * SIZE + c);
        cells.push(ch === "#" ? null : { r: r, c: c, ans: ch, num: 0, words: {} });
      }
    }
    function open(rr, cc) { return rr >= 0 && rr < SIZE && cc >= 0 && cc < SIZE && cells[rr * SIZE + cc]; }
    for (r = 0; r < SIZE; r++) {
      for (c = 0; c < SIZE; c++) {
        if (!open(r, c)) continue;
        var a = !open(r, c - 1) && open(r, c + 1);
        var d = !open(r - 1, c) && open(r + 1, c);
        if (!a && !d) continue;
        n++;
        cells[r * SIZE + c].num = n;
        if (a) addWord("across", n, r, c, 0, 1);
        if (d) addWord("down", n, r, c, 1, 0);
      }
    }
    function addWord(dir, num, r0, c0, dr, dc) {
      var w = { dir: dir, num: num, clue: CLUES[dir][num] || "", cells: [] };
      for (var rr = r0, cc = c0; open(rr, cc); rr += dr, cc += dc) {
        w.cells.push(rr * SIZE + cc);
        cells[rr * SIZE + cc].words[dir] = w;
      }
      words.push(w);
    }
    // reading order: every Across clue by number, then every Down
    words.sort(function (x, y) { return x.dir === y.dir ? x.num - y.num : (x.dir === "across" ? -1 : 1); });
  }

  /* ---- what the solver has done ---- */

  var state = { fill: [], wrong: [], revealed: [], elapsed: 0, done: false };
  var sel = { cell: -1, dir: "across" };
  var running = false, lastTick = 0, timerId = 0, paused = false;

  function load() {
    var saved = null;
    try { saved = JSON.parse(localStorage.getItem(STORE) || "null"); } catch (e) { saved = null; }
    var blank = cells.map(function () { return ""; });
    var ok = saved && saved.answer === SOLUTION && Array.isArray(saved.fill) && saved.fill.length === cells.length;
    state.fill = ok ? saved.fill.map(function (x) { return typeof x === "string" ? x.slice(0, 1) : ""; }) : blank;
    state.wrong = ok && Array.isArray(saved.wrong) ? saved.wrong.map(Boolean) : cells.map(function () { return false; });
    state.revealed = ok && Array.isArray(saved.revealed) ? saved.revealed.map(Boolean) : cells.map(function () { return false; });
    state.elapsed = ok && typeof saved.elapsed === "number" && saved.elapsed >= 0 ? saved.elapsed : 0;
    state.done = !!(ok && saved.done);
  }

  function save() {
    try {
      localStorage.setItem(STORE, JSON.stringify({
        answer: SOLUTION, fill: state.fill, wrong: state.wrong, revealed: state.revealed,
        elapsed: Math.round(state.elapsed), done: state.done
      }));
    } catch (e) { /* no storage: progress lasts as long as the tab */ }
  }

  /* ---- drawing ---- */

  var cellEls = [], clueEls = {};

  function drawGrid() {
    var grid = $("xwGrid");
    grid.innerHTML = "";
    cells.forEach(function (cell, i) {
      var el = document.createElement("div");
      if (!cell) {
        el.className = "xw-cell xw-block";
        el.setAttribute("aria-hidden", "true");
      } else {
        el.className = "xw-cell";
        el.setAttribute("role", "gridcell");
        el.dataset.i = i;
        el.innerHTML = (cell.num ? '<span class="xw-num">' + cell.num + "</span>" : "") + '<span class="xw-letter"></span>';
      }
      grid.appendChild(el);
      cellEls.push(el);
    });
  }

  function drawLists() {
    ["across", "down"].forEach(function (dir) {
      var ol = $(dir === "across" ? "xwAcross" : "xwDown");
      ol.innerHTML = "";
      words.filter(function (w) { return w.dir === dir; }).forEach(function (w) {
        var li = document.createElement("li");
        li.className = "xw-clue";
        li.innerHTML = '<span class="xw-clue-num">' + w.num + '</span><span class="xw-clue-text"></span>';
        li.lastChild.textContent = w.clue;
        li.addEventListener("click", function () { selectWord(w); });
        ol.appendChild(li);
        clueEls[dir + w.num] = li;
      });
    });
  }

  function current() { var c = cells[sel.cell]; return c ? c.words[sel.dir] : null; }
  function crossing() { var c = cells[sel.cell]; return c ? c.words[sel.dir === "across" ? "down" : "across"] : null; }
  function wordFull(w) { return w.cells.every(function (i) { return state.fill[i]; }); }

  function render() {
    var w = current(), x = crossing();
    var inWord = {};
    if (w) w.cells.forEach(function (i) { inWord[i] = true; });
    cells.forEach(function (cell, i) {
      if (!cell) return;
      var el = cellEls[i];
      el.querySelector(".xw-letter").textContent = state.fill[i];
      el.classList.toggle("is-word", !!inWord[i]);
      el.classList.toggle("is-sel", i === sel.cell);
      el.classList.toggle("is-wrong", !!state.wrong[i]);
      el.classList.toggle("is-revealed", !!state.revealed[i]);
      var label = (cell.words.across ? cell.words.across.num + " Across" : "") +
        (cell.words.across && cell.words.down ? ", " : "") +
        (cell.words.down ? cell.words.down.num + " Down" : "") +
        (state.fill[i] ? ": " + state.fill[i] : ": empty");
      el.setAttribute("aria-label", label);
    });
    words.forEach(function (word) {
      var li = clueEls[word.dir + word.num];
      li.classList.toggle("is-active", word === w);
      li.classList.toggle("is-cross", word === x);
      li.classList.toggle("is-done", wordFull(word));
    });
    if (w) {
      $("xwBarNum").textContent = w.num + (w.dir === "across" ? "A" : "D");
      $("xwBarText").textContent = w.clue;
    }
    $("xwGrid").classList.toggle("is-done", state.done);
  }

  function scrollClueIntoView() {
    // Only on layouts where the lists sit beside the grid; on a phone
    // the lists are far below, and jumping the page there would lose
    // the grid.
    if (!window.matchMedia("(min-width: 900px)").matches) return;
    [current(), crossing()].forEach(function (w) {
      if (!w) return;
      var li = clueEls[w.dir + w.num], box = li.parentNode;
      var top = li.offsetTop - box.offsetTop;
      if (top < box.scrollTop || top + li.offsetHeight > box.scrollTop + box.clientHeight) {
        box.scrollTo({ top: Math.max(0, top - box.clientHeight / 3), behavior: "instant" });
      }
    });
  }

  /* ---- moving around ---- */

  function select(i, dir) {
    var cell = cells[i];
    if (!cell) return;
    if (dir && cell.words[dir]) sel.dir = dir;
    else if (!cell.words[sel.dir]) sel.dir = sel.dir === "across" ? "down" : "across";
    sel.cell = i;
    render();
    scrollClueIntoView();
  }

  function firstEmpty(w) {
    for (var k = 0; k < w.cells.length; k++) if (!state.fill[w.cells[k]]) return w.cells[k];
    return w.cells[0];
  }

  function selectWord(w) { select(firstEmpty(w), w.dir); }

  function stepWord(delta) {
    var w = current();
    var k = words.indexOf(w);
    // skip over clues that are already filled, unless they all are
    for (var n = 1; n <= words.length; n++) {
      var next = words[(k + delta * n + words.length * n) % words.length];
      if (!wordFull(next) || n === words.length) { selectWord(next); return; }
    }
  }

  function afterTyping() {
    var w = current();
    var at = w.cells.indexOf(sel.cell);
    var k;
    for (k = at + 1; k < w.cells.length; k++) if (!state.fill[w.cells[k]]) return select(w.cells[k]);
    for (k = 0; k < at; k++) if (!state.fill[w.cells[k]]) return select(w.cells[k]);
    if (at < w.cells.length - 1) return select(w.cells[at + 1]);
    stepWord(1);
  }

  function move(dr, dc) {
    var dir = dr ? "down" : "across";
    if (sel.dir !== dir && cells[sel.cell].words[dir]) return select(sel.cell, dir);
    var r = cells[sel.cell].r, c = cells[sel.cell].c;
    for (;;) {
      r += dr; c += dc;
      if (r < 0 || r >= SIZE || c < 0 || c >= SIZE) return;
      if (cells[r * SIZE + c]) return select(r * SIZE + c, dir);
    }
  }

  /* ---- typing ---- */

  function type(ch) {
    if (state.done || paused || sel.cell < 0) return;
    if (state.revealed[sel.cell]) { afterTyping(); return; }
    state.fill[sel.cell] = ch;
    state.wrong[sel.cell] = false;
    startClock();
    afterTyping();
    checkFinished();
    save();
  }

  function erase() {
    if (state.done || paused || sel.cell < 0) return;
    if (state.fill[sel.cell] && !state.revealed[sel.cell]) {
      state.fill[sel.cell] = "";
      state.wrong[sel.cell] = false;
    } else {
      var w = current(), at = w.cells.indexOf(sel.cell);
      if (at > 0) {
        sel.cell = w.cells[at - 1];
        if (!state.revealed[sel.cell]) { state.fill[sel.cell] = ""; state.wrong[sel.cell] = false; }
      }
    }
    render();
    save();
  }

  function onKey(ev) {
    if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
    var t = ev.target;
    // the header's own menus and boxes keep their keys
    if (t && t.closest && t.closest("input, textarea, select, .topbar, .xw-menu")) return;
    if (sel.cell < 0) return;
    var k = ev.key;
    // a focused button or link answers its own Enter, Space and Tab
    if (t && t.closest && t.closest("button, a") && (k === "Enter" || k === " " || k === "Tab")) return;
    if (/^[a-z0-9]$/i.test(k)) { type(k.toUpperCase()); }
    else if (k === "Backspace" || k === "Delete") { erase(); }
    else if (k === "ArrowLeft") { move(0, -1); }
    else if (k === "ArrowRight") { move(0, 1); }
    else if (k === "ArrowUp") { move(-1, 0); }
    else if (k === "ArrowDown") { move(1, 0); }
    else if (k === "Tab") { stepWord(ev.shiftKey ? -1 : 1); }
    else if (k === "Enter") { stepWord(1); }
    else if (k === " ") { select(sel.cell, sel.dir === "across" ? "down" : "across"); }
    else return;
    ev.preventDefault();
  }

  /* ---- the on-screen keyboard (touch screens) ---- */

  var ROWS = { letters: ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"], digits: ["1234567890"] };
  var kbMode = "letters";

  function drawKeyboard() {
    var kb = $("xwKb");
    var rows = ROWS[kbMode].map(function (row, n) {
      var keys = row.split("").map(function (ch) {
        return '<button type="button" class="xw-key" data-key="' + ch + '">' + ch + "</button>";
      }).join("");
      if (n === ROWS[kbMode].length - 1) {
        keys = '<button type="button" class="xw-key xw-key-wide" data-key="mode">' + (kbMode === "letters" ? "123" : "ABC") + "</button>" +
          keys + '<button type="button" class="xw-key xw-key-wide" data-key="back" aria-label="Delete">' +
          '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false"><path d="M9 5h11a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H9l-6-7z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="m11 9 6 6m0-6-6 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></button>';
      }
      return '<div class="xw-kb-row">' + keys + "</div>";
    }).join("");
    kb.innerHTML = rows;
  }

  function onKbTap(ev) {
    var b = ev.target.closest(".xw-key");
    if (!b) return;
    ev.preventDefault();
    var k = b.dataset.key;
    if (k === "mode") { kbMode = kbMode === "letters" ? "digits" : "letters"; drawKeyboard(); return; }
    if (k === "back") { erase(); return; }
    type(k);
    // a digit is a one-off; go back to letters after it
    if (kbMode === "digits") { kbMode = "letters"; drawKeyboard(); }
  }

  /* ---- check, reveal, clear ---- */

  function scope(which) {
    if (which === "square") return [sel.cell];
    if (which === "word") return current().cells.slice();
    return cells.map(function (c, i) { return c ? i : -1; }).filter(function (i) { return i >= 0; });
  }

  function check(which) {
    scope(which).forEach(function (i) {
      state.wrong[i] = !!state.fill[i] && state.fill[i] !== cells[i].ans;
    });
    render(); save();
  }

  function reveal(which) {
    scope(which).forEach(function (i) {
      if (state.fill[i] !== cells[i].ans) {
        state.fill[i] = cells[i].ans;
        state.revealed[i] = true;
      }
      state.wrong[i] = false;
    });
    startClock();
    render();
    checkFinished();
    save();
  }

  function clearAll() {
    if (!window.confirm("Clear the whole puzzle and reset the clock?")) return;
    state.fill = cells.map(function () { return ""; });
    state.wrong = cells.map(function () { return false; });
    state.revealed = cells.map(function () { return false; });
    state.elapsed = 0;
    state.done = false;
    stopClock();
    showTime();
    hideNote();
    selectWord(words[0]);
    save();
  }

  function checkFinished() {
    var all = cells.every(function (c, i) { return !c || state.fill[i]; });
    if (!all) { hideNote(); return; }
    var right = cells.every(function (c, i) { return !c || state.fill[i] === c.ans; });
    if (right) {
      state.done = true;
      stopClock();
      var helped = state.revealed.some(Boolean);
      showNote("Solved in " + fmt(state.elapsed) + (helped ? ", with a little help." : ". Nicely done."), true);
      render();
    } else {
      showNote("Every square is filled, but something’s not right yet. Check can point it out.", false);
    }
  }

  function showNote(text, good) {
    var n = $("xwNote");
    n.textContent = text;
    n.classList.toggle("is-good", good);
    n.hidden = false;
  }
  function hideNote() { $("xwNote").hidden = true; }

  /* ---- the clock ---- */

  function fmt(sec) {
    sec = Math.floor(sec);
    var h = Math.floor(sec / 3600), m = Math.floor(sec / 60) % 60, s = sec % 60;
    return (h ? h + ":" + (m < 10 ? "0" : "") : "") + m + ":" + (s < 10 ? "0" : "") + s;
  }
  function showTime() { $("xwTime").textContent = fmt(state.elapsed); }

  function tick() {
    var now = Date.now();
    state.elapsed += (now - lastTick) / 1000;
    lastTick = now;
    showTime();
    if (Math.floor(state.elapsed) % 10 === 0) save();
  }
  function startClock() {
    if (running || state.done || paused || document.hidden) return;
    running = true; lastTick = Date.now();
    timerId = setInterval(tick, 1000);
  }
  function stopClock() {
    if (!running) return;
    tick();
    clearInterval(timerId);
    running = false;
  }

  function setPaused(on) {
    if (state.done) return;
    paused = on;
    $("xwPause").setAttribute("aria-pressed", String(on));
    $("xwPause").textContent = on ? "Resume" : "Pause";
    $("xwBoard").classList.toggle("is-paused", on);
    $("xwPaused").hidden = !on;
    if (on) { stopClock(); save(); } else startClock();
  }

  /* ---- menus (Check / Reveal) ---- */

  function wireMenu(btnId, menuId, act) {
    var btn = $(btnId), menu = $(menuId);
    btn.addEventListener("click", function (ev) {
      ev.stopPropagation();
      var open = menu.hidden;
      closeMenus();
      menu.hidden = !open;
      btn.setAttribute("aria-expanded", String(open));
    });
    menu.addEventListener("click", function (ev) {
      var b = ev.target.closest("button[data-scope]");
      if (!b) return;
      closeMenus();
      btn.blur();
      if (state.done || paused) return;
      act(b.dataset.scope);
    });
  }
  function closeMenus() {
    ["xwCheckMenu", "xwRevealMenu"].forEach(function (id) { $(id).hidden = true; });
    ["xwCheck", "xwReveal"].forEach(function (id) { $(id).setAttribute("aria-expanded", "false"); });
  }

  /* ---- start ---- */

  function boot() {
    buildModel();
    load();
    drawGrid();
    drawLists();
    drawKeyboard();

    $("xwGrid").addEventListener("click", function (ev) {
      var el = ev.target.closest(".xw-cell");
      if (!el || !el.dataset.i || paused) return;
      var i = +el.dataset.i;
      if (i === sel.cell) select(i, sel.dir === "across" ? "down" : "across");
      else select(i);
    });
    $("xwBarText").parentNode.addEventListener("click", function () {
      if (sel.cell >= 0) select(sel.cell, sel.dir === "across" ? "down" : "across");
    });
    $("xwPrev").addEventListener("click", function (ev) { ev.stopPropagation(); stepWord(-1); });
    $("xwNext").addEventListener("click", function (ev) { ev.stopPropagation(); stepWord(1); });
    $("xwKb").addEventListener("click", onKbTap);
    $("xwPause").addEventListener("click", function () { setPaused(!paused); });
    $("xwResume").addEventListener("click", function () { setPaused(false); });
    $("xwClear").addEventListener("click", clearAll);
    wireMenu("xwCheck", "xwCheckMenu", check);
    wireMenu("xwReveal", "xwRevealMenu", reveal);
    document.addEventListener("click", closeMenus);
    document.addEventListener("keydown", onKey);
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) { stopClock(); save(); }
      else if (!paused && state.fill.some(Boolean)) startClock();
    });
    window.addEventListener("pagehide", function () { stopClock(); save(); });

    showTime();
    // start where the puzzle starts: 1 Across, or wherever the work left off
    selectWord(words[0]);
    if (state.done) checkFinished();
    else if (state.fill.some(Boolean)) startClock();
  }

  PFML.ready.then(boot);
})();
