#!/usr/bin/env python3
"""Select trouble cases for deep reading, under a budget. Step 4 of the
pipeline. Pure code; it decides nothing about meaning, only order.

Run it on the episodes run (--triage <episodes run>): each episode then
appears once, through its representative piece. The budget limits how many
episodes are read closely (assembled and described); episodes not read
closely can still be drawn when the model is tested.
Cases are taken in tiers, and each selected case records why it was picked:

  1. top          episodes the scan scored reveals 3, best first. --top-max and
                  --top-per-group limit near-duplicates (many top cases can be
                  the same pattern in one group); top cases left out may still be drawn
                  when the model is tested, and the report lists them
  2. cross_check  code and triage disagree: the unit carries many code-computed
                  trouble hints (--hint-field), but triage saw nothing between
                  agents
  3. coverage     at least one case per trouble type x group x time period,
                  where such a case exists (best score first)
  4. score        the rest by score: reveals, then how much is between the
                  agents (exchanged > one_sided > none)
  5. random       a seeded random slice of the remaining trouble cases
                  (--random-share of the budget), whatever their score; it
                  measures how good triage's ranking is

--max-per-conversation stops one huge conversation (split into many parts)
from filling the budget in tiers 3-5; tiers 1-2 are never capped.

Usage:
  python3 select_cases.py --segment <segment run> --triage <triage run> --events <events.jsonl>
      --out <select run> --budget 150 [--random-share 0.2] [--periods 4]
      [--group-field extra.<field>] [--hint-field extra.<field> ...]
      [--cross-check-min 3] [--max-per-conversation 5] [--seed 1234]
"""

import argparse
import collections
import json
import os
import random

BETWEEN_RANK = {"exchanged": 2, "one_sided": 1, "none": 0}


def load_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def get_path(e, field):
    v = e
    for part in field.split("."):
        if not isinstance(v, dict):
            return None
        v = v.get(part)
    return v


