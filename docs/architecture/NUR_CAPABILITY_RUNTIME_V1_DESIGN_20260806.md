# NUR CAPABILITY RUNTIME V1 — ARCHITECTURAL DESIGN

**Document ID:** `docs/architecture/NUR_CAPABILITY_RUNTIME_V1_DESIGN_20260806.md`  
**Authored Date:** 2026-08-06  
**Status:** PROPOSED ARCHITECTURE & IMPLEMENTATION SPECIFICATION  
**Author:** Antigravity AI Engine & NUR Engineering Team  
**Scope:** Mind Plane → Brain Plane → Agency Spine Integration  
**Dependencies:** No AGPL dependencies. No Agentend installation/code copying. Pure native implementation on NUR Mind↔Brain↔Agency architecture.

---

## 1. Executive Summary & Architecture Invariants

The NUR Capability Runtime introduces a structured, capability-oriented execution model into the existing **Mind → Brain → Agency** cognitive architecture. It bridges conversational intent to deterministic, policy-governed execution without compromising owner sovereignty, data isolation, or epistemic safety.

### 1.1 Non-Negotiable Invariants

1. **Talk Endpoint Authority:** The existing authenticated `/api/v1/cognition/talk` and streaming `/api/v1/cognition/talk/stream` endpoints remain the single ingress point for all conversational and cognitive interactions.
2. **Cognitive Loop Continuity:** `run_mind_cognitive_loop` in `apps/api/app/mind/cognitive_loop.py` remains the primary cognitive orchestrator.
3. **Database RLS & Owner Scope:** PostgreSQL Row-Level Security (RLS) and owner tenant isolation (`owner_user_id`) remain authoritative. No capability or worker can bypass RLS or execute cross-owner operations.
4. **Model & Event Record Reuse:** All executions reuse existing PostgreSQL tables: `model_runs`, `model_run_sources`, `cognitive_events`, `agent_workflows`, `agent_steps`, `agent_approvals`, `agent_run_events`, `agent_checkpoints`, `agent_tool_calls`, `agent_policies`, and `why_changed_records`. No duplicate run or event tables will be created.
5. **Agency Spine as Sole Mutation Path:** The existing Agency compiler (`compiler.py`), policy engine (`policy.py`), approval engine (`approvals.py`), and dispatcher (`dispatcher.py`) remain the exclusive path for durable state mutations (`R1_PRIVATE_DRAFT`, `R2_DURABLE_PRIVATE`).
6. **No Raw Chain-of-Thought Leakage:** No raw chain-of-thought (CoT) is persisted to the database or streamed to the client. Only structured decision summaries, verified claims, and typed status events are exposed.
7. **No Side Effects Outside Agency:** Mind-plane workers are strictly read-only (`R0_READ_ONLY`). Any action proposing state mutation must emit a `WorkflowProposal` to Agency.
8. **No Parallel Backend:** Single backend runtime; no second server or shadow microservice.
9. **Zero Silent Fallbacks:** The runtime refuses rather than guesses. If a capability, tool, or argument is unresolvable, it halts with an explicit error or abstains into conversational dialogue.

---

## 2. Current Architecture Audit & Findings

### 2.1 Audited Components

| Subsystem | Primary Files | Current Reality Status |
| :--- | :--- | :--- |
| **Mind Loop** | `apps/api/app/mind/cognitive_loop.py`, `context.py`, `scope.py` | PRODUCTION (22-step loop, ScopeEnvelope resolved before retrieval) |
| **Brain Plane** | `apps/api/app/brain/cognition.py`, `router.py`, `critic.py`, `prompts.py`, `schemas.py` | PRODUCTION (Provider calls, structured result schemas, BrainTrace) |
| **Metacognition** | `apps/api/app/mind/metacognition.py`, `review_strategy.py`, `meta_review.py` | PRODUCTION (11 computable checks, review strategies, bounded depth-2 meta-review) |
| **Memory Steward** | `apps/api/app/mind/memory_steward.py`, `why_changed.py`, `beliefs.py`, `user_model.py` | PRODUCTION (Governed provenance, typed claims, WhyChanged ledger) |
| **Agency Spine** | `apps/api/app/agentic/compiler.py`, `runtime.py`, `tools.py`, `registry.py`, `approvals.py`, `policy.py` | PRODUCTION (DAG compilation, exact-call approvals, tool contracts) |
| **Agency Bridge** | `apps/api/app/mind/agency_bridge.py` | **CRITICAL DEFECT DETECTED** (Silent tool fallback, untyped step arguments) |

### 2.2 Critical Vulnerability in Current `agency_bridge.py`

Inspection of `apps/api/app/mind/agency_bridge.py` (lines 30–42) revealed a silent fallback:
```python
# CURRENT IMPLEMENTATION (VULNERABLE):
for idx, step in enumerate(proposal.steps):
    step_key = f"step_{idx + 1}"
    tool_key = getattr(step, "tool_key", None) or "create_draft_plan"
    proposed_steps.append(
        ProposedStep(
            key=step_key,
            role="SPECIALIST",
            tool_key=tool_key,
            depends_on=(),
            input_refs={"title": step.title, "description": step.description},
            rationale=step.description,
        )
    )
```

**Identified Flaws:**
1. **Silent Mapping to `create_draft_plan`:** If the Brain outputs an unknown tool key or omits `tool_key`, the code silently maps the step to `create_draft_plan`, hiding model generation failures and attempting unintended plan drafting.
2. **Untyped `input_refs`:** Input arguments are blindly set to `{"title": step.title, "description": step.description}`, ignoring the tool's actual argument schema (e.g. `schedule_timeline_event` requires `event_type`, `occurred_at`, etc.).
3. **Missing Tool Version & Lineage:** `tool_version` is not validated at the proposal stage.
4. **Missing Dependencies & Idempotency:** DAG dependencies are hardcoded to `depends_on=()`, flattening multi-step workflows. No idempotency keys or compensation actions are captured.

