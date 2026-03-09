# Architecture Patterns: Pipeline Porting

**Domain:** Production ML pipeline — health misinformation detection in short-form video
**Researched:** 2026-03-09
**Overall confidence:** HIGH (patterns are stable, well-established Python production idioms; structural decisions derived from existing codebase analysis)

---

## Recommended Architecture

The production backend uses a **layered architecture** with a strict one-way dependency rule:

```
API Layer (routers/)
    |
Worker Layer (worker/tasks.py)
    |
Pipeline Layer (core/pipeline/)
    |
Domain Layer (core/extraction/, core/inference/)
    |
DB Layer (db/models/, db/session.py)
```

The pipeline layer is the key insertion point. `process_video_task` in the worker calls a single `run_pipeline()` function from `core/pipeline/pipeline.py`. That function orchestrates the three domain modules: extraction (transcription + OCR + fusion) and inference. The worker task handles DB lifecycle (PENDING → STARTED → SUCCESS/FAILED) and result persistence; the pipeline modules handle domain logic only and have no DB awareness.

---

## Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `core/extraction/transcription.py` | Audio → text, provider-switchable (faster-whisper / OpenAI Whisper API) | Nothing (pure function) |
| `core/extraction/ocr/text_extractor.py` | Video frames → on-screen text via EasyOCR | Nothing (pure function) |
| `core/extraction/multimodal.py` | Combine transcript + OCR text into structured fusion dict | transcription.py, ocr/text_extractor.py |
| `core/inference/classifier.py` | Define `LLMProvider` Protocol; factory function to build provider from config | providers/ |
| `core/inference/providers/openai.py` | OpenAI GPT-4o provider implementation | openai SDK |
| `core/inference/providers/anthropic.py` | Anthropic Claude provider implementation | anthropic SDK |
| `core/inference/providers/ollama.py` | Ollama local model provider implementation | requests/httpx |
| `core/pipeline/pipeline.py` | Orchestrate transcription → OCR → fusion → inference in sequence | extraction/, inference/ |
| `core/schemas/pipeline.py` | Pydantic models for intermediate and final data structures | (used by all layers) |
| `worker/tasks.py` | DB status management, call pipeline, persist result | pipeline.py, db/models/ |
| `db/models/result.py` | Persist structured inference output | db/base.py |
| `api/routers/jobs.py` | Expose result fields in GET /jobs/{job_id} when SUCCESS | db/models/result.py |

---

## Provider Abstraction Pattern

**Use `typing.Protocol` (structural subtyping), not ABC.**

Rationale: Protocol gives duck-typing — providers don't need to import a base class, making each provider file independently testable and independently replaceable. ABC requires all providers to inherit from the base, creating coupling. Protocol is idiomatic modern Python (3.8+) and is the pattern used by the `openai` SDK's own type hints.

### The Protocol definition

```python
# backend/app/core/inference/classifier.py

from typing import Protocol, runtime_checkable
from app.core.schemas.pipeline import ClassificationResult, FusionResult


@runtime_checkable
class LLMProvider(Protocol):
    def classify(self, fusion: FusionResult) -> ClassificationResult:
        ...
```

Only one method on the Protocol: `classify(fusion: FusionResult) -> ClassificationResult`. Keep it narrow. Each provider is responsible for prompt construction, API call, JSON extraction, and retry logic internally.

### Factory function (not a registry class)

```python
# backend/app/core/inference/classifier.py

from app.core.core.config import settings
from app.core.inference.providers.openai import OpenAIProvider
from app.core.inference.providers.anthropic import AnthropicProvider
from app.core.inference.providers.ollama import OllamaProvider


def get_provider() -> LLMProvider:
    provider = settings.LLM_PROVIDER  # "openai" | "anthropic" | "ollama"
    if provider == "openai":
        return OpenAIProvider(
            api_key=settings.OPENAI_API_KEY,
            model=settings.OPENAI_MODEL,
        )
    elif provider == "anthropic":
        return AnthropicProvider(
            api_key=settings.ANTHROPIC_API_KEY,
            model=settings.ANTHROPIC_MODEL,
        )
    elif provider == "ollama":
        return OllamaProvider(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_MODEL,
        )
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider!r}")
```

