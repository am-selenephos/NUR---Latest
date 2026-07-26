# EVIDENCE INDEX — G17

All evidence produced locally on this machine. No secret value appears in any file here.

| Phase | Check | Result | Artifact |
| --- | --- | --- | --- |
| G17.0 | Seven specifications authored | committed `e9d849a` on `experiment/tribev2-neural-simulation` | `docs/neural-simulation/` |
| G17.1 | Official source revision | `af58661791a351a448a489042a28f6c37e1c14b7`, clone clean and untouched | `MODEL_PROVENANCE.json` |
| G17.1 | Official model revision | `f894e783020944dcd96e5568550afe2aa9743f9f`, `gated=False`, `cc-by-nc-4.0` | `MODEL_PROVENANCE.json` |
| G17.1 | Encoder revisions from official `config.yaml` | Llama-3.2-3B `13afe5124825`, vjepa2-vitg-fpc64-256 `875c192b7b70`, w2v-bert-2.0 `da985ba0987f`, dinov2-large `47b73eefe95e` | `MODEL_PROVENANCE.json` |
| G17.1 | Cold-cache footprint before download | ~18.4 GB across 5 repos (checkpoint alone is 676 MB) | `MODEL_PROVENANCE.json` |
| G17.1 | HuggingFace access | all 5 repos resolve incl. gated Llama; token never read or printed | `RESOURCE_PROFILE.json` |
| G17.1 | Hardware | RTX 5090 24 GB sm_120, 24 cores, 251 GB RAM, 26 TB free, CUDA 13.3 | `RESOURCE_PROFILE.json` |
| G17.1 | **torch 2.6.0 (official pin ceiling)** | **FAILS** — arch list stops at sm_90; real kernel launch raises `no kernel image is available for execution on the device`; `cuda.is_available()` misleadingly True | `RESOURCE_PROFILE.json` |
| G17.1 | **torch 2.9.1+cu128** | **PASSES** — sm_120 present, 4096² matmul in 0.097s | `RESOURCE_PROFILE.json` |
| G17.1 | Isolated venv, separate from the NUR API venv | Python 3.12.13 at `.venv-tribe` | — |
| G17.1 | Editable `tribev2` installed `--no-deps` from the official clone | `tribev2==0.1.0` resolves to `/home/nur/NUR-TRIBE-V2/tribev2/__init__.py` | — |
| G17.1 | All remaining official dependencies installed | exit 0; torch/torchvision held by constraint file | `deps-install.log`, `pin-torch.txt` |
| G17.1 | **Machine-wide package corruption discovered** | 1,100 injected files + 385 `.patched.py` in `~/.cache/uv`; 53 + 12 reached `.venv-tribe`; NUR API venv clean (0/0) | `ENV_INTEGRITY_INCIDENT.md`, `ENV_CONTAMINATION_FILELIST.txt`, `ENV_CONTAMINATION_UVCACHE_FILELIST.txt` |
| G17.1 | Corruption proven content-benign, not malicious | 1,118 files compared against pristine PyPI wheels: 53 differ, **all 53 by exactly the two-line header, 0 by anything else** | `ENV_INTEGRITY_INCIDENT.md` §4 |
| G17.1 | Corruption repaired in `.venv-tribe` | 9 packages reinstalled from fresh wheels with `--link-mode=copy`; re-scan 0 injected, 0 `.patched.py` | `ENV_INTEGRITY_INCIDENT.md` §5 |
| G17.1 | Post-repair stack | torch 2.11.0+cu128, torchvision 0.26.0+cu128, numpy 2.2.6, sm_120 True, capability (12,0), 2048² matmul 0.095s | — |

## Not yet captured

Real text, audio and video inference. Until those run, G17 is
`NUR_TRIBE_RESEARCH_PARTIAL` and TRIBE is **not** incorporated into NUR.
