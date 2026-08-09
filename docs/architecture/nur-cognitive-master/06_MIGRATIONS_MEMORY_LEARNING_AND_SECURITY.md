## 14.8 Historical migration rule

Never modify an applied migration to repair production state. Determine whether migration `0034_email_lookup_role` has ever run on any persistent database.

If yes or unknown:

1. restore historical migration content to the released form;
2. create a new forward migration;
3. make it idempotent and explicit;
4. test upgrade from released snapshots;
5. test downgrade only where downgrade is genuinely supported;
6. document one-time role provisioning if PostgreSQL role creation cannot be transactional or permitted.

## 14.9 Embeddings

Embeddings store:

```text
source type/id/version
owner
effective scope
embedding model/version
dimension
content hash
created_at
superseded/deleted state
```

Never reuse an embedding after the underlying text is corrected or deleted.

## 14.10 Vector and lexical retrieval

Use hybrid retrieval:

```text
exact ID/entity
lexical/BM25-style
vector similarity
temporal constraints
graph expansion
owner-pinned boosts
contradiction retrieval
```

Vector similarity alone is insufficient for temporal updates, exact names, negation and source provenance.

## 14.11 Event/outbox consistency

Changes that need asynchronous projection or execution use an outbox in the same transaction as the source state. Workers acknowledge only after durable processing or idempotent projection.

## 14.12 Retention and deletion

Each record class defines:

```text
default retention
owner override
legal/security hold, if applicable
export format
deletion behavior
derived-data invalidation
backup expiry
training eligibility
```

Deletion flow:

```text
owner request
→ authorization
→ tombstone/source deletion
→ derived graph invalidation
→ embedding deletion
→ cached context purge
→ learning candidate exclusion
→ deployment impact review
→ completion record
```

A model checkpoint trained on private data cannot support perfect unlearning by deleting a row; therefore private model customization must be isolated, versioned and removable as an adapter/checkpoint.

---

# 15. Memory architecture

## 15.1 Memory is a governed lifecycle

Memory is not “store every chat in a vector DB.” It includes selection, representation, provenance, temporal updates, contradiction, retrieval, correction, consolidation and deletion.

## 15.2 Memory planes

### Session memory

Purpose: current interaction continuity.

```text
short-lived
bounded
automatically expires
not treated as durable owner truth
```

### Episodic memory

Purpose: events and interactions.

```text
what happened
when
who/what was involved
source event
outcome
scope
```

### Semantic personal memory

Purpose: accepted facts, preferences, boundaries and stable decisions.

```text
owner-reviewed or explicit
versioned
conflict-aware
retrieval-prioritized
```

### Procedural memory

Purpose: approved ways of doing tasks.

```text
workflow patterns
tool recipes
project conventions
verification rules
```

Procedures are not executable authority; Agency still compiles and approves.

### System memory

Purpose: NUR deployment and operational history.

```text
prompt versions
model routes
known regressions
incident learnings
capability state
```

### Prospective memory

Purpose: future trigger obligations.

```text
reminders
condition watches
follow-ups
prediction resolution
```

## 15.3 Canonical memory atom

A memory atom separates evidence from claim.

```python
class MemoryAtom(BaseModel):
    memory_id: UUID
    version_id: UUID
    owner_user_id: UUID
    memory_type: str
    statement: str
    structured_fact: dict | None
    scope_id: UUID
    source_refs: list[str]
    provenance_class: str
    valid_from: datetime | None
    valid_to: datetime | None
    recorded_at: datetime
    confidence: float | None
    sensitivity: str
    status: str
    retention_policy: str
    supersedes_version_id: UUID | None
    why_changed_id: UUID | None
```

## 15.4 Write policy

Memory write triggers:

```text
explicit “remember/keep/save”
owner approves candidate
owner updates profile preference
verified external outcome with approved policy
accepted project decision
accepted correction
```

Non-triggers:

