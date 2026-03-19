# AIJAH Type & Enum Ledger

> Paste this document into context at the start of every Cursor session working on AIJAH.
> All type names, enum values, and payload shapes are defined here and nowhere else.
> Never use bare strings for enum values in business logic. Always reference this ledger.

---

## How to Use This Document

1. **Cursor sessions**: Paste this entire file into context when starting a new session
2. **Backend code**: All Python enums live in `backend/db/enums.py` — values must match this ledger exactly
3. **Frontend code**: All string constants must match the values defined here
4. **Database**: All Postgres enum types must match — defined in `001_create_enums.sql`
5. **API payloads**: When you send or receive JSON, the string values for typed fields must match

---

## Enums

### PlanStatus
Status of a plan in `plans.status`.

| Value | Meaning |
|---|---|
| `DRAFT` | Plan created by model, not yet surfaced to user |
| `PENDING` | Plan shown to user, awaiting approval/rejection decisions |
| `APPROVED` | All actions approved, ready for execution |
| `REJECTED` | User rejected the plan entirely |
| `EXECUTED` | All actions completed successfully |
| `PARTIAL` | Some actions succeeded, some failed or were rejected |

State machine:
```
DRAFT → PENDING → APPROVED → EXECUTED
                           → PARTIAL
              → REJECTED
```

---

### ActionStatus (used in plan_actions.status)
Status of a single action within a plan.

| Value | Meaning |
|---|---|
| `PENDING` | Awaiting user approval decision |
| `APPROVED` | User approved — executor will run this |
| `REJECTED` | User rejected — executor will skip this |
| `EXECUTED` | Executor completed this action successfully |
| `FAILED` | Executor attempted but the action failed |
| `SKIPPED` | Skipped due to plan-level rejection or dependency failure |

State machine:
```
PENDING → APPROVED → EXECUTED
                   → FAILED
        → REJECTED
        → SKIPPED
```

---

### ActionType
Type of file operation in `plan_actions.action_type`.

| Value | Meaning | Required payload fields |
|---|---|---|
| `RENAME` | Rename a file or folder in place | `from_path`, `to_path` |
| `MOVE` | Move a file or folder to a new parent | `from_path`, `to_path` |
| `CREATE_FOLDER` | Create a new directory | `path` |
| `ARCHIVE` | Move file to `.aijah_archive/` with timestamp | `from_path` |
| `CLASSIFY` | Tag or link a file to an entity (metadata only, no filesystem change) | `file_id`, `entity_id`, `link_type` |

---

### OutcomeType
Result of an executed action in `memory_events.outcome`.

| Value | Meaning |
|---|---|
| `SUCCESS` | Action completed exactly as intended |
| `FAILED` | Action attempted but threw an error |
| `PARTIAL` | Action partially completed (e.g. some files in a batch) |
| `REJECTED` | Action was rejected before execution |
| `CANCELLED` | Action was cancelled mid-execution |

---

### SessionMode
Mode of a session in `sessions.mode`.

**Phase 1 active values**: `CHAT`, `CLEANUP`, `PLANNING`  
**Phase 3 deferred**: `READ_ALOUD` — requires voice output (TTS). Do not implement in Phase 1 or 2.

| Value | Meaning | Phase |
|---|---|---|
| `CHAT` | General conversation, no specific task mode | 1 |
| `CLEANUP` | File reorganization / librarian mode | 1 |
| `PLANNING` | Structured planning mode | 1 |
| `READ_ALOUD` | Document reading mode — AIJAH reads files aloud via TTS | 3 |

---

### SessionStatus
Lifecycle status of a session in `sessions.status`.

| Value | Meaning |
|---|---|
| `ACTIVE` | Session is ongoing |
| `PAUSED` | Session paused by user |
| `COMPLETED` | Session ended successfully |
| `FAILED` | Session ended due to error |

---

### SessionState
Current working state of a session. Tracked in `task_state.current_step` (Phase 1 text field).
Promoted to a proper enum column `sessions.session_state` in Phase 2.

This is the UI-facing state: "what is AIJAH currently doing in this conversation?"

| Value | Meaning | What the UI shows |
|---|---|---|
| `IDLE` | No active task. Waiting for user input. | Chat input enabled |
| `SCANNING` | `scan_folder` tool is running. | "Scanning files..." spinner |
| `PLAN_READY` | Plan generated, not yet shown to user. | Transitional — brief |
| `AWAITING_APPROVAL` | Plan visible, waiting for approve/reject per action. | Approve / Reject buttons active |
| `EXECUTING` | Executor running approved actions. | Per-action progress indicator |
| `COMPLETE` | All approved actions finished successfully. | Success summary |
| `ERROR` | One or more actions failed or agent hit an error. | Error message, retry option |

