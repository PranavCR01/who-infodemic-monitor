# Codebase Concerns

**Analysis Date:** 2026-03-09

---

## Tech Debt

**Schema migrations managed via `create_all()` on startup:**
- Issue: `Base.metadata.create_all(bind=engine)` is called in `startup()` in `backend/app/main.py`. This creates tables if they do not exist but does not handle alterations — adding columns, renaming, or dropping fields silently fails against existing databases.
- Files: `backend/app/main.py` (line 16), `backend/app/db/session.py`
- Impact: Any schema change in `backend/app/db/models/video.py` or `backend/app/db/models/job.py` is invisible to existing Postgres containers. Developers will see silent drift between ORM and DB. Production upgrades without Alembic can corrupt or lose data.
- Fix approach: Introduce Alembic. Add `alembic init alembic` under `backend/`, configure `env.py` to import `Base` and `DATABASE_URL`, replace `create_all` call with a proper migration workflow. The `backend/app/db/migrations/` directory is already stubbed (empty `__init__.py`) indicating intent but zero implementation.

**`on_event("startup")` is deprecated in FastAPI:**
- Issue: `@app.on_event("startup")` used in `backend/app/main.py` (line 14) is deprecated since FastAPI 0.93. The recommended replacement is lifespan context managers.
- Files: `backend/app/main.py`
- Impact: Will produce deprecation warnings in logs; will be removed in a future FastAPI version, requiring an emergency fix when upgrading.
- Fix approach: Replace with `@asynccontextmanager` lifespan pattern and pass it to `FastAPI(lifespan=lifespan)`.

**Entire pipeline is a stub — no actual processing happens:**
- Issue: `process_video_task` in `backend/app/worker/tasks.py` (line 27) contains a single `TODO` comment where the transcription → OCR → inference pipeline should run. The task immediately marks jobs as `SUCCESS` without doing any real work.
- Files: `backend/app/worker/tasks.py`
- Impact: The system returns `SUCCESS` for every job regardless of outcome. All classification, transcription, and OCR modules are absent from the production codebase. There is no `Result` DB model, so no output is persisted.
- Fix approach: Port `pages/processes/transcription.py`, `pages/processes/ocr/text_extractor.py`, and `pages/processes/analysis.py` from the prototype repo. Create a `Result` ORM model. Wire into `process_video_task`.

**No `Result` database model exists:**
- Issue: There is no ORM model or DB table for storing classification outputs (label, confidence, explanation, evidence snippets). The `backend/app/db/models/` directory only contains `video.py` and `job.py`.
- Files: `backend/app/db/models/` (missing `result.py`)
- Impact: Even once the pipeline is wired in, there is nowhere to persist outputs. `GET /jobs/{job_id}` returns only status, never results.
- Fix approach: Add `backend/app/db/models/result.py` with fields: `id`, `job_id` (FK), `label` (enum: MISINFO/NO_MISINFO/DEBUNKING/CANNOT_RECOGNIZE), `confidence` (float), `explanation` (text), `evidence_snippets` (JSON), `created_at`. Add corresponding Alembic migration.

**`services/` layer is completely empty:**
- Issue: `backend/app/services/__init__.py` is an empty file. The directory has no implementation. All business logic currently lives directly in router functions and the Celery task.
- Files: `backend/app/services/` (empty)
- Impact: As complexity grows, router functions will absorb business logic, making routes harder to test and maintain. Already visible in `backend/app/api/routers/videos.py` where file-write and DB operations are inline.
- Fix approach: Extract file-save logic to a `StorageService`, DB persistence logic to `VideoService`/`JobService`. Routers should only handle HTTP concerns.

---

## Security Considerations

**Default hardcoded credentials in docker-compose and config:**
- Risk: `docker-compose.yml` (lines 4–6) hardcodes `POSTGRES_PASSWORD: postgres`. `backend/app/core/config.py` (line 7) defaults `DATABASE_URL` to `postgresql+psycopg://postgres:postgres@db:5432/infodemic`. If `.env` is missing or empty, the app silently uses these weak defaults.
- Files: `infra/docker-compose.yml`, `backend/app/core/config.py`
- Current mitigation: `.gitignore` excludes `.env`; credentials are not in the production `.env.example` values. Docker volume is local-only.
- Recommendations: Remove default values from `Settings` for sensitive fields (`DATABASE_URL`, passwords) so the app fails loudly when secrets are absent. Enforce secret validation at startup. Consider Docker secrets or a secrets manager for any future deployment beyond local dev.

**No file type or size validation on upload:**
- Risk: `POST /videos/upload` in `backend/app/api/routers/videos.py` (lines 14–38) accepts any file type and any size. A malicious actor could upload executables, enormous files, or path-traversal filenames.
- Files: `backend/app/api/routers/videos.py`
- Current mitigation: None.
- Recommendations: Validate `content_type` against an allowlist (`video/mp4`, `video/webm`, etc.). Enforce a maximum file size (e.g., 500MB). Sanitize `file.filename` before using it for extension extraction — `os.path.splitext` is used but the filename is never checked for traversal characters.

