#!/usr/bin/env python3
"""Audit the scan: measure how often its labels are right. Pure code; the
checking is done by the strongest model following
codebook/scan-audit-instructions.md.

  pack   Draw a seeded random sample of scanned units (default 40), and write
         one file with each unit's full text and the scan's label for it.
  tally  Read the auditor's verdicts and report agreement, with a 90%
         interval, for: the gate (trouble yes/no), the reveals score (exact,
         and within one), and whether the key event IDs point at the right
         moments. The result goes into the briefing's limits, and decides
         whether the ranking can be trusted.

Usage:
  python3 audit_scan.py pack  --segment <segment run> --scan <scan run> --out <audit run> [--n 40] [--seed 7]
                              [--setting setting.md]
  python3 audit_scan.py tally --out <audit run>
"""

import argparse
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from context import setting_block  # noqa: E402


def load_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def wilson(k, n, z=1.645):
    """90% interval for a share k/n."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def share(k, n):
    lo, hi = wilson(k, n)
    return f"{k} of {n} ({100 * k / n:.0f}%, 90% interval {100 * lo:.0f}–{100 * hi:.0f}%)" if n else "0 of 0"


def pack(args):
    labels = load_jsonl(os.path.join(args.scan, "triage.jsonl"))
    views = {v["unit_id"]: v["text"] for v in load_jsonl(os.path.join(args.segment, "views.jsonl"))}
    rnd = random.Random(args.seed)
    sample = rnd.sample(labels, min(args.n, len(labels)))
    os.makedirs(args.out, exist_ok=True)
    L = [f"# Scan audit: {len(sample)} random units", "", setting_block(args.setting)]
    for r in sample:
        lab = {k: r[k] for k in ("trouble", "types", "reveals", "between_agents", "key_event_ids",
                                 "trouble_line", "also", "why") if k in r}
        L += ["=" * 80, f"## Unit {r['unit_id']}", "", "Scan label:", "```json",
              json.dumps(lab, ensure_ascii=False), "```", "", views.get(r["unit_id"], "(text missing)"), ""]
    with open(os.path.join(args.out, "audit-batch.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    with open(os.path.join(args.out, "sample.json"), "w") as fh:
        json.dump([r["unit_id"] for r in sample], fh)
    print(f"wrote {args.out}/audit-batch.md: {len(sample)} units, ~{len(chr(10).join(L)) // 4:,} tokens")


def tally(args):
    sample = json.load(open(os.path.join(args.out, "sample.json")))
    rows = {r["unit_id"]: r for r in load_jsonl(os.path.join(args.out, "audit.jsonl"))}
    missing = [u for u in sample if u not in rows]
    got = [rows[u] for u in sample if u in rows]
    n = len(got)
    gate = sum(1 for r in got if r.get("gate_correct") is True)
    fn = sum(1 for r in got if r.get("gate_correct") is False and r.get("should_be_trouble") is True)
    fp = sum(1 for r in got if r.get("gate_correct") is False and r.get("should_be_trouble") is False)
    rev_exact = sum(1 for r in got if r.get("reveals_correct") == 0)
    rev_close = sum(1 for r in got if isinstance(r.get("reveals_correct"), int) and abs(r["reveals_correct"]) <= 1)
    ids = [r for r in got if r.get("ids_ok") in (True, False)]
    ids_ok = sum(1 for r in ids if r["ids_ok"])
    L = ["# Scan audit", "",
         f"Units audited: {n} of {len(sample)} drawn{' (missing: ' + ', '.join(missing) + ')' if missing else ''}.", "",
         f"- Gate (trouble yes/no) right: {share(gate, n)}. Missed trouble: {fn}. Trouble that was not: {fp}.",
         f"- Reveals score exactly right: {share(rev_exact, n)}; within one: {share(rev_close, n)}.",
         f"- Key event IDs point at the right moments: {share(ids_ok, len(ids))}.", "",
         "## Disagreements", ""]
    L += [f"- `{r['unit_id']}`: {r.get('note', '')}" for r in got
          if r.get("gate_correct") is False or r.get("reveals_correct") not in (0, None) or r.get("ids_ok") is False]
    out = {"audited": n, "gate_right": gate, "missed_trouble": fn, "false_trouble": fp,
           "reveals_exact": rev_exact, "reveals_within_one": rev_close, "ids_checked": len(ids), "ids_ok": ids_ok}
    for k, v in [("gate", (gate, n)), ("reveals_exact", (rev_exact, n)), ("reveals_within_one", (rev_close, n))]:
        lo, hi = wilson(*v)
        out[k + "_interval_90"] = [round(100 * lo), round(100 * hi)]
    with open(os.path.join(args.out, "audit.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    with open(os.path.join(args.out, "audit.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    print("\n".join(L[:8]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pack")
    p.add_argument("--segment", required=True)
    p.add_argument("--scan", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--n", type=int, default=40)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--setting")
    t = sub.add_parser("tally")
    t.add_argument("--out", required=True)
    args = ap.parse_args()
    pack(args) if args.cmd == "pack" else tally(args)


if __name__ == "__main__":
    main()
