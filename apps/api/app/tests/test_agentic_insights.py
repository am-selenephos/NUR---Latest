import asyncio
import inspect
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.rls import set_user_context
from app.insights.service import consolidate_owner
from app.tests.conftest import register_user


def H(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("nur_csrf")}


async def _seed_owner_corpus(client) -> dict[str, str]:
    journal = await client.post(
        "/api/v1/journal",
        headers=H(client),
        json={"body": "Small release proofs help me return instead of disappearing."},
    )
    assert journal.status_code == 201, journal.text

    plan = await client.post(
        "/api/v1/plans",
        headers=H(client),
        json={
            "title": "Return two bounded release proofs",
            "steps": [{"title": "Ship the first proof", "position": 0}],
        },
    )
    assert plan.status_code == 201, plan.text
    step_id = plan.json()["steps"][0]["id"]
    complete_step = await client.patch(
        f"/api/v1/plan-steps/{step_id}", headers=H(client), json={"done": True}
    )
    assert complete_step.status_code == 200, complete_step.text

    project = await client.post(
        "/api/v1/projects",
        headers=H(client),
        json={
            "title": "Evidence release",
            "objective": "Keep a real project record beside the plan and returned outcomes.",
            "system_slug": "creation",
        },
    )
    assert project.status_code == 201, project.text

    outcome_ids: list[str] = []
    for slug in ("ambition", "creation"):
        goal = await client.post(
            "/api/v1/goals",
            headers=H(client),
            json={"system_slug": slug, "title": f"Return one {slug} proof"},
        )
        assert goal.status_code == 201, goal.text
        action = await client.post(
            f"/api/v1/systems/{slug}/actions",
            headers=H(client),
            json={
                "title": f"Complete the bounded {slug} proof",
                "goal_id": goal.json()["id"],
                "effort_minutes": 10,
            },
        )
        assert action.status_code == 201, action.text
        action_id = action.json()["id"]
        completed = await client.patch(
            f"/api/v1/system-actions/{action_id}",
            headers=H(client),
            json={"status": "COMPLETED"},
        )
        assert completed.status_code == 200, completed.text
        returned = await client.post(
            f"/api/v1/systems/{slug}/actions/{action_id}/return",
            headers=H(client),
            json={
                "observed_result": f"A real {slug} proof was returned.",
                "structured_measurements": {"verified": True},
                "confidence": 0.9,
            },
        )
        assert returned.status_code == 201, returned.text
        outcome_ids.append(returned.json()["outcome"]["id"])

    missed = await client.post(
        "/api/v1/systems/introspection/actions",
        headers=H(client),
        json={"title": "Oversized reflection block", "effort_minutes": 120},
    )
    assert missed.status_code == 201, missed.text
    missed_result = await client.patch(
        f"/api/v1/system-actions/{missed.json()['id']}",
        headers=H(client),
        json={"status": "MISSED"},
    )
    assert missed_result.status_code == 200, missed_result.text

    return {
        "journal_id": journal.json()["id"],
        "plan_id": plan.json()["id"],
        "project_id": project.json()["id"],
        "first_outcome_id": outcome_ids[0],
    }


async def _add_returned_action(client, *, slug: str, title: str, result: str) -> str:
    action = await client.post(
        f"/api/v1/systems/{slug}/actions",
        headers=H(client),
        json={"title": title, "effort_minutes": 15},
    )
    assert action.status_code == 201, action.text
    action_id = action.json()["id"]
    completed = await client.patch(
        f"/api/v1/system-actions/{action_id}",
        headers=H(client),
        json={"status": "COMPLETED"},
    )
    assert completed.status_code == 200, completed.text
    returned = await client.post(
        f"/api/v1/systems/{slug}/actions/{action_id}/return",
        headers=H(client),
        json={
            "observed_result": result,
            "structured_measurements": {"verified": True},
            "confidence": 0.9,
        },
    )
    assert returned.status_code == 201, returned.text
    return returned.json()["outcome"]["id"]


async def _make_longitudinal(admin_engine, owner_user_id: str) -> None:
    async with admin_engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('app.current_user_id', :owner, true)"),
            {"owner": owner_user_id},
        )
        await connection.execute(
            text(
                """
                WITH ranked AS (
                    SELECT id, row_number() OVER (ORDER BY created_at, id) AS n
                    FROM cognitive_events
                    WHERE owner_user_id = :owner
                )
                UPDATE cognitive_events AS event
                SET created_at = event.created_at - make_interval(days => (ranked.n * 8)::integer)
                FROM ranked
                WHERE event.id = ranked.id
                """
            ),
            {"owner": owner_user_id},
        )


