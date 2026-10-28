/* ==========================================================
   PFML - the round demo (/round?demo=1)

   A round's page with the newest closed round's real tracks (Round 7 when
   it was asked for, 2026-10-26) as if that round voted here with its
   voting open: the listening section (listen.js, player.js) with the
   ballot in its track list (voting.js), so it can be tried before a
   season votes here.
   It replaced the listening demo's 10 stand-in tracks the same day (the
   user's call). Without ?demo=1 in the address this does nothing.

   Everything but the round is the real page: sign-in, the header, app.js,
   listen.js, player.js and voting.js. It names a stand-in round id
   (PFMLDemo.round) for app.js to open, and once signed in, the page's
   database calls are wrapped:
   - siteRounds answers with the stand-in, a copy of the real round;
   - the reads in READS go to the database with the real round's id in
     place of the stand-in's: its tracks, the reader's own track, who's in;
   - the ballot, its draft and who has voted go to the reader's practice
     ballot (site_demo_ballots), apart from every real vote;
   - any other call naming the stand-in is answered here too.
   So no vote reaches the database, which refuses one for a round voted
   in Music League anyway. The tracks come from the database when the
   page loads, never from this file: league data never goes in this public
   repo. README, Round demo.
   ========================================================== */

(function () {
  "use strict";

  if (!/(^|[?&])demo=1(&|$)/.test(location.search)) return;

  var DEMO_ROUND = "00000000-0000-4000-8000-00000000de30";
  // read from the database for the real round
  var READS = ["roundSubmissions", "mySubmissions", "roundSubmitters"];
  // the lounge's calls go to the practice lounge of the real round, always
  var LOUNGE = ["loungeStatus", "loungeMessages", "loungePost"];
  var SAMPLE_NOTE = "Sample note, for the demo: when a submitter chooses to show their note while people vote, " +
    "it shows here with their track, without their name.";

  // the round app.js opens (initRound), as if the address said ?site=
  window.PFMLDemo = { round: DEMO_ROUND };

  // Before app.js boots: its boot waits on the same PFML.ready, and was
  // registered after this, so it runs after this.
  PFML.ready.then(function (member) {
    var real = PFML.api;
    var src = null;
    var demo = {
      // The newest closed round with its playlists built, as a round voting
      // here with two days of voting left
      siteRounds: function () {
        return real.siteRounds().then(function (rounds) {
          src = (rounds || []).filter(function (x) {
            var p = PFML.roundPhase(x);
            return (p === "closed" || p === "finished") && (x.spotify_playlist || x.youtube_playlist);
          }).sort(function (a, b) {
            return Date.parse(b.closed_at || b.closes_at) - Date.parse(a.closed_at || a.closes_at);
          })[0] || null;
          if (!src) return [];
          var round = {};
          Object.keys(src).forEach(function (k) { round[k] = src[k]; });
          round.id = DEMO_ROUND;
          round.name = "Demo: " + src.name;
          round.prompt = "A practice round with this round’s tracks: listen, then try the ballot. Nothing here counts: " +
            "your practice ballot saves to your account, apart from real votes, on every device." +
            (src.prompt ? " The prompt: " + src.prompt : "");
          round.votes_on_site = true;
          // its lounge is the practice one (lounge.js)
          round.practice = true;
          round.voting_closes_at = new Date(Date.now() + 2 * 864e5).toISOString();
          round.voting_closed_at = null;
          return [round];
        });
      },
      // The practice ballot and its draft, in the database but apart from
      // every real vote (site_demo_ballots), so they follow the reader
      // between devices as a real round's do (asked 2026-10-27, when a
      // comment made on a phone didn't show on the computer):
      // [{submission, points, comment}] in, as the real calls give them out.
      castBallot: function (id, votes) {
        if (id !== DEMO_ROUND || !src) return Promise.reject(new Error("The demo only votes on its own round."));
        return real.saveDemoBallot(src.id, votes, true).then(function () { return null; });
      },
      myBallot: function (id) {
        if (id !== DEMO_ROUND || !src) return Promise.resolve([]);
        return real.myDemoBallot(src.id).then(function (row) {
          return ((row && row.ballot) || []).map(function (v) { return { submission_id: v.submission, points: v.points, comment: v.comment }; });
        });
      },
      roundVoters: function (id) {
        if (id !== DEMO_ROUND || !src) return Promise.resolve([]);
        return real.myDemoBallot(src.id).then(function (row) {
          return row && row.ballot && row.ballot.length && member ? [member.competitorId] : [];
        });
      },
      saveBallotDraft: function (id, votes) {
        if (id !== DEMO_ROUND || !src) return Promise.reject(new Error("The demo only votes on its own round."));
        return real.saveDemoBallot(src.id, votes, false);
      },
      myBallotDraft: function (id) {
        if (id !== DEMO_ROUND || !src) return Promise.resolve(null);
        return real.myDemoBallot(src.id).then(function (row) {
          return row && row.draft_saved_at ? { ballot: row.draft, saved_at: row.draft_saved_at } : null;
        });
      }
    };
    // A round voted in Music League has no notes to show while voting, so
    // the demo puts a sample, saying so, on the round's first track, to show
    // where a submitter's note goes (asked 2026-10-27). Only on the page.
    function sampleNote(rows) {
      rows = rows || [];
      if (!rows.length || rows.some(function (s) { return s.note; })) return rows;
      var first = rows.reduce(function (a, b) { return (b.position || 1e9) < (a.position || 1e9) ? b : a; });
      return rows.map(function (s) {
        if (s !== first) return s;
        var copy = {};
        Object.keys(s).forEach(function (k) { copy[k] = s[k]; });
        copy.note = SAMPLE_NOTE;
        return copy;
      });
    }
    PFML.api = new Proxy(real, {
      get: function (target, name) {
        if (Object.prototype.hasOwnProperty.call(demo, name)) return demo[name];
        var fn = target[name];
        if (typeof fn !== "function") return fn;
        return function () {
          var args = Array.prototype.slice.call(arguments), demoCall = false;
          for (var i = 0; i < args.length; i++) {
            if (args[i] !== DEMO_ROUND) continue;
            if (LOUNGE.indexOf(name) !== -1 && src && i === 0) {
              args[0] = src.id;
              args[1] = true;
              continue;
            }
            // anything else about the stand-in round stays on this page
            if (READS.indexOf(name) === -1 || !src) return Promise.resolve([]);
            args[i] = src.id;
            demoCall = true;
          }
          var out = fn.apply(target, args);
          return demoCall && name === "roundSubmissions" ? out.then(sampleNote) : out;
        };
      }
    });
  });
})();
