import datetime as dt

from sqlalchemy import text

from app.tests.conftest import register_user


SYSTEM_SLUGS = (
    "ambition",
    "rebuild",
    "creation",
    "growth",
    "introspection",
    "connection",
)


def H(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("nur_csrf")}


async def test_today_system_goal_schedule_glow_and_timeline_are_one_persisted_flow(client):
    await register_user(client, chosen_name="Living System Owner")

    initial_systems = (await client.get("/api/v1/systems")).json()["systems"]
    assert [row["title"] for row in initial_systems] == [
        "Ambition",
        "Rebuild",
        "Creation",
        "Growth",
        "Introspection",
        "Connection",
    ]
    assert all(row["progress_percent"] == 0 for row in initial_systems)

    diagnostic = await client.post(
        "/api/v1/systems/ambition/diagnostics",
        headers=H(client),
        json={
            "answers": {"private_direction": "Ship one real NUR slice."},
            "ratings": {"clarity": 8, "protection": 6, "movement": 5},
            "blockers": ["scope expansion"],
            "strengths": ["continuity"],
        },
    )
    assert diagnostic.status_code == 201
    assert diagnostic.json()["score"] == 63
    assert diagnostic.json()["glow"]["awarded_points"] == 3

    goal = await client.post(
        "/api/v1/goals",
        headers=H(client),
        json={
            "system_slug": "ambition",
            "title": "Ship the persisted daily operating slice",
            "why": "Turn private direction into verified movement.",
        },
    )
    assert goal.status_code == 201
    assert goal.json()["glow"]["awarded_points"] == 8

    objective = await client.post(
        f"/api/v1/goals/{goal.json()['id']}/objectives",
        headers=H(client),
        json={"title": "Complete one real end-to-end action"},
    )
    assert objective.status_code == 201
    assert objective.json()["glow"]["awarded_points"] == 6

    action = await client.post(
        "/api/v1/systems/ambition/actions",
        headers=H(client),
        json={
            "title": "Run the real owner journey test",
            "goal_id": goal.json()["id"],
            "objective_id": objective.json()["id"],
            "diagnostic_id": diagnostic.json()["id"],
            "effort_minutes": 20,
        },
    )
    assert action.status_code == 201
    action_id = action.json()["id"]

    schedule = await client.post(
        "/api/v1/schedules",
        headers=H(client),
        json={
            "system_slug": "ambition",
            "title": "Run the real owner journey test",
            "scheduled_for": dt.datetime.now(dt.UTC).isoformat(),
            "duration_minutes": 20,
            "goal_id": goal.json()["id"],
            "objective_id": objective.json()["id"],
            "system_action_id": action_id,
        },
    )
    assert schedule.status_code == 201
    assert schedule.json()["glow"]["awarded_points"] == 5

    missed = await client.post(
        "/api/v1/today/miss-action",
        headers=H(client),
        json={"action_id": action_id},
    )
    assert missed.status_code == 200
    assert missed.json()["action"]["status"] == "MISSED"
    assert missed.json()["glow"]["awarded_points"] == 0

    returned = await client.post(
        "/api/v1/today/complete-action",
        headers=H(client),
        json={"action_id": action_id},
    )
    assert returned.status_code == 200
    assert returned.json()["action"]["status"] == "COMPLETED"
    assert returned.json()["glow"]["awarded_points"] == 6
    assert returned.json()["return_glow"]["awarded_points"] == 7
    assert returned.json()["today"]["completed_today"][0]["id"] == action_id

    checkin = await client.post(
        "/api/v1/today/check-in",
        headers=H(client),
        json={
            "energy": 8,
            "pain": 2,
            "sleep_quality": 7,
            "nourishment": 8,
            "movement": 6,
            "emotional_load": 3,
            "clarity": 8,
            "note": "Capacity is real and measured.",
        },
    )
    assert checkin.status_code == 200
    assert checkin.json()["glow"]["awarded_points"] == 2
    assert checkin.json()["today"]["body"]["score"] > 0
    assert checkin.json()["today"]["mind"]["score"] > 0
    assert checkin.json()["today"]["body"]["sources"]["today_checkin"] is not None

    same_day = await client.post(
        "/api/v1/today/check-in",
        headers=H(client),
        json={
            "energy": 7,
            "pain": 2,
            "sleep_quality": 7,
            "nourishment": 8,
            "movement": 7,
            "emotional_load": 3,
            "clarity": 8,
        },
    )
    assert same_day.status_code == 200
    assert same_day.json()["glow"]["idempotent_replay"] is True

    detail = (await client.get("/api/v1/systems/ambition")).json()
    assert detail["progress_percent"] > 0
    assert detail["progress_sources"]["completed_actions"] == 1
    assert detail["progress_sources"]["glow_points"] == 35
    assert detail["prediction"]["provenance_label"] == "DETERMINISTIC_INFERENCE"

    glow = (await client.get("/api/v1/glow/summary")).json()
    assert glow["lifetime_points"] == 37
    assert glow["today_points"] == 37
    assert glow["level"] == 1
    assert glow["rank"] == "Orbit Seed"
    assert glow["achievements"][0]["achievement_key"] == "first_glow"

    scoreboard = (await client.get("/api/v1/glow/scoreboard")).json()
    assert scoreboard["provenance_label"] == "PERSISTED_GLOW_TRANSACTIONS"
    assert scoreboard["rows"][0]["system_slug"] == "ambition"
    assert scoreboard["rows"][0]["score"] == 35
    body = next(row for row in scoreboard["rows"] if row["system_slug"] == "introspection")
    assert body["score"] == 2

    timeline = (await client.get("/api/v1/universe/timeline")).json()["items"]
    timeline_kinds = {row["kind"] for row in timeline}
    assert {
        "SYSTEM_DIAGNOSTIC_RECORDED",
        "GOAL_CREATED",
        "OBJECTIVE_CREATED",
        "SCHEDULE_CREATED",
        "SYSTEM_ACTION_MISSED",
        "SYSTEM_ACTION_COMPLETED",
        "TODAY_CHECKIN",
    } <= timeline_kinds


