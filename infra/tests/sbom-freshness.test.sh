#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
SHA="$(git rev-parse HEAD)"

python3 infra/scripts/generate_sbom.py --source-sha "$SHA" --output-dir "$TMP/one" >/dev/null
python3 infra/scripts/generate_sbom.py --source-sha "$SHA" --output-dir "$TMP/two" >/dev/null

cmp "$TMP/one/MANUS_SBOM_NODE_CYCLONEDX.json" "$TMP/two/MANUS_SBOM_NODE_CYCLONEDX.json"
cmp "$TMP/one/MANUS_SBOM_PYTHON_CYCLONEDX.json" "$TMP/two/MANUS_SBOM_PYTHON_CYCLONEDX.json"
python3 infra/scripts/generate_sbom.py --check --source-sha "$SHA" --output-dir "$TMP/one" >/dev/null

python3 - "$TMP/one" "$SHA" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

directory = Path(sys.argv[1])
expected_sha = sys.argv[2]
for path in sorted(directory.glob("*.json")):
    document = json.loads(path.read_text(encoding="utf-8"))
    properties = {
        item["name"]: item["value"]
        for item in document["metadata"]["properties"]
    }
    assert properties["source.git_sha"] == expected_sha
    assert len(properties["source.input_sha256"]) == 64
    assert document["components"] == sorted(
        document["components"], key=lambda item: item["bom-ref"]
    )
PY

printf '\n' >> "$TMP/one/MANUS_SBOM_NODE_CYCLONEDX.json"
set +e
stale_output="$(python3 infra/scripts/generate_sbom.py --check --source-sha "$SHA" --output-dir "$TMP/one" 2>&1)"
stale_status=$?
set -e
[[ "$stale_status" -eq 1 ]]
[[ "$stale_output" == *"STALE"* ]]

printf 'SBOM freshness: PASS\n'
