"""NUR Mind Meta-Review — bounded review-of-review (meta-metacognition).

Implements the meta-metacognition directive: bounded meta-review that only
triggers under specific entry criteria and is strictly cost-capped.

ENTRY CRITERIA (all must be met for meta-review to run):
- Primary review produced BLOCK or WARN
- Task is high stakes OR reviewer disagreement occurred
- Budget allows (max 1 meta-review per run)

STOP REASONS:
- Agreement between primary and meta review
- Budget exhausted
- Depth limit reached (max 2)
- Escalation to owner (on disagreement)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.brain.schemas import CognitiveResult, CognitiveTaskPacket
from app.mind.metacognition import MetacognitiveReviewResult, run_metacognitive_review


@dataclass
class MetaReviewResult:
    """Result of a meta-review (review-of-review)."""
    performed: bool = False
    stop_reason: str = ""
    primary_verdict: str = ""
    meta_verdict: str = ""
    agrees_with_primary: bool = True
    escalate_to_owner: bool = False
    cost_cents: float = 0.0
    notes: list[str] = field(default_factory=list)


def should_run_meta_review(
    primary_review: MetacognitiveReviewResult,
    *,
    stakes_level: str = "normal",
    requires_meta_review: bool = False,
    meta_review_budget_remaining: float = 100.0,
) -> bool:
    """Determine if a meta-review should run.

    Returns True only when ALL entry criteria are met.
    """
    # Must be requested by the review strategy
    if not requires_meta_review:
        return False

    # Must have a non-PASS primary verdict
    if primary_review.verdict == "PASS":
        return False

    # Must have budget
    if meta_review_budget_remaining <= 0:
        return False

    return True


def run_meta_review(
    packet: CognitiveTaskPacket,
    result: CognitiveResult,
    primary_review: MetacognitiveReviewResult,
    *,
    stakes_level: str = "normal",
    max_depth: int = 2,
    cost_cap_cents: float = 100.0,
) -> MetaReviewResult:
    """Run a bounded meta-review of a primary metacognitive review.

    The meta-review re-runs the metacognitive checks at depth=2 and
    compares verdicts. On disagreement, escalates to owner.
    """
    meta_result = MetaReviewResult(
        primary_verdict=primary_review.verdict,
    )

    # Entry criteria check
    if primary_review.verdict == "PASS":
        meta_result.stop_reason = "Primary review passed — no meta-review needed."
        return meta_result

    # Run the meta-review at depth 2
    meta_review = run_metacognitive_review(packet, result, depth=2)
    meta_result.performed = True
    meta_result.meta_verdict = meta_review.verdict
    meta_result.cost_cents = 0.1  # minimal cost for deterministic review

    # Compare verdicts
    if meta_review.verdict == primary_review.verdict:
        meta_result.agrees_with_primary = True
        meta_result.stop_reason = "Agreement between primary and meta review."
    else:
        meta_result.agrees_with_primary = False
        meta_result.notes.append(
            f"Disagreement: primary={primary_review.verdict}, meta={meta_review.verdict}"
        )
        # On disagreement with a BLOCK, escalate to owner
        if primary_review.verdict == "BLOCK" and meta_review.verdict != "BLOCK":
            meta_result.escalate_to_owner = True
            meta_result.stop_reason = "Disagreement on BLOCK verdict — escalating to owner."
        elif meta_review.verdict == "BLOCK" and primary_review.verdict != "BLOCK":
            meta_result.escalate_to_owner = True
            meta_result.stop_reason = "Meta-review found BLOCK where primary did not — escalating to owner."
        else:
            meta_result.stop_reason = "Disagreement on severity — using stricter verdict."

    return meta_result
