# Feature Landscape

**Domain:** Production ML pipeline — health misinformation detection in short-form video
**Researched:** 2026-03-09
**Confidence:** HIGH (based on direct prototype source analysis + established production ML patterns)

---

## Context

This document maps the feature landscape for Milestone 3: porting the existing Streamlit prototype pipeline
(`pages/processes/`) into clean, production-grade modules and wiring them end-to-end through the Celery
task. The old repo code has been read directly — findings are based on actual prototype behavior, not
assumptions.

Prototype modules analyzed:
- `pages/processes/transcription.py` — Whisper-based transcription, Streamlit-coupled
- `pages/processes/ocr/text_extractor.py` — EasyOCR frame extraction, cleanly written
- `pages/processes/multimodal.py` — Fusion layer combining transcript + OCR
- `pages/processes/analysis.py` — LLM classification with JSON extraction, Streamlit-coupled

---

## Table Stakes

Features that must exist. Missing any one of these = the pipeline is not functional.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Transcription service (faster-whisper) | Core extraction step — without it, the LLM has no speech input | Medium | Prototype works; refactor is primarily removing Streamlit imports and adding error types |
| OCR service (EasyOCR) | Second modality — on-screen text is often the most misinformation-dense part of health TikToks | Medium | Prototype is clean; port is mostly a direct copy with typed interface |
| Multimodal fusion | Combines audio + visual text into LLM input; without it, classification is single-modality and less accurate | Low | Prototype already has good structure (`MultimodalExtractor.extract_all()`) |
| LLM inference with pluggable providers | Classification is the core product output; must support OpenAI at minimum | Medium | Prototype has 3 providers (OpenAI, Azure, Ollama) but Streamlit errors are embedded in fallback paths |
| Structured result output | `label + confidence + explanation + evidence_sentences` is the stated output contract | Low | Prototype's `_extract_json_block()` already handles this; port it cleanly with Pydantic validation |
| Result DB persistence | Without persisting to DB, `GET /jobs/{job_id}` never returns results; the whole API is useless | Medium | DB model + ORM write inside `process_video_task` |
| `GET /jobs/{job_id}` returns result | Status polling endpoint needs to expose classification output when `status=SUCCESS` | Low | Router change + schema extension |
| Error propagation (non-Streamlit) | Production code must raise typed exceptions, not call `st.error()` | Low | Systematic replacement of `st.error()` / `st.warning()` with `raise` or `logging.error()` |
| Logging (structured) | Workers need observable logs; plain `print()` is not sufficient for Docker log aggregation | Low | Use Python `logging` module with consistent logger names per module |

---

## Differentiators

Features that go beyond the minimum. Not required for the pipeline to function, but valued for
production quality, analyst UX, and demonstrating engineering maturity.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Pluggable provider interface (Protocol/ABC) | Swap OpenAI for Claude or Ollama via config, not code changes | Low | Define `InferenceProvider` protocol; implement adapters; task calls `provider.analyze(text)` |
| Pluggable transcription backend | Switch faster-whisper (local) vs Whisper API by env var, same calling contract | Low | Prototype already has `transcribe2()` pattern; formalize as `TranscriptionBackend` protocol |
| Confidence validation and clamping | LLM confidence scores are uncalibrated; clamp to [0,1], log when LLM emits out-of-range values | Very Low | 3 lines of validation in result parsing |
| Label validation against canonical schema | Reject `MISINFO.` or `misinfo` — normalize to canonical 4-label set | Very Low | Prototype already does `label.strip().upper().rstrip(".")` — port this exactly |
| Token budget guard | Prevent submitting transcripts that exceed model context limits; log warning | Low | Prototype has `_token_limit_warning()`; in production, raise instead of Streamlit warning |
| Per-job metadata in result | Store `model_used`, `provider`, `latency_ms`, `audio_char_count`, `ocr_detection_count` alongside result | Low | Adds observability; enables future eval comparisons without re-running |
| Eval benchmarking script | Run pipeline on a folder of videos, output CSV with `video_path, label, confidence, latency_ms` | Medium | Enables regression testing after model/prompt changes |
| Unit tests with mocked LLM/model calls | Verify parsing, error handling, label normalization without real API calls | Medium | Standard pytest + `unittest.mock.patch`; HIGH value for CI |
| Integration test: upload → job → result | End-to-end assertion that a full job produces a `Result` row with the expected shape | Medium | Requires test video fixture and mocked ML calls; validates full wiring |

