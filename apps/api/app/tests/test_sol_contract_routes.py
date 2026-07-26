import uuid

from app.tests.conftest import register_user


def H(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("nur_csrf")}


async def test_map_timeline_and_feasibility_contract_routes_are_persisted(client):
    await register_user(client, chosen_name="Contract Owner")

    goal = await client.post(
        "/api/v1/goals",
        headers=H(client),
        json={
            "system_slug": "ambition",
            "title": "Ship one source-bound route",
            "why": "The Map must follow real owner evidence.",
        },
    )
    assert goal.status_code == 201, goal.text

    plan = await client.post(
        "/api/v1/plans",
        headers=H(client),
        json={
            "title": "Contract plan",
            "steps": [{"title": "Return the browser proof"}],
        },
    )
    assert plan.status_code == 201, plan.text

    system_focus = await client.post(
        "/api/v1/map/from-system",
        headers=H(client),
        json={"system_slug": "ambition"},
    )
    assert system_focus.status_code == 201, system_focus.text
    assert system_focus.json()["node"]["id"] == "system:ambition"
    assert system_focus.json()["appears_on_map"] is True
    goal_focus = await client.post(
        "/api/v1/map/from-goal",
        headers=H(client),
        json={"source_id": goal.json()["id"]},
    )
    assert goal_focus.status_code == 201, goal_focus.text
    assert goal_focus.json()["node"]["id"] == f"goal:{goal.json()['id']}"
    plan_focus = await client.post(
        "/api/v1/map/from-plan",
        headers=H(client),
        json={"source_id": plan.json()["id"]},
    )
    assert plan_focus.status_code == 201, plan_focus.text
    assert plan_focus.json()["node"]["id"] == f"plan:{plan.json()['id']}"

    first_event = await client.post(
        "/api/v1/timeline/events",
        headers=H(client),
        json={
            "event_type": "OWNER_NEXT_MOVE",
            "title": "Large release pass",
            "description": "The original move is too large.",
            "time_kind": "FUTURE",
            "source_type": "OWNER",
            "importance": 80,
        },
    )
    assert first_event.status_code == 201, first_event.text
    easier = await client.post(
        f"/api/v1/timeline/{first_event.json()['id']}/make-easier",
        headers=H(client),
        json={"title": "One smaller release pass", "effort_minutes": 15},
    )
    assert easier.status_code == 201, easier.text
    assert easier.json()["event_payload"]["made_easier_from"] == first_event.json()["id"]
    assert easier.json()["importance"] == 70

    plan_from_timeline = await client.post(
        f"/api/v1/timeline/{easier.json()['id']}/turn-into-plan",
        headers=H(client),
        json={"title": "Smaller release plan"},
    )
    assert plan_from_timeline.status_code == 201, plan_from_timeline.text
    assert plan_from_timeline.json()["route"] == "/plan"

    outcome_event = await client.post(
        "/api/v1/timeline/events",
        headers=H(client),
        json={
            "event_type": "PROOF_DUE",
            "title": "Return contract proof",
            "time_kind": "FUTURE",
            "source_type": "OWNER",
        },
    )
    outcome = await client.post(
        f"/api/v1/timeline/{outcome_event.json()['id']}/outcome",
        headers=H(client),
        json={"observed_result": "The contract proof passed."},
    )
    assert outcome.status_code == 200, outcome.text
    assert outcome.json()["timeline_event"]["status"] == "COMPLETED"

    target_id = uuid.uuid4()
    feasibility = await client.post(
        "/api/v1/feasibility/assess",
        headers=H(client),
        json={
            "system_slug": "ambition",
            "subject_kind": "ACTION",
            "subject_id": str(target_id),
            "title": "Bounded proof pass",
            "desired_outcome": "Return one verified result.",
            "capacity_required": 0,
            "time_required_minutes": 10,
            "time_available_minutes": 20,
            "money_required_cents": 0,
            "money_available_cents": 0,
            "risk_level": "LOW",
        },
    )
    assert feasibility.status_code == 201, feasibility.text
    assessment_id = feasibility.json()["id"]
    filtered = await client.get(
        f"/api/v1/feasibility?target_type=ACTION&target_id={target_id}"
    )
    assert filtered.status_code == 200
    assert [row["id"] for row in filtered.json()] == [assessment_id]

    feasibility_plan = await client.post(
        f"/api/v1/feasibility/{assessment_id}/convert-to-plan",
        headers=H(client),
        json={},
    )
    assert feasibility_plan.status_code == 201, feasibility_plan.text
    assert feasibility_plan.json()["plan_id"]
    feasibility_timeline = await client.post(
        f"/api/v1/feasibility/{assessment_id}/add-to-timeline",
        headers=H(client),
        json={},
    )
    assert feasibility_timeline.status_code == 201, feasibility_timeline.text
    assert feasibility_timeline.json()["timeline_event_id"]

    insight = await client.post("/api/v1/insights/generate", headers=H(client), json={})
    assert insight.status_code == 201, insight.text
    insight_focus = await client.post(
        "/api/v1/map/from-insight",
        headers=H(client),
        json={"source_id": insight.json()["id"]},
    )
    assert insight_focus.status_code == 201, insight_focus.text
    assert insight_focus.json()["node"]["id"] == f"dedicated-insight:{insight.json()['id']}"

    timeline = await client.get("/api/v1/universe/timeline")
    kinds = [row["kind"] for row in timeline.json()["items"]]
    assert "MAP_FOCUS_CREATED" in kinds
    assert "FEASIBILITY_CONVERTED_TO_PLAN" in kinds
    assert "FEASIBILITY_ADDED_TO_TIMELINE" in kinds
