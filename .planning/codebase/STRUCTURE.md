# Codebase Structure

**Analysis Date:** 2026-03-09

## Directory Layout

```
who-infodemic-monitor/
├── backend/                    # Python backend (API + worker)
│   ├── Dockerfile              # Shared image for api and worker containers
│   ├── pyproject.toml          # Python dependencies
│   ├── storage/                # Local dev storage (not used in container — volume-mounted)
│   │   ├── videos/             # Uploaded video files
│   │   ├── artifacts/          # Pipeline output artifacts (future)
│   │   └── temp/               # Temporary processing files (future)
│   └── app/                    # Python package root
│       ├── __init__.py
│       ├── main.py             # FastAPI entrypoint
│       ├── api/                # HTTP layer
│       │   ├── __init__.py
│       │   └── routers/        # One file per resource group
│       │       ├── __init__.py
│       │       ├── videos.py   # POST /videos/upload
│       │       └── jobs.py     # POST /jobs/create, GET /jobs/{job_id}
│       ├── core/               # Domain logic and configuration
│       │   ├── __init__.py
│       │   ├── config.py       # Settings singleton (pydantic-settings)
│       │   ├── extraction/     # Signal extraction modules (stubs — to be populated)
│       │   │   ├── __init__.py
│       │   │   └── ocr/        # OCR extraction (stub)
│       │   │       └── __init__.py
│       │   ├── inference/      # LLM classification (stub)
│       │   │   ├── __init__.py
│       │   │   └── providers/  # Provider-specific clients (OpenAI, Azure, Ollama)
│       │   │       └── __init__.py
│       │   ├── pipeline/       # Orchestration: transcription → OCR → inference (stub)
│       │   │   └── __init__.py
│       │   ├── schemas/        # Shared Pydantic schemas (stub)
│       │   │   └── __init__.py
│       │   └── storage/        # Storage abstraction for future S3 (stub)
│       │       └── __init__.py
│       ├── db/                 # Database layer
│       │   ├── __init__.py
│       │   ├── base.py         # SQLAlchemy DeclarativeBase
│       │   ├── session.py      # Engine, SessionLocal, get_db()
│       │   ├── migrations/     # Alembic migrations (empty — not yet initialized)
│       │   └── models/         # ORM models
│       │       ├── __init__.py
│       │       ├── video.py    # Video model
│       │       └── job.py      # Job model + JobStatus enum
│       ├── services/           # Business logic services (empty stub)
│       │   └── __init__.py
│       ├── tests/              # Test suite (empty stub)
│       │   └── __init__.py
│       └── worker/             # Celery async task layer
│           ├── celery_app.py   # Celery instance configuration
│           └── tasks.py        # Task definitions (ping_task, process_video_task)
├── infra/
│   └── docker-compose.yml      # 4-service local orchestration
├── frontend/                   # Planned React/Next.js frontend (empty)
├── .env.example                # Environment variable template
├── .env                        # Local secrets (gitignored)
├── .gitignore
├── .github/
│   └── workflows/              # CI/CD (empty — not yet configured)
├── .planning/
│   └── codebase/               # GSD codebase analysis documents
└── CLAUDE.md                   # Project instructions and architecture notes
```

## Directory Purposes

**`backend/app/api/routers/`:**
- Purpose: HTTP endpoint definitions, one file per resource group
- Contains: FastAPI `APIRouter` instances with route handlers
- Key files: `backend/app/api/routers/videos.py`, `backend/app/api/routers/jobs.py`

**`backend/app/core/`:**
- Purpose: All domain logic isolated from HTTP and worker infrastructure
- Contains: Configuration, extraction modules, inference providers, schemas, storage abstractions
- Key files: `backend/app/core/config.py`
- Note: Subdirectories `extraction/`, `inference/`, `pipeline/`, `schemas/`, `storage/` are stubs created for future population

**`backend/app/db/`:**
- Purpose: Database access layer — ORM models, session management, migrations
- Contains: Base class, engine setup, model definitions
- Key files: `backend/app/db/base.py`, `backend/app/db/session.py`, `backend/app/db/models/video.py`, `backend/app/db/models/job.py`

**`backend/app/worker/`:**
- Purpose: Async task execution outside the HTTP request cycle
- Contains: Celery app configuration and task function definitions
- Key files: `backend/app/worker/celery_app.py`, `backend/app/worker/tasks.py`

**`backend/app/services/`:**
- Purpose: Business logic layer between API routers and DB/core (empty — not yet used)
- Note: Intended to hold service classes that routers delegate to, keeping routers thin

**`backend/app/tests/`:**
- Purpose: Test suite (empty — not yet implemented)

**`backend/storage/`:**
- Purpose: Local development file storage; in Docker the equivalent path is volume-mounted
- Contains: `videos/` (uploaded files), `artifacts/` (pipeline outputs), `temp/` (scratch)
- Generated: Files written at runtime
- Committed: No (`.gitignore` should exclude contents)

**`infra/`:**
- Purpose: Infrastructure configuration for local development
- Contains: `docker-compose.yml` defining 4 services (db, redis, api, worker)

