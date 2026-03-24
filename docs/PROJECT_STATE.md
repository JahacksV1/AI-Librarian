# AIJAH — Project State, Audit, and Roadmap

> Written after a full two-pass codebase audit (March 2026).
> This document is the single source of truth for where we are, what every piece does,
> how Docker fits in, and what comes next. Update it as work is completed.

---

## What AIJAH Actually Is

AIJAH is a **local file-organization copilot**. You describe what you want done with your files,
AIJAH scans the folder, proposes a step-by-step plan with every rename/move/archive spelled out,
you approve or reject individual actions, and then it executes only what you approved.

Nothing is automatic. Nothing is irreversible. Every file operation goes through you first.

The product has three visible pieces:

- **Conversation panel** — where you talk to AIJAH
- **Plan panel** — where the proposed plan appears with approve/reject controls per action
- **Activity tray** — a live log of every tool call, scan result, and event as they happen

Behind the scenes, every action is recorded in a database with a before-state and after-state,
so there is always a record of what was done and why.

---

## Phase Map (Big Picture)

| Phase | Name | What Gets Built | Status |
|---|---|---|---|
| **Phase 1** | The Body | All pipes working: scan → plan → approve → execute → memory | Code complete, tests pending |
| **Phase 1.5** | Provider Architecture | Swap Ollama for Claude or GPT-4o without changing anything else | Code complete, tests pending |
| **Phase 2** | Install the Brain | Memory retrieval, semantic search, document reading, MCP in own container | Not started |
| **Phase 3** | Grow the Brain | Voice input/output, browser control, reward learning | Not started |

The rule: **never start the next phase while the current phase's tests are failing.**

---

## Full Audit — What Is Built and Verified

### Backend

Every file in `backend/` has been read and confirmed complete.

| File | What It Does |
|---|---|
| `config.py` | Reads all environment variables (database URL, model provider, API keys, sandbox path). Has an `effective_model_name` property that picks the right default per provider. |
| `db/enums.py` | Single source of truth for all enum values (plan status, action status, session state, etc.). Also has `ModelProviderType` (OLLAMA, ANTHROPIC, OPENAI) added in Phase 1.5. Phase 2 enums pre-defined at the bottom. |
| `db/models.py` | All 13 SQLAlchemy ORM models matching the migration SQL exactly. |
| `db/connection.py` | Async database connection manager. Provides `db_manager.session()` context manager and `healthcheck()`. |
| `db/utils.py` | Plan status recalculation logic (e.g. when you approve/reject actions, the plan status updates). |
| `safety/sandbox.py` | Path guards so no tool can operate outside the sandbox. Scan, move, archive, create folder — all enforced to stay inside `SANDBOX_ROOT`. |
| `tools/scan_folder.py` | Reads the filesystem, upserts `file_entities` + `folder_entities` to DB, returns a summary to the agent. |
| `tools/propose_plan.py` | Writes a `plans` row and `plan_actions` rows to DB, returns `plan_id` to the agent. |
| `tools/execute_action.py` | Executes an APPROVED action (RENAME, MOVE, ARCHIVE, CREATE_FOLDER, CLASSIFY). Enforces APPROVED-only guard. Writes `memory_events` with pre/post state. |
| `tools/read_file_metadata.py` | Reads an existing `file_entity` row from DB by path. |
| `tools/get_task_state.py` | Reads the `task_state` row for a session. |
| `tools/update_task_state.py` | Writes state machine transitions to `task_state` (IDLE → SCANNING → PLAN_READY → AWAITING_APPROVAL → etc.). |
| `mcp_server.py` | Registers all 6 tools with FastMCP. Exports `mcp_http_app` for the `/mcp` mount and `mcp` object for in-process calls. |
| `agent/types.py` | Shared types: `ToolCall`, `ChatTurnResult`, `AgentLoopResult`, `EventCallback`, `emit_event`. Lives here to avoid circular imports between loop and providers. |
| `agent/providers/base.py` | Abstract `ModelProvider` class. One method: `chat_stream(messages, tools, event_callback) → ChatTurnResult`. |
| `agent/providers/__init__.py` | Factory: reads `MODEL_PROVIDER` from config, returns the right provider instance. |
| `agent/providers/ollama.py` | Streams from Ollama's `/api/chat` endpoint (NDJSON format). No format conversion needed — Ollama uses OpenAI-compatible messages natively. |
| `agent/providers/anthropic.py` | Streams from Anthropic's API (typed SSE events). Converts messages from internal format to Anthropic format (system prompt separate, tool results as user messages, tool calls as content blocks). |
| `agent/providers/openai.py` | Streams from OpenAI's API (delta SSE). Accumulates tool call fragments across chunks before parsing. No format conversion needed. |
| `agent/context.py` | Assembles the full context packet sent to the model before each call. Queries: session, operational policies, user preferences, task state, conversation history, recent memory events, active plan. Also has anti-redundancy rules in the system prompt to stop the model from re-proposing already-executed work. |
| `agent/loop.py` | The core while-loop. Calls `get_provider().chat_stream()`, handles tool calls via MCP, writes state transitions, emits SSE events, persists all messages to DB. Caps at 10 iterations. |
| `api/sse.py` | All 8 SSE event formatters + a `from_payload()` dispatcher that converts typed dicts to `data: {...}\n\n` strings. |
| `api/routes.py` | All 13 API endpoints. Sessions, plans, actions, scan, files, health. SSE streaming for `/messages` and `/plans/{id}/execute`. Provider-aware health check. |
| `main.py` | App entry point. Validates provider config at startup (fails fast if API key missing). Initializes DB connection and MCP tool cache. Mounts router and MCP app. |

