# AIJAH Phase Map

> Phases are not purely sequential. Some tracks run in parallel.
> This document answers: what are we building, in what order, who owns what, and what can happen at the same time?

---

## The Three Phases

| Phase | Name | Theme | Goal |
|---|---|---|---|
| Phase 1 | **The Body** | Build the pipes, make them work | Correct behavior, clean architecture, safe execution |
| Phase 2 | **Install the Brain** | Activate memory and retrieval | AIJAH gets progressively smarter with every action |
| Phase 3 | **Grow the Brain** | Expand modalities and learning | Voice, document reading, computer control, reward loop |

---

## Phase 1 — The Body

**Duration**: This week / sprint 1  
**Definition of done**: All 9 demo steps in `V1_CONTRACT.md` pass end-to-end.

### What must be true before Phase 2 can start

- [ ] Docker Compose stack boots with zero errors
- [ ] Backend talks to Ollama, tool-calling round-trip works
- [ ] `scan_folder` runs on sandbox folder
- [ ] Plan generation works (≥1 RENAME or MOVE action)
- [ ] Approve / Reject works in browser UI
- [ ] Approved actions execute safely on filesystem
- [ ] `memory_events` written with pre/post state
- [ ] All 13 DB tables exist and are correct

### Work tracks in Phase 1

Two tracks can run in parallel once Docker is up.

#### Track A — Infrastructure (your partner's focus)
This is the foundation everything else sits on. Nothing else works without this.

| Task | What it is | Blocks |
|---|---|---|
| Install Docker Desktop | Required to run the stack | Everything |
| Run `docker compose up` | Boot postgres + ollama + backend stub | All development |
| Connect to Postgres from local tool (DBeaver, TablePlus, psql) | Verify DB is alive | DB migration work |
| Run DB migrations (`001_create_enums.sql`, `002_create_tables.sql`) | Create all 13 tables and enums | Backend and agent loop |
| Pull Ollama model | `docker exec ollama ollama pull qwen2.5` | Agent loop testing |
| Manage postgres volume | Understand `pgdata` volume, how to reset, how to inspect | Ops |
| Write and run seed data | Insert a test user + device row | End-to-end testing |

**What your partner should learn and practice:**
- Docker basics: images, containers, volumes, `docker compose up/down/logs`
- Postgres basics: psql, running SQL files, reading table structure
- How to read `docker-compose.yml` and understand service dependencies
- How to inspect running containers: `docker ps`, `docker exec`, `docker logs`
- How to reset the database (drop volume, re-run migrations)

This is the database side of things. She owns it. Every time the backend needs a new table or migration, this is the track that runs it.

---

#### Track B — Backend + Agent Loop (your focus)
Can start in parallel once Track A has postgres and ollama running.

| Task | Depends on |
|---|---|
| FastAPI project scaffold (`backend/main.py`, requirements, Dockerfile) | Docker up |
| DB connection layer (`backend/db/connection.py`) | Postgres alive |
| Python enums (`backend/db/enums.py`) — must match TYPE_LEDGER | Migrations run |
| MCP server (`backend/mcp_server.py`) — 6 tools stubbed | FastAPI running |
| Agent loop (`backend/agent.py`) — core while loop | Ollama reachable + MCP mounted |
| Context assembler (`backend/context_assembler.py`) | DB tables exist |
| API routes — `/sessions`, `/plans`, `/actions`, `/scan`, `/health` | Agent loop working |
| SSE streaming — token stream from Ollama to browser | API routes done |
| Frontend HTML/JS — message input, plan display, approve/reject buttons | API routes done |

---

### What Phase 1 does NOT include (do not build)

- No vector embeddings (`pgvector`, `*_embeddings` tables)
- No document reading / OCR / PDF parsing
- No entity/ontology tables (`entities`, `entity_relationships`, `file_entity_links`)
- No voice input or output
- No separate `mcp-server` Docker service
- No Redis
- No complex frontend framework (plain HTML/JS is enough)

---

## Phase 2 — Install the Brain

**Starts**: After Phase 1 demo is passing end-to-end.

### What Phase 2 adds

| Addition | What it enables |
|---|---|
| `pgvector` extension in Postgres | Semantic similarity search in the same DB |
| `memory_event_embeddings` table + embedding pipeline | AIJAH retrieves similar past actions at prompt time |
| `document_extracts` + `document_extract_embeddings` | AIJAH can read PDFs, Word docs, images |
| `entities`, `entity_relationships`, `file_entity_links` | Ontology layer — clients, matters, document types |
| Full context assembler (vector retrieval) | Context packet gains "similar past events" layer |
| Separate `mcp-server` Docker service | MCP server extracted from backend process |
| `nomic-embed-text` model via Ollama | Local embedding model for generating vectors |

### What Phase 2 does NOT include

- No voice
- No browser/computer control
- No reward/learning loop
- No staged ontology proposals (Phase 3)

