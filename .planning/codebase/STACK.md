# Technology Stack

**Analysis Date:** 2026-03-09

## Languages

**Primary:**
- Python 3.11 — all backend logic, API, workers, models

**Secondary:**
- None currently active (frontend is planned but not yet implemented)

## Runtime

**Environment:**
- Python 3.11 (pinned in `backend/Dockerfile`: `FROM python:3.11-slim`)
- Containerized via Docker; development runtime is WSL2 on Windows

**Package Manager:**
- pip (standard Python installer)
- Lockfile: not present — dependencies declared in `backend/pyproject.toml` with `>=` version constraints only

## Frameworks

**Core:**
- FastAPI `>=0.110` — HTTP API layer; handles request routing, dependency injection, multipart upload
- Uvicorn `>=0.27` (with `[standard]` extras) — ASGI server running FastAPI in container; launched via `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`
- Celery `>=5.3` — distributed async task queue; runs video processing jobs
- SQLAlchemy `>=2.0` — ORM for PostgreSQL; **sync mode chosen explicitly** for Celery worker DB access compatibility

**Configuration:**
- Pydantic `>=2.6` — request/response validation and data models
- pydantic-settings `>=2.2` — settings management via `BaseSettings` in `backend/app/core/config.py`

**Build/Dev:**
- Docker — containerization of all services
- Docker Compose — local multi-service orchestration (defined in `infra/docker-compose.yml`)

## Key Dependencies

**Critical:**
- `psycopg[binary] >=3.1` — psycopg3 driver for PostgreSQL; provides `postgresql+psycopg://` dialect for SQLAlchemy; the `[binary]` extra avoids C compilation
- `redis >=5.0` — Python Redis client; used by Celery for broker and result backend connections
- `python-multipart >=0.0.9` — required by FastAPI to parse `multipart/form-data` (video file uploads)
- `aiofiles >=23.0` — async file I/O; present as dependency though upload currently uses synchronous file writing

**Infrastructure:**
- PostgreSQL 16 (Docker image `postgres:16`) — primary relational database
- Redis 7 (Docker image `redis:7`) — message broker (DB 0) and Celery result backend (DB 1)

**Planned (not yet integrated):**
- Whisper / faster-whisper — audio transcription (to be ported from old repo)
- EasyOCR — on-screen text extraction from video frames (to be ported from old repo)
- OpenAI / Azure OpenAI / Ollama — LLM inference providers (to be ported from old repo)
- ffmpeg — video processing system dependency; already installed in `backend/Dockerfile` via `apt-get install ffmpeg`
- OpenCV (`libgl1`, `libglib2.0-0`) — already installed in `backend/Dockerfile` as system dependencies for future OCR use

## Configuration

**Environment:**
- All settings loaded from `.env` file at repo root (committed to `.gitignore`, not tracked)
- Template provided at `.env.example`
- Settings class: `backend/app/core/config.py` — `Settings(BaseSettings)` with `env_file = ".env"` and `extra = "ignore"`
- Key config values:
  - `DATABASE_URL` — defaults to `postgresql+psycopg://postgres:postgres@db:5432/infodemic`
  - `CELERY_BROKER_URL` — defaults to `redis://redis:6379/0`
  - `CELERY_RESULT_BACKEND` — defaults to `redis://redis:6379/1`
  - `LOCAL_STORAGE_ROOT` — defaults to `/app/storage` (mounted Docker volume)
  - `APP_ENV` — `local` in `.env.example`
  - `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` — Postgres container credentials

**Build:**
- `backend/Dockerfile` — single-stage build: `python:3.11-slim`, installs system deps, installs Python package via `pip install .`, copies source
- `infra/docker-compose.yml` — orchestrates `db`, `redis`, `api`, and `worker` services; mounts `infodemic_storage` volume shared between `api` and `worker` containers

## Platform Requirements

**Development:**
- Docker Desktop (tested on WSL2/Windows)
- `.env` file at repo root populated from `.env.example`
- No local Python install required — all services run containerized

**Production:**
- Deployment target not yet defined
- Storage abstraction is designed to migrate from local volume (`LOCAL_STORAGE_ROOT`) to S3 in future
- No CI/CD pipeline currently configured (`.github/workflows/` directory exists but is empty)

---

*Stack analysis: 2026-03-09*
