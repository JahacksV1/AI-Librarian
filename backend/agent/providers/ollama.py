from __future__ import annotations

import json
from typing import Any

import httpx

from agent.providers.base import ModelProvider
from agent.types import ChatTurnResult, EventCallback, ToolCall, emit_event
from config import settings
from db.enums import SSEEventType


class OllamaProvider(ModelProvider):
    """Local Ollama provider.

    Wire format: POST /api/chat with NDJSON streaming.
    Messages and tool schemas use the OpenAI-compatible format natively --
    no conversion needed since that's what context.py already produces.
    """

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        event_callback: EventCallback | None,
    ) -> ChatTurnResult:
        url = f"{settings.ollama_url.rstrip('/')}/api/chat"
        payload = {
            "model": settings.effective_model_name,
            "messages": messages,
            "tools": tools,
            "stream": True,
        }

        content_chunks: list[str] = []
        accumulated_tool_calls: list[ToolCall] = []

        timeout = httpx.Timeout(connect=10.0, read=None, write=30.0, pool=30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    chunk = json.loads(line)
                    message_payload = chunk.get("message") or {}

                    content = message_payload.get("content") or ""
                    if content:
                        content_chunks.append(content)
                        await emit_event(
                            event_callback,
                            {"type": SSEEventType.TOKEN.value, "token": content},
                        )

                    chunk_tool_calls = _extract_tool_calls(message_payload)
                    if chunk_tool_calls:
                        existing_ids = {tc.id for tc in accumulated_tool_calls}
                        for tc in chunk_tool_calls:
                            if tc.id not in existing_ids:
                                accumulated_tool_calls.append(tc)
                                existing_ids.add(tc.id)

                    if chunk.get("done"):
                        break

        return ChatTurnResult(
            content="".join(content_chunks),
            tool_calls=accumulated_tool_calls,
        )


def _extract_tool_calls(message_payload: dict[str, Any]) -> list[ToolCall]:
    """Parse tool calls from an Ollama NDJSON message chunk."""
    tool_calls: list[ToolCall] = []

    for index, tool_call in enumerate(message_payload.get("tool_calls") or []):
        function = tool_call.get("function") or {}
        arguments = function.get("arguments") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}

        tool_calls.append(
            ToolCall(
                id=tool_call.get("id") or f"tool-call-{index}",
                name=function.get("name", ""),
                arguments=arguments,
            )
        )

    return [tc for tc in tool_calls if tc.name]
