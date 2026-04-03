# AIJAH State Machine

> States describe conditions, not actions.
> Transitions describe what causes the system to move between conditions.
> Guards describe what must be true for a transition to be allowed.

This document defines every state machine in the AIJAH system. There are three levels:

1. **Session State** — the high-level lifecycle of a single session (what the user sees)
2. **Plan State** — the lifecycle of a generated plan (`plans.status`)
3. **Action State** — the lifecycle of a single file action (`plan_actions.status`)

These three machines are nested: a session moves through states partly because of what happens to plans inside it, and plans move through states partly because of what happens to actions inside them.

---

## Why State Machines Matter Here

AIJAH is not a simple request/response app. It is an orchestration system. At any moment, the backend needs to know:

- Is the agent currently scanning? Then don't start another scan.
- Is a plan waiting for approval? Then don't execute it.
- Did the user reject the plan? Then the session goes back to IDLE.
- Did execution partially fail? The plan is PARTIAL and the session goes to ERROR.

Without defined states, the system becomes unpredictable — the AI does something, files maybe move, maybe not. With defined states, the system is deterministic. The UI knows what to show. The backend knows what is allowed. Debugging becomes possible.

---

## Level 1: Session State Machine

The session state lives in `task_state` (specifically the `current_step` field in Phase 1, promoted to its own `session_state` enum in Phase 2).

This is the view from the user's seat: "what is AIJAH currently doing in this conversation?"

### States

| State | Meaning | What the UI should show |
|---|---|---|
| `IDLE` | No active task. Waiting for user input. | Chat input ready, no progress indicator |
| `SCANNING` | `scan_folder` tool is running, indexing files. | "Scanning files..." spinner |
| `PLAN_READY` | Legacy/optional intermediate state; not required in the retrieval-first flow. | Optional transitional state only |
| `AWAITING_APPROVAL` | Plan is shown; waiting for user to approve/reject actions. | Approve / Reject buttons active per action |
| `EXECUTING` | Approved actions are being executed by the executor. | "Executing..." per-action progress |
| `COMPLETE` | All approved actions finished successfully. | Success summary, memory logged |
| `ERROR` | One or more actions failed, or the agent hit an unrecoverable error. | Error message, retry option |

### Transitions

```
IDLE
  │
  │  user sends message with a file task
  ▼
SCANNING ──────────────────────────────────────────────► ERROR
  │                                                (scan fails / path not found)
  │  scan_folder tool returns results
  ▼
IDLE
  │
  │  user asks for changes and propose_plan writes plan to DB
  ▼
AWAITING_APPROVAL ─────────────────────────────────────► IDLE
  │                                          (user rejects entire plan)
  │  user approves ≥1 action
  ▼
EXECUTING ─────────────────────────────────────────────► ERROR
  │                                          (all actions failed)
  │  all approved actions succeeded
  ▼
COMPLETE
  │
  │  user starts new task or sends follow-up
  ▼
IDLE
```

### Transition Table

| From | Event | Guard | To |
|---|---|---|---|
| `IDLE` | User sends file task message | None | `SCANNING` |
| `IDLE` | User sends chat-only message | None | `IDLE` (agent replies, stays IDLE) |
| `SCANNING` | `scan_folder` tool completes | Analysis/indexing complete | `IDLE` |
| `SCANNING` | `scan_folder` tool fails | Path invalid or permission error | `ERROR` |
| `IDLE` | `propose_plan` tool writes plan | User explicitly requested changes; plan has ≥1 action | `AWAITING_APPROVAL` |
| `AWAITING_APPROVAL` | User approves ≥1 action, clicks Execute | At least 1 action is APPROVED | `EXECUTING` |
| `AWAITING_APPROVAL` | User rejects all actions | All actions REJECTED | `IDLE` |
| `EXECUTING` | All actions complete with SUCCESS | outcome = SUCCESS for all | `COMPLETE` |
| `EXECUTING` | Some actions fail | ≥1 outcome = FAILED | `ERROR` |
| `EXECUTING` | Mixed results | Some SUCCESS, some FAILED | `COMPLETE` (plan = PARTIAL) |
| `COMPLETE` | User starts new task | None | `IDLE` |
| `ERROR` | User retries | None | `SCANNING` or `AWAITING_APPROVAL` |
| `ERROR` | User dismisses | None | `IDLE` |

### Guard Rules (non-negotiable)

These guards are enforced in code, not just convention:

1. **EXECUTING cannot start without APPROVED actions.** The executor checks `plan_actions.status = APPROVED` before touching the filesystem. If no APPROVED actions exist, execution is blocked.
2. **SCANNING cannot start outside SANDBOX_ROOT.** The `scan_folder` tool validates the path is within the configured root before doing anything.
3. **PLAN_READY cannot become EXECUTING directly.** The session must pass through AWAITING_APPROVAL. There is no "auto-execute" path.
4. **ERROR is always visible.** The UI must show what failed. Silent failures are not allowed.

---

## Level 2: Plan State Machine

Lives in `plans.status`. Maps to the `PlanStatus` enum in the type ledger.

### States

