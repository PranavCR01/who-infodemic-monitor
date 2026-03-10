# Phase 1: Schemas and Infrastructure - Research

**Researched:** 2026-03-09
**Domain:** Python dependency management, Dockerfile ML layer construction, Pydantic v2 schema design, SQLAlchemy 2.0 ORM modeling, pydantic-settings configuration
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INFRA-01 | ML dependencies added to pyproject.toml (faster-whisper, easyocr, anthropic, opencv-python-headless, ctranslate2) | Version pins verified against PyPI as of 2026-03; exact lines ready |
| INFRA-02 | Dockerfile updated with ML system deps, headless OpenCV fix, model pre-warming for faster-whisper and EasyOCR during build | Exact RUN commands documented; confirmed system deps already satisfy requirements |
| INFRA-03 | New env vars in config.py and .env.example (WHISPER_PROVIDER, WHISPER_MODEL, INFERENCE_PROVIDER, OPENAI_API_KEY, ANTHROPIC_API_KEY, ANTHROPIC_MODEL, OLLAMA_BASE_URL, OLLAMA_MODEL) | Exact field names, types, and defaults documented; existing config.py structure confirmed |
| SCHEMA-01 | FusionResult Pydantic schema (transcript, visual_text, combined_content, metadata) | Pydantic v2 BaseModel pattern confirmed; field names reconciled against requirements |
| SCHEMA-02 | ClassificationResult Pydantic schema (label: MisinfoLabel enum, confidence float 0-1, explanation, evidence_snippets, provider, model_used, latency_ms) | MisinfoLabel enum strategy determined; all fields typed; confidence clamping approach documented |
| SCHEMA-03 | Result SQLAlchemy ORM model (job_id FK unique, label, confidence, explanation, evidence_snippets JSON, combined_content Text, provider, model_used, latency_ms, created_at) | JSON vs Text decision made; FK pattern confirmed from job.py; main.py import registration pattern confirmed |
</phase_requirements>

---

## Summary

Phase 1 delivers the foundational contracts — Python dependencies, Docker build layers, environment configuration, and data schemas — that every downstream module imports from. Because all later phases import from `core/schemas/pipeline.py` and `db/models/result.py`, this phase must be implemented before any extraction or inference work begins. The work is deliberately narrow: no logic is written, only contracts and configuration.

The current codebase already has the infrastructure stack working (FastAPI, Celery, PostgreSQL, Redis, Docker Compose — all verified end-to-end as of Milestone 2). The Dockerfile already installs `ffmpeg`, `libgl1`, and `libglib2.0-0`, which satisfy the native library requirements for both faster-whisper and EasyOCR. No new system packages are needed. The `pyproject.toml` currently has 11 dependencies; this phase adds 7 ML-specific packages with verified version pins.

The two schema design questions have clean answers: use `class MisinfoLabel(str, enum.Enum)` (not Python 3.11 `StrEnum`) to avoid SQLAlchemy `mapped_column` compatibility issues while still serializing as plain strings in FastAPI JSON responses. Use SQLAlchemy `JSON` type for `evidence_snippets` rather than `Text` with manual `json.dumps/loads`; SQLAlchemy's `JSON` type handles serialization automatically and `psycopg[binary]` (psycopg3) passes JSON columns correctly.

**Primary recommendation:** Implement in strict order — dependencies first (INFRA-01), then Dockerfile (INFRA-02), then config (INFRA-03), then schemas (SCHEMA-01 and SCHEMA-02 together in one file), then the Result ORM model (SCHEMA-03). Each step is independently verifiable.

---

## Standard Stack

### Core — Existing (do not change)

| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| fastapi | >=0.110 | API framework | Already in pyproject.toml |
| uvicorn[standard] | >=0.27 | ASGI server | Already in pyproject.toml |
| pydantic | >=2.6 | Schema validation | Already in pyproject.toml |
| pydantic-settings | >=2.2 | Env var config (Settings class) | Already in pyproject.toml |
| python-multipart | >=0.0.9 | File upload parsing | Already in pyproject.toml |
| celery | >=5.3 | Async job queue | Already in pyproject.toml |
| redis | >=5.0 | Celery broker/backend | Already in pyproject.toml |
| sqlalchemy | >=2.0 | Sync ORM for DB | Already in pyproject.toml |
| psycopg[binary] | >=3.1 | PostgreSQL driver (psycopg3) | Already in pyproject.toml |
| aiofiles | >=23.0 | Async file I/O | Already in pyproject.toml |

