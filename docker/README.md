# Docker

Partner's domain. Files that live here:

- `docker-compose.yml` — defines four services: `frontend`, `backend`, `postgres`, `ollama`
- `postgres/init/` — runs migration SQL on first boot (copy from `backend/db/migrations/`)

## Services

| Service    | Port  | Image                  |
|------------|-------|------------------------|
| frontend   | 3000  | built from `frontend/Dockerfile` |
| backend    | 8000  | built from `backend/Dockerfile`  |
| postgres   | 5432  | `postgres:16`          |
| ollama     | 11434 | `ollama/ollama`        |

## Environment

Copy `.env.example` to `.env` at the repo root and fill in values.
All services read from the same `.env` via `env_file: .env` in compose.

## Sandbox Volume

Mount `./sandbox` into both `backend` and `ollama` containers at `/sandbox`.
This is `SANDBOX_ROOT` — the only path the agent is allowed to touch.