async def test_make_easier_preserves_lineage_and_only_rewards_completed_replacement(client):
    await register_user(client)
    original = await client.post(
        "/api/v1/systems/introspection/actions",
        headers=H(client),
        json={"title": "Exercise for one hour", "effort_minutes": 60},
    )
    easier = await client.post(
        "/api/v1/today/make-easier",
        headers=H(client),
        json={
            "action_id": original.json()["id"],
            "title": "Stretch for five minutes",
            "effort_minutes": 5,
        },
    )
    assert easier.status_code == 201
    body = easier.json()
    assert body["original"]["status"] == "CANCELLED"
    assert body["replacement"]["easier_from_id"] == original.json()["id"]
    assert body["glow"]["awarded_points"] == 0

    complete = await client.post(
        "/api/v1/today/complete-action",
        headers=H(client),
        json={"action_id": body["replacement"]["id"]},
    )
    assert complete.status_code == 200
    assert complete.json()["glow"]["awarded_points"] == 6


async def test_system_return_is_persisted_idempotent_and_owner_isolated(client):
    await register_user(client, chosen_name="Return Owner A")
    action = await client.post(
        "/api/v1/systems/introspection/actions",
        headers=H(client),
        json={"title": "Take a capacity-matched recovery walk"},
    )
    action_id = action.json()["id"]

    too_early = await client.post(
        f"/api/v1/systems/introspection/actions/{action_id}/return",
        headers=H(client),
        json={"observed_result": "Energy improved after the walk."},
    )
    assert too_early.status_code == 409

    completed = await client.patch(
        f"/api/v1/system-actions/{action_id}",
        headers=H(client),
        json={"status": "COMPLETED"},
    )
    assert completed.status_code == 200

    returned = await client.post(
        f"/api/v1/systems/introspection/actions/{action_id}/return",
        headers=H(client),
        json={
            "observed_result": "  Energy improved after the walk.  ",
            "structured_measurements": {"energy_before": 4, "energy_after": 6},
            "confidence": 0.7,
        },
    )
    assert returned.status_code == 201
    returned_body = returned.json()
    outcome_id = returned_body["outcome"]["id"]
    assert returned_body["outcome"]["observed_result"] == "Energy improved after the walk."
    assert returned_body["outcome"]["structured_measurements"] == {
        "energy_before": 4,
        "energy_after": 6,
        "system_slug": "introspection",
        "system_action_id": action_id,
    }
    assert returned_body["outcome"]["confidence"] == 0.7
    assert returned_body["glow"]["awarded_points"] == 15
    assert returned_body["idempotent_replay"] is False

    replay = await client.post(
        f"/api/v1/systems/introspection/actions/{action_id}/return",
        headers=H(client),
        json={"observed_result": "A replay cannot replace persisted evidence."},
    )
    assert replay.status_code == 201
    assert replay.json()["outcome"]["id"] == outcome_id
    assert replay.json()["outcome"]["observed_result"] == "Energy improved after the walk."
    assert replay.json()["glow"]["idempotent_replay"] is True
    assert replay.json()["idempotent_replay"] is True

    corrected = await client.patch(
        f"/api/v1/systems/introspection/actions/{action_id}/return",
        headers=H(client),
        json={
            "observed_result": "Energy improved by one point after the walk.",
            "reason": "The second reading was six, but the baseline was five.",
            "structured_measurements": {"energy_before": 5, "energy_after": 6},
            "confidence": 0.9,
        },
    )
    assert corrected.status_code == 200
    corrected_body = corrected.json()
    assert corrected_body["outcome"]["id"] == outcome_id
    assert corrected_body["outcome"]["confidence"] == 0.9
    assert corrected_body["outcome"]["structured_measurements"]["corrections"][0][
        "previous_observed_result"
    ] == "Energy improved after the walk."
    assert corrected_body["correction_count"] == 1
    assert corrected_body["glow"]["awarded_points"] == 0

    flow = (await client.get("/api/v1/timeline/flow")).json()
    projected = [row for row in flow["entries"] if row["source_id"] == outcome_id]
    assert len(projected) == 1
    assert projected[0]["title"] == "Energy improved by one point after the walk."
    assert projected[0]["source_type"] == "OUTCOME"
    assert projected[0]["status"] == "OBSERVED"
    assert projected[0]["system_slug"] == "introspection"
    assert projected[0]["lane"] == "past"

    alias_action = await client.post(
        "/api/v1/systems/introspection/actions",
        headers=H(client),
        json={"title": "A second action cannot borrow the first Return"},
    )
    denied_alias = await client.patch(
        f"/api/v1/system-actions/{alias_action.json()['id']}",
        headers=H(client),
        json={"outcome_id": outcome_id},
    )
    assert denied_alias.status_code == 409

    body = (await client.get("/api/v1/systems/introspection")).json()
    assert body["progress_sources"]["outcomes_returned"] == 1
    assert body["progress_sources"]["outcome_return_percent"] == 100
    assert body["progress_sources"]["formula_version"] == "v5-beta-2"

    graph = (await client.get("/api/v1/map")).json()
    outcome_node = next(row for row in graph["nodes"] if row["id"] == f"outcome:{outcome_id}")
    assert outcome_node["parent_id"] == "system:introspection"
    assert outcome_node["label"] == "Energy improved by one point after the walk."
    assert outcome_node["data"]["provenance_label"] == "OWNER_RETURNED_OUTCOME"
    assert any(
        edge["kind"] == "SYSTEM_TO_OUTCOME" and edge["target"] == outcome_node["id"]
        for edge in graph["edges"]
    )

    timeline = (await client.get("/api/v1/universe/timeline")).json()["items"]
    assert sum(row["kind"] == "OUTCOME_RETURNED" for row in timeline) == 1
    assert sum(row["kind"] == "OUTCOME_CORRECTED" for row in timeline) == 1

    client.cookies.clear()
    await register_user(client, chosen_name="Return Owner B")
    denied_return = await client.post(
        f"/api/v1/systems/introspection/actions/{action_id}/return",
        headers=H(client),
        json={"observed_result": "Foreign evidence must stay hidden."},
    )
    assert denied_return.status_code == 404

    owner_b_action = await client.post(
        "/api/v1/systems/introspection/actions",
        headers=H(client),
        json={"title": "Owner B action"},
    )
    denied_link = await client.patch(
        f"/api/v1/system-actions/{owner_b_action.json()['id']}",
        headers=H(client),
        json={"outcome_id": outcome_id},
    )
    assert denied_link.status_code == 404


