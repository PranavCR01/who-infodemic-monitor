from datetime import datetime, timezone

from app.worker.celery_app import celery_app


@celery_app.task(name="ping_task")
def ping_task():
    return {"status": "ok"}


@celery_app.task(name="process_video_task", bind=True)
def process_video_task(self, job_id: str):
    from app.db.models.video import Video  # noqa: F401 — needed for FK resolution
    from app.db.models.job import Job, JobStatus
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return {"error": "job not found"}

        job.status = JobStatus.STARTED
        job.updated_at = datetime.now(timezone.utc)
        db.commit()

        # TODO: plug in transcription → OCR → inference pipeline here

        job.status = JobStatus.SUCCESS
        job.updated_at = datetime.now(timezone.utc)
        db.commit()

        return {"job_id": job_id, "status": "SUCCESS"}

    except Exception as exc:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = JobStatus.FAILED
            job.updated_at = datetime.now(timezone.utc)
            db.commit()
        raise exc

    finally:
        db.close()
