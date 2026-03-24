# Phase 1.7 — Delivery handoff (scan architecture)

**Audience:** Anyone picking up AI-Librarian after March 2026 scan work (new chat, partner sync).  
**Git branch:** `feat/phase-1.7-scan-architecture-and-agent-fixes` (merge to `main` when ready).  
**Related living docs:** `TYPE_LEDGER.md` (schema/enums), `FE_BE_INTEGRATION.md` (SSE + REST contract).

---

## 1. What problem we were solving

Scans worked internally but were a **black box**: no durable scan history, category/preview data was not stored, the UI did not show scan results, change tracking was weak, and the model could not rely on **persisted** scan summaries across turns.

**Goals (minimum viable pipeline):**

1. Every scan is a **first-class DB record** with counts, status, and summary.
2. **Categories** (and text **previews** where applicable) persist on **`file_entities`**, not only in the tool JSON.
3. **Change detection:** paths missing after a rescan get **`exists_now = false`**; scan row records **new_files** / **deleted_files**.
4. **Frontend** shows scan lifecycle (counts, categories, new/removed) via **SSE** and can query **REST**.
5. **Context assembler** injects a **“Last scan”** block per **session** so the model can answer without rescanning when appropriate.
6. **Plan → approve → execute** remains the product path; scan work **feeds** that flow (tested end-to-end).

**Explicitly not in this phase:** collapsible folder tree in UI (`FolderTree`), staged scan depths beyond wiring, Alembic-style migrations (see §8).

---

## 2. Architecture (as shipped)

```
User message → Agent loop → MCP scan_folder (runs in mcp-server, /sandbox mounted)
    → INSERT scans (RUNNING) … UPDATE COMPLETED + summary_json
    → Upsert file_entities / folder_entities + guessed_category, content_preview, last_scan_id
    → Mark previously-seen paths under root not in this run: exists_now = false
    → Agent loop emits SSE: scan_started (before tool), scan_complete (after result)
    → Frontend: Scan panel + Activity log
    → Next turn: assemble_context adds “Last scan” from latest Scan for this session_id
```

**Consumers:**

| Consumer | Mechanism |
|----------|-----------|
| DB | `scans`, enriched `file_entities`, `folder_entities` |
| Model | Tool result + **Last scan** system text (session-scoped) |
| UI | `scan_started` / `scan_complete` SSE + optional `GET /scans`, `/folders` |

**Important:** **Last scan** is keyed by **`session_id`**. A **new** chat session has no prior `scans` rows until a scan runs in that session.

---

## 3. Exact changes (by area)

### Database

| Item | Detail |
|------|--------|
| New migration | `postgres/init/004_add_scans.sql` |
| Enums | `scan_status_enum` (RUNNING, COMPLETED, FAILED), `scan_depth_enum` (ROOT, DEEP, CONTENT) |
| Table | **`scans`**: session_id, device_id, root_path, scan_depth, recursive, file/folder counts, new/deleted/modified, timestamps, status, **summary_json** |
| `file_entities` | **`guessed_category`**, **`content_preview`**, **`last_scan_id`** → FK to `scans` |

ORM + Python enums: `backend/db/models.py`, `backend/db/enums.py`.

### Backend — scan tool

| File | Change |
|------|--------|
| `backend/tools/scan_folder.py` | Full lifecycle: create `Scan`, upsert with enrichments, change detection, finalize row + `summary_json`, return rich dict (`scan_id`, `changes`, `categories`, …). Runs on **MCP** where `/sandbox` exists. |

### Backend — API & SSE

| File | Change |
|------|--------|
| `backend/api/routes.py` | `GET /scans?session_id=`, `GET /scans/{scan_id}`, `GET /folders?device_id=&path_prefix=` |
| `backend/api/sse.py` | Payload helpers for `scan_started`, `scan_complete` |
| `backend/db/enums.py` | `SSEEventType.SCAN_STARTED`, `SCAN_COMPLETE` |

Note: **`POST /scan`** still calls `scan_folder` **inside the backend container**, which **does not** mount `./sandbox` in default Compose — prefer **chat + MCP** for real scans. (Optional follow-up: mount sandbox on backend or proxy `/scan` to MCP.)

### Backend — agent loop & context

| File | Change |
|------|--------|
| `backend/agent/loop.py` | Before MCP `scan_folder`: emit **`scan_started`**. After result: emit **`scan_complete`** (counts/categories from tool result). |
| `backend/agent/context.py` | Load latest **`Scan`** for session; format **Last scan** text. **Hoist** `metadata_json.tool_calls` to top-level **`tool_calls`** (OpenAI shape) so Anthropic replay sees **`tool_use`** blocks. |
| `backend/agent/providers/anthropic.py` | **Merge consecutive `role: "tool"`** messages into **one** `user` message with multiple **`tool_result`** blocks (fixes 400 on multi-tool turns, e.g. scan + propose_plan). |

