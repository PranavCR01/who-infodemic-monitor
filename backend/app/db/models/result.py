"""Result ORM model — persists pipeline classification output for a Job.

One Result row per Job (job_id unique constraint).
label stored as String(32), NOT SAEnum — validated at application layer via MisinfoLabel.
evidence_snippets stored as JSON — psycopg3 handles list serialization automatically.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Result(Base):
    __tablename__ = "results"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    job_id: Mapped[str] = mapped_column(
        String, ForeignKey("jobs.id"), unique=True, nullable=False
    )
    label: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_snippets: Mapped[list] = mapped_column(JSON, nullable=False)
    combined_content: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_used: Mapped[str] = mapped_column(String(128), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
