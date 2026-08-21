#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

TARGET="$TMP/NUR extracted release with spaces"
mkdir -p "$TARGET/infra/scripts" "$TARGET/apps/api/.venv/bin" "$TARGET/fake-bin"

cp "$ROOT/infra/scripts/bootstrap-dev.sh" "$TARGET/infra/scripts/bootstrap-dev.sh"
cp "$ROOT/package.json" "$ROOT/package-lock.json" "$TARGET/"
cp "$ROOT/apps/api/requirements.lock" "$ROOT/apps/api/requirements-dev.lock" "$TARGET/apps/api/"
cp "$ROOT/apps/api/pyproject.toml" "$TARGET/apps/api/"

LOG="$TMP/commands.log"
cat > "$TARGET/apps/api/.venv/bin/python" <<'SH'
#!/usr/bin/env bash
printf 'python' >> "$NUR_BOOTSTRAP_TEST_LOG"
printf ' <%s>' "$@" >> "$NUR_BOOTSTRAP_TEST_LOG"
printf '\n' >> "$NUR_BOOTSTRAP_TEST_LOG"
SH
cat > "$TARGET/fake-bin/npm" <<'SH'
#!/usr/bin/env bash
printf 'npm' >> "$NUR_BOOTSTRAP_TEST_LOG"
printf ' <%s>' "$@" >> "$NUR_BOOTSTRAP_TEST_LOG"
printf '\n' >> "$NUR_BOOTSTRAP_TEST_LOG"
SH
chmod +x "$TARGET/apps/api/.venv/bin/python" "$TARGET/fake-bin/npm"

PATH="$TARGET/fake-bin:$PATH" \
NUR_BOOTSTRAP_TEST_LOG="$LOG" \
bash "$TARGET/infra/scripts/bootstrap-dev.sh" --dependencies-only

grep -F 'npm <ci>' "$LOG" >/dev/null
grep -F "python <-m> <pip> <install> <--disable-pip-version-check> <--no-deps> <-r> <$TARGET/apps/api/requirements-dev.lock>" "$LOG" >/dev/null

if grep -E '(docker|psql|pg_isready|alembic)' "$LOG" >/dev/null; then
  printf 'bootstrap dependency-only mode invoked service provisioning\n' >&2
  exit 1
fi

if grep -Eq 'pip.*(--upgrade|apps/api\[dev\]|<-e>|<--editable>)|npm <install>' "$LOG"; then
  printf 'bootstrap used an unlocked dependency install\n' >&2
  exit 1
fi

printf 'bootstrap reproducibility: PASS\n'
