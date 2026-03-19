"""Shared types for the agent subsystem.

These live in their own module so that both the agent loop and every provider
can import them without creating circular dependencies.

    loop.py  ──imports──►  types.py  ◄──imports──  providers/*.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

EventCallback = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class ChatTurnResult:
    content: str
    tool_calls: list[ToolCall]


@dataclass(slots=True)
class AgentLoopResult:
    session_id: str
    assistant_message_id: str | None
    final_content: str
    iterations: int
    tool_calls_executed: int
    active_plan_id: str | None


async def emit_event(callback: EventCallback | None, payload: dict[str, Any]) -> None:
    """Send an SSE payload through the callback if one is provided."""
    if callback is not None:
        await callback(payload)