### 2.3 Required Remedy
The `WorkflowStep` schema and `agency_bridge.py` must be rewritten to strictly require:
- `tool_key`: Exact registered key from `app.agentic.tools.ALL_TOOLS`.
- `tool_version`: Pinned contract version string (e.g., `"1"`).
- `arguments`: Validated argument dictionary matching the tool's Pydantic schema.
- `dependencies`: Explicit list of step keys (`depends_on`).
- `risk_class`: Explicit `RiskClass` (`R0_READ_ONLY`, `R1_PRIVATE_DRAFT`, `R2_DURABLE_PRIVATE`).
- `requires_approval`: Boolean derived from policy evaluation.
- `timeout_seconds`: Pinned integer timeout.
- `estimated_cost_cents`: Cost ceiling.
- `idempotency_key`: Deterministic client/task-derived key.
- `compensation_action`: Optional undo tool key.

---

## 3. CapabilitySpec & CapabilityRegistry Architecture

### 3.1 Conceptual Model
- **Tools (`ToolContract`):** Low-level deterministic primitives (e.g. `get_plan`, `create_draft_plan`, `schedule_timeline_event`).
- **Capabilities (`CapabilitySpec`):** High-level cognitive competencies (e.g., `plan_from_conversation`, `deep_research`, `reflect_and_synthesize`). A capability defines intent patterns, required permissions, context hydration recipes, worker specifications, and output schemas.

```
       ┌──────────────────────────────────────────────────────────┐
       │                     CAPABILITY SPEC                      │
       │  (Intent Patterns + Scope Rules + Hydration Recipe + DAG) │
       └────────────────────────────┬─────────────────────────────┘
                                    │
             ┌──────────────────────┴──────────────────────┐
             ▼                                             ▼
┌─────────────────────────┐                   ┌─────────────────────────┐
│   READ-ONLY WORKER DAG  │                   │    WORKFLOW PROPOSAL    │
│  (Pure R0 Tool Calls)   │                   │ (Agency Spine R1/R2 DAG)│
└─────────────────────────┘                   └─────────────────────────┘
```

### 3.2 Python Schema: `CapabilitySpec`

```python
# apps/api/app/mind/capabilities/schemas.py
from __future__ import annotations

import enum
from typing import Any
from pydantic import BaseModel, Field


class ExecutionMode(enum.StrEnum):
    READ_ONLY_WORKER = "READ_ONLY_WORKER"
    COGNITIVE_SYNTHESIS = "COGNITIVE_SYNTHESIS"
    WORKFLOW_PROPOSAL = "WORKFLOW_PROPOSAL"
    HYBRID = "HYBRID"


class ContextHydrationRecipe(BaseModel):
    """Declarative specification of data layers required by a capability."""
    include_workspace_frame: bool = True
    hybrid_retrieval_limit: int = 6
    required_record_classes: list[str] = Field(default_factory=list)
    required_entity_types: list[str] = Field(default_factory=list)
    fetch_orbit_context: bool = False
    fetch_active_plans: bool = False
    fetch_timeline_window_days: int = 0
    max_context_tokens: int = 4000


class CapabilitySpec(BaseModel):
    """Specification of a discrete cognitive capability."""
    capability_id: str = Field(..., description="Unique slug, e.g., 'capability:plan_from_conversation'")
    name: str
    description: str
    intent_signatures: list[str] = Field(
        ..., description="Exemplar phrases used for semantic similarity matching"
    )
    allowed_surfaces: list[str] = Field(
        default_factory=lambda: ["talk"],
        description="Surfaces where this capability is permitted ('talk', 'plan', 'research', etc.)"
    )
    sensitivity_ceiling: str = Field(
        default="NORMAL",
        description="Maximum sensitivity allowed ('LOW', 'NORMAL', 'ELEVATED', 'HIGH')"
    )
    execution_mode: ExecutionMode
    required_tools: list[str] = Field(
        default_factory=list,
        description="Tool keys from app.agentic.tools.ALL_TOOLS required during execution"
    )
    worker_role: str = Field(default="SPECIALIST")
    hydration_recipe: ContextHydrationRecipe = Field(default_factory=ContextHydrationRecipe)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    min_confidence_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    timeout_seconds: int = Field(default=30, gt=0)
    estimated_cost_cents: float = Field(default=0.0, ge=0.0)
    abstention_prompt: str = Field(
        default="I notice you may want a plan, but I need more details before drafting one."
    )
```

### 3.3 The Capability Registry

