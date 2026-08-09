## Phase 14 — Learning candidate pipeline

### Objective

Turn outcomes and corrections into reviewed improvement proposals.

### Implement

- candidate tables;
- provenance/privacy review;
- dataset registry;
- evaluation runner;
- prompt/route/retrieval candidate changes;
- deployment registry;
- rollback.

### Tests

- private data excluded globally;
- poisoned candidate rejected;
- eval regression blocks;
- canary rollback;
- why-model-changed.

## Phase 15 — Model customization experiments

### Entry criteria

Only after:

- sufficient high-quality consented data;
- stable frozen evaluations;
- measurable architecture-limited gap ruled out;
- budget approved;
- rollback path proven.

### Work

- SFT baseline;
- preference adapter where justified;
- optional Tinker/Inkling experiment;
- owner-specific adapter isolation;
- shadow and canary.

### Exit

A checkpoint remains `RESEARCH` until deployment evidence exists.

## Phase 16 — Reliability and interoperability

### Objective

Harden connectors, optional MCP/A2A adapters and long-running execution.

### Implement

- transport authorization;
- capability and resource binding;
- peer-agent trust policy;
- connector revocation;
- OpenTelemetry lineage;
- recovery drills;
- optional durable workflow engine evaluation without replacing working Agency primitives prematurely.

## Phase 17 — Production readiness

### Required proof

```text
full CI green
migration from released DB
security red-team
cross-owner denial
provider outage drill
connector revocation drill
workflow recovery drill
deletion propagation drill
cost cap drill
model rollback drill
owner acceptance test
```

---

# 22. File-by-file target responsibility map

This is a target responsibility map. Create a file only when the phase implements real behavior.

## 22.1 Mind

```text
apps/api/app/mind/
  schemas.py               canonical Mind contracts
  scope.py                 scope resolution and intersection
  identity.py              identity loading and version selection
  constitution.py          versioned privileged product rules
  attention.py             deterministic salience
  context.py               task packet construction
  working_memory.py        bounded retrieval packing
  user_model.py            correctable user claims
  self_model.py            server-derived capability projection
  world_model.py           entity/edge composition
  beliefs.py               belief lifecycle
  hypotheses.py            hypothesis lifecycle
  goals.py                 goal hierarchy
  intentions.py            intention arbitration
  relationships.py         interaction continuity
  memory_steward.py        memory candidate governance
  review_strategy.py       strategy selection
  metacognition.py         result review orchestration
  meta_metacognition.py    review-of-review
  reviewer_models.py       reviewer performance
  calibration.py           confidence/outcome calibration
  blind_spots.py           blind-spot registry
  epistemic_governance.py  authority and promotion rules
  cognitive_debt.py        unresolved reasoning liabilities
  strategy_change.py       versioned review changes
  why_changed.py           generic change ledger
  projection.py            surface-safe views
  redaction.py             privacy-safe representations
  cognitive_loop.py        central Mind orchestration
  agency_bridge.py         typed handoff to existing Agency
```

## 22.2 Brain

```text
apps/api/app/brain/
  schemas.py               canonical Brain contracts
  models.py                model deployment registry access
  profiles.py              executable profile policy
  router.py                deterministic eligible route
  prompts.py               privileged instruction composition
  provider.py              provider-neutral interface
  providers/openai.py      OpenAI mapping
  responses_runtime.py     direct response path
  agents_runtime.py        bounded specialist path
  cognition.py             central Brain call
  planner.py               typed plan candidate
  researcher.py            evidence acquisition/synthesis
  simulator.py             scenario comparison
  evidence_validator.py    deterministic validation
  critic.py                independent reviewer runtime
  synthesizer.py           surface result mapping
  language.py              multilingual continuity
  multimodal.py            modality adapters
  guardrails.py            pre/post validation registry
  budgets.py               token/cost/call controls
  checkpoints.py           checkpoint/deployment refs
  evaluations.py           evaluation hooks
  tracing.py               operational trace summaries
```

## 22.3 State/learning

```text
apps/api/app/learning/
  candidates.py
  provenance.py
  datasets.py
  poisoning.py
  evaluations.py
  checkpoints.py
  deployments.py
  rollback.py
```

## 22.4 Shared contracts

```text
packages/shared-types/
  cognition.ts
  mind.ts
  agency.ts
  events.ts
  learning.ts
```

## 22.5 V197 bridge

Extend existing bridge ownership, for example:

```text
apps/web/src/bridge/
  cognition-v2.ts
  approvals.ts
  memory-review.ts
  why-changed.ts

apps/web/src/v197/
  talk-intelligence-state.ts
  approval-surface.ts
  memory-review-surface.ts
  why-changed-surface.ts
```

Do not create these exact names if current bridge conventions already provide a better home.

---

# 23. Normative implementation sketches

These snippets are contracts to reconcile with repository code. They are not permission to paste blindly or introduce duplicate base classes.

## 23.1 Provider instruction envelope

