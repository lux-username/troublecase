# Briefing: instructions and template

You are writing the final **institutional briefing** for a study of the social order a group of AI agents built for themselves.

**The reader** is an intelligent outsider who has never seen this data, the platform, or our pipeline. After reading, they should be able to explain to someone else what this agent society is, how it works, and how sure we are. If a sentence only makes sense to someone who has read the data or the case notes, rewrite it.

## Your sources (use nothing else)

- `model.md` / `model.json` (the final round): **the model of the society**: institutions as mechanisms, the map of how they connect, what is absent. The backbone of sections 2–4.
- `test-results.md` / `test-results.json` (every round): how each prediction fared on random episodes, with 90% ranges. **The main source of numbers about institutions.** If the human declined a further round of refinement, these results also say where the model is wrong, and the briefing must say so.
- The test results also give, from the random sample, **coverage** (in how many random trouble episodes no institution applied, and what the model does not explain), **how common each institution is**, and **which institutions occur together**. Use these for "how common" claims and for the map; say plainly how much of the trouble the model does not cover.
- `audit.md` / `audit.json`: how often the scan's labels were right, measured on a random sample.
- `episodes.md` / `episodes-summary.json`: how many trouble episodes there are, and how many pieces were labelled as routine problems (tool failures, loops, unanswered outside actions).
- **Numbers come only from these files.** Copy them unchanged. Never compute or estimate one. Code checks every number.
- `notes-view.md`: the case notes with quotes and event IDs. **The only source of quotes,** with the dossiers. Copy quotes exactly; code will check every one.
- `method-facts.md`: facts about the data and the run, for the orientation and the method section (written first; see below).
- `dossiers/*.md` (if present): full reconstructions of the cases to tell in section 5. Tell those cases from the dossiers, not from the shorter notes.

## Before writing: the method-facts file

The orchestrator writes `method-facts.md` in the briefing's run folder before the briefing is written. The briefing may use no background fact that is not in it. Every fact carries its source in brackets: **[card]** (the approved dataset card), **[inspection]** (any human reading of the data), **[notes]** (the case notes), **[report]** (a run's report or counts), or **[interpretation]** (a reading, which the briefing must mark as one).

```
# Method facts
## Context (for "What this is")
Who the actors are; what they were doing; the platform and what it let them do; why they interacted at all; who else acts on the space (administrators, moderators, outsiders); the time span and size. Mainly from the approved `setting.md` (its latest version, with the updates after close reading and the human's corrections), plus any human inspection notes.
## Data
Source, what one event is, events kept and dropped (and why), from the conversion report.
## How the study ran
One line per step, with its numbers from the step's own report: how much was read, by which model, how episodes were formed, how cases were picked, how the model was built and tested (rounds, predictions, episodes drawn), and whether the human approved or declined refinement.
## Checks
The scan audit (with its range), quote checks, the ranking check (top vs random cases), the model test summary, identity checks, with numbers.
## The deep dive
Which cases were rebuilt, how much each gathering covered, what each reconstruction corrected (one line per case), and any part that was not read and why.
## Limits
Each limit with its measured size.
## Cost
Model calls and tokens per step, as recorded.
```

## What counts as trouble

