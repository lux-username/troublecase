---
name: swarm-institutions
description: Map the institutions an AI agent swarm built for itself (roles, rules, signals, how trouble between agents is settled) from any multi-agent transcript dataset, as a working model of how the society works, tested on random cases, with an evidence-backed briefing in which every claim cites quoted, checkable evidence. Uses the trouble-case method from legal anthropology. Use when given a dataset of agents interacting (chat logs, boards, wikis, channels) and asked what social order they formed.
---

# Swarm institutions: from raw transcripts to an institutional briefing

## Purpose and stance

You are investigating the **social order a swarm built for itself**: who leads, what roles exist, which rules, protocols and signals it uses, and above all **how it handles trouble between agents**. The method is the **trouble-case method** (Llewellyn & Hoebel): institutions show most clearly when something goes wrong and has to be settled. So you look for trouble first, find the episodes that reveal most, read them closely, and build a **gears-level model** of the society: its institutions as mechanisms (what sets them off, who runs them, the steps, what backs them, how they fail). Then you **test the model's predictions on random episodes** it was not built from.

The two aims, and only what serves them:
1. **Find the trouble cases that give the most insight.**
2. **Build a tested, mechanism-level model of how the society works** and what its procedures and institutions are.

Counts serve these aims only as test results: "this prediction held in 14 of 18 random episodes". Nothing is classified or counted for its own sake.

Hard rules, everywhere:
- **Code counts; models read.** Every number in the briefing comes from code (test results, the scan audit, episode counts). No model estimates a count.
- **No model decides from a summary without the evidence in view.** Every claim cites event IDs, and quotes are checked word for word by code.
- **Preserve evidence; never filter it out.** Content that looks mechanical (links, tokens, overwrites, short posts) can be the social act itself. Shrink text when it is too long; never drop it. Flags describe; they never filter.
- **Between the agents.** The object is friction in the agents' relations with one another and how they handle it among themselves. Outside forces matter when agents react to them.
- **The model comes from the data**, not from expectations, and is tested on cases it was not built from.
- **Counter-cases only when necessary:** when one changes a conclusion or clearly shows where an institution stops. Failed predictions are always reported.
- **The skill stays dataset-neutral:** nothing here assumes a particular platform.

## Budget and cost preview

Ask the human **once, at the start**, for a budget (subscription session share or API spend). Before each model step, estimate its cost from the text to read **plus a fixed overhead per subagent** (often 60–100k tokens; it dominates when batches are small). Proceed on your own when a step fits the budget; ask only when it does not. Pack small units into large batches.

## Steps

Each step writes to a new run folder `outputs/<date>_<dataset>_<step>-v<N>/`. Never overwrite a previous run. Scripts are in `scripts/`; model instructions in `codebook/`.

