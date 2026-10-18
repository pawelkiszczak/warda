<!-- markdownlint-disable-file MD041 -->
## What

Closes #NNN. One or two sentences: what the change does for the user of Warda.

## Behaviour change

- New/changed commands, flags, config keys, API fields or hook outputs (exact names):
- Default behaviour unchanged? yes / no — if no, why:

## How to try it

```bash
# the shortest command sequence a reviewer can run on a laptop
```

## Tests

- New/changed test files and what each pins:
- [ ] `uv run pytest -q` passes; slow tests (`WARDA_SLOW=1`) run if touched

## Checklist

- [ ] Definition of done items in the issue are all met (or the task file was updated in this PR)
- [ ] Docs from the issue's Documentation section updated; `AGENTS.md` / `README.md` if commands or layout changed
- [ ] Shadow mode never changes agent behaviour; enforce mode fails closed (service/hook changes only)
- [ ] No payload text written to logs by default (service/hook changes only)
- [ ] Project card moved to *Review*
- [ ] No real personal data, work data or secrets
- [ ] `uv run pre-commit run --all-files` passes

## Manual test result

Paste the output of the issue's manual test.
