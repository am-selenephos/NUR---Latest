"""Promotion gates for planner, simulator, critic, and provider evaluation."""
from __future__ import annotations

from pydantic import BaseModel, Field


class EvaluationCase(BaseModel):
    case_id: str
    split: str
    expected: str


class EvaluationGate(BaseModel):
    cases: list[EvaluationCase] = Field(default_factory=list)
    shadow_pass_rate: float = 0.0

    def can_promote(self, observed: dict[str, str]) -> bool:
        held_out = [case for case in self.cases if case.split == "held_out"]
        if not held_out or self.shadow_pass_rate < 1.0:
            return False
        return all(observed.get(case.case_id) == case.expected for case in held_out)
