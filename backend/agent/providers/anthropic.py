from __future__ import annotations

import json
from typing import Any

import anthropic

from agent.providers.base import ModelProvider
from agent.types import ChatTurnResult, EventCallback, ToolCall, emit_event
from config import settings
from db.enums import SSEEventType


class AnthropicProvider(ModelProvider):
    """Claude models via Anthropic API.

    Wire format: SSE with typed events (content_block_delta, message_stop).
    Requires ANTHROPIC_API_KEY in environment.

    This provider converts from the internal OpenAI-compatible message format
    to the Anthropic format, and converts tool schemas from the OpenAI function
    envelope to the flat Anthropic schema.
    """

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        event_callback: EventCallback | None,
    ) -> ChatTurnResult:
        system_prompt, api_messages = _split_system_messages(messages)
        api_tools = [_convert_tool_schema(t) for t in tools]

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        content_chunks: list[str] = []
        tool_calls: list[ToolCall] = []

        active_tool_id: str | None = None
        active_tool_name: str | None = None
        active_tool_json_parts: list[str] = []

        kwargs: dict[str, Any] = {
            "model": settings.effective_model_name,
            "max_tokens": 4096,
            "messages": api_messages,
            "stream": True,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if api_tools:
            kwargs["tools"] = api_tools

        async with client.messages.stream(**kwargs) as stream:
            async for event in stream:
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        active_tool_id = block.id
                        active_tool_name = block.name
                        active_tool_json_parts = []

                elif event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        content_chunks.append(delta.text)
                        await emit_event(
                            event_callback,
                            {"type": SSEEventType.TOKEN.value, "token": delta.text},
                        )
                    elif delta.type == "input_json_delta":
                        active_tool_json_parts.append(delta.partial_json)

                elif event.type == "content_block_stop":
                    if active_tool_id and active_tool_name:
                        raw_json = "".join(active_tool_json_parts)
                        try:
                            arguments = json.loads(raw_json) if raw_json else {}
                        except json.JSONDecodeError:
                            arguments = {}
                        tool_calls.append(
                            ToolCall(
                                id=active_tool_id,
                                name=active_tool_name,
                                arguments=arguments,
                            )
                        )
                        active_tool_id = None
                        active_tool_name = None
                        active_tool_json_parts = []

        return ChatTurnResult(
            content="".join(content_chunks),
            tool_calls=tool_calls,
        )


def _split_system_messages(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Separate system messages from conversation messages.

    Anthropic expects the system prompt as a top-level parameter, not in the
    messages array.  Our internal format (from context.py) puts system content
    as {"role": "system", ...} entries.
    """
    system_parts: list[str] = []
    api_messages: list[dict[str, Any]] = []

    for msg in messages:
        if msg.get("role") == "system":
            system_parts.append(msg.get("content", ""))
        elif msg.get("role") == "tool":
            api_messages.append(_convert_tool_result_message(msg))
        elif msg.get("role") == "assistant" and msg.get("tool_calls"):
            api_messages.append(_convert_assistant_tool_call_message(msg))
        else:
            api_messages.append({"role": msg["role"], "content": msg.get("content", "")})

    return "\n\n".join(system_parts), api_messages


def _convert_assistant_tool_call_message(msg: dict[str, Any]) -> dict[str, Any]:
    """Convert an OpenAI-style assistant message with tool_calls to Anthropic format.

    OpenAI:  {"role": "assistant", "content": "...", "tool_calls": [{"id": "...", "function": {"name": "...", "arguments": {...}}}]}
    Anthropic: {"role": "assistant", "content": [{"type": "text", ...}, {"type": "tool_use", "id": "...", "name": "...", "input": {...}}]}
    """
    content_blocks: list[dict[str, Any]] = []

    text = msg.get("content", "")
    if text:
        content_blocks.append({"type": "text", "text": text})

    for tc in msg.get("tool_calls", []):
        func = tc.get("function", {})
        arguments = func.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        content_blocks.append({
            "type": "tool_use",
            "id": tc.get("id", ""),
            "name": func.get("name", ""),
            "input": arguments,
        })

    return {"role": "assistant", "content": content_blocks}


def _convert_tool_result_message(msg: dict[str, Any]) -> dict[str, Any]:
    """Convert an OpenAI-style tool result to Anthropic format.

    OpenAI:    {"role": "tool", "content": "...", "tool_call_id": "..."}
    Anthropic: {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "...", "content": "..."}]}
    """
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": msg.get("tool_call_id", ""),
                "content": msg.get("content", ""),
            }
        ],
    }


def _convert_tool_schema(tool: dict[str, Any]) -> dict[str, Any]:
    """Convert from OpenAI function-call format to Anthropic tool format.

    OpenAI:    {"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}
    Anthropic: {"name": "...", "description": "...", "input_schema": {...}}
    """
    func = tool.get("function", {})
    return {
        "name": func.get("name", ""),
        "description": func.get("description", ""),
        "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
    }
