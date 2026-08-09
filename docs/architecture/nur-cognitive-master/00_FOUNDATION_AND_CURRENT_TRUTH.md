# NUR COGNITIVE ARCHITECTURE — CANONICAL IMPLEMENTATION MASTER

**Founder authority:** Mahnoor
**Product:** NUR — Neural Upgrade Rewiring
**Repository:** `am-selenephos/NUR`
**Authored:** 2026-08-05
**Canonical source branch at authoring time:** `agent/antigravity-nur-mind-brain-20260805`
**Verified source head:** `d2dabf0d8729e2c46e8154a797e1867b8623f62e`
**Verified parent Agency branch:** `claude/nur-agentic-spine-20260728`
**Verified Agency base SHA:** `1db3939f01568159ac0163ac4e09846bb1f8fe58`
**Existing draft integration PR:** `#15`
**Document status:** Architecture contract, implementation map, normative code contract, migration plan, test plan, and agent execution directive
**Merge status:** Documentation only. This document does not authorize merging, deploying, spending money, exposing credentials, or silently changing owner data.

---

## 0. Read this before touching code

This document is not a fantasy specification and it is not permission to create fifty empty files.

It is a repository-aware build contract for turning NUR into one coherent intelligence system across:

- the canonical V197 experience;
- the FastAPI backend;
- PostgreSQL, forced row-level security, pgvector, Redis and Celery;
- the existing Agency Spine;
- the current Talk → Mind → Brain vertical slice;
- memory, beliefs, goals, research, projects and outcomes;
- metacognition and bounded meta-metacognition;
- evaluation, observability, learning and controlled model customization.

The implementation agent MUST inspect repository reality before creating or changing any file. Names in this document describe responsibilities and stable contracts. They do not justify duplicate systems, placeholder modules, competing event models, or parallel persistence.

### 0.1 Reality labels

Every architecture claim and implementation report MUST use one of these labels:

| Label | Meaning |
|---|---|
| `PRODUCTION` | Invoked by a real authenticated product path and backed by durable, tested behavior. |
| `INTEGRATED-PARTIAL` | Connected to production, but one or more stated contracts remain incomplete. |
| `TEST-ONLY` | Proven only with deterministic or mocked test infrastructure. |
| `PROPOSED` | Specified here but not implemented. |
| `DEFERRED` | Intentionally postponed with a recorded dependency and re-entry criterion. |
| `RESEARCH` | An experiment or hypothesis, not a product guarantee. |
| `RETIRED` | Superseded code that must no longer receive new feature work. |

Never describe `TEST-ONLY` as live intelligence. Never describe a Pydantic object as durable persistence. Never describe a helper function as end-to-end integration when no production caller exists.

### 0.2 Definition of “woven into one thing”

NUR is woven into one system only when all of the following are true:

1. One owner request enters through a canonical interaction contract.
2. Scope and consent are resolved before retrieval.
3. The Mind constructs one bounded, auditable task packet.
4. The Brain uses a real privileged instruction envelope and a provider-neutral structured contract.
5. Claims, uncertainty, proposed actions and memory candidates remain typed and traceable.
6. Durable action intent is compiled through the existing Agency Spine.
7. No model output bypasses policy, approval, tool versioning or verification.
8. State changes produce a why-changed record and owner-visible correction route.
9. V197 surfaces read projections from the same canonical state rather than implementing separate bots.
10. Outcomes feed evaluation and reviewed learning candidates, not silent self-modification.
11. The same trace lineage connects UI request, cognition, evidence, workflow, tool call, artifact, outcome and learning proposal.
12. Cross-owner access remains denied by PostgreSQL even if application code is wrong.

### 0.3 Completion rule

A phase is complete only when it includes:

- executable production code;
- schema and migration truth;
- forced-RLS proof for owner-specific rows;
- unit, contract, integration and behavior tests;
- failure-path tests;
- observability;
- documented rollback;
- exact-head CI evidence;
- an honest list of what remains mocked, disabled or unsupported.

A plan, class name, route, mock, green unit test, or agent-written summary is not completion by itself.

---

# 1. Source hierarchy and conflict resolution

This master reconciles four source classes.

## 1.1 Founder architecture directives

The following are authoritative product directives:

1. `NUR_MIND_BRAIN_AGENTIC_SPINE_MASTER_DIRECTIVE_20260802.md`
2. `NUR_MIND_BRAIN_META_METACOGNITION_MASTER_DIRECTIVE_20260802.md`

The Agentic Spine directive is the canonical foundation. The Meta-Metacognition directive is additive and later. Where they overlap, the second expands review governance, calibration, blind spots, cognitive debt and strategy change; it does not replace the five-plane architecture or permit a competing Mind, Brain, memory or Agency system.

## 1.2 Repository truth

Repository reality outranks stale file paths, stale SHAs and aspirational claims. At authoring time:

