"""Timeline, through real HTTP against real PostgreSQL.

Timeline claims to distinguish what was planned from what actually happened, and
never to convert one into the other silently. The tests that matter most are
therefore the refusals: that "unscheduled" cannot quietly carry a date, that a
completion verdict needs an actual end recorded with it, that a ripple never
moves a downstream item without the owner's chosen mode, that dependencies reuse
`map_edges` rather than a second table, and that no owner can read another's
timeline.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import text

from app.tests.conftest import register_user

API = "/api/v1"


async def _csrf(client) -> dict:
    return {"X-CSRF-Token": client.cookies.get("nur_csrf")}


async def _entry(client, title="Record NUR demo", event_type="ACTION", **extra) -> dict:
    body = {"event_type": event_type, "title": title, "source_type": "OWNER", **extra}
    response = await client.post(f"{API}/timeline/events", json=body, headers=await _csrf(client))
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture()
async def owner(client):
    response, email, password = await register_user(client)
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


def _iso(offset_days: float = 0.0) -> str:
    return (dt.datetime.now(dt.UTC) + dt.timedelta(days=offset_days)).isoformat()


# ── composition over canonical rows ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_flow_composes_canonical_entries_and_scheduled_actions(client, owner):
    """The Flow view has no store of its own — an entry created through the
    canonical endpoint must appear, alongside a `scheduled_actions` row read
    from Living's own table rather than a Timeline duplicate."""
    entry = await _entry(client, scheduled_for=_iso(1))
    schedule = await client.post(
        f"{API}/schedules",
        json={"system_slug": "creation", "title": "Deep work block", "scheduled_for": _iso(2)},
        headers=await _csrf(client),
    )
    assert schedule.status_code == 201, schedule.text

    flow = (await client.get(f"{API}/timeline/flow")).json()
    refs = {row["ref"] for row in flow["entries"]}
    assert f"timeline_event:{entry['id']}" in refs
    assert f"scheduled_action:{schedule.json()['id']}" in refs
    assert flow["provenance_label"] == "OWNER_TIMELINE_LEDGER"


@pytest.mark.asyncio
async def test_an_empty_timeline_is_empty_not_seeded(client, owner):
    flow = (await client.get(f"{API}/timeline/flow")).json()
    assert flow["entries"] == []
    assert flow["unscheduled"] == []
    assert flow["counts"]["total"] == 0


# ── truth model: unscheduled cannot carry a date ─────────────────────────────


@pytest.mark.asyncio
async def test_unscheduled_cannot_quietly_carry_a_date(client, owner):
    """§17. Falsified directly against the database, not just asserted in Python."""
    from app.db.session import get_sessionmaker
    from app.models import TimelineEvent
    from sqlalchemy.exc import IntegrityError

    maker = get_sessionmaker()
    async with maker() as db:
        await db.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"),
            {"uid": str(owner)},
        )
        db.add(TimelineEvent(
            owner_user_id=owner, event_type="ACTION", title="x", source_type="OWNER",
            date_precision="UNSCHEDULED", scheduled_for=dt.datetime.now(dt.UTC),
        ))
        with pytest.raises(IntegrityError) as caught:
            await db.commit()
    assert "ck_timeline_event_unscheduled_has_no_date" in str(caught.value)


@pytest.mark.asyncio
async def test_unscheduled_entries_appear_in_the_holding_field(client, owner):
    entry = await _entry(client, date_precision="UNSCHEDULED")
    flow = (await client.get(f"{API}/timeline/flow")).json()
    refs = {row["ref"] for row in flow["unscheduled"]}
    assert f"timeline_event:{entry['id']}" in refs
    assert f"timeline_event:{entry['id']}" not in {row["ref"] for row in flow["entries"]}


# ── truth model: no silent conversions ───────────────────────────────────────


