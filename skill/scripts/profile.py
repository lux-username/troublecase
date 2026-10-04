#!/usr/bin/env python3
"""Profile an unknown dataset folder. Step 1 of the universal converter.

Pure code, no model calls. Walks a folder (or a single file), reads every data
file it recognises, and writes a compact profile that a model can read instead
of the raw data:

  - file inventory: path, size, detected type, row count
  - per file: every field (nested fields as dotted paths), how often it is
    filled, its value types, distinct-value counts, string lengths, examples
  - a few random sample records per file (long strings truncated)
  - cross-file hints: likely ID fields, likely timestamps, likely long text,
    and fields that look like join keys between files

Formats: JSONL / NDJSON, JSON (a list of records, or an object holding one),
CSV / TSV, Parquet (needs pyarrow), and zip archives (members are profiled in
place, without extracting to disk). Anything else is listed in the inventory.

Usage:
  python3 profile.py <dataset_folder_or_file> --out <output_folder>
  (Parquet: uv run --with pyarrow python3 profile.py ...)

Writes <out>/profile.md (for the model) and <out>/profile.json (for code).
"""

import argparse
import csv
import io
import json
import os
import random
import re
import statistics
import sys
import zipfile
from datetime import datetime, timezone

SEED = 1234
N_SAMPLES = 3            # random sample records shown per file
N_EXAMPLES = 4           # example values shown per field
MAX_DEPTH = 3            # how deep nested objects are flattened into dotted paths
DISTINCT_CAP = 50_000    # stop counting distinct values past this
MAX_FIELDS_SHOWN = 60    # per file, in profile.md
TOP_VALUES_MAX = 12      # fields with at most this many distinct values get full value counts
TRUNC_EXAMPLE = 100      # chars kept from an example value
TRUNC_SAMPLE = 300       # chars kept from each string in a sample record
JOIN_VALUES_KEPT = 20_000  # distinct values kept per field for join-key checks

DATA_EXT = {
    ".jsonl": "jsonl", ".ndjson": "jsonl", ".json": "json",
    ".csv": "csv", ".tsv": "tsv", ".parquet": "parquet", ".pq": "parquet",
    ".zip": "zip",
}
TEXT_EXT = {".md", ".txt", ".rst", ".yaml", ".yml", ""}

ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?$")


# ---------------------------------------------------------------- field stats

class FieldStats:
    """Running statistics for one field across all rows of one file."""

    def __init__(self):
        self.present = 0          # key exists in the row
        self.filled = 0           # value is not null / "" / [] / {}
        self.types = {}
        self.distinct = set()
        self.distinct_capped = False
        self.lengths = []         # string lengths (all of them; fine at this scale)
        self.list_lengths = []
        self.examples = []
        self.counts = {}          # value -> count, while the field looks categorical
        self.looks_time = 0       # values that parse as ISO dates or epoch numbers
        self.multiline = 0        # strings containing a newline

    def add(self, value):
        self.present += 1
        t = type_name(value)
        self.types[t] = self.types.get(t, 0) + 1
        if value is None or value == "" or value == [] or value == {}:
            return
        self.filled += 1
        if isinstance(value, list):
            self.list_lengths.append(len(value))
        if isinstance(value, str):
            self.lengths.append(len(value))
            if "\n" in value:
                self.multiline += 1
            if ISO_RE.match(value.strip()):
                self.looks_time += 1
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            if 946684800 <= value <= 4102444800 or 946684800000 <= value <= 4102444800000:
                self.looks_time += 1
        if isinstance(value, (str, int, float, bool)):
            key = value if not isinstance(value, str) or len(value) <= 200 else value[:200] + f"…#{hash(value)}"
            if self.counts is not None:
                self.counts[key] = self.counts.get(key, 0) + 1
                if len(self.counts) > TOP_VALUES_MAX:
                    self.counts = None
            if not self.distinct_capped:
                self.distinct.add(key)
                if len(self.distinct) >= DISTINCT_CAP:
                    self.distinct_capped = True
            if len(self.examples) < N_EXAMPLES and value not in self.examples:
                self.examples.append(value)
        elif len(self.examples) < N_EXAMPLES and isinstance(value, list) and value:
            self.examples.append(value[:3])

    def summary(self, n_rows, per_element=False):
        if per_element:  # fields inside lists: rows don't apply, report element counts
            out = {"per_element": True, "elements": self.present, "filled_elements": self.filled,
                   "types": self.types}
        else:
            out = {
                "present_pct": pct(self.present, n_rows),
                "filled_pct": pct(self.filled, n_rows),
                "types": self.types,
            }
        if self.counts:
            out["value_counts"] = dict(sorted(self.counts.items(), key=lambda kv: -kv[1]))
        if self.distinct:
            out["distinct"] = f">={DISTINCT_CAP}" if self.distinct_capped else len(self.distinct)
        if self.lengths:
            out["str_len"] = {"min": min(self.lengths),
                              "median": int(statistics.median(self.lengths)),
                              "max": max(self.lengths)}
            out["multiline_pct"] = pct(self.multiline, self.filled)
        if self.list_lengths:
            out["list_len"] = {"min": min(self.list_lengths),
                               "median": int(statistics.median(self.list_lengths)),
                               "max": max(self.list_lengths)}
        if self.looks_time:
            out["looks_like_time_pct"] = pct(self.looks_time, self.filled)
        out["examples"] = [truncate(e, TRUNC_EXAMPLE) for e in self.examples]
        return out


