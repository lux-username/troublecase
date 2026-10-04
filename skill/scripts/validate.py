#!/usr/bin/env python3
"""Validate converted events. Step 5 of the universal converter.

Pure code, no model calls. Three parts:

1. Format: every line is an event in the target shape (codebook/event-format.md).
   Core fields present with the right types, IDs unique, `order` runs 0..n-1
   inside each conversation, replies point at real events, and every event
   says which raw rows it came from (extra.source_ref).
2. Coverage: the adapter's coverage.json accounts for every source row
   (rows = converted + dropped), and its row counts match the raw files,
   which this script counts again independently.
3. Side by side: a random sample of conversations, each event printed next
   to the raw rows it came from, for the model (and a human) to compare.

Usage:
  python3 validate.py --events <events.jsonl> --raw <dataset folder>
                      --coverage <coverage.json> --out <run folder>
                      [--conversations 6] [--events-per-conversation 8]

  --noise-flag FIELD=VALUE (or FIELD>=N, FIELD<=N), repeatable: sample the
  events behind each noise flag, e.g. --noise-flag extra.subkind=test or
  --noise-flag 'extra.url_share>=0.5'. Noise flags describe, they never filter;
  this sample is how we check what a flag would hide (see convert/SKILL.md).
  --hint-field FIELD, repeatable: a trouble or identity hint the adapter wrote
  (named in the dataset card). The noise check reports how much of each hint
  falls under each noise flag.

Writes <out>/validation.json, <out>/validation.md, <out>/side-by-side.md and,
with --noise-flag, <out>/noise-sample.md.
Exit code 1 if any hard check fails.
"""

import argparse
import collections
import csv
import gzip
import io
import json
import os
import random
import re
import statistics
import sys
import zipfile
from datetime import datetime

SEED = 1234
CORE = {
    "event_id": (str,),
    "dataset": (str,),
    "conversation_id": (str,),
    "actor": (str, type(None)),
    "timestamp": (str, type(None)),
    "order": (int,),
    "kind": (str,),
    "content": (str,),
    "in_reply_to": (str, type(None)),
}
KINDS = {"message", "action"}
MAX_EXAMPLES = 5          # failing event IDs listed per check
RAW_TRUNC = 1500          # chars of each raw row shown side by side
CONTENT_TRUNC = 1500


# ------------------------------------------------------------ raw access

def open_raw(raw_root, relpath):
    """Open a raw file by its path relative to the dataset folder.
    'archive.zip!/inner.jsonl' opens a zip member."""
    if "!/" in relpath:
        zpath, member = relpath.split("!/", 1)
        zf = zipfile.ZipFile(os.path.join(raw_root, zpath))
        return zf.open(member)
    path = os.path.join(raw_root, relpath)
    if relpath.lower().endswith(".gz"):
        return gzip.open(path, "rb")
    return open(path, "rb")


def raw_kind(relpath):
    rp = relpath.lower()
    if rp.endswith(".gz"):
        rp = rp[:-3]
    ext = os.path.splitext(rp)[1]
    return {".jsonl": "lines", ".ndjson": "lines", ".csv": "csv", ".tsv": "csv",
            ".json": "json"}.get(ext, "lines")


def count_raw_rows(raw_root, relpath):
    """Count rows the same way source_ref numbers them."""
    k = raw_kind(relpath)
    with open_raw(raw_root, relpath) as fh:
        if k == "lines":
            return sum(1 for line in fh if line.strip())
        if k == "csv":
            text = io.TextIOWrapper(fh, encoding="utf-8", errors="replace", newline="")
            csv.field_size_limit(sys.maxsize)
            return max(0, sum(1 for _ in csv.reader(text)) - 1)
        data = json.load(fh)
        return len(data) if isinstance(data, list) else None


