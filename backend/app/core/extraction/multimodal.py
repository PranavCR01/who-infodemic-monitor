"""Multimodal fusion — combines transcript + OCR into FusionResult.

Calls transcription and OCR modules, then builds the FusionResult schema
that gets passed to the inference provider.
"""
from __future__ import annotations

from app.core.extraction.ocr.text_extractor import VideoTextExtractor
from app.core.extraction.transcription import transcribe
from app.core.schemas.pipeline import FusionResult


class MultimodalFusion:
    """Fuse audio transcript and on-screen text for a video file."""

    def __init__(
        self,
        ocr_languages: list[str] | None = None,
        ocr_sample_fps: float = 1.0,
        ocr_min_confidence: float = 0.5,
        gpu: bool = False,
    ):
        self._ocr = VideoTextExtractor(languages=ocr_languages, gpu=gpu)
        self._ocr_fps = ocr_sample_fps
        self._ocr_confidence = ocr_min_confidence

    def fuse(self, video_path: str) -> FusionResult:
        """Run transcription + OCR and return a FusionResult."""
        transcript = transcribe(video_path)

        ocr = self._ocr.extract_text_from_video(
            video_path,
            sample_fps=self._ocr_fps,
            min_confidence=self._ocr_confidence,
        )
        visual_text: str = ocr.get("all_text", "")

        parts: list[str] = []
        if transcript:
            parts.append(f"[AUDIO TRANSCRIPT]\n{transcript}")
        if visual_text:
            parts.append(f"[ON-SCREEN TEXT]\n{visual_text}")
        combined = "\n\n".join(parts)

        metadata = {
            "audio_length_chars": len(transcript),
            "visual_length_chars": len(visual_text),
            "frames_processed": ocr.get("frame_count", 0),
            "ocr_detection_count": ocr.get("detection_count", 0),
            "ocr_sample_fps": self._ocr_fps,
            "ocr_confidence_threshold": self._ocr_confidence,
        }

        return FusionResult(
            transcript=transcript,
            visual_text=visual_text,
            combined_content=combined,
            metadata=metadata,
        )
