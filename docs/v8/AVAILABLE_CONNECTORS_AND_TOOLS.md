# Available connectors and tools — enumerated, not assumed

Enumerated 2026-07-26 in this Opus session. Each entry was tested, not inferred from a
capability list.

## Available and used

| Tool | Version | Used for |
| --- | --- | --- |
| Local shell / filesystem | bash on Arch, Linux 7.1.4 | repository inspection, Base64 decode of the canonical stages, dead-CSS analysis, hashing, evidence capture |
| Git | 2.55.0 | branch/HEAD verification, lineage, reversible `stash` for the bundle-size baseline |
| **GitHub CLI (`gh`)** | 2.96.0, authenticated as `am-statementforge` | read-only inspection of `am-selenephos/NUR`: default branch, `main` SHA, all five open draft PRs |
| Node / npm / npx | Node 20.20.2 | typecheck, vitest, vite build, Playwright |
| **Playwright + Chromium** | Chromium 150.0.7871.181 | live sign-in as the seeded owner, DOM diagnostics, frame-cadence measurement, 8-viewport capture, teardown proof |
| Python | 3.14.6 | Base64 decode, CSS rule analysis, wheel-vs-installed byte comparison |
| ffmpeg / ffprobe | n8.1.2 | **available but unused — no reference videos supplied** |
| ImageMagick | 7.1.2-27 | available; not yet needed |

## GitHub truth read this session

```
default branch : main
main SHA       : f265123f727ca2c314f3eee03d00e0654c70ce76  (2026-07-19)
last push      : 2026-07-23T12:31:08Z
open PRs       : #5 draft integration/nur-one-system-20260722  7a56510
                 #4 draft diagnostics/g09-pytest-20260722      eb94c2b
                 #3 draft rescue/lane-b-g13-uncommitted        4ded46c
                 #2 draft rescue/lane-a-g09-uncommitted        eaa3c53
                 #1 draft build-week-submission                c823512
```

Nothing was pushed, merged, closed, or modified on the remote.

## Unavailable

The following MCP connectors are listed in this environment but require an OAuth flow that
cannot run in a non-interactive session. Each is recorded rather than silently skipped:

```
CONNECTOR_UNAVAILABLE_GOOGLE_DRIVE
CONNECTOR_UNAVAILABLE_GMAIL
CONNECTOR_UNAVAILABLE_GOOGLE_CALENDAR
CONNECTOR_UNAVAILABLE_WOLFRAM
CONNECTOR_UNAVAILABLE_BLAZE_SQL
CONNECTOR_UNAVAILABLE_CB_INSIGHTS
CONNECTOR_UNAVAILABLE_FMP
CONNECTOR_UNAVAILABLE_JOBDATALAKE
CONNECTOR_UNAVAILABLE_MINDMAP
CONNECTOR_UNAVAILABLE_MOODYS
CONNECTOR_UNAVAILABLE_OXFORD_ECONOMICS
CONNECTOR_UNAVAILABLE_V0
CONNECTOR_UNAVAILABLE_ANTHROPIC_ECONOMIC_INDEX
```

To authorise them, use the claude.ai connector settings (for claude.ai connectors) or `claude
mcp` / `/mcp` in an interactive session. None of them is required for this mission: no Adobe,
Canva, Cloudinary, Dropbox or Drive connector is connected, so no founder asset library was
reachable and none was assumed to exist.

`CONNECTOR_UNAVAILABLE_REFERENCE_VIDEOS` — `/home/nur/Downloads/NUR-UI-REFERENCES/` does not
exist. `ffprobe`/`ffmpeg` are installed and ready; there is simply nothing to analyse.

## Security posture held

- Read-only against GitHub; no push, merge, tag, issue, or remote file change.
- No secret value printed, logged, screenshotted, or written to any artifact.
- No NUR source, credential, user data or private media sent to any external service.
- No connector output accepted without local verification — the GitHub SHAs were cross-checked
  against the local worktree.