---

## Anti-Features

Features to explicitly NOT build in this milestone.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Segment-level or frame-level classification | Doubles scope and complexity; video-level verdict is sufficient for v1 WHO use case | Flag as future milestone; `project.md` explicitly lists this as out-of-scope |
| Real-time streaming results (WebSocket/SSE) | Polling is sufficient; streaming requires significant API/worker architecture changes | Keep `GET /jobs/{job_id}` polling; revisit if UX feedback demands it |
| Frontend (React/Next.js) | Separate milestone per PROJECT.md; backend API-first approach is correct | Build API first, frontend later |
| Alembic migrations (this milestone) | The schema needs to stabilize (Result model must be added) before migration tooling is worth the setup time | Add Result model via `create_all`, flag Alembic as next-milestone work |
| Authentication / API keys | Out of scope per PROJECT.md; not needed for local WHO analyst use | Defer to a hardening milestone |
| Calibrated confidence scores | Requires labeled dataset + isotonic regression calibration; significant ML work | Report raw LLM confidence with clear disclaimer; calibration is a research milestone |
| Streaming transcription | faster-whisper does not natively support streaming; adds complexity for marginal latency gain on short videos | Batch transcription is fine for <60s videos |
| GPU support configuration | GPU adds Docker CUDA complexity; CPU inference is sufficient for prototype-to-production | Hardcode `device="cpu"` in transcription and OCR; leave GPU as config option for future |
| Multi-language OCR beyond en+es | Prototype defaults to `["en", "es"]`; adding languages increases EasyOCR memory and load time | Keep default; expose `OCR_LANGUAGES` env var for future extension |

---

## Prototype Gap Analysis

What the prototype does that needs to change (not just be ported):

### Critical Changes Required

**Streamlit removal from `transcription.py`:**
- `import streamlit as st` appears at line 7
- `st.error()` called in `_transcribe_local_faster_whisper()` — this will crash in a Docker worker context with no Streamlit session
- `st.info()` called in `transcriber()` — same problem
- `st.warning()` called in `split_video()`
- Fix: Replace all `st.*` calls with `logging.warning/error/info()` and `raise` where appropriate

**Streamlit removal from `analysis.py`:**
- `import streamlit as st` appears at line 6
- `st.error()` called in all three `analyze*` functions — these are the fallback error paths
- `_token_limit_warning()` uses `container.update()` (Streamlit widget API) — drop the Streamlit UI interaction, keep the token counting logic as a pure function that returns a warning string or raises
- Fix: Replace `st.error()` with `raise InferenceError(...)` or `logging.error()`; drop `container` parameter from function signatures

**Provider injection (no hardcoded clients):**
- Prototype passes `client` objects directly into function signatures (`analyze(transcript, model, client, container)`)
- Production: use dependency injection — `InferenceProvider` protocol with `OpenAIProvider`, `AzureProvider`, `OllamaProvider` adapters; the task resolves provider from settings at runtime

**Ollama URL hardcoded:**
- `url = "http://localhost:11434/api/chat"` in `analyze_local_mistral()` — will not work in Docker
- Fix: Read from `settings.OLLAMA_URL` (new config field), default to `http://ollama:11434`

### Clean Ports (minimal changes)

**`text_extractor.py` — nearly production-ready:**
- No Streamlit imports
- Clean class interface with typed return values
- Lazy model loading (`_get_reader()`) — correct pattern for avoiding startup cost
- Only change needed: replace `List`, `Dict`, `Tuple` from `typing` with built-in generic syntax (`list[...]`) for Python 3.11 compatibility; add `logging`

**`multimodal.py` — structurally sound:**
- Clean `MultimodalExtractor` class
- Good defensive dictionary access with `.get()` fallbacks
- Metadata tracking per-extraction (fps, confidence threshold) supports reproducibility
- Change needed: the import `from pages.processes.transcription import _transcribe_local_faster_whisper` is a direct old-repo import — replace with the new `TranscriptionService` interface

