"""Tests for Settings new ML configuration fields (INFRA-03).

RED PHASE: These tests fail until Plan 01 adds the fields to config.py.
"""
import pytest


def test_settings_defaults():
    """Settings loads all new env vars with sensible defaults."""
    from app.core.config import settings

    # Transcription
    assert hasattr(settings, "WHISPER_PROVIDER"), "WHISPER_PROVIDER not in Settings"
    assert hasattr(settings, "WHISPER_MODEL"), "WHISPER_MODEL not in Settings"
    assert settings.WHISPER_PROVIDER == "faster_whisper"
    assert settings.WHISPER_MODEL == "base"

    # Inference
    assert hasattr(settings, "INFERENCE_PROVIDER"), "INFERENCE_PROVIDER not in Settings"
    assert hasattr(settings, "OPENAI_API_KEY"), "OPENAI_API_KEY not in Settings"
    assert hasattr(settings, "ANTHROPIC_API_KEY"), "ANTHROPIC_API_KEY not in Settings"
    assert hasattr(settings, "ANTHROPIC_MODEL"), "ANTHROPIC_MODEL not in Settings"
    assert hasattr(settings, "OLLAMA_BASE_URL"), "OLLAMA_BASE_URL not in Settings"
    assert hasattr(settings, "OLLAMA_MODEL"), "OLLAMA_MODEL not in Settings"
    assert settings.INFERENCE_PROVIDER == "openai"
    assert settings.ANTHROPIC_MODEL == "claude-opus-4-6"
    assert settings.OLLAMA_BASE_URL == "http://ollama:11434"
    assert settings.OLLAMA_MODEL == "mistral"