```python
# apps/api/app/mind/capabilities/registry.py
from __future__ import annotations

from typing import Iterable
from app.agentic.registry import spec as get_tool_spec, UnknownToolError
from app.mind.capabilities.schemas import CapabilitySpec


class DuplicateCapabilityError(RuntimeError):
    """Raised when two specs register the same capability_id."""


class InvalidCapabilitySpecError(ValueError):
    """Raised when a CapabilitySpec references unknown tools or invalid configuration."""


class CapabilityRegistry:
    """In-memory validated catalog of all first-party NUR capabilities."""

    def __init__(self) -> None:
        self._specs: dict[str, CapabilitySpec] = {}

    def register(self, capability: CapabilitySpec) -> None:
        if capability.capability_id in self._specs:
            raise DuplicateCapabilityError(f"Duplicate capability registered: {capability.capability_id}")
        
        # Verify that all declared required tools exist in the Agency registry
        for tool_key in capability.required_tools:
            try:
                get_tool_spec(tool_key)
            except UnknownToolError as exc:
                raise InvalidCapabilitySpecError(
                    f"Capability '{capability.capability_id}' references unknown tool '{tool_key}'"
                ) from exc

        self._specs[capability.capability_id] = capability

    def get(self, capability_id: str) -> CapabilitySpec:
        if capability_id not in self._specs:
            raise KeyError(f"Unknown capability: {capability_id}")
        return self._specs[capability_id]

    def all(self) -> list[CapabilitySpec]:
        return list(self._specs.values())

    def filter_by_surface_and_scope(self, surface: str, sensitivity: str) -> list[CapabilitySpec]:
        return [
            cap for cap in self._specs.values()
            if surface in cap.allowed_surfaces and self._sensitivity_allowed(cap.sensitivity_ceiling, sensitivity)
        ]

    @staticmethod
    def _sensitivity_allowed(cap_ceiling: str, current_sensitivity: str) -> bool:
        order = {"LOW": 1, "NORMAL": 2, "ELEVATED": 3, "HIGH": 4}
        return order.get(cap_ceiling, 2) >= order.get(current_sensitivity, 2)
```

---

## 4. Constrained CapabilityResolver (Intent, Confidence & Abstention)

### 4.1 Resolution Algorithm
The `CapabilityResolver` matches user input against registered capabilities using a deterministic 3-tier evaluator:
1. **Scope & Sensitivity Filter:** Prunes capabilities incompatible with the `ScopeEnvelope` surface, sharing boundary, or sensitivity level.
2. **Deterministic Intent Classifier:** Evaluates linguistic triggers, structured parameters, and task modes (`mode: "plan"`, `mode: "research"`).
3. **Confidence Scoring & Threshold Gate:**
   - Confidence $\ge \text{min\_confidence\_threshold}$ (default 0.75): Resolve capability.
   - Confidence $< 0.75$: **Abstain**. Fall back to standard conversational dialogue (`DIRECT_TALK`) with typed uncertainty (`UncertaintyKind.INSUFFICIENT_EVIDENCE`).
   - If user input matches a forbidden domain (medical, financial advice, password exfiltration): **Refuse** (`REFUSE_SCOPE`).

### 4.2 Python Schema: `CapabilityResolution`

```python
# apps/api/app/mind/capabilities/resolver.py
from __future__ import annotations

import enum
from typing import Any
from pydantic import BaseModel, Field
from app.brain.schemas import UncertaintyKind
from app.mind.capabilities.schemas import CapabilitySpec


class ResolutionFallbackMode(enum.StrEnum):
    DIRECT_TALK = "DIRECT_TALK"
    CLARIFY_QUESTION = "CLARIFY_QUESTION"
    REFUSE_SCOPE = "REFUSE_SCOPE"


class CapabilityResolution(BaseModel):
    """The auditable result of intent evaluation."""
    selected_capability: CapabilitySpec | None = None
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    abstained: bool = False
    abstention_reason: str | None = None
    fallback_mode: ResolutionFallbackMode = ResolutionFallbackMode.DIRECT_TALK
    extracted_parameters: dict[str, Any] = Field(default_factory=dict)
    uncertainty_kind: UncertaintyKind | None = None
```

---

## 5. Progressive Context Hydration with ScopeEnvelope

Context hydration avoids the "everything-in-prompt" anti-pattern by progressively fetching only what the resolved capability requires, bounded by the `ScopeEnvelope`.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        PROGRESSIVE HYDRATION                           │
├────────────────────────────────────────────────────────────────────────┤
│ Layer 0: Scope & Privileged Identity Snapshot (0 DB reads, static)    │
│ Layer 1: Working Memory & Active Workspace Frame (1 read, ~400 tokens) │
│ Layer 2: Scoped Hybrid Retrieval (Reranked Top-k, ~1,200 tokens)       │
│ Layer 3: Capability-Specific Entities (e.g. Plan snapshot, Orbit)     │
│ Layer 4: Worker Intermediate Result Hydration (Read-only execution)    │
└────────────────────────────────────────────────────────────────────────┘
```

### 5.1 Hydration Step Implementation
1. **Layer 0 (Identity):** Frozen `IdentitySnapshot` loaded directly from `apps/api/app/mind/identity.py`.
2. **Layer 1 (Working Memory):** Frame state loaded from `app.omega.workspace_service.build_workspace_frame`.
3. **Layer 2 (Hybrid Retrieval):** `retrieve_hybrid` executed with query text and `ScopeEnvelope` filters.
4. **Layer 3 (Targeted Capability Fetch):**
   - If `CapabilitySpec.hydration_recipe.fetch_active_plans` is True, fetch active plan IDs for the orbit.
   - If `CapabilitySpec.hydration_recipe.fetch_timeline_window_days > 0`, fetch timeline events for that bounded window.
5. **Context Manifest Enforcement:** All included and excluded items are recorded in `ContextManifest`. If token count exceeds `max_context_tokens`, low-rank snippets are excluded and recorded in `excluded`.

---

## 6. Typed WorkerSpec & Read-Only Worker Runtime

### 6.1 Worker Safety Contract
Mind workers are strictly read-only orchestrators. They execute in-process within an RLS-scoped database session and can only invoke tools in `app.agentic.tools.READ_ONLY` (`R0_READ_ONLY`).

```python
# apps/api/app/mind/workers/schemas.py
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class WorkerSpec(BaseModel):
    worker_key: str
    role: str = "SPECIALIST"  # "RESEARCHER", "ANALYST", "PLANNER", "SYNTHESIZER"
    allowed_tools: tuple[str, ...]
    max_turns: int = 1
    timeout_seconds: int = 20
    token_budget: int = 2000
    cost_ceiling_cents: float = 2.0


