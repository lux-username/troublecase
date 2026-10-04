#!/usr/bin/env python3
"""Triage plumbing: pack conversation units into batches for a model to label,
and check the labels that come back. Step 3 of the pipeline. Pure code; the
labelling itself is done by a model (Sonnet) following codebook/trouble-rubric.md
(as subagents, or through the API).

  pack   Write batch files of unit texts (from segment.py's views.jsonl), each
         under a token limit, plus a manifest of which units are in which batch.
         --sample N picks a seeded random sample instead of all units (for a
         pilot); --include adds named units to the sample (known cases, as a
         sanity check; they are marked in the manifest).

  check  Read the labels (one JSONL file per batch) and check them against the
         rubric's format: every unit labelled exactly once, valid fields,
         consistent trouble/reveals values, and cited event IDs that really
         are in that unit. Writes triage.jsonl (all valid labels), a report,
         and a list of batches to rerun.

Usage:
  python3 triage.py pack --segment <segment run folder> --out <triage run folder>
                         [--max-batch-tokens 40000] [--sample 100 --seed 1234] [--include UNIT_ID ...]
  python3 triage.py check --segment <segment run folder> --run <triage run folder>
"""

import argparse
import collections
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from context import setting_block  # noqa: E402

TYPES = {"disagreement", "competing_claims", "rule_breach", "blame", "refusal", "overruled",
         "coordination_breakdown", "outside_authority", "identity_trouble", "other"}
FIELDS = {"unit_id", "trouble", "types", "reveals", "between_agents", "key_event_ids", "refers_elsewhere",
          "trouble_line", "also", "why"}
ALSO = {"tool_failure", "repetition_loop", "outside_action_unanswered", "lone_mishap"}
BETWEEN = {"none", "one_sided", "exchanged"}


