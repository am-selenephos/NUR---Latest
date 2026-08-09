## 11.1 ScopeEnvelope

```python
from __future__ import annotations
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

class MemoryReadMode(StrEnum):
    NONE = "NONE"
    APPROVED_ONLY = "APPROVED_ONLY"
    ORBIT_ONLY = "ORBIT_ONLY"
    PROJECT_ONLY = "PROJECT_ONLY"

class MemoryWriteMode(StrEnum):
    EPHEMERAL = "EPHEMERAL"
    REVIEW = "REVIEW"
    EXPLICIT_ONLY = "EXPLICIT_ONLY"

class ScopeEnvelope(BaseModel):
    schema_version: str = "1.0"
    scope_id: UUID = Field(default_factory=uuid4)
    owner_user_id: UUID
    orbit_id: UUID | None = None
    project_id: UUID | None = None
    capsule_id: UUID | None = None
    allowed_record_kinds: frozenset[str]
    allowed_entity_ids: frozenset[UUID] = frozenset()
    excluded_record_kinds: frozenset[str] = frozenset()
    memory_read_mode: MemoryReadMode
    memory_write_mode: MemoryWriteMode
    provider_policy: str
    retention_policy: str
    sensitivity_ceiling: str
    resolved_at: datetime
    policy_versions: dict[str, str]
    reason: str
```

## 11.2 CognitiveTaskPacketV2

```python
class CognitiveTaskPacketV2(BaseModel):
    schema_version: str = "2.0"
    task_id: UUID = Field(default_factory=uuid4)
    request_id: UUID
    trace_id: UUID
    owner_user_id: UUID
    task_class: str
    objective: str
    scope: ScopeEnvelope
    identity_version: str
    language: dict[str, str]
    owner_message: str
    current_situation: dict
    working_memory: list[dict]
    beliefs: list[dict]
    open_contradictions: list[dict]
    goals: list[dict]
    constraints: list[dict]
    evidence_refs: list[dict]
    available_capabilities: list[dict]
    budget: dict
    required_output_schema: str
    excluded_context: list[dict]
    risk_flags: list[str]
    review_strategy_id: str
```

## 11.3 CognitiveResultV2

```python
class ClaimKind(StrEnum):
    OBSERVATION = "OBSERVATION"
    OWNER_STATED = "OWNER_STATED"
    RESEARCH_DERIVED = "RESEARCH_DERIVED"
    INFERENCE = "INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"

class TypedClaim(BaseModel):
    claim_id: UUID = Field(default_factory=uuid4)
    text: str
    kind: ClaimKind
    evidence_refs: list[str]
    counter_evidence_refs: list[str] = []
    confidence: float | None = Field(default=None, ge=0, le=1)
    status: str

class ProposedAction(BaseModel):
    action_id: UUID = Field(default_factory=uuid4)
    action_kind: str
    description: str
    durable: bool
    tool_key: str | None = None
    arguments: dict = {}
    risk_class: str
    requires_owner_approval: bool = True
    success_criteria: list[str] = []
    verification_contract: dict = {}

class CognitiveResultV2(BaseModel):
    schema_version: str = "2.0"
    result_id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    direct_response: str
    claims: list[TypedClaim]
    assumptions: list[str]
    uncertainties: list[dict]
    alternatives: list[dict]
    proposed_actions: list[ProposedAction]
    memory_candidates: list[dict]
    belief_update_candidates: list[dict]
    evidence_refs: list[str]
    decision_summary: str
    verification_required: bool
    stop_reason: str
```

## 11.4 Contract rules

- Brain cannot add evidence IDs not present in the packet.
- Brain cannot mutate scope.
- Brain cannot mark an external action completed.
- Durable proposed actions must include tool/capability requirements.
- Memory and belief updates remain candidates.
- `decision_summary` is concise structured rationale, not hidden chain-of-thought.
- Uncertainty uses typed reason codes.

---

# 12. Brain–Agency contract

## 12.1 WorkflowProposalV2

