#!/usr/bin/env python3
"""Test the model of the society on random episodes. Pure code; the reading
is done by a model (Sonnet) following codebook/test-instructions.md.

The model (model.json) makes predictions of the form "when [trigger], then
[what happens]". This step checks them on episodes the model was NOT built
from, drawn at random, so the test is not rigged.

  draw   For each prediction, find the episodes where its trigger may occur
         (the scan's types and/or terms named in the prediction), leave out the
         episodes the model was built from and any drawn in earlier rounds, and
         draw --n at random, using at most --pool-share of the unseen episodes
         (default half), so a refinement round still has fresh ones. Pack the drawn episodes into batches: each episode
         appears once, with the list of predictions to judge on it, and its
         full text (every piece of the episode, up to --max-episode-tokens).
  tally  Check the readers' verdicts (holds / fails / not_applicable, with
         event IDs inside the episode) and count them per prediction, with a
         90% interval. Flags predictions that failed, whose trigger rarely
         applied, or that had too few cases to tell; and gives an overall
         verdict on how well the model maps the society ("cannot tell" when
         fewer than half the predictions could be judged). The numbers here are
         the briefing's numbers about the institutions.

Usage:
  python3 test_model.py draw  --model <model run> --episodes <episodes run> --segment <segment run>
                              --select <select run> --out <test run> [--exclude-draws <earlier test run> ...]
                              [--n 15] [--seed 11] [--setting setting.md]
                              [--max-episode-tokens 12000] [--max-batch-tokens 80000]
  python3 test_model.py tally --out <test run> --segment <segment run> --episodes <episodes run>
"""

import argparse
import collections
import json
import os
import random
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from context import setting_block  # noqa: E402
from audit_scan import wilson  # noqa: E402

VERDICTS = {"holds", "fails", "not_applicable"}
COVERAGE = {"covered", "partly", "uncovered"}


def load_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def episode_text(ep, views, units, max_tokens):
    """Every piece of the episode in time order, the representative first in
    priority; pieces beyond the cap are named, not silently dropped."""
    rep_t = _t(units[ep["representative"]])
    order = [ep["representative"]] + sorted((u for u in ep["units"] if u != ep["representative"]),
                                            key=lambda u: abs(_t(units[u]) - rep_t))
    kept, used, left = [], 0, []
    for u in order:
        t = len(views.get(u, "")) // 4
        if kept and used + t > max_tokens:
            left.append(u)
            continue
        kept.append(u)
        used += t
    kept.sort(key=lambda u: units[u].get("start") or "")
    text = "\n\n".join(views.get(u, f"(text of {u} missing)").rstrip() for u in kept)
    if left:
        text += f"\n\n[{len(left)} more piece(s) of this episode left out at the size limit: {', '.join(left)}]"
    return text


