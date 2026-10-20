"""Root pytest configuration: the pytester plugin and the capability / opt-in skips."""

from __future__ import annotations

import importlib.util
import os

import pytest

pytest_plugins = ["pytester"]


def _in_ci() -> bool:
    return os.environ.get("CI", "").strip().lower() not in ("", "0", "false")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Skip gated tests whose prerequisite is missing.

    - ``requires_mlx``: MLX is not installed (non-Apple-Silicon platforms).
    - ``slow``: unless ``WARDA_SLOW=1``.
    - ``requires_lid``: no fastText LID model on disk, except under CI (``CI`` set), where the tests run and fail
      loudly instead of being silently skipped.

    All conditions are read here, at collection time, so the environment of the current session decides.
    """
    from pretrain.quality.textstats import FETCH_LID_COMMAND, lid_model_path

    skips: list[tuple[str, pytest.MarkDecorator]] = []
    if importlib.util.find_spec("mlx") is None:
        skips.append(("requires_mlx", pytest.mark.skip(reason="mlx is not installed on this platform")))
    if os.environ.get("WARDA_SLOW") != "1":
        skips.append(("slow", pytest.mark.skip(reason="set WARDA_SLOW=1")))
    if lid_model_path() is None and not _in_ci():
        skips.append(("requires_lid", pytest.mark.skip(reason=f"no fastText LID model; run `{FETCH_LID_COMMAND}`")))
    for item in items:
        for marker, skip in skips:
            if item.get_closest_marker(marker) is not None:
                item.add_marker(skip)
