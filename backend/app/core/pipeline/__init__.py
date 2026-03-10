"""Pipeline runner — pure function, no DB session.

DB writes happen in tasks.py after this returns.
"""
from __future__ import annotations

from app.core.extraction.multimodal import MultimodalFusion
from app.core.inference import get_provider
from app.core.schemas.pipeline import ClassificationResult, FusionResult


def run_pipeline(video_path: str) -> tuple[FusionResult, ClassificationResult]:
    """Full pipeline: video file → (FusionResult, ClassificationResult).

    Steps:
    1. Fuse transcript + OCR into FusionResult
    2. Pass FusionResult to configured inference provider
    3. Return both (FusionResult carries combined_content for DB persistence)
    """
    fusion = MultimodalFusion().fuse(video_path)
    provider = get_provider()
    classification = provider.classify(fusion)
    return fusion, classification
