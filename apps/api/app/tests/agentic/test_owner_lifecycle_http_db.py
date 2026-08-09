"""Owner Agent lifecycle over real PostgreSQL, Redis, and forced RLS."""

from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agentic import handlers
from app.agentic.aggregate import aggregate_workflow
from app.agentic.enums import StepState
from app.agentic.orchestrator import transition_step
from app.db.rls import set_user_context
from app.models.agentic import AgentPolicy, AgentWorkflow
from app.tests.conftest import register_user

ORIGIN = "http://localhost:5173"
READ_TOOL = "get_timeline"


@pytest.fixture(scope="module", autouse=True)
def bind_agentic_handlers() -> None:
    handlers.bind_all_handlers()


def headers(client: AsyncClient) -> dict[str, str]:
    return {
        "X-CSRF-Token": client.cookies.get("nur_csrf"),
        "Origin": ORIGIN,
    }


def policy_payload(*, seen_version: int, auto_run: bool = True) -> dict:
    return {
        "seen_version": seen_version,
        "initiative_level": "SUGGEST",
        "max_risk_class": "R1_PRIVATE_DRAFT",
        "permitted_tools": [READ_TOOL],
        "auto_run_tools": [READ_TOOL] if auto_run else [],
        "denied_tools": [],
        "daily_budget_cents": 0,
        "max_proposals_per_day": 3,
        "cooldown_minutes": 180,
        "quiet_hours": None,
    }


def workflow_payload(*, request_id: UUID | None = None, title: str = "Owner review") -> dict:
    return {
        "request_id": str(request_id or uuid4()),
        "title": title,
        "objective": "Read a bounded owner timeline without inventing facts.",
        "context_manifest": {
            "included": ["owner timeline"],
            "excluded": ["other owners", "external network"],
        },
        "success_criteria": ["Return only owner-scoped timeline evidence."],
        "proposed_steps": [
            {
                "key": "read_timeline",
                "role": "researcher",
                "tool_key": READ_TOOL,
                "depends_on": [],
                "input_refs": {"limit": 3},
                "rationale": "Read only the bounded owner timeline.",
            }
        ],
    }


async def register(client: AsyncClient) -> UUID:
    response, _email, _password = await register_user(client)
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


