from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field


class OmegaStatusLabels(BaseModel):
    experience_ledger: str = "IMPLEMENTED"
    evidence_graph: str = "IMPLEMENTED"
    contradiction_engine: str = "IMPLEMENTED"
    prediction_resolution: str = "IMPLEMENTED"
    consolidation: str = "IMPLEMENTED"
    learning_proposals: str = "IMPLEMENTED"
    sentience_status: str = "UNRESOLVED_SENTIENCE_STATUS"


class OmegaExperienceIn(BaseModel):
    source_kind: str = "MANUAL"
    source_id: uuid.UUID | None = None
    orbit_id: uuid.UUID | None = None
    event_kind: str
    scope: str = "PRIVATE_ORBIT"
    language_tag: str = "und"
    summary: str = Field(min_length=1, max_length=4000)
    raw_ref: dict | None = None
    provenance_label: str = "OWNER_WRITTEN"
    sensitivity: str | None = None
    confidence: float = 1.0
    source_domain: str = "UNKNOWN"
    features: dict = Field(default_factory=dict)
    explicitness: str = "SYSTEM_OBSERVED"
    retention_policy: str = "SOURCE_BOUND"
    observed_at: dt.datetime | None = None
    source_fingerprint: str | None = None


class OmegaExperienceOut(BaseModel):
    id: uuid.UUID
    source_kind: str
    source_id: uuid.UUID | None
    orbit_id: uuid.UUID | None
    event_kind: str
    scope: str
    language_tag: str
    summary: str
    raw_ref: dict | None
    provenance_label: str
    sensitivity: str
    confidence: float
    source_domain: str
    features: dict
    explicitness: str
    retention_policy: str
    observed_at: dt.datetime
    invalidated_at: dt.datetime | None
    source_fingerprint: str | None
    created_at: dt.datetime
    model_config = {"from_attributes": True}


class OmegaClaimIn(BaseModel):
    claim_text: str = Field(min_length=1, max_length=2000)
    claim_type: str = "UNKNOWN"
    truth_status: str = "HYPOTHESIS"
    provenance_label: str = "MODEL_GENERATED"
    orbit_id: uuid.UUID | None = None
    confidence: float = 0.5
    evidence_id: uuid.UUID | None = None
    evidence_kind: str = "EXPERIENCE"


class OmegaClaimOut(BaseModel):
    id: uuid.UUID
    orbit_id: uuid.UUID | None
    claim_text: str
    claim_type: str
    truth_status: str
    confidence: float
    support_count: int
    contradiction_count: int
    last_supported_at: dt.datetime | None
    last_contradicted_at: dt.datetime | None
    created_at: dt.datetime
    updated_at: dt.datetime
    model_config = {"from_attributes": True}


class OmegaEvidenceOut(BaseModel):
    id: uuid.UUID
    claim_id: uuid.UUID
    evidence_kind: str
    evidence_id: uuid.UUID
    relation: str
    strength: float
    note: str | None
    created_at: dt.datetime
    model_config = {"from_attributes": True}


class OmegaClaimCandidate(BaseModel):
    claim_text: str
    claim_type: str = "UNKNOWN"
    truth_status: str = "HYPOTHESIS"
    confidence: float = 0.5
    sensitivity: str = "PRIVATE"
    requires_owner_confirmation: bool = False
    confirmation_reason: str | None = None
    source_experience_id: uuid.UUID | None = None
    provenance_label: str = "MODEL_GENERATED"


class OmegaReviewQueueOut(BaseModel):
    id: uuid.UUID
    orbit_id: uuid.UUID | None
    experience_id: uuid.UUID | None
    candidate_claim_text: str
    candidate_claim_type: str
    candidate_truth_status: str
    sensitivity: str
    reason: str
    model_candidate: dict
    status: str
    created_claim_id: uuid.UUID | None
    reviewed_at: dt.datetime | None
    created_at: dt.datetime
    updated_at: dt.datetime
    model_config = {"from_attributes": True}


class OmegaReviewEditIn(BaseModel):
    candidate_claim_text: str = Field(min_length=1, max_length=2000)
    candidate_claim_type: str = "UNKNOWN"


class OmegaWhyChanged(BaseModel):
    claim_id: uuid.UUID
    claim_text: str
    current_truth_status: str
    current_confidence: float
    changed_because: list[str] = Field(default_factory=list)
    supporting_edges: list[str] = Field(default_factory=list)
    contradicting_edges: list[str] = Field(default_factory=list)
    unresolved_note: str | None = None


