---
phase: 01-schemas-and-infrastructure
plan: "00"
subsystem: test-infrastructure
tags: [pytest, tdd, test-harness, wave-0]
requirements: [INFRA-03, SCHEMA-01, SCHEMA-02, SCHEMA-03]

dependency_graph:
  requires: []
  provides:
    - pytest optional dep in pyproject.toml
    - unit test directory at backend/app/tests/unit/
    - RED-phase stub for Settings new fields (INFRA-03)
    - RED-phase stubs for FusionResult and ClassificationResult schemas (SCHEMA-01, SCHEMA-02)
    - RED-phase stubs for Result ORM model (SCHEMA-03)
  affects:
    - 01-01-PLAN.md (can now verify Settings changes with automated pytest)
    - 01-02-PLAN.md (can now verify schemas and Result model with automated pytest)

tech_stack:
  added:
    - pytest>=8.0 (optional dep via pip install -e ".[test]")
  patterns:
    - TDD RED phase: stub tests import not-yet-created modules; fail at collection or assertion

key_files:
  created:
    - backend/app/tests/unit/__init__.py
    - backend/app/tests/unit/test_config.py
    - backend/app/tests/unit/test_schemas.py
    - backend/app/tests/unit/test_result_model.py
  modified:
    - backend/pyproject.toml

decisions:
  - testpaths set to "app/tests" (relative to /app in container, where backend/ is mounted)
  - pytest installed as optional dep [test] to avoid adding to production image by default
  - stub tests use direct imports rather than pytest.fail() so they fail at assertion time (not collection), unless the module doesn't exist yet (collection ImportError is acceptable for Wave 0)

metrics:
  duration: "6 minutes"
  completed: "2026-03-10"
  tasks_completed: 2
  tasks_total: 2
  files_created: 4
  files_modified: 1
---

# Phase 01 Plan 00: Test Infrastructure Setup Summary

Pytest test harness installed and 9 RED-phase stub tests created, enabling automated verify commands for all Wave 1 and Wave 2 tasks before any production code is written.

## What Was Built

### Task 1 — pytest optional dependency and test discovery config (fa1d3f9)

Added two new sections to `backend/pyproject.toml`:

```toml
[project.optional-dependencies]
test = [
  "pytest>=8.0",
]

[tool.pytest.ini_options]
testpaths = ["app/tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
```

pytest is installed via `pip install -e ".[test]"` inside the container, keeping it out of the production image dependency set.

### Task 2 — Unit test stub files (1f2b6ea)

Created `backend/app/tests/unit/` package with 3 RED-phase stub test files:

**test_config.py** (1 test, INFRA-03):
- `test_settings_defaults` — asserts WHISPER_PROVIDER, WHISPER_MODEL, INFERENCE_PROVIDER, OPENAI_API_KEY, ANTHROPIC_API_KEY, ANTHROPIC_MODEL, OLLAMA_BASE_URL, OLLAMA_MODEL are present in Settings with correct defaults. Fails until Plan 01 adds these fields to config.py.

**test_schemas.py** (4 tests, SCHEMA-01/02):
- `test_fusion_result` — constructs FusionResult and validates all fields
- `test_fusion_result_rejects_missing_fields` — confirms ValidationError on missing required fields
- `test_classification_result` — constructs ClassificationResult with full fields
- `test_classification_result_clamps_confidence` — verifies confidence is clamped to [0.0, 1.0]
- `test_misinfo_label_serializes_as_string` — verifies MisinfoLabel serializes as plain string in JSON

**test_result_model.py** (3 tests, SCHEMA-03):
- `test_result_model_fields` — inspects ORM column set against required field list
- `test_result_model_tablename` — asserts `__tablename__ == "results"`
- `test_result_model_job_id_unique` — checks `unique=True` on job_id column

All stubs fail in RED phase (ImportError at collection or assertion error) and will go GREEN when Plans 01-01 and 01-02 implement the production code.

## Deviations from Plan

None — plan executed exactly as written.

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 | fa1d3f9 | chore(01-00): add pytest optional dep and test discovery config |
| 2 | 1f2b6ea | test(01-00): add RED-phase stub tests for schemas and infrastructure |

## Self-Check

### Files Exist
- backend/pyproject.toml: FOUND (modified)
- backend/app/tests/unit/__init__.py: FOUND
- backend/app/tests/unit/test_config.py: FOUND
- backend/app/tests/unit/test_schemas.py: FOUND
- backend/app/tests/unit/test_result_model.py: FOUND

### Commits Exist
- fa1d3f9: FOUND
- 1f2b6ea: FOUND

## Self-Check: PASSED
