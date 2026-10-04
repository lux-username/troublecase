#!/usr/bin/env python3
"""Case assembly, follow-up search, and checks for the describe step.
Pure code; the describing is done by a model following
codebook/describe-questionnaire.md.

  build   For each selected case, write a case file: the case unit as the model
          reads it, its triage label, and related excerpts from OTHER
          conversations, each saying how it was found:
            - same actor:   events by the case's main actors in other
                            conversations within --window-hours of the case
            - reference:    conversations this one names, or that name it
            - rare term:    distinctive tokens shared with only a few
                            other conversations
            - before/after: neighbouring parts of the same conversation
          Excerpts are capped per case (--max-excerpt-chars). Cases are packed
          into batches for the describers.

  search  Follow-up search over all events, for a describer to run:
          --actor, --term, --conversation, --around EVENT_ID. Prints matching
          events (shortened) with IDs.

  check   Check the notes: one valid note per case, every cited event ID
          exists, and every quote appears word for word in that event's text
          (whitespace and URL shortening aside). Writes notes.jsonl and a report.

Usage:
  python3 assemble.py build  --segment <run> --select <run> --triage <run> --events <events.jsonl> --out <run>
                             [--cases-per-batch 10] [--window-hours 48] [--max-excerpt-chars 12000]
  python3 assemble.py search --events <events.jsonl> [--actor A] [--term T] [--conversation C] [--around ID] [--limit 15]
  python3 assemble.py check  --run <run> --events <events.jsonl>
"""

import argparse
import collections
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from segment import render_event, shorten_urls, TERM_RE  # noqa: E402
from context import setting_block  # noqa: E402

NOTE_FIELDS = {"case_id", "summary", "parties", "trouble", "handling", "mechanism", "norms", "outcome", "institutions",
               "evidence", "cross_conversation", "searches", "same_trouble_as", "escalate", "uncertainties"}


def load_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return None


def excerpt(e, max_chars=900):
    text, _, _ = render_event(e, [])
    return text if len(text) <= max_chars else text[:max_chars] + " …[shortened]"


# ------------------------------------------------------------ build