class WorkerResult(BaseModel):
    worker_key: str
    role: str
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    tool_calls_executed: list[dict[str, Any]] = Field(default_factory=list)
    duration_ms: int = 0
    error_code: str | None = None
    error_message: str | None = None
```

### 6.2 Worker Execution Engine
```python
# apps/api/app/mind/workers/runtime.py
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.registry import handler as get_tool_handler
from app.agentic.tools import READ_ONLY
from app.mind.workers.schemas import WorkerSpec, WorkerResult

READ_ONLY_KEYS = frozenset(t.contract.key for t in READ_ONLY)


async def execute_read_only_worker(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    worker_spec: WorkerSpec,
    task_input: dict[str, Any],
) -> WorkerResult:
    """Executes a bounded, read-only worker using registered R0 handlers."""
    start_time = time.monotonic()
    
    # Verify all tools in worker spec are strictly R0
    for tool_key in worker_spec.allowed_tools:
        if tool_key not in READ_ONLY_KEYS:
            return WorkerResult(
                worker_key=worker_spec.worker_key,
                role=worker_spec.role,
                success=False,
                error_code="ILLEGAL_MUTATING_TOOL",
                error_message=f"Tool '{tool_key}' is not R0_READ_ONLY. Workers cannot execute mutating tools.",
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )

    tool_calls_record = []
    output_data: dict[str, Any] = {}

    try:
        async with asyncio.timeout(worker_spec.timeout_seconds):
            for tool_key in worker_spec.allowed_tools:
                fn = get_tool_handler(tool_key)
                args = task_input.get(tool_key, {})
                tool_res = await fn(db, owner_user_id, **args)
                tool_calls_record.append({"tool_key": tool_key, "status": "SUCCESS"})
                output_data[tool_key] = tool_res

        return WorkerResult(
            worker_key=worker_spec.worker_key,
            role=worker_spec.role,
            success=True,
            data=output_data,
            tool_calls_record=tool_calls_record,
            duration_ms=int((time.monotonic() - start_time) * 1000),
        )
    except TimeoutError:
        return WorkerResult(
            worker_key=worker_spec.worker_key,
            role=worker_spec.role,
            success=False,
            error_code="WORKER_TIMEOUT",
            error_message=f"Worker timed out after {worker_spec.timeout_seconds}s",
            duration_ms=int((time.monotonic() - start_time) * 1000),
        )
    except Exception as exc:
        return WorkerResult(
            worker_key=worker_spec.worker_key,
            role=worker_spec.role,
            success=False,
            error_code="WORKER_EXECUTION_ERROR",
            error_message=str(exc),
            duration_ms=int((time.monotonic() - start_time) * 1000),
        )
```

---

## 7. Capability Execution DAG

For complex capabilities requiring multiple read workers (e.g. `deep_research` combining map neighbourhood and timeline retrieval), the Mind plane executes a DAG of read tasks before passing the consolidated evidence into the Brain synthesizer.

```
                  ┌──────────────────────┐
                  │ Capability Resolution│
                  └──────────┬───────────┘
                             │
            ┌────────────────┴────────────────┐
            ▼                                 ▼
   ┌─────────────────┐               ┌─────────────────┐
   │ Worker A (Map)  │               │Worker B (Timeline)
   └────────┬────────┘               └────────┬────────┘
            │                                 │
            └────────────────┬────────────────┘
                             ▼
                  ┌──────────────────────┐
                  │ Evidence Aggregator  │
                  └──────────┬───────────┘
                             ▼
                  ┌──────────────────────┐
                  │   Brain Synthesizer  │
                  └──────────────────────┘
```

1. **DAG Representation:** Set of `WorkerNode` definitions with `node_id` and `depends_on`.
2. **Topological Execution:** Resolves dependencies concurrently using `asyncio.gather` for independent stages.
3. **Cycle Rejection:** Reuses the Kahn's algorithm implementation from `app.agentic.compiler.topological_order`.

---

## 8. Brain, Critic & Metacognitive Integration

When capability data is hydrated and read-workers have finished, the resulting bundle is compiled into the `CognitiveTaskPacket` for the Brain:

1. **Profile Routing:** Fast/Balanced/Deep selected by `apps/api/app/brain/router.py`.
2. **Brain Execution:** `run_brain_step` invokes provider with structured `output_schema`.
3. **Critic Pass:** `evaluate_brain_result` checks for grounding against `ContextManifest`.
4. **Metacognition Review:** `run_metacognitive_review` executes 11 computable checks:
   - `privacy_scope_preserved`
   - `no_forbidden_claims`
   - `state_mutation_safety`
   - `no_raw_cot`
   - `capability_truth`
   - `scope_envelope_enforced`
   - + 5 standard grounding and consistency checks.
5. **Verdict Gate:** If Metacognition or Verification returns `BLOCK`, the loop cancels proposal submission and raises `AIOutputValidationError`.

---

## 9. Explicit WorkflowProposal → Agency Handoff

### 9.1 The Fixed `WorkflowStep` & `WorkflowProposal` Schema

```python
# apps/api/app/brain/schemas.py (MODIFICATIONS)

