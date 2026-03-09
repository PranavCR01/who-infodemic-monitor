# Roadmap: WHO Infodemic Monitor — Milestone 3 (ML Pipeline)

## Overview

Milestones 1 and 2 delivered a verified infrastructure stack: FastAPI, Celery, PostgreSQL, Redis, Docker, upload flow, job creation, and status polling — all working end-to-end. This milestone ports the ML pipeline from the Streamlit research prototype into the production backend. Five phases build in strict dependency order: shared data contracts first, extraction modules second, inference providers third, pipeline wiring fourth, and evaluation last. When complete, a public-health analyst can upload a video and receive a structured misinformation verdict — label, confidence, explanation, and evidence — via the existing job polling API.

## Milestones

- [x] **Milestone 1** — Infrastructure (Docker, FastAPI, Celery, Redis, Postgres) — complete
- [x] **Milestone 2** — Upload + Job Flow (upload, job creation, status polling) — complete
- [ ] **Milestone 3** — ML Pipeline (Phases 1-5 below)

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Schemas and Infrastructure** - Add ML dependencies, extend config, define Pydantic schemas and Result ORM model
- [ ] **Phase 2: Extraction Modules** - Port OCR, transcription, and multimodal fusion modules from prototype; bake models into Dockerfile
- [ ] **Phase 3: Inference Providers** - Implement pluggable LLM provider layer (OpenAI, Anthropic, Ollama) with Protocol-based interface and provider factory
- [ ] **Phase 4: Pipeline Wiring and Persistence** - Wire run_pipeline into Celery task, persist Result to DB, extend jobs API response
- [ ] **Phase 5: Evaluation** - Unit tests for each module, integration test for full pipeline, benchmarking script

## Phase Details