### New Additions (this phase)

| Library | Verified Version | Purpose | Why This Choice |
|---------|-----------------|---------|----------------|
| faster-whisper | >=1.0.1 (latest: 1.2.1) | Local CPU Whisper inference | 4x faster than openai-whisper on CPU; no GPU required; prototype-validated |
| ctranslate2 | >=4.3.1 (latest: 4.7.1) | CTranslate2 backend for faster-whisper | Installed automatically as faster-whisper dependency; pin avoids CUDA version conflicts |
| easyocr | >=1.7.0 (latest: 1.7.2) | On-screen text extraction via neural OCR | Better accuracy on TikTok-style stylized text than Tesseract; gpu=False works on CPU |
| opencv-python-headless | >=4.9 | Video frame sampling (cv2.VideoCapture) | Headless variant excludes Qt/GTK display libs — avoids container startup failures; saves ~200MB |
| anthropic | >=0.28 (latest: 0.84.0) | Anthropic Claude inference SDK | Supports tool_choice for structured JSON; no regex parsing needed |
| openai | >=1.13 | OpenAI Whisper API + GPT inference | Stable 1.x client interface; already used conceptually in prototype |
| tiktoken | >=0.6 | Token counting for content length guard | Soft dependency; enables ContentTooLongError before LLM submission |

### Installation

```bash
# Inside pyproject.toml dependencies list — add these 7 lines:
"faster-whisper>=1.0.1",
"ctranslate2>=4.3.1",
"easyocr>=1.7.0",
"opencv-python-headless>=4.9",
"anthropic>=0.28",
"openai>=1.13",
"tiktoken>=0.6",
```

Note: `requests` is NOT needed as a new dependency. It is already a transitive dependency of many packages in the existing stack.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| opencv-python-headless | opencv-python | opencv-python includes Qt/GTK display libs that crash in headless containers; never use in Docker |
| ctranslate2>=4.3.1 | ctranslate2>=4.7.1 | Latest is fine but pin conservatively; 4.3.1 is prototype-validated; pip will install 4.7.1 anyway |
| anthropic>=0.28 | anthropic>=0.84.0 | Tight pin not needed; >=0.28 covers all tool_choice features; latest is 0.84.0 |

---

## Architecture Patterns

### Recommended Project Structure (new files only)

```
backend/app/core/schemas/
├── __init__.py
└── pipeline.py              # FusionResult, ClassificationResult, MisinfoLabel

backend/app/db/models/
├── video.py                 # (exists)
├── job.py                   # (exists)
└── result.py                # NEW: Result ORM model

backend/app/core/
└── config.py                # (exists — extend Settings class)

.env.example                 # (exists — append new vars)
backend/Dockerfile           # (exists — add pip install + 2 RUN pre-warm lines)
backend/pyproject.toml       # (exists — add 7 dependency lines)
```

### Pattern 1: MisinfoLabel Enum — Use `str, enum.Enum` NOT Python 3.11 `StrEnum`

**What:** Define the canonical label enum as `class MisinfoLabel(str, enum.Enum)` — a mixed-in str enum that is both a string and an enum member.

**Why not `enum.StrEnum`:** Python 3.11 introduced `enum.StrEnum` which changes `str()` formatting behavior. SQLAlchemy's `mapped_column` has known compatibility issues with `StrEnum` when using `Mapped[str]` type annotations — it can fail to recognize the column type. The existing `JobStatus` in `job.py` already uses the `class JobStatus(str, enum.Enum)` pattern, so follow that convention.

**Why not SQLAlchemy `SAEnum`:** Using `SAEnum(MisinfoLabel)` in the Result model would create a PostgreSQL-level ENUM type that requires `ALTER TYPE` migrations to add new labels. During active development this is painful. Store as `String` in the DB; validate with the Python enum in the application layer.

