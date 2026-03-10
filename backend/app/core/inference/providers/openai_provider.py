"""OpenAI inference provider — uses GPT chat completions with JSON system prompt."""
from __future__ import annotations

import json
import re
import time

from app.core.schemas.pipeline import ClassificationResult, FusionResult, MisinfoLabel

_SYSTEM_PROMPT = """\
You are a public-health fact-checking assistant.

Given the video content below, respond ONLY with a JSON object (no markdown, no prose):
{
  "label": "MISINFO|NO_MISINFO|DEBUNKING|CANNOT_RECOGNIZE",
  "confidence": 0.87,
  "explanation": "2-4 sentence explanation of your decision.",
  "evidence_snippets": ["exact quote 1", "exact quote 2"]
}

Choose exactly one label:
- MISINFO: video contains false or misleading health information
- NO_MISINFO: video contains accurate health information
- DEBUNKING: video explicitly corrects misinformation
- CANNOT_RECOGNIZE: cannot determine (insufficient content)
"""


class OpenAIProvider:
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def classify(self, fusion: FusionResult) -> ClassificationResult:
        start = time.time()
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": fusion.combined_content or fusion.transcript},
            ],
            temperature=0,
        )
        latency_ms = int((time.time() - start) * 1000)
        content = resp.choices[0].message.content or ""
        parsed = _parse_json(content)
        return ClassificationResult(
            label=_safe_label(parsed.get("label")),
            confidence=float(parsed.get("confidence", 0.5)),
            explanation=str(parsed.get("explanation", "")),
            evidence_snippets=_safe_list(parsed.get("evidence_snippets")),
            provider="openai",
            model_used=self._model,
            latency_ms=latency_ms,
        )


def _parse_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    for m in re.finditer(r"\{.*\}", cleaned, flags=re.DOTALL):
        try:
            return json.loads(m.group(0))
        except Exception:
            continue
    return {}


def _safe_label(raw) -> MisinfoLabel:
    try:
        return MisinfoLabel(str(raw).strip().upper().rstrip("."))
    except Exception:
        return MisinfoLabel.CANNOT_RECOGNIZE


def _safe_list(raw) -> list[str]:
    if isinstance(raw, list):
        return [str(i).strip() for i in raw if str(i).strip()]
    if isinstance(raw, str):
        return [s.strip() for s in raw.split("\n") if s.strip()]
    return []
