# AIJAH — Caprices Branch Handoff

> Branch: `caprices`
> Commit: `68f7569`
> Date: April 2–3, 2026
> Authors: Caprise + Amira + AI session
>
> This document is a complete handoff for a new chat or a new collaborator.
> It explains the problem we were solving, every decision made, every file changed,
> and what the architecture looks like now versus before.

---

## 1. The Problem We Were Solving

### Immediate symptom

The app was crashing with **HTTP 400 errors after only two messages**. The model provider (Anthropic Claude) was rejecting calls because the input context was too large.

### Why it was happening

Every time the user sent a message, the backend assembled a context packet and sent it to the model. That packet included:

- A long system prompt
- Policies, preferences, task state
- The last N session messages including all tool results
- The last scan summary

The critical failure point: `scan_folder` returns a raw JSON payload that can contain **thousands of file and folder entries**. That payload was being:

1. Persisted verbatim to `session_messages` in the database
2. Appended verbatim to the in-memory `messages` list the model sees
3. Reloaded from the database on the very next turn and put back into context

One scan + one follow-up = two turns with the same giant payload in context = 400 error.

### The deeper problem

Beyond the immediate crash, the architecture had three connected issues the reset plan identified:

1. **No compaction**: Tool output was never summarized or stripped before being fed back to the model. Re-fetchable data was treated as permanent reasoning memory.

2. **No persistent working memory for scope**: After a scan, the model had no structured record of "I just indexed this path." It would rescan on follow-up questions instead of querying the indexed database.

3. **No service boundaries**: `scan_folder.py` was doing filesystem walking, DB upserts, change detection, category guessing, content previews, payload shaping, and duplicate heuristics all in one file. One file doing 20 jobs.

### The UI problem

The frontend was dumping raw JSON into every tool message in the conversation. There was no visual difference between a scan call, a retrieval call, a plan proposal, or an error. Developers and users both had no way to see what was actually happening.

---

## 2. Research Basis for the Decisions

Before making changes, the session researched current agent-memory patterns from OpenAI, Anthropic, and LangGraph. The key finding:

> Production agents separate context into three complementary layers. All three are needed. None can substitute for the others.

**Trimming** — keep a bounded recent window (already existed: `CONVERSATION_WINDOW_MESSAGES = 20`). Trimming alone is not enough if a single recent tool result is larger than the window budget.

**Compaction** — reduce what stays in context after tool calls. Anthropic's official guidance calls this "tool-result clearing": if the model can re-fetch data by calling a tool again, drop the large payload and keep only the record that the call happened. This is the fix for the 400 errors.

**Persistent memory** — store reusable knowledge outside the active prompt so it can be loaded back selectively. For AIJAH this means using the existing database tables (`task_state`, `scans`, `file_entities`, `folder_entities`) as the real memory layer instead of the transcript.

The research also confirmed:
- Bigger context windows make the problem worse, not better (context rot degrades quality before the hard limit)
- Embedding/vector search is correct for Phase 2, not Phase 1 — the current bottleneck is replaying structured data, not missing semantic retrieval
- Planning should be gated behind explicit user intent; analysis should flow freely

---

## 3. Memory Model Established

The session defined four explicit memory layers for AIJAH. This is the canonical reference going forward:

### Layer 1: Canonical Transcript (`session_messages`)

- **What it is**: Complete record of every user message, assistant message, and tool result
- **What writes it**: `loop.py` on every turn
- **What reads it**: The UI (conversation display), provider tool-call replay (Anthropic requires verbatim tool history), audit/debugging
- **What it is NOT**: The model's primary reasoning memory
- **Key rule**: Raw tool results are stored here in full. The model sees compacted versions.

### Layer 2: Working State (`task_state`)

- **What it is**: Small structured per-session state object
- **Fields**: `goal`, `current_step`, `active_plan_id`, `scratchpad_summary`, `active_entities_json`, `pending_action_ids_json`
- **What writes it**: The agent loop (state transitions), the model via `update_task_state` tool
- **New in this session**: `active_entities_json["scope"]` is now written by the loop after every scan, making it a **persistent analysis scope** (see Section 5 below)
- **Key rule**: Must stay small. Never duplicate full plan JSON here.

