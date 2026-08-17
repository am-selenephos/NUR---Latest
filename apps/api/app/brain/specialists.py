"""Bounded specialist execution contracts; no worker may widen scope or budget."""
from __future__ import annotations

import json

from pydantic import BaseModel, Field


class SpecialistBudget(BaseModel):
    max_calls: int = Field(ge=1, le=32)
    max_tokens: int = Field(ge=1, le=100_000)
    calls_used: int = 0


class SpecialistResult(BaseModel):
    specialist: str
    capability_id: str
    completed: bool
    output: dict = Field(default_factory=dict)
    tokens_used: int = 0


class SpecialistWorker:
    def __init__(self, specialist: str, *, allowed_capabilities: set[str] | frozenset[str]) -> None:
        self.specialist = specialist
        self.allowed_capabilities = frozenset(allowed_capabilities)

    def run(self, capability_id: str, payload: dict, budget: SpecialistBudget) -> SpecialistResult:
        if capability_id not in self.allowed_capabilities:
            raise PermissionError(f"Capability {capability_id!r} is outside specialist scope.")
        if budget.calls_used >= budget.max_calls:
            raise RuntimeError("Specialist call budget exhausted.")
        tokens_used = max(1, len(json.dumps(payload, sort_keys=True)) // 4)
        if tokens_used > budget.max_tokens:
            raise RuntimeError("Specialist token budget exhausted.")
        budget.calls_used += 1
        return SpecialistResult(
            specialist=self.specialist,
            capability_id=capability_id,
            completed=True,
            output={"accepted": True, "payload_keys": sorted(payload)},
            tokens_used=tokens_used,
        )