async def test_all_six_systems_mutate_and_project_real_owner_evidence(client):
    await register_user(client, chosen_name="Six Systems Owner")
    initial = {
        row["slug"]: row for row in (await client.get("/api/v1/systems")).json()["systems"]
    }
    assert tuple(initial) == SYSTEM_SLUGS

    outcome_ids: dict[str, str] = {}
    plan_ids: dict[str, str] = {}
    for slug in SYSTEM_SLUGS:
        diagnostic = await client.post(
            f"/api/v1/systems/{slug}/diagnostics",
            headers=H(client),
            json={
                "answers": {"current_state": f"Measured state for {slug}."},
                "ratings": {"clarity": 7},
                "strengths": ["owner evidence"],
            },
        )
        assert diagnostic.status_code == 201

        goal = await client.post(
            "/api/v1/goals",
            headers=H(client),
            json={"system_slug": slug, "title": f"Move {slug} with evidence"},
        )
        assert goal.status_code == 201

        plan = await client.post(
            "/api/v1/plans",
            headers=H(client),
            json={
                "title": f"Plan for {slug}",
                "orbit_id": initial[slug]["orbit_id"],
                "steps": [{"title": f"Do the next {slug} step"}],
            },
        )
        assert plan.status_code == 201
        plan_ids[slug] = plan.json()["id"]

        action = await client.post(
            f"/api/v1/systems/{slug}/actions",
            headers=H(client),
            json={
                "title": f"Complete one {slug} action",
                "goal_id": goal.json()["id"],
                "diagnostic_id": diagnostic.json()["id"],
            },
        )
        assert action.status_code == 201

        schedule = await client.post(
            "/api/v1/schedules",
            headers=H(client),
            json={
                "system_slug": slug,
                "title": f"Scheduled {slug} action",
                "scheduled_for": dt.datetime.now(dt.UTC).isoformat(),
                "goal_id": goal.json()["id"],
                "system_action_id": action.json()["id"],
                "plan_step_id": plan.json()["steps"][0]["id"],
            },
        )
        assert schedule.status_code == 201

        complete = await client.patch(
            f"/api/v1/system-actions/{action.json()['id']}",
            headers=H(client),
            json={"status": "COMPLETED"},
        )
        assert complete.status_code == 200

        returned = await client.post(
            f"/api/v1/systems/{slug}/actions/{action.json()['id']}/return",
            headers=H(client),
            json={
                "observed_result": f"Observed a real {slug} result.",
                "structured_measurements": {"verified": True},
                "confidence": 0.6,
            },
        )
        assert returned.status_code == 201
        outcome_ids[slug] = returned.json()["outcome"]["id"]

        insight = await client.post(
            "/api/v1/insights/generate",
            headers=H(client),
            json={"system_slug": slug},
        )
        assert insight.status_code == 201
        assert insight.json()["affected_system_slug"] == slug

    creation_project = await client.post(
        "/api/v1/projects",
        headers=H(client),
        json={
            "title": "Ship the Creation System proof",
            "objective": "Link a real Project to the Creation System.",
            "system_slug": "creation",
        },
    )
    assert creation_project.status_code == 201

    oversized_action = await client.post(
        "/api/v1/systems/introspection/actions",
        headers=H(client),
        json={
            "title": "Attempt a long high-load session",
            "effort_minutes": 60,
        },
    )
    assert oversized_action.status_code == 201
    low_capacity = await client.post(
        "/api/v1/today/check-in",
        headers=H(client),
        json={
            "energy": 0,
            "pain": 10,
            "sleep_quality": 0,
            "nourishment": 0,
            "movement": 0,
            "emotional_load": 10,
            "clarity": 0,
            "note": "Low capacity is owner-reported, not diagnosed.",
        },
    )
    assert low_capacity.status_code == 200
    today = low_capacity.json()["today"]
    assert today["body"]["capacity_band"] == "LOW"
    assert today["body"]["action_limit_minutes"] == 10
    assert today["body"]["operating_boundary"]["scope"] == "SELF_REPORTED_CAPACITY_SUPPORT"
    assert len(today["active_plans"]) == 6
    assert all(
        plan["body_capacity"]["action_limit_minutes"] == 10
        and plan["body_capacity"]["not_medical_advice"] is True
        for plan in today["active_plans"]
    )
    body_plan = next(plan for plan in today["active_plans"] if plan["system_slug"] == "introspection")
    assert body_plan["body_capacity"]["open_actions_above_guidance"] == 1
    assert today["next_move"]["id"] == oversized_action.json()["id"]
    assert today["next_move"]["body_capacity"]["exceeds_current_guidance"] is True

    snapshots = {
        row["slug"]: row for row in (await client.get("/api/v1/systems")).json()["systems"]
    }
    for slug in SYSTEM_SLUGS:
        snapshot = snapshots[slug]
        assert snapshot["progress_percent"] > 0
        assert snapshot["progress_sources"]["completed_actions"] == 1
        assert snapshot["progress_sources"]["outcomes_returned"] == 1
        assert snapshot["progress_sources"]["outcome_return_percent"] == 100
        assert snapshot["active_goal_count"] == 1
        assert snapshot["prediction"]["provenance_label"] == "DETERMINISTIC_INFERENCE"
    assert snapshots["growth"]["operating_boundary"]["scope"] == "FINANCIAL_ORGANIZATION_ONLY"
    assert snapshots["creation"]["related_projects"] == [{
        "id": creation_project.json()["id"],
        "title": "Ship the Creation System proof",
        "status": "ACTIVE",
        "objective": "Link a real Project to the Creation System.",
        "updated_at": creation_project.json()["updated_at"],
    }]

    graph = (await client.get("/api/v1/map")).json()
    nodes = {row["id"]: row for row in graph["nodes"]}
    edges = graph["edges"]
    for slug in SYSTEM_SLUGS:
        system_node = nodes[f"system:{slug}"]
        assert system_node["data"]["orbit_id"] == initial[slug]["orbit_id"]
        assert system_node["data"]["outcomes_returned"] == 1
        assert nodes[f"plan:{plan_ids[slug]}"]["parent_id"] == f"system:{slug}"
        assert nodes[f"outcome:{outcome_ids[slug]}"]["parent_id"] == f"system:{slug}"
        assert any(
            edge["kind"] == "SYSTEM_TO_PLAN"
            and edge["source"] == f"system:{slug}"
            and edge["target"] == f"plan:{plan_ids[slug]}"
            for edge in edges
        )

    timeline = (await client.get("/api/v1/universe/timeline?limit=200")).json()["items"]
    assert sum(row["kind"] == "OUTCOME_RETURNED" for row in timeline) == 6