### Layer 3: Indexed Filesystem Memory (`scans`, `file_entities`, `folder_entities`)

- **What it is**: Durable structured knowledge of what files and folders exist
- **What writes it**: `scan_folder` tool on every scan
- **What reads it**: `query_indexed_files` tool on every analysis follow-up
- **Key rule**: This is the main reusable memory outside the active prompt. After a path is scanned, all follow-up analysis questions should go through retrieval, not another scan.

### Layer 4: Audit and Execution Memory (`memory_events`, `plans`, `plan_actions`)

- **What it is**: Immutable record of what was proposed, approved, executed, and what the outcome was
- **What writes it**: `execute_action` and plan flow
- **What reads it**: Anti-repeat guardrails in `propose_plan`, the UI's plan panel
- **Key rule**: Safety-critical. Never bypass.

---

## 4. Every File Changed and Why

### Backend

---

#### `backend/agent/context.py` — MAJOR CHANGES

**What changed:**

1. **System prompt rewritten** — Added an explicit "Active analysis scope" reference. The model is now told: if you see `Active analysis scope` in the task state, that path is already indexed. Use `query_indexed_files` before rescanning. The retrieval-first decision policy was also tightened to reference the scope directly.

2. **`compact_tool_result_for_model()` added** — This is the compaction function. It takes a tool name and raw result dict, and returns a stripped version safe for the model's context window. For `scan_folder` it:
   - Removes the full `files` list (ROOT) or `file_sample` list (DEEP/CONTENT)
   - Removes the full `folders` list
   - Replaces them with `file_sample` (max 20) and `folder_summaries` (max 25, name + count only)
   - Adds `file_sample_note` and `folders_note` if truncation happened
   - For all other tools, passes through unchanged (already bounded)

3. **`_session_message_to_dict()` updated** — When loading TOOL messages from the database for context assembly, the compaction function is now applied. This means the windowed context on turn 2 does not re-expand from the full DB record.

4. **`_format_task_state()` rewritten** — Now extracts `active_entities_json["scope"]` and renders it as a separate human-readable "Active analysis scope" block below the JSON state. The scope block shows: path, scan_depth, scan_id, scanned_at, indexed counts, and top categories.

5. **Constants**: `_MODEL_REPLAY_MAX_FILES = 20` and `_MODEL_REPLAY_MAX_FOLDERS = 25`

**Why**: Context compaction is the primary fix for the 400 errors. This file is where context is assembled, so this is where the compaction lives. The scope block is the persistent memory layer — it survives across turns because it lives in `task_state`, not the transcript.

---

#### `backend/agent/loop.py` — SIGNIFICANT CHANGES

**What changed:**

1. **Import added**: `compact_tool_result_for_model` imported from `agent.context`

2. **`datetime, timezone` import added** — needed for writing `scanned_at` to the scope

3. **`_estimate_context_tokens()` added** — character-count heuristic (chars / 4 ≈ tokens) for logging. Returns an int.

4. **`_tool_result_message()` updated** — Now calls `compact_tool_result_for_model` before serializing the result for the in-memory `messages` list. The full raw result is still persisted to the DB separately.

5. **`_update_state_for_tool_result()` signature changed** — Added `tool_args: dict | None = None` parameter. After a scan completes, it now builds and writes an analysis scope to `task_state.active_entities_json["scope"]`:
   ```python
   scope = {
       "path": path,          # from tool_args["path"]
       "scan_id": ...,        # from result["scan_id"]
       "depth": ...,          # from result["scan_depth"]
       "categories": ...,     # from result["categories"]
       "file_count": ...,
       "folder_count": ...,
       "scanned_at": datetime.now(timezone.utc).isoformat(),
   }
   await update_task_state(..., active_entities_json={"scope": scope})
   ```

6. **Call site updated** — The `_update_state_for_tool_result(...)` call in `run_agent_loop` now passes `tool_args=tool_call.arguments`.

7. **Context logging updated** — `agent_loop.context` log now includes `estimated_tokens`. New `agent_loop.context_after_tool` log event added after each tool result is appended, showing `message_count` and `estimated_tokens` so context growth is visible per iteration.

