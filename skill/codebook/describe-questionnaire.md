# Describe: case questionnaire

You are writing case notes for a study of the **social order a group of AI agents built for themselves**: who leads, what roles exist, what rules and signals they use, and above all **how they handle trouble between themselves**. The method is the trouble-case method from legal anthropology: institutions show most clearly when something goes wrong and has to be settled.

Your notes are the material for a **working model of the society**: its institutions described as mechanisms (what sets them off, who runs them, what steps they follow, what backs them, how they fail). So the most important question for each case is not "what happened" but **"how does this work?"**: which procedure or authority was used, and how.

Each case file holds:
- **The case itself:** a conversation unit that triage marked as trouble, with every event shown as `[event_id] time · actor · kind`.
- **Related material:** excerpts from *other* conversations, found by code: the same actors nearby in time, references between conversations, rare shared terms, and what came just before or after. Each excerpt says how it was found.
- **The triage label:** a first reading, with key event IDs. It is a pointer, not a conclusion. Check it against the text.

## Rules

- **Evidence first.** Every claim cites event IDs. Quotes must be copied **exactly** from the event text (code will check this). Never quote from memory or paraphrase inside quotation marks.
- **Between the agents.** Focus on what agents do *to and with each other*. Outside actions (admins, the platform) matter when agents react to them, or when they change how agents deal with each other.
- **Use the related material only when it bears on this trouble.** It may show the rule being cited, the earlier decision, who someone is, or what happened next. Ignore excerpts that don't.
- **Follow-up search (required when something important is unexplained, at most 2 rounds per case).** If the case refers to something it doesn't show (who an actor is, which earlier decision or rule is cited, what happened next), you must search before writing the note, and record what you found or that you found nothing:
  `python3 <scripts>/assemble.py search --events <events.jsonl> [--actor NAME] [--term TEXT] [--conversation ID] [--around EVENT_ID]`
  It returns matching events with their IDs. Record each search you ran and what it found.
- **Say what you don't know.** If the evidence is ambiguous, say so in `uncertainties`. Don't fill gaps.
- **Content that looks mechanical can be social.** A link, code or token can be a signal; an overwrite can be a move in a conflict; a short post can be a protocol message.

## Output: one JSON object per case, one per line

```json
{
  "case_id": "<as given>",
  "summary": "2-4 sentences: what happened, citing event IDs",
  "parties": [{"actor": "<name as in the data>", "role_in_case": "<e.g. claimant, objector, enforcer, mediator, bystander, outside authority>"}],
  "trouble": "what the trouble was, in one or two sentences, with event IDs",
  "handling": "how it was handled or settled, by whom, by what means, with event IDs; or 'not settled'",
  "mechanism": {
    "trigger": "what set the handling off (the trouble, a request, a deadline...), with event IDs",
    "procedure": "the steps that were followed, in order, with event IDs; 'none visible' if it was ad hoc",
    "operated_by": "who ran it, and in what role (self-appointed, assigned, by authority...)",
    "backed_by": "what made it stick: staff or outside authority, peers' agreement, a stated rule, evidence, nothing",
    "ending": "how it ended: settled, dropped, overruled, left open; and who decided",
    "after": "what changed afterwards: a rule made, kept, forgotten or reversed; nothing visible"
  },
  "norms": [{"kind": "rule | protocol | precedent | authority | apology | sanction | correction | proposal | other", "statement": "the norm in plain words", "event_id": "<id>", "quote": "<exact words>"}],
  "outcome": "what changed afterwards, if visible, with event IDs",
  "institutions": "what this case shows about the agents' institutions (roles, rules, signals, settlement methods), as plainly as possible",
  "evidence": [{"event_id": "<id>", "quote": "<exact words, at most 300 characters>", "why": "<what it shows>"}],
  "cross_conversation": [{"event_id": "<id from related material or a search>", "found_by": "<how>", "relevance": "<why it matters>"}],
  "searches": [{"query": "<the search you ran>", "found": "<what it found, with event IDs>"}],
  "same_trouble_as": ["<other case or unit IDs that are clearly the same trouble, if any>"],
  "escalate": {"flag": false, "reason": "true if the case is unusually clear evidence of how an institution works, or fits no ordinary pattern (a candidate for the deep dive)"},
  "uncertainties": "what is unclear or could be read another way"
}
```

Give 3-8 `evidence` items: the moments that matter most, not every event. `norms` may be empty if none is visible. In `mechanism`, write "none visible" rather than guessing; a case that shows no mechanism is still useful evidence of where institutions are absent.
