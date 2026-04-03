from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from agent.context import assemble_context, compact_tool_result_for_model
from agent.providers import get_provider
from agent.types import (
    AgentLoopResult,
    ChatTurnResult,
    EventCallback,
    ToolCall,
    emit_event,
)
from config import settings
from db.connection import db_manager
from db.enums import RoleType, SSEEventType, SessionState
from db.models import Session, SessionMessage
from tools.update_task_state import update_task_state
from mcp_server import mcp

log = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 10
TOOL_TIMEOUT_SECONDS = 60  # Maximum wall-clock time allowed for any single tool call

# --- Tool Dispatch Contract (see docs/TOOL_DISPATCH.md) ---
# Parameters the agent loop injects from session context.
# These are stripped from tool schemas before the LLM sees them,
# then injected by the loop before MCP dispatch.
SYSTEM_INJECTED_PARAMS = frozenset({"session_id"})
TOOLS_REQUIRING_SESSION_ID = frozenset({
    "scan_folder",
    "query_indexed_files",
    "propose_plan",
    "get_task_state",
    "update_task_state",
})


_TOOL_SCHEMAS_CACHE: list[dict[str, Any]] | None = None


def _tool_to_function_schema(tool: Any) -> dict[str, Any]:
    name = getattr(tool, "name", "")
    description = getattr(tool, "description", "") or ""
    # In-process FastMCP 3.x uses .parameters; HTTP client MCP protocol uses .inputSchema
    input_schema = (
        getattr(tool, "parameters", None)
        or getattr(tool, "inputSchema", None)
        or getattr(tool, "input_schema", None)
        or {}
    )
    if not isinstance(input_schema, dict):
        input_schema = {"type": "object", "properties": {}, "required": []}
    if "type" not in input_schema:
        input_schema["type"] = "object"
    if "properties" not in input_schema:
        input_schema["properties"] = {}
    if "required" not in input_schema:
        input_schema["required"] = []

    filtered_props = {
        k: v for k, v in input_schema["properties"].items()
        if k not in SYSTEM_INJECTED_PARAMS
    }
    filtered_required = [
        r for r in input_schema["required"]
        if r not in SYSTEM_INJECTED_PARAMS
    ]

    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": filtered_props,
                "required": filtered_required,
            },
        },
    }


async def initialize_mcp_tool_cache() -> None:
    """Build the tool schema cache.

    When MCP_URL is set (Docker): connect to the external native MCP server via HTTP.
    When MCP_URL is empty (local dev): use the server object directly — avoids the
    FastMCP 3.x in-process Client deadlock.
    """
    global _TOOL_SCHEMAS_CACHE
    if _TOOL_SCHEMAS_CACHE is not None:
        return
    if settings.mcp_url:
        from fastmcp import Client
        async with Client(settings.mcp_url) as client:
            tools = await client.list_tools()
    else:
        tools = await mcp.list_tools()
    _TOOL_SCHEMAS_CACHE = [_tool_to_function_schema(tool) for tool in tools]


def get_cached_tool_schemas() -> list[dict[str, Any]]:
    global _TOOL_SCHEMAS_CACHE
    if _TOOL_SCHEMAS_CACHE is None:
        raise RuntimeError("MCP tool cache is not initialized. Call initialize_mcp_tool_cache() first.")
    return list(_TOOL_SCHEMAS_CACHE)


async def _persist_message(
    *,
    session_id: str,
    role: RoleType,
    content: str,
    tool_name: str | None = None,
    tool_call_id: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> str:
    session_uuid = uuid.UUID(session_id)

    async with db_manager.session() as session:
        session_row = await session.get(Session, session_uuid)
        if session_row is None:
            raise ValueError(f"Session not found: {session_id}")

        message = SessionMessage(
            session_id=session_uuid,
            role=role,
            content=content,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            metadata_json=metadata_json,
        )
        session.add(message)
        await session.commit()
        await session.refresh(message)
        return str(message.id)


def _serialize_tool_result(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=True, sort_keys=True)


def _estimate_context_tokens(messages: list[dict[str, Any]]) -> int:
    """Rough token estimate for the current message list.

    Uses a simple character-count heuristic (chars / 4 ≈ tokens).
    Good enough for logging and budget warnings; not a precise billing count.
    """
    total_chars = sum(len(json.dumps(m, ensure_ascii=True)) for m in messages)
    return total_chars // 4


def _assistant_tool_call_message(tool_calls: list[ToolCall], content: str) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.name,
                    "arguments": tool_call.arguments,
                },
            }
            for tool_call in tool_calls
        ],
    }