```python
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class InstructionEnvelope:
    constitution_version: str
    system_instructions: tuple[str, ...]
    task_instructions: tuple[str, ...]
    owner_message: str
    evidence_blocks: tuple[dict[str, Any], ...]

    def assert_safe(self) -> None:
        if not self.constitution_version:
            raise ValueError("constitution version is required")
        for block in self.evidence_blocks:
            if block.get("trust") != "UNTRUSTED_DATA":
                raise ValueError("every evidence block must declare untrusted-data status")
```

## 23.2 Provider request and result

```python
class ModelControls(BaseModel):
    deployment_id: str
    reasoning_effort: str | None = None
    max_output_tokens: int
    timeout_seconds: int
    temperature: float | None = None
    seed: int | None = None

class ProviderRequest(BaseModel):
    request_id: UUID
    trace_id: UUID
    instruction_envelope: dict
    controls: ModelControls
    output_schema_name: str
    output_schema: dict
    tools: list[dict] = []
    metadata: dict = {}

class ProviderUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cached_input_tokens: int = 0
    estimated_cost_cents: float = 0.0

class ProviderResult(BaseModel):
    provider: str
    deployment_id: str
    response_id: str | None
    parsed_output: dict
    usage: ProviderUsage
    finish_reason: str | None
    latency_ms: int
```

## 23.3 OpenAI adapter mapping principle

```python
async def generate_structured(
    self,
    *,
    request: ProviderRequest,
    output_model: type[BaseModel],
    event_sink: EventSink | None = None,
) -> ProviderResult:
    envelope = InstructionEnvelope(**request.instruction_envelope)
    envelope.assert_safe()

    input_items = [
        {
            "role": "developer",
            "content": "\n\n".join(
                (*envelope.system_instructions, *envelope.task_instructions)
            ),
        },
        {"role": "user", "content": envelope.owner_message},
    ]

    if envelope.evidence_blocks:
        input_items.append({
            "role": "user",
            "content": render_untrusted_evidence(envelope.evidence_blocks),
        })

    payload = {
        "model": resolve_provider_model(request.controls.deployment_id),
        "input": input_items,
        "text": {"format": json_schema_format(request.output_schema)},
        "max_output_tokens": request.controls.max_output_tokens,
    }
    apply_supported_reasoning_controls(payload, request.controls)

    response = await call_with_timeout_and_classified_retry(
        payload,
        timeout_seconds=request.controls.timeout_seconds,
        event_sink=event_sink,
    )
    parsed = output_model.model_validate_json(response.output_text)
    return provider_result_from_response(response, parsed.model_dump())
```

The exact OpenAI API field names must be verified against current official documentation at implementation time. The architectural rule is separation and truthful mapping, not a frozen vendor payload.

## 23.4 Router

```python
@dataclass(frozen=True)
class RouteWeights:
    quality: float
    latency: float
    cost: float
    calibration: float

async def select_route(
    packet: CognitiveTaskPacketV2,
    registry: ModelRegistry,
    weights: RouteWeights,
) -> RouteDecision:
    candidates = await registry.eligible(
        task_class=packet.task_class,
        modality=packet.current_situation.get("modalities", ["text"]),
        privacy_policy=packet.scope.provider_policy,
        output_schema=packet.required_output_schema,
    )

    scored: list[tuple[float, ModelDeployment]] = []
    for model in candidates:
        estimate = estimate_request(model, packet)
        if estimate.cost_cents > packet.budget["max_cost_cents"]:
            continue
        if estimate.input_tokens > model.max_context_tokens:
            continue
        if not model.healthy:
            continue
        score = (
            weights.quality * model.eval_score(packet.task_class)
            - weights.latency * model.p95_latency_seconds
            - weights.cost * estimate.cost_cents
            + weights.calibration * model.calibration_score(packet.task_class)
        )
        scored.append((score, model))

    if not scored:
        raise NoEligibleRoute("No deployment satisfies capability, privacy and budget constraints.")

    selected = max(scored, key=lambda item: item[0])[1]
    return RouteDecision.from_selection(packet, selected, scored)
```

## 23.5 Scope-first retrieval

```python
async def build_working_context(
    db: AsyncSession,
    *,
    scope: ScopeEnvelope,
    query: str,
    task_class: str,
    token_budget: int,
) -> ContextBundle:
    await assert_scope_valid(db, scope)

    exact = await exact_entity_retrieval(db, scope=scope, query=query)
    lexical = await lexical_retrieval(db, scope=scope, query=query)
    vector = await vector_retrieval(db, scope=scope, query=query)
    temporal = await temporal_expansion(db, scope=scope, query=query)
    contradictions = await contradiction_retrieval(
        db, scope=scope, candidate_refs=exact + lexical + vector
    )

    candidates = deduplicate_sources(
        exact + lexical + vector + temporal + contradictions
    )
    candidates = enforce_source_authority_and_sensitivity(candidates, scope)
    packed, excluded = pack_context(candidates, token_budget=token_budget)

    manifest = ContextManifestV2.from_selection(
        scope=scope,
        included=packed,
        excluded=excluded,
    )
    return ContextBundle(manifest=manifest, evidence=packed)
```
