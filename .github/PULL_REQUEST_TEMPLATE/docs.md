<!-- markdownlint-disable-file MD041 -->
## What

Closes #NNN. Which documents change and why.

## Kind

- [ ] Guide / reference doc
- [ ] ADR (`docs/decisions/`) — status: proposed / accepted / superseded
- [ ] Gate record (`docs/gates/`) — outcome: PASS / FAIL
- [ ] Team doc (`docs/team/`)
- [ ] Task catalogue (`docs/issues/`)

## Approvals needed

List who must approve (ADR and gate records name their approvers in the file).

## Checklist

- [ ] Every number cites the report or file it comes from
- [ ] Links resolve; `README.md` "Contents" updated for new top-level docs
- [ ] Examples are fictional; no real names, clients or secrets
- [ ] Catalogue changes: `uv run python scripts/issues_sync.py lint` passes; `sync` run before merge
- [ ] Project card moved to *Review*
- [ ] `uv run pre-commit run --all-files` passes

## Manual test result

Paste the issue's manual test result (e.g. the second person's recomputation for a gate record).