**Do not use a registry dict or plugin system.** A plain `if/elif` factory is explicit, grep-able, and fails loudly at startup on misconfiguration. A registry pattern adds indirection with no benefit at this scale.

The pipeline calls `get_provider()` once per task invocation. No singleton — provider objects are cheap to construct and this avoids stale config issues.

### Transcription provider abstraction (same pattern)

```python
# backend/app/core/extraction/transcription.py

from typing import Protocol

class TranscriptionBackend(Protocol):
    def transcribe(self, audio_path: str) -> str:
        ...

def get_transcription_backend() -> TranscriptionBackend:
    backend = settings.TRANSCRIPTION_BACKEND  # "faster_whisper" | "openai_whisper"
    if backend == "faster_whisper":
        return FasterWhisperBackend(model_size=settings.WHISPER_MODEL_SIZE)
    elif backend == "openai_whisper":
        return OpenAIWhisperBackend(api_key=settings.OPENAI_API_KEY)
    else:
        raise ValueError(f"Unknown TRANSCRIPTION_BACKEND: {backend!r}")
```

The old prototype has both `_transcribe_local_faster_whisper()` and `_transcribe_openai()` as module-level functions. Port them directly as separate `Backend` classes implementing the Protocol. Remove all `st.*` (Streamlit) calls — those were only for progress display, not logic.

---

## Directory Structure for New Files

```
backend/app/core/
├── extraction/
│   ├── __init__.py
│   ├── transcription.py         # TranscriptionBackend Protocol + get_transcription_backend() + FasterWhisperBackend + OpenAIWhisperBackend
│   ├── multimodal.py            # MultimodalFuser: combine transcript + OCR into FusionResult
│   └── ocr/
│       ├── __init__.py
│       └── text_extractor.py    # VideoTextExtractor (direct port from old repo, no Streamlit)
├── inference/
│   ├── __init__.py
│   ├── classifier.py            # LLMProvider Protocol + get_provider() factory
│   └── providers/
│       ├── __init__.py
│       ├── openai.py            # OpenAIProvider
│       ├── anthropic.py         # AnthropicProvider
│       └── ollama.py            # OllamaProvider
├── pipeline/
│   ├── __init__.py
│   └── pipeline.py              # run_pipeline(video_path, db_session) → ClassificationResult
├── schemas/
│   ├── __init__.py
│   └── pipeline.py              # FusionResult, ClassificationResult Pydantic models
├── storage/
│   └── __init__.py              # (stub, unchanged)
└── config.py                    # (existing, add new env vars)
```

New ORM model file:
```
backend/app/db/models/
└── result.py                    # Result model (FK → jobs.id)
```

---

## Pydantic Schemas

All inter-module data types live in `core/schemas/pipeline.py`. This ensures no circular imports and gives a single place to read the data contract.

```python
# backend/app/core/schemas/pipeline.py

from pydantic import BaseModel
from typing import Optional
from enum import Enum


class MisinfoLabel(str, Enum):
    MISINFO = "MISINFO"
    NO_MISINFO = "NO_MISINFO"
    DEBUNKING = "DEBUNKING"
    CANNOT_RECOGNIZE = "CANNOT_RECOGNIZE"


class FusionResult(BaseModel):
    transcript: str
    ocr_text: str
    unique_ocr_text: str
    combined_content: str
    source_video_path: str


class ClassificationResult(BaseModel):
    label: MisinfoLabel
    confidence: float                    # 0.0–1.0
    explanation: str
    evidence_snippets: list[str]
```

`FusionResult` is the output of multimodal fusion and the input to inference. `ClassificationResult` is what providers return and what gets persisted. The `MisinfoLabel` enum matches the canonical label schema exactly.

---

## Result DB Model

```python
# backend/app/db/models/result.py

import enum
import uuid
from datetime import datetime
from sqlalchemy import String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Result(Base):
    __tablename__ = "results"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(String, ForeignKey("jobs.id"), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_snippets: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-encoded list[str]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

**Key decisions:**
- `unique=True` on `job_id` — one result per job, enforced at DB level. A re-run should create a new job.
- `evidence_snippets` stored as `Text` (JSON-encoded list) rather than a JSONB column. Reason: the project uses `psycopg3` with SQLAlchemy sync ORM, and JSONB adds complexity for what is a simple read/write field. JSON string is fine for v1; migrate to JSONB if search/indexing is needed later.
- No relationship declared on `Job` model pointing back to `Result` — add that only when the API needs it. For now, the worker looks up the result by `job_id` and the API router queries `Result` by `job_id` when returning job details.

Register the model in `main.py` with a noqa import:
```python
import app.db.models.result  # noqa: F401
```

---

## Pipeline Orchestrator

```python
# backend/app/core/pipeline/pipeline.py