class WorkflowStepProposal(BaseModel):
    """A fully typed, validated step proposal for the Agency Spine."""
    key: str = Field(..., description="Unique step key within the workflow, e.g. 'step_1'")
    title: str
    description: str
    tool_key: str = Field(..., description="Exact tool key matching app.agentic.tools.ALL_TOOLS")
    tool_version: str = Field(default="1", description="Pinned tool contract version")
    role: str = Field(default="SPECIALIST", description="Agent role (OPERATOR, RESEARCHER, etc.)")
    arguments: dict[str, Any] = Field(..., description="Validated tool arguments matching tool input schema")
    depends_on: list[str] = Field(default_factory=list, description="Step keys this step depends on")
    risk_class: str = Field(..., description="R0_READ_ONLY, R1_PRIVATE_DRAFT, or R2_DURABLE_PRIVATE")
    requires_approval: bool = Field(default=True)
    timeout_seconds: int = Field(default=30, gt=0)
    estimated_cost_cents: float = Field(default=0.0, ge=0.0)
    idempotency_key: str = Field(..., description="Deterministic idempotency key for this step execution")
    compensation_action: str | None = Field(
        default=None, description="Optional tool_key for rollback/compensation"
    )


class WorkflowProposal(BaseModel):
    """Durable workflow proposal crossing from Brain/Mind into Agency."""
    proposal_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    task_id: uuid.UUID
    title: str
    rationale: str
    steps: list[WorkflowStepProposal] = Field(..., min_length=1)
    total_estimated_cost_cents: float = Field(default=0.0, ge=0.0)
    requires_owner_approval: bool = True
```

### 9.2 The Refactored `apps/api/app/mind/agency_bridge.py`

```python
# apps/api/app/mind/agency_bridge.py (REFACTORED)
from __future__ import annotations

import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.compiler import ProposedStep, compile_plan, CompileResult
from app.agentic.enums import StepState
from app.agentic.policy_store import load_policy
from app.agentic.registry import spec as get_tool_spec, UnknownToolError
from app.brain.schemas import WorkflowProposal
from app.models.agentic import AgentWorkflow, AgentStep, AgentApproval


class AgencyBridgeError(Exception):
    """Raised when a proposal cannot be submitted or compiled."""


async def submit_workflow_proposal(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    proposal: WorkflowProposal,
    orbit_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
) -> tuple[AgentWorkflow, CompileResult]:
    """Strictly maps a WorkflowProposal into the Agency Spine with zero silent fallbacks."""
    
    proposed_steps: list[ProposedStep] = []
    
    for step in proposal.steps:
        # Strict tool validation: No silent default to create_draft_plan!
        if not step.tool_key:
            raise AgencyBridgeError(f"Step '{step.key}' is missing required 'tool_key'.")
        
        try:
            tool_spec = get_tool_spec(step.tool_key)
        except UnknownToolError as exc:
            raise AgencyBridgeError(
                f"Step '{step.key}' references undeclared tool '{step.tool_key}'."
            ) from exc

        proposed_steps.append(
            ProposedStep(
                key=step.key,
                role=step.role,
                tool_key=step.tool_key,
                depends_on=tuple(step.depends_on),
                input_refs=step.arguments,
                rationale=step.description or step.title,
            )
        )

    policy = await load_policy(db, owner_user_id=owner_user_id, orbit_id=orbit_id, project_id=project_id)
    compile_result = compile_plan(tuple(proposed_steps), policy)

    if not compile_result.ok or not compile_result.steps:
        err_msg = "; ".join(f"[{e.code}] {e.message}" for e in compile_result.errors)
        raise AgencyBridgeError(f"Workflow compilation failed: {err_msg}")

    requires_approval = any(s.approval_required for s in compile_result.steps)
    initial_state = "BLOCKED_ON_APPROVAL" if requires_approval else "READY"

    # Persist durable AgentWorkflow
    workflow = AgentWorkflow(
        owner_user_id=owner_user_id,
        kind="COGNITIVE_WORKFLOW",
        title=proposal.title,
        objective=proposal.rationale,
        state=initial_state,
        plan_version=1,
        trigger_kind="MIND_COGNITIVE_RESULT",
        trigger_ref=proposal.task_id,
        initiative_level="SUGGEST",
        scope="PRIVATE",
        orbit_id=orbit_id,
        project_id=project_id,
        budget_cents=int(proposal.total_estimated_cost_cents),
        cost_cents=0,
        max_risk_class=max((s.risk_class for s in compile_result.steps), default="R1_PRIVATE_DRAFT"),
    )
    db.add(workflow)
    await db.flush()

    for compiled_step in compile_result.steps:
        step_state = StepState.BLOCKED if compiled_step.approval_required else StepState.READY
        db_step = AgentStep(
            owner_user_id=owner_user_id,
            workflow_id=workflow.id,
            ordinal=compiled_step.ordinal,
            key=compiled_step.key,
            role=compiled_step.role,
            tool_key=compiled_step.tool_key,
            tool_version=compiled_step.tool_version,
            risk_class=compiled_step.risk_class,
            requested_capabilities=list(compiled_step.requested_capabilities),
            depends_on=list(compiled_step.depends_on),
            state=step_state.value,
            input_refs=compiled_step.input_refs,
            timeout_seconds=compiled_step.timeout_seconds,
        )
        db.add(db_step)
        await db.flush()

        if compiled_step.approval_required:
            from app.agentic.orchestrator import argument_digest
            digest_str = argument_digest(compiled_step.tool_key, compiled_step.tool_version, compiled_step.input_refs)
            db_approval = AgentApproval(
                owner_user_id=owner_user_id,
                workflow_id=workflow.id,
                step_id=db_step.id,
                tool_key=compiled_step.tool_key,
                tool_version=compiled_step.tool_version,
                argument_digest=digest_str,
                plan_version=1,
                call_version="1",
                redacted_arguments=compiled_step.input_refs,
                rationale=compiled_step.input_refs.get("description", compiled_step.key),
                risk_class=compiled_step.risk_class,
                decision="PENDING",
            )
            db.add(db_approval)

    await db.flush()
    return workflow, compile_result