### Phase 1: Schemas and Infrastructure
**Goal**: All foundational contracts and configuration exist so every downstream module has a stable interface to code against
**Depends on**: Nothing (builds on completed Milestone 2 infrastructure)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, SCHEMA-01, SCHEMA-02, SCHEMA-03
**Success Criteria** (what must be TRUE):
  1. `docker compose build` succeeds with all ML system deps (`libgl1`, `libglib2.0-0`, `ffmpeg`) installed and faster-whisper + EasyOCR model weights baked into the image
  2. `FusionResult` and `ClassificationResult` Pydantic schemas importable from `backend/app/core/schemas/pipeline.py` with all required fields present and validated
  3. `Result` ORM model exists in `backend/app/db/models/result.py`, is registered with `Base`, and `docker compose up` creates the `results` table without error
  4. All new environment variables (`WHISPER_PROVIDER`, `WHISPER_MODEL`, `INFERENCE_PROVIDER`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`) are defined in `config.py` and documented in `.env.example`
**Plans**: TBD

### Phase 2: Extraction Modules
**Goal**: Audio transcription, on-screen OCR text extraction, and multimodal fusion all operate as clean, independently callable Python modules with no Streamlit dependencies
**Depends on**: Phase 1
**Requirements**: OCR-01, OCR-02, TRANS-01, TRANS-02, TRANS-03, TRANS-04, FUSION-01
**Success Criteria** (what must be TRUE):
  1. `VideoTextExtractor` in `backend/app/core/extraction/ocr.py` accepts a video file path and returns typed OCR results; `grep -r "streamlit" backend/` finds zero matches
  2. `TranscriptionService` in `backend/app/core/extraction/transcription.py` selects the correct backend via `WHISPER_PROVIDER` env var; `FasterWhisperBackend` uses a module-level singleton and does not reload the model per call
  3. `OpenAIWhisperBackend.transcribe()` raises `FileTooLargeError` when given a file over 25MB
  4. `MultimodalFusion.fuse()` returns a `FusionResult` with non-empty `transcript`, `visual_text`, and `combined_content` fields; raises `ContentTooLongError` when combined token count exceeds the provider limit
**Plans**: TBD

### Phase 3: Inference Providers
**Goal**: All three LLM providers (OpenAI, Anthropic, Ollama) implement the `InferenceProvider` Protocol and return valid `ClassificationResult` objects; provider selection is controlled entirely by environment variable
**Depends on**: Phase 1
**Requirements**: INFER-01, INFER-02, INFER-03, INFER-04, INFER-05, INFER-06
**Success Criteria** (what must be TRUE):
  1. `InferenceProvider` Protocol is defined in `backend/app/core/inference/classifier.py`; `get_provider(settings)` factory raises a loud error at startup if `INFERENCE_PROVIDER` is set to an unrecognised value
  2. `OpenAIProvider.classify()` uses `response_format=json_object` (or `json_schema`) to produce deterministic structured output without regex parsing
  3. `AnthropicProvider.classify()` uses `tool_choice` for deterministic structured JSON output
  4. `OllamaProvider.classify()` returns `CANNOT_RECOGNIZE` label (never crashes) when LLM output is malformed (truncated, trailing commas, multiple JSON objects)
  5. Any LLM output string not in `{MISINFO, NO_MISINFO, DEBUNKING, CANNOT_RECOGNIZE}` is normalized to `CANNOT_RECOGNIZE` across all three providers
**Plans**: TBD

### Phase 4: Pipeline Wiring and Persistence
**Goal**: A submitted video job runs the full pipeline end-to-end inside the Celery worker and the result is retrievable via the existing GET /jobs/{job_id} API endpoint
**Depends on**: Phase 2, Phase 3
**Requirements**: PIPE-01, PIPE-02, PIPE-03
**Success Criteria** (what must be TRUE):
  1. `run_pipeline(video_path, settings)` in `backend/app/core/pipeline.py` orchestrates transcription → OCR → fusion → inference and returns a `ClassificationResult`; the function accepts no DB session parameter
  2. After a job completes, a `Result` row exists in the database with non-null `label`, `confidence`, `explanation`, and `evidence_snippets` fields linked to the correct `job_id`
  3. `GET /jobs/{job_id}` returns `label`, `confidence`, `explanation`, `evidence_snippets`, `provider`, `model_used`, and `latency_ms` in the response body when `status == SUCCESS`
**Plans**: TBD

### Phase 5: Evaluation
**Goal**: Every module has automated test coverage; the full pipeline can be exercised end-to-end without manual curl commands; and bulk evaluation results can be captured in a CSV
**Depends on**: Phase 4
**Requirements**: EVAL-01, EVAL-02, EVAL-03, EVAL-04, EVAL-05
**Success Criteria** (what must be TRUE):
  1. `pytest tests/unit/` passes with mocked `cv2.VideoCapture` frames (OCR), mocked transcription backends, and mocked provider API responses — no real video files or API keys required
  2. Inference provider unit tests cover label normalization for unrecognised strings, JSON parse edge cases (truncated output, trailing commas), and `CANNOT_RECOGNIZE` fallback behavior
  3. `pytest tests/integration/` passes using a real short test video uploaded via `POST /videos/upload`, job created via `POST /jobs/create`, polled until `SUCCESS`, and asserts `label`, `confidence`, and `explanation` fields are present in the response
  4. `python scripts/eval_pipeline.py --input-dir <folder>` runs the pipeline on each video in the folder and writes a CSV with `video_path`, `label`, `confidence`, `latency_ms`, and `provider` columns
**Plans**: TBD

## Progress

**Execution Order:** 1 → 2 → 3 → 4 → 5
(Phases 2 and 3 have no dependency on each other and can be planned in any order)

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Schemas and Infrastructure | 0/TBD | Not started | - |
| 2. Extraction Modules | 0/TBD | Not started | - |
| 3. Inference Providers | 0/TBD | Not started | - |
| 4. Pipeline Wiring and Persistence | 0/TBD | Not started | - |
| 5. Evaluation | 0/TBD | Not started | - |
