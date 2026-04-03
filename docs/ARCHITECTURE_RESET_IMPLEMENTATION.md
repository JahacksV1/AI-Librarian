# Architecture Reset — Implementation Guide

> This document turns the ideas in `Architecture Reset Plan` into a practical implementation path for the current `AI-Librarian` codebase.
>
> Its job is not to replace the reset plan. Its job is to make the reset executable.

---

## 1. Purpose

The reset exists because AIJAH currently knows too much by replaying conversation history and scan payloads, and not enough by querying its structured database memory.

The implementation goal is simple:

- keep scans as the way AIJAH learns the filesystem
- add retrieval as the way AIJAH answers questions about what it already knows
- reserve planning for moments when the user wants real changes
- keep execution and safety exactly as strict as they are now

The target behavior is:

```text
scan if needed -> retrieve indexed facts -> summarize -> clarify -> plan only when asked -> approve -> execute
```

---

## 2. Core Decision

The architectural decision behind this reset is:

- `scan_folder` should be treated primarily as an indexing tool
- the model should answer most filesystem questions through retrieval over indexed data
- `propose_plan` should not be the default next step after a scan
- `execute_action` remains the only path for real filesystem changes

This means AIJAH should move away from:

- "I scanned something, so now I should plan"
- "I remember what exists because I just read a huge tool payload"
- "I know what to say because I reloaded the whole transcript"

And toward:

- "I scan to refresh knowledge"
- "I retrieve to answer questions"
- "I plan only when the user wants action"

---

## 3. What Is Wrong Today

These are the real issues this reset is trying to solve.

### 3.1 Transcript weight is too high

In `backend/agent/context.py`, the model currently receives:

- system prompt
- policies
- preferences
- task state
- recent memory events
- active plan
- last scan
- the full `session_messages` transcript

That works, but it scales badly. As sessions grow, the model sees more noise, more repeated information, and more stale framing.

### 3.2 Indexed filesystem memory is underused

The database already stores strong structured knowledge in:

- `scans`
- `file_entities`
- `folder_entities`
- `memory_events`

But the model cannot ask rich questions over that data. It can mostly:

- rescan
- inspect one exact file with `read_file_metadata`
- rely on the last scan payload

That is the main missing middle layer.

### 3.3 `scan_folder` is operationally solid but architecturally overloaded

`backend/tools/scan_folder.py` is doing useful work and should not be treated like a broken tool. It already:

- walks the filesystem
- writes scan rows
- upserts file and folder entities
- computes categories and previews
- returns a compact-ish payload

But it still serves two roles at once:

- indexing the system's durable filesystem knowledge
- acting as a model-facing understanding primitive

That is acceptable for now, but it is still a mixed responsibility.

### 3.4 Planning still happens too easily

The prompt is better than it used to be, but the architecture still leans too close to:

- scan
- summarize
- plan

instead of:

- scan
- retrieve
- summarize
- clarify
- plan if the user wants changes

---

## 4. Current Reality vs. Target Reality

This section matters because the earlier version of this doc sometimes blurred current behavior and desired behavior together.

### Current reality

- `scan_folder` exists and is useful.
- `read_file_metadata` exists but is narrow.
- `propose_plan` and `execute_action` are already the strongest safety-controlled part of the system.
- `context.py` still loads the full transcript into model context.
- `loop.py` does not have a retrieval tool to dispatch.
- the loop sets `SCANNING` when `scan_folder` starts and currently sets `PLAN_READY` after scan results.
- the frontend already handles generic tool calls and tool results well enough that a retrieval tool can fit into the current UI without a frontend rewrite.

### Target reality

- scans refresh indexed knowledge
- retrieval answers questions from indexed knowledge
- plans are created only when the user wants real changes
- transcript becomes a short conversational window, not the model's main long-term memory source
- scan results stop acting like the main reasoning substrate

---

## 5. Memory Model for This Phase

The reset plan already explains memory deeply. This implementation doc only needs the parts that drive code changes.

### `session_messages`

Keep as:

- the canonical transcript
- the UI conversation source
- the audit trail of user, assistant, and tool history

Change:

- stop using the entire transcript as hot-path model context every turn
- replace it with a recent window

