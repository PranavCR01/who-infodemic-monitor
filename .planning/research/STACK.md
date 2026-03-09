# Technology Stack — ML Pipeline Porting

**Project:** WHO Infodemic Monitor
**Milestone scope:** Port transcription, OCR, inference, and multimodal fusion from Streamlit prototype to production backend
**Researched:** 2026-03-09
**Overall confidence:** MEDIUM — library behavior is HIGH confidence from training knowledge; specific pinned versions need validation against PyPI before first container build

---

## Context

The infrastructure milestone (FastAPI + Celery + PostgreSQL + Redis + Docker) is complete and must not change. This research covers only the ML pipeline libraries that need to be added. The existing `backend/Dockerfile` already installs `ffmpeg`, `libgl1`, and `libglib2.0-0`, which satisfies core native dependencies for both faster-whisper and EasyOCR.

---

## Recommended Stack — ML Pipeline Additions

### Transcription

| Technology | Recommended Version | Purpose | Rationale |
|------------|--------------------|---------|-----------|
| `faster-whisper` | `>=1.0.1` | Local Whisper inference via CTranslate2 | 4x faster than openai-whisper on CPU, same model weights, no CUDA required in CPU mode, production-ready since v1.0. The prototype already uses this version pinned at `1.0.1`. |
| `ctranslate2` | `>=4.3.1` | CTranslate2 runtime (faster-whisper backend) | Must be installed alongside faster-whisper. Version 4.3.1 was validated in the prototype. Pin conservatively unless explicitly upgrading. |
| `openai` | `>=1.13` | OpenAI Whisper-1 API transcription | Already indirectly used via the prototype. The `>=1.13` series uses the stable `openai.OpenAI()` client interface. The prototype's `_transcribe_openai()` uses `client.audio.transcriptions.create()` which has been stable across 1.x. |

**Decision:** Use `faster-whisper` as the default transcription backend in Docker (CPU mode, `int8` compute type). OpenAI Whisper API is an opt-in override configured via `TRANSCRIPTION_PROVIDER=openai` env var. Do not require GPU in the worker container — this keeps the image portable and cost-effective. The prototype proves CPU mode works correctly.

**Confidence:** HIGH — faster-whisper CTranslate2 CPU path is well-established. The prototype pinned `faster-whisper==1.0.1` + `ctranslate2==4.3.1` and these were explicitly validated.

---

### OCR

| Technology | Recommended Version | Purpose | Rationale |
|------------|--------------------|---------|-----------|
| `easyocr` | `>=1.7.0` | On-screen text extraction from video frames | The prototype's `VideoTextExtractor` class uses it cleanly. No Streamlit deps. The library is CPU-capable and the `gpu=False` path is what the prototype uses. |
| `opencv-python-headless` | `>=4.9` | Video frame sampling (`cv2.VideoCapture`) | Use `opencv-python-headless` instead of `opencv-python` — the headless variant excludes Qt/GTK display libs, reducing container size by ~200MB. The `libgl1` + `libglib2.0-0` apt packages already in the Dockerfile satisfy EasyOCR's OpenCV native dependency even with the headless build. |

**Decision:** Use `easyocr` with `gpu=False` in Docker. EasyOCR downloads language models on first inference (~40MB for English). This must be handled at container startup or build time, not lazily at request time — see Pitfalls. `opencv-python-headless` is the correct Docker variant; do NOT use `opencv-python` (Qt display failures in headless containers).

**Confidence:** HIGH for usage patterns. MEDIUM for exact version pin — validate `easyocr>=1.7.0` against PyPI at build time.

---

### LLM Inference