### Frontend

| Path | Change |
|------|--------|
| `frontend/src/components/scan/ScanPanel.tsx`, `ScanSummary.tsx` | Scan results UI |
| `frontend/src/hooks/useScan.ts` | State from SSE |
| `frontend/src/hooks/useActivity.ts` | Log scan events |
| `frontend/src/hooks/useSSE.ts` | **`clearStreamError()`** — reset error UI without new session |
| `frontend/src/App.tsx` | **`left-column-stack`**, wire scan hook, header **Reconnect** vs **Clear error** |
| `frontend/src/components/plan/PlanCard.tsx` / `PlanPanel.tsx` | **Scrollable plan body** + **pinned** Approve All / Execute |
| `frontend/src/components/layout/AppShell.tsx`, `StatusBar.tsx` | Optional **`retryLabel`** |
| `frontend/src/lib/api.ts`, `types/api.ts`, `types/sse.ts`, `styles/panels.css` | Types, `getScans` / `getScan` / `getFolders`, layout CSS |

### Docs & tests

| Path | Role |
|------|------|
| `docs/TYPE_LEDGER.md` | Scans table, enums, SSE events, `file_entities` columns |
| `docs/FE_BE_INTEGRATION.md` | Scan SSE + endpoints |
| `test_phase_17.py` | Automated harness (DB + agent + SSE + REST + change/context checks) |

---

## 4. Alignment with the original plan

The internal plan matched **items 1–6** of the scan architecture spec (table, enrichments, `scan_folder`, SSE/API, context, FE panel). **Item 7** (PROJECT_STATE, V1_CONTRACT) may still be partial — update when you do a doc pass.

**Deferred from plan text:**

- **`FolderTree.tsx`** — not implemented; scan panel shows summary + categories only.
- **SSE from inside `scan_folder` on MCP** — not possible without a callback; **loop** emits scan SSE instead (same user-visible events).

---

## 5. Testing performed

### Automated

- **`python3 test_phase_17.py`** (with Compose up, `httpx` installed): schema, MCP scan via chat, SSE, DB row, enrichments, `/scans` / `/folders`, change-detection branch, context/fallback.

### Manual (browser)

- Scan → panel + activity events.
- **+1 new** / **−1 removed** after add/delete file.
- Follow-up **without** `scan_folder` in same session → answers from **Last scan** (with timestamp).
- **Propose plan → Approve all → Execute** → real files under **`sandbox/`** (host bind-mount to MCP).
- Plan panel **scroll** + visible **Approve All / Execute**.
- **Clear error** after failures without forced new session.

### Fixes validated in the same effort

- Anthropic **400** (orphan `tool_result`): metadata **tool_calls** hoist + merged tool results.
- **429** rate limits: operational; reduce rescans / session size.

---

## 6. Operations / migration note

- **Fresh Postgres volume:** `004_add_scans.sql` runs from `docker-entrypoint-initdb.d` on **first init only**.
- **Existing volume:** init scripts **do not** re-run; apply **`004`** manually once or introduce **Alembic** (recommended long-term) so upgrades never require `docker compose down -v`.

---

## 7. Quick start for a new contributor

1. Read this file end-to-end.
2. Pull branch **`feat/phase-1.7-scan-architecture-and-agent-fixes`** (or `main` after merge).
3. If DB already existed before this migration, apply **`postgres/init/004_add_scans.sql`** or recreate the volume once.
4. `docker compose up --build` — scan via **chat** (“scan /sandbox”), watch **Scan Results** + **Agent Activity**.
5. For contract details: **`docs/FE_BE_INTEGRATION.md`**, **`docs/TYPE_LEDGER.md`**.

---

## 8. Suggested follow-ups (not blocking “1.7 done”)

| Item | Note |
|------|------|
| **Alembic** (or similar) | Apply schema changes on app start / deploy without wiping volumes. |
| **`POST /scan` + sandbox** | Mount `./sandbox` on backend or delegate to MCP so REST scan matches chat. |
| **Execution visibility** | UI: show **from_path → to_path** after execute (today: Activity + `GET /plans/{id}`). |
| **`FolderTree`** | Planned in original UI sketch. |
| **Cross-session “last scan on device”** | Optional; today **Last scan** is **per session_id** only. |

---

*This document replaces the standalone planning narrative in `PHASE_1.7_SCAN_ARCHITECTURE.md` (removed to avoid duplicate sources of truth).*
