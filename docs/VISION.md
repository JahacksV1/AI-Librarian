# AIJAH — Vision Architecture

> "Build the body first. Then install the brain. Then grow the brain into an adult brain."

---

## What AIJAH Is

AIJAH is a local-first AI assistant. In its first form, it is a file librarian — it scans folders, understands the structure, proposes how to rename and reorganize files, waits for human approval, and then executes those changes safely.

Over time, AIJAH grows into a broader personal assistant with voice, document reading, semantic memory, and eventually a learned model of the user's world — their clients, their matters, their naming habits, their preferences.

Everything runs on the user's machine. No cloud required. No data leaves the device.

---

## The Core Analogy

| Layer | Analogy | What It Means |
|---|---|---|
| File scanner, MCP tools | Eyes & Hands | AIJAH can see the file system and act on it |
| Voice input | Ears | AIJAH can hear spoken instructions |
| Voice output, read-aloud | Mouth | AIJAH can speak responses and read documents |
| Ollama + prompting | Brain (v1) | AIJAH can reason and generate plans |
| Memory system | Growing brain | AIJAH learns from every approved action |

---

## Service Architecture

Five services. One Docker Compose file.

```
┌─────────────────────────────────────────────────────┐
│                   Docker Compose                    │
│                                                     │
│  frontend     :3000   Static HTML/JS UI             │
│  backend      :8000   FastAPI orchestrator          │
│                       + agent loop                  │
│                       + FastMCP server at /mcp      │
│  postgres     :5432   All structured state          │
│  ollama       :11434  Local LLM runtime             │
└─────────────────────────────────────────────────────┘
```

### backend (FastAPI)
- Hosts all REST API routes (`/sessions`, `/plans`, `/actions`, etc.)
- Runs the agent loop: context assembly → Ollama call → tool dispatch → response
- Hosts the MCP server via FastMCP mounted at `/mcp` (Streamable HTTP transport)
- Reads and writes all DB state
- Streams tokens to the frontend via SSE

### mcp-server (FastMCP, inside backend for Phase 1)
- Exposes tools to the agent loop: `scan_folder`, `read_file_metadata`, `propose_plan`, `execute_action`
- The agent loop connects to it via `mcp.ClientSession`
- In Phase 2+, this becomes its own separate service/process for cleaner separation

### ollama
- Runs `qwen2.5` (best local tool-calling model at time of design)
- Receives structured prompts with injected tool schemas
- Emits tool calls which the agent loop dispatches to MCP
- Does not natively speak MCP — a thin adapter in `agent.py` bridges them

### postgres
- Single database for all state: sessions, messages, plans, actions, events, file entities, preferences, policies
- Phase 2 adds `pgvector` extension for semantic search (no separate vector DB ever)

### frontend
- Simple static HTML/JS in Phase 1 — no framework required
- Shows the conversation, current plan, action list with approve/reject buttons
- Receives streaming tokens via SSE

---

## MCP: How Tools Actually Work

MCP (Model Context Protocol) is an open standard — a JSON-RPC 2.0 protocol — that standardizes how AI agents connect to external tools and data sources. It was launched by Anthropic in November 2024 and is now governed by the Linux Foundation's Agentic AI Foundation.

The core insight: before MCP, every AI app needed a custom connector for every tool. 10 AI apps × 20 tools = 200 custom integrations. MCP solves this the same way the Language Server Protocol (LSP) solved the editor-language problem in 2016: write one interface, works everywhere.

### The Three Roles

```
HOST (our backend / agent loop)
  manages the LLM and one or more MCP clients
  └── MCP CLIENT (inside backend)
        1:1 connection to one MCP server
        handles JSON-RPC routing, capability discovery
        └── MCP SERVER (our mcp_server.py)
              exposes tools, resources, and prompts
              runs the actual Python functions
```

### The MCP Session Lifecycle

The connection between the agent loop (MCP client) and the tool server (MCP server) has a strict startup sequence. Violating it causes protocol errors:

```
Phase 1 — INITIALIZATION (blocking, happens once at startup):
  Client → Server: initialize { protocolVersion, capabilities }
  Server → Client: initialize result { capabilities }
  Client → Server: initialized (notification)
  ⚠ No tool calls allowed until this completes.

Phase 2 — NORMAL OPERATION:
  Client → Server: tools/list   (discover available tools)
  Server → Client: list of tool schemas
  Client: caches schemas, converts to Ollama function-call format
  ... (many tool calls happen here, per the agent loop) ...

Phase 3 — SHUTDOWN:
  Either side sends close notification.
```

### The Five MCP Primitives

MCP servers can expose five types of capabilities. AIJAH uses Tools and Roots in Phase 1.

| Primitive | Purpose | AIJAH Use |
|---|---|---|
| **Tools** | Executable functions the model can call ("do things") | `scan_folder`, `propose_plan`, `execute_action` — Phase 1 |
| **Resources** | Addressable read-only data by URI ("read things") | Future: `resource://filesystem/sandbox/...` — Phase 2+ |
| **Prompts** | Reusable parameterized workflow templates | Future: cleanup workflows, naming convention templates |
| **Sampling** | Server asks the AI host to run an LLM completion | Future: autonomous research, self-correcting loops |
| **Roots** | Declares which filesystem paths the server is allowed to touch | `SANDBOX_ROOT` — enforced in Phase 1 |

### Roots: How Path Restriction Is Enforced at Protocol Level

The `Roots` primitive is how AIJAH enforces its sandbox restriction at the MCP level — not just in application code. At startup, the MCP client tells the server:

```json
{
  "roots": [
    { "uri": "file:///sandbox", "name": "Sandbox" }
  ]
}
```

The server respects this boundary. No tool can touch a path outside the declared roots. This is the same mechanism Cursor and VS Code use to restrict MCP servers to only the open workspace.

### Transport: Streamable HTTP

For Phase 1, FastMCP is mounted inside the FastAPI process at `/mcp` using **Streamable HTTP** — the current standard transport that replaced the older standalone SSE transport. A single HTTP endpoint handles both request/response and streaming.

In Phase 2+, the MCP server can be extracted into its own service/process. Because MCP supports remote communication over Streamable HTTP natively, this split requires no changes to the tool implementations — only the connection string changes.

---



AIJAH's memory is not a single thing. It is five distinct layers with different lifetimes and retrieval methods.

```
Layer 1: Current session memory
  What's happening right now. Messages in this conversation.
  Table: session_messages

Layer 2: Working memory (task state)
  What the assistant is actively trying to do.
  Active goal, current step, active plan ID, scratchpad summary.
  Table: task_state

Layer 3: Episodic memory
  Every past plan, action, approval, rejection, success, failure.
  Queryable by time, session, file path, outcome.
  Table: memory_events

Layer 4: Semantic memory (Phase 2)
  Vectorized summaries of memory_events and document extracts.
  Retrieved by embedding similarity at prompt time.
  Tables: memory_event_embeddings, document_extract_embeddings

Layer 5: Structured world model
  Exact facts: file entities, folder entities, user preferences, policies.
  The assistant's map of the user's file system and habits.
  Tables: file_entities, folder_entities, user_preferences, operational_policies
```

### Context Packet Assembly (Phase 2+)

Before every LLM call, a context assembler builds the prompt from these layers:

- **Always included**: active session summary + task_state + relevant policies + user preferences
- **Vector-retrieved**: top similar past memory_events + document extracts
- **Optional**: most recent failed attempts, most recent approved similar plans

The model must return structured grounding with every plan:
```json
{
  "goal": "organize invoices folder",
  "reasoning_summary": "...",
  "evidence": {
    "memory_events": ["uuid of relevant past event"],
    "preferences": ["prefers client-matter folder structure"],
    "entities": ["uuid of client entity"]
  },
  "actions": [...]
}
```

---

## The Approval & Safety Model

Every file action must pass through an approval gate. The gate is the database — not logic, not flags, not in-memory state.

```
Plan generated → status: DRAFT
Plan shown to user → status: PENDING
User clicks Approve → status: APPROVED
Executor reads DB → only executes APPROVED actions
User clicks Reject → status: REJECTED (never executed)
Execution completes → status: EXECUTED
Partial completion → status: PARTIAL
```

