---
name: convert-dataset
description: Convert an unknown multi-agent transcript dataset (JSONL, JSON, CSV, Parquet or zip) into the common event format used by the troublecase skill. Profiles the data with code, writes a dataset card, waits for human approval, generates a dataset-specific adapter, and validates the result against the raw data. Use as step 0, before segmenting and triage.
---

# Convert a dataset into events

You turn a dataset you have never seen into one JSONL file of **events** (see `../codebook/event-format.md`), with a record of every decision made along the way. Do not hand-write an answer from skimming the data. Follow the steps in order.

## Purpose and stance: read this before judging any data

The events you produce feed **an investigation of the social order a swarm built for itself**: its leaders, roles, rules, signals, conflicts, and how those conflicts get settled. Your job is to **keep that evidence intact and readable. You are not cleaning the data.**

What counts as "noise" is a judgement, and it has to be made with this purpose in mind. In agent swarms, **content that looks mechanical is often the social act itself**:
- A URL, a code or a token can be a **signal**. Agents may coordinate by touching a shared resource instead of writing prose, and the rules for doing so are often written around the link itself.
- **Overwriting or deleting** someone else's content can be a **conflict**, even when the content is mechanical.
- A very short post (a tag, a status word, a name) can be a **protocol message**.
- A test edit can be an agent **probing a rule or an authority**.
- Text **repeated** across many posts can be a **convention spreading by copying**, which is itself an institution.

So:
1. **Drop rows only for structural reasons:** an exact duplicate of another row, a row that belongs to no conversation, or metadata. **Never drop anything because of its content.** Count every drop, with its reason.
2. **Flags describe; they never filter.** Flags like `link_only`, `test` or `boilerplate` help later steps *prioritise and summarise*. Do not propose that any later step skip events because of a content flag.
3. **If size is the problem, shrink rather than exclude.** For example, shorten long URLs or collapse exact repeats with a count, in the text the models read. The events file keeps the full content.
4. **Before calling something noise, ask what social act it could be.** Then test it: read a random sample of what you would flag, look for social content, and report what you found. Code counts; the sample shows what the count hides.
5. **State the cost of any flag in the card:** how many events it covers, and what kinds of evidence would vanish if someone filtered on it.
6. **When in doubt, it's evidence.**

**Paths.** `<raw>` is the dataset folder (never modify it). `<run>` is a new folder `outputs/<YYYY-MM-DD>_<dataset>_convert-v<N>/`. Never reuse an existing run folder: if it exists, increase N. `<normalized>` is where event files go (`data-inputs/normalized/` in this project).

## Step 1. Profile (code)

```
python3 ../scripts/profile.py <raw> --out <run>
```

This writes `<run>/profile.md`: the file inventory, every field with fill rates, value counts, example values, random samples and one sample per record type, plus hints about IDs, timestamps, long text and join keys. If a Parquet file shows an error, rerun with `uv run --with pyarrow python3 ../scripts/profile.py …`.

Read `profile.md`, not the raw data.

## Step 2. Write the dataset card (you)

Copy the template in `../codebook/dataset-card.md` to `<run>/dataset-card.md` and fill it in from the profile. It has eight questions: what this is, what one message is, who is speaking, what makes a conversation, how replies work, what is noise, what else to keep, and what is uncertain.

- Cite the profile for every answer.
- When the answer would change the adapter and the profile can't settle it, run a small counting check (a few lines of Python) and record it under "Checks run". **Code counts; you never estimate a number you could count.**
- Flag uncertainty in section 8 as numbered questions with a proposed default. Don't guess silently.
- For section 6 (noise), apply the stance above. Every proposed noise flag needs a sampled check of what it covers, recorded under "Checks run".

## Step 3. Human approval gate. STOP HERE.

Show the human the card: the summary of each section, the proposed mapping, the expected event count, and the numbered open questions. Then **wait**. Do not write the adapter until the human answers.

- **Approved:** tick the box, record the approver and the date.
- **Corrections:** write them, word for word, under "Corrections", and update the card to match. Then continue.
- **Rejected:** redo step 2.

The approved card is quoted in the briefing's method and limits section, so it must say what was actually done.

## Step 4. Generate the adapter (you write code)

Write `<run>/adapter.py`. It is a standalone script, standard library only if possible, that implements the approved card:

```
python3 <run>/adapter.py --raw <raw> --out <normalized>/<dataset>.events.jsonl --coverage <run>/coverage.json
```

Requirements:
- Output follows `../codebook/event-format.md`. That means the core fields, plus `extra`, which always has `source_ref` (which raw rows each event came from, as `file:line`).
- It writes `coverage.json` and accounts for **every** source row, as either converted or dropped, with a plain-language reason.
- Events are sorted by `conversation_id`, then `order`, and `order` runs 0, 1, 2… in each conversation.
- It is deterministic: the same input gives the same output.
- Drops only for the structural reasons the card lists. Noise is kept and flagged, never dropped (see "Purpose and stance").

## Step 5. Validate (code, then you)

```
python3 ../scripts/validate.py --events <normalized>/<dataset>.events.jsonl --raw <raw> \
    --coverage <run>/coverage.json --out <run> \
    --noise-flag 'extra.<field>=<value>' ...   # one per noise flag the card defines
    --hint-field extra.<field> ...            # one per trouble or identity hint the card defines
```

1. **Format and coverage (code).** `validation.md` lists every check. Any **FAIL** means you fix the adapter and rerun steps 4–5. Warnings must be explained in the report.
2. **Side by side (you).** Read `side-by-side.md`: sampled conversations, each event next to its raw rows. For each sampled conversation, judge: is the content faithful (nothing lost, duplicated or invented)? Are the actor, time, order and kind right? Do the flags in `extra` match what you see? If anything is wrong, fix the adapter and rerun.
3. **What the noise flags hide (code, then you).** For each `--noise-flag`, `noise-sample.md` gives three things:
   - **Counts:** how many flagged events still contain sentence-like lines, and what share of each hint field (the trouble and identity hints the card defines, passed as `--hint-field`) falls under the flag.
   - **Sample A:** the sentence lines from flagged events that contain any. Social content in noise is usually *rare but important*, so a purely random sample tends to miss it.
   - **Sample B:** random flagged events, in full.

   Read both samples and ask of each event: is there a signal, a rule, a claim, a complaint, a correction, an overwrite or a convention here? Report the counts and the social examples you found, with event IDs. If a flag covers a meaningful share of a hint field, or Sample A turns up rules, signals or disputes, the report must say that **the flag must not be used to filter**, and why.

## Step 6. Setting: what is this, really? (code, then a fresh reader, then the human)

The card's setting answer (1b) was written from a profile, which shows the format but not the situation. Now that the events exist, get the situation right from real messages.

1. **Sample (code):**
   `python3 <scripts>/sample_setting.py --events <normalized>/<dataset>.events.jsonl --out <run>/setting-sample.md`
   About 80 messages spread across time, conversations and actors; half from conversations with several actors, so mechanical bulk cannot crowd out exchanges; a few short runs of consecutive messages; and a summary of non-message events (who does them, of what kinds). About 15k tokens.
2. **Read (a fresh subagent, strongest model):** give it only `codebook/setting-instructions.md` and the sample, nothing about the dataset from the card or this conversation, so the reading is independent. It writes `<run>/setting.md`: actors, what they are doing and what kind of situation they are in, the space and its uses, why they interact, who else acts on the space, their vocabulary, and numbered open questions. Every statement cites events and is marked observed, inferred, guess or background.
3. **Compare with the card (you):** where `setting.md` and the card's answer 1b disagree, say so.
4. **Human check:** show the human `setting.md`'s one-paragraph summary, the disagreements and the open questions, and ask for corrections. If the human is not available, continue and keep the open questions open. Record the answers in `setting.md` under "Human corrections".

The approved `setting.md` is the context for everything later: who counts as an outsider, what a message means, and the briefing's "What this is".


## Step 7. Hand off

Write `<run>/conversion-report.md`:
- the source, the date and the version of this skill
- a link to the approved card, with any corrections
- a link to the approved `setting.md`, with the human's corrections
- the coverage table (copied from `validation.md`): rows in, converted and dropped, with reasons
- the output statistics: events, conversations, kinds, actors, how often each `extra` field is filled
- the side-by-side verdict, conversation by conversation, with event IDs for any problems found
- the noise-flag check: for each flag, how many events it covers, and how much social content turned up in its sample
- known limits, which feed the briefing's method and limits section

The next step (segmenting) reads `<normalized>/<dataset>.events.jsonl`.
