# troublecase

*How AI swarms govern themselves, read from where things go wrong.*

**troublecase** is a Claude Code skill that maps the **institutions an AI agent swarm builds for itself**: who leads, what roles and rules exist, which signals and procedures the agents use, and above all **how they handle trouble between themselves**. Give it any multi-agent transcript dataset (chat logs, boards, wikis, channels) and it produces a briefing an outsider can read, in which every claim cites the messages it rests on.

Built for the AI Swarm Dynamics Hackathon (AI Village × Grove Research), October 2026.

## The method

The name comes from the **trouble-case method** from legal anthropology (Llewellyn & Hoebel, *The Cheyenne Way*, 1941): institutions show most clearly when something goes wrong and has to be settled. So the skill:

1. **Converts** any dataset into a common event format. A human approves a dataset card, and a fresh reader works out what the dataset actually is: who the agents are, what they are doing, and why they interact.
2. **Scans every conversation** for trouble between agents and scores how much each case reveals about rules, roles, procedures or authority. A second model audits a random sample of the scan, so its error rate is known.
3. **Reads the most revealing trouble episodes closely**, with material gathered from other conversations, and asks how each one *works*: what set off the response, the steps, who ran it, what made it stick, how it ended.
4. **Builds a mechanism-level model of the society**: its institutions, how they connect, what is absent. Each institution comes with predictions that could turn out false.
5. **Tests the model on random episodes it was not built from.** Every prediction is judged on every drawn episode, plus a check of what the model fails to explain. If the model maps the society poorly, the skill asks the human whether to refine and retest on fresh episodes; if not, the briefing says where the model is wrong.
6. **Reconstructs the key cases** from all the data, then writes the briefing: model first, then the cases in full, then strict conclusions that state their basis and what cannot be concluded.

Hard rules throughout: code does all counting; no model decides from a summary without the evidence in view; every quote, event ID and number in the briefing is checked by code; content that looks mechanical is never filtered out as noise.

## Install and run

```
mkdir my-study && cd my-study
mkdir -p .claude/skills data-inputs/raw
cp -R <this repo>/skill .claude/skills/troublecase
cp -R <your dataset> data-inputs/raw/<name>
claude
```

Then type `/troublecase`, or ask Claude Code to map the institutions in `data-inputs/raw/<name>`. The skill asks for a budget at the start and stops for your approval at a few points. The readable result lands in `report/<name>-v1/`: the briefing as Markdown, a self-contained web page and a PDF, plus the full case write-ups. Working files stay in `outputs/` as an audit trail.

Requirements: Claude Code with subagents (Sonnet and Opus); Python 3.9+, standard library only (`pyarrow` only for Parquet input); a Chrome-family browser for the PDF (optional).

## Status, honestly

- The pipeline has been run end to end on two datasets: a German wiki that AI agents used as a message board, and the AI Village. The second was a fresh, blind session that had only the skill and the data.
- The current design (a tested model instead of counting everything) has had one full run, on part of the AI Village. It produced a readable, honest briefing, and exposed a flaw in the testing step (too few fresh episodes left for a second round), which is now fixed. The newest test design (every prediction on every drawn episode, plus coverage) is code-checked but has not yet had a full run.
- [`docs/design-notes.md`](docs/design-notes.md) records every design decision, why it was made, and what each run taught us, including what went wrong.

## Layout

- `skill/SKILL.md`: the method and run order (start here)
- `skill/convert/SKILL.md`: the dataset converter sub-skill
- `skill/codebook/`: instructions for each model step
- `skill/scripts/`: pure-code steps (Python standard library)
- `docs/design-notes.md`: decisions and lessons

If you use AI Village data with this skill, follow AI Digest's research terms and cite AI Digest / AI Village.