---

### Docker

Every Docker file has been read and confirmed complete.

| File | What It Does |
|---|---|
| `docker-compose.yml` | Defines all services, their relationships, ports, volumes, and health checks. |
| `backend/Dockerfile` | Two-stage build: stage 1 installs Python dependencies, stage 2 copies only the installed packages + source. Produces a ~405MB image (vs 1.5GB+ for naive builds). |
| `frontend/Dockerfile` | Builds the Vite app (`npm run build`) and copies the `dist/` folder into an nginx container. The frontend is served as static files in Docker — not Vite dev server. |
| `frontend/nginx.conf` | nginx config. Serves static files. Proxies all `/api/*` requests to `http://backend:8000/`. Has `proxy_buffering off` so SSE streams pass through without being held. |
| `backend/.dockerignore` | Excludes `__pycache__`, `.env`, `.git`, `*.pyc` from the Docker build context. |
| `frontend/.dockerignore` | Same for the frontend — excludes `node_modules`, `.git`, etc. |
| `postgres/init/` | SQL files that run automatically on first Postgres boot (see Docker section below). |

---

### Frontend

All files in `frontend/` confirmed via code review.

| File | What It Does |
|---|---|
| `main.js` | App entry. Wires up panels, handles composer input, manages session lifecycle, sends messages, reads SSE streams. |
| `panels/plan.js` | Renders the plan card (goal, rationale, action list with approve/reject buttons, execute button). Updates in real time as action statuses change. |
| `panels/conversation.js` | Renders the message thread. Streams tokens into a live assistant message. Collapses tool call messages by default. |
| `panels/activity.js` | Logs every SSE event with colored type badges. Auto-scrolls. |
| `panels/composer.js` | Textarea + Send button. Disabled/enabled based on UI state. Placeholder text changes per state. |
| `state/store.js` | Single state object: `{ sessionId, activePlanId, uiState, drawerOpen }`. Pub/sub with `subscribe()`. |
| `state/router.js` | Routes incoming SSE event payloads to the right panel handler. |
| `api/backendApi.js` | All HTTP calls to the backend (createSession, sendMessage, getPlan, patchAction, approveAll, executePlan). |
| `api/sse.js` | Reads a streaming fetch response, parses `data: {...}\n\n` lines, calls a handler per event. |
| `api/health.js` | Parses the `/health` response and describes failures in human-readable terms. |
| `demo/demoMode.js` | Plays back a pre-scripted demo sequence when the backend is offline. So the UI is never blank. |
| `styles.css` | Full design system: Notion-inspired palette, Inter font, plan cards, badges, panels, dividers. |

---

### Tests

| File | What It Tests |
|---|---|
| `test_v1.py` | Full 9-step Phase 1 end-to-end test. Runs against a live backend at `localhost:8000`. Sends a real message, consumes the SSE stream, approves an action, executes it, verifies memory events. |
| `test_provider_switch.py` | Quick smoke test for provider validation. Checks `/health` for provider status, then does one model/tool round-trip. Use this when switching `MODEL_PROVIDER` in `.env`. |

---

## Docker — What It Is and How It Works Here

If you've never worked with Docker before, here's what's actually happening and why each decision was made.

### The Core Idea

