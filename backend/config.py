from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5"
    sandbox_root: str = "/sandbox"
    mcp_mount_path: str = "/mcp"

    class Config:
        env_file = ".env"


settings = Settings()
