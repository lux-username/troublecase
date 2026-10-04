#!/usr/bin/env python3
"""Check the briefing against the data. Pure code.

  - every quote written as "words" [event_id] appears word for word in that
    event's text (whitespace and URL shortening aside)
  - every event ID in square brackets exists
  - no talk about our own process (case notes, dossiers, reconstruction,
    units, tags...) before the method section
  - every number in the briefing appears in the numbers files (--counts) or the method facts
    (numbers that don't are listed for a human to look at; small numbers
    such as list positions are ignored)

Usage:
  python3 check_brief.py --brief <briefing.md> --events <events.jsonl>
                         --counts <file.json> [--counts <file.json> ...] [--facts <method-facts.md>] [--out <report.md>]
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from segment import shorten_urls  # noqa: E402

# transcript line in a block quote: > **Speaker** (time): words [event_id]
TRANSCRIPT_RE = re.compile(r'^>\s*\*\*[^*]+\*\*(?:\s*\([^)]*\))?\s*:\s*(.+?)\s*\[([^\]\s]+)\]\s*$', re.M)
QUOTE_RE = re.compile(r'[“"]([^"”]{3,600})[”"]\s*\[([^\]\s]+)\]')
ID_RE = re.compile(r'\[([A-Za-z]+[~:][^\]\s]+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\]')  # prefixed IDs or plain UUIDs
NUM_RE = re.compile(r'(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?![\w])')


def norm(s):
    s = s.replace("’", "'").replace("‘", "'").replace("…", "...")
    return re.sub(r"\s+", " ", s).strip()


def numbers_in(obj, out):
    if isinstance(obj, dict):
        for v in obj.values():
            numbers_in(v, out)
    elif isinstance(obj, list):
        for v in obj:
            numbers_in(v, out)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        out.add(float(obj))
    elif isinstance(obj, str):
        for m in NUM_RE.findall(obj):
            out.add(float(m.replace(",", "")))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--brief", required=True)
    ap.add_argument("--events", required=True)
    ap.add_argument("--counts", required=True, action="append",
                    help="a JSON file of allowed numbers; repeat for several (test results, audit, episodes summary)")
    ap.add_argument("--facts")
    ap.add_argument("--out")
    ap.add_argument("--fix-transcripts", action="store_true",
                    help="rewrite each transcript line's speaker and time from the event data "
                         "(the event ID decides who spoke and when) and list the corrections")
    args = ap.parse_args()

    text = open(args.brief, encoding="utf-8").read()
    events, meta = {}, {}
    for line in open(args.events, encoding="utf-8"):
        if line.strip():
            e = json.loads(line)
            events[e["event_id"]] = e.get("content") or ""
            meta[e["event_id"]] = (e.get("actor") or "(no name)", (e.get("timestamp") or "")[:16].replace("T", " "))
    fixes = []
    if args.fix_transcripts:
        line_re = re.compile(r'^(>\s*)\*\*([^*]+)\*\*(?:\s*\(([^)]*)\))?(\s*:\s*.+?\s*\[([^\]\s]+)\]\s*)$', re.M)

        def fix(m):
            eid = m.group(5)
            if eid not in meta:
                return m.group(0)
            actor, when = meta[eid]
            if m.group(2).strip() != actor:
                fixes.append(f"[{eid}] speaker '{m.group(2).strip()}' -> '{actor}'")
            return f"{m.group(1)}**{actor}** ({when} UTC){m.group(4)}"
        text = line_re.sub(fix, text)
        open(args.brief, "w", encoding="utf-8").write(text)

    quotes = QUOTE_RE.findall(text) + [(q.strip().strip('"“”'), i) for q, i in TRANSCRIPT_RE.findall(text)]
    bad_quotes = []
    for q, eid in quotes:
        raw = events.get(eid)
        if raw is None:
            bad_quotes.append((eid, q, "event not found"))
            continue
        nq = norm(q).rstrip(".,;")
        # allow quotes that elide with ... : check each piece
        pieces = [p.strip() for p in re.split(r"\.\.\.|\[…\]", nq) if p.strip()]
        hay = norm(raw) + " || " + norm(shorten_urls(raw))
        if not all(p in hay for p in pieces):
            bad_quotes.append((eid, q, "not word for word"))
    # glossary: "- **term**: meaning [event_id]" between "Glossary" and the next "## " heading
    gloss_bad, gloss_n, gloss_uncited = [], 0, []
    gm = re.search(r"\*\*Glossary[^\n]*\n(.*?)(?=\n## )", text, re.S)
    if gm:
        for line in gm.group(1).splitlines():
            m = re.match(r"\s*-\s*\*\*(.+?)\*\*(.*)$", line)
            if not m:
                continue
            gloss_n += 1
            cited = ID_RE.findall(m.group(2))
            if not cited:
                gloss_uncited.append(m.group(1))
                continue
            tokens = [t for t in re.split(r"[\s,/()….;:'\"“”]+|\.\.\.", m.group(1)) if len(t) >= 2]
            ok = any(any(t.lower() in (events.get(i) or "").lower() for t in tokens) for i in cited)
            if not ok:
                gloss_bad.append(f"{m.group(1)} [{', '.join(cited)}]")
    # process talk: our own working documents and steps named before the method section
    jargon_re = re.compile(r"\b(case notes?|earlier notes?|shorter notes?|dossiers?|reconstruct\w*|rebuil\w*|units?|tags?|tagged|escalat\w*|triage|apply step)\b", re.I)
    method_at = re.search(r"^## .*\b(Method|method)\b", text, re.M)
    pre_method = text[:method_at.start()] if method_at else text
    jargon = []
    for n, line in enumerate(pre_method.splitlines(), 1):
        if line.lstrip().startswith(("*Sources", ">")):
            continue
        for m in jargon_re.finditer(QUOTE_RE.sub(" ", line)):
            jargon.append(f"line {n}: '{m.group(0)}' in: {line.strip()[:100]}")
    ids = set(ID_RE.findall(text))
    missing_ids = sorted(i for i in ids if i not in events)

    known = set()
    for cpath in args.counts:
        with open(cpath, encoding="utf-8") as fh:
            numbers_in(json.load(fh), known)
    if args.facts:
        numbers_in(open(args.facts, encoding="utf-8").read(), known)
    body = TRANSCRIPT_RE.sub(" ", QUOTE_RE.sub(" ", text))  # numbers inside quotes come from the data
    body = ID_RE.sub(" ", body)
    unknown = []
    for m in NUM_RE.findall(body):
        v = float(m.replace(",", ""))
        if v <= 12 or v in known:
            continue
        unknown.append(m)

    L = ["# Briefing check", "",
         f"Quotes with an event ID: {len(quotes)}; not word for word or event missing: {len(bad_quotes)}.",
         f"Event IDs cited: {len(ids)}; not found: {len(missing_ids)}.",
         f"Numbers not found in counts or method facts (check by hand): {len(set(unknown))}.",
         f"Transcript speakers corrected from the data: {len(fixes)}." if args.fix_transcripts else "",
         f"Process words before the method section (check by hand): {len(jargon)}.",
         f"Glossary entries: {gloss_n}; without an event ID: {len(gloss_uncited)}; term not found in its cited event: {len(gloss_bad)}.", ""]
    if gloss_uncited or gloss_bad:
        L += ["## Glossary entries to fix", ""] + [f"- no event ID: {g}" for g in gloss_uncited] + \
             [f"- term not in cited event: {g}" for g in gloss_bad] + [""]
    if jargon:
        L += ["## Process words before the method section", "",
              "The reader never saw our working steps. Rewrite as what happened, or move to the method section.", ""] + \
             [f"- {j}" for j in jargon] + [""]
    if fixes:
        L += ["## Transcript speakers corrected", ""] + [f"- {f}" for f in fixes] + [""]
    if bad_quotes:
        L += ["## Quotes that failed", ""] + [f"- [{e}] {why}: \"{q[:120]}\"" for e, q, why in bad_quotes]
    if missing_ids:
        L += ["", "## Event IDs not found", ""] + [f"- {i}" for i in missing_ids]
    if unknown:
        L += ["", "## Numbers to check", ""] + [f"- {n}" for n in sorted(set(unknown), key=lambda s: float(s.replace(',', '')))]
    report = "\n".join(L) + "\n"
    if args.out:
        open(args.out, "w", encoding="utf-8").write(report)
    print(report)


if __name__ == "__main__":
    main()
