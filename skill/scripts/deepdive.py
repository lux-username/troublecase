#!/usr/bin/env python3
"""Deep dive: gather the full picture for a few chosen cases. Pure code; the
reconstruction is done by a model following codebook/deepdive-instructions.md.

Describe works from capped excerpts. Before the briefing tells a case in full,
this step goes back over ALL the data for it and builds one timeline across
conversations:

  - the whole conversation the case is in (every part, not just one unit)
  - every conversation it names, and every conversation that names it
  - every event, anywhere, that contains one of the case's rare terms
    (distinctive tokens shared with only a few conversations)
  - every message by the case's agents (posting accounts and claimed names)
    within --window-hours of the case, in any conversation
  - the other members of its trouble group, if any

Sources are added in that order of priority until --max-tokens is reached; the
report says what was left out. Everything is merged into one timeline,
sorted by time, each event labelled with its conversation and why it was
included.

Usage:
  python3 deepdive.py --segment <run> --events <events.jsonl> --out <run>
                      --unit UNIT_ID [--unit UNIT_ID ...]
                      [--window-hours 72] [--max-tokens 90000] [--alias-field extra.<field>]
"""

import argparse
import collections
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from segment import render_event, TERM_RE  # noqa: E402
from context import setting_block  # noqa: E402


def load_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return None


def get_path(e, field):
    v = e
    for p in field.split("."):
        if not isinstance(v, dict):
            return None
        v = v.get(p)
    return v


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--segment", required=True)
    ap.add_argument("--events", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--unit", action="append", required=True)
    ap.add_argument("--window-hours", type=float, default=72)
    ap.add_argument("--max-tokens", type=int, default=90000)
    ap.add_argument("--alias-field")
    ap.add_argument("--setting", help="approved setting.md: its summary and vocabulary go at the top of every batch as background")
    args = ap.parse_args()

    events = load_jsonl(args.events)
    by_id = {e["event_id"]: e for e in events}
    by_conv = collections.defaultdict(list)
    for e in events:
        by_conv[e["conversation_id"]].append(e)
    units = {u["unit_id"]: u for u in load_jsonl(os.path.join(args.segment, "units.jsonl"))}
    with open(os.path.join(args.segment, "index.json"), encoding="utf-8") as fh:
        index = json.load(fh)
    os.makedirs(os.path.join(args.out, "inputs"), exist_ok=True)
    os.makedirs(os.path.join(args.out, "dossiers"), exist_ok=True)
    report = ["# Deep-dive gathering", ""]

    for uid in args.unit:
        u = units[uid]
        cid = u["conversation_id"]
        start, end = ts(u["start"]), ts(u["end"])
        window = args.window_hours * 3600
        picked = collections.OrderedDict()   # event_id -> reason
        budget = [0]

        def add(e, why):
            if e["event_id"] in picked:
                return True
            t = len(render_event(e, [])[0]) // 4
            if budget[0] + t > args.max_tokens:
                return False
            picked[e["event_id"]] = why
            budget[0] += t
            return True

        left_out = collections.Counter()
        # 1. the whole conversation
        for e in by_conv[cid]:
            if not add(e, "the case's own conversation"):
                left_out["own conversation"] += 1
        # 2. conversations it names / that name it
        related = list(index["references"].get(cid, {}))
        related += [src for src, refs in index["references"].items() if cid in refs]
        for rc in dict.fromkeys(related):
            for e in by_conv.get(rc, []):
                if not add(e, f"conversation {rc} is named by or names this one"):
                    left_out["referenced conversations"] += 1
        # 3. rare terms anywhere
        terms = set()
        for e in by_conv[cid]:
            terms |= {m.lower() for m in TERM_RE.findall(e.get("content") or "")}
        rare = sorted((t for t in terms if t in index["rare_terms"]), key=lambda t: len(index["rare_terms"][t]))
        rare_set = set(rare[:40])
        for e in events:
            if e["conversation_id"] == cid or e["kind"] != "message":
                continue
            content = (e.get("content") or "").lower()
            hit = next((t for t in rare_set if t in content), None)
            if hit and not add(e, f"shares the rare term '{hit}'"):
                left_out["rare-term events"] += 1
        # 4. the case's agents nearby in time
        names = set(a for a in (e.get("actor") for e in by_conv[cid]) if a)
        if args.alias_field:
            for e in by_conv[cid]:
                names |= set(get_path(e, args.alias_field) or [])
        for e in events:
            if e["conversation_id"] == cid or e["kind"] != "message":
                continue
            t = ts(e.get("timestamp"))
            if t is None or start is None or t < start - window or t > end + window:
                continue
            claimed = set(get_path(e, args.alias_field) or []) if args.alias_field else set()
            who = (names & ({e.get("actor")} | claimed))
            if who and not add(e, f"by or signed as {sorted(who)[0]}, within {args.window_hours:.0f}h"):
                left_out["same-agent events"] += 1

        timeline = sorted(picked, key=lambda i: (by_id[i].get("timestamp") or "", i))
        case_id = "deep-" + re.sub(r"[^A-Za-z0-9]+", "-", uid).strip("-")
        L = [f"# Deep-dive input: {uid}", "",
             f"Conversation: {cid}. {len(timeline)} events from {len({by_id[i]['conversation_id'] for i in timeline})} "
             f"conversations, about {budget[0]:,} tokens, in time order. Each event says why it was included.", "",
             f"Left out at the size limit: {dict(left_out) if left_out else 'nothing'}.", "",
             setting_block(args.setting)]
        for i in timeline:
            e = by_id[i]
            L.append(f"--- conversation {e['conversation_id']} · included because: {picked[i]}")
            L.append(render_event(e, [])[0])
            L.append("")
        with open(os.path.join(args.out, "inputs", case_id + ".md"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(L) + "\n")
        reasons = collections.Counter(r.split(" ")[0] for r in picked.values())
        report.append(f"- `{uid}` → `inputs/{case_id}.md`: {len(timeline)} events, ~{budget[0]:,} tokens, "
                      f"{len({by_id[i]['conversation_id'] for i in timeline})} conversations; left out: "
                      f"{dict(left_out) if left_out else 'nothing'}")
    with open(os.path.join(args.out, "gathering-report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(report) + "\n")
    print("\n".join(report))


if __name__ == "__main__":
    main()