### Safety Rules (non-negotiable, Phase 1)

1. **No hard deletes.** All file removal operations use trash/archive. Files are moved to a `.aijah_archive` folder with a timestamp, never permanently deleted.
2. **Root path restriction.** All operations are restricted to a configured sandbox root path. The agent cannot touch files outside this root.
3. **Approval required before execution.** The executor reads `status = APPROVED` from the DB before touching any file. There is no way to bypass this from the UI.
4. **Pre/post state written to memory_events.** Every execution writes what the file looked like before and after. This enables undo.
5. **Staged ontology proposals.** When the model wants to create a new entity type or tag, it proposes it. Proposals are never auto-merged into the world model.

---

## Phase Breakdown

### Phase 1 — The Body
*Build and verify the body works.*

The goal is correct behavior and clean architecture — not "feels as smart as ChatGPT."

What Phase 1 delivers:
- Docker Compose stack boots
- Backend talks to Ollama (tool-calling works)
- Backend reaches MCP tools
- Filesystem scan works on a sandbox folder
- Plan generation works
- Approve/reject works in the UI
- Execute approved rename/move/create-folder works
- Session/messages/plan/action/event persistence works
- Simple browser UI works (streaming tokens visible)

What Phase 1 explicitly excludes:
- Vector embeddings (no pgvector yet)
- Document reading/OCR
- Entity/ontology tables
- Voice input/output
- Semantic retrieval in context assembly
- Browser/computer control

### Phase 2 — Install the Brain
*Make AIJAH progressively smarter by activating memory retrieval.*

What Phase 2 adds:
- `pgvector` extension enabled
- `memory_event_embeddings` table and embedding pipeline active
- `document_extracts` and `document_extract_embeddings` for reading files
- Full context packet assembler running (vector retrieval at prompt time)
- `entities`, `entity_relationships`, `file_entity_links` for ontology
- AIJAH starts recognizing client/matter patterns and naming conventions
- Model quality improves noticeably from episodic retrieval

### Phase 3 — Grow the Brain
*Expand input/output modalities and deepen learning.*

What Phase 3 adds:
- Voice input (transcription via Whisper)
- Voice output / read-aloud (ElevenLabs or local TTS)
- Browser/tab control for computer assistance
- Reward system: the model learns from outcomes, not just stores them
- Advanced ontology: triple-store style entity relationships
- Staged ontology proposals with user review flow
- Broader computer assistance beyond the file system

---

## Key Architectural Decisions

| Decision | Choice | Reason |
|---|---|---|
| Backend framework | FastAPI | Async, fast, clean OpenAPI docs, easy SSE |
| Local LLM | Ollama / qwen2.5 | Best local tool-calling benchmark at design time |
| MCP transport | Streamable HTTP (FastMCP) | Modern standard; SSE transport is deprecated |
| Database | PostgreSQL | Structured + vector (pgvector) in one DB |
| Streaming | SSE (not WebSocket) | Simpler for one-directional token streaming |
| File deletion | Trash/archive only | Safety — no data loss |
| Embeddings deferred | Phase 2 | Keeps Phase 1 simple and testable |
| MCP in-process (Phase 1) | FastMCP mounted at /mcp | Easier development; split to own service in Phase 2+ |

---

## Long-Term Vision

AIJAH is not just a file tool. It is the foundation of a personal AI body that knows its user deeply:

- **File librarian** — understands folder structure, client/matter naming, document types
- **Document reader** — can read, summarize, and extract from PDFs, Word docs, images
- **Voice companion** — can hear and speak; reads documents aloud like a podcast
- **Computer assistant** — can control browser tabs, open apps, navigate interfaces
- **Memory system** — learns from every approved action; builds a model of the user's world
- **Ontology builder** — understands relationships between clients, matters, documents, people, dates
- **Scheduler/planner** — eventually integrates calendar, deadlines, follow-up reminders

The architecture is designed so that each of these capabilities can be added as new MCP tools and new memory layers — without rebuilding the core.
