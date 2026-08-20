#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VALIDATOR="$ROOT/infra/scripts/validate-openai-local.sh"
TEST_ROOT="$(mktemp -d)"
trap 'rm -r -- "$TEST_ROOT"' EXIT HUP INT TERM
ENV_FILE="$TEST_ROOT/.env.local"
KEY=$'fake boot key with spaces "quotes" $dollar \\slash ;&() unicode-\u2603'

fail() {
  printf 'validate-openai-local regression failed: %s\n' "$1" >&2
  exit 1
}

write_config() {
  local provider="$1"
  local model="$2"
  local key="$3"
  {
    printf 'NUR_AI_PROVIDER=%q\n' "$provider"
    printf 'NUR_OPENAI_MODEL=%q\n' "$model"
    printf '%s=%q\n' "OPENAI_API_KEY" "$key"
  } > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
}

write_config openai "gpt-test" "$KEY"
OUTPUT="$(NUR_OPENAI_ENV_FILE="$ENV_FILE" bash "$VALIDATOR" 2>&1)"
[[ "$OUTPUT" == *"OpenAI configuration file is structurally valid."* ]] || fail "valid config was rejected"
[[ "$OUTPUT" == *"Live authentication has not yet been tested."* ]] || fail "valid config did not preserve the honest live-auth boundary"
[[ "$OUTPUT" != *"$KEY"* ]] || fail "valid config output exposed the key"

chmod 640 "$ENV_FILE"
set +e
MODE_OUTPUT="$(NUR_OPENAI_ENV_FILE="$ENV_FILE" bash "$VALIDATOR" 2>&1)"
MODE_STATUS=$?
set -e
[[ "$MODE_STATUS" -ne 0 ]] || fail "non-600 mode was accepted"
[[ "$MODE_OUTPUT" != *"$KEY"* ]] || fail "mode failure output exposed the key"

write_config disabled "gpt-test" "$KEY"
set +e
PROVIDER_OUTPUT="$(NUR_OPENAI_ENV_FILE="$ENV_FILE" bash "$VALIDATOR" 2>&1)"
PROVIDER_STATUS=$?
set -e
[[ "$PROVIDER_STATUS" -ne 0 ]] || fail "disabled provider was accepted"
[[ "$PROVIDER_OUTPUT" != *"$KEY"* ]] || fail "provider failure output exposed the key"

printf 'NUR_AI_PROVIDER=openai\nNUR_OPENAI_MODEL=' > "$ENV_FILE"
chmod 600 "$ENV_FILE"
set +e
SYNTAX_STATUS=0
NUR_OPENAI_ENV_FILE="$ENV_FILE" bash "$VALIDATOR" >/dev/null 2>&1 || SYNTAX_STATUS=$?
set -e
[[ "$SYNTAX_STATUS" -ne 0 ]] || fail "empty model was accepted"

rm -- "$ENV_FILE"
ln -s "$TEST_ROOT/missing" "$ENV_FILE"
set +e
SYMLINK_STATUS=0
NUR_OPENAI_ENV_FILE="$ENV_FILE" bash "$VALIDATOR" >/dev/null 2>&1 || SYMLINK_STATUS=$?
set -e
[[ "$SYMLINK_STATUS" -ne 0 ]] || fail "symbolic link was accepted"

printf 'validate-openai-local regression passed.\n'