**No authentication or authorization on any endpoint:**
- Risk: All API endpoints (`POST /videos/upload`, `POST /jobs/create`, `GET /jobs/{job_id}`, `GET /health`) are publicly accessible with no authentication. Any network-reachable client can upload files and trigger jobs.
- Files: `backend/app/api/routers/videos.py`, `backend/app/api/routers/jobs.py`, `backend/app/main.py`
- Current mitigation: Local-only deployment behind Docker networking.
- Recommendations: Before any internet-facing deployment, implement API key authentication at minimum (FastAPI `Security` dependency). For multi-user WHO use case, add JWT-based auth with role-based access control.

**Redis has no authentication configured:**
- Risk: `infra/docker-compose.yml` (line 13–15) runs Redis with no password (`requirepass` not set). CELERY_BROKER_URL defaults to `redis://redis:6379/0` with no credentials.
- Files: `infra/docker-compose.yml`, `backend/app/core/config.py`
- Current mitigation: Redis port is only exposed internally within the Docker network.
- Recommendations: Add `--requirepass` to the Redis command and include the password in `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND`.

**`.pycache__` files tracked in repository:**
- Risk: `backend/app/core/__pycache__/` and `backend/app/worker/__pycache__/` are committed to the repository (they appear in the directory listing alongside source files).
- Files: `backend/app/core/__pycache__/`, `backend/app/worker/__pycache__/`
- Current mitigation: None — `__pycache__/` is in `.gitignore` but existing committed cache files are not removed.
- Recommendations: Run `git rm -r --cached **/__pycache__` and commit. Confirm `.gitignore` entries are effective.

---

## Performance Bottlenecks

**Entire file loaded into memory on upload:**
- Problem: `content = file.file.read()` in `backend/app/api/routers/videos.py` (line 22) reads the entire uploaded video into a Python `bytes` object before writing it to disk.
- Files: `backend/app/api/routers/videos.py`
- Cause: Synchronous blocking read without streaming. For a 500MB video, this allocates 500MB in the API process RAM.
- Improvement path: Use `shutil.copyfileobj` or chunked streaming writes. Consider `aiofiles` (already a dependency per `backend/pyproject.toml`) for async disk I/O once the route is made async.

**Synchronous DB sessions inside async FastAPI routes:**
- Problem: Routes in `backend/app/api/routers/videos.py` and `backend/app/api/routers/jobs.py` use synchronous SQLAlchemy sessions (`Session` from `get_db()`). FastAPI runs sync route functions in a thread pool, which limits concurrency under load.
- Files: `backend/app/api/routers/videos.py`, `backend/app/api/routers/jobs.py`, `backend/app/db/session.py`
- Cause: Deliberate choice to use sync ORM for Celery compatibility, but the API layer does not benefit from this constraint.
- Improvement path: Use `AsyncSession` with `asyncpg` driver for the FastAPI API layer. Keep sync sessions only in Celery worker tasks.

**No DB connection pooling configuration:**
- Problem: `create_engine(settings.DATABASE_URL)` in `backend/app/db/session.py` (line 5) uses SQLAlchemy defaults (pool size 5, max overflow 10). No explicit pool settings for the expected concurrent load.
- Files: `backend/app/db/session.py`
- Cause: Default engine configuration.
- Improvement path: Set `pool_size`, `max_overflow`, and `pool_timeout` explicitly once load characteristics are known.

---

## Fragile Areas

**`process_video_task` exception handler re-queries a potentially missing job:**
- Files: `backend/app/worker/tasks.py` (lines 36–40)
- Why fragile: In the `except` block, the task re-queries `db.query(Job).filter(Job.id == job_id).first()`. If the job was deleted between the initial query and the exception, or if the DB session itself is broken, this second query silently returns `None` and the `if job:` guard swallows the failure without setting `FAILED` status.
- Safe modification: Reuse the `job` variable from the outer scope (already bound). Only re-query if needed after session rollback. Add explicit `db.rollback()` before the second query.
- Test coverage: No tests exist for this code path.

**Race condition between job creation and Celery task dispatch:**
- Files: `backend/app/api/routers/jobs.py` (lines 26–32)
- Why fragile: The job is committed to DB (line 28), then `process_video_task.delay(job_id)` is called (line 30), then `celery_task_id` is written back (lines 31–32). If the Celery worker picks up the task before line 32 commits, `job.celery_task_id` is `NULL` in DB during early task execution. If the API process crashes between lines 30 and 32, the task runs but `celery_task_id` is never stored.
- Safe modification: Set `celery_task_id` before committing, using a pre-generated task ID (Celery supports `apply_async(task_id=...)`).
- Test coverage: No tests exist.

