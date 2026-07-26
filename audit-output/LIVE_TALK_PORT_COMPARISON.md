# LIVE_TALK PORT COMPARISON — Phase 6

Question: does current commit `6d7eeef` contain the FINAL proven Live-Talk
versions (not an earlier intermediate)? **Yes — byte-identical to snapshot 06.**

## SHA-256 (first 12 hex) — 6 proven files
| File | current HEAD | snapshot 06 (proven) | baseline 01 | CUR==06 |
|---|---|---|---|---|
| apps/api/app/ai/openai_provider.py | c7fdd304916f | c7fdd304916f | 88a1fb0ea8b9 | ✅ |
| apps/api/app/ai/prompts.py | 9d9aa818dfe5 | 9d9aa818dfe5 | ce62d2c4835d | ✅ |
| apps/web/src/styles/v197-functional.css | 12e802b7f3e3 | 12e802b7f3e3 | 2be2f717f4fb | ✅ |
| infra/scripts/bootstrap-dev.sh | 3e55cdbd7466 | 3e55cdbd7466 | bb4982e3419d | ✅ |
| infra/scripts/openai-ui-smoke.mjs | f9eb745a5f9b | f9eb745a5f9b | 1d6233b2281e | ✅ |
| infra/scripts/live-talk-two-turn-proof.mjs | 5389e90124e9 | 5389e90124e9 | ABSENT | ✅ |

All six IDENTICAL to the proven snapshot 06 working tree; all six DIFFER from
baseline 01 (the pre-fix integration state). The proof script is new.

## The differences (baseline 01 → current 6d7eeef) are intentional and correct
| File | Δ | Purpose |
|---|---|---|
| openai_provider.py | +11/−2 | **gpt-4.1 fix:** replace unconditional `reasoning:{effort}` with `if _supports_reasoning_effort(model)` gate (o1/o3/o4/gpt-5 only). Baseline sent `reasoning.effort` to gpt-4.1 → 400 unsupported_parameter. |
| prompts.py | +9/−3 | **verifier-contract fix:** evidence rendered as verbatim `kind:id` tokens; explicit "no evidence ⇒ source_refs=[]" rule; grounded-claims rule. Baseline dumped raw dicts → model cited bare UUIDs → `provider_output_invalid` BLOCK. |
| v197-functional.css | +8/−0 | Fix `.nur-v197-provider-status` grid so the status `<strong>` isn't zero-width (real UI defect found in-browser). |
| bootstrap-dev.sh | +42/−3 | Durable venv creation (uv→virtualenv→venv fallback; reuse healthy venv; clear diagnostic) — replaces the fragile unconditional `python -m venv` + ensurepip. |
| openai-ui-smoke.mjs | +27/−9 | Fast-turn-tolerant waits, modal-open retry, whitespace-normalized persistence compare. |
| live-talk-two-turn-proof.mjs | NEW (+105) | The two-turn exact-reply + reload-persistence browser proof harness. |

Verdict: current Git **preserves the proven behavior exactly** (identical bytes),
and the delta vs the older integration baseline is precisely the set of gpt-4.1
compatibility fixes. No final prompt fix was missed; the new proof script is
identical; the CSS/smoke/bootstrap changes are justified and self-consistent.

## Does current 6d7eeef == the FINAL proven state? YES.
6d7eeef is the commit of snapshot 06's working-tree changes on top of baseline
7a56510. Content of all six files matches the working tree that achieved the
independently-run real LIVE_TALK_PASS. This is the final proven set, not an
intermediate patch.