```

---

## 10. Typed SSE Event Stream & AG-UI Compatibility Layer

### 10.1 Complete SSE Event Vocabulary (Version 1.0)

| Event Name | Emitted At | Data Payload Structure |
| :--- | :--- | :--- |
| `talk.scope.resolved` | Step 1 | `{"scope_id": str, "sharing_boundary": str, "surface": str}` |
| `talk.capability.resolved` | Step 2 | `{"capability_id": str, "confidence": float, "abstained": bool}` |
| `talk.context.hydrated` | Step 6 | `{"manifest_digest": str, "token_count": int, "included_count": int}` |
| `talk.accepted` | Step 7 | `{"turn_event_id": str, "model_run_id": str}` |
| `talk.worker.started` | Read Worker | `{"worker_key": str, "role": str}` |
| `talk.worker.completed` | Read Worker | `{"worker_key": str, "duration_ms": int, "success": bool}` |
| `talk.chunk` | Brain Stream | `{"text": str, "is_final": bool}` |
| `talk.validated` | Step 12 | `{"model_run_id": str, "response_event_id": str, "verdict": "PASS"\|"WARN"\|"BLOCK"}` |
| `memory.candidate` | Step 14 | `{"candidate_id": str, "status": str, "requires_owner_approval": bool}` |
| `workflow.proposed` | Step 17 | `{"workflow_id": str, "state": str, "step_count": int, "requires_approval": bool}` |
| `talk.failed` | On Error | `{"code": str, "retryable": bool, "reason": str}` |
| `talk.cancelled` | On Cancel | `{"model_run_id": str, "reason": str}` |

### 10.2 AG-UI (Agentic UI) Adapter
An AG-UI compatibility adapter in `packages/shared-types` transforms raw SSE streams into rich client-side UI states:
- **Thinking / Hydrating Indicator:** Triggered by `talk.scope.resolved` and `talk.capability.resolved`.
- **Streaming Markdown View:** Fed by delta tokens in `talk.chunk`.
- **Workflow Approval Modal:** Automatically populated when `workflow.proposed` emits `requires_approval: true`.
- **Memory Review Banner:** Renders candidate approvals from `memory.candidate`.

---

## 11. Budgets, Timeouts, Leases & Graceful Degradation

1. **Daily AI Budget Gate:** `assert_daily_ai_budget(db, owner_user_id)` is invoked at the very start of `run_mind_cognitive_loop`. If exceeded, raises `AIRequestBudgetExceeded` (HTTP 429).
2. **Worker Timeouts:** Every worker execution runs inside `asyncio.timeout(worker_spec.timeout_seconds)`.
3. **Step Leases in Agency Spine:** Agency worker claims use `lease_expires_at = now() + interval` and fenced `execution_attempt` UUIDs to avoid zombie workers or double executions.
4. **Graceful Degradation Tree:**
   - If Capability Resolution fails $\rightarrow$ Fall back to `DIRECT_TALK`.
   - If Read-Worker times out $\rightarrow$ Omit that worker's slice, log `UncertaintyKind.STALE_EVIDENCE`, proceed with baseline hybrid retrieval.
   - If Critic or Metacognition blocks $\rightarrow$ Suppress model claims, return safe fallback direct response with explanation.

---

## 12. Observability, Lineage & Privacy-Preserving Telemetry

### 12.1 Lineage Identifier Chain
Every cognitive run produces an unbroken audit chain:
$$\text{request\_id} \longrightarrow \text{scope\_envelope\_id} \longrightarrow \text{turn\_event\_id} \longrightarrow \text{model\_run\_id} \longrightarrow \text{workflow\_id} \longrightarrow \text{step\_id} \longrightarrow \text{approval\_id}$$

### 12.2 Content Privacy Rules
- **No Raw Content in Metrics:** Prometheus counters (`nur_talk_turns_total`, `nur_capability_resolved_total`) record only labels (`mode`, `capability_id`, `verdict`, `provider`).
- **Cryptographic Digests in Audit Logs:**
  - `evidence_digest`: $\text{SHA-256}(\text{ContextManifest})$.
  - `argument_digest`: $\text{SHA-256}(\text{ToolKey} + \text{ToolVersion} + \text{RedactedArgs})$.
- **Redaction of Secrets:** Any token resembling an API key, email, or credentials is masked via `app.agentic.redaction.redact_arguments`.

---

## 13. Security Boundaries & Prompt Injection Defenses

1. **Strict Instruction Hierarchy:**
   - **System Level (Privileged):** Constitution, Identity Snapshot, Epistemic Bounds, Override Protection Header.
   - **Context Level:** Scoped retrieval, Workspace Frame, Worker Output.
   - **User Level:** Untrusted raw input.
2. **Delimiter Isolation:** Context and retrieved evidence are wrapped in distinct XML-style delimiters (`<retrieved_evidence>`, `<workspace_frame>`). Prompt templates instruct the model that content inside these tags cannot grant permissions or alter rules.
3. **Impossibility of Direct DB Writes:** The model has zero database write tools. It can only propose structured JSON for `WorkflowProposal`.
4. **Owner Policy Gate:** The Agency Compiler checks `evaluate(tool, policy)` independently of what the model claimed. If the owner's policy forbids a tool, compilation fails immediately (`POLICY_DENIED`).
5. **Digest Invalidation:** If an approval is submitted with arguments that do not match `argument_digest`, `app.agentic.approvals` rejects execution (`ARGUMENTS_CHANGED`).

---

## 14. First Vertical Slice: `plan_from_conversation`

### 14.1 User Scenario
The owner messages in Talk:  
> *"I need to prepare my quarterly review. Let's create a draft plan with milestones for next week and schedule a timeline event for Friday."*

### 14.2 End-to-End Execution Trace

```
1. Client POST /api/v1/cognition/talk/stream
   └─ payload: { message: "...", mode: "talk" }