def build(args):
    events = load_jsonl(args.events)
    by_id = {e["event_id"]: e for e in events}
    by_conv = collections.defaultdict(list)
    for e in events:
        by_conv[e["conversation_id"]].append(e)
    units = {u["unit_id"]: u for u in load_jsonl(os.path.join(args.segment, "units.jsonl"))}
    views = {r["unit_id"]: r["text"] for r in load_jsonl(os.path.join(args.segment, "views.jsonl"))}
    with open(os.path.join(args.segment, "index.json"), encoding="utf-8") as fh:
        index = json.load(fh)
    labels = {r["unit_id"]: r for r in load_jsonl(os.path.join(args.triage, "triage.jsonl"))}
    selection = load_jsonl(os.path.join(args.select, "selection.jsonl"))
    conv_units = collections.defaultdict(list)
    for u in units.values():
        conv_units[u["conversation_id"]].append(u)

    os.makedirs(os.path.join(args.out, "cases"), exist_ok=True)
    os.makedirs(os.path.join(args.out, "notes"), exist_ok=True)
    window = args.window_hours * 3600
    stats = collections.Counter()
    case_ids = []
    for sel in selection:
        uid = sel["unit_id"]
        u = units[uid]
        cid = u["conversation_id"]
        case_id = "case-" + re.sub(r"[^A-Za-z0-9]+", "-", uid).strip("-")
        case_ids.append((case_id, uid))
        start, end = ts(u["start"]), ts(u["end"])
        found = []   # (found_by, event)
        seen = set(u["event_ids"])

        def add(how, e):
            if e["event_id"] not in seen:
                seen.add(e["event_id"])
                found.append((how, e))

        # before/after: neighbouring parts of the same conversation
        parts = sorted(conv_units[cid], key=lambda x: x["part"])
        for p in parts:
            if p["part"] == u["part"] - 1:
                for i in p["event_ids"][-2:]:
                    add("before: previous part of this conversation", by_id[i])
            if p["part"] == u["part"] + 1:
                for i in p["event_ids"][:2]:
                    add("after: next part of this conversation", by_id[i])
        # references: conversations named by this one, and ones that name it
        for target, first_ev in list(index["references"].get(cid, {}).items())[:4]:
            tev = by_conv.get(target, [])
            msgs = [e for e in tev if e["kind"] == "message"][:2]
            for e in msgs:
                add(f"reference: {first_ev} names conversation {target}", e)
        named_by = [(src, refs[cid]) for src, refs in index["references"].items() if cid in refs][:4]
        for src, ev_id in named_by:
            add(f"reference: {src} names this conversation", by_id[ev_id])
        # same actor nearby in time, in other conversations
        actors = u["actors"][:5]
        for a in actors:
            hits = 0
            for other_uid in index["actors"].get(a, {}):
                other = units.get(other_uid)
                if not other or other["conversation_id"] == cid:
                    continue
                os_, oe = ts(other["start"]), ts(other["end"])
                if None in (start, end, os_, oe) or os_ > end + window or oe < start - window:
                    continue
                for i in other["event_ids"]:
                    e = by_id[i]
                    if e.get("actor") == a and e["kind"] == "message":
                        add(f"same actor: {a} in {other['conversation_id']}", e)
                        hits += 1
                        break
                if hits >= 3:
                    break
        # rare terms shared with a few other conversations
        terms = set()
        for i in u["event_ids"]:
            terms |= {m.lower() for m in TERM_RE.findall(by_id[i].get("content") or "")}
        rare = [(t, index["rare_terms"][t]) for t in terms if t in index["rare_terms"]]
        rare.sort(key=lambda x: len(x[1]))
        for t, convs in rare[:6]:
            for c, first_ev in convs:
                if c != cid:
                    add(f"rare term: '{t}' (in {len(convs)} conversations)", by_id[first_ev])
                    break

        # write the case file, capping excerpts
        L = [f"# Case file {case_id}", "",
             f"Selected because: {sel['reason']}. Unit: {uid}.", "",
             setting_block(args.setting),
             "## Triage label (a pointer, not a conclusion)", "",
             "```json", json.dumps(labels[uid], ensure_ascii=False), "```", "",
             "## The case", "", views[uid].rstrip(), "",
             "## Related material from other conversations", ""]
        used = 0
        n = 0
        for how, e in found:
            block = f"*Found by {how}*\n{excerpt(e)}\n"
            if used + len(block) > args.max_excerpt_chars:
                stats["excerpts cut by cap"] += 1
                continue
            L.append(block)
            used += len(block)
            n += 1
            stats["excerpts: " + how.split(":")[0]] += 1
        if not n:
            L.append("(none found)")
        with open(os.path.join(args.out, "cases", case_id + ".md"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(L) + "\n")
        stats["cases"] += 1

    # batches
    batches = {}
    for i in range(0, len(case_ids), args.cases_per_batch):
        name = f"describe-{i // args.cases_per_batch + 1:03d}"
        batches[name] = [c for c, _ in case_ids[i:i + args.cases_per_batch]]
    manifest = {"cases": {c: u for c, u in case_ids}, "batches": batches,
                "events": os.path.abspath(args.events)}
    with open(os.path.join(args.out, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    sizes = [os.path.getsize(os.path.join(args.out, "cases", c + ".md")) for c, _ in case_ids]
    report = ["# Case assembly", "",
              f"Cases: {len(case_ids)}. Batches: {len(batches)} of up to {args.cases_per_batch}.",
              f"Case file size: median {sorted(sizes)[len(sizes) // 2] // 4:,} tokens, "
              f"total {sum(sizes) // 4:,} tokens (characters ÷ 4).", ""]
    report += [f"- {k}: {v}" for k, v in sorted(stats.items())]
    with open(os.path.join(args.out, "assembly-report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(report) + "\n")
    print("\n".join(report))


# ------------------------------------------------------------ search

def search(args):
    events = load_jsonl(args.events)
    out = []
    if args.around:
        conv = next((e["conversation_id"] for e in events if e["event_id"] == args.around), None)
        evs = [e for e in events if e["conversation_id"] == conv]
        idx = next((i for i, e in enumerate(evs) if e["event_id"] == args.around), 0)
        out = evs[max(0, idx - 3): idx + 4]
    else:
        for e in events:
            if args.actor and e.get("actor") != args.actor and args.actor not in (e.get("extra", {}).get("actor_signature") or []):
                continue
            if args.term and args.term.lower() not in (e.get("content") or "").lower():
                continue
            if args.conversation and e["conversation_id"] != args.conversation:
                continue
            out.append(e)
    total = len(out)
    for e in out[:args.limit]:
        print(f"--- conversation {e['conversation_id']}\n{excerpt(e, 700)}\n")
    print(f"[{min(total, args.limit)} of {total} matching events shown]")


# ------------------------------------------------------------ check

def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def check(args):
    with open(os.path.join(args.run, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    events = {e["event_id"]: e for e in load_jsonl(args.events)}
    problems = collections.defaultdict(list)
    valid, rerun = [], []
    for name, cases in manifest["batches"].items():
        path = os.path.join(args.run, "notes", name + ".jsonl")
        if not os.path.exists(path):
            problems[name].append("no notes file")
            rerun.append(name)
            continue
        rows = []
        for i, line in enumerate(open(path, encoding="utf-8"), 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    problems[name].append(f"line {i} is not JSON")
        got = collections.Counter(r.get("case_id") for r in rows)
        for c in cases:
            if got[c] != 1:
                problems[name].append(f"{c}: {got[c]} notes")
        for r in rows:
            errs = []
            if set(r) != NOTE_FIELDS:
                errs.append(f"fields differ: {sorted(set(r) ^ NOTE_FIELDS)}")
            cited = [x.get("event_id") for x in (r.get("evidence") or []) + (r.get("norms") or [])
                     + (r.get("cross_conversation") or []) if isinstance(x, dict)]
            missing = [c for c in cited if c not in events]
            if missing:
                errs.append(f"event IDs not found: {missing[:3]}")
            for x in (r.get("evidence") or []) + (r.get("norms") or []):
                if not isinstance(x, dict) or x.get("event_id") not in events or not x.get("quote"):
                    continue
                raw = events[x["event_id"]].get("content") or ""
                q = norm(x["quote"])
                if q not in norm(raw) and q not in norm(shorten_urls(raw)):
                    errs.append(f"quote not found verbatim in {x['event_id']}: {x['quote'][:60]!r}")
            if errs:
                problems[name].append(f"{r.get('case_id')}: " + "; ".join(errs[:4]))
            elif got[r.get("case_id")] == 1:
                r["batch"] = name
                r["unit_id"] = manifest["cases"].get(r.get("case_id"))
                valid.append(r)
        if problems[name] and name not in rerun:
            rerun.append(name)
    with open(os.path.join(args.run, "notes.jsonl"), "w", encoding="utf-8") as fh:
        for r in valid:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    L = ["# Describe check", "", f"Cases: {len(manifest['cases'])}. Valid notes: {len(valid)}. "
         f"Batches with problems: {len(rerun)}. Escalated: {sum(1 for r in valid if (r.get('escalate') or {}).get('flag'))}.", ""]
    for name, ps in problems.items():
        if ps:
            L.append(f"**{name}**")
            L += [f"- {p}" for p in ps[:15]]
    with open(os.path.join(args.run, "describe-check.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    with open(os.path.join(args.run, "rerun.json"), "w", encoding="utf-8") as fh:
        json.dump(rerun, fh)
    print("\n".join(L[:40]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    for a in ("--segment", "--select", "--triage", "--events", "--out"):
        b.add_argument(a, required=True)
    b.add_argument("--cases-per-batch", type=int, default=10)
    b.add_argument("--setting", help="approved setting.md: its summary and vocabulary go at the top of every batch as background")
    b.add_argument("--window-hours", type=float, default=48)
    b.add_argument("--max-excerpt-chars", type=int, default=12000)
    s = sub.add_parser("search")
    s.add_argument("--events", required=True)
    s.add_argument("--actor")
    s.add_argument("--term")
    s.add_argument("--conversation")
    s.add_argument("--around")
    s.add_argument("--limit", type=int, default=15)
    c = sub.add_parser("check")
    c.add_argument("--run", required=True)
    c.add_argument("--events", required=True)
    args = ap.parse_args()
    {"build": build, "search": search, "check": check}[args.cmd](args)


if __name__ == "__main__":
    main()
