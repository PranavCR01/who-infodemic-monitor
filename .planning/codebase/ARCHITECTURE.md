# Architecture

**Analysis Date:** 2026-03-09

## Pattern Overview

**Overall:** Async job-processing backend with layered REST API

**Key Characteristics:**
- HTTP API layer (FastAPI) receives requests and delegates work to an async queue
- Celery workers consume jobs from Redis and execute the processing pipeline
- PostgreSQL provides persistent state for videos, jobs, and (future) results
- The API and worker share the same codebase and DB models but run in separate containers
- Sync SQLAlchemy ORM (not async) is used throughout — chosen intentionally for Celery compatibility

## Layers

**API Layer:**
- Purpose: Accept HTTP requests, validate inputs, write initial DB records, dispatch Celery tasks
- Location: `backend/app/api/routers/`
- Contains: FastAPI `APIRouter` modules (`videos.py`, `jobs.py`)
- Depends on: DB models, `get_db` session dependency, Celery task handle
- Used by: External clients (curl, future frontend)

**Worker Layer:**
- Purpose: Execute long-running pipeline jobs asynchronously (transcription, OCR, inference)
- Location: `backend/app/worker/`
- Contains: `celery_app.py` (Celery init), `tasks.py` (task definitions)
- Depends on: DB models, `SessionLocal` (creates its own sessions, no FastAPI dependency injection)
- Used by: Celery broker (Redis)

**Domain / Core Layer:**
- Purpose: House extraction modules (transcription, OCR), inference logic, schemas, and storage abstractions
- Location: `backend/app/core/`
- Contains: `config.py`, and stub subdirectories: `extraction/`, `extraction/ocr/`, `inference/`, `inference/providers/`, `pipeline/`, `schemas/`, `storage/`
- Depends on: Nothing (should remain dependency-free from API/worker internals)
- Used by: Worker tasks (once pipeline is wired in)

**Database Layer:**
- Purpose: ORM definitions and session management
- Location: `backend/app/db/`
- Contains: `base.py` (DeclarativeBase), `session.py` (engine + SessionLocal + get_db), `models/video.py`, `models/job.py`
- Depends on: `core/config.py` for `DATABASE_URL`
- Used by: API routers (via `get_db` dependency), Worker tasks (via direct `SessionLocal`)

**Configuration Layer:**
- Purpose: Single source of truth for runtime settings
- Location: `backend/app/core/config.py`
- Contains: `Settings` class (pydantic-settings), exported `settings` singleton
- Depends on: Environment variables / `.env` file
- Used by: All layers

**Infrastructure Layer:**
- Purpose: Container orchestration and runtime environment
- Location: `infra/docker-compose.yml`, `backend/Dockerfile`
- Contains: 4 services: `db` (Postgres 16), `redis` (Redis 7), `api` (FastAPI/uvicorn), `worker` (Celery)
- Shared volume: `infodemic_storage` mounted at `/app/storage` in both `api` and `worker` containers

## Data Flow

**Video Upload Flow:**
1. Client sends `POST /videos/upload` with multipart file
2. `backend/app/api/routers/videos.py` reads file bytes, writes to `LOCAL_STORAGE_ROOT` (default: `/app/storage`)
3. A `Video` ORM record is created and committed to PostgreSQL
4. Response returns `video_id`, `filename`, `file_size`

**Job Processing Flow:**
1. Client sends `POST /jobs/create` with `{ "video_id": "..." }`
2. `backend/app/api/routers/jobs.py` validates video exists, creates `Job` record with `status=PENDING`
3. `process_video_task.delay(job_id)` is called — Celery enqueues task to Redis
4. Worker container picks up task from Redis queue
5. `backend/app/worker/tasks.py::process_video_task` updates `Job.status` → `STARTED`
6. Pipeline stub executes (transcription → OCR → inference — to be wired in)
7. `Job.status` updated to `SUCCESS` (or `FAILED` on exception)

**Status Polling Flow:**
1. Client sends `GET /jobs/{job_id}`
2. `backend/app/api/routers/jobs.py` queries `Job` by ID
3. Returns current `status`, `celery_task_id`, timestamps

**State Management:**
- All persistent state lives in PostgreSQL via SQLAlchemy ORM
- No in-memory state shared between API and worker — both read/write the same DB
- Celery result backend (Redis, db index 1) is configured but not yet used for result retrieval

## Key Abstractions

**Video:**
- Purpose: Represents an uploaded video file; links a UUID to a filesystem path
- Examples: `backend/app/db/models/video.py`
- Pattern: SQLAlchemy `Mapped` columns with `mapped_column()`, UUID primary key as VARCHAR string

**Job:**
- Purpose: Tracks async processing lifecycle for a single video
- Examples: `backend/app/db/models/job.py`
- Pattern: FK to `videos.id`, `JobStatus` enum (PENDING / STARTED / SUCCESS / FAILED), `updated_at` with `onupdate` trigger

**JobStatus:**
- Purpose: Canonical state machine enum for job lifecycle
- Examples: `backend/app/db/models/job.py` — `class JobStatus(str, enum.Enum)`
- Pattern: String enum, stored in Postgres as SAEnum column

**Settings:**
- Purpose: Type-safe, environment-variable-backed configuration singleton
- Examples: `backend/app/core/config.py`
- Pattern: `pydantic_settings.BaseSettings`, instantiated at module load as `settings`

**Celery App:**
- Purpose: Configured Celery instance shared by worker and API task dispatch
- Examples: `backend/app/worker/celery_app.py`
- Pattern: `autodiscover_tasks(["app.worker"])` with `task_track_started=True`

## Entry Points

**FastAPI Application:**
- Location: `backend/app/main.py`
- Triggers: uvicorn at container startup — `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`
- Responsibilities: Create FastAPI instance, register routers, run `Base.metadata.create_all()` on startup

**Celery Worker:**
- Location: `backend/app/worker/celery_app.py` (app), `backend/app/worker/tasks.py` (task definitions)
- Triggers: `celery -A app.worker.celery_app.celery_app worker --loglevel=INFO`
- Responsibilities: Listen to Redis broker, pick up `process_video_task` jobs, update Job status in DB

**Health Check:**
- Location: `backend/app/main.py` — `GET /health`
- Triggers: Container health probes, uptime monitors
- Responsibilities: Return `{"status": "ok"}`

## Error Handling

**Strategy:** Exception-based with Celery task retry boundary

**Patterns:**
- FastAPI routers raise `HTTPException` (404) for missing resources (Video, Job)
- Worker tasks wrap pipeline execution in `try/except`; on exception: sets `Job.status = FAILED`, re-raises the exception to Celery
- DB sessions in worker are manually managed (`SessionLocal()` / `db.close()` in `finally`)
- DB sessions in API are managed by `get_db()` generator dependency (auto-closed via `finally`)

## Cross-Cutting Concerns

**Logging:** Default Celery worker logging (`--loglevel=INFO`); no structured logging configured in API yet

**Validation:** Pydantic v2 models used for request bodies (`CreateJobRequest` in `jobs.py`); file uploads validated via FastAPI `UploadFile`

**Authentication:** Not implemented — all endpoints are unauthenticated

**Migrations:** Tables created via `Base.metadata.create_all(bind=engine)` on API startup; Alembic directory (`backend/app/db/migrations/`) exists but is empty — no migration scripts yet

**Storage:** Local filesystem at `LOCAL_STORAGE_ROOT` (`/app/storage`); shared Docker volume `infodemic_storage` bridges api and worker containers; designed for future S3 abstraction via `backend/app/core/storage/` (stub only)

---

*Architecture analysis: 2026-03-09*
