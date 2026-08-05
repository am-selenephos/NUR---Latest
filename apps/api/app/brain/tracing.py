"""Brain tracing — structured trace recording for Brain runs.

Every Brain run gets a deterministic trace ID chain:
  brain_run_id → model_run_id → task_id → request_id

No chain-of-thought is persisted.  Only structured decision summaries,
profile choices, evidence coverage, and cost are recorded.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BrainTrace:
    """Accumulates structured trace data during a Brain run."""
    brain_run_id: uuid.UUID = field(default_factory=uuid.uuid4)
    task_id: uuid.UUID | None = None
    model_run_id: uuid.UUID | None = None
    request_id: uuid.UUID | None = None
    profile_key: str = ""
    route_reason: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_cents: float = 0.0
    wall_time_ms: int = 0

    def record_step(self, step_name: str, **kwargs: Any) -> None:
        """Append a named trace step with structured metadata."""
        self.steps.append({"step": step_name, **kwargs})

    def to_metadata(self) -> dict[str, Any]:
        """Serialise for ``model_runs.run_metadata`` or ``brain_runs``."""
        return {
            "brain_run_id": str(self.brain_run_id),
            "task_id": str(self.task_id) if self.task_id else None,
            "model_run_id": str(self.model_run_id) if self.model_run_id else None,
            "request_id": str(self.request_id) if self.request_id else None,
            "profile_key": self.profile_key,
            "route_reason": self.route_reason,
            "steps": self.steps,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_cents": self.total_cost_cents,
            "wall_time_ms": self.wall_time_ms,
        }