**`on_startup` table creation is not idempotent on schema changes:**
- Files: `backend/app/main.py` (line 16)
- Why fragile: `create_all(checkfirst=True)` (SQLAlchemy default) creates missing tables but never alters existing ones. Adding a new column to `Video` or `Job` after first run silently leaves the DB schema out of sync with ORM models, causing `sqlalchemy.exc.ProgrammingError` at query time.
- Safe modification: Migrate to Alembic immediately, before any schema changes are made.
- Test coverage: No tests exist for DB initialization.

**File extension extracted from user-supplied filename only:**
- Files: `backend/app/api/routers/videos.py` (line 19)
- Why fragile: `ext = os.path.splitext(file.filename or "video")[1] or ".mp4"` trusts the client-supplied filename for extension. A file named `malware.exe` saves as `{uuid}.exe` in the storage directory. A file with no extension falls back to `.mp4` regardless of actual content type.
- Safe modification: Derive extension from validated `content_type` header using a lookup table, or use `python-magic` to inspect file bytes.
- Test coverage: No tests exist.

---

## Scaling Limits

**Local filesystem storage:**
- Current capacity: Single Docker volume (`infodemic_storage`) on the host machine.
- Limit: Cannot scale horizontally — multiple API/worker replicas require a shared filesystem or object storage. A second Docker host breaks file visibility entirely.
- Scaling path: Abstract storage behind a `StorageService` interface (the `backend/app/core/storage/` directory is already stubbed). Implement S3-compatible backend (AWS S3, MinIO). The CLAUDE.md engineering guidance already flags this.

**Single Celery worker, no concurrency configuration:**
- Current capacity: One worker process, default concurrency (number of CPUs).
- Limit: Video processing (transcription + OCR) is CPU-intensive. A single worker will serialize all jobs. Queue depth grows linearly with submission rate.
- Scaling path: Configure `--concurrency` explicitly. Add dedicated queues (e.g., `transcription`, `inference`). Use Celery task routing to separate lightweight tasks from GPU/CPU-heavy ones.

---

## Dependencies at Risk

**No pinned dependency versions:**
- Risk: `backend/pyproject.toml` uses open lower-bound version constraints (`fastapi>=0.110`, `celery>=5.3`, etc.) with no upper bounds. A major version bump in any dependency can silently break the application on a fresh install.
- Impact: `pip install .` could install FastAPI 0.115, Celery 6.x, or SQLAlchemy 3.x which may introduce breaking changes.
- Migration plan: Pin to exact versions using a lockfile (`uv lock`, `pip-tools`, or `poetry.lock`). Add a `requirements.lock` generated from current working state.

**`aiofiles` imported as dependency but not used:**
- Risk: `aiofiles>=23.0` is listed in `backend/pyproject.toml` (line 15) but no source file uses `import aiofiles`. This indicates planned async file I/O that has not been implemented.
- Impact: Unused dependency adds install time and potential supply-chain surface area.
- Migration plan: Either implement async file writes in the upload route (the intended use), or remove the dependency until it is needed.

---

## Missing Critical Features

**No Result persistence:**
- Problem: There is no DB model, API endpoint, or Celery task logic for storing classification results. The pipeline stub in `backend/app/worker/tasks.py` does not return or save any output.
- Blocks: Everything downstream — frontend display, analyst review, export, audit trails — depends on this.

**No authentication system:**
- Problem: Zero auth implementation exists. No API keys, no JWT, no session management.
- Blocks: Any deployment beyond localhost. WHO stakeholder access. Multi-user workflows.

**No input validation on video upload:**
- Problem: File type, size, and content are not validated at ingestion.
- Blocks: Safe public-facing deployment. Prevents abuse in any internet-accessible deployment.

**No Alembic migrations:**
- Problem: Schema evolution is impossible without manual DB intervention.
- Blocks: Any schema change after initial deployment (e.g., adding the `Result` table, adding metadata fields to `Video`).

---

## Test Coverage Gaps

**Zero test files exist:**
- What's not tested: Every route, every DB model, every Celery task, all error handling paths, file upload logic, job status transitions.
- Files: `backend/app/tests/__init__.py` is an empty stub. No test files exist anywhere in the repository.
- Risk: Any refactor or dependency upgrade can silently break core flows with no automated detection. The race condition in `jobs.py` and the exception handler bug in `tasks.py` cannot be caught without tests.
- Priority: High

**No CI pipeline:**
- What's not tested: Nothing is run on pull request or merge. `.github/workflows/` directory exists but contains no workflow files.
- Files: `.github/workflows/` (empty)
- Risk: No automated quality gate. Broken code can be merged to main without detection.
- Priority: High

---

*Concerns audit: 2026-03-09*
