# NUR Total System Architecture

This is a topology map, not a completion claim. Current implementation and proof remain
commit-specific.

```text
Exact V197 host/runtime
  -> idempotent nonvisual bridge
  -> FastAPI owner/shared APIs
  -> service layer and provenance verifier
  -> PostgreSQL + forced RLS
  -> Redis/Celery/Omega beat
  -> disabled/OpenAI server provider
```

## Domain layers

1. **Identity and boundary:** users, sessions, profiles, consent, CSRF, RLS.
2. **Personal evidence:** cognition events, Journal, decisions, references, corrections, outcomes.
3. **Action:** goals, objectives, Plans, steps, schedules, Today actions.
4. **Living model:** six founder-locked Systems (Ambition, Rebuild, Creation, Growth,
   Introspection, Connection), diagnostics/actions/progress, Body/Mind/Life, predictions.
5. **Reward:** Glow rules, transactions, streaks, achievements, levels, leaderboards.
6. **Intelligence:** Mind scope/capability/hydration, Brain provider profiles, structured output,
   verification, memory candidates, WhyChanged, Omega, and Hardness foundations.
7. **Agency:** typed tools, policy, compiler, exact-call approvals, outbox, worker runtime, and
   append-only execution evidence. Complete owner lifecycle UI/API remains a separate proof.
8. **Universe:** live aggregate, graph Map, Timeline, Orbits, Insights, feasibility.
9. **Outside/shared:** Research, Web Signals, Community, Group NUR, Council, Capsule.
10. **Work:** AM Projects, tasks, evidence, runs, reviews, deliverables.
11. **Language/experience:** locale/catalog targets, translation provenance, RTL, V197
    motion/performance. The 35-locale target is not current human-review proof.

## Data flow law

Meaningful action persists first. Services then emit provenance/audit/Timeline state and request an eligible idempotent Glow award. Universe read models aggregate only committed owner-visible records. Model output never becomes observed truth without provenance and confirmation gates.

## Visual law

No React visible renderer. Existing V197 slots are mutated narrowly. Missing surfaces are plain DOM/CSS/runtime adjuncts with V197 tokens, focus management, mobile geometry, and bridge/API bindings.