def _tool_result_message(tool_call: ToolCall, result: dict[str, Any]) -> dict[str, Any]:
    """Build a tool-result message for the live in-memory messages list.

    Uses the compact version of the result so the model's context window does not
    grow unboundedly on each iteration.  The full raw result is persisted to
    session_messages separately (see _persist_message call in run_agent_loop).
    """
    compact = compact_tool_result_for_model(tool_call.name, result)
    return {
        "role": "tool",
        "name": tool_call.name,
        "tool_call_id": tool_call.id,
        "content": _serialize_tool_result(compact),
    }


async def _update_state_for_tool_start(session_id: str, tool_name: str) -> None:
    if tool_name == "scan_folder":
        await update_task_state(session_id=session_id, current_step=SessionState.SCANNING.value)
    elif tool_name == "execute_action":
        await update_task_state(session_id=session_id, current_step=SessionState.EXECUTING.value)


async def _update_state_for_tool_result(
    session_id: str,
    tool_name: str,
    result: dict[str, Any],
    tool_args: dict[str, Any] | None = None,
) -> str | None:
    if tool_name == "scan_folder":
        # Scans are analysis/indexing operations; they do not imply a plan exists.
        # Transition back to IDLE and persist a compact analysis scope so subsequent
        # turns can answer follow-up questions via query_indexed_files without
        # rescanning — this is the persistent working-memory layer.
        path = (tool_args or {}).get("path", "")
        file_count = result.get("file_count") or len(result.get("files", []))
        folder_count = result.get("folder_count") or len(result.get("folders", []))
        scope = {
            "path": path,
            "scan_id": result.get("scan_id"),
            "depth": result.get("scan_depth"),
            "categories": result.get("categories", {}),
            "file_count": file_count,
            "folder_count": folder_count,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
        }
        await update_task_state(
            session_id=session_id,
            current_step=SessionState.IDLE.value,
            active_entities_json={"scope": scope},
        )
        return None

    if tool_name == "propose_plan":
        plan_id = result.get("plan_id")
        await update_task_state(
            session_id=session_id,
            current_step=SessionState.AWAITING_APPROVAL.value,
            active_plan_id=plan_id,
        )
        return plan_id

    if tool_name == "execute_action":
        outcome = result.get("outcome")
        next_state = SessionState.COMPLETE.value if outcome == "SUCCESS" else SessionState.ERROR.value
        await update_task_state(session_id=session_id, current_step=next_state)

    return None


def _normalize_tool_result(result: Any) -> dict[str, Any]:
    # FastMCP 3.x ToolResult (in-process) — structured_content is already a dict
    if hasattr(result, "structured_content") and isinstance(result.structured_content, dict):
        return result.structured_content

    if isinstance(result, dict):
        return result

    if hasattr(result, "data"):
        data = getattr(result, "data")
        if isinstance(data, dict):
            return data
        return {"data": data}

    if hasattr(result, "model_dump"):
        dumped = result.model_dump()
        if isinstance(dumped, dict):
            if isinstance(dumped.get("data"), dict):
                return dumped["data"]
            return dumped

    # FastMCP ToolResult with content list (may appear from HTTP client or in-process)
    content_list = None
    if hasattr(result, "content") and isinstance(result.content, list):
        content_list = result.content
    elif isinstance(result, list):
        content_list = result

    if content_list:
        first = content_list[0] if content_list else None
        text = getattr(first, "text", None) if first else None
        if text:
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, ValueError):
                return {"result": text}

    return {"result": str(result)}


@asynccontextmanager
async def _tool_client():
    """Yield an HTTP client when MCP_URL is configured, else None (direct in-process)."""
    if settings.mcp_url:
        from fastmcp import Client
        async with Client(settings.mcp_url) as client:
            yield client
    else:
        yield None


async def _call_tool(tool_call: ToolCall, http_client: Any = None) -> dict[str, Any]:
    """Dispatch a tool call via HTTP (Docker) or directly in-process (local dev)."""
    try:
        if http_client is not None:
            call_result = await asyncio.wait_for(
                http_client.call_tool(tool_call.name, arguments=tool_call.arguments or {}),
                timeout=TOOL_TIMEOUT_SECONDS,
            )
        else:
            call_result = await asyncio.wait_for(
                mcp.call_tool(tool_call.name, arguments=tool_call.arguments or {}),
                timeout=TOOL_TIMEOUT_SECONDS,
            )
    except asyncio.TimeoutError:
        return {
            "error": "timeout",
            "message": f"Tool '{tool_call.name}' exceeded {TOOL_TIMEOUT_SECONDS}s time limit.",
        }
    return _normalize_tool_result(call_result)


