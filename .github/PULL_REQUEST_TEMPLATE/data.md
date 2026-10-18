<!-- markdownlint-disable-file MD041 -->
## What

Closes #NNN. Which dataset, set or policy this adds or changes, and why.

## Data

| | Value |
|---|---|
| Dataset / version | e.g. `harness_pii v2`, `handwritten v1` |
| Rows added / removed / changed | |
| Split counts (train / dev / cal / test / test_ood) | |
| Languages (pl / en) | |
| Generator or authoring commit | |
| Command that rebuilds it | |

## Quality

- Labelling: who labelled, how many items double-labelled, Cohen's kappa (category / action):
- Confirm rate against generated gold (verification rounds):
- Known noise or open disagreements:

## Checklist

- [ ] Every person, company, identifier and secret is fictional; authors checked for their own employers' names
- [ ] Each committed file ≤ 500 KB; large outputs stay in `pretrain/work/` (gitignored)
- [ ] Licence of every source recorded (corpus changes)
- [ ] No `case_id` or payload text shared across splits (split-integrity test passes)
- [ ] Dataset card / manifest / `docs/bench/PROTOCOL.md` set version updated
- [ ] Task file updated if scope changed; project card moved to *Review*
- [ ] `uv run pre-commit run --all-files` passes

## Manual test result

Paste the spot-check from the issue's manual test (item ids and verdicts, no payload text if it could be sensitive).
