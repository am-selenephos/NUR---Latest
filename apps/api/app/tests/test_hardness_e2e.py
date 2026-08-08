"""End-to-end integration tests for Hardness / Self-Directed Learning Plane V1 Slice 1."""
from __future__ import annotations

import uuid
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cognition.correction_service import persist_user_correction
from app.learning.hardness.candidates import ingest_candidate_from_signal
from app.learning.hardness.pipeline import process_learning_signal, run_owner_correction_hardness_slice
from app.learning.hardness.schemas import (
    LearningIntervention,
    LearningSignalKind,
    PromotionRecommendation,
    SelectionStatus,
)
from app.learning.hardness.signals import persist_learning_signal
from app.models import UserCorrection
from app.models.hardness import (
    CurriculumSnapshotRecord,
    LearningCandidateRecord,
    LearningPromotionProposalRecord,
    LearningSignalRecord,
    TrainingExperimentRecord,
)
from app.tests.conftest import register_user

SET_USER = "SELECT set_config('app.current_user_id', :uid, true)"


async def test_canonical_production_chain_e2e(client, app_engine):
    """Canonical production call graph:
    persist_user_correction()
    → obtain canonical LearningSignalRecord
    → process_learning_signal(signal, intervention=SFT)
    → candidate → selector → curriculum → DryRun SFT → STRUCTURAL_ONLY → DRY_RUN_VALIDATED.

    Asserts exactly 1 UserCorrection and 1 LearningSignal before and after processing.
    """
    res, _, _ = await register_user(client)
    owner_user_id = uuid.UUID(res.json()["id"])

    session_maker = async_sessionmaker(app_engine, expire_on_commit=False, class_=AsyncSession)

    async with session_maker() as db:
        await db.execute(text(SET_USER), {"uid": str(owner_user_id)})

        corr_text = "The launch date is actually 2026-08-08, not 2026-08-01."
        corr_reason = "Date was changed in the steering committee meeting."

        # 1. Atomic entry point: persist user correction which emits exactly 1 canonical LearningSignal
        user_corr = await persist_user_correction(
            db,
            owner_user_id=owner_user_id,
            orbit_id=None,
            target_event_id=None,
            correction_text=corr_text,
            reason=corr_reason,
        )
        await db.flush()

        # Assert BEFORE processing: exactly 1 UserCorrection and 1 LearningSignal
        corrections_before = (await db.execute(select(UserCorrection).where(UserCorrection.owner_user_id == owner_user_id))).scalars().all()
        signals_before = (await db.execute(select(LearningSignalRecord).where(LearningSignalRecord.owner_user_id == owner_user_id))).scalars().all()
        assert len(corrections_before) == 1
        assert len(signals_before) == 1
        assert signals_before[0].source_correction_id == user_corr.id

        canonical_signal = signals_before[0]

        # 2. Process the canonical signal with explicit SFT intervention for DryRun coverage
        result = await process_learning_signal(
            db,
            signal=canonical_signal,
            base_checkpoint_id="base_model_v1",
            capability_id="temporal_cognition",
            task_class="event_date_reasoning",
            intervention=LearningIntervention.SFT,
        )

        assert result.signal_id == canonical_signal.id
        assert result.candidate_id is not None
        assert result.judgment.status == SelectionStatus.SELECTED
        assert result.curriculum_id is not None
        assert result.experiment_id is not None
        assert result.eval_result.verdict == "STRUCTURAL_ONLY"
        assert result.eval_result.real_model_evaluated is False
        assert result.eval_result.all_structural_gates_passed is True
        assert result.eval_result.all_critical_gates_passed is False
        assert result.recommendation == PromotionRecommendation.DRY_RUN_VALIDATED
        assert result.why_changed_ref is not None

        # Assert AFTER processing: counts remain exactly 1, no duplicate correction or signal created
        corrections_after = (await db.execute(select(UserCorrection).where(UserCorrection.owner_user_id == owner_user_id))).scalars().all()
        signals_after = (await db.execute(select(LearningSignalRecord).where(LearningSignalRecord.owner_user_id == owner_user_id))).scalars().all()
        candidates_after = (await db.execute(select(LearningCandidateRecord).where(LearningCandidateRecord.owner_user_id == owner_user_id))).scalars().all()
        curricula_after = (await db.execute(select(CurriculumSnapshotRecord).where(CurriculumSnapshotRecord.owner_user_id == owner_user_id))).scalars().all()
        experiments_after = (await db.execute(select(TrainingExperimentRecord).where(TrainingExperimentRecord.owner_user_id == owner_user_id))).scalars().all()
        proposals_after = (await db.execute(select(LearningPromotionProposalRecord).where(LearningPromotionProposalRecord.owner_user_id == owner_user_id))).scalars().all()

        assert len(corrections_after) == 1, "Processing must not create a duplicate UserCorrection"
        assert len(signals_after) == 1, "Processing must not create a duplicate LearningSignal"
        assert len(candidates_after) == 1
        assert len(curricula_after) == 1
        assert len(experiments_after) == 1
        assert len(proposals_after) == 1

        assert signals_after[0].id == canonical_signal.id
        assert signals_after[0].signal_kind == "OWNER_CORRECTION"
        assert candidates_after[0].recurrence_count == 1
        assert experiments_after[0].status == "COMPLETED"
        assert experiments_after[0].trainer_type == "DRY_RUN"
        assert proposals_after[0].recommendation == "DRY_RUN_VALIDATED"
        assert proposals_after[0].critical_gates_passed is False
        assert proposals_after[0].uncertainty_score == 10000
        assert proposals_after[0].why_changed_ref.startswith("why_changed:")


