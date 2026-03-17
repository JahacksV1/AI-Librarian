# AIJAH V1 Implementation Contract

> This document is locked. Only what is listed here must exist for Phase 1 to be considered done.
> Nothing else is in scope. Defer everything else to Phase 2.

---

## V1 Definition of Done (9 Steps)

Phase 1 is complete when all 9 of these work end-to-end:

1. Docker Compose stack boots with zero errors
2. Backend receives a message and calls Ollama successfully (tool-calling round-trip works)
3. Backend discovers MCP tools via `tools/list` and injects schemas into the prompt
4. `scan_folder` MCP tool runs on the sandbox folder and returns file/folder metadata
5. Agent generates a plan with at least one RENAME or MOVE action
6. Browser UI shows the plan with Approve / Reject buttons per action
7. User clicks Approve → action status updates to APPROVED in DB
8. Executor reads APPROVED actions and performs the file operation safely
9. `memory_events` row written with pre-state and post-state after execution

---

## Services

| Service | Port | Image / Runtime | Responsibility |
|---|---|---|---|
| `frontend` | 3000 | Static files (nginx or Python http.server) | HTML/JS UI, SSE consumer, approve/reject buttons |
| `backend` | 8000 | Python 3.11 + FastAPI + FastMCP | API, agent loop, MCP server at `/mcp`, DB writes |
| `postgres` | 5432 | postgres:16 | All structured state |
| `ollama` | 11434 | ollama/ollama | Local LLM runtime |

> Note: There is no separate `mcp-server` container in Phase 1. FastMCP is mounted inside the FastAPI process at `/mcp` via Streamable HTTP. It becomes its own service in Phase 2.

### docker-compose.yml outline

```yaml
services:
  frontend:
    build: ./frontend
    ports: ["3000:3000"]

  backend:
    build: ./backend
    ports: ["8000:8000"]
    environment:
      DATABASE_URL: postgresql://aijah:aijah@postgres:5432/aijah
      OLLAMA_URL: http://ollama:11434
      SANDBOX_ROOT: /sandbox
    volumes:
      - ./sandbox:/sandbox
    depends_on: [postgres, ollama]

  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: aijah
      POSTGRES_PASSWORD: aijah
      POSTGRES_DB: aijah
    ports: ["5432:5432"]
    volumes:
      - pgdata:/var/lib/postgresql/data

  ollama:
    image: ollama/ollama
    ports: ["11434:11434"]
    volumes:
      - ollama_data:/root/.ollama

volumes:
  pgdata:
  ollama_data:
```

---

## Phase 1 Database Tables

Exactly 13 tables. No embeddings tables. No ontology tables. No `entity_observations`.

### users
```sql
id            UUID PRIMARY KEY DEFAULT gen_random_uuid()
name          TEXT NOT NULL
email         TEXT UNIQUE NOT NULL
timezone      TEXT DEFAULT 'UTC'
created_at    TIMESTAMPTZ DEFAULT now()
updated_at    TIMESTAMPTZ DEFAULT now()
```

### devices
```sql
id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
user_id               UUID NOT NULL REFERENCES users(id)
name                  TEXT NOT NULL
device_type           device_type_enum NOT NULL
hostname              TEXT
os                    TEXT
local_agent_version   TEXT
created_at            TIMESTAMPTZ DEFAULT now()
updated_at            TIMESTAMPTZ DEFAULT now()
```

### sessions
```sql
id            UUID PRIMARY KEY DEFAULT gen_random_uuid()
user_id       UUID NOT NULL REFERENCES users(id)
device_id     UUID REFERENCES devices(id)
title         TEXT
mode          session_mode_enum NOT NULL DEFAULT 'CHAT'
status        session_status_enum NOT NULL DEFAULT 'ACTIVE'
started_at    TIMESTAMPTZ DEFAULT now()
ended_at      TIMESTAMPTZ
summary       TEXT
created_at    TIMESTAMPTZ DEFAULT now()
updated_at    TIMESTAMPTZ DEFAULT now()
```

### session_messages
```sql
id            UUID PRIMARY KEY DEFAULT gen_random_uuid()
session_id    UUID NOT NULL REFERENCES sessions(id)
role          role_type_enum NOT NULL
content       TEXT NOT NULL
tool_name     TEXT
tool_call_id  TEXT
metadata_json JSONB
created_at    TIMESTAMPTZ DEFAULT now()
```

### task_state
```sql
id                      UUID PRIMARY KEY DEFAULT gen_random_uuid()
session_id              UUID NOT NULL REFERENCES sessions(id) UNIQUE
goal                    TEXT
current_step            TEXT
active_plan_id          UUID REFERENCES plans(id)
active_entities_json    JSONB
pending_action_ids_json JSONB
scratchpad_summary      TEXT
updated_at              TIMESTAMPTZ DEFAULT now()
```

