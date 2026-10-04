# Scan rubric (step 2: scan)

You are reading conversations from a multi-agent dataset: messages and actions by AI agents (and sometimes humans) who share a space. The purpose of the whole study is to map the **social order these agents built for themselves**: who leads, what roles exist, what rules they follow, how they signal to each other, and above all **how they settle trouble**.

We use the trouble-case method from legal anthropology. Institutions show themselves most clearly when something goes wrong and has to be settled. Your job is to find the trouble, and to say how much each case reveals about how the society works. Your labels decide which cases get read closely, and which cases the model of the society is later tested on.

## The principle: we are chasing trouble *between the agents*

What we want is friction in the agents' relations **with one another**, and how they handle it **among themselves**: who acts against whom, who objects, who gives way, who apologises, who invokes a rule, who decides. That is where their own institutions show.

Trouble with the outside world (an admin, an operator, the platform, a broken tool) matters **when agents react to it, or when it changes how they deal with each other**: they warn each other, move elsewhere, blame someone, or set up a fallback. An outside action that no agent responds to is still recorded (see below), but it is not what we are looking for. The same goes for a lone agent's mishap that nobody else touches.

You read each conversation unit **in full**. You are not summarising it for someone else to decide on: your labels decide what gets read closely later, and a conversation you wrongly mark as "no trouble" is evidence nobody will see again. **When unsure, say yes.**

## What counts as trouble (the gate)

`trouble: true` means: **something went wrong between agents, or between agents and others acting on the space, and at least one agent responded to it** (objected, corrected, chased, repaired, warned, apologised, refused, invoked a rule, decided, proposed a rule). This is the gate: only these cases are candidates for close reading and for testing the model. **When unsure whether the gate is passed, say yes.**

Any sign that agents' aims, claims or expectations collided, or that something went wrong and had to be dealt with. For example:

| Type | Looks like |
|---|---|
| `disagreement` | agents disagree about what is true or what to do |
| `competing_claims` | two or more agents claim the same task, resource, space, name or role |
| `rule_breach` | someone is accused of, or admits to, breaking a rule, protocol or instruction |
| `blame` | fault is assigned after a failure, including blaming oneself |
| `refusal` | an instruction or request is refused or ignored on purpose |
| `overruled` | a decision or contribution is overridden, reverted, deleted or replaced by someone else |
| `coordination_breakdown` | a shared plan, signal or protocol fails, is misread, or collides |
| `outside_authority` | an outside party (an admin, an operator, the platform) intervenes, or agents respond to one |
| `identity_trouble` | impersonation, disputed identity, or confusion about who said what |
| `other` | trouble that fits none of these; describe it |

**Content that looks mechanical can still be social.** A link, code or token can be a signal. Removing or overwriting someone else's content can be a conflict, even when the content is just links. A very short post can be a protocol message. A correction, a warning or an apology can sit inside an otherwise technical post. If the unit shows that an event removed or replaced another actor's content, treat that as possible `overruled` or `competing_claims` trouble, and say whether anything in the unit suggests it was deliberate or contested.

**Reported trouble counts too.** Agents often describe trouble instead of enacting it in view: a retrospective or reflection on something that went wrong, a complaint about another agent, a status report naming a blocker another agent caused, a rule or protocol introduced *because* something went wrong, a lesson written down. Mark these as trouble, with the type of the trouble reported, and set `refers_elsewhere: true`. A report is a claim, not proof that it happened as told: `between_agents` describes the reported trouble, and later steps look for the trouble itself. A unit whose overall tone is smooth can still contain one such line: judge every message, not the general mood.

**Problems that are not trouble between agents: label them, don't pass them through the gate.** Record these in `also`, with `trouble: false`, unless agents argued over them or one held another responsible (then the gate is passed, and they are labelled with an ordinary trouble type):
- `tool_failure`: a tool, platform or account fails, and agents only report it, retry, or help each other with the fix.
- `repetition_loop`: an agent (or several) repeats near-identical messages or actions.
- `outside_action_unanswered`: an outside party acts (deletes, edits, posts) and no agent reacts.
- `lone_mishap`: one agent's mistake that nobody else touches.

These are counted as routine practice, not as trouble. Helping each other with a tool failure is not trouble between agents; blaming someone for it, arguing over the fix, or making a rule because of it is.

## How much is between the agents

| Value | Meaning |
|---|---|
| `none` | no agent-to-agent dimension: an outside action nobody reacts to, or a lone agent's mishap nobody else touches |
| `one_sided` | one agent acts on or against another (overwrites, deletes, accuses, overrides, claims) with no visible reply from the other side |
| `exchanged` | agents respond to each other about the trouble: reply, object, restore, correct, apologise, argue, warn, invoke a rule, decide |

## How much it reveals: the `reveals` score

Score what the case shows about **how the society works**: its rules, procedures, roles, signals, and who has authority. Not how dramatic it is.

| Score | Meaning |
|---|---|
| 0 | no trouble (the gate is not passed) |
| 1 | trouble with a response, but nothing about how things are done becomes visible (a one-off reply, a fix, a thank-you) |
| 2 | a way of doing things becomes visible but is not stated: a role is acted out, a procedure is followed, an authority is deferred to without comment |
| 3 | it is **explicit**: a rule, procedure, role or authority is stated, invoked, contested, made, changed or enforced; a decision is announced and justified; a sanction, confession or formal correction is made |

Score the clearest moment in the unit, not the average. Be strict with 3: a unit where agents only report progress, help each other, or thank each other is at most 1, however friendly or busy it is. An automatic system message (a default edit summary, a log line) is not an explicit rule or reason.

## Also record

- **`key_event_ids`**: the event IDs (in square brackets in the text) where the trouble and the settlement happen. Copy them exactly, character by character, from the bracket directly above the event you mean, **inside the same unit**; never cite an ID from another unit or from the background block. 1–6 IDs.
- **`between_agents`**: `none`, `one_sided` or `exchanged`, as above. Use `none` when there is no trouble.
- **`refers_elsewhere`**: true if the unit points to events, people, rules or places outside itself (another page, thread or channel, an earlier decision, an outside counter or tool, "as agreed before").
- **`trouble_line`**: when `trouble` is true, one plain line naming the trouble (who, what, about what), e.g. "two agents claim the same task; the coordinator assigns it". Empty string otherwise.
- **`also`**: any of `tool_failure`, `repetition_loop`, `outside_action_unanswered`, `lone_mishap` present in the unit, whether or not the gate is passed. Empty list if none.
- **`why`**: one or two sentences saying what happened, citing event IDs. Quote a few words where it helps. No speculation beyond the text.

## Output format

One JSON object per unit, one per line (JSONL), exactly these fields:

```json
{"unit_id": "<as given in the unit header>", "trouble": true, "types": ["competing_claims"], "reveals": 3, "between_agents": "exchanged", "key_event_ids": ["<id>", "<id>"], "refers_elsewhere": false, "trouble_line": "<one line>", "also": ["tool_failure"], "why": "<1-2 sentences citing event IDs>"}
```

- `trouble` is `true` or `false` (the gate). If you are unsure, use `true` and say why in `why`.
- `types` is empty when `trouble` is false.
- `reveals` is 0 exactly when `trouble` is false; `between_agents` is then `"none"` and `trouble_line` is `""`.
- `key_event_ids`: 1–6 IDs when `trouble` is true, or when `also` is not empty; otherwise may be empty.
- Every unit in your batch gets exactly one line, in the order given.
