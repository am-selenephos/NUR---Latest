"""NUR Mind Identity — versioned constitution loader and IdentitySnapshot manager.

Loads versioned constitution data (from DB table `mind_identity_versions` or fallbacks
to built-in `NUR_CONSTITUTION_V1`) and returns a frozen `IdentitySnapshot` for the Brain.
"""
from __future__ import annotations

from typing import Any
from app.brain.schemas import IdentitySnapshot
from app.mind.constitution import NUR_CONSTITUTION_V1


def load_identity(constitution_override: dict[str, Any] | None = None) -> IdentitySnapshot:
    """Load and return an ``IdentitySnapshot`` from override or default V1 constitution."""
    data = constitution_override or NUR_CONSTITUTION_V1
    return IdentitySnapshot(
        version=data.get("version", "v1.0.0-20260802"),
        name=data.get("name", "NUR"),
        voice_rules=data.get("voice_rules", []),
        epistemic_rules=data.get("epistemic_rules", []),
        privacy_rules=data.get("privacy_rules", []),
        initiative_rules=data.get("initiative_rules", []),
        language_behaviour=data.get("language_behaviour", {}),
        forbidden_claims=data.get("forbidden_claims", []),
    )
