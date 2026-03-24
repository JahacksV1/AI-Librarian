# AIJAH Phase 1.7 — Scan Architecture & End-to-End Visibility

> This plan was produced from a full codebase audit (March 2026) plus a design conversation
> synthesizing the ChatGPT scan architecture vision with the current state of the project.
> It is scoped to the minimum viable end-to-end pipeline — not the full vision.
> The full vision (staged scanning, content-aware analysis, scan modes) becomes additive work
> on top of this foundation.

---

## The Problem

Scanning works, but it's a black box: the scan fires, data goes to the DB, the model sees
a one-time response, the frontend sees nothing, and there's no history, no change tracking,
and no way for the user to see what AIJAH actually found.

Specific gaps found in the audit:

1. **No scan history.** There is no `scans` table. You can't answer "when was the last scan?",
   "what depth?", "how many files were found?" after the fact.
2. **Category guesses and content previews are ephemeral.** `scan_folder` computes them but
   only sends them in the tool response. They are not written to the database.
3. **No change detection.** Files that disappear between scans are never marked `exists_now=False`.
   `content_hash` is always `None`. There is no "new since last scan" tracking.
4. **The frontend is blind to the filesystem.** Zero scan-specific UI components. No file tree,
   no folder hierarchy, no category buckets, no scan progress.
5. **The `/scan` API endpoint drops data.** It calls `scan_folder` but strips the response
   down to just counts.

---

## What We're Building (Scoped)

A **minimal end-to-end scan pipeline** where:

1. Every scan is recorded as a first-class entity with history
2. Scan results (categories, previews) persist in the database instead of being thrown away
3. The frontend can show what was scanned, what was found, and what changed
4. The model plans from persisted scan data, not ephemeral tool responses

This is NOT the full ChatGPT vision yet. This is the foundation that makes the ChatGPT vision
possible later (staged scanning, multi-depth, content-aware analysis). We get the plumbing
working end-to-end first.

---

## Architecture Flow

```
User sends message
    |
    v
Agent Loop --> scan_folder tool
    |
    +--> Create scan record in DB (status=RUNNING)
    +--> Upsert file_entities + folder_entities
    +--> Persist guessed_category + content_preview to file_entities
    +--> Mark missing files exists_now=false (change detection)
    +--> Update scan record (status=COMPLETED, counts, summary)
    |
    +--> Rich scan response to model (with change summary)
    +--> SSE events: scan_started + scan_complete --> Frontend
                                                        |
                                                        v
                                                Scan Results Panel
                                                (folder tree, file counts,
                                                 categories, changes)
```

## Three Consumers of Scan Data

| Consumer | What It Gets | How It Gets It |
|---|---|---|
| **Agent/Model** | Rich scan response + persisted scan summary in context | Tool response + context assembler |
| **Frontend** | Scan lifecycle events + queryable scan/file/folder data | SSE events + REST API endpoints |
| **Database** | Scan records, enriched file_entities, change history | Direct writes from scan_folder tool |

---

## Context Impact Analysis

Adding the `scans` table does NOT flood the model with more context. Here's why:

**What changes in context assembly:**

One small block is added — the most recent scan summary for the session. This is approximately
3-5 lines of structured text:

```
## Last Scan
Scanned /sandbox at 2026-03-24T14:30:00Z (depth: DEEP, recursive)
Found: 42 files across 7 folders
Changes: 3 new files, 1 deleted, 2 modified
Top categories: invoices (12), contracts (8), receipts (6), unknown (16)
```

**What this replaces:**

Right now, the model gets the FULL scan tool response (every file path, every folder path,
every preview) dumped into the conversation as a tool result message — and then that data
is gone next turn. The scan summary is a *smaller, more useful* replacement that *persists*.

**What does NOT go into context:**

- The full `scans` table history (only the latest scan is included)
- Individual file_entity rows (the model already has these from the tool response)
- Content previews from the database (only sent when the model explicitly reads a file)
- Folder entity details (only counts and categories in the summary)

**Net effect on context size:** Roughly neutral. The scan summary adds ~100 tokens. The model
already receives the full scan tool response (~500-2000 tokens depending on file count) in the
conversation history. The summary gives the model *better* information in *less* space, and
it persists across turns instead of being buried in old tool messages.

The real beneficiaries of the `scans` table are the **frontend** (which currently sees nothing)
and **future scans** (which can now compare against previous scan records). The model gets a
small, bounded improvement.

---

## Work Items

### Item 1: New `scans` table + enum + ORM model

Add a `scans` table to record every scan as a first-class entity.

**Files to create/modify:**

- `postgres/init/004_add_scans.sql` — new migration file
- `backend/db/enums.py` — add `ScanStatus` and `ScanDepth` enums
- `backend/db/models.py` — add `Scan` ORM model
- `docs/TYPE_LEDGER.md` — document new enums (per enum sync rule)

**Table definition:**

