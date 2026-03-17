# AIJAH

AIJAH is a local-first AI assistant designed to help manage, reorganize, and understand files — built around a clean approval-driven architecture where the model proposes actions, the user approves them, and the system executes them safely, with full audit history and no hard deletes. The stack runs entirely on your machine via Docker Compose (FastAPI + Ollama + PostgreSQL + MCP) and is designed to grow in phases from a file librarian into a broader personal assistant with voice, document reading, and semantic memory.

## Foundation Documents

| Document | Purpose |
|---|---|
| [docs/VISION.md](docs/VISION.md) | Long-range vision — all phases, memory model, MCP primitives, safety model, future capabilities |
| [docs/V1_CONTRACT.md](docs/V1_CONTRACT.md) | Phase 1 locked contract — exact services, tables, API routes, MCP tools, demo flow |
| [docs/TYPE_LEDGER.md](docs/TYPE_LEDGER.md) | Type & enum ledger — all enums, payloads, state machines, tool contracts (paste into every session) |
| [docs/STATE_MACHINE.md](docs/STATE_MACHINE.md) | State machines — session, plan, and action states with transitions, guards, and UI rules |
| [docs/AGENT_LOOP.md](docs/AGENT_LOOP.md) | Agent loop — loop anatomy, context assembly, MCP tool call cycle, observability |
| [docs/PHASE_MAP.md](docs/PHASE_MAP.md) | Phase map — what gets built in what order, who owns what, what runs in parallel |

## How to Use These Docs

At the start of any new Cursor session working on AIJAH:

1. Paste `docs/TYPE_LEDGER.md` into context — this prevents type drift across sessions
2. Reference `docs/V1_CONTRACT.md` to know what phase you're building and what is deferred
3. Reference `docs/VISION.md` only when making architectural decisions

## Stack (Phase 1)

```
frontend      :3000   Static HTML/JS UI
backend       :8000   FastAPI orchestrator + agent loop + MCP server (FastMCP at /mcp)
postgres      :5432   PostgreSQL — all structured state
ollama        :11434  Local LLM runtime (qwen2.5)
```
