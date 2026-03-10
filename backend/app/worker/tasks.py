from datetime import datetime, timezone

from app.worker.celery_app import celery_app


@celery_app.task(name="ping_task")
def ping_task():
    return {"status": "ok"}


@celery_app.task(name="process_video_task", bind=True)
def process_video_task(self, job_id: str):
    from app.db.models.video import Video  # noqa: F401 — needed for FK resolution
    from app.db.models.job import Job, JobStatus
    from app.db.models.result import Result
    from app.db.session import SessionLocal
    from app.core.pipeline import run_pipeline

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return {"error": "job not found"}

        job.status = JobStatus.STARTED
        job.updated_at = datetime.now(timezone.utc)
        db.commit()

        # Resolve video file path
        video = db.query(Video).filter(Video.id == job.video_id).first()
        if not video:
            job.status = JobStatus.FAILED
            job.updated_at = datetime.now(timezone.utc)
            db.commit()
            return {"error": "video not found"}

        # Run full pipeline (pure — no DB I/O inside)
        fusion, classification = run_pipeline(video.file_path)

        # Persist result
        result = Result(
            job_id=job_id,
            label=classification.label.value,
            confidence=classification.confidence,
            explanation=classification.explanation,
            evidence_snippets=classification.evidence_snippets,
            combined_content=fusion.combined_content,
            provider=classification.provider,
            model_used=classification.model_used,
            latency_ms=classification.latency_ms,
        )
        db.add(result)

        job.status = JobStatus.SUCCESS
        job.updated_at = datetime.now(timezone.utc)
        db.commit()

        return {"job_id": job_id, "status": "SUCCESS", "label": classification.label.value}

    except Exception as exc:
        db.rollback()
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = JobStatus.FAILED
            job.updated_at = datetime.now(timezone.utc)
            db.commit()
        raise exc

    finally:
        db.close()
