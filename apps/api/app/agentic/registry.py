"""Tool resolution. Refuses rather than improvises.

A registry that returns something plausible for an unknown key is worse than one
that raises, because a planner will treat an empty result as a successful step
and build the rest of the plan on it. Every failure mode here is loud.

Handler binding is separate from contract declaration on purpose. A contract can
exist — so the policy engine and the approval card can reason about it — while
its handler is still unimplemented, and calling it fails with a specific error
instead of silently doing nothing.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.agentic.policy import ToolContract
from app.agentic.tools import ALL_TOOLS, ToolSpec

ToolHandler = Callable[..., Awaitable[Any]]


class UnknownToolError(LookupError):
    """Raised for a key with no contract. Never returns a default."""


class UnboundToolError(RuntimeError):
    """Raised when a declared tool has no handler bound yet."""


class DuplicateToolError(RuntimeError):
    """Two specs claiming the same key would make resolution ambiguous."""


def _index(specs: tuple[ToolSpec, ...]) -> dict[str, ToolSpec]:
    table: dict[str, ToolSpec] = {}
    for spec in specs:
        if spec.contract.key in table:
            raise DuplicateToolError(f"duplicate tool key: {spec.contract.key}")
        table[spec.contract.key] = spec
    return table


_SPECS: dict[str, ToolSpec] = _index(ALL_TOOLS)
_HANDLERS: dict[str, ToolHandler] = {}


def spec(key: str) -> ToolSpec:
    try:
        return _SPECS[key]
    except KeyError as exc:
        raise UnknownToolError(f"no contract registered for tool {key!r}") from exc


def contract(key: str) -> ToolContract:
    return spec(key).contract


def bind(key: str, handler: ToolHandler) -> None:
    """Attach a handler to a declared contract.

    Binding a key with no contract is rejected: it would create a callable tool
    the policy engine has never seen, which is capability escalation by
    accident.
    """
    if key not in _SPECS:
        raise UnknownToolError(f"cannot bind handler for undeclared tool {key!r}")
    _HANDLERS[key] = handler


def handler(key: str) -> ToolHandler:
    spec(key)  # raises UnknownToolError first, so the message is accurate
    try:
        return _HANDLERS[key]
    except KeyError as exc:
        raise UnboundToolError(
            f"tool {key!r} is declared but has no handler bound; it cannot be executed"
        ) from exc


def is_bound(key: str) -> bool:
    return key in _HANDLERS


def all_keys() -> tuple[str, ...]:
    return tuple(sorted(_SPECS))


def bound_keys() -> tuple[str, ...]:
    return tuple(sorted(_HANDLERS))


def catalog() -> tuple[ToolSpec, ...]:
    """Every declared tool, for the `/api/v1/agentic/tools` surface."""
    return tuple(_SPECS[key] for key in all_keys())
