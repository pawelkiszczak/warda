"""Turn the decision-item formats the labelling app accepts into one view for the UI.

Three formats share the closed vocabularies in `warda/schema.py`:

- `pii_gen` items: `state` (policy block, a blank line, then the call), `question`, `options`, `gold`, `category`,
  `action`.
- Brama rows (P0-11/P0-12): decider fields `policy`, `channel`, `destination`, `task`, `provenance`, `facts`,
  `payload` (with `{kind:key}` identifier placeholders) and the author's draft gold `gold_action`, `acceptable`,
  `gold_category`, `tier`, `clause`, `protected`, `rationale`, plus contrast-group metadata (`group`, `role`,
  `twin_of`, `track`, `scenario`, `use_case`).
- Handwritten rows (P1-10): like Brama, with `policy_id` instead of `policy`.

Policies are Markdown files; Brama's carry TOML front matter between `+++` lines (`id`, `name`, `clauses`).
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

from warda.schema import ACTIONS, CATEGORIES, DEST_CLASS

PLACEHOLDER = re.compile(r"\{([a-z_]+):([A-Za-z0-9_.]+)\}")
SILENCE = "silence"  # Brama's clause value when the policy does not settle the case
CONTEXT_FIELDS = ("channel", "destination", "task", "provenance")
REVIEW_META = (
    "track",
    "group",
    "role",
    "twin_of",
    "scenario",
    "use_case",
    "language",
    "tier",
    "split",
    "question_id",
    "template_id",
    "source",
    "author",
)
# Blind labelling (Brama R-08) hides everything that hints at the author's gold: role and track name the expected
# outcome (`safe_twin`, T8 restraint), so only the language stays.
BLIND_META = ("language",)


def load_policies(directory: Path | None) -> dict[str, dict[str, Any]]:
    """Policy id -> name, Markdown text and declared clause ids. Files without front matter use their stem as id."""
    if directory is None or not directory.is_dir():
        return {}
    policies = {}
    for path in sorted(directory.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        meta: dict[str, Any] = {}
        text = raw
        if raw.startswith("+++\n"):
            front, sep, body = raw[4:].partition("\n+++\n")
            if sep:
                meta, text = tomllib.loads(front), body
        policy_id = str(meta.get("id", path.stem))
        policies[policy_id] = {
            "id": policy_id,
            "name": str(meta.get("name", policy_id)),
            "text": text.strip(),
            "clauses": [str(c) for c in meta.get("clauses", [])],
        }
    return policies


def load_ids(path: Path | None) -> dict[str, str]:
    """Placeholder -> fictional value from a Brama ids sidecar (`{"values": {...}}`). Unknown ones stay visible."""
    if path is None or not path.is_file():
        return {}
    values = json.loads(path.read_text(encoding="utf-8")).get("values", {})
    return {str(k): str(v) for k, v in values.items()}


def resolve(text: str, ids: dict[str, str]) -> str:
    return PLACEHOLDER.sub(lambda m: ids.get(m.group(0), m.group(0)), text)


def unresolve(text: str, ids: dict[str, str]) -> str:
    """Map resolved values back to their placeholders, so marked spans compare with the gold's `protected`."""
    for placeholder, value in sorted(ids.items(), key=lambda kv: -len(kv[1])):
        text = text.replace(value, placeholder)
    return text


def segments(text: str, ids: dict[str, str]) -> list[dict[str, Any]]:
    """The payload as plain runs and placeholder runs, so the UI can mark identifiers without parsing them again."""
    out: list[dict[str, Any]] = []
    pos = 0
    for match in PLACEHOLDER.finditer(text):
        if match.start() > pos:
            out.append({"text": text[pos : match.start()]})
        placeholder = match.group(0)
        out.append({"text": ids.get(placeholder, placeholder), "placeholder": placeholder, "kind": match.group(1)})
        pos = match.end()
    if pos < len(text):
        out.append({"text": text[pos:]})
    return out


def policy_id(item: dict[str, Any]) -> str | None:
    value = item.get("policy") or item.get("policy_id")
    return str(value) if value else None


def proposed(item: dict[str, Any], ids: dict[str, str]) -> dict[str, Any]:
    """The gold under review: Brama/handwritten `gold_*` fields first, then the generator's `category`/`action`."""
    category = item.get("gold_category") or item.get("category")
    action = item.get("gold_action") or item.get("action")
    acceptable = item.get("acceptable")
    return {
        "category": category if category in CATEGORIES else None,
        "action": action if action in ACTIONS else None,
        "acceptable": [a for a in acceptable if a in ACTIONS] if isinstance(acceptable, list) else [],
        "clause": str(item["clause"]) if item.get("clause") else None,
        "protected": [resolve(str(p), ids) for p in item.get("protected") or []],
        "tier": item.get("tier"),
        "rationale": item.get("rationale"),
    }


def labelled_text(item: dict[str, Any], ids: dict[str, str]) -> str:
    """The text a labeller can mark protected spans in: the resolved payload, or the whole state for `pii_gen`."""
    if item.get("state"):
        return str(item["state"]).partition("\n\n")[2] or str(item["state"])
    return resolve(str(item.get("payload", "")), ids)


def allowed_clauses(item: dict[str, Any], policies: dict[str, dict[str, Any]]) -> list[str]:
    policy = policies.get(policy_id(item) or "")
    return [*policy["clauses"], SILENCE] if policy and policy["clauses"] else []


def view(
    item: dict[str, Any],
    policies: dict[str, dict[str, Any]],
    ids: dict[str, str],
    by_id: dict[str, dict[str, Any]],
    blind: bool,
) -> dict[str, Any]:
    out: dict[str, Any] = {"id": str(item["id"]), "clauses": allowed_clauses(item, policies)}
    if item.get("state"):
        # pii_gen renders the policy first and separates it from the call context with one blank line.
        head, _, body = str(item["state"]).partition("\n\n")
        out |= {
            "kind": "state",
            "policy": {"id": item.get("policy"), "name": None, "text": head if body else "", "found": bool(body)},
            "body": body or head,
        }
    else:
        pid = policy_id(item)
        policy = policies.get(pid or "")
        context = [{"key": key, "value": str(item[key])} for key in CONTEXT_FIELDS if item.get(key)]
        destination = item.get("destination")
        if destination in DEST_CLASS:
            context.insert(2, {"key": "destination_class", "value": DEST_CLASS[str(destination)]})
        out |= {
            "kind": "record",
            "policy": {
                "id": pid,
                "name": policy["name"] if policy else None,
                "text": policy["text"] if policy else "",
                "found": policy is not None,
            },
            "context": context,
            "facts": item.get("facts") if isinstance(item.get("facts"), dict) else {},
            "payload": segments(str(item.get("payload", "")), ids),
        }
    options = item.get("options")
    gold = item.get("gold")
    out |= {
        "question": item.get("question"),
        "options": options if isinstance(options, list) else [],
        "gold": gold if isinstance(gold, int) and not blind else None,
        "proposed": None if blind else proposed(item, ids),
        "meta": {key: item[key] for key in (BLIND_META if blind else REVIEW_META) if item.get(key) not in (None, "")},
        "twin": None,
    }
    twin = by_id.get(str(item.get("twin_of")))
    if twin is not None and not blind:
        out["twin"] = {
            "id": str(twin["id"]),
            "role": twin.get("role"),
            "payload": resolve(str(twin.get("payload", "")), ids),
            "context": {key: twin.get(key) for key in (*CONTEXT_FIELDS, "policy", "facts")},
            "proposed": proposed(twin, ids),
        }
    return out
