"""Plan compilation: turn a proposed plan into a durable, executable DAG.

Compilation is where a plan stops being a suggestion and becomes rows a worker
will act on, so it is the last cheap place to refuse. Three classes of problem
are caught here rather than at run time:

  * A cycle. Discovering one at run time means a workflow that never finishes
    and never fails — it sits in BLOCKED forever waiting on itself, which looks
    identical to a slow step and consumes an approval slot in the owner's inbox.

  * A denied tool. Compiling a step whose tool the policy engine refuses would
    build a plan guaranteed to stall halfway, after the owner has already
    approved the parts before it. Better to fail the whole plan with the policy
    reason attached than to strand it mid-execution.

  * A dangling dependency. A step depending on a key no step produces can never
    unblock. `unlock_dependants` already treats a missing dependency as
    unsatisfied, so this would be a permanent stall rather than a crash.

Everything here is pure. Compilation reads a proposed plan and the owner's
policy and returns either rows to insert or a refusal — it does not touch the
database, which is what lets the failure modes above be tested exhaustively.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from app.agentic.enums import StepState
from app.agentic.limits import DAGExecutionLimits, validate_dag_limits
from app.agentic.policy import Decision, OwnerPolicy, PolicyVerdict, evaluate
from app.agentic.registry import UnknownToolError, contract, spec


@dataclass(frozen=True)
class ProposedStep:
    """One node as the planner proposes it, before any validation."""

    key: str
    role: str
    tool_key: str
    depends_on: tuple[str, ...] = ()
    input_refs: dict = field(default_factory=dict)
    rationale: str = ""


@dataclass(frozen=True)
class CompiledStep:
    key: str
    ordinal: int
    role: str
    tool_key: str
    tool_version: str
    risk_class: str
    requested_capabilities: tuple[str, ...]
    depends_on: tuple[str, ...]
    approval_required: bool
    state: StepState
    input_refs: dict
    timeout_seconds: int


@dataclass(frozen=True)
class CompileError:
    code: str
    message: str
    step_key: str | None = None


@dataclass(frozen=True)
class CompileResult:
    ok: bool
    steps: tuple[CompiledStep, ...] = ()
    errors: tuple[CompileError, ...] = ()
    # Steps the owner will be asked about, surfaced up front so an approval card
    # can show the whole ask rather than one step at a time.
    approval_keys: tuple[str, ...] = ()


# Verification must be performed by a role that did not do the work. Anything
# else is a model grading its own homework, which is not verification.
EXECUTOR_ROLES = frozenset({"operator", "researcher", "implementer", "writer", "translator"})
VERIFIER_ROLES = frozenset({"verifier", "critic", "qa", "security_reviewer", "visual_reviewer"})


def topological_order(steps: tuple[ProposedStep, ...]) -> list[str] | None:
    """Kahn's algorithm. Returns None when a cycle exists.

    Returning None rather than raising keeps the caller in charge of how a cycle
    is reported — the compiler wants it as one error among several, not as an
    exception that hides every other problem in the plan.
    """
    keys = {s.key for s in steps}
    indegree = {s.key: sum(1 for d in s.depends_on if d in keys) for s in steps}
    dependants: dict[str, list[str]] = {s.key: [] for s in steps}
    for step in steps:
        for dep in step.depends_on:
            if dep in keys:
                dependants[dep].append(step.key)

    # Sorted so compilation is deterministic: the same plan always produces the
    # same ordinals, which makes plan versions comparable.
    ready = sorted(k for k, n in indegree.items() if n == 0)
    order: list[str] = []
    while ready:
        key = ready.pop(0)
        order.append(key)
        for nxt in sorted(dependants[key]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
                ready.sort()
    return order if len(order) == len(steps) else None


def compile_plan(
    proposed: tuple[ProposedStep, ...],
    policy: OwnerPolicy,
    *,
    within_scope: bool = True,
    now: dt.datetime | None = None,
    limits: DAGExecutionLimits | None = None,
    elapsed_seconds: float = 0.0,
    cancellation_requested: bool = False,
) -> CompileResult:
    errors: list[CompileError] = []
    policy_now = now or dt.datetime.now(dt.timezone.utc)

    if not proposed:
        return CompileResult(False, errors=(CompileError("EMPTY_PLAN", "A plan needs at least one step."),))

    if limits is not None:
        limit_result = validate_dag_limits(
            [
                {
                    "key": step.key,
                    "depends_on": list(step.depends_on),
                    "estimated_tokens": step.input_refs.get("estimated_tokens", 0),
                    "estimated_cost_cents": step.input_refs.get("estimated_cost_cents", 0),
                    "failed": step.input_refs.get("failed", False),
                }
                for step in proposed
            ],
            limits=limits,
            elapsed_seconds=elapsed_seconds,
            cancellation_requested=cancellation_requested,
        )
        errors.extend(
            CompileError("DAG_LIMIT", f"Agency DAG limit violated: {violation}")
            for violation in limit_result.violations
        )

    keys = [s.key for s in proposed]
    duplicates = {k for k in keys if keys.count(k) > 1}
    for key in sorted(duplicates):
        errors.append(CompileError("DUPLICATE_STEP_KEY", f"step key {key!r} appears more than once", key))

    known = set(keys)
    for step in proposed:
        for dep in step.depends_on:
            if dep not in known:
                errors.append(
                    CompileError("DANGLING_DEPENDENCY", f"depends on unknown step {dep!r}", step.key)
                )
        if step.key in step.depends_on:
            errors.append(CompileError("SELF_DEPENDENCY", "a step cannot depend on itself", step.key))

    order = topological_order(proposed)
    if order is None:
        errors.append(
            CompileError(
                "CYCLIC_PLAN",
                "the plan contains a dependency cycle and could never complete",
            )
        )

    # Tool resolution and the policy gate, per step.
    verdicts: dict[str, PolicyVerdict] = {}
    for step in proposed:
        try:
            tool = contract(step.tool_key)
        except UnknownToolError:
            errors.append(
                CompileError("UNKNOWN_TOOL", f"no contract for tool {step.tool_key!r}", step.key)
            )
            continue

        verdict = evaluate(tool, policy, now=policy_now, within_scope=within_scope)
        verdicts[step.key] = verdict
        if verdict.decision is Decision.DENY:
            # Carrying the policy's own reason means the owner is told why the
            # plan was refused, not merely that it was.
            errors.append(CompileError("POLICY_DENIED", verdict.reason, step.key))

        if step.role in VERIFIER_ROLES and step.tool_key not in _read_only_keys():
            errors.append(
                CompileError(
                    "VERIFIER_MUTATES",
                    f"verifier role {step.role!r} may only use read-only tools",
                    step.key,
                )
            )

    _check_verification_independence(proposed, errors)

    if errors:
        return CompileResult(False, errors=tuple(errors))

    assert order is not None  # a cycle would have produced an error above
    position = {key: index for index, key in enumerate(order)}
    by_key = {s.key: s for s in proposed}

    compiled: list[CompiledStep] = []
    approval_keys: list[str] = []
    for ordinal, key in enumerate(order, start=1):
        step = by_key[key]
        tool = contract(step.tool_key)
        tool_spec = spec(step.tool_key)
        needs_approval = verdicts[key].decision is Decision.REQUIRE_APPROVAL
        if needs_approval:
            approval_keys.append(key)
        compiled.append(
            CompiledStep(
                key=key,
                ordinal=ordinal,
                role=step.role,
                tool_key=step.tool_key,
                tool_version=tool.version,
                risk_class=tool.risk_class.value,
                requested_capabilities=tuple(sorted(tool.required_capabilities)),
                depends_on=tuple(sorted(step.depends_on, key=lambda d: position[d])),
                approval_required=needs_approval,
                # A step with dependencies starts BLOCKED; `unlock_dependants`
                # promotes it once every dependency has actually succeeded.
                state=StepState.BLOCKED if step.depends_on else StepState.READY,
                input_refs=dict(step.input_refs),
                timeout_seconds=tool_spec.timeout_seconds,
            )
        )

    return CompileResult(True, steps=tuple(compiled), approval_keys=tuple(approval_keys))


def _read_only_keys() -> frozenset[str]:
    from app.agentic.tools import READ_ONLY

    return frozenset(s.contract.key for s in READ_ONLY)


def _check_verification_independence(
    proposed: tuple[ProposedStep, ...], errors: list[CompileError]
) -> None:
    """A verifier step must not verify work it performed itself.

    Enforced structurally rather than by instruction, because "please review
    this impartially" is not a guarantee — it is a request the same runtime is
    free to ignore.
    """
    by_key = {s.key: s for s in proposed}
    for step in proposed:
        if step.role not in VERIFIER_ROLES:
            continue
        if not step.depends_on:
            errors.append(
                CompileError(
                    "VERIFIER_WITHOUT_SUBJECT",
                    "a verification step must depend on the work it verifies",
                    step.key,
                )
            )
            continue
        for dep in step.depends_on:
            subject = by_key.get(dep)
            if subject is not None and subject.role == step.role:
                errors.append(
                    CompileError(
                        "SELF_VERIFICATION",
                        f"role {step.role!r} would verify its own step {dep!r}",
                        step.key,
                    )
                )
