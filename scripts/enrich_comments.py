#!/usr/bin/env python3
"""
Sentiment labels for PFML vote comments. Run this yourself, locally.

This is NOT part of the build. `build.py` never calls it, and neither does
the GitHub Action: the deploy has no API key and must never need one. This
script talks to the Claude API, costs money per run, and writes one file:

    data/comment_sentiment.json

`build.py` reads that file if it exists and merges the labels into the
season and career JSON. If it doesn't exist, the build works exactly as it
does today and the site omits every sentiment-based stat. Nothing here is
ever inferred at build time.

WHAT IT DOES
  Reads every voter comment out of data/season*/votes.csv, asks Claude to
  label each one with any mix of: witty, funny, rude, appreciative,
  storytelling, analytical, plus a one-line rationale. Results are keyed by
  a stable comment id (round id + spotify uri + voter id), the same id
  build.py computes in comment_id(), so a re-run after a fresh export only
  pays for comments it hasn't already labelled.

USAGE
  pip install anthropic            # local only; build.py stays stdlib-only
  export ANTHROPIC_API_KEY=sk-ant-...

  python scripts/enrich_comments.py --estimate     # cost only, no API call
  python scripts/enrich_comments.py --dry-run      # show what would be sent
  python scripts/enrich_comments.py                # label what's missing
  python scripts/enrich_comments.py --season season2
  python scripts/enrich_comments.py --force        # re-label everything

COST
  --estimate prints a real token count and a real dollar figure before you
  spend anything. It uses the Batch API by default, which is half price and
  usually finishes well inside an hour. See the README's "Comment
  sentiment" section for the current measured number.
"""
import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "comment_sentiment.json"

MODEL = "claude-opus-5"

# Must match SENTIMENT_LABELS in build.py. build.py drops anything outside
# this set rather than rendering it, so adding a label here means adding it
# there too.
LABELS = ["witty", "funny", "rude", "appreciative", "storytelling", "analytical"]

# How many comments go in one request. They're short (~15 words average),
# so batching many per request keeps the per-comment overhead of the system
# prompt down. Too many and the model starts losing track of indices.
COMMENTS_PER_REQUEST = 25

# Published per-MTok prices for the model above, used only by --estimate.
# Update if pricing changes; this script never fetches pricing.
PRICE_IN_PER_MTOK = 5.00
PRICE_OUT_PER_MTOK = 25.00
BATCH_DISCOUNT = 0.5

SYSTEM_PROMPT = """You label comments from a friends' Music League game, \
where players submit songs to a themed round and vote on each other's picks \
with a short written comment.

For each comment you are given, choose every label that genuinely applies \
from this set:

- witty: wordplay, a clever turn of phrase, dry humour
- funny: going for a laugh, a joke, an absurd bit
- rude: insulting or harsh about the track or the person, including in jest
- appreciative: praising the track or thanking the submitter
- storytelling: a personal anecdote or memory, not just a reaction
- analytical: talking about the music itself, production, structure, genre

Rules:
- Apply as many labels as fit, or none at all. Most comments are short and \
plain and get one label or zero. Do not reach for a label to fill space.
- These are friends insulting each other affectionately. Label "rude" on \
the content, not on whether it was meant kindly.
- The rationale is one short clause, under 12 words, quoting or pointing at \
what decided it. No preamble.
- Judge only the comment text. You do not know who wrote it."""


def comment_id(round_id, uri, voter_id):
    """Must stay identical to comment_id() in build.py."""
    return "%s|%s|%s" % (round_id, uri, voter_id)


