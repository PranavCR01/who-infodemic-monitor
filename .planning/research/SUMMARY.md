# Project Research Summary

**Project:** WHO Infodemic Monitor — ML Pipeline Porting (Milestone 3)
**Domain:** Production ML pipeline — health misinformation detection in short-form video
**Researched:** 2026-03-09
**Confidence:** HIGH

## Executive Summary

This milestone ports a validated Streamlit research prototype into a production FastAPI/Celery backend. The infrastructure is already in place (FastAPI, Celery, PostgreSQL, Redis, Docker — all verified end-to-end as of Milestone 2). The remaining work is well-scoped: strip Streamlit coupling from three prototype modules, wrap each in a clean Protocol-based interface, wire them through a `run_pipeline()` orchestrator, persist results to a new `Result` DB model, and expose the output through the existing `GET /jobs/{job_id}` endpoint. The recommended approach is a strict layered architecture (API → Worker → Pipeline → Domain → DB), with Protocol-based provider abstractions for both transcription and LLM inference, and Pydantic schemas as the data contracts between layers.

The key technical decision is to treat the prototype code as reference material, not as code to import directly. The three modules (`transcription.py`, `text_extractor.py`, `analysis.py`) contain all the domain logic needed, but `transcription.py` and `analysis.py` are Streamlit-coupled at their error-handling boundaries. The port is primarily a refactoring exercise, not a rewrite — the OCR module (`text_extractor.py`) is nearly production-ready and can be ported with minimal changes. The transcription and inference modules require systematic replacement of `st.error()` / `st.warning()` calls with `logging` and typed exceptions.

The dominant risks are operational, not algorithmic. EasyOCR and faster-whisper both download model weights lazily at first use — in Docker, this means re-downloading on every container restart unless models are baked into the image. The prototype's JSON parsing for LLM output is fragile (regex-based, fails on trailing commas and truncated responses) and must be hardened for production volumes. Celery's prefork concurrency model is incompatible with thread-unsafe ML model initialization unless the worker is configured carefully. These are all known problems with straightforward mitigations, and none require architectural changes.

## Key Findings

### Recommended Stack

The production ML pipeline adds four library categories to the existing infrastructure stack. For transcription, `faster-whisper>=1.0.1` with `ctranslate2>=4.3.1` is the correct choice — it is 4x faster than the original `openai-whisper` package on CPU, requires no GPU or CUDA base image, and was already validated in the prototype. The OpenAI Whisper API is a supported alternative via env var (`TRANSCRIPTION_PROVIDER=openai`). For OCR, `easyocr>=1.7.0` with `opencv-python-headless>=4.9` is mandatory — the headless OpenCV variant excludes Qt display libraries and avoids container startup failures. For inference, three providers are supported via a common Protocol: `openai>=1.13`, `anthropic>=0.28`, and `requests>=2.31` (for Ollama). Anthropic structured output must use the tool-use API (`tool_choice: {"type": "tool", ...}`) rather than prompt-only JSON, which eliminates the regex parsing fragility entirely. Supporting ML utilities include `pydantic>=2.6` (already installed) for schema validation and `tiktoken>=0.6` as a soft dependency for token budget guards.

**Core technologies:**
- `faster-whisper` + `ctranslate2`: local CPU transcription — validated in prototype, portable, no GPU required
- `easyocr` + `opencv-python-headless`: frame OCR — headless variant required for Docker; `gpu=False` for CPU mode
- `openai>=1.13`: OpenAI GPT-4o inference and Whisper API transcription — stable 1.x client interface
- `anthropic>=0.28`: Claude inference via tool-use for structured output — eliminates JSON parsing fragility
- `pydantic>=2.6`: schema validation at module boundaries — `InferenceLabel`, `ClassificationResult`, `FusionResult`
- Models must be pre-downloaded in Dockerfile (`WhisperModel("base")` + `easyocr.Reader(["en"])`) — adds ~500MB to image but eliminates cold-start failures

### Expected Features

The feature set for this milestone is tightly constrained to what makes the pipeline functional end-to-end. Research directly analyzed the prototype source code, giving HIGH confidence on exactly what needs to change.

