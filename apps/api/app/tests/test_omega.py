from pathlib import Path

from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.ai.schemas import AIProviderResult, NURTalkOutput
from app.omega.evaluation_cases_runner import load_omega_fixture_cases, run_omega_fixture_evaluation
from app.tests.conftest import register_user

SET_USER = "SELECT set_config('app.current_user_id', :uid, true)"
OMEGA_TABLES = [
    "omega_experiences",
    "omega_claims",
    "omega_evidence_edges",
    "omega_contradictions",
    "omega_workspace_frames",
    "omega_predictions",
    "omega_learning_proposals",
    "omega_consolidation_runs",
    "omega_review_queue",
]


def H(c: AsyncClient) -> dict:
    return {"X-CSRF-Token": c.cookies.get("nur_csrf")}


def other_client(client) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=client.app), base_url="http://test")


class OmegaTestProvider:
    name = "openai"

    async def complete_private_talk(self, request, event_sink=None):  # noqa: ARG002
        return AIProviderResult(
            provider="openai",
            model="omega-test-model",
            available=True,
            raw_response_id="resp_omega_test",
            usage={"input_tokens": 1, "output_tokens": 1},
            output=NURTalkOutput(
                direct_response="The workspace frame was bounded.",
                observed=[],
                inferred=[],
                hypotheses=[],
                uncertainty=[],
                next_move="Review the bounded frame.",
                memory_candidates=[],
                source_refs=[],
            ),
        )


async def test_omega_tables_force_rls(client, super_engine):
    await register_user(client)
    async with super_engine.connect() as conn:
        rows = (await conn.execute(text("""
            SELECT relname, relrowsecurity, relforcerowsecurity
            FROM pg_class
            WHERE relname = ANY(:tables)
            ORDER BY relname
        """), {"tables": OMEGA_TABLES})).mappings().all()
    assert {r["relname"] for r in rows} == set(OMEGA_TABLES)
    assert all(r["relrowsecurity"] and r["relforcerowsecurity"] for r in rows)


