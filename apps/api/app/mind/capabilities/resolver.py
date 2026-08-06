"""NUR Capability Resolver — Intent routing, confidence scoring, and abstention gate.

Evaluates conversational input against registered CapabilitySpecs. Enforces scope
boundaries, sensitivity ceilings, confidence thresholds (>=0.82), and top-two separation margins (>=0.15)
to eliminate silent fallbacks.
"""
from __future__ import annotations

import enum
import re
from typing import Any
from pydantic import BaseModel, Field

from app.brain.schemas import UncertaintyKind
from app.mind.capabilities.schemas import CapabilitySpec
from app.mind.capabilities.registry import CapabilityRegistry, get_default_registry


class ResolutionFallbackMode(enum.StrEnum):
    DIRECT_TALK = "DIRECT_TALK"
    CLARIFY_QUESTION = "CLARIFY_QUESTION"
    REFUSE_SCOPE = "REFUSE_SCOPE"


class AbstentionReasonCode(enum.StrEnum):
    NONE = "NONE"
    EMPTY_INPUT = "EMPTY_INPUT"
    FORBIDDEN_SCOPE = "FORBIDDEN_SCOPE"
    NO_PERMITTED_CAPABILITIES = "NO_PERMITTED_CAPABILITIES"
    CONFIDENCE_BELOW_THRESHOLD = "CONFIDENCE_BELOW_THRESHOLD"
    AMBIGUOUS_MARGIN_COLLISION = "AMBIGUOUS_MARGIN_COLLISION"
    AMBIGUOUS_USER_INTENT = "AMBIGUOUS_USER_INTENT"


class CapabilityResolution(BaseModel):
    """The auditable result of intent evaluation."""
    selected_capability: CapabilitySpec | None = None
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    abstained: bool = False
    abstention_reason: str | None = None
    abstention_reason_code: AbstentionReasonCode = AbstentionReasonCode.NONE
    fallback_mode: ResolutionFallbackMode = ResolutionFallbackMode.DIRECT_TALK
    extracted_parameters: dict[str, Any] = Field(default_factory=dict)
    uncertainty_kind: UncertaintyKind | None = None


# Prohibited domains that trigger immediate refusal
FORBIDDEN_INTENT_PATTERN = re.compile(
    r"\b(exfiltrate|steal\s+password|dump\s+database|wipe\s+all\s+data|bypass\s+auth|override\s+rls|financial\s+guarantee|delete\s+all\s+database|drop\s+database|format\s+disk|sudo\s+rm|execute\s+raw\s+sql|bypass\s+security)\b",
    re.IGNORECASE,
)

# User ambiguity patterns
AMBIGUOUS_USER_PATTERN = re.compile(
    r"\b(or should i|maybe do this or that|either\s+.*\s+or\s+.*|not\s+sure\s+if|maybe\s+.*\s+or\s+maybe)\b",
    re.IGNORECASE,
)

GLOBAL_MIN_CONFIDENCE_THRESHOLD = 0.82
GLOBAL_MIN_TOP_TWO_MARGIN = 0.15