| State | Meaning |
|---|---|
| `DRAFT` | Model just created the plan. Not yet shown to user. |
| `PENDING` | Plan surfaced to user in UI. Awaiting their decisions. |
| `APPROVED` | All actions in this plan are APPROVED. Ready to execute. |
| `REJECTED` | User rejected the entire plan. No actions will run. |
| `EXECUTED` | All actions completed successfully. |
| `PARTIAL` | Some actions succeeded, some failed or were rejected individually. |

### Transitions

```
DRAFT
  │  plan surfaced to UI
  ▼
PENDING
  ├── user approves all actions ──────────────────► APPROVED
  │                                                      │
  │                                                      │ execute_action called for each
  │                                                      ▼
  │                                               all succeed → EXECUTED
  │                                               mixed       → PARTIAL
  │
  └── user rejects entire plan ───────────────────► REJECTED
```

### How plan status is derived

Plan status is computed from action statuses:

- If any action is PENDING or APPROVED → plan is `PENDING` or `APPROVED`
- If all actions are REJECTED → plan is `REJECTED`
- If all actions are EXECUTED → plan is `EXECUTED`
- If mix of EXECUTED + (FAILED or REJECTED) → plan is `PARTIAL`

---

## Level 3: Action State Machine

Lives in `plan_actions.status`. Maps to the `ActionStatus` enum in the type ledger.

### States

| State | Meaning |
|---|---|
| `PENDING` | Created with plan. Awaiting user decision. |
| `APPROVED` | User approved this action. Executor will run it. |
| `REJECTED` | User rejected this specific action. Will never run. |
| `EXECUTED` | Executor ran this action successfully. |
| `FAILED` | Executor attempted but threw an error. |
| `SKIPPED` | Skipped because the parent plan was rejected, or a dependency failed. |

### Transitions

```
PENDING
  ├── user clicks Approve ──────────────► APPROVED
  │                                            │
  │                                            │ executor picks up action
  │                                            ├── success ──► EXECUTED
  │                                            └── failure ──► FAILED
  │
  ├── user clicks Reject ──────────────► REJECTED
  │
  └── parent plan rejected ────────────► SKIPPED
```

### Guard: Only APPROVED actions are executed

```python
# Pseudocode — enforced in execute_action tool
def execute_action(action_id):
    action = db.get(plan_actions, action_id)
    if action.status != ActionStatus.APPROVED:
        raise ValueError(f"Cannot execute action with status {action.status}")
    # ... proceed
```

This guard is the most important single rule in the system. It is the safety gate.

---

## How the Three Machines Relate

```
Session: AWAITING_APPROVAL
    └── Plan: PENDING
            ├── Action: PENDING (waiting for user)
            ├── Action: APPROVED (user clicked approve)
            └── Action: REJECTED (user clicked reject)

                    ↓ user clicks "Execute"

Session: EXECUTING
    └── Plan: APPROVED
            ├── Action: EXECUTED ✓
            ├── Action: EXECUTING (in progress)
            └── Action: APPROVED (queued)

                    ↓ all done

Session: COMPLETE  (or ERROR if failures)
    └── Plan: EXECUTED  (or PARTIAL)
            ├── Action: EXECUTED ✓
            ├── Action: EXECUTED ✓
            └── Action: EXECUTED ✓
```

---

## State in the Database vs. State in the Agent Loop

There are two kinds of state in AIJAH. It's important to know which is which.

### Persisted state (in the DB — source of truth)

- `plans.status` — the actual status of every plan
- `plan_actions.status` — the actual status of every action
- `task_state.current_step` — the agent's working memory of what it's doing
- `memory_events` — the immutable audit log of every transition

### Transient state (in the agent loop — working memory)

- Whether Ollama is currently streaming a response
- Whether the executor is mid-action
- Whether the frontend SSE connection is alive

The DB is always the source of truth. If the backend crashes and restarts, it can reconstruct what was happening by reading the DB. The agent loop state is re-derived from the DB on restart.

---

## What the UI Must Enforce

The frontend has responsibilities too. Based on session state, certain UI elements must appear, be disabled, or be hidden:

| Session State | Chat input | Approve buttons | Execute button | Progress indicator |
|---|---|---|---|---|
| `IDLE` | Enabled | Hidden | Hidden | None |
| `SCANNING` | Disabled | Hidden | Hidden | "Scanning..." |
| `PLAN_READY` | Disabled | Hidden | Hidden | "Generating plan..." |
| `AWAITING_APPROVAL` | Disabled | Active | Enabled (if ≥1 APPROVED) | None |
| `EXECUTING` | Disabled | Disabled | Disabled | Per-action progress |
| `COMPLETE` | Enabled | Hidden | Hidden | "Done" summary |
| `ERROR` | Enabled | Hidden | "Retry" shown | Error detail |

---

## Phase 2 Additions (do not implement in Phase 1)

In Phase 2, the session state machine gains additional states for document reading:

- `READING` — agent is reading a document's content via `document_extracts`
- `SUMMARIZING` — agent is generating a summary from extracted content

And a `SessionState` enum is added to the DB (`sessions.session_state` column), so state is persisted and queryable, not just held in `task_state.current_step`.

Phase 1 tracks current session state via `task_state.current_step` (a text field). That is enough for Phase 1.
