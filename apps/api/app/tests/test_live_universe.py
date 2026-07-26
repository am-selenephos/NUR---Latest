from httpx import ASGITransport, AsyncClient

from app.tests.conftest import register_user


SYSTEM_TITLES = [
    "Ambition",
    "Rebuild",
    "Creation",
    "Growth",
    "Introspection",
    "Connection",
]


def H(client: AsyncClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("nur_csrf")}


async def test_live_universe_aggregates_only_persisted_owner_ledger(client):
    await register_user(client, chosen_name="Live Owner")
    orbit_id = (await client.get("/api/v1/orbits")).json()[1]["id"]

    goal = (await client.post(
        "/api/v1/goals",
        headers=H(client),
        json={"system_slug": "creation", "title": "Ship the living universe"},
    )).json()
    objective = (await client.post(
        f"/api/v1/goals/{goal['id']}/objectives",
        headers=H(client),
        json={"title": "Prove the owner ledger"},
    )).json()
    plan = (await client.post(
        "/api/v1/plans",
        headers=H(client),
        json={
            "title": "Live Universe acceptance",
            "orbit_id": orbit_id,
            "steps": [{"title": "Read the aggregate", "position": 0}],
        },
    )).json()
    project = (await client.post(
        "/api/v1/projects",
        headers=H(client),
        json={
            "title": "NUR Live Universe",
            "objective": "Turn persisted owner evidence into one current view.",
            "system_slug": "creation",
        },
    )).json()
    brief = (await client.post(
        "/api/v1/research/briefs",
        headers=H(client),
        json={"question": "Which evidence changes this implementation?", "orbit_id": orbit_id},
    )).json()
    community = (await client.post(
        "/api/v1/community/consultation-notes",
        headers=H(client),
        json={"title": "Founder review", "note": "Keep V197 exact.", "orbit_id": orbit_id},
    )).json()
    web_signal = (await client.post(
        "/api/v1/web-signals/questions",
        headers=H(client),
        json={"question": "What should be researched next?", "orbit_id": orbit_id},
    )).json()

    response = await client.get("/api/v1/universe/live")
    assert response.status_code == 200, response.text
    live = response.json()

    assert live["provenance_label"] == "OWNER_LEDGER_AGGREGATE"
    assert live["owner"]["chosen_name"] == "Live Owner"
    assert [row["title"] for row in live["active_systems"]] == SYSTEM_TITLES
    assert {row["id"] for row in live["active_goals"]} >= {goal["id"]}
    assert {row["id"] for row in live["active_objectives"]} >= {objective["id"]}
    assert {row["id"] for row in live["active_plans"]} >= {plan["id"]}
    assert {row["id"] for row in live["projects"]} >= {project["id"]}
    assert any(row["id"] == brief["id"] and row["kind"] == "RESEARCH_BRIEF" for row in live["signals"])
    assert any(row["id"] == web_signal["id"] and row["kind"] == "WEB_SIGNAL_QUESTION" for row in live["signals"])
    assert live["community"]["live_connected"] is False
    assert live["community"]["latest_note"]["id"] == community["id"]
    assert live["state"]["confidence_kind"] == "source_coverage_not_truth_probability"
    assert live["state"]["source_count"] > 0
    assert live["people_orbits"] == []
    assert live["group_orbits"] == []
    assert live["timeline_highlights"]
    assert live["what_changed"]

    async with AsyncClient(
        transport=ASGITransport(app=client.app), base_url="http://test"
    ) as other:
        await register_user(other, chosen_name="Other Owner")
        isolated = (await other.get("/api/v1/universe/live")).json()
        serialized = str(isolated)
        for private_value in (
            goal["title"],
            objective["title"],
            plan["title"],
            project["title"],
            brief["question"],
            community["title"],
            web_signal["question"],
        ):
            assert private_value not in serialized
