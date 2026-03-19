from __future__ import annotations

import json
from typing import Any

import openai

from agent.providers.base import ModelProvider
from agent.types import ChatTurnResult, EventCallback, ToolCall, emit_event
from config import settings
from db.enums import SSEEventType


class OpenAIProvider(ModelProvider):
    """GPT models via OpenAI API.

    Wire format: SSE with delta objects (data: {...}, data: [DONE]).
    Requires OPENAI_API_KEY in environment.

    Messages and tool schemas use the OpenAI function-call format natively --
    no conversion needed since that's what context.py already produces.
    Tool call arguments arrive as incremental string fragments across multiple
    chunks, so we accumulate them before parsing.
    """

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        event_callback: EventCallback | None,
    ) -> ChatTurnResult:
        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

        kwargs: dict[str, Any] = {
            "model": settings.effective_model_name,
            "messages": messages,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools

        content_chunks: list[str] = []

        # Tool calls arrive incrementally: each chunk carries an index and
        # partial name/arguments strings that must be concatenated.
        pending_calls: dict[int, _PendingToolCall] = {}

        stream = await client.chat.completions.create(**kwargs)

        async for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            if choice is None:
                continue

            delta = choice.delta

            if delta.content:
                content_chunks.append(delta.content)
                await emit_event(
                    event_callback,
                    {"type": SSEEventType.TOKEN.value, "token": delta.content},
                )

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in pending_calls:
                        pending_calls[idx] = _PendingToolCall()

                    pending = pending_calls[idx]
                    if tc_delta.id:
                        pending.id = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            pending.name += tc_delta.function.name
                        if tc_delta.function.arguments:
                            pending.arguments_json += tc_delta.function.arguments

        tool_calls = _finalize_tool_calls(pending_calls)

        return ChatTurnResult(
            content="".join(content_chunks),
            tool_calls=tool_calls,
        )


class _PendingToolCall:
    """Accumulator for incrementally-streamed tool call fragments."""

    __slots__ = ("id", "name", "arguments_json")

    def __init__(self) -> None:
        self.id: str = ""
        self.name: str = ""
        self.arguments_json: str = ""


def _finalize_tool_calls(
    pending: dict[int, _PendingToolCall],
) -> list[ToolCall]:
    """Convert accumulated fragments into resolved ToolCall objects."""
    result: list[ToolCall] = []
    for idx in sorted(pending):
        p = pending[idx]
        if not p.name:
            continue
        try:
            arguments = json.loads(p.arguments_json) if p.arguments_json else {}
        except json.JSONDecodeError:
            arguments = {}
        result.append(
            ToolCall(
                id=p.id or f"tool-call-{idx}",
                name=p.name,
                arguments=arguments,
            )
        )
    return result