| Technology | Recommended Version | Purpose | Rationale |
|------------|--------------------|---------|-----------|
| `openai` | `>=1.13` | OpenAI GPT-4o inference | The `openai` package is already needed for Whisper API. Reuse the same package for inference. The prototype uses `client.chat.completions.create()` which is stable across 1.x. |
| `anthropic` | `>=0.28` | Anthropic Claude inference | Current production SDK uses `anthropic.Anthropic()` client with `client.messages.create()`. Supports structured output via tool use (`tools=` parameter) — better than prompt-only JSON for production reliability. |
| `requests` | `>=2.31` | Ollama HTTP API calls | The prototype uses `requests.post("http://localhost:11434/api/chat")`. In Docker, Ollama is an external service; the URL should be configurable via env var (`OLLAMA_BASE_URL`). |

**Decision:** Support three providers via a pluggable interface: `openai`, `anthropic`, `ollama`. Default provider configured via `INFERENCE_PROVIDER` env var. The provider abstraction wraps each in a class implementing a common interface — see Architecture section below.

**Note on Anthropic structured output:** The prototype uses prompt-engineering ("respond ONLY as JSON") plus regex JSON extraction. For production, use Anthropic's tool-use feature (`tools=[]` parameter) to force structured output. This is more reliable than regex parsing and eliminates the `_extract_json_block()` fragility. See Implementation Notes below.

**Confidence:** HIGH for openai 1.x and requests usage patterns. MEDIUM for anthropic SDK version — the `>=0.28` range covers the stable `messages.create()` API with tool use support, but validate the exact minimum version that introduced tool use before pinning.

---

### Supporting ML/Processing

| Technology | Recommended Version | Purpose | Rationale |
|------------|--------------------|---------|-----------|
| `pydantic` | `>=2.6` (already installed) | Schema validation for pipeline results | Already in pyproject.toml. Use `BaseModel` for `ExtractionResult`, `InferenceResult`, `PipelineResult` data classes — strict validation at module boundaries. |
| `tiktoken` | `>=0.6` | Optional token counting/truncation | The prototype uses it for token limit warnings. In production it's useful for truncating long transcripts before sending to LLMs with context limits. Make it optional (soft dependency). |

---

## Docker Considerations

### Base Image

Keep `python:3.11-slim`. Do NOT upgrade to 3.12 — the current `pyproject.toml` requires `>=3.11` and the Dockerfile pins 3.11. Changing this mid-project introduces unnecessary risk.

### System Dependencies — What to Add

The existing Dockerfile already installs:
- `ffmpeg` — audio extraction (satisfies faster-whisper input requirements)
- `libgl1` — OpenCV native dependency
- `libglib2.0-0` — OpenCV native dependency

No additional system packages are needed for the ML pipeline. faster-whisper and EasyOCR both run on the existing native dependency set.

### Model Download Strategy

**Problem:** EasyOCR and faster-whisper both download models lazily on first use. In a Docker container this means:
1. First job execution blocks for 30-120 seconds downloading models
2. Models re-download on every container restart (no caching)
3. No network access in production environments will cause silent failures

**Solution:** Pre-warm models in the Dockerfile during build. Add after pip install:

```dockerfile
# Pre-download faster-whisper "base" model during build
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"

# Pre-download EasyOCR English model during build
RUN python -c "import easyocr; easyocr.Reader(['en'], gpu=False)"
```

This adds ~500MB to the image but eliminates cold-start latency and download failures at runtime.

**Confidence:** HIGH — this pattern is standard for ML model serving in Docker.

### Container Size Estimate

Base `python:3.11-slim`: ~130MB
+ System deps (ffmpeg, libgl, libglib): ~130MB
+ Python packages (existing): ~80MB
+ faster-whisper + ctranslate2: ~150MB
+ EasyOCR + OpenCV headless: ~200MB
+ Pre-downloaded models (whisper-base + easyocr-en): ~200MB
**Total estimated: ~900MB–1.1GB**

This is acceptable for an ML processing container. Using `opencv-python-headless` over `opencv-python` saves ~200MB.

---

## Provider Abstraction Pattern

**Recommendation:** Abstract over LLM providers using a Protocol/ABC class with dependency injection via the worker task.

