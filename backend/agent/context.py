from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import select

from config import settings
from db.connection import db_manager
from db.models import (
    MemoryEvent,
    OperationalPolicy,
    Plan,
    PlanAction,
    Scan,
    Session,
    SessionMessage,
    TaskState,
    UserPreference,
)

SYSTEM_PROMPT = f"""You are AIJAH, a local file assistant. Your job is to help the user organize their files safely.

The sandbox root path is: {settings.sandbox_root}
All file paths you use in tool calls must be absolute paths starting with {settings.sandbox_root}.

Rules you must always follow:
- Never perform file operations without a plan being proposed and approved first.
- Always call scan_folder first to discover the current state of files, then call propose_plan with the results.
- Never delete files. Use archive instead.
- Only operate within the sandbox root path ({settings.sandbox_root}).
- If you are unsure about a file's purpose, ask the user before including it in a plan.
- When you propose a plan, explain your reasoning clearly so the user can make an informed decision.

Rules about avoiding redundant or incorrect plans:
- Before calling propose_plan, review the "Recently executed actions" section below (if present).
  Do NOT propose moving or renaming a file that has already been successfully moved or renamed in this session.
- If a file's canonical path already indicates it is in an organized location (e.g. it contains a subfolder
  like "organized/"), verify whether it actually needs to move before including it in a plan.
- If the task state shows current_step = "AWAITING_APPROVAL", a plan is already pending.
  Do NOT call propose_plan again. Instead, tell the user a plan exists and ask if they want to proceed.
- Do not create CREATE_FOLDER actions for folders that already appear in the scan results.
- If scan_folder returns no files that need organizing, tell the user rather than generating an empty or
  trivially wrong plan."""


def _json_default(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return value.value
    return str(value)


def _format_policies(policies: list[OperationalPolicy]) -> str | None:
    if not policies:
        return None

    lines = ["Active operational policies:"]
    for policy in policies:
        lines.append(f"- [{policy.policy_type.value}] {policy.policy_name}: {policy.policy_text}")
    return "\n".join(lines)


def _format_preferences(preferences: list[UserPreference]) -> str | None:
    if not preferences:
        return None

    lines = ["Known user preferences:"]
    for preference in preferences:
        value_json = json.dumps(
            preference.preference_value_json,
            default=_json_default,
            ensure_ascii=True,
            sort_keys=True,
        )
        lines.append(
            f"- {preference.preference_key}: {value_json} "
            f"(source={preference.source.value}, confidence={preference.confidence})"
        )
    return "\n".join(lines)


def _format_task_state(task_state: TaskState | None) -> str | None:
    if task_state is None:
        return None

    payload = {
        "goal": task_state.goal,
        "current_step": task_state.current_step,
        "active_plan_id": str(task_state.active_plan_id) if task_state.active_plan_id else None,
        "active_entities_json": task_state.active_entities_json,
        "pending_action_ids_json": task_state.pending_action_ids_json,
        "scratchpad_summary": task_state.scratchpad_summary,
        "updated_at": task_state.updated_at.isoformat() if task_state.updated_at else None,
    }
    return (
        "Current task state:\n"
        f"{json.dumps(payload, default=_json_default, ensure_ascii=True, sort_keys=True, indent=2)}"
    )


def _format_recent_memory_events(events: list[MemoryEvent]) -> str | None:
    if not events:
        return None

    lines = ["Recently executed actions in this session (do not repeat these):"]
    for event in events:
        action_type = event.action_taken_json.get("action_type", "?") if event.action_taken_json else "?"
        outcome = event.outcome.value if event.outcome else "?"

        pre_path = None
        post_path = None
        if event.pre_state_json and isinstance(event.pre_state_json, dict):
            pre_path = event.pre_state_json.get("path")
        if event.post_state_json and isinstance(event.post_state_json, dict):
            post_path = event.post_state_json.get("path")

        if pre_path and post_path and pre_path != post_path:
            lines.append(f"- {action_type}: {pre_path} → {post_path} ({outcome})")
        elif pre_path:
            lines.append(f"- {action_type}: {pre_path} ({outcome})")
        else:
            change = json.dumps(event.intended_change_json, default=_json_default) if event.intended_change_json else "{}"
            lines.append(f"- {action_type}: {change} ({outcome})")

    return "\n".join(lines)


def _format_active_plan(plan: Plan, actions: list[PlanAction]) -> str | None:
    if plan is None:
        return None

    lines = [
        f"Active plan (status={plan.status.value}, id={plan.id}):",
        f"  Goal: {plan.goal}",
        f"  Rationale: {plan.rationale_summary}",
        f"  Actions ({len(actions)}):",
    ]
    for action in actions:
        payload = action.action_payload_json or {}
        from_path = payload.get("from_path", payload.get("path", "?"))
        to_path = payload.get("to_path")
        if to_path:
            lines.append(f"    [{action.status.value}] {action.action_type.value}: {from_path} → {to_path}")
        else:
            lines.append(f"    [{action.status.value}] {action.action_type.value}: {from_path}")

    return "\n".join(lines)


def _format_last_scan(scan: Scan | None) -> str | None:
    if scan is None:
        return None

    lines = [
        "Last scan:",
        f"  Scanned {scan.root_path} at {scan.started_at.isoformat() if scan.started_at else '?'}"
        f" (depth: {scan.scan_depth.value}, {'recursive' if scan.recursive else 'non-recursive'})",
        f"  Found: {scan.file_count or 0} files across {scan.folder_count or 0} folders",
        f"  Changes: {scan.new_files or 0} new, {scan.deleted_files or 0} deleted, {scan.modified_files or 0} modified",
    ]

    if scan.summary_json and isinstance(scan.summary_json, dict):
        categories = scan.summary_json.get("categories")
        if categories and isinstance(categories, dict):
            parts = [f"{cat} ({count})" for cat, count in categories.items()]
            lines.append(f"  Categories: {', '.join(parts)}")

    return "\n".join(lines)


def _session_message_to_dict(message: SessionMessage) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "role": message.role.value.lower(),
        "content": message.content,
    }

    if message.tool_name:
        payload["name"] = message.tool_name

    if message.tool_call_id:
        payload["tool_call_id"] = message.tool_call_id

    if message.metadata_json:
        raw_tcs = message.metadata_json.get("tool_calls")
        if raw_tcs:
            # Hoist tool_calls to top level in OpenAI function-call envelope format
            # so that AnthropicProvider._split_system_messages can find and convert them.
            # Stored format: {"id": "...", "name": "...", "arguments": {...}}
            # Expected format: {"id": "...", "type": "function", "function": {"name": "...", "arguments": {...}}}
            payload["tool_calls"] = [
                {
                    "id": tc.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": tc.get("name", ""),
                        "arguments": tc.get("arguments", {}),
                    },
                }
                for tc in raw_tcs
            ]
        else:
            payload["metadata"] = message.metadata_json

    return payload


