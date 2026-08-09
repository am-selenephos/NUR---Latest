"""Gate 2 proof: owner-bound cognitive substrate, honest cycle, deterministic
outcome revision with provenance (mandate D/E/F)."""

from httpx import ASGITransport, AsyncClient

from app.tests.conftest import register_user


def H(c: AsyncClient) -> dict:
    return {"X-CSRF-Token": c.cookies.get("nur_csrf")}


async def other_client(client) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=client.app), base_url="http://test")


async def test_event_ledger_and_cycle_is_honest(client):
    await register_user(client)
    # seed traces so retrieval has something REAL to find
    r = await client.post("/api/v1/journal", headers=H(client),
                          json={"body": "The interior galaxy must keep the V197 visual language exact."})
    assert r.status_code == 201
    orbit_id = (await client.get("/api/v1/orbits")).json()[0]["id"]
    r = await client.post(f"/api/v1/orbits/{orbit_id}/decisions", headers=H(client),
                          json={"statement": "V197 is the frozen visual reference.",
                                "rationale": "Screenshot parity is the contract."})
    assert r.status_code == 201

    r = await client.post("/api/v1/cognition/events", headers=H(client),
                          json={"event_kind": "TALK_TURN",
                                "content_text": "How do I keep the visual language exact while shipping?"})
    assert r.status_code == 201
    body = r.json()
    ev_id = body["event"]["id"]
    cycle = body["cycle"]
    assert cycle is not None
    # real retrieval found the seeded traces
    kinds = {ref["kind"] for ref in cycle["retrieved"]}
    assert kinds & {"JOURNAL_ENTRY", "DECISION"}
    # the gateway is honestly disabled — no invented intelligence
    assert cycle["gateway"] == "disabled" and cycle["gateway_available"] is False
    assert "AI provider is disabled" in cycle["gateway_reason"]
    assert cycle["proposals"] == []
    # the cycle left a durable EVALUATION_EVENT with provenance
    ev = await client.get(f"/api/v1/cognition/events/{cycle['evaluation_event_id']}")
    assert ev.status_code == 200
    payload = ev.json()["structured_payload"]
    assert payload["trigger_event_id"] == ev_id
    assert payload["gateway_available"] is False
    assert isinstance(payload["retrieved"], list)


async def test_cross_owner_cognition_is_invisible(client):
    await register_user(client)
    r = await client.post("/api/v1/cognition/events", headers=H(client),
                          json={"event_kind": "JOURNAL_ENTRY", "content_text": "private-to-A marker-xyz"})
    a_event = r.json()["event"]["id"]
    r = await client.post("/api/v1/hypotheses", headers=H(client),
                          json={"question": "q", "hypothesis_text": "A-only hypothesis"})
    a_hyp = r.json()["id"]

    async with await other_client(client) as b:
        await register_user(b, chosen_name="Bee")
        ids = {e["id"] for e in (await b.get("/api/v1/cognition/events")).json()}
        assert a_event not in ids
        assert (await b.get(f"/api/v1/cognition/events/{a_event}")).status_code == 404
        hyp_ids = {h["id"] for h in (await b.get("/api/v1/hypotheses")).json()}
        assert a_hyp not in hyp_ids
        assert (await b.patch(f"/api/v1/hypotheses/{a_hyp}", headers=H(b),
                              json={"status": "ARCHIVED"})).status_code == 404


async def test_outcome_revises_hypothesis_with_provenance(client):
    await register_user(client)
    r = await client.post("/api/v1/hypotheses", headers=H(client),
                          json={"question": "Does a morning block raise focus?",
                                "hypothesis_text": "A 9am deep-work block yields 90 focused minutes.",
                                "prediction": {"focus_minutes": 90}})
    hyp = r.json()
    assert hyp["status"] == "PROPOSED" and hyp["confidence"] == 0.5

    # F3: experiments demand criteria; empty criteria are refused
    r = await client.post("/api/v1/experiments", headers=H(client),
                          json={"title": "x", "intervention": "y", "hypothesis_id": hyp["id"]})
    assert r.status_code == 422

    r = await client.post("/api/v1/experiments", headers=H(client),
                          json={"title": "Morning block, 5 days", "intervention": "Block 9-11am",
                                "hypothesis_id": hyp["id"],
                                "success_criteria": {"focus_minutes": ">=80"}})
    exp = r.json()
    assert exp["status"] == "ACTIVE"

    r = await client.post(f"/api/v1/experiments/{exp['id']}/outcomes", headers=H(client),
                          json={"observed_result": "Got 70 focused minutes; phone still nearby.",
                                "structured_measurements": {"focus_minutes": 70},
                                "supports": True, "rationale": "Direction held even if magnitude missed."})
    out = r.json()
    diff = out["difference_from_prediction"]["compared"]["focus_minutes"]
    assert diff == {"predicted": 90, "observed": 70, "delta": -20}
    assert abs(out["hypothesis_confidence"] - 0.6) < 1e-6
    assert out["claim_status"] == "EMERGING"

    h = [x for x in (await client.get("/api/v1/hypotheses")).json() if x["id"] == hyp["id"]][0]
    assert h["status"] == "TESTING"


