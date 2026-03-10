# Requirements: WHO Infodemic Monitor

**Defined:** 2026-03-09
**Core Value:** A public-health analyst can upload a video and receive a reliable, explainable misinformation verdict — with evidence — in under 60 seconds.

## v1 Requirements

### Infrastructure & Configuration

- [ ] **INFRA-01**: ML dependencies added to pyproject.toml: `faster-whisper`, `easyocr`, `anthropic`, `opencv-python-headless`, `ctranslate2`
- [ ] **INFRA-02**: Dockerfile updated with ML system deps (`libgl1`, `libglib2.0-0`), model pre-warming commands for faster-whisper and EasyOCR during build (prevents cold-start on first job)
- [x] **INFRA-03**: New environment variables in `config.py` and `.env.example`: `WHISPER_PROVIDER`, `WHISPER_MODEL`, `INFERENCE_PROVIDER`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`

### Data Schemas & Models

- [x] **SCHEMA-01**: `FusionResult` Pydantic schema: `transcript: str`, `visual_text: str`, `combined_content: str`, `metadata: dict`
- [x] **SCHEMA-02**: `ClassificationResult` Pydantic schema: `label: MisinfoLabel`, `confidence: float` (0.0–1.0 clamped), `explanation: str`, `evidence_snippets: list[str]`, `provider: str`, `model_used: str`, `latency_ms: int`
- [x] **SCHEMA-03**: `Result` SQLAlchemy ORM model with fields: `id` (UUID), `job_id` (FK → jobs.id, unique), `label` (String), `confidence` (Float), `explanation` (Text), `evidence_snippets` (JSON), `combined_content` (Text), `provider` (String), `model_used` (String), `latency_ms` (Integer), `created_at` (DateTime)

### OCR Extraction

- [ ] **OCR-01**: `VideoTextExtractor` ported to `backend/app/core/extraction/ocr.py` — zero Streamlit imports, configurable `fps` and `confidence_threshold` parameters, typed return values
- [ ] **OCR-02**: EasyOCR `Reader` initialized once per worker process (module-level singleton) — not re-created per task call

### Transcription Extraction

- [ ] **TRANS-01**: `TranscriptionBackend` Protocol defined: `transcribe(file_path: str) -> str`
- [ ] **TRANS-02**: `FasterWhisperBackend` implemented: `WhisperModel` loaded once per worker process (module-level singleton), configurable `model_size` via `WHISPER_MODEL` env var, CPU mode default
- [ ] **TRANS-03**: `OpenAIWhisperBackend` implemented: cloud transcription via OpenAI Whisper API, raises `FileTooLargeError` if file > 25MB
- [ ] **TRANS-04**: `TranscriptionService` selects backend via `WHISPER_PROVIDER` env var (`faster-whisper` | `openai`), ported to `backend/app/core/extraction/transcription.py`

### Multimodal Fusion

- [ ] **FUSION-01**: `MultimodalFusion.fuse(transcript: str, ocr_result: list) -> FusionResult` ported to `backend/app/core/extraction/multimodal.py` — raises `ContentTooLongError` if combined token count exceeds provider limit

### Inference Providers

- [ ] **INFER-01**: `InferenceProvider` Protocol defined: `classify(fusion: FusionResult) -> ClassificationResult`
- [ ] **INFER-02**: `OpenAIProvider` implemented using `response_format` / `json_schema` for deterministic structured output
- [ ] **INFER-03**: `AnthropicProvider` implemented using `tool_choice` for deterministic structured JSON output
- [ ] **INFER-04**: `OllamaProvider` implemented with robust JSON parsing: handles trailing commas, truncated responses, multi-object output — falls back to `CANNOT_RECOGNIZE` on parse failure (never crashes)
- [ ] **INFER-05**: `get_provider(settings) -> InferenceProvider` factory selects provider via `INFERENCE_PROVIDER` env var — fails loudly at startup if value is unrecognised
- [ ] **INFER-06**: Canonical label schema enforced across all providers: `MISINFO | NO_MISINFO | DEBUNKING | CANNOT_RECOGNIZE` — any unrecognised LLM output string maps to `CANNOT_RECOGNIZE`

### Pipeline Orchestration & Persistence

- [ ] **PIPE-01**: `run_pipeline(video_path: str, settings: Settings) -> ClassificationResult` in `backend/app/core/pipeline.py` — pure domain logic, no DB session, orchestrates transcription → OCR → fusion → inference
- [ ] **PIPE-02**: `process_video_task` wired end-to-end: loads video path from DB, calls `run_pipeline`, persists `Result` row, updates `Job` status to `SUCCESS` or `FAILED` (on any exception, including `ContentTooLongError`)
- [ ] **PIPE-03**: `GET /jobs/{job_id}` response extended to include result fields (`label`, `confidence`, `explanation`, `evidence_snippets`, `provider`, `model_used`, `latency_ms`) when `status == SUCCESS`

### Evaluation & Testing

- [ ] **EVAL-01**: pytest unit tests for OCR module — mock `cv2.VideoCapture` frames, assert text extraction logic without real video files
- [ ] **EVAL-02**: pytest unit tests for transcription module — mock both backends, assert provider selection and error handling
- [ ] **EVAL-03**: pytest unit tests for each inference provider — mock API responses, assert label mapping, test JSON parsing edge cases (truncated output, trailing commas, wrong label strings)
- [ ] **EVAL-04**: Integration test: upload a real short test video → `POST /jobs/create` → poll `GET /jobs/{job_id}` until `SUCCESS` → assert response contains `label`, `confidence`, `explanation`
- [ ] **EVAL-05**: Eval benchmarking script at `scripts/eval_pipeline.py` — accepts `--input-dir` of video files, runs pipeline on each, outputs CSV with `video_path`, `label`, `confidence`, `latency_ms`, `provider`

## v2 Requirements

### Results & Review

- **RESULT-01**: Analyst can mark a result as reviewed (human-in-the-loop annotation)
- **RESULT-02**: Analyst can override the predicted label with a corrected label
- **RESULT-03**: Results exportable as CSV from API endpoint

### Scale & Performance

- **PERF-01**: Celery worker supports concurrent task processing (`--concurrency > 1`) with thread-safe ML model sharing
- **PERF-02**: Video file storage abstracted to support S3 (beyond local Docker volume)
- **PERF-03**: Alembic migrations replace `create_all` startup hack

### Providers

- **PROV-01**: Azure OpenAI provider added alongside existing OpenAI provider
- **PROV-02**: Whisper model size configurable per-request (not just globally)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Frontend (React/Next.js) | Separate milestone — backend API first |
| User authentication / multi-tenant | Single-user system for v1 |
| Video segment-level classification | Video-level only for v1 — too complex |
| Real-time streaming results | Polling sufficient for v1 |
| GPU Docker support | CPU-mode sufficient for prototype scale |
| LLM retry on failure | Fail-fast chosen for v1 — analyst resubmits |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 1 | Pending |
| INFRA-02 | Phase 1 | Pending |
| INFRA-03 | Phase 1 | Complete |
| SCHEMA-01 | Phase 1 | Complete |
| SCHEMA-02 | Phase 1 | Complete |
| SCHEMA-03 | Phase 1 | Complete |
| OCR-01 | Phase 2 | Pending |
| OCR-02 | Phase 2 | Pending |
| TRANS-01 | Phase 2 | Pending |
| TRANS-02 | Phase 2 | Pending |
| TRANS-03 | Phase 2 | Pending |
| TRANS-04 | Phase 2 | Pending |
| FUSION-01 | Phase 2 | Pending |
| INFER-01 | Phase 3 | Pending |
| INFER-02 | Phase 3 | Pending |
| INFER-03 | Phase 3 | Pending |
| INFER-04 | Phase 3 | Pending |
| INFER-05 | Phase 3 | Pending |
| INFER-06 | Phase 3 | Pending |
| PIPE-01 | Phase 4 | Pending |
| PIPE-02 | Phase 4 | Pending |
| PIPE-03 | Phase 4 | Pending |
| EVAL-01 | Phase 5 | Pending |
| EVAL-02 | Phase 5 | Pending |
| EVAL-03 | Phase 5 | Pending |
| EVAL-04 | Phase 5 | Pending |
| EVAL-05 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 27 total
- Mapped to phases: 27
- Unmapped: 0

---
*Requirements defined: 2026-03-09*
*Last updated: 2026-03-09 after roadmap creation — all 27 requirements mapped*
