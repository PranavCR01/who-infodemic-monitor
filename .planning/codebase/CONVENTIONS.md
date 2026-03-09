# Coding Conventions

**Analysis Date:** 2026-03-09

## Naming Patterns

**Files:**
- Snake_case for all Python files: `config.py`, `celery_app.py`, `session.py`
- Module names match their primary content: `videos.py` contains the `videos` router, `jobs.py` contains the `jobs` router
- ORM model files named after their DB table (singular): `video.py`, `job.py`

**Classes:**
- PascalCase for all classes: `Video`, `Job`, `JobStatus`, `CreateJobRequest`, `Settings`
- ORM models use PascalCase singular nouns matching the domain concept: `Video`, `Job`
- Pydantic request schemas named as `{Action}{Resource}Request`: `CreateJobRequest`
- Enum classes inherit from both `str` and `enum.Enum`: `class JobStatus(str, enum.Enum)`

**Functions:**
- Snake_case for all functions and methods: `get_db()`, `upload_video()`, `create_job()`, `get_job()`
- FastAPI route handlers named descriptively after their action: `upload_video`, `create_job`, `get_job`
- Celery tasks named with `_task` suffix: `ping_task`, `process_video_task`
- Private/internal helpers prefixed with `_` (pattern from old repo, not yet present in new code)

**Variables:**
- Snake_case: `video_id`, `job_id`, `file_path`, `celery_task_id`
- Constants and settings use UPPER_SNAKE_CASE: `CELERY_BROKER_URL`, `DATABASE_URL`, `LOCAL_STORAGE_ROOT`

**Enum Values:**
- UPPER_SNAKE_CASE string literals: `PENDING`, `STARTED`, `SUCCESS`, `FAILED`

## Code Style

**Formatting:**
- No dedicated formatter config file detected (no `.prettierrc`, no `[tool.ruff]` or `[tool.black]` section in `pyproject.toml`)
- Code is consistent with PEP 8 style: 4-space indentation, blank lines between top-level definitions
- Line length appears to stay within ~100 characters

**Linting:**
- `# noqa: F401` used where intentional unused imports are required (side-effect imports for SQLAlchemy FK resolution)
- Comments always accompany `noqa` suppressions explaining why: `# noqa: F401 — needed for FK resolution`

## Import Organization

**Order (observed pattern):**
1. Standard library (`os`, `uuid`, `enum`, `datetime`)
2. Third-party frameworks (`fastapi`, `sqlalchemy`, `celery`, `pydantic`)
3. Internal application imports (`app.core.config`, `app.db.models.*`, `app.worker.tasks`)

**Internal import style:**
- Absolute imports only: `from app.db.models.video import Video` — never relative imports
- Specific symbol imports preferred: `from sqlalchemy.orm import Mapped, mapped_column` rather than `import sqlalchemy`

**Deferred imports:**
- Inside Celery tasks, model imports are deferred inside the function body to avoid circular imports at worker startup:
  ```python
  def process_video_task(self, job_id: str):
      from app.db.models.video import Video  # noqa: F401 — needed for FK resolution
      from app.db.models.job import Job, JobStatus
      from app.db.session import SessionLocal
  ```

## FastAPI Patterns

**Router setup:**
- Each resource gets its own router file under `backend/app/api/routers/`
- Router prefix and tags defined at instantiation: `router = APIRouter(prefix="/videos", tags=["videos"])`
- Routers registered in `backend/app/main.py` via `app.include_router()`

**Dependency injection:**
- DB session provided via `Depends(get_db)` in route signatures
- `get_db()` is a generator dependency that always closes the session in `finally`

**Response format:**
- Routes return plain `dict` literals — no Pydantic response models defined yet
- Keys use snake_case: `video_id`, `job_id`, `celery_task_id`

**Error handling:**
- `HTTPException` raised directly in route handlers with appropriate HTTP status codes
- 404 for missing resources: `raise HTTPException(status_code=404, detail="Video not found")`
- No custom exception classes or global exception handlers yet

**Startup event:**
- `@app.on_event("startup")` used to run `Base.metadata.create_all()` — this is the deprecated lifecycle style (Pydantic v2 / FastAPI recommends `lifespan` context manager)

## SQLAlchemy ORM Patterns

**Model definition:**
- SQLAlchemy 2.0 `Mapped` + `mapped_column` style (not the legacy `Column` approach):
  ```python
  id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
  filename: Mapped[str] = mapped_column(String)
  ```
- All primary keys are UUID strings generated via `str(uuid.uuid4())`
- Timestamps use `datetime.now(timezone.utc)` with explicit timezone — never naive datetimes
- `default=lambda: ...` pattern used for column defaults (callable lambdas, not expressions)
- `onupdate=lambda: datetime.now(timezone.utc)` used for `updated_at` columns

**Session management:**
- Sync SQLAlchemy only — no async sessions (chosen for Celery worker compatibility)
- `SessionLocal` factory used directly inside Celery tasks
- `get_db()` generator dependency used in FastAPI routes

## Celery Task Patterns

**Task decoration:**
- Named tasks using explicit `name=` parameter: `@celery_app.task(name="process_video_task", bind=True)`
- `bind=True` used for tasks that may need `self` (retry, introspection)

**Task structure:**
- DB session opened manually (`SessionLocal()`) and closed in `finally`
- Status progression committed incrementally: PENDING → STARTED → SUCCESS/FAILED
- `updated_at` set manually on status changes (not relying on ORM `onupdate` since it requires `db.commit()` trigger via attribute change, not direct assignment)
- Exceptions re-raised after marking job FAILED: `raise exc`

## Configuration

**Settings pattern:**
- `pydantic-settings` `BaseSettings` with environment variable loading
- UPPER_SNAKE_CASE field names match environment variable names directly
- Default values provided for all settings (enables local development without `.env`)
- `class Config: env_file = ".env"` declared inside `Settings`
- Single `settings` singleton instance exported from `backend/app/core/config.py`

## Comments

**When to comment:**
- `noqa` suppressions always include an inline explanation: `# noqa: F401 — needed for FK resolution`
- TODO comments mark stubs that need pipeline wiring: `# TODO: plug in transcription → OCR → inference pipeline here`
- Section comments group related imports or model registrations: `# Register models so Base.metadata knows about them`

**Style:**
- Em dash used in inline comments: `# noqa: F401 — needed for FK resolution`
- Comments are concise and factual

## Module Design

**Exports:**
- No barrel files (`__init__.py` files are all empty)
- Each module is imported directly by consumers using its full path: `from app.api.routers import jobs, videos`

**Package markers:**
- Every directory has an `__init__.py` to be importable as a package
- All `__init__.py` files are empty — no re-exports or initialization logic

---

*Convention analysis: 2026-03-09*
