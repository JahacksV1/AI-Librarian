# AIJAH — Docker Sync & Phase 1 Execution Roadmap

> This document captures the full current state of both tracks (Caprice's Docker infrastructure
> and the backend code track), what is verified complete, what still needs to be done, and the
> exact execution steps for each person to bring Phase 1 to a working end-to-end demo.
>
> Read this alongside `docs/V1_CONTRACT.md` (the acceptance criteria) and `docs/TYPE_LEDGER.md`
> (paste into every new Cursor session).

---

## Architecture Overview

```
Browser :3000
    │  fetch + EventSource
    ▼
frontend container (nginx:alpine)
    │  HTTP /api/*  (proxy or direct)
    ▼
backend container :8000  (FastAPI + agent loop)
    ├── asyncpg  ──────────────────► postgres container :5432 (internal)
    ├── httpx    ──────────────────► ollama container  :11434
    └── in-process mount at /mcp ──► mcp_server.py (FastMCP)
                                          ├── tools/*.py  ────► postgres
                                          └── safety/sandbox.py ► /sandbox volume (bind mount)
```

Every service communicates by Docker service name on the internal network — not localhost.
The env vars `DATABASE_URL`, `OLLAMA_URL`, and `SANDBOX_ROOT` are already wired correctly in
`docker-compose.yml`. The Docker network itself does not need to change. Everything remaining
lives inside the `backend` container or in Caprice's infrastructure fixes.

---

## What Is Already Built and Verified

### Caprice's Track — Infrastructure

| Item | Status | Detail |
|---|---|---|
| `docker-compose.yml` — 4 services | Complete | `frontend`, `backend`, `postgres`, `ollama` all defined |
| `backend/Dockerfile` | Complete | `python:3.12-slim`, installs requirements, runs uvicorn — correct |
| `frontend/Dockerfile` | Complete | `nginx:alpine`, serves static files — correct |
| `sandbox/` with test files | Complete | Bind-mounted into backend at `/sandbox` |
| Named volumes `pgdata` + `ollama_data` | Complete | Persist across restarts correctly |
| Env vars pointed at Docker service names | Complete | `DATABASE_URL`, `OLLAMA_URL`, `SANDBOX_ROOT` all correct |
| First compose build ran | Complete | Images built, network created, containers created |

The architecture is sound. The service topology matches the V1 contract exactly. No structural changes needed.

### Your Track — Backend Code (Steps 1–5 Complete)

| Item | Status | Detail |
|---|---|---|
| `config.py` | Complete | Pydantic `Settings` reading from `.env` — all required fields present |
| `db/enums.py` | Complete | All enums from TYPE_LEDGER — values match migrations exactly |
| `db/connection.py` | Complete | Async SQLAlchemy engine, session factory, `db_manager.session()` context manager, `healthcheck()` |
| `db/models.py` | Complete | All 13 SQLAlchemy ORM models — schema matches migration SQL exactly |
| `db/migrations/001_create_enums.sql` | Complete | All 11 Postgres enum types with `pgcrypto` extension |
| `db/migrations/002_create_tables.sql` | Complete | All 13 Phase 1 tables with correct FK relationships and indexes |
| `safety/sandbox.py` | Complete | Path guards, `resolve_path`, `scan_paths`, `move_path`, `archive_destination`, `create_folder` |
| `tools/scan_folder.py` | Complete | Reads filesystem, upserts `file_entities` + `folder_entities`, returns summary |
| `tools/read_file_metadata.py` | Complete | Reads existing `file_entity` from DB by path |
| `tools/propose_plan.py` | Complete | Writes `plans` + `plan_actions` rows to DB, returns `plan_id` |
| `tools/execute_action.py` | Complete | Executes APPROVED actions, enforces status guard, writes `memory_events`, updates entities |
| `tools/get_task_state.py` | Complete | Reads `task_state` for a session |
| `tools/update_task_state.py` | Complete | Writes `task_state` fields for a session |
| `mcp_server.py` | Complete | FastMCP app, all 6 tools registered with correct descriptions, `mcp_http_app` exported |

