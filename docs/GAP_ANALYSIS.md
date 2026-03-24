# AIJAH — Gap Analysis: Current State vs. Working Product

> Written March 2026 after MCP extraction and real-filesystem scanning were confirmed working.
> This is the prioritized list of what to build next, and why, in that order.

---

## What Is Working Right Now

- Scans your real computer (`C:/Users/jaham`) via the native MCP server
- Agent gives responses based on actual file contents and structure
- `ScanPanel` shows categories, file/folder counts, and top folder names
- `PlanPanel` shows proposed actions with Approve / Reject / Execute controls
- Activity log streams all SSE events in real time
- MCP server runs natively on the host; Docker handles DB + backend + frontend

---

## Gap 1 — Sessions Are Ephemeral (Most Critical)

**What happens today:**
Every time the page loads, `useSession` calls `createSession()` and gets a brand new session. The old conversation is in the database but the UI has no way to reach it. Refresh the page → blank conversation, no scan context, no active plan. Start over.

**What `SessionList.tsx` needs to actually work:**
Three things are missing:

- **Backend:** No `GET /sessions?user_id={id}` endpoint exists in `routes.py`. The API can create and fetch a single session but cannot list them.
- **Frontend `api.ts`:** No `getSessions()` function.
- **Frontend `useSession`:** Always calls `createSession()` on init. No concept of restoring a previous session.

**The session restore flow (what needs to be built):**

```
1. Page loads → GET /sessions?user_id=...  (get list)
2. Check localStorage for last active session ID
3. If found and still active → restore it:
     GET /sessions/{id}/messages  → seedMessages() into conversation panel
     GET /scans?session_id={id}   → loadFromResponse() into scan panel
     GET /sessions/{id}/plans     → find most recent PENDING/APPROVED plan → set activePlanId
4. If not found → createSession() as today
5. SessionList renders all sessions, clicking one runs the same restore flow
```

The infrastructure for this is almost entirely in place. `useSSE.seedMessages()` exists. `useScan.loadFromResponse()` exists. The `GET /sessions/{id}/messages`, `GET /scans?session_id={id}`, and `GET /sessions/{id}/plans` backend endpoints all exist. Only the list endpoint and the orchestration logic are missing.

**Session memory safety:**
This is already handled correctly. In `assemble_context()`, memory events are queried `WHERE session_id = current_session_id` — each session sees only its own action history. Cross-session data is limited to the device's last scan (folder/file metadata, not action history). There is no confusion or overlap between sessions with the current design. This is intentional.

---

## Gap 2 — Scan Panel Is Read-Only

**What happens today:**
`ScanPanel` shows folder names from the scan result as plain `<li>` elements with no click handling. The user can see "there's a folder called Downloads with 847 items" but cannot do anything with it.

**What would make this immediately useful:**
Clicking a folder name adds a pre-filled message to the chat composer:

> "Tell me more about C:/Users/jaham/Downloads — scan it in detail"

No new backend work. No new API. Just a click handler on each folder item in `ScanSummary.tsx` that calls an `onFolderSelect(path)` prop, which the parent wires to inject text into the `Composer`. The `Composer` already takes an initial value and a send trigger.

This is ~30 lines of code and turns the scan panel from a read-only display into an interactive navigation tool.

**The full folder browser (Phase 2):**
A proper tree browser that fetches `/folders?device_id=...` and renders the full hierarchy is a bigger piece. The `getFolders()` API function exists in `api.ts` but is not used anywhere yet. That belongs in Phase 2.

---

## Gap 3 — Broken REST Endpoint (Latent Bug, Not Blocking)

`POST /api/scan` in `routes.py` calls `scan_folder()` directly — not through the MCP server. Inside Docker, `C:/Users/jaham` doesn't exist. Any call to this endpoint throws `FileNotFoundError`. The agent never calls this endpoint (it uses MCP), and the frontend never calls it either, so nothing is broken today. But it is live and will cause real errors if it is ever hit.

