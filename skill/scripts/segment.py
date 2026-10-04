#!/usr/bin/env python3
"""Segment events into conversation units, render what models read, and build
the cross-conversation index. Step 2 of the pipeline. Pure code, no model calls.

1. Units. Each conversation becomes one unit. A conversation that is too long
   to read in one go is split into parts, cutting at the longest pauses in
   activity. Each later part opens with a few events from the end of the
   previous part, marked as context, so a reader never starts mid-exchange.
   Every event belongs to exactly one part for counting.
2. Reading view. The text a model reads for each unit: every event, with its
   event ID, time, actor and kind. Long URLs are shortened (they are kept in
   full in the events file). Nothing is left out: content is shrunk, not
   filtered.
3. Index, for case assembly (finding material in OTHER conversations):
   - actors: where each actor (and, optionally, each claimed alias) is active
   - references: which conversations mention another conversation by name
   - rare terms: distinctive tokens shared by only a few conversations
4. Report: unit sizes and token estimates, for setting the triage budget.

Usage:
  python3 segment.py --events <events.jsonl> --out <run folder>
      [--max-tokens 8000] [--max-events 80] [--overlap 3]
      [--show-field extra.<field> ...]   # shown under each event in the reading view
      [--hint-field extra.<field> ...]   # counted per unit (trouble/identity hints)
      [--alias-field extra.<field> ...]  # extra names for an actor, indexed like actors
      [--max-term-df 25]
"""

import argparse
import collections
import json
import os
import re
import statistics
from datetime import datetime

URL_RE = re.compile(r"(?:https?://|www\.)[^\s\]\)\"'<>|]+", re.I)
URL_PATH_KEEP = 60            # characters of host + path kept from a URL in the reading view
URL_PARAMS_KEEP = 3           # query parameters kept (names, with values cut short)
URL_VALUE_KEEP = 24           # characters kept from each kept parameter value
EVENT_CHAR_CAP = 6000         # per event in the reading view; full text stays in the events file
CONTEXT_CHAR_CAP = 600        # per context event repeated at the start of a later part
FIELD_CHAR_CAP = 400          # per shown extra field
LINK_RUN_KEEP = 6             # runs of pure link lines longer than this are shortened
MARKUP_RE = re.compile(r"[\[\]=*#|`'<>{}]+")
TERM_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-]{4,}")
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-]{5,}")


# ------------------------------------------------------------ helpers

def get_path(e, field):
    v = e
    for part in field.split("."):
        if not isinstance(v, dict):
            return None
        v = v.get(part)
    return v


def shorten_urls(text):
    """Keep what tends to carry meaning in a URL (the site, the path, and the
    names of query parameters with short values) and drop long encoded queries.
    The full URL stays in the events file and in the index."""
    def short(m):
        u = re.sub(r"^https?://", "", m.group(0), flags=re.I)
        base, _, query = u.partition("?")
        base = base if len(base) <= URL_PATH_KEEP else base[:URL_PATH_KEEP] + "…"
        if not query:
            return f"<url {base}>"
        params = [p for p in re.split(r"[&;]", query) if p][:URL_PARAMS_KEEP]
        kept = []
        for p in params:
            name, eq, val = p.partition("=")
            val = val if len(val) <= URL_VALUE_KEEP else val[:URL_VALUE_KEEP] + "…"
            kept.append(name[:URL_VALUE_KEEP] + eq + val)
        more = "&…" if len([p for p in re.split(r"[&;]", query) if p]) > URL_PARAMS_KEEP else ""
        return f"<url {base}?{'&'.join(kept)}{more}>"
    return URL_RE.sub(short, text)


def is_link_line(line):
    """A line that is a link and almost nothing else (2 words or fewer besides it)."""
    return bool(URL_RE.search(line)) and len(MARKUP_RE.sub(" ", URL_RE.sub(" ", line)).split()) <= 2


def link_target(line):
    u = re.sub(r"^https?://", "", URL_RE.search(line).group(0), flags=re.I)
    return "/".join(u.split("?")[0].split("/")[:3]).lower()


