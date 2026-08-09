from sqlalchemy import text

from app.tests.conftest import register_user


def H(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("nur_csrf")}


async def test_social_orbit_timeline_insight_and_live_universe_owner_flow(client):
    await register_user(client, chosen_name="Live Intelligence Owner")

    person_orbit = await client.post(
        "/api/v1/orbits/from-conversation",
        headers=H(client),
        json={
            "display_name": "Selene",
            "relationship_type": "collaborator",
            "conversation_summary": "We agreed to review the release evidence together.",
            "unresolved_count": 1,
            "shared_goal_count": 1,
        },
    )
    assert person_orbit.status_code == 201, person_orbit.text
    person = person_orbit.json()["person"]
    orbit = person_orbit.json()["orbit"]
    assert orbit["kind"] == "PERSON"

    summary = await client.post(f"/api/v1/orbits/{orbit['id']}/summary")
    assert summary.status_code == 200, summary.text
    assert summary.json()["unresolved_count"] == 1
    assert summary.json()["shared_goal_count"] == 1
    assert "oldest unresolved thread" in summary.json()["next_action"]

    council = await client.post(
        f"/api/v1/orbits/{orbit['id']}/start-council",
        headers=H(client),
        json={
            "title": "Release council",
            "purpose": "Decide whether the evidence is sufficient to release.",
            "person_ids": [person["id"]],
        },
    )
    assert council.status_code == 200, council.text
    assert council.json()["council"]["kind"] == "COUNCIL"
    assert "no personal Talk" in council.json()["privacy"]

    timeline = await client.post(
        "/api/v1/timeline/events",
        headers=H(client),
        json={
            "event_type": "PROJECT_MILESTONE",
            "title": "Return the release evidence",
            "description": "Attach a verified test result.",
            "time_kind": "FUTURE",
            "source_type": "OWNER",
            "orbit_id": orbit["id"],
            "importance": 90,
        },
    )
    assert timeline.status_code == 201, timeline.text
    attached = await client.post(
        f"/api/v1/timeline/{timeline.json()['id']}/attach-outcome",
        headers=H(client),
        json={"observed_result": "The acceptance test passed and evidence was attached."},
    )
    assert attached.status_code == 200, attached.text
    assert attached.json()["timeline_event"]["status"] == "COMPLETED"

    insight = await client.post(
        "/api/v1/insights/generate",
        headers=H(client),
        json={},
    )
    assert insight.status_code == 201, insight.text
    candidate = insight.json()
    assert candidate["status"] == "CANDIDATE"
    assert candidate["evidence"]
    assert candidate["what_nur_may_be_wrong_about"]
    accepted = await client.post(
        f"/api/v1/insights/{candidate['id']}/accept",
        headers=H(client),
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "ACCEPTED"
    memory = await client.post(
        f"/api/v1/insights/{candidate['id']}/save-to-memory",
        headers=H(client),
    )
    assert memory.status_code == 200, memory.text
    assert memory.json()["status"] == "CANDIDATE"
    plan = await client.post(
        f"/api/v1/insights/{candidate['id']}/convert-to-plan",
        headers=H(client),
        json={},
    )
    assert plan.status_code == 200, plan.text
    assert plan.json()["route"] == "/plan"
    timeline_link = await client.post(
        f"/api/v1/insights/{candidate['id']}/add-to-timeline",
        headers=H(client),
    )
    assert timeline_link.status_code == 200, timeline_link.text

    live = (await client.get("/api/v1/universe/live")).json()
    assert any(row["id"] == orbit["id"] for row in live["people_orbits"])
    assert any(row["kind"] == "COUNCIL" for row in live["group_orbits"])
    assert any(row["id"] == candidate["id"] for row in live["latest_insights"])
    assert any(row["kind"] == "INSIGHT_REVIEW_DUE" for row in live["timeline_highlights"])
    assert live["state"]["confidence_kind"] == "source_coverage_not_truth_probability"

    graph = (await client.get("/api/v1/map")).json()
    node_ids = {row["id"] for row in graph["nodes"]}
    assert f"person:{person['id']}" in node_ids
    assert f"orbit:{orbit['id']}" in node_ids
    assert f"dedicated-insight:{candidate['id']}" in node_ids
    assert f"timeline:{timeline_link.json()['timeline_event_id']}" in node_ids
    assert any(edge["kind"] == "ORBIT_MEMBER" for edge in graph["edges"])
    assert graph["counts"]["people"] == 1
    assert graph["counts"]["social_orbits"] == 2
    assert all("layout" in row["data"] for row in graph["nodes"])
    master_layout = next(row["data"]["layout"] for row in graph["nodes"] if row["id"] == "nur")
    assert master_layout["exclusion_radius"] == 210

    insight_summary = (await client.get("/api/v1/universe/insights-summary")).json()
    assert any(row["id"] == candidate["id"] for row in insight_summary["claims"])
    assert any(
        row["id"] == candidate["id"] and row["record_kind"] == "DEDICATED_INSIGHT"
        for row in insight_summary["dedicated_insights"]
    )
    assert all(row["record_kind"] == "OMEGA_CLAIM" for row in insight_summary["omega_claims"])
    assert insight_summary["counts"]["dedicated_insights"] == 1
    assert insight_summary["counts"]["claims"] == (
        insight_summary["counts"]["dedicated_insights"]
        + insight_summary["counts"]["omega_claims"]
    )
    timeline_summary = (await client.get("/api/v1/universe/timeline")).json()
    assert any(row["kind"] == "INSIGHT_REVIEW_DUE" for row in timeline_summary["items"])


async def test_live_intelligence_tables_force_rls_and_second_owner_is_isolated(
    client, app_engine
):
    owner_a, _, _ = await register_user(client, chosen_name="Owner A")
    social = await client.post(
        "/api/v1/orbits/from-conversation",
        headers=H(client),
        json={
            "display_name": "Private person",
            "conversation_summary": "Owner A only.",
        },
    )
    event = await client.post(
        "/api/v1/timeline/events",
        headers=H(client),
        json={
            "event_type": "PRIVATE_EVENT",
            "title": "Owner A event",
            "source_type": "OWNER",
        },
    )
    await client.post(
        f"/api/v1/timeline/{event.json()['id']}/attach-outcome",
        headers=H(client),
        json={"observed_result": "Owner A returned private evidence."},
    )
    insight = await client.post("/api/v1/insights/generate", headers=H(client), json={})
    assert insight.status_code == 201, insight.text

    client.cookies.clear()
    owner_b, _, _ = await register_user(client, chosen_name="Owner B")
    assert (await client.get("/api/v1/orbits/people")).json() == []
    assert (await client.get("/api/v1/timeline")).json() == []
    assert (await client.get("/api/v1/insights")).json() == []
    assert (await client.get(f"/api/v1/orbits/{social.json()['orbit']['id']}")).status_code == 404
    assert (await client.get(f"/api/v1/insights/{insight.json()['id']}")).status_code == 404

    tables = ["people", "orbit_members", "orbit_events", "timeline_events", "insights"]
    async with app_engine.connect() as connection:
        await connection.execute(
            text("SELECT set_config('app.current_user_id', :uid, false)"),
            {"uid": owner_b.json()["id"]},
        )
        flags = (await connection.execute(text("""
            SELECT relname, relrowsecurity, relforcerowsecurity
            FROM pg_class
            WHERE relname = ANY(:tables)
            ORDER BY relname
        """), {"tables": tables})).all()
        assert len(flags) == len(tables)
        assert all(row.relrowsecurity and row.relforcerowsecurity for row in flags)
        for table in tables:
            count = (await connection.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
            assert count == 0, f"Owner B could see rows in {table}"

    assert owner_a.json()["id"] != owner_b.json()["id"]
