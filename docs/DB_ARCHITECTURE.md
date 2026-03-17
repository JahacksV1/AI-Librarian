# Database Architecture Note

This note explains what the Phase 1 database layer is for, how to use it, and what to watch out for as AIJAH grows.

## Why this folder exists

The `backend/db/` folder gives AIJAH a single, consistent database layer.

It separates the database into four responsibilities:

- `enums.py`: allowed typed values used across Python, Postgres, and the frontend
- `migrations/`: the SQL contract that actually creates enums and tables in Postgres
- `connection.py`: the shared gateway for opening and closing DB sessions safely
- `models.py`: the Python-side table definitions used by backend code

This means later code should reuse the DB layer rather than recreating table logic, enum strings, or connection setup.

## File by file

### `enums.py`
Use this whenever code needs a known state or typed value.

Examples:
- `PlanStatus.APPROVED`
- `ActionStatus.PENDING`
- `SessionMode.CHAT`

Important rule:
- Never use bare strings in business logic when an enum already exists.

If a new enum value is needed later, update all three places:
1. `docs/TYPE_LEDGER.md`
2. `backend/db/enums.py`
3. a Postgres migration that updates the enum type in the database

Do not just edit `enums.py` and assume the database will match.

### `migrations/`
These files are the real schema contract.

- `001_create_enums.sql` creates the Postgres enum types
- `002_create_tables.sql` creates the Phase 1 tables and indexes

The database is created from these files, not from SQLAlchemy alone.

### `connection.py`
This file is the shared DB access point.

It creates:
- one async engine
- one session factory
- one safe `session()` context manager
- one `healthcheck()` helper

This file should be reused by:
- API routes
- MCP tools
- agent loop code
- startup / shutdown logic

Important rule:
- Use `async with db_manager.session() as session:` instead of creating ad hoc connections.

Important warning:
- The current pattern does not auto-commit writes.
- Any code that creates or updates rows must call `await session.commit()` intentionally.
- If a future write path forgets to commit, the work may appear to succeed in code but never persist to Postgres.

### `models.py`
This file defines ORM models. Here, "model" means database model, not AI model.

Examples:
- `User` maps to the `users` table
- `Session` maps to the `sessions` table
- `Plan` maps to the `plans` table
- `TaskState` maps to the `task_state` table

This file exists so Python code can work with classes and fields instead of rewriting raw SQL everywhere.

Important rule:
- `models.py` should stay focused on schema definitions and relationships.
- Avoid putting business logic here. Keep business logic in routes, tools, services, or the agent loop.

## Is `models.py` too big?

Not for Phase 1.

A single ORM file around this size is normal when a project has a dozen related tables. Right now it is still one coherent responsibility: database schema definitions.

Possible future split, when Phase 2 or 3 adds more tables:
- `db/models/core.py`
- `db/models/planning.py`
- `db/models/filesystem.py`
- `db/models/memory.py`

That is a future cleanup, not something required right now.

## How these files get used later

The normal flow will be:

1. FastAPI starts up
2. The backend imports `db_manager` from `connection.py`
3. A route, MCP tool, or agent function opens a DB session
4. That code imports models from `models.py`
5. It reads or writes rows using those models
6. It calls `await session.commit()` if data changed
7. The session closes safely

This is why these files matter now even before the full MCP or agent loop exists.

## Where MCP fits

The next phase of work uses the DB layer rather than replacing it.

MCP tools will do things like:
- scan folders
- create plans
- update task state
- write memory events
- execute approved actions

Those tools should not invent their own database access pattern.
They should reuse:
- `db/enums.py`
- `db/connection.py`
- `db/models.py`

## Where Ollama / AI fits

Ollama is already part of Phase 1.

From `docs/V1_CONTRACT.md`, the Phase 1 order is:
1. backend receives a message and calls Ollama successfully
2. backend discovers MCP tools and injects them into the prompt
3. model chooses tools when needed
4. tool results go back into context
5. agent produces a plan or response

So the rough stack is:
- DB layer stores state
- MCP tools read/write that state
- backend calls Ollama
- Ollama decides when to use MCP tools
- tool results and state changes flow back through the DB

The AI does not replace the DB layer. It sits on top of it.

## Things to keep looking out for

- Keep enum values aligned across `TYPE_LEDGER`, Python enums, and Postgres enums
- Do not forget `await session.commit()` after writes
- Do not put business logic directly into ORM model classes
- Do not create duplicate connection code outside `connection.py`
- Do not add Phase 2 tables or vector features into Phase 1 files
- Keep safety-critical state changes visible in the database, not only in memory

## Good default habits

- Reuse enums instead of strings
- Reuse `db_manager.session()` instead of custom connection code
- Let SQL migrations define schema changes
- Treat `models.py` as the Python mirror of the SQL schema
- Keep DB code boring, predictable, and consistent

## Current status

The Phase 1 DB folder is in a good place to support the next step: MCP tools and server wiring.

What exists now:
- enum definitions
- SQL migrations
- connection management
- ORM models

What comes next:
- sandbox safety module
- MCP tools that use the DB layer
- MCP server registration
- agent loop and Ollama integration