**Why**: The loop is the execution path. Compaction must happen here (not just in context assembly) because the in-memory `messages` list is what the model sees within a single multi-tool turn. Writing scope to `task_state` here is the persistent memory write — it happens immediately after a scan completes and before the next model call.

---

#### `backend/tools/update_task_state.py` — MINOR CHANGE

**What changed:**

Added `active_entities_json: dict | None = None` parameter. When provided, it merges into the existing JSONB field using `.update()` rather than replacing it wholesale:

```python
if active_entities_json is not None:
    current = task_state.active_entities_json or {}
    current.update(active_entities_json)
    task_state.active_entities_json = current
```

**Why**: The loop writes `{"scope": {...}}` after a scan. The model can write its own keys to `active_entities_json` via the MCP tool. Merging instead of replacing ensures neither overwrites the other.

---

#### `backend/tools/scan_folder.py` — SIGNIFICANT CHANGES

**What changed:**

1. **Import section rewritten** — Intelligence helpers removed from the file. Now imports from `services.scan_intelligence`:
   ```python
   from services.scan_intelligence import (
       build_file_payload,
       build_folder_payload,
       guess_category,
       read_content_preview,
   )
   ```

2. **Removed inline code**:
   - `_CATEGORY_KEYWORDS` (list of 12 keyword-to-category mappings)
   - `_TEXT_EXTENSIONS` (frozenset of text file extensions)
   - `_PREVIEW_MAX_BYTES`, `_PREVIEW_CHARS`
   - `_guess_category()` function
   - `_read_content_preview()` function
   - `_to_iso()` function
   - `_folder_payload()` function
   - `_file_payload()` function

3. **New constants added**:
   ```python
   _FILE_SAMPLE_LIMIT = 20     # max file entries returned in any scan payload
   _FOLDER_SAMPLE_LIMIT = 50   # max folder entries returned in any scan payload
   ```

4. **ROOT return payload changed**: Previously returned `"files": [full list up to 5000]`. Now returns `"file_count"` (total) + `"file_sample"` (capped at 20) + `"file_sample_note"` if truncated. Folder list also capped at 50.

5. **DEEP/CONTENT return payload changed**: Previously returned all folder payloads. Now capped at `_FOLDER_SAMPLE_LIMIT = 50` with `"folders_note"` if truncated.

6. **`_count_immediate_children()` kept inline** — This is scan-specific logic, not a general intelligence helper.

7. **Call sites updated**: All `_guess_category()` → `guess_category()`, `_read_content_preview()` → `read_content_preview()`, `_file_payload()` → `build_file_payload()`, `_folder_payload()` → `build_folder_payload()`.

**Why**: Two separate reasons. The payload bounds fix the 400 errors at the source — even if something in the loop misses compaction, the tool itself now produces safe output. The service extraction gives `scan_folder.py` one job: orchestrate the scan pipeline. It no longer needs to know how to guess a category or render a file dict.

---

#### `backend/services/scan_intelligence.py` — NEW FILE

This file was created as `backend/services/__init__.py` + `backend/services/scan_intelligence.py`.

**Contents:**

- `guess_category(filename, extension) → str` — keyword + extension lookup, returns category name
- `read_content_preview(file_path, extension) → str | None` — reads first 200 chars of text files
- `find_duplicate_candidates(file_entities) → list[dict]` — groups files by (filename, size_bytes), returns groups with >1 member. Labeled as "heuristic — not content-verified."
- `build_file_payload(file_entity) → dict` — compact file summary dict for model-facing payloads
- `build_folder_payload(folder_entity, child_count, file_count, categories_present) → dict` — compact folder summary dict

**Why**: These are pure functions with no side effects and no database access. They were buried inside a 400-line file that also owned the full scan pipeline. Extracting them makes testing straightforward and keeps the concern of "how to describe a file to the model" separate from "how to scan a directory."

---

#### `backend/tools/query_indexed_files.py` — NEW FILE

**What it does**: Lets the model query `file_entities` and `folder_entities` from the database without scanning the filesystem. Supports:

- `path_prefix` filter (sandbox-validated)
- `entity_type`: `"file"` or `"folder"`
- `extension`, `category`, `min_size_bytes`, `max_size_bytes`, `exists_now` filters
- `sort_by`: name, size, modified_at, extension, path
- `sort_order`: asc / desc
- `limit`: clamped to max 100
- `include_counts`: returns aggregate breakdowns (by_category, by_extension, total_size_bytes for files; by_parent_path for folders)

**Returns**: `entity_type`, `total_matching`, `returned`, `results` list, optional `counts`.

**Constants**: `_MAX_LIMIT = 100`, `_DEFAULT_LIMIT = 25`, `_AGGREGATE_TOP_N = 25`

**Why**: This is the most important missing tool in the architecture. Without it, the only way to answer "what are the biggest PDFs?" or "what categories exist here?" is to rescan or read raw transcript. With it, every follow-up analysis question can be answered from the indexed database in milliseconds, with no context cost beyond the compact result.

---

#### `backend/mcp_server.py` — MINOR CHANGES

**What changed:**

1. Added `query_indexed_files_tool` registration with full description and all parameter schemas.
2. Updated `propose_plan` description to clarify it is for real changes only, not analysis.

---

#### `backend/api/routes.py` — MINOR CHANGES

**What changed:** Removed the deprecated `POST /scan` REST endpoint and `ScanRequest` model. This endpoint bypassed the MCP architecture and was marked non-canonical.

---

#### `docker-compose.yml` — MINOR CHANGE

**What changed:** Added `SANDBOX_ROOT=/Users/amira/AIJAH/AI-Librarian/sandbox` to the backend service's `environment` section.

**Why**: The backend in Docker uses `SANDBOX_ROOT` only to build the system prompt (telling the model what path prefix to use). The native MCP server, which actually touches the filesystem, runs outside Docker with the real host path. These two must match exactly or the model will call tools with `/sandbox` and the MCP server will reject them as out-of-sandbox. The `environment` override in compose takes precedence over the `.env` file's `/sandbox` value.

---

### Frontend

---

#### `frontend/src/types/ui.ts` — MINOR CHANGE

**What changed:** Added two optional fields to `ConversationMessage`:

```typescript
toolName?: string    // which tool this message belongs to
isResult?: boolean   // true = tool_result, false = tool_call
```

**Why**: `MessageBubble` needs to know which tool produced a message to decide how to render it. The content field alone is raw JSON with no structural marker.

---

#### `frontend/src/hooks/useSSE.ts` — MINOR CHANGE

**What changed:** Both `tool_call` and `tool_result` cases in `routeEvent` now populate `toolName` and `isResult` when creating the `ConversationMessage` object.

---

#### `frontend/src/components/conversation/MessageBubble.tsx` — SIGNIFICANT REWRITE

**Before**: All tool messages rendered as `<details><summary>Title</summary><pre>raw JSON</pre></details>`.

**After**: Branches on `toolName` and `isResult`:

- `scan_folder` + `isResult=true` → `<ScanResultCard>`
- `query_indexed_files` + `isResult=true` → `<RetrievalResultCard>`
- Any tool + `isResult=false` (tool call, not result) → compact one-liner `<details>` with italic label (e.g. "Scanning /sandbox/Downloads…")
- Everything else → original collapsible details with raw JSON

Also accepts and passes down `onSuggest?: (text: string) => void` for follow-up chips.

---

#### `frontend/src/components/conversation/ScanResultCard.tsx` — NEW FILE

Renders a scan result as a structured card. Shows:

- Header with folder icon, "Scan complete" title, depth badge (Root / Deep / Content)
- Stats row: file count, folder count, new files (+), deleted files (-)
- Category chips (up to 6, sorted by count)
- Top folders list (up to 8, with child/file count)
- File sample list (up to 5)
- Truncation notes if lists were capped
- Follow-up suggestion chips: "Show the largest files", "Show files by category", "Go deeper into [first folder]", "Find potential duplicate files"
- "Show raw data" / "Hide raw data" toggle — raw JSON always available for debugging

---

#### `frontend/src/components/conversation/RetrievalResultCard.tsx` — NEW FILE

