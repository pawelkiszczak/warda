#!/usr/bin/env bash
# Recreate the separately licensed StyloMetrix runtime used by stylometrix_worker.py.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV="$ROOT/pretrain/.venv-stylometrix"
ARCHIVE="${TMPDIR:-/tmp}/pl_nask-0.0.7.tar.gz"
uv venv --python 3.11 "$ENV"
uv pip install --python "$ENV/bin/python" stylo-metrix 'numpy<2' 'spacy-transformers>=1.3,<1.4' 'morfeusz2==1.99.14'
curl --fail --location --retry 3 'https://mozart.ipipan.waw.pl/~rtuora/spacy/pl_nask-0.0.7.tar.gz' --output "$ARCHIVE"
uv pip install --python "$ENV/bin/python" --no-deps "$ARCHIVE"
rm -f "$ARCHIVE"
"$ENV/bin/python" - <<'PY'
from pathlib import Path
import re
import site

path = next((Path(root) / "pl_nask" / "morf.py" for root in site.getsitepackages()
             if (Path(root) / "pl_nask" / "morf.py").is_file()), None)
if path is None:
    raise SystemExit("pl_nask/morf.py not found in site-packages; cannot patch the Morfeusz import")
source = path.read_text()
pattern = r'if platform\.uname\(\)\.system == ["\']Darwin["\']:\s*\n[ \t]+from \. import morf_interface as morfeusz2\s*\nelse:\s*\n[ \t]+import morfeusz2'
source, count = re.subn(pattern, "import morfeusz2", source, count=1)
if not count and not re.search(r"(?m)^import morfeusz2(?:\s|#|$)", source):
    raise SystemExit(f"Expected Darwin Morfeusz import block not found in {path}")
path.write_text(source)
PY
printf 'StyloMetrix environment ready: %s\n' "$ENV"
