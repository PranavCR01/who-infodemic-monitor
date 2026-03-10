"""OCR text extraction from video frames using EasyOCR.

No Streamlit dependencies. GPU is disabled by default (CPU Docker containers).
"""
from __future__ import annotations

from typing import Any

import cv2
import numpy as np


class VideoTextExtractor:
    """Extract on-screen text from video frames."""

    def __init__(self, languages: list[str] | None = None, gpu: bool = False):
        self._reader = None
        self.languages = languages or ["en", "es"]
        self.gpu = gpu

    def _get_reader(self):
        """Lazy-load EasyOCR reader (downloads models on first call)."""
        if self._reader is None:
            import easyocr
            self._reader = easyocr.Reader(self.languages, gpu=self.gpu)
        return self._reader

    def extract_frames(self, video_path: str, fps: float = 1.0) -> list[np.ndarray]:
        """Sample frames from video at the given FPS rate."""
        frames: list[np.ndarray] = []
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Cannot open video: {video_path}")

        video_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        frame_interval = max(1, int(video_fps / fps))

        frame_count = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_count % frame_interval == 0:
                frames.append(frame)
            frame_count += 1

        cap.release()
        return frames

    def extract_text_from_frame(self, frame: np.ndarray) -> list[tuple[str, float]]:
        """Return [(text, confidence)] for a single frame, filtering below 0.3."""
        reader = self._get_reader()
        results = reader.readtext(frame)
        return [(text, conf) for (_, text, conf) in results if conf > 0.3]

    def extract_text_from_video(
        self,
        video_path: str,
        sample_fps: float = 1.0,
        min_confidence: float = 0.5,
    ) -> dict[str, Any]:
        """Extract all text from video by sampling frames.

        Returns:
            all_text: combined text from all frames
            unique_text: deduplicated text phrases
            frame_count: number of frames processed
            detections: list of {frame_idx, text, confidence}
            detection_count: total detections above threshold
        """
        frames = self.extract_frames(video_path, fps=sample_fps)

        detections: list[dict[str, Any]] = []
        text_list: list[str] = []

        for frame_idx, frame in enumerate(frames):
            for text, conf in self.extract_text_from_frame(frame):
                if conf >= min_confidence:
                    text_list.append(text)
                    detections.append(
                        {"frame_idx": frame_idx, "text": text, "confidence": round(conf, 3)}
                    )

        return {
            "all_text": " ".join(text_list),
            "unique_text": list(dict.fromkeys(text_list)),  # preserve insertion order
            "frame_count": len(frames),
            "detections": detections,
            "detection_count": len(detections),
        }
