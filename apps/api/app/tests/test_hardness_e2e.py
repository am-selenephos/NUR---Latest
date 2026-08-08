"""End-to-end integration test for Hardness / Self-Directed Learning Plane V1 Slice 1."""
from __future__ import annotations

import uuid
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.learning.hardness.candidates import ingest_candidate_from_signal
from app.learning.hardness.pipeline import process_learning_signal, run_owner_correction_hardness_slice
from app.learning.hardness.schemas import (
    LearningIntervention,
    LearningSignalKind,
    PromotionRecommendation,
    SelectionStatus,
)
from app.learning.hardness.signals import persist_learning_signal
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

        corr_text = "The launch date is actually 2026-08-08, not 2026-08-01."
        corr_reason = "Date was changed in the steering committee meeting."

        # 2. Run first owner correction slice end-to-end with SFT intervention
        result1 = await run_owner_correction_hardness_slice(
            db,
            owner_user_id=owner_user_id,
            correction_text=corr_text,
            reason=corr_reason,
            base_checkpoint_id="base_model_v1",
            capability_id="temporal_cognition",
            task_class="event_date_reasoning",
            intervention=LearningIntervention.SFT,
        )

        assert result1.signal_id is not None
        assert result1.candidate_id is not None
        assert result1.judgment.status == SelectionStatus.SELECTED
        assert result1.curriculum_id is not None
        assert result1.experiment_id is not None
        assert result1.eval_result.verdict == "STRUCTURAL_ONLY"
        assert result1.eval_result.real_model_evaluated is False
        assert result1.eval_result.all_structural_gates_passed is True
        assert result1.eval_result.all_critical_gates_passed is False
        assert result1.recommendation == PromotionRecommendation.DRY_RUN_VALIDATED
        assert result1.why_changed_ref is not None

        # Verify exactly 1 signal, 1 candidate, 1 curriculum, 1 experiment, 1 proposal in DB
        signals = (await db.execute(select(LearningSignalRecord).where(LearningSignalRecord.owner_user_id == owner_user_id))).scalars().all()
        candidates = (await db.execute(select(LearningCandidateRecord).where(LearningCandidateRecord.owner_user_id == owner_user_id))).scalars().all()
        curricula = (await db.execute(select(CurriculumSnapshotRecord).where(CurriculumSnapshotRecord.owner_user_id == owner_user_id))).scalars().all()
        experiments = (await db.execute(select(TrainingExperimentRecord).where(TrainingExperimentRecord.owner_user_id == owner_user_id))).scalars().all()
        proposals = (await db.execute(select(LearningPromotionProposalRecord).where(LearningPromotionProposalRecord.owner_user_id == owner_user_id))).scalars().all()

        assert len(signals) == 1
        assert len(candidates) == 1
        assert len(curricula) == 1
        assert len(experiments) == 1
        assert len(proposals) == 1

        assert signals[0].id == result1.signal_id
        assert signals[0].signal_kind == "OWNER_CORRECTION"
        assert signals[0].structured_payload["correction_text"] == corr_text
        assert candidates[0].recurrence_count == 1
        assert experiments[0].status == "COMPLETED"
        assert experiments[0].trainer_type == "DRY_RUN"
        assert proposals[0].recommendation == "DRY_RUN_VALIDATED"
        assert proposals[0].critical_gates_passed is False
        assert proposals[0].why_changed_ref.startswith("why_changed:")

        # 3. Repeated correction with identical text deduplicates candidate and increments recurrence
        result2 = await run_owner_correction_hardness_slice(
            db,
            owner_user_id=owner_user_id,
            correction_text=corr_text,
            reason=corr_reason,
            base_checkpoint_id="base_model_v1",
            capability_id="temporal_cognition",
            task_class="event_date_reasoning",
            intervention=LearningIntervention.SFT,
        )

        assert result2.candidate_id == result1.candidate_id
        assert result2.candidate_fingerprint == result1.candidate_fingerprint

        cand_row = (await db.execute(select(LearningCandidateRecord).where(LearningCandidateRecord.id == result1.candidate_id))).scalar_one()
        assert cand_row.recurrence_count == 2
        assert cand_row.status == "SELECTED"

        # 4. Default NO_CHANGE intervention: creates curriculum snapshot, but 0 training experiments or proposals
        result_default_nc = await run_owner_correction_hardness_slice(
            db,
            owner_user_id=owner_user_id,
            correction_text="Different correction text for no-change test",
            reason="testing default NO_CHANGE intervention",
            base_checkpoint_id="base_model_v1",
            capability_id="temporal_cognition",
            task_class="event_date_reasoning",
            # Note: default intervention is LearningIntervention.NO_CHANGE
        )

        assert result_default_nc.curriculum_id is not None
        assert result_default_nc.dataset_hash is not None
        assert result_default_nc.experiment_id is None, "Default NO_CHANGE intervention must not create training experiment"
        assert result_default_nc.artifact is None
        assert result_default_nc.eval_result is None
        assert result_default_nc.proposal_id is None
        assert result_default_nc.recommendation is None
        assert result_default_nc.why_changed_ref.startswith("why_changed:")

        # 5. Direct process_learning_signal with NO_CHANGE intervention
        raw_sig_nc = await persist_learning_signal(
            db,
            owner_user_id=owner_user_id,
            signal_kind=LearningSignalKind.OWNER_CORRECTION,
            task_class="no_change_check",
            summary="Direct signal test for NO_CHANGE",
            structured_payload={"failure_signature": "sig_nc", "desired_behavior": "desired_nc"},
        )
        res_direct_nc = await process_learning_signal(
            db,
            signal=raw_sig_nc,
            intervention=LearningIntervention.NO_CHANGE,
        )
        assert res_direct_nc.curriculum_id is not None
        assert res_direct_nc.experiment_id is None
        assert res_direct_nc.proposal_id is None
        assert res_direct_nc.recommendation is None

        # 6. Verify exact signal retry idempotency
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