class OmegaExport(BaseModel):
    exported_at: dt.datetime
    owner_user_id: uuid.UUID
    safety: dict
    counts: dict
    claims: list[OmegaClaimOut]
    contradictions: list[OmegaContradictionOut]
    predictions: list[OmegaPredictionOut]
    consolidation_runs: list[OmegaConsolidationOut]
    learning_proposals: list[OmegaLearningProposalOut]
    review_queue: list[OmegaReviewQueueOut]


class OmegaContradictionOut(BaseModel):
    id: uuid.UUID
    orbit_id: uuid.UUID | None
    claim_a_id: uuid.UUID
    claim_b_id: uuid.UUID
    status: str
    severity: str
    description: str
    proposed_resolution: str | None
    resolved_by_event_id: uuid.UUID | None
    created_at: dt.datetime
    updated_at: dt.datetime
    model_config = {"from_attributes": True}


class OmegaPredictionIn(BaseModel):
    prediction_text: str = Field(min_length=1, max_length=2000)
    expected_observation: str = Field(min_length=1, max_length=1000)
    orbit_id: uuid.UUID | None = None
    model_run_id: uuid.UUID | None = None
    claim_id: uuid.UUID | None = None
    plan_step_id: uuid.UUID | None = None
    metric: str | None = None
    time_window: str | None = None
    confidence: float = 0.5


class OmegaPredictionOut(BaseModel):
    id: uuid.UUID
    orbit_id: uuid.UUID | None
    prediction_text: str
    expected_observation: str
    metric: str | None
    time_window: str | None
    confidence: float
    status: str
    outcome_id: uuid.UUID | None
    prediction_error: float | None
    created_at: dt.datetime
    resolved_at: dt.datetime | None
    model_config = {"from_attributes": True}


class OmegaLearningProposalIn(BaseModel):
    proposal_kind: str
    description: str = Field(min_length=1, max_length=2000)
    evidence_summary: str = Field(min_length=1, max_length=2000)
    supporting_evaluation_ids: list[uuid.UUID] = Field(default_factory=list)


class OmegaLearningProposalOut(BaseModel):
    id: uuid.UUID
    proposal_kind: str
    description: str
    evidence_summary: str
    supporting_evaluation_ids: list[uuid.UUID]
    risk_level: str
    status: str
    approved_by_owner: bool
    created_at: dt.datetime
    updated_at: dt.datetime
    model_config = {"from_attributes": True}


class OmegaConsolidationOut(BaseModel):
    id: uuid.UUID
    run_kind: str
    orbit_id: uuid.UUID | None
    input_counts: dict
    created_claims: int
    updated_claims: int
    contradictions_found: int
    predictions_resolved: int
    proposals_created: int
    status: str
    completed_at: dt.datetime | None
    error_class: str | None
    created_at: dt.datetime
    model_config = {"from_attributes": True}


class OmegaWorkspaceFrameOut(BaseModel):
    id: uuid.UUID
    orbit_id: uuid.UUID | None
    task_mode: str
    active_question: str
    attention_items: dict
    retrieved_claim_ids: list[uuid.UUID]
    retrieved_experience_ids: list[uuid.UUID]
    active_contradiction_ids: list[uuid.UUID]
    risk_flags: list[str]
    scope_statement: str
    status: str
    created_at: dt.datetime
    model_config = {"from_attributes": True}


class OmegaTalkSummary(BaseModel):
    enabled: bool = True
    workspace_frame_id: uuid.UUID | None = None
    what_changed: list[str] = Field(default_factory=list)
    open_contradictions: list[str] = Field(default_factory=list)
    unresolved_predictions: list[str] = Field(default_factory=list)
    memory_note: str = "I can hold this as a hypothesis, not a fact."


class OmegaDashboard(BaseModel):
    statuses: OmegaStatusLabels = Field(default_factory=OmegaStatusLabels)
    claims: list[OmegaClaimOut]
    contradictions: list[OmegaContradictionOut]
    predictions: list[OmegaPredictionOut]
    consolidation_runs: list[OmegaConsolidationOut]
    learning_proposals: list[OmegaLearningProposalOut]
    recent_experiences: list[OmegaExperienceOut]
    review_queue: list[OmegaReviewQueueOut] = Field(default_factory=list)