```python
# backend/app/core/inference/base.py
from abc import ABC, abstractmethod
from app.core.schemas.results import InferenceResult

class InferenceProvider(ABC):
    @abstractmethod
    def classify(self, content: str) -> InferenceResult:
        ...

# backend/app/core/inference/providers/openai_provider.py
class OpenAIProvider(InferenceProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        ...
    def classify(self, content: str) -> InferenceResult:
        ...

# backend/app/core/inference/providers/anthropic_provider.py
class AnthropicProvider(InferenceProvider):
    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022"):
        ...
    def classify(self, content: str) -> InferenceResult:
        ...

# backend/app/core/inference/providers/ollama_provider.py
class OllamaProvider(InferenceProvider):
    def __init__(self, base_url: str, model: str = "mistral"):
        ...
    def classify(self, content: str) -> InferenceResult:
        ...

# backend/app/core/inference/factory.py
def get_provider(settings: Settings) -> InferenceProvider:
    if settings.INFERENCE_PROVIDER == "anthropic":
        return AnthropicProvider(settings.ANTHROPIC_API_KEY, settings.INFERENCE_MODEL)
    elif settings.INFERENCE_PROVIDER == "ollama":
        return OllamaProvider(settings.OLLAMA_BASE_URL, settings.INFERENCE_MODEL)
    else:  # default: openai
        return OpenAIProvider(settings.OPENAI_API_KEY, settings.INFERENCE_MODEL)
```

**Why this pattern:**
- The worker task calls `get_provider(settings).classify(content)` — zero branching in task logic
- Each provider handles its own client initialization, retry, and error normalization
- Adding a new provider (e.g., Azure OpenAI) means adding one file, not touching the task
- Settings injection makes providers testable with mocks

**Transcription follows the same pattern:**

```python
# backend/app/core/extraction/transcription.py
class TranscriptionProvider(ABC):
    @abstractmethod
    def transcribe(self, video_path: str) -> str: ...

class FasterWhisperProvider(TranscriptionProvider): ...
class OpenAIWhisperProvider(TranscriptionProvider): ...

def get_transcription_provider(settings: Settings) -> TranscriptionProvider:
    if settings.TRANSCRIPTION_PROVIDER == "openai":
        return OpenAIWhisperProvider(settings.OPENAI_API_KEY)
    return FasterWhisperProvider()  # default
```

**Confidence:** HIGH — this is a standard Python ABC/factory pattern with no library-specific risks.

---

## Result Schema Design

### DB Model: `results` table

```python
# backend/app/db/models/result.py
class Result(Base):
    __tablename__ = "results"

    id: Mapped[str] = mapped_column(primary_key=True)          # UUID str
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), unique=True)
    label: Mapped[str] = mapped_column(String(32))             # MISINFO | NO_MISINFO | DEBUNKING | CANNOT_RECOGNIZE
    confidence: Mapped[float] = mapped_column(Float)           # 0.0 – 1.0
    explanation: Mapped[str] = mapped_column(Text)             # 2-4 sentence rationale
    evidence_snippets: Mapped[list] = mapped_column(JSON)      # list[str] — verbatim quotes
    keywords: Mapped[list] = mapped_column(JSON)               # list[str] — topic keywords
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)   # audio transcript
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)     # combined OCR text
    inference_latency_secs: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
```

**Design rationale:**
- `evidence_snippets` and `keywords` are stored as `JSON` columns (PostgreSQL JSONB-compatible via SQLAlchemy `JSON` type). This avoids a separate join table for a list that is always read together with the result.
- `label` is a plain `String(32)` rather than a DB enum — the canonical enum lives in the Python application layer (`LabelEnum`), avoiding schema migrations when the enum is adjusted during development.
- `unique=True` on `job_id` FK enforces one result per job at the DB level.
- `transcript` and `ocr_text` stored for debugging and future re-analysis without re-running extraction.
- `inference_latency_secs` stored for performance monitoring.