```sql
CREATE TYPE scan_status_enum AS ENUM ('RUNNING', 'COMPLETED', 'FAILED');
CREATE TYPE scan_depth_enum AS ENUM ('ROOT', 'DEEP', 'CONTENT');

CREATE TABLE scans (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID REFERENCES sessions(id),
    device_id       UUID NOT NULL REFERENCES devices(id),
    root_path       TEXT NOT NULL,
    scan_depth      scan_depth_enum NOT NULL DEFAULT 'DEEP',
    recursive       BOOLEAN NOT NULL DEFAULT true,
    file_count      INTEGER,
    folder_count    INTEGER,
    new_files       INTEGER DEFAULT 0,
    deleted_files   INTEGER DEFAULT 0,
    modified_files  INTEGER DEFAULT 0,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    status          scan_status_enum NOT NULL DEFAULT 'RUNNING',
    summary_json    JSONB,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_scans_session_id ON scans(session_id);
CREATE INDEX idx_scans_device_id ON scans(device_id);
```

**Enum sync rule:** Three places updated together — `004_add_scans.sql`, `backend/db/enums.py`,
`docs/TYPE_LEDGER.md`.

---

### Item 2: Add `guessed_category` and `content_preview` columns to `file_entities`

Persist the category guess and text preview that `scan_folder` already computes but currently
throws away.

**Files to modify:**

- `postgres/init/004_add_scans.sql` — include ALTER TABLE in same migration
- `backend/db/models.py` — add columns to `FileEntity`
- `docs/TYPE_LEDGER.md` — update `file_entities` table description

**SQL (in same migration):**

```sql
ALTER TABLE file_entities ADD COLUMN guessed_category TEXT;
ALTER TABLE file_entities ADD COLUMN content_preview TEXT;
ALTER TABLE file_entities ADD COLUMN scan_id UUID REFERENCES scans(id);
```

**Why:** `scan_folder` already computes these values per file but only returns them in the
tool response. The model forgets them next turn. The frontend can never see them. Persisting
means the model can reference categories across turns, the frontend can display categorized
file lists, and future scans can compare.

---

### Item 3: Update `scan_folder` tool — scan records, persist enrichments, detect changes

This is the core backend work. Modify the existing `scan_folder` to:

1. Create a `Scan` record at the start (status=RUNNING)
2. Write `guessed_category` and `content_preview` to `file_entities` (already computed, not saved)
3. Set `exists_now=False` on file/folder entities under the scan root that weren't seen this run
4. Count new, deleted, and modified files
5. Update the `Scan` record at the end (status=COMPLETED, counts, summary)
6. Return a richer response including change summary

**Files to modify:**

- `backend/tools/scan_folder.py` — main changes

**Change detection logic:**

```
After upserting found files/folders:
  previously_known = file_entities WHERE device_id=X
                     AND canonical_path LIKE '{scan_root}%'
                     AND exists_now=True
  seen_paths = set of paths found in this scan
  missing = previously_known - seen_paths
  UPDATE file_entities SET exists_now=False WHERE canonical_path IN missing
  Same for folder_entities
```

**Enrichment persistence:** The `guessed_category` and `content_preview` logic already exists
in `scan_folder.py`'s response-building section. Move the writes to happen during the upsert,
not after.

**Scan record lifecycle:**

```
scan_folder called
  --> INSERT scan (RUNNING)
  --> do work
  --> UPDATE scan (COMPLETED + counts)
  --> return
  (on error: UPDATE scan (FAILED))
```

---

### Item 4: New SSE events + new API endpoints

The frontend needs to know when a scan starts and completes — with actual data, not just a
`tool_call` JSON blob.

**New SSE events:**

| Event Type | When | Payload |
|---|---|---|
| `scan_started` | `scan_folder` begins | `{ scan_id, root_path, scan_depth }` |
| `scan_complete` | `scan_folder` finishes | `{ scan_id, file_count, folder_count, new_files, deleted_files, categories }` |

**Files to modify:**

- `backend/db/enums.py` — add to `SSEEventType`
- `backend/api/sse.py` — add `scan_started_event()` and `scan_complete_event()` formatters
- `backend/tools/scan_folder.py` — emit events via event callback

**New API endpoints:**

| Method | Path | Returns |
|---|---|---|
| `GET` | `/scans?session_id=X` | List of scan records for a session |
| `GET` | `/scans/{scan_id}` | Single scan with summary |
| `GET` | `/folders?device_id=X&path_prefix=Y` | Folder entities (data in DB, no endpoint yet) |

**Files to modify:**

- `backend/api/routes.py` — add 3 new endpoints

---

### Item 5: Update context assembler with last scan summary

When the model gets its context before each turn, it should see the most recent scan results —
not rely on remembering a tool response from 3 turns ago.

**Files to modify:**

- `backend/agent/context.py` — add scan summary to `ContextPacket`

**What gets added to context:**

