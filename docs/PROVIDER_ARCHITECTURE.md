# AIJAH — Model Provider Architecture

> This document defines the model provider abstraction for Phase 1.5.
> It covers what changes, why, how each piece fits together, and the exact build order.
> Read this before writing any provider code.

---

## Why This Exists

Phase 1 proved the full pipeline works: scan → plan → approve → execute → memory.
The model (`qwen2.5` via Ollama) is the weakest link in plan quality.
We want to swap in stronger models (Claude, GPT-4o) without changing anything else.

The local body (tools, MCP, sandbox, DB) stays the same.
Only the "who is thinking" part changes.

---

## What a Provider Is

A provider is a translator between your backend and a specific LLM API.

Your backend assembles a prompt (messages + tool schemas) and needs back two things:
1. A stream of text tokens (so the frontend can show live typing)
2. A list of tool calls (so the loop can dispatch them via MCP)

Different LLM APIs accept prompts in different formats and return responses
in different formats. A provider handles that translation in both directions.

Everything else — context assembly, MCP dispatch, the agent loop, SSE to the
frontend, DB persistence — is already provider-agnostic and does not change.

---

## The Streaming Pipeline (How Data Flows)

There are two separate streaming connections in the system. They must not be confused.

### Stream A: LLM → Backend (provider-specific)

This is the raw model output. The backend is the **consumer**.

```
LLM API  ──[provider-specific format]──►  Provider class (in backend)
```

- Ollama sends NDJSON (one JSON object per line, `done: true` at end)
- Anthropic sends SSE with event types (`content_block_delta`, `message_stop`)
- OpenAI sends SSE with delta objects (`data: {...}`, `data: [DONE]` at end)

Each provider class knows how to read its own format and extract tokens + tool calls.

### Stream B: Backend → Frontend (always the same)

This is the standardized event stream. The backend is the **producer**.

```
Agent loop  ──[SSE events]──►  Frontend (browser)
```

Format is always SSE (`data: {json}\n\n`).
Event types are defined in `SSEEventType` enum (see TYPE_LEDGER):

| Event Type | What It Carries | When It Fires |
|---|---|---|
| `token` | `{ token: "word" }` | Each token as model generates it |
| `tool_call` | `{ tool: "scan_folder", args: {...} }` | Model decided to call a tool |
| `tool_result` | `{ tool: "scan_folder", result: {...} }` | Tool returned data |
| `plan_created` | `{ plan_id, goal, action_count }` | propose_plan tool wrote a plan to DB |
| `action_executed` | `{ action_id, outcome, action_type }` | An action was executed |
| `execution_complete` | `{ plan_id, succeeded, failed }` | All approved actions finished |
| `message_complete` | `{ message_id, content }` | Model finished its text response |
| `error` | `{ message, detail }` | Something went wrong |

The frontend subscribes to Stream B and routes events to UI panels.
Stream B does not change regardless of which provider generated the tokens.

### Where the provider boundary sits

```
                    PROVIDER BOUNDARY
                          │
context.py ──► messages   │   ┌─────────────────────┐
                          │   │  Provider class      │
tool cache ──► tools      ├──►│  - convert formats   │──► LLM API
                          │   │  - stream response   │◄── (Stream A)
event_callback ──────────►│   │  - emit token events │
                          │   │  - return result     │──► ChatTurnResult
                          │   └─────────────────────┘
                          │
loop.py ◄── ChatTurnResult│
  │                       │
  ├── MCP dispatch        │  (none of this changes)
  ├── DB persistence      │
  └── SSE to frontend     │  (Stream B)
```

---

## Key Terms