@pytest.mark.asyncio
async def test_a_completion_verdict_needs_an_actual_end_recorded_with_it(client, owner):
    entry = await _entry(client)
    response = await client.post(
        f"{API}/timeline/entries/{entry['id']}/actual",
        json={"completion_state": "SUCCESSFUL"},
        headers=await _csrf(client),
    )
    assert response.status_code == 422, response.text
    assert "actual end" in response.text.lower()

    with_end = await client.post(
        f"{API}/timeline/entries/{entry['id']}/actual",
        json={"completion_state": "SUCCESSFUL", "actual_end_at": _iso()},
        headers=await _csrf(client),
    )
    assert with_end.status_code == 200, with_end.text
    assert with_end.json()["completion_state"] == "SUCCESSFUL"


@pytest.mark.asyncio
async def test_predicted_can_only_become_observed_through_the_named_endpoint(client, owner):
    """§5: predicted must never silently become actual. There is no PATCH status."""
    entry = await _entry(client, status="PREDICTED")
    confirmed = await client.post(
        f"{API}/timeline/entries/{entry['id']}/confirm-observed",
        headers=await _csrf(client),
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "OBSERVED"

    again = await client.post(
        f"{API}/timeline/entries/{entry['id']}/confirm-observed",
        headers=await _csrf(client),
    )
    assert again.status_code == 409, again.text


@pytest.mark.asyncio
async def test_there_is_no_generic_status_patch_route(client, owner):
    """The absence is the point: only named transitions may move `status`."""
    entry = await _entry(client)
    response = await client.patch(
        f"{API}/timeline/entries/{entry['id']}",
        json={"status": "COMPLETED"},
        headers=await _csrf(client),
    )
    assert response.status_code in {404, 405}, response.text


# ── reschedule history ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reschedule_with_history_preserves_the_original_time(client, owner):
    entry = await _entry(client, scheduled_for=_iso(1))
    original = entry["scheduled_for"]
    moved = await client.post(
        f"{API}/timeline/entries/{entry['id']}/reschedule-with-history",
        json={"new_start_at": _iso(3), "reason": "Codex usage unavailable"},
        headers=await _csrf(client),
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["status"] == "RESCHEDULED"

    history = (await client.get(
        f"{API}/timeline/entries/{entry['id']}/reschedule-history"
    )).json()
    assert len(history["items"]) == 1
    row = history["items"][0]
    assert row["previous_start_at"] == original
    assert row["reason"] == "Codex usage unavailable"
    assert row["source"] == "OWNER"


# ── dependencies reuse map_edges ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_dependency_is_a_map_edge_not_a_second_table(client, owner):
    first = await _entry(client, title="Understand the architecture")
    second = await _entry(client, title="Record the walkthrough")
    created = await client.post(
        f"{API}/timeline/dependencies",
        json={
            "predecessor_ref_type": "timeline_event", "predecessor_ref_id": first["id"],
            "successor_ref_type": "timeline_event", "successor_ref_id": second["id"],
            "dependency_kind": "FINISH_BEFORE", "lag_minutes": 30,
        },
        headers=await _csrf(client),
    )
    assert created.status_code == 201, created.text
    assert created.json()["user_confirmed"] is True

    from app.db.session import get_sessionmaker

    maker = get_sessionmaker()
    async with maker() as db:
        await db.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"),
            {"uid": str(owner)},
        )
        rows = (await db.execute(text(
            "SELECT edge_type FROM map_edges WHERE id = :id"
        ), {"id": created.json()["id"]})).all()
    assert rows and rows[0][0] == "DEPENDS_ON"

    deps = (await client.get(f"{API}/timeline/entries/{second['id']}/dependencies")).json()
    assert len(deps["predecessors"]) == 1
    assert deps["predecessors"][0]["dependency_kind"] == "FINISH_BEFORE"
    assert deps["predecessors"][0]["lag_minutes"] == 30


@pytest.mark.asyncio
async def test_an_item_cannot_depend_on_itself(client, owner):
    entry = await _entry(client)
    response = await client.post(
        f"{API}/timeline/dependencies",
        json={
            "predecessor_ref_type": "timeline_event", "predecessor_ref_id": entry["id"],
            "successor_ref_type": "timeline_event", "successor_ref_id": entry["id"],
        },
        headers=await _csrf(client),
    )
    assert response.status_code == 422, response.text


# ── ripple: preview persists nothing, apply requires a mode ─────────────────


@pytest.mark.asyncio
async def test_ripple_preview_persists_nothing(client, owner):
    first = await _entry(client, title="Finish walkthrough", scheduled_for=_iso(1))
    second = await _entry(client, title="Publish case study", scheduled_for=_iso(2))
    await client.post(
        f"{API}/timeline/dependencies",
        json={
            "predecessor_ref_type": "timeline_event", "predecessor_ref_id": first["id"],
            "successor_ref_type": "timeline_event", "successor_ref_id": second["id"],
        },
        headers=await _csrf(client),
    )
    preview = await client.post(
        f"{API}/timeline/ripple-preview",
        json={"entry_id": first["id"], "new_start_at": _iso(4)},
        headers=await _csrf(client),
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert len(body["affected"]) == 1
    assert body["affected"][0]["ref"] == f"timeline_event:{second['id']}"
    assert body["requires_confirmation"] is True

    # Nothing was written: refetching the second entry shows its original time.
    unchanged = (await client.get(f"{API}/timeline/flow")).json()
    row = next(r for r in unchanged["entries"] if r["ref"] == f"timeline_event:{second['id']}")
    assert row["scheduled_for"] == second["scheduled_for"]


@pytest.mark.asyncio
async def test_ripple_apply_move_only_never_touches_dependents(client, owner):
    first = await _entry(client, title="Finish walkthrough", scheduled_for=_iso(1))
    second = await _entry(client, title="Publish case study", scheduled_for=_iso(2))
    await client.post(
        f"{API}/timeline/dependencies",
        json={
            "predecessor_ref_type": "timeline_event", "predecessor_ref_id": first["id"],
            "successor_ref_type": "timeline_event", "successor_ref_id": second["id"],
        },
        headers=await _csrf(client),
    )
    applied = await client.post(
        f"{API}/timeline/ripple-apply",
        json={"entry_id": first["id"], "new_start_at": _iso(4), "mode": "MOVE_ONLY"},
        headers=await _csrf(client),
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["dependents_moved"] == []

    flow = (await client.get(f"{API}/timeline/flow")).json()
    row = next(r for r in flow["entries"] if r["ref"] == f"timeline_event:{second['id']}")
    assert row["scheduled_for"] == second["scheduled_for"]


@pytest.mark.asyncio
async def test_ripple_apply_shift_dependents_moves_them_and_records_history(client, owner):
    first = await _entry(client, title="Finish walkthrough", scheduled_for=_iso(1))
    second = await _entry(client, title="Publish case study", scheduled_for=_iso(2))
    await client.post(
        f"{API}/timeline/dependencies",
        json={
            "predecessor_ref_type": "timeline_event", "predecessor_ref_id": first["id"],
            "successor_ref_type": "timeline_event", "successor_ref_id": second["id"],
        },
        headers=await _csrf(client),
    )
    applied = await client.post(
        f"{API}/timeline/ripple-apply",
        json={"entry_id": first["id"], "new_start_at": _iso(4), "mode": "SHIFT_DEPENDENTS"},
        headers=await _csrf(client),
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["dependents_moved"] == [f"timeline_event:{second['id']}"]

    history = (await client.get(
        f"{API}/timeline/entries/{second['id']}/reschedule-history"
    )).json()
    assert len(history["items"]) == 1
    assert history["items"][0]["source"] == "RIPPLE"


# ── recurrences ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_flexible_rhythm_needs_a_target_frequency(client, owner):
    entry = await _entry(client)
    response = await client.put(
        f"{API}/timeline/entries/{entry['id']}/recurrence",
        json={"recurrence_rule": "3x/week", "recurrence_mode": "FLEXIBLE", "starts_at": _iso()},
        headers=await _csrf(client),
    )
    assert response.status_code == 422, response.text

    with_target = await client.put(
        f"{API}/timeline/entries/{entry['id']}/recurrence",
        json={
            "recurrence_rule": "3x/week", "recurrence_mode": "FLEXIBLE",
            "target_frequency": 3, "starts_at": _iso(),
        },
        headers=await _csrf(client),
    )
    assert with_target.status_code == 200, with_target.text
    assert with_target.json()["target_frequency"] == 3


@pytest.mark.asyncio
async def test_pausing_a_recurrence_is_reversible(client, owner):
    entry = await _entry(client)
    await client.put(
        f"{API}/timeline/entries/{entry['id']}/recurrence",
        json={"recurrence_rule": "daily", "starts_at": _iso()},
        headers=await _csrf(client),
    )
    paused = await client.post(
        f"{API}/timeline/entries/{entry['id']}/recurrence/pause", headers=await _csrf(client),
    )
    assert paused.status_code == 200, paused.text
    assert paused.json()["paused_at"] is not None
    resumed = await client.post(
        f"{API}/timeline/entries/{entry['id']}/recurrence/resume", headers=await _csrf(client),
    )
    assert resumed.json()["paused_at"] is None


# ── phases ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_phase_span_must_be_ordered(client, owner):
    response = await client.post(
        f"{API}/timeline/phases",
        json={"name": "NUR Beta Completion", "starts_at": _iso(5), "ends_at": _iso(1)},
        headers=await _csrf(client),
    )
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_a_phase_can_be_created_and_patched(client, owner):
    created = await client.post(
        f"{API}/timeline/phases",
        json={"name": "NUR Beta Completion", "starts_at": _iso(0), "ends_at": _iso(30)},
        headers=await _csrf(client),
    )
    assert created.status_code == 201, created.text
    patched = await client.patch(
        f"{API}/timeline/phases/{created.json()['id']}",
        json={"status": "ACTIVE"},
        headers=await _csrf(client),
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["status"] == "ACTIVE"


# ── conflict detection ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_overlapping_events_are_detected(client, owner):
    await _entry(client, title="NUR demo recording", scheduled_for=_iso(1), ends_at=_iso(1.08))
    await _entry(client, title="Group consultation", scheduled_for=_iso(1.03), ends_at=_iso(1.1))
    analysis = await client.post(
        f"{API}/timeline/conflict-analysis",
        json={"range_start": _iso(-1), "range_end": _iso(3)},
        headers=await _csrf(client),
    )
    assert analysis.status_code == 200, analysis.text
    body = analysis.json()
    assert len(body["overlaps"]) == 1
    assert body["provenance_label"] == "DETERMINISTIC_FRAME"


@pytest.mark.asyncio
async def test_workload_is_unknown_without_configured_capacity(client, owner):
    """§21: avoid fake scores. No capacity input exists yet, so every day says so."""
    await _entry(client, scheduled_for=_iso(1), ends_at=_iso(1.3))
    analysis = await client.post(
        f"{API}/timeline/conflict-analysis",
        json={"range_start": _iso(-1), "range_end": _iso(3)},
        headers=await _csrf(client),
    )
    body = analysis.json()
    assert body["capacity_configured"] is False
    assert all(state == "UNKNOWN" for state in body["load_by_day"].values())


@pytest.mark.asyncio
async def test_a_dependency_order_violation_is_detected(client, owner):
    first = await _entry(client, title="Finish walkthrough", scheduled_for=_iso(2))
    second = await _entry(client, title="Publish case study", scheduled_for=_iso(1))
    await client.post(
        f"{API}/timeline/dependencies",
        json={
            "predecessor_ref_type": "timeline_event", "predecessor_ref_id": first["id"],
            "successor_ref_type": "timeline_event", "successor_ref_id": second["id"],
        },
        headers=await _csrf(client),
    )
    analysis = (await client.post(
        f"{API}/timeline/conflict-analysis",
        json={"range_start": _iso(-1), "range_end": _iso(4)},
        headers=await _csrf(client),
    )).json()
    assert len(analysis["dependency_order_violations"]) == 1
    assert analysis["dependency_order_violations"][0]["successor_ref"] == f"timeline_event:{second['id']}"


# ── reviews ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generated_review_is_deterministic_and_labelled(client, owner):
    entry = await _entry(client, scheduled_for=_iso(-1))
    await client.post(
        f"{API}/timeline/entries/{entry['id']}/actual",
        json={"actual_end_at": _iso(-1), "completion_state": "SUCCESSFUL"},
        headers=await _csrf(client),
    )
    generated = await client.post(
        f"{API}/timeline/reviews/generate",
        json={
            "review_type": "WEEKLY",
            "period_start": _iso(-7), "period_end": _iso(1),
        },
        headers=await _csrf(client),
    )
    assert generated.status_code == 201, generated.text
    findings = generated.json()["findings"][0]
    assert findings["provenance_label"] == "DETERMINISTIC_FRAME"
    assert findings["period_entry_count"] >= 1


@pytest.mark.asyncio
async def test_a_manual_review_stores_the_owners_own_words(client, owner):
    created = await client.post(
        f"{API}/timeline/reviews",
        json={
            "review_type": "DAILY", "period_start": _iso(-1), "period_end": _iso(),
            "summary": "Moved fast today, no meaningful Glow.",
        },
        headers=await _csrf(client),
    )
    assert created.status_code == 201, created.text
    assert created.json()["summary"] == "Moved fast today, no meaningful Glow."


# ── external sync: honestly disconnected ─────────────────────────────────────


@pytest.mark.asyncio
async def test_external_sync_never_reports_a_fake_connection(client, owner):
    status = (await client.get(f"{API}/timeline/external-sync/status")).json()
    assert status["connected"] is False
    assert status["available_providers"] == []

    sync = await client.post(f"{API}/timeline/external-sync", headers=await _csrf(client))
    assert sync.status_code == 503, sync.text
    assert "No calendar provider is connected" in sync.text


# ── preferences ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_preferences_default_to_flow_and_round_trip(client, owner):
    defaults = (await client.get(f"{API}/timeline/preferences")).json()
    assert defaults["view_mode"] == "FLOW"
    patched = await client.patch(
        f"{API}/timeline/preferences",
        json={"view_mode": "HORIZONS", "lane_grouping": "SYSTEM"},
        headers=await _csrf(client),
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["view_mode"] == "HORIZONS"
    assert patched.json()["lane_grouping"] == "SYSTEM"


# ── smart sections and horizons ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_smart_sections_surface_real_rows_only(client, owner):
    overdue = await _entry(client, scheduled_for=_iso(-2), status="SCHEDULED")
    unscheduled = await _entry(client, date_precision="UNSCHEDULED")
    body = (await client.get(f"{API}/timeline/smart-sections")).json()
    assert any(row["ref"] == f"timeline_event:{overdue['id']}" for row in body["overdue"])
    assert any(row["ref"] == f"timeline_event:{unscheduled['id']}" for row in body["unscheduled"])
    assert body["provenance_label"] == "OWNER_TIMELINE_LEDGER"


@pytest.mark.asyncio
async def test_horizons_bucket_a_goal_by_its_target_date(client, owner):
    soon = dt.date.today() + dt.timedelta(days=20)
    goal = await client.post(
        f"{API}/goals",
        json={"system_slug": "creation", "title": "Ship the beta", "target_date": soon.isoformat()},
        headers=await _csrf(client),
    )
    assert goal.status_code == 201, goal.text
    horizons = (await client.get(f"{API}/timeline/horizons")).json()
    thirty = {row["ref"] for row in horizons["buckets"]["THIRTY_DAYS"]}
    assert f"goal:{goal.json()['id']}" in thirty


# ── isolation ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_owner_can_read_or_move_another_owners_timeline(client, owner):
    entry = await _entry(client, title="Private entry", scheduled_for=_iso(1))
    phase = await client.post(
        f"{API}/timeline/phases", json={"name": "Private phase"}, headers=await _csrf(client),
    )
    assert phase.status_code == 201

    second, _, _ = await register_user(client)
    assert second.status_code == 201, second.text

    assert (await client.get(
        f"{API}/timeline/entries/{entry['id']}/reschedule-history"
    )).status_code == 404
    assert (await client.post(
        f"{API}/timeline/entries/{entry['id']}/start", headers=await _csrf(client),
    )).status_code == 404
    assert (await client.patch(
        f"{API}/timeline/phases/{phase.json()['id']}",
        json={"status": "ACTIVE"}, headers=await _csrf(client),
    )).status_code == 404

    flow = (await client.get(f"{API}/timeline/flow")).json()
    assert f"timeline_event:{entry['id']}" not in {row["ref"] for row in flow["entries"]}