### `task_state`

Keep as:

- the compact working state for the active session

Change:

- keep it small
- be careful not to treat advisory assistant notes as equivalent to safety-critical state

### `scans`, `file_entities`, `folder_entities`

Keep as:

- the durable filesystem memory

Change:

- make them queryable by the model through a retrieval tool

### `memory_events`

Keep as:

- the action and outcome history
- the anti-repeat and audit layer

Change:

- no urgent change required in this phase

---

## 6. Tool Model After the Reset

The tool surface should become easier to reason about if each tool has one main role.

### Current tool roles

- `scan_folder` -> index
- `read_file_metadata` -> detail
- `propose_plan` -> plan
- `execute_action` -> execute
- `get_task_state` -> state read
- `update_task_state` -> state write

### Missing role

- `query_indexed_files` -> retrieval

This is the most important missing tool in the current architecture.

Without it, the model has no good way to answer questions like:

- what are the biggest PDFs under this path
- which folders have the most files
- what categories dominate this area
- what changed since the last scan
- what files look similar enough to review for duplicates

### Phase 1 tool principle

For this phase, we are not trying to redesign every tool. We are doing the minimum change that unlocks better behavior:

- keep `scan_folder`
- add `query_indexed_files`
- keep `read_file_metadata`
- keep `propose_plan`
- keep `execute_action`

---

## 7. `query_indexed_files` in Plain English

The new retrieval tool should let the model ask focused questions against existing indexed filesystem data.

It should be able to filter by things like:

- `path_prefix`
- `entity_type`
- `extension`
- `category`
- `exists_now`
- size range

It should be able to sort by things like:

- size
- modified time
- name
- extension

It should return:

- total matching rows
- a compact result list
- optional aggregate counts

The point is not to dump raw database rows. The point is to give the model enough factual structure to answer clearly and ask a smart follow-up question.

---

## 8. Code Changes for Phase 1

This is the practical implementation scope.

### Step 1: Add retrieval

Create:

- `backend/tools/query_indexed_files.py`

Modify:

- `backend/mcp_server.py`
- `backend/agent/loop.py`
- `docs/TOOL_DISPATCH.md`

Why:

- this adds the missing retrieval layer without changing the safety model

### Step 2: Update context assembly

Modify:

- `backend/agent/context.py`

Why:

- replace full transcript replay with a recent conversation window
- keep active plan, task state, memory events, and last scan as structured context
- reduce prompt bloat and force reliance on retrieval over transcript rereading

### Step 3: Tighten system prompt guidance

Modify:

- `backend/agent/context.py`

Why:

- explicitly tell the model to use retrieval for analysis
- prefer retrieval over rescanning when the data is already indexed
- ask clarifying questions before planning
- explain findings with concrete numbers instead of generic summaries

### Step 4: Fix state semantics

Modify:

- `backend/agent/loop.py`
- possibly `docs/STATE_MACHINE.md`

Why:

- today the loop marks `PLAN_READY` after scan results, which does not match the desired "analysis first" behavior
- this should be adjusted so scans do not imply a plan exists

This is the most important correction to the earlier version of this document.

### Step 5: Clean the contracts

Modify:

- `docs/TOOL_DISPATCH.md`
- `docs/STATE_MACHINE.md`

Why:

- the docs need to match the real tool and loop contracts
- `scan_folder` currently includes `scan_depth`, and the dispatch doc should reflect that

---

## 9. Build Plan (Recommended Order)

This is the implementation order to minimize rework and keep behavior stable while the architecture shifts.

### Stage A: Retrieval foundation

Files:

- `backend/tools/query_indexed_files.py` (new)
- `backend/mcp_server.py`
- `backend/agent/loop.py`
- `docs/TOOL_DISPATCH.md`

Done when:

- the model can call `query_indexed_files` with filters/sort/limit
- `session_id` is SYS-injected in loop dispatch
- retrieval tool returns compact results + optional counts
- MCP schemas expose only LLM-facing args

Stop/go gate:

- pass 3 manual prompts without planning:
  - "what's in this folder?"
  - "show biggest PDFs"
  - "what categories dominate here?"

