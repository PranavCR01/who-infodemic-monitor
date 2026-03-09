import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models.job import Job, JobStatus
from app.db.models.video import Video
from app.db.session import get_db
from app.worker.tasks import process_video_task

router = APIRouter(prefix="/jobs", tags=["jobs"])


class CreateJobRequest(BaseModel):
    video_id: str


@router.post("/create")
def create_job(payload: CreateJobRequest, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.id == payload.video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    job_id = str(uuid.uuid4())
    job = Job(id=job_id, video_id=payload.video_id, status=JobStatus.PENDING)
    db.add(job)
    db.commit()

    task = process_video_task.delay(job_id)
    job.celery_task_id = task.id
    db.commit()

    return {
        "job_id": job.id,
        "video_id": job.video_id,
        "status": job.status,
        "celery_task_id": job.celery_task_id,
    }


@router.get("/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job.id,
        "video_id": job.video_id,
        "status": job.status,
        "celery_task_id": job.celery_task_id,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }
