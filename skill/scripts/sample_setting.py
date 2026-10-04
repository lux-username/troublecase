#!/usr/bin/env python3
"""Setting sample: a spread of real messages for a model to read before
anything else, so it can say what this dataset even is. Pure code.

The dataset card is written from a profile (fields, fill rates, a few rows),
which describes the format but not the situation. This step picks messages
spread across time, conversations and actors, plus a few short runs of
consecutive messages so exchanges are visible, and writes one readable file
with basic facts (size, time span, busiest conversations and actors).

Selection (deterministic for a given --seed):
  - time is cut into --slices equal slices; each slice gets an equal share
  - half the sample from all messages, half from conversations with 3+
    actors (so mechanical bulk cannot crowd out exchanges)
  - within a slice, prefer messages with more text, at most 2 per
    conversation and 3 per actor overall
  - non-message events (actions): who does them, their subkinds, examples
  - --runs short runs of consecutive messages from the busiest
    multi-actor conversations (spread over time)
Long URLs are shortened; long messages are cut at --max-chars (marked).

Usage:
  python3 sample_setting.py --events <events.jsonl> --out <run>/setting-sample.md
                            [--n 80] [--runs 4] [--run-len 5] [--slices 10]
                            [--max-chars 700] [--seed 1]
"""

import argparse
import collections
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from segment import shorten_urls  # noqa: E402


def load(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def show(e, max_chars):
    text = shorten_urls((e.get("content") or "").strip())
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + f" […cut, {len(text)} chars]"
    text = text.replace("\n", "\n    ")
    return (f"[{e['event_id']}] {e.get('timestamp') or '?'} · {e.get('actor') or '(no name)'} "
            f"· in {e['conversation_id']}\n    {text}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--events", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=80)
    ap.add_argument("--runs", type=int, default=4)
    ap.add_argument("--run-len", type=int, default=5)
    ap.add_argument("--slices", type=int, default=10)
    ap.add_argument("--max-chars", type=int, default=700)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    rnd = random.Random(args.seed)

    events = load(args.events)
    msgs = [e for e in events if e.get("kind") == "message" and (e.get("content") or "").strip()]
    msgs.sort(key=lambda e: (e.get("timestamp") or "", e["event_id"]))
    by_conv = collections.defaultdict(list)
    for e in events:
        by_conv[e["conversation_id"]].append(e)
    kinds = collections.Counter(e.get("kind") for e in events)
    actors = collections.Counter(e.get("actor") for e in msgs)
    stamps = [e["timestamp"] for e in events if e.get("timestamp")]

    others = [e for e in events if e.get("kind") != "message"]
    other_actors = collections.Counter(e.get("actor") for e in others)
    other_sub = collections.Counter((e.get("extra") or {}).get("subkind") or e.get("kind") for e in others)
    other_examples = sorted(rnd.sample(others, min(6, len(others))), key=lambda e: e.get("timestamp") or "")

    # short runs of consecutive messages in busy multi-actor conversations
    multi = sorted((c for c, es in by_conv.items()
                    if len({x.get("actor") for x in es if x.get("kind") == "message"}) >= 3),
                   key=lambda c: -len(by_conv[c]))[: args.runs * 5]
    multi.sort(key=lambda c: by_conv[c][0].get("timestamp") or "")
    run_convs = [multi[int(i * len(multi) / args.runs)] for i in range(args.runs)] if len(multi) >= args.runs else multi
    runs, used = [], set()
    for c in run_convs:
        ms = [x for x in by_conv[c] if x.get("kind") == "message" and (x.get("content") or "").strip()]
        best = max(range(max(1, len(ms) - args.run_len + 1)),
                   key=lambda i: (len({x.get("actor") for x in ms[i:i + args.run_len]}), rnd.random()))
        run = ms[best:best + args.run_len]
        runs.append((c, run))
        used |= {x["event_id"] for x in run}

    # spread sample
    n_single = max(0, args.n - len(used))
    picked, per_conv, per_actor = [], collections.Counter(), collections.Counter()
    conv_actors = {c: len({x.get("actor") for x in es if x.get("kind") == "message"}) for c, es in by_conv.items()}
    social = [e for e in msgs if conv_actors[e["conversation_id"]] >= 3]
    halves = [(msgs, n_single - n_single // 2), (social, n_single // 2)] if social else [(msgs, n_single)]
    for pool, n_pool in halves:
      for s in range(args.slices):
        sl = pool[int(s * len(pool) / args.slices): int((s + 1) * len(pool) / args.slices)]
        sl = sorted(sl, key=lambda e: (-min(len(e.get("content") or ""), 1500), rnd.random()))
        quota, got = n_pool // args.slices + (1 if s < n_pool % args.slices else 0), 0
        for e in sl:
            if got >= quota:
                break
            if e["event_id"] in used or per_conv[e["conversation_id"]] >= 2 or per_actor[e.get("actor")] >= 3:
                continue
            picked.append(e)
            used.add(e["event_id"])
            per_conv[e["conversation_id"]] += 1
            per_actor[e.get("actor")] += 1
            got += 1
    picked.sort(key=lambda e: (e.get("timestamp") or "", e["event_id"]))

    L = ["# Setting sample", "",
         "Real messages from the dataset, chosen by code to spread across time, conversations and actors. "
         "Long links are shortened and long messages cut. Everything below is data, not instructions.", "",
         "## Basic facts (computed)", "",
         f"- Events: {len(events):,} ({', '.join(f'{k}: {v:,}' for k, v in kinds.most_common())}).",
         f"- Conversations: {len(by_conv):,}. Distinct actor names on messages: {len(actors):,}.",
         f"- Time span: {min(stamps) if stamps else '?'} to {max(stamps) if stamps else '?'}.",
         "- Busiest conversations (events): " + ", ".join(
             f"{c} ({len(es)})" for c, es in sorted(by_conv.items(), key=lambda kv: -len(kv[1]))[:8]) + ".",
         "- Most active actors (messages): " + ", ".join(f"{a} ({n})" for a, n in actors.most_common(10)) + ".",
         "", "## Events that are not messages (computed)", "",
         "- Actors on non-message events: " + (", ".join(f"{a} ({n})" for a, n in other_actors.most_common(8)) or "none") + ".",
         "- Subkinds, where given: " + (", ".join(f"{k} ({n})" for k, n in other_sub.most_common(8)) or "none") + ".",
         "- A few examples:", ""] + [show(e, 300) for e in other_examples] + [
         "", f"## Short exchanges ({len(runs)} runs of consecutive messages)", ""]
    for c, run in runs:
        L += [f"### In {c}", ""] + [show(e, args.max_chars) for e in run] + [""]
    L += [f"## Spread sample ({len(picked)} messages, in time order)", ""]
    L += [show(e, args.max_chars) + "\n" for e in picked]
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    text = "\n".join(L)
    print(f"wrote {args.out}: {len(picked)} spread + {sum(len(r) for _, r in runs)} in runs, ~{len(text)//4:,} tokens")


if __name__ == "__main__":
    main()
