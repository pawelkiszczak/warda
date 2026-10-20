from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Self, cast

import pytest
import requests

from pretrain.quality import fetch_lid

PAYLOAD = b"fake fastText model bytes " * 4
NAME = "lid.tiny.bin"


class FakeResponse:
    def __init__(self, chunks: list[bytes], error: Exception | None = None) -> None:
        self.chunks = chunks
        self.error = error

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int) -> Iterator[bytes]:
        yield from self.chunks
        if self.error is not None:
            raise self.error


class FakeSession:
    def __init__(self, response: FakeResponse | None) -> None:
        self.response = response
        self.urls: list[str] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.urls.append(url)
        if self.response is None:
            raise AssertionError("no request expected")
        return self.response


@pytest.fixture(autouse=True)
def tiny_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fetch_lid, "MODELS", {"tiny": (NAME, hashlib.sha256(PAYLOAD).hexdigest())})


def run(model_dir: Path, session: FakeSession) -> tuple[Path, bool]:
    return fetch_lid.fetch("tiny", model_dir, cast(requests.Session, session))


def test_verified_download_lands_in_place_with_no_partial_file(tmp_path: Path) -> None:
    session = FakeSession(FakeResponse([PAYLOAD[:10], PAYLOAD[10:]]))
    path, downloaded = run(tmp_path / "models", session)
    assert downloaded
    assert path == tmp_path / "models" / NAME
    assert path.read_bytes() == PAYLOAD
    assert list(path.parent.iterdir()) == [path]
    assert session.urls == [fetch_lid.BASE_URL + NAME]


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (FakeResponse([b"tampered bytes"]), ValueError),
        (FakeResponse([PAYLOAD[:10]], error=requests.ConnectionError("reset")), requests.ConnectionError),
    ],
    ids=["checksum-mismatch", "interrupted"],
)
def test_failed_download_installs_nothing(tmp_path: Path, response: FakeResponse, error: type[Exception]) -> None:
    with pytest.raises(error):
        run(tmp_path, FakeSession(response))
    assert list(tmp_path.iterdir()) == []


def test_valid_existing_file_is_kept_without_a_request(tmp_path: Path) -> None:
    (tmp_path / NAME).write_bytes(PAYLOAD)
    session = FakeSession(None)
    assert run(tmp_path, session) == (tmp_path / NAME, False)
    assert session.urls == []


def test_corrupt_existing_file_is_replaced(tmp_path: Path) -> None:
    (tmp_path / NAME).write_bytes(b"truncated")
    path, downloaded = run(tmp_path, FakeSession(FakeResponse([PAYLOAD])))
    assert downloaded
    assert path.read_bytes() == PAYLOAD