def fetch_raw_rows(raw_root, relpath, numbers):
    """Return {number: raw text} for the requested 1-based line numbers
    (JSONL counts physical lines; CSV counts data rows; JSON counts array index)."""
    want = set(numbers)
    out = {}
    k = raw_kind(relpath)
    with open_raw(raw_root, relpath) as fh:
        if k == "lines":
            for i, line in enumerate(fh, 1):
                if i in want:
                    out[i] = line.decode("utf-8", errors="replace").rstrip("\n")
                    if len(out) == len(want):
                        break
        elif k == "csv":
            text = io.TextIOWrapper(fh, encoding="utf-8", errors="replace", newline="")
            csv.field_size_limit(sys.maxsize)
            reader = csv.reader(text)
            header = next(reader, [])
            for i, row in enumerate(reader, 1):
                if i in want:
                    out[i] = json.dumps(dict(zip(header, row)), ensure_ascii=False)
        else:
            data = json.load(fh)
            for i in want:
                if isinstance(data, list) and 0 <= i < len(data):
                    out[i] = json.dumps(data[i], ensure_ascii=False)
    return out


def parse_ref(ref):
    path, _, num = ref.rpartition(":")
    return path, int(num)


# ------------------------------------------------------------ checks

class Checks:
    def __init__(self):
        self.results = []   # (name, passed, detail, examples)

    def add(self, name, failures, total, detail="", hard=True):
        self.results.append({
            "check": name, "hard": hard,
            "passed": len(failures) == 0,
            "failures": len(failures), "checked": total,
            "detail": detail, "examples": failures[:MAX_EXAMPLES],
        })

    @property
    def hard_failed(self):
        return [r for r in self.results if r["hard"] and not r["passed"]]


def is_iso(ts):
    try:
        datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def check_format(events, bad_lines, raw_root, ck):
    n = len(events)
    ck.add("every line is valid JSON", bad_lines, n + len(bad_lines))

    missing, wrongtype = [], []
    for e in events:
        for f, types in CORE.items():
            if f not in e:
                missing.append(f"{e.get('event_id', '?')}: no {f}")
            elif not isinstance(e[f], types) or (types == (int,) and isinstance(e[f], bool)):
                wrongtype.append(f"{e.get('event_id', '?')}: {f} is {type(e[f]).__name__}")
    ck.add("core fields present", missing, n)
    ck.add("core fields have the right types", wrongtype, n)

    ids = collections.Counter(e.get("event_id") for e in events)
    ck.add("event_id unique", [f"{k} ×{c}" for k, c in ids.items() if c > 1], n)

    ds = collections.Counter(e.get("dataset") for e in events)
    ck.add("one dataset name", [] if len(ds) == 1 else [f"{k} ×{c}" for k, c in ds.items()], n)

    ck.add("kind is message or action",
           [f"{e.get('event_id')}: {e.get('kind')}" for e in events if e.get("kind") not in KINDS], n)
    ck.add("messages have content",
           [e.get("event_id") for e in events if e.get("kind") == "message" and not (e.get("content") or "").strip()], n)
    ck.add("actions have a description",
           [e.get("event_id") for e in events if e.get("kind") == "action" and not (e.get("content") or "").strip()],
           n, hard=False)
    ck.add("timestamps are ISO 8601",
           [f"{e.get('event_id')}: {e.get('timestamp')}" for e in events
            if isinstance(e.get("timestamp"), str) and not is_iso(e["timestamp"])], n)

    # order: 0..n-1 inside each conversation, and the file is sorted that way
    convs = collections.defaultdict(list)
    for e in events:
        convs[e.get("conversation_id")].append(e.get("order"))
    bad_order = [c for c, orders in convs.items() if sorted(orders) != list(range(len(orders)))]
    ck.add("order runs 0..n-1 inside each conversation", bad_order, len(convs))
    unsorted = []
    seen_done = set()
    prev = None
    for e in events:
        c = e.get("conversation_id")
        if prev is not None and c != prev[0]:
            seen_done.add(prev[0])
            if c in seen_done:
                unsorted.append(f"{c} appears in two places")
        elif prev is not None and isinstance(e.get("order"), int) and isinstance(prev[1], int) and e["order"] < prev[1]:
            unsorted.append(f"{e.get('event_id')} out of order")
        prev = (c, e.get("order"))
    ck.add("file sorted by conversation, then order", unsorted, n, hard=False)

    # timestamps should not go backwards as order increases (soft)
    back = []
    byconv = collections.defaultdict(list)
    for e in events:
        byconv[e.get("conversation_id")].append(e)
    for c, evs in byconv.items():
        evs = sorted(evs, key=lambda x: x.get("order") if isinstance(x.get("order"), int) else 0)
        ts = [x.get("timestamp") for x in evs if x.get("timestamp")]
        if any(b < a for a, b in zip(ts, ts[1:])):
            back.append(c)
    ck.add("timestamps never go backwards within a conversation", back, len(byconv), hard=False)

    idset = set(ids)
    ck.add("in_reply_to points to an existing event",
           [f"{e.get('event_id')} -> {e.get('in_reply_to')}" for e in events
            if e.get("in_reply_to") and e["in_reply_to"] not in idset], n)

    noref, badref = [], []
    files = set()
    for e in events:
        refs = (e.get("extra") or {}).get("source_ref") if isinstance(e.get("extra"), dict) else None
        if not refs or not isinstance(refs, list):
            noref.append(e.get("event_id"))
            continue
        for r in refs:
            try:
                p, _ = parse_ref(r)
                files.add(p)
            except (ValueError, AttributeError):
                badref.append(f"{e.get('event_id')}: {r}")
    ck.add("every event has extra.source_ref", noref, n)
    ck.add("source_ref is 'file:number'", badref, n)
    missing_files = [p for p in files if not os.path.exists(os.path.join(raw_root, p.split("!/")[0]))]
    ck.add("source_ref files exist in the raw folder", missing_files, len(files))
    return byconv


