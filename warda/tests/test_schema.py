"""Contract tests: the shared literals in `warda.schema` match `pii_gen` and the decision record shape."""

import dataclasses

import pytest

from pretrain.harness import pii_gen
from warda.schema import ACTIONS, CHANNELS, DEST_CLASS, DEST_CLASSES, INBOUND_CHANNELS, Decision, DecisionInput, Policy


def test_actions_order_matches_action_text_positions() -> None:
    for lang in ("pl", "en"):
        assert list(pii_gen.ACTION_VERB[lang]) == list(ACTIONS)
        assert len(pii_gen.ACTION_TEXT[lang]) == len(ACTIONS)


def test_destination_class_values_are_destination_classes() -> None:
    assert set(DEST_CLASS.values()) <= set(DEST_CLASSES)


def test_pii_gen_channels_are_channels() -> None:
    assert set(pii_gen.CHANNELS) <= set(CHANNELS)
    assert set(pii_gen.INBOUND) <= set(INBOUND_CHANNELS)


def test_decision_keys_exact() -> None:
    assert set(Decision.__required_keys__) == {"action", "confidence", "reason", "redacted_payload", "category"}
    assert not Decision.__optional_keys__


def test_policy_and_input_validate_their_fields() -> None:
    policy = Policy(
        id="strict",
        language="pl",
        text="Polityka danych",
        table={"credential": dict.fromkeys(DEST_CLASSES, "block")},
    )
    DecisionInput(payload="x", channel="git_commit", destination="saas", policy=policy, language="pl")
    with pytest.raises(ValueError, match=r"policy\.table action"):
        Policy(id="p", language="pl", text="t", table={"credential": {"internal": "yolo"}})
    with pytest.raises(ValueError, match=r"input\.channel"):
        DecisionInput(payload="x", channel="carrier_pigeon", destination="saas", policy=policy, language="pl")
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.language = "de"  # type: ignore[misc]  # a validated record must not bypass __post_init__
