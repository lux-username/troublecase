#!/usr/bin/env python3
"""Episodes: merge scanned pieces that are the same trouble, so everything
after this counts troubles, not pieces. Pure code.

A long conversation is split into pieces for reading, and one trouble can run
across several pieces, or across conversations. Two trouble pieces (scan gate
passed) are joined into one episode when, within --window-hours of each other:

  - they are neighbouring pieces of the same conversation and their key
    events share an actor; or
  - one's conversation names the other's (a reference in the index) and their
    key events share an actor and a rare term; or
  - their key events share at least --min-shared-terms of the index's rare
    terms (distinctive words found in only a few conversations).

Episodes never grow beyond --max-units pieces (a join that would exceed it is
skipped and reported), so one busy period cannot swallow everything.

Each episode gets one merged label: the highest reveals score, the strongest
between-agents value, all types, all key events, and the trouble lines of
its pieces. Its representative piece is the one with the highest score.

Outputs (in --out):
  episodes.jsonl   one line per episode (members, representative, merged label)
  triage.jsonl     the scan labels with each episode's merged label on its
                   representative piece and the other members left out, so
                   select_cases.py picks at most one piece per episode
  episodes.md      a report: how many pieces became how many episodes, and why

Usage:
  python3 episodes.py --segment <segment run> --scan <scan run> --events <events.jsonl> --out <episodes run>
                      [--window-hours 24] [--min-shared-terms 2] [--max-units 12]
"""

import argparse
import collections
import json
import os
from datetime import datetime

BETWEEN_RANK = {"exchanged": 2, "one_sided": 1, "none": 0}


