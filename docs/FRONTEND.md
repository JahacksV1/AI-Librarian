# Frontend Architecture (Canonical)

This document is the set-in-stone frontend contract for AIJAH.

## Stack

- Build tool: Vite
- UI framework: React
- Language: TypeScript
- App shape: Single-page dashboard (Plan left, Conversation right, Activity bottom)

## Why this stack

AIJAH is a local-first interactive dashboard with SSE updates from FastAPI. It does not need SSR or multi-page routing, so Vite + React + TypeScript is the cleanest fit.

## Layered Architecture

Three layers only:

1. Components (UI only)
2. Hooks (state + behavior)
3. API/SSE utilities (network only)

Rule: components do not fetch; hooks do not render; API utilities do not own state.

## Folder layout

- `frontend/src/components`: presentational components and shell layout
- `frontend/src/hooks`: state orchestration and event routing
- `frontend/src/lib`: HTTP + SSE utilities
- `frontend/src/types`: shared TypeScript domain and wire types
- `frontend/src/demo`: isolated demo data and demo mode switch
- `frontend/src/styles`: global and panel styles

## Status model

Use a single enum-like state for UI transitions:

- `connecting`
- `idle`
- `streaming`
- `scanning`
- `awaiting_approval`
- `executing`
- `complete`
- `error`

Do not use multiple booleans for loading/success/error.

## SSE contract

Frontend must support these events from backend:

- `token`
- `message_complete`
- `tool_call`
- `tool_result`
- `plan_created`
- `action_executed`
- `execution_complete`
- `error`

This contract is provider-agnostic (Ollama, Anthropic, OpenAI).

## Demo mode (easy on/off)

Demo mode exists only for UI iteration and can be disabled without deleting files.

Enable demo mode by either:

- `VITE_DEMO_MODE=true` in frontend env, or
- app URL query param `?demo=1`

Disable demo mode by removing query param and setting `VITE_DEMO_MODE=false` (or unset).

When disabled, frontend uses real backend data only.

## UI principles

- Neutral professional visual style
- Low visual noise, clear hierarchy
- Explicit empty states and error states
- Keep components small and single-purpose

## Backend integration

- FastAPI runs on `http://localhost:8000`
- Vite runs on `http://localhost:3000`
- Frontend uses `/api/*` and Vite proxy rewrites to backend routes
- Streaming endpoints remain `text/event-stream`

## Implementation boundaries

- `frontend/` is the only active frontend codebase.
- Legacy frontend docs were removed intentionally.
