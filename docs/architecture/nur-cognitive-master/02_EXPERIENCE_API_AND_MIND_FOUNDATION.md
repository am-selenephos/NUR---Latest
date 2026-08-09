## 6.4 SSE event vocabulary

Use a versioned discriminated union. Do not add ad-hoc strings from random modules.

```text
talk.accepted
talk.replayed
talk.scope.resolved
talk.retrieval.started
talk.retrieval.completed
brain.route.selected
provider.created
response.text.delta
provider.retry
provider.completed
review.started
review.completed
workflow.proposed
approval.required
memory.candidate
talk.validated
talk.failed
talk.cancelled
```

Every event contains:

```json
{
  "schema_version": "1.0",
  "event_id": "uuid",
  "request_id": "uuid",
  "trace_id": "uuid",
  "sequence": 12,
  "occurred_at": "RFC3339",
  "type": "talk.validated",
  "data": {}
}
```

Rules:

- sequence is monotonic per request;
- terminal events are mutually exclusive;
- reconnect uses last event ID or durable replay;
- sensitive evidence excerpts are not streamed by default;
- tool result claims require Agency-confirmed data;
- a retry after visible text is emitted must not silently replace text without UI reconciliation.

## 6.5 Today

Today is a projection of owner-approved commitments and relevant state, not a generic recommendation feed.

It may show:

- due plans;
- approved workflow status;
- blocked approvals;
- prediction outcomes due;
- owner-pinned attention items;
- reminders;
- one explainable NUR suggestion.

It must not create urgency from model sentiment. Every surfaced item includes `why surfaced`, source, dismiss/snooze and scope.

## 6.6 Journal

Journal remains owner-authored private content.

Rules:

- no automatic permanent psychological interpretation;
- no silent memory extraction;
- analysis is scoped to the requested entry or selected window;
- inferred patterns remain candidates;
- owner can exclude an entry from future AI use;
- deletion propagates to summaries, embeddings and derived claims.

## 6.7 Plan

Plan displays owner goals, plan versions, dependencies, actions and outcomes. Brain-created plans are proposals until owner acceptance or an explicit policy allows a narrow reversible update.

UI distinctions:

```text
OWNER PLAN
NUR PROPOSAL
APPROVED WORKFLOW
IN EXECUTION
VERIFIED OUTCOME
BLOCKED / FAILED
```

## 6.8 Systems, Map and Orbits

These surfaces project the world model without pretending every graph edge is fact.

Edge styles must distinguish:

```text
OWNER_CONFIRMED
SYSTEM_DERIVED
RESEARCH_SUPPORTED
HYPOTHESIS
CONTRADICTED
STALE
```

Clicking an edge exposes evidence, confidence, scope and why-changed history.

## 6.9 Timeline

Timeline is the temporal spine. It should support:

- source events;
- plan changes;
- workflow transitions;
- external outcomes;
- belief changes;
- corrections;
- learning deployments;
- rollback events.

Derived summaries must link back to immutable or versioned source records.

## 6.10 Insights

An Insight is not a model thought. It is a reviewed, evidence-linked candidate with lifecycle:

```text
CANDIDATE
REVIEWED
ACCEPTED
REJECTED
STALE
SUPERSEDED
```

## 6.11 Research

Research briefs show claim-to-source coverage, freshness and contradictions. The UI must let the owner:

- open sources;
- exclude a source;
- request a counter-search;
- correct a synthesis;
- save only selected claims;
- avoid saving raw private queries into global learning.

## 6.12 Projects

Project surfaces show:

- objective and success criteria;
- current state;
- decisions needed;
- artifacts;
- approved workflows;
- test evidence;
- budget and latency;
- blockers;
- why a strategy changed.

## 6.13 Approval experience

An approval card must show the exact call, not vague permission:

```text
tool name and version
purpose
arguments, redacted where needed
resources affected
risk class
reversibility
estimated cost
timeout
expected result
verification rule
expiry
```

Approval is bound to an argument digest, plan version and tool version. Changing any of them invalidates the approval.

## 6.14 Correction experience