def load_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def ts(s):
    try:
        return datetime.fromisoformat((s or "").replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--segment", required=True)
    ap.add_argument("--scan", required=True)
    ap.add_argument("--events", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--window-hours", type=float, default=24)
    ap.add_argument("--min-shared-terms", type=int, default=2)
    ap.add_argument("--max-units", type=int, default=12)
    args = ap.parse_args()

    units = {u["unit_id"]: u for u in load_jsonl(os.path.join(args.segment, "units.jsonl"))}
    labels = {r["unit_id"]: r for r in load_jsonl(os.path.join(args.scan, "triage.jsonl"))}
    index = json.load(open(os.path.join(args.segment, "index.json"), encoding="utf-8"))
    actor_of = {}
    for e in load_jsonl(args.events):
        actor_of[e["event_id"]] = e.get("actor")

    trouble = sorted(u for u, r in labels.items() if r.get("trouble") and u in units)
    key_actors = {u: {actor_of.get(i) for i in labels[u]["key_event_ids"]} - {None} for u in trouble}
    # rare terms carried by each piece's key events
    ev_terms = collections.defaultdict(set)
    for term, hits in index["rare_terms"].items():
        for _conv, eid in hits:
            ev_terms[eid].add(term)
    key_terms = {u: set().union(*[ev_terms.get(i, set()) for i in labels[u]["key_event_ids"]]) for u in trouble}
    refs = index.get("references", {})
    window = args.window_hours * 3600

    def mid(u):
        a, b = ts(units[u].get("start")), ts(units[u].get("end"))
        return (a + b) / 2 if a and b else a or b

    parent = {u: u for u in trouble}
    size = {u: 1 for u in trouble}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    why = collections.Counter()
    skipped = 0

    def join(a, b, reason):
        nonlocal skipped
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        if size[ra] + size[rb] > args.max_units:
            skipped += 1
            return
        parent[rb] = ra
        size[ra] += size[rb]
        why[reason] += 1

    def close(a, b):
        ma, mb = mid(a), mid(b)
        return ma is not None and mb is not None and abs(ma - mb) <= window

    # 1. neighbouring pieces of one conversation
    by_conv = collections.defaultdict(list)
    for u in trouble:
        by_conv[units[u]["conversation_id"]].append(u)
    for conv, us in by_conv.items():
        us.sort(key=lambda u: (units[u].get("part", 0), units[u].get("start") or ""))
        for a, b in zip(us, us[1:]):
            if units[b].get("part", 0) - units[a].get("part", 0) == 1 and close(a, b) and key_actors[a] & key_actors[b]:
                join(a, b, "neighbouring pieces, shared actor")
    # 2. conversations that name each other
    for src, targets in refs.items():
        for tgt in targets:
            for a in by_conv.get(src, []):
                for b in by_conv.get(tgt, []):
                    if close(a, b) and key_actors[a] & key_actors[b] and key_terms[a] & key_terms[b]:
                        join(a, b, "conversations name each other, shared actor and rare term")
    # 3. shared rare terms (only terms shared by few pieces, so this stays cheap)
    term_units = collections.defaultdict(list)
    for u in trouble:
        for t in key_terms[u]:
            term_units[t].append(u)
    pair_terms = collections.Counter()
    for t, us in term_units.items():
        if len(us) > 20:
            continue
        for i in range(len(us)):
            for j in range(i + 1, len(us)):
                pair_terms[(us[i], us[j])] += 1
    for (a, b), n in pair_terms.items():
        if n >= args.min_shared_terms and close(a, b):
            join(a, b, "shared rare terms")

    groups = collections.defaultdict(list)
    for u in trouble:
        groups[find(u)].append(u)

    def rank(u):
        r = labels[u]
        return (r["reveals"], BETWEEN_RANK.get(r["between_agents"], 0), units[u].get("n_actors", 0))

    os.makedirs(args.out, exist_ok=True)
    episodes, rep_label = [], {}
    for i, (root, members) in enumerate(sorted(groups.items(), key=lambda kv: min(units[u].get("start") or "" for u in kv[1])), 1):
        members.sort(key=lambda u: units[u].get("start") or "")
        rep = max(members, key=rank)
        ls = [labels[u] for u in members]
        merged = dict(labels[rep])
        merged["types"] = sorted({t for r in ls for t in r["types"]})
        merged["reveals"] = max(r["reveals"] for r in ls)
        merged["between_agents"] = max((r["between_agents"] for r in ls), key=lambda b: BETWEEN_RANK.get(b, 0))
        merged["key_event_ids"] = [e for r in ls for e in r["key_event_ids"]]
        merged["refers_elsewhere"] = any(r["refers_elsewhere"] for r in ls)
        merged["also"] = sorted({a for r in ls for a in r.get("also", [])})
        merged["trouble_line"] = " | ".join(dict.fromkeys(r["trouble_line"] for r in ls if r.get("trouble_line")))
        eid = f"ep-{i:04d}"
        merged["episode_id"] = eid
        rep_label[rep] = merged
        episodes.append({"episode_id": eid, "representative": rep, "units": members,
                         "conversations": sorted({units[u]["conversation_id"] for u in members}),
                         "start": units[members[0]].get("start"), "end": units[members[-1]].get("end"),
                         "est_tokens": sum(units[u].get("est_tokens", 0) for u in members),
                         **{k: merged[k] for k in ("types", "reveals", "between_agents", "key_event_ids",
                                                   "trouble_line", "also")}})
    member_of = {u: ep["episode_id"] for ep in episodes for u in ep["units"]}
    with open(os.path.join(args.out, "episodes.jsonl"), "w", encoding="utf-8") as fh:
        for ep in episodes:
            fh.write(json.dumps(ep, ensure_ascii=False) + "\n")
    with open(os.path.join(args.out, "triage.jsonl"), "w", encoding="utf-8") as fh:
        for u, r in labels.items():
            if u in rep_label:
                fh.write(json.dumps(rep_label[u], ensure_ascii=False) + "\n")
            elif u not in member_of:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    multi = [ep for ep in episodes if len(ep["units"]) > 1]
    cross = [ep for ep in episodes if len(ep["conversations"]) > 1]
    L = ["# Episodes", "",
         f"Trouble pieces (scan gate passed): {len(trouble)}. Episodes: {len(episodes)}. "
         f"Episodes of more than one piece: {len(multi)} (largest {max((len(e['units']) for e in episodes), default=0)}). "
         f"Spanning more than one conversation: {len(cross)}.", "",
         f"Joins: {dict(why)}. Joins skipped because an episode would exceed {args.max_units} pieces: {skipped}.", "",
         f"Reveals score (episodes): {dict(sorted(collections.Counter(e['reveals'] for e in episodes).items()))}.",
         f"Between agents (episodes): {dict(collections.Counter(e['between_agents'] for e in episodes))}.",
         f"Not trouble between agents, labelled (all pieces): "
         f"{dict(collections.Counter(a for r in labels.values() for a in r.get('also', [])).most_common())}.", "",
         "## Largest episodes", ""]
    for ep in sorted(episodes, key=lambda e: -len(e["units"]))[:10]:
        L.append(f"- `{ep['episode_id']}` ({len(ep['units'])} pieces, {len(ep['conversations'])} conversations, "
                 f"reveals {ep['reveals']}): {ep['trouble_line'][:200]}")
    summary = {"trouble_pieces": len(trouble), "episodes": len(episodes), "multi_piece_episodes": len(multi),
               "cross_conversation_episodes": len(cross), "pieces_scanned": len(labels),
               "reveals": dict(collections.Counter(e["reveals"] for e in episodes)),
               "between_agents": dict(collections.Counter(e["between_agents"] for e in episodes)),
               "types": dict(collections.Counter(t for e in episodes for t in e["types"])),
               "routine_labels": dict(collections.Counter(a for r in labels.values() for a in r.get("also", [])))}
    with open(os.path.join(args.out, "episodes-summary.json"), "w") as fh:
        json.dump(summary, fh, indent=1)
    with open(os.path.join(args.out, "episodes.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("\n".join(L[:9]))


if __name__ == "__main__":
    main()