def check_coverage(events, coverage, raw_root, ck):
    rows = []
    srcs = coverage.get("sources", {})
    arith, recount = [], []
    for path, s in srcs.items():
        dropped = sum((s.get("dropped") or {}).values())
        if s.get("rows") != s.get("converted", 0) + dropped:
            arith.append(f"{path}: rows {s.get('rows')} != converted {s.get('converted')} + dropped {dropped}")
        try:
            counted = count_raw_rows(raw_root, path)
        except Exception as ex:
            counted = f"could not count ({type(ex).__name__})"
        if counted is not None and counted != s.get("rows"):
            recount.append(f"{path}: coverage says {s.get('rows')}, raw file has {counted}")
        rows.append({"source": path, "rows": s.get("rows"), "recounted": counted,
                     "converted": s.get("converted"), "dropped": s.get("dropped") or {}})
    ck.add("coverage adds up (rows = converted + dropped)", arith, len(srcs))
    ck.add("coverage row counts match the raw files (recounted)", recount, len(srcs))

    # every converted row should be referenced by at least one event
    refd = collections.defaultdict(set)
    for e in events:
        for r in (e.get("extra") or {}).get("source_ref") or []:
            try:
                p, num = parse_ref(r)
                refd[p].add(num)
            except (ValueError, AttributeError):
                pass
    mism = []
    for path, s in srcs.items():
        if len(refd.get(path, ())) != s.get("converted"):
            mism.append(f"{path}: coverage says {s.get('converted')} converted, events cite {len(refd.get(path, ()))} distinct rows")
    ck.add("converted rows match the rows the events cite", mism, len(srcs))
    w = coverage.get("events_written")
    ck.add("events_written matches the events file",
           [] if w == len(events) else [f"coverage says {w}, file has {len(events)}"], 1)
    return rows


# ------------------------------------------------------------ stats and samples

def stats(events, byconv):
    sizes = [len(v) for v in byconv.values()]
    kinds = collections.Counter(e.get("kind") for e in events)
    lens = [len(e.get("content") or "") for e in events if e.get("kind") == "message"]
    extra_fill = collections.Counter()
    for e in events:
        for k, v in (e.get("extra") or {}).items():
            if v not in (None, "", [], {}):
                extra_fill[k] += 1
    n = len(events)
    return {
        "events": n,
        "conversations": len(byconv),
        "kinds": dict(kinds),
        "distinct_actors": len({e.get("actor") for e in events if e.get("actor")}),
        "actor_null_pct": round(100 * sum(1 for e in events if not e.get("actor")) / n, 1) if n else 0,
        "timestamp_null_pct": round(100 * sum(1 for e in events if not e.get("timestamp")) / n, 1) if n else 0,
        "in_reply_to_filled": sum(1 for e in events if e.get("in_reply_to")),
        "conversation_size": {"min": min(sizes), "median": statistics.median(sizes), "max": max(sizes),
                              "single_event": sum(1 for s in sizes if s == 1),
                              "over_60": sum(1 for s in sizes if s > 60)} if sizes else {},
        "message_content_chars": {"min": min(lens), "median": statistics.median(lens), "max": max(lens),
                                  "total": sum(lens)} if lens else {},
        "extra_fill_pct": {k: round(100 * c / n, 1) for k, c in extra_fill.most_common()},
    }


