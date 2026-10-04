# troublecase (skill)

Maps the institutions an AI agent swarm built for itself, from any multi-agent transcript dataset. It finds the trouble episodes that reveal most, builds a mechanism-level model of how the society works, tests that model on random episodes, and writes a checked briefing. `SKILL.md` has the method and run order.

```
SKILL.md                     method, steps, models, limits
convert/SKILL.md             step 0: any dataset -> events file + setting
codebook/
  dataset-card.md            the card the converter fills in (human approves)
  event-format.md            the common event format
  setting-instructions.md    what is this dataset, really? (fresh reader)
  trouble-rubric.md          the scan: gate, reveals score, routine problems
  scan-audit-instructions.md checking a random sample of scan labels
  describe-questionnaire.md  close reading, centred on mechanisms
  model-instructions.md      building (and revising) the model of the society
  test-instructions.md       judging the model's predictions on random episodes
  deepdive-instructions.md   reconstructing a case across all the data
  briefing-template.md       the briefing and its strict conclusions
scripts/                     pure code, Python standard library
  profile.py, validate.py    converter: profile the raw data, check the conversion
  sample_setting.py          spread sample for the setting reading
  segment.py                 conversations -> readable pieces + index
  context.py                 the setting's background block for every batch
  triage.py                  the scan: pack batches, check labels
  audit_scan.py              scan audit: draw, tally with ranges
  episodes.py                merge pieces of the same trouble into episodes
  select_cases.py            pick episodes for close reading
  assemble.py                case files across conversations; search; quote check
  induce.py                  notes view + ranking check; model check
  test_model.py              draw random episodes per prediction; tally results
  deepdive.py                gather everything bearing on a case
  check_brief.py             check quotes, IDs, numbers, glossary; fill speakers
  render_report.py           report/ folder: briefing as .md, .html, .pdf, cases
```
