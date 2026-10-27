/* ==========================================================
   PFML - the round demo (/round?demo=1)

   A round's page with the newest closed round's real tracks (Round 7 when
   it was asked for, 2026-10-26) as if that round voted here with its
   voting open: the listening section (listen.js, player.js) and, below it,
   the ballot (voting.js), so both can be tried before a season votes here.
   It replaced the listening demo's 10 stand-in tracks the same day (the
   user's call). Without ?demo=1 in the address this does nothing.

   Everything but the round is the real page: sign-in, the header, app.js,
   listen.js, player.js and voting.js. It names a stand-in round id
   (PFMLDemo.round) for app.js to open, and once signed in, the page's
   database calls are wrapped:
   - siteRounds answers with the stand-in, a copy of the real round;
   - the reads in READS go to the database with the real round's id in
     place of the stand-in's: its tracks, the reader's own track, who's in;
   - the ballot and who has voted are answered here and kept only until
     the page reloads;
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

  // the round app.js opens (initRound), as if the address said ?site=
  window.PFMLDemo = { round: DEMO_ROUND };

  // Before app.js boots: its boot waits on the same PFML.ready, and was
  // registered after this, so it runs after this.
  PFML.ready.then(function (member) {
    var real = PFML.api;
    var src = null, ballot = null;
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
          round.prompt = "A practice round with this round’s tracks: listen, then try the ballot. Nothing here is saved or counted." +
            (src.prompt ? " The prompt: " + src.prompt : "");
          round.votes_on_site = true;
          round.voting_closes_at = new Date(Date.now() + 2 * 864e5).toISOString();
          round.voting_closed_at = null;
          return [round];
        });
      },
      // the ballot, on this page only: [{submission, points, comment}] in,
      // [{submission_id, points, comment}] out, as the database has it
      castBallot: function (id, votes) {
        if (id !== DEMO_ROUND) return Promise.reject(new Error("The demo only votes on its own round."));
        ballot = votes.map(function (v) { return { submission_id: v.submission, points: v.points, comment: v.comment }; });
        return Promise.resolve(null);
      },
      myBallot: function (id) {
        return Promise.resolve(id === DEMO_ROUND && ballot ? ballot : []);
      },
      roundVoters: function (id) {
        return Promise.resolve(id === DEMO_ROUND && ballot && member ? [member.competitorId] : []);
      }
    };
    PFML.api = new Proxy(real, {
      get: function (target, name) {
        if (Object.prototype.hasOwnProperty.call(demo, name)) return demo[name];
        var fn = target[name];
        if (typeof fn !== "function") return fn;
        return function () {
          var args = Array.prototype.slice.call(arguments);
          for (var i = 0; i < args.length; i++) {
            if (args[i] !== DEMO_ROUND) continue;
            // anything else about the stand-in round stays on this page
            if (READS.indexOf(name) === -1 || !src) return Promise.resolve([]);
            args[i] = src.id;
          }
          return fn.apply(target, args);
        };
      }
    });
  });
})();
