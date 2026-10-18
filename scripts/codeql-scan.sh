#!/usr/bin/env bash
set -euo pipefail

if ! command -v codeql >/dev/null 2>&1; then
  printf 'CodeQL CLI is required; install it with: brew install --cask codeql\n' >&2
  exit 1
fi

repo_root=$(git rev-parse --show-toplevel)
tmpdir=$(mktemp -d)
# shellcheck disable=SC2329  # invoked via `trap cleanup EXIT` below
cleanup() {
  if [[ -n "${CODEQL_SARIF_DIR:-}" ]]; then
    mkdir -p "$CODEQL_SARIF_DIR"
    cp "$tmpdir"/*.sarif "$CODEQL_SARIF_DIR/" 2>/dev/null || true
  fi
  rm -rf "$tmpdir"
}
trap cleanup EXIT
mkdir -p "$tmpdir/src"
git -C "$repo_root" checkout-index -a --prefix="$tmpdir/src/"

languages=()
if find "$tmpdir/src" -type f -name '*.py' -print -quit | grep -q .; then
  languages+=(python)
fi
if find "$tmpdir/src" -type f \( -name '*.js' -o -name '*.jsx' -o -name '*.mjs' -o -name '*.cjs' \) -print -quit | grep -q .; then
  languages+=(javascript)
fi
if find "$tmpdir/src/.github/workflows" -type f \( -name '*.yml' -o -name '*.yaml' \) -print -quit 2>/dev/null | grep -q .; then
  languages+=(actions)
fi
if ((${#languages[@]} == 0)); then
  printf 'No CodeQL-supported languages found in the git index.\n' >&2
  exit 1
fi

language_csv=$(IFS=,; printf '%s' "${languages[*]}")
if ! codeql database create "$tmpdir/db" --db-cluster --language="$language_csv" \
  --build-mode=none --source-root="$tmpdir/src" --threads=0 --quiet >"$tmpdir/codeql.log" 2>&1; then
  cat "$tmpdir/codeql.log" >&2
  exit 1
fi

found=0
for language in "${languages[@]}"; do
  sarif="$tmpdir/$language.sarif"
  # Repo-local models (codeql/*-models) extend the standard library models, e.g. Starlette route input as untrusted.
  model_args=()
  if [[ -f "$tmpdir/src/codeql/$language-models/qlpack.yml" ]]; then
    model_args=(--additional-packs="$tmpdir/src/codeql" --model-packs="warda/$language-models")
  fi
  if ! codeql database analyze "$tmpdir/db/$language" "codeql/$language-queries:codeql-suites/$language-code-scanning.qls" \
    ${model_args[@]+"${model_args[@]}"} --download --format=sarif-latest --sarif-category="/language:$language" \
    --output="$sarif" --threads=0 --quiet \
    >"$tmpdir/codeql.log" 2>&1; then
    cat "$tmpdir/codeql.log" >&2
    exit 1
  fi
  if ! python3 - "$sarif" "$tmpdir/src" <<'PY'
import json
import pathlib
import sys
from urllib.parse import unquote, urlparse

sarif_path, source_root = sys.argv[1:]
source_root = pathlib.Path(source_root)
data = json.loads(pathlib.Path(sarif_path).read_text())
has_results = False
for run in data.get("runs", []):
    for result in run.get("results", []):
        has_results = True
        location = (result.get("locations") or [{}])[0].get("physicalLocation", {})
        artifact = location.get("artifactLocation", {}).get("uri", "<unknown>")
        parsed = urlparse(artifact)
        path = pathlib.Path(unquote(parsed.path)) if parsed.scheme == "file" else pathlib.Path(unquote(artifact))
        if not path.is_absolute():
            path = source_root / path
        try:
            display_path = path.relative_to(source_root).as_posix()
        except ValueError:
            display_path = artifact
        line = location.get("region", {}).get("startLine", 1)
        rule_id = result.get("ruleId", "unknown")
        message = result.get("message", {}).get("text", "").replace("\n", " ")
        print(f"{display_path}:{line}: [{rule_id}] {message}")
if has_results:
    sys.exit(1)
PY
  then
    found=1
  fi
done
exit "$found"
