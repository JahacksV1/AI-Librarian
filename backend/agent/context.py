from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
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
- Only call propose_plan when the user is asking for (or agrees to) real changes such as organizing,
  moving, renaming, archiving, creating folders, or deduping. If the user's intent is unclear,
  ask clarifying questions first and do analysis-only responses.
- For analysis questions (what exists, biggest files, categories, likely duplicates), prefer
  query_indexed_files over propose_plan. Use specific filters and sorting so your answer is
  grounded in indexed facts.
- Retrieval-first decision policy:
  1) If the task state shows "Active analysis scope", the data for that path is already indexed
     in the database. Use query_indexed_files with path_prefix set to that path before considering
     a rescan. Use the scan_id from the scope as confirmation that the data is available.
  2) If indexed data is missing or clearly stale for the requested path, call scan_folder
     (ROOT first) then query_indexed_files.
  3) Only call propose_plan after the user clearly asks for changes.
- Always include concrete evidence from retrieval in your answer (counts, filenames, sizes,
  categories, or paths). Avoid vague summaries.
- For likely duplicates, use retrieval heuristics (name/size/path similarity) and label results as
  "potential duplicates" unless content hash evidence exists.
- After scanning a folder, do NOT automatically propose a plan. First, summarize what you found
  and ask what the user wants to do next (e.g., focus on a subfolder, identify duplicates, or
  propose an organization plan). Propose a plan only once the user confirms they want changes.
- Never delete files. Use archive instead.
- Only operate within the sandbox root path ({settings.sandbox_root}).
- If you are unsure about a file's purpose, ask the user before including it in a plan.
- When you propose a plan, explain your reasoning clearly so the user can make an informed decision.

Rules about scan depth — read carefully:
- When first exploring an unfamiliar path, ALWAYS start with scan_depth=ROOT (immediate children only).
  ROOT is instant and gives you the folder structure to orient yourself.
- If a path has already been scanned in this session (check "Active analysis scope" in task state,
  or "Last scan" context), prefer query_indexed_files first instead of rescanning.
- Query patterns to prefer:
  - "biggest PDFs" -> query_indexed_files(entity_type="file", extension="pdf", sort_by="size", sort_order="desc")
  - "category breakdown" -> query_indexed_files(..., include_counts=true)
  - "largest folders / folder list" -> query_indexed_files(entity_type="folder", path_prefix=...)
- After a ROOT scan, summarize what you found at that level and ask which subfolder to focus on next.
  Only propose a plan if the user wants to take action.
- Only go DEEP or CONTENT on a specific subfolder when the user explicitly asks.
- Never call scan_folder with scan_depth=DEEP or CONTENT on {settings.sandbox_root} itself — it contains
  hundreds of thousands of files and will time out. Always ROOT first.

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

CONVERSATION_WINDOW_MESSAGES = 20

# ---------------------------------------------------------------------------
# Tool-result compaction
# ---------------------------------------------------------------------------
# Raw tool output is always persisted to session_messages for the UI, audit,
# and debugging.  What the model sees in its message window is a compact,
# high-signal summary.  Re-fetchable details (full file/folder lists) are
# stripped; the model can call query_indexed_files to drill into specifics.

_MODEL_REPLAY_MAX_FILES = 20    # max file entries in a compacted scan result
_MODEL_REPLAY_MAX_FOLDERS = 25  # max folder entries in a compacted scan result