**The entire DB layer, safety module, and all MCP tool implementations are complete and architecturally correct.**
`execute_action.py` already has the APPROVED status guard built in at the tool level. The agent loop will
also enforce it at the API level. The tools are pure Python functions with no FastMCP coupling — exactly
as designed.

---

## What Still Needs to Be Done

### Caprice's Open Items (Infrastructure)

These 4 items are required before a clean `docker compose up` is possible and before end-to-end testing
can begin.

---

#### Item 1 — Fix the Postgres host port conflict

**What:** The host machine already has something running on port 5432, which prevents Docker from
binding the Postgres container's port to the host.

**Fix:** In `docker-compose.yml`, change the postgres service ports line:

```yaml
# Before
ports:
  - "5432:5432"

# After
ports:
  - "5433:5432"   # host_port:container_port
```

**Important:** The `DATABASE_URL` environment variable does NOT change. It uses the internal Docker
network port (`postgres:5432`), not the host port. Only the host-side binding changes. After this fix,
connecting from outside Docker (e.g. DBeaver or psql from a terminal) uses port 5433. Inside Docker,
everything still talks to port 5432.

---

#### Item 2 — Auto-run migrations on first boot

**What:** The 13-table schema and all enum types live in `backend/db/migrations/`. Right now they
don't run automatically when the postgres container starts. Postgres:16 has a built-in mechanism for
this: any `.sql` files placed in `/docker-entrypoint-initdb.d/` inside the container are executed
in filename order on first boot (only runs when the `pgdata` volume is empty/new).

**Fix — Step 1:** Create the `postgres/init/` directory at the repo root.

**Fix — Step 2:** Copy both migration files into it:

```
postgres/
└── init/
    ├── 001_create_enums.sql   (copied from backend/db/migrations/)
    └── 002_create_tables.sql  (copied from backend/db/migrations/)
```

These are copies, not symlinks — Docker builds need them at this path.

**Fix — Step 3:** Add the volume mount to the `postgres` service in `docker-compose.yml`:

```yaml
postgres:
  image: postgres:16
  environment:
    - POSTGRES_USER=aijah
    - POSTGRES_PASSWORD=aijah
    - POSTGRES_DB=aijah
  volumes:
    - pgdata:/var/lib/postgresql/data
    - ./postgres/init:/docker-entrypoint-initdb.d    # ← add this line
  ports:
    - "5433:5432"
```

**Note:** This only runs on first boot. If the `pgdata` volume already exists with data in it,
the init scripts are skipped. To re-run migrations from scratch: `docker compose down -v` (removes
the volume) then `docker compose up`.

---

#### Item 3 — Write seed data

**What:** Every backend operation requires a valid `session_id`, which requires a `session` row,
which requires a `user` row and a `device` row. Without seed data, any end-to-end test will fail
the moment it hits the DB.

**Fix:** Create `postgres/init/003_seed.sql` with hardcoded UUIDs so the same IDs can be used
in testing without re-querying:

```sql
-- Test user
INSERT INTO users (id, name, email, timezone)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'Test User',
    'test@aijah.local',
    'UTC'
) ON CONFLICT DO NOTHING;

-- Test device (Windows PC on this machine)
INSERT INTO devices (id, user_id, name, device_type, hostname)
VALUES (
    '00000000-0000-0000-0000-000000000002',
    '00000000-0000-0000-0000-000000000001',
    'Dev Machine',
    'WINDOWS_PC',
    'aijah-dev'
) ON CONFLICT DO NOTHING;
```

The `ON CONFLICT DO NOTHING` clauses make this safe to re-run if you ever reset and re-run
the init scripts.

---

#### Item 4 — Pull the Ollama model

**What:** After `docker compose up`, the ollama container is running but has no models downloaded.
The named volume `ollama_data` persists the models, so this only needs to happen once.

**Fix:** After `docker compose up`, run:

```bash
docker exec <ollama-container-name> ollama pull qwen2.5
```

To find the container name: `docker ps` — look for the ollama container (usually `aijah-ollama-1`).

This download is ~5GB and takes a few minutes. Once done, it persists in the `ollama_data` volume
across all future restarts. `qwen2.5` is the model specified in `.env.example` as `OLLAMA_MODEL`
and is the best local option for tool-calling in Phase 1.