```python
class WorkflowStepProposal(BaseModel):
    key: str
    title: str
    role: str
    tool_key: str
    tool_version: str | None = None
    arguments: dict
    depends_on: list[str]
    expected_outputs: list[str]
    requested_capabilities: list[str]
    risk_class: str
    approval_rule: str
    timeout_seconds: int
    estimated_cost_cents: int
    verification_contract: dict
    rollback_strategy: dict | None = None

class WorkflowProposalV2(BaseModel):
    schema_version: str = "2.0"
    proposal_id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    request_id: UUID
    trace_id: UUID
    owner_user_id: UUID
    objective: str
    success_criteria: list[str]
    plan_version: int = 1
    steps: list[WorkflowStepProposal]
    total_budget_cents: int
    max_risk_class: str
    requires_owner_approval: bool
    scope_id: UUID
    expires_at: datetime | None
```

## 12.2 Handoff rules

1. Mind accepts workflow proposals only for explicit durable-action intent.
2. The proposal is normalized and schema-validated.
3. Tool keys must exist in the Agency registry.
4. Agency compiler computes the authoritative risk, capability and approval state.
5. Model-proposed `approval_rule` cannot weaken policy.
6. Exact argument digests bind approval.
7. No execution occurs in the cognitive transaction.
8. Workflow persistence and response persistence share trace lineage.
9. A normal Talk response produces no workflow rows.
10. If compilation fails, Talk returns a proposal-blocked explanation, not success.

## 12.3 Production integration point

The production loop should contain a deliberate branch after validation:

```python
workflow = None
if intent.kind == "DURABLE_ACTION" and result.proposed_actions:
    proposal = workflow_proposal_from_result(packet, result)
    workflow, compile_result = await submit_workflow_proposal(
        db,
        owner_user_id=packet.owner_user_id,
        proposal=proposal,
        orbit_id=packet.scope.orbit_id,
        project_id=packet.scope.project_id,
    )
```

This branch must not run merely because `next_move` is non-empty.

---

# 13. Agency Spine integration

The existing Agency Spine remains authoritative for durable execution.

## 13.1 Existing responsibilities to preserve

```text
workflow and step DAG
policy and risk evaluation
registered tools
exact-call approvals
outbox
dispatcher
Celery worker
durable claim and fencing
idempotency
verification
artifact ledger
cost accounting
quiet hours
recovery
Map/Orbit/Timeline projection
```

## 13.2 Tool contract

Every tool has:

```text
tool key
semantic version
input schema
output schema
capabilities
risk class
side-effect class
idempotency support
timeout
retry policy
redaction policy
verification function
rollback support
```

## 13.3 Least-capability rule

A workflow receives only capabilities required by compiled steps. A Researcher with a read-only search tool does not inherit email, repository write or deployment access.

## 13.4 Approval state machine

```text
NOT_REQUIRED
PENDING
APPROVED
REJECTED
EXPIRED
REVOKED
SUPERSEDED
CONSUMED
```

An approval is consumed only by the matching tool key/version, argument digest, workflow plan version, owner and scope.

## 13.5 Step state machine

```text
PROPOSED
READY
BLOCKED
CLAIMED
RUNNING
VERIFYING
SUCCEEDED
FAILED_RETRYABLE
FAILED_TERMINAL
CANCELLED
COMPENSATING
COMPENSATED
```

## 13.6 Tool result truth

Model prose cannot mark a step successful. Success requires:

- tool return;
- durable artifact or state observation;
- verifier result;
- commit of outcome state.

## 13.7 Recovery

Crash recovery uses durable step claims, leases/fencing and idempotency. Long-running workflows must resume from persisted state rather than replaying all model decisions.

## 13.8 Connector boundary

MCP/A2A/connector integration is an adapter to the tool registry, not a bypass.

Required controls:

```text
auth grant and expiry
resource owner
capability allowlist
server identity
transport security
argument schema
response size/type limits
prompt-injection isolation
rate and cost limits
audit and revocation
```

Peer agents are untrusted services. Their output is evidence or a proposed result, never policy.

---

# 14. State and data architecture

## 14.1 Storage principles