async def test_map_future_timeline_and_feasibility_are_derived_and_persisted(client):
    await register_user(client, chosen_name="Map Owner")
    await client.post(
        "/api/v1/today/check-in",
        headers=H(client),
        json={
            "energy": 8,
            "pain": 2,
            "sleep_quality": 8,
            "nourishment": 8,
            "movement": 7,
            "emotional_load": 3,
            "clarity": 8,
        },
    )
    goal = await client.post(
        "/api/v1/goals",
        headers=H(client),
        json={"system_slug": "introspection", "title": "Protect enough energy to keep moving"},
    )
    future = dt.datetime.now(dt.UTC) + dt.timedelta(days=3)
    schedule = await client.post(
        "/api/v1/schedules",
        headers=H(client),
        json={
            "system_slug": "introspection",
            "title": "Review the capacity trend",
            "scheduled_for": future.isoformat(),
            "goal_id": goal.json()["id"],
        },
    )
    assert schedule.status_code == 201

    assessment = await client.post(
        "/api/v1/feasibility",
        headers=H(client),
        json={
            "system_slug": "introspection",
            "subject_kind": "ACTION",
            "title": "Twenty minute recovery walk",
            "desired_outcome": "Support energy without exceeding capacity.",
            "capacity_required": 40,
            "time_required_minutes": 20,
            "time_available_minutes": 30,
            "money_required_cents": 0,
            "money_available_cents": 0,
            "risk_level": "LOW",
        },
    )
    assert assessment.status_code == 201
    assert assessment.json()["result"] == "FEASIBLE"
    assert assessment.json()["current_capacity"] >= 40
    assert assessment.json()["glow"]["awarded_points"] == 5
    assert assessment.json()["source_refs"] == ["today.body"]

    prediction = await client.post(
        "/api/v1/map/predict-path",
        headers=H(client),
        json={
            "system_slug": "introspection",
            "path_type": "easier",
            "goal_id": goal.json()["id"],
            "horizon_days": 14,
        },
    )
    assert prediction.status_code == 201
    assert prediction.json()["status"] == "OPEN"
    assert prediction.json()["expected_observation"]["path_type"] == "easier"
    assert prediction.json()["provenance_label"] == "DETERMINISTIC_HYPOTHESIS"

    graph = (await client.get("/api/v1/map")).json()
    assert graph["provenance_label"] == "OWNER_LEDGER_DERIVED_GRAPH"
    node_ids = {row["id"] for row in graph["nodes"]}
    assert "nur" in node_ids
    assert {f"system:{slug}" for slug in SYSTEM_SLUGS} <= node_ids
    assert f"goal:{goal.json()['id']}" in node_ids
    assert f"prediction:{prediction.json()['id']}" in node_ids
    assert any(edge["kind"] == "SYSTEM_TO_GOAL" for edge in graph["edges"])

    rebuilt = await client.post("/api/v1/map/rebuild", headers=H(client))
    assert rebuilt.status_code == 200
    assert rebuilt.json()["rebuild"]["status"] == "REBUILT_FROM_OWNER_LEDGER"

    timeline = (await client.get("/api/v1/universe/timeline")).json()["items"]
    future_item = next(row for row in timeline if row["id"] == schedule.json()["id"])
    assert future_item["lane"] == "future"
    assert future_item["kind"] == "SCHEDULE_DUE"
    assert any(row["kind"] == "PREDICTION_MADE" for row in timeline)
    assert any(row["kind"] == "FEASIBILITY_CREATED" for row in timeline)

    insights = (await client.get("/api/v1/universe/insights-summary")).json()
    assert insights["counts"]["feasibility_assessments"] == 1
    assert insights["feasibility"][0]["result"] == "FEASIBLE"


