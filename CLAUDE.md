\# CLAUDE.md



\## Project Overview



This repository is the \*\*production-system version\*\* of a research project focused on \*\*health misinformation detection in short-form video\*\* (TikTok / Reels / Shorts). The project was initially developed in the context of \*\*AI Tools for Managing Infodemics\*\*, with anticipated use by \*\*WHO representatives and public-health stakeholders\*\*.



The original system began as a \*\*research/demo pipeline\*\* using \*\*Streamlit\*\* for the interface and a combination of:



\- Whisper / faster-whisper for transcription

\- EasyOCR for on-screen text extraction

\- LLM-based classification (OpenAI, Azure, Ollama/local)

\- CSV exports and experiment folders for reproducibility



This repository transforms that research prototype into a \*\*scalable, modular, production-grade application\*\*.



Goals:



\- Real backend service

\- Async job processing

\- Database-backed state

\- Clean APIs

\- Eventually a polished frontend for non-technical users



The end goal is a system that is both:



1\. Useful to \*\*real public-health users\*\*

2\. Architecturally strong enough to be \*\*impressive for software / AI engineering roles\*\*



---



\# Core Mission



Build a system that can:



1\. Ingest short-form health-related videos

2\. Extract multimodal signals

&nbsp;  - spoken transcript

&nbsp;  - on-screen OCR text

3\. Run misinformation classification

4\. Return structured results

&nbsp;  - label

&nbsp;  - confidence

&nbsp;  - explanation

&nbsp;  - evidence snippets

5\. Support human review workflows

6\. Scale beyond a prototype interface



---



\# Label Schema



The classification system uses four labels:



\- `MISINFO`

\- `NO\_MISINFO`

\- `DEBUNKING`

\- `CANNOT\_RECOGNIZE`



These labels are the canonical output format unless explicitly changed later.



---



\# Two-Repository Strategy



There are effectively \*\*two related repositories\*\*.



\## 1. Old Repository — Research / Prototype



The original repo contains:



\- Streamlit UI

\- OCR / transcription modules

\- multimodal extraction

\- experimentation scripts

\- CSV exports

\- evaluation scripts



Purpose:



\- prototyping

\- manual analysis

\- experimentation

\- research benchmarking



However, it is \*\*not suitable for production\*\*, because:



\- UI and logic are tightly coupled

\- Streamlit code appears in core modules

\- no job persistence

\- no async processing architecture

\- weak deployment structure



---



\## 2. New Repository — Production Platform



This repository contains:



\- FastAPI backend

\- Celery worker system

\- PostgreSQL database

\- Redis queue

\- modular architecture

\- Docker infrastructure



This repo should remain:



\- modular

\- clean

\- production-oriented

\- easy to explain to collaborators and recruiters



---



\# Old Repository Architecture



\## Core Pipeline



The research pipeline performs:



1\. Video input

2\. Audio transcription

3\. OCR text extraction

4\. Multimodal fusion

5\. LLM classification

6\. Result explanation

7\. Export / visualization



---



\# Important Files in the Old Repo



\## `pages/processes/ocr/text\_extractor.py`



\### Purpose

Extract on-screen text from video frames.



\### Key functionality



\- Initializes EasyOCR reader

\- Samples video frames

\- Extracts text from frames

\- Filters by confidence



\### Main class



`VideoTextExtractor`



\### Important methods



\- `\_get\_reader()`

\- `extract\_frames(video\_path, fps)`

\- `extract\_text\_from\_frame(frame)`

\- `extract\_text\_from\_video(...)`



---



\## `pages/processes/transcription.py`



\### Purpose



Handles audio transcription.



\### Features



\- OpenAI Whisper transcription

\- faster-whisper local transcription

\- supports Streamlit file uploads

\- supports direct file paths

\- optional video splitting for long files



\### Important functions



\- `\_transcribe\_openai()`

\- `\_transcribe\_local\_faster\_whisper()`

\- `transcribe()`

\- `transcribe2()`

\- `split\_video()`



\### Note



This file currently includes Streamlit logic and must be refactored for production.



---



\## `pages/processes/multimodal.py`



