"""SQLAlchemy models for NUR Hardness / Self-Directed Learning Plane V1.

All tables are owner-isolated with PostgreSQL forced Row Level Security.
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Boolean, Float, ForeignKey, ForeignKeyConstraint, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from app.db.base import Base
from app.models._mixins import now_utc, uuid_pk


def _owner() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )


def _created() -> Mapped[dt.datetime]:
    return mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        default=now_utc,
        nullable=False,
    )


class LearningSignalRecord(Base):
    __tablename__ = "learning_signals"

    id = uuid_pk()
    owner_user_id = _owner()
    orbit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orbits.id", ondelete="SET NULL"),
    )
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cognitive_events.id", ondelete="SET NULL"),
    )
    signal_kind: Mapped[str] = mapped_column(String(48), nullable=False)
    capability_id: Mapped[str | None] = mapped_column(String(64))
    task_class: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(String, nullable=False)
    structured_payload: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
    created_at = _created()


class LearningCandidateRecord(Base):
    __tablename__ = "learning_candidates"

    id = uuid_pk()
    owner_user_id = _owner()
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    signal_kind: Mapped[str] = mapped_column(String(48), nullable=False)
    capability_id: Mapped[str | None] = mapped_column(String(64))
    task_class: Mapped[str] = mapped_column(String(64), nullable=False)
    failure_signature: Mapped[str | None] = mapped_column(String)
    desired_behavior: Mapped[str | None] = mapped_column(String)

    # Score metrics in integer basis points (0 to 10000)
    novelty_score: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    recurrence_score: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    impact_score: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    uncertainty_score: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    counterexample_value: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    transferability_score: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    recency_score: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    poisoning_risk: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    privacy_risk: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    contamination_risk: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)

    learning_scope: Mapped[str] = mapped_column(
        String(32),
        default="OWNER_LOCAL",
        server_default="OWNER_LOCAL",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(24),
        default="CANDIDATE",
        server_default="CANDIDATE",
        nullable=False,
    )
    risk_status: Mapped[str] = mapped_column(
        String(24),
        default="UNASSESSED",
        server_default="UNASSESSED",
        nullable=False,
    )

    selection_score: Mapped[int | None] = mapped_column(Integer)
    learning_value: Mapped[int | None] = mapped_column(Integer)
    risk_penalty: Mapped[int | None] = mapped_column(Integer)
    redundancy_penalty: Mapped[int | None] = mapped_column(Integer)
    selection_policy_version: Mapped[str | None] = mapped_column(String(32))
    selection_rationale: Mapped[str | None] = mapped_column(String)

    reason_codes: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
        nullable=False,
    )
    source_refs: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
        nullable=False,
    )
    recurrence_count: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default=text("1"),
        nullable=False,
    )
    last_seen_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        default=now_utc,
        nullable=False,
    )
    created_at = _created()
    updated_at = _created()


class CurriculumSnapshotRecord(Base):
    __tablename__ = "curriculum_snapshots"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "id", name="uq_curriculum_snapshots_owner_id"),
    )

    id = uuid_pk()
    owner_user_id = _owner()
    selector_policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    target_capabilities: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
        nullable=False,
    )
    intervention: Mapped[str] = mapped_column(String(32), nullable=False)
    dataset_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_manifest: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
    ordered_candidate_ids: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
        nullable=False,
    )
    train_ids: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
        nullable=False,
    )
    validation_ids: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
        nullable=False,
    )
    heldout_ids: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
        nullable=False,
    )
    privacy_manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provenance_manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at = _created()


class TrainingExperimentRecord(Base):
    __tablename__ = "training_experiments"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "id", name="uq_training_experiments_owner_id"),
        ForeignKeyConstraint(
            ["owner_user_id", "curriculum_id"],
            ["curriculum_snapshots.owner_user_id", "curriculum_snapshots.id"],
            name="fk_training_experiments_curriculum_owner",
            ondelete="CASCADE",
        ),
    )

    id = uuid_pk()
    owner_user_id = _owner()
    base_checkpoint_id: Mapped[str] = mapped_column(String(64), nullable=False)
    curriculum_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    curriculum_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    intervention: Mapped[str] = mapped_column(String(32), nullable=False)
    target_capabilities: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
        nullable=False,
    )
    hypothesis: Mapped[str] = mapped_column(String, nullable=False)
    success_metrics: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
    critical_regression_gates: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
        nullable=False,
    )
    max_cost_cents: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    trainer_type: Mapped[str] = mapped_column(
        String(32),
        default="DRY_RUN",
        server_default="DRY_RUN",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(24),
        default="CREATED",
        server_default="CREATED",
        nullable=False,
    )
    candidate_artifact_hash: Mapped[str | None] = mapped_column(String(64))
    candidate_metadata: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
    created_at = _created()


class LearningPromotionProposalRecord(Base):
    __tablename__ = "learning_promotion_proposals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_user_id", "experiment_id"],
            ["training_experiments.owner_user_id", "training_experiments.id"],
            name="fk_promotion_proposals_experiment_owner",
            ondelete="CASCADE",
        ),
    )

    id = uuid_pk()
    owner_user_id = _owner()
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    candidate_checkpoint_id: Mapped[str] = mapped_column(String(64), nullable=False)
    base_checkpoint_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_metric_delta: Mapped[float] = mapped_column(Float, nullable=False)
    general_regression_delta: Mapped[float] = mapped_column(Float, nullable=False)
    critical_gates_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    evaluation_summary: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
    recommendation: Mapped[str] = mapped_column(String(32), nullable=False)
    uncertainty_score: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    rationale: Mapped[str] = mapped_column(String, nullable=False)
    why_changed_ref: Mapped[str | None] = mapped_column(String(128))
    created_at = _created()