async def test_user_a_cannot_read_user_b_omega_experiences_and_claims(client, app_engine, super_engine):
    ra, _, _ = await register_user(client)
    uid_a = ra.json()["id"]
    exp = (await client.post("/api/v1/omega/experiences/from-event", headers=H(client), json={
        "event": {
            "source_kind": "MANUAL",
            "event_kind": "DECISION",
            "summary": "A-only Omega marker alpha-771",
            "provenance_label": "OWNER_WRITTEN",
        }
    })).json()
    claim = (await client.post("/api/v1/omega/claims", headers=H(client), json={
        "claim_text": "A-only Omega claim alpha-771",
        "claim_type": "DECISION",
        "truth_status": "OBSERVED",
        "provenance_label": "OWNER_WRITTEN",
        "evidence_id": exp["id"],
        "evidence_kind": "EXPERIENCE",
    })).json()
    client.cookies.clear()
    rb, _, _ = await register_user(client, chosen_name="Bee")
    uid_b = rb.json()["id"]

    assert claim["id"] not in {c["id"] for c in (await client.get("/api/v1/omega/claims")).json()}
    assert exp["id"] not in {e["id"] for e in (await client.get("/api/v1/omega/experiences")).json()}
    assert (await client.post(f"/api/v1/omega/claims/{claim['id']}/confirm", headers=H(client))).status_code == 404

    async with app_engine.connect() as conn:
        await conn.execute(text(SET_USER), {"uid": uid_b})
        b_counts = {
            table: (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
            for table in ["omega_experiences", "omega_claims", "omega_evidence_edges"]
        }
        await conn.rollback()
        await conn.execute(text(SET_USER), {"uid": uid_a})
        a_counts = {
            table: (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
            for table in ["omega_experiences", "omega_claims", "omega_evidence_edges"]
        }
        await conn.rollback()

    assert all(v == 0 for v in b_counts.values())
    assert a_counts["omega_experiences"] == 1
    assert a_counts["omega_claims"] == 1
    assert a_counts["omega_evidence_edges"] == 1


async def test_model_generated_claim_not_observed_and_owner_written_can_be_observed(client):
    await register_user(client)
    model_claim = (await client.post("/api/v1/omega/claims", headers=H(client), json={
        "claim_text": "Model thinks this should be fact.",
        "claim_type": "FACT",
        "truth_status": "OBSERVED",
        "provenance_label": "MODEL_GENERATED",
    })).json()
    owner_claim = (await client.post("/api/v1/omega/claims", headers=H(client), json={
        "claim_text": "Owner explicitly decided the research layer is private.",
        "claim_type": "DECISION",
        "truth_status": "OBSERVED",
        "provenance_label": "OWNER_WRITTEN",
    })).json()
    assert model_claim["truth_status"] == "HYPOTHESIS"
    assert owner_claim["truth_status"] == "OBSERVED"


async def test_outcome_contradicts_prediction_and_correction_weakens_claim(client, super_engine):
    response, _, _ = await register_user(client)
    owner_user_id = response.json()["id"]
    plan = (await client.post("/api/v1/plans", headers=H(client), json={
        "title": "Omega prediction route",
        "steps": [{"title": "Ship the owner proof"}],
    })).json()
    step_id = plan["steps"][0]["id"]
    prediction = (await client.post("/api/v1/omega/predictions", headers=H(client), json={
        "prediction_text": "The owner proof will mention green status.",
        "expected_observation": "green status",
        "plan_step_id": step_id,
        "confidence": 0.72,
    })).json()
    claim = (await client.post("/api/v1/omega/claims", headers=H(client), json={
        "claim_text": "visual exact language is always enough",
        "claim_type": "HYPOTHESIS",
        "truth_status": "HYPOTHESIS",
        "provenance_label": "MODEL_GENERATED",
    })).json()
    await client.post("/api/v1/cognition/corrections", headers=H(client), json={
        "correction_text": "visual exact language is not always enough",
        "reason": "Owner correction should weaken overconfident claim.",
    })
    await client.post("/api/v1/outcomes", headers=H(client), json={
        "plan_step_id": step_id,
        "observed_result": "The owner proof shipped but had red status.",
    })
    run = (await client.post("/api/v1/omega/consolidate", headers=H(client), json={"run_kind": "POST_OUTCOME"})).json()
    claims = (await client.get("/api/v1/omega/claims")).json()
    predictions = (await client.get("/api/v1/omega/predictions")).json()
    weakened = [c for c in claims if c["id"] == claim["id"]][0]
    resolved = [p for p in predictions if p["id"] == prediction["id"]][0]
    assert run["updated_claims"] >= 1
    assert weakened["truth_status"] == "CONTRADICTED"
    assert resolved["status"] == "DISCONFIRMED"
    why = (await client.get(
        f"/api/v1/omega/claims/{claim['id']}/why-changed"
    )).json()
    assert any("HYPOTHESIS" in item for item in why["changed_because"])

    async with super_engine.connect() as db:
        row = (
            await db.execute(
                text(
                    "SELECT previous_version, new_version FROM why_changed_records "
                    "WHERE owner_user_id=:owner_user_id AND entity_id=:claim_id "
                    "AND change_class='contradicted'"
                ),
                {"owner_user_id": owner_user_id, "claim_id": claim["id"]},
            )
        ).mappings().one()
    assert row["previous_version"].startswith("HYPOTHESIS:")
    assert row["new_version"].startswith("CONTRADICTED:")


async def test_contradiction_detected_between_decision_and_constraint(client):
    await register_user(client)
    await client.post("/api/v1/omega/claims", headers=H(client), json={
        "claim_text": "Capsule law must not send raw owner memory to recipients.",
        "claim_type": "CONSTRAINT",
        "truth_status": "OBSERVED",
        "provenance_label": "OWNER_WRITTEN",
    })
    await client.post("/api/v1/omega/claims", headers=H(client), json={
        "claim_text": "We will send raw owner memory to recipients.",
        "claim_type": "DECISION",
        "truth_status": "HYPOTHESIS",
        "provenance_label": "MODEL_GENERATED",
    })
    run = (await client.post("/api/v1/omega/consolidate", headers=H(client), json={"run_kind": "MANUAL"})).json()
    contradictions = (await client.get("/api/v1/omega/contradictions?status=OPEN")).json()
    assert run["contradictions_found"] >= 1
    assert any("raw owner memory" in c["description"] for c in contradictions)


async def test_workspace_frame_caps_sources_and_excludes_secrets(client, super_engine, monkeypatch):
    await register_user(client)
    monkeypatch.setattr("app.cognition.intelligence_kernel.get_ai_provider", lambda: OmegaTestProvider())
    for i in range(9):
        await client.post("/api/v1/omega/claims", headers=H(client), json={
            "claim_text": f"Owner claim {i}",
            "claim_type": "HYPOTHESIS",
            "truth_status": "HYPOTHESIS",
            "provenance_label": "MODEL_GENERATED",
        })
    await client.post("/api/v1/omega/experiences/from-event", headers=H(client), json={
        "event": {
            "source_kind": "MANUAL",
            "event_kind": "SECRET_NOTE",
            "summary": "secret: should-not-enter-frame",
            "provenance_label": "OWNER_WRITTEN",
        }
    })
    talk = (await client.post("/api/v1/cognition/talk", headers=H(client), json={
        "message": "What changed?",
        "locale": "en",
    })).json()
    frame_id = talk["omega"]["workspace_frame_id"]
    assert frame_id
    async with super_engine.connect() as conn:
        frame = (await conn.execute(text("""
            SELECT attention_items, retrieved_claim_ids, retrieved_experience_ids, risk_flags, scope_statement
            FROM omega_workspace_frames WHERE id=:id
        """), {"id": frame_id})).mappings().one()
    assert len(frame["retrieved_claim_ids"]) <= 6
    assert len(frame["retrieved_experience_ids"]) <= 6
    assert "should-not-enter-frame" not in str(frame["attention_items"])
    assert "no chain-of-thought" in frame["scope_statement"].lower()
    assert "omega_context_owner_only" in frame["risk_flags"]


async def test_learning_proposal_guardrails_and_transitions(client):
    await register_user(client)
    blocked = await client.post("/api/v1/omega/learning-proposals", headers=H(client), json={
        "proposal_kind": "MEMORY_POLICY",
        "description": "Rewrite RLS and auth policy automatically.",
        "evidence_summary": "Should be blocked.",
    })
    assert blocked.status_code == 422
    created = (await client.post("/api/v1/omega/learning-proposals", headers=H(client), json={
        "proposal_kind": "PLANNING_HEURISTIC",
        "description": "Ask for outcome before strengthening a planning pattern.",
        "evidence_summary": "Repeated corrections showed over-promotion risk.",
    })).json()
    approved = (await client.post(f"/api/v1/omega/learning-proposals/{created['id']}/approve", headers=H(client))).json()
    rolled_back = (await client.post(f"/api/v1/omega/learning-proposals/{created['id']}/rollback", headers=H(client))).json()
    assert approved["approved_by_owner"] is True and approved["status"] == "APPROVED"
    assert rolled_back["approved_by_owner"] is False and rolled_back["status"] == "ROLLED_BACK"


async def test_capsule_recipient_cannot_retrieve_owner_omega_context(client):
    await register_user(client)
    claim = (await client.post("/api/v1/omega/claims", headers=H(client), json={
        "claim_text": "Omega-only owner secret marker omega-priv-994",
        "claim_type": "FACT",
        "truth_status": "OBSERVED",
        "provenance_label": "OWNER_WRITTEN",
    })).json()
    orbit = (await client.get("/api/v1/orbits")).json()[0]["id"]
    decision = (await client.post(f"/api/v1/orbits/{orbit}/decisions", headers=H(client), json={
        "statement": "Capsule recipients see only approved sources.",
    })).json()
    source = (await client.post(f"/api/v1/orbits/{orbit}/sources", headers=H(client), json={
        "source_kind": "DECISION",
        "source_id": decision["id"],
    })).json()
    async with other_client(client) as b:
        _, b_email, _ = await register_user(b, chosen_name="Bee")
        capsule = (await client.post(f"/api/v1/orbits/{orbit}/capsules", headers=H(client), json={
            "title": "Omega isolation",
            "purpose": "Prove capsule isolation from owner Omega memory.",
            "capability": "ASK_SCOPED_QUESTIONS",
            "orbit_source_ids": [source["id"]],
        })).json()
        await client.post(f"/api/v1/capsules/{capsule['id']}/grants", headers=H(client), json={
            "recipient_email": b_email,
            "capability": "ASK_SCOPED_QUESTIONS",
        })
        answer = (await b.post(f"/api/v1/capsules/{capsule['id']}/questions", headers=H(b), json={
            "question": "What is omega-priv-994?",
        })).json()
        assert answer["answer_mode"] == "NOT_AVAILABLE"
        assert "omega-priv-994" not in answer["answer_text"]
        assert "omega-priv-994" not in str(answer["source_refs"])
        assert "omega-priv-994" not in (answer["policy_explanation"] or "")
        assert (await b.post(f"/api/v1/omega/claims/{claim['id']}/confirm", headers=H(b))).status_code == 404


async def test_sensitive_model_generated_claim_waits_for_owner_review_then_approves_as_inferred(client):
    await register_user(client)
    await client.post("/api/v1/cognition/events", headers=H(client), json={
        "event_kind": "MODEL_RESPONSE",
        "content_text": "Model response: identity preference may be private and sensitive.",
    })
    run = (await client.post("/api/v1/omega/consolidate", headers=H(client), json={"run_kind": "MANUAL"})).json()
    reviews = (await client.get("/api/v1/omega/review-queue")).json()
    assert run["input_counts"]["queued_review_items"] == 1
    assert reviews[0]["status"] == "PENDING_REVIEW"
    assert reviews[0]["candidate_truth_status"] == "INFERRED"
    approved = (await client.post(f"/api/v1/omega/review-queue/{reviews[0]['id']}/approve", headers=H(client))).json()
    claims = (await client.get("/api/v1/omega/claims")).json()
    assert approved["status"] == "APPROVED"
    assert any(c["id"] == approved["created_claim_id"] and c["truth_status"] == "INFERRED" for c in claims)


async def test_owner_omega_export_excludes_raw_capsule_and_chain_of_thought(client):
    await register_user(client)
    await client.post("/api/v1/omega/claims", headers=H(client), json={
        "claim_text": "Owner export is structured and owner-only.",
        "claim_type": "FACT",
        "truth_status": "OBSERVED",
        "provenance_label": "OWNER_WRITTEN",
    })
    exported = (await client.get("/api/v1/omega/export")).json()
    dumped = str(exported).lower()
    assert exported["safety"]["owner_only"] is True
    assert exported["safety"]["capsule_recipient_context_excluded"] is True
    assert exported["safety"]["chain_of_thought_excluded"] is True
    assert "chain_of_thought_excluded" in dumped
    assert "raw private dump" not in dumped


async def test_why_changed_reports_evidence_edges_not_hidden_reasoning(client):
    await register_user(client)
    exp = (await client.post("/api/v1/omega/experiences/from-event", headers=H(client), json={
        "event": {
            "source_kind": "MANUAL",
            "event_kind": "OUTCOME_REPORTED",
            "summary": "Outcome evidence improved a planning pattern.",
            "provenance_label": "OBSERVED_OUTCOME",
        }
    })).json()
    claim = (await client.post("/api/v1/omega/claims", headers=H(client), json={
        "claim_text": "Outcome evidence improved a planning pattern.",
        "claim_type": "PATTERN",
        "truth_status": "OBSERVED",
        "provenance_label": "OBSERVED_OUTCOME",
        "evidence_id": exp["id"],
        "evidence_kind": "EXPERIENCE",
    })).json()
    why = (await client.get(f"/api/v1/omega/claims/{claim['id']}/why-changed")).json()
    assert why["supporting_edges"]
    assert "supporting evidence" in " ".join(why["changed_because"]).lower()
    assert "chain" not in str(why).lower()


async def test_omega_claim_lifecycle_uses_canonical_why_changed_ledger(client, super_engine):
    response, _, _ = await register_user(client)
    owner_user_id = response.json()["id"]
    claim = (await client.post("/api/v1/omega/claims", headers=H(client), json={
        "claim_text": "A durable claim changes only through reviewed evidence.",
        "claim_type": "HYPOTHESIS",
        "truth_status": "HYPOTHESIS",
        "provenance_label": "OWNER_WRITTEN",
        "confidence": 0.45,
    })).json()

    confirmed = await client.post(
        f"/api/v1/omega/claims/{claim['id']}/confirm",
        headers=H(client),
    )
    assert confirmed.status_code == 200
    retired = await client.post(
        f"/api/v1/omega/claims/{claim['id']}/retire",
        headers=H(client),
    )
    assert retired.status_code == 200

    why = (await client.get(
        f"/api/v1/omega/claims/{claim['id']}/why-changed"
    )).json()
    joined_reasons = " ".join(why["changed_because"]).lower()
    assert "owner retired" in joined_reasons
    assert "owner confirmed" in joined_reasons
    assert "held owner-visible record" in joined_reasons

    async with super_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT entity_type, change_class, previous_version, "
                    "new_version, trigger FROM why_changed_records "
                    "WHERE owner_user_id=:owner_user_id AND entity_id=:claim_id"
                ),
                {"owner_user_id": owner_user_id, "claim_id": claim["id"]},
            )
        ).mappings().all()

    assert len(rows) == 3
    assert {row["entity_type"] for row in rows} == {"omega_claim"}
    assert {row["change_class"] for row in rows} == {
        "created",
        "promoted",
        "retracted",
    }
    assert {(row["previous_version"], row["new_version"]) for row in rows} == {
        (None, "HYPOTHESIS"),
        ("HYPOTHESIS", "OBSERVED"),
        ("OBSERVED", "RETIRED"),
    }