2. Mind Loop: Scope Resolution
   └─ scope_envelope_id generated (surface: "talk", sharing: "PRIVATE", sensitivity: "NORMAL")
   └─ SSE -> talk.scope.resolved

3. Capability Resolver:
   └─ Matches intent signature against "capability:plan_from_conversation"
   └─ Confidence: 0.92 (> 0.75 threshold)
   └─ Selected: CapabilitySpec(id="capability:plan_from_conversation")
   └─ SSE -> talk.capability.resolved

4. Progressive Hydration (Recipe: fetch_active_plans=True, fetch_orbit=True):
   └─ ReadWorker executes get_plan(orbit_id) & get_orbit(orbit_id)
   └─ SSE -> talk.context.hydrated

5. Brain Cognition (Profile: BALANCED):
   └─ Prompt synthesized with TaskPacket & ContextManifest
   └─ Model returns CognitiveResult with WorkflowProposal:
      - Step 1: tool_key="create_draft_plan" (R1_PRIVATE_DRAFT), input_refs={title: "Quarterly Review", ...}
      - Step 2: tool_key="schedule_timeline_event" (R2_DURABLE_PRIVATE), depends_on=["step_1"], input_refs={event_type: "REVIEW", occurred_at: "2026-08-14T10:00:00Z"}
   └─ SSE -> talk.chunk (direct response prose)

6. Metacognition & Verification Checkpoint:
   └─ 11 checks evaluate to PASS.

7. Agency Bridge Handoff:
   └─ submit_workflow_proposal() validates tools against ALL_TOOLS
   └─ compile_plan() builds DAG: step_1 (READY), step_2 (BLOCKED, depends on step_1)
   └─ Policy Engine flags step_2 as REQUIRE_APPROVAL (R2 risk)
   └─ Inserts AgentWorkflow (BLOCKED_ON_APPROVAL), AgentStep (x2), AgentApproval (x1 with argument_digest)
   └─ SSE -> workflow.proposed { workflow_id: "...", requires_approval: true }

8. ModelRun Completed & Committed:
   └─ TalkTurnOut persisted with all evidence and lineage digests.
```

---

## 15. Exact Python Schemas & Module Boundaries

### 15.1 New/Modified Mind Plane Schemas (`apps/api/app/mind/capabilities/`)

```
apps/api/app/mind/capabilities/
├── __init__.py
├── schemas.py       # CapabilitySpec, ContextHydrationRecipe, ExecutionMode
├── registry.py      # CapabilityRegistry, catalog indexing & validation
├── resolver.py      # CapabilityResolver, intent matching & abstention logic
└── definitions/
    ├── __init__.py
    ├── plan_from_conversation.py   # Spec for slice 1
    ├── deep_research.py            # Spec for slice 2
    └── summarize_day.py            # Spec for slice 3
```

### 15.2 New Mind Workers Runtime (`apps/api/app/mind/workers/`)

```
apps/api/app/mind/workers/
├── __init__.py
├── schemas.py       # WorkerSpec, WorkerResult
├── runtime.py       # execute_read_only_worker (RLS bounded, R0 only)
└── dag.py           # Multi-worker async DAG executor
```

---

## 16. Exact File Impact & Proposed File Tree

### 16.1 Impacted Existing Files

| File Path | Nature of Change | Rationale |
| :--- | :--- | :--- |
| `apps/api/app/brain/schemas.py` | **MODIFY** | Replace `WorkflowStep` with typed `WorkflowStepProposal` (tool_version, arguments, dependencies, idempotency_key). |
| `apps/api/app/mind/agency_bridge.py` | **MODIFY** | Remove silent fallback to `create_draft_plan`. Add strict validation, argument passing, and compilation error propagation. |
| `apps/api/app/mind/cognitive_loop.py` | **MODIFY** | Wire `CapabilityResolver`, emit `talk.capability.resolved` SSE, pass capability context to Brain. |
| `apps/api/app/mind/context.py` | **MODIFY** | Incorporate capability hydration recipe into `build_cognitive_task_packet`. |
| `apps/api/app/cognition/streaming.py` | **MODIFY** | Add `talk.capability.resolved`, `talk.context.hydrated`, `talk.worker.*` events to `TalkStreamCoordinator`. |
| `packages/shared-types/src/index.ts` | **MODIFY** | Add `CapabilitySpecView`, `CapabilityResolutionView`, and updated `TalkSSEEventData` types. |

### 16.2 New Files to Create

```
apps/api/app/mind/capabilities/__init__.py
apps/api/app/mind/capabilities/schemas.py
apps/api/app/mind/capabilities/registry.py
apps/api/app/mind/capabilities/resolver.py
apps/api/app/mind/capabilities/definitions/__init__.py
apps/api/app/mind/capabilities/definitions/plan_from_conversation.py
apps/api/app/mind/workers/__init__.py
apps/api/app/mind/workers/schemas.py
apps/api/app/mind/workers/runtime.py
apps/api/app/mind/workers/dag.py
apps/api/app/tests/test_capabilities_registry.py
apps/api/app/tests/test_capability_resolver.py
apps/api/app/tests/test_read_only_workers.py
apps/api/app/tests/test_agency_bridge_strict.py
apps/api/app/tests/test_plan_from_conversation_slice.py
```

---

## 17. Database Reuse & Migration Impact

### 17.1 Zero Schema Churn Guarantee
No new database tables are required. The Capability Runtime leverages the existing robust schema:
- **`model_runs`**: Stores capability resolution and worker execution metadata in `run_metadata`.
- **`cognitive_events`**: Stores user turn and model responses with `structured_payload`.
- **`agent_workflows`**: Holds compiled workflows triggered by `MIND_COGNITIVE_RESULT`.
- **`agent_steps`**: Holds DAG steps with `tool_key`, `tool_version`, `input_refs`, and `risk_class`.
- **`agent_approvals`**: Holds exact-call approvals bound by `argument_digest`.
- **`why_changed_records`**: Captures change provenance.

**Migration Requirements:** 0 new migrations required. All models and tables are 100% reused.

---

## 18. Frontend TypeScript Contract & AG-UI State Machine

```typescript
// packages/shared-types/src/index.ts (ADDITIONS)