async def set_policy(client: AsyncClient, *, seen_version: int, auto_run: bool = True) -> dict:
    response = await client.put(
        "/api/v1/agentic/policy",
        json=policy_payload(seen_version=seen_version, auto_run=auto_run),
        headers=headers(client),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def create_workflow(client: AsyncClient, payload: dict | None = None) -> dict:
    response = await client.post(
        "/api/v1/agentic/workflows",
        json=payload or workflow_payload(),
        headers=headers(client),
    )
    assert response.status_code == 201, response.text
    return response.json()


@asynccontextmanager
async def owner_session(app_engine, owner: UUID):
    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as db:
        await set_user_context(db, owner)
        yield db


async def fail_workflow(app_engine, owner: UUID, workflow_id: UUID, step_id: UUID) -> None:
    async with owner_session(app_engine, owner) as db:
        moved = await transition_step(
            db,
            owner_user_id=owner,
            step_id=step_id,
            current=StepState.QUEUED,
            nxt=StepState.FAILED,
        )
        assert moved
        await db.execute(
            text(
                "UPDATE agent_steps SET failure_code = 'TRANSIENT_TEST' "
                "WHERE id = :step AND owner_user_id = :owner"
            ),
            {"step": step_id, "owner": owner},
        )
        assert await aggregate_workflow(
            db, owner_user_id=owner, workflow_id=workflow_id
        ) == "FAILED"
        await db.commit()


@pytest.mark.asyncio
async def test_policy_is_versioned_validated_and_browser_write_protected(client, app_engine):
    owner = await register(client)
    default = await client.get("/api/v1/agentic/policy")
    assert default.status_code == 200
    assert default.json()["version"] == 0
    assert default.json()["persisted"] is False

    missing_csrf = await client.put(
        "/api/v1/agentic/policy",
        json=policy_payload(seen_version=0),
        headers={"Origin": ORIGIN},
    )
    assert missing_csrf.status_code == 403

    cross_site = await client.put(
        "/api/v1/agentic/policy",
        json=policy_payload(seen_version=0),
        headers={
            "X-CSRF-Token": client.cookies.get("nur_csrf"),
            "Origin": "https://attacker.example",
            "Sec-Fetch-Site": "cross-site",
        },
    )
    assert cross_site.status_code == 403

    created = await set_policy(client, seen_version=0)
    assert created["version"] == 1
    assert created["granted_capabilities"] == ["read_timeline"]

    stale = await client.put(
        "/api/v1/agentic/policy",
        json=policy_payload(seen_version=0, auto_run=False),
        headers=headers(client),
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "STALE_POLICY_VERSION"

    updated = await set_policy(client, seen_version=1, auto_run=False)
    assert updated["version"] == 2
    async with owner_session(app_engine, owner) as db:
        rows = (
            await db.execute(select(AgentPolicy).where(AgentPolicy.owner_user_id == owner))
        ).scalars().all()
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_create_is_atomic_owner_idempotent_and_cursor_bounded(client):
    await register(client)
    await set_policy(client, seen_version=0)
    request_id = uuid4()
    payload = workflow_payload(request_id=request_id)
    first = await create_workflow(client, payload)
    replay = await create_workflow(client, payload)
    assert first["id"] == replay["id"]
    assert first["idempotent_replay"] is False
    assert replay["idempotent_replay"] is True
    assert first["state"] == "PLAN_READY"
    assert first["steps"][0]["approval_required"] is False

    conflict_payload = workflow_payload(request_id=request_id, title="Different payload")
    conflict = await client.post(
        "/api/v1/agentic/workflows",
        json=conflict_payload,
        headers=headers(client),
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    await create_workflow(client)
    await create_workflow(client)
    page_one = await client.get("/api/v1/agentic/workflows?limit=2")
    assert page_one.status_code == 200
    assert len(page_one.json()["workflows"]) == 2
    cursor = page_one.json()["next_cursor"]
    assert cursor
    page_two = await client.get(
        "/api/v1/agentic/workflows", params={"limit": 2, "cursor": cursor}
    )
    assert page_two.status_code == 200
    ids_one = {item["id"] for item in page_one.json()["workflows"]}
    ids_two = {item["id"] for item in page_two.json()["workflows"]}
    assert ids_one.isdisjoint(ids_two)


@pytest.mark.asyncio
async def test_start_routes_approval_and_cross_owner_ids_are_invisible(client, app_engine):
    owner = await register(client)
    await set_policy(client, seen_version=0, auto_run=False)
    workflow = await create_workflow(client)
    workflow_id = workflow["id"]

    async with AsyncClient(
        transport=ASGITransport(app=client.app), base_url="http://test"
    ) as other:
        await register(other)
        wrong_owner = await other.post(
            f"/api/v1/agentic/workflows/{workflow_id}/start",
            json={"seen_plan_version": 1},
            headers=headers(other),
        )
        assert wrong_owner.status_code == 404

    started = await client.post(
        f"/api/v1/agentic/workflows/{workflow_id}/start",
        json={"seen_plan_version": 1},
        headers=headers(client),
    )
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["state"] == "WAITING_APPROVAL"
    assert body["steps"][0]["state"] == "WAITING_APPROVAL"
    assert body["queued_step_ids"] == []
    async with owner_session(app_engine, owner) as db:
        approval = (
            await db.execute(
                text(
                    "SELECT argument_digest, plan_version, call_version "
                    "FROM agent_approvals WHERE workflow_id = :workflow"
                ),
                {"workflow": UUID(workflow_id)},
            )
        ).mappings().one()
        assert approval["argument_digest"].startswith("sha256:")
        assert approval["plan_version"] == 1
        assert len(approval["call_version"]) >= 64


@pytest.mark.asyncio
async def test_cancel_fences_steps_and_unsent_outbox(client, app_engine):
    owner = await register(client)
    await set_policy(client, seen_version=0)
    workflow = await create_workflow(client)
    started = await client.post(
        f"/api/v1/agentic/workflows/{workflow['id']}/start",
        json={"seen_plan_version": 1},
        headers=headers(client),
    )
    assert started.status_code == 200
    old_attempt = started.json()["steps"][0]["execution_attempt"]
    cancelled = await client.post(
        f"/api/v1/agentic/workflows/{workflow['id']}/cancel",
        headers=headers(client),
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["state"] == "CANCELLED"
    assert cancelled.json()["steps"][0]["state"] == "CANCELLED"
    assert cancelled.json()["steps"][0]["execution_attempt"] != old_attempt
    async with owner_session(app_engine, owner) as db:
        state = (
            await db.execute(
                text(
                    "SELECT state FROM agent_dispatch_outbox "
                    "WHERE workflow_id = :workflow"
                ),
                {"workflow": UUID(workflow["id"])},
            )
        ).scalar_one()
        assert state == "CANCELLED"


@pytest.mark.asyncio
async def test_retry_creates_immutable_lineage_successor(client, app_engine):
    owner = await register(client)
    await set_policy(client, seen_version=0)
    original = await create_workflow(client)
    started = await client.post(
        f"/api/v1/agentic/workflows/{original['id']}/start",
        json={"seen_plan_version": 1},
        headers=headers(client),
    )
    step_id = started.json()["steps"][0]["id"]
    await fail_workflow(
        app_engine, owner, UUID(original["id"]), UUID(step_id)
    )

    request_id = uuid4()
    retry = await client.post(
        f"/api/v1/agentic/workflows/{original['id']}/retry",
        json={"request_id": str(request_id), "seen_plan_version": 1},
        headers=headers(client),
    )
    assert retry.status_code == 201, retry.text
    successor = retry.json()
    assert successor["id"] != original["id"]
    assert successor["retry_of_workflow_id"] == original["id"]
    assert successor["state"] == "PLAN_READY"
    assert successor["steps"][0]["id"] != step_id

    replay = await client.post(
        f"/api/v1/agentic/workflows/{original['id']}/retry",
        json={"request_id": str(request_id), "seen_plan_version": 1},
        headers=headers(client),
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == successor["id"]
    assert replay.json()["idempotent_replay"] is True

    original_after = await client.get(
        f"/api/v1/agentic/workflows/{original['id']}"
    )
    assert original_after.json()["state"] == "FAILED"
    async with owner_session(app_engine, owner) as db:
        original_row = await db.get(AgentWorkflow, UUID(original["id"]))
        successor_row = await db.get(AgentWorkflow, UUID(successor["id"]))
        assert original_row.state == "FAILED"
        assert successor_row.retry_of_workflow_id == original_row.id