---

#### Verify Everything Is Working

After the 4 items above are done, run through this checklist:

```
[ ] docker compose up — all 4 containers start, no port errors
[ ] docker logs aijah-backend-1 — shows "Application startup complete"
[ ] docker logs aijah-postgres-1 — shows migration files ran on init
[ ] Connect to postgres on localhost:5433 (user: aijah, pass: aijah, db: aijah)
[ ] Run: SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';
    → should return all 13 tables
[ ] Run: SELECT * FROM users; → should return the seed test user
[ ] GET http://localhost:8000/health → {"status": "ok", "db": "connected", "ollama": "reachable"}
```

---

### Your Open Items — Steps 6–9

Steps 1–5 are complete. Steps 6–9 are what remains to finish Phase 1.

The file structure for these new files follows the execution roadmap:

```
backend/
├── agent/
│   ├── context.py    ← Step 6A
│   └── loop.py       ← Step 6B
├── api/
│   ├── sse.py        ← Step 7A
│   └── routes.py     ← Step 7B
└── main.py           ← Step 8 (update existing stub)

frontend/
├── index.html        ← already exists (stub)
├── app.js            ← Step 9A (new)
└── style.css         ← Step 9B (new)
```

---

#### Step 6A — `backend/agent/context.py`

**What it does:** Assembles the full context packet that the agent loop sends to Ollama before each
model call. Context quality is the single most important factor in how well the agent behaves.

**Function signature:**

```python
async def assemble_context(session_id: str) -> ContextPacket
```

**What it queries from DB (in this order):**

1. `sessions` — get the session row to find `user_id` and `device_id`
2. `operational_policies WHERE user_id = ? AND is_active = true` — safety and naming rules
3. `user_preferences WHERE user_id = ?` — known user habits
4. `task_state WHERE session_id = ?` — current working memory (goal, current_step, active_plan_id)
5. `session_messages WHERE session_id = ? ORDER BY created_at ASC` — full conversation history

**How it assembles the message list for Ollama:**

```python
messages = []

# 1. System message — hardcoded role + safety rules + active policies appended
messages.append({
    "role": "system",
    "content": SYSTEM_PROMPT + format_policies(policies)
})

# 2. User preferences — injected as a second system message so model knows naming habits
if preferences:
    messages.append({
        "role": "system",
        "content": format_preferences(preferences)
    })

# 3. Task state — injected so model knows what step it's in and what plan is active
if task_state:
    messages.append({
        "role": "system",
        "content": format_task_state(task_state)
    })

# 4. Full conversation history — all session_messages in order
for msg in session_messages:
    messages.append({
        "role": msg.role.value.lower(),   # RoleType → "user"/"assistant"/"tool"/"system"
        "content": msg.content
    })
```

**The system prompt (from `docs/AGENT_LOOP.md`, word for word):**

```
You are AIJAH, a local file assistant. Your job is to help the user organize their files safely.

Rules you must always follow:
- Never perform file operations without a plan being proposed and approved first.
- Always call propose_plan before suggesting any rename, move, or archive action.
- Never delete files. Use archive instead.
- Only operate within the sandbox root path.
- If you are unsure about a file's purpose, ask the user before including it in a plan.
- When you propose a plan, explain your reasoning clearly so the user can make an informed decision.
```

**Phase 1 only.** Phase 2 adds vector-retrieved similar memory events to this context packet.
Do not implement that now.

---

#### Step 6B — `backend/agent/loop.py`

**What it does:** The core agent loop. Called every time a user sends a message. Runs iteratively
until the model produces a final text response or hits the 10-iteration cap.

**Function signature:**

```python
async def run_agent_loop(
    session_id: str,
    user_message: str,
    sse_queue: asyncio.Queue
) -> None
```

The `sse_queue` is how the loop sends events to the HTTP response stream without coupling to the
FastAPI response object directly.

**Full loop structure:**

