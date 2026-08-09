# 4. Whole-system architecture

## 4.1 Plane boundaries

```text
┌────────────────────────────────────────────────────────────────────┐
│ EXPERIENCE PLANE                                                   │
│ V197 shell · Talk · Today · Journal · Plan · Systems · Map         │
│ Orbits · Timeline · Insights · Research · Projects · approvals     │
│ corrections · evidence · why-changed · memory review               │
└───────────────────────────────┬────────────────────────────────────┘
                                │ owner intent / feedback / consent
┌───────────────────────────────▼────────────────────────────────────┐
│ MIND PLANE                                                         │
│ scope · identity · attention · working memory · user/self/world    │
│ beliefs · hypotheses · goals · intentions · relationships          │
│ memory stewardship · review strategy · metacognition · why-changed │
└───────────────────────────────┬────────────────────────────────────┘
                                │ CognitiveTaskPacket
┌───────────────────────────────▼────────────────────────────────────┐
│ BRAIN PLANE                                                        │
│ model registry/router · privileged prompts · provider boundary     │
│ direct cognition · planner · researcher · simulator · critic       │
│ language/multimodal specialists · structured output · budget       │
└───────────────────────────────┬────────────────────────────────────┘
                                │ CognitiveResult / WorkflowProposal
┌───────────────────────────────▼────────────────────────────────────┐
│ AGENCY SPINE                                                       │
│ compiler · policy · exact-call approval · outbox · Celery worker   │
│ tool registry · claim/fencing · verification · artifacts · recovery│
└───────────────────────────────┬────────────────────────────────────┘
                                │ durable events / outcomes / evidence
┌───────────────────────────────▼────────────────────────────────────┐
│ STATE + LEARNING PLANE                                             │
│ PostgreSQL · forced RLS · pgvector · Redis · Omega · event ledger  │
│ memory graph · evaluations · corrections · learning candidates     │
│ model/prompt registry · deployment history · rollback              │
└────────────────────────────────────────────────────────────────────┘
```

## 4.2 The three control loops

### Interaction loop

```text
owner message
→ scope
→ context
→ cognition
→ verification
→ response
→ correction or memory review
```

### Action loop

```text
durable-action intent
→ plan proposal
→ deterministic compiler
→ policy
→ exact-call approval
→ outbox
→ worker claim
→ tool
→ verifier
→ artifact/outcome
→ projection
```

### Learning loop

```text
trace + owner correction + external outcome
→ evaluation
→ learning candidate
→ provenance/privacy/poisoning review
→ frozen benchmark
→ candidate prompt/route/retrieval/model change
→ shadow evaluation
→ approval
→ staged deployment
→ monitoring
→ rollback or promotion
```

These loops share identifiers but never share authority accidentally. A good answer cannot authorize a tool. A successful tool result cannot automatically rewrite identity. A high model confidence cannot override owner correction.

## 4.3 Canonical lineage identifiers

Every run must be traceable using UUIDs or stable version IDs:

```text
request_id
conversation_id
turn_event_id
scope_envelope_id
context_manifest_id
cognitive_task_id
brain_run_id
model_run_id
review_id
meta_review_id
response_event_id
workflow_proposal_id
workflow_id
step_id
approval_id
tool_call_id
artifact_id
outcome_id
memory_candidate_id
belief_change_id
learning_candidate_id
deployment_id
trace_id
```

Rules:

- IDs are created once at the owning boundary.
- Downstream records reference, never regenerate, the upstream ID.
- Browser-visible IDs are opaque and owner-scoped.
- Logs may contain IDs but not raw private content by default.
- Retried work preserves the idempotency key and creates attempt IDs.
- A replayed response must identify itself as replay without duplicating side effects.

## 4.4 State ownership

| State | Owner |
|---|---|
| Current UI selection | Experience |
| Owner intent and consent | Experience → Mind input |
| Scope envelope | Mind |
| Identity and constitution | Mind |
| Working context selection | Mind |
| Provider/model route | Brain |
| Model output | Brain |
| Belief or memory candidate | Mind |
| Durable workflow | Agency |
| Tool authority | Agency policy and approval |
| Tool result | Agency artifact/outcome |
| Evaluation | Learning plane |
| Deployment decision | Reviewed governance |

---

# 5. Canonical end-to-end behavior

## 5.1 Talk: answer-only path

The simplest owner message must not invoke the whole universe unnecessarily.

```text
POST /api/v1/cognition/talk
→ authenticate owner
→ resolve request id and idempotency
→ classify intent = ANSWER_ONLY
→ create ScopeEnvelope
→ select minimum necessary context
→ build CognitiveTaskPacket
→ route profile
→ provider call
→ deterministic validation
→ optional critic according to review strategy
→ synthesize NURTalkOutput
→ persist response and evaluation
→ stream owner-visible result
```

Required invariants:

- A greeting does not retrieve unrelated history.
- A direct rewrite request can be answered from the current message only.
- A question about stored state cannot claim an answer without retrieved evidence.
- A provider failure creates a durable error state and honest visible message.
- A duplicate `request_id` replays the existing result and does not repeat model cost or action.
- `EPHEMERAL` memory mode never creates personal memory candidates.
- Response streaming cannot make a durable-action claim before Agency verification.

## 5.2 Talk: durable-action proposal path

