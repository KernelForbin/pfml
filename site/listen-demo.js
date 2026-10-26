/* ==========================================================
   PFML - the listening demo (/round?demo=1)

   A round's page with a stand-in round of 10 tracks, so its listening
   section (listen.js, player.js) can be tried anywhere, a phone with its
   screen locked included, without a real round to play. Asked for
   2026-10-26, first on the Submit page, then moved with listening to the
   round page. Without ?demo=1 in the address this does nothing.

   Everything but the round is the real page: sign-in, the header, app.js,
   listen.js and player.js. It names its round (PFMLDemo.round) for app.js
   to open, and once signed in, the page's database calls are wrapped: the
   ones that read rounds and their tracks answer with the stand-in, and any
   call naming the stand-in round is answered here, so nothing about it
   reaches the database and nothing is saved.

   The tracks were picked at random from Spotify on 2026-10-26, none of them
   a league submission (league data never goes in this public repo): 5 sent
   from Spotify, 5 from YouTube, each under 5 minutes. The rows are what
   round_playlists.py makes of a real round: its own matcher found each
   track's copy on the other service, the round's one shuffle gave the
   positions, and the stand-in has a real, public YouTube playlist of all 10
   in that order, made on the user's account at their request. The length
   beside each is the submitted track's. README, Listening demo.
   ========================================================== */

(function () {
  "use strict";

  if (!/(^|[?&])demo=1(&|$)/.test(location.search)) return;

  var DEMO_ROUND = "00000000-0000-4000-8000-00000000de30";
  var TRACKS = [
    { platform: "spotify", track: "43OjswTQMkuvQQEP38Roxl", title: "Bandelero", artist: "Slightly Stoopid", position: 9, spotify_match: "43OjswTQMkuvQQEP38Roxl", youtube_match: "VEgDAY_Bhj0" },   // 2:47
    { platform: "spotify", track: "3I7esPjuU7uhQzIpLeYXlc", title: "10 Meter geh’", artist: "Wolfgang Preiml", position: 3, spotify_match: "3I7esPjuU7uhQzIpLeYXlc", youtube_match: "aWW-Nf9CpeQ" },   // 3:17
    { platform: "spotify", track: "5dvRv1XYMNvuX2xuu6CNIF", title: "Hurricane (Johnnie's Theme)", artist: "Lord Huron", position: 10, spotify_match: "5dvRv1XYMNvuX2xuu6CNIF", youtube_match: "kGiPa0bGKRM" },   // 2:46
    { platform: "spotify", track: "1F9kEuwT29fgqlovIclu81", title: "love race (feat. Kellin Quinn)", artist: "mgk, Kellin Quinn", position: 5, spotify_match: "1F9kEuwT29fgqlovIclu81", youtube_match: "tAztwrYHCWE" },   // 3:09
    { platform: "spotify", track: "3lqaXaor2lhGbC9T8B7XNV", title: "You're So Good For Me", artist: "Humble Pie", position: 1, spotify_match: "3lqaXaor2lhGbC9T8B7XNV", youtube_match: "AkG1yusgc50" },   // 3:51
    { platform: "youtube", track: "csARzcsjark", title: "Speechless (Audio)", artist: "Michael Jackson", position: 8, spotify_match: "1O1LkHTi3Lep9OHE8BvOVe", youtube_match: "csARzcsjark" },   // 3:20
    { platform: "youtube", track: "5Y_OP7KmEL8", title: "Big Train", artist: "Tucka", position: 2, spotify_match: "4L4N497WPHrOsq2Z3kXtn7", youtube_match: "5Y_OP7KmEL8" },   // 4:42
    { platform: "youtube", track: "7qxWhkY1Z4Y", title: "Different People", artist: "No Doubt", position: 6, spotify_match: "6PM8yaNDDfXc0kHIMSuIKR", youtube_match: "7qxWhkY1Z4Y" },   // 4:36
    { platform: "youtube", track: "HRqOcPBLR7g", title: "Those Memories of You (Official Music Video)", artist: "Linda Ronstadt, Dolly Parton, Emmylou Harris", position: 7, spotify_match: "7sdNvO1i0MeKRseYnuebGN", youtube_match: "HRqOcPBLR7g" },   // 4:21
    { platform: "youtube", track: "0z8J0Rt_TD8", title: "Lola Lola", artist: "Hella Chluy", position: 4, spotify_match: "57mYlab6SEwPqq4Oc6RFb5", youtube_match: "0z8J0Rt_TD8" }   // 3:25
  ];

  // the round app.js opens (initRound), as if the address said ?site=
  window.PFMLDemo = { round: DEMO_ROUND };

  // Before app.js boots: its boot waits on the same PFML.ready, and was
  // registered after this, so it runs after this.
  PFML.ready.then(function () {
    var real = PFML.api;
    var now = Date.now(), day = 864e5;
    var round = {
      id: DEMO_ROUND, season_key: "season3", name: "Listening demo",
      prompt: "A stand-in round for trying the player: 5 tracks sent from Spotify, 5 from YouTube. " +
        "Its YouTube playlist is real and public, for listening off the site. Nothing here is saved.",
      opens_at: null, closes_at: new Date(now - day).toISOString(), closed_at: null, created_at: new Date(now - 3 * day).toISOString(),
      votes_on_site: false, songs_per_round: 1, services: ["spotify", "youtube", "soundcloud"], repeat_rule: "warn",
      spotify_playlist: null, youtube_playlist: "PLft5RplZTPho"
    };
    var demo = {
      siteRounds: function () { return Promise.resolve([round]); },
      roundSubmissions: function (id) {
        if (id !== DEMO_ROUND) return real.roundSubmissions(id);
        return Promise.resolve(TRACKS.map(function (t, i) {
          var row = { id: "00000000-0000-4000-8000-0000000000" + (10 + i), tag: "AB"[Math.floor(i / 5)] + (i % 5 + 1), note: "" };
          Object.keys(t).forEach(function (k) { row[k] = t[k]; });
          return row;
        }));
      }
    };
    PFML.api = new Proxy(real, {
      get: function (target, name) {
        if (Object.prototype.hasOwnProperty.call(demo, name)) return demo[name];
        var fn = target[name];
        if (typeof fn !== "function") return fn;
        return function () {
          // anything about the stand-in round stays on this page
          for (var i = 0; i < arguments.length; i++) if (arguments[i] === DEMO_ROUND) return Promise.resolve([]);
          return fn.apply(target, arguments);
        };
      }
    });
  });
})();