```python
MAX_TOOL_ITERATIONS = 10

async def run_agent_loop(session_id, user_message, sse_queue):

    # 1. Persist user message
    await db.insert_message(session_id, role=RoleType.USER, content=user_message)

    # 2. Assemble context
    context_messages = await assemble_context(session_id)

    # 3. Get cached MCP tool schemas (cached at app startup — not per-call)
    tools = get_cached_tool_schemas()

    iteration = 0

    while True:
        iteration += 1

        # 4. Iteration cap — hard stop at 10 tool calls
        if iteration > MAX_TOOL_ITERATIONS:
            log.error("agent_loop.max_iterations_exceeded", session_id=session_id)
            await db.insert_message(
                session_id, role=RoleType.ASSISTANT,
                content="I ran into an issue completing that task. Please try again."
            )
            await sse_queue.put(error_event("Max iterations exceeded", ""))
            break

        # 5. Call Ollama with stream=True
        log.info("agent_loop.context", session_id=session_id,
                 message_count=len(context_messages), iteration=iteration)

        response = await ollama_client.chat(
            model=settings.ollama_model,
            messages=context_messages,
            tools=tools,
            stream=True
        )

        # 6. Stream tokens to frontend via SSE queue
        full_response = await stream_tokens(response, sse_queue)

        log.info("agent_loop.model_response", session_id=session_id,
                 had_tool_calls=bool(full_response.tool_calls),
                 tool_names=[tc.name for tc in (full_response.tool_calls or [])])

        # 7. Handle tool calls
        if full_response.tool_calls:
            for tool_call in full_response.tool_calls:

                log.info("agent_loop.tool_call", session_id=session_id,
                         tool=tool_call.name, args=tool_call.args)

                # Emit SSE event so UI can show "Using tool: scan_folder..."
                await sse_queue.put(tool_call_event(tool_call.name, tool_call.args))

                # Execute via MCP (in-process call)
                result = await mcp_client.call_tool(tool_call.name, tool_call.args)

                log.info("agent_loop.tool_result", session_id=session_id,
                         tool=tool_call.name, result_preview=str(result)[:200])

                await sse_queue.put(tool_result_event(tool_call.name, result))

                # If propose_plan ran, emit special event so frontend fetches the plan
                if tool_call.name == "propose_plan" and "plan_id" in result:
                    await sse_queue.put(plan_created_event(
                        plan_id=result["plan_id"],
                        goal=tool_call.args.get("goal", ""),
                        action_count=result.get("action_count", 0)
                    ))

                # Persist tool message to DB
                await db.insert_message(
                    session_id,
                    role=RoleType.TOOL,
                    content=json.dumps(result),
                    tool_name=tool_call.name,
                    tool_call_id=tool_call.id
                )

                # Append result to running context
                context_messages.append({
                    "role": "tool",
                    "content": json.dumps(result),
                    "tool_call_id": tool_call.id
                })

                # Write state machine transition to DB
                await write_state_transition(session_id, tool_call.name, result)

            continue  # go back to top of loop — model will see tool results

        # 8. Final text response — model is done
        message_row = await db.insert_message(
            session_id, role=RoleType.ASSISTANT, content=full_response.content
        )
        await sse_queue.put(message_complete_event(str(message_row.id), full_response.content))
        break
```

**State machine transitions the loop writes to `task_state`:**

| Tool Call | `current_step` written |
|---|---|
| `scan_folder` called | `SCANNING` |
| `scan_folder` returns | `PLAN_READY` |
| `propose_plan` returns | `AWAITING_APPROVAL` + set `active_plan_id` |
| Any tool raises exception | `ERROR` |

These writes happen inside `write_state_transition()` — a small helper that calls
`tools/update_task_state.py` with the appropriate values.

**Observability — what must be logged on every loop run:**

```python
# Before each Ollama call
log.info("agent_loop.context", extra={
    "session_id": session_id,
    "message_count": len(context_messages),
    "iteration": iteration,
    "has_task_state": ...,
    "active_plan_id": ...,
    "current_step": ...,
})

# After each Ollama call
log.info("agent_loop.model_response", extra={
    "session_id": session_id,
    "had_tool_calls": bool(response.tool_calls),
    "tool_names": [...],
    "response_length": len(response.content),
})

# Each tool call
log.info("agent_loop.tool_call", extra={"session_id": ..., "tool": ..., "args": ...})
log.info("agent_loop.tool_result", extra={"session_id": ..., "tool": ..., "result_preview": ...})

# State transitions
log.info("agent_loop.state_transition", extra={
    "session_id": ..., "from_step": ..., "to_step": ..., "trigger": ...
})
```

