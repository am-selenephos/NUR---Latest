"""Validated owner inputs for the public Agent lifecycle."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.agentic.enums import InitiativeLevel, RiskClass


def _clean_unique(values: list[str]) -> list[str]:
    cleaned = [value.strip() for value in values]
    if any(not value for value in cleaned):
        raise ValueError("values cannot be blank")
    if len(cleaned) != len(set(cleaned)):
        raise ValueError("values must be unique")
    return cleaned


class QuietHoursIn(BaseModel):
    start: int = Field(ge=0, le=23)
    end: int = Field(ge=0, le=23)
    timezone: str = Field(default="UTC", min_length=1, max_length=80)

    @field_validator("timezone")
    @classmethod
    def clean_timezone(cls, value: str) -> str:
        return value.strip()


class AgentPolicyPut(BaseModel):
    seen_version: int = Field(ge=0)
    initiative_level: InitiativeLevel = InitiativeLevel.SUGGEST
    max_risk_class: RiskClass = RiskClass.R1_PRIVATE_DRAFT
    permitted_tools: list[str] = Field(default_factory=list, max_length=64)
    auto_run_tools: list[str] = Field(default_factory=list, max_length=64)
    denied_tools: list[str] = Field(default_factory=list, max_length=64)
    daily_budget_cents: int = Field(default=0, ge=0, le=10_000_000)
    max_proposals_per_day: int = Field(default=3, ge=0, le=100)
    cooldown_minutes: int = Field(default=180, ge=0, le=43_200)
    quiet_hours: QuietHoursIn | None = None

    @field_validator("permitted_tools", "auto_run_tools", "denied_tools")
    @classmethod
    def clean_tools(cls, value: list[str]) -> list[str]:
        return _clean_unique(value)

    @model_validator(mode="after")
    def validate_relationships(self) -> "AgentPolicyPut":
        permitted = set(self.permitted_tools)
        auto_run = set(self.auto_run_tools)
        denied = set(self.denied_tools)
        if not auto_run <= permitted:
            raise ValueError(
                "auto_run_tools must be a subset of permitted_tools: "
                f"{sorted(auto_run - permitted)}"
            )
        if overlap := permitted & denied:
            raise ValueError(
                f"a tool cannot be both permitted and denied: {sorted(overlap)}"
            )
        return self


class ProposedStepIn(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,119}$")
    role: str = Field(min_length=1, max_length=64)
    tool_key: str = Field(min_length=1, max_length=120)
    depends_on: list[str] = Field(default_factory=list, max_length=64)
    input_refs: dict[str, Any] = Field(default_factory=dict)
    rationale: str = Field(min_length=1, max_length=2000)

    @field_validator("key", "role", "tool_key", "rationale")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("depends_on")
    @classmethod
    def clean_dependencies(cls, value: list[str]) -> list[str]:
        return _clean_unique(value)


class WorkflowCreateIn(BaseModel):
    request_id: UUID
    title: str = Field(min_length=1, max_length=400)
    objective: str = Field(min_length=1, max_length=5000)
    context_manifest: dict[str, Any] = Field(min_length=1)
    success_criteria: list[str] = Field(min_length=1, max_length=20)
    proposed_steps: list[ProposedStepIn] = Field(min_length=1, max_length=64)

    @field_validator("title", "objective")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("success_criteria")
    @classmethod
    def clean_success_criteria(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("success criteria cannot be blank")
        if any(len(item) > 500 for item in cleaned):
            raise ValueError("each success criterion must be at most 500 characters")
        return cleaned


class WorkflowStartIn(BaseModel):
    seen_plan_version: int = Field(ge=1)


class WorkflowRetryIn(BaseModel):
    request_id: UUID
    seen_plan_version: int = Field(ge=1)