State machine:
```
IDLE → SCANNING → PLAN_READY → AWAITING_APPROVAL → EXECUTING → COMPLETE
                                       │                  │
                                       ▼                  ▼
                                     IDLE              ERROR → IDLE
```

See `docs/STATE_MACHINE.md` for full transition table and guard rules.

---

### EventType
Type of memory event in `memory_events.event_type`.

| Value | Meaning |
|---|---|
| `SCAN` | Filesystem scan was performed |
| `PLAN` | A plan was generated |
| `RENAME` | A file or folder was renamed |
| `MOVE` | A file or folder was moved |
| `ARCHIVE` | A file was archived |
| `CLASSIFY` | A file was classified/tagged |
| `FAILURE` | An action failed |
| `APPROVAL` | A user approved an action or plan |
| `REJECTION` | A user rejected an action or plan |

---

### RoleType
Role of a message in `session_messages.role`.

| Value | Meaning |
|---|---|
| `SYSTEM` | System prompt injected at session start |
| `USER` | Message from the human user |
| `ASSISTANT` | Message from the AI model |
| `TOOL` | Tool result message (MCP tool output appended to context) |

---

### PolicyType
Category of an operational policy in `operational_policies.policy_type`.

| Value | Meaning |
|---|---|
| `SAFETY` | Hard safety rules (no delete, path restrictions) |
| `NAMING` | File/folder naming conventions |
| `ARCHIVE` | Rules about what to archive and how |
| `LEGAL` | Rules specific to legal matter files |
| `REVIEW` | Rules about what requires manual review |

---

### EntityType
Type of a domain entity in `entities.entity_type` **(Phase 2 — not in Phase 1 DB)**.

> These tables (`entities`, `entity_relationships`, `file_entity_links`) do not exist in Phase 1.
> `CLASSIFY` action type exists in Phase 1 but will not link to entities until Phase 2.

| Value | Meaning |
|---|---|
| `CLIENT` | A client the user works with |
| `MATTER` | A legal matter or project |
| `DOCUMENT_TYPE` | A category of document (invoice, contract, receipt) |
| `WORKFLOW` | A workflow or process |
| `FOLDER_PATTERN` | A recognized folder naming pattern |
| `TAG` | A general-purpose classification tag |

---

### LinkType
Type of relationship between a file and an entity in `file_entity_links.link_type` **(Phase 2)**.

| Value | Meaning |
|---|---|
| `CLASSIFIED_AS` | File is classified as this document type |
| `BELONGS_TO_CLIENT` | File belongs to this client |
| `BELONGS_TO_MATTER` | File belongs to this matter |
| `RESEMBLES` | File resembles/is similar to this entity |

---

### ObservationType
Type of observation recorded in `entity_observations.observation_type` **(Phase 2 — table does not exist in Phase 1)**.

| Value | Meaning |
|---|---|
| `SCAN` | Observed during a filesystem scan |
| `READ` | Observed by reading file content |
| `METADATA` | Observed from file metadata (size, modified date, etc.) |
| `CONTENT_EXTRACT` | Observed from extracted document content |

---

### DeviceType
Type of device in `devices.device_type`.

