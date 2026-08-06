"""Brain model profiles — FAST / BALANCED / DEEP / CRITIC.

Each profile maps to a provider + model + configuration.  The router selects
a profile; the provider adapter uses it.  Profiles are defined in code for now;
the ``brain_model_profiles`` migration adds a DB-backed override layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.brain.schemas import BrainProfileKey


@dataclass(frozen=True)
class BrainProfile:
    """Immutable provider configuration for one cognitive profile."""
    key: BrainProfileKey
    description: str
    reasoning_effort: str          # "low", "medium", "high"
    temperature: float             # 0.0 – 1.0 (only for non-reasoning models)
    max_output_tokens: int
    timeout_seconds: int
    max_specialist_calls: int      # 0 = no sub-calls allowed
    requires_structured_output: bool
    cost_weight: float             # relative cost multiplier for budget checks
    model: str | None = None

    def provider_overrides(self) -> dict[str, Any]:
        """Return provider-specific kwargs overlay."""
        return {
            "reasoning_effort": self.reasoning_effort,
            "timeout_seconds": self.timeout_seconds,
        }


# ── Built-in profile catalogue ─────────────────────────────────────────────

FAST = BrainProfile(
    key=BrainProfileKey.FAST,
    description="Low-latency responses: greetings, simple Q&A, classification.",
    reasoning_effort="low",
    temperature=0.3,
    max_output_tokens=1024,
    timeout_seconds=15,
    max_specialist_calls=0,
    requires_structured_output=True,
    cost_weight=0.3,
)

BALANCED = BrainProfile(
    key=BrainProfileKey.BALANCED,
    description="Standard Talk responses with evidence grounding.",
    reasoning_effort="medium",
    temperature=0.4,
    max_output_tokens=4096,
    timeout_seconds=30,
    max_specialist_calls=1,
    requires_structured_output=True,
    cost_weight=1.0,
)

DEEP = BrainProfile(
    key=BrainProfileKey.DEEP,
    description="Complex reasoning, planning, research synthesis.",
    reasoning_effort="high",
    temperature=0.5,
    max_output_tokens=8192,
    timeout_seconds=60,
    max_specialist_calls=3,
    requires_structured_output=True,
    cost_weight=2.5,
)

CRITIC = BrainProfile(
    key=BrainProfileKey.CRITIC,
    description="Independent verification of claims and evidence coverage.",
    reasoning_effort="high",
    temperature=0.2,
    max_output_tokens=2048,
    timeout_seconds=30,
    max_specialist_calls=0,
    requires_structured_output=True,
    cost_weight=1.5,
)

PROFILES: dict[BrainProfileKey, BrainProfile] = {
    BrainProfileKey.FAST: FAST,
    BrainProfileKey.BALANCED: BALANCED,
    BrainProfileKey.DEEP: DEEP,
    BrainProfileKey.CRITIC: CRITIC,
}


def get_profile(key: BrainProfileKey) -> BrainProfile:
    """Return the profile for *key*, or BALANCED if unknown."""
    return PROFILES.get(key, BALANCED)
