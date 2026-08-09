import datetime as dt
import uuid

from sqlalchemy import ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from app.db.base import Base
from app.models._mixins import now_utc, uuid_pk


class AccountDeletionRequest(Base):
    __tablename__ = "account_deletion_requests"

    id = uuid_pk()
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    account_ref: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    receipt_token_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(48), nullable=False, default="PENDING")
    requested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, server_default=text("now()"), nullable=False
    )
    purge_after: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cancelled_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    purge_started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    purged_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    claim_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    failure_code: Mapped[str | None] = mapped_column(String(80))
    cleanup_summary: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, server_default=text("now()"), nullable=False
    )


class AccountCleanupItem(Base):
    __tablename__ = "account_cleanup_items"

    id = uuid_pk()
    deletion_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account_deletion_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    cleanup_kind: Mapped[str] = mapped_column(String(48), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(32))
    resource_ref: Mapped[str | None] = mapped_column(Text)
    resource_ref_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, server_default=text("now()"), nullable=False
    )
