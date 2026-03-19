# AIJAH Tool Dispatch Contract

> The agent loop is the bridge between the LLM and MCP tools.
> The LLM decides *what* to do. The loop injects *who is doing it*.
> This document defines that boundary for every Phase 1 tool.

---

## Why This Document Exists

MCP tool schemas are sent to the LLM so it can decide which tools to call and with what arguments. But some parameters are **system context** — values the agent loop knows from the current session that the LLM has no way to determine (like `session_id`).

If a system parameter leaks into the LLM's schema, the model will either:
- Omit it (causing a default/empty value → runtime error)
- Hallucinate a value (causing a wrong UUID → data integrity failure)

This document prevents that by classifying every parameter up front.

---

## How It Works

The agent loop performs two operations on every tool call cycle:

### 1. Schema Filtering (before Ollama sees the tools)

When tool schemas are fetched from MCP and converted to Ollama format, **system-injected parameters are stripped** from `properties` and `required`. The LLM never sees them.

### 2. Argument Injection (before MCP receives the call)

When the LLM requests a tool call, the loop **injects system parameters** into the arguments dict before forwarding to MCP. The tool function receives the complete argument set — it doesn't know or care that some came from the LLM and some from the loop.

---

## Parameter Classification

### Legend

| Tag | Meaning |
|-----|---------|
| **LLM** | Model fills this based on user intent. Appears in the Ollama schema. |
| **SYS** | Agent loop injects this from session context. Hidden from the Ollama schema. |

---

## Tool Contracts

### scan_folder

Scan a directory inside SANDBOX_ROOT and write file/folder metadata into the database.

| Parameter | Type | Tag | Source |
|-----------|------|-----|--------|
| `path` | `str` | **LLM** | Model decides which directory to scan based on user request |
| `recursive` | `bool` | **LLM** | Model decides scan depth (default `true`) |
| `session_id` | `str` | **SYS** | Agent loop injects from `run_agent_loop(session_id=...)` |

**What the LLM sees:**
```json
{ "path": "/sandbox", "recursive": true }
```

**What MCP receives (after injection):**
```json
{ "path": "/sandbox", "recursive": true, "session_id": "a7e099a8-..." }
```

---

### propose_plan

Write a proposed plan and its actions to the database.

| Parameter | Type | Tag | Source |
|-----------|------|-----|--------|
| `goal` | `str` | **LLM** | Model describes the plan's objective |
| `rationale_summary` | `str` | **LLM** | Model explains its reasoning |
| `actions` | `list[dict]` | **LLM** | Model defines the file operations (see action payload shapes in TYPE_LEDGER.md) |
| `session_id` | `str` | **SYS** | Agent loop injects from `run_agent_loop(session_id=...)` |

**What the LLM sees:**
```json
{
  "goal": "Organize downloads by file type",
  "rationale_summary": "Group files into Documents, Images, and Archive folders",
  "actions": [
    { "action_type": "CREATE_FOLDER", "target_type": "folder", "target_path": "/sandbox/Documents", "action_payload": { "path": "/sandbox/Documents" } },
    { "action_type": "MOVE", "target_type": "file", "target_path": "/sandbox/draft_contract.txt", "action_payload": { "from_path": "/sandbox/draft_contract.txt", "to_path": "/sandbox/Documents/draft_contract.txt" } }
  ]
}
```

**What MCP receives (after injection):**
```json
{ "session_id": "a7e099a8-...", "goal": "...", "rationale_summary": "...", "actions": [...] }
```

---

### get_task_state

Read the current working-memory state for a session.

| Parameter | Type | Tag | Source |
|-----------|------|-----|--------|
| `session_id` | `str` | **SYS** | Agent loop injects from `run_agent_loop(session_id=...)` |

**What the LLM sees:** No parameters. The LLM calls this with `{}` when it wants to check current state.

**What MCP receives (after injection):**
```json
{ "session_id": "a7e099a8-..." }
```

---

### update_task_state

Update the current working-memory state for a session.

