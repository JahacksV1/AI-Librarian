from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env from the project root (one level above this file's directory).
# This works whether mcp_server.py is run natively from the backend/ folder
# or whether settings are injected as real environment variables by Docker Compose.
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_PATH), extra="ignore")

    # --- Database ---
    database_url: str

    # --- Model provider ---
    model_provider: str = "ollama"
    model_name: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # --- Ollama (used when model_provider=ollama) ---
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5"

    # --- Sandbox ---
    sandbox_root: str = "/sandbox"

    # --- MCP ---
    mcp_mount_path: str = "/mcp"
    # When set, backend connects to MCP over HTTP (extracted container). When empty, uses in-process.
    mcp_url: str = ""

    # --- HTTP (optional; enables CORS when non-empty) ---
    # Comma-separated origins, e.g. http://localhost:3000,http://127.0.0.1:3000
    cors_origins: str = ""

    @property
    def effective_model_name(self) -> str:
        """Resolve the model name: explicit MODEL_NAME takes priority,
        then falls back to provider-specific defaults."""
        if self.model_name:
            return self.model_name

        defaults = {
            "ollama": self.ollama_model or "qwen2.5",
            "anthropic": "claude-3-5-haiku-20241022",
            "openai": "gpt-4o",
        }
        return defaults.get(self.model_provider.lower(), self.model_provider)


settings = Settings()