---

## Service Interface Design

### What a clean transcription service interface looks like

The prototype exposes multiple function variants (`transcribe`, `transcribe2`, `transcriber`, `_transcribe_openai`, `_transcribe_local_faster_whisper`) with inconsistent signatures. Production simplifies to a single interface.

**Pattern:** Protocol-based backend with a service class that delegates.

```python
# backend/app/core/extraction/transcription.py

from typing import Protocol

class TranscriptionBackend(Protocol):
    def transcribe(self, video_path: str) -> str:
        ...

class FasterWhisperBackend:
    def __init__(self, model_size: str = "base", device: str = "cpu", compute_type: str = "int8"):
        self._model = None  # lazy load
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type

    def transcribe(self, video_path: str) -> str:
        # lazy init, transcribe, return text
        ...

class OpenAIWhisperBackend:
    def __init__(self, api_key: str, model: str = "whisper-1"):
        ...

    def transcribe(self, video_path: str) -> str:
        ...

class TranscriptionService:
    def __init__(self, backend: TranscriptionBackend):
        self.backend = backend

    def transcribe(self, video_path: str) -> str:
        # validate path exists, call backend, handle errors with logging + raise
        ...
```

The Celery task builds a `TranscriptionService` from settings:
```python
backend = FasterWhisperBackend() if settings.TRANSCRIPTION_PROVIDER == "local" else OpenAIWhisperBackend(api_key=settings.OPENAI_API_KEY)
svc = TranscriptionService(backend=backend)
transcript = svc.transcribe(video_path)
```

**Why this is better than the prototype:**
- One calling convention (`svc.transcribe(path)`) instead of 5 function variants
- Provider selection is in config, not in caller code
- Backend can be replaced (or mocked in tests) by passing a different object
- No Streamlit, no hardcoded model names in function calls

### What a clean inference provider interface looks like

```python
# backend/app/core/inference/providers/base.py

from typing import Protocol
from app.core.schemas.result import ClassificationResult

class InferenceProvider(Protocol):
    def classify(self, text: str) -> ClassificationResult:
        ...
```

`ClassificationResult` is a Pydantic model (see Result Schema section below). Each provider implements `classify(text) -> ClassificationResult`. The provider is resolved from settings and injected into the pipeline function.

---

## Result Schema

### What a proper result schema looks like

The prototype dict (`label`, `keywords`, `confidence`, `explanation`, `evidence_sentences`, `time_taken_secs`) is the right starting point. Production adds validation, type safety, and persistence metadata.

**Pydantic schema (`backend/app/core/schemas/result.py`):**

```python
from enum import Enum
from pydantic import BaseModel, Field, field_validator

class MisinfoLabel(str, Enum):
    MISINFO = "MISINFO"
    NO_MISINFO = "NO_MISINFO"
    DEBUNKING = "DEBUNKING"
    CANNOT_RECOGNIZE = "CANNOT_RECOGNIZE"

class ClassificationResult(BaseModel):
    label: MisinfoLabel
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str
    evidence_sentences: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    model_used: str
    provider: str
    latency_ms: int

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))
```

**DB model (`backend/app/db/models/result.py`):**

```python
class Result(Base):
    __tablename__ = "results"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False, unique=True)
    label: Mapped[str] = mapped_column(SAEnum(MisinfoLabel), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_snippets: Mapped[dict] = mapped_column(JSON, nullable=True)
    keywords: Mapped[dict] = mapped_column(JSON, nullable=True)
    model_used: Mapped[str] = mapped_column(nullable=True)
    provider: Mapped[str] = mapped_column(nullable=True)
    latency_ms: Mapped[int] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
```

**What the GET /jobs/{job_id} response looks like when SUCCESS:**
```json
{
  "job_id": "abc-123",
  "status": "SUCCESS",
  "result": {
    "label": "MISINFO",
    "confidence": 0.91,
    "explanation": "The video claims vaccines cause autism, which contradicts established medical consensus.",
    "evidence_sentences": [
      "vaccines are proven to cause autism in children",
      "doctors won't tell you this"
    ],
    "keywords": ["vaccine", "autism", "misinformation", "health"],
    "model_used": "gpt-4o",
    "provider": "openai",
    "latency_ms": 3420
  }
}
```

