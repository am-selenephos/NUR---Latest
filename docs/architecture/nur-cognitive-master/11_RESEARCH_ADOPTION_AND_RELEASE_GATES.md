## 24.1 Agent orchestration

### OpenAI practical agent guidance

Adopt:

- model + tools + instructions as explicit components;
- start with one central agent and add specialists only when justified;
- manager pattern for a unified user experience;
- standardized, tested tool definitions;
- explicit exit conditions and guardrails.

Adapt:

- NUR’s manager is split into Mind governance and Brain cognition;
- durable execution remains outside the model loop in Agency;
- tools are never globally exposed merely because a model can select them.

Reject:

- any interpretation that a general model loop should directly own irreversible execution.

### Anthropic trustworthy-agent guidance

Adopt:

- preserve meaningful human control;
- treat prompt injection as a layered systems problem;
- use constrained permissions and visible oversight;
- evaluate real autonomy and failure modes, not branding.

Adapt:

- owner approval is bound to exact calls;
- NUR adds forced-RLS and memory provenance as foundational controls.

## 24.2 ReAct and reasoning/action loops

Adopt:

- observations from tools can improve plans;
- actions and reasoning need a structured loop;
- exception handling and exit conditions matter.

Adapt:

- persist decision summaries and typed state transitions instead of hidden reasoning traces;
- Agency, not the model, executes actions;
- every observation remains typed and untrusted until validated.

Reject:

- storing raw chain-of-thought as a long-term memory source;
- unconstrained action loops.

## 24.3 Reflexion and verbal feedback

Adopt:

- outcome feedback can produce useful strategy candidates;
- failure summaries can inform future attempts.

Adapt:

- reflections are `LearningCandidate` or procedural-memory candidates;
- they require provenance, evaluation and review;
- failures from one owner do not become global policy automatically.

Reject:

- self-generated reflection as sufficient proof that behavior improved.

## 24.4 CRITIC and external-tool feedback

Adopt:

- external evidence and tools can make review more reliable;
- factual, code and safety checks should use the appropriate verifier.

Adapt:

- deterministic validators run before expensive model critics;
- critic tools are read-only and scoped;
- review strategy determines which external checks are required.

## 24.5 Self-Refine and intrinsic self-correction limits

Adopt:

- one or two bounded refinement cycles may improve some outputs;
- refinement should operate on explicit feedback.

Constraint:

Research also shows intrinsic self-correction can fail or degrade reasoning without external feedback. Therefore NUR never treats “review your answer” as a high-stakes guarantee.

Implementation consequence:

```text
deterministic validation
+ external evidence/outcome
+ independent reviewer where justified
> same-model self-critique alone
```

## 24.6 MemGPT and tiered memory

Adopt:

- context is a limited working set;
- memory tiers should move relevant information into active context;
- long-running interaction requires explicit memory management.

Adapt:

- tiers are governed by scope, provenance, temporal state and deletion;
- source events remain auditable;
- the model does not autonomously write unrestricted core memory.

## 24.7 Generative Agents

Adopt:

- observation, planning and reflection are distinct functions;
- event history can support higher-level summaries;
- retrieval quality is central to coherent behavior.

Adapt:

- NUR is an owner-support product, not a simulation of human life;
- no claim of humanlike emotion or consciousness;
- reflection is governed and cannot overwrite owner truth.

## 24.8 LongMemEval and LoCoMo

Adopt evaluation dimensions:

```text
extraction
multi-session reasoning
temporal reasoning
updates
abstention
event summarization
```

Adapt:

- add provenance roles, correction, deletion, prospective memory and RLS;
- audit benchmark answer quality;
- maintain a private NUR regression corpus with known source truth.

## 24.9 2026 graph/provenance memory research

Recent work emphasizes provenance-enriched graphs, typed memory representations, temporal organization, conflict handling and bounded hierarchical retrieval.

Adopt:

- immutable evidence linked to typed claims;
- property graph or hyperedge-like relations where multi-party context needs it;
- non-destructive consolidation;
- query-adaptive graph retrieval;
- temporal versions;
- conflict detection at write time.

Do not adopt unverified benchmark claims as product guarantees. Implement concepts behind feature flags and compare against simpler baselines.

## 24.10 NIST AI RMF and GenAI Profile

Adopt governance structure:

```text
GOVERN
MAP
MEASURE
MANAGE
```

Use it to organize:

- accountable owners;
- use-case context;
- data and model risk;
- evaluation and monitoring;
- mitigation and incident response;
- lifecycle retirement.

## 24.11 OWASP LLM/agentic risks

Adopt explicit controls for:

- prompt injection;
- insecure output handling;
- training and memory poisoning;
- denial of service/wallet;
- supply chain;
- sensitive disclosure;
- insecure tools/plugins;
- excessive agency;
- overreliance.

NUR adds owner-scope, Agency approval and long-term memory poisoning as first-class architecture.

## 24.12 MCP

Adopt:

- typed tools/resources;
- transport authorization where supported;
- environment-based credentials for local stdio where appropriate;
- OAuth-based HTTP authorization;
- explicit resource owner and revocation.

Reject:

- treating an MCP server as trusted merely because it is connected;
- exposing all server tools to every Brain task;
- allowing server content to change system authority.

## 24.13 A2A

Potential future use:

