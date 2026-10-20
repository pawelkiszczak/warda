"""Download fastText's language-ID model into `textstats.MODEL_DIR`, verified against a pinned SHA-256.

    uv run python -m pretrain.quality.fetch_lid                 # lid.176.bin, ~126 MB (what textstats prefers)
    uv run python -m pretrain.quality.fetch_lid --variant ftz   # lid.176.ftz, ~917 KB (CI)

The file is streamed into a temporary file next to the target and moved into place only after the checksum matches,
so an interrupted or tampered download never leaves a model `textstats` would load. Rerunning is a no-op when the
file is already present and valid.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import tempfile
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from pretrain.quality.textstats import LID_FILENAMES, MODEL_DIR

BASE_URL = "https://dl.fbaipublicfiles.com/fasttext/supervised-models/"
# variant -> (file name, SHA-256). Names come from textstats so it always looks for what this writes; the checksums
# are pinned from the upstream files, so a changed upstream file fails loudly and must be re-reviewed.
MODELS = {
    "bin": (LID_FILENAMES[0], "7e69ec5451bc261cc7844e49e4792a85d7f09c06789ec800fc4a44aec362764e"),
    "ftz": (LID_FILENAMES[1], "8f3472cfe8738a7b6099e8e999c3cbfae0dcd15696aac7d7738a8039db603e83"),
}
CHUNK = 1 << 20
TIMEOUT = 60.0


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1.0, status_forcelist=(429, 500, 502, 503, 504))
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def fetch(variant: str, model_dir: Path = MODEL_DIR, session: requests.Session | None = None) -> tuple[Path, bool]:
    """Ensure the verified model file exists; return its path and whether it was downloaded."""
    name, expected = MODELS[variant]
    target = model_dir / name
    if target.is_file() and sha256_of(target) == expected:
        return target, False
    model_dir.mkdir(parents=True, exist_ok=True)
    fd, part_name = tempfile.mkstemp(dir=model_dir, prefix=f".{name}.", suffix=".part")
    part = Path(part_name)
    try:
        digest = hashlib.sha256()
        with (
            os.fdopen(fd, "wb") as out,
            (session or _session()).get(BASE_URL + name, stream=True, timeout=TIMEOUT) as response,
        ):
            response.raise_for_status()
            for chunk in response.iter_content(CHUNK):
                digest.update(chunk)
                out.write(chunk)
        actual = digest.hexdigest()
        if actual != expected:
            raise ValueError(f"{name}: SHA-256 {actual} does not match the pinned {expected}; not installed")
        os.replace(part, target)
    finally:
        part.unlink(missing_ok=True)
    return target, True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--variant", choices=sorted(MODELS), default="bin", help="bin (default) or the small ftz")
    args = parser.parse_args()
    path, downloaded = fetch(args.variant)
    print(f"{'downloaded and verified' if downloaded else 'already present and verified'}: {path}", flush=True)


if __name__ == "__main__":
    main()
