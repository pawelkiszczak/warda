"""Lint the task catalogue in docs/issues/ and mirror it to GitHub issues through the `gh` CLI.

    uv run python scripts/issues_sync.py lint
    uv run python scripts/issues_sync.py sync [--repo OWNER/NAME] [--dry-run] [--only P0-01,P0-02]

The markdown files are the source of truth. `sync` creates missing labels and milestones, creates issues for files
whose `github_issue` is 0 (writing the new number back into the file), then rewrites every issue's title, body,
labels and milestone from its file so dependency links resolve to issue numbers.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ISSUES_DIR = Path(__file__).resolve().parents[1] / "docs/issues"
DEFAULT_REPO = "pawelkiszczak/warda"

SECTIONS = [
    "## Context",
    "## Scope",
    "## Deliverables",
    "## Definition of done",
    "## Automated tests",
    "## Documentation",
    "## Manual test (human, before the PR)",
]
RESERVED = ["## Dependencies", "## Team / hardware / estimate"]

TEAMS = [
    "coordination",
    "data-general",
    "data-decision",
    "labelling",
    "research",
    "benchmarks",
    "model",
    "tools",
    "gdpr",
]
TYPES = ["feature", "infra", "data", "experiment", "docs", "decision"]

LABELS: dict[str, tuple[str, str]] = {
    **{f"phase:{n}": ("5319e7", f"Phase {n} of the team plan") for n in range(6)},
    **{f"team:{t}": ("0e8a16", "Owning team") for t in TEAMS},
    **{f"type:{t}": ("1d76db", "") for t in TYPES},
    **{f"gate:{n}": ("b60205", f"Feeds gate {n}") for n in range(1, 5)},
    "hardware:laptop": ("c2e0c6", "Any laptop, 8–16 GB, no GPU"),
    "hardware:strong": ("fbca04", "Mac ≥ 64 GB or NVIDIA ≥ 24 GB (generation); Mac 96–128 GB or rented GPU (training)"),
    "hardware:cloud": ("e99695", "Rented GPU (RunPod/Lambda/vast.ai) or free Kaggle/Colab hours"),
}

HARDWARE_TEXT: dict[str, str] = {
    "laptop": "Any laptop (8–16 GB RAM, no GPU). Everything in this task runs on CPU; no shared machine needed.",
    "strong": (
        "Strong machine for the full run (Mac ≥ 64 GB or NVIDIA ≥ 24 GB for generation; Mac 96–128 GB or a rented GPU "
        "for training; see `docs/team/HARDWARE.md` and `scripts/queue.sh`). The CPU `--limit` smoke path still has to "
        "work on a laptop and is part of the definition of done."
    ),
    "cloud": (
        "Rented or free cloud GPU (ADR-0005). Budget approved by the coordinator before the run; the CPU smoke path "
        "still has to work on a laptop."
    ),
}

MILESTONES = [
    "Phase 0 — Kick-off (weeks 1–2)",
    "Phase 1 — Data and trials (weeks 2–6)",
    "Phase 2 — Base training and service skeleton (weeks 6–10)",
    "Phase 3 — Decision training and gates 2–3 (weeks 10–13)",
    "Phase 4 — Integrations (weeks 13–16)",
    "Phase 5 — Shadow mode and gate 4 (weeks 16–20)",
]

ID_RE = re.compile(r"^P[0-5]-\d{2}$")
KEYS = ("id", "title", "labels", "milestone", "depends_on", "estimate_hours", "hardware", "github_issue")


@dataclass(frozen=True)
class Issue:
    id: str
    title: str
    labels: list[str]
    milestone: str
    depends_on: list[str]
    estimate_hours: float
    hardware: str
    github_issue: int
    body: str
    path: Path

    @property
    def phase(self) -> int:
        return int(self.id[1])


def parse_issue(path: Path) -> Issue:
    lines = path.read_text(encoding="utf-8").split("\n")
    marks = [i for i, line in enumerate(lines) if line == "+++"]
    if len(marks) < 2 or marks[0] != 0:
        raise ValueError(f"{path}: missing +++ front matter")
    meta = tomllib.loads("\n".join(lines[1 : marks[1]]))
    missing = [k for k in KEYS if k not in meta]
    if missing:
        raise ValueError(f"{path}: missing key(s) {', '.join(missing)}")
    if not ID_RE.match(meta["id"]):
        raise ValueError(f"{path}: id {meta['id']!r} does not match P<phase>-<nn>")
    if not path.name.startswith(f"{meta['id']}-"):
        raise ValueError(f"{path}: filename must start with {meta['id']}-")
    if meta["hardware"] not in HARDWARE_TEXT:
        raise ValueError(f"{path}: hardware {meta['hardware']!r} not in {sorted(HARDWARE_TEXT)}")
    return Issue(
        id=meta["id"],
        title=meta["title"],
        labels=list(meta["labels"]),
        milestone=meta["milestone"],
        depends_on=list(meta["depends_on"]),
        estimate_hours=meta["estimate_hours"],
        hardware=meta["hardware"],
        github_issue=int(meta["github_issue"]),
        body="\n".join(lines[marks[1] + 1 :]).strip(),
        path=path,
    )


def load_all(directory: Path = ISSUES_DIR) -> list[Issue]:
    return sorted((parse_issue(p) for p in directory.glob("P*.md")), key=lambda i: i.id)


def labels_for(issue: Issue) -> list[str]:
    return [*issue.labels, f"hardware:{issue.hardware}"]


def _cycles(issues: list[Issue]) -> list[str]:
    graph = {i.id: list(i.depends_on) for i in issues}
    state: dict[str, int] = {}  # 1 = on stack, 2 = done
    found: list[str] = []

    def visit(node: str, stack: list[str]) -> None:
        state[node] = 1
        for dep in graph.get(node, []):
            if dep not in graph:
                continue
            if state.get(dep) == 1:
                found.append(" -> ".join([*stack[stack.index(dep) :], dep]))
            elif dep not in state:
                visit(dep, [*stack, dep])
        state[node] = 2

    for node in graph:
        if node not in state:
            visit(node, [node])
    return found


def lint(issues: list[Issue]) -> list[str]:
    ids = [i.id for i in issues]
    errors: list[str] = [f"duplicate id {dup}" for dup in sorted({x for x in ids if ids.count(x) > 1})]
    known = set(ids)
    phase_of = {i.id: i.phase for i in issues}
    for issue in issues:
        tag = issue.id
        for label in issue.labels:
            if label.startswith("hardware:"):
                errors.append(f"{tag}: label {label} is reserved (derived from the hardware field)")
            elif label not in LABELS:
                errors.append(f"{tag}: unknown label {label}")
        if issue.milestone not in MILESTONES:
            errors.append(f"{tag}: unknown milestone {issue.milestone!r}")
        else:
            phase = MILESTONES.index(issue.milestone)
            if f"phase:{phase}" not in issue.labels or phase != issue.phase:
                errors.append(f"{tag}: phase label/id must match milestone {issue.milestone!r}")
        if sum(label.startswith("team:") for label in issue.labels) != 1:
            errors.append(f"{tag}: needs exactly one team:* label")
        if sum(label.startswith("type:") for label in issue.labels) != 1:
            errors.append(f"{tag}: needs exactly one type:* label")
        for dep in issue.depends_on:
            if dep not in known:
                errors.append(f"{tag}: unknown dependency {dep}")
            elif phase_of[dep] > issue.phase:
                errors.append(f"{tag}: depends on later-phase issue {dep}")
        lines = issue.body.split("\n")
        positions = []
        for heading in SECTIONS:
            if heading in lines:
                positions.append(lines.index(heading))
            else:
                errors.append(f"{tag}: missing section {heading!r}")
        if positions != sorted(positions):
            errors.append(f"{tag}: sections out of order")
        errors.extend(
            f"{tag}: section {heading!r} is rendered by the sync; remove it" for heading in RESERVED if heading in lines
        )
    errors.extend(f"dependency cycle {c}" for c in _cycles(issues))
    return errors


def render_body(issue: Issue, numbers: dict[str, int]) -> str:
    deps = (
        "".join(f"- {dep} — #{numbers[dep]}\n" if numbers.get(dep) else f"- {dep}\n" for dep in issue.depends_on)
        or "- none\n"
    )
    team = next(label for label in issue.labels if label.startswith("team:")).removeprefix("team:")
    estimate = f"{issue.estimate_hours:g}"
    return (
        f"{issue.body}\n\n## Dependencies\n\n{deps}"
        f"\n## Team / hardware / estimate\n\n- Team: {team}\n"
        f"- Hardware: `{issue.hardware}` — {HARDWARE_TEXT[issue.hardware]}\n- Estimate: {estimate} h\n"
        f"\n<!-- synced from docs/issues/{issue.path.name} by scripts/issues_sync.py; edit the file, not the issue -->\n"
    )


def gh(args: list[str], *, input: str | None = None) -> str:
    try:
        return subprocess.run(["gh", *args], check=True, capture_output=True, text=True, input=input).stdout
    except subprocess.CalledProcessError as e:
        raise SystemExit(f"gh {' '.join(args)} failed:\n{e.stderr}") from e


def ensure_labels(repo: str) -> None:
    existing = {
        row["name"] for row in json.loads(gh(["label", "list", "--repo", repo, "--limit", "200", "--json", "name"]))
    }
    for name, (color, description) in LABELS.items():
        if name not in existing:
            gh(["label", "create", name, "--repo", repo, "--color", color, "--description", description])
            print(f"label created {name}")


def ensure_milestones(repo: str) -> dict[str, int]:
    rows = json.loads(gh(["api", f"repos/{repo}/milestones?state=all&per_page=100"]))
    numbers = {row["title"]: row["number"] for row in rows}
    for title in MILESTONES:
        if title not in numbers:
            row = json.loads(gh(["api", f"repos/{repo}/milestones", "-f", f"title={title}"]))
            numbers[title] = row["number"]
            print(f"milestone created {title}")
    return numbers


def write_number(path: Path, number: int) -> None:
    text = path.read_text(encoding="utf-8")
    path.write_text(re.sub(r"^github_issue = \d+$", f"github_issue = {number}", text, count=1, flags=re.M), "utf-8")


def sync(repo: str, issues: list[Issue], dry_run: bool, only: set[str] | None = None) -> None:
    selected = [i for i in issues if only is None or i.id in only]
    numbers = {i.id: i.github_issue for i in issues}
    if dry_run:
        print(f"would ensure {len(LABELS)} labels and {len(MILESTONES)} milestones on {repo}")
    else:
        ensure_labels(repo)
        ensure_milestones(repo)
    for issue in selected:
        if issue.github_issue:
            continue
        title = f"[{issue.id}] {issue.title}"
        if dry_run:
            print(f"would create {issue.id} {title}")
            continue
        args = ["issue", "create", "--repo", repo, "--title", title, "--body-file", "-", "--milestone", issue.milestone]
        for label in labels_for(issue):
            args += ["--label", label]
        url = gh(args, input=render_body(issue, numbers)).strip()
        number = int(url.rsplit("/", 1)[1])
        numbers[issue.id] = number
        write_number(issue.path, number)
        print(f"created #{number} {issue.id} {issue.title}")
    for issue in selected:
        number = numbers[issue.id]
        if dry_run:
            if number:
                print(f"would update #{number} {issue.id} {issue.title}")
            continue
        args = ["issue", "edit", str(number), "--repo", repo, "--title", f"[{issue.id}] {issue.title}"]
        args += ["--body-file", "-", "--milestone", issue.milestone, "--add-label", ",".join(labels_for(issue))]
        gh(args, input=render_body(issue, numbers))
        print(f"updated #{number} {issue.id} {issue.title}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("lint", help="validate docs/issues/")
    sync_p = sub.add_parser("sync", help="create/update labels, milestones and issues on GitHub")
    sync_p.add_argument("--repo", default=DEFAULT_REPO)
    sync_p.add_argument("--dry-run", action="store_true")
    sync_p.add_argument("--only", help="comma-separated issue ids")
    args = parser.parse_args(argv)

    issues = load_all()
    errors = lint(issues)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    if args.command == "lint":
        print(f"ok: {len(issues)} issues")
        return 0
    only = set(args.only.split(",")) if args.only else None
    sync(args.repo, issues, args.dry_run, only)
    return 0


if __name__ == "__main__":
    sys.exit(main())
