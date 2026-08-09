"""Pure contracts for the deterministic Agentic Insights quality boundary."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvidenceCandidate:
    source_kind: str
    source_id: uuid.UUID
    source_domain: str
    relation: str
    provenance_label: str
    explicitness: str
    confidence: float
    observation_id: uuid.UUID | None = None
    source_event_id: uuid.UUID | None = None
    source_domain_event_id: uuid.UUID | None = None
    source_insight_id: uuid.UUID | None = None
    source_feedback_id: uuid.UUID | None = None
    source_fingerprint: str | None = None
    evidence_summary: str | None = None
    occurred_at_iso: str | None = None


@dataclass(frozen=True, slots=True)
class InsightDraft:
    insight_type: str
    title: str
    claim: str
    epistemic_state: str
    time_scale: str
    source_domains: tuple[str, ...]
    supporting_evidence: tuple[EvidenceCandidate, ...]
    counter_evidence: tuple[EvidenceCandidate, ...]
    assumptions: tuple[str, ...]
    alternative_explanations: tuple[str, ...]
    uncertainty: str
    positive_interpretation: str
    hard_interpretation: str
    suggested_action: str
    affected_system_slug: str | None = None
    affected_goal_id: uuid.UUID | None = None
    affected_project_id: uuid.UUID | None = None
    affected_person_id: uuid.UUID | None = None
    orbit_id: uuid.UUID | None = None
    calibration_target: str | None = None
    window_start_iso: str | None = None
    window_end_iso: str | None = None


@dataclass(frozen=True, slots=True)
class QualityVerdict:
    passes: bool
    reason_codes: tuple[str, ...]
    source_diversity: int
    support_score: int
    counter_score: int
    quality_score: int
