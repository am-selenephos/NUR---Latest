# NUR Agentic Insights Responsibility Matrix

Updated: 2026-08-09

This matrix records the implementation boundary for the first Agentic Insights
release. It prevents a second intelligence stack from being built beside NUR's
canonical Experience -> Mind -> Brain -> State -> Outcomes -> Memory -> Omega
path. `CREATE` below means the smallest missing persistence or service contract,
not a replacement domain.

## Source Authority

- Repository: `am-selenephos/NUR`
- Continuation branch: `agent/nur-completion-foundation-20260809`
- Audited head before this slice: `5ce3efa578d955563c3cb60d54cd4a5312c1c3e6`
- Canonical presentation: `apps/web/public/v197/NUR_V197_CHECKBOX_TICK_RESTORED.html`
- Presentation law: the V197 source, geometry, assets, canvas ownership, and RAF
  ownership remain unchanged. Agentic Insights extends only API contracts and
  the nonvisual bridge.

## Responsibility Matrix

| Requirement | Existing canonical owner | Production caller | Persistence | Existing proof | Gap | Decision |
|---|---|---|---|---|---|---|
| Canonical owner events | Cognition and domain services | Talk, Journal, Plans, Living, Timeline, Projects, Research, Community | `cognitive_events`, `domain_events` | Cognition, Living, Timeline, Project, memory, Glow tests | Events are not projected incrementally into one feature contract | EXTEND bounded projection from `CognitiveEvent`; do not add another event ledger |
| Normalized observation | Omega experience service | Omega consolidation worker | `omega_experiences` | `test_omega.py` | Missing explicit domain/features/explicitness/retention/invalidation fields | EXTEND `OmegaExperience` and its ingestion service |
| Cross-domain pattern | Omega claims and contradictions | Omega consolidation | `omega_claims`, `omega_contradictions`, `omega_evidence_edges` | Omega route/service tests | No deterministic cross-domain, longitudinal candidate record | CREATE one versioned `insight_patterns` record; reuse Omega evidence and contradictions |
| Reviewed owner Insight | Dedicated Insights API | V197 Insights bridge | `insights` | `test_live_intelligence.py`, V197 lens tests | Lifecycle, epistemic state, alternatives, quality scores, evidence digest, cooldown, and version lineage are incomplete | EXTEND `Insight`; retain legacy `status` for compatibility and add governed lifecycle |
| Evidence graph | Omega evidence graph and Map | Omega/API/Map | `omega_evidence_edges`; Insight JSON evidence | Omega and Map tests | Dedicated Insight evidence is copied JSON and cannot be invalidated reliably | CREATE owner-scoped `insight_evidence_relations` referencing normalized observations and canonical source IDs |
| Counter-evidence and contradiction search | Omega contradiction service | Omega consolidation | `omega_contradictions`, evidence edges | Omega tests | Legacy Insight generation can surface with no material counter-evidence or alternative explanation | EXTEND deterministic quality gate; no candidate passes the agentic lane without both |
| Owner review and correction | Insights API and correction/Hardness service | V197 owner controls | `insights`, `user_corrections`, `learning_signals` | Live Intelligence and Hardness tests | Feedback history and version transition are not first-class | CREATE `insight_feedback`; route correction through canonical correction and Hardness paths |
| Non-resurrection | Insight lifecycle | On-demand and scheduled consolidator | `insights` | None | Rejected inference can be generated again because no evidence digest is compared | EXTEND fingerprint/evidence digest/version policy; same evidence remains rejected |
| Source change/deletion invalidation | Source domains plus periodic reconciliation | Insights consolidator | source rows and evidence relations | Account deletion and owner RLS tests | Generic JSON references stay apparently valid after source removal | CREATE bounded relation reconciliation; retract when material supporting evidence disappears |
| WhyChanged | Mind WhyChanged | Hardness and Omega review surfaces | migration `0054` created `why_changed_records` | unit model tests | Runtime service still writes `CognitiveEvent` instead of the dedicated table | REPAIR model/service to use the canonical append-only table; expose Insight history |
| Longitudinal timescales | Timeline/Omega | scheduled consolidation | timestamps on canonical stores | Timeline and Omega tests | No explicit fast/daily/weekly/longitudinal label on Insight patterns | EXTEND pattern and Insight time-window contracts |
| NUR self-insight | Corrections, review feedback, Hardness | owner correction and scheduled consolidator | corrections and learning signals | Hardness tests | NUR cannot surface a governed pattern about its own repeated inference mistakes | EXTEND the same detector with an owner-feedback calibration pattern; never alter production behavior silently |
| Bounded triggers | Cognitive events, Celery, Omega scheduler | worker and beat | Omega consolidation runs | worker/registered-task tests | No pending checkpoint or bounded Agentic Insights worker | CREATE one checkpoint and ID-only scheduled task; dedupe, cooldown, and per-run caps are mandatory |
| Owner isolation | PostgreSQL forced RLS | every route and worker | all private tables | broad RLS corpus | New persistence does not yet exist | CREATE tables with FORCE RLS and explicit cross-owner tests |
| Links back to NUR | Timeline, Map, Orbits, Goals, Projects | V197 bridge | canonical source IDs | Map/Timeline/Project tests | Insight detail lacks one normalized navigation contract | EXTEND API output with canonical routes; do not copy source bodies unnecessarily |
| V197 Insights surface | V197 nonvisual bridge | `/universe/insights` | API snapshot only | `universe-lenses.spec.ts`, hydration tests | Controls use legacy labels and cannot inspect evidence/WhyChanged | EXTEND bridge-rendered controls and adjunct detail only; leave canonical HTML untouched |
| Empty state | V197 Insights hydration | signed-in owner | none | existing no-fake copy tests | Current wording differs from the mandate | EXTEND bridge copy to: `NUR doesn't have enough evidence for a reliable pattern yet.` |
| Provider use | Brain/Omega provider boundary | optional valuable synthesis | model runs | provider failure and Omega tests | Deterministic lane must work without a provider | REUSE provider only after deterministic value gate; first slice is deterministic and honest |

## First Vertical Slice

The implemented path must be:

`CognitiveEvent -> OmegaExperience.features -> InsightPattern -> Insight ->
InsightEvidenceRelation -> V197 Insights -> InsightFeedback/UserCorrection ->
WhyChangedRecord`.

The slice is accepted only with real PostgreSQL proof for cross-owner denial,
same-evidence non-resurrection, source invalidation, bounded checkpoint replay,
and a NUR self-calibration insight. Source presence, mocked copy, or an existing
route is not completion evidence.
