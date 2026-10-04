# Design notes

Decisions from planning on 3 Oct, with the reasoning behind each, plus the questions still open. Update this file when a decision changes.

## Decisions

**Package it as a skill.** A future swarm chaser drops the folder into their agent and points it at their data. `SKILL.md` stays short and keeps the model on rails: run the scripts in order, and never freelance an answer from skimming. The method itself (codebook, questionnaire) is mostly careful writing. The machinery (scripts) is built by Claude Code to spec. If the scripts run out of time, the method alone is still a usable skill.

**Events are for storage; conversations are for analysis.** A single message rarely shows an institution. A decision is a sequence: proposal, objection, settlement. So we store the finest grain (one message or action per event) and derive conversations from it. Evidence still cites individual message IDs.

**Triage uses a small model, not keywords.** Keyword search misses institutional moments that are phrased plainly. The small model reads each whole conversation and answers one concrete question. It is told to say yes when unsure, because a wrongly rejected conversation is lost evidence that no one ever sees. We measure misses by having the big model read a random sample of 30–50 rejects. The miss rate goes in the briefing.

**Look for trouble cases first** (Llewellyn & Hoebel). "Trouble" includes:
- disagreement over what to do
- competing claims to a task or resource
- accusations of breaking a rule
- blame after a failure
- refusing an instruction
- being overruled
- coordination breaking down

Known blind spot: institutions that never get tested (a leader always obeyed, a division of labor that never breaks) produce no trouble. A later pass over routine cooperation can cover those. Until then, the briefing states this limit.

**Categories are discovered from the data, not fixed in advance** (inductive coding). Describe, then induce, then apply. Fixing the categories up front would force the swarm into our guesses. A large "other" bucket means the categories need to be induced again.

**Evidence goes everywhere.** Notes carry their own excerpts and message IDs. No model reads a summary without the evidence beside it.

**The briefing is self-contained.** It has these parts:
1. Summary
2. Institutional map (each claim with a count, a percentage and evidence tags)
3. Evidence entries with the excerpted exchanges
4. Open questions
5. Method and limits

Each pattern claim shows 2–3 of the clearest examples and the IDs of the rest, plus a counterexample **when a good one helps** (it shows where a pattern stops); otherwise none, to save space. (Changed 4 Oct from "at least one counterexample", which Lukas judged gimmicky.) Format: Markdown.

**Step 0 is a universal converter (decided 3 Oct, 15:15).** Don't hand-write an adapter for each dataset. The first sub-skill converts any dataset itself:
1. *Profile* (code): a file inventory, field statistics and random samples. The model sees a compact profile, not the raw data.
2. *Interpret* (model): writes a **dataset card**. What is one message here, who is the speaker, what makes a conversation, what reply cues exist, what is noise, and which dataset-specific fields to keep. Uncertainties are flagged, not guessed.
3. *Generate the adapter* (model writes code) into the target format.
4. *Validate*: code checks the format and coverage (rows converted, rows dropped and why). Then the model compares random converted conversations side by side with their raw source. If this fails, revise and rerun.
5. *Hand off*: the transcripts, the dataset card and a conversion report. The card and report feed the briefing's method and limits section.

The target format is a small required core (`event_id`, `dataset`, `conversation_id`, `actor`, `timestamp`/`order`, `kind`, `content`) plus an open `extra` object for dataset-specific fields. The wiki's signature name, `page_family` and removed-lines hints would go in `extra`. The core never grows to fit a dataset.

Testing: (a) the German wiki, scored against the hand inspection in `data-inspection-german-wiki.md`; (b) AI Village, a format not seen before; (c) if time allows, a third dataset such as the Swarm Traces JSONL, to show it really is universal.

**Decided (3 Oct, 15:23): the converter pauses after writing the dataset card, shows it to the human and waits for approval before generating the adapter.** The human can approve, correct individual answers, or reject it. The approved card, with any corrections noted, is saved with the run and quoted in the briefing's method and limits section. A dataset card has about eight questions: what this is, what one message is, who is speaking, what makes a conversation, how replies work, what is noise, what else is worth keeping, and what is uncertain.