import logging
from app.core.extraction.transcription import get_transcription_backend
from app.core.extraction.ocr.text_extractor import VideoTextExtractor
from app.core.extraction.multimodal import MultimodalFuser
from app.core.inference.classifier import get_provider
from app.core.schemas.pipeline import ClassificationResult

logger = logging.getLogger(__name__)


def run_pipeline(video_path: str) -> ClassificationResult:
    logger.info("Pipeline start: %s", video_path)

    # Step 1: Transcription
    transcription_backend = get_transcription_backend()
    transcript = transcription_backend.transcribe(video_path)
    logger.info("Transcription complete: %d chars", len(transcript))

    # Step 2: OCR
    ocr_extractor = VideoTextExtractor()
    ocr_result = ocr_extractor.extract_text_from_video(video_path)
    logger.info("OCR complete: %d detections", len(ocr_result))

    # Step 3: Fusion
    fuser = MultimodalFuser()
    fusion = fuser.fuse(transcript=transcript, ocr_result=ocr_result, video_path=video_path)
    logger.info("Fusion complete")

    # Step 4: Inference
    provider = get_provider()
    result = provider.classify(fusion)
    logger.info("Inference complete: label=%s confidence=%.2f", result.label, result.confidence)

    return result
```

`run_pipeline()` takes only `video_path` and returns a `ClassificationResult`. No DB session parameter — the pipeline is pure domain logic. DB writes happen in the task layer, not here. This keeps the pipeline testable in isolation (no DB required for unit tests of the pipeline).

---

## process_video_task Wiring

The worker task becomes:

```python
# backend/app/worker/tasks.py

import json
import logging
from app.worker.celery_app import celery_app
from app.db.session import SessionLocal
from app.db.models.job import Job, JobStatus
from app.db.models.video import Video
from app.db.models.result import Result
from app.core.pipeline.pipeline import run_pipeline

logger = logging.getLogger(__name__)


@celery_app.task(name="process_video_task", bind=True)
def process_video_task(self, job_id: str) -> None:
    db = SessionLocal()
    try:
        # 1. Fetch job and mark STARTED
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        job.status = JobStatus.STARTED
        db.commit()

        # 2. Fetch associated video file path
        video = db.query(Video).filter(Video.id == job.video_id).first()
        if not video:
            raise ValueError(f"Video not found for job: {job_id}")

        # 3. Run pipeline (pure domain layer — no DB)
        classification = run_pipeline(video_path=video.file_path)

        # 4. Persist result
        result = Result(
            job_id=job_id,
            label=classification.label.value,
            confidence=classification.confidence,
            explanation=classification.explanation,
            evidence_snippets=json.dumps(classification.evidence_snippets),
        )
        db.add(result)

        # 5. Mark SUCCESS
        job.status = JobStatus.SUCCESS
        db.commit()

    except Exception as exc:
        logger.exception("process_video_task failed for job_id=%s", job_id)
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.status = JobStatus.FAILED
                db.commit()
        except Exception:
            pass
        raise exc
    finally:
        db.close()
```

**Key patterns:**
- DB session created at task start, closed in `finally` — same as existing stub, extended.
- `run_pipeline()` called between STARTED and result persistence — no DB passed in.
- Result written before marking SUCCESS — if result write fails, job stays STARTED temporarily then fails. This is intentional: no SUCCESS without a persisted result.
- `raise exc` after marking FAILED — Celery sees the task as failed in the result backend, allowing retry policies to work if added later.

---

## GET /jobs/{job_id} Result Extension

When job is SUCCESS, the jobs router should join the result:

```python
# In backend/app/api/routers/jobs.py — extend the GET handler

from app.db.models.result import Result
import json

# In the route handler, after fetching job:
result = db.query(Result).filter(Result.job_id == job_id).first()
result_data = None
if result:
    result_data = {
        "label": result.label,
        "confidence": result.confidence,
        "explanation": result.explanation,
        "evidence_snippets": json.loads(result.evidence_snippets),
    }