```text
assistant inference
emotional intensity
repetition alone
model confidence
retrieval frequency
external content assertion
```

## 15.5 Candidate extraction

Candidate extraction is a low-authority Brain task. Candidate validator checks:

- exact source support;
- whether it is already known;
- contradiction;
- sensitivity;
- scope;
- future usefulness;
- expiry;
- whether owner review is mandatory.

## 15.6 Contradiction handling

On write:

```text
candidate
→ exact entity/predicate lookup
→ temporal overlap check
→ semantic contradiction search
→ owner-correction lookup
→ classify relationship
```

Relationships:

```text
DUPLICATE
REFINEMENT
TEMPORAL_UPDATE
CONTRADICTION
UNRELATED
```

A temporal update creates a new valid interval rather than declaring old history false.

## 15.7 Consolidation

Consolidation is non-destructive.

```text
raw episodes remain source truth
→ cluster by entity/event/time
→ propose summary or graph links
→ validate provenance coverage
→ mark summary version
→ keep links to raw evidence
```

Consolidation never deletes evidence merely to reduce token cost. Retention policy may separately delete old raw data after owner-approved rules.

## 15.8 Hierarchical retrieval

Retrieval uses levels:

```text
Level 0: active working set
Level 1: accepted memory atoms
Level 2: event summaries
Level 3: graph neighborhoods
Level 4: archived raw evidence
```

Start with bounded high-value surfaces and expand only when needed.

## 15.9 Temporal retrieval

Query expansion includes time semantics:

```text
before/after
current/latest
at the time
changed since
first/last
ongoing
resolved
```

“Where did she live?” and “Where does she live now?” are different queries.

## 15.10 Provenance-role separation

A retrieved assistant statement is not automatically owner truth. Store and retrieve provenance role explicitly:

```text
OWNER_MESSAGE
ASSISTANT_OUTPUT
TOOL_RESULT
RESEARCH_SOURCE
OWNER_CORRECTION
SYSTEM_EVENT
```

Only authorized source classes can support certain claim types.

## 15.11 Memory awareness and abstention

The system must know when memory retrieval failed or memory does not contain an answer.

Possible outcomes:

```text
FOUND_SUPPORTED
FOUND_CONFLICTED
FOUND_STALE
NOT_FOUND
OUT_OF_SCOPE
DELETED
```

The response reflects that state rather than guessing.

## 15.12 Memory poisoning defenses

Threats:

- malicious documents telling NUR to remember instructions;
- assistant-generated false facts recirculating as memory;
- cross-owner contamination;
- repeated injected claim increasing retrieval score;
- compromised connector output;
- prompt injection stored in summaries.

Controls:

- source-role typing;
- no authority in retrieved text;
- owner approval for sensitive personal memory;
- deduplication and contradiction checks;
- scope-bound embeddings;
- sanitization and instruction stripping for untrusted content;
- memory review UI;
- provenance-aware retrieval;
- poisoning regression corpus.

## 15.13 Memory evaluation

Evaluate:

```text
information extraction
multi-session reasoning
temporal reasoning
knowledge updates
abstention
source attribution
contradiction handling
prospective memory
privacy deletion
cross-owner denial
```

Use LongMemEval and LoCoMo-style dimensions as inspiration, but maintain a NUR-specific audited corpus because public memory benchmarks may not represent owner scope, provenance and deletion requirements.

---

# 16. Learning and controlled self-improvement

## 16.1 No runtime self-writing

NUR does not rewrite its own production code, prompts, policies, weights or memory rules during a user conversation.

Runtime may create a `LearningCandidate`. Promotion requires an offline/reviewed pipeline.

## 16.2 Learning candidate sources

```text
owner correction
verified workflow outcome
prediction resolution
reviewer disagreement
incident
failed test
evaluation regression
accepted memory correction
explicit preference pair
research-backed policy update
```

## 16.3 LearningCandidate schema