async def test_living_tables_force_rls_and_hide_every_foreign_owner_row(
    client, app_engine
):
    owner_a, _, _ = await register_user(client, chosen_name="Owner A")
    goal = await client.post(
        "/api/v1/goals",
        headers=H(client),
        json={"system_slug": "growth", "title": "Owner A private goal"},
    )
    action = await client.post(
        "/api/v1/systems/growth/actions",
        headers=H(client),
        json={"title": "Owner A private action", "goal_id": goal.json()["id"]},
    )
    await client.post(
        "/api/v1/systems/growth/diagnostics",
        headers=H(client),
        json={"ratings": {"clarity": 5}},
    )
    await client.post(
        "/api/v1/schedules",
        headers=H(client),
        json={
            "system_slug": "growth",
            "title": "Owner A private schedule",
            "scheduled_for": dt.datetime.now(dt.UTC).isoformat(),
            "goal_id": goal.json()["id"],
            "system_action_id": action.json()["id"],
        },
    )
    await client.post(
        "/api/v1/today/check-in",
        headers=H(client),
        json={
            "energy": 5,
            "pain": 5,
            "sleep_quality": 5,
            "nourishment": 5,
            "movement": 5,
            "emotional_load": 5,
            "clarity": 5,
        },
    )

    client.cookies.clear()
    owner_b, _, _ = await register_user(client, chosen_name="Owner B")
    assert (await client.get("/api/v1/goals")).json() == []
    denied = await client.patch(
        f"/api/v1/system-actions/{action.json()['id']}",
        headers=H(client),
        json={"status": "COMPLETED"},
    )
    assert denied.status_code == 404

    tables = [
        "goals",
        "objectives",
        "system_diagnostics",
        "system_actions",
        "scheduled_actions",
        "today_checkins",
        "glow_achievements",
        "feasibility_assessments",
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
