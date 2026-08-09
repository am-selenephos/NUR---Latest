## 19.9 LLM-as-judge controls

LLM judges are fallible and may exhibit position, verbosity and self-preference bias.

Controls:

- randomized output order;
- rubric with atomic criteria;
- blind model identity;
- multiple judges for critical changes;
- deterministic metrics where possible;
- human audit sample;
- judge calibration against owner outcomes;
- disagreement preserved, not averaged away blindly.

## 19.10 Confidence and uncertainty evaluation

- calibration curves;
- Brier/log scores for resolvable predictions;
- selective accuracy under abstention;
- uncertainty-type correctness;
- false-certainty rate;
- missing-evidence recognition.

## 19.11 Regression gates

A candidate cannot ship based only on average improvement. Define non-regression floors for:

```text
privacy
cross-owner isolation
tool authorization
owner correction adherence
Roman Urdu identity
high-stakes uncertainty
cost
latency
schema reliability
```

## 19.12 Fresh coding evaluation

Use repository-local tasks and fresh issues, because memorized public benchmarks can overstate coding capability. Required acceptance remains repository CI plus maintainer review of diff quality and architecture fit.

## 19.13 Exact release evidence

Release report includes:

```text
base SHA
head SHA
diff stat
migrations
all commands
exact test totals
skips/xfails
provider mode
security scans
known limitations
rollback
CI run URL/ID
```

No manual arithmetic or “all tests passed” without terminal/CI evidence.

---

# 20. Migration from PR #15 to canonical architecture

## 20.1 Preserve what is real

Keep:

- `run_talk_kernel` idempotency/replay behavior;
- production connection to Mind loop;
- current persistence and SSE compatibility;
- scoped retrieval and evidence packet;
- ModelRun records;
- existing memory candidate and prediction services;
- existing verifier;
- existing Agency compiler and workflow infrastructure;
- green CI baseline.

## 20.2 Correct misleading or partial contracts

### Identity prompt

Move identity/constitution into a privileged provider instruction field. Preserve fixed security rules by composing versioned privileged layers, not by replacing them with owner-controlled text.

### Router

Make profile selection affect actual model deployment, reasoning control, output tokens, timeouts and cost.

### Structured result

Introduce `CognitiveResultV2` behind a feature flag. Either ask provider for it directly or validate a documented adapter from `NURTalkOutput`.

### Critic

Rename deterministic critic and add real critic runtime.

### Metacognition

Replace hardcoded passes with computed state or `UNKNOWN`. Correct the check-count claim.

### Agency

Add proposed actions/workflow candidates and production handoff for explicit durable intent.

### Migration

Resolve historical `0034` safely through forward migration.

## 20.3 Compatibility strategy

Use feature flags:

```text
NUR_COGNITION_V2
NUR_PRIVILEGED_IDENTITY_PROMPT
NUR_MODEL_ROUTER_V2
NUR_MODEL_CRITIC
NUR_WORKFLOW_PROPOSAL_V2
NUR_MEMORY_GRAPH_V1
NUR_META_REVIEW_V1
```

## 20.4 Dual-read/dual-write

Only where necessary and temporary:

- write old response payload plus new canonical result reference;
- read V2 if present, otherwise adapt V1;
- compare shadow output without showing it;
- remove compatibility after migration and evidence.

Never create two sources of durable truth.

## 20.5 Branch strategy

Recommended stacked sequence:

```text
PR #15 source head
→ docs/canonical-cognitive-architecture
→ fix/cognition-contract-v2
→ feat/agency-proposal-production-handoff
→ feat/privileged-provider-routing
→ feat/review-governance
→ feat/memory-belief-foundation
→ feat/learning-evaluation
```

Each branch is small enough for review and independently green. Do not run multiple coding agents in the same worktree.

## 20.6 Merge order

No child branch merges before its parent is integrated or retargeted cleanly. Rebase/retarget only after preserving exact-head CI and resolving conflicts deliberately.

---