def compact_tool_result_for_model(tool_name: str, result: dict[str, Any]) -> dict[str, Any]:
    """Return a token-safe version of a tool result for the model's context window.

    The compacted version is used:
    - in the live agent loop (appended to the in-memory messages list)
    - when loading TOOL messages from the DB for context assembly

    This prevents large scan or retrieval payloads from consuming the context
    budget on every subsequent iteration or follow-up turn.
    """
    if result.get("error"):
        return result

    if tool_name == "scan_folder":
        # Build compact dict excluding the large raw lists
        compact: dict[str, Any] = {
            k: v for k, v in result.items()
            if k not in ("files", "file_sample", "folders")
        }

        # Bounded file sample (ROOT returns "files"; DEEP/CONTENT return "file_sample")
        files = result.get("files") or result.get("file_sample") or []
        if files:
            compact["file_sample"] = files[:_MODEL_REPLAY_MAX_FILES]
            if len(files) > _MODEL_REPLAY_MAX_FILES:
                compact["file_sample_note"] = (
                    f"Showing {_MODEL_REPLAY_MAX_FILES} of {len(files)} files. "
                    "Use query_indexed_files for more."
                )

        # Bounded folder summaries (name + size indicator only)
        folders = result.get("folders") or []
        if folders:
            compact["folder_summaries"] = [
                {
                    "canonical_path": f.get("canonical_path", ""),
                    "folder_name": f.get("folder_name", ""),
                    "child_count": f.get("child_count", f.get("file_count", 0)),
                }
                for f in folders[:_MODEL_REPLAY_MAX_FOLDERS]
            ]
            if len(folders) > _MODEL_REPLAY_MAX_FOLDERS:
                compact["folders_note"] = (
                    f"Showing {_MODEL_REPLAY_MAX_FOLDERS} of {len(folders)} folders. "
                    "Use query_indexed_files(entity_type='folder') for more."
                )

        return compact

    # All other tools (query_indexed_files is already result-bounded) pass through.
    return result


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

    # Exclude active_entities_json from the raw JSON block — the scope it contains
    # is formatted as a dedicated "Active analysis scope" section below for clarity.
    payload = {
        "goal": task_state.goal,
        "current_step": task_state.current_step,
        "active_plan_id": str(task_state.active_plan_id) if task_state.active_plan_id else None,
        "pending_action_ids_json": task_state.pending_action_ids_json,
        "scratchpad_summary": task_state.scratchpad_summary,
        "updated_at": task_state.updated_at.isoformat() if task_state.updated_at else None,
    }
    lines = [
        "Current task state:",
        json.dumps(payload, default=_json_default, ensure_ascii=True, sort_keys=True, indent=2),
    ]

    # Analysis scope — written by the agent loop after each scan_folder call.
    # This is persistent working memory: it tells the model which path is already
    # indexed in the DB so follow-up questions can use query_indexed_files instead
    # of rescanning.
    scope_data = (
        task_state.active_entities_json.get("scope")
        if isinstance(task_state.active_entities_json, dict)
        else None
    )
    if scope_data and isinstance(scope_data, dict):
        lines.append("")
        lines.append(
            "Active analysis scope (path already indexed — "
            "use query_indexed_files before rescanning):"
        )
        if scope_data.get("path"):
            lines.append(f"  path: {scope_data['path']}")
        if scope_data.get("depth"):
            lines.append(f"  scan_depth: {scope_data['depth']}")
        if scope_data.get("scan_id"):
            lines.append(f"  scan_id: {scope_data['scan_id']}")
        if scope_data.get("scanned_at"):
            lines.append(f"  scanned_at: {scope_data['scanned_at']}")
        fc = scope_data.get("file_count")
        fol = scope_data.get("folder_count")
        if fc is not None:
            lines.append(f"  indexed: {fc} files, {fol or 0} folders")
        cats = scope_data.get("categories")
        if cats and isinstance(cats, dict):
            cat_str = ", ".join(f"{k}({v})" for k, v in list(cats.items())[:8])
            lines.append(f"  categories: {cat_str}")

    return "\n".join(lines)


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


def _format_last_scan(scan: Scan | None, current_session_id: str | None = None) -> str | None:
    if scan is None:
        return None

    is_from_prior_session = (
        current_session_id is not None
        and str(scan.session_id) != current_session_id
    )
    label = "Last scan (prior session — device memory):" if is_from_prior_session else "Last scan:"

    lines = [
        label,
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

        top_folders = scan.summary_json.get("top_folders")
        if top_folders and isinstance(top_folders, list):
            folder_names = [Path(p).name for p in top_folders[:5]]
            lines.append(f"  Top folders: {', '.join(folder_names)}")

    return "\n".join(lines)


def _session_message_to_dict(message: SessionMessage) -> dict[str, Any]:
    # For TOOL messages, compact the persisted payload before putting it in the
    # model's context window.  The full raw content stays in the DB for the UI,
    # audit, and debugging; only the model sees the compacted version.
    content = message.content
    if message.role.value == "TOOL" and message.tool_name:
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                compact = compact_tool_result_for_model(message.tool_name, parsed)
                if compact is not parsed:
                    content = json.dumps(compact, ensure_ascii=True, sort_keys=True)
        except (json.JSONDecodeError, ValueError):
            pass  # If it can't be parsed, leave content as-is

    payload: dict[str, Any] = {
        "role": message.role.value.lower(),
        "content": content,
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


def _is_assistant_tool_call_message(message: SessionMessage) -> bool:
    if message.role.value != "ASSISTANT":
        return False
    if not message.metadata_json or not isinstance(message.metadata_json, dict):
        return False
    return bool(message.metadata_json.get("tool_calls"))


def _window_conversation_rows(rows: list[SessionMessage], window_size: int) -> list[SessionMessage]:
    """Return a recent conversation window while preserving tool-call continuity.

    We keep a bounded tail for normal chat continuity, but if the window starts
    inside tool-result rows we expand backward so provider adapters still see a
    coherent assistant tool-call message followed by tool results.
    """
    if window_size <= 0 or len(rows) <= window_size:
        return rows

    start = len(rows) - window_size

    # Never start in the middle of consecutive tool rows.
    while start > 0 and rows[start].role.value == "TOOL":
        start -= 1

    # If this slice begins right after an assistant tool-call envelope, include it.
    if start > 0 and _is_assistant_tool_call_message(rows[start - 1]):
        start -= 1

    return rows[start:]


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
        conversation_rows = _window_conversation_rows(
            conversation_rows,
            window_size=CONVERSATION_WINDOW_MESSAGES,
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

        # Try session-scoped first (most relevant — what happened in this conversation).
        # Fall back to device-scoped so a new session inherits knowledge from past scans.
        last_scan: Scan | None = await session.scalar(
            select(Scan)
            .where(Scan.session_id == session_uuid)
            .order_by(Scan.started_at.desc())
            .limit(1)
        )
        if last_scan is None and session_row.device_id is not None:
            last_scan = await session.scalar(
                select(Scan)
                .where(
                    Scan.device_id == session_row.device_id,
                    Scan.status == "COMPLETED",
                )
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
        last_scan_text=_format_last_scan(last_scan, current_session_id=str(session_row.id)),
        conversation_messages=[_session_message_to_dict(message) for message in conversation_rows],
    )