async def test_owner_correction_convenience_wrapper_and_deduplication(client, app_engine):
    """Test the run_owner_correction_hardness_slice convenience wrapper and candidate deduplication."""
    res, _, _ = await register_user(client)
    owner_user_id = uuid.UUID(res.json()["id"])

    session_maker = async_sessionmaker(app_engine, expire_on_commit=False, class_=AsyncSession)

    async with session_maker() as db:
        await db.execute(text(SET_USER), {"uid": str(owner_user_id)})

        corr_text = "The server port should be 8080."
        corr_reason = "Default configuration change."

        # 1. Run slice with wrapper
        result1 = await run_owner_correction_hardness_slice(
            db,
            owner_user_id=owner_user_id,
            correction_text=corr_text,
            reason=corr_reason,
            base_checkpoint_id="base_model_v1",
            capability_id="infrastructure_reasoning",
            task_class="port_config",
            intervention=LearningIntervention.SFT,
        )

        assert result1.signal_id is not None
        assert result1.candidate_id is not None
        assert result1.judgment.status == SelectionStatus.SELECTED

        # 2. Repeated correction with identical text deduplicates candidate and increments recurrence
        result2 = await run_owner_correction_hardness_slice(
            db,
            owner_user_id=owner_user_id,
            correction_text=corr_text,
            reason=corr_reason,
            base_checkpoint_id="base_model_v1",
            capability_id="infrastructure_reasoning",
            task_class="port_config",
            intervention=LearningIntervention.SFT,
        )

        assert result2.candidate_id == result1.candidate_id
        assert result2.candidate_fingerprint == result1.candidate_fingerprint

        cand_row = (await db.execute(select(LearningCandidateRecord).where(LearningCandidateRecord.id == result1.candidate_id))).scalar_one()
        assert cand_row.recurrence_count == 2
        assert cand_row.status == "SELECTED"


async def test_owner_correction_default_no_change_pipeline(client, app_engine):
    """Verify default intervention is NO_CHANGE: curriculum snapshot is created, but zero experiments/artifacts/proposals."""
    res, _, _ = await register_user(client)
    owner_user_id = uuid.UUID(res.json()["id"])

    session_maker = async_sessionmaker(app_engine, expire_on_commit=False, class_=AsyncSession)

    async with session_maker() as db:
        await db.execute(text(SET_USER), {"uid": str(owner_user_id)})

        # 1. Default wrapper call (defaults to NO_CHANGE)
        result_default = await run_owner_correction_hardness_slice(
            db,
            owner_user_id=owner_user_id,
            correction_text="Different correction for no-change default test",
            reason="testing default NO_CHANGE intervention",
            base_checkpoint_id="base_model_v1",
            capability_id="general_cognition",
            task_class="guidance",
        )

        assert result_default.curriculum_id is not None
        assert result_default.dataset_hash is not None
        assert result_default.experiment_id is None, "Default NO_CHANGE intervention must not create training experiment"
        assert result_default.artifact is None
        assert result_default.eval_result is None
        assert result_default.proposal_id is None
        assert result_default.recommendation is None
        assert result_default.why_changed_ref.startswith("why_changed:")

        # 2. Direct process_learning_signal with NO_CHANGE intervention
        raw_sig = await persist_learning_signal(
            db,
            owner_user_id=owner_user_id,
            signal_kind=LearningSignalKind.OWNER_CORRECTION,
            task_class="no_change_check",
            summary="Direct signal test for NO_CHANGE",
            structured_payload={"failure_signature": "sig_nc", "desired_behavior": "desired_nc"},
        )
        res_direct = await process_learning_signal(
            db,
            signal=raw_sig,
            intervention=LearningIntervention.NO_CHANGE,
        )
        assert res_direct.curriculum_id is not None
        assert res_direct.experiment_id is None
        assert res_direct.proposal_id is None
        assert res_direct.recommendation is None


async def test_signal_ingest_retry_idempotency(client, app_engine):
    """Verify that retrying ingestion of the exact same signal object does not increment recurrence."""
    res, _, _ = await register_user(client)
    owner_user_id = uuid.UUID(res.json()["id"])

    session_maker = async_sessionmaker(app_engine, expire_on_commit=False, class_=AsyncSession)

    async with session_maker() as db:
        await db.execute(text(SET_USER), {"uid": str(owner_user_id)})

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
