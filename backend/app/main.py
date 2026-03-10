from fastapi import FastAPI

from app.api.routers import jobs, videos
from app.db.base import Base
from app.db.session import engine

# Register models so Base.metadata knows about them
import app.db.models.video  # noqa: F401
import app.db.models.job    # noqa: F401
import app.db.models.result  # noqa: F401

app = FastAPI(title="WHO Infodemic Monitor API", version="0.1.0")


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)


app.include_router(videos.router)
app.include_router(jobs.router)


@app.get("/health")
def health():
    return {"status": "ok"}