Docker lets you package a program and everything it needs (language runtime, libraries, config) into a
**container** — an isolated box that runs the same way on any machine. Without Docker, you'd have to
install Python, PostgreSQL, and Ollama directly on your computer, deal with version conflicts, and
hope the setup works the same on every machine. With Docker, each service runs in its own container
and they talk to each other over a private internal network.

### What a Container Is vs. an Image

- An **image** is the blueprint — a snapshot of a filesystem with a program and its dependencies.
  Think of it like a recipe.
- A **container** is a running instance of that image. Think of it as a dish made from the recipe.
  You can run multiple containers from the same image.

When you run `docker compose up`, Docker builds the images (if needed) and starts containers from them.

### The Current Services

```
Browser (you)
    │
    ▼ port 3003
frontend container  (nginx serving built React/Vite files)
    │ /api/* → backend:8000
    ▼ port 8000
backend container   (Python + FastAPI + agent loop)
    ├── port 5432 (internal) ──► postgres container  (database)
    ├── port 11434 (internal) ─► ollama container    (local AI model, --profile local)
    └── port 8001 ─────────────► MCP server (NATIVE PROCESS on host machine)
                                 runs: scripts/start-mcp.ps1 / start-mcp.sh
                                 has full local filesystem access
```

**Why the MCP server runs natively (not in Docker):**
Docker containers are isolated from the host filesystem — they can only see paths explicitly
mounted as volumes. The MCP server needs to scan and act on local files (Documents, Downloads,
any path the user grants). A containerized process cannot do this without hardcoding every path
at startup. The MCP server runs as a native Python process so it has full filesystem access,
exactly like VS Code's language servers or Ollama running on the host.

The Docker backend reaches the native MCP server via `host.docker.internal:8001` — a special
hostname Docker provides that resolves to the host machine from inside any container.

---

### Ports: Host vs. Container

Ports have two sides: **host** (your Mac) and **container** (inside Docker).

```
"5433:5432"   →   host port 5433   maps to   container port 5432
"8000:8000"   →   host port 8000   maps to   container port 8000
"3003:80"     →   host port 3003   maps to   container port 80
```

- When **you** connect to Postgres from a GUI tool (TablePlus, DBeaver), you use **port 5433**
  (the host port). We use 5433 instead of 5432 because your Mac already had something running on 5432.
- When the **backend** connects to Postgres *inside Docker*, it uses **port 5432** (the container
  port, via the service name `postgres`). The `DATABASE_URL` never changes.
- The frontend is on **3003** in Docker. When you're doing local dev with Vite, you use **3000**
  instead — that's a different mode entirely (see Dev vs. Docker below).

---

### Volumes: How Data Persists

Containers are ephemeral — if you delete a container, everything inside it is gone. Volumes are
how you keep data alive outside the container lifecycle.

There are two types in use:

**Named volumes** (Docker manages them):
- `pgdata` — stores the actual Postgres database files. Survives `docker compose down`.
  Only deleted with `docker compose down -v` (the `-v` flag).
- `ollama_data` — stores the downloaded AI model weights (~5GB). Also survives restarts.
  This means you only need to `ollama pull qwen2.5` once.

**Bind mounts** (point to real folders on your Mac):
- `./sandbox:/sandbox` — your sandbox test files on the host are visible inside the backend
  container at `/sandbox`. When AIJAH "moves a file," it's moving it in this real folder.
  Bind mounts are NOT deleted by `docker compose down -v`, so your sandbox files are always safe.

```
docker compose down       →  stops containers, removes them. Volumes SURVIVE.
docker compose down -v    →  stops containers, removes them AND volumes. Clean slate.
                              Postgres re-runs migrations. Ollama loses the model (re-pull needed).
```

---

### Health Checks and `depends_on`

Without health checks, Docker starts all containers at the same time. The backend would try to
connect to Postgres before Postgres was ready, crash, and you'd see confusing errors.

Health checks solve this:

```yaml
postgres:
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U aijah -d aijah"]
    interval: 5s
    timeout: 3s
    retries: 5
```

This tells Docker: run `pg_isready` every 5 seconds. If it passes, Postgres is "healthy."

Then the backend uses `condition: service_healthy`:

```yaml
backend:
  depends_on:
    postgres:
      condition: service_healthy
```

This means: **do not start the backend container until Postgres has passed its health check.**
No more race conditions. The startup order is guaranteed.

---

### Why Ollama Is Optional (`--profile local`)

In Phase 1.5, we added support for cloud providers (Claude, GPT-4o). When you're using Claude,
you don't need Ollama running — it's wasting 4–8 GB of RAM doing nothing.

The solution is Docker Compose **profiles**. The Ollama service has `profiles: ["local"]`:

```yaml
ollama:
  profiles: ["local"]    ← only starts when you explicitly ask for it
  image: ollama/ollama
  ...
```

Usage:
```bash
docker compose up                    # starts backend, frontend, postgres only (cloud provider mode)
docker compose --profile local up    # starts everything including Ollama (local model mode)
```

The backend also no longer has `depends_on: ollama` — it starts regardless of whether Ollama
is running. The model provider it uses is controlled by `MODEL_PROVIDER` in `.env`.

---

### Auto-Migrations: How the Database Gets Created

The Postgres Docker image has a built-in trick: any `.sql` files you place in a folder called
`/docker-entrypoint-initdb.d/` inside the container will run in alphabetical order **on first boot**
(only when the `pgdata` volume is empty/new).

We use this by bind-mounting `./postgres/init/` into that folder:

```yaml
postgres:
  volumes:
    - pgdata:/var/lib/postgresql/data
    - ./postgres/init:/docker-entrypoint-initdb.d   ← our SQL files
```

The folder contains:
- `001_create_enums.sql` — creates all 11 Postgres enum types
- `002_create_tables.sql` — creates all 13 tables with correct foreign keys and indexes
- `003_seed.sql` — inserts a test user and test device with fixed UUIDs for testing

On `docker compose down -v` + `docker compose up`, all three re-run and you get a clean database.
On a regular `docker compose down` + `docker compose up`, they are skipped (data already exists).

---

### The Multi-Stage Backend Dockerfile

A naive Dockerfile that installs Python and all dependencies produces a huge image (~1.5GB).
The multi-stage build cuts this to ~405MB by separating the build environment from the runtime:

```dockerfile
# Stage 1: Install dependencies (has pip, build tools, etc.)
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime (only has what's needed to run)
FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /install /usr/local   ← copies only the installed packages
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Stage 1 is discarded after the build. The final image only contains Stage 2.

---

### nginx: Why the Frontend Doesn't Use Vite in Docker

Vite is a **development tool** — it watches files for changes and hot-reloads the browser.
It is not a production server. In Docker (and in anything resembling production), you:

1. **Build** the app once: `npm run build` → outputs a `dist/` folder of optimized static files
2. **Serve** that `dist/` folder with nginx — a real, fast static file server

The frontend Dockerfile does exactly this:

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_API_BASE=/api
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build          ← produces dist/

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
```

The nginx config then proxies all `/api/*` requests to the backend container:

```nginx
location /api/ {
    proxy_pass http://backend:8000/;
    proxy_buffering off;        ← critical: SSE streams must not be buffered
    proxy_read_timeout 86400s;  ← keep connection alive for long agent runs
}
```

`proxy_buffering off` is critical for SSE. Without it, nginx would hold the response in memory
and batch it — you'd see no live tokens until the whole response was done.

**Dev mode vs. Docker mode:**

| Mode | Frontend | Backend | Port |
|---|---|---|---|
| Local dev | Vite dev server (`npm run dev`) | uvicorn directly | Frontend: 3000, Backend: 8000 |
| Docker | nginx serving `dist/` | uvicorn in container | Frontend: 3003, Backend: 8000 (internal) |

---

## What Needs to Be Done Next

### Gate 1 — Close Phase 1 (run the tests)

These confirm the code that's already written actually works end-to-end. Nothing in Phase 2
starts until both pass.

**Item 1: Run `test_v1.py` (9-step V1 test)**

Prerequisites:
- `docker compose --profile local up` (needs Ollama)
- `docker compose exec ollama ollama pull qwen2.5` (one-time, ~5GB)
- `MODEL_PROVIDER=ollama` in `.env`

Run:
```bash
python test_v1.py
```

This walks through: health check → create session → send message → watch scan_folder and
propose_plan tool calls → fetch plan → approve an action → execute → verify memory event written.

**Item 2: Run `test_provider_switch.py` (provider smoke test)**

Prerequisites:
- `docker compose up` (no Ollama needed)
- `MODEL_PROVIDER=anthropic` and `ANTHROPIC_API_KEY=sk-...` in `.env`

Run:
```bash
python test_provider_switch.py
```

