"""Transcription module — no Streamlit dependencies.

Supports faster-whisper (local CPU) and OpenAI Whisper-1 (hosted).
Provider is selected via settings.WHISPER_PROVIDER.
"""
from __future__ import annotations

import contextlib
import os

from app.core.config import settings


def transcribe(video_path: str) -> str:
    """Transcribe audio from a video file. Returns the transcript string.

    Picks backend from settings.WHISPER_PROVIDER:
      - "faster_whisper": local CTranslate2 model (CPU, no GPU required)
      - "openai": OpenAI Whisper-1 API
    """
    provider = settings.WHISPER_PROVIDER
    if provider == "openai":
        return _transcribe_openai(video_path)
    return _transcribe_faster_whisper(video_path)


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------

def _transcribe_faster_whisper(video_path: str) -> str:
    """Use local faster-whisper (CTranslate2) on CPU."""
    from faster_whisper import WhisperModel

    model = WhisperModel(
        settings.WHISPER_MODEL,
        device="cpu",
        compute_type="int8",
    )
    segments, _ = model.transcribe(video_path, beam_size=5)
    return " ".join(seg.text.strip() for seg in segments).strip()


def _transcribe_openai(video_path: str) -> str:
    """Use OpenAI Whisper-1 via the OpenAI Python client."""
    from openai import OpenAI

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    with open(video_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="text",
        )
    return resp if isinstance(resp, str) else getattr(resp, "text", str(resp))
