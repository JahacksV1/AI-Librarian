from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import select

from db.connection import db_manager
from db.models import OperationalPolicy, Session, SessionMessage, TaskState, UserPreference

SYSTEM_PROMPT = """You are AIJAH, a local file assistant. Your job is to help the user organize their files safely.

Rules you must always follow:
- Never perform file operations without a plan being proposed and approved first.
- Always call propose_plan before suggesting any rename, move, or archive action.
- Never delete files. Use archive instead.
- Only operate within the sandbox root path.
- If you are unsure about a file's purpose, ask the user before including it in a plan.
- When you propose a plan, explain your reasoning clearly so the user can make an informed decision."""


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


def _session_message_to_ollama(message: SessionMessage) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "role": message.role.value.lower(),
        "content": message.content,
    }

    if message.tool_name:
        payload["name"] = message.tool_name

    if message.metadata_json:
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
    conversation_messages: list[dict[str, Any]] = field(default_factory=list)

    def to_ollama_messages(self) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": self.system_prompt}]

        if self.policies_text:
            messages.append({"role": "system", "content": self.policies_text})

        if self.preferences_text:
            messages.append({"role": "system", "content": self.preferences_text})

        if self.task_state_text:
            messages.append({"role": "system", "content": self.task_state_text})

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

    return ContextPacket(
        session_id=str(session_row.id),
        user_id=str(session_row.user_id),
        device_id=str(session_row.device_id) if session_row.device_id else None,
        system_prompt=SYSTEM_PROMPT,
        policies_text=_format_policies(policies),
        preferences_text=_format_preferences(preferences),
        task_state_text=_format_task_state(task_state),
        conversation_messages=[_session_message_to_ollama(message) for message in conversation_rows],
    )
