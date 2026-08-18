from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, Field


class DAGExecutionLimits(BaseModel):
    max_width: int = Field(default=4, ge=1, le=128)
    max_calls: int = Field(default=32, ge=1, le=10_000)
    max_tokens: int = Field(default=100_000, ge=1, le=10_000_000)
    max_cost_cents: int = Field(default=100_000, ge=0, le=10_000_000)
    deadline_seconds: float = Field(default=300.0, gt=0, le=86_400)


class DAGValidationResult(BaseModel):
    allowed: bool
    width: int = 0
    calls: int = 0
    tokens: int = 0
    cost_cents: int = 0
    violations: list[str] = Field(default_factory=list)
    failure_propagation: list[str] = Field(default_factory=list)


def _width(nodes: list[dict]) -> int:
    keys = {str(node.get("key")) for node in nodes}
    remaining = {key: {str(dep) for dep in node.get("depends_on", []) if str(dep) in keys} for key, node in ((str(item.get("key")), item) for item in nodes)}
    max_width = 0
    while remaining:
        ready = sorted(key for key, deps in remaining.items() if not deps)
        if not ready:
            return max(max_width, len(remaining))
        max_width = max(max_width, len(ready))
        for key in ready:
            remaining.pop(key)
        for deps in remaining.values():
            deps.difference_update(ready)
    return max_width


def validate_dag_limits(
    nodes: Iterable[dict],
    *,
    limits: DAGExecutionLimits,
    elapsed_seconds: float = 0.0,
    cancellation_requested: bool = False,
) -> DAGValidationResult:
    """Validate a proposed DAG before Agency queues any step."""
    items = [dict(node) for node in nodes]
    width = _width(items)
    calls = len(items)
    tokens = sum(max(0, int(node.get("estimated_tokens", 0))) for node in items)
    cost = sum(max(0, int(node.get("estimated_cost_cents", 0))) for node in items)
    violations: list[str] = []
    if width > limits.max_width:
        violations.append("MAX_WIDTH")
    if calls > limits.max_calls:
        violations.append("MAX_CALLS")
    if tokens > limits.max_tokens:
        violations.append("MAX_TOKENS")
    if cost > limits.max_cost_cents:
        violations.append("MAX_COST")
    if elapsed_seconds > limits.deadline_seconds:
        violations.append("DEADLINE")
    if cancellation_requested:
        violations.append("CANCELLED")

    failure_propagation = [
        str(node.get("key"))
        for node in items
        if node.get("failed") or node.get("state") in {"FAILED", "CANCELLED"}
    ]
    if failure_propagation:
        violations.append("DEPENDENCY_FAILURE")

    return DAGValidationResult(
        allowed=not violations,
        width=width,
        calls=calls,
        tokens=tokens,
        cost_cents=cost,
        violations=violations,
        failure_propagation=failure_propagation,
    )
