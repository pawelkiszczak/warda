<!-- markdownlint-disable-file MD041 -->
## What

Closes #NNN. The question this run answers, in one sentence.

## Setup

| | Value |
|---|---|
| Config / model size | |
| Data version + commit | |
| Hardware (machine, RAM, GPU) and wall time | |
| MLflow run name(s) | |
| Seed(s) | |

Reproduce:

```bash
# exact command(s); include the CPU --limit smoke variant
```

## Results

| Run / decider | Set | accuracy | macro-F1 | leak_recall_public | false_block_rate | ECE | coverage@1% |
|---|---|---|---|---|---|---|---|
| baseline (`tier1` / `always_allow`) | | | | | | | |
| this run | | | | | | | |

Metric definitions: `docs/bench/PROTOCOL.md`. Report `n` for every set.

## Conclusion

What we now believe, what we do next, and whether a gate or ADR changes.

## Checklist

- [ ] Report under `docs/model/` or `docs/bench/` updated with the numbers above and links to `report.json` / `eval.json`
- [ ] Weights and large artefacts stay out of git (paths + SHA-256 recorded instead)
- [ ] CPU `--limit` smoke still runs on a laptop
- [ ] Task file updated if scope changed; project card moved to *Review*
- [ ] `uv run pre-commit run --all-files` passes

## Manual test result

Paste the issue's manual test output.
