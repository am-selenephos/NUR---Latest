## 8.3 Attention and salience

Attention is a deterministic queue, with optional model explanation. The model cannot manufacture an emergency merely because a sentence sounds emotional.

### Candidate sources

```text
new owner message
Journal entry
Plan change
due action
missed action
prediction due
contradiction
Project blocker
returned workflow outcome
relationship correction
new research evidence
Capsule event
security signal
budget threshold
provider or connector failure
```

### Feature vector

```text
owner_pinned
explicit_urgency
deadline_proximity
risk_class
goal_relevance
project_relevance
contradiction_strength
outcome_due
repeat_count
novelty
unresolved_age
scope_match
reversibility
estimated_owner_cost
```

### Example score

```python
score = (
    4.0 * owner_pinned
    + 2.5 * explicit_urgency
    + 2.0 * deadline_proximity
    + 2.0 * risk_weight
    + 1.5 * goal_relevance
    + 1.2 * contradiction_strength
    + 1.0 * repeat_signal
    - 1.0 * stale_penalty
    - 1.5 * dismissed_recently
)
```

The precise formula is configuration, versioned and testable. The UI shows score components in plain language, not a mysterious number.

### Lifecycle

```text
CANDIDATE
ACTIVE
SNOOZED
DISMISSED
RESOLVED
EXPIRED
SUPERSEDED
```

## 8.4 Working memory and context construction

Working memory is a bounded per-run package. It is not the database and it is not a transcript dump.

### Retrieval stages

```text
scope gate
→ task classification
→ exact entity lookup
→ owner-pinned records
→ lexical retrieval
→ vector retrieval
→ graph-neighborhood expansion
→ temporal query expansion
→ contradiction retrieval
→ authority and sensitivity filter
→ deduplication
→ representation selection
→ token-budget packing
→ context manifest
```

### Priority order

```text
owner correction
owner-confirmed fact
owner-pinned record
verified external outcome
active goal/project state
fresh authoritative source
accepted memory
contested belief
hypothesis
model inference
```

### Representation choices

```text
FULL
EXCERPT
STRUCTURED_SUMMARY
ENTITY_FACTS
CLAIM_BUNDLE
TEMPORAL_SLICE
HASH_ONLY
EXCLUDED
```

### Token-budget allocation

Budget is divided deliberately:

```text
privileged instructions
owner request
critical evidence
working state
contradictions
response allowance
review allowance
```

Do not let long low-value history consume the evidence or output budget.

### Context manifest

The manifest records:

```text
included item and representation
excluded item category and reason
retrieval score components
sensitivity decision
token estimate
source version
freshness
owner correction status
```

The manifest is persisted for high-stakes or durable-action runs and may be sampled for routine Talk according to retention policy.

## 8.5 User model

The user model is a typed, correctable claim graph. It must avoid diagnostic certainty, stereotyping and permanent labels from temporary behavior.

### Claim classes

```text
OWNER_STATED
OWNER_CONFIRMED
OWNER_CORRECTED
OBSERVED_PATTERN
NUR_INFERRED
RESEARCH_DERIVED
CONTRADICTED
RETRACTED
```

### Claim schema

```text
claim id
statement
predicate/entity form
scope
provenance
source evidence
counter-evidence
confidence
sensitivity
status
effective time
recorded time
expiry/review time
owner confirmation state
may_be_wrong_about
why-changed id
```

### Promotion rules

- `NUR_INFERRED` cannot become `OWNER_CONFIRMED` without owner confirmation.
- Sensitive medical, psychological, religious, sexual, political or relational inferences remain non-durable unless explicitly saved.
- Repeated language does not automatically prove a stable preference.
- A direct owner correction immediately blocks the contradicted inference from retrieval as truth.
- Historical versions remain auditable but not active.

## 8.6 Self model

The self model is computed from server state and deployment records, not invented by the language model.

### Required fields

```text
identity version
prompt versions
provider registry
model routes
provider health
configured credentials: boolean only
available tools and capabilities
approval policy summary
current budget
rate limits
active workflow load
known model limitations
recent failure classes
known regressions
last successful external action
current deployment version
```

### Capability statements

The response synthesizer maps self-model state to approved language:

```text
CAN_NOW
CAN_PROPOSE
REQUIRES_APPROVAL
REQUIRES_CONNECTION
REQUIRES_OWNER_INPUT
DISABLED
UNSUPPORTED
UNKNOWN
```

Example:

```text
“I can draft the email now. Sending it requires the Gmail connection and an exact-call approval.”
```

Not allowed:

```text
“I sent it” when only a draft was generated.
“I checked your email” without a connector read.
“I will keep monitoring” without a scheduled workflow.
```

## 8.7 World model

The world model is an evidence-aware temporal property graph projected from canonical NUR records.

### Entity classes

```text
OWNER
PERSON
ORGANIZATION
PROJECT
SYSTEM
GOAL
PLAN
ACTION
EVENT
RESOURCE
DOCUMENT
RESEARCH_SOURCE
CLAIM
BELIEF
HYPOTHESIS
PREDICTION
OUTCOME
ARTIFACT
TOOL
LOCATION
```

### Edge classes

```text
RELATES_TO
PART_OF
DEPENDS_ON
BLOCKS
SUPPORTS
CONTRADICTS
CAUSED_BY_CANDIDATE
PRECEDES
FOLLOWS
OWNS
SHARED_WITH
REQUIRES
SATISFIES
SUPERSEDES
DERIVED_FROM
```

### Edge properties

```text
source refs
valid time
recorded time
confidence
status
scope
sensitivity
owner confirmation
model/prompt version
why-changed
```

### Causal restraint

Causal edges begin as `CAUSED_BY_CANDIDATE`. Promotion requires:

- owner confirmation;
- domain evidence;
- repeated verified outcomes; or
- a reviewed research basis.

Correlation, temporal ordering and causal claim are never conflated.

## 8.8 Beliefs, hypotheses and predictions

These are separate systems with related evidence.

### Belief

A durable working proposition used in future reasoning.

```text
CANDIDATE
SUPPORTED
CONTESTED
CONTRADICTED
OWNER_CORRECTED
STALE
RETRACTED
```

### Hypothesis

A testable explanation that remains explicitly uncertain.

```text
OPEN
TESTING
SUPPORTED_PARTIAL
REFUTED
ABANDONED
```

### Prediction

A time-bound expected outcome with a resolution method.

```text
OPEN
DUE
RESOLVED_TRUE
RESOLVED_FALSE
RESOLVED_PARTIAL
UNRESOLVABLE
CANCELLED
```

### Evidence rules

Every belief or hypothesis stores:

```text
evidence_for
evidence_against
owner corrections
source authority
freshness
alternative explanations
falsification condition
next review date
```

Every prediction stores:

```text
stated probability
resolution date
resolution source
outcome
Brier/log score where applicable
error direction
review strategy
```

## 8.9 Goals and intentions

Goals are owner-level desired states. Intentions are temporary system commitments.

### Goal hierarchy

```text
VALUE
→ LIFE_DIRECTION
→ SYSTEM_GOAL
→ OBJECTIVE
→ PLAN
→ ACTION
→ OUTCOME
```

### Intention arbitration

Inputs:

```text
explicit owner request
owner priority
deadline
capacity
risk
cost
dependencies
reversibility
scope
current workflow load
conflicting goals
```

Outputs:

```text
RESPOND
CLARIFY
RESEARCH
PROPOSE_MEMORY
PROPOSE_BELIEF_CHANGE
PROPOSE_WORKFLOW
WAIT_FOR_OUTCOME
DEFER
BLOCK
```

The Mind may propose a different intention when constraints make the request impossible, but it must explain the conflict and preserve owner control.

## 8.10 Relationship continuity

Relationship continuity is interaction policy, not a claim that software has human emotion.

Store only owner-approved or operationally necessary state:

```text
preferred name
pronouns/address style
formality
tone preference
language/script preference
known communication boundaries
unresolved correction
recent misunderstanding
repair requested
privacy preference
follow-up preference
```

Never store as factual state:

```text
“NUR is jealous”
“NUR needs the owner”
“NUR is the owner’s only relationship”
“NUR is conscious”
```

Warm language may be part of voice, but durable state remains truthful.