**The setting travels with every reading step.** From the scan on, every script that packs text for a model takes `--setting <setting.md>` and puts a short background block at the top (the setting's summary, the human's corrections and the actors' vocabulary, with event IDs stripped), labelled as context, not evidence. Use the converter's approved setting until step 6, and the updated one after it.

**0. Convert** (sub-skill `convert/SKILL.md`). Profile the data with code, write a dataset card, **wait for human approval**, generate an adapter, validate against the raw data. Then the **setting**: code samples real messages spread across the data, a fresh reader (Opus) says who the actors are, what they are doing, what kind of situation they are in and why they interact, and the human corrects it. Output: one events file (core fields plus `extra`), `setting.md`, and a conversion report.

**1. Segment** — `scripts/segment.py`. Conversations become pieces a model can read (long ones split at their longest pauses); a reading view per piece (every event with its ID; long URLs and long runs of identical link lines shortened, never removed); an index of actors, references between conversations, and rare shared terms. Pass the dataset's hint fields (`--hint-field`, `--show-field`, `--alias-field`) named in the dataset card.

**2. Scan** — `scripts/triage.py pack|check`, rubric `codebook/trouble-rubric.md`. **Sonnet** reads **every** piece (it is what finds rare cases) and records: the gate (did something go wrong between agents, or with others acting on the space, and did someone respond? yes when unsure), types, a 0–3 **reveals** score (how much of a rule, procedure, role or authority becomes visible; strict with 3), one line naming the trouble, key event IDs, and routine problems that are not trouble between agents (`tool_failure`, `repetition_loop`, `outside_action_unanswered`, `lone_mishap`). Pack large batches (the per-reader overhead dominates small ones). Run one **pilot** (about 100 random pieces plus a few known cases) first; fix the rubric and rerun the pilot only if labels are inconsistent. Code checks every label.

**3. Audit the scan** — `scripts/audit_scan.py pack|tally`, instructions `codebook/scan-audit-instructions.md`. **Opus** re-checks 40 random scan labels against the text. Code reports how often the gate, the reveals score and the key events were right, with 90% ranges. If the gate or the reveals score is often wrong, tell the human before going on: the ranking rests on them.

**4. Episodes** — `scripts/episodes.py`. Code merges pieces that are the same trouble (neighbouring pieces with a shared actor; conversations that name each other with a shared actor and rare term; shared rare terms) into **episodes**, within a time window and a size cap. From here on everything counts episodes, not pieces.

**5. Select, assemble and read closely** — `scripts/select_cases.py --triage <episodes run>`, then `scripts/assemble.py build|search|check`, questionnaire `codebook/describe-questionnaire.md`. Pick episodes for close reading under the budget: the highest reveals scores, cases where code and scan disagree, variety across trouble types, groups and periods, and a **random slice** (it measures whether the ranking works). For each, code builds a case file with related excerpts from other conversations. A model (Sonnet or Opus) writes a note per case, centred on the **mechanism**: trigger, procedure, who ran it, what backed it, how it ended, what changed after. It must search when something important is unexplained. Code checks every quote word for word; redo any case that fails.

**6. Build the model** — `scripts/induce.py prepare|check`, instructions `codebook/model-instructions.md`. Code writes one view of all notes (plus the ranking check: do top cases show a rule or procedure more often than random ones?). **Opus** reads all notes at once and writes `model.json` / `model.md`: each institution as a mechanism, with 2–3 **predictions** ("when [trigger], then [what happens]") that could fail on a new case; a map of how institutions connect; what is absent. In the same pass it writes `setting-update.md`; append it to the setting under "Updates after close reading". Code checks the model.

**7. Test the model** — `scripts/test_model.py draw|tally`, instructions `codebook/test-instructions.md`. Two phases per round:
- **Random sample, every prediction** (`draw --mode all`, the default): code draws random unseen episodes (not the ones the model was built from, nor any drawn in earlier rounds), and **Sonnet** judges **every** prediction on each (holds, fails and what happened instead, or not applicable, with event IDs), plus one coverage question per episode: is something going on that none of the institutions explains? Then `tally`.
- **Top-up for rare institutions** (`draw --mode topup`, into the same test run): for predictions that met fewer than 5 applicable episodes, code draws targeted episodes where their trigger may occur; Sonnet judges those predictions; `tally` again.

**A round uses at most half of the unseen episodes** (`--pool-share 0.5`, the default, for each phase), so a refinement round still has fresh ones; use `--pool-share 1.0` only for a round you know is the last. Code counts per prediction with 90% ranges and flags failed predictions and triggers that rarely apply. From the random sample only, it also reports **coverage** (the share of random trouble episodes where no institution applied, and the readers' notes on what the model does not explain), **how common each institution is**, and **which institutions occur together** (a test of the map). It gives an overall verdict: the model maps the society **well**, **partly** or **poorly**, or **cannot tell** when fewer than half the predictions met 5 applicable episodes. "Cannot tell" is not a pass: report it as untested. Many uncovered episodes also count against the model, whatever its predictions did.

**If the model maps the society only partly or poorly:** write down which predictions failed and what the failed episodes show instead. Then **ask the human** whether to refine the model and test again, with the cost of one more round (one Opus revision plus a fresh draw) **and how many unseen episodes are left** (from the test results). If too few are left for the revised predictions to be judged (fewer than about 5 applicable per prediction), say so plainly: a further round would add little, unless more data is brought in (for example, scanning a further stretch of the dataset to make fresh episodes).
- **If yes:** Opus revises the model from the test results, including the coverage notes (`model-instructions.md`, "When revising"); the revised predictions get new IDs; test again on a **fresh** random draw (`--exclude-draws` every earlier test run). Ask again after each round; at most three rounds unless the human says otherwise.
- **If no:** carry on. The briefing reports the last test results and states plainly where the model is known to be wrong.

**8. Deep dive** — `scripts/deepdive.py`, instructions `codebook/deepdive-instructions.md`. For each main institution, take its clearest case; add a counter-case only when necessary (when one changes the conclusion or clearly shows where the institution stops); add any case the readers flagged as unusual. Usually 4–6 cases. For each, code gathers **everything** that bears on it, in one timeline across conversations (the whole conversation, conversations it names or that name it, every event with its rare terms, everything its agents wrote nearby in time under every name). **Opus** reconstructs the case, answers the required questions, and says whether the case works the way the model describes. Output: one dossier per case. If a dossier shows the model is wrong, say so in the briefing.

**9. Brief** — instructions `codebook/briefing-template.md`, check `scripts/check_brief.py`. First write `method-facts.md` (format in the template). **Opus** writes the briefing from the model, the test results, the scan audit, the episode counts, the notes, the dossiers and the method facts. It leads with how the society works (the map, then each institution: how it works and how well that held up when tested), tells the deep-dive cases as what happened (no mention of our earlier notes; corrections go in the method section), and ends with strict conclusions, each with its basis and strength, plus what cannot be concluded. Run `check_brief.py --fix-transcripts --counts test-results.json --counts audit.json --counts episodes-summary.json --facts method-facts.md`: code fills in each transcript line's speaker and time from the event data, then checks every quote, event ID, number and glossary term, and lists process words; fix anything that fails.

**10. Report** — `scripts/render_report.py --brief <brief run>/briefing.md --dossiers <deepdive run>/dossiers --name <dataset>`. Copies what a person reads into one folder at the project root, `report/<dataset>-v<N>/`: `briefing.md`, `briefing.html` (one self-contained web page with a contents list, linking to the full cases), `briefing.pdf` (printed by a headless Chrome, Chromium, Edge or Brave if one is installed; otherwise the script says so), and `cases/` (each deep-dive write-up as `.md` and `.html`). Everything else stays in `outputs/` as the audit trail. Tell the human the report folder's path first. If an Artifact or page-publishing tool is available, offer to publish `briefing.html` as a private page.

**11. Baseline (optional, for evaluation).** Give a frontier model as much raw data as fits and the same question, with no method; check its answer with the same code.

## Models

- **Scan and model tests: Sonnet.** They read the most text, and everything later rests on them. **Do not use Haiku** to save budget: on one test, 35% of Haiku's scan labels failed the code checks and had to be redone. If the budget cannot cover Sonnet on everything, scan a sample with Sonnet and say so, rather than everything with Haiku.
- **Setting reading, scan audit, building and revising the model, deep dive, brief: the strongest model** (Opus).
- **Close reading:** Sonnet or Opus. On one test, both were fully accurate, with Opus slightly sharper.

## What the briefing must state as limits

The scan audit (how often its labels were right, with ranges); that episodes are formed by code and are approximate; how the model was tested (rounds, episodes drawn) and, if refinement was declined, where it is known to be wrong; how identity was handled (names in text vs. account labels); artifacts that look like conflict; the sample behind close reading and the ranking check; institutions that never produce trouble (invisible to this method); anything dropped in conversion.
