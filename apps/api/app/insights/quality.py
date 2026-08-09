"""Versioned deterministic Insight quality and material-change policy."""

from __future__ import annotations

import hashlib
import json

from app.insights.contracts import EvidenceCandidate, InsightDraft, QualityVerdict

QUALITY_POLICY_VERSION = "agentic-insights-quality-v1"


def evidence_digest(evidence: tuple[EvidenceCandidate, ...]) -> str:
    canonical = sorted(
        (
            row.source_kind,
            str(row.source_id),
            row.source_domain,
            row.relation,
            row.provenance_label,
            row.explicitness,
            round(float(row.confidence), 6),
            row.source_fingerprint or "",
        )
        for row in evidence
    )
    payload = json.dumps(canonical, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def evaluate_quality(draft: InsightDraft) -> QualityVerdict:
    support = draft.supporting_evidence
    counter = draft.counter_evidence
    source_domains = {
        domain.strip().upper() for domain in draft.source_domains if domain.strip()
    }
    reason_codes: list[str] = []
    if len(source_domains) < 2:
        reason_codes.append("SOURCE_DIVERSITY")
    if len(support) < 2:
        reason_codes.append("SUPPORTING_EVIDENCE")
    if not counter:
        reason_codes.append("COUNTER_EVIDENCE")
    if not draft.alternative_explanations:
        reason_codes.append("ALTERNATIVE_EXPLANATION")
    if not draft.uncertainty.strip():
        reason_codes.append("UNCERTAINTY")
    if draft.epistemic_state not in {
        "OBSERVED", "INFERRED", "HYPOTHESIS", "UNCERTAIN",
        "NEEDS_OWNER_CONFIRMATION",
    }:
        reason_codes.append("EPISTEMIC_STATE")

    support_score = _mean_confidence(support)
    counter_score = _mean_confidence(counter)
    components = (
        min(10_000, len(source_domains) * 4_000),
        min(10_000, len(support) * 3_000),
        10_000 if counter else 0,
        10_000 if draft.alternative_explanations else 0,
        10_000 if draft.uncertainty.strip() else 0,
        10_000 if draft.epistemic_state in {
            "OBSERVED", "INFERRED", "HYPOTHESIS", "UNCERTAIN",
            "NEEDS_OWNER_CONFIRMATION",
        } else 0,
    )
    quality_score = round(sum(components) / len(components))
    return QualityVerdict(
        passes=not reason_codes and quality_score >= 7_000,
        reason_codes=tuple(reason_codes),
        source_diversity=len(source_domains),
        support_score=support_score,
        counter_score=counter_score,
        quality_score=quality_score,
    )


def _mean_confidence(evidence: tuple[EvidenceCandidate, ...]) -> int:
    if not evidence:
        return 0
    bounded = [max(0.0, min(1.0, float(row.confidence))) for row in evidence]
    return round(sum(bounded) / len(bounded) * 10_000)