```text
owner asks for an external or durable action
→ intent classifier marks DURABLE_ACTION_CANDIDATE
→ Brain may return proposed_actions / WorkflowProposalCandidate
→ Mind validates intent, scope, capability and completeness
→ deterministic proposal normalizer
→ existing Agency compile_plan
→ policy evaluation
→ workflow persisted
→ risky steps BLOCKED_ON_APPROVAL
→ Talk response presents plan and approval requirement
→ no tool executes until Agency state permits dispatch
```

Examples of durable action intent:

```text
send an email
create or change a calendar event
publish or deploy
modify a repository
spend money
submit an application
write to a production database
share a Capsule
contact another person
run an external connector mutation
```

Examples that must remain answer-only unless the owner explicitly asks for persistence:

```text
explain how to send an email
write an email draft
brainstorm a schedule
show a possible plan
analyze a repository diff
summarize a document
```

The model may suggest an action. It may not convert a suggestion into execution authority.

## 5.3 Research-to-decision path

```text
owner question
→ freshness and stakes classification
→ scope minimization
→ query plan
→ source policy
→ primary-source retrieval
→ source ingestion as untrusted evidence
→ authority/freshness scoring
→ contradiction search
→ claim-evidence graph
→ deterministic citation coverage
→ independent critic for high stakes
→ synthesis
→ owner-visible uncertainty
→ optional Research Brief / Insight candidate
```

Research output must distinguish:

- source fact;
- model inference;
- unresolved disagreement;
- stale or jurisdiction-limited material;
- action recommendation;
- missing evidence.

A web page can inform a recommendation but cannot instruct NUR to call a tool, expose a secret, change a policy or ignore the owner.

## 5.4 Memory review path

```text
owner turn or outcome
→ memory candidate extraction
→ classify candidate type
→ attach provenance and source event
→ sensitivity and scope check
→ contradiction search
→ retention policy
→ owner review card
→ KEEP / CORRECT / REJECT / DEFER
→ accepted memory version
→ why-changed ledger
→ affected retrieval indexes updated
```

No memory candidate is promoted merely because the assistant repeated it confidently.

## 5.5 Belief change path

```text
new evidence or owner correction
→ retrieve current belief version
→ compare evidence for/against
→ determine change class
→ create belief-change candidate
→ high-impact review if required
→ commit new version
→ invalidate affected projections
→ append WhyChangedRecord
→ expose “Why did this change?” and rollback route
```

High-impact beliefs include:

- owner identity or boundaries;
- medical, legal or financial state;
- relationship interpretations;
- project commitments;
- authorization and capability state;
- persistent recommendations used by future workflows.

## 5.6 Prospective memory path

Prospective memory is remembering to act or surface something later, not just recalling facts.

```text
owner future intention
→ parse trigger and desired action
→ distinguish reminder from condition watch
→ create canonical scheduled/conditional proposal
→ Agency approval where external action is involved
→ persist trigger state
→ evaluate at bounded cadence
→ notify or propose action
→ mark outcome
```

A reminder is not a belief. A due prediction is not a memory fact. Keep their persistence and lifecycle distinct.

## 5.7 Multimodal evidence path

```text
file/image/audio/video received
→ malware/type/size checks
→ source record and retention policy
→ modality adapter
→ page/frame/timestamp segments
→ extracted observations with confidence
→ owner correction support
→ evidence refs in CognitiveTaskPacket
→ no direct action authority
```

Every multimodal observation must carry:

```text
source_file_id
page/frame/timestamp
extractor/model version
confidence
content hash
scope
retention policy
owner corrections
```

## 5.8 Project delivery path

```text
project objective
→ retrieve project scope and state
→ detect blockers and missing decisions
→ planner creates typed plan proposal
→ simulator checks dependencies and rollback
→ critic checks feasibility and repository truth
→ Agency compiles executable steps
→ approvals
→ execution and artifacts
→ tests and acceptance evidence
→ outcome and project state projection
```

NUR must not equate “code was generated” with “project task completed.” Completion is tied to tests, artifacts, target environment and acceptance criteria.

---

# 6. Experience plane and V197 integration

## 6.1 Principle: intelligence is visible through consequences, not dashboards

Do not expose every internal table as a panel. The owner should see:

- the answer;
- what evidence mattered;
- what is uncertain;
- what NUR proposes;
- what requires approval;
- what changed;
- how to correct it;
- whether an action actually completed.

The owner should not have to inspect internal “agent logs” to know whether NUR is guessing.

## 6.2 V197 preservation

The canonical V197 DOM, CSS and runtime remain the visible shell. New work must follow current surface ownership and adjunct isolation rules.

Allowed extension pattern:

```text
existing V197 surface
→ typed bridge state
→ minimal DOM projection
→ API/SSE contract
→ no duplicate parent shell
```

Forbidden pattern:

```text
new generic SPA dashboard
→ separate navigation
→ separate identity/persona
→ duplicated Talk implementation
→ direct database-shaped UI
```

## 6.3 Talk UI contract

Talk should support these owner-visible states:

```text
IDLE
SUBMITTING
ACCEPTED
RETRIEVING
THINKING
STREAMING
VALIDATING
AWAITING_APPROVAL
COMPLETED
FAILED_RETRYABLE
FAILED_BLOCKED
CANCELLED
REPLAYED
```

Owner-visible response anatomy:

```text
direct response
optional evidence indicator
uncertainty disclosure
next move
proposed durable action card
memory candidate card
why-changed indicator
correction affordance
trace status, not hidden reasoning
```

The UI must never show a completed assistant bubble if the backend recorded failure. Streaming text is provisional until `talk.validated` or equivalent terminal event arrives.
