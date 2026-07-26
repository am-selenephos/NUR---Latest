from sqlalchemy import text

from app.tests.conftest import register_user


def H(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("nur_csrf")}


async def test_registration_provisions_the_six_persisted_nur_systems(client):
    await register_user(client, chosen_name="Seven Systems Owner")
    rows = (await client.get("/api/v1/orbits")).json()
    systems = [row for row in rows if row["kind"] != "PERSONAL_BRIDGE"]

    assert [row["title"] for row in systems] == [
        "Ambition",
        "Rebuild",
        "Creation",
        "Growth",
        "Introspection",
        "Connection",
    ]
    assert all(row["status"] == "ACTIVE" for row in systems)


async def test_glow_reward_is_persisted_idempotent_and_owner_scoped(client, super_engine):
    owner, _, _ = await register_user(client, chosen_name="Glow Owner")
    owner_id = owner.json()["id"]
    orbit_id = (await client.get("/api/v1/orbits")).json()[0]["id"]
    journal = await client.post(
        "/api/v1/journal",
        headers=H(client),
        json={"body": "A real Track A journal trace.", "orbit_id": orbit_id},
    )
    assert journal.status_code == 201

    payload = {
        "event_type": "journal_saved",
        "source_kind": "JOURNAL_ENTRY",
        "source_id": journal.json()["id"],
        "orbit_id": orbit_id,
        "idempotency_key": f"journal:{journal.json()['id']}:saved",
    }
    auto_summary = await client.get("/api/v1/glow/summary")
    assert auto_summary.status_code == 200
    assert auto_summary.json()["balance"] == 4
    assert auto_summary.json()["lifetime_points"] == 4

    first = await client.post("/api/v1/glow/rewards", headers=H(client), json=payload)
    assert first.status_code == 201
    assert first.json()["awarded_points"] == 4
    assert first.json()["balance"] == 4
    assert first.json()["idempotent_replay"] is True

    replay = await client.post("/api/v1/glow/rewards", headers=H(client), json=payload)
    assert replay.status_code == 201
    assert replay.json()["awarded_points"] == 4
    assert replay.json()["balance"] == 4
    assert replay.json()["idempotent_replay"] is True

    summary = await client.get("/api/v1/glow/summary")
    assert summary.status_code == 200
    assert summary.json()["balance"] == 4
    assert summary.json()["lifetime_points"] == 4
    assert len(summary.json()["recent_transactions"]) == 1

    async with super_engine.connect() as conn:
        persisted = (await conn.execute(text(
            "SELECT count(*) FROM glow_transactions WHERE owner_user_id=:uid"
        ), {"uid": owner_id})).scalar_one()
    assert persisted == 1

    client.cookies.clear()
    await register_user(client, chosen_name="Other Owner")
    denied = await client.post("/api/v1/glow/rewards", headers=H(client), json={
        **payload,
        "idempotency_key": "other-owner-cannot-claim-source",
    })
    assert denied.status_code == 404
    other_summary = await client.get("/api/v1/glow/summary")
    assert other_summary.json()["balance"] == 0


async def test_plan_step_glow_requires_a_completed_owned_step(client):
    await register_user(client)
    orbit_id = (await client.get("/api/v1/orbits")).json()[0]["id"]
    plan = await client.post(
        "/api/v1/plans",
        headers=H(client),
        json={
            "title": "Track A movement",
            "orbit_id": orbit_id,
            "steps": [{"title": "Return one tested move"}],
        },
    )
    assert plan.status_code == 201
    step_id = plan.json()["steps"][0]["id"]
    reward_payload = {
        "event_type": "plan_step_completed",
        "source_kind": "PLAN_STEP",
        "source_id": step_id,
        "orbit_id": orbit_id,
        "idempotency_key": f"plan-step:{step_id}:completed",
    }

    premature = await client.post("/api/v1/glow/rewards", headers=H(client), json=reward_payload)
    assert premature.status_code == 409

    completed = await client.patch(
        f"/api/v1/plan-steps/{step_id}",
        headers=H(client),
        json={"done": True},
    )
    assert completed.status_code == 200
    awarded = await client.post("/api/v1/glow/rewards", headers=H(client), json=reward_payload)
    assert awarded.status_code == 201
    assert awarded.json()["awarded_points"] == 8
    assert awarded.json()["streak"]["current_count"] == 1


async def test_translation_foundation_persists_an_honest_disabled_state(client, super_engine):
    first, _, _ = await register_user(client, chosen_name="Translator")
    owner_id = first.json()["id"]
    translated = await client.post(
        "/api/v1/translations",
        headers=H(client),
        json={
            "source_text": "I need one clear next move.",
            "source_locale": "en",
            "target_locale": "ko",
            "content_type": "TALK_MESSAGE",
        },
    )
    assert translated.status_code == 200
    body = translated.json()
    assert body["target_locale"] == "ko"
    assert body["provider"] == "disabled"
    assert body["status"] == "NOT_CONNECTED"
    assert body["translated_text"] is None
    assert "not connected" in body["reason"].lower()

    listing = await client.get("/api/v1/translations")
    assert listing.status_code == 200
    assert [row["id"] for row in listing.json()] == [body["id"]]

    async with super_engine.connect() as conn:
        persisted_owner = (await conn.execute(text(
            "SELECT owner_user_id FROM translations WHERE id=:id"
        ), {"id": body["id"]})).scalar_one()
    assert str(persisted_owner) == owner_id

    client.cookies.clear()
    await register_user(client, chosen_name="Other Translator")
    assert (await client.get("/api/v1/translations")).json() == []


async def test_translation_source_equal_target_is_local_and_deterministic(client):
    await register_user(client)
    response = await client.post(
        "/api/v1/translations",
        headers=H(client),
        json={
            "source_text": "NUR stays NUR.",
            "source_locale": "en",
            "target_locale": "en",
            "content_type": "UI_NOTE",
        },
    )
    assert response.status_code == 200
    assert response.json()["translated_text"] == "NUR stays NUR."
    assert response.json()["provider"] == "local"
    assert response.json()["status"] == "COMPLETE"
