#!/usr/bin/env python3
"""Generate or verify deterministic CycloneDX SBOMs from committed lockfiles."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "docs/completion/sbom"
NODE_FILENAME = "MANUS_SBOM_NODE_CYCLONEDX.json"
PYTHON_FILENAME = "MANUS_SBOM_PYTHON_CYCLONEDX.json"
SHA_PATTERN = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare existing SBOMs with lock-derived expected bytes without writing",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUT,
        help="SBOM directory (default: docs/completion/sbom)",
    )
    parser.add_argument(
        "--source-sha",
        help="exact Git source SHA; required outside a Git checkout",
    )
    return parser.parse_args()


def resolve_source_sha(explicit: str | None) -> str:
    if explicit:
        source_sha = explicit.strip().lower()
    else:
        try:
            source_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
            ).strip().lower()
        except (OSError, subprocess.CalledProcessError) as exc:
            raise SystemExit(
                "Cannot establish SBOM source SHA outside Git; pass --source-sha explicitly."
            ) from exc
    if not SHA_PATTERN.fullmatch(source_sha):
        raise SystemExit(f"Invalid SBOM source SHA: {source_sha!r}")
    return source_sha


def source_input_digest(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(ROOT).as_posix().encode()
        digest.update(relative)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def integrity_hash(integrity: object) -> list[dict[str, str]] | None:
    if not isinstance(integrity, str) or "-" not in integrity:
        return None
    algorithm, encoded = integrity.split("-", 1)
    cyclone_algorithm = {
        "sha256": "SHA-256",
        "sha384": "SHA-384",
        "sha512": "SHA-512",
    }.get(algorithm.lower())
    if cyclone_algorithm is None:
        return None
    try:
        content = base64.b64decode(encoded, validate=True).hex()
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError(f"Invalid package-lock integrity value: {integrity}") from exc
    return [{"alg": cyclone_algorithm, "content": content}]


def package_component(
    name: str,
    version: str,
    ecosystem: str,
    integrity: object = None,
) -> dict[str, object]:
    purl_name = quote(name, safe="/")
    purl = f"pkg:{ecosystem}/{purl_name}@{quote(version, safe='.+-')}"
    component: dict[str, object] = {
        "type": "library",
        "bom-ref": purl,
        "name": name.rsplit("/", 1)[-1] if name.startswith("@") else name,
        "version": version,
        "purl": purl,
    }
    if name.startswith("@"):
        component["group"] = name.rsplit("/", 1)[0]
    hashes = integrity_hash(integrity)
    if hashes:
        component["hashes"] = hashes
    return component


def node_components() -> list[dict[str, object]]:
    lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    components: dict[str, dict[str, object]] = {}
    for location, data in sorted(lock.get("packages", {}).items()):
        if not location.startswith("node_modules/") or not isinstance(data, dict):
            continue
        name = data.get("name")
        if not isinstance(name, str):
            name = location.rsplit("node_modules/", 1)[-1]
        version = data.get("version")
        if not isinstance(version, str):
            continue
        component = package_component(name, version, "npm", data.get("integrity"))
        components[str(component["bom-ref"])] = component
    return [components[key] for key in sorted(components)]


def python_components() -> list[dict[str, object]]:
    lines: list[str] = []
    for filename in ("requirements.lock", "requirements-dev.lock"):
        for raw in (ROOT / "apps/api" / filename).read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw or raw.startswith("#") or raw.startswith("-"):
                continue
            lines.append(raw)
    components: dict[str, dict[str, object]] = {}
    for raw in lines:
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^;\s]+)(?:\s*;\s*.+)?", raw)
        if not match:
            raise ValueError(f"Unsupported locked requirement: {raw}")
        name, version = match.groups()
        component = package_component(name, version, "pypi")
        components[str(component["bom-ref"])] = component
    return [components[key] for key in sorted(components)]


def bom_bytes(
    *,
    ecosystem: str,
    components: list[dict[str, object]],
    source_paths: list[Path],
    source_sha: str,
) -> bytes:
    input_sha = source_input_digest(source_paths)
    serial = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"https://nur.app/sbom/{ecosystem}/{source_sha}/{input_sha}",
    )
    bom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": f"pkg:generic/nur@{source_sha}",
                "name": "NUR",
                "version": source_sha,
            },
            "properties": [
                {
                    "name": "source.files",
                    "value": ";".join(path.relative_to(ROOT).as_posix() for path in source_paths),
                },
                {"name": "source.git_sha", "value": source_sha},
                {"name": "source.input_sha256", "value": input_sha},
                {"name": "source.ecosystem", "value": ecosystem},
            ],
        },
        "components": components,
    }
    return (json.dumps(bom, indent=2, sort_keys=True) + "\n").encode()


def expected_documents(source_sha: str) -> dict[str, bytes]:
    node_sources = [ROOT / "package.json", ROOT / "package-lock.json"]
    python_sources = [
        ROOT / "apps/api/requirements.lock",
        ROOT / "apps/api/requirements-dev.lock",
    ]
    return {
        NODE_FILENAME: bom_bytes(
            ecosystem="node",
            components=node_components(),
            source_paths=node_sources,
            source_sha=source_sha,
        ),
        PYTHON_FILENAME: bom_bytes(
            ecosystem="python",
            components=python_components(),
            source_paths=python_sources,
            source_sha=source_sha,
        ),
    }


def main() -> int:
    args = parse_args()
    source_sha = resolve_source_sha(args.source_sha)
    output_dir = args.output_dir.resolve()
    documents = expected_documents(source_sha)

    if args.check:
        stale: list[str] = []
        for filename, expected in documents.items():
            path = output_dir / filename
            if not path.is_file() or path.read_bytes() != expected:
                stale.append(filename)
        if stale:
            print(f"SBOM_CHECK=STALE files={','.join(stale)}", file=sys.stderr)
            return 1
        print(
            json.dumps(
                {
                    "mode": "check",
                    "source_sha": source_sha,
                    "status": "fresh",
                    "node_components": len(node_components()),
                    "python_components": len(python_components()),
                },
                sort_keys=True,
            )
        )
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, payload in documents.items():
        (output_dir / filename).write_bytes(payload)
    print(
        json.dumps(
            {
                "mode": "generate",
                "source_sha": source_sha,
                "node_components": len(node_components()),
                "python_components": len(python_components()),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