# 21. Implementation program

Every phase starts with repository inspection and ends with exact-head CI. No phase may create placeholders for future phases.

## Phase 0 — Recovery and Git truth

### Objective

Reconstruct the exact current state after any IDE/chat crash and protect local work.

### Actions

```text
pwd
git status --short --branch
git branch --show-current
git rev-parse HEAD
git remote -v
git fetch origin
git log --graph --decorate --oneline -n 20
git diff
git diff --cached
git ls-files --others --exclude-standard
```

### Classification

Every difference is labeled:

```text
pushed commit
local-only commit
tracked uncommitted
untracked source
untracked generated
temporary IDE artifact
```

### Forbidden

```text
reset --hard
clean -fd
checkout .
restore .
stash
rebase
force push
```

until the state is understood and backed up.

### Exit

- current branch/head known;
- remote relationship known;
- no edits lost;
- clean isolated continuation branch or protected worktree.

## Phase 1 — Architecture truth audit

### Objective

Map existing code to canonical responsibilities.

### Deliverable

A matrix:

```text
responsibility
existing file/function/table/route
production caller
persistence
security boundary
tests
gap
decision: reuse/extend/retire/create
```

### Required searches

- all direct provider calls;
- all Talk endpoints/callers;
- all workflow/approval/tool models;
- all memory and belief-like records;
- all SSE event strings;
- all owner-context and RLS helpers;
- all migrations touching relevant tables/roles;
- all V197 bridge ownership.

### Exit

No planned new component duplicates an existing canonical one.

## Phase 2 — Contract V2 foundation

### Objective

Introduce versioned contracts without changing visible behavior.

### Implement

```text
ScopeEnvelope
CognitiveTaskPacketV2
CognitiveResultV2
TypedClaim
TypedUncertainty
ProposedAction
ReviewStrategyRef
WorkflowProposalV2
versioned SSE envelope
```

### Tests

- serialization roundtrip;
- owner/task/trace IDs preserved;
- unknown evidence rejected;
- action completion cannot appear in proposed state;
- schema compatibility adapters;
- TypeScript/Python contract parity.

### Exit

Contracts exist in shared canonical modules and are not yet falsely claimed as production behavior.

## Phase 3 — Scope-first context

### Objective

Make scope a required object for retrieval and cognition.

### Implement

- scope resolver service;
- scope policy model;
- intersection logic;
- retrieval signatures requiring scope;
- context manifest persistence policy;
- excluded context reasons;
- Capsule/Project/Orbit tests.

### Migration

Add scope envelope and optional context manifest tables only if existing records cannot support them.

### Tests

- no retrieval before scope;
- scope cannot widen;
- cross-Orbit exclusion;
- Capsule shared/private separation;
- revoked connector scope;
- worker re-resolution.

### Exit

Every production cognition path receives a scope envelope.

## Phase 4 — Privileged identity and provider request

### Objective

Use the NUR constitution as a true privileged instruction.

### Implement

- `InstructionEnvelope`;
- provider request with system/developer/user/evidence separation;
- prompt registry/version hashes;
- OpenAI adapter mapping;
- provider-disabled behavior;
- redacted trace.

### Tests

- malicious evidence cannot alter privileged instructions;
- owner text cannot overwrite policy;
- identity version recorded;
- actual provider payload test;
- no raw prompt in logs;
- Roman Urdu behavior corpus.

### Exit

Identity is not buried in Omega/user content.

## Phase 5 — Executable model routing

### Objective

Make routes control real provider behavior.

### Implement

- model deployment registry;
- profile eligibility;
- provider health;
- actual reasoning/output/timeout controls;
- budget estimator;
- fallback policy;
- route persistence.

### Tests

- FAST and DEEP produce different real payload controls;
- unsupported control rejects or maps explicitly;
- low budget route;
- no eligible route;
- provider outage fallback;
- privacy restriction excludes provider.

### Exit

Route metadata matches the request actually sent.

## Phase 6 — Canonical structured cognition

