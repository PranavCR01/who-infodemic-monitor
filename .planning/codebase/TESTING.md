# Testing Patterns

**Analysis Date:** 2026-03-09

## Test Framework

**Runner:**
- No test framework is installed or configured yet
- `pyproject.toml` at `backend/pyproject.toml` has no `[tool.pytest]` or `[tool.pytest.ini_options]` section
- No `pytest.ini`, `setup.cfg`, `conftest.py`, or `tox.ini` detected anywhere in the repo

**Assertion Library:**
- Not applicable — no tests exist

**Run Commands:**
```bash
# No test commands defined yet
# Intended future runner: pytest (standard FastAPI/Python convention)
pytest                      # Run all tests
pytest --cov=app            # With coverage
pytest -v                   # Verbose output
```

## Test File Organization

**Location:**
- A `backend/app/tests/` directory exists with only an empty `__init__.py`
- No test files have been written yet
- The intended pattern is a centralized `tests/` directory inside `backend/app/`

**Naming:**
- Not established — no test files exist
- Standard Python convention to follow: `test_*.py` prefix (e.g., `test_videos.py`, `test_jobs.py`)

**Structure:**
```
backend/app/tests/
└── __init__.py             # empty — directory reserved for future tests
```

## Test Structure

**Suite Organization:**
- Not yet established
- Recommended pattern for FastAPI projects:
  ```python
  # test_videos.py
  def test_upload_video_success(client, tmp_path):
      ...

  def test_upload_video_stores_record(client, db_session):
      ...
  ```

**Patterns:**
- No setup/teardown patterns established
- No fixture patterns established

## Mocking

**Framework:**
- Not configured
- Standard choice for this stack: `pytest` with `unittest.mock` or `pytest-mock`

**What to Mock (recommended for this stack):**
- File system operations in upload tests (use `tmp_path` pytest fixture)
- Celery task dispatch (`process_video_task.delay`) — mock to avoid triggering workers
- External LLM API calls (OpenAI, Azure) when inference module is ported
- Database sessions can be replaced with a test SQLite database via `create_engine("sqlite://")`

**What NOT to Mock:**
- SQLAlchemy ORM behavior — use a real in-memory DB (SQLite) for model tests
- FastAPI request/response cycle — use `TestClient` for route tests

## Fixtures and Factories

**Test Data:**
- No factories or fixtures defined yet
- Recommended pattern when tests are added:
  ```python
  # conftest.py
  import pytest
  from fastapi.testclient import TestClient
  from sqlalchemy import create_engine
  from sqlalchemy.orm import sessionmaker
  from app.main import app
  from app.db.base import Base
  from app.db.session import get_db

  @pytest.fixture
  def db_session():
      engine = create_engine("sqlite:///:memory:")
      Base.metadata.create_all(engine)
      Session = sessionmaker(bind=engine)
      session = Session()
      yield session
      session.close()

  @pytest.fixture
  def client(db_session):
      app.dependency_overrides[get_db] = lambda: db_session
      yield TestClient(app)
      app.dependency_overrides.clear()
  ```

**Location:**
- `backend/app/tests/conftest.py` — does not exist yet, recommended location for shared fixtures

## Coverage

**Requirements:**
- None enforced — no coverage configuration present
- No `[tool.coverage]` section in `pyproject.toml`

**View Coverage:**
```bash
# Once pytest and pytest-cov are added to dependencies:
pytest --cov=app --cov-report=html
```

## Test Types

**Unit Tests:**
- Not yet written
- Scope should cover: ORM model field defaults, `JobStatus` enum values, `Settings` config loading, utility functions

**Integration Tests:**
- Not yet written
- Scope should cover: full HTTP request/response cycle via `TestClient`, DB row creation on upload, job status transitions

**E2E Tests:**
- Not planned currently
- Full pipeline E2E would require Docker Compose running with real Celery workers

## Current State Assessment

The testing infrastructure is entirely absent. The only evidence of test intent is:

- `backend/app/tests/__init__.py` — empty file marking the package, indicating tests directory was scaffolded deliberately
- No pytest, pytest-asyncio, httpx, or pytest-mock packages in `backend/pyproject.toml` dependencies

**Missing packages to add before writing tests:**
```toml
# In backend/pyproject.toml [project.optional-dependencies] or a [tool.pytest] dev group:
pytest>=8.0
pytest-cov>=4.0
httpx>=0.27          # required by FastAPI TestClient
pytest-mock>=3.12
```

**Critical gap:** The `process_video_task` Celery task in `backend/app/worker/tasks.py` has no test coverage for its status transition logic (PENDING → STARTED → SUCCESS/FAILED), which is currently the core of the application's behavior.

---

*Testing analysis: 2026-03-09*