@dataclass(slots=True)
class ContextPacket:
    session_id: str
    user_id: str
    device_id: str | None
    system_prompt: str
    policies_text: str | None = None
    preferences_text: str | None = None
    task_state_text: str | None = None
    recent_memories_text: str | None = None
    active_plan_text: str | None = None
    last_scan_text: str | None = None
    conversation_messages: list[dict[str, Any]] = field(default_factory=list)

    def to_messages(self) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": self.system_prompt}]

        if self.policies_text:
            messages.append({"role": "system", "content": self.policies_text})

        if self.preferences_text:
            messages.append({"role": "system", "content": self.preferences_text})

        if self.task_state_text:
            messages.append({"role": "system", "content": self.task_state_text})

        if self.recent_memories_text:
            messages.append({"role": "system", "content": self.recent_memories_text})

        if self.active_plan_text:
            messages.append({"role": "system", "content": self.active_plan_text})

        if self.last_scan_text:
            messages.append({"role": "system", "content": self.last_scan_text})

        messages.extend(self.conversation_messages)
        return messages

    def debug_summary(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "device_id": self.device_id,
            "message_count": len(self.conversation_messages),
            "has_policies": self.policies_text is not None,
            "has_preferences": self.preferences_text is not None,
            "has_task_state": self.task_state_text is not None,
            "has_recent_memories": self.recent_memories_text is not None,
            "has_active_plan": self.active_plan_text is not None,
            "has_last_scan": self.last_scan_text is not None,
        }


async def assemble_context(session_id: str) -> ContextPacket:
    session_uuid = uuid.UUID(session_id)

    async with db_manager.session() as session:
        session_row = await session.get(Session, session_uuid)
        if session_row is None:
            raise ValueError(f"Session not found: {session_id}")

        policies = list(
            await session.scalars(
                select(OperationalPolicy)
                .where(
                    OperationalPolicy.user_id == session_row.user_id,
                    OperationalPolicy.is_active.is_(True),
                )
                .order_by(OperationalPolicy.created_at.asc(), OperationalPolicy.id.asc())
            )
        )
        preferences = list(
            await session.scalars(
                select(UserPreference)
                .where(UserPreference.user_id == session_row.user_id)
                .order_by(UserPreference.created_at.asc(), UserPreference.id.asc())
            )
        )
        task_state = await session.scalar(
            select(TaskState).where(TaskState.session_id == session_uuid)
        )
        conversation_rows = list(
            await session.scalars(
                select(SessionMessage)
                .where(SessionMessage.session_id == session_uuid)
                .order_by(SessionMessage.created_at.asc(), SessionMessage.id.asc())
            )
        )

        # Recent memory events — last 10 for this session, most recent first
        recent_events = list(
            await session.scalars(
                select(MemoryEvent)
                .where(MemoryEvent.session_id == session_uuid)
                .order_by(MemoryEvent.created_at.desc())
                .limit(10)
            )
        )
        # Reverse so they read chronologically in the prompt
        recent_events = list(reversed(recent_events))

        # Active plan with actions (only if a plan is currently pending or partially executed)
        active_plan: Plan | None = None
        active_plan_actions: list[PlanAction] = []
        if task_state is not None and task_state.active_plan_id is not None:
            active_plan = await session.get(Plan, task_state.active_plan_id)
            if active_plan is not None:
                active_plan_actions = list(
                    await session.scalars(
                        select(PlanAction)
                        .where(PlanAction.plan_id == active_plan.id)
                        .order_by(PlanAction.created_at.asc())
                    )
                )

        last_scan: Scan | None = await session.scalar(
            select(Scan)
            .where(Scan.session_id == session_uuid)
            .order_by(Scan.started_at.desc())
            .limit(1)
        )

    return ContextPacket(
        session_id=str(session_row.id),
        user_id=str(session_row.user_id),
        device_id=str(session_row.device_id) if session_row.device_id else None,
        system_prompt=SYSTEM_PROMPT,
        policies_text=_format_policies(policies),
        preferences_text=_format_preferences(preferences),
        task_state_text=_format_task_state(task_state),
        recent_memories_text=_format_recent_memory_events(recent_events),
        active_plan_text=_format_active_plan(active_plan, active_plan_actions) if active_plan else None,
        last_scan_text=_format_last_scan(last_scan),
        conversation_messages=[_session_message_to_dict(message) for message in conversation_rows],
    )