return {
    "job_id": job.id,
    "video_id": job.video_id,
    "status": job.status,
    "celery_task_id": job.celery_task_id,
    "created_at": job.created_at,
    "updated_at": job.updated_at,
    "result": result_data,  # None if not yet complete
}
```

---

## Build Order (Dependency Graph)

This is the safe implementation sequence — each item can be built and tested before the next depends on it.

```
1. core/schemas/pipeline.py
   (FusionResult, ClassificationResult, MisinfoLabel)
   No dependencies. Define data contracts first.

2. db/models/result.py
   Depends on: db/base.py (exists)
   Register in main.py imports.

3. core/extraction/ocr/text_extractor.py
   Depends on: schemas/pipeline.py (indirectly via ocr_result shape)
   Port VideoTextExtractor, remove all Streamlit imports.
   Test in isolation with a sample video frame.

4. core/extraction/transcription.py
   Depends on: schemas/pipeline.py (none for transcript — plain str return)
   Port FasterWhisperBackend and OpenAIWhisperBackend.
   Remove Streamlit progress callbacks.
   Test with a short audio file.

5. core/extraction/multimodal.py
   Depends on: transcription.py, ocr/text_extractor.py, schemas/pipeline.py
   Port MultimodalExtractor → MultimodalFuser.
   Unit-testable with mocked extractor outputs.

6. core/inference/providers/openai.py
   Depends on: schemas/pipeline.py (ClassificationResult, FusionResult)
   Port _extract_json_block() and prompt construction from analysis.py.
   Test with a mocked OpenAI client.

7. core/inference/providers/ollama.py
   Depends on: schemas/pipeline.py
   Port analyze_local_mistral() logic.

8. core/inference/providers/anthropic.py
   Depends on: schemas/pipeline.py
   New provider — not in old repo, add via Anthropic SDK.

9. core/inference/classifier.py
   Depends on: all providers, schemas/pipeline.py
   Define LLMProvider Protocol, get_provider() factory.

10. core/pipeline/pipeline.py
    Depends on: transcription.py, ocr/text_extractor.py, multimodal.py, classifier.py
    run_pipeline() integration. Integration-testable at this point.

11. worker/tasks.py (extend existing stub)
    Depends on: pipeline.py, db/models/result.py
    Wire run_pipeline() call, persist Result, update Job status.

12. api/routers/jobs.py (extend existing)
    Depends on: db/models/result.py
    Add result fields to GET /jobs/{job_id} response.