### Pydantic Schema (API Response)

```python
# backend/app/core/schemas/results.py
from pydantic import BaseModel
from typing import Optional
import enum

class InferenceLabel(str, enum.Enum):
    MISINFO = "MISINFO"
    NO_MISINFO = "NO_MISINFO"
    DEBUNKING = "DEBUNKING"
    CANNOT_RECOGNIZE = "CANNOT_RECOGNIZE"

class InferenceResult(BaseModel):
    label: InferenceLabel
    confidence: float          # 0.0 – 1.0
    explanation: str
    evidence_snippets: list[str]
    keywords: list[str]
    inference_latency_secs: Optional[float] = None

class ExtractionResult(BaseModel):
    transcript: str
    ocr_text: str
    combined_content: str      # formatted: [AUDIO TRANSCRIPT]\n...\n\n[ON-SCREEN TEXT]\n...

class PipelineResult(BaseModel):
    extraction: ExtractionResult
    inference: InferenceResult
```

**Why use `str` enum for `InferenceLabel`:** FastAPI serializes `str` enums as their string value by default. This means `GET /jobs/{job_id}` returns `"label": "MISINFO"` not `"label": 0` — which is what the API consumer expects.

**Confidence:** HIGH — this schema design pattern is standard SQLAlchemy 2.0 + Pydantic v2 and maps directly to the existing DB model conventions in the codebase.

---

## Anthropic SDK: Structured Output Best Practices

### Use Tool Use, Not Prompt-Only JSON

The prototype uses a prompt-engineering approach: "respond ONLY as JSON". This is fragile — the model occasionally wraps output in markdown fences or adds prose. The prototype's `_extract_json_block()` handles this with regex, which is a maintenance burden.

**Production approach:** Use Anthropic's tool use feature to force structured output:

```python
import anthropic

client = anthropic.Anthropic(api_key=api_key)

tools = [{
    "name": "classify_content",
    "description": "Classify health content for misinformation",
    "input_schema": {
        "type": "object",
        "properties": {
            "label": {
                "type": "string",
                "enum": ["MISINFO", "NO_MISINFO", "DEBUNKING", "CANNOT_RECOGNIZE"]
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "explanation": {"type": "string"},
            "evidence_sentences": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 3
            },
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 10
            }
        },
        "required": ["label", "confidence", "explanation", "evidence_sentences", "keywords"]
    }
}]

response = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=1024,
    tools=tools,
    tool_choice={"type": "tool", "name": "classify_content"},  # force tool use
    messages=[
        {"role": "user", "content": content}
    ],
    system=SYSTEM_PROMPT
)

# Extract tool input — always structured, never needs regex
tool_use = next(b for b in response.content if b.type == "tool_use")
result = tool_use.input  # already a dict, no parsing needed
```

**Why `tool_choice: {"type": "tool", "name": "..."}` matters:** This forces the model to use the specified tool, guaranteeing structured JSON output. Without it, the model can sometimes return a text response instead of a tool call.

**For OpenAI:** Use `response_format={"type": "json_object"}` or the newer `response_format={"type": "json_schema", "json_schema": {...}}` in GPT-4o. Both eliminate the need for regex extraction.

