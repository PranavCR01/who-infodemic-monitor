"""Tests for pipeline Pydantic schemas (SCHEMA-01, SCHEMA-02).

RED PHASE: These tests fail until Plan 02 creates app/core/schemas/pipeline.py.
"""
import pytest


def test_fusion_result():
    """FusionResult validates all required fields."""
    from app.core.schemas.pipeline import FusionResult

    result = FusionResult(
        transcript="spoken words here",
        visual_text="on-screen text here",
        combined_content="combined text",
        metadata={"frame_count": 30},
    )
    assert result.transcript == "spoken words here"
    assert result.visual_text == "on-screen text here"
    assert result.combined_content == "combined text"
    assert result.metadata == {"frame_count": 30}


def test_fusion_result_rejects_missing_fields():
    """FusionResult raises ValidationError when required field is missing."""
    from pydantic import ValidationError
    from app.core.schemas.pipeline import FusionResult

    with pytest.raises(ValidationError):
        FusionResult(transcript="only transcript")  # missing visual_text, combined_content, metadata


def test_classification_result():
    """ClassificationResult validates fields and clamps confidence."""
    from app.core.schemas.pipeline import ClassificationResult, MisinfoLabel

    result = ClassificationResult(
        label=MisinfoLabel.MISINFO,
        confidence=0.95,
        explanation="This video makes false health claims.",
        evidence_snippets=["snippet A", "snippet B"],
        provider="openai",
        model_used="gpt-4o",
        latency_ms=1200,
    )
    assert result.label == MisinfoLabel.MISINFO
    assert result.confidence == 0.95
    assert len(result.evidence_snippets) == 2


def test_classification_result_clamps_confidence():
    """Confidence values outside [0.0, 1.0] are clamped, not rejected."""
    from app.core.schemas.pipeline import ClassificationResult, MisinfoLabel

    high = ClassificationResult(
        label=MisinfoLabel.NO_MISINFO,
        confidence=1.5,  # too high — must clamp to 1.0
        explanation="ok",
        evidence_snippets=[],
        provider="openai",
        model_used="gpt-4o",
        latency_ms=500,
    )
    assert high.confidence == 1.0

    low = ClassificationResult(
        label=MisinfoLabel.CANNOT_RECOGNIZE,
        confidence=-0.1,  # too low — must clamp to 0.0
        explanation="unclear",
        evidence_snippets=[],
        provider="openai",
        model_used="gpt-4o",
        latency_ms=300,
    )
    assert low.confidence == 0.0


def test_misinfo_label_serializes_as_string():
    """MisinfoLabel enum members serialize as plain string values in JSON."""
    import json
    from app.core.schemas.pipeline import ClassificationResult, MisinfoLabel

    result = ClassificationResult(
        label=MisinfoLabel.DEBUNKING,
        confidence=0.8,
        explanation="This video corrects misinformation.",
        evidence_snippets=[],
        provider="anthropic",
        model_used="claude-opus-4-6",
        latency_ms=2000,
    )
    serialized = json.loads(result.model_dump_json())
    assert serialized["label"] == "DEBUNKING", f"Expected 'DEBUNKING' string, got {serialized['label']!r}"