**`frontend/`:**
- Purpose: Planned React/Next.js dashboard for WHO end-users (empty)

## Key File Locations

**Entry Points:**
- `backend/app/main.py`: FastAPI application factory, router registration, DB table creation on startup
- `backend/app/worker/celery_app.py`: Celery application instance
- `backend/app/worker/tasks.py`: All Celery task definitions

**Configuration:**
- `backend/app/core/config.py`: `Settings` class and `settings` singleton — import from here everywhere
- `.env.example`: Template showing all required environment variables
- `infra/docker-compose.yml`: Service topology and volume definitions
- `backend/Dockerfile`: Container build instructions

**Core Logic:**
- `backend/app/worker/tasks.py`: `process_video_task` — the pipeline integration point
- `backend/app/db/models/video.py`: `Video` ORM model
- `backend/app/db/models/job.py`: `Job` ORM model and `JobStatus` enum

**API Endpoints:**
- `backend/app/api/routers/videos.py`: `POST /videos/upload`
- `backend/app/api/routers/jobs.py`: `POST /jobs/create`, `GET /jobs/{job_id}`

**Database:**
- `backend/app/db/base.py`: Import `Base` here when defining new ORM models
- `backend/app/db/session.py`: Import `get_db` for FastAPI routes; import `SessionLocal` for Celery tasks

**Testing:**
- `backend/app/tests/`: Empty — test files go here

## Naming Conventions

**Files:**
- Snake case: `celery_app.py`, `text_extractor.py`, `api_helpers.py`
- Resource-named routers: `videos.py`, `jobs.py` (matches URL prefix)
- Model files named after their table's singular entity: `video.py`, `job.py`

**Directories:**
- Snake case: `routers/`, `models/`, `extraction/`, `celery_app/`
- Noun plurals for collections: `routers/`, `models/`, `providers/`
- Noun singulars for logical groupings: `core/`, `worker/`, `storage/`

**Python Classes:**
- PascalCase: `Video`, `Job`, `JobStatus`, `Settings`, `VideoTextExtractor`

**Python Functions/Variables:**
- Snake case: `process_video_task`, `get_db`, `upload_video`, `create_job`

**Environment Variables:**
- SCREAMING_SNAKE_CASE: `DATABASE_URL`, `CELERY_BROKER_URL`, `LOCAL_STORAGE_ROOT`

## Where to Add New Code

**New API endpoint group (e.g., results):**
- Implementation: `backend/app/api/routers/results.py`
- Register in: `backend/app/main.py` via `app.include_router(results.router)`

**New ORM model:**
- Implementation: `backend/app/db/models/{entity}.py` — extend `Base` from `backend/app/db/base.py`
- Register in: `backend/app/main.py` — add `import app.db.models.{entity}  # noqa: F401`

**New Celery task:**
- Implementation: `backend/app/worker/tasks.py` — add `@celery_app.task(name="...")` decorated function

**Extraction module (transcription, OCR):**
- Transcription: `backend/app/core/extraction/transcription.py`
- OCR: `backend/app/core/extraction/ocr/text_extractor.py`
- Wire into: `backend/app/worker/tasks.py::process_video_task`

**Inference module:**
- Base classifier: `backend/app/core/inference/classifier.py`
- Provider clients: `backend/app/core/inference/providers/{provider}.py` (e.g., `openai.py`, `azure.py`, `ollama.py`)

**Pipeline orchestrator:**
- Implementation: `backend/app/core/pipeline/pipeline.py`
- Called from: `backend/app/worker/tasks.py::process_video_task`

**Business logic service:**
- Implementation: `backend/app/services/{resource}_service.py`
- Called from: API routers (keep routers thin)

**Shared Pydantic schemas:**
- Implementation: `backend/app/core/schemas/{resource}.py`

**Storage abstraction:**
- Implementation: `backend/app/core/storage/storage.py` (local + future S3)

**Tests:**
- Location: `backend/app/tests/`
- Naming: `test_{module}.py` (e.g., `test_videos.py`, `test_jobs.py`)

## Special Directories

**`backend/app/db/migrations/`:**
- Purpose: Alembic migration scripts (not yet initialized)
- Generated: Yes (by Alembic `alembic revision` commands)
- Committed: Yes (migration scripts are versioned)
- Current state: Empty `__init__.py` only — `alembic init` not yet run

**`backend/storage/`:**
- Purpose: Local development copy of the shared video storage volume
- Generated: Yes (runtime writes)
- Committed: No (gitignored contents; directory itself may be committed as placeholder)

**`.planning/codebase/`:**
- Purpose: GSD analysis documents consumed by planning and execution commands
- Generated: Yes (by `/gsd:map-codebase`)
- Committed: Yes

**`backend/app/core/extraction/ocr/`:**
- Purpose: Reserved for `VideoTextExtractor` ported from old repo's `pages/processes/ocr/text_extractor.py`
- Generated: No
- Committed: Yes (currently stub)

**`backend/app/core/inference/providers/`:**
- Purpose: Reserved for per-provider LLM clients (OpenAI, Azure, Ollama)
- Generated: No
- Committed: Yes (currently stub)

---

*Structure analysis: 2026-03-09*