**For Ollama:** Keep the prompt-based JSON approach (the prototype's `_extract_json_block()` logic). Ollama models vary in their support for structured output tools. Accept that Ollama is a lower-reliability provider and document this clearly.

**Confidence:** HIGH for Anthropic tool use pattern (this is the documented production approach as of 2024). MEDIUM for exact parameter names — validate against current Anthropic SDK docs before implementing.

---

## pyproject.toml Additions

The current `backend/pyproject.toml` only contains the infrastructure dependencies. Add:

```toml
dependencies = [
  # existing
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

  # ML pipeline additions
  "faster-whisper>=1.0.1",
  "ctranslate2>=4.3.1",
  "easyocr>=1.7.0",
  "opencv-python-headless>=4.9",
  "openai>=1.13",
  "anthropic>=0.28",
  "requests>=2.31",
  "tiktoken>=0.6",
]
```

**Note on `sqlalchemy`, `psycopg[binary]`, `aiofiles`:** These appear in CLAUDE.md as already added but are absent from the pyproject.toml found on disk. Confirm the current file contents before modifying — the worktree may be behind main.

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Transcription | `faster-whisper` (local, default) | `openai-whisper` (original OpenAI package) | openai-whisper is slower (PyTorch-based), larger image size (~1.5GB with PyTorch vs ~150MB with CTranslate2). The prototype already validated faster-whisper. |
| Transcription | `faster-whisper` (CPU) | GPU-accelerated inference | GPU requires CUDA base image (~3GB), GPU-enabled Docker runtime on host, costs more. Not justified for the demo/prototype stage. Add GPU support later if latency is unacceptable. |
| OCR | `easyocr` | `pytesseract` | Tesseract has poor accuracy on stylized text (TikTok-style overlays, bold captions). EasyOCR is more accurate on this content type. The prototype validated it. |
| OCR OpenCV | `opencv-python-headless` | `opencv-python` | `opencv-python` includes Qt GUI dependencies that fail silently in headless containers. `opencv-python-headless` is the explicit headless build. |
| Inference | Anthropic tool use | Prompt-only JSON + regex | Regex JSON extraction fails on edge cases (nested JSON, markdown fences). Tool use is deterministic. |
| Inference | Per-provider classes + factory | Single function with if/elif | Class-per-provider pattern is testable, extensible, and doesn't require modifying core task logic to add providers. |
| Result storage | `JSON` column for arrays | Separate `evidence_snippets` / `keywords` join tables | Evidence snippets are always read alongside the result (no independent querying needed). JSON columns are simpler and sufficient for this access pattern. |
| Result label | Python `str` enum + `String(32)` column | PostgreSQL `ENUM` type via `SAEnum` | PostgreSQL ENUMs require `ALTER TYPE` migrations to add values. During active development this is painful. Python str enum provides the same validation with easier iteration. |

---

## Configuration Keys to Add

The following environment variables need to be added to `.env.example` and `backend/app/core/config.py`:

```env
# Transcription
TRANSCRIPTION_PROVIDER=faster_whisper   # faster_whisper | openai
WHISPER_MODEL_SIZE=base                  # tiny | base | small | medium | large-v3

# Inference
INFERENCE_PROVIDER=openai                # openai | anthropic | ollama
INFERENCE_MODEL=gpt-4o                   # model name per-provider
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
OLLAMA_BASE_URL=http://ollama:11434      # when running Ollama as a Docker service

# OCR
OCR_LANGUAGES=en,es                      # comma-separated language codes
OCR_SAMPLE_FPS=1.0                       # frames per second to sample
OCR_MIN_CONFIDENCE=0.5                   # minimum detection confidence
```

---

## Sources

- Prototype code (reference only): `D:\Python files\tiktok-2026-01-29\pages\processes\transcription.py`, `analysis.py`, `ocr\text_extractor.py`, `multimodal.py`
- Existing production stack: `D:\Python files\who-infodemic-monitor\.planning\codebase\STACK.md`
- faster-whisper version note from prototype: `pip install faster-whisper==1.0.1 ctranslate2==4.3.1` (comment in transcription.py line 54-55) — MEDIUM confidence, validate against current PyPI
- Anthropic tool use API: training knowledge as of August 2025 — MEDIUM confidence, validate parameter names against current Anthropic SDK docs
- OpenCV headless Docker pattern: HIGH confidence, industry-standard practice
- EasyOCR model pre-warming: HIGH confidence, standard ML Docker pattern

*Version pinning noted as MEDIUM confidence where PyPI validation is needed. All library behavior and patterns are HIGH confidence.*