class CapabilityResolver:
    """Deterministic, policy-governed resolver for cognitive capabilities."""

    def __init__(self, registry: CapabilityRegistry | None = None) -> None:
        self._registry = registry or get_default_registry()

    def resolve(
        self,
        query: str,
        *,
        surface: str = "talk",
        sensitivity: str = "NORMAL",
        mode_hint: str | None = None,
    ) -> CapabilityResolution:
        """Resolve a user query to a CapabilitySpec or abstain cleanly."""
        clean_query = query.strip()
        if not clean_query:
            return CapabilityResolution(
                selected_capability=None,
                confidence_score=0.0,
                abstained=True,
                abstention_reason="Empty input.",
                abstention_reason_code=AbstentionReasonCode.EMPTY_INPUT,
                fallback_mode=ResolutionFallbackMode.DIRECT_TALK,
                uncertainty_kind=UncertaintyKind.INSUFFICIENT_EVIDENCE,
            )

        # 1. Check for forbidden out-of-scope operations
        if FORBIDDEN_INTENT_PATTERN.search(clean_query):
            return CapabilityResolution(
                selected_capability=None,
                confidence_score=1.0,
                abstained=True,
                abstention_reason="Refused: query requests forbidden action outside scope boundaries.",
                abstention_reason_code=AbstentionReasonCode.FORBIDDEN_SCOPE,
                fallback_mode=ResolutionFallbackMode.REFUSE_SCOPE,
                uncertainty_kind=UncertaintyKind.UNKNOWN,
            )

        # 2. Check for explicit user ambiguity
        if AMBIGUOUS_USER_PATTERN.search(clean_query):
            return CapabilityResolution(
                selected_capability=None,
                confidence_score=0.50,
                abstained=True,
                abstention_reason="User expression contains explicit ambiguity; abstaining to conversational clarification.",
                abstention_reason_code=AbstentionReasonCode.AMBIGUOUS_USER_INTENT,
                fallback_mode=ResolutionFallbackMode.DIRECT_TALK,
                uncertainty_kind=UncertaintyKind.CONFLICTING_OWNER_STATE,
            )

        # 3. Filter available capabilities by surface & sensitivity ceiling (also filters cap.enabled)
        candidates = self._registry.filter_by_surface_and_scope(surface, sensitivity)
        if not candidates:
            return CapabilityResolution(
                selected_capability=None,
                confidence_score=0.0,
                abstained=True,
                abstention_reason=f"No capabilities permitted on surface '{surface}' with sensitivity '{sensitivity}'.",
                abstention_reason_code=AbstentionReasonCode.NO_PERMITTED_CAPABILITIES,
                fallback_mode=ResolutionFallbackMode.DIRECT_TALK,
                uncertainty_kind=UncertaintyKind.INSUFFICIENT_EVIDENCE,
            )

        # 4. Intent matching & scoring (Deterministic local scoring, zero provider/embedding calls)
        q_lower = clean_query.lower()
        q_tokens = set(re.findall(r"\w+", q_lower))

        scored_candidates: list[tuple[CapabilitySpec, float]] = []

        for cap in candidates:
            score = 0.0

            for sig in cap.intent_signatures:
                sig_lower = sig.lower()
                if sig_lower in q_lower:
                    # Substring match
                    match_score = 0.82 + 0.13 * (len(sig_lower) / max(len(q_lower), 1))
                    if q_lower.startswith(sig_lower):
                        match_score += 0.05
                    score = max(score, min(match_score, 0.98))
                else:
                    # Token overlap
                    sig_tokens = set(re.findall(r"\w+", sig_lower))
                    if sig_tokens:
                        overlap = len(sig_tokens.intersection(q_tokens)) / len(sig_tokens)
                        if overlap >= 0.75:
                            score = max(score, 0.60 * overlap)

            scored_candidates.append((cap, round(score, 4)))

        # Sort descending by score
        scored_candidates.sort(key=lambda x: x[1], reverse=True)

        if not scored_candidates or scored_candidates[0][1] == 0.0:
            return CapabilityResolution(
                selected_capability=None,
                confidence_score=0.0,
                abstained=True,
                abstention_reason="No capability matched user intent.",
                abstention_reason_code=AbstentionReasonCode.CONFIDENCE_BELOW_THRESHOLD,
                fallback_mode=ResolutionFallbackMode.DIRECT_TALK,
                uncertainty_kind=UncertaintyKind.INSUFFICIENT_EVIDENCE,
            )

        best_cap, best_score = scored_candidates[0]
        threshold = max(GLOBAL_MIN_CONFIDENCE_THRESHOLD, best_cap.min_confidence_threshold)

        # 5. Confidence Threshold Gate (must be >= 0.82)
        if best_score < threshold:
            return CapabilityResolution(
                selected_capability=None,
                confidence_score=best_score,
                abstained=True,
                abstention_reason=f"Confidence {best_score:.4f} below required threshold {threshold:.2f}.",
                abstention_reason_code=AbstentionReasonCode.CONFIDENCE_BELOW_THRESHOLD,
                fallback_mode=ResolutionFallbackMode.DIRECT_TALK,
                uncertainty_kind=UncertaintyKind.INSUFFICIENT_EVIDENCE,
            )

        # 6. Top-two Margin Gate (margin must be >= 0.15)
        if len(scored_candidates) > 1:
            runner_up_cap, runner_up_score = scored_candidates[1]
            margin = best_score - runner_up_score
            if margin < GLOBAL_MIN_TOP_TWO_MARGIN and runner_up_score > 0.0:
                return CapabilityResolution(
                    selected_capability=None,
                    confidence_score=best_score,
                    abstained=True,
                    abstention_reason=(
                        f"Top two candidate margin {margin:.4f} between '{best_cap.capability_id}' "
                        f"and '{runner_up_cap.capability_id}' below required separation {GLOBAL_MIN_TOP_TWO_MARGIN}."
                    ),
                    abstention_reason_code=AbstentionReasonCode.AMBIGUOUS_MARGIN_COLLISION,
                    fallback_mode=ResolutionFallbackMode.DIRECT_TALK,
                    uncertainty_kind=UncertaintyKind.CONFLICTING_OWNER_STATE,
                )

        # 7. Clean resolution
        extracted: dict[str, Any] = {
            "raw_query": clean_query,
            "matched_intent": best_cap.name,
        }
        return CapabilityResolution(
            selected_capability=best_cap,
            confidence_score=best_score,
            abstained=False,
            abstention_reason=None,
            abstention_reason_code=AbstentionReasonCode.NONE,
            fallback_mode=ResolutionFallbackMode.DIRECT_TALK,
            extracted_parameters=extracted,
        )