1. PostgreSQL is the source of durable truth.
2. Redis is coordination/cache, not owner truth.
3. Celery messages carry IDs, not private state dumps.
4. pgvector is a retrieval index over versioned source records, not an independent memory database.
5. Graph projections are derived from canonical entities, edges and evidence.
6. Raw events and accepted state are distinct.
7. Every owner-specific table uses forced RLS.
8. Every derived record points to its source and version.
9. Deletion and retention are designed before data collection.
10. Migrations are forward-only once applied.

## 14.2 Proposed table families

Do not create every table immediately. Reuse existing models where responsibilities match. The canonical target families are:

```text
mind_scope_envelopes
mind_context_manifests
mind_attention_items
mind_user_claims
mind_world_entities
mind_world_edges
mind_beliefs
mind_hypotheses
mind_goal_links
mind_intentions
mind_why_changed
mind_review_strategies
mind_reviews
mind_meta_reviews
mind_reviewer_profiles
mind_blind_spots
mind_cognitive_debt

brain_model_deployments
brain_route_decisions
brain_runs
brain_validations
brain_critic_runs

memory_records
memory_versions
memory_evidence_links
memory_contradictions
memory_consolidation_jobs
prospective_memory_items

learning_candidates
learning_dataset_items
learning_eval_runs
learning_checkpoints
learning_deployments
learning_rollbacks
```

Existing `CognitiveEvent`, `ModelRun`, `ModelRunSource`, memory candidates, predictions, evaluations and Agency tables should be extended or referenced rather than copied.

## 14.3 Bitemporal state

Important claims and relations need two times:

```text
valid_time: when the fact is believed to apply in the represented world
recorded_time: when NUR learned or recorded it
```

Example:

```text
Owner worked at X from 2024-01 to 2025-03.
NUR learned this on 2026-08-05.
```

This prevents “latest inserted row” from erasing historical truth.

## 14.4 Append-only evidence

Raw source events and evidence references are append-only except for privacy deletion/tombstoning. Corrections create new records and invalidation links.

Derived active state uses version pointers:

```text
belief.active_version_id
memory.active_version_id
world_edge.active_version_id
```

## 14.5 RLS template

Every owner-specific table follows an audited pattern:

```sql
ALTER TABLE mind_beliefs ENABLE ROW LEVEL SECURITY;
ALTER TABLE mind_beliefs FORCE ROW LEVEL SECURITY;

CREATE POLICY mind_beliefs_owner_select
ON mind_beliefs
FOR SELECT
USING (owner_user_id = app_current_user_id());

CREATE POLICY mind_beliefs_owner_insert
ON mind_beliefs
FOR INSERT
WITH CHECK (owner_user_id = app_current_user_id());

CREATE POLICY mind_beliefs_owner_update
ON mind_beliefs
FOR UPDATE
USING (owner_user_id = app_current_user_id())
WITH CHECK (owner_user_id = app_current_user_id());

CREATE POLICY mind_beliefs_owner_delete
ON mind_beliefs
FOR DELETE
USING (owner_user_id = app_current_user_id());
```

Tests must set the real application role and session owner context. Superuser tests do not prove isolation.

## 14.6 Cross-owner denial matrix

For every owner-specific table test:

```text
owner A SELECT owner A = allowed
owner A SELECT owner B = denied/empty
owner A INSERT owner B = denied
owner A UPDATE owner B = denied
owner A DELETE owner B = denied
missing owner context = denied
invalid owner context = denied
worker with explicit owner context = limited to owner
```

Also test joins, subqueries, functions, views, background workers and SECURITY DEFINER functions.

## 14.7 SECURITY DEFINER discipline

A SECURITY DEFINER function:

- has an explicit safe `search_path`;
- owns the narrowest possible privilege;
- takes exact typed inputs;
- returns minimum data;
- revokes PUBLIC execute;
- validates caller authorization where needed;
- is tested under forced RLS;
- is created by a forward migration;
- does not swallow privilege errors that leave ambiguous state.

A BYPASSRLS role is exceptional and must be NOLOGIN, narrow, documented and independently audited.
