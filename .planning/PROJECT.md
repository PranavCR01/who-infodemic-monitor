# WHO Infodemic Monitor

## What This Is

A production-grade health misinformation detection platform for short-form video (TikTok / Reels / Shorts), built for WHO representatives and public-health stakeholders. The system ingests videos, extracts multimodal signals (speech transcript + on-screen text), classifies content using LLMs, and returns structured verdicts with evidence and explanations.

## Core Value

A public-health analyst can upload a video and receive a reliable, explainable misinformation verdict — with evidence — in under 60 seconds.

## Requirements

### Validated

- ✓ Docker Compose infrastructure (api, worker, db, redis) — Milestone 1
- ✓ FastAPI backend with /health endpoint — Milestone 1
- ✓ Celery + Redis async job execution verified — Milestone 1
- ✓ POST /videos/upload — file saved, Video DB row created — Milestone 2
- ✓ POST /jobs/create — Job row created, Celery task enqueued — Milestone 2
- ✓ GET /jobs/{job_id} — status polling (PENDING → STARTED → SUCCESS) — Milestone 2
- ✓ infodemic_storage Docker volume shared between api and worker — Milestone 2

### Active

#### Extraction
- [ ] Transcription module: audio → text via faster-whisper (local) or OpenAI Whisper API, switchable via config
- [ ] OCR module: video frames → on-screen text via EasyOCR, with confidence filtering and frame sampling
- [ ] Multimodal fusion module: combine transcript + OCR into structured input for inference

#### Inference
- [ ] Inference module with pluggable LLM providers: OpenAI (GPT-4o), Anthropic Claude, Ollama (local)
- [ ] Structured output: label (MISINFO / NO_MISINFO / DEBUNKING / CANNOT_RECOGNIZE), confidence, explanation, evidence snippets
- [ ] Provider selection via environment config (no hardcoded provider)

#### Persistence
- [ ] Result DB model: job_id, label, confidence, explanation, evidence_snippets, created_at
- [ ] Results persisted to DB after successful inference
- [ ] GET /jobs/{job_id} response includes result fields when job is SUCCESS

#### Pipeline integration
- [ ] process_video_task wired end-to-end: video file → transcription → OCR → fusion → inference → persist result

#### Evaluation
- [ ] pytest unit tests for each module (transcription, OCR, multimodal, inference) with mocked dependencies
- [ ] Integration test: upload video → create job → poll until SUCCESS → assert result shape
- [ ] Eval benchmarking scaffold: script to run pipeline on a folder of videos and output CSV with labels + latency

### Out of Scope

- Frontend (React/Next.js) — separate milestone
- Alembic migrations — currently using create_all on startup, acceptable for now
- Video segment-level classification — video-level only for v1
- Real-time streaming results — polling is sufficient for v1
- Multi-tenant auth / API keys — single-user system for now
- User management — no login/accounts in this milestone

## Context

This codebase is a brownfield production rewrite of a Streamlit research prototype (`D:\Python files\tiktok-2026-01-29`). The old repo contains working but non-modular pipeline code with Streamlit dependencies embedded in core logic. The port must:
- Remove all Streamlit imports from pipeline code
- Separate concerns cleanly (extractor / provider / pipeline layers)
- Use dependency injection for LLM providers and transcription backends
- Follow production patterns: logging, error handling, typed interfaces

Label schema is canonical and must not change: `MISINFO | NO_MISINFO | DEBUNKING | CANNOT_RECOGNIZE`

## Constraints

- **Tech stack**: Python 3.12, FastAPI, Celery, SQLAlchemy 2.0 (sync), psycopg3, Redis, Docker
- **ORM**: Sync SQLAlchemy only — Celery workers are sync, async ORM causes issues
- **Secrets**: All credentials via environment variables, never hardcoded
- **Deployment**: Docker-first — all production code must run inside containers
- **Old repo**: Source reference only — do not import from it directly
- **No Streamlit**: Zero Streamlit imports in backend/ or any production module

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Sync SQLAlchemy | Celery task compatibility — async ORM breaks in sync worker context | — Pending |
| create_all on startup | Defer Alembic until schema stabilizes | — Pending |
| Docker volume for storage | Share video files between api and worker containers | ✓ Good |
| Pluggable LLM providers | Support OpenAI, Claude, Ollama without changing pipeline code | — Pending |
| faster-whisper as default | CTranslate2-based, 4x faster than openai-whisper, same accuracy | — Pending |

---
*Last updated: 2026-03-09 after project initialization (Milestones 1 & 2 complete)*