def type_name(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if isinstance(v, list):
        return "list"
    if isinstance(v, dict):
        return "object"
    return type(v).__name__


def pct(a, b):
    return round(100.0 * a / b, 1) if b else 0.0


def truncate(v, n):
    """Shorten long strings everywhere inside a value, for display."""
    if isinstance(v, str):
        return v if len(v) <= n else v[:n] + f"… [+{len(v) - n} chars]"
    if isinstance(v, list):
        shown = [truncate(x, n) for x in v[:5]]
        if len(v) > 5:
            shown.append(f"… [+{len(v) - 5} items]")
        return shown
    if isinstance(v, dict):
        return {k: truncate(x, n) for k, x in v.items()}
    return v


def flatten(row, prefix="", depth=0):
    """Yield (dotted_path, value) for a record. Nested objects are expanded up
    to MAX_DEPTH; lists are kept whole (their element fields are profiled
    separately under path[] when they hold objects)."""
    if not isinstance(row, dict):
        yield (prefix or "(value)", row)
        return
    for k, v in row.items():
        path = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict) and v and depth < MAX_DEPTH:
            yield from flatten(v, path, depth + 1)
        else:
            yield (path, v)
            if isinstance(v, list) and v and isinstance(v[0], dict) and depth < MAX_DEPTH:
                for item in v[:50]:  # element fields, from the first 50 elements
                    for p, x in flatten(item, path + "[]", depth + 1):
                        yield (p, x)


# ----------------------------------------------------------- record readers

def read_jsonl(fh):
    """Yield (record, error) for each non-blank line."""
    for line in fh:
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="replace")
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line), None
        except json.JSONDecodeError as e:
            yield None, str(e)[:80]


def read_json(fh):
    """A JSON file is records if it is a list, or if it is an object holding a
    list of objects somewhere (the biggest such list wins). Otherwise it is a
    single document and is described by its shape."""
    data = json.load(fh)
    path, records = find_records(data)
    return data, path, records


def find_records(data, path="$"):
    if isinstance(data, list) and data and all(isinstance(x, dict) for x in data[:100]):
        return path, data
    best = (None, None)
    if isinstance(data, dict):
        for k, v in data.items():
            p, r = find_records(v, f"{path}.{k}")
            if r is not None and (best[1] is None or len(r) > len(best[1])):
                best = (p, r)
    return best