Without these logs, debugging agent behavior is guesswork. The model will make bad decisions and
without logs you won't know if it was a context problem, a tool contract problem, or a prompt problem.

---

#### Step 7A — `backend/api/sse.py`

**What it does:** Formats all SSE events as properly structured `data: ...\n\n` strings.

All 8 event types from `docs/TYPE_LEDGER.md`:

```python
import json

def _event(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"

def token_event(token: str) -> str:
    return _event({"type": "token", "token": token})

def message_complete_event(message_id: str, content: str) -> str:
    return _event({"type": "message_complete", "message_id": message_id, "content": content})

def tool_call_event(tool: str, args: dict) -> str:
    return _event({"type": "tool_call", "tool": tool, "args": args})

def tool_result_event(tool: str, result: dict) -> str:
    return _event({"type": "tool_result", "tool": tool, "result": result})

def plan_created_event(plan_id: str, goal: str, action_count: int) -> str:
    return _event({"type": "plan_created", "plan_id": plan_id, "goal": goal, "action_count": action_count})

def action_executed_event(action_id: str, outcome: str, action_type: str) -> str:
    return _event({"type": "action_executed", "action_id": action_id, "outcome": outcome, "action_type": action_type})

def execution_complete_event(plan_id: str, succeeded: int, failed: int) -> str:
    return _event({"type": "execution_complete", "plan_id": plan_id, "succeeded": succeeded, "failed": failed})

def error_event(message: str, detail: str) -> str:
    return _event({"type": "error", "message": message, "detail": detail})
```

---

#### Step 7B — `backend/api/routes.py`

**What it does:** All HTTP endpoints defined in `docs/V1_CONTRACT.md`. The routes are the thin layer
between HTTP and the agent loop / DB — no business logic lives here.

**Full route list:**

```
POST   /sessions                           Create session
GET    /sessions/{session_id}              Get session
PATCH  /sessions/{session_id}              Update session status/title

POST   /sessions/{session_id}/messages     Send user message → triggers agent loop → SSE stream
GET    /sessions/{session_id}/messages     Get message history
GET    /sessions/{session_id}/plans        List plans for session

GET    /plans/{plan_id}                    Get plan with full action list
PATCH  /actions/{action_id}               Approve or reject a single action
POST   /plans/{plan_id}/approve-all        Approve all PENDING actions in a plan
POST   /plans/{plan_id}/execute            Execute all APPROVED actions → SSE stream

POST   /scan                               Trigger folder scan
GET    /files                              List known file entities

GET    /health                             Health check
```

**The two most important routes in detail:**

**`POST /sessions/{session_id}/messages`** — this is the main entry point for the entire system:

```python
@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: str, body: SendMessageRequest):
    queue = asyncio.Queue()

    async def run_loop():
        try:
            await run_agent_loop(session_id, body.content, queue)
        except Exception as e:
            await queue.put(error_event(str(e), ""))
        finally:
            await queue.put(None)  # sentinel — signals stream end

    asyncio.create_task(run_loop())

    async def event_stream():
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

**`POST /plans/{plan_id}/execute`** — iterates APPROVED actions and streams results:

```python
@router.post("/plans/{plan_id}/execute")
async def execute_plan(plan_id: str):
    async def event_stream():
        succeeded = 0
        failed = 0

        async with db_manager.session() as session:
            actions = await session.scalars(
                select(PlanAction).where(
                    PlanAction.plan_id == uuid.UUID(plan_id),
                    PlanAction.status == ActionStatus.APPROVED   # guard — only APPROVED
                )
            )
            for action in actions:
                result = await execute_action(str(action.id))
                outcome = result.get("outcome", "FAILED")
                if outcome == "SUCCESS":
                    succeeded += 1
                else:
                    failed += 1
                yield action_executed_event(
                    action_id=str(action.id),
                    outcome=outcome,
                    action_type=action.action_type.value
                )

        yield execution_complete_event(plan_id, succeeded, failed)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

---

#### Step 8 — Update `backend/main.py`