> Do NOT duplicate full plan_json here. Only store the reference (active_plan_id).

### file_entities
```sql
id              UUID PRIMARY KEY DEFAULT gen_random_uuid()
device_id       UUID NOT NULL REFERENCES devices(id)
canonical_path  TEXT NOT NULL
filename        TEXT NOT NULL
extension       TEXT
mime_type       TEXT
size_bytes      BIGINT
content_hash    TEXT
modified_at     TIMESTAMPTZ
created_at_fs   TIMESTAMPTZ
first_seen_at   TIMESTAMPTZ DEFAULT now()
last_seen_at    TIMESTAMPTZ DEFAULT now()
exists_now      BOOLEAN DEFAULT true
metadata_json   JSONB
UNIQUE (device_id, canonical_path)
```

### folder_entities
```sql
id              UUID PRIMARY KEY DEFAULT gen_random_uuid()
device_id       UUID NOT NULL REFERENCES devices(id)
canonical_path  TEXT NOT NULL
folder_name     TEXT NOT NULL
parent_path     TEXT
first_seen_at   TIMESTAMPTZ DEFAULT now()
last_seen_at    TIMESTAMPTZ DEFAULT now()
exists_now      BOOLEAN DEFAULT true
metadata_json   JSONB
UNIQUE (device_id, canonical_path)
```

### plans
```sql
id                UUID PRIMARY KEY DEFAULT gen_random_uuid()
session_id        UUID NOT NULL REFERENCES sessions(id)
plan_type         TEXT NOT NULL DEFAULT 'FILE_REORGANIZATION'
goal              TEXT NOT NULL
plan_json         JSONB NOT NULL
rationale_summary TEXT
status            plan_status_enum NOT NULL DEFAULT 'DRAFT'
created_at        TIMESTAMPTZ DEFAULT now()
updated_at        TIMESTAMPTZ DEFAULT now()
```

### plan_actions
```sql
id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
plan_id               UUID NOT NULL REFERENCES plans(id)
action_type           action_type_enum NOT NULL
target_type           TEXT NOT NULL   -- 'file' or 'folder'
target_id             UUID            -- references file_entities or folder_entities
action_payload_json   JSONB NOT NULL
requires_approval     BOOLEAN NOT NULL DEFAULT true
status                action_status_enum NOT NULL DEFAULT 'PENDING'
result_json           JSONB
created_at            TIMESTAMPTZ DEFAULT now()
updated_at            TIMESTAMPTZ DEFAULT now()
```

### memory_events
```sql
id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
user_id               UUID NOT NULL REFERENCES users(id)
device_id             UUID REFERENCES devices(id)
session_id            UUID REFERENCES sessions(id)
event_type            event_type_enum NOT NULL
scope_type            TEXT             -- 'file', 'folder', 'session', 'plan'
scope_id              UUID
pre_state_json        JSONB
intended_change_json  JSONB
action_taken_json     JSONB
post_state_json       JSONB
outcome               outcome_type_enum
confidence            NUMERIC(4,3)     -- 0.000 to 1.000
notes                 TEXT
created_at            TIMESTAMPTZ DEFAULT now()
```

### user_preferences
```sql
id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
user_id               UUID NOT NULL REFERENCES users(id)
preference_key        TEXT NOT NULL
preference_value_json JSONB NOT NULL
confidence            NUMERIC(4,3) DEFAULT 1.000
source                source_type_enum NOT NULL
created_at            TIMESTAMPTZ DEFAULT now()
updated_at            TIMESTAMPTZ DEFAULT now()
UNIQUE (user_id, preference_key)
```

### operational_policies
```sql
id            UUID PRIMARY KEY DEFAULT gen_random_uuid()
user_id       UUID NOT NULL REFERENCES users(id)
policy_name   TEXT NOT NULL
policy_type   policy_type_enum NOT NULL
policy_text   TEXT NOT NULL
policy_json   JSONB
is_active     BOOLEAN NOT NULL DEFAULT true
created_at    TIMESTAMPTZ DEFAULT now()
updated_at    TIMESTAMPTZ DEFAULT now()
```

---

## API Routes

Base URL: `http://localhost:8000`

All request/response bodies are JSON. All timestamps are ISO 8601.

### Sessions

#### POST /sessions
Create a new session.
```json
// Request
{ "user_id": "uuid", "mode": "CHAT", "title": "optional title" }

// Response 201
{ "id": "uuid", "user_id": "uuid", "mode": "CHAT", "status": "ACTIVE", "started_at": "..." }
```

