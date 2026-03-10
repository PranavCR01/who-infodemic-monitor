"""Inference provider factory.

Usage:
    from app.core.inference import get_provider
    provider = get_provider()
    result = provider.classify(fusion_result)
"""
from __future__ import annotations

from app.core.config import settings


def get_provider():
    """Return the configured inference provider instance."""
    name = settings.INFERENCE_PROVIDER
    if name == "anthropic":
        from app.core.inference.providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider(
            api_key=settings.ANTHROPIC_API_KEY,
            model=settings.ANTHROPIC_MODEL,
        )
    if name == "ollama":
        from app.core.inference.providers.ollama_provider import OllamaProvider
        return OllamaProvider(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_MODEL,
        )
    # default: openai
    from app.core.inference.providers.openai_provider import OpenAIProvider
    return OpenAIProvider(
        api_key=settings.OPENAI_API_KEY,
        model="gpt-4o",
    )
