# RC2 Research Contract Reconciliation

**Closure basis:** `cd678d4092c6f215306b254d527b1d67fa32c13d`  
**Decision:** **V5 Research is a local-staging contract; live external retrieval remains J6 / external-provider hold.**  
**Route ownership:** Research remains embedded in the canonical Systems-hosted V197 surface. No separate generic React Research page is introduced.

## Decision

The controlling V5 contract is **A. Local research staging is part of V5**:

> The owner can enter a bounded Research question, NUR persists it in the owner-scoped local ledger, reload shows the same question, and the product does not invent external sources, citations, or provider success.

This is classified as **H-RESEARCH = PASS / local V5 contract**. It is not classified as a live-web pass. External retrieval, source fetching, citation verification, and connected-provider execution remain unclaimed and belong to **J6 / external-provider hold**.

The UI location is intentionally the current canonical Systems-hosted Research field. The route `/universe/research` continues to resolve to the Systems root; the Research card contains the local staging control and persisted result summary. This preserves the existing V197 route ownership rather than inventing a separate chamber.

## Authority reconciliation

| Authority | Evidence | Interpretation |
|---|---|---|
| Research/Web/Expert/Tender specification, `docs/research-web-expert-tender-spec.md:5-8` | Track A explicitly says `research_briefs` and `research_source_notes` exist with owner scoping/RLS, and that the V197 Research field can persist a local question through `POST /api/v1/research/briefs` while inventing no sources when no provider is connected. | **Controlling product contract for V5 local staging.** |
| Route map, `docs/route-map.md:24-31` | `/universe/research` is a Research field with `/api/v1/research/briefs` and related owner backend paths; external retrieval remains provider-gated. | Research is a real field backed by local persistence, not a live-web claim. |
| Full UI surface inventory, `docs/02-full-ui-surface-inventory.md:3-18` | Research is `LIVE_PARTIAL`, presented through the canonical card, with local persisted questions. | Confirms local staging is in V5, but does not require a separate chamber. |
| Track-A/Track-B truth table, `docs/07-track-a-vs-track-b-truth-table.md:10-13` | Research/Web is “persisted local question/source-note staging”; explicit external cited providers and verifiers are Track B. | Separates the V5 local contract from the unclaimed live-retrieval contract. |
| Backend implementation, `apps/api/app/api/v1/product_surfaces.py:230-335` | `POST/GET/PATCH /research/briefs`, source-note routes, owner checks, provenance events, and conversion to an owner Orbit reference are implemented. | The persistence contract is real and owner-scoped. |
| Backend tests, `apps/api/app/tests/test_product_surfaces.py:10-112` | Research brief/source-note creation, `OWNER_WRITTEN` provenance, `NOT_CONNECTED` provider status, timeline events, owner isolation, and RLS denial are tested. | Local staging is independently backed by API and security evidence. |
| New machine registry, `docs/interaction-registry.json:2-18` | The newer machine registry source hash is `397c302579472e60f5bd667546a96b6e3f262aa40bd932d10c1946e13b046dd2`; it registers generic world focus and local tabs but no active `#research-query` or `[data-research-submit]` selector. | Indicates the older inline control was not part of the current rendered surface, not that the V5 backend contract was removed. |
| Route/client matrix, `docs/completion/MANUS_ROUTE_CLIENT_CONTRACT_MATRIX.csv` Research row | Frontend entry is `/universe/research`, render owner is `nativeRoute collapses to /systems`, and status is `ROUTE_OWNERSHIP_GAP`; the backend local contract exists while an independent chamber is missing. | Confirms the correct implementation shape: restore the bounded control inside Systems, not a separate chamber. |
| Current browser route contract, `apps/web/e2e/full-interface.spec.ts:25-32,83-102` | Research maps to `#page-systems`; the previous test asserted old inline selectors were absent. | The route ownership assertion remains authoritative; the stale absence assertion was reconciled into a persistence proof. |
| Current V197 bridge, `apps/web/src/bridge/v197Hydration.ts:895-907,1057-1074,1167-1217` | Research summaries consume persisted `researchBriefs`, state that questions are held without invented sources, and route the portal through the Systems host. | Confirms the visible surface is Systems-hosted local staging. |

## Conflict resolution

The older `docs/interaction-registry.md:51-57` says `#research-query` and `[data-research-submit]` are `WIRED` to `POST /research/briefs`. Its own source date is 2026-07-11 and its source hash is the older historical V197 registry hash. The newer machine-readable registry omits those selectors, and the current bridge explicitly removed `data-research-submit` from the former portal control. The prior browser test then asserted the selectors were absent. These sources described a **route/UI ownership gap and a stale selector contract**, not a decision to remove local Research persistence.

The closure therefore reconciles both sides without silently making a test authoritative. It keeps Research inside the Systems-hosted canonical surface, restores only the bounded local question control named by the Track-A product specification, and retains the explicit provider-disabled boundary. No live retrieval, external citation, source claim, or generic replacement page is added.

## Implemented V5 proof

The closure implementation adds a `#research-staging` section to the existing `#universe-research` card with `#research-query` and `[data-research-submit]`. The existing typed V197 action layer calls `createResearchBrief(question, activeOrbitId)` through the existing CSRF-protected API client, refreshes the owner snapshot, clears the input, and displays an honest local-only confirmation. The canonical browser proof now:

1. opens `/universe/research` and verifies the Systems root remains the route owner;
2. enters a unique local question and saves it through the existing bridge/API path;
3. verifies the owner mock state receives the persisted Research brief;
4. reloads the route and verifies the same question is rendered from persisted state;
5. preserves the provider-disabled/no-invented-source copy; and
6. continues to verify that no separate React replacement root is mounted.

## Final classification

| Gate | Classification |
|---|---|
| H-RESEARCH local V5 staging | **PASS / local V5 contract** |
| H-RESEARCH live retrieval | **HOLD / J6 external** |
| Separate Research chamber | **Not required; route remains intentionally Systems-hosted** |
| External sources/citations/provider success | **Not claimed** |