Every owner-visible claim with durable influence should support:

```text
Correct this
This is outdated
Do not remember this
Use only in this Orbit
Restore previous version
Show evidence
Why did this change?
```

Corrections are first-class events, not free-text comments lost in a transcript.

## 6.15 Accessibility and internationalization

Required:

- keyboard navigation;
- screen-reader states for streaming and approvals;
- reduced motion;
- mobile and desktop parity;
- RTL support for Urdu script;
- natural Roman Urdu/Hinglish when selected;
- locale-independent internal enums;
- no meaning encoded only by color;
- dates shown in owner locale with stored UTC timestamps.

---

# 7. Canonical API and event contracts

## 7.1 API design rules

1. Domain APIs expose product concepts, not raw tables.
2. Writes are idempotent where retries are expected.
3. Every owner-specific request establishes database owner context.
4. Mutations return the durable record or accepted workflow, not a fictional success message.
5. Errors are typed, public-safe and traceable.
6. Versioning occurs at schema boundaries.
7. Browser never receives provider credentials, internal policies or unrestricted tool definitions.

## 7.2 Proposed endpoint inventory

```text
POST   /api/v1/cognition/talk
POST   /api/v1/cognition/talk/{model_run_id}/cancel
GET    /api/v1/cognition/runs/{model_run_id}
GET    /api/v1/cognition/runs/{model_run_id}/evidence
GET    /api/v1/cognition/runs/{model_run_id}/why
POST   /api/v1/cognition/runs/{model_run_id}/correct

GET    /api/v1/mind/attention
POST   /api/v1/mind/attention/{id}/snooze
POST   /api/v1/mind/attention/{id}/dismiss
GET    /api/v1/mind/beliefs
GET    /api/v1/mind/beliefs/{id}
POST   /api/v1/mind/beliefs/{id}/correct
POST   /api/v1/mind/beliefs/{id}/restore
GET    /api/v1/mind/why-changed/{entity_type}/{entity_id}

GET    /api/v1/memory/candidates
POST   /api/v1/memory/candidates/{id}/keep
POST   /api/v1/memory/candidates/{id}/correct
POST   /api/v1/memory/candidates/{id}/reject
GET    /api/v1/memory/records
DELETE /api/v1/memory/records/{id}

GET    /api/v1/agency/workflows/{id}
POST   /api/v1/agency/approvals/{id}/approve
POST   /api/v1/agency/approvals/{id}/reject
POST   /api/v1/agency/workflows/{id}/cancel

GET    /api/v1/learning/candidates
GET    /api/v1/learning/deployments
POST   /api/v1/learning/candidates/{id}/review
POST   /api/v1/learning/deployments/{id}/rollback
```

Do not add endpoints if an existing canonical route already owns the responsibility. Reconcile first.

## 7.3 Error envelope

```json
{
  "error": {
    "code": "provider_rate_limited",
    "public_message": "Live AI is temporarily rate limited.",
    "retryable": true,
    "retry_after_seconds": 30,
    "trace_id": "uuid",
    "details": null
  }
}
```

Never return raw provider messages, stack traces, SQL, prompts, policy text or secrets.

## 7.4 Capability response

The Experience plane needs an honest capability endpoint or included state:

```json
{
  "provider": {
    "configured": true,
    "healthy": true,
    "model_profiles": ["FAST", "BALANCED", "DEEP"]
  },
  "tools": {
    "read": ["research.search", "project.read"],
    "write": ["draft.create"],
    "approval_required": ["email.send", "calendar.create"]
  },
  "limits": {
    "daily_budget_remaining_cents": 120,
    "max_run_seconds": 60,
    "multimodal": false
  },
  "identity_version": "nur-constitution-2.0.0"
}
```

This state is server-derived and not a model statement.

## 7.5 Shared TypeScript contracts

The repository should define browser-safe shared types in the existing shared-types package rather than duplicating interfaces in V197 modules.

