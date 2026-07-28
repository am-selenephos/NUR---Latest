"""What may cross into a checkpoint, an approval card, or telemetry.

Three destinations, one rule: none of them may carry a secret, and none of them
may carry more of the owner's private text than the destination actually needs.

The distinction that matters is between *redacting* and *dropping*. A redacted
value keeps its key, so an owner reading an approval card can see that a field
exists and was withheld. A dropped value would make the card quietly incomplete,
which is worse than showing a mask — the owner would be approving something with
an invisible parameter in it.

Secrets are matched by key name rather than by value pattern. Pattern matching
on values is a losing game: it fails open on anything unusual, and failing open
here means a token in a checkpoint.
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "«redacted»"

# Substring match, case-insensitive. Deliberately broad — a false positive costs
# an owner one masked field on a card; a false negative costs a leaked token.
SECRET_KEY_PARTS: tuple[str, ...] = (
    "password", "passwd", "secret", "token", "api_key", "apikey", "authorization",
    "auth", "credential", "private_key", "session", "cookie", "bearer",
    "access_key", "refresh", "signature", "otp", "pin",
)

# Owner content that may exist in working state but must never reach telemetry.
PRIVATE_TEXT_KEYS: tuple[str, ...] = (
    "journal_text", "talk_text", "entry_body", "memory_text", "raw_input",
    "message", "body", "content", "note",
)

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SECRET_KEY_PARTS)


def redact_arguments(value: Any, *, drop_private_text: bool = False) -> Any:
    """Recursively mask secrets. Structure is preserved so nothing goes missing.

    `drop_private_text` is off for approval cards — the owner is entitled to see
    the text NUR proposes to act on, because that is the thing they are being
    asked to approve — and on for telemetry, where owner prose has no business
    at all.
    """
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, inner in value.items():
            if is_secret_key(str(key)):
                out[key] = REDACTED
            elif drop_private_text and str(key).lower() in PRIVATE_TEXT_KEYS:
                out[key] = REDACTED
            else:
                out[key] = redact_arguments(inner, drop_private_text=drop_private_text)
        return out
    if isinstance(value, (list, tuple)):
        rendered = [redact_arguments(item, drop_private_text=drop_private_text) for item in value]
        return type(value)(rendered) if isinstance(value, tuple) else rendered
    if isinstance(value, str) and drop_private_text:
        return _EMAIL.sub(REDACTED, value)
    return value


def contains_secret(value: Any) -> bool:
    """True if any key anywhere looks like a secret. Used as an assertion before
    a checkpoint is written, so an unredacted blob cannot be persisted."""
    if isinstance(value, dict):
        return any(
            is_secret_key(str(k)) and v != REDACTED or contains_secret(v)
            for k, v in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(contains_secret(item) for item in value)
    return False


def telemetry_safe(value: Any) -> Any:
    """Redaction for traces and logs: secrets masked, owner prose withheld."""
    return redact_arguments(value, drop_private_text=True)
