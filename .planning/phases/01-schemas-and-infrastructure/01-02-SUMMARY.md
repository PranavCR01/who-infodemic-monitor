---
phase: 01-schemas-and-infrastructure
plan: "02"
subsystem: database
tags: [pydantic, sqlalchemy, schemas, orm, pipeline-contracts]

# Dependency graph
requires:
  - phase: 01-schemas-and-infrastructure/01-00
    provides: "pytest setup, RED-phase stub tests for schemas and infrastructure"
  - phase: 01-schemas-and-infrastructure/01-01
    provides: "ML deps, Dockerfile pre-warm, pydantic-settings config"
provides:
  - "MisinfoLabel(str, enum.Enum) with 4 canonical labels: MISINFO, NO_MISINFO, DEBUNKING, CANNOT_RECOGNIZE"
  - "FusionResult Pydantic model — extraction output contract for transcript + OCR fusion"
  - "ClassificationResult Pydantic model — inference output contract with clamped confidence field_validator"
  - "Result ORM model mapped to 'results' table with job_id unique FK and JSON evidence_snippets"
  - "app/db/base.py DeclarativeBase — SQLAlchemy ORM foundation for the worktree"
affects:
  - "02-extraction — imports FusionResult from app.core.schemas.pipeline"
  - "03-inference — imports ClassificationResult, MisinfoLabel from app.core.schemas.pipeline"
  - "04-pipeline-wiring — creates Result rows after run_pipeline returns ClassificationResult"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "(str, enum.Enum) for label enums — avoids SQLAlchemy SAEnum DB type, validates at application layer"
    - "ForeignKey string reference (jobs.id) — no need to import Job model in result.py"
    - "JSON column type for list fields — psycopg3 handles serialization automatically"
    - "@field_validator with clamp pattern — defensive confidence normalization before persistence"

key-files:
  created:
    - backend/app/core/schemas/pipeline.py
    - backend/app/db/models/result.py
    - backend/app/db/base.py
  modified:
    - backend/app/main.py

key-decisions:
  - "MisinfoLabel uses (str, enum.Enum) NOT StrEnum — avoids SQLAlchemy mapped_column compatibility issues while preserving plain-string JSON serialization"
  - "label column is String(32) NOT SAEnum — DB-level enum avoided; MisinfoLabel validation happens in Pydantic ClassificationResult"
  - "evidence_snippets uses SQLAlchemy JSON type — psycopg3 auto-serializes Python list to JSON, no manual string encoding"
  - "ClassificationResult.confidence clamped via @field_validator — LLM outputs may exceed [0,1] range"
  - "app/db/base.py auto-fixed into worktree — prerequisite DeclarativeBase was missing from this branch"

patterns-established:
  - "Contract-first schema design: pipeline.py is single source of truth for all inter-module data types"
  - "Application-layer enum validation: use (str, enum.Enum) in Pydantic, String column in ORM"
  - "JSON for list columns: evidence_snippets and similar list fields use JSON not Text"

requirements-completed: [SCHEMA-01, SCHEMA-02, SCHEMA-03]

# Metrics
duration: 28min
completed: 2026-03-10
---

# Phase 1 Plan 02: Schemas and Infrastructure — Pydantic Schemas + Result ORM

**Pydantic pipeline contracts (MisinfoLabel, FusionResult, ClassificationResult) and Result ORM model created — establishes typed data flow from extraction through inference to persistence**

## Performance

- **Duration:** 28 min
- **Started:** 2026-03-10T18:34:28Z
- **Completed:** 2026-03-10T19:02:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Created `app/core/schemas/pipeline.py` — single import source for all pipeline data contracts used by Phase 2 (Extraction), Phase 3 (Inference), and Phase 4 (Pipeline Wiring)
- MisinfoLabel(str, enum.Enum) with 4 canonical labels serializes as plain strings in FastAPI JSON responses
- ClassificationResult.confidence field_validator clamps out-of-range LLM outputs to [0.0, 1.0]
- Result ORM model with job_id unique constraint, String(32) label, and JSON evidence_snippets wired into main.py registration
- All 9 unit tests passing (5 schema tests + 3 result model tests + 1 config test)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create pipeline.py with MisinfoLabel, FusionResult, ClassificationResult** - `5fe4777` (feat)
2. **Task 2: Create Result ORM model and register in main.py** - `09b34cc` (feat)