| Term | What It Means |
|---|---|
| **NDJSON** | Newline-Delimited JSON. Each line is a complete JSON object. Ollama's streaming format. |
| **SSE** | Server-Sent Events. A standard for streaming data over HTTP. Format: `data: {...}\n\n`. Used by Anthropic, OpenAI, and by our backend-to-frontend stream. |
| **Token** | Roughly one word or word-piece. LLMs generate responses one token at a time. Streaming sends each token as it's generated. |
| **Tool call** | When the model outputs a structured request to run a function instead of (or alongside) text. Contains a function name and arguments. |
| **Wire format** | The exact JSON structure a specific API expects or returns. Each provider has its own wire format. |
| **Provider** | A class that translates between our internal format and a specific LLM API's wire format. |
| **ChatTurnResult** | Our internal type for "what the model returned." Has `.content` (string) and `.tool_calls` (list of ToolCall). Every provider returns this same type. |
| **ToolCall** | Our internal type for a tool invocation. Has `.id` (string), `.name` (string), `.arguments` (dict). |
| **EventCallback** | An async function that accepts a dict payload. The provider calls this for each token event. The loop passes it through to the SSE queue. |

---

## What Differs Per Provider

### Message Format

How the conversation history is structured in the API request.

| Concept | Ollama / OpenAI | Anthropic |
|---|---|---|
| System prompt | `{"role": "system", "content": "..."}` in messages array | Separate `system` parameter outside messages |
| User message | `{"role": "user", "content": "..."}` | Same |
| Assistant text | `{"role": "assistant", "content": "..."}` | Same |
| Assistant with tool call | `tool_calls` array on the assistant message object | `content` array containing `{"type": "tool_use", "id": "...", "name": "...", "input": {...}}` blocks |
| Tool result | `{"role": "tool", "content": "...", "tool_call_id": "..."}` | `{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "...", "content": "..."}]}` |

The provider's job: take our internal messages (which use the Ollama/OpenAI format since that's what context.py produces) and convert them to whatever the API expects.

### Tool Schema Format

How you describe available tools to the model.

| Provider | Format |
|---|---|
| Ollama / OpenAI | `{"type": "function", "function": {"name": "...", "description": "...", "parameters": {json_schema}}}` |
| Anthropic | `{"name": "...", "description": "...", "input_schema": {json_schema}}` — flat, no `function` wrapper |

The inner JSON Schema (the `parameters` / `input_schema` object) is the same across all providers.
The provider's job: unwrap or rewrap the outer envelope.

### Streaming Response

How the model's output arrives over the wire.

**Ollama** — NDJSON:
```
{"message": {"content": "I"}, "done": false}
{"message": {"content": " will"}, "done": false}
{"message": {"tool_calls": [...]}, "done": true}
```

**OpenAI** — SSE:
```
data: {"choices": [{"delta": {"content": "I"}}]}
data: {"choices": [{"delta": {"content": " will"}}]}
data: {"choices": [{"delta": {"tool_calls": [...]}}]}
data: [DONE]
```

**Anthropic** — SSE with typed events:
```
event: content_block_delta
data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "I"}}

event: content_block_start
data: {"type": "content_block_start", "content_block": {"type": "tool_use", "id": "...", "name": "scan_folder"}}

event: input_json_delta
data: {"type": "input_json_delta", "delta": {"partial_json": "{\"path\": \"/sandbox\"}"}}

event: message_stop
data: {"type": "message_stop"}
```

Each provider reads its own format and normalizes it to our internal types.

---

## New Types

### ModelProviderType (add to enums.py and TYPE_LEDGER)

| Value | Meaning |
|---|---|
| `OLLAMA` | Local model via Ollama runtime |
| `ANTHROPIC` | Claude models via Anthropic API |
| `OPENAI` | GPT models via OpenAI API |

This enum is used in config validation only (Phase 1.5).
It is NOT stored in the database. Sessions do not record which provider was used (yet).
When we add per-session model selection (future), it would be stored on the session row.

---

## Config Changes

### New fields in config.py (Settings class)