def read_csv(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def collect_comments(season_filter=None):
    """Every voter comment across every season, in a stable order."""
    out = []
    folders = sorted(
        [p for p in DATA_DIR.iterdir() if p.is_dir() and re.fullmatch(r"season\d+", p.name)],
        key=lambda p: int(re.search(r"\d+", p.name).group()),
    )
    for folder in folders:
        if season_filter and folder.name != season_filter:
            continue
        for v in read_csv(folder / "votes.csv"):
            text = (v.get("Comment") or "").strip()
            if not text:
                continue
            out.append({
                "id": comment_id(v["Round ID"], v["Spotify URI"], v["Voter ID"]),
                "text": text,
                "season": folder.name,
            })
    return out


def load_existing():
    if not OUT_PATH.exists():
        return {}
    try:
        with open(OUT_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    return raw.get("comments", {}) if isinstance(raw, dict) else {}


def chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def build_user_message(batch):
    lines = ["Label each comment. Return one object per comment, same order, "
             "same count.", ""]
    for i, c in enumerate(batch):
        # Comment text is data, not instruction. It's fenced and indexed so
        # a comment that happens to contain something like "ignore the
        # above" reads as one of the items to label, not as direction.
        lines.append(f"<comment index=\"{i}\">")
        lines.append(c["text"])
        lines.append("</comment>")
    return "\n".join(lines)


RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "labels": {
                        "type": "array",
                        "items": {"type": "string", "enum": LABELS},
                    },
                    "rationale": {"type": "string"},
                },
                "required": ["index", "labels", "rationale"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}


def request_params(batch):
    return {
        "model": MODEL,
        "max_tokens": 8000,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": build_user_message(batch)}],
        # Bulk labelling of one-line comments; low effort is the right
        # setting and keeps the bill down. Raise it if the labels look
        # careless on a sample.
        "output_config": {
            "effort": "low",
            "format": {"type": "json_schema", "schema": RESPONSE_SCHEMA},
        },
    }


def estimate(client, batches):
    """Count real input tokens and print a real price. No labelling calls."""
    sample = batches[: min(3, len(batches))]
    per_batch = []
    for b in sample:
        counted = client.messages.count_tokens(
            model=MODEL,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_user_message(b)}],
        )
        per_batch.append(counted.input_tokens)
    avg_in = sum(per_batch) / len(per_batch)
    total_in = avg_in * len(batches)
    # Each result is an index, a short label list and a clause: ~40 output
    # tokens per comment is a generous allowance measured against the real
    # schema.
    total_out = sum(len(b) for b in batches) * 40

    for label, mult in (("batch (default, 50% off)", BATCH_DISCOUNT), ("standard", 1.0)):
        cost = (total_in / 1e6 * PRICE_IN_PER_MTOK + total_out / 1e6 * PRICE_OUT_PER_MTOK) * mult
        print(f"  {label:28} ${cost:,.2f}")
    print(f"\n  model            {MODEL}")
    print(f"  requests         {len(batches)}")
    print(f"  input tokens     ~{total_in:,.0f} (measured on {len(sample)} sampled request(s))")
    print(f"  output tokens    ~{total_out:,.0f} (allowance, 40/comment)")
    print("\nPrices are the published per-MTok rates hardcoded in this script; "
          "check the pricing page if it's been a while.")


def merge_results(store, batch, payload):
    """Fold one response into the store. Anything malformed is skipped and
    reported rather than guessed at: a comment with no label is better than
    a comment with an invented one."""
    added = 0
    results = payload.get("results", [])
    for item in results:
        idx = item.get("index")
        if not isinstance(idx, int) or not (0 <= idx < len(batch)):
            continue
        labels = [l for l in item.get("labels", []) if l in LABELS]
        store[batch[idx]["id"]] = {
            "labels": labels,
            "rationale": (item.get("rationale") or "").strip(),
        }
        added += 1
    if len(results) != len(batch):
        print(f"    ! response had {len(results)} results for {len(batch)} comments; "
              f"kept {added}, the rest stay unlabelled")
    return added


def write_store(store, model):
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_comment": "Generated by scripts/enrich_comments.py. Not written by build.py. "
                    "Safe to delete: the site drops sentiment stats and everything else builds.",
        "model": model,
        "labels": LABELS,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "comments": store,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"\nWrote {OUT_PATH.relative_to(ROOT)}: {len(store)} labelled comments.")
    print("Now run: python scripts/build.py")