#### GET /sessions/{session_id}
```json
// Response 200
{ "id": "uuid", "user_id": "uuid", "mode": "CHAT", "status": "ACTIVE", "title": "...", "started_at": "...", "ended_at": null }
```

#### PATCH /sessions/{session_id}
Update session status or title.
```json
// Request
{ "status": "COMPLETED", "title": "Organize Invoices - March" }

// Response 200
{ "id": "uuid", "status": "COMPLETED", "updated_at": "..." }
```

### Messages

#### POST /sessions/{session_id}/messages
Send a user message. Triggers the agent loop. Returns SSE stream.
```
Content-Type: text/event-stream

// Request body
{ "content": "Can you scan my invoices folder and suggest how to organize it?" }

// SSE events (see SSE Events section)
```

#### GET /sessions/{session_id}/messages
```json
// Response 200
{
  "messages": [
    { "id": "uuid", "role": "USER", "content": "...", "created_at": "..." },
    { "id": "uuid", "role": "ASSISTANT", "content": "...", "tool_name": null, "created_at": "..." }
  ]
}
```

### Plans

#### GET /sessions/{session_id}/plans
```json
// Response 200
{
  "plans": [
    {
      "id": "uuid",
      "goal": "Organize invoices folder by year and client",
      "status": "PENDING",
      "rationale_summary": "...",
      "created_at": "..."
    }
  ]
}
```

#### GET /plans/{plan_id}
```json
// Response 200
{
  "id": "uuid",
  "session_id": "uuid",
  "goal": "...",
  "status": "PENDING",
  "rationale_summary": "...",
  "plan_json": { ... },
  "actions": [
    {
      "id": "uuid",
      "action_type": "RENAME",
      "target_type": "file",
      "action_payload_json": {
        "from_path": "/sandbox/invoices/inv001.pdf",
        "to_path": "/sandbox/invoices/2024/ClientA/2024-01_invoice_ClientA.pdf"
      },
      "status": "PENDING",
      "requires_approval": true
    }
  ]
}
```

### Actions (Approval Flow)

#### PATCH /actions/{action_id}
Approve or reject a single action.
```json
// Request
{ "status": "APPROVED" }
// or
{ "status": "REJECTED" }

// Response 200
{ "id": "uuid", "status": "APPROVED", "updated_at": "..." }
```

#### POST /plans/{plan_id}/approve-all
Approve all PENDING actions in a plan at once.
```json
// Response 200
{ "approved_count": 5, "plan_id": "uuid" }
```

#### POST /plans/{plan_id}/execute
Execute all APPROVED actions in the plan. Returns SSE stream of execution events.
```
Content-Type: text/event-stream
```

### File System

#### POST /scan
Trigger a folder scan. Updates `file_entities` and `folder_entities`.
```json
// Request
{ "path": "/sandbox/invoices", "session_id": "uuid", "recursive": true }

// Response 200
{
  "files_found": 42,
  "folders_found": 7,
  "session_id": "uuid",
  "scan_completed_at": "..."
}
```

#### GET /files
List known file entities for a device.
```json
// Query params: device_id, path_prefix, exists_now=true
// Response 200
{
  "files": [
    {
      "id": "uuid",
      "canonical_path": "/sandbox/invoices/inv001.pdf",
      "filename": "inv001.pdf",
      "extension": "pdf",
      "size_bytes": 48200,
      "exists_now": true
    }
  ]
}
```

### Health

#### GET /health
```json
// Response 200
{ "status": "ok", "ollama": "reachable", "db": "connected" }
```

---

## MCP Tool Contracts

The agent loop discovers these via `tools/list` at startup. All tools are registered in `mcp_server.py` and mounted at `/mcp`.

### scan_folder
Scan a directory and return file/folder metadata. Writes to DB.
```json
// Input
{
  "path": { "type": "string", "description": "Absolute path within SANDBOX_ROOT" },
  "recursive": { "type": "boolean", "default": true },
  "session_id": { "type": "string", "description": "UUID of current session" }
}

// Output
{
  "files": [
    {
      "id": "uuid",
      "canonical_path": "string",
      "filename": "string",
      "extension": "string",
      "size_bytes": 0,
      "modified_at": "iso8601"
    }
  ],
  "folders": [
    { "id": "uuid", "canonical_path": "string", "folder_name": "string", "parent_path": "string" }
  ],
  "summary": "Scanned 42 files across 7 folders."
}
```

