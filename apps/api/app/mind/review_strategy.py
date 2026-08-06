"""NUR Mind Review Strategy — strategy-selected metacognitive reviews.

Implements directive §8.13: the review strategy selector maps
task_class × stakes × evidence_count → review configuration.

Review strategies determine:
- Which checks are critical vs advisory
- Whether a meta-review (review-of-review) is warranted
- Reviewer calibration and known blind spots
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ReviewDepth(StrEnum):
    """How deep the metacognitive review goes."""
    MINIMAL = "minimal"        # fast-path: forbidden claims + scope only
    STANDARD = "standard"      # all 11 checks
    DEEP = "deep"              # all checks + stricter thresholds
    EXHAUSTIVE = "exhaustive"  # all checks + meta-review required


@dataclass(frozen=True)
class ReviewConfiguration:
    """Configuration for a metacognitive review run."""
    depth: ReviewDepth
    critical_checks: frozenset[str]  # checks that cause BLOCK if failed
    advisory_checks: frozenset[str]  # checks that cause WARN if failed
    requires_meta_review: bool = False
    max_meta_review_depth: int = 1
    cost_cap_cents: float = 100.0
    notes: str = ""


# ── Default critical and advisory check sets ──────────────────────────────

_ALWAYS_CRITICAL = frozenset({
    "privacy_scope_preserved",
    "no_forbidden_claims",
    "state_mutation_safety",
    "no_raw_cot",
    "capability_truth",
})

_STANDARD_ADVISORY = frozenset({
    "epistemic_grounding",
    "single_next_move",
    "uncertainty_acknowledged",
    "cost_and_resource_bounded",
    "identity_and_voice_aligned",
    "scope_envelope_enforced",
})


# ── Strategy catalogue ────────────────────────────────────────────────────

MINIMAL_REVIEW = ReviewConfiguration(
    depth=ReviewDepth.MINIMAL,
    critical_checks=frozenset({"no_forbidden_claims", "privacy_scope_preserved"}),
    advisory_checks=frozenset(),
    requires_meta_review=False,
    notes="Fast-path for low-stakes greetings and simple Q&A.",
)

STANDARD_REVIEW = ReviewConfiguration(
    depth=ReviewDepth.STANDARD,
    critical_checks=_ALWAYS_CRITICAL,
    advisory_checks=_STANDARD_ADVISORY,
    requires_meta_review=False,
    notes="Standard review for typical Talk turns.",
)

DEEP_REVIEW = ReviewConfiguration(
    depth=ReviewDepth.DEEP,
    critical_checks=_ALWAYS_CRITICAL | frozenset({"epistemic_grounding"}),
    advisory_checks=_STANDARD_ADVISORY - frozenset({"epistemic_grounding"}),
    requires_meta_review=False,
    cost_cap_cents=200.0,
    notes="Deep review for complex reasoning and challenge tasks.",
)

EXHAUSTIVE_REVIEW = ReviewConfiguration(
    depth=ReviewDepth.EXHAUSTIVE,
    critical_checks=_ALWAYS_CRITICAL | frozenset({"epistemic_grounding", "scope_envelope_enforced"}),
    advisory_checks=_STANDARD_ADVISORY - frozenset({"epistemic_grounding", "scope_envelope_enforced"}),
    requires_meta_review=True,
    max_meta_review_depth=2,
    cost_cap_cents=500.0,
    notes="Exhaustive review for high-stakes durable actions.",
)


def select_review_strategy(
    *,
    task_class: str,
    stakes_level: str,
    evidence_count: int = 0,
    has_workflow_proposal: bool = False,
) -> ReviewConfiguration:
    """Select the appropriate review strategy based on task context.

    This is a deterministic, auditable selection — no neural routing.
    """
    # Durable actions always get exhaustive review
    if has_workflow_proposal:
        return EXHAUSTIVE_REVIEW

    # High-stakes tasks get deep review
    if stakes_level in ("high", "critical"):
        return DEEP_REVIEW

    # Challenge and research tasks get deep review
    if task_class in ("challenge", "research", "plan"):
        return DEEP_REVIEW

    # Low-stakes greetings get minimal review
    if stakes_level == "low" and evidence_count == 0:
        return MINIMAL_REVIEW

    # Everything else gets standard review
    return STANDARD_REVIEW


# ── Reviewer calibration ──────────────────────────────────────────────────

@dataclass
class ReviewerCalibration:
    """Tracks known blind spots and calibration for review processes."""
    known_blind_spots: list[str] = field(default_factory=list)
    false_positive_rate: float = 0.0   # rate of unnecessary BLOCKs
    false_negative_rate: float = 0.0   # rate of missed issues
    total_reviews: int = 0
    total_blocks: int = 0
    total_overrides: int = 0           # owner overrode BLOCK

    def record_review(self, verdict: str, owner_override: bool = False) -> None:
        """Record a review outcome for calibration tracking."""
        self.total_reviews += 1
        if verdict == "BLOCK":
            self.total_blocks += 1
        if owner_override:
            self.total_overrides += 1
