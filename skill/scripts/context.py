"""Background block from the approved setting.md, for the top of every batch a
model reads (scan, scan audit, case files, model building, model tests, deep dive).

It takes the setting's one-paragraph summary, the human's corrections, the
actors' vocabulary and everything under "Updates after close reading", and labels them as background: they help a reader make
sense of fragments, but they are not evidence and are never cited.
"""

import re

HEADER = ("## Background: the setting (context, not evidence)\n\n"
          "What this dataset is, from the approved setting description. Use it to make sense of what you read "
          "(who the actors are, what their words mean, who is an outsider). Do not cite it and do not treat it "
          "as a finding: every claim still rests on the events in front of you. If what you read contradicts it, "
          "say so.\n\n")

UPDATE = re.compile(r"^#+\s*updates after close reading", re.I)
KEEP = re.compile(r"^#+\s*(?:\d+[a-z]?\.\s*)?(in one paragraph|human corrections|their vocabulary|vocabulary)\b", re.I)


def _ids_only(inside):
    """True if a bracket holds only ID-like tokens (e.g. [x~12], [a4c14b72, 4fdc57f6])."""
    toks = [t for t in re.split(r"[,;\s]+", inside) if t]
    return bool(toks) and all(len(t) >= 4 and re.search(r"\d", t) and re.fullmatch(r"[\w~:@./-]+", t)
                              for t in toks)


def setting_block(path, max_chars=9000):
    """Return the background block, or '' when no path is given."""
    if not path:
        return ""
    text = open(path, encoding="utf-8").read()
    out, keep, update = [], False, False
    for line in text.splitlines():
        if line.startswith("#") and UPDATE.match(line):
            update = keep = True
            out.append("### Updates after close reading")
            continue
        if update:
            out.append(line)
            continue
        if line.startswith("#"):
            keep = bool(KEEP.match(line))
            if keep:
                out.append("### " + re.sub(r"^#+\s*", "", line))
            continue
        if keep:
            out.append(line)
    body = "\n".join(out).strip() or text.strip()
    # no event IDs in the background: readers must cite only events they can see
    body = re.sub(r"\s*\[([^\[\]]+)\]", lambda m: "" if _ids_only(m.group(1)) else m.group(0), body)
    if len(body) > max_chars:
        body = body[:max_chars].rstrip() + "\n[…cut]"
    return HEADER + body + "\n\n"
