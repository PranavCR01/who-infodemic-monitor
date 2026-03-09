import os
import uuid

from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.video import Video
from app.db.session import get_db

router = APIRouter(prefix="/videos", tags=["videos"])


@router.post("/upload")
def upload_video(file: UploadFile = File(...), db: Session = Depends(get_db)):
    video_id = str(uuid.uuid4())

    os.makedirs(settings.LOCAL_STORAGE_ROOT, exist_ok=True)
    ext = os.path.splitext(file.filename or "video")[1] or ".mp4"
    file_path = os.path.join(settings.LOCAL_STORAGE_ROOT, f"{video_id}{ext}")

    content = file.file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    video = Video(
        id=video_id,
        filename=file.filename or "upload",
        file_path=file_path,
        file_size=len(content),
    )
    db.add(video)
    db.commit()

    return {
        "video_id": video_id,
        "filename": video.filename,
        "file_size": video.file_size,
    }
