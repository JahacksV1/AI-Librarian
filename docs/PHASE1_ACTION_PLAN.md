# Phase 1 — Clear Action Plan

> **TL;DR:** `/health` is a *verification step*, not a separate feature. It proves the whole stack works. Run the steps below once, then move on to your other Layer 1 work.

---

## Where `/health` Fits

```
Phase 1 Infrastructure (Caprice's track)     Phase 1 Backend (your track)
────────────────────────────────────        ─────────────────────────────
1. docker compose up                         Steps 1–5: DB, tools, MCP ✓
2. Postgres port 5433                        Steps 6–9: agent loop, routes, frontend
3. Init scripts (001, 002, 003)
4. Pull Ollama model (qwen2.5)
                    │
                    ▼
            VERIFICATION CHECKLIST
            ─────────────────────
            • docker compose up — no errors
            • Backend logs: "Application startup complete"
            • Postgres: tables exist, seed data present
            • GET /health → {"status":"ok","db":"connected","ollama":"reachable"}  ← this one
```

**`/health`** = one-line proof that backend + DB + Ollama are all talking. It's the last checkbox before you say "infrastructure is done."

---

## What Went Wrong (and what was fixed)

| Problem | Cause | Fix |
|---------|-------|-----|
| `/health` returned 404 | Old backend image (no route) | Rebuild backend |
| Backend crashed on startup | SQLAlchemy `Mapped["X" \| None]` annotation bug | Fixed in `db/models.py` — union must be inside the string: `Mapped["X \| None"]` |

The annotation fix is already in place. You just need to rebuild and verify.

---

## Exact Terminal Steps (run once)

Copy-paste this block. Run it in order.

```bash
cd /Users/amira/AIJAH/AI-Librarian

# 1. Rebuild backend with the fixed models
docker compose build --no-cache backend

# 2. Start everything
docker compose up -d

# 3. Wait for backend to finish startup (lifespan does DB + MCP init)
sleep 8

# 4. Verify /health
curl http://localhost:8000/health
```

**Expected output:**
```json
{"status":"ok","db":"connected","ollama":"reachable"}
```

If you get that, **infrastructure verification is done.** Move on.

---

## If /health still fails

Run:
```bash
docker compose logs backend --tail=50
```

Look for Python tracebacks. Share the output if you need help.

---

## What's Done vs What's Left (Layer 1)

### ✅ Done (Infrastructure — Caprice's track)
- docker-compose.yml, 4 services
- Postgres port 5433
- Init scripts: 001_create_enums, 002_create_tables, 003_seed
- Ollama model pulled (qwen2.5)
- Sandbox mounted

### ✅ Done (Backend — your track)
- Steps 1–5: config, db layer, enums, models, safety, all 6 MCP tools
- Steps 6–8: agent loop, context, routes, main.py
- `/health` route exists (in api/routes.py)

### ⏳ To verify (one-time)
- Run the 4 terminal steps above
- Confirm `/health` returns OK

### 📋 Still to do (from SYNC roadmap)
- **Step 9:** Frontend — `app.js`, `style.css` (message input, plan display, approve/reject)
- **End-to-end demo:** Run through all 9 steps in V1_CONTRACT.md

---

## Summary

1. **`/health`** = verification that backend + DB + Ollama work. Not a feature to build.
2. **Run the 4 steps** above once. That should fix it.
3. **Then** focus on Step 9 (frontend) and the end-to-end demo.
4. You don't need to "finish" /health as a separate task — it's a checkbox. Once it passes, you're done with that part.