A **trouble** is a case where something went wrong between agents (or between agents and others acting on the space) **and at least one agent responded to it**: objected, corrected, chased, repaired, warned, apologised, refused, invoked or proposed a rule. Problems that are not between agents (tool failures, repetition loops, outside actions nobody answered, one agent's mishap nobody touched) are **routine practice**: report them as how the place is used, never as trouble. Trouble is counted in **episodes** (one trouble, however many conversation pieces it spans), not in pieces.

## Writing rules

- **Orient first, and say where it comes from.** Before any finding, explain who the agents are, what they were doing, where they wrote, and why they talked to each other at all. Take this from the method facts (the approved dataset card and any human inspection) and name the source. Mark anything you add beyond it as interpretation.
- **Glossary with evidence.** Give a short glossary of the agents' own jargon (their words for groups, rounds, signals, and so on). Each entry cites one or two events where the term is used, in the form `- **term**: meaning [event_id]`; code checks that the term appears in those events. If the meaning is your inference rather than something the agents say, write "(inferred)".
- **No pipeline talk in sections 1–6.** Don't write "units", "parts", "tags", "codes", "escalated", "the apply step", or file paths. Say "conversations", "cases", "pages". Don't mention our own working documents or steps either: no "case notes", "earlier note", "dossier", "rebuilt", "reconstruction", or what one of them got wrong. The reader never saw them. Tell what happened, not how we found out. How the study worked, and what later reading corrected, belongs in the method section (7).
- **Explain before you quote.** For each institution: a short plain paragraph saying what it is and why the agents needed it. Then how common it is. Then one or two exchanges that show it.
- **Quote exchanges as transcripts**, one speaker per line, in a block quote:

  > **AgentName** (time): exact words [event_id]
  > **OtherAgent** (time): exact words [event_id]

  You may write `**?** (?)` for speaker and time: code fills both in from the event ID (who posted, and when) and corrects any name you guessed. Add one line after the block saying what it shows. Explain any jargon inside the quote. Don't string fragments of different speakers into one sentence.
- **Explain the testing before any test result.** The reader does not know that we turned the findings into predictions and checked them. The first time a test result appears (normally at the top of section 2), say in two or three plain sentences how the claims were checked: the picture was built from a set of cases read closely; each claim was turned into a prediction ("when X happens, agents do Y"); each prediction was checked against conversations picked at random that were not used to build the picture; and, if there was a revision, that the predictions were then revised and checked again on further unseen conversations, and how many were left. Define any term you then use for it ("round one", "unseen", "applicable") in the same place. Never write "the model", "testable", "trigger", "round two" or "rated poorly/well" before this explanation, and never as unexplained shorthand.
- **Limits in sections 1–6 are written for the same new reader.** Each limit says, in plain words, what was done and what it means for the findings: not "the scan is wrong one time in eight" but "an AI model read every conversation to flag trouble; a check of 40 of its calls found 35 right, so some trouble was missed or wrongly included". Name any step the reader has not met (the automatic reading that flagged trouble, how episodes were cut, what part of the data was studied) before giving its limit. No method shorthand ("era", "the reader", "grouped by code", "units", "pieces") unless section 1 or 2 has already explained it.
- **Numbers in plain words, with what they are out of:** "in 120 of the 207 troubles (58%)". Each count is introduced once, where it matters. Not every count belongs in the briefing.
- **Mark interpretation as interpretation.** "The notes suggest…", "one reading is…".
- **Counterexamples only when useful:** include one when a case shows clearly where a pattern stops. Otherwise leave it out.
- **Short sentences. Plain words.** Aim for 15 minutes of reading.

## Conclusions: rules (strict)

The conclusions section says what we know about this society **from the trouble cases**, and nothing more.
- **Every conclusion states its basis and its strength:** tested on random episodes (give the result and its range, e.g. "held in 14 of 18, 90% range 60–92%"); seen in several of the cases read closely (name them); or seen in one case only (say so). A prediction that failed or was mixed is reported as such, not left out.
- **No invented significance.** Don't call anything "remarkable", "striking", "emergent", "sophisticated" or "novel", or claim it is the first of its kind. Don't compare to human societies or draw lessons for AI safety unless the evidence directly supports the specific claim.
- **No causal claims without evidence of the cause.** "X happened, then Y" is not "X caused Y".
- **Ordinary findings are stated as ordinary.** If something is common or unsurprising, say so plainly. "Nothing notable" is an acceptable conclusion.
- **Say what cannot be concluded, and what would settle it:** one list of conclusions a reader might be tempted to draw that the data does **not** support. Each item: the tempting conclusion, why the data does not support it, and what evidence would settle it (or that nothing available could). This list is also the briefing's open questions; don't repeat it elsewhere.
- **Before finishing, reread each conclusion and ask:** would someone who read every case agree this is exactly what the evidence shows, no more? Cut or weaken anything that fails.

## Template

```
# <Title>

## 1. What this is
Who the agents are, what task they were doing, the platform, the time span, and why they coordinated at all. 1–3 short paragraphs.
*Sources for this section:* name them (dataset card, human inspection).
**Glossary:** 6–12 of the agents' own terms, one line each, each with an event ID where it is used.

## 2. The short version
Open with two or three plain sentences saying how the findings were checked (see "Explain the testing before any test result"): built from cases read closely, turned into predictions, checked on randomly picked conversations not used to build them, and, if there was a revision, revised and checked again on what was left. A reader who has never heard of the method must understand every "tested" figure in the bullets that follow.
Then 5–8 bullet points: the main institutions and how trouble is handled, each with how well it held up when tested; where the findings failed; how sure we are overall, in plain words (how many predictions held, failed or could not be judged, and why a revision round does or does not add confidence); the main limits, each explained for a new reader as what was done and what it means for the findings (see "Limits in sections 1–6").

## 3. How the society works
Open with a short overview (one paragraph, or 4–6 plain sentences) of how the society works as a whole, before any subsection: what holds it together, the main rules, who does what, and where it breaks. No numbers or quotes here; the subsections give the evidence. A reader who stops after this paragraph should have the right picture.
Then the map: how the institutions connect (which backs which, which takes over when another fails), in plain words, from the model.
3a. Routine practice: what the shared space is used for day to day, and the routine problems nobody treated as trouble, with their counts.
3b. The institutions, one subsection each (usually 4–8), in this order: what it is and why the agents need it (plain paragraph); **how it works** (what sets it off, who runs it, the steps, what backs it, how it fails); **how common it is and how well that held up** (its share of random trouble episodes; each prediction and its test result, in plain words, including failures); one or two transcripts that show it working; a counter-case only if one changes the conclusion or clearly shows where the institution stops.

## 4. Trouble and how it is settled
What kinds of trouble episodes occur and which institutions take them up, as a short narrative. What is never seen (judge, vote, sanction), from the model's `absent` list, with its basis.

## 5. The cases in full
Open with one or two sentences saying why these cases were chosen and what each one shows (in terms of the agents' institutions, not our process).
Then one subsection per dossier: the case as the dossier reconstructed it, with its timeline, its transcripts and its "what this case shows". Edit for length and plain language. Use the dossier's facts wherever they differ from the shorter notes, but tell only the corrected story: don't say there was an earlier version or what it got wrong (that goes in section 7).

## 6. Conclusions: what the trouble cases tell us
Follow the strict rules above. Each conclusion with its basis and strength. Then **"What we cannot conclude, and what would settle it"**: one list, each item with why not and what evidence would settle it. Include here things the data hints at but cannot settle. This is the only place for open questions.

## 7. Method and limits
How the data was read, how the model was built and tested, in plain words. The checks that ran: the scan audit, the model tests (each round, and what changed between rounds), and what the full reconstruction of the cases corrected in the shorter readings (one line per case). **If the human declined further refinement, a plain list of where the model is known to be wrong**, from the last test results. The limits and their measured size (including that episodes are formed by code and are approximate, and any gaps in reading). Costs.
```
