from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "who_infodemic_monitor",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# Auto-discover tasks in app.worker.tasks
celery_app.autodiscover_tasks(["app.worker"])

celery_app.conf.update(task_track_started=True)