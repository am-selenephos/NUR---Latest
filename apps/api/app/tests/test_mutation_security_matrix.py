from __future__ import annotations

from pathlib import Path
import uuid

from app.core.mutation_security import (
    PUBLIC_BROWSER_MUTATIONS,
    READ_ONLY_POST_ALLOWLIST,
    build_mutation_security_matrix,
    render_mutation_security_matrix_csv,
)
from app.core.security import bootstrap_csrf_matches
from app.main import create_app
from app.tests.conftest import register_user


REPO_ROOT = Path(__file__).resolve().parents[4]
MATRIX_PATH = REPO_ROOT / "contracts" / "mutation-security-matrix.csv"
ALLOWED_ORIGIN = "http://localhost:4173"


def test_generated_matrix_covers_every_effective_fastapi_operation() -> None:
    rows = build_mutation_security_matrix(create_app())
    keys = [(row.method, row.path) for row in rows]

    assert rows
    assert len(keys) == len(set(keys))
    assert MATRIX_PATH.read_text(encoding="utf-8") == render_mutation_security_matrix_csv(rows)


def test_every_browser_mutation_has_csrf_and_trusted_origin() -> None:
    rows = build_mutation_security_matrix(create_app())
    mutations = [row for row in rows if row.method in {"POST", "PUT", "PATCH", "DELETE"}]

    assert mutations
    assert all(row.compliant for row in mutations), [
        (row.method, row.path, row.classification, row.dependencies)
        for row in mutations
        if not row.compliant
    ]
    assert {
        (row.method, row.path)
        for row in mutations
        if row.classification == "READ_ONLY_POST"
    } == set(READ_ONLY_POST_ALLOWLIST)
    assert {
        (row.method, row.path)
        for row in mutations
        if row.classification == "PUBLIC_BROWSER_MUTATION"
    } == PUBLIC_BROWSER_MUTATIONS


async def test_public_browser_auth_requires_bootstrap_csrf_and_origin(client) -> None:
    payload = {
        "chosen_name": "Bootstrap Owner",
        "email": f"bootstrap-{uuid.uuid4().hex}@nurapp.dev",
        "password": "orbit-passphrase-9",
        "consent": True,
    }

    missing_bootstrap = await client.post(
        "/api/v1/auth/register",
        headers={"Origin": ALLOWED_ORIGIN, "Sec-Fetch-Site": "same-site"},
        json=payload,
    )
    assert missing_bootstrap.status_code == 403

    anonymous = await client.get("/api/v1/auth/me")
    assert anonymous.status_code == 401
    bootstrap = client.cookies.get("nur_csrf")
    assert bootstrap_csrf_matches(bootstrap)

    forged_origin = await client.post(
        "/api/v1/auth/register",
        headers={"Origin": "https://attacker.invalid", "Sec-Fetch-Site": "cross-site"},
        json=payload,
    )
    assert forged_origin.status_code == 403

    registered = await client.post(
        "/api/v1/auth/register",
        headers={"Origin": ALLOWED_ORIGIN, "Sec-Fetch-Site": "same-site"},
        json=payload,
    )
    assert registered.status_code == 201
    session_csrf = client.cookies.get("nur_csrf")
    assert session_csrf and session_csrf != bootstrap


async def test_projects_file_delete_enforces_csrf_and_origin_before_lookup(client) -> None:
    registered, _, _ = await register_user(client)
    assert registered.status_code == 201
    file_id = uuid.uuid4()

    missing_csrf = await client.delete(f"/api/v1/projects/files/{file_id}")
    assert missing_csrf.status_code == 403

    forged_origin = await client.delete(
        f"/api/v1/projects/files/{file_id}",
        headers={
            "Origin": "https://attacker.invalid",
            "Sec-Fetch-Site": "cross-site",
            "X-CSRF-Token": client.cookies.get("nur_csrf"),
        },
    )
    assert forged_origin.status_code == 403

    guarded_lookup = await client.delete(
        f"/api/v1/projects/files/{file_id}",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Sec-Fetch-Site": "same-site",
            "X-CSRF-Token": client.cookies.get("nur_csrf"),
        },
    )
    assert guarded_lookup.status_code == 404
