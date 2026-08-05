"""Brain model router — selects a profile for each cognitive task.

Replaces the keyword-only ``task_router.route_task()`` with a structured
routing decision that considers stakes, context size, task class, budget
and language.  Every decision is recorded in a ``RouteDecision``.
"""
from __future__ import annotations

from app.brain.profiles import BrainProfile, get_profile
from app.brain.schemas import BrainProfileKey, CognitiveTaskPacket, RouteDecision

# ── Task-class → default profile mapping ────────────────────────────────────

_CLASS_DEFAULTS: dict[str, BrainProfileKey] = {
    "talk": BrainProfileKey.BALANCED,
    "challenge": BrainProfileKey.DEEP,
    "reflect": BrainProfileKey.DEEP,
    "summarize": BrainProfileKey.FAST,
    "plan": BrainProfileKey.DEEP,
    "research": BrainProfileKey.DEEP,
    "classify": BrainProfileKey.FAST,
}

# ── Keywords that indicate higher stakes ────────────────────────────────────

_HIGH_STAKES_TOKENS = frozenset({
    "decide", "commit", "irreversible", "contract", "deadline",
    "medical", "legal", "financial", "safety", "critical",
    "investment", "surgery", "diagnosis",
})

_CHALLENGE_TOKENS = frozenset({
    "challenge me", "push back", "don't soothe", "be honest",
    "disagree", "what am i wrong about",
})


def classify_stakes(user_input: str) -> str:
    """Return 'low', 'normal', 'high' or 'critical'."""
    lowered = user_input.lower()
    if any(tok in lowered for tok in _HIGH_STAKES_TOKENS):
        return "high"
    if any(tok in lowered for tok in _CHALLENGE_TOKENS):
        return "high"
    if len(user_input) > 2000:
        return "high"
    if len(user_input) < 40:
        return "low"
    return "normal"


def route(packet: CognitiveTaskPacket) -> RouteDecision:
    """Select the best Brain profile for *packet* and return a recorded decision.

    Routing factors (per directive §5):
    - task class
    - stakes level
    - context size (evidence count)
    - budget remaining
    - risk flags
    """
    task_class = packet.task_class
    stakes = classify_stakes(packet.user_input)
    evidence_count = len(packet.evidence_refs)
    budget_remaining = packet.self_capabilities.daily_budget_remaining
    has_risk_flags = bool(packet.risk_flags)

    # Start from the task-class default
    profile_key = _CLASS_DEFAULTS.get(task_class, BrainProfileKey.BALANCED)
    reasons: list[str] = [f"task_class={task_class}"]

    # Upgrade for high stakes
    if stakes in ("high", "critical"):
        if profile_key == BrainProfileKey.FAST:
            profile_key = BrainProfileKey.BALANCED
            reasons.append("upgraded:fast→balanced (high stakes)")
        elif profile_key == BrainProfileKey.BALANCED:
            profile_key = BrainProfileKey.DEEP
            reasons.append("upgraded:balanced→deep (high stakes)")

    # Upgrade for heavy evidence context
    if evidence_count > 4 and profile_key == BrainProfileKey.FAST:
        profile_key = BrainProfileKey.BALANCED
        reasons.append("upgraded:fast→balanced (evidence>4)")

    # Upgrade for risk flags
    if has_risk_flags and profile_key != BrainProfileKey.DEEP:
        profile_key = BrainProfileKey.DEEP
        reasons.append("upgraded→deep (risk_flags present)")

    # Downgrade if budget is critically low
    if budget_remaining <= 3 and profile_key in (BrainProfileKey.DEEP, BrainProfileKey.CRITIC):
        profile_key = BrainProfileKey.FAST
        reasons.append("downgraded→fast (budget≤3)")

    profile: BrainProfile = get_profile(profile_key)
    estimated_tokens = min(profile.max_output_tokens, 800 + evidence_count * 400)

    return RouteDecision(
        task_class=task_class,
        selected_profile=profile_key,
        reason="; ".join(reasons),
        stakes_level=stakes,
        estimated_tokens=estimated_tokens,
    )
