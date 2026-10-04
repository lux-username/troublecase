# Target event format (v1)

Every dataset is converted into this one shape: a JSONL file, one **event** per line. An event is one message or one action. Conversations are built from events later (segmenting), but each event already carries a first-guess `conversation_id`.

The core is small and the same for every dataset. **The core never grows to fit a dataset.** Anything dataset-specific goes in `extra`.

## Core fields (required on every event)

| Field | Type | Meaning |
|---|---|---|
| `event_id` | string | Stable and unique within the dataset. Every citation in the briefing points to one. Reuse the source's own ID when it has one. |
| `dataset` | string | Short dataset name, e.g. `team-chat-2026`. |
| `conversation_id` | string | The natural grouping the source gives (thread, channel, page). Segmenting may split it later. |
| `actor` | string or null | Who did it, **exactly as the source names them**. No merging of renamed agents here. Null only if the source has no actor at all. |
| `timestamp` | string or null | ISO 8601 UTC (`2026-06-16T19:22:48Z`) when known. |
| `order` | integer | A guaranteed sequence inside the conversation (0, 1, 2…), for when timestamps tie or are missing. |
| `kind` | string | `message` (text written for others to read) or `action` (something done: a delete, a tool call, a probe). |
| `content` | string | The text of the message, or a short plain description of the action. Never empty for a `message`. |
| `in_reply_to` | string or null | The `event_id` this replies to, **only when the source says so explicitly**. Inferred replies are a later step, not the adapter's job. |

## `extra` (optional object)

Whatever the dataset card says is worth keeping, under clear names. Typical kinds: a name claimed in the text that differs from `actor` (e.g. `actor_signature`), a larger grouping above the conversation, whose content an event removed or overwrote (a trouble hint), whether the actor is a human or an admin, and descriptive noise flags (e.g. `subkind`).

**One `extra` field is required: `source_ref`.** It is a list of the raw rows the event came from, each written as `"<file path relative to the dataset folder>:<line number>"` (1-based; for JSON arrays, the array index; for CSV, the data row number, not counting the header). `validate.py` uses it to show each converted event next to its raw source, whatever the dataset.

Rules for `extra`:
- Keep it flat where possible, with short snake_case names.
- Do not copy whole raw records into it. Keep only fields that the card justifies.
- The most valuable fields point *towards* social evidence: trouble hints, role and identity signals. Noise flags describe; they never filter (see "Purpose and stance" in `convert/SKILL.md`).

## File layout

- `data-inputs/normalized/<dataset>.events.jsonl`: the events, sorted by `conversation_id` then `order`.
- The run folder (`outputs/<date>_<dataset>_convert-vN/`) holds `profile.md`, `dataset-card.md` (approved), `adapter.py` (a copy of the adapter that ran), `coverage.json` and `conversion-report.md`.

## `coverage.json` (written by the adapter)

The adapter accounts for every source row, so code can check that nothing went missing silently:

```json
{
  "dataset": "team-chat-2026",
  "sources": {
    "messages.jsonl": {"rows": 52000, "converted": 51870,
                       "dropped": {"exact duplicate of another row": 130}},
    "channels.csv": {"rows": 40, "converted": 0,
                     "dropped": {"lookup table, joined into extra": 40}}
  },
  "events_written": 51870
}
```

For every source, `rows` must equal `converted` plus the sum of `dropped`. The `dropped` reasons are plain-language strings, because they are quoted in the report. Files that are deliberately not converted (metadata) are listed with `"converted": 0` and a reason such as `{"metadata, not conversation": 1}`. They can also be left out and named in the card.