async def test_consolidation_lock_blocks_double_run(client, super_engine):
    r, _, _ = await register_user(client)
    uid = r.json()["id"]
    async with super_engine.begin() as conn:
        await conn.execute(text("""
            INSERT INTO omega_consolidation_runs(owner_user_id, run_kind, status)
            VALUES (:uid, 'MANUAL', 'STARTED')
        """), {"uid": uid})
    locked = await client.post("/api/v1/omega/consolidate", headers=H(client), json={"run_kind": "MANUAL"})
    assert locked.status_code == 409
    assert "already running" in locked.text


async def test_omega_fixture_runner_covers_25_messy_cases():
    fixture = Path(__file__).parent / "fixtures" / "omega_v1_messy_project_cases.jsonl"
    cases = load_omega_fixture_cases(fixture)
    result = run_omega_fixture_evaluation(cases)
    assert result["case_count"] == 25
    assert all(value == 25 for value in result["totals"].values())


async def test_omega_scheduler_beat_task_is_registered():
    from app.workers.celery_app import celery

    schedule = celery.conf.beat_schedule["nur-omega-consolidate-due-owners"]
    assert schedule["task"] == "nur.omega_consolidate_due_owners"
    assert schedule["schedule"] >= 3600


async def test_omega_stress_105_experiences_is_idempotent_and_count_only(client):
    await register_user(client)
    for i in range(105):
        await client.post("/api/v1/cognition/events", headers=H(client), json={
            "event_kind": "OUTCOME_REPORTED",
            "content_text": f"Outcome: observed: stress marker {i} returned one visible result.",
        })
    first = (await client.post("/api/v1/omega/consolidate", headers=H(client), json={"run_kind": "MANUAL"})).json()
    second = (await client.post("/api/v1/omega/consolidate", headers=H(client), json={"run_kind": "MANUAL"})).json()
    assert first["input_counts"]["recent_events"] == 100
    assert first["input_counts"]["created_experiences"] == 100
    assert first["created_claims"] == 100
    assert second["input_counts"]["created_experiences"] == 0
    assert "stress marker" not in str(first["input_counts"])
