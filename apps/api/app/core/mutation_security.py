from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
MUTATION_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# POST is normally a mutation. These exact owner-scoped operations are
# intentionally read-only and therefore form a narrow, auditable exception.
READ_ONLY_POST_ALLOWLIST: dict[tuple[str, str], str] = {
    ("POST", "/api/v1/orbits/{orbit_id}/summary"): (
        "Computes an owner-scoped summary; persists nothing."
    ),
    ("POST", "/api/v1/projects/files/{file_id}/verify"): (
        "Reads stored bytes and checksum state; persists nothing."
    ),
    ("POST", "/api/v1/timeline/conflict-analysis"): (
        "Computes conflicts from owner-scoped timeline rows."
    ),
    ("POST", "/api/v1/timeline/external-sync"): (
        "Honest unavailable-provider probe; always returns 503 and persists nothing."
    ),
    ("POST", "/api/v1/timeline/ripple-preview"): (
        "Computes a hypothetical ripple preview; persists nothing."
    ),
}

PUBLIC_BROWSER_MUTATIONS = frozenset(
    {
        ("POST", "/api/v1/account/deletion/cancel"),
        ("POST", "/api/v1/account/deletion/receipt"),
        ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/password/forgot"),
        ("POST", "/api/v1/auth/password/reset"),
        ("POST", "/api/v1/auth/register"),
    }
)

SIGNED_MACHINE_MUTATIONS: dict[tuple[str, str], str] = {
    ("POST", "/api/v1/billing/webhooks/{provider}"): (
        "Machine webhook authenticated by bounded X-Signature verification; browser CSRF is not authority."
    ),
}


@dataclass(frozen=True)
class MutationSecurityRow:
    method: str
    path: str
    name: str
    classification: str
    authentication: str
    csrf: str
    trusted_origin: str
    machine_guard: str
    dependencies: str
    allowlist_reason: str
    compliant: bool


def _effective_routes(app: FastAPI) -> list[Any]:
    routes: list[Any] = []
    for route in app.router.routes:
        if isinstance(route, APIRoute):
            routes.append(route)
        elif hasattr(route, "effective_candidates"):
            routes.extend(route.effective_candidates())
    return routes


def _dependency_names(dependant: Any) -> set[str]:
    names: set[str] = set()

    def walk(node: Any) -> None:
        for child in getattr(node, "dependencies", ()):
            call = getattr(child, "call", None)
            if call is not None:
                names.add(getattr(call, "__name__", call.__class__.__name__))
            walk(child)

    walk(dependant)
    return names


def _header_names(dependant: Any) -> set[str]:
    names: set[str] = set()

    def walk(node: Any) -> None:
        for field in getattr(node, "header_params", ()):
            alias = getattr(getattr(field, "field_info", None), "alias", None)
            names.add(str(alias or getattr(field, "name", "")).lower())
        for child in getattr(node, "dependencies", ()):
            walk(child)

    walk(dependant)
    return names


def build_mutation_security_matrix(app: FastAPI) -> list[MutationSecurityRow]:
    """Generate one deterministic security row per effective FastAPI operation."""
    rows: list[MutationSecurityRow] = []
    seen: set[tuple[str, str]] = set()
    for route in _effective_routes(app):
        path = str(getattr(route, "path_format", None) or route.path)
        dependant = route.dependant
        dependencies = _dependency_names(dependant)
        headers = _header_names(dependant)
        for method in sorted(route.methods or ()):
            key = (method, path)
            if key in seen:
                raise RuntimeError(
                    f"Duplicate FastAPI operation in mutation matrix: {method} {path}"
                )
            seen.add(key)

            has_session = "get_current_identity" in dependencies
            has_csrf = bool(
                {"require_csrf", "require_public_browser_csrf"} & dependencies
            )
            has_origin = "require_trusted_origin" in dependencies
            reason = ""
            machine_guard = ""

            if method in SAFE_METHODS:
                classification = "SAFE_METHOD"
                compliant = True
            elif key in READ_ONLY_POST_ALLOWLIST:
                classification = "READ_ONLY_POST"
                reason = READ_ONLY_POST_ALLOWLIST[key]
                compliant = method == "POST" and has_session and not has_csrf
            elif key in PUBLIC_BROWSER_MUTATIONS:
                classification = "PUBLIC_BROWSER_MUTATION"
                compliant = not has_session and has_csrf and has_origin
            elif key in SIGNED_MACHINE_MUTATIONS:
                classification = "SIGNED_MACHINE_MUTATION"
                reason = SIGNED_MACHINE_MUTATIONS[key]
                machine_guard = "X-Signature" if "x-signature" in headers else "MISSING"
                compliant = not has_session and not has_csrf and machine_guard == "X-Signature"
            elif method in MUTATION_METHODS:
                classification = "AUTHENTICATED_BROWSER_MUTATION"
                compliant = has_session and has_csrf and has_origin
            else:
                classification = "UNKNOWN_METHOD"
                compliant = False

            rows.append(
                MutationSecurityRow(
                    method=method,
                    path=path,
                    name=route.name,
                    classification=classification,
                    authentication="SESSION" if has_session else "PUBLIC",
                    csrf="YES" if has_csrf else "NO",
                    trusted_origin="YES" if has_origin else "NO",
                    machine_guard=machine_guard,
                    dependencies=";".join(sorted(dependencies)),
                    allowlist_reason=reason,
                    compliant=compliant,
                )
            )
    return sorted(rows, key=lambda row: (row.path, row.method, row.name))


def render_mutation_security_matrix_csv(rows: list[MutationSecurityRow]) -> str:
    output = StringIO(newline="")
    fieldnames = [
        "method",
        "path",
        "name",
        "classification",
        "authentication",
        "csrf",
        "trusted_origin",
        "machine_guard",
        "dependencies",
        "allowlist_reason",
        "compliant",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                **{
                    name: getattr(row, name)
                    for name in fieldnames
                    if name != "compliant"
                },
                "compliant": "YES" if row.compliant else "NO",
            }
        )
    return output.getvalue()