**Must have (table stakes):**
- Transcription service (faster-whisper) — core extraction; no transcript means no LLM input
- OCR service (EasyOCR) — second modality; on-screen text is often the most misinformation-dense signal in health TikToks
- Multimodal fusion — combines audio + visual text into structured LLM input
- LLM inference with pluggable providers — classification is the core product output
- Structured result output — `label + confidence + explanation + evidence_sentences` is the API contract
- Result DB persistence — without this, `GET /jobs/{job_id}` never returns results
- Error propagation (non-Streamlit) — replace all `st.error()` / `st.warning()` with `logging` and typed exceptions
- Structured logging — Docker log aggregation requires Python `logging` module, not `print()`

**Should have (competitive / production quality):**
- Pluggable provider interface (Protocol/ABC) — swap OpenAI/Claude/Ollama via env var, not code changes
- Confidence clamping and label normalization — reject `"misinfo."`, clamp `1.5` to `1.0`
- Token budget guard — prevent submitting transcripts that exceed LLM context limits
- Per-job metadata in result — `model_used`, `provider`, `latency_ms` for audit and future eval comparisons
- Unit tests with mocked ML calls — `test_inference.py` first (pure logic); then transcription and OCR
- Integration test (upload → job → result) — validates full wiring without real ML calls

**Defer (v2+):**
- Alembic migrations — schema needs to stabilize first; `create_all` is acceptable for this milestone
- Frontend (React/Next.js) — separate milestone per project plan
- Calibrated confidence scores — requires labeled dataset and isotonic regression
- Segment-level classification — doubles scope; video-level verdict sufficient for v1 WHO use case
- GPU support — adds Docker CUDA complexity; CPU inference sufficient
- Authentication / API keys — out of scope per project plan
- Azure OpenAI provider — Ollama is lower priority too; OpenAI + Anthropic cover the v1 provider set

### Architecture Approach

The production architecture uses a strict layered model with a one-way dependency rule: API → Worker → Pipeline → Domain → DB. The pipeline layer (`core/pipeline/pipeline.py`) is the key design decision — it exposes a single `run_pipeline(video_path: str) -> ClassificationResult` function that orchestrates transcription, OCR, fusion, and inference in sequence. Critically, this function receives no DB session parameter. DB writes (PENDING → STARTED, result persistence, SUCCESS/FAILED) happen exclusively in `worker/tasks.py`. This makes `run_pipeline()` testable in isolation without a database. All inter-module data types are defined as Pydantic models in `core/schemas/pipeline.py` — `FusionResult` and `ClassificationResult` — giving a single authoritative data contract readable from one file. Provider selection (transcription backend and LLM provider) uses a factory function (`get_provider()`, `get_transcription_backend()`) that reads from settings and returns the appropriate Protocol-implementing class. No provider-specific logic ever appears in `pipeline.py` or `tasks.py`.

**Major components:**
1. `core/extraction/transcription.py` — `TranscriptionBackend` Protocol + `FasterWhisperBackend` + `OpenAIWhisperBackend`; pure function, no DB
2. `core/extraction/ocr/text_extractor.py` — direct port of `VideoTextExtractor`; minimal changes needed
3. `core/extraction/multimodal.py` — `MultimodalFuser.fuse()` combining transcript + OCR into `FusionResult`
4. `core/inference/classifier.py` — `LLMProvider` Protocol + `get_provider()` factory
5. `core/inference/providers/` — `OpenAIProvider`, `AnthropicProvider`, `OllamaProvider` (one file each)
6. `core/pipeline/pipeline.py` — `run_pipeline()` orchestrator; only entry point for the worker
7. `db/models/result.py` — `Result` ORM model (FK to `jobs.id`, unique); stores `label`, `confidence`, `explanation`, `evidence_snippets`
8. `worker/tasks.py` (extend) — wraps `run_pipeline()` with DB lifecycle management
9. `api/routers/jobs.py` (extend) — joins `Result` row into `GET /jobs/{job_id}` response when `status=SUCCESS`

