"""Bounded load and recovery (Phase 16).

A burst of concurrent uploads must be *bounded* by the per-owner limiter rather
than all admitted or crashing the process, the service must stay responsive
throughout, and once the window clears the owner can proceed again — the system
degrades and recovers, it does not fall over.
"""

import asyncio

from app.core.config import get_settings
from app.tests.conftest import register_user

from .conftest import clear_run_keys


def H(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("nur_csrf")}


async def _make_project(client) -> str:
    r = await client.post(
        "/api/v1/projects", headers=H(client),
        json={"title": "Load", "objective": "Stay bounded under a burst."},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _upload(client, project_id: str, i: int):
    return await client.post(
        f"/api/v1/projects/{project_id}/files", headers=H(client),
        files={"upload": (f"burst-{i}.txt", f"payload-{i}".encode(), "text/plain")},
    )


async def test_upload_burst_is_bounded_and_service_recovers(client, monkeypatch):
    await register_user(client, chosen_name="Load Owner")
    project_id = await _make_project(client)

    cap = 5
    burst = 25
    monkeypatch.setattr(get_settings(), "upload_rate_limit_max", cap)
    monkeypatch.setattr(get_settings(), "upload_rate_limit_window_seconds", 300)

    # Fire the whole burst concurrently.
    responses = await asyncio.gather(*[_upload(client, project_id, i) for i in range(burst)])
    codes = [r.status_code for r in responses]
    accepted = sum(1 for c in codes if c == 201)
    throttled = sum(1 for c in codes if c == 429)

    # Bounded: no more than the cap were admitted, the rest were cleanly throttled,
    # and every request got a definite answer (nothing hung or 5xx'd).
    assert accepted <= cap, codes
    assert accepted >= 1
    assert throttled >= 1
    assert accepted + throttled == burst, codes

    # Responsive: the service still answers liveness while throttling.
    assert (await client.get("/healthz")).status_code == 200

    # Recovery: once the window clears (simulated by resetting the limiter), the
    # owner can upload again — the throttle was temporary, not a wedged state.
    # Clear only this run's keys; flushdb is server-wide and would wipe the
    # limiter state of any concurrently running suite.
    await clear_run_keys(client.app.state.redis)
    recovered = await _upload(client, project_id, 999)
    assert recovered.status_code == 201, recovered.text