_Note: TDD tasks — tests were written RED in plan 01-00, GREEN implemented here._

## Files Created/Modified
- `backend/app/core/schemas/pipeline.py` — MisinfoLabel enum + FusionResult + ClassificationResult Pydantic models
- `backend/app/db/models/result.py` — Result ORM model mapped to 'results' table, 11 columns
- `backend/app/db/base.py` — SQLAlchemy DeclarativeBase (auto-fix prerequisite)
- `backend/app/main.py` — Added `import app.db.models.result  # noqa: F401` for create_all registration

## Decisions Made
- MisinfoLabel uses `(str, enum.Enum)` NOT `StrEnum` to avoid SQLAlchemy mapped_column compatibility issues while preserving plain-string JSON serialization
- `label` column is `String(32)` not `SAEnum(MisinfoLabel)` — DB-level enum type avoided; validation happens in Pydantic ClassificationResult at application layer
- `evidence_snippets` uses SQLAlchemy `JSON` type — psycopg3 handles list serialization automatically without manual encoding
- `ClassificationResult.confidence` clamped via `@field_validator` — LLM outputs not guaranteed to be in [0,1] range

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Created missing app/db/base.py in worktree**
- **Found during:** Task 2 (Create Result ORM model)
- **Issue:** The `claude/sharp-morse` worktree branched from commit `fa1d3f9` (plan 01-00), which predates the milestone 2 commit (`8d92d6d`) that added `base.py`, `video.py`, `job.py`, etc. Result ORM model requires `from app.db.base import Base` — import would fail without it.
- **Fix:** Created `backend/app/db/base.py` with `DeclarativeBase` (identical to main repo version) as prerequisite
- **Files modified:** `backend/app/db/base.py`
- **Verification:** `test_result_model_fields` imports and inspects Result successfully — all 3 result model tests pass
- **Committed in:** `09b34cc` (Task 2 commit)

**2. [Rule 3 - Blocking] Simplified main.py for worktree context**
- **Found during:** Task 2 (Register result model in main.py)
- **Issue:** Plan's interface showed full main.py with router imports and DB session that don't exist in this worktree. Using the exact plan content would cause import errors on server startup.
- **Fix:** Added only `import app.db.models.result  # noqa: F401` to the existing simple main.py rather than replacing with the full version
- **Files modified:** `backend/app/main.py`
- **Verification:** Tests don't import main.py directly; import line satisfies plan's `must_haves.artifacts` requirement
- **Committed in:** `09b34cc` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 3 - blocking)
**Impact on plan:** Both auto-fixes were necessary for correctness in the worktree context. No scope creep. All success criteria met.

## Issues Encountered
- Docker volume path format on Windows: `/d/Python files/...` (Git Bash format) didn't work for `docker run -v` mounts; required Windows format `D:/Python files/...`. Resolved by using Windows path format in all docker run commands.
- `docker compose exec api pytest` not usable because the running infra container (from `recursing-easley` worktree) mounts a non-existent path. Used `docker run --rm -v ... infra-api sh -c "pytest ..."` pattern instead.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 2 (Extraction): Can import `FusionResult` from `app.core.schemas.pipeline` — contract ready
- Phase 3 (Inference): Can import `ClassificationResult`, `MisinfoLabel` from `app.core.schemas.pipeline` — contract ready
- Phase 4 (Pipeline Wiring): Can create `Result` rows via `app.db.models.result.Result` — ORM model ready
- Phase 1 complete: all 3 plans (01-00, 01-01, 01-02) done

---
*Phase: 01-schemas-and-infrastructure*
*Completed: 2026-03-10*
