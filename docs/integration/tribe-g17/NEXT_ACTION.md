# NEXT ACTION — G17

Updated 2026-07-26, after reconciling the 403 contradiction.

## Where the pipeline actually stands

| Stage | Result |
| --- | --- |
| `tribev2` imports from the official clone | **PASS** |
| `TribeModel.from_pretrained("facebook/tribev2")` | **PASS** — 677 MB checkpoint cached |
| text → speech → transcription (gTTS + `uvx whisperx`) | **PASS** — 71 items, Python 3.12 |
| text feature extraction | **BLOCKED** — 403 `meta-llama/Llama-3.2-3B` |
| audio inference | not attempted |
| video inference | not attempted |

The blocker is the **text encoder**, not the model and not the Blackwell torch override.

## Founder action — one request, no secret involved

Request access at `https://huggingface.co/meta-llama/Llama-3.2-3B` using the account the local
token belongs to. Meta approves these manually. No new token, no rotation, no config change.

Then:

```bash
cd /home/nur/NUR-TRIBE-V2-PROOF
UV_PYTHON=3.12 UV_HTTP_TIMEOUT=600 .venv-tribe/bin/python text_inference_probe.py
```

## Agent action that does not wait

Audio inference uses `facebook/w2v-bert-2.0`, which is **not** gated. Video uses
`facebook/vjepa2-vitg-fpc64-256` and `facebook/dinov2-large`, also ungated. Both paths bypass
the blocked text encoder, so a real forward pass — and therefore the first genuine test of
torch 2.11 on sm_120 against this model — can be obtained without the founder.

```bash
# next: adapt text_inference_probe.py to audio_path, supply a short local wav,
# capture shape / vertex-dim / timings / peak VRAM exactly as for text
```

## Do not

- do not call TRIBE incorporated — G17 remains `NUR_TRIBE_RESEARCH_PARTIAL`, 18/37;
- do not claim the gated repo is accessible from metadata resolution again;
- do not downgrade torch to satisfy the `<2.7` metadata pin;
- do not modify the official clone at `/home/nur/NUR-TRIBE-V2`;
- do not rotate the OpenAI key.
