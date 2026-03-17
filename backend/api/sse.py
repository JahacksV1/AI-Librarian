from __future__ import annotations

import json
from typing import Any

from db.enums import SSEEventType


def _event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=True)}\n\n"


def token_event(token: str) -> str:
    return _event({"type": SSEEventType.TOKEN.value, "token": token})


def message_complete_event(message_id: str, content: str) -> str:
    return _event(
        {
            "type": SSEEventType.MESSAGE_COMPLETE.value,
            "message_id": message_id,
            "content": content,
        }
    )


def tool_call_event(tool: str, args: dict[str, Any]) -> str:
    return _event({"type": SSEEventType.TOOL_CALL.value, "tool": tool, "args": args})


def tool_result_event(tool: str, result: dict[str, Any]) -> str:
    return _event({"type": SSEEventType.TOOL_RESULT.value, "tool": tool, "result": result})


def plan_created_event(plan_id: str, goal: str, action_count: int) -> str:
    return _event(
        {
            "type": SSEEventType.PLAN_CREATED.value,
            "plan_id": plan_id,
            "goal": goal,
            "action_count": action_count,
        }
    )


def action_executed_event(action_id: str, outcome: str, action_type: str) -> str:
    return _event(
        {
            "type": SSEEventType.ACTION_EXECUTED.value,
            "action_id": action_id,
            "outcome": outcome,
            "action_type": action_type,
        }
    )


def execution_complete_event(plan_id: str, succeeded: int, failed: int) -> str:
    return _event(
        {
            "type": SSEEventType.EXECUTION_COMPLETE.value,
            "plan_id": plan_id,
            "succeeded": succeeded,
            "failed": failed,
        }
    )


def error_event(message: str, detail: str) -> str:
    return _event(
        {
            "type": SSEEventType.ERROR.value,
            "message": message,
            "detail": detail,
        }
    )


def from_payload(payload: dict[str, Any]) -> str:
    event_type = payload.get("type")

    if event_type == SSEEventType.TOKEN.value:
        return token_event(token=str(payload.get("token", "")))
    if event_type == SSEEventType.MESSAGE_COMPLETE.value:
        return message_complete_event(
            message_id=str(payload.get("message_id", "")),
            content=str(payload.get("content", "")),
        )
    if event_type == SSEEventType.TOOL_CALL.value:
        return tool_call_event(
            tool=str(payload.get("tool", "")),
            args=payload.get("args", {}) or {},
        )
    if event_type == SSEEventType.TOOL_RESULT.value:
        return tool_result_event(
            tool=str(payload.get("tool", "")),
            result=payload.get("result", {}) or {},
        )
    if event_type == SSEEventType.PLAN_CREATED.value:
        return plan_created_event(
            plan_id=str(payload.get("plan_id", "")),
            goal=str(payload.get("goal", "")),
            action_count=int(payload.get("action_count", 0)),
        )
    if event_type == SSEEventType.ACTION_EXECUTED.value:
        return action_executed_event(
            action_id=str(payload.get("action_id", "")),
            outcome=str(payload.get("outcome", "")),
            action_type=str(payload.get("action_type", "")),
        )
    if event_type == SSEEventType.EXECUTION_COMPLETE.value:
        return execution_complete_event(
            plan_id=str(payload.get("plan_id", "")),
            succeeded=int(payload.get("succeeded", 0)),
            failed=int(payload.get("failed", 0)),
        )
    if event_type == SSEEventType.ERROR.value:
        return error_event(
            message=str(payload.get("message", "Unknown error")),
            detail=str(payload.get("detail", "")),
        )

    return _event(payload)
