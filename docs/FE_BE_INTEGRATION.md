# Frontend ↔ Backend integration (contract + execution plan)

This doc is the **stable contract** between the FastAPI backend and any UI (current Vite JS, future TypeScript, etc.). If something here disagrees with code, treat **this doc as the target** and fix code or the doc in the same PR.

### Frontend module layout (connection layer)

These files are the **back-end boundary**. Prefer renaming them to `.ts` in place over stuffing fetch logic into UI components.

| File | Responsibility |
|------|------------------|
| `frontend/api/config.js` | Resolve API base URL (`VITE_API_BASE`, `window.API_BASE`, dev `/api`). |
| `frontend/api/http.js` | `apiFetch` / `apiJson` + error handling (no route paths here). |
| `frontend/api/backendApi.js` | One exported function per REST endpoint; mirrors §2. |
| `frontend/api/sse.js` | Parse `text/event-stream` from a `fetch` `Response`. |
| `frontend/api/health.js` | Pure helpers: `isHealthOk`, `describeHealthFailure`. |
| `frontend/api/types.js` | JSDoc-only placeholders → becomes `types.ts` or OpenAPI codegen. |
| `frontend/api/client.js` | Optional re-exports from `backendApi.js` (back-compat barrel). |
| `frontend/demo/demoMode.js` | Offline demo; no network. |
| `frontend/main.js` | DOM + panel wiring only; imports `api/*` for I/O. |

---

## 1. Transport & origins

| Mode | Browser origin | API calls | Notes |
|------|----------------|-----------|--------|
| **Dev (recommended)** | `http://localhost:3000` (Vite) | Same-origin to `/api/*` via **Vite proxy** → `http://localhost:8000/*` | Set `VITE_API_BASE=/api`. No CORS required for this path. |
| **Dev (direct to API)** | `http://localhost:3000` | `http://localhost:8000/...` | Requires **`CORS_ORIGINS`** on the backend. |
| **Prod (Docker)** | e.g. `http://localhost:3003` | Compose **`frontend`** image: build with `VITE_API_BASE=/api`, nginx proxies `/api` → `backend:8000` (see **`docs/DOCKER.md`**) | Nginx must **not buffer** `text/event-stream` (`proxy_buffering off`). |

**Streaming:** Agent streams use **POST** endpoints that return `Content-Type: text/event-stream`. The browser **`EventSource` API cannot be used** (GET-only). Use **`fetch` + `ReadableStream`** and parse `data: {...}\n\n` frames (see `frontend/api/sse.js`).

---

## 2. REST contract (paths are relative to API root)

API root is either:

- **Empty** when the UI calls `http://localhost:8000` directly, or  
- **`/api`** when using the Vite proxy (backend sees `/health`, not `/api/health` — the proxy strips `/api`).

| Method | Path | Body | Response |
|--------|------|------|----------|
| GET | `/health` | — | JSON: see §3 |
| POST | `/sessions` | `{ user_id, mode?, title?, device_id? }` | Session object (`id`, …) |
| POST | `/sessions/{session_id}/messages` | `{ content }` | **SSE stream** (not JSON) |
| GET | `/plans/{plan_id}` | — | Plan + actions |
| PATCH | `/actions/{action_id}` | `{ status }` (`APPROVED` / `REJECTED`) | `{ id, status, updated_at }` |
| POST | `/plans/{plan_id}/approve-all` | — | `{ approved_count, plan_id }` |
| POST | `/plans/{plan_id}/execute` | — | **SSE stream** |
| GET | `/scans?session_id=X` | — | List of scan records |
| GET | `/scans/{scan_id}` | — | Single scan with summary |
| GET | `/folders?device_id&path_prefix` | — | Folder entities |

**Default dev user:** The UI may use `user_id = "00000000-0000-0000-0000-000000000001"` until real auth exists; that user must exist in DB (seed/migration).

---

## 3. `/health` JSON (provider-aware)

The UI **must not** assume Ollama-only fields.

| Field | Meaning |
|-------|--------|
| `status` | `"ok"` if DB + model gate pass; else `"degraded"` |
| `db` | `"connected"` / `"disconnected"` |
| `model_provider` | `ollama` \| `anthropic` \| `openai` |
| `model_name` | Effective model id |
| `model_status` | Ollama: `reachable` / `unreachable`; cloud: `configured` / `missing_api_key` |
| `ollama` | Present when `model_provider=ollama` (legacy / UI hints) |

**UI rule:** Treat as unhealthy when `status !== "ok"` **or** when `model_status` indicates failure (`unreachable`, `missing_api_key`, etc.).

---

## 4. SSE event contract (`data: {JSON}\n\n`)

`type` is always present. Aligns with `backend/db/enums.py` → `SSEEventType` and `backend/api/sse.py`.

| `type` | Payload fields (representative) |
|--------|----------------------------------|
| `token` | `token` |
| `message_complete` | `message_id`, `content` |
| `tool_call` | `tool`, `args` |
| `tool_result` | `tool`, `result` |
| `plan_created` | `plan_id`, `goal`, `action_count` |
| `action_executed` | `action_id`, `outcome`, `action_type` |
| `execution_complete` | `plan_id`, `succeeded`, `failed` |
| `scan_started` | `scan_id`, `root_path`, `scan_depth` |
| `scan_complete` | `scan_id`, `file_count`, `folder_count`, `new_files`, `deleted_files`, `categories` |
| `error` | `message`, `detail` |

The UI router (`frontend/state/router.js`) should stay a **thin switch on `type`**; TS migration should preserve these strings as a union type.

---

## 5. Environment variables

### Backend (`.env`)

| Variable | Purpose |
|----------|---------|
| `CORS_ORIGINS` | Optional. Comma-separated list, e.g. `http://localhost:3000,http://127.0.0.1:3000`. Enables `CORSMiddleware` when non-empty. |

### Frontend (Vite)

| Variable | Purpose |
|----------|---------|
| `VITE_API_BASE` | Base path for API. Dev with proxy: `/api`. Direct to FastAPI: `http://localhost:8000`. Prod: set at build time or use `window.API_BASE` in `index.html`. |

---

## 6. Execution roadmap (building blocks)

Check off in order; each step survives framework changes if the contract above is kept.

### Phase A — Connectivity (done / maintain)

1. **Vite proxy** — `/api` → backend, strip prefix so routes match §2.
2. **`VITE_API_BASE`** — Single place for API root in `frontend/api/client.js`.
3. **`CORS_ORIGINS`** — Backend opt-in for direct cross-origin dev.
4. **Health UI** — Use §3 (no Ollama-only checks for Anthropic/OpenAI).

### Phase B — Contract tests (backend-owned)

1. **SSE parser parity** — Reuse the same parsing assumptions as `test_v1.py` / `test_provider_switch.py` (optional: extract shared fixture).
2. **Smoke:** `GET /health` + `POST /sessions` + one `POST .../messages` stream until first `token` or `error`.

### Phase C — Prod Docker

1. **Nginx (or Traefik)** — SPA fallback + `/api` upstream to `backend:8000`; disable proxy buffering for SSE paths.
2. **Align ports** — Document Vite dev (3000) vs Compose `frontend` port (3003) so nobody chases the wrong tab.

### Phase D — Product hardening (later)

1. Auth headers / session cookies once user model exists.
2. Trust gates: only approved actions execute (already modeled in API; UI exposes approve/execute).

---

## 7. Related docs

- `docs/UI_MASTER_PLAN.md` — Product UX and layout (can change independently if §2–§4 stay true).
