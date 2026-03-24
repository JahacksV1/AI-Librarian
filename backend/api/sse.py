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


def scan_started_event(scan_id: str, root_path: str, scan_depth: str) -> str:
    return _event(
        {
            "type": SSEEventType.SCAN_STARTED.value,
            "scan_id": scan_id,
            "root_path": root_path,
            "scan_depth": scan_depth,
        }
    )


def scan_complete_event(
    scan_id: str,
    file_count: int,
    folder_count: int,
    new_files: int,
    deleted_files: int,
    categories: dict[str, int],
) -> str:
    return _event(
        {
            "type": SSEEventType.SCAN_COMPLETE.value,
            "scan_id": scan_id,
            "file_count": file_count,
            "folder_count": folder_count,
            "new_files": new_files,
            "deleted_files": deleted_files,
            "categories": categories,
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
    if event_type == SSEEventType.SCAN_STARTED.value:
        return scan_started_event(
            scan_id=str(payload.get("scan_id", "")),
            root_path=str(payload.get("root_path", "")),
            scan_depth=str(payload.get("scan_depth", "")),
        )
    if event_type == SSEEventType.SCAN_COMPLETE.value:
        return scan_complete_event(
            scan_id=str(payload.get("scan_id", "")),
            file_count=int(payload.get("file_count", 0)),
            folder_count=int(payload.get("folder_count", 0)),
            new_files=int(payload.get("new_files", 0)),
            deleted_files=int(payload.get("deleted_files", 0)),
            categories=payload.get("categories", {}) or {},
        )
    if event_type == SSEEventType.ERROR.value:
        return error_event(
            message=str(payload.get("message", "Unknown error")),
            detail=str(payload.get("detail", "")),
        )

    return _event(payload)
