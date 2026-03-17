from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from agent.loop import initialize_mcp_tool_cache
from api.routes import router as api_router
from db.connection import db_manager
from mcp_server import mcp_http_app


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Startup gates: DB must be reachable and MCP tools must be discoverable.
    await db_manager.healthcheck()
    await initialize_mcp_tool_cache()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(api_router)
app.mount("/mcp", mcp_http_app)


@app.get("/")
async def read_root() -> dict[str, str]:
    return {"status": "ok"}