Renders a `query_indexed_files` result as a structured card. Shows:

- Header with magnifying glass icon and human-readable query description (e.g. ".pdf files under Downloads sorted by size desc")
- Stats row: total matching, returned, total size (if counts requested)
- Category chips from `counts.by_category`
- Result list (up to 8 items) with name and size
- Truncation note if results were capped
- Follow-up suggestion chips: "Show more results", "Find duplicates among these files", "Show category breakdown", "Scan deeper into [path]"
- "Show raw data" toggle

---

#### `frontend/src/components/conversation/ConversationPanel.tsx` — MINOR CHANGE

**What changed:** Passes `onSuggest` down to each `MessageBubble`:

```tsx
onSuggest={disabled ? undefined : (text) => void onSend(text)}
```

When a suggestion chip is clicked, it calls `onSend` with the prefilled text string. If the session is disabled (scanning, executing), chips are rendered but non-functional.

---

#### `frontend/src/styles/panels.css` — SIGNIFICANT ADDITIONS

Added ~180 lines of CSS for:

- `.tool-card` base layout (scan and retrieval cards share this)
- `.tool-card-header`, `.tool-card-icon`, `.tool-card-title`
- `.tool-card-stats`, `.stat`, `.stat-value`, `.stat-label`, `.stat-new`, `.stat-deleted`
- `.tool-card-categories`, `.category-chip`, `.category-count`
- `.tool-card-section`, `.tool-card-section-label`
- `.folder-list`, `.folder-list-item`, `.folder-name`, `.folder-count`
- `.file-list`, `.file-list-item`, `.file-name`, `.file-size`
- `.tool-card-note`, `.tool-card-empty`
- `.tool-card-suggestions`, `.suggestion-chips`, `.suggestion-chip` (with hover state)
- `.tool-card-raw-toggle`, `.tool-card-raw`
- `.msg-tool-call`, `.tool-call-label`

---

### Documentation

---

#### `docs/Architecture Reset Plan` — NEW FILE (committed)

This is the original architecture analysis document written by Caprise. It defines:

- What AIJAH currently looks like (puzzle map)
- What is already solid
- Where the connections are weak (scan+understanding mixed, loop relies on transcript weight, under-queried memory)
- Seven memory layer definitions (session_messages, task_state, scans, file_entities, folder_entities, memory_events, user_preferences)
- Minimum strong tool set definition
- Proposed boundary changes
- Plan workstreams

This document is the "why we did this at all" reference.

---

#### `docs/ARCHITECTURE_RESET_IMPLEMENTATION.md` — NEW FILE (committed)

The implementation guide that translates the Architecture Reset Plan into executable steps for the current codebase. Covers:

- Core decision: scan = indexer, retrieval = analysis, plan = only for real changes
- What was wrong (3.1 transcript weight, 3.2 under-queried memory, 3.3 overloaded scan_folder, 3.4 too much planning)
- Current vs target reality
- Tool model (current + missing `query_indexed_files`)
- Phase 1 build plan (Stages A–E)
- Verification goals (4 scenarios)
- Known limits (scan_folder still mixed, duplicate detection heuristic-only, no content_hash yet)

---

#### `docs/AGENT_LOOP.md` — MAJOR REWRITE

The previous version described an Ollama-only loop with full transcript replay. It was significantly outdated.

The new version documents:

- Current loop behavior: windowed context, compaction, scope writing, provider-agnostic
- Four memory layers table
- What is NOT in hot context (by design)
- Analysis scope format and lifecycle
- Tool-result compaction: where it's applied and what it strips
- Tool registry table (all 7 tools, system-injected params)
- Observability events: `agent_loop.context`, `agent_loop.model_response`, `agent_loop.tool_call`, `agent_loop.tool_result`, `agent_loop.context_after_tool`
- Provider support summary

---

#### `docs/STATE_MACHINE.md` — MINOR UPDATE

Updated `PLAN_READY` state description to "Legacy/optional intermediate state; not required in the retrieval-first flow." Updated the session state transition table so `SCANNING → IDLE` is the post-scan transition (not `SCANNING → PLAN_READY` as it was before).

