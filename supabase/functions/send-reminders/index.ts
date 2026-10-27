// @ts-nocheck
// send-reminders: app notifications now, email later (README, Reminders).
// Deployed by hand from the Supabase dashboard (Edge Functions, name
// "send-reminders") with "Enforce JWT verification" OFF: it checks every
// caller itself, in the three ways below, and refuses anything else with 401. Its keys are Edge Function secrets,
// never in the site:
//   REMINDERS_SECRET   shared with the five-minute timer (Vault, reminders_secret)
//   VAPID_PRIVATE_JWK  the push signing key: a P-256 JWK (x, y, d); its public
//                      half is vapidPublicKey in site/config.js
//   RESEND_API_KEY     email, for later: without it no email is sent at all,
//   REMINDERS_FROM     and the sender asks the database for push only
//
// POST with x-reminders-secret, from the timer (supabase/setup/reminders_cron.sql):
//   claims whatever is due (reminders_claim, which records it first, so two
//   runs can't send the same reminder) and sends it. A device the push
//   service says is gone is forgotten.
// POST {"test": true} as a signed-in member: one test notification to the
//   caller's own devices, found with the caller's own sign-in.
// GET ?unsubscribe=<token>: email's unsubscribe link (later); the token is
//   the member's id signed with REMINDERS_SECRET.
// Plain fetch and WebCrypto, no libraries, and one file to paste into the
// dashboard. The push block below is plain JavaScript inside TypeScript,
// so type checking is off for this file (it changes nothing at run time).

// ---- webpush: begin ----
// Web Push, with nothing but
// WebCrypto: the message encryption of RFC 8291 (aes128gcm, RFC 8188) and
// the VAPID signature of RFC 8292. No libraries, like search-tracks, and
// plain JavaScript (no types), so this block runs in a browser too: that's
// how it was checked against RFC 8291's worked example (Section 5,
// Appendix A), byte for byte (tests/test_reminders.py says how).

const enc = new TextEncoder();

export function b64url(bytes) {
  let s = "";
  for (const b of new Uint8Array(bytes)) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function unb64url(text) {
  const s = atob(String(text).replace(/\s+/g, "").replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(s, (c) => c.charCodeAt(0));
}

function concat(...parts) {
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let at = 0;
  for (const p of parts) { out.set(p, at); at += p.length; }
  return out;
}

async function hkdf(salt, ikm, info, length) {
  const key = await crypto.subtle.importKey("raw", ikm, "HKDF", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits({ name: "HKDF", hash: "SHA-256", salt, info }, key, length * 8);
  return new Uint8Array(bits);
}

// A P-256 key from its uncompressed public point (65 bytes) and, for a
// private key, its 32-byte secret: the JWK form WebCrypto takes.
function jwkFor(publicRaw, privateRaw) {
  const jwk = { kty: "EC", crv: "P-256", x: b64url(publicRaw.slice(1, 33)), y: b64url(publicRaw.slice(33, 65)), ext: true };
  if (privateRaw) jwk.d = b64url(privateRaw);
  return jwk;
}

// RFC 8291: the body for one push message to one subscription (its p256dh
// and auth, base64url). `fixed` ({salt, senderPublic, senderPrivate}) is
// only for checking against the RFC's example; normally both are fresh.
export async function encrypt(plaintext, p256dh, auth, fixed) {
  const uaPublic = unb64url(p256dh);
  const authSecret = unb64url(auth);
  if (uaPublic.length !== 65 || uaPublic[0] !== 4 || authSecret.length !== 16) throw new Error("bad subscription keys");
  const salt = fixed ? unb64url(fixed.salt) : crypto.getRandomValues(new Uint8Array(16));
  let asPrivate, asPublic;
  if (fixed) {
    asPublic = unb64url(fixed.senderPublic);
    asPrivate = await crypto.subtle.importKey("jwk", jwkFor(asPublic, unb64url(fixed.senderPrivate)),
      { name: "ECDH", namedCurve: "P-256" }, false, ["deriveBits"]);
  } else {
    const pair = await crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, true, ["deriveBits"]);
    asPrivate = pair.privateKey;
    asPublic = new Uint8Array(await crypto.subtle.exportKey("raw", pair.publicKey));
  }
  const uaKey = await crypto.subtle.importKey("raw", uaPublic, { name: "ECDH", namedCurve: "P-256" }, false, []);
  const ecdhSecret = new Uint8Array(await crypto.subtle.deriveBits({ name: "ECDH", public: uaKey }, asPrivate, 256));
  const keyInfo = concat(enc.encode("WebPush: info\0"), uaPublic, asPublic);
  const ikm = await hkdf(authSecret, ecdhSecret, keyInfo, 32);
  const cek = await hkdf(salt, ikm, enc.encode("Content-Encoding: aes128gcm\0"), 16);
  const nonce = await hkdf(salt, ikm, enc.encode("Content-Encoding: nonce\0"), 12);
  // one record: the message and the last-record delimiter (0x02)
  const padded = concat(typeof plaintext === "string" ? enc.encode(plaintext) : plaintext, new Uint8Array([2]));
  const aes = await crypto.subtle.importKey("raw", cek, "AES-GCM", false, ["encrypt"]);
  const sealed = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, aes, padded));
  // header: salt, record size 4096, and the sender's public key
  const header = concat(salt, new Uint8Array([0, 0, 16, 0, 65]), asPublic);
  return concat(header, sealed);
}