### Stage B: Context slimming

Files:

- `backend/agent/context.py`

Done when:

- context uses a recent transcript window (not full transcript)
- old transcript still persists in DB for UI/audit
- provider tool-call replay is still valid (especially Anthropic)

Stop/go gate:

- run at least one multi-tool turn and confirm no tool-call replay errors

### Stage C: Prompt behavior alignment

Files:

- `backend/agent/context.py`

Done when:

- prompt explicitly prefers retrieval over rescanning when data exists
- prompt asks for clarification before planning
- prompt directs plan creation only on explicit action intent

Stop/go gate:

- in a scan-follow-up conversation, assistant summarizes + asks clarifying question without proposing a plan

### Stage D: State semantics correction

Files:

- `backend/agent/loop.py`
- `docs/STATE_MACHINE.md`

Done when:

- scan completion no longer implies plan readiness by default
- `PLAN_READY` / `AWAITING_APPROVAL` semantics match real plan lifecycle

Stop/go gate:

- after analysis-only scan + retrieval turns, session state stays non-planning

### Stage E: Contract and docs hardening

Files:

- `docs/TOOL_DISPATCH.md`
- `docs/ARCHITECTURE_RESET_IMPLEMENTATION.md`
- (optional) `backend/api/routes.py` for `POST /scan` deprecation/removal

Done when:

- docs reflect the exact shipped contracts
- caveats remain explicit (duplicate detection heuristic, mixed `scan_folder` role)
- non-canonical scan path is removed or clearly marked as legacy

Stop/go gate:

- a new contributor can follow docs without conflicting instructions

---

## 10. What Does Not Change

This reset is intentionally narrow.

- `execute_action` remains the execution boundary
- approval is still required before changes
- sandbox enforcement remains authoritative
- `memory_events` remains the audit layer
- the database schema does not need a major redesign for this phase
- the frontend does not need a structural rewrite for this backend improvement
- Docker topology does not need to change for this phase

---

## 11. Known Limits and Honest Caveats

This section is here so the document stays trustworthy.

### `scan_folder` is not fully decomposed yet

For phase 1, `scan_folder` remains a mixed-responsibility tool. That is acceptable as long as retrieval becomes the main analysis path.

### Duplicate detection is heuristic-only for now

`FileEntity.content_hash` exists in the schema, but it is not currently populated by `scan_folder`.

That means early duplicate detection should be described as:

- name-based
- size-based
- location-based

Not true content-verified deduplication.

### Retrieval queries may need indexing work later

The current schema is sufficient to build `query_indexed_files`, but heavier aggregate queries may eventually need better database indexes.

### `POST /scan` is not the intended architecture path

`backend/api/routes.py` still exposes a direct REST scan path that bypasses the MCP-centered architecture. It should not be treated as the long-term product path.

---

## 12. Verification Goals

After this reset phase, AIJAH should behave like this.

### Scenario 1: Analysis without planning

- user asks what is in a folder
- AI scans if needed
- AI retrieves indexed facts
- AI summarizes what exists
- AI asks what the user wants to focus on
- no plan is created unless the user asks for changes

### Scenario 2: Targeted retrieval

- user asks for biggest PDFs, likely duplicates, or category breakdowns
- AI uses retrieval over indexed entities
- AI answers with specific numbers and paths
- AI does not rescan unless the knowledge is stale or missing

### Scenario 3: Plan only after user intent is clear

- user asks to organize an area
- AI scans if needed
- AI retrieves enough detail to understand the area
- AI asks one clarifying question if needed
- AI proposes a plan only after the user confirms the intended action

### Scenario 4: Safety remains unchanged

- no real filesystem change happens without plan approval
- execution still runs only through `execute_action`
- memory events still record outcomes

---

## 13. Final Guidance

If there is one thing to remember from this document, it is this:

AIJAH should stop using scans and transcripts as its default intelligence layer, and start using indexed retrieval as its normal way of understanding the filesystem.

That is the reset.

Everything else in this phase exists to make that one change real.

---

*Last updated: April 2026. Reframed for clarity so it can function as the execution guide for the ideas in `Architecture Reset Plan`, rather than trying to replace that document.*