def pick_conversations(byconv, k, rng):
    """A mix: half picked by event (favours busy conversations), half by
    conversation (favours the typical small one)."""
    convs = sorted(byconv)
    multi = [c for c in convs if len(byconv[c]) > 1]
    picks = []
    weighted = [c for c in multi for _ in range(min(len(byconv[c]), 50))]
    while weighted and len(picks) < (k + 1) // 2:
        c = rng.choice(weighted)
        if c not in picks:
            picks.append(c)
        weighted = [x for x in weighted if x != c]
    rest = [c for c in convs if c not in picks]
    rng.shuffle(rest)
    picks += rest[:k - len(picks)]
    return picks


def side_by_side(byconv, picks, raw_root, per_conv, rng):
    L = ["# Side-by-side samples", "",
         "Each converted event is shown next to the raw rows it cites in `extra.source_ref`. "
         "Read these and judge: is `content` faithful to the source? Is anything lost, duplicated "
         "or invented? Are `actor`, `timestamp`, `order` and `kind` right? Record the verdict in "
         "`conversion-report.md`.", ""]
    for c in picks:
        evs = sorted(byconv[c], key=lambda x: x.get("order") if isinstance(x.get("order"), int) else 0)
        n = len(evs)
        if n > per_conv:  # show a window, not just the start
            start = rng.randrange(0, n - per_conv + 1)
            evs = evs[start:start + per_conv]
            L.append(f"## Conversation `{c}` ({n} events; showing order {start}–{start + per_conv - 1})")
        else:
            L.append(f"## Conversation `{c}` ({n} events)")
        L.append("")
        need = collections.defaultdict(set)
        for e in evs:
            for r in (e.get("extra") or {}).get("source_ref") or []:
                p, num = parse_ref(r)
                need[p].add(num)
        raw = {}
        for p, nums in need.items():
            try:
                for num, text in fetch_raw_rows(raw_root, p, nums).items():
                    raw[(p, num)] = text
            except Exception as ex:
                raw[(p, -1)] = f"could not read {p}: {ex}"
        for e in evs:
            extra = dict(e.get("extra") or {})
            refs = extra.pop("source_ref", [])
            L.append(f"### `{e.get('event_id')}` · order {e.get('order')} · {e.get('kind')} · "
                     f"actor `{e.get('actor')}` · {e.get('timestamp')}")
            L.append("")
            L.append("**Converted content:**")
            L.append("```")
            content = e.get("content") or ""
            L.append(content if len(content) <= CONTENT_TRUNC else content[:CONTENT_TRUNC] + f"\n… [+{len(content) - CONTENT_TRUNC} chars]")
            L.append("```")
            L.append("**extra:** `" + json.dumps(trunc_obj(extra), ensure_ascii=False).replace("`", "'") + "`")
            L.append("")
            for r in refs:
                p, num = parse_ref(r)
                text = raw.get((p, num), "(raw row not found)")
                L.append(f"**Raw `{r}`:**")
                L.append("```json")
                L.append(text if len(text) <= RAW_TRUNC else text[:RAW_TRUNC] + f" … [+{len(text) - RAW_TRUNC} chars]")
                L.append("```")
            L.append("")
    return "\n".join(L) + "\n"


def parse_flag(spec):
    for op in (">=", "<=", "="):
        if op in spec:
            field, value = spec.split(op, 1)
            return field.strip(), op, value.strip()
    raise SystemExit(f"bad --noise-flag {spec!r}: use FIELD=VALUE, FIELD>=N or FIELD<=N")


def get_path(e, field):
    v = e
    for part in field.split("."):
        if not isinstance(v, dict):
            return None
        v = v.get(part)
    return v


def matches(e, field, op, value):
    v = get_path(e, field)
    if v is None:
        return False
    if op == "=":
        return str(v) == value
    try:
        return float(v) >= float(value) if op == ">=" else float(v) <= float(value)
    except (TypeError, ValueError):
        return False