Replace the current stub (just a healthcheck) with the fully wired entry point:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from mcp_server import mcp_http_app
from api.routes import router
from db.connection import db_manager
from agent.loop import initialize_mcp_tool_cache

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Verify DB is reachable before accepting requests
    await db_manager.healthcheck()

    # Discover and cache MCP tool schemas once at startup
    # The agent loop reads from this cache — not on every message
    await initialize_mcp_tool_cache()

    yield
    # (shutdown logic here if needed)

app = FastAPI(lifespan=lifespan)
app.include_router(router)
app.mount("/mcp", mcp_http_app)
```

The `initialize_mcp_tool_cache()` function in `loop.py` calls `tools/list` on the in-process MCP
server at startup, converts the tool schemas to Ollama function-call format, and stores them in a
module-level variable. The loop reads this cache on every iteration.

---

#### Step 9A — `frontend/app.js`

**What it does:** The SSE consumer, plan card renderer, and approve/reject handler. No framework —
plain JavaScript using `fetch` and `EventSource`.

**Key behaviors:**

```javascript
// On load: create a session and store the ID
const session = await fetch('/sessions', {
    method: 'POST',
    body: JSON.stringify({ user_id: '00000000-0000-0000-0000-000000000001', mode: 'CLEANUP' })
}).then(r => r.json());

sessionId = session.id;