```ts
export type RealityStatus =
  | "PRODUCTION"
  | "INTEGRATED_PARTIAL"
  | "TEST_ONLY"
  | "PROPOSED"
  | "DEFERRED";

export type EvidenceKind =
  | "OWNER_MESSAGE"
  | "MEMORY"
  | "JOURNAL"
  | "PLAN"
  | "PROJECT"
  | "OUTCOME"
  | "RESEARCH_SOURCE"
  | "TOOL_RESULT";

export interface EvidenceRef {
  kind: EvidenceKind;
  id: string;
  version?: string;
  excerpt?: string;
  confidence?: number;
  occurredAt?: string;
}

export interface TalkResponseView {
  requestId: string;
  modelRunId: string;
  responseEventId: string;
  directResponse: string;
  uncertainty: string[];
  nextMove?: string;
  evidenceCount: number;
  proposedWorkflowId?: string;
  memoryCandidateIds: string[];
  whyChangedId?: string;
  status: "VALIDATED" | "AWAITING_APPROVAL" | "FAILED";
}
```

## 7.6 Version strategy

- Pydantic/TypeScript schema versions are explicit.
- Additive optional fields can remain within a version.
- Required semantic changes require a new version.
- Stored payloads retain the schema version used at creation.
- Replayers migrate or adapt old payloads deliberately.
- SSE clients ignore unknown additive events but fail visibly on incompatible version.

---

# 8. Mind plane — durable cognition governance

The Mind is the continuity and governance layer. It does not generate prose by itself and it does not call external tools directly.

## 8.1 Scope resolver

Scope resolution occurs before retrieval and before provider invocation.

### Inputs

```text
owner_user_id
surface
conversation/thread
Orbit
Project
System
Capsule/shared context
community/group context
explicitly selected files
connector identity and permissions
memory mode
retention mode
requested action
```

### Output

A durable or reproducible `ScopeEnvelope` containing:

```text
scope id
owner
allowed record classes
allowed entity ids
excluded record classes
sharing boundary
connector boundary
memory read policy
memory write policy
retention policy
sensitivity ceiling
reason for scope
policy versions
```

### Enforcement

- Retrieval services require a `ScopeEnvelope`, not merely `owner_user_id`.
- Provider packets contain only selected representations.
- Shared Capsule content is never merged into private owner memory without explicit promotion.
- Community content cannot reveal private Orbit state.
- Connector data remains connector-scoped and records the authorization grant.
- Background workflows re-resolve scope at execution time and compare it to proposal-time scope.
- Revoked permission blocks execution even if an old approval exists.

### Failure behavior

If scope cannot be resolved:

```text
BLOCK
→ do not retrieve
→ do not invoke provider
→ persist safe failure reason
→ ask owner for a precise selection
```

## 8.2 Identity kernel and constitution

Identity is a versioned product contract, not a role-play paragraph generated every turn.

### Identity version fields

```text
identity_version
public_name
product_role
mission
voice_principles
values
epistemic_rules
privacy_rules
relationship_rules
initiative_rules
disagreement_style
repair_style
language_profiles
humour_limits
safety_behavior
forbidden_claims
capability_claim_policy
created_at
supersedes_version
change_reason
approval_record
```

### Prompt hierarchy

```text
provider platform rules
→ NUR constitution and privileged identity
→ task-specific privileged policy
→ owner request
→ retrieved evidence as untrusted quoted data
→ tool results as typed observations
```

Never place the NUR constitution inside a user-controlled dictionary that the provider serializes as normal user content. The provider adapter must use an API field or system/developer message with privileged semantics.

### Identity consistency

The same identity principles apply across English, Urdu, Roman Urdu, Hindi and Roman Hindi. Localization changes expression, not truthfulness, privacy, consent or authority.

Language profiles define:

```text
preferred script
code-switch behavior
formality
pronouns
technical vocabulary policy
cultural idiom bounds
safety wording
translation loss warnings
```

### Identity evaluation

Create a frozen corpus that tests:

- tone continuity;
- directness without fabricated certainty;
- Roman Urdu naturalness;
- refusal to claim human biology or secret capabilities;
- no dependency or exclusivity manipulation;
- correction and repair behavior;
- capability honesty;
- consistent action boundaries.