This verifies: health check shows provider configured → create session → send message →
tool-call round-trip works with Claude.

---

### Gate 2 — Dev Quality of Life (quick win)

**Item 3: Add Docker Compose watch**

Right now, any Python file change requires a full `docker compose up --build` to see the effect
inside Docker. Docker Compose watch eliminates this by syncing file changes into the running
container instantly. Only `requirements.txt` changes trigger a rebuild.

Add to `docker-compose.yml` under the `backend` service:

```yaml
backend:
  develop:
    watch:
      - action: sync
        path: ./backend
        target: /app
      - action: rebuild
        path: ./backend/requirements.txt
```

Run with: `docker compose watch` instead of `docker compose up`.

---

### Phase 2 — Install the Brain

The Docker changes in Phase 2 come in two waves. Do the database/embeddings work first,
MCP extraction last.

**Wave 1: pgvector + embeddings (Docker side)**

| What | Why |
|---|---|
| Switch `postgres:16` → `pgvector/pgvector:pg16` in compose | This image includes the pgvector extension. One line change. |
| Add `003_add_pgvector.sql` migration | `CREATE EXTENSION vector;` + new embeddings tables + entity tables |
| Pull `nomic-embed-text` in Ollama | Local embedding model for converting text to vectors |

pgvector is a Postgres extension that adds a `vector` column type. You store a list of 768
numbers next to each file or memory event, and can then find "similar" items using distance
math instead of keyword matching. This is what lets AIJAH say "I've seen something like this
before" instead of only remembering exact strings.

**Wave 2: MCP server extraction (Docker side)**

Currently the MCP server (the 6 tools) runs **inside the backend process** — they share memory.
In Phase 2, it becomes its own container:

```
Before:
  backend container  [ FastAPI + agent loop + MCP tools + sandbox access ]

After:
  backend container  [ FastAPI + agent loop ]
       │ HTTP calls to mcp-server:8001
       ▼
  mcp-server container  [ MCP tools + sandbox access ]
       │
  ./sandbox bind mount (moves from backend to mcp-server)
```

Changes needed in `docker-compose.yml`:
- Add `mcp-server` service on port 8001
- Move `./sandbox:/sandbox` bind mount from `backend` to `mcp-server`
- Add `MCP_URL=http://mcp-server:8001` to backend environment
- Change backend from `Client(mcp)` (in-process) to `Client("http://mcp-server:8001/mcp")` (HTTP)

Do this **after** the embedding pipeline is built and stable. It's a structural change that
touches the loop, the client, and the compose file — better to do it in one focused step.

---

### Phase 3 — Grow the Brain (future)

Not planned in detail yet. Triggers when Phase 2 memory retrieval is producing visibly better responses.

| Addition | Docker Change |
|---|---|
| Voice input (Whisper) | New `whisper-server` container on port 8002 |
| Voice output (TTS) | New `tts-server` container on port 8003 |
| Faster local models | GPU passthrough via nvidia-container-toolkit |
| More services | Resource limits, profiles for dev vs. prod configs |

---

## Quick Reference: Docker Commands

```bash
# --- Starting the stack ---

# Start backend services (cloud provider mode — no Ollama)
docker compose up

# Start backend services with Ollama (local model mode)
docker compose --profile local up

# Start the MCP server natively (REQUIRED — run in a separate terminal)
# Windows:
.\scripts\start-mcp.ps1
# Mac/Linux:
./scripts/start-mcp.sh

# Start with file-sync hot reload on the backend
docker compose watch

# Rebuild images after dependency changes
docker compose up --build

# Stop everything (data preserved)
docker compose down

# Stop everything and wipe the database and model weights
docker compose down -v

# View live logs for a specific service
docker logs aijah-backend-1 -f
docker logs aijah-postgres-1 -f

# Connect to Postgres directly
docker compose exec postgres psql -U aijah -d aijah

# Pull the Ollama model (one-time, ~5GB)
docker compose exec ollama ollama pull qwen2.5

# Run a quick health check
curl http://localhost:8000/health
```

---

## Enum Sync Rule

Three places must always match. If you ever add an enum value, update all three:

```
docs/TYPE_LEDGER.md           ← human contract (source of truth)
backend/db/enums.py           ← Python enums
postgres/init/001_create_enums.sql  ← Postgres enum types
```

---

*Last updated: March 2026 — post Phase 1 + Phase 1.5 implementation audit.*
*Next update: after test_v1.py and test_provider_switch.py pass.*
