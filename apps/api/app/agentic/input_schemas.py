"""Explicit argument schemas for bound tools, used to validate an owner's EDIT.

Handler-signature introspection was the alternative and is deliberately not
used: a keyword-only parameter with a default tells Python nothing about
whether the *value an owner supplies* is the right shape, and `**kwargs` or a
signature change would silently widen what an EDIT accepts. These schemas are
declared once, independent of the handler's Python signature, and are the
thing an EDIT is actually checked against.

Only bound tools are listed — an unbound tool is refused before its arguments
would ever matter.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    type: type | tuple[type, ...]
    required: bool = False


# tool_key -> {argument name -> Field}. A field's absence from a step's edit
# payload is fine when not required; its presence with the wrong Python type,
# or any key not listed here at all, is not.
INPUT_SCHEMAS: dict[str, dict[str, Field]] = {
    # ── Read-only ──
    "get_today_state": {},
    "get_system_snapshot": {"system_slug": Field(str, required=True)},
    "get_plan": {"plan_id": Field(str)},
    "get_timeline": {"limit": Field(int)},
    "get_map_neighbourhood": {"node_id": Field(str), "depth": Field(int)},
    "get_orbit": {"orbit_id": Field(str)},
    "get_project": {"project_id": Field(str)},
    "get_project_evidence": {"project_id": Field(str, required=True)},
    "get_insight": {"insight_id": Field(str)},
    "search_approved_memory": {"query": Field(str), "limit": Field(int)},
    # ── Private drafts ──
    "create_draft_plan": {
        "title": Field(str, required=True),
        "orbit_id": Field(str),
        "steps": Field(list),
    },
    "create_memory_candidate": {
        "candidate_text": Field(str, required=True),
        "orbit_id": Field(str),
        "memory_type": Field(str),
    },
    "create_research_brief": {
        "question": Field(str, required=True),
        "notes": Field(str),
        "orbit_id": Field(str),
    },
    "create_insight_candidate": {
        "title": Field(str, required=True),
        "claim": Field(str, required=True),
        "what_nur_may_be_wrong_about": Field(str, required=True),
        "evidence": Field(list),
        "counter_evidence": Field(list),
        "confidence": Field((int, float)),
        "affected_system_slug": Field(str),
    },
    "create_timeline_draft": {
        "title": Field(str, required=True),
        "description": Field(str),
        "system_slug": Field(str),
        "importance": Field(int),
    },
    # ── Durable ──
    "activate_plan": {"plan_id": Field(str, required=True)},
    "schedule_timeline_event": {
        "event_id": Field(str, required=True),
        "scheduled_for": Field(str, required=True),
    },
    "accept_or_correct_insight": {
        "insight_id": Field(str, required=True),
        "decision": Field(str, required=True),
        "correction": Field(str),
    },
}


def validate_arguments(tool_key: str, arguments: dict) -> list[str]:
    """Return every problem with `arguments` against the tool's schema.

    Empty means valid. `{}` itself is valid only when the schema has no
    required fields — an empty edit to a tool that requires `title` is not a
    smaller version of the call, it is a different, invalid one.
    """
    schema = INPUT_SCHEMAS.get(tool_key)
    if schema is None:
        return [f"no input schema declared for {tool_key!r}"]

    problems: list[str] = []
    for name in arguments:
        if name not in schema:
            problems.append(f"unknown field {name!r}")

    for name, field in schema.items():
        if name not in arguments:
            if field.required:
                problems.append(f"missing required field {name!r}")
            continue
        value = arguments[name]
        if value is None:
            if field.required:
                problems.append(f"{name!r} is required and cannot be null")
            continue
        # bool is a subclass of int; a boolean is never the intended value for
        # a declared int/float field, and letting it through would accept
        # `true` for something like `limit`.
        if isinstance(value, bool) or not isinstance(value, field.type):
            problems.append(f"{name!r} must be {field.type}, got {type(value).__name__}")

    return problems
