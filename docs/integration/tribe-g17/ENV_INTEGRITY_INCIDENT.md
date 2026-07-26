# ENVIRONMENT INTEGRITY INCIDENT — installed library source files were rewritten

**Discovered:** 2026-07-25, while installing the official TRIBE v2 dependencies into
`/home/nur/NUR-TRIBE-V2-PROOF/.venv-tribe`.

**Discovered by:** a hard `SyntaxError` on `import tribev2`, not by a scan. The traceback
bottomed out in `httpx/_auth.py`:

```
SyntaxError: from __future__ imports must occur at the beginning of the file
```

This is not a TRIBE defect, not a dependency-resolution defect, and not caused by the torch
version. It is a pre-existing corruption of this machine's Python package storage.

---

## 1. What was done to the files

Two distinct mutations, both applied at the same instant.

### Mutation A — injected header (breaks imports)

Two lines prepended to the top of installed `.py` files:

```python
import logging
logging.basicConfig(level=logging.INFO)
```

Harmless-looking, but it is inserted **above** module docstrings and above
`from __future__ import annotations`. Python requires `__future__` imports to be the first
statement, so every file that used one became a hard `SyntaxError`. That is the failure mode
that blocked TRIBE.

It also silently forces global `INFO`-level logging on any process that imports an affected
module — which is why unrelated `INFO:matplotlib.font_manager:` lines appear in output.

### Mutation B — `.patched.py` sibling files

Alongside some modules sits a `<name>.py.patched.py` containing the entire module body
re-indented inside a `try:` block, closed with:

```python
except Exception as e:
    print(f"Error in {os.path.basename('{file_path}')}: {e}")
```

Note `'{file_path}'` — an f-string placeholder that was never expanded, and `os` is never
imported. These are the output of a broken automated code-rewriting script. They are not
importable module names, so they are inert dead weight rather than an active hazard.

---

## 2. Scope

| Location | Injected `.py` | `.patched.py` |
| --- | --- | --- |
| `~/.cache/uv/archive-v0/` (511 archive entries) | **1,100** | 385 |
| `.venv-tribe` site-packages | 53 | 12 |
| `/home/nur/NUR-INTEGRATION-20260722/apps/api/.venv` | **0** | **0** |

Affected packages in `.venv-tribe`: httpcore, httpx, pygments, psutil, networkx, jinja2,
shellingham, tokenizers, mpmath.

Affected in the uv cache more broadly: torch internals (`_dynamo`, `_inductor`, `_functorch`,
`autograd`, `fx`, `cuda`, `distributed`), ray, aiohttp, starlette/fastapi, datasets,
transformers, vllm, dnspython, anyio, lark, tqdm, supervisor, and others.

**The NUR API venv is clean.** No NUR product code is affected. Nothing in any Git repository
is affected — this is entirely in installed third-party packages and the package cache.

File lists preserved: `ENV_CONTAMINATION_FILELIST.txt`, `ENV_CONTAMINATION_UVCACHE_FILELIST.txt`.

---

## 3. How one script poisoned every environment — the hardlink mechanism

Every mutated file carries the same mtime, to the same second:

```
2026-04-10 01:04:21
```

`.venv-tribe` was created 2026-07-25 — three and a half months *later*. The corruption did not
happen here. It arrived with the packages.

`uv` installs by **hardlinking** from `~/.cache/uv/archive-v0/` into each venv. `httpx/_auth.py`
has link count 6:

```
/home/nur/.cache/uv/archive-v0/lulWUcvVrh4ss3b3rXf_I/httpx/_auth.py
/home/nur/private_ai_core/venv_vllm/.../httpx/_auth.py
/home/nur/NUR-TRIBE-V2-PROOF/.venv-tribe/.../httpx/_auth.py
/home/nur/am_backdoor_lab/venv_hf_upload_clean/.../httpx/_auth.py
/home/nur/am_backdoor_lab/venv_modelscan_tf/.../httpx/_auth.py
/home/nur/MADDY_HUNT/AM_LIQUID_CORE/brain/am_neural_fluid/.../httpx/_auth.py
```

One inode, six names. A script that edited site-packages **in place** inside any one of those
environments wrote through to the shared inode — so it simultaneously edited the cache and
every other venv on the machine, including ones created months afterwards. Creating a fresh
venv does not escape it; a fresh venv re-links the same poisoned inodes.

This is the most probable explanation for the previously unexplained `.venv` destruction
incident recorded during the live-talk work.

---

## 4. Is it malicious?

**No evidence of malice. Verified, not assumed.**

Pristine wheels for all nine affected packages were downloaded fresh from PyPI
(`--no-cache-dir`) and compared file-by-file against what is installed:

```
files compared:            1,118
files differing:              53
differing by exactly the
  two-line header, and
  nothing else:               53
differing in any other way:    0
```

No inserted network call, no credential access, no exfiltration, no changed logic, no altered
control flow. Every byte of every difference is accounted for by the two-line header.

The signature — an unexpanded `{file_path}`, `os` used but never imported, a blanket
`try/except` wrapper, `basicConfig` stamped on every file — reads as a naive automated
"add logging / add error handling" script run recursively over a site-packages tree. Careless,
not hostile.

It should still be treated as a control failure: an unreviewed script had write access to
shared package storage and its blast radius was every Python environment on the machine.

---

## 5. Repair performed (scope: `.venv-tribe` only)

The nine affected packages were reinstalled from freshly downloaded wheels with
`--link-mode=copy`, so `.venv-tribe` now holds **independent copies** rather than hardlinks
into the shared cache. Any future in-place edit inside this venv can no longer propagate to
the cache or to any other environment.

Not touched, deliberately:

- `~/.cache/uv` beyond replacing the entries for those nine packages — the cache is
  regenerable, but wholesale cleaning would force a re-download of torch and every other large
  wheel, and would be a machine-wide action outside this mission's scope;
- `/home/nur/private_ai_core/`, `/home/nur/am_backdoor_lab/`, `/home/nur/MADDY_HUNT/` —
  founder-owned environments, out of scope, and nothing was deleted from them;
- the official TRIBE clone at `/home/nur/NUR-TRIBE-V2` — untouched, 0 modified files.

---

## 6. Founder decisions this raises

1. **~1,100 cache files and 385 `.patched.py` files remain corrupted** in `~/.cache/uv`. Every
   *new* venv built on this machine that resolves an affected package from cache will inherit
   the breakage. A full `uv cache clean` fixes it permanently at the cost of re-downloading
   everything (torch alone is 782 MB). Recommended, but it is a machine-wide action and is not
   being taken unilaterally.
2. **Other environments are still corrupted** — `private_ai_core/venv_vllm`,
   `am_backdoor_lab/venv_hf_upload_clean`, `am_backdoor_lab/venv_modelscan_tf`,
   `MADDY_HUNT/AM_LIQUID_CORE/brain/am_neural_fluid`. They were left alone.
3. **The script that did this still exists somewhere** and was run at 2026-04-10 01:04:21. If it
   is still in a pipeline, it will do this again. Worth locating.
4. Consider setting `UV_LINK_MODE=copy` machine-wide to remove the write-through hazard.