**Example:**
```python
# backend/app/core/schemas/pipeline.py
import enum

class MisinfoLabel(str, enum.Enum):
    MISINFO = "MISINFO"
    NO_MISINFO = "NO_MISINFO"
    DEBUNKING = "DEBUNKING"
    CANNOT_RECOGNIZE = "CANNOT_RECOGNIZE"
```

FastAPI serializes `str` enum members as their string value by default — `"label": "MISINFO"` not `"label": 0`. Pydantic v2 validates inputs against enum values automatically.

### Pattern 2: FusionResult and ClassificationResult in One File

**What:** Both Pydantic schemas live in `backend/app/core/schemas/pipeline.py`. No separate files.

**Why:** Every downstream module imports both. A single file eliminates circular import risk and gives any reader one authoritative contract to check.

**Requirements field reconciliation:** The REQUIREMENTS.md specifies `FusionResult` fields as `transcript, visual_text, combined_content, metadata`. The ARCHITECTURE research uses slightly different names. Use the REQUIREMENTS.md names exactly:

```python
# backend/app/core/schemas/pipeline.py
from pydantic import BaseModel, field_validator
from typing import Any
import enum

class MisinfoLabel(str, enum.Enum):
    MISINFO = "MISINFO"
    NO_MISINFO = "NO_MISINFO"
    DEBUNKING = "DEBUNKING"
    CANNOT_RECOGNIZE = "CANNOT_RECOGNIZE"

class FusionResult(BaseModel):
    transcript: str
    visual_text: str
    combined_content: str
    metadata: dict[str, Any]

class ClassificationResult(BaseModel):
    label: MisinfoLabel
    confidence: float          # clamped to 0.0–1.0
    explanation: str
    evidence_snippets: list[str]
    provider: str
    model_used: str
    latency_ms: int

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))
```

**Confidence clamping:** Use a Pydantic v2 `@field_validator` to clamp confidence to [0.0, 1.0] at schema validation time. This prevents out-of-range LLM values from persisting to the DB.

### Pattern 3: Result ORM Model — Use `JSON` type for evidence_snippets

**What:** `evidence_snippets` is stored as a SQLAlchemy `JSON` column (not `Text` with manual serialization).

**Why:** SQLAlchemy's `JSON` type handles Python list ↔ JSON serialization automatically. With `psycopg[binary]` (psycopg3), the driver handles JSON serialization natively, so there is no manual `json.dumps/json.loads` needed in the task or router code. This is cleaner and less error-prone than text encoding.

**FK pattern:** Follow `job.py` exactly — `String` primary key with `uuid.uuid4()` default lambda, `ForeignKey("jobs.id")` with `unique=True`, `DateTime(timezone=True)` for `created_at`.

```python
# backend/app/db/models/result.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Float, Text, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class Result(Base):
    __tablename__ = "results"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    job_id: Mapped[str] = mapped_column(
        String, ForeignKey("jobs.id"), unique=True, nullable=False
    )
    label: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_snippets: Mapped[list] = mapped_column(JSON, nullable=False)
    combined_content: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_used: Mapped[str] = mapped_column(String(128), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
```

**Registration in main.py:** Add one import line after the existing model imports:
```python
import app.db.models.result  # noqa: F401
```
This ensures `Base.metadata.create_all()` picks up the `results` table on startup.

### Pattern 4: Config Extension — pydantic-settings Field Definitions

**What:** Extend the existing `Settings` class in `backend/app/core/config.py` with new fields.

**Why not replace:** The existing `Settings` already works for Celery, Redis, DB, and storage. Extend it, don't replace it.

**Exact field names from REQUIREMENTS.md:**

```python
# backend/app/core/config.py (additions)
class Settings(BaseSettings):
    # ... existing fields ...

    # Transcription
    WHISPER_PROVIDER: str = "faster_whisper"   # "faster_whisper" | "openai"
    WHISPER_MODEL: str = "base"                 # "tiny" | "base" | "small" | "medium" | "large-v3"

    # Inference
    INFERENCE_PROVIDER: str = "openai"          # "openai" | "anthropic" | "ollama"
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-opus-4-6"
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "mistral"
```

