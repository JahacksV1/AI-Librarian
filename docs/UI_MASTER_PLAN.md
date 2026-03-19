# AIJAH UI Master Plan (v2)

> This is the single canonical frontend spec. All previous UI docs have been deleted.
> If it's not in this document, it's not in scope for Phase 1 frontend.

---

## 1. What the UI must communicate

AIJAH is not a chatbot. It is a **file-operation copilot with an approval gate**.

The UI must make three things visible at all times:

- **Intent** -- what the user asked for (conversation)
- **Proposed plan** -- what AIJAH wants to do, with approve/reject per action
- **Trace** -- what AIJAH looked at, called, and returned (SSE event stream)

If those three are clear, the product feels trustworthy and premium.

---

## 2. Design system

**Reference:** Notion (clean white, generous spacing, content-focused)

### Palette

- Surfaces: `#ffffff` (primary), `#f7f7f5` (secondary/cards), `#f0f0ee` (hover)
- Text: `#37352f` (primary), `#787774` (secondary), `#b4b4b0` (muted)
- Accent: `#2eaadc` (links, primary actions)
- Semantic: `#0f7b6c` (success/approved), `#eb5757` (error/failed), `#f2c94c` (warning/pending)
- Borders: `#e9e9e7` (subtle dividers only, not every element)

### Typography

- Font: `"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`
- Body: 14px / 1.5 line-height
- Labels: 12px, secondary color, 500 weight
- Panel headers: 11px uppercase, letter-spacing 0.06em, muted color
- Plan goal: 18px, 600 weight

### Elevation and borders

- Panels: no visible border by default. Use background color contrast (#fff on #f7f7f5 page) to define zones.
- Hover: subtle background shift (not shadow lifts on everything)
- Cards (action items): 1px #e9e9e7 border, 8px radius
- Shadows: only on overlays/modals if needed later. Flat otherwise.

### Micro-interactions

- Buttons: background color transition on hover (150ms ease). No translateY lifts.
- Action cards: left border-color changes to accent on hover
- Badges: pill-shaped, 11px, background tint matching semantic color
- Transitions: keep to background-color and opacity only. No transforms on cards.

---

## 3. Layout

```
+------------------------------------------------------------------+
|  AIJAH                          [status pill]   [retry if error]  |  <- topbar (48px)
+------------------------------------------------------------------+
|              |                                                     |
|  DRAWER      |            PLAN STAGE                              |  <- main area
|  (340px)     |            (fills remaining)                       |
|              |                                                     |
|  conversation|   [goal]                                           |
|  messages    |   [rationale]                                      |
|  ...         |   [action cards with approve/reject]               |
|              |   [execute button]                                 |
|              |                                                     |
|  [collapse   |                                                     |
|   icon at    |   +----------------------------------------------+ |
|   top]       |   |  floating composer bar (always visible)       | |
|              |   +----------------------------------------------+ |
+--------------+-----------------------------------------------------+
|  AGENT ACTIVITY TRAY  (200px, pinned open, clean log style)       |
|  tool_call -> scan_folder   |  tool_result <- 12 files            |
+------------------------------------------------------------------+
```

### Zones

- **Left: Conversation Drawer** (340px, collapsible to 48px icon rail)
  - Message thread (USER / ASSISTANT / TOOL roles)
  - TOOL messages collapsed by default (chevron to expand JSON)
  - Collapse button in drawer header; reopen via icon in topbar or icon rail click
  - When collapsed: shows a chat bubble icon only, clicking reopens
- **Center: Plan Stage** (primary focus, fills remaining width)
  - Empty state: centered muted text "Send a message to get started"
  - When plan exists: goal, rationale, action list, approve/reject, execute
  - This is the largest zone -- it's the product surface
- **Bottom: Floating Composer** (inside plan stage, bottom-anchored)
  - Always visible regardless of drawer state
  - Textarea + Send button
  - Disabled during SCANNING / EXECUTING states, placeholder text changes
- **Bottom: Agent Activity Tray** (200px default, spans full width)
  - Clean formatted log, same visual language as rest of UI (not terminal-style)
  - Colored event type badges (blue for tool_call, green for tool_result, purple for plan_created, amber for state, red for error)
  - Auto-scrolls to newest event
  - Pinned open during development

---

## 4. SSE integration (the heartbeat)

SSE = Server-Sent Events. One-way live stream from backend to frontend over HTTP.

### Two SSE streams

**Stream 1: Agent thinking** (POST /sessions/{session_id}/messages)
- token, tool_call, tool_result, plan_created, message_complete, error

**Stream 2: Plan execution** (POST /plans/{plan_id}/execute)
- action_executed, execution_complete, error

### SSE event -> UI behavior map

| Event | Conversation | Plan stage | Activity tray | Composer |
|-------|-------------|------------|---------------|----------|
| token | Append to streaming message | -- | -- | disabled |
| tool_call | Show collapsed "Using {tool}" | -- | Log with blue badge | disabled |
| tool_result | Update collapsed tool msg | -- | Log with green badge | disabled |
| plan_created | -- | Fetch + render plan | Log with purple badge | disabled, "Review the plan" |
| message_complete | Finalize message | -- | -- | enabled |
| action_executed | -- | Update action card badge | Log with amber badge | disabled |
| execution_complete | -- | Show summary | Log with green badge | enabled |
| error | -- | Show inline error if relevant | Log with red badge | enabled |

---

## 5. State management

### Single state object

```javascript
{ sessionId, activePlanId, uiState, drawerOpen }
```

### UI states

| uiState | Composer | Plan stage | Activity |
|---------|----------|------------|----------|
| initializing | disabled, "Connecting..." | empty state | empty |
| idle | enabled, "Ask AIJAH..." | plan or empty | visible |
| streaming | disabled, "Thinking..." | unchanged | live events |
| scanning | disabled, "Scanning files..." | unchanged | live events |
| awaiting_approval | disabled, "Review the plan" | plan visible | visible |
| executing | disabled, "Executing..." | progress shown | live events |
| complete | enabled | summary shown | visible |
| error | enabled | error if relevant | error logged |

---

## 6. File architecture

```
frontend/
  index.html
  vite.config.js
  package.json

  styles/
    main.css

  app/
    main.js
    bootstrap.js

  api/
    client.js

  stream/
    sse.js

  state/
    store.js

  events/
    router.js

  panels/
    conversation.js
    plan.js
    activity.js

  layout/
    drawer.js
    composer.js
```

---

## 7. Out of scope (Phase 1)

- Auth / login
- Multiple sessions / session list
- Filesystem tree visualization
- Mobile layout
- Dark theme
- Undo
- Keyboard shortcuts