### What table stakes vs differentiating means for result schema

**Table stakes (must have):**
- `label` — from canonical 4-label set, validated
- `confidence` — float [0,1], clamped
- `explanation` — human-readable reasoning (2-4 sentences)
- `evidence_sentences` — verbatim quotes from transcript/OCR that drove the decision

**Differentiating (adds value):**
- `keywords` — content summary, useful for dashboard filtering
- `model_used` + `provider` — audit trail; lets analysts compare GPT-4o vs Claude results
- `latency_ms` — operational metric; flags slow providers
- Future: `calibrated_confidence` (isotonic regression), `segment_breakdowns`, `source_credibility_score`

**Anti-pattern — do NOT add:**
- A raw `raw_llm_response` field in the API response — log it server-side, never expose to clients
- Nullable `label` — if classification fails, the label is `CANNOT_RECOGNIZE`, not NULL

---

## Testing Patterns

### Standard for ML pipeline testing in this codebase

**Stack:** pytest + unittest.mock.patch. No additional frameworks needed.

**Test dependencies to add to `backend/pyproject.toml`:**
```toml
[project.optional-dependencies]
test = [
    "pytest>=8.0",
    "pytest-cov>=4.0",
    "httpx>=0.27",      # required by FastAPI TestClient
    "pytest-mock>=3.12",
]
```

### Unit tests with mocks — the right pattern for each module

**Rule:** Mock at the boundary of the system under test. Never mock internal logic.

**Transcription unit tests:**
- Test `FasterWhisperBackend.transcribe()` by mocking `WhisperModel` constructor and `model.transcribe()`
- Test `TranscriptionService` error handling by mocking backend to raise `Exception`; assert `TranscriptionError` is raised
- Do NOT mock file I/O — use `tmp_path` pytest fixture with a real (tiny) test video or wav file

```python
def test_transcription_returns_text(monkeypatch, tmp_path):
    fake_segments = [Mock(text=" Hello world")]
    monkeypatch.setattr("faster_whisper.WhisperModel.transcribe", lambda *a, **kw: (fake_segments, None))
    # ... assert result == "Hello world"
```

**OCR unit tests:**
- Mock `easyocr.Reader.readtext()` to return a list of `(bbox, text, confidence)` tuples
- Test frame sampling logic with a synthetic video (or mock `cv2.VideoCapture`)
- Test confidence filtering: assert detections below `min_confidence` are excluded

**Inference unit tests:**
- Mock the HTTP call (OpenAI client or `requests.post` for Ollama) to return a known JSON response
- Test `_extract_json_block()` exhaustively — this is pure logic with no IO, test it directly:
  - Valid JSON response → correct fields
  - JSON wrapped in markdown fences → stripped and parsed
  - Malformed response → `CANNOT_RECOGNIZE` fallback
  - Out-of-range confidence (1.5) → clamped to 1.0
  - Label normalization: `"misinfo."` → `"MISINFO"`
- Test each provider adapter independently

**Test file structure:**
```
backend/app/tests/
├── conftest.py                  # shared fixtures: db_session, client, tmp_video
├── unit/
│   ├── test_transcription.py    # TranscriptionService, FasterWhisperBackend
│   ├── test_ocr.py              # VideoTextExtractor
│   ├── test_inference.py        # _extract_json_block, provider adapters
│   └── test_result_schema.py    # Pydantic validators (confidence clamping, label enum)
└── integration/
    ├── test_upload_flow.py       # POST /videos/upload → Video row
    ├── test_job_flow.py          # POST /jobs/create → GET /jobs/{id}
    └── test_pipeline.py          # upload → job → mock pipeline → result in GET response
```

### Integration test pattern

Integration tests use `TestClient` (synchronous HTTPX wrapper) with a SQLite in-memory DB override. They do NOT require Docker.