def reasons_count(picked, reason):
    return sum(1 for r in picked.values() if r == reason)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--segment", required=True)
    ap.add_argument("--triage", required=True)
    ap.add_argument("--events", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--budget", type=int, required=True, help="number of cases to read closely")
    ap.add_argument("--random-share", type=float, default=0.2)
    ap.add_argument("--periods", type=int, default=4)
    ap.add_argument("--group-field", help="event field that names a larger group (majority per unit)")
    ap.add_argument("--hint-field", action="append", default=[])
    ap.add_argument("--cross-check-min", type=int, default=3,
                    help="hint events in a unit that make a 'none' label worth a second look")
    ap.add_argument("--max-per-conversation", type=int, default=5)
    ap.add_argument("--top-max", type=int, default=None, help="most reveals-3 episodes taken in tier 1")
    ap.add_argument("--top-per-group", type=int, default=None, help="most tier-1 cases per group")
    ap.add_argument("--seed", type=int, default=1234)
    args = ap.parse_args()

    units = {u["unit_id"]: u for u in load_jsonl(os.path.join(args.segment, "units.jsonl"))}
    labels = {r["unit_id"]: r for r in load_jsonl(os.path.join(args.triage, "triage.jsonl"))}
    missing = set(units) - set(labels)

    # group per unit: the most common value of --group-field among its events
    group = {}
    if args.group_field:
        ev_group = {}
        for e in load_jsonl(args.events):
            ev_group[e["event_id"]] = get_path(e, args.group_field)
        for uid, u in units.items():
            c = collections.Counter(ev_group.get(i) for i in u["event_ids"] if ev_group.get(i))
            group[uid] = c.most_common(1)[0][0] if c else "(none)"

    # time periods: equal-sized slices of unit start times
    starts = sorted(u["start"] for u in units.values() if u.get("start"))
    cuts = [starts[int(len(starts) * k / args.periods)] for k in range(1, args.periods)] if starts else []

    def period(u):
        s = u.get("start") or ""
        return sum(1 for c in cuts if s >= c)

    def hint_events(uid):
        return sum(units[uid]["hints"].get(f, 0) for f in args.hint_field)

    def score(uid):
        r = labels[uid]
        return (r["reveals"], BETWEEN_RANK.get(r["between_agents"], 0), units[uid]["n_actors"])

    trouble = [uid for uid, r in labels.items() if r["trouble"] and uid in units]
    picked = collections.OrderedDict()
    per_conv = collections.Counter()

    def take(uid, reason, capped=True):
        if uid in picked:
            return False
        conv = units[uid]["conversation_id"]
        if capped and per_conv[conv] >= args.max_per_conversation:
            return False
        picked[uid] = reason
        per_conv[conv] += 1
        return True

    random_n = int(round(args.budget * args.random_share))
    main_budget = args.budget - random_n

    # 1. top
    top_all = sorted([u for u in trouble if labels[u]["reveals"] == 3], key=score, reverse=True)
    top_group = collections.Counter()
    top_left_out = []
    for uid in top_all:
        g = group.get(uid, "(all)")
        if (args.top_max is not None and reasons_count(picked, "top") >= args.top_max) or \
           (args.top_per_group is not None and top_group[g] >= args.top_per_group):
            top_left_out.append(uid)
            continue
        if take(uid, "top", capped=False):
            top_group[g] += 1
    # 2. cross_check
    for uid in sorted(units, key=hint_events, reverse=True):
        if hint_events(uid) < args.cross_check_min:
            break
        r = labels.get(uid)
        if r and (not r["trouble"] or r["between_agents"] == "none"):
            take(uid, "cross_check", capped=False)
    # 3. coverage: best case per type x group x period, among cases with something between agents
    cells = collections.defaultdict(list)
    for uid in trouble:
        if labels[uid]["between_agents"] == "none":
            continue
        for t in labels[uid]["types"]:
            cells[(t, group.get(uid, "(all)"), period(units[uid]))].append(uid)
    cell_list = sorted(cells.items(), key=lambda kv: (len(kv[1]), kv[0]))  # rarest cells first
    for cell, uids in cell_list:
        if len(picked) >= main_budget:
            break
        if any(u in picked for u in uids):
            continue
        for uid in sorted(uids, key=score, reverse=True):
            if take(uid, "coverage"):
                break
    # 4. score
    for uid in sorted(trouble, key=score, reverse=True):
        if len(picked) >= main_budget:
            break
        take(uid, "score")
    # 5. random
    rng = random.Random(args.seed)
    rest = [u for u in sorted(trouble) if u not in picked]
    rng.shuffle(rest)
    n_random = 0
    for uid in rest:
        if n_random >= random_n:
            break
        if take(uid, "random"):
            n_random += 1

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "selection.jsonl"), "w", encoding="utf-8") as fh:
        for uid, reason in picked.items():
            r = labels[uid]
            fh.write(json.dumps({"unit_id": uid, "reason": reason, "conversation_id": units[uid]["conversation_id"],
                                 "reveals": r["reveals"], "episode_id": r.get("episode_id"), "between_agents": r["between_agents"],
                                 "types": r["types"], "group": group.get(uid), "period": period(units[uid]),
                                 "est_tokens": units[uid]["est_tokens"]}, ensure_ascii=False) + "\n")

    reasons = collections.Counter(picked.values())
    sel_tokens = sum(units[u]["est_tokens"] for u in picked)
    L = ["# Case selection", "",
         f"Budget: {args.budget} cases ({random_n} reserved for the random slice). "
         f"Selected: {len(picked)} cases, {sel_tokens:,} estimated tokens of unit text.", "",
         f"Units: {len(units)}. Labelled: {len(labels)}. Missing labels: {len(missing)}. "
         f"Trouble: {len(trouble)}.", "",
         "## Why cases were picked", ""]
    L += [f"- {k}: {v}" for k, v in reasons.most_common()]
    if reasons.get("top", 0) + reasons.get("cross_check", 0) > args.budget:
        L.append(f"- NOTE: the top and cross-check tiers alone exceed the budget; they are never cut.")
    if top_left_out:
        L += ["", f"Reveals-3 episodes not taken in tier 1 (group or top-max cap): {len(top_left_out)}. "
              f"Taken later in other tiers: {sum(1 for u in top_left_out if u in picked)}. "
              "The rest may still be drawn when the model is tested.", ""]
        L += [f"- `{u}`" for u in top_left_out if u not in picked]
    L += ["", "## Trouble cases: selected vs all", "", "| Between agents | All trouble | Selected |", "|---|---|---|"]
    for b in ("exchanged", "one_sided", "none"):
        L.append(f"| {b} | {sum(1 for u in trouble if labels[u]['between_agents'] == b)} | "
                 f"{sum(1 for u in picked if labels[u]['between_agents'] == b)} |")
    L += ["", "| Reveals | All trouble | Selected |", "|---|---|---|"]
    for s in (3, 2, 1):
        L.append(f"| {s} | {sum(1 for u in trouble if labels[u]['reveals'] == s)} | "
                 f"{sum(1 for u in picked if labels[u]['reveals'] == s)} |")
    L += ["", f"Coverage cells (type x group x period, with something between agents): {len(cells)}; "
          f"cells with a selected case: {sum(1 for us in cells.values() if any(u in picked for u in us))}.",
          f"Most cases from one conversation in tiers 3-5: capped at {args.max_per_conversation}."]
    with open(os.path.join(args.out, "selection-report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
