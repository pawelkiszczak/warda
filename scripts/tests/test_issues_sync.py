from pathlib import Path

import pytest

from scripts import issues_sync
from scripts.issues_sync import MILESTONES, SECTIONS, Issue, lint, load_all, parse_issue, render_body

BODY = "\n\n".join(f"{heading}\n\ntext" for heading in SECTIONS)


def write_issue(directory: Path, issue_id: str, **overrides: object) -> Path:
    phase = int(issue_id[1])
    meta: dict[str, object] = {
        "id": f'"{issue_id}"',
        "title": '"A task"',
        "labels": f'["phase:{phase}", "team:tools", "type:feature"]',
        "milestone": f'"{MILESTONES[phase]}"',
        "depends_on": "[]",
        "estimate_hours": "4",
        "hardware": '"laptop"',
        "github_issue": "0",
    }
    meta.update(overrides)
    body = str(meta.pop("body", BODY))
    path = directory / f"{issue_id}-task.md"
    front = "\n".join(f"{key} = {value}" for key, value in meta.items())
    path.write_text(f"+++\n{front}\n+++\n\n{body}\n", encoding="utf-8")
    return path


def test_parse_issue_reads_front_matter_and_body(tmp_path: Path) -> None:
    issue = parse_issue(write_issue(tmp_path, "P1-02", depends_on='["P0-01"]', hardware='"strong"'))
    assert issue.id == "P1-02"
    assert issue.milestone == MILESTONES[1]
    assert issue.depends_on == ["P0-01"]
    assert issue.hardware == "strong"
    assert issue.github_issue == 0
    assert issue.body.startswith("## Context")


def test_parse_rejects_filename_id_mismatch(tmp_path: Path) -> None:
    path = write_issue(tmp_path, "P0-01")
    wrong = path.rename(tmp_path / "P0-02-x.md")
    with pytest.raises(ValueError, match="filename must start with P0-01-"):
        parse_issue(wrong)


def test_parse_rejects_unknown_hardware(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="hardware"):
        parse_issue(write_issue(tmp_path, "P0-01", hardware='"gpu"'))


def test_lint_flags_unknown_label_bad_order_and_cycle(tmp_path: Path) -> None:
    swapped = BODY.replace("## Context", "## TMP").replace("## Scope", "## Context").replace("## TMP", "## Scope")
    issues = [
        parse_issue(write_issue(tmp_path, "P0-01", labels='["phase:0", "team:tools", "type:feature", "bogus"]')),
        parse_issue(write_issue(tmp_path, "P0-02", body=swapped)),
        parse_issue(write_issue(tmp_path, "P0-03", depends_on='["P0-04"]')),
        parse_issue(write_issue(tmp_path, "P0-04", depends_on='["P0-03"]')),
    ]
    errors = lint(issues)
    assert "P0-01: unknown label bogus" in errors
    assert "P0-02: sections out of order" in errors
    assert any(e.startswith("dependency cycle") and "P0-03" in e and "P0-04" in e for e in errors)
    assert len(errors) == 3


def test_lint_rejects_dependency_on_later_phase(tmp_path: Path) -> None:
    issues = [
        parse_issue(write_issue(tmp_path, "P0-01", depends_on='["P1-01"]')),
        parse_issue(write_issue(tmp_path, "P1-01")),
    ]
    assert lint(issues) == ["P0-01: depends on later-phase issue P1-01"]


def test_lint_rejects_hardware_label_and_reserved_section(tmp_path: Path) -> None:
    issue = parse_issue(
        write_issue(
            tmp_path,
            "P0-01",
            labels='["phase:0", "team:tools", "type:feature", "hardware:laptop"]',
            body=BODY + "\n\n## Dependencies\n\n- none",
        )
    )
    errors = lint([issue])
    assert "P0-01: label hardware:laptop is reserved (derived from the hardware field)" in errors
    assert "P0-01: section '## Dependencies' is rendered by the sync; remove it" in errors


def test_lint_rejects_phase_milestone_mismatch(tmp_path: Path) -> None:
    issue = parse_issue(write_issue(tmp_path, "P0-01", milestone=f'"{MILESTONES[2]}"'))
    assert lint([issue]) == [f"P0-01: phase label/id must match milestone {MILESTONES[2]!r}"]


def test_render_body_appends_dependencies_and_footer(tmp_path: Path) -> None:
    issue = parse_issue(write_issue(tmp_path, "P1-01", depends_on='["P0-01", "P0-02"]', hardware='"strong"'))
    body = render_body(issue, {"P0-01": 7, "P0-02": 0})
    assert body.startswith(issue.body)
    assert "## Dependencies\n\n- P0-01 — #7\n- P0-02\n" in body
    assert "- Team: tools\n" in body
    assert "- Hardware: `strong` — Strong machine" in body
    assert "- Estimate: 4 h\n" in body
    assert "<!-- synced from docs/issues/P1-01-task.md" in body


def test_render_body_without_dependencies(tmp_path: Path) -> None:
    issue = parse_issue(write_issue(tmp_path, "P0-01"))
    assert "## Dependencies\n\n- none\n" in render_body(issue, {})


def test_repo_catalogue_lints_clean() -> None:
    issues = load_all()
    assert issues, "docs/issues/ has no issue files"
    assert lint(issues) == []


def test_sync_dry_run_makes_no_gh_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> str:
        raise AssertionError("gh called during dry run")

    monkeypatch.setattr(issues_sync, "gh", fail)
    path = write_issue(tmp_path, "P0-01")
    issues: list[Issue] = [parse_issue(path)]
    before = path.read_text(encoding="utf-8")
    issues_sync.sync("owner/repo", issues, dry_run=True)
    assert path.read_text(encoding="utf-8") == before


def test_sync_creates_then_edits_and_writes_number_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], str | None]] = []

    def fake_gh(args: list[str], *, input: str | None = None) -> str:
        calls.append((args, input))
        if args[:2] == ["label", "list"]:
            return "[]"
        if args[0] == "api" and len(args) == 2:
            return "[]"
        if args[0] == "api":
            return '{"number": 1}'
        if args[:2] == ["issue", "create"]:
            return f"https://github.com/owner/repo/issues/{40 + sum(c[0][:2] == ['issue', 'create'] for c in calls)}\n"
        return ""

    monkeypatch.setattr(issues_sync, "gh", fake_gh)
    first = write_issue(tmp_path, "P0-01")
    second = write_issue(tmp_path, "P0-02", depends_on='["P0-01"]')
    issues_sync.sync("owner/repo", [parse_issue(first), parse_issue(second)], dry_run=False)

    assert parse_issue(first).github_issue == 41
    assert parse_issue(second).github_issue == 42
    create = [c for c in calls if c[0][:2] == ["issue", "create"]]
    assert "hardware:laptop" in create[0][0]
    edits = [c for c in calls if c[0][:2] == ["issue", "edit"]]
    assert [c[0][2] for c in edits] == ["41", "42"]
    assert "- P0-01 — #41" in (edits[1][1] or "")