| Field | Type | Default | Required When |
|---|---|---|---|
| `model_provider` | `str` | `"ollama"` | Always |
| `model_name` | `str` | `""` | Optional — each provider has a default |
| `anthropic_api_key` | `str` | `""` | `model_provider = anthropic` |
| `openai_api_key` | `str` | `""` | `model_provider = openai` |

### Provider defaults when model_name is empty

| Provider | Default Model |
|---|---|
| Ollama | `qwen2.5` |
| Anthropic | `claude-sonnet-4-20250514` |
| OpenAI | `gpt-4o` |

### Backward compatibility

The existing `OLLAMA_URL` and `OLLAMA_MODEL` fields in config.py stay.
`OLLAMA_URL` is still used by the Ollama provider.
`OLLAMA_MODEL` becomes a fallback for `MODEL_NAME` when provider is Ollama.

---

## Docker Changes

### Problem

The `ollama` service is currently a hard dependency of `backend` in docker-compose.yml.
When using a cloud provider, Ollama is unnecessary and wastes 4-8 GB of RAM.

### Solution: Docker Compose profiles

Tag the `ollama` service with a profile so it only starts when requested:

```yaml
ollama:
  profiles: ["local"]     # only starts with: docker compose --profile local up
  image: ollama/ollama
  ...
```

Remove `ollama` from backend's `depends_on`.

Usage:
- `docker compose up` — starts backend, frontend, postgres (cloud provider mode)
- `docker compose --profile local up` — starts everything including Ollama

### Health check changes

`GET /health` currently always checks Ollama. Change to conditional:
- `model_provider = ollama` → check Ollama reachability (existing logic)
- `model_provider = anthropic` → check that `ANTHROPIC_API_KEY` is set
- `model_provider = openai` → check that `OPENAI_API_KEY` is set

Health response gains two new fields:
```json
{
  "status": "ok",
  "db": "connected",
  "model_provider": "anthropic",
  "model_name": "claude-sonnet-4-20250514",
  "model_status": "configured"
}
```

---

## File Structure

### New files

```
backend/
  agent/
    providers/
      __init__.py          # Factory: get_provider() reads config, returns correct provider
      base.py              # Abstract ModelProvider class — the contract
      ollama.py            # OllamaProvider — wraps existing _run_ollama_chat() logic
      anthropic.py         # AnthropicProvider — Claude via official SDK
      openai.py            # OpenAIProvider — GPT via official SDK
```

### Modified files

| File | What Changes |
|---|---|
| `backend/db/enums.py` | Add `ModelProviderType` enum |
| `backend/config.py` | Add `model_provider`, `model_name`, `anthropic_api_key`, `openai_api_key` |
| `backend/agent/loop.py` | Remove `_run_ollama_chat()`. Import `get_provider()`. Call `provider.chat_stream()` in the loop. |
| `backend/main.py` | Add provider config validation at startup (lifespan) |
| `backend/api/routes.py` | Update health check to include provider info |
| `backend/requirements.txt` | Add `anthropic`, `openai` packages |
| `.env.example` | Add new config fields with comments |
| `docker-compose.yml` | Add `profiles: ["local"]` to ollama, remove from depends_on |
| `docs/TYPE_LEDGER.md` | Add `ModelProviderType` enum section |

### Files that do NOT change

- `backend/agent/context.py` — context assembly is provider-agnostic
- `backend/api/sse.py` — SSE formatting is provider-agnostic
- `backend/mcp_server.py` — MCP tool registration doesn't involve the model
- `backend/tools/*.py` — all tool implementations are provider-agnostic
- `backend/db/models.py` — no new tables or columns
- `backend/db/utils.py` — plan status logic doesn't involve the model
- `backend/safety/sandbox.py` — filesystem operations don't involve the model

---

## The Provider Contract (what base.py defines)

```
class ModelProvider:
    async def chat_stream(messages, tools, event_callback) → ChatTurnResult
```

**Inputs:**