URL_TOKEN = re.compile(r"\S*(?:https?://|www\.)\S*", re.I)
MARKUP = re.compile(r"[\[\]=*#|`'<>{}]+")


def sentence_lines(e, repeated):
    """Lines that read like sentences once URLs and markup are removed
    (8+ words) and are not boilerplate repeated across many events."""
    out = []
    for line in (e.get("content") or "").split("\n"):
        if repeated.get(line.strip(), 0) >= 10:
            continue
        if len(MARKUP.sub(" ", URL_TOKEN.sub(" ", line)).split()) >= 8:
            out.append(line)
    return out


def noise_sample(events, specs, per_flag, rng, hint_fields=()):
    """For each noise flag: how many events it covers, how many of those still
    carry signs of social content, and two samples: a random one, and one drawn
    from the events most likely to be social. Rare social content (a rule, a
    confession) is easy to miss in a purely random sample."""
    L = ["# What the noise flags cover", "",
         "Each section is a random sample of the events behind one noise flag, shown in full. "
         "For every event, ask: is there a signal, a rule, a claim, a complaint, a correction, "
         "an overwrite or a convention here? Count the ones that carry social content and record "
         "the count, with event IDs, in `conversion-report.md`. Flags describe; they never filter.", ""]
    counts = {}
    n_messages = sum(1 for e in events if e.get("kind") == "message")
    repeated = collections.Counter()
    for e in events:
        for line in {x.strip() for x in (e.get("content") or "").split("\n") if x.strip()}:
            repeated[line] += 1
    for spec in specs:
        field, op, value = parse_flag(spec)
        hit = [e for e in events if matches(e, field, op, value)]
        with_sentences = [e for e in hit if sentence_lines(e, repeated)]
        with_hints = {f: [e for e in hit if get_path(e, f)] for f in hint_fields}
        hint_totals = {f: sum(1 for e in events if get_path(e, f)) for f in hint_fields}
        counts[spec] = {"events": len(hit), "with_sentences": len(with_sentences),
                        **{f"with_{f.split('.')[-1]}": len(v) for f, v in with_hints.items()}}
        L.append(f"## `{spec}`: {len(hit)} events "
                 f"({round(100 * len(hit) / len(events), 1) if events else 0}% of all events; "
                 f"{sum(1 for e in hit if e.get('kind') == 'message')} of {n_messages} messages)")
        L.append("")
        L.append("Signs of social content inside this flag (counted by code):")
        L.append("")
        L.append(f"- {len(with_sentences)} events contain sentence-like lines (8+ words outside URLs and markup, not boilerplate)")
        for f, v in with_hints.items():
            if hint_totals[f]:
                L.append(f"- {len(v)} events carry `{f}`: {round(100 * len(v) / hint_totals[f])}% of all events with that hint")
        L.append("")
        L.append(f"### Sample A: events with sentence-like lines ({min(per_flag, len(with_sentences))} of {len(with_sentences)}, only the sentence lines shown)")
        L.append("")
        for e in rng.sample(with_sentences, min(per_flag, len(with_sentences))):
            L.append(f"- `{e.get('event_id')}` (actor `{e.get('actor')}`): "
                     + " ⏎ ".join(x.strip()[:300] for x in sentence_lines(e, repeated)[:3]).replace("`", "'"))
        L.append("")
        L.append(f"### Sample B: random events under this flag ({min(per_flag, len(hit))}, in full)")
        L.append("")
        for e in rng.sample(hit, min(per_flag, len(hit))):
            hints = {f: get_path(e, f) for f in hint_fields if get_path(e, f)}
            L.append(f"#### `{e.get('event_id')}` · {e.get('kind')} · actor `{e.get('actor')}` · "
                     f"conversation `{e.get('conversation_id')}`")
            if hints:
                L.append("hints: `" + json.dumps(trunc_obj(hints), ensure_ascii=False).replace("`", "'") + "`")
            L.append("```")
            c = e.get("content") or ""
            L.append(c if len(c) <= 3000 else c[:3000] + f"\n… [+{len(c) - 3000} chars]")
            L.append("```")
            L.append("")
    return "\n".join(L) + "\n", counts


