"""Pipeline data contracts.

All extraction and inference modules import from this file.
Do not split into multiple files — a single import source eliminates circular import risk.
"""
import enum
from typing import Any

from pydantic import BaseModel, field_validator


class MisinfoLabel(str, enum.Enum):
    """Canonical misinformation classification labels.

    Uses (str, enum.Enum) NOT enum.StrEnum — avoids SQLAlchemy mapped_column
    compatibility issues. Members serialize as plain string values in FastAPI
    JSON responses (e.g., "MISINFO" not 0).
    """
    MISINFO = "MISINFO"
    NO_MISINFO = "NO_MISINFO"
    DEBUNKING = "DEBUNKING"
    CANNOT_RECOGNIZE = "CANNOT_RECOGNIZE"


class FusionResult(BaseModel):
    """Output of MultimodalFusion.fuse() — combined transcript + OCR signals.

    Passed directly to InferenceProvider.classify().
    """
    transcript: str
    visual_text: str
    combined_content: str
    metadata: dict[str, Any]


class ClassificationResult(BaseModel):
    """Output of InferenceProvider.classify() — structured misinformation verdict.

    Persisted to the Result ORM model in Phase 4.
    label is stored as String in DB (not SAEnum) — validated here at application layer.
    """
    label: MisinfoLabel
    confidence: float
    explanation: str
    evidence_snippets: list[str]
    provider: str
    model_used: str
    latency_ms: int

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        """Clamp confidence to [0.0, 1.0]. LLM outputs are not always in range."""
        return max(0.0, min(1.0, v))
