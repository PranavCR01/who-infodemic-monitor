---
phase: 1
slug: schemas-and-infrastructure
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-09
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `backend/pyproject.toml` — add `[tool.pytest.ini_options]` section |
| **Quick run command** | `docker compose exec api pytest app/tests/unit/ -x -q` |
| **Full suite command** | `docker compose exec api pytest app/tests/ -v` |
| **Estimated runtime** | ~10 seconds (unit only, no real containers or APIs) |

---

## Sampling Rate

- **After every task commit:** `docker compose exec api python -c "import faster_whisper, easyocr, cv2, anthropic, openai, tiktoken; print('imports OK')"` (INFRA-01 smoke)
- **After every plan wave:** `docker compose exec api pytest app/tests/unit/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green + INFRA-02 smoke passes
- **Max feedback latency:** ~15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| deps | 01 | 1 | INFRA-01 | smoke | `docker compose exec api python -c "import faster_whisper, easyocr, cv2, anthropic, openai, tiktoken; print('OK')"` | ❌ Wave 0 | ⬜ pending |
| dockerfile | 01 | 1 | INFRA-02 | smoke | `docker compose exec worker python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8', local_files_only=True); print('OK')"` | ❌ Wave 0 | ⬜ pending |
| config | 01 | 1 | INFRA-03 | unit | `docker compose exec api pytest app/tests/unit/test_config.py -x` | ❌ Wave 0 | ⬜ pending |
| fusion-schema | 02 | 2 | SCHEMA-01 | unit | `docker compose exec api pytest app/tests/unit/test_schemas.py::test_fusion_result -x` | ❌ Wave 0 | ⬜ pending |
| classification-schema | 02 | 2 | SCHEMA-02 | unit | `docker compose exec api pytest app/tests/unit/test_schemas.py::test_classification_result -x` | ❌ Wave 0 | ⬜ pending |
| result-model | 02 | 2 | SCHEMA-03 | unit | `docker compose exec api pytest app/tests/unit/test_result_model.py -x` | ❌ Wave 0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/pyproject.toml` — add `[project.optional-dependencies.test]` with `pytest>=8.0` and `[tool.pytest.ini_options]` for test discovery
- [ ] `backend/tests/__init__.py` — already exists (empty, good)
- [ ] `backend/tests/unit/__init__.py` — create unit test subdirectory
- [ ] `backend/tests/unit/test_config.py` — stubs for INFRA-03 (Settings loads all new env vars with defaults)
- [ ] `backend/tests/unit/test_schemas.py` — stubs for SCHEMA-01 (FusionResult) and SCHEMA-02 (ClassificationResult, MisinfoLabel, confidence clamping)
- [ ] `backend/tests/unit/test_result_model.py` — stubs for SCHEMA-03 (Result ORM: table creation, INSERT/SELECT roundtrip, job_id unique constraint)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `docker compose build` succeeds with pre-warmed ML models | INFRA-02 | Requires full Docker build; not automatable in unit test | Run `docker compose build --no-cache` and verify no errors; check worker logs for model download |
| `docker compose up` creates `results` table | SCHEMA-03 | Requires running Postgres container | Run `docker compose up -d db api` then `docker compose exec db psql -U postgres -d infodemic -c "\dt"` and verify `results` appears |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
