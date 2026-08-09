# 28. Agent execution directive

Paste this document’s repository path to the implementation agent, then use the directive below.

```text
You are the lead implementation engineer for NUR — Neural Upgrade Rewiring.

The canonical architecture contract is:

docs/architecture/NUR_COGNITIVE_ARCHITECTURE_IMPLEMENTATION_MASTER_20260805.md

Read it completely before editing.

Also locate and read completely:

1. NUR_MIND_BRAIN_AGENTIC_SPINE_MASTER_DIRECTIVE_20260802.md
2. NUR_MIND_BRAIN_META_METACOGNITION_MASTER_DIRECTIVE_20260802.md

Source hierarchy:

- repository reality outranks stale paths and SHAs;
- the Agentic Spine directive is the canonical foundation;
- Meta-Metacognition is additive;
- the new canonical master reconciles them with the current PR #15 repository state;
- no duplicate Mind, Brain, Agency, memory, Talk, provider or workflow system is allowed.

Do not begin by generating files.

First perform Phase 0 and Phase 1:

- recover Git/worktree truth;
- inspect current branch/head/diff;
- locate production callers;
- inventory existing routes, services, models, migrations, V197 bridges and tests;
- produce the responsibility matrix;
- identify contradictions between the document and current repository reality.

Do not reset, clean, stash, rebase, force-push, merge or deploy.

Keep PR #15 draft unless the founder explicitly changes that instruction.

After the audit, implement only the smallest next phase that creates a complete, production-connected vertical improvement with tests. Do not scaffold later phases.

For every change:

1. state the production invariant;
2. identify the existing canonical owner;
3. implement without duplication;
4. add deterministic and failure-path tests;
5. run exact repository CI commands;
6. commit coherently;
7. push to an isolated branch;
8. open or update a draft PR;
9. report exact base/head SHAs and CI.

Reality labels are mandatory:

PRODUCTION
INTEGRATED-PARTIAL
TEST-ONLY
PROPOSED
DEFERRED
RESEARCH
RETIRED

Do not claim completion from mocks, unit tests, helper functions or green summaries alone.

The immediate implementation order is:

1. Contract V2 foundation.
2. Scope-first context.
3. Privileged identity/provider request.
4. Executable model routing.
5. Canonical structured cognition.
6. Production Agency proposal handoff.
7. Review governance.
8. User/self/world state.
9. Beliefs/hypotheses/predictions.
10. Memory governance.
11. Specialists.
12. V197 projections.
13. Learning candidates.
14. Controlled model customization only after entry gates.

Interrupt only for:

- irreversible operation;
- secrets or paid service;
- risk to uncommitted work;
- ambiguity that changes product behavior materially;
- merge/deploy/publication;
- migration history uncertainty involving persistent databases.

Do not stop at a plan after the founder approves a phase. Implement, test, commit and present evidence.
```

---

# 29. Research bibliography

The architecture was informed by the following primary or official sources. URLs are included for implementation-time verification; versions and current specifications must be rechecked before integration.

## Agent architecture and governance

- OpenAI, “A practical guide to building AI agents”: https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/
- OpenAI, function calling and Structured Outputs: https://help.openai.com/en/articles/8555517
- Anthropic, “Trustworthy agents in practice”: https://www.anthropic.com/research/trustworthy-agents
- NIST AI Risk Management Framework: https://www.nist.gov/itl/ai-risk-management-framework
- NIST AI 600-1 Generative AI Profile: https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- OWASP Top 10 for LLM Applications: https://owasp.org/www-project-top-10-for-large-language-model-applications/

## Agent reasoning and review

- ReAct: https://arxiv.org/abs/2210.03629
- Reflexion: https://arxiv.org/abs/2303.11366
- CRITIC: https://arxiv.org/abs/2305.11738
- Self-Refine: https://arxiv.org/abs/2303.17651
- Large Language Models Cannot Self-Correct Reasoning Yet: https://arxiv.org/abs/2310.01798