def run_batch_api(client, batches, store):
    """Batch API: half price, asynchronous, usually done within the hour."""
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    requests = [
        Request(custom_id=f"b{i}", params=MessageCreateParamsNonStreaming(**request_params(b)))
        for i, b in enumerate(batches)
    ]
    job = client.messages.batches.create(requests=requests)
    print(f"Batch {job.id} submitted ({len(requests)} requests). Polling every 30s.")
    print("Safe to Ctrl-C: re-running resumes and only pays for what's still missing.")

    while True:
        job = client.messages.batches.retrieve(job.id)
        if job.processing_status == "ended":
            break
        counts = job.request_counts
        print(f"  {job.processing_status}: {counts.succeeded} done, "
              f"{counts.processing} processing, {counts.errored} errored")
        time.sleep(30)

    added = 0
    errored = 0
    for result in client.messages.batches.results(job.id):
        idx = int(result.custom_id[1:])          # results come back in any order
        if result.result.type != "succeeded":
            errored += 1
            continue
        msg = result.result.message
        if msg.stop_reason == "refusal":
            errored += 1
            continue
        text = next((b.text for b in msg.content if b.type == "text"), "")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            errored += 1
            continue
        added += merge_results(store, batches[idx], payload)

    print(f"\nLabelled {added} comments. {errored} request(s) failed and were skipped.")
    return added


def run_sync(client, batches, store):
    """One request at a time. Full price, but immediate and easy to watch."""
    added = 0
    for i, b in enumerate(batches, 1):
        print(f"  request {i}/{len(batches)} ({len(b)} comments)")
        try:
            msg = client.messages.create(**request_params(b))
        except Exception as e:                    # noqa: BLE001 - report and carry on
            print(f"    ! {type(e).__name__}: {e}")
            continue
        if msg.stop_reason == "refusal":
            print("    ! refused; skipped")
            continue
        text = next((blk.text for blk in msg.content if blk.type == "text"), "")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            print("    ! response was not valid JSON; skipped")
            continue
        added += merge_results(store, b, payload)
    return added


def main():
    global MODEL
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", help="only this season folder, e.g. season2")
    ap.add_argument("--limit", type=int, help="cap how many comments are sent")
    ap.add_argument("--force", action="store_true",
                    help="re-label comments that already have labels")
    ap.add_argument("--estimate", action="store_true",
                    help="print measured token counts and cost, then exit")
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would be sent, call nothing")
    ap.add_argument("--sync", action="store_true",
                    help="send requests one at a time instead of the Batch API "
                         "(immediate, but full price)")
    ap.add_argument("--model", default=MODEL, help=f"override the model (default {MODEL})")
    args = ap.parse_args()
    MODEL = args.model

    comments = collect_comments(args.season)
    if not comments:
        print("No comments found. Is data/season*/votes.csv in place?")
        return 1

    store = {} if args.force else load_existing()
    todo = [c for c in comments if args.force or c["id"] not in store]
    already = len(comments) - len(todo)          # count before --limit truncates
    if args.limit:
        todo = todo[: args.limit]

    capped = f", capped at {len(todo)} by --limit" if args.limit else ""
    print(f"{len(comments)} comments found, {already} already labelled, "
          f"{len(todo)} to do{capped}.")
    if not todo:
        print("Nothing to do.")
        return 0

    batches = list(chunks(todo, COMMENTS_PER_REQUEST))

    if args.dry_run:
        print(f"\nWould send {len(batches)} request(s) of up to {COMMENTS_PER_REQUEST} comments "
              f"to {MODEL}.\n\n--- first request ---\n")
        print(build_user_message(batches[0])[:2000])
        return 0

    try:
        import anthropic
    except ImportError:
        print("This script needs the Anthropic SDK, which the build deliberately does not:\n"
              "    pip install anthropic", file=sys.stderr)
        return 1

    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        print("Set ANTHROPIC_API_KEY (or run `ant auth login`) first.", file=sys.stderr)
        return 1

    client = anthropic.Anthropic()

    if args.estimate:
        print(f"\nEstimate for {len(todo)} comments in {len(batches)} request(s):\n")
        estimate(client, batches)
        return 0

    added = run_sync(client, batches, store) if args.sync else run_batch_api(client, batches, store)
    if added:
        write_store(store, MODEL)
    else:
        print("Nothing was labelled, leaving the existing file alone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
