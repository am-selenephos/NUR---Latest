import datetime as dt
import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import AIRequestBudgetExceeded
from app.billing.entitlements import resolve_entitlement
from app.core.config import get_settings
from app.models.cognition import ModelRun


async def assert_daily_ai_budget(db: AsyncSession, *, owner_user_id: uuid.UUID) -> None:
    s = get_settings()
    if s.ai_provider != "openai":
        return
    start = dt.datetime.now(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # The transaction-scoped lock stays held through the caller's provider run
    # and ModelRun commit. Concurrent requests for one owner therefore observe
    # the preceding committed provider run instead of all passing a stale count.
    lock_key = f"nur:ai-budget:{owner_user_id}:{start.date().isoformat()}"
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": lock_key},
    )

    actual_count = (
        await db.execute(
            select(func.count(ModelRun.id)).where(
                ModelRun.owner_user_id == owner_user_id,
                ModelRun.created_at >= start,
                ModelRun.provider == "openai",
            )
        )
    ).scalar_one()
    entitlement = await resolve_entitlement(
        db,
        owner_user_id=owner_user_id,
        feature_key="ai.daily_requests",
    )
    limit = s.ai_per_user_daily_limit
    if entitlement.allowed and entitlement.usage_limit is not None:
        limit = entitlement.usage_limit
    if actual_count >= limit:
        raise AIRequestBudgetExceeded("Daily AI request limit reached.")

    request_ceiling = s.ai_request_cost_ceiling_cents
    reserved_cents = actual_count * request_ceiling
    if reserved_cents + request_ceiling > s.ai_daily_budget_cents:
        raise AIRequestBudgetExceeded(
            "Daily AI cost ceiling reached; no provider request was started."
        )

    # No cost row is written here. The ceiling is conservative policy used to
    # decide whether another provider request may start; it is never presented
    # as provider-reported actual spend. The caller's real ModelRun is the only
    # durable usage record, and the advisory lock remains held until it commits.