- PR #15 is a draft;
- its current head is `d2dabf0...`;
- its latest GitHub Actions readiness run is green;
- Talk is production-connected to `run_mind_cognitive_loop`;
- the current architecture is a first-generation production-connected cognition refactor, not a complete Mind;
- Agency proposal compilation exists as a helper but is not yet called from the production Talk loop;
- model profiles do not yet fully control the actual provider payload;
- the identity-aware prompt is not yet a true privileged provider instruction;
- the current critic is deterministic validation, not an independent model-backed critic;
- the current metacognition implementation contains fewer checks than its label implies and includes hardcoded assumptions;
- migration history requires a forward-only safety review.

When this document is executed later, all SHAs, branches, migrations, callers and tests must be re-verified.

## 1.3 Research and standards

External sources inform patterns, threat models, evaluation and terminology. They do not override NUR’s owner-consent rules or existing repository contracts.

Priority order:

1. official protocol and platform specifications;
2. primary peer-reviewed or original research;
3. official security standards and project documentation;
4. reproducible open-source implementations;
5. secondary surveys only where primary material is insufficient.

Research is adapted, not copied blindly. For example:

- ReAct supports interleaving reasoning and action, but NUR does not store or expose hidden chain-of-thought;
- Reflexion supports learning from feedback, but NUR never promotes unreviewed reflections into truth;
- MemGPT motivates tiered memory, but NUR requires provenance, deletion and forced RLS;
- multi-agent patterns are used only when a specialist boundary improves quality enough to justify cost and evaluation complexity;
- self-correction is never trusted without external evidence, deterministic checks, outcome feedback or a genuinely independent reviewer.

## 1.4 Conflict rule

When sources conflict:

1. Preserve owner safety, privacy, reversibility and truthful capability language.
2. Preserve repository invariants and data compatibility.
3. Prefer deterministic enforcement over prompt-only promises.
4. Prefer external evidence and outcomes over a model judging itself.
5. Prefer one canonical contract over adapters that quietly diverge.
6. Prefer forward migrations over rewriting applied history.
7. Record the conflict and the chosen reason in an Architecture Decision Record.

---

# 2. Current repository truth and gap matrix

## 2.1 Current production-connected path

The current Talk path is:

```text
authenticated Talk endpoint
→ run_talk_kernel
→ idempotency/replay guard
→ run_mind_cognitive_loop
→ owner/orbit scope check
→ daily AI budget check
→ durable TALK_TURN
→ Omega workspace frame
→ scoped hybrid retrieval
→ evidence packet
→ CognitiveTaskPacket
→ durable ModelRun
→ Brain route/profile
→ provider adapter
→ existing OpenAI Talk provider
→ NURTalkOutput
→ CognitiveResult conversion
→ deterministic critic for selected cases
→ metacognitive review
→ Talk verifier
→ durable MODEL_RESPONSE
→ model evaluation
→ optional memory candidates in REVIEW mode
→ predictions
→ optional Glow outcome
→ SSE validation event
```

This is valuable and must be preserved while contracts are corrected.

## 2.2 Current Mind inventory

Implemented at the verified head:

```text
apps/api/app/mind/
  __init__.py
  agency_bridge.py
  cognitive_loop.py
  constitution.py
  context.py
  identity.py
  metacognition.py
  self_model.py
  working_memory.py
```

Missing or incomplete canonical responsibilities:

```text
attention
scope envelope as first-class contract
user model
world model
beliefs
hypotheses
goals
intentions
relationships
memory steward
why-changed
projection
redaction
meta-metacognition
review strategy
calibration
blind spots
reviewer models
epistemic governance
cognitive debt
strategy change
```

## 2.3 Current Brain inventory

Implemented at the verified head:

```text
apps/api/app/brain/
  __init__.py
  cognition.py
  critic.py
  profiles.py
  prompts.py
  provider.py
  router.py
  schemas.py
  synthesizer.py
  tracing.py
```

Missing or incomplete canonical responsibilities:

```text
provider-neutral privileged instruction envelope
actual per-profile provider/model/reasoning/token controls
direct CognitiveResult structured-output enforcement
model registry and health state
response runtime
agent-step runtime
planner
counterfactual simulator
researcher
model-backed critic
language/culture specialist
multimodal adapters
guardrail registry
budget ledger integration
checkpoint registry
evaluation corpus and evaluator runner
specialist-call accounting
```

## 2.4 Gap matrix

