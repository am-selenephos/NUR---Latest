"""Pydantic schemas and enums for NUR Hardness / Self-Directed Learning Plane V1."""
from __future__ import annotations

import datetime as dt
from enum import Enum
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LearningSignalKind(str, Enum):
    OWNER_CORRECTION = "OWNER_CORRECTION"
    VERIFIED_FAILURE = "VERIFIED_FAILURE"
    TOOL_FAILURE = "TOOL_FAILURE"
    OUTCOME_MISS = "OUTCOME_MISS"
    CRITIC_DISAGREEMENT = "CRITIC_DISAGREEMENT"
    CALIBRATION_ERROR = "CALIBRATION_ERROR"
    CONTRADICTION = "CONTRADICTION"
    CAPABILITY_GAP = "CAPABILITY_GAP"
    SUCCESSFUL_NOVEL_SOLUTION = "SUCCESSFUL_NOVEL_SOLUTION"


class LearningIntervention(str, Enum):
    NO_CHANGE = "NO_CHANGE"
    MEMORY_UPDATE = "MEMORY_UPDATE"
    RETRIEVAL_POLICY = "RETRIEVAL_POLICY"
    ROUTER_POLICY = "ROUTER_POLICY"
    CONTEXT_RECIPE = "CONTEXT_RECIPE"
    PROMPT_EXPERIMENT = "PROMPT_EXPERIMENT"
    SYNTHETIC_DATA = "SYNTHETIC_DATA"
    SFT = "SFT"
    PREFERENCE_TRAINING = "PREFERENCE_TRAINING"
    RL = "RL"
    CODE_CHANGE_PROPOSAL = "CODE_CHANGE_PROPOSAL"


class LearningScope(str, Enum):
    OWNER_LOCAL = "OWNER_LOCAL"
    PRIVATE_MODEL = "PRIVATE_MODEL"
    GLOBAL_PRODUCT = "GLOBAL_PRODUCT"


class SelectionStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    SELECTED = "SELECTED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"


class RiskAssessmentStatus(str, Enum):
    UNASSESSED = "UNASSESSED"
    ASSESSED = "ASSESSED"


class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_RUN = "NOT_RUN"


class TournamentVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    STRUCTURAL_ONLY = "STRUCTURAL_ONLY"


class HardnessSliceStatus(str, Enum):
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"
    SELECTED = "SELECTED"
    DRY_RUN_VALIDATED = "DRY_RUN_VALIDATED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class TrainerType(str, Enum):
    DRY_RUN = "DRY_RUN"


class PromotionRecommendation(str, Enum):
    PROMOTION_CANDIDATE = "PROMOTION_CANDIDATE"
    REJECTED = "REJECTED"
    DRY_RUN_VALIDATED = "DRY_RUN_VALIDATED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class ExperimentStatus(str, Enum):
    CREATED = "CREATED"
    TRAINING = "TRAINING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


# ── Bounded Basis-Point Helper ──

def _validate_basis_points(v: int) -> int:
    if not (0 <= v <= 10000):
        raise ValueError(f"Basis points score must be between 0 and 10000 inclusive, got {v}")
    return v


# ── Schemas ──

class LearningSignalCreate(BaseModel):
    owner_user_id: uuid.UUID
    orbit_id: uuid.UUID | None = None
    source_event_id: uuid.UUID | None = None
    source_correction_id: uuid.UUID | None = None
    idempotency_key: str | None = None
    signal_kind: LearningSignalKind
    capability_id: str | None = None
    task_class: str
    summary: str
    structured_payload: dict[str, Any] = Field(default_factory=dict)


class LearningSignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_user_id: uuid.UUID
    orbit_id: uuid.UUID | None = None
    source_event_id: uuid.UUID | None = None
    source_correction_id: uuid.UUID | None = None
    idempotency_key: str | None = None
    signal_kind: LearningSignalKind
    capability_id: str | None = None
    task_class: str
    summary: str
    structured_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: dt.datetime


class LearningCandidateScores(BaseModel):
    novelty_score: int = Field(default=0, ge=0, le=10000)
    recurrence_score: int = Field(default=0, ge=0, le=10000)
    impact_score: int = Field(default=0, ge=0, le=10000)
    uncertainty_score: int = Field(default=0, ge=0, le=10000)
    counterexample_value: int = Field(default=0, ge=0, le=10000)
    transferability_score: int = Field(default=0, ge=0, le=10000)
    recency_score: int = Field(default=0, ge=0, le=10000)
    poisoning_risk: int = Field(default=0, ge=0, le=10000)
    privacy_risk: int = Field(default=0, ge=0, le=10000)
    contamination_risk: int = Field(default=0, ge=0, le=10000)


class LearningCandidateCreate(BaseModel):
    owner_user_id: uuid.UUID
    fingerprint: str
    signal_kind: LearningSignalKind
    capability_id: str | None = None
    task_class: str
    failure_signature: str | None = None
    desired_behavior: str | None = None
    scores: LearningCandidateScores = Field(default_factory=LearningCandidateScores)
    learning_scope: LearningScope = LearningScope.OWNER_LOCAL
    risk_status: RiskAssessmentStatus = RiskAssessmentStatus.UNASSESSED
    source_refs: list[str] = Field(default_factory=list)


class LearningCandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_user_id: uuid.UUID
    fingerprint: str
    signal_kind: LearningSignalKind
    capability_id: str | None = None
    task_class: str
    failure_signature: str | None = None
    desired_behavior: str | None = None

    novelty_score: int
    recurrence_score: int
    impact_score: int
    uncertainty_score: int
    counterexample_value: int
    transferability_score: int
    recency_score: int
    poisoning_risk: int
    privacy_risk: int
    contamination_risk: int

    learning_scope: LearningScope
    status: SelectionStatus
    risk_status: RiskAssessmentStatus = RiskAssessmentStatus.UNASSESSED
    selection_score: int | None = None
    learning_value: int | None = None
    risk_penalty: int | None = None
    redundancy_penalty: int | None = None
    selection_policy_version: str | None = None
    selection_rationale: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    recurrence_count: int
    last_seen_at: dt.datetime
    created_at: dt.datetime
    updated_at: dt.datetime


class SyntheticEvaluationFixture(BaseModel):
    target_delta: float = 0.10
    regression_delta: float = 0.005
    privacy_passed: bool = True
    scope_passed: bool = True
    agency_passed: bool = True
    calibration_passed: bool = True


class SelectorJudgment(BaseModel):
    candidate_id: uuid.UUID
    fingerprint: str
    status: SelectionStatus
    selection_score: int
    learning_value: int
    risk_penalty: int
    redundancy_penalty: int
    policy_version: str
    rationale: str
    reason_codes: list[str]
    hard_gates_passed: bool


class CurriculumSnapshotCreate(BaseModel):
    owner_user_id: uuid.UUID
    selector_policy_version: str
    target_capabilities: list[str]
    intervention: LearningIntervention
    dataset_hash: str
    dataset_manifest: dict[str, Any]
    ordered_candidate_ids: list[str]
    train_ids: list[str]
    validation_ids: list[str]
    heldout_ids: list[str]
    privacy_manifest_hash: str
    provenance_manifest_hash: str

    @field_validator("train_ids", "validation_ids", "heldout_ids")
    @classmethod
    def validate_disjoint(cls, v: list[str], info) -> list[str]:
        # Disjointness is validated comprehensively in CurriculumBuilder
        return v


class CurriculumSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_user_id: uuid.UUID
    selector_policy_version: str
    target_capabilities: list[str]
    intervention: LearningIntervention
    dataset_hash: str
    dataset_manifest: dict[str, Any]
    ordered_candidate_ids: list[str]
    train_ids: list[str]
    validation_ids: list[str]
    heldout_ids: list[str]
    privacy_manifest_hash: str
    provenance_manifest_hash: str
    created_at: dt.datetime


class TrainingExperimentCreate(BaseModel):
    owner_user_id: uuid.UUID
    base_checkpoint_id: str
    curriculum_id: uuid.UUID
    curriculum_hash: str
    intervention: LearningIntervention
    target_capabilities: list[str]
    hypothesis: str
    success_metrics: dict[str, Any]
    critical_regression_gates: list[str]
    max_cost_cents: int = 0
    trainer_type: TrainerType = TrainerType.DRY_RUN


class TrainingExperimentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_user_id: uuid.UUID
    base_checkpoint_id: str
    curriculum_id: uuid.UUID
    curriculum_hash: str
    intervention: LearningIntervention
    target_capabilities: list[str]
    hypothesis: str
    success_metrics: dict[str, Any]
    critical_regression_gates: list[str]
    max_cost_cents: int
    trainer_type: TrainerType
    status: ExperimentStatus
    candidate_artifact_hash: str | None = None
    candidate_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: dt.datetime


class CandidateArtifact(BaseModel):
    candidate_checkpoint_id: str
    base_checkpoint_id: str
    experiment_id: uuid.UUID
    curriculum_hash: str
    trainer_type: TrainerType
    artifact_hash: str
    metrics_summary: dict[str, Any] = Field(default_factory=dict)
    spend_cents: int = 0
    real_training_performed: bool = False
    external_provider_invoked: bool = False
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))


class CriticalGateResult(BaseModel):
    gate_name: str
    status: GateStatus = GateStatus.NOT_RUN
    passed: bool = False
    details: str


class TournamentEvaluationResult(BaseModel):
    evaluation_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    candidate_checkpoint_id: str
    base_checkpoint_id: str
    experiment_id: uuid.UUID
    target_metric_base: float = 0.0
    target_metric_candidate: float = 0.0
    target_metric_delta: float = 0.0
    general_regression_delta: float = 0.0
    privacy_passed: bool = False
    scope_isolation_passed: bool = False
    agency_approval_passed: bool = False
    calibration_passed: bool = False
    critical_gates: list[CriticalGateResult] = Field(default_factory=list)
    all_structural_gates_passed: bool = False
    all_critical_gates_passed: bool = False
    evaluation_mode: str = "DRY_RUN_SYNTHETIC"
    real_model_evaluated: bool = False
    verdict: str  # PASS / FAIL / STRUCTURAL_ONLY
    reason_codes: list[str] = Field(default_factory=list)
    evaluated_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))


class PromotionProposalCreate(BaseModel):
    owner_user_id: uuid.UUID
    experiment_id: uuid.UUID
    candidate_checkpoint_id: str
    base_checkpoint_id: str
    target_metric_delta: float = 0.0
    general_regression_delta: float = 0.0
    critical_gates_passed: bool = False
    evaluation_summary: dict[str, Any] = Field(default_factory=dict)
    recommendation: PromotionRecommendation = PromotionRecommendation.REJECTED
    uncertainty_score: int = Field(default=10000, ge=0, le=10000)
    rationale: str
    why_changed_ref: str | None = None


class PromotionProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_user_id: uuid.UUID
    experiment_id: uuid.UUID
    candidate_checkpoint_id: str
    base_checkpoint_id: str
    target_metric_delta: float
    general_regression_delta: float
    critical_gates_passed: bool
    evaluation_summary: dict[str, Any]
    recommendation: PromotionRecommendation
    uncertainty_score: int
    rationale: str
    why_changed_ref: str | None = None
    created_at: dt.datetime