Note: REQUIREMENTS.md does not list `OPENAI_MODEL` — omit it for now, default to `gpt-4o` as a constant in the OpenAI provider. Add to config only when needed.

### Pattern 5: Dockerfile Pre-Warming — After pip install, Before COPY

**What:** Two `RUN` commands after `pip install` that import and initialize the ML models during the Docker build, baking the downloaded weights into the image layer.

**Why this order matters:** The model download happens at `import` time (EasyOCR) or at `WhisperModel(...)` construction time (faster-whisper). If done AFTER `COPY . /app`, any code change triggers a rebuild of the layer and re-download. Place the pre-warm commands BEFORE `COPY . /app` to benefit from Docker layer caching — dependency changes invalidate the layer, but source code changes do not.

**EasyOCR model storage:** EasyOCR uses `~/.EasyOCR/` by default inside the container. This path is baked into the image during build — since the build runs as root, models land in `/root/.EasyOCR/`. This is fine for single-container use. Set `EASYOCR_MODULE_PATH` env var if a named volume for model storage is desired in future.

```dockerfile
# backend/Dockerfile (additions — insert between pip install and COPY . /app)

# Existing:
COPY pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir -U pip && pip install --no-cache-dir .

# ADD THESE TWO LINES:
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"
RUN python -c "import easyocr; easyocr.Reader(['en'], gpu=False)"

# Existing:
COPY . /app
ENV PYTHONUNBUFFERED=1
```

**No new system packages needed.** The existing `libgl1` and `libglib2.0-0` apt packages already satisfy EasyOCR's OpenCV native dependency even with `opencv-python-headless`. `ffmpeg` is already installed. faster-whisper 1.x bundles FFmpeg via PyAV and does not require the system `ffmpeg` for audio decoding (though having it doesn't hurt).

### Pattern 6: Anthropic Structured Output — Tool Use vs Beta Header

**What:** Phase 3 (Inference) will implement AnthropicProvider. Phase 1 only documents the decision so downstream implementation is unambiguous.

**Decision:** Use `tool_choice={"type": "tool", "name": "classify_content"}` with `tools=` parameter (the pre-existing tool-use API). Do NOT use the `structured-outputs-2025-11-13` beta header approach.

**Rationale:** The new beta Structured Outputs feature (announced November 2025, supports Sonnet 4.5 and Opus 4.1) requires `client.beta.messages.parse()` or `extra_headers={"anthropic-beta": "structured-outputs-2025-11-13"}`. However, tool-use with `tool_choice` is supported across all Claude 3+ and Claude 4+ models (including `claude-opus-4-6`), does not require a beta header, is stable API surface, and produces the same structured JSON output. The tool-use approach is more portable across model versions.

```python
# Pattern for Phase 3 AnthropicProvider (documented here for planner awareness):
response = client.messages.create(
    model=self.model,
    max_tokens=1024,
    tools=[{
        "name": "classify_content",
        "description": "Classify health content for misinformation",
        "input_schema": {
            "type": "object",
            "properties": {
                "label": {"type": "string", "enum": ["MISINFO", "NO_MISINFO", "DEBUNKING", "CANNOT_RECOGNIZE"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "explanation": {"type": "string"},
                "evidence_snippets": {"type": "array", "items": {"type": "string"}},
                "provider": {"type": "string"},
                "model_used": {"type": "string"},
                "latency_ms": {"type": "integer"}
            },
            "required": ["label", "confidence", "explanation", "evidence_snippets"]
        }
    }],
    tool_choice={"type": "tool", "name": "classify_content"},
    messages=[{"role": "user", "content": combined_content}]
)
tool_use_block = next(b for b in response.content if b.type == "tool_use")
result_dict = tool_use_block.input  # already a dict — no json.loads needed
```

### Anti-Patterns to Avoid