- capability discovery;
- task delegation;
- asynchronous task state;
- structured artifacts.

Constraints:

- peer agents are external trust domains;
- NUR keeps the owner-visible Conductor;
- delegation requires capability, scope, budget, audit and completion verification;
- governance and dissent require NUR’s own layer above the protocol.

## 24.14 PostgreSQL RLS

Adopt:

- enable and force row-level security;
- default deny;
- narrow roles;
- explicit policies;
- test as application roles;
- treat BYPASSRLS as exceptional.

## 24.15 pgvector

Adopt as one retrieval index inside PostgreSQL, alongside lexical, temporal and graph retrieval. Keep source records and metadata canonical; embeddings are invalidated on correction/deletion.

## 24.16 OpenTelemetry

Adopt standard semantic names where stable and appropriate for:

- provider/model operations;
- retrieval;
- tool execution;
- workflow invocation;
- token usage;
- HTTP/database/messaging spans.

Protect sensitive message and instruction content; record versions/hashes and opt-in redacted samples rather than raw payloads.

## 24.17 Durable execution systems

Temporal-style durable execution validates the general architecture principle that business workflows should survive crashes from durable history. NUR already has Agency primitives; evaluate replacement or integration only if current recovery, timers and orchestration become demonstrably insufficient. Do not rewrite a functioning Agency Spine for fashion.

## 24.18 Human feedback, SFT and preference training

Adopt:

- curated demonstrations;
- pairwise preferences;
- held-out evaluation;
- awareness that annotator preferences are not universal truth;
- explicit privacy and PII handling.

Constraint:

Model alignment depends on deployment architecture as well as weights. Fine-tuning does not replace scope, policy, RLS or approval.

## 24.19 Tinker and Inkling

Adopt as a possible later experimentation path for controlled adapters/checkpoints, especially when lower-level training primitives and LoRA reduce infrastructure burden.

Do not:

- auto-upload private NUR history;
- let a model choose its own training data and deploy itself;
- spend money without approval;
- promote a self-evaluated checkpoint.

---

# 25. Anti-patterns and explicit prohibitions

## 25.1 Architecture anti-patterns

```text
one bot per UI page
second workflow engine
second memory database as truth
model directly writes beliefs
model directly executes tools
flat transcript dump into every prompt
vector similarity as truth
all context available to all agents
identity prompt embedded as user data
same-model critic called “independent”
hardcoded pass checks
historical migration rewrite
```

## 25.2 Implementation anti-patterns

```text
empty files with TODOs
unused schema arguments
classes with no production caller
mock-only “integration”
noqa to hide design mistakes
swallowing privilege errors
manual test-count arithmetic
blind npm audit fix
force push without need
agent summaries without diff/CI proof
```

## 25.3 Learning anti-patterns

```text
train on raw private chats
train on assistant outputs as truth
optimize engagement
promote owner-specific preference globally
self-grade and self-deploy
no frozen holdout
no rollback
no dataset lineage
```

## 25.4 Product anti-patterns

```text
fake sentience claims
exclusive dependency language
hidden memory
hidden action
fake completion
unclear approval
unexplained recommendation changes
```

---

# 26. Definition of actually complete

NUR Mind + Brain is not “complete” because all future intelligence is solved. It is release-complete for a defined version when:

## 26.1 Interaction

- every canonical Talk request is scope-first;
- identity is privileged and versioned;
- model route is real;
- output is canonical structured cognition;
- evidence and uncertainty are valid;
- replay/cancellation/failure work;
- V197 surfaces are coherent.

## 26.2 Action

- explicit durable intent creates a proposal;
- ordinary Talk creates none;
- Agency owns plan compilation and execution;
- approval is exact-call bound;
- outcome is verified;
- crash recovery is proven.

## 26.3 Memory and state

- accepted memory is provenance-aware and correctable;
- beliefs/hypotheses/predictions are distinct;
- temporal updates work;
- deletion propagates;
- cross-owner isolation is proven;
- why-changed is visible.

## 26.4 Review

- deterministic validation exists;
- model critic is honestly labeled and separately measured;
- review strategy matches task;
- meta-review is bounded;
- calibration and blind spots update from outcomes.

## 26.5 Learning

- corrections and outcomes create reviewed candidates;
- private data policy is enforced;
- frozen evaluations gate changes;
- deployment and rollback are recorded;
- no silent runtime self-modification.

## 26.6 Operations

- full CI green;
- security test corpus green;
- observability and budgets active;
- runbooks exist;
- exact deployment version known;
- known limitations are owner-visible.

---

# 27. Required CI and release gates

## Backend

```text
python -m ruff check app
python -m pytest
clean Alembic upgrade
released-snapshot upgrade
migration role/security assertions
PostgreSQL integration
Redis/Celery/Agency integration
RLS cross-owner suite
```

## Web/mobile

```text
npm ci
naming scan
secret scan
web typecheck
web unit tests
production build
mocked Talk E2E desktop/mobile
approval E2E
memory/correction E2E
RTL and accessibility
mobile typecheck
npm audit --audit-level=high
```

## Model/evaluation

```text
provider contract tests
identity corpus
structured-output corpus
prompt-injection corpus
memory corpus
high-stakes review corpus
route/cost regression
shadow comparison
```

## Release report

The agent must report exact outputs, not a story.