- `messages: list[dict]`
  The assembled conversation from context.py. Uses Ollama/OpenAI message format
  (roles: system, user, assistant, tool). The provider converts this internally
  if its API uses a different format.

- `tools: list[dict]`
  MCP tool schemas in OpenAI function-call format (from the tool cache).
  The provider converts this internally if its API uses a different schema envelope.

- `event_callback: async (dict) → None`
  The provider MUST call this with `{"type": "token", "token": "..."}` for each
  token as it arrives from the stream. This is what enables live typing in the frontend.

**Output:**

- `ChatTurnResult`
  Has `.content` (str) — the full text the model generated.
  Has `.tool_calls` (list[ToolCall]) — each has `.id`, `.name`, `.arguments`.
  If the model responded with text only, `tool_calls` is empty.
  If the model responded with tool calls only, `content` may be empty.

**Error handling:**

- Network errors (timeout, connection refused): raise — the loop catches and sets ERROR state
- Auth errors (401, 403): raise with clear message mentioning the API key
- Rate limit (429): raise — future improvement could add retry logic
- Model not found: raise with clear message mentioning MODEL_NAME

---

## Build Order

Each step is a checkpoint. Run the test after steps marked with ✓ to verify nothing broke.

| Step | What | Why | Who |
|---|---|---|---|
| 1 | Add `ModelProviderType` to `enums.py` | New type must exist before anything references it | Backend |
| 2 | Update `docs/TYPE_LEDGER.md` with new enum | Keep ledger as single source of truth | Backend |
| 3 | Update `config.py` — add new fields with Ollama defaults | Config must exist before provider code reads it | Backend |
| 4 | Update `.env.example` — document new fields | Developer reference | Backend |
| 5 | Create `providers/base.py` — abstract class | Contract must exist before implementations | Backend |
| 6 | Create `providers/__init__.py` — factory function | Wiring layer between config and providers | Backend |
| 7 | Create `providers/ollama.py` — extract `_run_ollama_chat()` | Move existing code, zero behavior change | Backend |
| 8 | Update `loop.py` — use `get_provider().chat_stream()` | Remove direct Ollama coupling | Backend |
| **✓** | **Run test_v1.py — must still pass all 9 steps** | **Verify the refactor didn't break anything** | **Both** |
| 9 | Update `main.py` — add startup validation | Fail fast on bad config | Backend |
| 10 | Update health check in `routes.py` | Frontend needs to know active provider | Backend |
| 11 | Update `docker-compose.yml` — Ollama profiles | Make Ollama optional | Infra (Caprice) |
| 12 | Create `providers/anthropic.py` | New capability: Claude | Backend |
| 13 | Create `providers/openai.py` | New capability: GPT-4o | Backend |
| 14 | Update `requirements.txt` | Add SDK dependencies | Backend |
| **✓** | **Test with `MODEL_PROVIDER=anthropic`** | **Verify cloud provider works end-to-end** | **Both** |

---

## Frontend Connection Points

The frontend does NOT need to change for providers to work.
Stream B (backend → frontend SSE) is identical regardless of provider.

When the frontend adds model selection UI later, it needs:

1. **Read current provider**: `GET /health` → `model_provider` and `model_name` fields
2. **Change provider** (future): either restart backend with new `.env` values,
   or add a `PATCH /settings` endpoint that updates user preferences.
   Per-session selection would add `model_provider` field to `POST /sessions`.

The thought panel / stream panel Caprice is building consumes SSE events.
These events have the same types and shapes regardless of which model generated them.
No provider-specific logic needed on the frontend.

---

## What This Does NOT Include

- Per-session model selection (future — requires session schema change)
- Model comparison UI (future — requires running same prompt through multiple providers)
- Cost tracking (future — each provider has different pricing)
- Retry logic for rate limits (future — start with fail-fast)
- Gemini provider (can be added later following the same pattern)
- Any database schema changes (no migrations needed for Phase 1.5)