\### Purpose



Combine transcript and OCR signals.



\### Outputs



\- audio transcript

\- visual text

\- unique visual text

\- frame detections

\- combined multimodal content

\- metadata



\### Key class



`MultimodalExtractor`



---



\## `pages/processes/analysis.py`



\### Purpose



LLM-based misinformation classification.



\### Responsibilities



\- prompt construction

\- structured JSON extraction

\- model routing

\- error handling

\- token warnings



\### Supported providers



\- OpenAI

\- Azure OpenAI

\- Ollama (local models)



\### Key functions



\- `\_extract\_json\_block()`

\- `analyze()`

\- `analyze2()`

\- `analyze\_local\_mistral()`



---



\## `pages/processes/api\_helpers.py`



\### Purpose



Provider configuration and validation.



\### Features



\- OpenAI API key validation

\- Azure credential validation

\- Ollama health checks

\- model token limit definitions



---



\## `pages/processes/utils.py`



\### Purpose



General helper functions.



Includes:



\- token counting

\- CSV export

\- Streamlit state helpers

\- keyword visualization



---



\## `pages/2\_Analysis.py`



\### Purpose



Main Streamlit UI.



Features:



\- provider selection

\- video upload

\- pipeline execution

\- result visualization

\- charts and metrics

\- CSV download



---



\## `scripts/run\_mistral.py`



Batch pipeline using local models.



Features:



\- YAML config

\- batch video processing

\- transcription + classification

\- CSV output



---



\## `scripts/run\_multimodal\_batch.py`



Batch multimodal processing pipeline.



Outputs include:



\- transcripts

\- OCR text

\- combined multimodal input

\- predicted labels

\- explanations

\- confidence scores



---



\## `scripts/analyze\_experiment.py`



Post-processing and experiment analysis.



Generates:



\- label distribution plots

\- confidence histograms

\- latency statistics

\- experiment README summaries



---



\# Known Limitations of the Old Repo



\- video-level classification only

\- limited visual reasoning beyond OCR

\- no calibrated confidence

\- no large benchmark evaluation

\- CPU performance constraints

\- weak deployment architecture



---



\# New Repository Architecture



This repo builds a \*\*production backend platform\*\*.



\## Structure

backend/
app/
api/
core/
db/
services/
worker/

infra/
docker-compose.yml

frontend/

.env.example
.gitignore



---

# Backend Components

## `backend/Dockerfile`

Defines backend container.

Responsibilities:

- Python runtime
- system dependencies (ffmpeg/OpenCV)
- install Python dependencies
- copy backend code

---

## `backend/pyproject.toml`

Python dependency configuration.

Includes:

- FastAPI
- Celery
- Redis
- Pydantic
- SQLAlchemy 2.0
- psycopg[binary] (psycopg3 driver for Postgres)
- aiofiles

---

## `backend/app/main.py`

FastAPI entrypoint.

Current functionality:

- create API instance
- expose `/health` endpoint
- register `/videos` and `/jobs` routers
- on startup: run `Base.metadata.create_all()` to create DB tables

---

## `backend/app/core/config.py`

Configuration management.

Provides:

- Celery broker URL
- Redis backend
- DATABASE_URL (postgresql+psycopg://postgres:postgres@db:5432/infodemic)
- LOCAL_STORAGE_ROOT (/app/storage — video upload dir inside container)
- environment variable loading via pydantic-settings

---

## `backend/app/worker/celery_app.py`

Celery initialization.

Responsibilities:

- connect to Redis broker
- configure task discovery
- manage async job execution

---

## `backend/app/worker/tasks.py`

Celery task definitions.

Currently includes:

- `ping_task()` for worker validation
- `process_video_task(job_id)` — updates Job status PENDING → STARTED → SUCCESS/FAILED
  - imports Video model to resolve FK at runtime
  - pipeline stub ready for transcription/OCR/inference integration

---

## `backend/app/db/base.py`

SQLAlchemy declarative base.

- `Base` class used by all ORM models

---

## `backend/app/db/session.py`

Database session management.

- sync SQLAlchemy engine (chosen for Celery compatibility)
- `SessionLocal` — session factory
- `get_db()` — FastAPI dependency for DB sessions

---

## `backend/app/db/models/video.py`

Video ORM model.

Fields: `id` (UUID str), `filename`, `file_path`, `file_size`, `created_at`

---

## `backend/app/db/models/job.py`

Job ORM model + `JobStatus` enum.

Fields: `id` (UUID str), `video_id` (FK → videos.id), `status`, `celery_task_id`, `created_at`, `updated_at`

Status values: `PENDING`, `STARTED`, `SUCCESS`, `FAILED`

---

## `backend/app/api/routers/videos.py`

Video upload endpoint.

- `POST /videos/upload` — accepts multipart file, saves to LOCAL_STORAGE_ROOT, creates Video DB row
- returns `video_id`, `filename`, `file_size`

---

## `backend/app/api/routers/jobs.py`

Job management endpoints.

- `POST /jobs/create` — validates video exists, creates Job row (PENDING), enqueues Celery task, returns job_id
- `GET /jobs/{job_id}` — returns current job status and metadata

---

## `infra/docker-compose.yml`

Local service orchestration.

Services:

- Postgres
- Redis
- FastAPI API
- Celery worker

Purpose:

- reproducible local infrastructure
- simplified onboarding

---

## `.env.example`

Template environment configuration.

Used to define required environment variables safely.

---

# Infrastructure Milestone Status

## Milestone 1 — Infrastructure (commit c1c0440)

- WSL2 Linux runtime
- Docker Desktop
- Docker container networking
- FastAPI backend container
- Postgres container
- Redis container
- Celery worker container
- asynchronous Celery task execution verified
- repository pushed to GitHub

## Milestone 2 — Upload + Job Flow (completed 2026-03-09)

- `POST /videos/upload` — file saved, Video row created in DB
- `POST /jobs/create` — Job row created, Celery task enqueued
- `GET /jobs/{job_id}` — status polling
- Worker processes task: PENDING → STARTED → SUCCESS
- End-to-end verified: ~380ms job execution latency
- `infodemic_storage` Docker volume shared between api and worker containers

---

# What Still Needs to Be Built

## Backend

1. ~~SQLAlchemy database models~~ ✓ done
2. ~~upload endpoints~~ ✓ done
3. ~~job creation + status endpoints~~ ✓ done
4. Alembic migrations (currently using create_all on startup)
5. Result model + persistence (label, confidence, explanation)
6. Port transcription module from old repo (remove Streamlit deps)
7. Port OCR module from old repo
8. Port inference/analysis module from old repo
9. Wire pipeline into process_video_task

---

## Frontend

Planned future stack:

- React / Next.js
- TypeScript
- interactive dashboard
- result review workflow

---

# WHO User Experience Goals

The final system should support:

- video upload
- clear job status
- readable explanations
- evidence visualization
- analyst review workflow
- exportable outputs

---

# Engineering Guidance

When working on this repository:

- keep architecture modular
- avoid Streamlit dependencies in core backend
- separate API / service / pipeline layers
- never hardcode secrets
- design storage abstraction for future S3
- maintain reproducibility

---

# Immediate Next Steps

Planned development sequence:

1. ~~Add SQLAlchemy models~~ ✓
2. ~~Implement upload endpoint~~ ✓
3. ~~Implement job creation API~~ ✓
4. ~~Integrate Celery job pipeline~~ ✓
5. Port transcription module (pages/processes/transcription.py → backend/app/core/extraction/transcription.py)
6. Port OCR module (pages/processes/ocr/text_extractor.py → backend/app/core/extraction/ocr.py)
7. Port inference module (pages/processes/analysis.py → backend/app/core/inference/)
8. Add Result DB model + persist outputs
9. Add Alembic migrations
10. Implement frontend interface

---

# Summary

This project began as a **Streamlit-based research pipeline** for detecting health misinformation in short-form video.

This repository rebuilds the system as a **production-grade backend platform** with modular architecture, async processing, and scalable infrastructure.

The long-term goal is to create a reliable system usable by **public-health stakeholders while demonstrating strong engineering architecture**.