export interface CapabilitySpecView {
  capability_id: string;
  name: string;
  description: string;
  allowed_surfaces: string[];
  sensitivity_ceiling: string;
  estimated_cost_cents: number;
}

export interface CapabilityResolutionView {
  capability_id: string | null;
  confidence: number;
  abstained: boolean;
  abstention_reason: string | null;
}

export interface WorkflowStepProposalView {
  key: string;
  title: string;
  description: string;
  tool_key: string;
  tool_version: string;
  risk_class: string;
  requires_approval: boolean;
  arguments: Record<string, unknown>;
  dependencies: string[];
}

export interface WorkflowProposalView {
  proposal_id: string;
  task_id: string;
  title: string;
  rationale: string;
  steps: WorkflowStepProposalView[];
  total_estimated_cost_cents: number;
  requires_owner_approval: boolean;
}
```

---

## 19. Security Test Matrix & Verification Strategy

| Test Suite | Scenario Tested | Expected Result |
| :--- | :--- | :--- |
| `test_capabilities_registry.py` | Register capability referencing unknown tool | Fails at startup with `InvalidCapabilitySpecError` |
| `test_capability_resolver.py` | Low-confidence query ($<0.75$) | Abstains with `DIRECT_TALK` and `UncertaintyKind.INSUFFICIENT_EVIDENCE` |
| `test_capability_resolver.py` | Query exceeding Scope sensitivity ceiling | Filtered out; capability is not offered |
| `test_read_only_workers.py` | Worker configured with mutating tool (`activate_plan`) | Rejection with `ILLEGAL_MUTATING_TOOL` |
| `test_read_only_workers.py` | Worker execution exceeds timeout | Halts cleanly with `WORKER_TIMEOUT` |
| `test_agency_bridge_strict.py` | Proposal with missing or empty `tool_key` | Raises `AgencyBridgeError` (no silent `create_draft_plan` fallback) |
| `test_agency_bridge_strict.py` | Proposal with cyclic step dependencies | Compiler catches and refuses with `CYCLIC_PLAN` |
| `test_agency_bridge_strict.py` | Mutated step payload after approval | `argument_digest` mismatch causes `ResumeRefusal.ARGUMENTS_CHANGED` |
| `test_plan_from_conversation.py` | Full vertical slice execution | End-to-end trace completes, produces valid workflow & approval rows |

---

## 20. Acceptance Criteria & Stacked PR Execution Plan

### 20.1 Acceptance Criteria
1. **Zero Silent Fallbacks:** No code path exists that maps unknown tools to `create_draft_plan`.
2. **Capability Validation:** All capabilities registered in `CapabilityRegistry` reference validated tools.
3. **Intent Abstention:** Unambiguous conversational turns (confidence $<0.75$) do not trigger workers or workflows.
4. **Pure Read-Only Workers:** Worker runtime strictly denies non-R0 tools.
5. **Digest Integrity:** Exact-call argument digests are computed and verified before Agency approval.
6. **Test Coverage:** $\ge 95\%$ unit test coverage across all new capability modules with zero regressions in existing test suite (145/145 passing).

### 20.2 Stacked PR Execution Plan

```
PR 1: CapabilitySpec, Registry & Schema Hardening
  ├─ Update WorkflowStepProposal schema in app/brain/schemas.py
  ├─ Fix agency_bridge.py to remove silent create_draft_plan fallback
  ├─ Implement CapabilitySpec and CapabilityRegistry in app/mind/capabilities/
  └─ Tests: test_capabilities_registry.py, test_agency_bridge_strict.py

PR 2: CapabilityResolver & Progressive Context Hydration
  ├─ Implement CapabilityResolver with confidence scoring & abstention
  ├─ Implement progressive hydration in app/mind/context.py
  └─ Tests: test_capability_resolver.py

PR 3: Read-Only Worker Runtime & Execution DAG
  ├─ Implement execute_read_only_worker and DAG runner in app/mind/workers/
  ├─ Enforce R0_READ_ONLY constraints
  └─ Tests: test_read_only_workers.py

PR 4: First Vertical Slice (plan_from_conversation) & SSE Integration
  ├─ Register plan_from_conversation definition
  ├─ Integrate into run_mind_cognitive_loop with talk.capability.resolved SSE event
  ├─ Update shared-types package
  └─ Tests: test_plan_from_conversation_slice.py, full vertical slice regression
```

---
*End of Design Document.*