```
## Last Scan
Scanned /sandbox at 2026-03-24T14:30:00Z (depth: DEEP, recursive)
Found: 42 files across 7 folders
Changes: 3 new files, 1 deleted, 2 modified
Top categories: invoices (12), contracts (8), receipts (6), unknown (16)
```

This queries the most recent `Scan` record for the session and formats a summary. The model
plans from persistent knowledge instead of ephemeral tool output.

---

### Item 6: Frontend — scan results panel + file/folder visibility

Add a scan results section to the UI that shows what AIJAH actually found. This is the critical
gap — right now the user sees nothing about the filesystem.

**New files:**

- `frontend/src/hooks/useScan.ts` — hook for scan state
- `frontend/src/components/scan/ScanPanel.tsx` — main panel
- `frontend/src/components/scan/FolderTree.tsx` — folder hierarchy view
- `frontend/src/components/scan/ScanSummary.tsx` — counts + categories

**Modified files:**

- `frontend/src/types/api.ts` — add Scan, Folder types
- `frontend/src/types/sse.ts` — add `scan_started`, `scan_complete` to union
- `frontend/src/lib/api.ts` — add `getScans()`, `getScan()`, `getFolders()`, update `getFiles()`
- `frontend/src/hooks/useSSE.ts` — handle new scan events
- `frontend/src/App.tsx` — integrate scan panel into layout
- `frontend/src/styles/panels.css` — scan panel styles

**Layout:**

Current layout is Plan (left) | Conversation (right) | Activity (bottom).

The scan panel sits above the plan panel on the left side — it appears when a scan is
active/complete, showing what was found. The plan panel appears below it when a plan is created.

```
+---------------------------+---------------------------+
|  Scan Results             |                           |
|  42 files, 7 folders      |     Conversation          |
|  Categories: ...          |                           |
|  Changes: 3 new, 1 del   |                           |
+---------------------------+                           |
|  Plan                     |                           |
|  Goal: Organize invoices  |                           |
|  Actions: [approve/reject]|                           |
+---------------------------+---------------------------+
|  Activity Log                                         |
+-------------------------------------------------------+
```

**What the scan panel shows:**

- Scan status indicator (scanning... / complete / failed)
- File count and folder count
- Category breakdown (invoices: 12, contracts: 8, etc.)
- Change summary (3 new files, 1 deleted)
- Collapsible folder tree with file counts per folder

---

### Item 7: Update documentation

**Files to modify:**

- `docs/TYPE_LEDGER.md` — add ScanStatus, ScanDepth enums; update file_entities columns; add scans table
- `docs/PROJECT_STATE.md` — add scan architecture section, update audit tables
- `docs/FE_BE_INTEGRATION.md` — add new SSE events and API endpoints to contract
- `docs/V1_CONTRACT.md` — note this as Phase 1.7 addendum (scan persistence + visibility)

---

## Dependency Order

```
Item 1 (scans table + enums)
    |
    v
Item 2 (file_entities columns) -- same migration file as Item 1
    |
    v
Item 3 (scan_folder tool update) -- depends on Items 1+2
    |
    +---> Item 4 (SSE events + API endpoints) -- depends on Item 3
    |         |
    |         v
    |     Item 6 (frontend scan panel) -- depends on Item 4
    |
    +---> Item 5 (context assembler) -- depends on Item 1

Item 7 (docs) -- runs throughout, finalized at end
```

Items 1+2 are one migration. Item 3 is the big backend change. Items 4+5 can run in parallel
after Item 3. Item 6 depends on Item 4. Item 7 is continuous.

---

## Naming Conventions (per existing standards)

| Item | Convention | This Plan |
|---|---|---|
| Migration file | `NNN_description.sql` | `004_add_scans.sql` |
| Postgres enums | `snake_case` + `_enum` | `scan_status_enum`, `scan_depth_enum` |
| Table | `snake_case`, plural | `scans` |
| Python enums | `PascalCase` | `ScanStatus`, `ScanDepth` |
| API routes | `kebab-case` | `/scans`, `/scans/{scan_id}`, `/folders` |
| Docker | — | No changes needed |
| Environment variables | — | None needed |

---

## What This Enables Later (NOT in this plan)

Once this foundation is in place, future work becomes straightforward additive steps:

- **Staged scanning** (root/deep/content) — the `scan_depth` enum and `scans` table already
  support it; just needs tool logic
- **Scan-to-scan comparison** — query two scan records and diff their file sets
- **Content-aware scanning** — deeper text extraction, heading parsing, better classification
- **Scan mode / Plan mode / Execute mode / Review mode** — frontend renders different views
  per `SessionState`, which already exists
- **Category confidence + sensitivity** — add columns to `file_entities` later

---

*Created: March 2026 — post full codebase audit.*  
*Status: Implemented in codebase (migration `004_add_scans.sql`, `scan_folder`, SSE, APIs, FE scan panel, context `Last scan`).*