### Critical Pitfalls

1. **EasyOCR downloads models at runtime into an ephemeral container layer** — pre-download in Dockerfile with `RUN python -c "import easyocr; easyocr.Reader(['en','es'], gpu=False)"` and pass `model_storage_directory` pointing to a persistent path; never rely on `~/.EasyOCR/` inside Docker

2. **faster-whisper reloads the model on every Celery task** — use a module-level singleton in the worker process (`_whisper_model = None` with lazy init on first task) or load via `worker_process_init` signal; the prototype creates `WhisperModel(...)` inside the function body, which adds 2–4 seconds per job

3. **Streamlit removal is not just removing the import** — `transcription.py` has 7 `st.*` call sites, `analysis.py` has ~6; removing the import without replacing call sites causes `NameError` at runtime on first error condition; add a CI `grep -r "streamlit" backend/` check that fails the build

4. **LLM provider abstraction breaks silently on response shape differences** — OpenAI uses `resp.choices[0].message.content`, Ollama uses `data["message"]["content"]`, Anthropic uses `resp.content[0].text`; silent fallback to empty string produces `CANNOT_RECOGNIZE` jobs that look successful; raise `ProviderError` on API failures, reserve `CANNOT_RECOGNIZE` for actual classification outcomes

5. **Celery prefork pool is unsafe with ML model initialization** — CTranslate2 (faster-whisper) and PyTorch (EasyOCR) use thread pools that deadlock after fork; use `--pool=solo` during development; for production concurrency, use `--pool=threads` or `--concurrency=1 --autoscale`

6. **JSON parsing fails on production LLM output** — the prototype's `_extract_json_block` regex approach fails on trailing commas, truncated responses, and nested quotes; strip code fences first, try `json.loads` on whole string, fall back to stricter regex; log every fallback at DEBUG level; use Anthropic tool-use or OpenAI `response_format=json_object` to eliminate parsing entirely for those providers

## Implications for Roadmap

Based on the combined research, the milestone decomposes naturally into four phases that respect the build order dependency graph. Each phase is independently testable.

### Phase 1: Schemas and Data Contracts

**Rationale:** All other phases depend on the shared Pydantic schemas (`FusionResult`, `ClassificationResult`, `MisinfoLabel`). Defining these first eliminates circular dependency risk and gives every other phase a clear interface to code against. The `Result` DB model also belongs here — adding it before any pipeline code ensures the table exists when the first test job runs.

