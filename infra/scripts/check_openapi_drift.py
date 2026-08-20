#!/usr/bin/env python3
"""Fail when frontend API-client operations are not present in FastAPI OpenAPI.

The client intentionally stores paths without the public ``/api/v1`` prefix.
Path parameters are normalized to ``{param}`` on both sides so naming differences
such as ``{workflow_id}`` versus ``{id}`` do not create false drift. Query-string
suffixes are ignored because OpenAPI describes the path separately from query
parameters.
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from pathlib import Path
from typing import Iterable

METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
CLIENT_OPERATION_RE = re.compile(
    r"\.(?P<method>get|post|put|patch|delete)(?:<.*?>)?\s*\(\s*"
    r"(?P<quote>['\"`])(?P<path>.*?)(?P=quote)",
    re.IGNORECASE | re.DOTALL,
)
INTERPOLATION_RE = re.compile(r"\$\{[^}]+\}")
PARAM_RE = re.compile(r"\{[^}]+\}")
DYNAMIC_ACTIONS: dict[tuple[str, str], tuple[str, ...]] = {
    ("POST", "/omega/review-queue/{param}/{param}"): ("approve", "reject"),
    ("POST", "/projects/runs/{param}/{param}"): ("approve", "cancel", "reject", "queue", "retry"),
}


def normalize_client_path(path: str) -> str:
    """Convert one client path into the OpenAPI comparison shape."""
    normalized = path.strip()
    if normalized.startswith("/api/v1"):
        normalized = normalized[len("/api/v1") :]
    normalized = normalized.split("?", 1)[0]
    # A client may append a pre-built query string template such as ${query}.
    normalized = re.sub(r"\$\{[^}]*query[^}]*\}$", "", normalized, flags=re.IGNORECASE)
    normalized = INTERPOLATION_RE.sub("{param}", normalized)
    normalized = PARAM_RE.sub("{param}", normalized)
    normalized = re.sub(r"/{2,}", "/", normalized)
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    if len(normalized) > 1:
        normalized = normalized.rstrip("/")
    return normalized


def extract_client_operations(source: str) -> set[tuple[str, str]]:
    operations: set[tuple[str, str]] = set()
    for match in CLIENT_OPERATION_RE.finditer(source):
        method = match.group("method").upper()
        path = match.group("path")
        if method in METHODS and path.startswith("/"):
            operations.add((method, normalize_client_path(path)))
    return operations


def extract_openapi_operations(schema: dict) -> set[tuple[str, str]]:
    operations: set[tuple[str, str]] = set()
    for path, item in schema.get("paths", {}).items():
        normalized = normalize_client_path(path)
        for method in item:
            upper = method.upper()
            if upper in METHODS:
                operations.add((upper, normalized))
    return operations


def expand_dynamic_actions(
    client_operations: Iterable[tuple[str, str]],
) -> set[tuple[str, str]]:
    expanded: set[tuple[str, str]] = set()
    for operation in client_operations:
        actions = DYNAMIC_ACTIONS.get(operation)
        if not actions:
            expanded.add(operation)
            continue
        method, path = operation
        prefix = path.rsplit("/", 1)[0]
        for action in actions:
            expanded.add((method, f"{prefix}/{action}"))
    return expanded


def compare_operations(
    client_operations: Iterable[tuple[str, str]],
    openapi_operations: Iterable[tuple[str, str]],
) -> list[tuple[str, str]]:
    openapi = set(openapi_operations)
    return sorted(expand_dynamic_actions(client_operations) - openapi)


def load_openapi() -> dict:
    repo_root = Path(__file__).resolve().parents[2]
    api_root = repo_root / "apps" / "api"
    sys.path.insert(0, str(api_root))
    module = importlib.import_module("app.main")
    application = getattr(module, "app", None)
    if application is None or not hasattr(application, "openapi"):
        raise RuntimeError("apps/api/app/main.py does not expose a FastAPI app")
    return application.openapi()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--client",
        action="append",
        default=["apps/web/src/bridge/v197ApiClient.ts"],
        help="Frontend client source file; may be supplied more than once.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable output.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    client_operations: set[tuple[str, str]] = set()
    missing_files: list[str] = []
    for relative in args.client:
        path = repo_root / relative
        if not path.exists():
            missing_files.append(relative)
            continue
        client_operations.update(extract_client_operations(path.read_text(encoding="utf-8")))
    if missing_files:
        print(json.dumps({"pass": False, "missing_client_files": missing_files}, indent=2))
        return 2

    try:
        schema = load_openapi()
    except Exception as exc:  # noqa: BLE001 - the error is part of the gate output.
        print(f"OpenAPI drift gate could not load FastAPI schema: {exc}", file=sys.stderr)
        return 2
    openapi_operations = extract_openapi_operations(schema)
    expanded_client_operations = expand_dynamic_actions(client_operations)
    missing = compare_operations(client_operations, openapi_operations)
    result = {
        "pass": not missing,
        "client_operation_count": len(expanded_client_operations),
        "openapi_operation_count": len(openapi_operations),
        "missing_client_operations": [
            {"method": method, "path": path} for method, path in missing
        ],
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(json.dumps(result, indent=2))
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