### Work tracks in Phase 2

#### Track A — Database (infrastructure owner)
- Enable `pgvector` in Postgres Docker image
- Add embeddings tables (migrations `003_add_pgvector.sql`, etc.)
- Add entity tables
- Learn what a vector is conceptually (not math — just: "a list of numbers that represents meaning")
- Understand what embedding queries look like (`<->` distance operator in pgvector)

#### Track B — Backend + Context
- Build embedding pipeline: call `nomic-embed-text` via Ollama, store vectors
- Update context assembler to run vector retrieval on each agent call
- Build `read_document` MCP tool (PDF/Word text extraction)
- Build `search_memory` MCP tool (semantic search over past events)
- Extract MCP server into own Docker service

---

## Phase 3 — Grow the Brain

**Starts**: After Phase 2 memory retrieval is working and producing noticeably better responses.

### What Phase 3 adds

| Addition | What it enables |
|---|---|
| Voice input via Whisper (local) | User can speak to AIJAH |
| Voice output via local TTS | AIJAH can read responses aloud |
| `READ_ALOUD` session mode | Document read-aloud mode (reads files like a podcast) |
| Browser/computer control MCP tools | AIJAH can navigate tabs, open apps |
| Reward system | Model learns from outcomes, not just stores them |
| Staged ontology proposals | Model proposes new entity types; user reviews before merge |
| `environment_actions` table | Tracks browser/app control actions |

---

## Who Owns What

| Area | Owner | Why |
|---|---|---|
| Docker Compose, container config | Partner | Infrastructure — service boundaries, volumes, networking |
| Postgres: migrations, schema, data inspection | Partner | Database side — running SQL, managing volumes, inspecting tables |
| FastAPI backend, agent loop, MCP server | You | Business logic — this is where the AI behavior lives |
| Frontend HTML/JS | You (or shared) | Simple in Phase 1; grows in Phase 2+ |
| MCP tool implementations | You | Tool contracts are defined in TYPE_LEDGER and V1_CONTRACT |
| System prompt and context assembly | You | This is what makes the AI feel smart or dumb |

---

## What Your Partner Should Learn and When

### Before Phase 1 starts
1. Docker Desktop install and basic navigation
2. `docker compose up` and reading `docker compose logs`
3. What `postgres:16` container is — how to connect, how to run a `.sql` file

### During Phase 1
4. Reading and understanding `docker-compose.yml`
5. Using `psql` or a GUI (DBeaver / TablePlus / pgAdmin) to inspect tables
6. Running DB migrations: `psql -h localhost -U aijah -d aijah -f 001_create_enums.sql`
7. Understanding volumes: `pgdata` persists across restarts; how to wipe and rebuild
8. Inserting seed data: write a `seed.sql` file that inserts a test user + device

### Before Phase 2
9. What `pgvector` is — extension to add vector columns to Postgres
10. What an embedding is conceptually — a list of numbers that encodes meaning
11. How to run a new migration without losing existing data

### Phase 2+
12. Redis basics (if we decide to use it for caching sessions or job queues)
13. Understanding `docker network` — how services talk to each other by service name
14. Log aggregation — how to use `docker logs` effectively and read structured JSON logs

---

## Parallel Track Map (Visual)

```
Week 1 (Phase 1):

Track A (Infrastructure)          Track B (Backend)
─────────────────────────────      ──────────────────────────────
Install Docker                 →   (blocked until Docker up)
docker compose up              →   FastAPI scaffold
Pull qwen2.5 model             →   DB connection layer
Run migrations (13 tables)     →   Python enums
Seed test data                 →   MCP tools stub
Verify postgres accessible     →   Agent loop
                                   API routes
                                   SSE streaming
                                   Frontend UI
                                   End-to-end demo test

Week 2+ (Phase 2):

Track A                            Track B
─────────────────────────────      ──────────────────────────────
Enable pgvector                →   Embedding pipeline
Add entity tables              →   Context assembler (vector)
Add embeddings tables          →   read_document tool
Learn vector queries           →   search_memory tool
                                   Extract MCP to own service
```

---

## Key Rule

> Never start Phase 2 work while Phase 1 demo steps are failing.
> Phase 1 is the body. The brain has nowhere to live until the body is working.

---

## Document Map

| Document | When to read it |
|---|---|
| `docs/TYPE_LEDGER.md` | Paste into every Cursor session — it's the single source of truth for all types |
| `docs/V1_CONTRACT.md` | Before writing any Phase 1 code — locks exactly what must exist |
| `docs/STATE_MACHINE.md` | Before building any approval flow, execution logic, or UI state |
| `docs/AGENT_LOOP.md` | Before writing `agent.py` or `context_assembler.py` |
| `docs/VISION.md` | When making architectural decisions or onboarding someone new |
| `docs/PHASE_MAP.md` (this file) | When deciding what to build next, or who should work on what |
