from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent.loop import ChatTurnResult, EventCallback


class ModelProvider(ABC):
    """Abstract base for all LLM providers.

    Every provider receives:
    - messages: list of dicts in Ollama/OpenAI chat format (assembled by context.py).
    - tools: list of tool schemas in OpenAI function-call format (from MCP cache).
    - event_callback: async callable for streaming token SSE events to the frontend.

    Each provider is responsible for:
    1. Converting messages from the common format to its own wire format.
    2. Converting tool schemas from the common format to its own wire format.
    3. Making the HTTP request with the correct URL, auth, and payload.
    4. Reading the streaming response in its own format.
    5. Calling event_callback with {"type": "token", "token": "..."} for each token.
    6. Returning a ChatTurnResult with the full content and any tool calls.

    The rest of the agent loop (context assembly, MCP dispatch, DB writes, SSE to
    frontend) is provider-agnostic and does not change.
    """

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        event_callback: EventCallback | None,
    ) -> ChatTurnResult:
        """Send messages + tools to the LLM, stream tokens via event_callback,
        and return the complete response with any tool calls."""
        ...