**Fix:** Remove the `ScanRequest` model and `scan_filesystem()` handler from `routes.py`. Remove the `from tools.scan_folder import scan_folder` import. All scan operations must go through the MCP server.

---

## Gap 4 — Agent Has No Guidance for a Large Root

`SANDBOX_ROOT=C:/Users/jaham` is the entire home directory — potentially hundreds of thousands of files. The system prompt tells the model to operate within this root but gives no guidance on where to start. On first message, the agent often attempts a DEEP or CONTENT scan of the entire home directory, which either times out or returns an overwhelming result.

**Fix:** Add one paragraph to `SYSTEM_PROMPT` in `context.py`:

```
When first exploring an unfamiliar root, ALWAYS start with a ROOT scan (immediate
children only) to orient yourself. Then ask the user which subfolder to focus on
before going DEEP or CONTENT on anything.
```

This is a 15-minute change that prevents the agent from doing a house-wide sweep on every first message.

---

## Gap 5 — No Visibility of What the Agent Can See

The user has no indication in the UI of what path the agent is configured to operate on. There is no "watching C:/Users/jaham" label anywhere. When the agent fails or succeeds, the user doesn't know what scope it was operating in.

**Fix:** Expose `sandbox_root` on the `/health` endpoint. Display it in the `StatusBar` as a small "Watching: ~/jaham" label (truncated to the last path segment).

---

## Gap 6 — PROJECT_STATE.md Is Outdated

The docs still describe:

- The old vanilla JS frontend (`main.js`, `panels/plan.js`, etc.) — does not exist; replaced by React/Vite
- Phase 2 item: "Extract MCP to own container" — already done and running natively
- Phase 1 table shows "tests pending" for items that have since changed architecture

Stale docs cause every future session to start with wrong assumptions. Update to reflect the actual React/Vite component structure, the native MCP server as current architecture (not future), and the real "what's next" list above.

---

## Build Order

Prioritized by impact-to-effort ratio:

```
PRIORITY 1 — Session persistence + restore (~3–4 hours)
  Backend:  Add GET /sessions?user_id={id} to routes.py
  API:      Add getSessions() to lib/api.ts
  Hook:     Rewrite useSession to restore last session from localStorage + list sessions
  App.tsx:  Wire SessionList into left column, restore scan + plan state on session select
  Result:   Refresh the page → conversation resumes where you left off

PRIORITY 2 — System prompt: staged scan guidance (~15 minutes)
  context.py: Add ROOT-first instruction to SYSTEM_PROMPT
  Result:     Agent stops trying to scan the entire home directory on first message

PRIORITY 3 — Folder click-through (~1 hour)
  ScanSummary.tsx: Add onFolderSelect prop + click handler on each folder item
  ScanPanel.tsx:   Pass through onFolderSelect from parent
  App.tsx:         Wire onFolderSelect to pre-fill and send Composer message
  Result:          Click a folder → agent scans it deeper

PRIORITY 4 — Remove broken /scan endpoint (~15 minutes)
  routes.py: Delete ScanRequest model and scan_filesystem() handler
  Result:    Cleaner API, no silent landmine

PRIORITY 5 — Expose sandbox_root in UI (~30 minutes)
  routes.py:   Add sandbox_root field to /health response
  StatusBar:   Read from health check, show "Watching: ~/jaham"
  Result:      User always knows what the agent can see

PRIORITY 6 — Update PROJECT_STATE.md (~30 minutes)
  Replace vanilla JS frontend table with React/Vite component map
  Update architecture section to reflect native MCP as current (not future)
  Update "what's next" to this gap list
```

---

## What Is NOT a Gap Right Now

- **Full file browser** — scan panel folder list is sufficient for Phase 1; tree browser is Phase 2
- **Auth / multi-user** — hardcoded test user UUID is fine for dev
- **Tauri packaging** — Phase 3
- **pgvector / embeddings** — Phase 2
- **One-click startup script** — Phase 2.5

The core product loop (chat → scan → plan → approve → execute) works end-to-end. The gaps are around continuity and polish, not the main pipeline.

---

*Last updated: March 2026*