def trunc_obj(v, n=200):
    if isinstance(v, str):
        return v if len(v) <= n else v[:n] + "…"
    if isinstance(v, list):
        return [trunc_obj(x, n) for x in v[:10]] + (["…"] if len(v) > 10 else [])
    if isinstance(v, dict):
        return {k: trunc_obj(x, n) for k, x in v.items()}
    return v


# ------------------------------------------------------------ output

def write_md(path, ck, cov_rows, st, picks):
    L = ["# Validation", "",
         f"Generated by `validate.py` (code only). Hard failures: **{len(ck.hard_failed)}**.", "",
         "## Checks", "", "| Check | Result | Checked | Failing examples |", "|---|---|---|---|"]
    for r in ck.results:
        res = "pass" if r["passed"] else ("**FAIL**" if r["hard"] else "warn")
        if not r["passed"]:
            res += f" ({r['failures']})"
        ex = "; ".join(f"`{x}`" for x in r["examples"])
        L.append(f"| {r['check']} | {res} | {r['checked']} | {ex} |")
    L += ["", "## Coverage", "", "| Source | Rows (adapter) | Rows (recounted) | Converted | Dropped |", "|---|---|---|---|---|"]
    for r in cov_rows:
        d = "; ".join(f"{k}: {v}" for k, v in r["dropped"].items()) or "none"
        L.append(f"| `{r['source']}` | {r['rows']} | {r['recounted']} | {r['converted']} | {d} |")
    L += ["", "## Output statistics", "", "```json", json.dumps(st, ensure_ascii=False, indent=1), "```", "",
          "## Conversations sampled for side-by-side review", ""]
    L += [f"- `{c}`" for c in picks]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--events", required=True)
    ap.add_argument("--raw", required=True, help="the raw dataset folder that source_ref paths are relative to")
    ap.add_argument("--coverage", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--conversations", type=int, default=6)
    ap.add_argument("--events-per-conversation", type=int, default=8)
    ap.add_argument("--noise-flag", action="append", default=[],
                    help="FIELD=VALUE, FIELD>=N or FIELD<=N; repeatable")
    ap.add_argument("--noise-samples", type=int, default=20, help="events sampled per noise flag")
    ap.add_argument("--hint-field", action="append", default=[],
                    help="a trouble or identity hint field named in the card, e.g. extra.<field>; repeatable")
    args = ap.parse_args()

    events, bad = [], []
    with open(args.events, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as ex:
                bad.append(f"line {i}: {str(ex)[:60]}")
    with open(args.coverage, encoding="utf-8") as fh:
        coverage = json.load(fh)

    ck = Checks()
    byconv = check_format(events, bad, args.raw, ck)
    cov_rows = check_coverage(events, coverage, args.raw, ck)
    st = stats(events, byconv)
    rng = random.Random(SEED)
    picks = pick_conversations(byconv, args.conversations, rng)

    os.makedirs(args.out, exist_ok=True)
    noise_counts = {}
    if args.noise_flag:
        text, noise_counts = noise_sample(events, args.noise_flag, args.noise_samples,
                                         random.Random(SEED), args.hint_field)
        with open(os.path.join(args.out, "noise-sample.md"), "w", encoding="utf-8") as fh:
            fh.write(text)
        st["noise_flags"] = noise_counts
    with open(os.path.join(args.out, "validation.json"), "w", encoding="utf-8") as fh:
        json.dump({"checks": ck.results, "coverage": cov_rows, "stats": st, "sampled": picks},
                  fh, ensure_ascii=False, indent=1, default=str)
    write_md(os.path.join(args.out, "validation.md"), ck, cov_rows, st, picks)
    with open(os.path.join(args.out, "side-by-side.md"), "w", encoding="utf-8") as fh:
        fh.write(side_by_side(byconv, picks, args.raw, args.events_per_conversation, rng))

    for r in ck.results:
        mark = "ok  " if r["passed"] else ("FAIL" if r["hard"] else "warn")
        print(f"{mark} {r['check']}" + ("" if r["passed"] else f"  ({r['failures']}: {r['examples'][:2]})"))
    print(f"wrote {args.out}/validation.md, validation.json, side-by-side.md"
          + (", noise-sample.md" if args.noise_flag else ""))
    sys.exit(1 if ck.hard_failed else 0)


if __name__ == "__main__":
    main()
