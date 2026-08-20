#!/usr/bin/env python3
"""Generate a deterministic CycloneDX SBOM from committed lockfiles."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/completion/sbom"


def package_component(name: str, version: str, ecosystem: str, integrity: str | None = None) -> dict:
    purl_name = name.replace("@", "%40", 1) if name.startswith("@") else name
    purl = f"pkg:{ecosystem}/{purl_name}@{version}"
    component = {
        "type": "library",
        "bom-ref": purl,
        "group": name.rsplit("/", 1)[0] if name.startswith("@") else None,
        "name": name.rsplit("/", 1)[-1] if name.startswith("@") else name,
        "version": version,
        "purl": purl,
    }
    if component["group"] is None:
        component.pop("group")
    if integrity:
        component[" hashes"] = [{"alg": "SHA-512", "content": integrity.removeprefix("sha512-")}]
        component["hashes"] = component.pop(" hashes")
    return component


def node_components() -> list[dict]:
    lock = json.loads((ROOT / "package-lock.json").read_text())
    components: list[dict] = []
    for location, data in sorted(lock.get("packages", {}).items()):
        if not location.startswith("node_modules/") or not isinstance(data, dict):
            continue
        name = location.removeprefix("node_modules/")
        version = data.get("version")
        if not isinstance(version, str):
            continue
        components.append(package_component(name, version, "npm", data.get("integrity")))
    return components


def python_components() -> list[dict]:
    lines: list[str] = []
    for filename in ("requirements.lock", "requirements-dev.lock"):
        for raw in (ROOT / "apps/api" / filename).read_text().splitlines():
            raw = raw.strip()
            if not raw or raw.startswith("#") or raw.startswith("-"):
                continue
            lines.append(raw)
    components: dict[str, dict] = {}
    for raw in lines:
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^;]+)", raw)
        if not match:
            raise ValueError(f"Unsupported locked requirement: {raw}")
        name, version = match.groups()
        key = name.lower().replace("_", "-")
        components[key] = package_component(name, version, "pypi")
    return [components[key] for key in sorted(components)]


def write_bom(path: Path, components: list[dict], source: list[str]) -> None:
    bom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": "urn:uuid:nur-completion-ledger",
        "version": 1,
        "metadata": {
            "component": {"type": "application", "name": "NUR", "version": "completion-branch"},
            "properties": [
                {"name": "source.files", "value": ";".join(source)},
                {"name": "source.git_sha", "value": __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()},
            ],
        },
        "components": components,
    }
    path.write_text(json.dumps(bom, indent=2, sort_keys=True) + "\n")


OUT.mkdir(parents=True, exist_ok=True)
write_bom(OUT / "MANUS_SBOM_NODE_CYCLONEDX.json", node_components(), ["package.json", "package-lock.json"])
write_bom(OUT / "MANUS_SBOM_PYTHON_CYCLONEDX.json", python_components(), ["apps/api/requirements.lock", "apps/api/requirements-dev.lock"])
print(json.dumps({"node_components": len(node_components()), "python_components": len(python_components())}, sort_keys=True))
