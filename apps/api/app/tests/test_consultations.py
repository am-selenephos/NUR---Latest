import pytest
from sqlalchemy import text

from app.tests.conftest import register_user


def H(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("nur_csrf")}


def save_cookies(client) -> dict[str, str]:
    return dict(client.cookies)


def use_cookies(client, cookies: dict[str, str]) -> None:
    client.cookies.clear()
    for name, value in cookies.items():
        client.cookies.set(name, value)


async def test_consultation_full_return_glow_and_room_boundary(client, app_engine):
    owner_response, _, _ = await register_user(client, chosen_name="Consultation Owner")
    owner_id = owner_response.json()["id"]
    owner_orbit = owner_response.json()["orbit"]["id"]
    owner_cookies = save_cookies(client)
    secret = await client.post(
        "/api/v1/journal", headers=H(client),
        json={"body": "Private owner context must never enter Consultation."},
    )
    assert secret.status_code == 201
    room = await client.post(
        "/api/v1/community/rooms", headers=H(client),
        json={"title": "Decision room", "room_kind": "GROUP"},
    )
    assert room.status_code == 201, room.text
    room_id = room.json()["id"]

    client.cookies.clear()
    member_response, member_email, _ = await register_user(client, chosen_name="Consultation Member")
    member_id = member_response.json()["id"]
    member_cookies = save_cookies(client)

    client.cookies.clear()
    outsider_response, _, _ = await register_user(client, chosen_name="Consultation Outsider")
    outsider_id = outsider_response.json()["id"]
    outsider_cookies = save_cookies(client)

    use_cookies(client, owner_cookies)
    added = await client.post(
        f"/api/v1/community/rooms/{room_id}/members", headers=H(client),
        json={"email": member_email, "role": "MEMBER"},
    )
    assert added.status_code == 201, added.text
    created = await client.post(
        "/api/v1/consultations", headers=H(client),
        json={
            "title": "Release consultation",
            "question": "What evidence is enough to release?",
            "purpose": "Make one bounded release decision.",
            "desired_outcome": "A decision with a return check.",
            "scope_statement": "Only room contributions and explicit stage records.",
            "room_id": room_id,
            "orbit_id": owner_orbit,
            "system_slug": "ambition",
        },
    )
    assert created.status_code == 201, created.text
    consultation_id = created.json()["id"]
    assert created.json()["current_stage"] == "ORIENT"
    assert created.json()["privacy"] == "BOUNDED_CONSULTATION_ONLY"

    use_cookies(client, member_cookies)
    visible = await client.get(f"/api/v1/consultations/{consultation_id}")
    assert visible.status_code == 200, visible.text
    assert visible.json()["consultation"]["current_user_role"] == "MEMBER"
    assert "Private owner context" not in visible.text
    contribution = await client.post(
        f"/api/v1/consultations/{consultation_id}/contributions", headers=H(client),
        json={
            "contribution_type": "COUNTEREXAMPLE",
            "body": "One browser proof is not enough when the privacy test is red.",
            "evidence": ["owned WebKit run"],
        },
    )
    assert contribution.status_code == 201, contribution.text
    denied_advance = await client.post(
        f"/api/v1/consultations/{consultation_id}/stages/ORIENT", headers=H(client),
        json={"payload": {"actual_question": "member cannot decide"}},
    )
    assert denied_advance.status_code == 403
    member_journal = await client.get("/api/v1/journal")
    assert all("Private owner context" not in row["body"] for row in member_journal.json())

    use_cookies(client, outsider_cookies)
    assert (await client.get("/api/v1/consultations")).json() == []
    assert (await client.get(f"/api/v1/consultations/{consultation_id}")).status_code == 404

    use_cookies(client, owner_cookies)
    payloads = {
        "ORIENT": {"actual_question": "What evidence is enough?", "affected_people": ["owner", "member"]},
        "GATHER": {"facts": ["WebKit passed"], "constraints": ["privacy test must pass"]},
        "MAP": {"options": ["release", "hold"], "minority_positions": ["one more privacy pass"]},
        "MOVE": {"selected_action": "Run the privacy suite", "success_signal": "all tests pass"},
        "RETURN": {"outcome": "Privacy and WebKit suites passed", "prediction_comparison": "matched"},
    }
    for stage, payload in payloads.items():
        response = await client.post(
            f"/api/v1/consultations/{consultation_id}/stages/{stage}",
            headers=H(client), json={"payload": payload},
        )
        assert response.status_code == 201, f"{stage}: {response.text}"
    returned = response.json()
    assert returned["stage"] == "RETURN"
    assert returned["glow"]["status"] == "AWARDED"
    assert returned["glow"]["awarded_points"] == 18
    detail = await client.get(f"/api/v1/consultations/{consultation_id}")
    assert detail.json()["consultation"]["status"] == "COMPLETED"
    assert detail.json()["next_stage"] is None
    assert [row["stage"] for row in detail.json()["completed_stages"]] == [
        "ORIENT", "GATHER", "MAP", "MOVE", "RETURN",
    ]
    timeline = await client.get("/api/v1/timeline")
    assert any(row["event_type"] == "CONSULTATION_RETURN_COMPLETED" for row in timeline.json())

    tables = ["consultations", "consultation_contributions", "consultation_stage_records"]
    async with app_engine.connect() as connection:
        await connection.execute(
            text("SELECT set_config('app.current_user_id', :uid, false)"),
            {"uid": outsider_id},
        )
        flags = (await connection.execute(text("""
            SELECT relname, relrowsecurity, relforcerowsecurity
            FROM pg_class WHERE relname = ANY(:tables) ORDER BY relname
        """), {"tables": tables})).all()
        assert len(flags) == 3
        assert all(row.relrowsecurity and row.relforcerowsecurity for row in flags)
        for table in tables:
            assert (await connection.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one() == 0

    async with app_engine.connect() as connection:
        await connection.execute(
            text("SELECT set_config('app.current_user_id', :uid, false)"),
            {"uid": member_id},
        )
        with pytest.raises(Exception):
            await connection.execute(text("""
                INSERT INTO consultation_stage_records(
                    consultation_id, consultation_owner_user_id, owner_user_id, stage, stage_payload
                ) VALUES (:consultation_id, :owner_id, :member_id, 'ORIENT', '{}'::jsonb)
            """), {"consultation_id": consultation_id, "owner_id": owner_id, "member_id": member_id})