def collapse_link_runs(text):
    """Shorten long runs of pure link lines. Every line with words in it is
    kept, and so is at least one line for each distinct link target (site plus
    the first two path parts), plus the first three and the last line of the
    run. The rest is replaced by a count. Returns (text, lines hidden)."""
    lines = text.split("\n")
    out, hidden_total, i = [], 0, 0
    while i < len(lines):
        if not is_link_line(lines[i]):
            out.append(lines[i])
            i += 1
            continue
        j = i
        while j < len(lines) and is_link_line(lines[j]):
            j += 1
        run = lines[i:j]
        if len(run) <= LINK_RUN_KEEP:
            out += run
        else:
            keep, seen = {0, 1, 2, len(run) - 1}, set()
            for k, line in enumerate(run):
                t = link_target(line)
                if t not in seen:
                    seen.add(t)
                    keep.add(k)
            out += [line for k, line in enumerate(run) if k in keep]
            hidden = len(run) - len(keep)
            if hidden:
                out.append(f"[… {hidden} more link lines to the same targets; full text in the events file]")
                hidden_total += hidden
        i = j
    return "\n".join(out), hidden_total


def est_tokens(text):
    return len(text) // 4 + 1


def parse_ts(ts):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return None


def fmt_value(v):
    if isinstance(v, list):
        s = "; ".join(str(x) for x in v)
    else:
        s = str(v)
    s = shorten_urls(s.replace("\n", " ⏎ "))
    return s if len(s) <= FIELD_CHAR_CAP else s[:FIELD_CHAR_CAP] + "…"


def render_event(e, show_fields, context=False):
    head = (f"[{e['event_id']}] {e.get('timestamp') or 'no time'} · "
            f"{e.get('actor') or '(no actor)'} · {e.get('kind')}")
    if context:
        head = "(context from previous part) " + head
    collapsed, hidden_links = collapse_link_runs(e.get("content") or "")
    body = shorten_urls(collapsed)
    cut = 0
    cap = CONTEXT_CHAR_CAP if context else EVENT_CHAR_CAP
    if len(body) > cap:
        cut = len(body) - cap
        where = "in the previous part" if context else "in the events file"
        body = body[:cap] + f"\n[… {cut} more characters; full text {where}]"
    if context:
        cut, hidden_links = 0, 0  # context excerpts are not counted
    lines = [head, body]
    for f in show_fields:
        v = get_path(e, f)
        if v not in (None, "", [], {}):
            lines.append(f"  ↳ {f.split('.')[-1]}: {fmt_value(v)}")
    return "\n".join(lines), cut, hidden_links


# ------------------------------------------------------------ splitting