async def test_journal_plans_research_persist(client):
    await register_user(client)
    assert (await client.post("/api/v1/journal", headers=H(client), json={"body": "kept"})).status_code == 201
    assert (await client.get("/api/v1/journal")).json()[0]["body"] == "kept"
    r = await client.post("/api/v1/plans", headers=H(client),
                          json={"title": "Interior pass", "steps": [{"title": "one real move"}]})
    step = r.json()["steps"][0]
    r = await client.patch(f"/api/v1/plan-steps/{step['id']}", headers=H(client), json={"done": True})
    assert r.json()["done"] is True and r.json()["done_at"]
    r = await client.post("/api/v1/outcomes", headers=H(client),
                          json={"observed_result": "Shipped the pass.", "plan_step_id": step["id"]})
    assert r.status_code == 201
    outcome = r.json()
    flow = (await client.get("/api/v1/timeline/flow")).json()
    projected = [row for row in flow["entries"] if row["source_id"] == outcome["id"]]
    assert len(projected) == 1
    assert projected[0]["title"] == "Shipped the pass."
    assert projected[0]["source_type"] == "OUTCOME"
    assert projected[0]["status"] == "OBSERVED"
    assert projected[0]["lane"] == "past"
    assert projected[0]["plan_id"]
    r = await client.post("/api/v1/research-drafts", headers=H(client),
                          json={"question": "What does neuroscience say about identity change?"})
    assert r.json()["status"] == "STAGED"


async def test_visible_glow_evidence_requires_persisted_outcome(client):
    await register_user(client)
    initial = (await client.get("/api/v1/orbits/current-state")).json()
    assert initial["outcomes_returned"] == 0

    r = await client.post("/api/v1/plans", headers=H(client),
                          json={"title": "Outcome gate", "steps": [{"title": "Make one real move"}]})
    step = r.json()["steps"][0]

    r = await client.patch(f"/api/v1/plan-steps/{step['id']}", headers=H(client), json={"done": True})
    assert r.status_code == 200 and r.json()["done"] is True
    after_done = (await client.get("/api/v1/orbits/current-state")).json()
    assert after_done["outcomes_returned"] == 0

    r = await client.post("/api/v1/outcomes", headers=H(client),
                          json={"observed_result": "The real-world state changed.", "plan_step_id": step["id"]})
    assert r.status_code == 201
    after_outcome = (await client.get("/api/v1/orbits/current-state")).json()
    assert after_outcome["outcomes_returned"] == 1


async def test_disabled_talk_persists_error_run_without_fake_assistant_response(client, super_engine):
    from sqlalchemy import text

    await register_user(client)
    orbit_id = (await client.get("/api/v1/orbits")).json()[0]["id"]
    r = await client.post(
        "/api/v1/cognition/talk",
        headers=H(client),
        json={"message": "Keep this as one private line.", "orbit_id": orbit_id, "locale": "en"},
    )
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail == {
        "code": "provider_disabled",
        "message": "Live AI is not enabled on this server.",
        "model_run_id": detail["model_run_id"],
        "retryable": False,
    }
    thread = (await client.get(f"/api/v1/cognition/talk-thread?orbit_id={orbit_id}")).json()
    assert [row["who"] for row in thread][-1:] == ["user"]
    async with super_engine.connect() as conn:
        run = (
            await conn.execute(
                text("SELECT status, output_event_id, error FROM model_runs WHERE id=:id"),
                {"id": detail["model_run_id"]},
            )
        ).one()
    assert run.status == "ERROR"
    assert run.output_event_id is None
    assert run.error["code"] == "provider_disabled"
