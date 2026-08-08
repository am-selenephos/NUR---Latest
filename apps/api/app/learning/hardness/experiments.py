"""Experiment planning and lifecycle management for Hardness plane."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.learning.hardness.schemas import (
    CandidateArtifact,
    ExperimentStatus,
    TrainerType,
)
from app.models.hardness import CurriculumSnapshotRecord, TrainingExperimentRecord


async def create_training_experiment(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    base_checkpoint_id: str,
    curriculum: CurriculumSnapshotRecord,
    hypothesis: str,
    success_metrics: dict[str, Any] | None = None,
    critical_regression_gates: list[str] | None = None,
    max_cost_cents: int = 0,
    trainer_type: TrainerType = TrainerType.DRY_RUN,
) -> TrainingExperimentRecord:
    """Create and persist a new falsifiable training experiment hypothesis."""
    default_metrics = {
        "primary_metric": "target_capability_accuracy",
        "target_min_improvement_pct": 5.0,
        "max_regression_pct": 1.0,
    }
    default_gates = [
        "gate_owner_privacy",
        "gate_scope_isolation",
        "gate_agency_boundaries",
        "gate_confidence_calibration",
    ]

    record = TrainingExperimentRecord(
        owner_user_id=owner_user_id,
        base_checkpoint_id=base_checkpoint_id,
        curriculum_id=curriculum.id,
        curriculum_hash=curriculum.dataset_hash,
        intervention=curriculum.intervention,
        target_capabilities=curriculum.target_capabilities,
        hypothesis=hypothesis,
        success_metrics=success_metrics or default_metrics,
        critical_regression_gates=critical_regression_gates or default_gates,
        max_cost_cents=max_cost_cents,
        trainer_type=trainer_type.value,
        status=ExperimentStatus.CREATED.value,
    )
    db.add(record)
    await db.flush()
    return record


async def complete_experiment_with_artifact(
    db: AsyncSession,
    *,
    experiment_id: uuid.UUID,
    artifact: CandidateArtifact,
) -> TrainingExperimentRecord | None:
    """Mark an experiment as completed with candidate artifact metadata."""
    stmt = select(TrainingExperimentRecord).where(TrainingExperimentRecord.id == experiment_id)
    res = await db.execute(stmt)
    exp = res.scalars().first()
    if not exp:
        return None

    exp.status = ExperimentStatus.COMPLETED.value
    exp.candidate_artifact_hash = artifact.artifact_hash
    exp.candidate_metadata = {
        "candidate_checkpoint_id": artifact.candidate_checkpoint_id,
        "spend_cents": artifact.spend_cents,
        "metrics_summary": artifact.metrics_summary,
        "trainer_type": artifact.trainer_type.value,
    }
    await db.flush()
    return exp
