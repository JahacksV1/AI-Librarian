from __future__ import annotations

from agent.providers.base import ModelProvider
from db.enums import ModelProviderType


def get_provider() -> ModelProvider:
    """Return the model provider based on MODEL_PROVIDER in settings.

    Imports are deferred so that providers with optional SDK dependencies
    (anthropic, openai) don't fail at import time if their packages aren't installed.
    """
    from config import settings

    name = settings.model_provider.upper()

    if name == ModelProviderType.OLLAMA.value:
        from agent.providers.ollama import OllamaProvider
        return OllamaProvider()

    if name == ModelProviderType.ANTHROPIC.value:
        from agent.providers.anthropic import AnthropicProvider
        return AnthropicProvider()

    if name == ModelProviderType.OPENAI.value:
        from agent.providers.openai import OpenAIProvider
        return OpenAIProvider()

    valid = ", ".join(v.value for v in ModelProviderType)
    raise ValueError(
        f"Unknown MODEL_PROVIDER: '{settings.model_provider}'. "
        f"Valid values: {valid}"
    )


__all__ = ["ModelProvider", "get_provider"]
