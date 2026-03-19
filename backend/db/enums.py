"""
Single source of truth for all enums used across backend, DB, and API.

Values must match:
  - docs/TYPE_LEDGER.md  (the human contract)
  - db/migrations/001_create_enums.sql  (Postgres types)
  - Frontend string constants in app.js

Never use bare strings for enum values in business logic — always import from here.
"""

from enum import Enum


class PlanStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    PARTIAL = "PARTIAL"


class ActionStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ActionType(str, Enum):
    RENAME = "RENAME"
    MOVE = "MOVE"
    CREATE_FOLDER = "CREATE_FOLDER"
    ARCHIVE = "ARCHIVE"
    CLASSIFY = "CLASSIFY"


class OutcomeType(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class SessionMode(str, Enum):
    CHAT = "CHAT"
    CLEANUP = "CLEANUP"
    PLANNING = "PLANNING"
    # READ_ALOUD deferred to Phase 3


class SessionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SessionState(str, Enum):
    """UI-facing working state — stored as text in task_state.current_step (Phase 1)."""
    IDLE = "IDLE"
    SCANNING = "SCANNING"
    PLAN_READY = "PLAN_READY"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    COMPLETE = "COMPLETE"
    ERROR = "ERROR"


class EventType(str, Enum):
    SCAN = "SCAN"
    PLAN = "PLAN"
    RENAME = "RENAME"
    MOVE = "MOVE"
    ARCHIVE = "ARCHIVE"
    CLASSIFY = "CLASSIFY"
    FAILURE = "FAILURE"
    APPROVAL = "APPROVAL"
    REJECTION = "REJECTION"


class RoleType(str, Enum):
    SYSTEM = "SYSTEM"
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    TOOL = "TOOL"


class PolicyType(str, Enum):
    SAFETY = "SAFETY"
    NAMING = "NAMING"
    ARCHIVE = "ARCHIVE"
    LEGAL = "LEGAL"
    REVIEW = "REVIEW"


class DeviceType(str, Enum):
    WINDOWS_PC = "WINDOWS_PC"
    MAC = "MAC"
    LAPTOP = "LAPTOP"
    MAC_LAPTOP = "MAC_LAPTOP"
    VM = "VM"
    SERVER = "SERVER"


class SourceType(str, Enum):
    MODEL = "MODEL"
    USER = "USER"
    RULE = "RULE"
    TOOL = "TOOL"
    EXPLICIT_USER = "EXPLICIT_USER"
    INFERRED = "INFERRED"
    APPROVED = "APPROVED"


# --- Model provider types (Phase 1.5 — config only, not stored in DB) ---

class ModelProviderType(str, Enum):
    """Which LLM provider the backend uses for the agent loop."""
    OLLAMA = "OLLAMA"
    ANTHROPIC = "ANTHROPIC"
    OPENAI = "OPENAI"


# --- Phase 2 enums (defined here for reference, not used in Phase 1 DB) ---

class EntityType(str, Enum):
    CLIENT = "CLIENT"
    MATTER = "MATTER"
    DOCUMENT_TYPE = "DOCUMENT_TYPE"
    WORKFLOW = "WORKFLOW"
    FOLDER_PATTERN = "FOLDER_PATTERN"
    TAG = "TAG"


class LinkType(str, Enum):
    CLASSIFIED_AS = "CLASSIFIED_AS"
    BELONGS_TO_CLIENT = "BELONGS_TO_CLIENT"
    BELONGS_TO_MATTER = "BELONGS_TO_MATTER"
    RESEMBLES = "RESEMBLES"


class ObservationType(str, Enum):
    SCAN = "SCAN"
    READ = "READ"
    METADATA = "METADATA"
    CONTENT_EXTRACT = "CONTENT_EXTRACT"


# --- SSE event types (frontend wire format) ---

class SSEEventType(str, Enum):
    TOKEN = "token"
    MESSAGE_COMPLETE = "message_complete"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    PLAN_CREATED = "plan_created"
    ACTION_EXECUTED = "action_executed"
    EXECUTION_COMPLETE = "execution_complete"
    ERROR = "error"
