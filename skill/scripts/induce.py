#!/usr/bin/env python3
"""Prepare the model-building step, and check its output. Pure code; the
model of the society is written by the strongest model following
codebook/model-instructions.md.

  prepare  Group cases that are the same trouble (the notes' same_trouble_as
           links, plus cases whose evidence cites the same events), then write
           one compact view of all notes for the model to read at once. The
           view keeps every quote and event ID; it only drops repetition.
  check    Check model.json: every institution described as a mechanism, cited
           cases exist, and every prediction has a trigger code can search for
           and a test for holding or failing.

Usage:
  python3 induce.py prepare --describe <describe run> --select <select run> --out <model run>
  python3 induce.py check   --run <model run>
"""

import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from context import setting_block  # noqa: E402


def load_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def prepare(args):
    notes = load_jsonl(os.path.join(args.describe, "notes.jsonl"))
    reasons = {r["unit_id"]: r["reason"] for r in load_jsonl(os.path.join(args.select, "selection.jsonl"))}
    by_case = {n["case_id"]: n for n in notes}
    unit_to_case = {n["unit_id"]: n["case_id"] for n in notes}

    # union-find over same_trouble_as links and shared evidence events
    parent = {c: c for c in by_case}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    for n in notes:
        for ref in n.get("same_trouble_as") or []:
            other = ref if ref in by_case else unit_to_case.get(ref)
            if other is None:  # links can name a unit or conversation; match loosely
                other = next((c for c in by_case if ref and (ref in c or ref in by_case[c]["unit_id"])), None)
            if other and other != n["case_id"]:
                union(n["case_id"], other)
    ev_owner = collections.defaultdict(set)
    for n in notes:
        for x in n.get("evidence") or []:
            ev_owner[x.get("event_id")].add(n["case_id"])
    for owners in ev_owner.values():
        owners = sorted(owners)
        for o in owners[1:]:
            union(owners[0], o)
    groups = collections.defaultdict(list)
    for c in by_case:
        groups[find(c)].append(c)
    group_id = {}
    for i, (root, members) in enumerate(sorted(groups.items(), key=lambda kv: -len(kv[1])), 1):
        for m in members:
            group_id[m] = f"G{i:02d}"

    os.makedirs(args.out, exist_ok=True)
    L = ["# All case notes, compact view", "", setting_block(args.setting),
         f"{len(notes)} cases in {len(groups)} trouble groups (cases in the same group look like the same "
         "trouble, linked by the notes or by shared evidence). Each case shows why it was selected "
         "(top = reveals most, coverage = variety, random = random sample).", ""]
    for n in sorted(notes, key=lambda n: (group_id[n["case_id"]], n["case_id"])):
        L.append(f"## {n['case_id']}  [group {group_id[n['case_id']]}, selected: {reasons.get(n['unit_id'])}"
                 f"{', ESCALATED: ' + n['escalate'].get('reason', '') if n['escalate'].get('flag') else ''}]")
        for k in ("summary", "trouble", "handling", "outcome", "institutions", "uncertainties"):
            if n.get(k):
                L.append(f"**{k}:** {n[k]}")
        mech = n.get("mechanism") or {}
        if isinstance(mech, dict) and any(mech.values()):
            L.append("**mechanism:** " + "; ".join(f"{k}: {v}" for k, v in mech.items() if v))
        if n.get("parties"):
            L.append("**parties:** " + "; ".join(f"{p.get('actor')} ({p.get('role_in_case')})" for p in n["parties"]))
        for x in n.get("norms") or []:
            L.append(f"- norm ({x.get('kind')}): {x.get('statement')} [{x.get('event_id')}] \"{x.get('quote')}\"")
        for x in n.get("evidence") or []:
            L.append(f"- evidence [{x.get('event_id')}] \"{x.get('quote')}\": {x.get('why')}")
        for x in n.get("cross_conversation") or []:
            L.append(f"- elsewhere [{x.get('event_id')}] ({x.get('found_by')}): {x.get('relevance')}")
        L.append("")
    with open(os.path.join(args.out, "notes-view.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    # ranking check: do the top-ranked cases reveal more than the random ones?
    def shows(n):
        mech = n.get("mechanism") or {}
        proc = str(mech.get("procedure", "")).strip().lower() if isinstance(mech, dict) else ""
        return bool(n.get("norms")) or (proc and not proc.startswith("none"))
    rank = {}
    for reason in sorted(set(reasons.values())):
        ns = [n for n in notes if reasons.get(n["unit_id"]) == reason]
        rank[reason] = {"cases": len(ns), "show_a_norm_or_procedure": sum(1 for n in ns if shows(n))}
    with open(os.path.join(args.out, "notes-summary.json"), "w", encoding="utf-8") as fh:
        json.dump({"notes": len(notes), "groups": len(groups), "ranking_check": rank}, fh, indent=1)
    with open(os.path.join(args.out, "groups.json"), "w", encoding="utf-8") as fh:
        json.dump({"group_of_case": group_id,
                   "groups": {g: sorted(c for c, gg in group_id.items() if gg == g)
                              for g in sorted(set(group_id.values()))}}, fh, indent=1)
    size = sum(len(x) for x in L)
    print(f"{len(notes)} notes, {len(groups)} groups (largest {max(len(v) for v in groups.values())} cases), "
          f"view ~{size // 4:,} tokens -> {args.out}/notes-view.md")


SCAN_TYPES = {"disagreement", "competing_claims", "rule_breach", "blame", "refusal", "overruled",
              "coordination_breakdown", "outside_authority", "identity_trouble", "other"}
INST_FIELDS = ("id", "name", "what", "why", "trigger", "operated_by", "procedure", "backed_by", "fails_when",
               "evidence_cases", "predictions")


def check(args):
    """Check model.json: every institution complete, cited cases exist, every
    prediction has a trigger code can search for and a holds/fails test."""
    with open(os.path.join(args.run, "model.json"), encoding="utf-8") as fh:
        model = json.load(fh)
    with open(os.path.join(args.run, "groups.json"), encoding="utf-8") as fh:
        cases = set(json.load(fh)["group_of_case"])
    problems, ids = [], set()
    insts = model.get("institutions", [])
    for inst in insts:
        name = inst.get("id", "?")
        for f in INST_FIELDS:
            if not inst.get(f):
                problems.append(f"{name}: missing {f}")
        bad = [c for c in inst.get("evidence_cases") or [] if c not in cases]
        if bad:
            problems.append(f"{name}: unknown cases {bad[:3]}")
        if len(inst.get("evidence_cases") or []) < 2 and not inst.get("rare"):
            problems.append(f"{name}: fewer than 2 evidence cases and not marked rare")
        for p in inst.get("predictions") or []:
            pid = p.get("id", "?")
            if pid in ids:
                problems.append(f"{pid}: duplicate prediction id")
            ids.add(pid)
            for f in ("statement", "holds_if", "fails_if"):
                if not p.get(f):
                    problems.append(f"{pid}: missing {f}")
            trig = p.get("trigger") or {}
            if not (trig.get("types") or trig.get("terms")):
                problems.append(f"{pid}: trigger needs scan types or terms")
            badt = [t for t in trig.get("types") or [] if t not in SCAN_TYPES]
            if badt:
                problems.append(f"{pid}: unknown scan types {badt}")
    if not model.get("map"):
        problems.append("missing map")
    print(f"institutions: {len(insts)}, predictions: {len(ids)}, problems: {len(problems)}")
    for p in problems[:30]:
        print(" -", p)
    sys.exit(1 if problems else 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--describe", required=True)
    p.add_argument("--select", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--setting", help="approved setting.md: its summary and vocabulary go at the top as background")
    c = sub.add_parser("check")
    c.add_argument("--run", required=True)
    args = ap.parse_args()
    prepare(args) if args.cmd == "prepare" else check(args)


if __name__ == "__main__":
    main()
