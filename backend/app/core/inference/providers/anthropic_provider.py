"""Anthropic inference provider — uses tool_choice for guaranteed structured output."""
from __future__ import annotations

import time

from app.core.schemas.pipeline import ClassificationResult, FusionResult, MisinfoLabel

_CLASSIFICATION_TOOL = {
    "name": "classify_video",
    "description": "Classify a health-related video for misinformation.",
    "input_schema": {
        "type": "object",
        "properties": {
            "label": {
                "type": "string",
                "enum": ["MISINFO", "NO_MISINFO", "DEBUNKING", "CANNOT_RECOGNIZE"],
                "description": "Misinformation classification label.",
            },
            "confidence": {
                "type": "number",
                "description": "Confidence score between 0 and 1.",
            },
            "explanation": {
                "type": "string",
                "description": "2-4 sentence explanation of the decision.",
            },
            "evidence_snippets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "1-3 exact quotes from the content that influenced the decision.",
            },
        },
        "required": ["label", "confidence", "explanation", "evidence_snippets"],
    },
}

_SYSTEM_PROMPT = """\
You are a public-health fact-checking assistant. \
Analyze the provided video content and classify it for health misinformation. \
Use the classify_video tool to return your structured verdict.

Labels:
- MISINFO: contains false or misleading health information
- NO_MISINFO: contains accurate health information
- DEBUNKING: explicitly corrects misinformation
- CANNOT_RECOGNIZE: cannot determine (insufficient content)
"""


class AnthropicProvider:
    def __init__(self, api_key: str, model: str = "claude-opus-4-6"):
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def classify(self, fusion: FusionResult) -> ClassificationResult:
        start = time.time()
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            tools=[_CLASSIFICATION_TOOL],
            tool_choice={"type": "tool", "name": "classify_video"},
            messages=[
                {
                    "role": "user",
                    "content": fusion.combined_content or fusion.transcript,
                }
            ],
        )
        latency_ms = int((time.time() - start) * 1000)

        # With tool_choice forced, first content block is always a tool_use block.
        tool_input: dict = {}
        for block in resp.content:
            if block.type == "tool_use":
                tool_input = block.input or {}
                break

        return ClassificationResult(
            label=_safe_label(tool_input.get("label")),
            confidence=float(tool_input.get("confidence", 0.5)),
            explanation=str(tool_input.get("explanation", "")),
            evidence_snippets=_safe_list(tool_input.get("evidence_snippets")),
            provider="anthropic",
            model_used=self._model,
            latency_ms=latency_ms,
        )


def _safe_label(raw) -> MisinfoLabel:
    try:
        return MisinfoLabel(str(raw).strip().upper())
    except Exception:
        return MisinfoLabel.CANNOT_RECOGNIZE


def _safe_list(raw) -> list[str]:
    if isinstance(raw, list):
        return [str(i).strip() for i in raw if str(i).strip()]
    return []