async def run_agent_loop(
    *,
    session_id: str,
    user_message: str,
    event_callback: EventCallback | None = None,
) -> AgentLoopResult:
    await initialize_mcp_tool_cache()

    assistant_message_id: str | None = None
    active_plan_id: str | None = None
    tool_calls_executed = 0

    await _persist_message(
        session_id=session_id,
        role=RoleType.USER,
        content=user_message,
    )

    context_packet = await assemble_context(session_id)
    messages = context_packet.to_messages()
    tools = get_cached_tool_schemas()

    log.info(
        "agent_loop.context",
        extra={
            "session_id": session_id,
            "message_count": len(messages),
            "estimated_tokens": _estimate_context_tokens(messages),
            "has_task_state": context_packet.task_state_text is not None,
            "tool_count": len(tools),
        },
    )

    provider = get_provider()

    async with _tool_client() as http_client:
        for iteration in range(1, MAX_TOOL_ITERATIONS + 1):
            try:
                turn = await provider.chat_stream(
                    messages=messages,
                    tools=tools,
                    event_callback=event_callback,
                )
            except Exception as exc:
                await update_task_state(
                    session_id=session_id,
                    current_step=SessionState.ERROR.value,
                    scratchpad_summary=str(exc),
                )
                await emit_event(
                    event_callback,
                    {
                        "type": SSEEventType.ERROR.value,
                        "message": "Model call failed",
                        "detail": str(exc),
                    },
                )
                raise

            log.info(
                "agent_loop.model_response",
                extra={
                    "session_id": session_id,
                    "iteration": iteration,
                    "had_tool_calls": bool(turn.tool_calls),
                    "tool_names": [tool_call.name for tool_call in turn.tool_calls],
                    "response_length": len(turn.content),
                },
            )

            if turn.tool_calls:
                messages.append(_assistant_tool_call_message(turn.tool_calls, turn.content))

                if turn.content:
                    assistant_message_id = await _persist_message(
                        session_id=session_id,
                        role=RoleType.ASSISTANT,
                        content=turn.content,
                        metadata_json={
                            "tool_calls": [
                                {"id": tool_call.id, "name": tool_call.name, "arguments": tool_call.arguments}
                                for tool_call in turn.tool_calls
                            ]
                        },
                    )

                for tool_call in turn.tool_calls:
                    tool_calls_executed += 1

                    await emit_event(
                        event_callback,
                        {
                            "type": SSEEventType.TOOL_CALL.value,
                            "tool": tool_call.name,
                            "args": tool_call.arguments,
                        },
                    )

                    log.info(
                        "agent_loop.tool_call",
                        extra={
                            "session_id": session_id,
                            "tool": tool_call.name,
                            "tool_args": tool_call.arguments,
                        },
                    )

                    if tool_call.name in TOOLS_REQUIRING_SESSION_ID:
                        tool_call.arguments["session_id"] = session_id

                    await _update_state_for_tool_start(session_id, tool_call.name)

                    if tool_call.name == "scan_folder":
                        await emit_event(
                            event_callback,
                            {
                                "type": SSEEventType.SCAN_STARTED.value,
                                "scan_id": "",
                                "root_path": tool_call.arguments.get("path", ""),
                                "scan_depth": tool_call.arguments.get("scan_depth", "DEEP"),
                            },
                        )

                    try:
                        result = await _call_tool(tool_call, http_client=http_client)
                    except Exception as exc:
                        error_detail = str(exc)
                        await update_task_state(
                            session_id=session_id,
                            current_step=SessionState.ERROR.value,
                            scratchpad_summary=error_detail,
                        )
                        await emit_event(
                            event_callback,
                            {
                                "type": SSEEventType.ERROR.value,
                                "message": f"Tool call failed: {tool_call.name}",
                                "detail": error_detail,
                            },
                        )
                        # Feed the error back to the model as a tool result so it
                        # can recover rather than crashing the entire loop.
                        result = {"error": "tool_call_failed", "message": error_detail}

                    log.info(
                        "agent_loop.tool_result",
                        extra={
                            "session_id": session_id,
                            "tool": tool_call.name,
                            "result_preview": _serialize_tool_result(result)[:200],
                        },
                    )

                    await emit_event(
                        event_callback,
                        {
                            "type": SSEEventType.TOOL_RESULT.value,
                            "tool": tool_call.name,
                            "result": result,
                        },
                    )

                    if tool_call.name == "propose_plan" and "plan_id" in result:
                        active_plan_id = result["plan_id"]
                        await emit_event(
                            event_callback,
                            {
                                "type": SSEEventType.PLAN_CREATED.value,
                                "plan_id": result["plan_id"],
                                "goal": tool_call.arguments.get("goal", ""),
                                "action_count": result.get("action_count", 0),
                            },
                        )

                    if tool_call.name == "scan_folder" and "scan_id" in result:
                        summary_json = result.get("summary_json") or {}
                        top_folders: list[str] = []
                        if isinstance(summary_json, dict):
                            top_folders = summary_json.get("top_folders") or []
                        # For ROOT depth, top_folders comes directly from the folders list
                        if not top_folders and result.get("scan_depth") == "ROOT":
                            top_folders = [
                                f.get("canonical_path", "")
                                for f in result.get("folders", [])[:10]
                            ]
                        # DEEP/CONTENT: top_folders from folder payloads sorted by file_count
                        if not top_folders and result.get("scan_depth") in ("DEEP", "CONTENT"):
                            top_folders = [
                                f.get("canonical_path", "")
                                for f in result.get("folders", [])[:10]
                            ]
                        # file_count: ROOT returns files[], DEEP/CONTENT returns file_count int
                        raw_files = result.get("files", [])
                        file_count = result.get("file_count", len(raw_files))
                        await emit_event(
                            event_callback,
                            {
                                "type": SSEEventType.SCAN_COMPLETE.value,
                                "scan_id": result.get("scan_id", ""),
                                "file_count": file_count,
                                "folder_count": result.get("folder_count", len(result.get("folders", []))),
                                "new_files": result.get("changes", {}).get("new_files", 0),
                                "deleted_files": result.get("changes", {}).get("deleted_files", 0),
                                "categories": result.get("categories", {}),
                                "root_path": tool_call.arguments.get("path", ""),
                                "scan_depth": result.get("scan_depth", "DEEP"),
                                "top_folders": top_folders,
                            },
                        )

                    await _persist_message(
                        session_id=session_id,
                        role=RoleType.TOOL,
                        content=_serialize_tool_result(result),
                        tool_name=tool_call.name,
                        tool_call_id=tool_call.id,
                    )
                    messages.append(_tool_result_message(tool_call, result))

                    log.info(
                        "agent_loop.context_after_tool",
                        extra={
                            "session_id": session_id,
                            "iteration": iteration,
                            "tool": tool_call.name,
                            "message_count": len(messages),
                            "estimated_tokens": _estimate_context_tokens(messages),
                        },
                    )

                    maybe_plan_id = await _update_state_for_tool_result(
                        session_id, tool_call.name, result, tool_args=tool_call.arguments
                    )
                    if maybe_plan_id:
                        active_plan_id = maybe_plan_id

                continue

            assistant_message_id = await _persist_message(
                session_id=session_id,
                role=RoleType.ASSISTANT,
                content=turn.content,
            )
            await emit_event(
                event_callback,
                {
                    "type": SSEEventType.MESSAGE_COMPLETE.value,
                    "message_id": assistant_message_id,
                    "content": turn.content,
                },
            )

            return AgentLoopResult(
                session_id=session_id,
                assistant_message_id=assistant_message_id,
                final_content=turn.content,
                iterations=iteration,
                tool_calls_executed=tool_calls_executed,
                active_plan_id=active_plan_id,
            )

    fallback_content = "I ran into an issue completing that task. Please try again."
    await update_task_state(
        session_id=session_id,
        current_step=SessionState.ERROR.value,
        scratchpad_summary="Maximum tool iterations exceeded.",
    )
    assistant_message_id = await _persist_message(
        session_id=session_id,
        role=RoleType.ASSISTANT,
        content=fallback_content,
    )
    await emit_event(
        event_callback,
        {
            "type": SSEEventType.ERROR.value,
            "message": "Maximum tool iterations exceeded",
            "detail": f"Agent stopped after {MAX_TOOL_ITERATIONS} iterations.",
        },
    )

    return AgentLoopResult(
        session_id=session_id,
        assistant_message_id=assistant_message_id,
        final_content=fallback_content,
        iterations=MAX_TOOL_ITERATIONS,
        tool_calls_executed=tool_calls_executed,
        active_plan_id=active_plan_id,
    )
