# External Integrations

**Analysis Date:** 2026-03-09

## APIs & External Services

**LLM Inference (planned — not yet wired into production backend):**
- OpenAI API — misinformation classification via GPT models
  - SDK/Client: `openai` Python package (in old repo; not yet in `backend/pyproject.toml`)
  - Auth: `OPENAI_API_KEY` environment variable (expected; not yet in `.env.example`)
- Azure OpenAI — alternative LLM provider
  - SDK/Client: `openai` Python package with Azure endpoint configuration
  - Auth: `AZURE_OPENAI_KEY`, `AZURE_OPENAI_ENDPOINT` (expected; not yet in `.env.example`)
- Ollama — local model serving (e.g., Mistral)
  - SDK/Client: HTTP requests to local Ollama API (`http://localhost:11434`)
  - Auth: None (local service, no auth)
  - Note: intended for air-gapped or cost-free inference scenarios

**Transcription (planned — not yet wired into production backend):**
- OpenAI Whisper API — cloud audio transcription
  - SDK/Client: `openai` Python package
  - Auth: `OPENAI_API_KEY`
- faster-whisper — local transcription model
  - SDK/Client: `faster-whisper` Python package (not yet in `backend/pyproject.toml`)
  - Auth: None (local model)

## Data Storage

**Databases:**
- PostgreSQL 16
  - Connection env var: `DATABASE_URL` (value: `postgresql+psycopg://postgres:postgres@db:5432/infodemic`)
  - Client: SQLAlchemy 2.0 ORM with psycopg3 driver (`psycopg[binary]`)
  - Session management: `backend/app/db/session.py` — sync `SessionLocal`, `get_db()` FastAPI dependency
  - Schema: `videos` table, `jobs` table; no Alembic migrations yet — tables created via `Base.metadata.create_all()` on app startup in `backend/app/main.py`
  - Docker volume: `infodemic_pgdata` persists Postgres data

**File Storage:**
- Local filesystem (current)
  - Mount: `infodemic_storage` Docker volume shared between `api` and `worker` containers
  - Path inside container: `/app/storage` (configured via `LOCAL_STORAGE_ROOT`)
  - Files stored as: `{video_id}{original_ext}` in `LOCAL_STORAGE_ROOT`
  - Upload handled in: `backend/app/api/routers/videos.py`
- AWS S3 (planned)
  - Noted in engineering guidance as future migration target from local storage
  - No S3 SDK or credentials are present yet

**Caching:**
- Redis 7 (dual-purpose)
  - Celery broker: `redis://redis:6379/0` (env var: `CELERY_BROKER_URL`)
  - Celery result backend: `redis://redis:6379/1` (env var: `CELERY_RESULT_BACKEND`)
  - Not used for application-level caching currently

## Authentication & Identity

**Auth Provider:**
- None (no authentication layer implemented yet)
- No JWT, session, or OAuth middleware present in `backend/app/main.py` or routers
- All API endpoints are currently open/unauthenticated

## Monitoring & Observability

**Error Tracking:**
- None configured — no Sentry, Datadog, or equivalent SDK present

**Logs:**
- Celery worker logging: `--loglevel=INFO` flag in Docker Compose worker command
- FastAPI: default Uvicorn access logs (stdout)
- No structured logging library (e.g., `loguru`, `structlog`) present

## CI/CD & Deployment

**Hosting:**
- Not yet defined for production
- Local development via Docker Compose (`infra/docker-compose.yml`)

**CI Pipeline:**
- `.github/workflows/` directory exists but contains no workflow files
- No automated test runs, linting, or deployment pipelines configured

## Environment Configuration

**Required env vars (from `.env.example`):**
- `APP_ENV` — environment label (e.g., `local`)
- `POSTGRES_USER` — PostgreSQL username
- `POSTGRES_PASSWORD` — PostgreSQL password
- `POSTGRES_DB` — PostgreSQL database name
- `DATABASE_URL` — full SQLAlchemy connection string
- `REDIS_URL` — Redis connection URL
- `CELERY_BROKER_URL` — Celery broker URL
- `CELERY_RESULT_BACKEND` — Celery result backend URL
- `LOCAL_STORAGE_ROOT` — path inside container for video uploads

**Secrets location:**
- `.env` file at repo root (excluded from git via `.gitignore`)
- Template at `.env.example` (committed to git)
- No secrets manager (Vault, AWS Secrets Manager, etc.) integrated

## Webhooks & Callbacks

**Incoming:**
- None configured

**Outgoing:**
- None configured

## OCR Integration (planned — not yet in production backend)

**EasyOCR:**
- Purpose: extract on-screen text from video frames
- SDK: `easyocr` Python package (in old repo at `pages/processes/ocr/text_extractor.py`)
- System deps: OpenCV (`libgl1`, `libglib2.0-0`) already installed in `backend/Dockerfile`
- Target location when ported: `backend/app/core/extraction/ocr/`

---

*Integration audit: 2026-03-09*
