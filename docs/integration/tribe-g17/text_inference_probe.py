"""G17.1 — official TRIBE v2 text inference feasibility probe.

Runs the documented quick-start path from the official README against the pinned
model revision, and records everything the G17 gate requires. Prints no secret:
the HuggingFace token is used by the library from its own cache and is never read,
echoed, or written here.
"""
import hashlib, json, os, resource, sys, time, warnings
from pathlib import Path

PROOF = Path("/home/nur/NUR-TRIBE-V2-PROOF")
CACHE = Path("/home/nur/.cache/nur-models/tribev2")
CACHE.mkdir(parents=True, exist_ok=True)

captured = []
warnings.simplefilter("always")
_orig = warnings.showwarning
def _capture(message, category, filename, lineno, file=None, line=None):
    captured.append(f"{category.__name__}: {str(message)[:300]}")
    _orig(message, category, filename, lineno, file, line)
warnings.showwarning = _capture

def disk_bytes(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())

def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

import torch
result = {
    "torch": torch.__version__,
    "cuda": torch.version.cuda,
    "device_name": torch.cuda.get_device_name(0),
    "capability": list(torch.cuda.get_device_capability(0)),
    "sm_120_in_arch_list": "sm_120" in torch.cuda.get_arch_list(),
    "arch_list": torch.cuda.get_arch_list(),
}
import torchvision
result["torchvision"] = torchvision.__version__

a = torch.randn(2048, 2048, device="cuda"); b = torch.randn(2048, 2048, device="cuda")
torch.cuda.synchronize(); t0 = time.time(); c = (a @ b).sum().item(); torch.cuda.synchronize()
result["cuda_matmul_ok"] = bool(c == c)
result["cuda_matmul_seconds"] = round(time.time() - t0, 4)
del a, b; torch.cuda.empty_cache(); torch.cuda.reset_peak_memory_stats()

import tribev2
result["tribev2_module_file"] = tribev2.__file__
from tribev2 import TribeModel

disk_before = disk_bytes(CACHE)
t0 = time.time()
model = TribeModel.from_pretrained("facebook/tribev2", cache_folder=str(CACHE))
result["model_load_seconds_cold"] = round(time.time() - t0, 2)
result["cache_disk_delta_bytes"] = disk_bytes(CACHE) - disk_before

for name in ("best.ckpt", "config.yaml"):
    hits = list(CACHE.rglob(name))
    if hits:
        result[f"{name}_sha256"] = sha256(hits[0])
        result[f"{name}_bytes"] = hits[0].stat().st_size

t0 = time.time()
df = model.get_events_dataframe(text_path=str(PROOF / "sample_text.txt"))
result["preprocess_seconds"] = round(time.time() - t0, 2)
result["events_rows"] = int(len(df))

t0 = time.time()
preds, segments = model.predict(events=df)
result["inference_seconds_cold"] = round(time.time() - t0, 2)
result["output_shape"] = list(getattr(preds, "shape", []))
result["expected_vertex_dim_fsaverage5"] = 20484
result["vertex_dim_matches"] = bool(result["output_shape"] and result["output_shape"][-1] == 20484)
result["n_segments"] = int(len(segments)) if segments is not None else None

t0 = time.time()
preds2, _ = model.predict(events=df)
result["inference_seconds_warm"] = round(time.time() - t0, 2)

import subprocess
result["source_revision"] = subprocess.run(
    ["git", "-C", "/home/nur/NUR-TRIBE-V2", "rev-parse", "HEAD"],
    capture_output=True, text=True).stdout.strip()
result["source_dirty_files"] = len(subprocess.run(
    ["git", "-C", "/home/nur/NUR-TRIBE-V2", "status", "--short"],
    capture_output=True, text=True).stdout.split("\n")) - 1
snapshots = sorted(CACHE.rglob("snapshots/*"))
result["model_revision"] = [s.name for s in snapshots if s.is_dir()]
result["feature_encoder_revisions"] = sorted(
    {p.parent.parent.name + "@" + p.name
     for p in Path(os.path.expanduser("~/.cache/huggingface/hub")).rglob("snapshots/*")
     if p.is_dir()}
) if Path(os.path.expanduser("~/.cache/huggingface/hub")).exists() else []

result["peak_ram_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
result["peak_vram_bytes"] = int(torch.cuda.max_memory_allocated())
result["sampling_hz_documented"] = 1
result["hemodynamic_offset_seconds_documented"] = 5
result["warnings"] = captured[:40]
result["secret_printed"] = False

(PROOF / "g17_text_inference.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({k: v for k, v in result.items() if k != "warnings"}, indent=2))
print(f"\nwarnings captured: {len(captured)}")
