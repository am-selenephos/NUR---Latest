import uuid

from app.insights.contracts import EvidenceCandidate, InsightDraft
from app.insights.quality import evidence_digest, evaluate_quality


def _draft(*, domains: tuple[str, ...], alternatives: tuple[str, ...]) -> InsightDraft:
    support = tuple(
        EvidenceCandidate(
            source_kind="COGNITIVE_EVENT",
            source_id=uuid.uuid4(),
            source_domain=domain,
            relation="SUPPORTS",
            provenance_label="OWNER_LEDGER",
            explicitness="SYSTEM_OBSERVED",
            confidence=0.9,
        )
        for domain in domains
    )
    counter = (
        EvidenceCandidate(
            source_kind="COGNITIVE_EVENT",
            source_id=uuid.uuid4(),
            source_domain="LIVING",
            relation="CONTRADICTS",
            provenance_label="OWNER_LEDGER",
            explicitness="SYSTEM_OBSERVED",
            confidence=0.8,
        ),
    )
    return InsightDraft(
        insight_type="EXECUTION_PATTERN",
        title="Returned evidence spans more than one life domain",
        claim="Completed small actions co-occur with returned outcomes across domains.",
        epistemic_state="INFERRED",
        time_scale="LONGITUDINAL",
        source_domains=domains,
        supporting_evidence=support,
        counter_evidence=counter,
        assumptions=("The recorded action statuses reflect the owner's intended meaning.",),
        alternative_explanations=alternatives,
        uncertainty="The records show co-occurrence, not causation.",
        positive_interpretation="The owner repeatedly returns evidence.",
        hard_interpretation="The pattern is not universal and misses remain visible.",
        suggested_action="Keep the next action small enough to return evidence.",
    )


def test_quality_gate_requires_cross_domain_counter_evidence_and_alternative():
    single_domain = _draft(domains=("LIVING",), alternatives=("External constraints may explain the result.",))
    verdict = evaluate_quality(single_domain)
    assert verdict.passes is False
    assert "SOURCE_DIVERSITY" in verdict.reason_codes

    no_alternative = _draft(domains=("LIVING", "PROJECTS"), alternatives=())
    verdict = evaluate_quality(no_alternative)
    assert verdict.passes is False
    assert "ALTERNATIVE_EXPLANATION" in verdict.reason_codes

    complete = _draft(
        domains=("LIVING", "PROJECTS"),
        alternatives=("The same external support may have enabled both outcomes.",),
    )
    verdict = evaluate_quality(complete)
    assert verdict.passes is True
    assert verdict.source_diversity == 2
    assert verdict.support_score > verdict.counter_score
    assert verdict.quality_score >= 7000


def test_evidence_digest_is_order_independent_and_materially_changes():
    draft = _draft(
        domains=("LIVING", "PROJECTS"),
        alternatives=("The same external support may have enabled both outcomes.",),
    )
    first = evidence_digest((*draft.supporting_evidence, *draft.counter_evidence))
    second = evidence_digest(tuple(reversed((*draft.supporting_evidence, *draft.counter_evidence))))
    assert first == second

    changed = evidence_digest(
        (*draft.supporting_evidence, *draft.counter_evidence,
         EvidenceCandidate(
             source_kind="COGNITIVE_EVENT",
             source_id=uuid.uuid4(),
             source_domain="JOURNAL",
             relation="QUALIFIES",
             provenance_label="OWNER_WRITTEN",
             explicitness="OWNER_EXPLICIT",
             confidence=1.0,
         ))
    )
    assert changed != first
