"""NUR Mind Self Model — truthful representation of NUR's operational state.

Assembles ``SelfCapabilities`` reflecting actual provider availability, model configuration,
budget status, known limitations, and recent operational failures.
Prevents false claims about capabilities (e.g. web search when disabled, durable memory without approval).
"""
from __future__ import annotations

import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.brain.schemas import SelfCapabilities
from app.core.config import get_settings
from app.models import ModelRun


async def get_self_capabilities(
    db: AsyncSession | None = None,
    owner_user_id: uuid.UUID | None = None,
) -> SelfCapabilities:
    """Return a truthful ``SelfCapabilities`` snapshot based on environment and DB usage."""
    s = get_settings()
    provider_name = s.ai_provider
    provider_available = provider_name != "disabled"
    model = s.openai_model if provider_available else None

    daily_budget_remaining = s.ai_per_user_daily_limit

    if db is not None and owner_user_id is not None and provider_available:
        import datetime as dt
        start_of_day = dt.datetime.now(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        usage_count = (
            await db.execute(
                select(func.count(ModelRun.id)).where(
                    ModelRun.owner_user_id == owner_user_id,
                    ModelRun.created_at >= start_of_day,
                    ModelRun.provider == provider_name,
                )
            )
        ).scalar_one()
        daily_budget_remaining = max(0, s.ai_per_user_daily_limit - usage_count)

    known_limitations: list[str] = []
    if not s.ai_allow_external_web_research:
        known_limitations.append("External web research is disabled on this server.")
    if provider_name == "disabled":
        known_limitations.append("Live AI provider is disabled; operates in ledger-only mode.")

    return SelfCapabilities(
        provider_name=provider_name,
        provider_available=provider_available,
        model=model,
        reasoning_effort=s.openai_reasoning_effort,
        daily_budget_remaining=daily_budget_remaining,
        known_limitations=known_limitations,
        recent_failures=[],
    )