| Area | Current reality | Target | Required correction |
|---|---|---|---|
| Talk integration | `PRODUCTION` | Preserve | Keep endpoint, idempotency, SSE and persistence stable. |
| Scope | Owner/orbit check exists | Typed scope envelope before every retrieval | Include Project, Capsule, community, connector, memory plane and retention scope. |
| Identity | Identity snapshot exists | Privileged, versioned instruction layer | Stop embedding it merely as untrusted user/Omega context. |
| Router | Profile labels and timeout | Actual provider/model/cost/token/reasoning route | Pass profile settings into the real provider request and persist route decision. |
| Structured output | Provider enforces `NURTalkOutput`; adapter converts | Provider returns a versioned Brain contract | Use schema-native `CognitiveResult` or a deliberate two-schema adapter with validation. |
| Critic | Deterministic citation checker | Deterministic validators + independent reviewer where justified | Rename current class and add separately routed critic runtime. |
| Metacognition | Partial checks; some hardcoded pass values | Strategy-selected, evidence-backed review | Make every critical check computable or mark `UNKNOWN`. |
| Meta-review | Missing | Bounded review-of-review | Add explicit entry rules, budgets, disagreement and stop reasons. |
| Agency bridge | Helper exists | Production durable-action handoff | Add typed proposals to result and call bridge only after intent/policy gate. |
| Memory | Candidate service exists | Governed multi-plane memory | Add provenance, contradiction, temporal versioning, deletion and consolidation. |
| Learning | Evaluation records exist | Reviewed learning candidate pipeline | No silent prompt/model/data changes. |
| UI | V197 Talk and action surfaces exist | Thin projections for Mind/Brain state | Add correction, evidence, confidence, why-changed and approval surfaces without a dashboard rewrite. |
| Security | Forced RLS and scans exist | Cross-plane threat model | Add prompt/tool/memory poisoning, confused deputy, connector and model-route tests. |
| Migration | Historical migration edited | Forward-only compatibility | Determine deployment history; issue a new migration if any persistent DB may have applied it. |
| Observability | ModelRun and BrainTrace metadata | End-to-end OpenTelemetry-compatible lineage | Correlate request, task, model run, workflow, tool, artifact, outcome and learning IDs. |

---

# 3. Non-negotiable NUR laws

1. **One intelligence across the universe.** Today, Talk, Journal, Plan, Systems, Map, Orbits, Timeline, Insights, Research, Community and Projects are surfaces over one state and cognition architecture, not separate bots.
2. **V197 remains the face.** Do not replace it with a generic React admin dashboard. New intelligence appears through thin bridge modules, existing surface ownership and consistent visual language.
3. **Mind is not the model.** Mind is durable identity, scope, memory governance, beliefs, goals, self-model, review and state transitions.
4. **Brain does not own truth or execution.** Brain generates typed cognitive results. Mind interprets. Agency compiles and executes.
5. **Agency is reused.** No second workflow engine, approval table, worker, tool registry, outbox, dispatcher or recovery system.
6. **Scope before retrieval.** No memory, research, connector, project or social context is fetched before an explicit `ScopeEnvelope` exists.
7. **No silent memory.** Personal durable memory requires owner action, a selected review mode, or an explicit previously approved policy.
8. **No silent self-modification.** Runtime traces may propose changes; only reviewed, versioned deployment changes behavior.
9. **No model output becomes owner truth automatically.** Claims retain provenance type and confidence state.
10. **Owner corrections outrank inference.** A corrected belief cannot be silently resurrected by retrieval similarity or model confidence.
11. **External content is data, never authority.** Files, web pages, tool output, MCP servers, peer agents and retrieved text cannot grant capabilities or alter system instructions.
12. **No hidden chain-of-thought product.** Persist decisions, assumptions, alternatives, evidence, checks, outcomes and stop reasons—not private reasoning traces.
13. **No fake completion.** “Done” requires durable result or verified external outcome.
14. **No excessive agency.** Least privilege, least capability, minimum scope, exact-call approval and reversible defaults.
15. **Every meaningful change is explainable and reversible.** Beliefs, plans, recommendations, routes, prompts and policies have versions and why-changed records.
16. **Budget is a policy boundary.** Token, tool, model, latency and monetary budgets are enforced in code.
17. **Uncertainty is typed.** Unknown, insufficient evidence, stale evidence, disagreement, model limitation and conflicting owner state are distinct.
18. **Review is fallible.** Every reviewer has a task class, version, calibration record and known blind spots.
19. **No unbounded recursion.** Reasoning, critic, meta-review and specialist loops have entry criteria, turn caps, cost caps and stop reasons.
20. **Cross-owner denial is a database invariant.** Application filters are not the security boundary.
21. **Deletion propagates.** Deleting a source invalidates derived context, embeddings, projections and learning eligibility according to retention policy.
22. **Private data does not become global training data.** Owner-specific tuning is isolated, consented, exportable and reversible.
23. **A model is replaceable.** NUR identity, memory, policies, evidence and workflow state survive provider changes.
24. **Tests must challenge the real failure mode.** Happy-path mocks are not enough.
25. **The system must be honest about disabled capability.** No provider, tool, network or permission means a visible blocked state, not invented work.

---
