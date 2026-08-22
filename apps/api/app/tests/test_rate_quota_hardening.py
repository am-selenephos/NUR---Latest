"""Concurrency proofs for the bounded rate and quota paths."""

import asyncio
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.budget import assert_daily_ai_budget
from app.ai.errors import AIRequestBudgetExceeded
from app.core.config import get_settings
from app.db.rls import set_user_context
from app.models.cognition import ModelRun
from app.services.rate_limit import _fixed_window, namespaced
from app.tests.conftest import register_user


def _csrf(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("nur_csrf")}


async def _project(client) -> str:
    response = await client.post(
        "/api/v1/projects",
        headers=_csrf(client),
        json={"title": "Bounded quota", "objective": "Prove concurrent uploads serialize."},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_fixed_window_repairs_an_existing_counter_without_ttl(client) -> None:
    redis = client.app.state.redis
    raw_key = "rl:atomic-ttl-repair"
    key = namespaced(raw_key)
    await redis.set(key, 1)
    assert await redis.ttl(key) == -1

    assert await _fixed_window(redis, key=raw_key, max_n=5, window_s=45) is True

    ttl = await redis.ttl(key)
    assert 0 < ttl <= 45


async def test_daily_ai_request_reservation_is_atomic_across_sessions(
    client,
    app_engine,
    monkeypatch,
) -> None:
    registration, _, _ = await register_user(client, chosen_name="Atomic AI")
    owner_id = uuid.UUID(registration.json()["id"])
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider", "openai")
    monkeypatch.setattr(settings, "ai_per_user_daily_limit", 1)
    monkeypatch.setattr(settings, "ai_daily_budget_cents", 100)
    monkeypatch.setattr(settings, "ai_request_cost_ceiling_cents", 10, raising=False)
    sessions = async_sessionmaker(app_engine, expire_on_commit=False, class_=AsyncSession)

    async def reserve() -> bool:
        async with sessions() as db:
            await set_user_context(db, owner_id)
            try:
                await assert_daily_ai_budget(db, owner_user_id=owner_id)
            except AIRequestBudgetExceeded:
                await db.rollback()
                return False
            db.add(
                ModelRun(
                    owner_user_id=owner_id,
                    provider="openai",
                    status="COMPLETED",
                )
            )
            await db.commit()
            return True

    outcomes = await asyncio.gather(reserve(), reserve())
    assert sorted(outcomes) == [False, True]


async def test_daily_ai_cents_budget_uses_an_explicit_ceiling_not_fake_cost(
    client,
    app_engine,
    monkeypatch,
) -> None:
    registration, _, _ = await register_user(client, chosen_name="Cents AI")
    owner_id = uuid.UUID(registration.json()["id"])
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider", "openai")
    monkeypatch.setattr(settings, "ai_per_user_daily_limit", 50)
    monkeypatch.setattr(settings, "ai_daily_budget_cents", 15)
    monkeypatch.setattr(settings, "ai_request_cost_ceiling_cents", 10, raising=False)
    sessions = async_sessionmaker(app_engine, expire_on_commit=False, class_=AsyncSession)

    async with sessions() as db:
        await set_user_context(db, owner_id)
        await assert_daily_ai_budget(db, owner_user_id=owner_id)
        db.add(
            ModelRun(
                owner_user_id=owner_id,
                provider="openai",
                status="COMPLETED",
            )
        )
        await db.commit()

    async with sessions() as db:
        await set_user_context(db, owner_id)
        with pytest.raises(AIRequestBudgetExceeded, match="cost ceiling"):
            await assert_daily_ai_budget(db, owner_user_id=owner_id)
        await db.rollback()

    async with sessions() as db:
        await set_user_context(db, owner_id)
        reservations = (
            await db.execute(
                select(ModelRun).where(
                    ModelRun.owner_user_id == owner_id,
                    ModelRun.provider == "budget_reservation",
                )
            )
        ).scalars().all()
        assert reservations == []


async def test_non_provider_run_does_not_consume_ai_request_or_cents_budget(
    client,
    app_engine,
    monkeypatch,
) -> None:
    registration, _, _ = await register_user(client, chosen_name="Deterministic AI")
    owner_id = uuid.UUID(registration.json()["id"])
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider", "openai")
    monkeypatch.setattr(settings, "ai_per_user_daily_limit", 1)
    monkeypatch.setattr(settings, "ai_daily_budget_cents", 10)
    monkeypatch.setattr(settings, "ai_request_cost_ceiling_cents", 10)
    sessions = async_sessionmaker(app_engine, expire_on_commit=False, class_=AsyncSession)

    async with sessions() as db:
        await set_user_context(db, owner_id)
        await assert_daily_ai_budget(db, owner_user_id=owner_id)
        db.add(
            ModelRun(
                owner_user_id=owner_id,
                provider="DETERMINISTIC_WORKER",
                status="COMPLETED",
            )
        )
        await db.commit()

    async with sessions() as db:
        await set_user_context(db, owner_id)
        await assert_daily_ai_budget(db, owner_user_id=owner_id)
        await db.rollback()


async def test_concurrent_owner_uploads_cannot_oversubscribe_storage(
    client,
    monkeypatch,
) -> None:
    from app.api.v1 import projects as project_routes

    await register_user(client, chosen_name="Concurrent storage")
    project_id = await _project(client)
    settings = get_settings()
    monkeypatch.setattr(settings, "project_storage_quota_bytes", 50)
    monkeypatch.setattr(settings, "upload_rate_limit_max", 20)

    real_storage = project_routes.get_object_storage()

    class SlowStorage:
        async def put(self, chunks, *, max_bytes):
            await asyncio.sleep(0.075)
            return await real_storage.put(chunks, max_bytes=max_bytes)

        def delete(self, object_key: str) -> bool:
            return real_storage.delete(object_key)

    slow_storage = SlowStorage()
    monkeypatch.setattr(project_routes, "get_object_storage", lambda: slow_storage)

    async def upload(name: str, byte: bytes):
        return await client.post(
            f"/api/v1/projects/{project_id}/files",
            headers=_csrf(client),
            files={"upload": (name, byte * 30, "text/plain")},
        )

    first, second = await asyncio.gather(upload("first.txt", b"a"), upload("second.txt", b"b"))
    assert sorted([first.status_code, second.status_code]) == [201, 413]

    listed = await client.get(f"/api/v1/projects/{project_id}/files")
    assert listed.status_code == 200
    assert [item["byte_size"] for item in listed.json()] == [30]


async def test_deleted_project_file_releases_owner_storage_quota(client, monkeypatch) -> None:
    await register_user(client, chosen_name="Quota release")
    project_id = await _project(client)
    settings = get_settings()
    monkeypatch.setattr(settings, "project_storage_quota_bytes", 20)

    first = await client.post(
        f"/api/v1/projects/{project_id}/files",
        headers=_csrf(client),
        files={"upload": ("first.txt", b"a" * 20, "text/plain")},
    )
    assert first.status_code == 201, first.text

    deleted = await client.delete(
        f"/api/v1/projects/files/{first.json()['id']}",
        headers=_csrf(client),
    )
    assert deleted.status_code == 200, deleted.text

    replacement = await client.post(
        f"/api/v1/projects/{project_id}/files",
        headers=_csrf(client),
        files={"upload": ("replacement.txt", b"b" * 20, "text/plain")},
    )
    assert replacement.status_code == 201, replacement.text