def read_csv(fh, delimiter=None):
    text = fh if isinstance(fh, io.TextIOBase) else io.TextIOWrapper(fh, encoding="utf-8", errors="replace", newline="")
    csv.field_size_limit(sys.maxsize)
    if delimiter is None:
        head = text.read(64 * 1024)
        text.seek(0)
        try:
            delimiter = csv.Sniffer().sniff(head, delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
    for row in csv.DictReader(text, delimiter=delimiter):
        yield {k: coerce(v) for k, v in row.items()}, None


def coerce(v):
    """CSV gives strings; turn obvious numbers back into numbers for stats."""
    if v is None or v == "":
        return v
    try:
        return int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            return v


def read_parquet(path_or_fh):
    try:
        import pyarrow.parquet as pq
    except ImportError:
        raise RuntimeError("Parquet needs pyarrow. Rerun with: uv run --with pyarrow python3 profile.py ...")
    table = pq.read_table(path_or_fh)
    for batch in table.to_batches(max_chunksize=10_000):
        for row in batch.to_pylist():
            yield row, None


# ----------------------------------------------------------- per-file profile

TYPE_NAME_RE = re.compile(r"(^|_|\.)(type|kind|event|action|role|op|category|status|source)s?($|_)", re.I)


def pick_type_field(fields, n):
    """A top-level field that splits records into a few kinds, so samples can
    show every kind instead of only the most common one."""
    best = None
    for p, fs in fields.items():
        if "." in p or "[]" in p or not fs.counts or not (2 <= len(fs.counts) <= TOP_VALUES_MAX):
            continue
        if fs.filled < 0.9 * n:
            continue
        score = (1 if TYPE_NAME_RE.search(p) else 0, -len(fs.counts))
        if best is None or score > best[0]:
            best = (score, p)
    return best[1] if best else None


def stratified_samples(records_iter_factory, field, rng):
    """One random record per value of `field` (reservoir sampling per value)."""
    seen, picks = {}, {}
    for rec, err in records_iter_factory():
        if err is not None or not isinstance(rec, dict):
            continue
        v = rec.get(field)
        if not isinstance(v, (str, int, bool)):
            continue
        seen[v] = seen.get(v, 0) + 1
        if rng.randrange(seen[v]) == 0:
            picks[v] = rec
    return picks


def profile_records(records_iter, rng):
    """Consume (record, error) pairs; return stats, samples, row count, errors."""
    fields = {}
    order = []
    n = 0
    bad = 0
    bad_examples = []
    reservoir = []
    for rec, err in records_iter:
        if err is not None:
            bad += 1
            if len(bad_examples) < 3:
                bad_examples.append(err)
            continue
        n += 1
        # reservoir sampling: every record has the same chance of being shown
        if len(reservoir) < N_SAMPLES:
            reservoir.append(rec)
        else:
            j = rng.randrange(n)
            if j < N_SAMPLES:
                reservoir[j] = rec
        for p, v in flatten(rec):
            fs = fields.get(p)
            if fs is None:
                fs = fields[p] = FieldStats()
                order.append(p)
            fs.add(v)
    return fields, order, n, bad, bad_examples, reservoir


def profile_file(name, kind, opener, size, rng):
    """opener() returns a fresh binary file handle. Returns a dict profile."""
    info = {"path": name, "type": kind, "bytes": size}
    try:
        if kind == "json":
            with opener() as fh:
                data, rpath, records = read_json(io.TextIOWrapper(fh, encoding="utf-8", errors="replace"))
            info["json_shape"] = shape(data)
            if records is None:
                info["note"] = "single JSON document, not a list of records"
                return info
            info["records_at"] = rpath
        factory = record_factory(kind, opener, records if kind == "json" else None)
        if factory is None:
            return info
        result = profile_records(factory(), rng)
    except Exception as e:  # keep going; report the failure in the profile
        info["error"] = f"{type(e).__name__}: {e}"[:300]
        return info

    fields, order, n, bad, bad_examples, samples = result
    info["rows"] = n
    if bad:
        info["unparseable_rows"] = bad
        info["unparseable_examples"] = bad_examples
    info["fields"] = {p: fields[p].summary(n, per_element="[]" in p) for p in order}
    info["samples"] = [truncate(s, TRUNC_SAMPLE) for s in samples]
    tf = pick_type_field(fields, n)
    if tf:
        try:
            picks = stratified_samples(factory, tf, rng)
            info["samples_by_kind"] = {"field": tf,
                                       "records": {str(k): truncate(v, TRUNC_SAMPLE) for k, v in picks.items()}}
        except Exception as e:
            info["samples_by_kind_error"] = str(e)[:200]
    # keep raw distinct values (capped) for cross-file join checks; dropped before writing
    info["_values"] = {p: set(list(fields[p].distinct)[:JOIN_VALUES_KEPT])
                       for p in order if fields[p].distinct and "[]" not in p}
    return info


def record_factory(kind, opener, records=None):
    """Return a function that yields (record, error) pairs from the start,
    so a file can be read more than once without holding it in memory."""
    if kind == "json":
        return lambda: ((r, None) for r in records)
    if kind == "jsonl":
        def gen():
            with opener() as fh:
                yield from read_jsonl(fh)
        return gen
    if kind in ("csv", "tsv"):
        def gen():
            with opener() as fh:
                yield from read_csv(fh, "\t" if kind == "tsv" else None)
        return gen
    if kind == "parquet":
        def gen():
            with opener() as fh:
                yield from read_parquet(io.BytesIO(fh.read()))
        return gen
    return None


def shape(data, depth=0):
    """A short description of a JSON document's structure."""
    if depth > 2:
        return type_name(data)
    if isinstance(data, dict):
        keys = list(data.keys())
        d = {k: shape(data[k], depth + 1) for k in keys[:25]}
        if len(keys) > 25:
            d["…"] = f"+{len(keys) - 25} more keys"
        return d
    if isinstance(data, list):
        return f"list[{len(data)}] of {type_name(data[0]) if data else 'nothing'}"
    return truncate(data, 60) if isinstance(data, str) else data


def text_preview(opener, size):
    with opener() as fh:
        raw = fh.read(4000)
    txt = raw.decode("utf-8", errors="replace")
    return {"bytes": size, "first_lines": txt.splitlines()[:15]}


# ----------------------------------------------------------- folder walking

def detect(name):
    ext = os.path.splitext(name.lower())[1]
    if ext in DATA_EXT:
        return DATA_EXT[ext]
    if ext in TEXT_EXT:
        return "text"
    return "other"


def walk(root):
    """Yield (display_name, kind, opener, size) for every file, descending
    into zip archives."""
    if os.path.isfile(root):
        paths = [root]
        base = os.path.dirname(root)
    else:
        paths = []
        for d, dirs, files in os.walk(root):
            dirs[:] = sorted(x for x in dirs if not x.startswith("."))
            paths += [os.path.join(d, f) for f in sorted(files) if not f.startswith(".")]
        base = root
    for p in paths:
        name = os.path.relpath(p, base)
        kind = detect(p)
        size = os.path.getsize(p)
        if kind == "zip":
            yield name, "zip", None, size
            try:
                zf = zipfile.ZipFile(p)
            except zipfile.BadZipFile:
                continue
            for zi in zf.infolist():
                if zi.is_dir() or os.path.basename(zi.filename).startswith("."):
                    continue
                if "__MACOSX" in zi.filename:
                    continue
                yield (f"{name}!/{zi.filename}", detect(zi.filename),
                       (lambda zf=zf, zi=zi: zf.open(zi)), zi.file_size)
        else:
            yield name, kind, (lambda p=p: open(p, "rb")), size


# ----------------------------------------------------------- cross-file hints

def hints(files):
    out = {"id_candidates": [], "time_candidates": [], "long_text_candidates": [],
           "join_candidates": []}
    for f in files:
        n = f.get("rows")
        if not n:
            continue
        for p, s in f["fields"].items():
            d = s.get("distinct")
            if isinstance(d, int) and d == n and s.get("filled_pct") == 100.0 and "[]" not in p:
                out["id_candidates"].append(f"{f['path']} :: {p}")
            if s.get("looks_like_time_pct", 0) >= 90:
                out["time_candidates"].append(f"{f['path']} :: {p}")
            if s.get("str_len", {}).get("median", 0) >= 200:
                out["long_text_candidates"].append(
                    f"{f['path']} :: {p} (median {s['str_len']['median']} chars)")
    # join keys: fields in different files whose values overlap a lot
    tables = []
    for f in files:
        keep = {}
        for p, vals in f.get("_values", {}).items():
            s = f["fields"][p]
            if list(s["types"]) != ["str"] and "str" not in s["types"]:
                continue  # small numbers overlap by coincidence
            if s.get("looks_like_time_pct", 0) >= 50:
                continue  # timestamps overlap by coincidence
            if isinstance(s.get("distinct"), int) and s["distinct"] < 20:
                continue  # low-cardinality categories (e.g. a "source" column) are not join keys
            keep[p] = vals
        if keep:
            tables.append((f["path"], keep))
    for i, (fa, va) in enumerate(tables):
        for fb, vb in tables[i + 1:]:
            for pa, sa in va.items():
                if len(sa) < 5:
                    continue
                for pb, sb in vb.items():
                    if len(sb) < 5:
                        continue
                    inter = len(sa & sb)
                    small = min(len(sa), len(sb))
                    if inter >= 20 and inter / small >= 0.5:
                        out["join_candidates"].append(
                            f"{fa} :: {pa}  <->  {fb} :: {pb}  "
                            f"({inter} shared values; {pct(inter, small)}% of the smaller side)")
    return out


# ----------------------------------------------------------- output

def write_markdown(prof, path):
    L = []
    L.append(f"# Dataset profile: {prof['dataset_root']}")
    L.append("")
    L.append(f"Generated {prof['generated']} by `profile.py` (no model calls). "
             f"Random seed {SEED}. Strings are truncated for display.")
    L.append("")
    L.append("## File inventory")
    L.append("")
    L.append("| File | Type | Size | Rows | Fields | Notes |")
    L.append("|---|---|---|---|---|---|")
    for f in prof["files"]:
        notes = []
        if f.get("error"):
            notes.append("ERROR: " + f["error"])
        if f.get("unparseable_rows"):
            notes.append(f"{f['unparseable_rows']} unparseable rows")
        if f.get("records_at"):
            notes.append(f"records at `{f['records_at']}`")
        if f.get("note"):
            notes.append(f["note"])
        L.append(f"| `{f['path']}` | {f['type']} | {human(f['bytes'])} | "
                 f"{f.get('rows', '')} | {len(f.get('fields', {})) or ''} | {'; '.join(notes)} |")
    L.append("")

    h = prof["hints"]
    L.append("## Cross-file hints (heuristic, computed by code)")
    L.append("")
    for key, title in [("id_candidates", "Unique, always-filled fields (possible IDs)"),
                       ("time_candidates", "Fields that look like timestamps"),
                       ("long_text_candidates", "Long text fields (possible message content)"),
                       ("join_candidates", "Fields whose values overlap across files (possible join keys)")]:
        L.append(f"**{title}:**")
        L.extend([f"- `{x}`" for x in h[key]] or ["- none found"])
        L.append("")

    for f in prof["files"]:
        if f["type"] in ("zip", "other"):
            continue
        L.append(f"## `{f['path']}`")
        L.append("")
        if f["type"] == "text":
            L.append("Text file, first lines:")
            L.append("```")
            L.extend(f.get("preview", {}).get("first_lines", []))
            L.append("```")
            L.append("")
            continue
        if f.get("error"):
            L.append(f"Could not read: {f['error']}")
            L.append("")
            continue
        if "json_shape" in f:
            L.append("JSON shape:")
            L.append("```json")
            js = json.dumps(f["json_shape"], ensure_ascii=False, indent=1)
            L.append(js if len(js) <= 1500 else js[:1500] + "\n… [shape truncated; see profile.json]")
            L.append("```")
            L.append("")
        if not f.get("fields"):
            continue
        L.append(f"{f['rows']} rows. Fill % counts values that are not null/empty.")
        L.append("")
        L.append("| Field | Filled | Types | Distinct | Length (min/med/max) | Examples |")
        L.append("|---|---|---|---|---|---|")
        items = list(f["fields"].items())
        for p, s in items[:MAX_FIELDS_SHOWN]:
            types = ", ".join(f"{t} {pct(c, sum(s['types'].values()))}%" if len(s['types']) > 1 else t
                              for t, c in s["types"].items())
            ln = s.get("str_len") or s.get("list_len")
            ln = f"{ln['min']}/{ln['median']}/{ln['max']}" + (" items" if "list_len" in s and "str_len" not in s else "") if ln else ""
            extra = []
            if s.get("multiline_pct"):
                extra.append(f"multiline {s['multiline_pct']}%")
            if s.get("looks_like_time_pct"):
                extra.append(f"time-like {s['looks_like_time_pct']}%")
            if s.get("value_counts"):
                ex = "counts: " + "; ".join(cell(f"{k} ×{c}") for k, c in s["value_counts"].items())
            else:
                ex = "; ".join(cell(e) for e in s["examples"])
            filled = (f"{s['filled_elements']} of {s['elements']} list elements"
                      if s.get("per_element") else f"{s['filled_pct']}%")
            L.append(f"| `{p}` | {filled} | {types} | {s.get('distinct', '')} | "
                     f"{ln}{(' ' + ', '.join(extra)) if extra else ''} | {ex} |")
        if len(items) > MAX_FIELDS_SHOWN:
            L.append(f"| … | | | | | {len(items) - MAX_FIELDS_SHOWN} more fields in profile.json |")
        L.append("")
        L.append(f"Random sample records ({len(f['samples'])}):")
        L.append("")
        for s in f["samples"]:
            L.append("```json")
            L.append(json.dumps(s, ensure_ascii=False, indent=1))
            L.append("```")
        L.append("")
        sk = f.get("samples_by_kind")
        if sk:
            L.append(f"One random record for each value of `{sk['field']}`:")
            L.append("")
            for k, rec in sk["records"].items():
                L.append(f"`{sk['field']}` = `{k}`:")
                L.append("```json")
                L.append(json.dumps(rec, ensure_ascii=False, indent=1))
                L.append("```")
            L.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


def cell(v):
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    s = s.replace("|", "\\|").replace("\n", "⏎").replace("`", "'")
    return f"`{s}`"


def human(b):
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.0f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dataset", help="dataset folder (or a single file)")
    ap.add_argument("--out", required=True, help="folder to write profile.md and profile.json into")
    args = ap.parse_args()

    rng = random.Random(SEED)
    files = []
    for name, kind, opener, size in walk(args.dataset):
        print(f"profiling {name} ({kind}, {human(size)})", file=sys.stderr)
        if kind in ("jsonl", "json", "csv", "tsv", "parquet"):
            files.append(profile_file(name, kind, opener, size, rng))
        elif kind == "text" and opener and size < 5_000_000:
            files.append({"path": name, "type": "text", "bytes": size, "preview": text_preview(opener, size)})
        else:
            files.append({"path": name, "type": kind, "bytes": size})

    prof = {
        "dataset_root": os.path.abspath(args.dataset),
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "files": files,
        "hints": hints(files),
    }
    for f in files:
        f.pop("_values", None)

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "profile.json"), "w", encoding="utf-8") as fh:
        json.dump(prof, fh, ensure_ascii=False, indent=1, default=str)
    write_markdown(prof, os.path.join(args.out, "profile.md"))
    print(f"wrote {args.out}/profile.md and profile.json", file=sys.stderr)


if __name__ == "__main__":
    main()
