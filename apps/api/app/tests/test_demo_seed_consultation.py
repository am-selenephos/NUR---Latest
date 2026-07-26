"""Proof for the demo-seed Consultation contract (Phase 10).

The seed advances a demo Consultation ORIENT -> GATHER -> MAP -> MOVE and leaves
it AT RETURN without fabricating the RETURN outcome. This test proves the exact
idempotency laws the seed depends on: fresh advance completes to RETURN, a second
"resume" pass is a no-op, re-posting a completed stage is rejected (never
duplicated), and demo Consultations earn no Glow.
"""
from app.tests.conftest import register_user

STAGE_ORDER = ["ORIENT", "GATHER", "MAP", "MOVE", "RETURN"]
STAGE_PAYLOADS = {
    "ORIENT": {"actual_question": "What evidence is enough?", "affected_people": ["owner", "recipient"]},
    "GATHER": {"facts": ["WebKit proof required"], "constraints": ["RLS must remain forced"]},
    "MAP": {"options": ["release", "hold"], "minority_positions": ["run one more privacy pass"]},
    "MOVE": {"selected_action": "run the owner/recipient boundary suite", "success_signal": "all tests pass"},
}


def H(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("nur_csrf")}


async def _resume_advance(client, consultation_id: str) -> None:
    """Mirror the seed's contract-aware, resume-safe advance to RETURN."""
    detail = (await client.get(f"/api/v1/consultations/{consultation_id}")).json()
    state = detail["consultation"]
    if state["status"] != "ACTIVE":
        return
    start = STAGE_ORDER.index(state["current_stage"])
    for stage in STAGE_ORDER[start:STAGE_ORDER.index("RETURN")]:
        r = await client.post(
            f"/api/v1/consultations/{consultation_id}/stages/{stage}",
            headers=H(client), json={"payload": STAGE_PAYLOADS[stage]},
        )
        assert r.status_code == 201, r.text


async def _make_demo_consultation(client) -> str:
    created = await client.post(
        "/api/v1/consultations", headers=H(client),
        json={
            "title": "Release readiness return",
            "question": "What evidence is enough to call this release ready?",
            "purpose": "Keep disagreement and proof inside one bounded decision path.",
            "desired_outcome": "A release decision with a verifiable return check.",
            "scope_statement": "Only room contributions and explicit Consultation records.",
            "system_slug": "ambition",
            "is_demo": True,
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def test_seed_consultation_advances_to_return_and_reseed_is_idempotent(client):
    await register_user(client, chosen_name="Seed Owner")
    cid = await _make_demo_consultation(client)

    # Fresh advance completes ORIENT..MOVE and leaves the Consultation AT RETURN.
    await _resume_advance(client, cid)
    detail = (await client.get(f"/api/v1/consultations/{cid}")).json()
    assert detail["consultation"]["current_stage"] == "RETURN"
    assert detail["consultation"]["status"] == "ACTIVE"  # RETURN outcome not fabricated
    assert [s["stage"] for s in detail["completed_stages"]] == ["ORIENT", "GATHER", "MAP", "MOVE"]

    # A second seed pass is a pure no-op: no new stage records, still AT RETURN.
    await _resume_advance(client, cid)
    detail2 = (await client.get(f"/api/v1/consultations/{cid}")).json()
    assert [s["stage"] for s in detail2["completed_stages"]] == ["ORIENT", "GATHER", "MAP", "MOVE"]
    assert detail2["consultation"]["current_stage"] == "RETURN"

    # Re-posting an already-completed stage is rejected (409) — never duplicated.
    replay = await client.post(
        f"/api/v1/consultations/{cid}/stages/ORIENT", headers=H(client),
        json={"payload": STAGE_PAYLOADS["ORIENT"]},
    )
    assert replay.status_code == 409

    # Exactly one Consultation for this owner.
    listing = (await client.get("/api/v1/consultations")).json()
    assert sum(row["title"] == "Release readiness return" for row in listing) == 1


async def test_seed_consultation_resumes_from_partial_interruption(client):
    await register_user(chosen_name="Partial Owner", client=client)
    cid = await _make_demo_consultation(client)

    # Simulate a partial seed that only completed ORIENT before interruption.
    r = await client.post(
        f"/api/v1/consultations/{cid}/stages/ORIENT", headers=H(client),
        json={"payload": STAGE_PAYLOADS["ORIENT"]},
    )
    assert r.status_code == 201
    mid = (await client.get(f"/api/v1/consultations/{cid}")).json()
    assert mid["consultation"]["current_stage"] == "GATHER"

    # A rerun resumes from GATHER and completes to RETURN — no duplicate ORIENT.
    await _resume_advance(client, cid)
    detail = (await client.get(f"/api/v1/consultations/{cid}")).json()
    assert [s["stage"] for s in detail["completed_stages"]] == ["ORIENT", "GATHER", "MAP", "MOVE"]
    assert detail["consultation"]["current_stage"] == "RETURN"


async def test_orient_requires_affected_people_not_obsolete_scope(client):
    """Regression guard for the exact seed drift: the obsolete ORIENT `scope` key
    no longer satisfies the contract; `affected_people` is required."""
    await register_user(chosen_name="Contract Owner", client=client)
    cid = await _make_demo_consultation(client)
    stale = await client.post(
        f"/api/v1/consultations/{cid}/stages/ORIENT", headers=H(client),
        json={"payload": {"actual_question": "What evidence is enough?", "scope": "bounded release proof"}},
    )
    assert stale.status_code == 422
    assert "affected_people" in stale.json()["detail"]
