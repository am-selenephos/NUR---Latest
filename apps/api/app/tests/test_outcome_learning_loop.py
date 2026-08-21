"""Observed outcomes and owner corrections must change governed future state."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cognition.personal_memory_service import approve_candidate
from app.db.rls import set_user_context
from app.mind.context import load_semantic_hydration_inputs
from app.models import (
    ClaimEvidence,
    CognitiveEvent,
    LearningCandidateRecord,
    LearningSignalRecord,
    MemoryCandidate,
    PersonalMemory,
    Prediction,
    SemanticClaim,
    WhyChangedRecordRow,
)
from app.tests.conftest import register_user

API = "/api/v1"


async def _csrf(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("nur_csrf")}


@pytest.fixture()
async def owner(client) -> uuid.UUID:
    response, _, _ = await register_user(client)
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


async def _make_prediction(client) -> str:
    goal = await client.post(
        f"{API}/goals",
        json={"system_slug": "creation", "title": "Close the learning loop"},
        headers=await _csrf(client),
    )
    assert goal.status_code == 201, goal.text
    prediction = await client.post(
        f"{API}/map/predict-path",
        json={
            "system_slug": "creation",
            "path_type": "continue",
            "goal_id": goal.json()["id"],
            "horizon_days": 14,
        },
        headers=await _csrf(client),
    )
    assert prediction.status_code == 201, prediction.text
    return prediction.json()["id"]


@pytest.mark.asyncio
async def test_prediction_resolution_closes_governed_learning_and_memory_loop(
    client,
    owner,
    super_engine,
):
    prediction_id = await _make_prediction(client)
    learning = "Migration work must be represented before estimating delivery."
    response = await client.post(
        f"{API}/map/predictions/{prediction_id}/resolve",
        json={"resolution": "CONTRADICTED", "learning": learning},
        headers=await _csrf(client),
    )
    assert response.status_code == 200, response.text

    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner)
        prediction = await db.scalar(
            select(Prediction).where(
                Prediction.id == uuid.UUID(prediction_id),
                Prediction.owner_user_id == owner,
            )
        )
        assert prediction is not None
        assert prediction.outcome_event_id is not None

        signal = await db.scalar(
            select(LearningSignalRecord).where(
                LearningSignalRecord.owner_user_id == owner,
                LearningSignalRecord.idempotency_key
                == f"prediction:{prediction_id}:resolution",
            )
        )
        assert signal is not None
        assert signal.signal_kind == "OUTCOME_MISS"
        candidate = await db.scalar(
            select(LearningCandidateRecord).where(
                LearningCandidateRecord.owner_user_id == owner,
                LearningCandidateRecord.source_refs.contains([f"signal:{signal.id}"]),
            )
        )
        assert candidate is not None
        assert candidate.risk_status == "ASSESSED"
        assert candidate.status in {"SELECTED", "DEFERRED", "REJECTED"}

        memory_candidate = await db.scalar(
            select(MemoryCandidate).where(
                MemoryCandidate.owner_user_id == owner,
                MemoryCandidate.source_event_id == prediction.outcome_event_id,
            )
        )
        assert memory_candidate is not None
        assert memory_candidate.status == "CANDIDATE"
        assert memory_candidate.provenance_label == "OBSERVED_OUTCOME"
        assert memory_candidate.candidate_text == learning

        claim = await db.scalar(
            select(SemanticClaim).where(
                SemanticClaim.owner_user_id == owner,
                SemanticClaim.subject_ref == f"prediction:{prediction_id}",
            )
        )
        assert claim is not None
        assert claim.status == "DISPUTED"
        assert claim.counterevidence_count == 1

        changed_types = set(
            await db.scalars(
                select(WhyChangedRecordRow.entity_type).where(
                    WhyChangedRecordRow.owner_user_id == owner
                )
            )
        )
        assert {"prediction", "belief", "memory", "learning_candidate"} <= changed_types

        before_approval = await load_semantic_hydration_inputs(
            db,
            owner_user_id=owner,
            orbit_id=prediction.orbit_id,
            limit=10,
        )
        assert all(item["content"] != learning for item in before_approval["approved_memory"])
        assert any(item["claim"] == prediction.statement for item in before_approval["beliefs"])

    approved = await client.post(
        f"{API}/memory-candidates/{memory_candidate.id}/approve",
        json={"review_note": "This observed correction should guide future estimates."},
        headers=await _csrf(client),
    )
    assert approved.status_code == 200, approved.text

    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner)
        after_approval = await load_semantic_hydration_inputs(
            db,
            owner_user_id=owner,
            orbit_id=prediction.orbit_id,
            limit=10,
        )
        assert any(item["content"] == learning for item in after_approval["approved_memory"])

        counts_before_retry = {
            "signals": await db.scalar(
                select(func.count()).select_from(LearningSignalRecord).where(
                    LearningSignalRecord.owner_user_id == owner,
                    LearningSignalRecord.idempotency_key
                    == f"prediction:{prediction_id}:resolution",
                )
            ),
            "events": await db.scalar(
                select(func.count()).select_from(CognitiveEvent).where(
                    CognitiveEvent.owner_user_id == owner,
                    CognitiveEvent.source_ref == f"prediction_resolution:{prediction_id}",
                )
            ),
        }

    duplicate = await client.post(
        f"{API}/map/predictions/{prediction_id}/resolve",
        json={"resolution": "CONFIRMED", "learning": "must not replace evidence"},
        headers=await _csrf(client),
    )
    assert duplicate.status_code == 409, duplicate.text

    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner)
        assert await db.scalar(
            select(func.count()).select_from(LearningSignalRecord).where(
                LearningSignalRecord.owner_user_id == owner,
                LearningSignalRecord.idempotency_key
                == f"prediction:{prediction_id}:resolution",
            )
        ) == counts_before_retry["signals"]
        assert await db.scalar(
            select(func.count()).select_from(CognitiveEvent).where(
                CognitiveEvent.owner_user_id == owner,
                CognitiveEvent.source_ref == f"prediction_resolution:{prediction_id}",
            )
        ) == counts_before_retry["events"]


@pytest.mark.asyncio
async def test_owner_correction_invalidates_derived_state_and_changes_future_retrieval(
    client,
    owner,
    super_engine,
):
    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner)
        source = CognitiveEvent(
            owner_user_id=owner,
            event_kind="MODEL_RESPONSE",
            content_text="The deadline is Friday.",
        )
        db.add(source)
        await db.flush()
        old_candidate = MemoryCandidate(
            owner_user_id=owner,
            source_event_id=source.id,
            candidate_text="The deadline is Friday.",
            original_text="The deadline is Friday.",
            provenance_label="MODEL_GENERATED",
            created_by="MODEL",
            source_object_ids={"assistant_message_event_id": str(source.id)},
        )
        db.add(old_candidate)
        claim = SemanticClaim(
            owner_user_id=owner,
            claim_text="The deadline is Friday.",
            subject_ref="talk:deadline",
            status="SUPPORTED",
            confidence=0.9,
            evidence_count=2,
        )
        db.add(claim)
        await db.flush()
        db.add(
            ClaimEvidence(
                owner_user_id=owner,
                claim_id=claim.id,
                event_id=source.id,
                supports=True,
                rationale="model inference",
            )
        )
        memory = await approve_candidate(
            db,
            owner_user_id=owner,
            candidate_id=old_candidate.id,
            review_note="Accepted before later correction.",
        )
        source_id = source.id
        old_candidate_id = old_candidate.id
        memory_id = memory.id
        claim_id = claim.id
        await db.commit()

    correction_text = "The deadline is Monday, not Friday."
    corrected = await client.post(
        f"{API}/cognition/corrections",
        json={
            "target_event_id": str(source_id),
            "correction_text": correction_text,
            "reason": "Owner supplied the authoritative date.",
        },
        headers=await _csrf(client),
    )
    assert corrected.status_code == 201, corrected.text
    correction_id = corrected.json()["id"]

    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner)
        old_memory = await db.get(PersonalMemory, memory_id)
        prior_candidate = await db.get(MemoryCandidate, old_candidate_id)
        revised_claim = await db.get(SemanticClaim, claim_id)
        assert old_memory is not None and old_memory.status == "RETIRED"
        assert prior_candidate is not None and prior_candidate.status == "REJECTED"
        assert revised_claim is not None and revised_claim.status == "DISPUTED"
        assert revised_claim.counterevidence_count == 1

        correction_candidate = await db.scalar(
            select(MemoryCandidate).where(
                MemoryCandidate.owner_user_id == owner,
                MemoryCandidate.source_object_ids["source_correction_id"].astext
                == correction_id,
            )
        )
        assert correction_candidate is not None
        assert correction_candidate.candidate_text == correction_text
        assert correction_candidate.status == "CANDIDATE"
        assert correction_candidate.provenance_label == "USER_CORRECTION"

        semantic = await load_semantic_hydration_inputs(
            db,
            owner_user_id=owner,
            limit=20,
        )
        assert all(item["id"] != str(memory_id) for item in semantic["approved_memory"])
        assert any(item["claim"] == correction_text for item in semantic["beliefs"])


@pytest.mark.asyncio
async def test_correction_target_is_owner_scoped(client, super_engine):
    first, _, _ = await register_user(client)
    first_id = uuid.UUID(first.json()["id"])
    async with AsyncSession(super_engine) as db:
        await set_user_context(db, first_id)
        source = CognitiveEvent(
            owner_user_id=first_id,
            event_kind="MODEL_RESPONSE",
            content_text="Private owner-one inference",
        )
        db.add(source)
        await db.flush()
        source_id = source.id
        await db.commit()

    second, _, _ = await register_user(client)
    assert second.status_code == 201, second.text
    response = await client.post(
        f"{API}/cognition/corrections",
        json={
            "target_event_id": str(source_id),
            "correction_text": "Attempted cross-owner reference",
        },
        headers=await _csrf(client),
    )
    assert response.status_code == 404, response.text