---

#### `docs/TOOL_DISPATCH.md` — SIGNIFICANT ADDITIONS

Added the full `query_indexed_files` contract:

- All 12 LLM-facing parameters with types and descriptions
- `session_id` marked SYS-injected
- Example payload (what LLM sees vs what MCP receives)

Updated the summary table to include `query_indexed_files`. Updated `propose_plan` description notes.

---

## 5. How the Analysis Scope Works End-to-End

This is the most important new behavior. Here is the full flow:

1. User: "Scan my sandbox folder."
2. Model calls `scan_folder(path="/Users/amira/AIJAH/AI-Librarian/sandbox", scan_depth="ROOT")`
3. `scan_folder` indexes the filesystem, returns a result dict with `scan_id`, `scan_depth`, `file_count`, `folder_count`, `categories`, `file_sample` (≤20), `folder_summaries` (≤50).
4. `loop.py` receives the result. Before appending to the model's message list, it calls `compact_tool_result_for_model("scan_folder", result)` — strips large lists, replaces with bounded samples.
5. The compact result is appended to `messages`. The full result is persisted to `session_messages`.
6. `_update_state_for_tool_result()` builds a scope object and calls `update_task_state(active_entities_json={"scope": {...}})`.
7. The scope is now stored in `task_state.active_entities_json["scope"]` in the database.
8. Model responds with a summary and asks what the user wants next. Session state = `IDLE`.
9. User: "What are the biggest files in Downloads?"
10. `assemble_context()` runs. Loads `task_state`. `_format_task_state()` sees `active_entities_json["scope"]`, formats it as an "Active analysis scope" block in the context:
    ```
    Active analysis scope (path already indexed — use query_indexed_files before rescanning):
      path: /Users/amira/AIJAH/AI-Librarian/sandbox
      scan_depth: ROOT
      scan_id: abc123
      scanned_at: 2026-04-03T01:05:07Z
      indexed: 1 files, 39 folders
      categories: unknown(1)
    ```
11. Model sees this in its system context. System prompt says: if you see this, use `query_indexed_files` first.
12. Model calls `query_indexed_files(path_prefix=".../Downloads", entity_type="file", sort_by="size", sort_order="desc")` — **no rescan needed**.
13. Retrieval returns results from the indexed DB. Model answers with concrete file names and sizes.

---

## 6. What Was Verified in Testing

The stack was started and three test scenarios were run successfully:

| Test | Expected | Actual |
|---|---|---|
| Scan sandbox root | `scan_folder` called, indexed 39 folders, compact payload returned, no 400 | ✅ Pass |
| Follow-up: biggest files in Downloads | `query_indexed_files` called first, scan only if data missing, retrieval result returned, no plan proposed | ✅ Pass (retrieval-first, then scan subfolder, then retrieval) |
| Follow-up: category breakdown across all files | `query_indexed_files` with `include_counts=true`, no rescan, no plan, 118 files categorized | ✅ Pass |

No HTTP 400 errors across all three turns.

---

## 7. Known Remaining Issues

### Duplicate path records in the database

The `file_entities` table has records with two different path prefixes: `/sandbox/...` (from a previous MCP server run with `SANDBOX_ROOT=/sandbox`) and `/Users/amira/AIJAH/AI-Librarian/sandbox/...` (from the current MCP server run).

**Fix**: Run `docker compose down -v && docker compose up` to wipe the DB volume and start fresh. Do this once after the path mismatch is resolved.

### `scan_folder` is still a mixed-responsibility tool

Phase 1 accepted this. The indexing logic (DB upserts, change detection) and the payload shaping logic are still in the same function. `scan_intelligence.py` extracted the pure helpers, but the main function still does both jobs. This is the next decomposition target.

### Duplicate detection is heuristic-only

`find_duplicate_candidates()` in `scan_intelligence.py` groups by (filename, size_bytes). It does not use content hashes because `FileEntity.content_hash` is not populated by `scan_folder`. Real deduplication requires content hashing. This is Phase 2.

### The old `compact-tool-replay` todo

The plan's first todo was renamed/merged during implementation. The `compact_tool_result_for_model()` function in `context.py` is the implementation of what that todo described.

