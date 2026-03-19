# AIJAH frontend

## Where the backend boundary lives

Connection logic is split on purpose so it can become TypeScript without rewriting the UI:

| Layer | Path |
|--------|------|
| API base URL | `api/config.js` |
| HTTP transport | `api/http.js` |
| REST contract (one function per route) | `api/backendApi.js` |
| SSE stream parsing | `api/sse.js` |
| `/health` helpers | `api/health.js` |
| JSDoc placeholders for types | `api/types.js` |

`main.js` only wires DOM + panels and imports from `api/*`.

`demo/demoMode.js` is offline-only (no `fetch`).

See **`docs/FE_BE_INTEGRATION.md`** for the wire contract.

## Scripts

- `npm run dev` — Vite on port 3000, `/api` proxied to FastAPI on 8000
- `npm run build` / `npm run preview`

## Docker (production-like UI)

Compose builds this image with **`VITE_API_BASE=/api`** and nginx proxies **`/api/*`** → **`backend:8000`**. Open **`http://localhost:3003`**. See **`docs/DOCKER.md`**.