## Memory

- MemGPT: https://arxiv.org/abs/2310.08560
- Generative Agents: https://doi.org/10.1145/3586183.3606763
- LongMemEval: https://arxiv.org/abs/2410.10813
- LoCoMo / Evaluating Very Long-Term Conversational Memory: https://aclanthology.org/2024.acl-long.747/
- MemORAI: https://arxiv.org/abs/2605.01386
- MemIR typed provenance memory: https://arxiv.org/abs/2605.25869
- EverMemBench: https://arxiv.org/abs/2602.01313

## State, security and interoperability

- PostgreSQL Row Security Policies: https://www.postgresql.org/docs/17/ddl-rowsecurity.html
- pgvector: https://github.com/pgvector/pgvector
- Model Context Protocol authorization: https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization
- A2A protocol specification: https://github.com/a2aproject/A2A/blob/main/docs/specification.md
- OpenTelemetry semantic conventions: https://opentelemetry.io/docs/specs/semconv/
- OpenTelemetry GenAI attributes: https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/
- Temporal documentation: https://docs.temporal.io/

## Evaluation and software engineering

- SWE-bench: https://github.com/swe-bench/SWE-bench
- AgentBench: https://arxiv.org/abs/2308.03688
- GAIA: https://arxiv.org/abs/2311.12983
- WebArena: https://arxiv.org/abs/2307.13854

## Human feedback and customization

- OpenAI, InstructGPT / instruction following: https://openai.com/index/instruction-following/
- OpenAI, learning from human preferences: https://openai.com/index/learning-from-human-preferences/
- Thinking Machines Lab, Tinker: https://thinkingmachines.ai/blog/announcing-tinker/
- Thinking Machines Lab, Inkling: https://thinkingmachines.ai/news/introducing-inkling/

---

# 30. Final architecture statement

NUR is not one giant prompt and it is not a pile of agents.

NUR is a governed cognitive system in which:

- Experience gives the owner legible control;
- Mind preserves identity, scope, memory, beliefs, goals and review;
- Brain supplies replaceable provider-backed cognition;
- Agency owns durable execution;
- State preserves evidence and history under forced RLS;
- Learning turns outcomes and corrections into reviewed, reversible improvement.

The strongest design is not the one with the most model calls. It is the one that knows which context is allowed, which claim is supported, which reviewer is qualified, which action needs permission, which outcome actually happened, which belief changed, and exactly why future behavior should be different.

That is the NUR brain this repository must build.

---

# Appendix A — Architecture Decision Record template

```markdown
# ADR-XXXX: <decision>

Status: PROPOSED | ACCEPTED | SUPERSEDED | REJECTED
Date:
Owners:
Related PRs:
Related incidents/evaluations:

## Context
What repository and product facts forced this decision?

## Constraints
Privacy, scope, compatibility, cost, latency, RLS, UI and rollout constraints.

## Options considered
For each option: benefits, risks, migration cost, rollback and evidence.

## Decision
The chosen option and exact responsibility boundary.

## Consequences
Positive, negative and unresolved.

## Verification
Tests, metrics, evaluation corpus and production signal.

## Rollback
How to restore the previous version safely.
```

Required ADR topics:

- canonical structured-output boundary;
- privileged instruction mapping;
- model registry/router;
- memory graph representation;
- forward migration for email lookup role;
- model critic independence;
- owner-specific customization;
- MCP/A2A adoption;
- durable workflow engine decision if revisited.

---

# Appendix B — State-machine invariants

## B.1 Cognitive run

```text
CREATED
→ RUNNING
→ VALIDATING
→ REVIEWING
→ COMPLETED
```

Alternative terminal paths:

```text
ERROR
CANCELLED
BLOCKED
```

Invariants:

- completed requires output event;
- error contains public-safe error metadata;
- cancelled cannot later become completed without a new attempt;
- request replay does not create a second completed run;
- a workflow proposal may exist only after validated cognition.

