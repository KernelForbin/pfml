// search-tracks: track search for the Submit page (README, Submissions on
// the site, Searching). Deployed by hand from the Supabase dashboard
// (Edge Functions, name "search-tracks"); its keys are Edge Function
// secrets, never in the site:
//   SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET  the Spotify app the playlists use
//   YOUTUBE_SEARCH_KEY                        an API key from a second Google
//                                             project, so searching can't use
//                                             up the playlist builder's
//                                             100-searches-a-day allowance
//
// POST {"service": "spotify" | "youtube", "q": "..."} as a signed-in
// member; answers {"results": [{id, title, artist, album, seconds, image}]} or
// {"error": "..."}. Members only: it asks the database is_member() with the
// caller's own sign-in, which also checks that sign-in is genuine.
//
// YouTube answers are kept in search_cache (no policies: nothing signed in
// can read it) for a week, so a repeated search costs nothing. Only the
// service, the search text and the day go in it, never who searched:
// "searched Stagger Lee" next to a name could give a submitter away.
// Plain fetch, no libraries.

const ALLOWED_ORIGINS = ["https://pfml.fun", "http://localhost:8000", "http://127.0.0.1:8000"];
const CACHE_DAYS = 7;

function cors(origin: string | null): Record<string, string> {
  return {
    "Access-Control-Allow-Origin": origin && ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0],
    "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Vary": "Origin",
  };
}

function reply(body: unknown, status: number, origin: string | null): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...cors(origin), "Content-Type": "application/json" },
  });
}

// Supabase's own keys: the new JSON dictionaries first, the legacy names after.
function projectKey(kind: "publishable" | "secret"): string {
  const dict = Deno.env.get(kind === "publishable" ? "SUPABASE_PUBLISHABLE_KEYS" : "SUPABASE_SECRET_KEYS");
  if (dict) {
    try {
      const keys = JSON.parse(dict);
      if (keys.default) return keys.default;
    } catch { /* fall through to the legacy name */ }
  }
  return Deno.env.get(kind === "publishable" ? "SUPABASE_ANON_KEY" : "SUPABASE_SERVICE_ROLE_KEY") ?? "";
}

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";

async function isMember(authorization: string | null): Promise<boolean> {
  if (!authorization || !authorization.startsWith("Bearer ")) return false;
  const res = await fetch(`${SUPABASE_URL}/rest/v1/rpc/is_member`, {
    method: "POST",
    headers: { apikey: projectKey("publishable"), Authorization: authorization, "Content-Type": "application/json" },
    body: "{}",
  });
  return res.ok && (await res.json()) === true;
}

type Result = { id: string; title: string; artist: string; album: string | null; seconds: number | null; image: string | null };

// ---- Spotify: the app's own sign-in (client credentials), no user involved

let spotifyToken = { value: "", until: 0 };

async function spotifySearch(q: string): Promise<Result[]> {
  if (Date.now() > spotifyToken.until - 60_000) {
    const basic = btoa(`${Deno.env.get("SPOTIFY_CLIENT_ID")}:${Deno.env.get("SPOTIFY_CLIENT_SECRET")}`);
    const t = await fetch("https://accounts.spotify.com/api/token", {
      method: "POST",
      headers: { Authorization: `Basic ${basic}`, "Content-Type": "application/x-www-form-urlencoded" },
      body: "grant_type=client_credentials",
    });
    if (!t.ok) throw new Error(`spotify token ${t.status}`);
    const tok = await t.json();
    spotifyToken = { value: tok.access_token, until: Date.now() + tok.expires_in * 1000 };
  }
  // Search returns at most 10 since February 2026.
  const url = `https://api.spotify.com/v1/search?type=track&limit=10&q=${encodeURIComponent(q)}`;
  const res = await fetch(url, { headers: { Authorization: `Bearer ${spotifyToken.value}` } });
  if (!res.ok) throw new Error(`spotify search ${res.status}`);
  const data = await res.json();
  return (data.tracks?.items ?? []).filter(Boolean).map((t: any) => {
    const images = t.album?.images ?? [];
    return {
      id: t.id,
      title: t.name,
      artist: (t.artists ?? []).map((a: any) => a.name).join(", "),
      album: t.album?.name ?? null,                     // for the repeat gauge's album rule
      seconds: Math.round(t.duration_ms / 1000),
      image: images.length ? images[images.length - 1].url : null,   // the smallest
    };
  });
}