async def test_cross_domain_longitudinal_insight_evidence_correction_and_isolation(
    client, admin_engine
):
    owner, _, _ = await register_user(client, chosen_name="Agentic Insight Owner")
    owner_id = owner.json()["id"]
    seeded = await _seed_owner_corpus(client)
    await _make_longitudinal(admin_engine, owner_id)

    consolidated = await client.post(
        "/api/v1/insights/consolidate",
        headers=H(client),
        json={"run_kind": "MANUAL"},
    )
    assert consolidated.status_code == 200, consolidated.text
    result = consolidated.json()
    assert result["processed_observations"] <= result["max_observations"]
    assert result["surfaced_insight_id"]

    insight_id = result["surfaced_insight_id"]
    detail = await client.get(f"/api/v1/insights/{insight_id}")
    assert detail.status_code == 200, detail.text
    candidate = detail.json()
    assert candidate["lifecycle_status"] == "SURFACED"
    assert candidate["epistemic_state"] == "INFERRED"
    assert candidate["time_scale"] == "LONGITUDINAL"
    assert len(candidate["source_domains"]) >= 2
    assert candidate["source_diversity"] >= 2
    assert candidate["alternative_explanations"]
    assert candidate["what_nur_may_be_wrong_about"]
    assert candidate["quality_dimensions"]["passes"] is True
    assert candidate["canonical_links"]["timeline"] == "/universe/timeline"
    assert candidate["canonical_links"]["map"] == "/universe/map"
    assert candidate["canonical_links"]["project"].endswith(seeded["project_id"])

    evidence = await client.get(f"/api/v1/insights/{insight_id}/evidence")
    assert evidence.status_code == 200, evidence.text
    relations = evidence.json()["relations"]
    assert any(row["relation"] == "SUPPORTS" for row in relations)
    assert any(row["relation"] == "CONTRADICTS" for row in relations)
    assert all(row["source_exists"] is True for row in relations)
    assert all(row["source_id"] for row in relations)

    corrected = await client.post(
        f"/api/v1/insights/{insight_id}/correct",
        headers=H(client),
        json={"correction": "The release support and reduced scope both mattered; size alone did not explain it."},
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["lifecycle_status"] == "OWNER_CORRECTED"
    assert corrected.json()["insight_version"] == candidate["insight_version"] + 1

    why = await client.get(f"/api/v1/insights/{insight_id}/why-changed")
    assert why.status_code == 200, why.text
    changes = why.json()["changes"]
    assert any(row["change_class"] == "created" for row in changes)
    assert any(row["change_class"] == "corrected" and row["owner_correction"] for row in changes)
    assert all("chain" not in str(row).lower() for row in changes)

    client.cookies.clear()
    other, _, _ = await register_user(client, chosen_name="Other Insight Owner")
    assert other.json()["id"] != owner_id
    assert (await client.get(f"/api/v1/insights/{insight_id}")).status_code == 404
    assert (await client.get(f"/api/v1/insights/{insight_id}/evidence")).status_code == 404
    assert (await client.get(f"/api/v1/insights/{insight_id}/why-changed")).status_code == 404
    assert (await client.get("/api/v1/insights")).json() == []


async def test_rejected_evidence_does_not_resurrect_until_material_change(
    client, admin_engine
):
    owner, _, _ = await register_user(client, chosen_name="Non Resurrection Owner")
    owner_id = owner.json()["id"]
    await _seed_owner_corpus(client)
    await _make_longitudinal(admin_engine, owner_id)
    first = await client.post(
        "/api/v1/insights/consolidate", headers=H(client), json={"run_kind": "MANUAL"}
    )
    assert first.status_code == 200, first.text
    first_id = first.json()["surfaced_insight_id"]

    rejected = await client.post(f"/api/v1/insights/{first_id}/reject", headers=H(client))
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["lifecycle_status"] == "OWNER_REJECTED"

    unchanged = await client.post(
        "/api/v1/insights/consolidate", headers=H(client), json={"run_kind": "MANUAL"}
    )
    assert unchanged.status_code == 200, unchanged.text
    assert unchanged.json()["surfaced_insight_id"] is None
    assert unchanged.json()["suppressed_reason"] == "UNCHANGED_REJECTED_EVIDENCE"
    assert unchanged.json()["suppressed_insight_id"] == first_id

    await _add_returned_action(
        client,
        slug="growth",
        title="Return a materially new release proof",
        result="External support removed the release blocker.",
    )
    changed = await client.post(
        "/api/v1/insights/consolidate", headers=H(client), json={"run_kind": "MANUAL"}
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["surfaced_insight_id"] not in {None, first_id}
    next_detail = (
        await client.get(f"/api/v1/insights/{changed.json()['surfaced_insight_id']}")
    ).json()
    assert next_detail["parent_insight_id"] == first_id
    assert next_detail["insight_version"] == rejected.json()["insight_version"] + 1


async def test_source_deletion_retracts_or_versions_material_insight(
    client, admin_engine
):
    owner, _, _ = await register_user(client, chosen_name="Source Lifecycle Owner")
    owner_id = owner.json()["id"]
    await _seed_owner_corpus(client)
    await _make_longitudinal(admin_engine, owner_id)
    result = (
        await client.post(
            "/api/v1/insights/consolidate", headers=H(client), json={"run_kind": "MANUAL"}
        )
    ).json()
    insight_id = result["surfaced_insight_id"]
    relations = (
        await client.get(f"/api/v1/insights/{insight_id}/evidence")
    ).json()["relations"]
    source = next(
        row
        for row in relations
        if row["source_kind"] == "OUTCOME" and row["relation"] == "SUPPORTS"
    )

    async with admin_engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM outcomes WHERE id = :source_id"),
            {"source_id": source["source_id"]},
        )

    reconciled = await client.post(
        "/api/v1/insights/consolidate", headers=H(client), json={"run_kind": "MANUAL"}
    )
    assert reconciled.status_code == 200, reconciled.text
    assert reconciled.json()["invalidated_relations"] >= 1
    prior = (await client.get(f"/api/v1/insights/{insight_id}")).json()
    assert prior["lifecycle_status"] in {"SUPERSEDED", "RETRACTED"}
    assert prior["source_invalidated_at"] is not None


async def test_repeated_owner_feedback_generates_nur_blind_spot(client, admin_engine):
    owner, _, _ = await register_user(client, chosen_name="NUR Calibration Owner")
    await _seed_owner_corpus(client)
    await _make_longitudinal(admin_engine, owner.json()["id"])
    first = (
        await client.post(
            "/api/v1/insights/consolidate", headers=H(client), json={"run_kind": "MANUAL"}
        )
    ).json()["surfaced_insight_id"]
    await client.post(f"/api/v1/insights/{first}/reject", headers=H(client))

    await _add_returned_action(
        client,
        slug="growth",
        title="Return a second calibration proof",
        result="A bounded proof returned after the owner rejected NUR's first framing.",
    )
    second = (
        await client.post(
            "/api/v1/insights/consolidate", headers=H(client), json={"run_kind": "MANUAL"}
        )
    ).json()["surfaced_insight_id"]
    await client.post(
        f"/api/v1/insights/{second}/correct",
        headers=H(client),
        json={"correction": "NUR ignored external support and over-weighted action size."},
    )

    calibration = await client.post(
        "/api/v1/insights/consolidate", headers=H(client), json={"run_kind": "MANUAL"}
    )
    assert calibration.status_code == 200, calibration.text
    self_id = calibration.json()["self_insight_id"]
    assert self_id
    self_insight = (await client.get(f"/api/v1/insights/{self_id}")).json()
    assert self_insight["insight_type"] == "NUR_BLIND_SPOT"
    assert self_insight["calibration_target"] == "NUR_INFERENCE"
    assert self_insight["epistemic_state"] == "INFERRED"
    assert self_insight["alternative_explanations"]


async def test_agentic_insight_tables_force_rls(client, app_engine):
    owner_a, _, _ = await register_user(client, chosen_name="RLS Insight A")
    await _seed_owner_corpus(client)
    client.cookies.clear()
    owner_b, _, _ = await register_user(client, chosen_name="RLS Insight B")
    tables = [
        "insight_patterns",
        "insight_evidence_relations",
        "insight_feedback",
        "insight_projection_checkpoints",
        "insight_projection_runs",
        "why_changed_records",
    ]
    async with app_engine.connect() as connection:
        await connection.execute(
            text("SELECT set_config('app.current_user_id', :owner, false)"),
            {"owner": owner_b.json()["id"]},
        )
        flags = (
            await connection.execute(
                text(
                    """
                    SELECT relname, relrowsecurity, relforcerowsecurity
                    FROM pg_class WHERE relname = ANY(:tables) ORDER BY relname
                    """
                ),
                {"tables": tables},
            )
        ).all()
        assert len(flags) == len(tables)
        assert all(row.relrowsecurity and row.relforcerowsecurity for row in flags)
        for table in tables:
            assert (
                await connection.execute(text(f"SELECT count(*) FROM {table}"))
            ).scalar_one() == 0
    assert owner_a.json()["id"] != owner_b.json()["id"]


async def test_forged_cross_owner_evidence_source_is_rejected(
    client, app_engine, admin_engine
):
    owner_a, _, _ = await register_user(client, chosen_name="Evidence Owner A")
    seeded_a = await _seed_owner_corpus(client)
    await _make_longitudinal(admin_engine, owner_a.json()["id"])
    run_a = await client.post(
        "/api/v1/insights/consolidate", headers=H(client), json={"run_kind": "MANUAL"}
    )
    insight_a = run_a.json()["surfaced_insight_id"]

    client.cookies.clear()
    owner_b, _, _ = await register_user(client, chosen_name="Evidence Owner B")
    seeded_b = await _seed_owner_corpus(client)
    assert seeded_a["first_outcome_id"] != seeded_b["first_outcome_id"]

    async with app_engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('app.current_user_id', :owner, true)"),
            {"owner": owner_a.json()["id"]},
        )
        with pytest.raises(IntegrityError, match="invalid or cross-owner"):
            async with connection.begin_nested():
                await connection.execute(
                    text(
                        """
                        INSERT INTO insight_evidence_relations(
                            owner_user_id, insight_id, source_kind, source_id,
                            source_domain, relation, provenance_label, explicitness,
                            confidence, insight_version
                        ) VALUES (
                            :owner, :insight, 'OUTCOME', :foreign_source,
                            'OUTCOME', 'SUPPORTS', 'OBSERVED_OUTCOME',
                            'SYSTEM_OBSERVED', 0.9, 1
                        )
                        """
                    ),
                    {
                        "owner": owner_a.json()["id"],
                        "insight": insight_a,
                        "foreign_source": seeded_b["first_outcome_id"],
                    },
                )


