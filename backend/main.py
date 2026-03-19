from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

from agent.loop import initialize_mcp_tool_cache
from api.routes import router as api_router
from db.connection import db_manager
from mcp_server import mcp_http_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Startup gates: DB must be reachable and MCP tools must be discoverable.
    log.info("startup: checking DB connection...")
    await db_manager.healthcheck()
    log.info("startup: DB connected")
    log.info("startup: initializing MCP tool cache...")
    await initialize_mcp_tool_cache()
    log.info("startup: MCP tool cache ready")
    yield
    log.info("shutdown: complete")


app = FastAPI(lifespan=lifespan)
app.include_router(api_router)
app.mount("/mcp", mcp_http_app)


@app.get("/")
async def read_root() -> dict[str, str]:
    return {"status": "ok"}