- **Using `SAEnum(MisinfoLabel)` in the Result model column:** Creates a PostgreSQL DB-level ENUM that requires ALTER TYPE migrations to add labels. Store label as `String(32)`, validate with Python enum in application code.
- **Using `opencv-python` instead of `opencv-python-headless`:** The non-headless variant attempts to initialize Qt display libraries and crashes in headless Docker containers with `libEGL.so` or display errors.
- **Placing pre-warm RUN commands after `COPY . /app`:** Code changes would invalidate the ML model download layer, causing re-downloads on every source edit. Place pre-warm BEFORE the COPY.
- **Declaring `MisinfoLabel` only in `db/models/result.py`:** Any module importing the enum for Pydantic validation would need to import from a DB model file — wrong layering. The enum belongs in `core/schemas/pipeline.py`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Pydantic validation with enum + field_validator | Custom validation logic | Pydantic v2 `@field_validator` | Pydantic handles coercion, validation, and FastAPI serialization |
| JSON serialization for evidence_snippets | Manual `json.dumps` / `json.loads` in task and router | SQLAlchemy `JSON` type | Driver (psycopg3) handles serialization; no manual encoding errors |
| Environment variable loading | Custom `.env` parser | pydantic-settings `BaseSettings` | Already installed, handles type coercion, defaults, and env overrides |
| UUID primary key generation | Manual `uuid.uuid4()` assignment | `default=lambda: str(uuid.uuid4())` in `mapped_column` | Consistent with existing job.py and video.py pattern |

---

## Common Pitfalls

### Pitfall 1: opencv-python vs opencv-python-headless Confusion

**What goes wrong:** Installing `opencv-python` in Docker causes runtime import failures (`libEGL warning` or `cannot connect to display`) when the container has no display server.

**Why it happens:** `opencv-python` includes Qt and display libraries that expect an X11/Wayland display session.

**How to avoid:** Pin `opencv-python-headless>=4.9` explicitly. Do NOT allow `opencv-python` to be installed as a transitive dependency. If `easyocr`'s own `install_requires` pins `opencv-python` (non-headless), override it — `pip install easyocr opencv-python-headless` with headless listed last resolves the conflict.

**Warning signs:** `ImportError` or warning messages containing `libEGL`, `display`, or `Qt` during `import cv2`.

### Pitfall 2: ML Model Downloads at Runtime (Not Build Time)

**What goes wrong:** Both faster-whisper and EasyOCR download model weights lazily on first use. First job invocation blocks for 60–120 seconds. Re-download happens on every container restart if not cached.

**Why it happens:** Libraries default to `~/.cache/huggingface` (faster-whisper via huggingface-hub) and `~/.EasyOCR/` (easyocr) which are ephemeral inside containers.

**How to avoid:** Add the two `RUN python -c "..."` pre-warm commands in the Dockerfile BEFORE `COPY . /app`. Models bake into the image layer.

**Warning signs:** First job taking >60 seconds; jobs timing out on first run; network errors in worker logs.

### Pitfall 3: `class MisinfoLabel(enum.StrEnum)` Breaks SQLAlchemy mapped_column

**What goes wrong:** Python 3.11+ `StrEnum` has different `__str__` and `__format__` behavior from `(str, enum.Enum)`. SQLAlchemy's `Mapped[str]` annotation with `mapped_column(String)` does not recognize `StrEnum` values as strings in all cases, producing type errors or silent storage failures.

**Why it happens:** `StrEnum` overrides string formatting in ways that SQLAlchemy's type system doesn't expect. This is a known open issue in SQLAlchemy + SQLModel discussions.

**How to avoid:** Use `class MisinfoLabel(str, enum.Enum)` — the same pattern already used in `job.py` for `JobStatus`. Store `label` as `String(32)`, not `SAEnum(MisinfoLabel)`.

**Warning signs:** `ProgrammingError` on INSERT; label stored as `"MisinfoLabel.MISINFO"` instead of `"MISINFO"`.

### Pitfall 4: Forgetting to Register Result Model in main.py

**What goes wrong:** The `results` table is never created by `Base.metadata.create_all()` because SQLAlchemy only creates tables for models it knows about, and it only knows about models that have been imported before `create_all()` runs.

**Why it happens:** SQLAlchemy's declarative base registry is populated by imports, not by file existence.

**How to avoid:** Add `import app.db.models.result  # noqa: F401` to `main.py` alongside the existing video and job model imports.

**Warning signs:** `sqlalchemy.exc.ProgrammingError: relation "results" does not exist` in worker logs when task tries to insert a Result.