async def test_concurrent_same_key_consolidation_creates_one_run(
    client, app_engine, admin_engine
):
    owner, _, _ = await register_user(client, chosen_name="Insight Concurrency Owner")
    owner_id = uuid.UUID(owner.json()["id"])
    await _seed_owner_corpus(client)
    await _make_longitudinal(admin_engine, str(owner_id))
    sessions = async_sessionmaker(app_engine, expire_on_commit=False)

    async def execute_once() -> uuid.UUID:
        async with sessions() as db:
            await set_user_context(db, owner_id)
            run = await consolidate_owner(
                db,
                owner_user_id=owner_id,
                run_kind="EVENT",
                idempotency_key="concurrency-proof-v1",
                worker_id="test-worker",
            )
            await db.commit()
            return run.id

    first_id, second_id = await asyncio.gather(execute_once(), execute_once())
    assert first_id == second_id
    async with app_engine.connect() as connection:
        await connection.execute(
            text("SELECT set_config('app.current_user_id', :owner, false)"),
            {"owner": str(owner_id)},
        )
        count = (
            await connection.execute(
                text(
                    "SELECT count(*) FROM insight_projection_runs "
                    "WHERE idempotency_key = 'concurrency-proof-v1'"
                )
            )
        ).scalar_one()
        assert count == 1


def test_insight_worker_tasks_and_periodic_schedules_are_real():
    from app.workers import tasks
    from app.workers.celery_app import celery

    celery.loader.import_default_modules()
    celery.finalize()
    assert "nur.insights_consolidate_owner" in celery.tasks
    assert "nur.insights_consolidate_due_owners" in celery.tasks
    assert list(inspect.signature(tasks.insights_consolidate_owner_task).parameters) == [
        "owner_user_id",
        "run_kind",
    ]
    schedule = celery.conf.beat_schedule
    assert schedule["nur-insights-event-consolidation"]["args"] == ("EVENT",)
    assert schedule["nur-insights-daily-consolidation"]["args"] == ("DAILY",)
    assert schedule["nur-insights-weekly-consolidation"]["args"] == ("WEEKLY",)