### Objective

Make `CognitiveResultV2` the validated Brain output.

### Implement

- direct provider schema or explicit adapter;
- typed claims, uncertainty, alternatives and proposed actions;
- evidence validator;
- synthesizer V2;
- compatibility payload.

### Tests

- malformed result;
- invented ref;
- unsupported claim;
- too many proposed actions;
- fake action-completed field;
- old replay compatibility.

### Exit

The unused `output_schema` fiction is gone.

## Phase 7 — Durable-action handoff

### Objective

Connect explicit durable action intent to existing Agency safely.

### Implement

- deterministic/structured intent classification;
- proposed action normalization;
- workflow proposal compiler adapter;
- production call from Mind loop;
- response projection for approval.

### Tests

```text
ordinary Talk → no workflow
email draft → no send workflow
explicit send → workflow proposal
approval-required step → blocked
no approval → no tool execution
changed arguments → approval invalid
compile failure → honest blocked response
```

### Exit

Brain proposes, Mind validates, Agency owns execution.

## Phase 8 — Review governance

### Objective

Separate deterministic validation, model critic and meta-review.

### Implement

- review strategy registry;
- deterministic validator results;
- critic provider call;
- reviewer profile;
- meta-review entry rules;
- stop reasons;
- review persistence.

### Tests

- same-model critic labeled lower independence;
- critic cannot add evidence;
- `UNKNOWN` does not pass;
- high-stakes route invokes required review;
- routine route avoids unnecessary cost;
- disagreement preserved.

### Exit

Review claims match actual implementation.

## Phase 9 — User/self/world model foundation

### Objective

Add durable, provenance-aware state without psychological overreach.

### Implement

- user claim versions;
- self-model projection;
- world entities and edges;
- evidence links;
- temporal validity;
- owner correction;
- why-changed.

### Tests

- inferred sensitive claim cannot auto-promote;
- owner correction wins;
- temporal update preserves history;
- causal edge remains candidate;
- deletion invalidates projection;
- cross-owner graph denial.

### Exit

Map/Systems projections can distinguish fact, inference and hypothesis.

## Phase 10 — Beliefs, hypotheses and predictions

### Objective

Create separate lifecycles and evaluation.

### Implement

- belief versions/status;
- hypothesis tests;
- prediction resolution;
- confidence and calibration data;
- contradiction review;
- UI projections.

### Tests

- belief versus hypothesis separation;
- stale evidence;
- prediction outcome scoring;
- correction/rollback;
- no silent certainty.

## Phase 11 — Memory governance V2

### Objective

Build provenance-aware, conflict-aware, temporal memory.

### Implement

- memory atoms/versions;
- candidate validator;
- contradiction relationships;
- hierarchical retrieval;
- consolidation;
- deletion propagation;
- prospective memory.

### Tests

- explicit save;
- REVIEW candidate;
- EPHEMERAL no write;
- duplicate/refinement/temporal update/contradiction;
- poisoned file instruction;
- provenance-role confusion;
- long-history retrieval;
- deletion.

## Phase 12 — Planner, researcher and simulator

### Objective

Add specialists only after central contracts are stable.

### Implement

- typed specialist requests/results;
- manager/conductor orchestration;
- call budgets;
- research evidence graph;
- plan DAG;
- scenario assumptions.

### Tests

- specialist output cannot change scope;
- max call cap;
- planner tool mismatch;
- researcher counter-source;
- simulator fake precision;
- synthesis preserves dissent.

## Phase 13 — V197 intelligence surfaces

### Objective

Expose evidence, uncertainty, approvals, corrections and why-changed through the existing design.

### Implement

- bridge contracts;
- Talk state reconciliation;
- approval card;
- memory review card;
- correction flow;
- why-changed drawer;
- Map edge status;
- Timeline events.

### Tests

- desktop/mobile;
- RTL;
- Roman Urdu;
- accessibility;
- reload/replay;
- provider failure;
- approval block;
- no parent UI overlap.
