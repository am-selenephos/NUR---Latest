# Appendix F — Glossary

**Agency Spine:** Existing durable workflow, policy, approval, tool and recovery infrastructure.

**Brain:** Replaceable provider-backed computation that returns typed cognitive results.

**Cognitive debt:** An unresolved cognitive-system liability likely to affect future decisions.

**CognitiveResult:** Canonical Brain output containing response, claims, uncertainty and proposals.

**Context manifest:** Auditable account of included/excluded context and token packing.

**Evidence:** A scoped source observation that may support or contradict a claim.

**Experience plane:** V197 and other owner-facing surfaces.

**Mind:** Durable governance layer for identity, scope, memory, beliefs, goals and review.

**Meta-metacognition:** Bounded review of whether the review strategy and reviewer were appropriate.

**Owner truth:** Information explicitly stated or confirmed by the owner, still subject to temporal updates and correction.

**Proposed action:** Brain output suggesting an action; it has no execution authority.

**Scope envelope:** Typed boundary that controls which data, connectors and memory planes may be used.

**Why-changed:** Versioned explanation of a durable state transition, excluding hidden chain-of-thought.

**Workflow proposal:** Typed plan candidate compiled and governed by Agency.

---

# Appendix G — Immediate next branch

The first implementation branch after this documentation should not begin beliefs or a giant file tree. It should repair the contract boundary:

```text
feat/cognition-contract-v2
```

Its exact scope:

- introduce versioned V2 contracts;
- keep visible Talk behavior compatible;
- add provider request separation contract;
- add route decision contract;
- add tests proving evidence/owner/trace lineage;
- do not yet change external action execution;
- do not yet add long-term beliefs or fine-tuning.

Only after this branch is green should the privileged provider mapping and Agency handoff branches begin.