def load_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def pack(args):
    units = load_jsonl(os.path.join(args.segment, "units.jsonl"))
    views = {r["unit_id"]: r["text"] for r in load_jsonl(os.path.join(args.segment, "views.jsonl"))}
    chosen = units
    included = set(args.include or [])
    if args.sample:
        rng = random.Random(args.seed)
        pool = [u for u in units if u["unit_id"] not in included]
        chosen = rng.sample(pool, min(args.sample, len(pool)))
        missing = included - {u["unit_id"] for u in units}
        if missing:
            raise SystemExit(f"--include units not found: {sorted(missing)}")
        chosen += [u for u in units if u["unit_id"] in included]
        rng.shuffle(chosen)  # known cases are not grouped at the end
    os.makedirs(os.path.join(args.out, "batches"), exist_ok=True)
    os.makedirs(os.path.join(args.out, "labels"), exist_ok=True)

    batches, cur, cur_tok = [], [], 0
    for u in chosen:
        t = u["est_tokens"]
        if cur and (cur_tok + t > args.max_batch_tokens or len(cur) >= args.max_batch_units):
            batches.append(cur)
            cur, cur_tok = [], 0
        cur.append(u["unit_id"])
        cur_tok += t
    if cur:
        batches.append(cur)

    manifest = {"segment": os.path.abspath(args.segment), "sample": args.sample, "seed": args.seed,
                "included_known_cases": sorted(included), "batches": {}}
    for i, ids in enumerate(batches, 1):
        name = f"batch-{i:03d}"
        manifest["batches"][name] = ids
        with open(os.path.join(args.out, "batches", name + ".md"), "w", encoding="utf-8") as fh:
            fh.write(f"# Triage {name}: {len(ids)} units\n\n" + setting_block(args.setting) + "Units, in order:\n")
            fh.write("\n".join(f"- {uid}" for uid in ids) + "\n\n")
            for uid in ids:
                fh.write("=" * 80 + "\n" + views[uid].rstrip() + "\n\n")
    with open(os.path.join(args.out, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    total = sum(u["est_tokens"] for u in chosen)
    print(f"packed {len(chosen)} units ({total:,} est. tokens) into {len(batches)} batches in {args.out}")


def check(args):
    with open(os.path.join(args.run, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    units = {u["unit_id"]: u for u in load_jsonl(os.path.join(args.segment, "units.jsonl"))}
    problems = collections.defaultdict(list)   # batch -> problems
    valid, rerun, repairs = [], [], []
    for name, ids in manifest["batches"].items():
        path = os.path.join(args.run, "labels", name + ".jsonl")
        if not os.path.exists(path):
            problems[name].append("no labels file")
            rerun.append(name)
            continue
        rows = []
        with open(path, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    problems[name].append(f"line {i} is not JSON")
        seen = collections.Counter(r.get("unit_id") for r in rows)
        for uid in ids:
            if seen[uid] == 0:
                problems[name].append(f"{uid}: not labelled")
            elif seen[uid] > 1:
                problems[name].append(f"{uid}: labelled {seen[uid]} times")
        for r in rows:
            uid = r.get("unit_id")
            errs = []
            if uid not in ids:
                errs.append("unit not in this batch")
            if set(r) != FIELDS:
                errs.append(f"fields {sorted(set(r) ^ FIELDS)} wrong")
            if not isinstance(r.get("trouble"), bool):
                errs.append("trouble not true/false")
            if r.get("reveals") not in (0, 1, 2, 3):
                errs.append("reveals not 0-3")
            if r.get("trouble") is False and (r.get("reveals") != 0 or r.get("types") or r.get("trouble_line")):
                errs.append("no trouble but reveals, types or trouble_line given")
            if r.get("trouble") is True and (r.get("reveals") == 0 or not r.get("types") or not r.get("trouble_line")):
                errs.append("trouble but reveals 0, no types or no trouble_line")
            if not isinstance(r.get("also"), list) or any(a not in ALSO for a in r.get("also") or []):
                errs.append("also must be a list of tool_failure/repetition_loop/outside_action_unanswered/lone_mishap")
            if r.get("between_agents") not in BETWEEN:
                errs.append("between_agents not none/one_sided/exchanged")
            if r.get("trouble") is False and r.get("between_agents") != "none":
                errs.append("no trouble but between_agents set")
            bad_types = [t for t in r.get("types") or [] if t not in TYPES]
            if bad_types:
                errs.append(f"unknown types {bad_types}")
            if uid in units:
                allowed = set(units[uid]["event_ids"]) | set(units[uid]["context_event_ids"])
                # repair an ID the model shortened, but only when it matches exactly one
                # event in this unit (e.g. a dropped prefix); every repair is counted
                fixed_ids = []
                for e in r.get("key_event_ids") or []:
                    if e not in allowed and isinstance(e, str):
                        cands = [a for a in allowed if a.endswith(e) or a.startswith(e)]
                        if len(cands) == 1:
                            repairs.append(f"{name} {uid}: {e} -> {cands[0]}")
                            e = cands[0]
                    fixed_ids.append(e)
                r["key_event_ids"] = fixed_ids
                bad_ids = [e for e in r.get("key_event_ids") or [] if e not in allowed]
                if bad_ids:
                    errs.append(f"event IDs not in unit: {bad_ids[:3]}")
                if r.get("trouble") and not r.get("key_event_ids"):
                    errs.append("trouble but no key event IDs")
            if errs:
                problems[name].append(f"{uid}: " + "; ".join(errs))
            elif seen[uid] == 1:
                r["batch"] = name
                r["known_case"] = uid in manifest.get("included_known_cases", [])
                valid.append(r)
        if problems[name] and name not in rerun:
            rerun.append(name)

    with open(os.path.join(args.run, "triage.jsonl"), "w", encoding="utf-8") as fh:
        for r in valid:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    n_units = sum(len(v) for v in manifest["batches"].values())
    tr = [r for r in valid if r["trouble"]]
    L = ["# Triage check", "",
         f"Units in manifest: {n_units}. Valid labels: {len(valid)}. Batches to rerun: {len(rerun)}. "
         f"Event IDs repaired (shortened by the model, matched to exactly one event in the unit): {len(repairs)}.", "",
         "## Results (valid labels only)", "",
         f"- Trouble: {len(tr)} of {len(valid)} ({round(100 * len(tr) / len(valid), 1) if valid else 0}%)",
         f"- Reveals scores: {dict(sorted(collections.Counter(r['reveals'] for r in valid).items()))}",
         f"- Not trouble between agents, labelled (any unit): {dict(collections.Counter(a for r in valid for a in r['also']).most_common())}",
         f"- Between agents (trouble only): {dict(collections.Counter(r['between_agents'] for r in tr))}",
         f"- Types: {dict(collections.Counter(t for r in tr for t in r['types']).most_common())}",
         f"- Refers elsewhere: {sum(1 for r in valid if r['refers_elsewhere'])}", ""]
    known = [r for r in valid if r.get("known_case")]
    if known:
        L += ["## Known cases (sanity check)", ""]
        L += [f"- `{r['unit_id']}`: trouble={r['trouble']}, reveals={r['reveals']}, "
              f"between_agents={r['between_agents']}, types={r['types']}"
              for r in known]
        L.append("")
    if any(problems.values()):
        L += ["## Problems", ""]
        for name, ps in problems.items():
            if ps:
                L.append(f"**{name}**")
                L += [f"- {p}" for p in ps[:20]]
    with open(os.path.join(args.run, "triage-check.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    with open(os.path.join(args.run, "id-repairs.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(repairs) + "\n")
    with open(os.path.join(args.run, "rerun.json"), "w", encoding="utf-8") as fh:
        json.dump(rerun, fh)
    print("\n".join(L[:12]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pack")
    p.add_argument("--segment", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--max-batch-tokens", type=int, default=25000)
    p.add_argument("--setting", help="approved setting.md: its summary and vocabulary go at the top of every batch as background")
    p.add_argument("--max-batch-units", type=int, default=60)
    p.add_argument("--sample", type=int)
    p.add_argument("--seed", type=int, default=1234)
    p.add_argument("--include", action="append")
    c = sub.add_parser("check")
    c.add_argument("--segment", required=True)
    c.add_argument("--run", required=True)
    args = ap.parse_args()
    pack(args) if args.cmd == "pack" else check(args)


if __name__ == "__main__":
    main()