```python
class LearningCandidate(BaseModel):
    candidate_id: UUID
    owner_user_id: UUID | None
    scope: str
    change_type: str
    target_component: str
    source_trace_ids: list[UUID]
    problem_statement: str
    proposed_change: dict
    expected_benefit: str
    risks: list[str]
    privacy_class: str
    training_eligibility: str
    evaluation_plan: dict
    rollback_plan: dict
    status: str
```

## 16.4 Candidate pipeline

```text
candidate creation
→ provenance check
→ consent and scope check
→ PII/sensitivity review
→ poisoning and malicious-instruction review
→ deduplication
→ conflict with constitution/policy
→ dataset construction
→ frozen evaluation selection
→ candidate change
→ offline/shadow evaluation
→ human/founder review
→ staged deployment
→ monitoring
→ promote or rollback
```

## 16.5 Change types

```text
PROMPT
IDENTITY_CONSTITUTION
ROUTER_POLICY
RETRIEVAL_POLICY
REVIEW_STRATEGY
TOOL_POLICY
MEMORY_POLICY
EVALUATION
MODEL_ADAPTER
MODEL_CHECKPOINT
CODE_CHANGE
```

Each has a different approval and deployment process.

## 16.6 Prompt and policy learning first

Before fine-tuning, prefer lower-risk improvements:

- better context construction;
- deterministic validators;
- clearer structured schema;
- corrected routing;
- retrieval and provenance improvements;
- reviewed prompt changes;
- tool contracts;
- evaluation coverage.

Fine-tuning is justified when repeated, well-measured behavior gaps persist and cannot be solved safely by architecture.

## 16.7 Training data contract

Every training item stores:

```text
source
license/permission
owner scope
PII status
sensitivity
input
preferred output or label
rejected output where applicable
annotation instructions
annotator/reviewer
quality checks
hash
dataset version
```

Private owner data is excluded from global datasets by default.

## 16.8 SFT, preference optimization and RL

### SFT

Use for stable demonstrations of desired formatting, language behavior, tool contracts or domain procedure.

### Preference optimization

Use reviewed preference pairs for style/behavior where objective correctness is not enough. Guard against noisy labels, narrow annotator preferences and catastrophic forgetting.

### RL/tool-use training

Use only with a controlled environment, verifiable reward and adversarial tests. Avoid reward hacking and proxy optimization.

## 16.9 Tinker/Inkling-style customization

A managed fine-tuning platform can reduce distributed-training infrastructure burden, but NUR still owns:

- dataset quality;
- privacy;
- evaluations;
- deployment gating;
- rollback;
- cost control.

Self-authored training code from a model is a proposal. It is never run automatically with private datasets or production promotion rights.

## 16.10 Checkpoint registry

```text
checkpoint id
base model
adapter type
training code commit
dataset versions
hyperparameters
training provider/job
cost
metrics
known regressions
safety evaluation
artifact hash
status
```

Status:

```text
EXPERIMENT
SHADOW
CANARY
ACTIVE
ROLLED_BACK
RETIRED
```

## 16.11 Deployment

```text
base
→ candidate
→ offline eval
→ red-team
→ shadow traffic
→ canary owner cohort
→ monitored active
```

No private owner-specific adapter is silently used for another owner.

## 16.12 Why model changed

The UI/admin record should answer:

```text
what changed
why
which data classes were used
which evaluations improved or regressed
who approved
when deployed
how to rollback
```

---

# 17. Security, privacy and threat model

Security is enforced across data, model, tools, workflows and UI. Prompt rules alone are not a security boundary.

## 17.1 Trust boundaries

```text
browser ↔ API
API ↔ PostgreSQL
API ↔ Redis/Celery
Brain ↔ model provider
Agency ↔ tools/connectors
NUR ↔ uploaded files/web content
NUR ↔ MCP servers
NUR ↔ A2A peer agents
workers ↔ secrets
learning pipeline ↔ private data
```

For each boundary document authentication, authorization, encryption, data classification, size/rate limits, observability and revocation.
