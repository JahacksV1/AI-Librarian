from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent.loop import initialize_mcp_tool_cache
from api.routes import router as api_router
from config import settings
from db.connection import db_manager
from db.enums import ModelProviderType
from mcp_server import mcp_http_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)


def _validate_provider_config() -> None:
    """Fail fast if the selected provider is missing required config."""
    provider = settings.model_provider.upper()
    valid = {v.value for v in ModelProviderType}
    if provider not in valid:
        raise ValueError(
            f"Invalid MODEL_PROVIDER='{settings.model_provider}'. "
            f"Valid values: {', '.join(sorted(valid))}"
        )
    if provider == ModelProviderType.ANTHROPIC.value and not settings.anthropic_api_key:
        raise ValueError(
            "MODEL_PROVIDER=anthropic requires ANTHROPIC_API_KEY to be set."
        )
    if provider == ModelProviderType.OPENAI.value and not settings.openai_api_key:
        raise ValueError(
            "MODEL_PROVIDER=openai requires OPENAI_API_KEY to be set."
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    log.info("startup: validating provider config...")
    _validate_provider_config()
    log.info(
        "startup: provider=%s  model=%s",
        settings.model_provider,
        settings.effective_model_name,
    )
    log.info("startup: checking DB connection...")
    await db_manager.healthcheck()
    log.info("startup: DB connected")
    log.info("startup: initializing MCP tool cache...")
    await initialize_mcp_tool_cache()
    log.info("startup: MCP tool cache ready")
    yield
    log.info("shutdown: complete")


app = FastAPI(lifespan=lifespan)

_cors = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
if _cors:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router)
app.mount("/mcp", mcp_http_app)


@app.get("/")
async def read_root() -> dict[str, str]:
    return {"status": "ok"}