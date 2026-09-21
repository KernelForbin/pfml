#!/usr/bin/env python3
"""Make one-time invite links that tie a Google account to a player.

    python scripts/invites.py                  links for every unlinked player
    python scripts/invites.py --player "Rick D"
    python scripts/invites.py --list           show who's linked, who isn't
    python scripts/invites.py --admin "Rick D" make that (linked) player an
                                               admin, who can delete any reply

A link looks like https://pfml.fun/?invite=CODE. Whoever opens it and signs
in with Google becomes that player, permanently, and the link stops working.
So send each one privately, to the right person. Re-running only makes links
for players who have no member account and no unused link yet; an unused
link for a player is reprinted, not replaced.

Needs SUPABASE_URL and SUPABASE_SECRET_KEY in .env (see scripts/supa.py).
Run scripts/publish.py first so the players table is filled in.
"""
import argparse
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import supa  # noqa: E402

SITE = "https://pfml.fun"


def fetch_state():
    players = supa.request("GET", "/rest/v1/players?select=competitor_id,name&order=name")
    members = supa.request("GET", "/rest/v1/members?select=competitor_id,role")
    invites = supa.request("GET", "/rest/v1/invites?select=code,competitor_id,claimed_by")
    return players, members, invites


def main():
    ap = argparse.ArgumentParser(description="Make PFML invite links.")
    ap.add_argument("--player", help="only this player (exact name)")
    ap.add_argument("--list", action="store_true", help="show status, create nothing")
    ap.add_argument("--admin", metavar="NAME", help="give an already-linked player the admin role")
    args = ap.parse_args()

    players, members, invites = fetch_state()
    if not players:
        raise SystemExit("No players yet. Run scripts/publish.py first.")
    by_name = {p["name"]: p["competitor_id"] for p in players}
    linked = {m["competitor_id"]: m["role"] for m in members}
    open_invite = {i["competitor_id"]: i["code"] for i in invites if not i["claimed_by"]}

    if args.admin:
        cid = by_name.get(args.admin)
        if not cid:
            raise SystemExit(f"No player named {args.admin!r}.")
        if cid not in linked:
            raise SystemExit(f"{args.admin} hasn't claimed an invite yet, so there's no account to promote.")
        supa.request("PATCH", f"/rest/v1/members?competitor_id=eq.{cid}", body={"role": "admin"},
                     headers={"Prefer": "return=minimal"})
        print(f"{args.admin} is now an admin.")
        return

    if args.list:
        for p in players:
            state = (f"linked ({linked[p['competitor_id']]})" if p["competitor_id"] in linked
                     else "invite sent, not claimed" if p["competitor_id"] in open_invite
                     else "no invite yet")
            print(f"  {p['name']:28} {state}")
        return

    targets = players
    if args.player:
        if args.player not in by_name:
            raise SystemExit(f"No player named {args.player!r}. Names are as in the export: "
                             + ", ".join(sorted(by_name)))
        targets = [p for p in players if p["name"] == args.player]

    lines = []
    for p in targets:
        cid = p["competitor_id"]
        if cid in linked:
            continue
        code = open_invite.get(cid)
        if not code:
            code = secrets.token_urlsafe(12)
            supa.request("POST", "/rest/v1/invites", body={"code": code, "competitor_id": cid},
                         headers={"Prefer": "return=minimal"})
        lines.append(f"{p['name']}: {SITE}/?invite={code}")

    if not lines:
        print("Everyone selected is already linked.")
        return
    print("Send each link privately to that person. Each works once.\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