```python
# conftest.py
@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

The end-to-end integration test (upload → job → result):
1. Upload a tiny real `.mp4` test fixture (kept in `backend/app/tests/fixtures/`)
2. Call `POST /jobs/create` — mock `process_video_task.delay` to avoid needing a real worker
3. Directly call the task function with a test DB session — `process_video_task(job_id)` — with mocked ML calls
4. Assert `GET /jobs/{job_id}` returns `status=SUCCESS` and `result.label` is one of the 4 canonical labels

**Why mock the Celery task dispatch but call the task function directly:**
- Testing `task.delay()` requires a running Celery worker — too heavy for unit/integration tests
- Testing the task function directly (synchronously) validates all pipeline logic
- This is the standard pattern for Celery + pytest

### Eval benchmarking scaffold

The eval script (`scripts/eval_pipeline.py` or `backend/scripts/`) is NOT a test — it is a measurement tool.

Purpose: given a folder of labeled videos, run the full pipeline and output:
```
video_path, true_label, predicted_label, confidence, latency_ms, model_used, transcript_chars, ocr_chars
```

Pattern:
```python
# scripts/eval_pipeline.py
import csv
from pathlib import Path
from app.core.pipeline import run_pipeline  # the wired-up pipeline function

results = []
for video_path in Path(args.input_dir).glob("*.mp4"):
    result = run_pipeline(str(video_path))
    results.append({
        "video": video_path.name,
        "label": result.label,
        "confidence": result.confidence,
        "latency_ms": result.latency_ms,
    })

with open(args.output_csv, "w") as f:
    writer = csv.DictWriter(f, fieldnames=results[0].keys())
    writer.writeheader()
    writer.writerows(results)
```

This is table stakes for an ML pipeline — without it, there is no way to know if a model or prompt change improved or regressed accuracy.

---

## Feature Dependencies

```
TranscriptionService
    → requires: faster-whisper or OpenAI API key in settings
    → produces: transcript (str)

OCRService
    → requires: EasyOCR models (auto-downloaded on first use), OpenCV
    → produces: visual_text, detections (list)

MultimodalFusion
    → requires: TranscriptionService, OCRService
    → produces: combined_content (str), metadata (dict)

InferenceService
    → requires: MultimodalFusion output, LLM provider config
    → produces: ClassificationResult (Pydantic model)

Result DB write
    → requires: InferenceService output, Job.id, DB session
    → produces: Result row in PostgreSQL

GET /jobs/{job_id} with result
    → requires: Result row exists for job_id

Unit tests
    → requires: pytest, httpx, pytest-mock in pyproject.toml

Integration tests
    → requires: test fixture video file, SQLite in-memory DB (no Docker)

Eval script
    → requires: complete wired pipeline (all above), labeled video folder
```

---

## MVP Recommendation

For this milestone, prioritize in this exact order:

1. **Port + clean `OCRService`** — least coupling to remove; `text_extractor.py` is nearly production-ready; gives a green path through the pipeline first
2. **Port + clean `TranscriptionService`** — remove Streamlit, add Protocol interface, lazy model loading
3. **Port + clean `InferenceService`** — remove Streamlit, add typed provider adapters (OpenAI first), validate result schema with Pydantic
4. **Add `Result` DB model** — minimal: `job_id`, `label`, `confidence`, `explanation`, `evidence_snippets`
5. **Wire `process_video_task`** — call extraction → fusion → inference → persist `Result`
6. **Extend `GET /jobs/{job_id}`** — return `result` dict when `status=SUCCESS`
7. **Unit tests** — `test_inference.py` first (pure logic, highest value); then transcription and OCR
8. **Integration test** — upload → job → result assertion

Defer to next milestone: Alembic migrations, eval benchmarking script, calibrated confidence, additional LLM providers (Azure, Ollama), token budget guard.

---

## Confidence Notes

| Area | Confidence | Basis |
|------|------------|-------|
| Prototype behavior | HIGH | Direct source code read |
| Streamlit removal scope | HIGH | Direct source code read; all `st.*` calls identified |
| Service interface patterns | HIGH | Standard Python Protocol/DI pattern; no library-specific risk |
| Result schema design | HIGH | Standard Pydantic v2; matches existing DB model conventions in codebase |
| Test patterns | HIGH | Standard pytest + unittest.mock; no exotic dependencies |
| Eval script pattern | MEDIUM | Standard pattern; exact script structure may need adjustment to fit `run_pipeline()` signature once defined |

---

*Research: 2026-03-09*