## 8.11 Memory steward

The memory steward controls proposal, conflict detection, review, promotion, expiry and deletion.

### Candidate types

```text
FACT
PREFERENCE
BOUNDARY
PERSON
DECISION
PROJECT
GOAL
PATTERN
OUTCOME
CORRECTION
PROCEDURE
```

### Candidate requirements

```text
source event
exact proposed memory
scope
sensitivity
reason to remember
expected future use
retention proposal
conflicting records
confidence
owner review requirement
```

### Promotion

```text
CANDIDATE
→ VALIDATED
→ OWNER_APPROVED
→ ACTIVE
```

or:

```text
CANDIDATE
→ CORRECTED
→ OWNER_APPROVED
→ ACTIVE
```

Rejection records the reason so the same inference is not repeatedly proposed.

## 8.12 Why-changed ledger

Create a generic append-only change explanation contract for:

```text
belief
user-model claim
world edge
plan
recommendation
route policy
prompt
identity
memory
review strategy
```

Required fields:

```text
entity type/id
previous version
new version
change class
trigger
supporting evidence
counter-evidence
owner correction
model/prompt/policy versions
actor
occurred_at
affected future behavior
rollback target
```

The record is an explanation of the state transition, not chain-of-thought.

## 8.13 Projection and redaction

Mind state is not sent raw to the browser or model.

Projection chooses the owner-visible representation. Redaction removes:

- secrets;
- unnecessary PII;
- hidden system policy;
- connector tokens;
- raw sensitive evidence when a summary suffices;
- cross-scope identifiers;
- internal abuse-detection details.

Redaction decisions themselves are testable and versioned.

---

# 9. Metacognition and meta-metacognition

## 9.1 Metacognition is a review process, not a magic adjective

A review checks whether a result meets a task-specific standard. It must not be a fixed checklist with hardcoded `True` values.

Every check returns:

```text
PASS
WARN
FAIL
UNKNOWN
NOT_APPLICABLE
```

`UNKNOWN` is not treated as `PASS`.

## 9.2 Review strategy selection

The Mind selects a `ReviewStrategy` before review.

### Strategy examples

#### Routine conversational response

```text
schema validation
capability honesty
forbidden-claim scan
basic evidence linkage
latency budget
```

#### Research synthesis

```text
claim-evidence coverage
source authority
freshness
contradiction search
citation validity
uncertainty
```

#### Software/code change

```text
repository truth
call-graph proof
type/lint/test gates
migration compatibility
security boundaries
rollback
diff scope
```

#### Durable external action

```text
intent confirmation
scope
capability
argument completeness
risk and reversibility
approval binding
verification contract
```

#### Medical/legal/financial

```text
current authoritative sources
jurisdiction and date
uncertainty
professional escalation
no diagnostic or guaranteed outcome claim
```

#### Relationship interpretation

```text
owner-stated facts over inference
alternative explanations
sensitivity
no diagnosis
no certainty about another person’s internal state
```

### Strategy record

```text
strategy id/version
task class
selection reason
alternatives rejected
stakes
required deterministic checks
required reviewers
evidence threshold
max review cycles
cost/latency budget
stop condition
```

## 9.3 Deterministic validators

Deterministic checks run before model review:

- Pydantic/JSON Schema validation;
- citation IDs exist in packet;
- no source ref outside scope;
- no proposed tool outside registry;
- required action arguments present;
- token/cost budget respected;
- owner correction conflict detected;
- forbidden claims and fake-completion patterns;
- output fields obey cardinality bounds;
- approval-required actions remain proposals;
- secrets and raw credentials absent;
- timestamps and versions valid.

## 9.4 Independent model critic

A model critic is independent only when its invocation and context are meaningfully separated from the generator.

Minimum independence:

- separately routed critic profile;
- explicit critic instruction;
- generator output presented as untrusted candidate;
- original evidence and scope available;
- no automatic access to generator’s private reasoning;
- critic result typed and persisted;
- critic cannot execute tools;
- critic performance measured separately.

For highest stakes, use provider or model diversity when cost and privacy permit. Same-model self-review is acceptable only as a lower-confidence reviewer and never the only gate for irreversible action.
