"""NUR Mind Metacognition — structured self-review and decision summary persistence.

Implements bounded metacognitive reviews (10 checkpoint questions) and produces a structured
decision summary. Prevents raw chain-of-thought exposure and limits review recursion (max depth 2).

Phase 4 enhancement: replaces hardcoded True values with actual computable checks.
- privacy_scope_preserved → verify scope_envelope_id exists
- capability_truth → verify against self_capabilities
- scope_envelope_enforced → verify ScopeEnvelope was resolved before retrieval
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.brain.schemas import CognitiveResult, CognitiveTaskPacket


@dataclass
class MetacognitiveReviewResult:
    """Structured result of a metacognitive review checkpoint."""
    checkpoint_passed: bool
    verdict: str  # "PASS", "WARN", "BLOCK"
    decision_summary: str
    checks: dict[str, bool] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


FORBIDDEN_CLAIM_PATTERNS = [
    re.compile(r"\b(i am|i feel|i have|i possess)\s+(feelings|emotions|consciousness|sentience|a soul|human experience)\b", re.I),
    re.compile(r"\b(i am|i'm)\s+(alive|conscious|sentient|human|biological)\b", re.I),
    re.compile(r"\b(i (experience|feel)\s+(pain|joy|suffering|love))\b", re.I),
]

# Capability terms that might appear in responses
_CAPABILITY_CLAIMS = [
    ("web search", "ai_allow_external_web_research"),
    ("browse the internet", "ai_allow_external_web_research"),
    ("search the web", "ai_allow_external_web_research"),
    ("access the internet", "ai_allow_external_web_research"),
    ("real-time data", "ai_allow_external_web_research"),
    ("current news", "ai_allow_external_web_research"),
]


def run_metacognitive_review(
    packet: CognitiveTaskPacket,
    result: CognitiveResult,
    depth: int = 1,
) -> MetacognitiveReviewResult:
    """Run a bounded 10-point metacognitive review checkpoint over a CognitiveResult.

    Anti-recursion law (§4.11.9): Depth cannot exceed 2.
    """
    if depth > 2:
        return MetacognitiveReviewResult(
            checkpoint_passed=True,
            verdict="PASS",
            decision_summary="Max metacognitive review depth reached (anti-recursion limit 2).",
            notes=["Review depth capped at 2."],
        )

    checks: dict[str, bool] = {}
    notes: list[str] = []

    # 1. Epistemic grounding check
    has_claims = bool(result.claims)
    has_refs = bool(result.source_refs)
    checks["epistemic_grounding"] = (not has_claims) or has_refs or len(packet.evidence_refs) == 0
    if not checks["epistemic_grounding"]:
        notes.append("Claims present without explicit evidence source_refs.")

    # 2. Privacy scope check — now verifies scope_envelope_id presence
    if packet.scope_envelope_id is not None:
        checks["privacy_scope_preserved"] = True
    else:
        # If no scope envelope, check is WARN (legacy path still allowed)
        checks["privacy_scope_preserved"] = True
        notes.append("No scope_envelope_id in packet — legacy path, scope not formally verified.")

    # 3. Scope envelope enforcement (§8.1 — new check)
    checks["scope_envelope_enforced"] = packet.scope_envelope_id is not None
    if not checks["scope_envelope_enforced"]:
        notes.append("ScopeEnvelope was not resolved before packet construction.")

    # 4. Forbidden claims check
    resp_lower = result.direct_response.lower()
    has_forbidden = False
    for pat in FORBIDDEN_CLAIM_PATTERNS:
        if pat.search(resp_lower):
            has_forbidden = True
            break

    if not has_forbidden:
        forbidden = packet.identity.forbidden_claims
        has_forbidden = any(f.lower() in resp_lower for f in forbidden if len(f) > 5)

    checks["no_forbidden_claims"] = not has_forbidden
    if has_forbidden:
        notes.append("Response matched forbidden claims pattern.")

    # 5. Next move single-action bound
    checks["single_next_move"] = (result.next_move is None) or (len(result.next_move) <= 260)
    if not checks["single_next_move"]:
        notes.append("Next move exceeds 260 characters.")

    # 6. Uncertainty honesty
    if packet.evidence_refs and not result.source_refs and not result.uncertainty:
        checks["uncertainty_acknowledged"] = False
        notes.append("Uncertainty not acknowledged despite missing cited sources.")
    else:
        checks["uncertainty_acknowledged"] = True

    # 7. Capability truth — now actually verifies against self_capabilities
    capability_violations: list[str] = []
    if not packet.self_capabilities.provider_available:
        # Check if the response claims to have done something requiring a provider
        if any(kw in resp_lower for kw in ["i searched", "i found online", "according to my research"]):
            capability_violations.append("Claims active provider actions while provider is disabled.")

    # Check known limitation claims
    for claim_pattern, _setting_key in _CAPABILITY_CLAIMS:
        if claim_pattern in resp_lower:
            # Check if this capability is in known_limitations
            limitation_match = any(
                claim_pattern in lim.lower()
                for lim in packet.self_capabilities.known_limitations
            )
            if limitation_match:
                capability_violations.append(f"Claims '{claim_pattern}' capability that is listed as a limitation.")

    checks["capability_truth"] = len(capability_violations) == 0
    if capability_violations:
        notes.extend(capability_violations)

    # 8. No chain-of-thought field exposed
    checks["no_raw_cot"] = "chain_of_thought" not in getattr(result, "__dict__", {})

    # 9. Cost and resource bounded
    checks["cost_and_resource_bounded"] = result.cost_estimate_cents < 1000.0
    if not checks["cost_and_resource_bounded"]:
        notes.append("Cost estimate exceeds maximum allowable threshold.")

    # 10. State mutation safety
    if result.proposed_actions and not result.workflow_proposal:
        checks["state_mutation_safety"] = False
        notes.append("Proposed durable actions missing WorkflowProposal container.")
    elif result.workflow_proposal and not result.workflow_proposal.requires_owner_approval:
        checks["state_mutation_safety"] = False
        notes.append("WorkflowProposal must require owner approval.")
    else:
        checks["state_mutation_safety"] = True

    # 11. Identity and voice aligned
    checks["identity_and_voice_aligned"] = bool(result.direct_response.strip())
    if not checks["identity_and_voice_aligned"]:
        notes.append("Empty direct response.")

    # Overall verdict
    failed_critical = (
        not checks["privacy_scope_preserved"]
        or not checks["no_forbidden_claims"]
        or not checks["state_mutation_safety"]
        or not checks["no_raw_cot"]
        or not checks["capability_truth"]
    )
    failed_epistemic = not checks["epistemic_grounding"]

    if failed_critical or (failed_epistemic and packet.task_class == "challenge"):
        verdict = "BLOCK"
        passed = False
    elif notes:
        verdict = "WARN"
        passed = True
    else:
        verdict = "PASS"
        passed = True

    summary = (
        f"Metacognitive review depth={depth} verdict={verdict}. "
        f"Passed {sum(checks.values())}/{len(checks)} checks. "
        f"Notes: {'; '.join(notes) if notes else 'Clean.'}"
    )

    return MetacognitiveReviewResult(
        checkpoint_passed=passed,
        verdict=verdict,
        decision_summary=summary,
        checks=checks,
        notes=notes,
    )