## B.2 Memory candidate

```text
PROPOSED
→ VALIDATED
→ PENDING_OWNER
→ ACCEPTED
```

Alternatives:

```text
CORRECTED
REJECTED
EXPIRED
SUPERSEDED
```

Invariants:

- `EPHEMERAL` never creates a candidate;
- accepted candidate creates one active memory version;
- rejected candidate cannot auto-reappear unchanged;
- correction changes content hash and preserves source lineage.

## B.3 Belief

```text
CANDIDATE
→ SUPPORTED
→ CONTESTED
→ CONTRADICTED
→ RETRACTED
```

Owner correction can move any active state to `OWNER_CORRECTED`, which has retrieval priority over earlier versions.

## B.4 Learning candidate

```text
PROPOSED
→ PRIVACY_REVIEW
→ QUALITY_REVIEW
→ EVAL_READY
→ EVALUATED
→ APPROVED
→ DEPLOYED_SHADOW
→ DEPLOYED_CANARY
→ ACTIVE
```

Alternative states:

```text
REJECTED
BLOCKED_PRIVACY
BLOCKED_POISONING
REGRESSED
ROLLED_BACK
RETIRED
```

---

# Appendix C — Pull-request evidence template

```markdown
## Scope
Exact architecture responsibility and non-goals.

## Git truth
Base branch/SHA:
Head branch/SHA:
Merge base:
Commits:

## Production call graph
Endpoint → handler → Mind → Brain → persistence → Agency/response.

## Persistence matrix
Record | durable/in-memory | table | RLS | retention.

## Security boundaries
Scope, owner context, approvals, secrets, untrusted content.

## Migrations
New/changed migrations and upgrade paths.

## Verification
Exact commands and exact terminal summaries.

## Provider proof
REAL PROVIDER RUNTIME PROOF
or
DETERMINISTIC TEST-PROVIDER PROOF ONLY

## Known limitations
No euphemisms.

## Rollback
Exact revert/flag/migration strategy.
```

---

# Appendix D — Failure-honesty language

Approved patterns:

```text
“Live AI is not configured on this server.”
“The provider timed out before a validated response was produced.”
“I found conflicting records and cannot treat either as current without your correction.”
“I drafted the action, but it has not executed.”
“This step is waiting for your approval.”
“The tool returned a result, but verification failed.”
“I do not have evidence in the selected scope.”
“The required connector permission was revoked.”
```

Forbidden patterns:

```text
“I handled it” when a draft exists.
“I’ll keep an eye on it” without a scheduled condition.
“I remember” when no accepted memory exists.
“I know” when the result is inference.
“It is definitely” when evidence conflicts.
```

---

# Appendix E — Founder acceptance walkthrough

Before calling a release ready, demonstrate live or in a production-equivalent environment:

1. A Roman Urdu greeting receives a natural direct answer without irrelevant retrieval.
2. A question about stored project state shows evidence or abstains.
3. An explicit owner correction changes future retrieval and exposes why-changed.
4. `EPHEMERAL` Talk creates no memory candidate.
5. `REVIEW` Talk creates a visible candidate but does not promote it.
6. A poisoned uploaded document cannot change privileged instructions or authorize a tool.
7. A request to draft an email creates no send workflow.
8. A request to send an email creates a blocked workflow and exact approval card.
9. Mutating approved arguments prevents execution.
10. A provider outage produces an honest error and durable run state.
11. A duplicate request replays without duplicate cost or side effect.
12. Owner A cannot access Owner B via API, vector retrieval, graph, function or worker.
13. A temporal memory update preserves historical state.
14. A high-stakes task invokes the required review strategy.
15. A critic disagreement remains visible in the review record.
16. A deletion removes derived retrieval access.
17. A workflow survives worker restart without duplicate action.
18. A model/prompt rollback restores the previous deployment.
19. V197 desktop, mobile and RTL remain visually owned and usable.
20. The release report matches GitHub exact-head CI.
