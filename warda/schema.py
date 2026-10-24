"""Shared Warda vocabulary: the closed literal sets and the policy / decision-input records.

`pretrain/harness/pii_gen.py` imports its literals (`ACTIONS`, `CATEGORIES`, `DEST_CLASS`, `DEST_CLASSES`)
from here, so product code (`warda/`) and research code (`pretrain/`) cannot drift apart. The tuples are
ordered: positions are meaningful (option lines in prompts and question records).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypedDict, get_args

Action = Literal["allow", "redact", "ask_user", "block"]
ACTIONS: tuple[str, ...] = get_args(Action)  # derived, so the runtime tuple and the type cannot drift
CATEGORIES = (
    "none",
    "direct_pii",
    "quasi_identifying",
    "special_category",
    "credential",
    "confidential_business",
    "test_fixture",
)
DEST_CLASSES = ("internal", "client", "llm", "saas", "public")
DEST_CLASS: dict[str, str] = {
    "internal_repo": "internal",
    "internal_tracker": "internal",
    "internal_chat": "internal",
    "local_model": "internal",
    "client_repo": "client",
    "client_tracker": "client",
    "client_chat": "client",
    "llm_provider": "llm",
    "saas": "saas",
    "public_repo": "public",
    "public_search": "public",
    "public_package": "public",
}
CHANNELS = (
    "git_commit",
    "pr_description",
    "issue_comment",
    "chat_message",
    "http_post",
    "web_search",
    "llm_prompt",
    "code_comment",
    "log_event",
    "docs",
)
INBOUND_CHANNELS = ("sql_result", "file_read", "log_read")
LANGUAGES = ("pl", "en")


class Decision(TypedDict):
    """The typed decision a Warda decider must return."""

    action: Action
    confidence: float
    reason: str
    redacted_payload: str | None
    category: str | None


def _require_member(field_name: str, value: str, allowed: tuple[str, ...] | dict[str, str]) -> None:
    if value not in allowed:
        expected = ", ".join(allowed)
        raise ValueError(f"{field_name} {value!r} is not one of: {expected}")


@dataclass(frozen=True)
class Policy:
    """A data policy: rules per (category, destination class) plus written exception clauses."""

    id: str
    language: str
    text: str
    table: dict[str, dict[str, str]]  # category -> destination class -> action
    exceptions: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _require_member("policy.language", self.language, LANGUAGES)
        for category, rule in self.table.items():
            _require_member("policy.table category", category, CATEGORIES)
            for dest_class, action in rule.items():
                _require_member("policy.table destination class", dest_class, DEST_CLASSES)
                _require_member("policy.table action", action, ACTIONS)


@dataclass(frozen=True)
class DecisionInput:
    """One outbound item to decide on. No gold fields: gold lives only in training/eval records."""

    payload: str
    channel: str
    destination: str
    policy: Policy
    language: str
    task: str | None = None
    provenance: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.policy, Policy):
            raise TypeError(f"input.policy must be a Policy, got {type(self.policy).__name__}")
        _require_member("input.channel", self.channel, CHANNELS)
        _require_member("input.destination", self.destination, DEST_CLASS)
        _require_member("input.language", self.language, LANGUAGES)