// ---- YouTube: an API key from its own Google project, answers cached

function isoSeconds(iso: string): number | null {
  const m = /^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$/.exec(iso ?? "");
  if (!m) return null;
  const [d, h, mi, s] = m.slice(1).map((x) => Number(x ?? 0));
  return ((d * 24 + h) * 60 + mi) * 60 + s;
}

class QuotaError extends Error {}

async function youtubeSearch(q: string): Promise<Result[]> {
  const key = Deno.env.get("YOUTUBE_SEARCH_KEY");
  const search = await fetch("https://www.googleapis.com/youtube/v3/search?part=snippet&type=video&videoCategoryId=10" +
    `&maxResults=10&q=${encodeURIComponent(q)}&key=${key}`);
  if (search.status === 403) {
    const body = await search.text();
    if (body.includes("quota")) throw new QuotaError("youtube quota");
  }
  if (!search.ok) throw new Error(`youtube search ${search.status}`);
  const ids = ((await search.json()).items ?? []).map((i: any) => i.id?.videoId).filter(Boolean);
  if (!ids.length) return [];
  // titles and lengths from videos.list (1 unit, not the search allowance)
  const vids = await fetch("https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails" +
    `&id=${ids.join(",")}&key=${key}`);
  if (!vids.ok) throw new Error(`youtube videos ${vids.status}`);
  const byId = new Map(((await vids.json()).items ?? []).map((v: any) => [v.id, v]));
  return ids.filter((id: string) => byId.has(id)).map((id: string) => {
    const v: any = byId.get(id);
    return {
      id,
      title: v.snippet.title,
      artist: String(v.snippet.channelTitle ?? "").replace(/ - Topic$/, ""),
      album: null,
      seconds: isoSeconds(v.contentDetails?.duration),
      image: v.snippet.thumbnails?.default?.url ?? null,
    };
  });
}

function cacheHeaders(): Record<string, string> {
  // a secret key goes on apikey only (it isn't a JWT)
  return { apikey: projectKey("secret"), "Content-Type": "application/json" };
}

async function cached(service: string, query: string): Promise<Result[] | null> {
  const since = new Date(Date.now() - CACHE_DAYS * 86_400_000).toISOString().slice(0, 10);
  const res = await fetch(`${SUPABASE_URL}/rest/v1/search_cache?select=results` +
    `&service=eq.${service}&query=eq.${encodeURIComponent(query)}&cached_on=gte.${since}`, { headers: cacheHeaders() });
  if (!res.ok) return null;
  const rows = await res.json();
  return rows.length ? rows[0].results : null;
}

async function remember(service: string, query: string, results: Result[]): Promise<void> {
  await fetch(`${SUPABASE_URL}/rest/v1/search_cache?on_conflict=service,query`, {
    method: "POST",
    headers: { ...cacheHeaders(), Prefer: "resolution=merge-duplicates,return=minimal" },
    body: JSON.stringify({ service, query, results, cached_on: new Date().toISOString().slice(0, 10) }),
  });
}

// ---- the request

Deno.serve(async (req: Request) => {
  const origin = req.headers.get("Origin");
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors(origin) });
  if (req.method !== "POST") return reply({ error: "POST only" }, 405, origin);
  if (!(await isMember(req.headers.get("Authorization")))) return reply({ error: "members only" }, 401, origin);

  let body: any;
  try { body = await req.json(); } catch { return reply({ error: "bad request" }, 400, origin); }
  const service = body?.service;
  const q = String(body?.q ?? "").replace(/\s+/g, " ").trim();
  if (service !== "spotify" && service !== "youtube") return reply({ error: "service must be spotify or youtube" }, 400, origin);
  if (q.length < 1 || q.length > 120) return reply({ error: "search for 1 to 120 characters" }, 400, origin);

  try {
    if (service === "spotify") return reply({ results: await spotifySearch(q) }, 200, origin);
    const query = q.toLowerCase();
    const hit = await cached("youtube", query);
    if (hit) return reply({ results: hit }, 200, origin);
    const results = await youtubeSearch(q);
    await remember("youtube", query, results);
    return reply({ results }, 200, origin);
  } catch (e) {
    if (e instanceof QuotaError) return reply({ error: "quota" }, 200, origin);
    console.error(String(e));
    return reply({ error: "search failed" }, 502, origin);
  }
});