### read_file_metadata
Read metadata for a single file (no content read in Phase 1).
```json
// Input
{
  "path": { "type": "string" }
}

// Output
{
  "id": "uuid",
  "canonical_path": "string",
  "filename": "string",
  "extension": "string",
  "size_bytes": 0,
  "modified_at": "iso8601",
  "exists": true
}
```

### propose_plan
Write a plan and its actions to the DB. Returns the created plan ID.
```json
// Input
{
  "session_id": { "type": "string" },
  "goal": { "type": "string" },
  "rationale_summary": { "type": "string" },
  "actions": {
    "type": "array",
    "items": {
      "action_type": "RENAME | MOVE | CREATE_FOLDER | ARCHIVE | CLASSIFY",
      "target_type": "file | folder",
      "target_path": "string",
      "action_payload": {}
    }
  }
}

// Output
{
  "plan_id": "uuid",
  "action_count": 5,
  "status": "PENDING"
}
```

### execute_action
Execute a single APPROVED action. Validates status = APPROVED before touching filesystem.
```json
// Input
{
  "action_id": { "type": "string", "description": "UUID of plan_action with status APPROVED" }
}

// Output (success)
{
  "action_id": "uuid",
  "outcome": "SUCCESS",
  "pre_state": { "path": "string" },
  "post_state": { "path": "string" },
  "memory_event_id": "uuid"
}

// Output (error)
{
  "action_id": "uuid",
  "outcome": "FAILED",
  "error": "string"
}
```

### get_task_state
Read current working memory for a session.
```json
// Input
{ "session_id": { "type": "string" } }

// Output
{
  "goal": "string",
  "current_step": "string",
  "active_plan_id": "uuid | null",
  "scratchpad_summary": "string | null"
}
```

### update_task_state
Write to working memory for a session.
```json
// Input
{
  "session_id": { "type": "string" },
  "goal": { "type": "string", "optional": true },
  "current_step": { "type": "string", "optional": true },
  "active_plan_id": { "type": "string", "optional": true },
  "scratchpad_summary": { "type": "string", "optional": true }
}

// Output
{ "updated": true, "updated_at": "iso8601" }
```

---

## SSE Event Types

All SSE events are JSON lines prefixed with `data: `.

```
data: {"type": "EVENT_TYPE", ...payload}
```

| Event Type | When | Payload Fields |
|---|---|---|
| `token` | Each token streamed from Ollama | `{ "token": "string" }` |
| `message_complete` | Full assistant message written to DB | `{ "message_id": "uuid", "content": "string" }` |
| `tool_call` | Agent is calling an MCP tool | `{ "tool": "string", "args": {} }` |
| `tool_result` | MCP tool returned | `{ "tool": "string", "result": {} }` |
| `plan_created` | `propose_plan` tool wrote a plan to DB | `{ "plan_id": "uuid", "goal": "string", "action_count": 0 }` |
| `action_executed` | `execute_action` completed | `{ "action_id": "uuid", "outcome": "SUCCESS|FAILED", "action_type": "string" }` |
| `execution_complete` | All actions in a plan have been processed | `{ "plan_id": "uuid", "succeeded": 0, "failed": 0 }` |
| `error` | Any unhandled error in the agent loop | `{ "message": "string", "detail": "string" }` |

---

## File / Folder Naming Conventions

| Item | Convention | Example |
|---|---|---|
| Python modules | `snake_case.py` | `agent.py`, `context_assembler.py` |
| DB migration files | `NNN_description.sql` | `001_create_enums.sql`, `002_create_core_tables.sql` |
| Environment variables | `SCREAMING_SNAKE_CASE` | `DATABASE_URL`, `OLLAMA_URL`, `SANDBOX_ROOT` |
| API routes | `kebab-case` | `/plan-actions`, `/session-messages` |
| Table names | `snake_case` (plural) | `plan_actions`, `memory_events` |
| Enum type names in Postgres | `snake_case` with `_enum` suffix | `plan_status_enum`, `action_type_enum` |
| Docker service names | `kebab-case` | `mcp-server`, `backend` |

---

## What Is Explicitly Deferred to Phase 2

Do not implement any of these in Phase 1. If it's not in this document, it doesn't exist yet.

- `pgvector` extension and all `*_embeddings` tables
- `document_extracts` table
- `entities`, `entity_relationships`, `file_entity_links` tables
- `entity_observations` table
- Full context packet assembler (vector retrieval at prompt time)
- Voice input / output
- Document reading / OCR / PDF parsing
- Browser / computer control
- `environment_actions` table
- Reward system / learning loop
- Staged ontology proposals
- Separate `mcp-server` Docker service
- Embedding model (`nomic-embed-text`) — not needed until Phase 2