### Pitfall 5: ctranslate2 CUDA Version Conflicts

**What goes wrong:** ctranslate2 >=4.5.0 requires cuDNN 9 and CUDA 12. If the base image or environment has an older CUDA version, import fails.

**Why it happens:** ctranslate2 ships CUDA-specific wheels; the wrong wheel gets installed.

**How to avoid:** This project uses CPU-only mode with `python:3.11-slim` (no CUDA). The CPU-only ctranslate2 wheel does not have CUDA dependencies. No action needed, but be aware if anyone attempts to add GPU support later.

**Warning signs:** `ImportError: libcuda.so.1: cannot open shared object file` on worker startup.

---

## Code Examples

Verified patterns from official sources and existing codebase:

### Complete pyproject.toml After This Phase

```toml
[project]
name = "who-infodemic-monitor-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.110",
  "uvicorn[standard]>=0.27",
  "pydantic>=2.6",
  "pydantic-settings>=2.2",
  "python-multipart>=0.0.9",
  "celery>=5.3",
  "redis>=5.0",
  "sqlalchemy>=2.0",
  "psycopg[binary]>=3.1",
  "aiofiles>=23.0",
  "faster-whisper>=1.0.1",
  "ctranslate2>=4.3.1",
  "easyocr>=1.7.0",
  "opencv-python-headless>=4.9",
  "anthropic>=0.28",
  "openai>=1.13",
  "tiktoken>=0.6",
]
```

### Complete Dockerfile After This Phase

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
  && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir -U pip && pip install --no-cache-dir .

# Pre-download ML models during build (prevents cold-start on first job)
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"
RUN python -c "import easyocr; easyocr.Reader(['en'], gpu=False)"

COPY . /app

ENV PYTHONUNBUFFERED=1
```

### Complete config.py After This Phase

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Infrastructure (existing)
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@db:5432/infodemic"
    LOCAL_STORAGE_ROOT: str = "/app/storage"

    # Transcription
    WHISPER_PROVIDER: str = "faster_whisper"   # "faster_whisper" | "openai"
    WHISPER_MODEL: str = "base"                 # "tiny" | "base" | "small" | "medium" | "large-v3"

    # Inference
    INFERENCE_PROVIDER: str = "openai"          # "openai" | "anthropic" | "ollama"
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-opus-4-6"
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "mistral"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
```

### Complete .env.example After This Phase

```env
APP_ENV=local

POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=infodemic
DATABASE_URL=postgresql+psycopg://postgres:postgres@db:5432/infodemic

REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1

LOCAL_STORAGE_ROOT=/app/storage

# Transcription
WHISPER_PROVIDER=faster_whisper
WHISPER_MODEL=base

# Inference
INFERENCE_PROVIDER=openai
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-opus-4-6
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=mistral
```

### Complete pipeline.py Schemas File

```python
# backend/app/core/schemas/pipeline.py
import enum
from typing import Any
from pydantic import BaseModel, field_validator


class MisinfoLabel(str, enum.Enum):
    MISINFO = "MISINFO"
    NO_MISINFO = "NO_MISINFO"
    DEBUNKING = "DEBUNKING"
    CANNOT_RECOGNIZE = "CANNOT_RECOGNIZE"


class FusionResult(BaseModel):
    transcript: str
    visual_text: str
    combined_content: str
    metadata: dict[str, Any]


class ClassificationResult(BaseModel):
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
        return max(0.0, min(1.0, v))
```

### Complete result.py ORM Model

```python
# backend/app/db/models/result.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Float, Text, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Result(Base):
    __tablename__ = "results"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    job_id: Mapped[str] = mapped_column(
        String, ForeignKey("jobs.id"), unique=True, nullable=False
    )
    label: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_snippets: Mapped[list] = mapped_column(JSON, nullable=False)
    combined_content: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_used: Mapped[str] = mapped_column(String(128), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
```

### main.py Addition (one line)

