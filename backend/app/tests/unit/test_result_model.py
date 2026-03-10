"""Tests for Result ORM model (SCHEMA-03).

RED PHASE: These tests fail until Plan 02 creates app/db/models/result.py.

Note: DB roundtrip tests require a running Postgres container.
Field-existence tests can run without DB.
"""
import pytest


def test_result_model_fields():
    """Result model has all required field definitions."""
    from app.db.models.result import Result
    from sqlalchemy import inspect

    mapper = inspect(Result)
    column_names = {col.key for col in mapper.mapper.column_attrs}

    required_fields = {
        "id", "job_id", "label", "confidence", "explanation",
        "evidence_snippets", "combined_content", "provider",
        "model_used", "latency_ms", "created_at",
    }
    missing = required_fields - column_names
    assert not missing, f"Result model missing columns: {missing}"


def test_result_model_tablename():
    """Result model maps to the 'results' table."""
    from app.db.models.result import Result
    assert Result.__tablename__ == "results"


def test_result_model_job_id_unique():
    """job_id column has a unique constraint."""
    from app.db.models.result import Result
    from sqlalchemy import inspect

    mapper = inspect(Result)
    job_id_col = next(
        col for col in mapper.mapper.column_attrs if col.key == "job_id"
    )
    # Access underlying Column to check unique constraint
    actual_col = Result.__table__.c["job_id"]
    assert actual_col.unique, "job_id must have unique=True"