def _t(u):
    try:
        return datetime.fromisoformat((u.get("start") or "").replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def draw(args):
    """--mode all (default): a random sample of unseen episodes, each judged on
    EVERY prediction plus a coverage question. --mode topup: after tallying an
    'all' round, draw targeted episodes for the predictions that met fewer than
    5 applicable episodes, and add them to the same test run. --mode targeted:
    the older design, a separate targeted draw per prediction."""
    model = json.load(open(os.path.join(args.model, "model.json"), encoding="utf-8"))
    episodes = {e["episode_id"]: e for e in load_jsonl(os.path.join(args.episodes, "episodes.jsonl"))}
    units = {u["unit_id"]: u for u in load_jsonl(os.path.join(args.segment, "units.jsonl"))}
    views = {v["unit_id"]: v["text"] for v in load_jsonl(os.path.join(args.segment, "views.jsonl"))}
    built_from = {r.get("episode_id") for r in load_jsonl(os.path.join(args.select, "selection.jsonl"))} - {None}
    earlier = set()
    for d in args.exclude_draws or []:
        man = json.load(open(os.path.join(d, "manifest.json")))
        earlier |= {ep for items in man["batches"].values() for ep, _ in items}
    manifest_path = os.path.join(args.out, "manifest.json")
    old = json.load(open(manifest_path)) if args.mode == "topup" else None
    if old:
        earlier |= {ep for items in old["batches"].values() for ep, _ in items}
    pool = [e for eid, e in episodes.items() if eid not in built_from and eid not in earlier]
    rnd = random.Random(args.seed)
    cap = max(1, int(len(pool) * args.pool_share))
    preds = [(inst["id"], p) for inst in model["institutions"] for p in inst.get("predictions", [])]
    pred_by_id = {p["id"]: (inst_id, p) for inst_id, p in preds}
    draws, how = collections.defaultdict(list), {}

    if args.mode == "all":
        for e in rnd.sample(pool, min(cap, len(pool))):
            draws[e["episode_id"]] = [p["id"] for _, p in preds]
        how["all"] = f"{len(draws)} random unseen episodes, every prediction judged on each"
    else:
        if args.mode == "topup":
            res = json.load(open(os.path.join(args.out, "test-results.json")))
            todo = {pid for pid, r in res["predictions"].items() if r["applicable"] < 5}
            preds_to_draw = [(i, p) for i, p in preds if p["id"] in todo]
        else:
            preds_to_draw = list(preds)
        lowered = {}

        def text_of(e):
            return (e.get("trouble_line", "") + " " + " ".join(views.get(u, "") for u in e["units"])).lower()
        rnd.shuffle(preds_to_draw)
        for inst_id, p in preds_to_draw:
            trig = p.get("trigger") or {}
            types, terms = set(trig.get("types") or []), [t.lower() for t in trig.get("terms") or []]

            def by_type(e):
                return bool(types & set(e["types"]))

            def by_term(e):
                if e["episode_id"] not in lowered:
                    lowered[e["episode_id"]] = text_of(e)
                return any(t in lowered[e["episode_id"]] for t in terms)
            if types and terms:
                elig = [e for e in pool if by_type(e) and by_term(e)]
                how[p["id"]] = "scan type and term"
                if len(elig) < args.n:
                    elig = [e for e in pool if by_type(e) or by_term(e)]
                    how[p["id"]] = "scan type or term (too few with both)"
            elif types:
                elig, how[p["id"]] = [e for e in pool if by_type(e)], "scan type"
            else:
                elig, how[p["id"]] = [e for e in pool if by_term(e)], "term"
            # reuse episodes already drawn first, then add new ones only while the
            # round's share of the unseen pool lasts, so later rounds still have fresh episodes
            rnd.shuffle(elig)
            already = [e for e in elig if e["episode_id"] in draws]
            new = [e for e in elig if e["episode_id"] not in draws]
            chosen = already[:args.n]
            for e in new:
                if len(chosen) >= args.n or len(draws) >= cap:
                    break
                chosen.append(e)
                draws[e["episode_id"]]
            for e in chosen:
                draws[e["episode_id"]].append(p["id"])
            how[p["id"]] += f"; {len(elig)} eligible, {len(chosen)} drawn"

    os.makedirs(os.path.join(args.out, "batches"), exist_ok=True)
    batches, cur, cur_t = [], [], 0
    texts = {}
    for eid in sorted(draws, key=lambda x: rnd.random()):
        texts[eid] = episode_text(episodes[eid], views, units, args.max_episode_tokens)
        t = len(texts[eid]) // 4
        if cur and cur_t + t > args.max_batch_tokens:
            batches.append(cur)
            cur, cur_t = [], 0
        cur.append(eid)
        cur_t += t
    if cur:
        batches.append(cur)
    manifest = old or {"batches": {}, "batch_mode": {}, "how_drawn": {}, "unseen_pool": len(pool),
                       "pred_inst": {p["id"]: i for i, p in preds}}
    manifest.setdefault("batch_mode", {})
    manifest.setdefault("pred_inst", {p["id"]: i for i, p in preds})
    manifest["how_drawn"].update(how)
    start = len(manifest["batches"])
    coverage = args.mode == "all"
    for k, b in enumerate(batches, start + 1):
        name = f"test-{k:03d}"
        manifest["batches"][name] = [[eid, draws[eid]] for eid in b]
        manifest["batch_mode"][name] = args.mode
        used = sorted({pid for eid in b for pid in draws[eid]})
        L = [f"# Model test {name}: {len(b)} episodes" + (" (every prediction, plus coverage)" if coverage else ""),
             "", setting_block(args.setting), "## Predictions to judge in this batch", ""]
        for pid in used:
            inst_id, p = pred_by_id[pid]
            L += [f"### {pid} (institution: {inst_id})", "", f"- **Prediction:** {p['statement']}",
                  f"- **Applies when:** {(p.get('trigger') or {}).get('description', '')}",
                  f"- **Holds if:** {p['holds_if']}", f"- **Fails if:** {p['fails_if']}", ""]
        if coverage:
            L += ["### _coverage", "", "For every episode, also answer: is something going on in this episode "
                  "that none of the institutions above explains? (See the test instructions.)", ""]
        for eid in b:
            L += ["=" * 80, f"## Episode {eid}", "",
                  f"Judge on this episode: {', '.join(draws[eid])}" + (", and _coverage" if coverage else ""),
                  "", texts[eid], ""]
        with open(os.path.join(args.out, "batches", name + ".md"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(L) + "\n")
    all_drawn = {ep for items in manifest["batches"].values() for ep, _ in items}
    manifest["drawn"] = len(all_drawn)
    manifest["left_unseen_after_this_round"] = manifest["unseen_pool"] - len(all_drawn)
    with open(manifest_path, "w") as fh:
        json.dump(manifest, fh, indent=1)
    total_t = sum(len(texts[e]) // 4 for e in texts)
    print(f"mode {args.mode}: {len(draws)} episodes drawn now ({len(all_drawn)} in this test run) of "
          f"{manifest['unseen_pool']} unseen at the start; {manifest['left_unseen_after_this_round']} stay unseen. "
          f"{len(batches)} new batches, ~{total_t:,} tokens of episode text.")
    if manifest["left_unseen_after_this_round"] < 5 * max(1, len(preds)) // 2:
        print("WARNING: few unseen episodes remain; a further round could judge only a few predictions.")
    for pid, h in how.items():
        print(f"  {pid}: {h}")


def tally(args):
    man = json.load(open(os.path.join(args.out, "manifest.json")))
    units = {u["unit_id"]: u for u in load_jsonl(os.path.join(args.segment, "units.jsonl"))}
    episodes = {e["episode_id"]: e for e in load_jsonl(os.path.join(args.episodes, "episodes.jsonl"))}
    allowed = {eid: {i for u in e["units"] for i in units[u]["event_ids"] + units[u].get("context_event_ids", [])}
               for eid, e in episodes.items()}
    problems, rerun, valid = collections.defaultdict(list), [], []
    for name, items in man["batches"].items():
        path = os.path.join(args.out, "results", name + ".jsonl")
        if not os.path.exists(path):
            problems[name].append("no results file")
            rerun.append(name)
            continue
        rows = []
        for i, line in enumerate(open(path, encoding="utf-8"), 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    problems[name].append(f"line {i} is not JSON")
        want = {(eid, pid) for eid, pids in items for pid in pids}
        if man.get("batch_mode", {}).get(name, "targeted") == "all":
            want |= {(eid, "_coverage") for eid, _ in items}
        got = collections.Counter((r.get("episode_id"), r.get("prediction_id")) for r in rows)
        for k in want:
            if got[k] != 1:
                problems[name].append(f"{k[0]} / {k[1]}: {got[k]} verdicts")
        for r in rows:
            k = (r.get("episode_id"), r.get("prediction_id"))
            errs = []
            if k not in want:
                errs.append("not asked in this batch")
            if k[1] == "_coverage":
                if r.get("verdict") not in COVERAGE:
                    errs.append("coverage verdict not covered/partly/uncovered")
                elif r["verdict"] != "covered" and not r.get("event_ids"):
                    errs.append("partly/uncovered without event IDs")
            elif r.get("verdict") not in VERDICTS:
                errs.append("verdict not holds/fails/not_applicable")
            if not r.get("note"):
                errs.append("no note")
            if r.get("verdict") in ("holds", "fails", "partly", "uncovered"):
                if r.get("verdict") in ("holds", "fails") and not r.get("event_ids"):
                    errs.append("holds/fails without event IDs")
                bad = [i for i in r.get("event_ids") or [] if i not in allowed.get(k[0], set())]
                if bad:
                    errs.append(f"event IDs not in this episode: {bad[:3]}")
            if errs:
                problems[name].append(f"{k[0]} / {k[1]}: " + "; ".join(errs))
            elif got[k] == 1:
                valid.append(r)
        if problems[name] and name not in rerun:
            rerun.append(name)

    cov_rows = [r for r in valid if r["prediction_id"] == "_coverage"]
    valid = [r for r in valid if r["prediction_id"] != "_coverage"]
    per = collections.defaultdict(collections.Counter)
    fails = collections.defaultdict(list)
    for r in valid:
        per[r["prediction_id"]][r["verdict"]] += 1
        if r["verdict"] == "fails":
            fails[r["prediction_id"]].append(r)
    asked = collections.Counter(pid for items in man["batches"].values() for _, pids in items for pid in pids)
    # coverage, prevalence and co-occurrence: only from the random all-predictions sample
    all_eps = {eid for name, items in man["batches"].items() if man.get("batch_mode", {}).get(name) == "all"
               for eid, _ in items}
    pred_inst = man.get("pred_inst", {})
    applied = collections.defaultdict(set)   # episode -> institutions whose predictions applied
    for r in valid:
        if r["episode_id"] in all_eps and r["verdict"] in ("holds", "fails"):
            applied[r["episode_id"]].add(pred_inst.get(r["prediction_id"], r["prediction_id"].split(".")[0]))
    judged_eps = {r["episode_id"] for r in valid if r["episode_id"] in all_eps}
    cov = collections.Counter(r["verdict"] for r in cov_rows if r["episode_id"] in all_eps)
    n_all = len(judged_eps)
    none_applied = sum(1 for e in judged_eps if not applied.get(e))
    insts = sorted(set(pred_inst.values()))
    prevalence = {}
    for inst in insts:
        k = sum(1 for e in judged_eps if inst in applied.get(e, set()))
        lo, hi = wilson(k, n_all)
        prevalence[inst] = {"episodes": k, "of": n_all, "pct": round(100 * k / n_all) if n_all else None,
                            "interval_90": [round(100 * lo), round(100 * hi)] if n_all else None}
    pairs = collections.Counter()
    for e in judged_eps:
        a = sorted(applied.get(e, set()))
        for x in range(len(a)):
            for y in range(x + 1, len(a)):
                pairs[(a[x], a[y])] += 1
    lo, hi = wilson(none_applied, n_all)
    coverage = {"random_episodes": n_all, "no_institution_applied": none_applied,
                "no_institution_applied_pct": round(100 * none_applied / n_all) if n_all else None,
                "no_institution_applied_interval_90": [round(100 * lo), round(100 * hi)] if n_all else None,
                "reader_says": dict(cov),
                "together": [{"institutions": list(k), "episodes": v} for k, v in pairs.most_common(10)]}
    results, flags = {}, {}
    for pid in sorted(asked):
        c = per[pid]
        app = c["holds"] + c["fails"]
        lo, hi = wilson(c["holds"], app)
        results[pid] = {"drawn": asked[pid], "judged": sum(c.values()), "holds": c["holds"], "fails": c["fails"],
                        "not_applicable": c["not_applicable"], "applicable": app,
                        "holds_pct": round(100 * c["holds"] / app) if app else None,
                        "interval_90": [round(100 * lo), round(100 * hi)] if app else None}
        if app < 5:
            flags[pid] = "too few applicable cases to tell"
        elif app < 0.5 * sum(c.values()):
            flags[pid] = "trigger rarely applied (the prediction's trigger does not pick out the right episodes)"
        elif c["holds"] / app < 0.6:
            flags[pid] = "failed (held in fewer than 60% of applicable episodes)"
        elif c["holds"] / app < 0.8:
            flags[pid] = "mixed (held in 60-79%)"
        else:
            flags[pid] = "held (80% or more)"
    testable = [p for p in results if not flags[p].startswith("too few")]
    bad = [p for p in testable if flags[p].startswith(("failed", "trigger"))]
    mixed = [p for p in testable if flags[p].startswith("mixed")]
    if not testable or len(testable) < len(results) / 2:
        overall = "cannot tell: fewer than half the predictions had 5 or more applicable episodes"
    elif len(bad) >= len(testable) / 3:
        overall = "poorly"
    elif bad or len(mixed) >= len(testable) / 3:
        overall = "partly"
    else:
        overall = "well"
    out = {"overall": overall, "predictions": results, "flags": flags,
           "unseen_left": man.get("left_unseen_after_this_round"),
           "coverage": coverage, "prevalence": prevalence,
           "summary": {"predictions": len(results), "testable": len(testable), "failed_or_trigger_off": len(bad),
                       "mixed": len(mixed), "held": sum(1 for p in testable if flags[p].startswith("held"))}}
    with open(os.path.join(args.out, "test-results.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    L = ["# Model test results", "",
         f"**How well the model maps the society: {overall}.** Predictions: {len(results)}; testable (5+ applicable "
         f"episodes): {len(testable)}; held: {out['summary']['held']}; mixed: {len(mixed)}; failed or trigger off: {len(bad)}.",
         "", f"Unseen episodes left for a further round: {man.get('left_unseen_after_this_round', '?')} "
         f"(of {man.get('unseen_pool', '?')} unseen before this round).",
         "", "Episodes were drawn at random from those the model was not built from. A prediction 'holds' or "
         "'fails' only on episodes where its trigger applies; the interval is a 90% range for the share that "
         "holds.", "", "| Prediction | Drawn | Applicable | Holds | Fails | Holds % (90% range) | Flag |",
         "|---|---|---|---|---|---|---|"]
    for pid, r in results.items():
        rng = f"{r['holds_pct']}% ({r['interval_90'][0]}–{r['interval_90'][1]}%)" if r["applicable"] else "–"
        L.append(f"| {pid} | {r['drawn']} | {r['applicable']} | {r['holds']} | {r['fails']} | {rng} | {flags[pid]} |")
    if n_all:
        L += ["", "## How much of the society the model covers (random sample, every prediction judged)", "",
              f"Random episodes judged on every prediction: {n_all}. In {none_applied} "
              f"({coverage['no_institution_applied_pct']}%, 90% range {coverage['no_institution_applied_interval_90'][0]}–"
              f"{coverage['no_institution_applied_interval_90'][1]}%) no institution's prediction applied. "
              f"Readers' coverage verdicts: {dict(cov)}.", "", "How common each institution is (share of random trouble "
              "episodes where at least one of its predictions applied):", ""]
        L += [f"- {i}: {v['episodes']} of {v['of']} ({v['pct']}%, 90% range {v['interval_90'][0]}–{v['interval_90'][1]}%)"
              for i, v in prevalence.items()]
        if pairs:
            L += ["", "Institutions that applied in the same episode most often: " +
                  "; ".join(f"{a} + {b} ({n})" for (a, b), n in pairs.most_common(8)) + "."]
        gaps = [r for r in cov_rows if r["verdict"] != "covered"]
        if gaps:
            L += ["", "**What the model does not explain** (readers' notes; material for refining the model):", ""]
            L += [f"- `{r['episode_id']}` ({r['verdict']}) [{', '.join(r.get('event_ids', []))}]: {r['note']}" for r in gaps]
        under = [pid for pid, r in results.items() if r["applicable"] < 5]
        if under and not any(m == "topup" for m in man.get("batch_mode", {}).values()):
            L += ["", f"Predictions with fewer than 5 applicable episodes: {', '.join(under)}. A targeted top-up draw "
                  "(`draw --mode topup`) can add episodes for them, within the round's share of the unseen pool."]
    L += ["", "## Where predictions failed", ""]
    for pid, rs in fails.items():
        L.append(f"**{pid}**")
        L += [f"- `{r['episode_id']}` [{', '.join(r.get('event_ids', []))}]: {r['note']}" for r in rs]
        L.append("")
    if any(problems.values()):
        L += ["## Problems with the readers' output", ""]
        for name, ps in problems.items():
            L += [f"- {name}: {p}" for p in ps[:15]]
    with open(os.path.join(args.out, "test-results.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    with open(os.path.join(args.out, "rerun.json"), "w") as fh:
        json.dump(rerun, fh)
    print("\n".join(L[:4]))
    if rerun:
        print(f"batches to rerun: {rerun}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draw")
    for a in ("--model", "--episodes", "--segment", "--select", "--out"):
        d.add_argument(a, required=True)
    d.add_argument("--exclude-draws", action="append")
    d.add_argument("--mode", choices=["all", "topup", "targeted"], default="all")
    d.add_argument("--n", type=int, default=15, help="episodes per prediction (topup and targeted modes)")
    d.add_argument("--pool-share", type=float, default=0.5,
                   help="most of the unseen episodes this round may use (default half, so a refinement round "
                        "still has fresh ones; use 1.0 for a final round)")
    d.add_argument("--seed", type=int, default=11)
    d.add_argument("--setting")
    d.add_argument("--max-episode-tokens", type=int, default=12000)
    d.add_argument("--max-batch-tokens", type=int, default=80000)
    t = sub.add_parser("tally")
    t.add_argument("--out", required=True)
    t.add_argument("--segment", required=True)
    t.add_argument("--episodes", required=True)
    args = ap.parse_args()
    draw(args) if args.cmd == "draw" else tally(args)


if __name__ == "__main__":
    main()