// RFC 8292: "vapid t=<signed JWT>, k=<public key>" for the push service at
// the endpoint's origin. vapidJwk is the P-256 private key as a JWK (x, y, d).
export async function vapidHeader(endpoint, vapidJwk, subject) {
  const now = Math.floor(Date.now() / 1000);
  const head = b64url(enc.encode(JSON.stringify({ typ: "JWT", alg: "ES256" })));
  const claims = b64url(enc.encode(JSON.stringify({ aud: new URL(endpoint).origin, exp: now + 12 * 3600, sub: subject })));
  const key = await crypto.subtle.importKey("jwk", vapidJwk, { name: "ECDSA", namedCurve: "P-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, key, enc.encode(`${head}.${claims}`));
  const publicRaw = concat(new Uint8Array([4]), unb64url(vapidJwk.x), unb64url(vapidJwk.y));
  return `vapid t=${head}.${claims}.${b64url(sig)}, k=${b64url(publicRaw)}`;
}

// Sends one message; resolves to the push service's HTTP status. 404 and
// 410 mean the subscription is gone and should be forgotten.
export async function sendPush(subscription, message, vapidJwk, subject) {
  const body = await encrypt(JSON.stringify(message), subscription.p256dh, subscription.auth);
  const res = await fetch(subscription.endpoint, {
    method: "POST",
    headers: {
      "Content-Encoding": "aes128gcm",
      "Content-Type": "application/octet-stream",
      "TTL": String(24 * 3600),
      "Urgency": "normal",
      "Authorization": await vapidHeader(subscription.endpoint, vapidJwk, subject),
    },
    body,
  });
  return res.status;
}
// ---- webpush: end ----

const SITE = "https://pfml.fun/";
const SUBJECT = "https://pfml.fun";

// Supabase's own keys: the new JSON dictionaries first, the legacy names after
// (the same as search-tracks).
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

async function rpc(name: string, body: unknown, authorization?: string): Promise<Response> {
  // a secret key goes on apikey only (it isn't a JWT); a member's call
  // carries their own sign-in instead
  const headers: Record<string, string> = authorization
    ? { apikey: projectKey("publishable"), Authorization: authorization, "Content-Type": "application/json" }
    : { apikey: projectKey("secret"), "Content-Type": "application/json" };
  return await fetch(`${SUPABASE_URL}/rest/v1/rpc/${name}`, { method: "POST", headers, body: JSON.stringify(body) });
}

// constant-time, so the secret can't be guessed a character at a time
function same(a: string, b: string): boolean {
  if (!a || !b || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function vapidKey(): JsonWebKey | null {
  try {
    const jwk = JSON.parse(Deno.env.get("VAPID_PRIVATE_JWK") ?? "");
    return jwk && jwk.d && jwk.x && jwk.y ? jwk : null;
  } catch {
    return null;
  }
}

// "in 3 days", "in 5 hours": the server doesn't know the reader's time zone
function left(iso: string): string {
  const mins = Math.round((Date.parse(iso) - Date.now()) / 60000);
  if (mins < 90) return `in ${Math.max(mins, 1)} min`;
  const hours = Math.round(mins / 60);
  return hours < 36 ? `in ${hours} hours` : `in ${Math.round(hours / 24)} days`;
}

type Claim = { round_id: string; kind: string; user_id: string; channel: string; round_name: string;
               closes_at: string; email: string | null; subscriptions: Sub[] | null };
type Sub = { endpoint: string; p256dh: string; auth: string };

// What each reminder says. The voting ones only ever go to players who
// haven't voted (reminders_claim). A new round opens the Submit page; the
// rest open the round's own page, where it plays and votes (2026-10-26).
export function message(c: Claim): { title: string; body: string; url: string; tag: string } {
  const page = c.kind === "round_open" ? `${SITE}submit` : `${SITE}round?site=${encodeURIComponent(c.round_id)}`;
  const at = { url: page, tag: `${c.round_id}:${c.kind}` };
  switch (c.kind) {
    case "round_open":
      return { ...at, title: `${c.round_name} is open`, body: `Submit your track. Submissions close ${left(c.closes_at)}.` };
    case "playlist_ready":
      return { ...at, title: `${c.round_name}: the playlist is ready`, body: "Every track, in one shuffled order." };
    case "vote_halfway":
      return { ...at, title: `Halfway through voting: ${c.round_name}`, body: `You haven't voted yet. Voting closes ${left(c.closes_at)}.` };
    default:
      return { ...at, title: `Voting closes ${left(c.closes_at)}`, body: `You haven't voted in ${c.round_name} yet.` };
  }
}

// New replies and reactions on a member's own comments, summed up by
// inbox_claim. One notification per run, never one per reaction. Escapes,
// not the characters, so the file stays plain ASCII through any clipboard.
type Inbox = { user_id: string; replies: number; reactions: number; last_kind: string; last_actor: string;
               last_text: string; subscriptions: Sub[] };
const GLYPHS: Record<string, string> = { fire: "\u{1F525}", laugh: "\u{1F602}", hundred: "\u{1F4AF}", eyes: "\u{1F440}",
                                         grimace: "\u{1F62C}", heart: "\u2764\uFE0F" };

export function inboxMessage(n: Inbox): { title: string; body: string; url: string; tag: string } {
  const at = { url: `${SITE}?inbox=1`, tag: "inbox" };
  if (n.replies + n.reactions === 1 && n.last_kind === "reply") {
    return { ...at, title: `${n.last_actor} replied to your comment`, body: `\u201C${n.last_text}\u201D` };
  }
  if (n.replies + n.reactions === 1) {
    return { ...at, title: `${n.last_actor} reacted ${GLYPHS[n.last_text] ?? n.last_text} to your comment`, body: "Open your inbox to see it." };
  }
  const parts = [n.replies ? `${n.replies} ${n.replies === 1 ? "reply" : "replies"}` : "",
                 n.reactions ? `${n.reactions} ${n.reactions === 1 ? "reaction" : "reactions"}` : ""].filter(Boolean);
  return { ...at, title: "New on your comments", body: `${parts.join(" and ")}. The latest from ${n.last_actor}.` };
}

// A commissioner's announcement (announcements_claim), to every member who
// has a device and wants them: who posted it, and the message.
type Announcement = { announcement_id: string; body: string; author: string; user_id: string; subscriptions: Sub[] };

export function announcementMessage(a: Announcement): { title: string; body: string; url: string; tag: string } {
  return { title: `From ${a.author}`, body: a.body.length > 180 ? a.body.slice(0, 179) + "\u2026" : a.body,
           url: SITE, tag: `announce:${a.announcement_id}` };
}

async function pushTo(subs: Sub[], msg: unknown, jwk: JsonWebKey): Promise<number> {
  let sent = 0;
  for (const s of subs) {
    try {
      const status = await sendPush(s, msg, jwk, SUBJECT);
      if (status === 404 || status === 410) await rpc("forget_push_endpoint", { p_endpoint: s.endpoint });
      else if (status >= 200 && status < 300) sent++;
      else console.error(`push service answered ${status}`);
    } catch (err) {
      console.error(`push failed: ${err}`);
    }
  }
  return sent;
}

async function signed(userId: string): Promise<string> {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(Deno.env.get("REMINDERS_SECRET") ?? ""),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(userId)));
  return btoa(String.fromCharCode(...sig)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function sendEmail(c: Claim, msg: { title: string; body: string; url: string }): Promise<boolean> {
  const unsubscribe = `${SUPABASE_URL}/functions/v1/send-reminders?unsubscribe=${c.user_id}.${await signed(c.user_id)}`;
  const esc = (s: string) => s.replace(/[&<>"']/g, (ch) => `&#${ch.charCodeAt(0)};`);
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${Deno.env.get("RESEND_API_KEY")}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      from: Deno.env.get("REMINDERS_FROM"),
      to: [c.email],
      subject: msg.title,
      text: `${msg.body}\n\n${msg.url}\n\nStop these emails: ${unsubscribe}`,
      html: `<p>${esc(msg.body)}</p><p><a href="${esc(msg.url)}">Open PFML</a></p>` +
        `<p style="color:#6A6172;font-size:13px"><a href="${esc(unsubscribe)}">Stop these emails</a></p>`,
      headers: { "List-Unsubscribe": `<${unsubscribe}>` },
    }),
  });
  return res.ok;
}

async function runDue(): Promise<Response> {
  const jwk = vapidKey();
  const channels = [...(jwk ? ["push"] : []), ...(Deno.env.get("RESEND_API_KEY") && Deno.env.get("REMINDERS_FROM") ? ["email"] : [])];
  if (!channels.length) return Response.json({ sent: 0, note: "no channel set up" });
  const res = await rpc("reminders_claim", { p_channels: channels });
  if (!res.ok) return Response.json({ error: `claim failed: ${res.status}` }, { status: 500 });
  const claims: Claim[] = await res.json();
  let sent = 0;
  for (const c of claims) {
    const msg = message(c);
    if (c.channel === "push" && jwk) sent += await pushTo(c.subscriptions ?? [], msg, jwk);
    else if (c.channel === "email" && c.email && (await sendEmail(c, msg))) sent++;
  }
  // replies and reactions on members' comments: push only
  let inbox = 0;
  if (jwk) {
    const res = await rpc("inbox_claim", {});
    if (!res.ok) console.error(`inbox claim failed: ${res.status}`);
    else for (const n of (await res.json()) as Inbox[]) inbox += await pushTo(n.subscriptions ?? [], inboxMessage(n), jwk);
  }
  // announcements from the commissioners: push only
  let announced = 0;
  if (jwk) {
    const res = await rpc("announcements_claim", {});
    if (!res.ok) console.error(`announcements claim failed: ${res.status}`);
    else for (const a of (await res.json()) as Announcement[]) announced += await pushTo(a.subscriptions ?? [], announcementMessage(a), jwk);
  }
  return Response.json({ claimed: claims.length, sent, inbox, announced });
}

async function test(authorization: string): Promise<Response> {
  const jwk = vapidKey();
  if (!jwk) return Response.json({ error: "notifications aren't set up yet" }, { status: 503 });
  const res = await rpc("my_push_subscriptions", {}, authorization);
  if (!res.ok) return Response.json({ error: "members only" }, { status: 401 });
  const subs: Sub[] = await res.json();
  if (!subs.length) return Response.json({ error: "notifications aren't on for any of your devices" }, { status: 404 });
  const sent = await pushTo(subs, { title: "PFML notifications are on", body: "This is what a reminder will look like.", url: SITE, tag: "test" }, jwk);
  return Response.json({ sent });
}

async function unsubscribe(token: string): Promise<Response> {
  const [userId, sig] = token.split(".");
  const page = (text: string, status = 200) => new Response(
    `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>PFML</title>` +
    `<p style="font:16px system-ui;padding:24px">${text}</p>`, { status, headers: { "Content-Type": "text/html; charset=utf-8" } });
  // no secret, no link can be right (and signing with an empty key throws:
  // a 500 here before 2026-10-25's fix)
  if (!Deno.env.get("REMINDERS_SECRET")) return page("That link isn't right.", 401);
  if (!userId || !sig || !same(sig, await signed(userId))) return page("That link isn't right.", 401);
  await rpc("email_reminders_off", { p_user: userId });
  return page("Done: no more reminder emails. Turn them back on from the menu under your initials on pfml.fun.");
}

const CORS = {
  "Access-Control-Allow-Origin": "https://pfml.fun",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });
  const url = new URL(req.url);
  if (req.method === "GET" && url.searchParams.get("unsubscribe")) return await unsubscribe(url.searchParams.get("unsubscribe") ?? "");
  if (req.method !== "POST") return new Response(null, { status: 405 });
  if (same(req.headers.get("x-reminders-secret") ?? "", Deno.env.get("REMINDERS_SECRET") ?? "")) return await runDue();
  const authorization = req.headers.get("Authorization");
  let body: { test?: boolean } = {};
  try { body = await req.json(); } catch { /* not JSON: refused below */ }
  if (body.test === true && authorization && authorization.startsWith("Bearer ")) {
    const res = await test(authorization);
    for (const [k, v] of Object.entries(CORS)) res.headers.set(k, v);
    return res;
  }
  return new Response(JSON.stringify({ error: "not allowed" }), { status: 401, headers: { ...CORS, "Content-Type": "application/json" } });
});
