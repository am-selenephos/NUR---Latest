## 9.5 Meta-metacognition: review the reviewer

Meta-review asks whether the selected review process was appropriate and effective.

Entry criteria:

```text
high or critical stakes
reviewer disagreement
owner correction of a reviewed result
repeated failure class
large confidence/outcome error
policy or prompt change
new model deployment
unresolved deterministic warning
```

Meta-review questions:

```text
Was the correct review strategy selected?
Did the review test the real failure mode?
Was evidence authority appropriate?
Did reviewers share the same model or prompt blind spot?
Was the critic calibrated for this task class and language?
Did the review over-escalate or under-escalate?
Was a known owner correction ignored?
Did verbosity masquerade as depth?
Would external verification resolve the uncertainty?
Is another cycle worth its cost and latency?
```

## 9.6 Reviewer performance model

Each reviewer version tracks:

```text
task classes
languages
false-positive rate
false-negative rate
missed contradiction rate
owner correction rate
over/under escalation
confidence calibration
cost
latency
known blind spots
last evaluated
active authority state
```

Authority states:

```text
ACTIVE
LIMITED
SHADOW
SUSPENDED
RETIRED
```

A reviewer that repeatedly misses a class loses authority for that class until re-evaluated.

## 9.7 Calibration engine

Calibration compares stated confidence with outcomes.

Metrics by task class, profile, reviewer, language and source type:

- Brier score;
- log loss where appropriate;
- expected calibration error;
- coverage versus accuracy;
- abstention quality;
- overconfidence frequency;
- underconfidence frequency;
- correction rate.

Do not force fake numerical confidence for purely subjective responses. Use categorical uncertainty when probabilities are not meaningful.

## 9.8 Blind-spot registry

Blind spots are versioned operational findings:

```text
blind spot id
description
affected task class
models/reviewers
triggering incidents
detection heuristic
mitigation
residual risk
review date
```

Examples:

- same-model confirmation bias;
- English-source dominance in Roman Urdu tasks;
- recency bias;
- source-position bias;
- over-trusting owner-like retrieved text;
- confusing plan completeness with executability;
- missing revoked connector permission;
- treating absence of evidence as evidence of absence.

## 9.9 Cognitive debt

Cognitive debt represents unresolved architecture or knowledge liabilities that can degrade future decisions.

Examples:

```text
stale belief with high downstream use
unresolved contradiction
unreviewed prompt regression
missing evaluation coverage
known reviewer blind spot
pending deletion propagation
historical migration ambiguity
unsupported language path
```

Debt has severity, owner, affected surfaces, deadline and blocking policy.

## 9.10 Strategy change governance

A review strategy changes only through:

```text
failure/outcome evidence
→ strategy-change proposal
→ impact analysis
→ frozen regression suite
→ shadow evaluation
→ approval
→ versioned deployment
→ monitoring
→ rollback
```

## 9.11 Stop rules

No review loop continues because “more thinking might help.” Stop when:

- all required checks pass;
- unresolved uncertainty is irreducible without owner input or external evidence;
- cost or latency cap is reached;
- additional reviewer is not sufficiently independent;
- repeated cycles produce no material change;
- the correct outcome is to abstain, clarify or block.

Persist the stop reason.

---

# 10. Brain plane — provider-backed cognition

The Brain is replaceable cognition infrastructure. It owns model calls and typed outputs, not durable truth, personal memory or action authority.

## 10.1 Canonical task classes

Use stable enums, not uncontrolled free text:

```text
DIRECT_RESPONSE
CLASSIFICATION
CONTEXT_SUMMARY
MEMORY_CANDIDATE
BELIEF_REVIEW
RESEARCH_QUERY
RESEARCH_SYNTHESIS
PLAN_CONSTRUCTION
COUNTERFACTUAL_SIMULATION
HIGH_STAKES_REVIEW
CODE_OR_PROJECT_TASK
WORKFLOW_PROPOSAL
MULTIMODAL_INTERPRETATION
TRANSLATION
LANGUAGE_REPAIR
```

## 10.2 Model registry

The registry maps logical profiles to actual provider capabilities.

Each model deployment stores:

```text
provider
provider model id
logical deployment id
supported modalities
structured-output support
tool support
reasoning controls
context limit
output limit
latency distribution
cost schedule
privacy/data policy
region
health
known failure classes
evaluation scores
active date
retirement date
```

Provider names and model IDs are configuration, not hardcoded across domain modules.

## 10.3 Profiles are executable policy

Profiles must change the real request, not just metadata.

```text
FAST
BALANCED
DEEP
CRITIC
RESEARCH
MULTIMODAL
TRANSLATION
```

Each profile defines:

```text
allowed providers/models
reasoning effort
max input/output tokens
timeout
retry policy
max model calls
max specialist calls
max tool proposals
cost ceiling
latency target
required structured schema
required reviewers
fallback chain
```

If the selected provider does not support a requested control, the adapter either maps it explicitly or rejects the route. It does not silently pretend the control was applied.

## 10.4 Router

Routing factors:

```text
task class
stakes
complexity
context size
modality
language
structured-output reliability
required tools
latency target
budget
privacy policy
provider health
review requirement
```

Router output:

```text
route decision id
profile
provider/model deployment
reason
alternatives
estimated tokens/cost/latency
fallback chain
policy versions
```

### Routing algorithm

Start deterministic. A model may advise, but code enforces eligibility and budget.

```python
eligible = registry.filter(
    task=packet.task_class,
    modality=packet.modalities,
    privacy=packet.scope.provider_policy,
    schema=packet.required_output_schema,
)
eligible = [m for m in eligible if m.health == "HEALTHY"]
eligible = [m for m in eligible if estimated_cost(m, packet) <= packet.budget.max_cost_cents]
selected = rank(eligible, quality_weight, latency_weight, cost_weight)
```

