import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, EmailStr, Field, SecretStr


class OwnerExportTable(BaseModel):
    name: str
    ownership_basis: str
    row_count: int
    rows: list[dict[str, Any]]


class OwnerExportChecksum(BaseModel):
    algorithm: str
    covers: str
    value: str


class OwnerExportManifest(BaseModel):
    schema_url: str = Field(alias="schema")
    version: str
    owner_user_id: uuid.UUID
    provenance: dict[str, Any]
    summary: dict[str, int]
    tables: list[OwnerExportTable]
    objects: list[dict[str, Any]]
    checksum: OwnerExportChecksum


class SessionInventoryItem(BaseModel):
    id: uuid.UUID
    created_at: dt.datetime
    expires_at: dt.datetime
    revoked_at: dt.datetime | None
    current: bool
    state: str


class SessionInventoryResponse(BaseModel):
    sessions: list[SessionInventoryItem]


class SessionRevocationResponse(BaseModel):
    revoked_session_count: int


class AccountDeletionRequestIn(BaseModel):
    password: SecretStr
    confirmation: str = Field(max_length=64)


class AccountDeletionAccepted(BaseModel):
    request_id: uuid.UUID
    status: str
    requested_at: dt.datetime
    purge_after: dt.datetime
    immediate_access_shutdown: bool
    receipt_token: str


class AccountDeletionCancelIn(BaseModel):
    email: EmailStr
    password: SecretStr
    confirmation: str = Field(max_length=64)


class AccountDeletionCancelled(BaseModel):
    cancelled: bool
    status: str
    login_required: bool


class AccountDeletionReceiptIn(BaseModel):
    request_id: uuid.UUID
    receipt_token: SecretStr


class AccountDeletionReceiptOut(BaseModel):
    request_id: uuid.UUID
    status: str
    requested_at: dt.datetime
    purge_after: dt.datetime
    cancelled_at: dt.datetime | None
    purged_at: dt.datetime | None
    cleanup_summary: dict[str, Any]