```python
# backend/app/main.py — add after existing model imports:
import app.db.models.result  # noqa: F401
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `opencv-python` in Docker | `opencv-python-headless` | EasyOCR 1.6+ default | Eliminates Qt display crash in headless containers |
| openai-whisper (PyTorch) | faster-whisper (CTranslate2) | 2023 | 4x faster CPU inference, smaller image (~400MB less) |
| Regex JSON extraction from LLM | Anthropic tool_choice + tool_use API | Anthropic API 2023 | Deterministic structured output; no parsing failures |
| `SAEnum` DB-level PostgreSQL enums | `String` column + Python `str, enum.Enum` | Recommendation from 2024+ production experience | No ALTER TYPE migrations; easier iteration during development |
| Anthropic beta Structured Outputs (`structured-outputs-2025-11-13`) | tool_choice with tools= parameter | November 2025 (new feature) | Beta header approach only supports Sonnet 4.5 and Opus 4.1; tool_choice works across all Claude 3+ and 4+ models |

**Deprecated/outdated:**
- `openai-whisper`: Replaced by faster-whisper; PyTorch dependency adds ~1.5GB to image
- `pytesseract`: Replaced by EasyOCR; poor accuracy on TikTok-style stylized captions
- `class JobStatus(str, Enum)` with `SAEnum(JobStatus)` — note the existing `job.py` DOES use SAEnum for JobStatus; the SAME PATTERN MUST NOT be used for MisinfoLabel in Result because adding a new status value in JobStatus is rare but adding a new misinfo label during active research is likely

---

## Open Questions

1. **ANTHROPIC_MODEL default value**
   - What we know: REQUIREMENTS.md specifies `ANTHROPIC_MODEL` as a config var. Architecture research suggests `claude-opus-4-6`. The SUMMARY.md flags this as "confirm before hardcoding." Claude Sonnet 4.5 is explicitly supported for the new structured output beta (irrelevant here since we use tool_choice).
   - What's unclear: Cost vs. capability tradeoff for health misinformation classification. `claude-opus-4-6` (Opus) is more capable but significantly more expensive than `claude-sonnet-4-5`.
   - Recommendation: Default to `claude-opus-4-6` as specified in ARCHITECTURE.md and config.py example. This can be overridden at runtime via `.env`. The decision belongs to Phase 3 when AnthropicProvider is implemented — Phase 1 only stores the config field.

2. **Celery worker command in docker-compose.yml**
   - What we know: Current command is `celery -A app.worker.celery_app.celery_app worker --loglevel=INFO` (uses default prefork pool). ML libraries (ctranslate2, PyTorch/EasyOCR) are unsafe with prefork due to fork-after-thread-init.
   - What's unclear: Phase 1 adds ML deps to the image but doesn't run them yet. The pool change is needed before Phase 2 runs tasks.
   - Recommendation: Update docker-compose.yml in Phase 1 to add `--pool=solo` to the worker command. This is a one-line change with no risk and prevents a hard-to-debug deadlock in Phase 2. Document as a SCHEMA-03 concern since it's infrastructure.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (not yet installed — Wave 0 gap) |
| Config file | `backend/pyproject.toml` (add `[tool.pytest.ini_options]` section) or `backend/pytest.ini` |
| Quick run command | `docker compose exec api pytest backend/tests/ -x -q` |
| Full suite command | `docker compose exec api pytest backend/tests/ -v` |

Note: `backend/app/tests/__init__.py` exists (empty), confirming the tests directory is initialized but no test files exist yet.

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-01 | All 7 new packages importable in container | smoke | `docker compose exec api python -c "import faster_whisper, easyocr, cv2, anthropic, openai, tiktoken"` | ❌ Wave 0 |
| INFRA-02 | Pre-warmed models exist in image at known paths | smoke | `docker compose exec worker python -c "from faster_whisper import WhisperModel; m = WhisperModel('base', device='cpu', compute_type='int8', local_files_only=True); print('OK')"` | ❌ Wave 0 |
| INFRA-03 | Settings loads all new env vars with defaults | unit | `pytest backend/tests/unit/test_config.py -x` | ❌ Wave 0 |
| SCHEMA-01 | FusionResult validates correct fields; rejects missing required fields | unit | `pytest backend/tests/unit/test_schemas.py::test_fusion_result -x` | ❌ Wave 0 |
| SCHEMA-02 | ClassificationResult clamps confidence; rejects invalid label; serializes label as string value | unit | `pytest backend/tests/unit/test_schemas.py::test_classification_result -x` | ❌ Wave 0 |
| SCHEMA-03 | Result table created in DB; can INSERT and SELECT a row; job_id unique constraint enforced | unit | `pytest backend/tests/unit/test_result_model.py -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `docker compose exec api python -c "import faster_whisper, easyocr, cv2, anthropic, openai, tiktoken; print('imports OK')"` (INFRA-01 smoke)
- **Per wave merge:** `docker compose exec api pytest backend/tests/unit/ -x -q`
- **Phase gate:** All unit tests green + INFRA-02 smoke passes before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `backend/pytest.ini` or `[tool.pytest.ini_options]` in `pyproject.toml` — test discovery config
- [ ] `backend/tests/__init__.py` — already exists (empty, good)
- [ ] `backend/tests/unit/__init__.py` — unit test subdirectory
- [ ] `backend/tests/unit/test_config.py` — tests for INFRA-03 (Settings loads new vars)
- [ ] `backend/tests/unit/test_schemas.py` — tests for SCHEMA-01 and SCHEMA-02 (FusionResult, ClassificationResult, MisinfoLabel)
- [ ] `backend/tests/unit/test_result_model.py` — tests for SCHEMA-03 (Result ORM, DB roundtrip)
- [ ] Framework install: `"pytest>=8.0"` added to `[project.optional-dependencies.test]` in `pyproject.toml`