No eligible model means `BLOCKED_CAPABILITY`, not silent fallback to an incompatible path.

## 10.5 Provider boundary

Only provider adapters call external model APIs.

Normative interface:

```python
class BrainProvider(Protocol):
    name: str

    async def generate_structured(
        self,
        *,
        request: ProviderRequest,
        output_model: type[BaseModel],
        event_sink: EventSink | None,
    ) -> ProviderResult: ...

    async def embed(self, *, texts: list[str], model: str) -> EmbeddingResult: ...

    async def health(self, deployment: ModelDeployment) -> ProviderHealth: ...
```

Provider request contains distinct privileged and untrusted fields:

```text
system_instructions
developer/task instructions
owner message
untrusted evidence blocks
tool definitions
schema
model controls
budget
timeout
trace context
```

The adapter must not hide privileged instructions inside owner content or Omega context.

## 10.6 Structured output

The provider returns the schema required by the task, preferably `CognitiveResultV2` for central cognition.

If a provider can only enforce a different schema, the adapter documents a two-stage boundary:

```text
provider schema
→ validated adapter conversion
→ canonical schema
```

Conversion failures are typed and fail closed. The `output_schema` argument cannot exist unused.

## 10.7 Prompt architecture

Prompt layers are versioned separately:

```text
constitution
security boundary
surface/task policy
profile policy
output schema instructions
owner request
untrusted evidence
```

Evidence is delimited and labeled as untrusted. Tool output is structured and never concatenated into privileged instructions.

Prompt records store:

```text
prompt id/version
content hash
change reason
owner/product approval
evaluation suite
active deployment
```

Raw private prompt payload logging is off by default. Store hashes, versions, token counts and redacted summaries.

## 10.8 Conductor

The Conductor retains final synthesis and user interaction ownership.

Responsibilities:

```text
interpret task packet
choose direct answer or specialist path
request missing information
sequence bounded specialists
combine results
honor review strategy
return canonical CognitiveResult
```

The manager pattern is preferred over uncontrolled peer handoffs because NUR requires one identity, one scope and one approval owner.

## 10.9 Planner

Planner output is a typed plan, not prose bullets.

Required fields:

```text
objective
success criteria
assumptions
missing information
steps
dependencies
reversible/irreversible flags
tool/capability requirements
approval points
cost/time estimates
verification criteria
rollback/recovery
```

Planner does not persist Agency rows. It returns a candidate.

## 10.10 Counterfactual simulator

Simulation compares paths under explicit assumptions.

For each scenario:

```text
assumption set
path
expected benefits
risks
dependencies
reversibility
unknowns
evidence basis
what would change the conclusion
```

Do not fabricate precise probabilities. When probabilities are used, state elicitation method and calibration class.

## 10.11 Researcher

Researcher creates a query plan and evidence graph.

```text
question
scope and freshness requirement
source class preference
queries
primary sources
counter-sources
authority/freshness score
claims
citations
unresolved contradictions
```

Researcher cannot grant itself browser, connector or payment authority. It receives approved read tools from Agency/runtime policy.

## 10.12 Deterministic evidence validator

Rename the current “critic” according to what it actually does, for example:

```text
EvidenceValidator
ClaimCoverageValidator
```

Responsibilities:

- source ref exists;
- ref is in scope;
- claim has support where required;
- output contains no invented refs;
- evidence and claim version align;
- unsupported claim policy is respected.

## 10.13 Model critic

The model critic receives:

```text
review strategy
candidate result
owner request
evidence bundle
known corrections
capability state
```

It returns:

```text
verdict
failed checks
unsupported claims
contradictions
missing evidence
risk escalation
recommended disposition
confidence
```

Disposition:

```text
PASS
PASS_WITH_WARNING
REVISE
REQUEST_EVIDENCE
REQUEST_OWNER_INPUT
BLOCK
```

## 10.14 Synthesizer

The synthesizer maps canonical cognitive output to surface-safe output. It may rephrase but cannot change claim status, remove required uncertainty, add capabilities or convert a proposal into completion.

## 10.15 Language and culture specialist

Use when translation or language identity requires more than a simple locale instruction.

It verifies:

- natural Roman Urdu/Hinglish rather than transliteration sludge;
- script preference;
- pronouns and address style;
- technical term consistency;
- preservation of epistemic qualifiers;
- cultural idioms without invented familiarity.

## 10.16 Multimodal adapters

Adapters produce observations, not conclusions.

```text
ImageAdapter
DocumentAdapter
AudioAdapter
VideoAdapter
```

Each observation includes source segment, confidence and model version. High-impact interpretations require review or owner confirmation.

## 10.17 Brain trace

Brain trace stores operational summaries:

```text
route
prompt versions
model deployment
step names
timing
token usage
cost
validator results
review decisions
stop reason
```

It does not store hidden chain-of-thought.

## 10.18 Failure classification

```text
PROVIDER_DISABLED
PROVIDER_MISCONFIGURED
AUTHENTICATION
RATE_LIMIT
QUOTA
UNSUPPORTED_MODEL
TIMEOUT
NETWORK
SCHEMA_INVALID
SAFETY_BLOCK
BUDGET_EXCEEDED
CONTEXT_TOO_LARGE
NO_ELIGIBLE_ROUTE
CANCELLED
UNKNOWN_PROVIDER_ERROR
```

Retry only transient classes and only before irreversible side effects. Retrying a model generation after visible streaming requires reconciliation.

---

# 11. Mind–Brain contracts
