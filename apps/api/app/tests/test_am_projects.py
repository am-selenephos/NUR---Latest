from sqlalchemy import text

from app.tests.conftest import register_user


def H(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("nur_csrf")}


async def test_am_project_owner_flow_requires_evidence_and_explicit_run_approval(client):
    await register_user(client, chosen_name="Project Owner")

    created = await client.post(
        "/api/v1/projects",
        headers=H(client),
        json={
            "title": "Ship a verifiable NUR vertical",
            "objective": "Produce a tested source package and evidence ledger.",
            "system_slug": "creation",
            "budget_cents": 5000,
        },
    )
    assert created.status_code == 201, created.text
    project = created.json()
    assert project["permission_policy"]["external_actions_require_owner_approval"] is True
    assert project["permission_policy"]["spend"] is False
    owner_state = (await client.get("/api/v1/orbits/current-state")).json()
    assert owner_state["active_systems"] == 6

    task = await client.post(
        f"/api/v1/projects/{project['id']}/tasks",
        headers=H(client),
        json={
            "title": "Run the acceptance suite",
            "acceptance_criteria": "All project tests pass and the log is checksummed.",
            "status": "READY",
            "priority": 90,
            "assigned_role": "verifier",
        },
    )
    assert task.status_code == 201, task.text
    task_id = task.json()["id"]

    no_evidence = await client.patch(
        f"/api/v1/projects/tasks/{task_id}",
        headers=H(client),
        json={"status": "DONE"},
    )
    assert no_evidence.status_code == 409
    assert "PASSED evidence" in no_evidence.json()["detail"]

    invalid_evidence = await client.post(
        f"/api/v1/projects/{project['id']}/evidence",
        headers=H(client),
        json={
            "task_id": task_id,
            "evidence_kind": "TEST_LOG",
            "summary": "The suite passed.",
            "verification_status": "PASSED",
        },
    )
    assert invalid_evidence.status_code == 409

    evidence = await client.post(
        f"/api/v1/projects/{project['id']}/evidence",
        headers=H(client),
        json={
            "task_id": task_id,
            "evidence_kind": "TEST_LOG",
            "summary": "The isolated acceptance suite passed.",
            "locator": "proof/project-tests.log",
            "checksum_sha256": "a" * 64,
            "verification_status": "PASSED",
            "verifier": "pytest",
        },
    )
    assert evidence.status_code == 201, evidence.text
    assert evidence.json()["glow"]["awarded_points"] == 6

    completed = await client.patch(
        f"/api/v1/projects/tasks/{task_id}",
        headers=H(client),
        json={"status": "DONE"},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["task"]["completed_at"] is not None
    assert completed.json()["glow"]["awarded_points"] == 8

    forbidden_run = await client.post(
        f"/api/v1/projects/{project['id']}/runs",
        headers=H(client),
        json={
            "task_id": task_id,
            "role": "operator",
            "request_summary": "Publish the build without review.",
            "tool_policy": {"publish": True},
        },
    )
    assert forbidden_run.status_code == 422

    proposed = await client.post(
        f"/api/v1/projects/{project['id']}/runs",
        headers=H(client),
        json={
            "task_id": task_id,
            "role": "verifier",
            "request_summary": "Re-run the bounded local test suite.",
            "tool_policy": {"filesystem_read": True},
            "budget_cents": 0,
        },
    )
    assert proposed.status_code == 201, proposed.text
    assert proposed.json()["status"] == "PROPOSED"
    assert proposed.json()["tool_policy"]["deploy"] is False

    approved = await client.post(
        f"/api/v1/projects/runs/{proposed.json()['id']}/approve",
        headers=H(client),
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["started_at"] is None

    missing_checksum = await client.post(
        f"/api/v1/projects/{project['id']}/artifacts",
        headers=H(client),
        json={
            "task_id": task_id,
            "run_id": proposed.json()["id"],
            "artifact_kind": "SOURCE_PACKAGE",
            "title": "Bootable package",
            "locator": "artifacts/nur.zip",
            "provenance_label": "MODEL_GENERATED",
        },
    )
    assert missing_checksum.status_code == 409

    artifact = await client.post(
        f"/api/v1/projects/{project['id']}/artifacts",
        headers=H(client),
        json={
            "task_id": task_id,
            "run_id": proposed.json()["id"],
            "artifact_kind": "SOURCE_PACKAGE",
            "title": "Bootable package",
            "locator": "artifacts/nur.zip",
            "checksum_sha256": "b" * 64,
            "provenance_label": "MODEL_GENERATED",
        },
    )
    assert artifact.status_code == 201, artifact.text

    review = await client.post(
        f"/api/v1/projects/{project['id']}/reviews",
        headers=H(client),
        json={
            "task_id": task_id,
            "run_id": proposed.json()["id"],
            "decision": "APPROVE",
            "note": "Evidence and package checksum agree.",
        },
    )
    assert review.status_code == 201, review.text
    assert review.json()["reviewer_label"] == "OWNER"

    project_done = await client.patch(
        f"/api/v1/projects/{project['id']}",
        headers=H(client),
        json={"status": "COMPLETED"},
    )
    assert project_done.status_code == 200, project_done.text
    assert project_done.json()["status"] == "COMPLETED"

    summary = (await client.get("/api/v1/projects/summary")).json()
    assert summary["provenance_label"] == "OWNER_PROJECT_LEDGER"
    assert summary["counts"]["projects"] == 1
    assert summary["projects"][0]["task_counts"]["DONE"] == 1
    assert summary["projects"][0]["verified_evidence"] == 1

    graph = (await client.get("/api/v1/map")).json()
    node_ids = {row["id"] for row in graph["nodes"]}
    assert f"project:{project['id']}" in node_ids
    assert f"project-task:{task_id}" in node_ids
    assert any(edge["kind"] == "SYSTEM_TO_PROJECT" for edge in graph["edges"])
    assert any(edge["kind"] == "PROJECT_TO_TASK" for edge in graph["edges"])
    assert graph["counts"]["projects"] == 1

    timeline = (await client.get("/api/v1/universe/timeline")).json()["items"]
    kinds = {row["kind"] for row in timeline}
    assert {
        "PROJECT_CREATED",
        "PROJECT_TASK_CREATED",
        "PROJECT_EVIDENCE_ADDED",
        "PROJECT_TASK_COMPLETED",
        "PROJECT_RUN_PROPOSED",
        "PROJECT_RUN_APPROVED",
        "PROJECT_REVIEW_RECORDED",
    } <= kinds

    glow = (await client.get("/api/v1/glow/summary")).json()
    assert glow["lifetime_points"] == 22


async def test_am_project_tables_force_rls_and_foreign_owner_cannot_read_or_mutate(
    client, app_engine
):
    owner_a, _, _ = await register_user(client, chosen_name="Project Owner A")
    project = await client.post(
        "/api/v1/projects",
        headers=H(client),
        json={"title": "Owner A private project", "objective": "Stay private."},
    )
    task = await client.post(
        f"/api/v1/projects/{project.json()['id']}/tasks",
        headers=H(client),
        json={"title": "Private task", "acceptance_criteria": "Private proof."},
    )
    run = await client.post(
        f"/api/v1/projects/{project.json()['id']}/runs",
        headers=H(client),
        json={"task_id": task.json()["id"], "role": "planner", "request_summary": "Private proposal."},
    )
    await client.post(
        f"/api/v1/projects/{project.json()['id']}/artifacts",
        headers=H(client),
        json={"artifact_kind": "NOTE", "title": "Private artifact", "locator": "private/note"},
    )
    await client.post(
        f"/api/v1/projects/{project.json()['id']}/evidence",
        headers=H(client),
        json={"evidence_kind": "NOTE", "summary": "Private evidence."},
    )
    await client.post(
        f"/api/v1/projects/{project.json()['id']}/reviews",
        headers=H(client),
        json={"run_id": run.json()["id"], "decision": "CORRECT", "note": "Private review."},
    )

    client.cookies.clear()
    owner_b, _, _ = await register_user(client, chosen_name="Project Owner B")
    assert (await client.get("/api/v1/projects")).json() == []
    assert (await client.get(f"/api/v1/projects/{project.json()['id']}")).status_code == 404
    assert (await client.patch(
        f"/api/v1/projects/tasks/{task.json()['id']}",
        headers=H(client),
        json={"status": "BLOCKED"},
    )).status_code == 404

    tables = [
        "am_projects",
        "am_project_tasks",
        "am_project_runs",
        "am_project_artifacts",
        "am_project_evidence",
        "am_project_reviews",
    ]
    async with app_engine.connect() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"),
            {"uid": owner_b.json()["id"]},
        )
        counts = {
            table: (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
            for table in tables
        }
        forced = dict((await conn.execute(text("""
            SELECT relname, relforcerowsecurity
            FROM pg_class
            WHERE relname = ANY(:tables)
        """), {"tables": tables})).all())
        await conn.rollback()

    assert all(value == 0 for value in counts.values())
    assert set(forced) == set(tables)
    assert all(forced.values())
    assert owner_a.json()["id"] != owner_b.json()["id"]
