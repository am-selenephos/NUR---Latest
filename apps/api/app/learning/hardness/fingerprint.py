"""Deterministic canonical JSON serialization and SHA-256 fingerprinting for Hardness plane."""
from __future__ import annotations

import datetime as dt
from enum import Enum
import hashlib
import json
from typing import Any
import uuid


def _json_default(obj: Any) -> Any:
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, (dt.datetime, dt.date)):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, bytes):
        return obj.hex()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def canonical_json_dumps(data: Any) -> str:
    """Serialize data into deterministic, canonical JSON with sorted keys and minimal separators."""
    return json.dumps(
        data,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
        default=_json_default,
    )


def canonical_json_bytes(data: Any) -> bytes:
    """Serialize data into deterministic UTF-8 canonical JSON bytes."""
    return canonical_json_dumps(data).encode("utf-8")


def sha256_hex(data: Any) -> str:
    """Compute SHA-256 hex digest of string, bytes, or JSON-serializable structure."""
    if isinstance(data, bytes):
        raw = data
    elif isinstance(data, str):
        raw = data.encode("utf-8")
    else:
        raw = canonical_json_bytes(data)
    return hashlib.sha256(raw).hexdigest()


def compute_candidate_fingerprint(
    *,
    owner_user_id: uuid.UUID,
    signal_kind: str,
    task_class: str,
    failure_signature: str | None = None,
    desired_behavior: str | None = None,
) -> str:
    """Compute deterministic fingerprint for a learning candidate."""
    normalized_payload = {
        "owner_user_id": str(owner_user_id),
        "signal_kind": signal_kind.strip().upper(),
        "task_class": task_class.strip().lower(),
        "failure_signature": (failure_signature or "").strip(),
        "desired_behavior": (desired_behavior or "").strip(),
    }
    return sha256_hex(normalized_payload)


def compute_dataset_hash(ordered_candidates: list[dict[str, Any]]) -> str:
    """Compute SHA-256 hash over an ordered sequence of candidate items."""
    return sha256_hex(ordered_candidates)
