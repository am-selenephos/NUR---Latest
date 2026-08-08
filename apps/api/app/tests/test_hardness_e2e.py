"""End-to-end integration test for Hardness / Self-Directed Learning Plane V1 Slice 1."""
from __future__ import annotations

import uuid
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cognition.correction_service import persist_user_correction
from app.learning.hardness.pipeline import run_owner_correction_hardness_slice
from app.learning.hardness.schemas import PromotionRecommendation, SelectionStatus
from app.models.hardness import (
    CurriculumSnapshotRecord,
    LearningCandidateRecord,
    LearningPromotionProposalRecord,
    LearningSignalRecord,
    TrainingExperimentRecord,
)
from app.tests.conftest import register_user

SET_USER = "SELECT set_config('app.current_user_id', :uid, true)"


async def test_owner_correction_hardness_slice_e2e(client, app_engine):
    # 1. Register user
    res, _, _ = await register_user(client)
    owner_user_id = uuid.UUID(res.json()["id"])

    session_maker = async_sessionmaker(app_engine, expire_on_commit=False, class_=AsyncSession)

    async with session_maker() as db:
        await db.execute(text(SET_USER), {"uid": str(owner_user_id)})

        # 2. Test cognition hook integration (persist_user_correction)
        corr_text = "The launch date is actually 2026-08-08, not 2026-08-01."
        corr_reason = "Date was changed in the steering committee meeting."

        corr_row = await persist_user_correction(
            db,
            owner_user_id=owner_user_id,
            orbit_id=None,
            target_event_id=None,
            correction_text=corr_text,
            reason=corr_reason,
        )
        assert corr_row is not None

        # Verify learning signal was persisted by the hook
        sig_stmt = select(LearningSignalRecord).where(
            LearningSignalRecord.owner_user_id == owner_user_id
        )
        sig_res = await db.execute(sig_stmt)
        signals = sig_res.scalars().all()
        assert len(signals) == 1
        assert signals[0].signal_kind == "OWNER_CORRECTION"
        assert signals[0].structured_payload["correction_text"] == corr_text

        # 3. Run full end-to-end slice pipeline
        result1 = await run_owner_correction_hardness_slice(
            db,
            owner_user_id=owner_user_id,
            correction_text=corr_text,
            reason=corr_reason,
            base_checkpoint_id="base_model_v1",
            capability_id="temporal_cognition",
            task_class="event_date_reasoning",
        )

        assert result1.signal_id is not None
        assert result1.candidate_id is not None
        assert result1.judgment.status == SelectionStatus.SELECTED
        assert result1.curriculum_id is not None
        assert result1.experiment_id is not None
        assert result1.eval_result.verdict == "PASS"
        assert result1.eval_result.real_model_evaluated is False
        assert result1.recommendation == PromotionRecommendation.DRY_RUN_VALIDATED
        assert result1.why_changed_ref is not None

        # 4. Verify candidate deduplication & recurrence increment on repeated correction
        result2 = await run_owner_correction_hardness_slice(
            db,
            owner_user_id=owner_user_id,
            correction_text=corr_text,
            reason=corr_reason,
            base_checkpoint_id="base_model_v1",
            capability_id="temporal_cognition",
            task_class="event_date_reasoning",
        )

        assert result2.candidate_id == result1.candidate_id
        assert result2.candidate_fingerprint == result1.candidate_fingerprint

        # Verify candidate row in database
        cand_stmt = select(LearningCandidateRecord).where(
            LearningCandidateRecord.id == result1.candidate_id
        )
        cand_row = (await db.execute(cand_stmt)).scalar_one()
        assert cand_row.recurrence_count == 2
        assert cand_row.status == "SELECTED"
        assert cand_row.selection_score is not None
        assert cand_row.learning_value is not None

        # 5. Verify curriculum snapshot partitions and hashes
        curr_stmt = select(CurriculumSnapshotRecord).where(
            CurriculumSnapshotRecord.id == result1.curriculum_id
        )
        curr_row = (await db.execute(curr_stmt)).scalar_one()
        assert curr_row.dataset_hash == result1.dataset_hash
        assert curr_row.selector_policy_version == "hardness-selector-v1"
        assert "temporal_cognition" in curr_row.target_capabilities

        # 6. Verify training experiment record
        exp_stmt = select(TrainingExperimentRecord).where(
            TrainingExperimentRecord.id == result1.experiment_id
        )
        exp_row = (await db.execute(exp_stmt)).scalar_one()
        assert exp_row.status == "COMPLETED"
        assert exp_row.trainer_type == "DRY_RUN"
        assert exp_row.candidate_artifact_hash == result1.artifact.artifact_hash

        # 7. Verify promotion proposal and WhyChanged lineage
        prop_stmt = select(LearningPromotionProposalRecord).where(
            LearningPromotionProposalRecord.id == result1.proposal_id
        )
        prop_row = (await db.execute(prop_stmt)).scalar_one()
        assert prop_row.recommendation == "DRY_RUN_VALIDATED"
        assert prop_row.critical_gates_passed is True
        assert prop_row.why_changed_ref.startswith("why_changed:")

        # 8. Verify exact signal retry idempotency
        from app.learning.hardness.candidates import ingest_candidate_from_signal
        from app.learning.hardness.schemas import LearningSignalKind
        from app.learning.hardness.signals import persist_learning_signal

        raw_sig = await persist_learning_signal(
            db,
            owner_user_id=owner_user_id,
            signal_kind=LearningSignalKind.OWNER_CORRECTION,
            task_class="idempotency_check",
            summary="Checking retry",
            structured_payload={"failure_signature": "sig_retry", "desired_behavior": "desired_retry"},
        )
        cand_retry_1 = await ingest_candidate_from_signal(
            db, signal=raw_sig, failure_signature="sig_retry", desired_behavior="desired_retry"
        )
        rec_before = cand_retry_1.recurrence_count

        # Re-ingest the exact same signal object (retry scenario)
        cand_retry_2 = await ingest_candidate_from_signal(
            db, signal=raw_sig, failure_signature="sig_retry", desired_behavior="desired_retry"
        )
        assert cand_retry_2.id == cand_retry_1.id
        assert cand_retry_2.recurrence_count == rec_before, "Retry of identical signal must not increment recurrence"