**Decided while building the converter (3 Oct, evening).** The full spec is in `skill-prototype/codebook/event-format.md`.
- **The core `kind` stays generic: `message` or `action`.** Dataset-specific kinds (the wiki's relay, edit and admin) go in `extra.subkind`. This keeps the core the same for every dataset.
- **`in_reply_to` is in the core, but only for explicit reply fields.** It is a generic idea, and the adapter never infers replies.
- **Every event carries `extra.source_ref`** (raw file and line). This is what lets one validator compare converted events with their raw source on any dataset.
- **The adapter accounts for every source row** in `coverage.json`, as converted or dropped with a reason. The validator recounts the raw files on its own, so nothing goes missing silently.
- **The profiler is standard-library Python.** No pandas, so it runs anywhere. Parquet needs pyarrow (`uv run --with pyarrow`).
- **The card step may run small counting checks** when the profile can't settle a question that changes the adapter. Each check is recorded in the card.

**Decided (3 Oct, late): link dumps are shortened, never skipped.** A rule to skip link-heavy edits at triage was tested and rejected. It would have hidden:
- 2,888 messages with real sentences, including the counter-signalling rules (written as sentences with URLs inside) and public error confessions
- 82% of the overwrite trouble hints
- short signal posts, which no word-count rule can catch

In the wiki, links are part of the institutions: counter URLs carry the signal itself, and links between pages are how agents point to fallback pages. Instead:
- **Shorten, don't skip.** Before a model reads a conversation, long URLs become short tags (domain plus the start of the path). That cuts the wiki's message text by 54%. The events file keeps full URLs, so citations stay exact.
- **Relay-page edit wars are counted by code first:** who overwrote whom, how often, and whether anyone restored. Models then read sampled windows with that count in view, instead of all 2,000+ relay edits on `WillkommenImWiki`.
- **(Proposed, adapter v2):** extract links between wiki pages into a structured field, for the segmenter and the page network.

**Decided (3 Oct, late): the converter knows what it's for.** `convert/SKILL.md` now opens with "Purpose and stance". The events feed an investigation of the swarm's social order, so the converter preserves evidence rather than cleaning data. Noise is a judgement made with that purpose in mind: in swarms, links can be signals, overwrites can be conflicts, short posts can be protocol messages, and repeats can be conventions spreading. The rules:
- drop only for structural reasons
- flags describe and never filter
- shrink rather than exclude
- ask what social act something could be, and test it
- state the cost of every flag
- when in doubt, it's evidence

The card template's noise question now asks "what social act could this be?" and requires a sampled check.

**The noise check samples by risk, not only at random.** Testing the new step on the flawed `link_share` rule showed that a random sample of 20 flagged events contained no social talk, because the rules and confessions are about 1% of the flagged set. So `validate.py --noise-flag` now:
- counts the signs of social content under each flag (sentence-like lines, overwrite hints, signatures)
- samples the sentence lines separately

That version caught the problem: two counter-signalling rules in the first 20 lines, and 42% of all overwrite hints under the flag.

**Decided (3 Oct, late): the skill stays dataset-neutral.** Skill files (`skill-prototype/`) contain no examples, field names or numbers from any particular dataset, because the skill has to work on sources it has never seen. The validator takes a dataset's hint fields as arguments (`--hint-field`) instead of building in one adapter's field names. Lessons from specific datasets live in `docs/` and the run folders. The skill carries only the general rule.

**Decided (3 Oct, late): triage labels everything, and a budget limits only how deeply cases are read.**
- **Triage reads every conversation**, with URLs shortened. For each one it records:
  - trouble or not (still tuned to say yes when unsure)
  - the type of trouble, from the list above
  - **how much it reveals about institutions:** is a settlement visible? (a rule invoked, an appeal to precedent or authority, a decision, a sanction or correction)
  - the event IDs where the trouble and the settlement happen
  - whether it refers to events outside the conversation
- **Selection is done by code under a token budget** set by the human:
  - first, cover every type of trouble, every larger group and every time period
  - then take cases in order of settlement score
  - plus a random slice (15–20%)
- **The best cases are always read closely.** The budget can only cut cases from the middle and the bottom of the ranking, never the top.
- **Code and the model check each other.** Strong code-computed trouble hints on a conversation that triage rated low send the case to deep reading.
- **No early stopping ("saturation") by reading order.** Considered and rejected: the result would depend on the order cases were read in, and rare institutions could be missed. Instead, **induce reads all the notes at once**. If they don't fit, the model induces separately on 2–3 random halves, merges the results, and reports how well the halves agreed.
- **Apply tags every trouble case**, reading the conversation itself rather than a summary. The tagger can **escalate** a case that fits no category, or that shows an institution unusually clearly. Escalated cases are then described properly, and the categories are revised once. So every trouble case is read by a model at least twice: once at triage, once at tagging.
- **The random slice measures how good triage's ranking is.** If random cases turn out as revealing as top-ranked ones, the ranking is weak, and the briefing says so.
- **Counts always cover the whole population.** The briefing says which claims rest on all cases and which on the closely read sample.

**Decided (3 Oct, late): case assembly, because trouble can span conversations.** This is a new step between selection and describe. For each selected case, it builds a **case file** of quoted excerpts with event IDs, drawn from the whole dataset:
1. **Code finds candidates using an index built once over all events:**
   - the same actors (labels and claimed signatures) nearby in time
   - explicit references (links, @-mentions, names of other conversations)
   - rare shared terms (distinctive tokens in the case that appear in only a few other conversations; rarity is computed by code, so no word lists are needed)
   - activity just before and just after the case
2. **The big model directs a follow-up search.** It lists what is still unexplained ("who is X?", "what earlier decision is cited?", "what happened next?"). Code searches all events and returns excerpts with surrounding context. At most 2 rounds, with a cap on excerpts per case.
3. **The model picks the relevant excerpts.** Each one records how it was found (which actor, reference, term or question), so the trail can be checked.

**A case is its own unit, separate from a conversation.** Assembled cases that share evidence events are merged by code, and the merge is recorded. Tagged-only cases carry a "continues elsewhere" flag, plus a code check for shared actors and rare terms. The briefing reports trouble counts before and after merging.

The page-links field proposed for wiki adapter v2 is dropped. The general index covers references between conversations on any dataset.

**Decided (3 Oct, late): what models read (the segmenter's "reading view").** Every event is shown with its event ID, time, actor and kind. Nothing is left out; text is shrunk in three ways, each counted in the segment report:
- **Long URLs are shortened** to the site, the path, and up to 3 query parameters with short values. Keys and page names usually sit in the path. The full URL stays in the events file and the index.
- **Long runs of pure link lines are shortened.** Every line with words in it is kept, plus at least one line for each distinct link target, plus the first three and the last line of the run. The rest is replaced by a count. On the wiki this hid about 42,000 link lines and lost no distinct target.
- **Context events** repeated at the start of a split conversation's later part are capped at a short excerpt.

On the wiki, these cut the reading text from about 4.3M to 2.8M tokens. Large conversations are split at their longest pauses. Every event belongs to exactly one part (checked by code).

**References between conversations** are found by name matching. A name that is also a common word across the dataset (in more than 25 conversations) doesn't count, because it can't tell us which conversation is meant.

**Decided (3 Oct, late): we chase trouble *between the agents*.** This is now the opening principle of `codebook/trouble-rubric.md`. What we want is friction in the agents' relations with one another, and how they handle it among themselves. Trouble with the outside world (admins, operators, the platform, tools) matters when agents react to it, or when it changes how they deal with each other.

**Why it came up:** the first triage pilot (`outputs/2026-10-03_german-wiki_triage-pilot-v1/`) labelled pages that an admin deleted with no reaction inconsistently. Two subagents marked all 34 such units as trouble; a third marked all 24 of its units as not trouble. That swung the trouble rate between about 30% and 65%.

**The fix:** such outside actions are labelled the same way every time (trouble, `outside_authority`, settlement 1), so they stay countable. A new triage field, `between_agents`, records how far the trouble is between agents:
- `none`: no agent-to-agent dimension
- `one_sided`: one agent acts on or against another, with no reply
- `exchanged`: agents respond to each other

The selection step uses this field, so cleaned-up pages are counted but don't crowd out real disputes. The settlement score now rates how the *agents* handled the trouble; an automatic system message is not an explicit reason.

**Learned from the first full run (3 Oct, night).**
- **Triage cost is mostly per-subagent overhead, not reading.** Each subagent used 60–100k tokens whether its batch held 3 units or 60. 136 batches used a whole Pro session. Next time, pack tiny units into much bigger batches (about 200), so there are fewer subagents.
- **Apply only needs to read cases with something between agents.** Triage already labels the "outside action, nobody reacted" cases in one fixed way, so they are counted as one category straight from triage. On the wiki that cuts apply from 4,133 cases to about 1,024.
- **Describe uses the triage label as a reading guide** (key event IDs plus a short explanation), with the evidence still in view.
- **Selection:** a cap per group on top-score cases needs a meaningful tie-break. "Most actors" dropped the clearest cases, so the cap was removed for this run. Run select-v4 took all 75 settlement-3 cases, plus 10 for coverage and 15 random: 100 cases. (v2 and v3 are marked superseded.)
- **Models:** Sonnet for triage (labels were consistent after the rubric fix); Opus for describe, at the human's choice.
- **Subagents sometimes wrote their labels out with a script.** Code checks catch format and ID errors, and an audit of all "no trouble" labels against code-computed trouble hints found no misses.

**Decided (4 Oct, early): how apply reads, and what it counts.** Lukas chose: group split troubles (yes), tag from key events only (no).
- **Count troubles, not segments (new step: `plan_apply.py`).** The segmenter splits long conversations so they fit a reader. That split must not multiply a trouble in the counts. When at least 3 neighbouring parts of one conversation get identical triage labels, they form one **trouble group**. The group is tagged once, from one representative part read in full (a part that describe read, if any). Parts whose labels differ stay separate and are read on their own, so a rule proposal, truce or admin intervention inside a long dispute is not lumped in. Patterns code can count (who overwrote whom) are counted by code. The briefing reports both counts: troubles and parts. On the wiki this gives 9 groups covering 154 parts, mostly the relay-page edit war, and leaves 879 units to read.
- **Apply reads every case in full. No windowed reading.** Rejected: tagging large cases from triage's key events only. It would make apply re-read triage's choices instead of giving an independent second reading, so it could not catch what triage missed or got wrong. Describe found triage's key events off by one in places and its "blame" type overused.
- **Group tags are checked:** where describe read other members of a group, code compares their notes with the group's tags, and a disagreement splits the group.
- **Cost preview before each model step:** code estimates text plus overhead per subagent. The human sets one total budget at the start; the agent goes ahead on its own within it and asks only when a step would exceed it.
- **Keep independent audit samples:** the random slice in describe, and a sample of triage's rejects, always get a full reading.

**Considered (4 Oct): fold the tagging (apply) into describe? No, with one future option.** The categories don't exist until induce has read all the describe notes, so describe can't tag with them. Merging would mean fixing the categories in advance, which is the deductive approach the design rejects. Describe also reads only the sample, while apply covers every trouble case with something between agents. And keeping interpretation (describe) apart from counting (apply, tagging against written definitions) keeps the counts reproducible. **Future option:** on a second dataset of the same kind, or a later run of the same swarm, pass the earlier codebook to describe as an optional pre-tag. Induce would then only look for new categories.

**Decided (4 Oct, morning, after Lukas read the first briefing): trouble means someone responded.** The first briefing counted every triage candidate as trouble: 70% of its "troubles" were overwrites on link and test pages that nobody objected to. Under the trouble-case method, trouble needs a response: someone objects, corrects, chases, repairs, warns, apologises or proposes a rule. Triage still casts a wide net. At the counting stage (`aggregate.py --passive-handling`), cases whose only handling is "not addressed" or "admin cleanup only" become **routine practice**, reported separately with their own counts. On the wiki: 879 candidates gave 207 troubles and 672 routine cases.

**Decided (4 Oct, morning): the briefing is written for an outsider.** The first briefing assumed context the reader did not have, used pipeline jargon (units, parts, tags), and strung fragments of quotes into sentences. The new template (`codebook/briefing-template.md`) starts with an orientation (who, what task, where, why they talk, and a glossary of the agents' jargon). It keeps pipeline jargon out of sections 1–5, explains each institution before quoting it, and shows exchanges as transcripts, one speaker per line.

**Decided (4 Oct): code fills in who spoke and when in transcripts.** The case notes carry no timestamps, and a writer can confuse the name signed in the text with the account that posted. `check_brief.py --fix-transcripts` sets each transcript line's speaker and time from the event ID and lists every correction. In briefing v2, 2 names were corrected (one quote signed "Mar26OAI" was posted by another account).

**Decided (4 Oct): a deep dive before the briefing, plus sourced orientation and glossary.** Lukas asked earlier that, once a few important cases are picked, the process go back over the data and assemble the full picture. Case assembly only did that with capped excerpts, and describe's optional follow-up searches were used in just 4 of 100 notes. New step 9, `deepdive.py`: for the 4–6 cases the briefing tells in full, code gathers everything that bears on each one in one timeline across conversations (on the wiki, 113–496 events from 41–174 conversations per case). A strong model then reconstructs the case against required questions, with searches mandatory for open threads. Describe's searches are now required when something is unexplained. The briefing's orientation must name its sources (the dataset card now has a "setting" question; for the wiki, the hand inspection). Glossary entries must cite events where the term is used, checked by code.

**Decided (4 Oct, Lukas): the dossiers go into the briefing, and it ends with strict conclusions.** The deep-dive dossiers become the briefing's "cases in full" section. A new conclusions section says what we know about the society from the trouble cases. Each conclusion states its basis (counted across all troubles, seen in several cases, or one case) and its strength, and the section lists what cannot be concluded. No invented significance: no "remarkable/emergent/novel", no causal claims without evidence, no unsupported comparisons, and ordinary findings stated as ordinary. "We tolerate no false-impressive false-insight."

**Pipeline, draft 2:**
1. convert
2. segment (and build the index)
3. triage (all conversations)
4. select (code, under a budget)
5. assemble case files
6. describe
7. induce (all notes at once)
8. apply (all trouble cases, with escalation)
9. aggregate (code)
10. brief

## Draft event shape (v1; superseded for the wiki by v2 in `data-inspection-german-wiki.md`)

| Field | Purpose |
|---|---|
| `event_id` | A stable ID. Every citation points to one. |
| `dataset` | Which source the event came from. |
| `actor` | The raw name, as given. Agents rename themselves: Swarm Traces found 7,905 names among roughly 1,200 agents. Merging identities is a stretch goal. |
| `timestamp` | May be empty. |
| `order` | A guaranteed sequence, for when timestamps fail. |
| `in_reply_to` | An event ID, if one is known. On the OpenAI-style boards this has to be inferred from conventions like `zzR_X_TO_Y` and `zzANSWER<handle>`. |
| `kind` | `message` or `action`. |
| `content` | The text, or a description of the action. |

## Open questions

1. **What does the data actually look like?** German wiki: done, see `data-inspection-german-wiki.md`. AI Village: still pending.
2. **Cost.** Big model preferred; Lukas will spend some credits. Test on a slice first.
3. **Segmenting AI Village.** Split on time gaps or topic changes. Are computer-use turns included?
4. **Oversized conversations.** Split them, keeping the evidence.
5. **Institutions only visible across all notes** (also the cross-conversation problem). If the notes don't fit in one read, use the historians' approach: a **saturation loop** (induce categories from growing samples until no new categories appear, then apply them to everything) plus **per-agent records** (prosopography: the roles, orders and disputes recorded for each agent). Slicing by time also shows change over time.
6. **Change over time.** One snapshot, or periods?
7. **The baseline.** Which model, how much raw data, which exact questions.

## Stretch goals (not in draft 1)

- A second, independent tagging run, with the agreement rate reported
- Merging renamed agents into single identities
- A routine-cooperation pass to find the untested institutions

## Evaluation plan (sketch)

- **Answer key:** the METR/Redwood "Coordination norms and technologies" findings. A good run on comparable data should surface things like HOLD/VETO/owner conventions, veto countdowns, appeals to precedent, and identity or signing fixes after impersonation.
- **Baseline:** the same questions given to a frontier model with as much raw data as fits. Compare coverage, accuracy, citations and hallucinations.
- **Filter recall:** the measured miss rate from the reject sample.

## Reading

- Merry, Canfield & Wright, "Law: Anthropological Aspects" (overview)
- Morris, "Anthropology and Legal Realism," *Alabama Law Review* (2022): the trouble-case method summarized
- Holleman, "Trouble-Cases and Trouble-Less Cases" (*Law & Society Review*): the blind spot
- Gluckman, "Limitations of the Case-Method in the Study of Tribal Law"
- Swarm Traces (swarmtraces.org): a model of evidence-heavy reporting

## Decided (3 Oct, Lukas): the briefing tells what happened, not how we found out

Briefing v3 opened its full cases with "these cases were rebuilt… the rebuilding corrected the shorter case notes", and ended each case with "What the full reconstruction corrected". The reader never saw the case notes, so this is talk about our own process. Cause: the template said "keep what the dossier corrected", which read as "tell the story of the correction". **Fix (template and SKILL.md):** sections 1–7 never mention our working documents or steps (case notes, dossiers, reconstruction, earlier versions). Cases are told in their corrected form. What the deep dive corrected goes in the method section, one line per case, as evidence that rebuilding from all the data matters.

## Decided (3 Oct, Lukas): "What we cannot conclude" and "Open questions" merge into one list

In briefing v3 the two sections repeated each other (whether the last answer ends a run, whether agreed answers were right, how many agents there were). They are two sides of one question. **Fix (template):** the conclusions section ends with one list, "What we cannot conclude, and what would settle it". Each item gives the tempting conclusion, why the data does not support it, and what evidence would settle it. There is no separate open-questions section; method and limits becomes section 7.

## Decided (3 Oct, Lukas): the method-facts file is a defined step; "How the society works" opens with an overview

- **Method facts.** The briefing's orientation, glossary context and method section come from `method-facts.md`. In the wiki run it was written by hand, and the skill never said how. A fresh run could skip it and give a thin orientation. **Fix:** the template defines its format (context, data, how the study ran, checks, deep dive, limits, cost), every fact tagged with its source. SKILL.md step 10 says to write it first.
- **Overview.** Section 3 now opens with one plain paragraph on how the society works as a whole, before the subsections, so a reader who stops there has the right picture.

## Decided (3 Oct, Lukas): work out "what even is this" early, from real messages

The dataset card's setting answer came from a profile (fields and a few rows), and on the wiki the real understanding came from Lukas reading about 90 lines by hand. A fresh run has no such reading. **New converter step 6, "Setting":** `sample_setting.py` picks about 80 messages spread over time, conversations and actors (half from conversations with several actors), a few short exchanges, and a summary of non-message events. A fresh subagent reads only that and `codebook/setting-instructions.md`, and writes `setting.md` with every statement cited and marked observed, inferred or guess, plus open questions. The human corrects it.

**Tested blind** (`outputs/2026-10-03_german-wiki_setting-test-v1/score.md`). Both runs got the core right: AI agents doing timed multi-round lookup tasks, the wiki as a link relay and as a board between cohorts, why the cohorts relay (those behind depend on those ahead), and that it looks like an evaluation, kept as an inference. The first sampler missed the administrator entirely because it only showed messages. Adding non-message events fixed that. Neither reached the specific institutions (counter signals, the fear that the final answer ends the run), which is the later steps' job.

**Built (3 Oct, Lukas: "Yes, do it"):**
- **The setting travels with every reading step.** `scripts/context.py` takes the setting's summary, the human's corrections and the vocabulary (about 1k tokens). Triage, assemble (case files), induce (notes view), apply and the deep dive put it at the top of every batch with `--setting`, labelled "context, not evidence: don't cite it; say so if what you read contradicts it". It costs about 4% of a triage batch.
- **The setting is updated once, after induce.** The induce model already reads every note, so in the same pass it writes `setting-update.md` (corrections, the actors' beliefs about their situation, roles, outsiders, new vocabulary), every line with event IDs. It is appended to the setting in the induce run folder. Apply, the deep dive and the briefing's method facts use that version. This is where facts like "the agents believed the final answer ends the run", which a small early sample cannot reach, enter the context.

## Decided (4 Oct): changes the first fresh test run made to the skill

The fresh run on AI Village era 1 (`../swarm-test-run-1/`) edited its own copy of the skill in five places. All five were reviewed and taken into `skill-prototype/`, two of them reworded:
- **`validate.py` reads gzipped files.** A plain bug: the source was `.jsonl.gz`. Taken as is.
- **`check_brief.py` recognises plain UUID event IDs.** Without this, the checker silently skipped every event ID on a dataset whose IDs are UUIDs, so nothing was checked. Taken as is.
- **`apply.py --shuffle-seed`** (optional): spreads units across batches, so neighbouring parts of one conversation are not read side by side and blurred together. Off by default. Taken as is.
- **Trouble rubric: "reported trouble counts too."** Agents often describe trouble afterwards (retrospectives, complaints, status reports naming a blocker, a rule made because something went wrong) instead of enacting it in view. Pilot 1 missed these; pilot 2 found 67 troubles in 97 pieces instead of 44 in 83. Taken, but the test run's examples were quotes from the AI Village data, so they were replaced with generic wording (the skill stays dataset-neutral). Added: a report is a claim, not proof; later steps look for the trouble itself.
- **Trouble rubric: cite IDs only from the unit being read, never from the background block.** The readers had copied event IDs from the setting background block. Taken, and the cause fixed: `context.py` now strips event IDs from the background block, so there is nothing to copy.

## Decided (4 Oct, Lukas): triage runs on Sonnet, never Haiku

The fresh AI Village run used Haiku 4.5 for triage, because the skill only said "a smaller model". 381 of 1,087 labels (35%) failed the code checks and had to be redone. On the wiki, Sonnet's labels almost all passed. **SKILL.md now names the models:** Sonnet for triage and apply; Opus for induce, deep dive, brief and the setting reading; either for describe. If the budget is short, triage a sample with Sonnet rather than everything with Haiku.

## Decided (4 Oct, Lukas): one easy-to-find report folder

The fresh test run left 14 run folders in `outputs/`, and the readable result was buried in one of them. **New final step, "Report"** (`scripts/render_report.py`): it writes `report/<dataset>-v<N>/` at the project root with only what a person reads: the briefing as `.md`, as one self-contained web page (`.html`, contents list, citations shown small, links to the cases) and as a `.pdf` (printed by a headless Chrome-family browser if installed), plus `cases/` with the full deep-dive write-ups. **The deep dives are included as separate files, not inside the PDF:** the briefing already tells each case in short, and the full write-up is there for anyone who wants every step. The working files stay in `outputs/` as the audit trail. Standard library only; never overwrites (a new vN each time).

## Decided (4 Oct, Lukas): a tested model of the society replaces counting everything

**Why.** The appraisal of the first AI Village run found that about 85% of the tokens (the Haiku scan plus classifying every piece) bought the least reliable output: counts with unknown error. The two Haiku pilot runs agreed on trouble-or-not for only 55 of 77 pieces. When Sonnet re-read pieces Haiku had marked "no trouble", it reversed 97 of 99. The deep dive found the earlier labels wrong in every case. The count was also of pieces, not troubles, and was dominated by tool failures and repetition loops that are not between agents. What we want is: (1) the trouble cases that give the most insight, and (2) a gears-level model of how the society works. Neither needs every piece classified.

**The new pipeline (SKILL.md steps 2–9):**
- **Scan** (Sonnet, every piece): a gate (something went wrong between agents, or with others acting on the space, and someone responded), a strict 0–3 "reveals" score, one line naming the trouble, and routine problems labelled as such (`tool_failure`, `repetition_loop`, `outside_action_unanswered`, `lone_mishap`), so they no longer count as trouble.
- **Scan audit** (Opus, 40 random labels): the scan's error rate, with ranges.
- **Episodes** (code): pieces that are the same trouble are merged, so everything counts troubles, not pieces. Joins are deliberately conservative (cross-conversation joins need a shared actor and a shared rare term); episodes are approximate and the briefing says so.
- **Close reading** centred on mechanism: trigger, procedure, who ran it, what backed it, how it ended, what changed after.
- **Build the model** (Opus): institutions as mechanisms, each with 2–3 predictions that could fail ("when X, then Y"), a map of how they connect, and what is absent.
- **Test the model** (Sonnet on random episodes the model was not built from): holds / fails / not applicable, counted by code with 90% ranges, and an overall verdict (well / partly / poorly). **These test results are the briefing's numbers.**
- **Refinement loop (Lukas):** if the model maps the society only partly or poorly, the orchestrator writes down what failed and **asks the human** whether to refine and retest. If yes, Opus revises the model from the failures and it is retested on a **fresh** random draw (reusing the same episodes would only test whether it memorised its failures). If no, the run carries on and the briefing states where the model is known to be wrong.
- **Counter-cases only when necessary (Lukas):** a deep dive goes to a counter-case only if it changes a conclusion or clearly shows where an institution stops. Failed predictions are always reported.

**Dropped:** classifying every piece (`apply.py`), its planning step (`plan_apply.py`), the full counting tables (`aggregate.py`), the second pilot unless the first is inconsistent, and Haiku. The one useful check from the counting step, whether top-ranked cases reveal more than random ones, now comes from the notes (`induce.py prepare` writes `notes-summary.json`).

**Expected cost on AI Village era 1:** about 14–17M tokens instead of about 35M. Most of the remainder is the Sonnet scan, which is kept because it is what finds the rare cases.

**Code-checked, not yet run with models:** the new scripts were run end to end on stand-in data (the wiki's old scan labels converted to the new format, a made-up two-prediction model and made-up verdicts). Draws avoid the cases the model was built from, a second round draws entirely fresh episodes, and event IDs are checked. On that data the ranking check reproduced the wiki's figures (75 of 75 top cases vs 2 of 15 random ones showing a norm). Lukas will design the first real test.

## Decided (4 Oct): lessons from the first draft-3 run (AI Village era 2, first 25 days)

The run (`../swarm-test-run-2/`, report in its `report/ai-village-v4/`) worked as designed:
- **Cost:** Sonnet scan, scan audit (gate right 35 of 40), 69 episodes, 20 cases read closely, a model of 6 institutions with 12 predictions, two test rounds, 5 deep dives. About 7.2M subagent tokens. Per message read, that is roughly a third cheaper than the old pipeline.
- **Honesty:** the briefing is model-first and plainly honest about what was and was not tested ("treat the picture as plausible, not well tested").

**What went wrong, and the fixes:**
- **The test pool ran out.** Round one drew 43 of the 49 unseen episodes, so the refinement round had 6 episodes and could judge only 2 of 10 predictions. Code still rated that round "well". **Fixes in `test_model.py` and SKILL.md:** a round uses at most half the unseen episodes by default (`--pool-share`); the overall verdict is "cannot tell" when fewer than half the predictions could be judged; and the question to the human about refining must say how many unseen episodes are left, and whether more data would be needed for a meaningful further round.
- **Draws often missed the situation** ("the random picks mostly missed it") for predictions whose triggers were only scan types. A known weakness: triggers with good `terms` aim better. Left to the model instructions for now.
- **The ranking check did not separate cases** here (top 11 of 11 vs random 5 of 5 showed a rule or procedure): on a short, scoped stretch with a strict gate, almost every episode is revealing. Not a bug; the briefing reported it.

**Changes the run made to the skill, adopted:**
- `profile.py`: a crash on a field with no fill rate (`s.get`). A plain bug fix.
- `briefing-template.md`: explain the testing in plain words before the first test result, define any term used for it, and write the limits in sections 1–6 for a new reader (what was done and what it means), with no method shorthand.

## Decided (4 Oct, Lukas): every prediction on every drawn episode, plus coverage

**Was:** a separate targeted draw per prediction, picked by the scan's trouble types or terms. **Now** (`test_model.py draw --mode all`, the default): each round draws a random sample of unseen episodes and judges **every** prediction on each, plus one coverage question ("is something going on here that none of the institutions explains?"). Then, only for predictions with fewer than 5 applicable episodes, a targeted top-up (`--mode topup`) adds episodes where their trigger may occur.

**Why (Lukas's idea):**
- It tests whether the model maps the society at all. Coverage is the share of random trouble episodes no institution explains, and the readers' notes say what is missing. That is material for the refinement round.
- It shows how common each institution is in random trouble episodes, which per-prediction draws cannot.
- It removes a bias: episodes the scan mislabelled were never tested before.
- Co-occurrence tests the model's map (which institutions fire together).
- Each episode read informs every prediction, so the small unseen pool goes further.

**Kept:** the round cap (at most half the unseen pool per phase), the "cannot tell" verdict, and the targeted mode (`--mode targeted`) for comparison. Coverage, how common each institution is, and co-occurrence are computed only from the random sample, never from top-up episodes.

**On whether the era-2 round-two model was better than round one:** the test cannot say. Round two judged only 2 predictions on 6 episodes, one of them unchanged from round one. Dropping a failed prediction raises the hold rate without showing improvement, and the deep dives still found errors in the revised version. It is probably a more accurate description, but that is not demonstrated.

Code-checked on stand-in data: both phases, the manifest records which batches are random and which are top-up, and coverage counts only the random ones.