| Parameter | Type | Tag | Source |
|-----------|------|-----|--------|
| `goal` | `str?` | **LLM** | Model updates the current goal if needed |
| `current_step` | `str?` | **LLM** | Model updates the step (use SessionState values) |
| `active_plan_id` | `str?` | **LLM** | Model links a plan to the session |
| `scratchpad_summary` | `str?` | **LLM** | Model writes working notes |
| `session_id` | `str` | **SYS** | Agent loop injects from `run_agent_loop(session_id=...)` |

**Note:** The agent loop also calls `update_task_state` directly (not via MCP) for automatic state transitions like SCANNING and EXECUTING. The LLM's access to this tool is for cases where it wants to set `goal` or `scratchpad_summary`.

---

### read_file_metadata

Read metadata for a single file inside SANDBOX_ROOT.

| Parameter | Type | Tag | Source |
|-----------|------|-----|--------|
| `path` | `str` | **LLM** | Model decides which file to inspect |

**No system-injected parameters.** Schema passes through unmodified.

---

### execute_action

Execute a single APPROVED plan action.

| Parameter | Type | Tag | Source |
|-----------|------|-----|--------|
| `action_id` | `str` | **LLM** | Model specifies which approved action to execute |

**No system-injected parameters.** Schema passes through unmodified.

---

## Summary Table

| Tool | LLM-facing params | System-injected params |
|------|-------------------|------------------------|
| `scan_folder` | `path`, `recursive` | `session_id` |
| `propose_plan` | `goal`, `rationale_summary`, `actions` | `session_id` |
| `get_task_state` | *(none)* | `session_id` |
| `update_task_state` | `goal`, `current_step`, `active_plan_id`, `scratchpad_summary` | `session_id` |
| `read_file_metadata` | `path` | *(none)* |
| `execute_action` | `action_id` | *(none)* |

---

## Implementation Reference

The dispatch logic lives in `backend/agent/loop.py`:

```python
# Tools that need session_id injected by the agent loop.
TOOLS_REQUIRING_SESSION_ID = {
    "scan_folder",
    "propose_plan",
    "get_task_state",
    "update_task_state",
}

# Parameters to strip from tool schemas before sending to Ollama.
SYSTEM_INJECTED_PARAMS = {
    "session_id",
}
```

Schema filtering happens in `get_cached_tool_schemas()` or a wrapper that strips `SYSTEM_INJECTED_PARAMS` from each tool's `properties` and `required`.

Argument injection happens just before `_call_tool()`:
```python
if tool_call.name in TOOLS_REQUIRING_SESSION_ID:
    tool_call.arguments["session_id"] = session_id
```

---

## Context the LLM Needs

The system prompt must tell the LLM the sandbox root path so it can form valid `path` arguments. This is injected by `context.py`:

```
The sandbox root path is: /sandbox
All file paths you use in tool calls must be absolute paths starting with /sandbox.
```

Without this, the LLM has to guess the path — which defeats the purpose of having clean tool contracts.

---

## Adding a New Tool (Checklist)

When adding a new MCP tool to `mcp_server.py`:

1. Define the pure function in `backend/tools/new_tool.py`
2. Register it in `mcp_server.py`
3. **Update this document**: classify every parameter as LLM or SYS
4. If any parameter is SYS:
   - Add it to `SYSTEM_INJECTED_PARAMS` in `loop.py` if it's a new param name
   - Add the tool name to the appropriate injection set (e.g. `TOOLS_REQUIRING_SESSION_ID`)
5. Verify the filtered schema looks correct (only LLM-facing params visible)
6. Test that the loop injects the correct value before MCP dispatch

---

## Related Documents

| Document | What it answers |
|----------|----------------|
| `docs/TYPE_LEDGER.md` | What are the enum values, payload shapes, and API contracts? |
| `docs/TOOL_DISPATCH.md` (this file) | Which tool params does the LLM fill vs the loop inject? |
| `docs/AGENT_LOOP.md` | How does the loop work? What gets logged? |
| `docs/STATE_MACHINE.md` | What state transitions are allowed? |