**Delivers:** `core/schemas/pipeline.py`, `db/models/result.py` (registered in `main.py`), extended `core/config.py` and `.env.example` with all new env vars (`TRANSCRIPTION_BACKEND`, `LLM_PROVIDER`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OLLAMA_BASE_URL`, `WHISPER_MODEL_SIZE`, etc.)

**Addresses:** Result schema design (FEATURES.md), settings extensions required (ARCHITECTURE.md)

**Avoids:** Circular imports from premature coupling; `time_taken_secs` prototype field leaking into ORM constructor (Pitfall 14)

**Research flag:** SKIP — standard Pydantic v2 + SQLAlchemy 2.0 patterns; well-documented

### Phase 2: Extraction Modules (OCR + Transcription + Fusion)

**Rationale:** These are the domain leaves — they have no dependencies on inference or the pipeline orchestrator. OCR is ported first because `text_extractor.py` is nearly production-ready (no Streamlit coupling). Transcription second because the Streamlit removal is mechanical but requires audit. Fusion third because it depends on both.

**Delivers:** `core/extraction/ocr/text_extractor.py` (ported), `core/extraction/transcription.py` (`TranscriptionBackend` Protocol + `FasterWhisperBackend` + `OpenAIWhisperBackend`), `core/extraction/multimodal.py` (`MultimodalFuser`), Dockerfile additions (model pre-download layers)

**Addresses:** Transcription service, OCR service, multimodal fusion (FEATURES.md table stakes)

**Avoids:** EasyOCR model download at runtime (Pitfall 1); faster-whisper model reload per task (Pitfall 2); Streamlit removal errors (Pitfall 6); OOM on long videos — convert frame list to generator (Pitfall 7); OpenAI Whisper 25MB limit — preserve split logic (Pitfall 9)

**Research flag:** SKIP — all patterns are direct ports from validated prototype code; no novel decisions

### Phase 3: Inference Providers and Pipeline Orchestrator

**Rationale:** Inference is the most complex porting task because `analysis.py` has both Streamlit coupling and the fragile JSON parsing logic. Building providers in isolation (OpenAI first, then Anthropic with tool-use, then Ollama) before wiring into the pipeline allows each to be unit-tested independently. The pipeline orchestrator is built last in this phase, when all inputs (transcription, OCR, fusion, inference) are available.

**Delivers:** `core/inference/providers/openai.py`, `core/inference/providers/anthropic.py`, `core/inference/providers/ollama.py`, `core/inference/classifier.py` (`LLMProvider` Protocol + `get_provider()` factory), `core/pipeline/pipeline.py` (`run_pipeline()`)

**Addresses:** LLM inference with pluggable providers, pluggable provider interface (FEATURES.md); provider abstraction pattern (ARCHITECTURE.md)

**Avoids:** Provider response shape differences causing silent `CANNOT_RECOGNIZE` (Pitfall 3); JSON parsing failures (Pitfall 4 — use Anthropic tool-use and OpenAI `json_object` mode); `CANNOT_RECOGNIZE` masking infrastructure errors (raise `ProviderError` not fallback); Ollama hardcoded URL (Pitfall 10)

**Research flag:** NEEDS RESEARCH — validate Anthropic SDK tool-use exact parameter names against current SDK docs before implementing; confirm `claude-opus-4-6` is the correct model ID string

### Phase 4: Task Wiring, Result Persistence, and API Extension

**Rationale:** This phase connects all domain modules to the infrastructure layer. The Celery task is extended to call `run_pipeline()`, persist the `Result`, and update job status. The jobs router is extended to return result data when `status=SUCCESS`. This is the integration phase — unit tests exist by now; this phase adds the integration test.

**Delivers:** Extended `worker/tasks.py` (full pipeline wiring), extended `api/routers/jobs.py` (result in response), unit test suite (`tests/unit/`), integration test (`tests/integration/test_pipeline.py`)

**Addresses:** Result DB persistence, `GET /jobs/{job_id}` returns result, unit tests, integration test (FEATURES.md); `process_video_task` wiring (ARCHITECTURE.md)

**Avoids:** DB session leaking into pipeline layer (Anti-Pattern 1 from ARCHITECTURE.md); Celery prefork concurrency unsafe with ML models (Pitfall 5 — configure `--pool=solo` in dev, document production concurrency settings); `time_taken_secs` prototype field leaking into ORM (Pitfall 14)

**Research flag:** SKIP — Celery task DB session management, result persistence pattern, and TestClient integration testing are all well-documented standard patterns already reflected in the existing task stub

### Phase Ordering Rationale

- Schemas first because every other module imports from `core/schemas/pipeline.py` — defining them first eliminates the temptation to pass raw dicts between modules
- Extraction before inference because transcription and OCR have no external API dependencies (faster-whisper runs locally), making them testable without API keys; this gives early confidence the pipeline works before inference is wired
- Inference providers before the orchestrator because each provider can be unit-tested with mocked HTTP calls independently of the full pipeline; building them in isolation catches provider-specific bugs early
- Task wiring last because it is the integration point — all domain modules must be correct before the Celery task is a meaningful test target
- This order directly avoids the "anti-pattern: importing from old prototype directly" (ARCHITECTURE.md) — each module is built clean from the start rather than importing from the old repo and refactoring in-place

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3 (Inference Providers):** Validate Anthropic SDK `tool_choice` parameter names and exact format against current SDK documentation before implementing; the research notes MEDIUM confidence on this specific parameter. Confirm the correct current Anthropic model ID (`claude-opus-4-6` noted as "confirm before hardcoding" in ARCHITECTURE.md).

Phases with standard patterns (skip research-phase):
- **Phase 1 (Schemas):** Standard Pydantic v2 + SQLAlchemy 2.0; zero novel decisions
- **Phase 2 (Extraction):** Direct port from validated prototype code; all patterns HIGH confidence
- **Phase 4 (Task Wiring):** Standard Celery + FastAPI TestClient patterns; already reflected in existing codebase

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | faster-whisper and EasyOCR were validated in the prototype; OpenCV headless pattern is industry-standard; only version pin validation needed against PyPI before build |
| Features | HIGH | Based on direct source code read of the prototype — all Streamlit call sites identified, all function signatures analyzed; no assumptions |
| Architecture | HIGH | Layered architecture and Protocol-based provider abstraction are stable Python 3.11 production idioms; build order derived from actual module import dependencies |
| Pitfalls | HIGH (critical) / MEDIUM (operational) | Streamlit removal and JSON parsing pitfalls observed directly in code (HIGH); Docker model download and Celery fork behavior are well-established patterns (MEDIUM) |

**Overall confidence:** HIGH

### Gaps to Address

- **Anthropic SDK exact parameter names:** The `tool_choice` parameter format and minimum SDK version that introduced tool-use support should be validated against current `anthropic` SDK docs (PyPI / GitHub) before implementing `AnthropicProvider`. Research rates this MEDIUM confidence. Resolution: check Anthropic SDK changelog for the version that added `tool_choice` before pinning `>=0.28`.

- **Anthropic model ID string:** The architecture research flags `claude-opus-4-6` as "confirm before hardcoding." The correct production default (cost vs. capability tradeoff for health classification) should be explicitly decided — `claude-3-5-sonnet-20241022` is documented as production-grade and may be more cost-effective than Opus for this use case.

- **faster-whisper + ctranslate2 PyPI version pins:** Research notes MEDIUM confidence on `>=1.0.1` / `>=4.3.1` because PyPI state at implementation time may differ from prototype. Validate `pip install faster-whisper ctranslate2` succeeds with these constraints in a clean environment before the Dockerfile is updated.

- **EasyOCR model storage volume strategy:** The Dockerfile pre-download approach bakes models into the image (~500MB addition). An alternative is a named Docker volume with a one-time init container. The decision should be made before writing the Dockerfile layer — image baking is simpler but increases image size; volume approach is more flexible for model updates.

- **Celery concurrency configuration for production:** Research recommends `--pool=solo` for development, but the production-ready configuration (threads vs. prefork vs. solo with autoscale) depends on the deployment environment and expected throughput. Flag for explicit decision before deploying beyond local Docker Compose.

## Sources

### Primary (HIGH confidence)
- Prototype source code (direct read): `pages/processes/transcription.py`, `pages/processes/analysis.py`, `pages/processes/ocr/text_extractor.py`, `pages/processes/multimodal.py` — all Streamlit call sites identified, function signatures analyzed
- Existing production codebase (direct read): `backend/app/worker/tasks.py`, `backend/app/db/`, `backend/app/api/routers/` — patterns derived from actual code, not assumptions
- Project documentation: `.planning/PROJECT.md`, `.planning/codebase/CONCERNS.md`, `CLAUDE.md`
- Python standard library patterns: `typing.Protocol`, `logging`, `abc.ABC` — stable Python 3.8+ idioms

### Secondary (MEDIUM confidence)
- EasyOCR library internals: `model_storage_directory` parameter behavior in Docker — well-documented in EasyOCR README and GitHub issues
- faster-whisper / CTranslate2: model loading patterns and per-process singleton behavior — library documentation and known Celery/fork interaction patterns
- Anthropic SDK structured output via tool-use: training knowledge as of August 2025 — validate parameter names against current SDK before implementing
- OpenAI `response_format=json_object` mode: training knowledge — stable since GPT-4o launch

### Tertiary (LOW confidence)
- Version pins (`faster-whisper>=1.0.1`, `ctranslate2>=4.3.1`, `easyocr>=1.7.0`): based on prototype comments and library release history — validate against PyPI before pinning in pyproject.toml

---
*Research completed: 2026-03-09*
*Ready for roadmap: yes*