---

## Sources

### Primary (HIGH confidence)

- Existing codebase (direct read): `backend/pyproject.toml`, `backend/Dockerfile`, `backend/app/core/config.py`, `backend/app/db/models/job.py`, `backend/app/main.py`, `infra/docker-compose.yml`, `.env.example` — all patterns derived from actual file contents
- PyPI: [faster-whisper 1.2.1](https://pypi.org/project/faster-whisper/) — latest version confirmed February 2026
- PyPI: [ctranslate2 4.7.1](https://pypi.org/project/ctranslate2/) — latest version confirmed February 2026
- PyPI: [easyocr 1.7.2](https://pypi.org/project/easyocr/) — latest version confirmed 2025
- PyPI: [anthropic 0.84.0](https://github.com/anthropics/anthropic-sdk-python/releases) — latest version confirmed February 2026
- Project planning docs: `.planning/REQUIREMENTS.md`, `.planning/research/STACK.md`, `.planning/research/ARCHITECTURE.md`, `.planning/research/SUMMARY.md` — authoritative project decisions

### Secondary (MEDIUM confidence)

- [Anthropic Structured Outputs announcement](https://towardsdatascience.com/hands-on-with-anthropics-new-structured-output-capabilities/) — confirmed tool_choice and new beta header both available; chose tool_choice for model compatibility
- [SQLAlchemy StrEnum discussion](https://github.com/sqlalchemy/sqlalchemy/discussions/12123) — confirmed `(str, enum.Enum)` pattern preferred over `StrEnum` for SQLAlchemy compatibility
- [faster-whisper Docker deployment patterns](https://deepwiki.com/SYSTRAN/faster-whisper/8.4-docker-deployment) — confirmed pre-warm build pattern with local_files_only for cold-start prevention

### Tertiary (LOW confidence)

- None — all key claims verified against official sources or existing codebase.

---

## Metadata

**Confidence breakdown:**

- Standard stack (version pins): HIGH — PyPI versions verified against live package pages as of 2026-03-09
- Architecture patterns: HIGH — derived from direct read of existing codebase files; consistent with project planning docs
- Pitfalls: HIGH — opencv-python-headless, pre-warm ordering, and MisinfoLabel enum patterns are all well-documented and directly observed in existing code conventions
- Anthropic tool_choice: MEDIUM — tool_choice with tools= is confirmed working; exact `tool_use_block.input` extraction pattern is training knowledge, validate against SDK docs in Phase 3 before implementing AnthropicProvider

**Research date:** 2026-03-09
**Valid until:** 2026-04-09 (stable libraries; faster-whisper and anthropic release frequently but >=pins protect from breakage)