def split_conversation(evs, rendered_tokens, max_tokens, max_events):
    """Return a list of (start, end) index ranges. Cuts at the longest pause
    in the second half of each window."""
    total = sum(rendered_tokens)
    if total <= max_tokens and len(evs) <= max_events:
        return [(0, len(evs))]
    ranges = []
    start = 0
    n = len(evs)
    while start < n:
        tok, end = 0, start
        while end < n and (end == start or (tok + rendered_tokens[end] <= max_tokens and end - start < max_events)):
            tok += rendered_tokens[end]
            end += 1
        if end >= n:
            ranges.append((start, n))
            break
        # look for the longest pause in the second half of the window
        lo = start + max(1, (end - start) // 2)
        best, best_gap = end, -1.0
        for i in range(lo, end):
            a, b = parse_ts(evs[i - 1].get("timestamp")), parse_ts(evs[i].get("timestamp"))
            gap = (b - a) if (a is not None and b is not None) else 0.0
            if gap > best_gap:
                best, best_gap = i, gap
        ranges.append((start, best))
        start = best
    return ranges


# ------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--events", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-tokens", type=int, default=8000, help="split units above this (estimated tokens)")
    ap.add_argument("--max-events", type=int, default=80, help="split units with more events than this")
    ap.add_argument("--overlap", type=int, default=3, help="context events repeated at the start of a later part")
    ap.add_argument("--show-field", action="append", default=[])
    ap.add_argument("--hint-field", action="append", default=[])
    ap.add_argument("--alias-field", action="append", default=[])
    ap.add_argument("--max-term-df", type=int, default=25,
                    help="a term counts as rare if it appears in at most this many conversations")
    args = ap.parse_args()

    convs = collections.OrderedDict()
    with open(args.events, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                e = json.loads(line)
                convs.setdefault(e["conversation_id"], []).append(e)
    for evs in convs.values():
        evs.sort(key=lambda e: e["order"])

    os.makedirs(args.out, exist_ok=True)
    units_f = open(os.path.join(args.out, "units.jsonl"), "w", encoding="utf-8")
    views_f = open(os.path.join(args.out, "views.jsonl"), "w", encoding="utf-8")

    actor_idx = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, None, None]))
    alias_idx = collections.defaultdict(lambda: collections.defaultdict(int))
    term_convs = collections.defaultdict(set)
    term_first = {}
    unit_rows = []
    truncated_events = 0
    link_lines_hidden = 0
    events_with_hidden_links = 0
    event_to_unit = {}

    for cid, evs in convs.items():
        rendered, toks = [], []
        for e in evs:
            text, cut, hidden = render_event(e, args.show_field)
            truncated_events += 1 if cut else 0
            link_lines_hidden += hidden
            events_with_hidden_links += 1 if hidden else 0
            rendered.append(text)
            toks.append(est_tokens(text))
        ranges = split_conversation(evs, toks, args.max_tokens, args.max_events)
        for k, (a, b) in enumerate(ranges):
            uid = cid if len(ranges) == 1 else f"{cid}#part{k + 1}of{len(ranges)}"
            part = evs[a:b]
            ctx = evs[max(0, a - args.overlap):a] if k > 0 else []
            header = [f"# Conversation unit {uid}",
                      f"Source conversation: {cid}" + (f" (part {k + 1} of {len(ranges)})" if len(ranges) > 1 else ""),
                      f"{len(part)} events, {part[0].get('timestamp')} to {part[-1].get('timestamp')}", ""]
            body = [render_event(e, args.show_field, context=True)[0] for e in ctx] + rendered[a:b]
            text = "\n".join(header) + "\n\n".join(body) + "\n"
            views_f.write(json.dumps({"unit_id": uid, "text": text}, ensure_ascii=False) + "\n")
            actors = collections.Counter(e.get("actor") for e in part if e.get("actor"))
            row = {
                "unit_id": uid,
                "conversation_id": cid,
                "part": k + 1, "parts": len(ranges),
                "event_ids": [e["event_id"] for e in part],
                "context_event_ids": [e["event_id"] for e in ctx],
                "start": part[0].get("timestamp"), "end": part[-1].get("timestamp"),
                "n_events": len(part),
                "n_messages": sum(1 for e in part if e.get("kind") == "message"),
                "n_actors": len(actors),
                "actors": [a for a, _ in actors.most_common(30)],
                "est_tokens": est_tokens(text),
                "hints": {f: sum(1 for e in part if get_path(e, f) not in (None, "", [], {}))
                          for f in args.hint_field},
            }
            units_f.write(json.dumps(row, ensure_ascii=False) + "\n")
            unit_rows.append(row)
            for e in part:
                event_to_unit[e["event_id"]] = uid
                if e.get("actor"):
                    slot = actor_idx[e["actor"]][uid]
                    slot[0] += 1
                    slot[1] = slot[1] or e["event_id"]
                    slot[2] = e["event_id"]
                for f in args.alias_field:
                    v = get_path(e, f)
                    for name in (v if isinstance(v, list) else [v] if v else []):
                        alias_idx[str(name)][uid] += 1
        # rare terms are counted per source conversation, on full text (URLs included:
        # a shared key inside a link is exactly the kind of thread we want to follow)
        seen = set()
        for e in evs:
            if e.get("kind") != "message":
                continue
            for t in set(m.lower() for m in TERM_RE.findall(e.get("content") or "")):
                if t in seen:
                    continue
                seen.add(t)
                term_convs[t].add(cid)
                term_first.setdefault((t, cid), e["event_id"])
    units_f.close()
    views_f.close()

    # references: a conversation's text names another conversation
    name_to_conv = {}
    for cid in convs:
        for name in {cid, re.split(r"[/~:#]", cid)[-1]}:
            if len(name) >= 6:
                name_to_conv.setdefault(name.lower(), set()).add(cid)
    # a name that is also a common word across the dataset (in more conversations
    # than a rare term may be) can't tell us which conversation is meant
    for name in [n for n in name_to_conv if len(term_convs.get(n, ())) > args.max_term_df]:
        del name_to_conv[name]
    references = collections.defaultdict(dict)   # cid -> {referenced cid: first event id}
    for cid, evs in convs.items():
        for e in evs:
            for tok in set(m.lower() for m in NAME_RE.findall(e.get("content") or "")):
                for target in name_to_conv.get(tok, ()):
                    if target != cid and target not in references[cid]:
                        references[cid][target] = e["event_id"]

    rare = {t: sorted(cs) for t, cs in term_convs.items() if 2 <= len(cs) <= args.max_term_df}
    index = {
        "built_from": os.path.abspath(args.events),
        "notes": {
            "actors": "actor -> unit_id -> [events, first_event_id, last_event_id]",
            "aliases": "claimed name (from --alias-field) -> unit_id -> events",
            "references": "conversation_id -> {conversation it names: first event_id that names it}",
            "rare_terms": f"term -> [[conversation_id, first event_id]], terms in 2..{args.max_term_df} conversations",
            "event_to_unit": "event_id -> unit_id",
        },
        "actors": {a: {u: v for u, v in d.items()} for a, d in actor_idx.items()},
        "aliases": {a: dict(d) for a, d in alias_idx.items()},
        "references": references,
        "rare_terms": {t: [[c, term_first[(t, c)]] for c in cs] for t, cs in rare.items()},
        "event_to_unit": event_to_unit,
    }
    with open(os.path.join(args.out, "index.json"), "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False)

    write_report(args, convs, unit_rows, truncated_events, references, rare, index,
                 link_lines_hidden, events_with_hidden_links)
    print(f"wrote {len(unit_rows)} units from {len(convs)} conversations to {args.out}")


def write_report(args, convs, units, truncated, references, rare, index,
                 link_lines_hidden=0, events_with_hidden_links=0):
    split = [c for c in convs if any(u["conversation_id"] == c and u["parts"] > 1 for u in units)]
    toks = [u["est_tokens"] for u in units]
    total = sum(toks)
    with_msg = [u for u in units if u["n_messages"]]
    L = ["# Segmentation report", "",
         f"Events: `{args.events}`. Settings: split above {args.max_tokens} estimated tokens or "
         f"{args.max_events} events; {args.overlap} context events at the start of later parts. "
         f"Token estimates are characters ÷ 4 of the reading view (URLs shortened).", "",
         "## Units", "",
         f"- Conversations: {len(convs)}",
         f"- Units: {len(units)} ({len(split)} conversations split into parts)",
         f"- Units with at least one message: {len(with_msg)}",
         f"- Unit size (estimated tokens): median {int(statistics.median(toks))}, "
         f"largest {max(toks)}, total {total:,}",
         f"- Total for units with messages: {sum(u['est_tokens'] for u in with_msg):,} tokens",
         f"- Events shortened in the reading view (over {EVENT_CHAR_CAP} characters after URL shortening): {truncated}",
         f"- Link lines hidden from long runs of pure links: {link_lines_hidden:,} in {events_with_hidden_links:,} events "
         f"(every distinct link target and every line with words kept; counts shown in place)",
         "", "### Conversations split into parts", "",
         "| Conversation | Events | Parts |", "|---|---|---|"]
    for c in sorted(split, key=lambda c: -len(convs[c]))[:30]:
        L.append(f"| `{c}` | {len(convs[c])} | {sum(1 for u in units if u['conversation_id'] == c)} |")
    L += ["", "### Largest units", "", "| Unit | Events | Est. tokens |", "|---|---|---|"]
    for u in sorted(units, key=lambda u: -u["est_tokens"])[:10]:
        L.append(f"| `{u['unit_id']}` | {u['n_events']} | {u['est_tokens']:,} |")
    if args.hint_field:
        L += ["", "### Hints per unit", ""]
        for f in args.hint_field:
            n_units = sum(1 for u in units if u["hints"].get(f))
            L.append(f"- `{f}`: present in {n_units} units, {sum(u['hints'].get(f, 0) for u in units)} events")
    L += ["", "## Index (for case assembly)", "",
          f"- Actors indexed: {len(index['actors'])}",
          f"- Aliases indexed: {len(index['aliases'])}" + (f" (from {', '.join(args.alias_field)})" if args.alias_field else ""),
          f"- Conversations that name another conversation: {len(references)} "
          f"({sum(len(v) for v in references.values())} references)",
          f"- Rare terms (in 2 to {args.max_term_df} conversations): {len(rare):,}"]
    with open(os.path.join(args.out, "segment-report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
