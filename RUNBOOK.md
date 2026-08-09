# Runbook

This runbook describes local operation. Commands must be run from the exact candidate commit;
results from another SHA are not release evidence.

## Start

```bash
bash RUN_NUR.sh
```

This starts Postgres, Redis, the FastAPI server, Celery worker, Celery beat, and
Vite, runs health checks, seeds the local demo, and opens the browser. Runtime
PIDs and logs live under `.nur-runtime/`.

## Status

```bash
bash RUN_NUR.sh status
```

Expected local URLs:

- Web: `http://localhost:5173`
- API health: `http://localhost:8000/healthz`
- API ready: `http://localhost:8000/readyz`
- Metrics: `http://localhost:8000/metrics`

## Logs

```bash
bash RUN_NUR.sh logs
```

The logs helper redacts common key/token patterns before printing.

## Stop

```bash
bash RUN_NUR.sh stop
```

This stops local PIDs and compose services. The named Postgres volume remains
until removed manually.

## Reset Local Data

```bash
bash RUN_NUR.sh reset-demo
```

This is destructive to local demo data. Do not run it against an environment containing data that
must be retained.

## Database migration role

Alembic must use the schema-owner connection through `ALEMBIC_DATABASE_URL`. The runtime
`nur_app` role is intentionally unable to own schemas or bypass forced RLS. A fresh environment
may also require:

```bash
bash infra/scripts/provision-email-lookup-role.sh
```

Never point a migration command at a database inferred from a default URL. Verify the target,
current revision, and single Alembic head before upgrade or rollback work.

## Credential incident

If any provider credential is reported in chat, an archive, a log, or another uncontrolled
location, stop using it. Revoke and rotate it in the provider's trusted control plane, out of band.
Do not retrieve, copy, transfer, or reuse an old `.env` to restore service. Review provider usage,
then provision a fresh least-privilege value through the hidden local configuration flow.

## Runtime recovery

- Use `bash RUN_NUR.sh status` and `bash RUN_NUR.sh logs` before restarting services.
- Keep owner data and the dispatch/event ledgers intact while diagnosing Agency or worker faults.
- Do not mark approvals complete, rewrite workflow state, or delete outbox rows by hand.
- Provider-disabled mode is an honest degraded mode; it must not fabricate AI or external actions.
- Backup, restore, and drill helpers live in `infra/scripts/dr-*.sh`. Their existence is not proof
  of an achieved RPO/RTO; retain the timed drill evidence for the exact candidate.

## Account erasure worker

`DELETE /api/v1/account` revokes every owner session and marks the account
`deletion_pending` immediately. Celery beat then runs `nur.account_deletion_purge`
after `NUR_ACCOUNT_DELETION_GRACE_HOURS`. Cleanup is leased and idempotent: a
missing local object is a completed retry, while a real deletion failure returns
the request to `PENDING` with bounded backoff. Do not delete queue rows or object
files manually. A configured external provider without an erasure adapter is
recorded as `PURGED_EXTERNAL_ACTION_REQUIRED`; it is never reported as erased.

## Package

```bash
bash RUN_NUR.sh package
```

The packager excludes `.env`, `.env.local`, node modules, build outputs,
runtime logs, DB files, proof artifacts, and `.git`; then it runs the secret
scan and writes a SHA-256 sidecar.

Inspect and independently verify the produced package before distribution. Packaging does not
rotate a credential that was exposed elsewhere.
