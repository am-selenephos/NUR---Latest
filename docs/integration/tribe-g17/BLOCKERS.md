# BLOCKERS — G17 NUR Neural Simulation Lab

Verdict: **NUR_TRIBE_RESEARCH_PARTIAL** (18 of 37 requirements PASS)

## T1 — torch pin cannot run on this GPU  (RESOLVED with a documented deviation)

TRIBE v2 pins `torch>=2.5.1,<2.7`. This machine is an RTX 5090 Laptop, compute capability
**12.0 (sm_120, Blackwell)**.

Established empirically, not assumed:

| torch | compiled arch list | real kernel launch |
| --- | --- | --- |
| 2.6.0+cu124 (the pin's ceiling) | sm_50…sm_90 | **FAILS** — `CUDA error: no kernel image is available for execution on the device` |
| 2.9.1+cu128 | …sm_100, **sm_120** | passes — 4096² matmul in 0.097s |

`torch.cuda.is_available()` returns **True** under the failing configuration. Only an actual
kernel launch exposes the problem — a trap worth remembering.

**Resolution:** run on `torch 2.9.1+cu128`, recorded as a deliberate deviation from the official
pin, forced by hardware. **Residual risk:** TRIBE was validated on 2.5–2.6; API drift on 2.9 is
possible and must be proven by real inference, never assumed. The alternative — CPU-only within
the pin — is faithful but impractical for V-JEPA2 ViT-g video encoding behind an interactive
surface.

## T2 — No real inference has run yet  (OPEN — the gate that matters)

G17 cannot pass without real **text, audio and video** inference. None has run. Everything so far
is specification, provenance and feasibility. An honest disabled shell is not incorporation and
will not be described as such.

## T3 — Path collision resolved

`/home/nur/NUR-TRIBE-V2` was already the **official facebookresearch/tribev2 clone** (`af58661`,
clean) — not a NUR worktree. It was left untouched, since overwriting an existing worktree is
forbidden. The NUR experiment worktree was created at `/home/nur/NUR-TRIBE-V2-WT` on branch
`experiment/tribev2-neural-simulation`.

## T4 — Commercial licence  (FOUNDER, not blocking research mode)

CC-BY-NC-4.0 confirmed from the licence file and model card. A paid or public NUR build must ship
this feature **disabled**. Shipping it commercially requires either a commercial licence from
Meta or a commercially compatible replacement provider behind the same contract. No action needed
for local research use.

## T5 — Machine-wide Python package corruption  (RESOLVED for this venv; OPEN machine-wide)

`import tribev2` failed with a hard `SyntaxError` in `httpx/_auth.py`. The cause was not TRIBE,
not the dependency resolution, and not the torch version: **installed third-party library source
files on this machine have been rewritten in place.**

Two lines were prepended to affected `.py` files —

```python
import logging
logging.basicConfig(level=logging.INFO)
```

— above module docstrings and above `from __future__ import annotations`, which Python requires
to be the first statement. Every file using one became a syntax error. Alongside them sit
`<name>.py.patched.py` files wrapping whole module bodies in `try/except` with an unexpanded
`{file_path}` placeholder: the output of a broken automated rewriting script.

Scope: **1,100** injected files and 385 `.patched.py` across 511 `~/.cache/uv/archive-v0` entries;
53 + 12 of them surfaced in `.venv-tribe`. The NUR API venv is **clean** (0 / 0). No Git-tracked
file anywhere is affected.

Mechanism: uv **hardlinks** from its cache into every venv. `httpx/_auth.py` had link count 6,
shared between the cache, `.venv-tribe`, `private_ai_core/venv_vllm`, two `am_backdoor_lab`
venvs, and `MADDY_HUNT/AM_LIQUID_CORE`. One script editing site-packages in place wrote through
the shared inode into the cache and every other environment — including venvs created three
months later. All mutated files carry the identical mtime `2026-04-10 01:04:21`. This is the
most probable explanation for the previously unexplained `.venv` destruction incident.

Malicious? **No — verified rather than assumed.** Pristine wheels were downloaded fresh from PyPI
and compared file by file: 1,118 files compared, 53 differing, **53 differing by exactly the
two-line header and nothing else, 0 differing in any other way.** No network call, credential
access, or logic change was inserted.

**Resolved here:** the nine affected packages were reinstalled from freshly downloaded wheels
with `--link-mode=copy`, so `.venv-tribe` now holds independent copies that cannot write back to
the shared cache. Verified 0 injected, 0 `.patched.py`. Torch pair unchanged.

**Still open, founder-owned:** the uv cache and four other environments remain corrupted, and the
script that did it has not been located. Detail and options in `ENV_INTEGRITY_INCIDENT.md`.

## T6 — Gated text encoder blocks inference  (FOUNDER_ACTION_REQUIRED_HUGGINGFACE_ACCESS)

**This supersedes the "Not a blocker — Hugging Face access" note below, which was wrong.**

### The contradiction, resolved

Two records disagreed:

| Source | Claim |
| --- | --- |
| `RESOURCE_PROFILE.json` line 23 | "all five repos resolvable with the existing token, **including gated meta-llama/Llama-3.2-3B**" |
| `MODEL_PROVENANCE.json` line 28 | `meta-llama/Llama-3.2-3B` → `"gated": "manual"` |

Both were recorded in the same run, seconds apart. They are not actually contradictory — the
first is **an over-claim built on the second**. "Resolvable" meant the HuggingFace *metadata
API* returned the model card, revision and file list. For a `gated: manual` repository the
model card is public; **file downloads are not**. I wrote "resolvable" and read it later as
"accessible", which is the error. Metadata resolution was never evidence of download rights.

`FOUNDER_ACTION_REQUIRED_HUGGINGFACE_ACCESS` was explicitly *not* raised on that basis. It is
raised now.

### Exact failure

```
OSError: You are trying to access a gated repo.
403 Client Error.
Cannot access gated repo for url
  https://huggingface.co/meta-llama/Llama-3.2-3B/resolve/main/config.json
Access to model meta-llama/Llama-3.2-3B is restricted and you are not in the authorized list.
```

| Question | Answer |
| --- | --- |
| Which repository returned 403 | `meta-llama/Llama-3.2-3B` — **only** this one |
| Which request failed | `GET /meta-llama/Llama-3.2-3B/resolve/main/config.json` |
| Which call chain | `neuralset/extractors/text.py:300` → `AutoTokenizer.from_pretrained` → `transformers/utils/hub.py:503 cached_files` |
| Is the token present | **Yes.** A 403 is authorisation-denied, not authentication-missing; a missing token yields 401. The token value was never read, printed or logged. |
| Was access revoked | **No evidence of revocation.** It was never granted. `gated: manual` was recorded at first contact. |
| Does the endpoint differ | **Yes, and this is the crux.** The earlier check used the metadata endpoint (`/api/models/...`); the failure is on the file endpoint (`/resolve/...`). Different authorisation. |
| Model, encoder, or other | **Encoder.** The TRIBE checkpoint itself is fine — `facebook/tribev2` downloaded completely (677 MB, matching the documented 676 MB) and `TribeModel.from_pretrained` succeeded. The block is the *text* encoder only. |

### How far the pipeline actually got

1. `tribev2` imports from the official clone — **OK**
2. `TribeModel.from_pretrained("facebook/tribev2")` — **OK**, checkpoint cached
3. `get_events_dataframe(text_path=...)` → gTTS → `uvx whisperx` transcription — **OK**
   (71 items processed; the whisperx toolchain was built on Python 3.12)
4. Text feature extraction → `AutoTokenizer.from_pretrained("meta-llama/Llama-3.2-3B")` — **403**

So the deviation stack (torch 2.11 on sm_120, Blackwell override) is **not** the blocker.
Nothing to date contradicts it; it simply has not been exercised through a full forward pass.

### Founder action

Request access at `https://huggingface.co/meta-llama/Llama-3.2-3B` with the same account the
local token belongs to. Meta grants these manually, usually within hours. No new token, no
rotation, no configuration change — the existing token starts working once the account is on
the authorised list.

Verification afterwards, which prints no secret:

```bash
cd /home/nur/NUR-TRIBE-V2-PROOF
UV_PYTHON=3.12 UV_HTTP_TIMEOUT=600 .venv-tribe/bin/python text_inference_probe.py
```

### Independent work that continues now

Audio and video inference both avoid the text encoder, so `w2v-bert-2.0`, `vjepa2-vitg` and
`dinov2-large` paths can be exercised while text stays blocked. That is the next TRIBE action.

## Not a blocker

~~Hugging Face access — the existing token resolves all five repos including the gated
`meta-llama/Llama-3.2-3B`. `FOUNDER_ACTION_REQUIRED_HUGGINGFACE_ACCESS` is **not** raised.~~
**RETRACTED 2026-07-26 — see T6.** Metadata resolution was mistaken for download access. The
label is now raised.

Hardware — 24 GB VRAM, 251 GB RAM, 26 TB free against an 18.4 GB cold cache. Still ample.