// On message submit: open SSE connection
async function sendMessage(content) {
    const response = await fetch(`/sessions/${sessionId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content })
    });

    const reader = response.body.getReader();
    // read chunks, parse "data: {...}\n\n" lines, dispatch to handlers
}

// SSE event handlers
const handlers = {
    token:             (e) => appendToken(e.token),
    message_complete:  (e) => finalizeMessage(e.message_id, e.content),
    tool_call:         (e) => showToolIndicator(e.tool),
    tool_result:       (e) => hideToolIndicator(),
    plan_created:      (e) => fetchAndRenderPlan(e.plan_id),
    action_executed:   (e) => updateActionRow(e.action_id, e.outcome),
    execution_complete:(e) => showExecutionSummary(e.succeeded, e.failed),
    error:             (e) => showErrorBanner(e.message)
};

// Plan card rendering
async function fetchAndRenderPlan(planId) {
    const plan = await fetch(`/plans/${planId}`).then(r => r.json());
    renderPlanCard(plan);
    setSessionState('AWAITING_APPROVAL');
}

// Per-action approve/reject
async function approveAction(actionId) {
    await fetch(`/actions/${actionId}`, {
        method: 'PATCH',
        body: JSON.stringify({ status: 'APPROVED' })
    });
    updateActionRowStatus(actionId, 'APPROVED');
    checkEnableExecuteButton();
}

// Execute button — visible only when ≥1 action is APPROVED
async function executePlan(planId) {
    setSessionState('EXECUTING');
    const response = await fetch(`/plans/${planId}/execute`, { method: 'POST' });
    // read SSE stream, dispatch action_executed and execution_complete events
}
```

**UI state** — the UI follows `docs/STATE_MACHINE.md` exactly:

| Session State | Chat input | Approve buttons | Execute button | Indicator |
|---|---|---|---|---|
| `IDLE` | Enabled | Hidden | Hidden | None |
| `SCANNING` | Disabled | Hidden | Hidden | "Scanning files..." |
| `PLAN_READY` | Disabled | Hidden | Hidden | "Generating plan..." |
| `AWAITING_APPROVAL` | Disabled | Active | Enabled if ≥1 APPROVED | None |
| `EXECUTING` | Disabled | Disabled | Disabled | Per-action progress |
| `COMPLETE` | Enabled | Hidden | Hidden | "Done" summary |
| `ERROR` | Enabled | Hidden | "Retry" shown | Error detail |

---

#### Step 9B — `frontend/style.css`

Minimal, clean. Two-column layout:
- Left column: chat transcript (message bubbles, tool-call indicators)
- Right column: plan card (action list, per-action approve/reject, execute button)

No framework, no build step — plain CSS loaded by `index.html`.

---

## The 9 Acceptance Criteria (V1 Demo Steps)

Phase 1 is complete when all 9 of these pass end-to-end. Test in order — each one builds on the last.

| # | Step | What to verify | Who owns it |
|---|---|---|---|
| 1 | `docker compose up` boots clean | All 4 containers running, no port errors, all 13 tables exist in postgres | Caprice |
| 2 | Backend → Ollama round-trip | `POST /sessions` + `POST /sessions/{id}/messages` → Ollama returns a response | You |
| 3 | MCP tool discovery | Backend logs show tool schemas cached at startup; system prompt includes tool names | You |
| 4 | `scan_folder` runs on sandbox | Message "scan my sandbox folder" → scan_folder tool called → `file_entities` rows appear in DB | You |
| 5 | Plan generated | Agent calls `propose_plan` → `plans` row + `plan_actions` rows appear in DB with status PENDING | You |
| 6 | Browser shows plan | `plan_created` SSE event → frontend fetches `GET /plans/{id}` → plan card with action rows visible | You |
| 7 | Approve works | Click Approve on an action → `PATCH /actions/{id}` → DB shows `action_status = APPROVED` | Both verify in DB |
| 8 | Execution runs safely | Click Execute → `execute_action` runs → file actually moved/renamed in `/sandbox` → no errors | You |
| 9 | Memory event written | After execution → `SELECT * FROM memory_events` → row exists with `pre_state_json` and `post_state_json` | Both verify in DB |

---

## How the Two Tracks Connect

```
Caprice completes Items 1–4 (port fix, migrations, seed, model pull)
    │
    ▼
docker compose up — all 4 services healthy
    │
    ├──────────────────────────────────────────────────────────────┐
    │                                                              │
    ▼ (unblocks you)                                               ▼ (Caprice learns)
You build Steps 6–9                                 Caprice runs psql, verifies tables,
context.py → loop.py → sse.py →                     inspects DB after each demo step,
routes.py → main.py → frontend                      manages volumes + resets when needed
    │
    ▼
End-to-end demo test — all 9 steps pass
    │
    ▼
Phase 1 complete → Phase 2 can start
```

---

## Non-Negotiable Rules While Building

These are enforced by the architecture docs and must not be bypassed:

1. **`execute_action` guard is already in the tool** — `tools/execute_action.py` checks
   `action.status != ActionStatus.APPROVED` before touching the filesystem. The API route must
   also check this. Double-enforcement is correct.

2. **No auto-execute path** — there is no code path that goes from `AWAITING_APPROVAL` to
   `EXECUTING` without a user clicking Execute. The state machine in `docs/STATE_MACHINE.md`
   has no such transition and it must not be added.

3. **`task_state.current_step` is the source of truth for session state** — every state transition
   in the agent loop writes to this field. The UI derives its state from polling or re-reading this
   field. In-memory state that isn't persisted does not count.

4. **DB is always the source of truth** — if the backend container restarts mid-execution, it
   must be able to reconstruct what was happening by reading the DB. No in-memory state that
   isn't also in the DB.

5. **MCP tool discovery happens once at startup** — `tools/list` is called once in `lifespan()`,
   not on every agent loop iteration. The result is cached in a module-level variable.

6. **Enums in three places must stay in sync** — `docs/TYPE_LEDGER.md` → `db/enums.py` →
   `db/migrations/001_create_enums.sql`. If you ever add a value, update all three.

7. **`CLASSIFY` in Phase 1 is metadata-only** — the action type exists and `execute_action.py`
   handles it (no filesystem change). The `entities` table does not exist until Phase 2.
   Do not add it now.

---

## What Is Explicitly Out of Scope (Phase 1)

Do not build any of the following. If it's not in `docs/V1_CONTRACT.md`, it doesn't exist yet:

- `pgvector` extension, embeddings tables, semantic search
- `document_extracts` table, PDF/Word/OCR reading
- `entities`, `entity_relationships`, `file_entity_links` tables
- Voice input or output (Whisper, TTS)
- `READ_ALOUD` session mode
- Separate `mcp-server` Docker container (FastMCP stays in-process until Phase 2)
- Redis
- Any frontend framework (React, Vue, etc.) — plain HTML/JS only
- Reward system, learning loop, staged ontology proposals
