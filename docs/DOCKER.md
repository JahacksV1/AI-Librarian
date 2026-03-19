# Docker vs local dev — ports, profiles, and what to run when

This doc matches **`docker-compose.yml`** and the frontend API layer (**`docs/FE_BE_INTEGRATION.md`**).

---

## Mental model: two ways to work

| Mode | What you run | Typical use |
|------|----------------|-------------|
| **Local dev** | Postgres (Docker or local) + **uvicorn** + **`npm run dev` (Vite on 3000)** | Fast iteration, hot reload, `/api` proxy in Vite → `localhost:8000` |
| **Full stack in Compose** | **`docker compose up`** | Same URLs every time, closer to “prod-like”; UI is **built** static files + nginx **`/api` → backend** |

You do **not** run the Vite dev server inside the Compose `frontend` service — that image serves **built** assets from `npm run build`.

---

## Ports (host)

| Port | Service | Notes |
|------|---------|--------|
| **8000** | FastAPI | REST + SSE |
| **3003** | Frontend (nginx) | Static UI; API calls go to **`/api`** on same origin (proxied to backend) |
| **5433** | PostgreSQL | Host → container `5432` |
| **11434** | Ollama | Only with **`--profile local`** |

Vite **dev** uses **3000** on the host — not the Compose frontend port. That’s intentional: dev = Vite; Compose UI = 3003.

---

## Ollama profile (unchanged idea, still valid)

- **`MODEL_PROVIDER=ollama`** → you need a running Ollama instance the backend can reach.
- In Compose, start it with:  
  `docker compose --profile local up`  
  so the **`ollama`** service runs.
- **`anthropic` / `openai`** → **no** Ollama container; cloud keys in `.env` are enough.

The backend **does not** `depends_on: ollama` so you can use cloud providers without pulling Ollama. That’s still the right tradeoff.

---

## Is Docker “still good” with Vite + providers + future pgvector?

**Yes**, with one important distinction:

- **Postgres** in Compose is still the right place for the app DB. Later, **pgvector** is usually “change image or `CREATE EXTENSION` in init,” not a different orchestrator. You can stay on Compose.
- **Vite** stays a **dev/build tool**; production-like Compose serves **`dist/`** via nginx, not `vite dev`.
- **Multiple model providers** are **env-driven** (`MODEL_PROVIDER`, keys); Docker doesn’t need a fork per provider beyond optional Ollama profile.

---

## Testing while UI work is in flight

You don’t need the browser or the `frontend` service to validate the agent + API:

1. **Backend + DB:**  
   `docker compose up postgres backend`  
   (add `--profile local` + Ollama only if you test **ollama**.)
2. Run **`test_v1.py`**, **`test_provider_switch.py`**, etc. against **`http://localhost:8000`**.

That keeps CI/agent tests independent of Vite and nginx.

---

## Compose gaps we fixed (see repo)

1. **Frontend image** — must **`npm run build`**, not copy raw sources into nginx.
2. **Same-origin API in Compose** — nginx should **`proxy_pass`** **`/api`** → **`http://backend:8000`** (strip `/api`), with **proxy buffering off** for SSE.
3. **Build-time `VITE_API_BASE=/api`** so the built JS uses **`/api`** against the nginx host.

If anything drifts, check **`frontend/Dockerfile`**, **`frontend/nginx.conf`**, and **`docker-compose.yml`** `frontend.build.args`.