| Value | Meaning |
|---|---|
| `WINDOWS_PC` | Windows desktop |
| `MAC` | macOS desktop (iMac, Mac Mini, Mac Studio) |
| `LAPTOP` | Laptop — any OS (use when OS distinction doesn't matter) |
| `MAC_LAPTOP` | macOS laptop (MacBook Air, MacBook Pro) |
| `VM` | Virtual machine |
| `SERVER` | Server |

---

### SourceType
How a preference or relationship was established in `user_preferences.source` and `entity_relationships.source`.

| Value | Meaning |
|---|---|
| `MODEL` | Inferred by the AI model |
| `USER` | Explicitly stated by the user |
| `RULE` | Derived from an operational policy |
| `TOOL` | Set by a tool result |
| `EXPLICIT_USER` | Directly typed/confirmed by user (highest confidence) |
| `INFERRED` | Inferred from patterns without explicit confirmation |
| `APPROVED` | User approved a model-proposed value |

---

### ModelProviderType
Which LLM provider the backend uses for the agent loop. Used in config validation only (Phase 1.5). Not stored in the database.

| Value | Meaning |
|---|---|
| `OLLAMA` | Local model via Ollama runtime (default) |
| `ANTHROPIC` | Claude models via Anthropic API |
| `OPENAI` | GPT models via OpenAI API |

Defined in: `backend/db/enums.py`
Read from: `MODEL_PROVIDER` in `.env` / `config.py`

---

### EnvironmentType
Type of environment in `environment_actions.environment_type` **(Phase 3 — table and tools do not exist until Phase 3)**.

| Value | Meaning |
|---|---|
| `BROWSER` | A web browser tab |
| `FILESYSTEM` | The local file system |
| `APP` | A desktop application |

---

## State Machines (Visual)

### Plan Lifecycle
```
                    ┌─────────┐
                    │  DRAFT  │  (model writes plan to DB)
                    └────┬────┘
                         │ surfaced to user
                    ┌────▼────┐
                    │ PENDING │  (user sees approve/reject UI)
                    └────┬────┘
           ┌─────────────┼─────────────┐
      user │             │             │ user
    rejects│         user│approves     │ approves
     all   │          all│             │ some
           ▼             ▼             ▼
      ┌──────────┐  ┌──────────┐  ┌──────────┐
      │ REJECTED │  │ APPROVED │  │ APPROVED │
      └──────────┘  └────┬─────┘  └────┬─────┘
                         │              │
                    all succeed    mixed results
                         ▼              ▼
                    ┌──────────┐  ┌──────────┐
                    │ EXECUTED │  │ PARTIAL  │
                    └──────────┘  └──────────┘
```

### Action Lifecycle
```
┌─────────┐
│ PENDING │  (created with plan)
└────┬────┘
     ├──── user approves ──►  ┌──────────┐
     │                        │ APPROVED │
     │                        └────┬─────┘
     │                             ├── executor runs ──►  ┌──────────┐
     │                             │                      │ EXECUTED │
     │                             │                      └──────────┘
     │                             └── executor fails ──► ┌────────┐
     │                                                     │ FAILED │
     │                                                     └────────┘
     ├──── user rejects ──►  ┌──────────┐
     │                       │ REJECTED │
     │                       └──────────┘
     └──── plan rejected ──► ┌─────────┐
                             │ SKIPPED │
                             └─────────┘
```

---

## Database Tables Summary

One line per table. Phase 1 only.

| Table | Key Columns | Purpose |
|---|---|---|
| `users` | id, name, email, timezone | User accounts |
| `devices` | id, user_id, name, device_type, hostname | Registered devices |
| `sessions` | id, user_id, device_id, mode, status | Conversation sessions |
| `session_messages` | id, session_id, role, content, tool_name | All messages in a session |
| `task_state` | id, session_id, goal, current_step, active_plan_id | Working memory per session |
| `file_entities` | id, device_id, canonical_path, filename, exists_now | Known files on device |
| `folder_entities` | id, device_id, canonical_path, folder_name, parent_path | Known folders on device |
| `plans` | id, session_id, goal, status, plan_json | Generated plans |
| `plan_actions` | id, plan_id, action_type, status, action_payload_json | Individual actions within a plan |
| `memory_events` | id, session_id, event_type, pre_state_json, post_state_json, outcome | Audit log of every event |
| `user_preferences` | id, user_id, preference_key, preference_value_json, confidence | Learned or stated user preferences |
| `operational_policies` | id, user_id, policy_name, policy_type, policy_text, is_active | Safety and behavior rules |

---

## API Payload Shapes

These are the exact JSON shapes for API request and response bodies. Language-agnostic (TypeScript-style interfaces for readability).

### Session payloads

```typescript
// POST /sessions — request
interface CreateSessionRequest {
  user_id: string        // uuid
  mode: SessionMode      // "CHAT" | "CLEANUP" | "READ_ALOUD" | "PLANNING"
  title?: string
}

// POST /sessions — response (201)
interface SessionResponse {
  id: string
  user_id: string
  mode: SessionMode
  status: SessionStatus  // always "ACTIVE" on create
  title: string | null
  started_at: string     // ISO 8601
}

// PATCH /sessions/{session_id} — request
interface UpdateSessionRequest {
  status?: SessionStatus
  title?: string
}
```

### Message payloads

```typescript
// POST /sessions/{session_id}/messages — request
interface SendMessageRequest {
  content: string        // user's message text
}

// GET /sessions/{session_id}/messages — response
interface MessagesResponse {
  messages: MessageRecord[]
}

interface MessageRecord {
  id: string
  role: RoleType         // "USER" | "ASSISTANT" | "TOOL" | "SYSTEM"
  content: string
  tool_name: string | null
  tool_call_id: string | null
  metadata_json: object | null
  created_at: string
}
```

### Plan payloads

```typescript
// GET /plans/{plan_id} — response
interface PlanDetailResponse {
  id: string
  session_id: string
  goal: string
  plan_type: string
  status: PlanStatus
  rationale_summary: string | null
  plan_json: object
  actions: ActionRecord[]
  created_at: string
  updated_at: string
}

interface ActionRecord {
  id: string
  plan_id: string
  action_type: ActionType
  target_type: "file" | "folder"
  target_id: string | null
  action_payload_json: ActionPayload
  requires_approval: boolean
  status: ActionStatus
  result_json: object | null
  created_at: string
  updated_at: string
}
```

### Action payload shapes (action_payload_json)

```typescript
// RENAME
interface RenamePayload {
  from_path: string    // absolute path within SANDBOX_ROOT
  to_path: string      // absolute path within SANDBOX_ROOT
}

// MOVE
interface MovePayload {
  from_path: string
  to_path: string
}

// CREATE_FOLDER
interface CreateFolderPayload {
  path: string         // absolute path to create
}

// ARCHIVE
interface ArchivePayload {
  from_path: string
  archive_reason?: string
}

// CLASSIFY (metadata only, no filesystem change)
interface ClassifyPayload {
  file_id: string      // uuid in file_entities
  entity_id: string    // uuid in entities (Phase 2)
  link_type: LinkType
  confidence: number   // 0.0 to 1.0
}
```

### Approval payloads

```typescript
// PATCH /actions/{action_id} — request
interface UpdateActionRequest {
  status: "APPROVED" | "REJECTED"
}

// PATCH /actions/{action_id} — response
interface UpdateActionResponse {
  id: string
  status: ActionStatus
  updated_at: string
}

// POST /plans/{plan_id}/approve-all — response
interface ApproveAllResponse {
  approved_count: number
  plan_id: string
}
```

### Scan payloads

```typescript
// POST /scan — request
interface ScanRequest {
  path: string           // must be within SANDBOX_ROOT
  session_id: string
  recursive?: boolean    // default true
}

// POST /scan — response
interface ScanResponse {
  files_found: number
  folders_found: number
  session_id: string
  scan_completed_at: string
}
```

---

## MCP Tool Contracts

These are the exact tool signatures the agent discovers via `tools/list`. All tools are registered in `backend/mcp_server.py`.

### scan_folder
```typescript
// Input
{ path: string, recursive: boolean, session_id: string }

// Output
{
  files: Array<{ id: string, canonical_path: string, filename: string, extension: string, size_bytes: number, modified_at: string }>,
  folders: Array<{ id: string, canonical_path: string, folder_name: string, parent_path: string }>,
  summary: string   // e.g. "Scanned 42 files across 7 folders."
}
```

### read_file_metadata
```typescript
// Input
{ path: string }

// Output
{ id: string, canonical_path: string, filename: string, extension: string, size_bytes: number, modified_at: string, exists: boolean }
```

### propose_plan
```typescript
// Input
{
  session_id: string,
  goal: string,
  rationale_summary: string,
  actions: Array<{
    action_type: ActionType,    // "RENAME" | "MOVE" | "CREATE_FOLDER" | "ARCHIVE" | "CLASSIFY"
    target_type: "file" | "folder",
    target_path: string,
    action_payload: RenamePayload | MovePayload | CreateFolderPayload | ArchivePayload
  }>
}

// Output
{ plan_id: string, action_count: number, status: "PENDING" }
```

### execute_action
```typescript
// Input
{ action_id: string }   // UUID of plan_action with status = "APPROVED"

// Output (success)
{ action_id: string, outcome: "SUCCESS", pre_state: object, post_state: object, memory_event_id: string }

// Output (failure)
{ action_id: string, outcome: "FAILED", error: string }
```

### get_task_state
```typescript
// Input
{ session_id: string }

// Output
{ goal: string | null, current_step: string | null, active_plan_id: string | null, scratchpad_summary: string | null }
```

### update_task_state
```typescript
// Input
{ session_id: string, goal?: string, current_step?: string, active_plan_id?: string, scratchpad_summary?: string }

// Output
{ updated: true, updated_at: string }
```

---

## SSE Event Types

All SSE events arrive as `data: <json>\n\n`. Parse `type` first to determine the shape.

```typescript
type SSEEvent =
  | { type: "token";             token: string }
  | { type: "message_complete";  message_id: string; content: string }
  | { type: "tool_call";         tool: string; args: object }
  | { type: "tool_result";       tool: string; result: object }
  | { type: "plan_created";      plan_id: string; goal: string; action_count: number }
  | { type: "action_executed";   action_id: string; outcome: "SUCCESS" | "FAILED"; action_type: ActionType }
  | { type: "execution_complete"; plan_id: string; succeeded: number; failed: number }
  | { type: "error";             message: string; detail: string }
```

---

## File & Folder Naming Conventions

| Item | Convention | Example |
|---|---|---|
| Python modules | `snake_case.py` | `agent.py`, `context_assembler.py`, `mcp_server.py` |
| Python classes | `PascalCase` | `AgentLoop`, `ContextAssembler` |
| Python functions | `snake_case` | `assemble_context()`, `run_agent_loop()` |
| DB migration files | `NNN_description.sql` | `001_create_enums.sql`, `002_create_tables.sql` |
| DB table names | `snake_case`, plural | `plan_actions`, `memory_events`, `session_messages` |
| DB column names | `snake_case` | `canonical_path`, `action_payload_json` |
| Postgres enum type names | `snake_case` + `_enum` suffix | `plan_status_enum`, `action_type_enum` |
| Environment variables | `SCREAMING_SNAKE_CASE` | `DATABASE_URL`, `OLLAMA_URL`, `SANDBOX_ROOT` |
| API route paths | `kebab-case` | `/session-messages`, `/plan-actions` |
| Docker service names | `kebab-case` | `mcp-server`, `backend` |

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://aijah:aijah@postgres:5432/aijah` | PostgreSQL connection string |
| `OLLAMA_URL` | `http://ollama:11434` | Ollama API base URL |
| `OLLAMA_MODEL` | `qwen2.5` | Model name to use for tool-calling |
| `SANDBOX_ROOT` | `/sandbox` | Absolute root path; all file operations restricted to this |
| `MCP_MOUNT_PATH` | `/mcp` | Path where FastMCP is mounted inside FastAPI |
| `LOG_LEVEL` | `INFO` | Python logging level |

---

## Quick Reference Card

```
PlanStatus:     DRAFT | PENDING | APPROVED | REJECTED | EXECUTED | PARTIAL
ActionStatus:   PENDING | APPROVED | REJECTED | EXECUTED | FAILED | SKIPPED
ActionType:     RENAME | MOVE | CREATE_FOLDER | ARCHIVE | CLASSIFY
OutcomeType:    SUCCESS | FAILED | PARTIAL | REJECTED | CANCELLED
SessionMode:    CHAT | CLEANUP | PLANNING | READ_ALOUD(P3)
SessionStatus:  ACTIVE | PAUSED | COMPLETED | FAILED
SessionState:   IDLE | SCANNING | PLAN_READY | AWAITING_APPROVAL | EXECUTING | COMPLETE | ERROR
EventType:      SCAN | PLAN | RENAME | MOVE | ARCHIVE | CLASSIFY | FAILURE | APPROVAL | REJECTION
RoleType:       SYSTEM | USER | ASSISTANT | TOOL
PolicyType:     SAFETY | NAMING | ARCHIVE | LEGAL | REVIEW
EntityType:     CLIENT | MATTER | DOCUMENT_TYPE | WORKFLOW | FOLDER_PATTERN | TAG  [Phase 2]
LinkType:       CLASSIFIED_AS | BELONGS_TO_CLIENT | BELONGS_TO_MATTER | RESEMBLES  [Phase 2]
SourceType:     MODEL | USER | RULE | TOOL | EXPLICIT_USER | INFERRED | APPROVED
DeviceType:     WINDOWS_PC | MAC | LAPTOP | MAC_LAPTOP | VM | SERVER
EnvironmentType: BROWSER | FILESYSTEM | APP  [Phase 3]
```

---

## Foundation Document Map

| Document | What it answers |
|---|---|
| `docs/TYPE_LEDGER.md` (this file) | What are all the types, enums, and payload shapes? |
| `docs/STATE_MACHINE.md` | What states exist? What transitions are allowed? What are the guards? |
| `docs/AGENT_LOOP.md` | How does the agent loop work? How is context assembled? What gets logged? |
| `docs/V1_CONTRACT.md` | What must exist for Phase 1 to be done? What is deferred? |
| `docs/VISION.md` | Where is this going long-term? Why is the architecture built this way? |
| `docs/PHASE_MAP.md` | What gets built in what order? Who owns what? What runs in parallel? |
