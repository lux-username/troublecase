# Dataset card: instructions and template

## Instructions for the model

You are reading `profile.md`, a compact profile of a dataset you have never seen, produced by `scripts/profile.py`. Your job is to write a **dataset card**: a short, plain-language description of what the data is and how to turn it into events (see `codebook/event-format.md`).

**Why this card exists:** the events feed an investigation of the swarm's social order (roles, rules, signals, conflicts and how they're settled). The card's job is to preserve that evidence, not to clean the data. Read "Purpose and stance" in `convert/SKILL.md` before answering section 6.

A human will read the card and approve or correct it **before** any adapter is written. So:

- **Base every answer on the profile.** Point to the evidence: a file, a field, a fill rate, a value count, a sample record. Write it as `(profile: messages.jsonl :: text, 99.5% filled)`.
- **Flag uncertainty; don't guess.** If the profile can't settle a question, say so in answer 8 and say what would settle it (for example, "read 10 consecutive messages from the busiest thread").
- **You may run small checks** (a `grep`, or a few lines of Python that count something) when the profile leaves a question open, and the answer changes the adapter. Record each check and its result under "Checks run". Code does the counting. Never estimate a number you could count.
- **Prefer the source's own structure.** Reuse its IDs, its groupings and its timestamps. Invent as little as possible.
- **Plain language.** The approver may not read code. Name fields in `code font`, but explain them in words.

Fill in every section below. Keep it to about two pages.

---

# Dataset card: `<dataset name>`

Status: **DRAFT, awaiting approval**
Profile: `<path to profile.md>` · Written by: `<model>` · Date: `<date>`

## 1. What is this dataset?
Where it comes from, who or what produced it, the time span, the overall size. Which files matter and which are metadata.

## 1b. What is the setting?
Who the actors seem to be (agents, humans, bots; which systems), what they were doing, where they wrote, and **why they interacted at all**. Say what is known from the data's own documentation, what you can see in samples (cite them), and what is guesswork. This becomes the briefing's orientation, so the approver should correct it here.

## 2. What is one message (one event)?
Which file and which rows become events. Is one row one event, or does a row need splitting or merging? Which field holds the text? Do some rows become `action` events instead of `message` events?

## 3. Who is speaking?
Which field names the actor. Can actors rename themselves? Are there other identity signals (signatures in the text, IPs, flags for humans or admins)? Which one goes in `actor`, and which go in `extra`?

## 4. What makes a conversation?
The natural grouping (thread, channel, page) and its field. How big do groups get (median, largest)? Is there a larger unit above it (topic, family) worth keeping in `extra`?

## 5. How do replies work?
Is there an explicit reply field? If not, what cues exist in the text (@-mentions, quoting, signatures, naming)? The adapter fills `in_reply_to` only from explicit fields.

## 6. What looks like noise, and what social act could it be?
List the content that looks mechanical: tests, link dumps, bots, boilerplate, repeats, automated logs. For each kind, give:
- **What social act it could be.** A link can be a signal, an overwrite can be a conflict, a repeat can be a convention spreading, a test can be a probe of a rule. Say if you can't think of one.
- **The flag** you propose in `extra`, and how many events it covers (counted).
- **A sampled check.** Read at least 20 random flagged events and report how many carry social content, with examples. Record it under "Checks run".

Noise is **kept and flagged, never dropped.** Rows are dropped only for structural reasons (an exact duplicate, no conversation to belong to, metadata); list those here, with counts. Never suggest that a later step skip events because of a content flag. If size is a concern, propose a way to shrink the text the models read (e.g. shortening URLs) instead.

## 7. What else is worth keeping?
Dataset-specific fields for `extra`, each with a one-line reason. Favour things that point *towards* social evidence: trouble hints (whose content was removed or overwritten), role signals, signatures, admin or human actions, links between conversations. Noise flags are for describing and summarising, not for filtering. Name the hint fields explicitly: validation checks how much of each one falls under each noise flag.

## 8. What is uncertain?
Open questions, risks and assumptions, each with how it could be settled. Number them so the approver can answer by number.

## Proposed mapping

| Core field | Source | Rule |
|---|---|---|
| `event_id` | | |
| `dataset` | | |
| `conversation_id` | | |
| `actor` | | |
| `timestamp` | | |
| `order` | | |
| `kind` | | |
| `content` | | |
| `in_reply_to` | | |
| `extra.*` | | |

Expected output: about `<N>` events from `<M>` source rows. Rows to be dropped, and why: `<…>`.

## Checks run
| Check | Result |
|---|---|

---

## Approval
- [ ] Approved as written
- [ ] Approved with corrections (listed below)
- [ ] Rejected: redo the card

Corrections and answers to section 8:

Approved by: ______ Date: ______
