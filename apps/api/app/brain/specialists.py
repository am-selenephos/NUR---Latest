from __future__ import annotations

import json
from collections.abc import Callable
from uuid import UUID

from pydantic import BaseModel, Field


class SpecialistBudget(BaseModel):
    max_calls: int = Field(ge=1, le=32)
    max_tokens: int = Field(ge=1, le=100_000)
    calls_used: int = 0
    max_cost_cents: int = Field(default=1000, ge=0, le=1_000_000)
    cost_used_cents: int = 0


class SpecialistContext(BaseModel):
    owner_user_id: UUID
    allowed_record_classes: set[str] = Field(default_factory=set)
    included_context: dict[str, str] = Field(default_factory=dict)
    excluded_context: set[str] = Field(default_factory=set)

    def narrow(self, requested_record_class: str | None) -> "SpecialistContext":
        if requested_record_class and self.allowed_record_classes and requested_record_class not in self.allowed_record_classes:
            raise PermissionError("Specialist context request would widen the inherited scope.")
        included = {
            key: value
            for key, value in self.included_context.items()
            if key not in self.excluded_context
        }
        return self.model_copy(update={"included_context": included})


class SpecialistResult(BaseModel):
    specialist: str
    capability_id: str
    completed: bool
    output: dict = Field(default_factory=dict)
    tokens_used: int = 0
    cost_used_cents: int = 0
    role: str = ""
    typed_result: bool = False
    context_record_ids: list[str] = Field(default_factory=list)
    error_code: str | None = None


class SpecialistWorker:
    """A bounded Brain-side reasoning role with no Agency authority."""

    def __init__(self, specialist: str, *, allowed_capabilities: set[str] | frozenset[str]) -> None:
        self.specialist = specialist
        self.allowed_capabilities = frozenset(allowed_capabilities)

    def _check_budget(self, payload: dict, budget: SpecialistBudget) -> int:
        if budget.calls_used >= budget.max_calls:
            raise RuntimeError("Specialist call budget exhausted.")
        tokens_used = max(1, len(json.dumps(payload, sort_keys=True)) // 4)
        if tokens_used > budget.max_tokens:
            raise RuntimeError("Specialist token budget exhausted.")
        cost = max(1, tokens_used // 10)
        if budget.cost_used_cents + cost > budget.max_cost_cents:
            raise RuntimeError("Specialist cost budget exhausted.")
        budget.calls_used += 1
        budget.cost_used_cents += cost
        return tokens_used

    def run(self, capability_id: str, payload: dict, budget: SpecialistBudget) -> SpecialistResult:
        if capability_id not in self.allowed_capabilities:
            raise PermissionError(f"Capability {capability_id!r} is outside specialist scope.")
        tokens_used = self._check_budget(payload, budget)
        return SpecialistResult(
            specialist=self.specialist,
            capability_id=capability_id,
            completed=True,
            output={"accepted": True, "payload_keys": sorted(payload)},
            tokens_used=tokens_used,
            cost_used_cents=max(1, tokens_used // 10),
            role=self.specialist,
            typed_result=True,
        )

    def run_reasoning(
        self,
        capability_id: str,
        payload: dict,
        budget: SpecialistBudget,
        *,
        context: SpecialistContext,
        deadline_seconds: float,
        cancel_requested: bool = False,
        handler: Callable[[str, dict, SpecialistContext], dict] | None = None,
    ) -> SpecialistResult:
        if capability_id not in self.allowed_capabilities:
            raise PermissionError(f"Capability {capability_id!r} is outside specialist scope.")
        if cancel_requested:
            return SpecialistResult(
                specialist=self.specialist,
                capability_id=capability_id,
                completed=False,
                role=self.specialist,
                error_code="CANCELLED",
            )
        if deadline_seconds <= 0:
            raise TimeoutError("Specialist deadline exceeded before reasoning started.")
        requested_class = payload.get("record_class")
        narrowed = context.narrow(requested_class)
        tokens_used = self._check_budget(payload, budget)
        if handler is None:
            output = self._default_reasoning(payload, narrowed)
        else:
            output = handler(capability_id, payload, narrowed)
        if not isinstance(output, dict) or not isinstance(output.get("kind"), str):
            return SpecialistResult(
                specialist=self.specialist,
                capability_id=capability_id,
                completed=False,
                role=self.specialist,
                typed_result=False,
                tokens_used=tokens_used,
                cost_used_cents=max(1, tokens_used // 10),
                error_code="MALFORMED_RESULT",
            )
        return SpecialistResult(
            specialist=self.specialist,
            capability_id=capability_id,
            completed=True,
            output=output,
            tokens_used=tokens_used,
            cost_used_cents=max(1, tokens_used // 10),
            role=self.specialist,
            typed_result=True,
            context_record_ids=sorted(narrowed.included_context),
        )

    def _default_reasoning(self, payload: dict, context: SpecialistContext) -> dict:
        if self.specialist == "research":
            return {
                "kind": "research_analysis",
                "summary": f"Research request received: {payload.get('query', '')}",
                "evidence_gaps": ["provider retrieval not invoked by this bounded fixture"],
                "scope": sorted(context.allowed_record_classes),
            }
        if self.specialist == "planning":
            return {
                "kind": "planning_analysis",
                "summary": f"Planning request received: {payload.get('objective', '')}",
                "evidence_gaps": ["owner success criteria require explicit confirmation"],
                "scope": sorted(context.allowed_record_classes),
            }
        if self.specialist == "evidence":
            return {
                "kind": "evidence_analysis",
                "summary": "Evidence was retained as scoped input, not authority.",
                "evidence_gaps": [],
                "scope": sorted(context.allowed_record_classes),
            }
        return {
            "kind": "domain_analysis",
            "summary": "Bounded domain analysis completed without Agency authority.",
            "evidence_gaps": [],
            "scope": sorted(context.allowed_record_classes),
        }