---

## 8. Files That Were NOT Changed

The following files were deliberately left alone:

- `backend/tools/propose_plan.py` — safety-critical, no changes needed
- `backend/tools/execute_action.py` — safety-critical, no changes needed
- `backend/tools/read_file_metadata.py` — narrow single-file inspector, fine as-is
- `backend/tools/get_task_state.py` — fine as-is
- `backend/db/models.py` — no schema changes (Phase 1 contract)
- `backend/db/enums.py` — no new enum values needed
- `backend/db/migrations/` — no schema changes
- `frontend/src/components/plan/` — plan panel unchanged
- `frontend/src/components/scan/ScanPanel.tsx` and `ScanSummary.tsx` — already structured, unchanged
- `docs/V1_CONTRACT.md` — locked Phase 1 contract, unchanged
- `docs/DB_ARCHITECTURE.md` — still partially stale but not blocked on it
- `docs/PROVIDER_ARCHITECTURE.md` — accurate, unchanged

---

## 9. How To Run the Stack

### Prerequisites

- Docker Desktop running
- Python 3.12+ for the local virtualenv
- `.venv` created at repo root: `python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt`

### Starting everything

**Terminal 1 — Native MCP server** (must run on host, not in Docker, so it can access the local filesystem):

```bash
cd AI-Librarian/backend
DATABASE_URL=postgresql+asyncpg://aijah:aijah@localhost:5433/aijah \
SANDBOX_ROOT=/Users/amira/AIJAH/AI-Librarian/sandbox \
MCP_MOUNT_PATH=/mcp \
../.venv/bin/python mcp_server.py
```

MCP server starts on `http://0.0.0.0:8001/mcp`.

**Terminal 2 — Docker stack** (backend + frontend + postgres):

```bash
cd AI-Librarian
docker compose up --build
```

First time after the path-mismatch fix, do: `docker compose down -v && docker compose up --build`

- Backend: `http://localhost:8000`
- Frontend: `http://localhost:3003`
- Health check: `curl http://localhost:8000/health`

### Environment

`.env` sets `MODEL_PROVIDER=anthropic` and `MODEL_NAME=claude-sonnet-4-20250514`. The Anthropic API key is already in `.env`. Cloud providers do not need the Ollama service. If you want local Ollama: `docker compose --profile local up`.

---

## 10. What to Work On Next

In priority order:

1. **Clean up duplicate path records**: `docker compose down -v && docker compose up` to wipe stale `/sandbox/...` path entries.

2. **Active scope freshness check**: Currently the model trusts the scope is fresh. Add a staleness check: if `scanned_at` is more than N hours ago, treat it as potentially stale and offer to rescan.

3. **Split `scan_folder` fully**: Separate the indexing pipeline (filesystem walk + DB upsert + change detection) from the payload shaping (what the model gets back). Create `backend/services/scan_indexer.py` for the former, keep only orchestration in `scan_folder.py`.

4. **Content hashing for real deduplication**: Populate `FileEntity.content_hash` during CONTENT-depth scans. Once content hashes exist, `find_duplicate_candidates` can use them for verified deduplication.

5. **UI: scope indicator in the left panel**: Show the currently focused path and scan freshness somewhere visible outside the conversation. The `ScanPanel` already shows scan status from SSE events; extend it to also show the persistent scope from `task_state`.

6. **UI: scan subfolder from result cards**: The `ScanResultCard` shows top folders. Make folder names in that list clickable to trigger a deeper scan directly, instead of requiring the user to type "scan the Downloads folder deeper."

7. **`query_indexed_files` path deduplication**: The retrieval results currently include both `/sandbox/...` and `/Users/.../sandbox/...` paths for the same file because of historical scan data. The deduplication query should filter by `device_id` and optionally by `path_prefix` to avoid showing stale `/sandbox/...` records after the path is fixed.

8. **Update `docs/DB_ARCHITECTURE.md`**: Still describes MCP/agent loop as upcoming. Bring it in line with current shipped state.

---

*Last updated: April 3, 2026. Branch: `caprices`. Commit: `68f7569`.*
