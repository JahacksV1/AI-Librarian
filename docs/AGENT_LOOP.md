# AIJAH Agent Loop

> The agent loop is the brainstem of the system.
> Everything else — tools, memory, the database, the UI — is peripheral to it.
> If the agent loop is wrong, everything is wrong.

---

## What the Agent Loop Is

The agent loop is the code that runs every time the user sends a message and expects the AI to do something. It is an iterative cycle:

```
1. Assemble context from DB + memory layers
2. Call the configured provider with that context + available tools
3. Model either responds with text, or requests a tool call
4. If tool call → execute the MCP tool → compact result → append to messages → go back to step 2
5. If text response → stream it to the UI → write to DB → loop ends
```

This is not a one-shot call. It is a loop. The model can call tools multiple times in a single user message — for example: scan folder, then query indexed files, then summarize — all before producing its final text response.

---

## The Loop in Pseudocode

```python
async def run_agent_loop(session_id: str, user_message: str):
    # 1. Persist the user message
    await db.insert_message(session_id, role=USER, content=user_message)

    # 2. Assemble context packet (windowed — see Context Assembly below)
    context = await assemble_context(session_id)
    messages = context.to_messages()  # bounded recent window, not full history

    # 3. Discover available MCP tools (done once at startup, cached)
    tools = get_cached_tool_schemas()  # system-injected params stripped from LLM view

    # 4. Main loop
    while iteration < MAX_TOOL_ITERATIONS:
        # Call the configured provider (Ollama, Anthropic, OpenAI)
        response = await provider.chat_stream(messages, tools, event_callback)

        # Did the model request a tool call?
        if response.tool_calls:
            # Inject system params (e.g. session_id) the model never sees
            for tool_call in response.tool_calls:
                inject_session_params(tool_call)
                result = await mcp.call_tool(tool_call.name, tool_call.args)

                # ── Compaction ────────────────────────────────────────────
                # Persist FULL result to session_messages (for UI / audit).
                # Append only a COMPACT version to the live messages list.
                # This stops large scan payloads from inflating context.
                await db.insert_message(session_id, role=TOOL, content=full_result)
                messages.append(tool_result_message(tool_call, compact_result))
                # ──────────────────────────────────────────────────────────

                # After scan_folder: write analysis scope to task_state (persistent memory)
                if tool_call.name == "scan_folder":
                    await update_task_state(
                        session_id,
                        current_step="IDLE",
                        active_entities_json={"scope": {path, scan_id, depth, categories, ...}},
                    )

            continue

        # No tool calls — model produced a final text response
        await db.insert_message(session_id, role=ASSISTANT, content=response.content)
        break
```

Key points:
- The loop continues as long as the model is requesting tool calls
- Each tool result is compacted before being appended to the live message list
- Full raw results are always persisted to `session_messages` for UI / audit
- After a scan, the loop writes a compact analysis scope to `task_state.active_entities_json`
- Tokens stream to the frontend in real time via SSE during each model call

---

## Context Assembly

The context packet is what the model sees. It is assembled fresh at the start of every user turn from several memory layers.

### Memory layers (current)

| Layer | Source | Role |
|---|---|---|
| System prompt | `context.py` | Rules, sandbox root, retrieval-first policy |
| Policies | `operational_policies` DB table | Active safety/naming rules |
| Preferences | `user_preferences` DB table | User preferences |
| Task state | `task_state` DB table | Working memory: goal, current step, active plan, **analysis scope** |
| Recent memory events | `memory_events` DB table | Last 10 executed actions (anti-repeat) |
| Active plan | `plans` + `plan_actions` tables | Current pending plan if one exists |
| Last scan | `scans` table | Summary of most recent scan |
| Conversation window | `session_messages` table (last 20 rows) | Short-term continuity |

### What is NOT in hot context (by design)

- Full raw tool results — stored in `session_messages` but **compacted** when loaded into the window
- Entire transcript history — windowed to last 20 messages
- Embeddings or semantic memory — deferred to Phase 2

### Analysis scope (persistent working memory)

After every `scan_folder` call, the loop writes a compact scope object to `task_state.active_entities_json["scope"]`:

```json
{
  "path": "/sandbox/Downloads",
  "scan_id": "abc123",
  "depth": "ROOT",
  "categories": {"document": 5, "photo": 3},
  "file_count": 8,
  "folder_count": 3,
  "scanned_at": "2026-04-03T12:00:00Z"
}
```

`context.py` formats this as an "Active analysis scope" block in the task state section. The model sees it on every subsequent turn and uses it to answer follow-up questions via `query_indexed_files` instead of rescanning.

### Tool-result compaction

`compact_tool_result_for_model(tool_name, result)` in `context.py` is applied in two places:

1. In `loop.py`: before appending tool results to the live in-memory message list
2. In `context.py._session_message_to_dict`: when loading TOOL messages from the DB into the windowed context

The compact version strips full file/folder lists while preserving summary stats, categories, and a bounded sample. Full raw results remain in the DB.

---

## Tool Registry

Current tools registered in `mcp_server.py`:

| Tool | Role | Session-injected |
|---|---|---|
| `scan_folder` | Index path into file/folder entities | `session_id` |
| `query_indexed_files` | Retrieve from indexed entities | `session_id` |
| `read_file_metadata` | Inspect one file | — |
| `propose_plan` | Create approval-backed plan | `session_id` |
| `execute_action` | Execute one APPROVED action | — |
| `get_task_state` | Read working state | `session_id` |
| `update_task_state` | Write working state | `session_id` |

See `docs/TOOL_DISPATCH.md` for full parameter classification.

---

## Observability

The loop logs context snapshots at key points. Look for these log events:

- `agent_loop.context` — at the start of each turn: `message_count`, `estimated_tokens`, `tool_count`
- `agent_loop.model_response` — after each provider call: `had_tool_calls`, `tool_names`, `response_length`
- `agent_loop.tool_call` — before each tool dispatch: `tool`, `tool_args`
- `agent_loop.tool_result` — after each tool result: `tool`, `result_preview`
- `agent_loop.context_after_tool` — after each tool result is appended: `message_count`, `estimated_tokens`

The `estimated_tokens` field uses a character-count heuristic (chars / 4). Use it to watch for context growth between iterations and across turns.

---

## Provider Support

The loop is provider-agnostic. All providers implement `chat_stream(messages, tools, event_callback) → ChatTurnResult`. The loop assembles context in OpenAI/Ollama message format; each provider adapter converts to its own wire format and normalizes tool calls back.

See `docs/PROVIDER_ARCHITECTURE.md` for the full provider boundary definition.

