from app.worker.celery_app import celery_app


@celery_app.task(name="ping_task")
def ping_task():
    return {"status": "ok"}