```

**Critical constraint on step 3 (OCR):** EasyOCR initializes a model on first call (`_get_reader()`). In the old repo this is a one-time Streamlit session-state cache. In the worker, this initialization happens per-task invocation unless the `VideoTextExtractor` instance is reused. For v1, re-initializing per task is acceptable (adds ~2–4 seconds startup cost). If latency becomes an issue, use a Celery `initializer` to warm the model at worker startup via `celery_app.conf.worker_init_callback` or store the reader at module level in `text_extractor.py` (module-level singletons are safe in Celery since each worker process has its own Python interpreter).

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: DB session passed into pipeline modules
**What:** Passing `db: Session` as a parameter to `run_pipeline()` or to individual extractors.
**Why bad:** Makes pipeline code non-testable without a real DB; blurs the layer boundary between domain logic and persistence.
**Instead:** DB writes happen only in `tasks.py` — before the pipeline call (STARTED) and after it returns (persist result + SUCCESS/FAILED).

### Anti-Pattern 2: Importing from old prototype directly
**What:** `from pages.processes.transcription import transcribe` inside any backend module.
**Why bad:** Creates a hard dependency on a different repo/path that won't exist inside the Docker container. Will fail at runtime silently or loudly.
**Instead:** Port the logic — copy and modify, remove Streamlit, use the new Protocol interface.

### Anti-Pattern 3: Singleton LLM provider at module level
**What:** `_provider = OpenAIProvider(...)` at the top of `classifier.py`, shared across all tasks.
**Why bad:** Celery workers run multiple tasks concurrently. A shared provider instance with mutable state (e.g., conversation history) causes cross-task contamination. HTTP clients (openai SDK) may also have connection pool issues.
**Instead:** Call `get_provider()` once per task invocation. Provider objects are stateless (no history), so construction is cheap.

### Anti-Pattern 4: Swallowing exceptions in pipeline stages
**What:** `try: transcript = backend.transcribe(path) except: transcript = ""`
**Why bad:** Silent failures produce `CANNOT_RECOGNIZE` results that look valid. Errors become invisible.
**Instead:** Let exceptions propagate out of `run_pipeline()`. The task-level `try/except` marks the job `FAILED`. Logs contain the actual error. Downstream: add per-stage error context with `raise RuntimeError("Transcription failed") from exc` for clearer tracebacks.

### Anti-Pattern 5: Provider-specific logic in pipeline.py
**What:** `if settings.LLM_PROVIDER == "openai": ... elif ...` inside `pipeline.py`.
**Why bad:** Defeats the entire purpose of the Protocol abstraction. Adding a new provider requires modifying pipeline.py.
**Instead:** `pipeline.py` only calls `provider.classify(fusion)`. Provider selection is encapsulated in `get_provider()` in `classifier.py`.

---

## Scalability Considerations

| Concern | At current scale (single worker) | At 10 workers | At 100 workers |
|---------|-----------------------------------|---------------|----------------|
| EasyOCR model init | Module-level singleton per process — fine | Each worker process loads its own model — ~4GB RAM total | Memory-prohibitive; need shared inference service or lighter model |
| faster-whisper model | Same as EasyOCR — per-process singleton | 10 copies in RAM | Need GPU inference service (Triton or similar) |
| LLM API rate limits | No concern | Concurrent tasks can hit rate limits | Need rate-limit-aware retry with exponential backoff (tenacity library) |
| DB connections | SessionLocal per task, closed in finally — fine | pgBouncer or connection pool tuning | Connection pool exhaustion; use PgBouncer in front of Postgres |
| Storage volume | Local Docker volume — fine | Must be shared NFS or S3 | S3 only; local volumes don't scale horizontally |

For v1 (single worker, 1–10 concurrent users), none of these are blockers. The architecture is designed so all the future-state changes (S3 storage, GPU inference) are isolated to specific modules (`core/storage/`, provider classes) without touching the pipeline or worker layers.

---

## Settings Extensions Required

Add to `backend/app/core/config.py` (pydantic-settings `Settings` class):

```python
# Transcription
TRANSCRIPTION_BACKEND: str = "faster_whisper"   # "faster_whisper" | "openai_whisper"
WHISPER_MODEL_SIZE: str = "base"                  # "tiny" | "base" | "small" | "medium" | "large-v2"

# Inference
LLM_PROVIDER: str = "openai"                      # "openai" | "anthropic" | "ollama"
OPENAI_API_KEY: str = ""
OPENAI_MODEL: str = "gpt-4o"
ANTHROPIC_API_KEY: str = ""
ANTHROPIC_MODEL: str = "claude-opus-4-6"
OLLAMA_BASE_URL: str = "http://localhost:11434"
OLLAMA_MODEL: str = "mistral"
```

All of these should also appear in `.env.example` with placeholder values.

---

## Sources

**Confidence assessment:**

| Area | Confidence | Basis |
|------|------------|-------|
| Protocol vs ABC for provider abstraction | HIGH | Stable Python 3.8+ pattern; well-documented in typing module; used by major SDKs |
| Factory function vs registry | HIGH | Established production Python pattern; confirmed in multiple FastAPI production guides |
| Celery task DB session management | HIGH | Directly reflected in the existing tasks.py stub pattern already in the codebase |
| Result model schema | HIGH | Derived directly from PROJECT.md requirements (label, confidence, explanation, evidence_snippets) |
| OCR model initialization in Celery | MEDIUM | Celery worker process model is well-known; module-level singleton behavior confirmed by Python import semantics |
| Build order / dependency graph | HIGH | Derived from actual import dependencies between modules — no circular dependencies in this order |
| evidence_snippets as JSON Text vs JSONB | MEDIUM | Pragmatic for v1; JSONB is Postgres-specific and adds complexity; can be migrated later |

*Note: WebSearch and external documentation could not be queried in this research session (tool access restricted). All findings based on context files and training-data knowledge of stable Python production patterns. Flag for validation: Anthropic SDK model ID (`claude-opus-4-6`) — confirm latest model string before hardcoding.*
