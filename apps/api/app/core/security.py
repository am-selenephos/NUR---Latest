"""Password hashing (Argon2id), session-token, and CSRF cryptography.

Session cookie value: "<session_id>.<secret>".
The DB stores HMAC-SHA256(SESSION_SECRET, secret) — never the secret, and never a
keyless hash: a database dump alone cannot validate or forge session tokens.
Rotating SESSION_SECRET invalidates every live session (the documented rotation lever).

CSRF is a signed double-submit: token = HMAC-SHA256(CSRF_SECRET, session_id).
The server recomputes the expected value from the *resolved* session, so a token
is only ever valid for the session it was issued to. Rotating CSRF_SECRET
invalidates outstanding tokens without touching sessions.
"""
import hashlib
import hmac
import secrets
import uuid

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

# Argon2id is the argon2-cffi default type.
_ph = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)
# Constant dummy hash so unknown-email logins cost the same as bad-password logins.
_DUMMY_HASH = _ph.hash("nur-timing-equalizer")


def _mac(key: str, message: str) -> str:
    return hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()


def hash_password(raw: str) -> str:
    return _ph.hash(raw)


def verify_password(raw: str, password_hash: str | None) -> bool:
    try:
        return _ph.verify(password_hash or _DUMMY_HASH, raw)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def hash_session_secret(secret: str) -> str:
    """Keyed digest stored in sessions.session_secret_hash (see module docstring)."""
    return _mac(get_settings().session_secret, secret)


def hash_password_reset_token(token: str) -> str:
    """Keyed, domain-separated digest. Raw reset tokens never enter storage."""
    return _mac(get_settings().session_secret, f"password-reset:{token}")


def new_password_reset_token() -> tuple[str, str]:
    """Returns (raw_token_for_delivery, keyed_digest_for_storage)."""
    token = secrets.token_urlsafe(48)
    return token, hash_password_reset_token(token)


def hash_account_deletion_receipt_token(token: str) -> str:
    """Keyed digest for a deletion receipt secret retained after owner purge."""
    return _mac(get_settings().session_secret, f"account-deletion-receipt:{token}")


def new_account_deletion_receipt_token() -> tuple[str, str]:
    """Return the one-time owner receipt token and only its durable digest."""
    token = secrets.token_urlsafe(48)
    return token, hash_account_deletion_receipt_token(token)


def opaque_fingerprint(value: str, *, purpose: str) -> str:
    """Short keyed identifier suitable for limiter keys and audit metadata."""
    return _mac(get_settings().session_secret, f"{purpose}:{value}")[:16]


def new_session_token() -> tuple[uuid.UUID, str, str]:
    """Returns (session_id, cookie_value, secret_hash_hex)."""
    sid = uuid.uuid4()
    secret = secrets.token_urlsafe(32)
    return sid, f"{sid}.{secret}", hash_session_secret(secret)


def split_session_cookie(value: str) -> tuple[uuid.UUID, str] | None:
    sid_raw, _, secret = value.partition(".")
    if not secret:
        return None
    try:
        return uuid.UUID(sid_raw), secret
    except ValueError:
        return None


def secret_matches(secret: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_session_secret(secret), stored_hash)


def csrf_token_for(session_id: uuid.UUID) -> str:
    """Signed double-submit token, bound to one session."""
    return _mac(get_settings().csrf_secret, str(session_id))


def csrf_matches(supplied: str | None, expected: str) -> bool:
    if not supplied:
        return False
    return hmac.compare_digest(supplied, expected)


def email_fingerprint(email: str) -> str:
    """Non-reversible fingerprint for audit metadata — raw emails stay out of audit rows."""
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()[:16]
