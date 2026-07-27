# Quickstart Boot

## One-click launch

On Linux, double-click `START_NUR.desktop` (or run `bash START_NUR.sh`).
On macOS, double-click `RUN_NUR.command` after configuring OpenAI once.

The first interactive Linux launch opens a hidden local OpenAI setup. After
that, the same launcher starts Postgres, Redis, FastAPI, worker, scheduler,
V197 web interface, demo data, health checks, and real server-side Talk. The
API key stays only in ignored `.env.local` and is never included in the ZIP.

To configure explicitly:

```bash
bash START_NUR.sh setup
```

Docker Engine/Desktop, Node.js, npm, Python 3, and standard PostgreSQL client
tools must be installed. The launcher diagnoses missing prerequisites instead
of pretending NUR started.

Fastest way from the unzipped repository root:

```bash
bash RUN_NUR.sh
```

Then open:

```text
http://localhost:5173
```

Demo credentials are printed by `seed-demo-nur.sh`. Defaults:

```text
Owner: owner@nur.app / owner-demo-pass-123
Recipient: recipient@nur.app / recipient-demo-pass-123
```

The low-level `RUN_NUR.sh` default remains an honest disabled-provider boot for
testing. To configure real AI manually:

```bash
bash infra/scripts/configure-openai-local.sh
bash RUN_NUR.sh openai
```

The key is written to `.env.local`, which is ignored and excluded from the
bootable zip.

Useful one-file commands:

```bash
bash RUN_NUR.sh doctor
bash RUN_NUR.sh status
bash RUN_NUR.sh seed
bash RUN_NUR.sh logs
bash RUN_NUR.sh stop
bash RUN_NUR.sh reset-demo
bash RUN_NUR.sh package
```

## Presentation-day auth recovery

To preserve the current database, restart in honest disabled-provider mode,
and verify API readiness plus the demo browser session in one command:

```bash
bash infra/scripts/presentation-recovery.sh
```

This does not run `reset-demo`. It fails closed if login or `/auth/me` cannot
be verified.
