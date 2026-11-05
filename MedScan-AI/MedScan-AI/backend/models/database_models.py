"""ORM tables.

Privacy: we deliberately do NOT store the original filename (it often contains a
patient name), patient identifiers, or EXIF/DICOM metadata. Images are identified
by a random UUID and a SHA-256 hash.
There is no User table: authentication is not implemented in this version.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MedicalImage(Base):
    __tablename__ = "medical_images"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    category: Mapped[str] = mapped_column(String(40), index=True)
    stored_path: Mapped[str] = mapped_column(String(300))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    size_bytes: Mapped[int] = mapped_column(Integer)
    source_format: Mapped[str] = mapped_column(String(10))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    analyses: Mapped[list["AnalysisResult"]] = relationship(back_populates="image", cascade="all, delete-orphan")


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    image_id: Mapped[str] = mapped_column(ForeignKey("medical_images.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending|completed|failed
    model_id: Mapped[str] = mapped_column(String(80))
    model_info: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    findings: Mapped[list | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str | None] = mapped_column(String(40), nullable=True)
    top_finding: Mapped[str | None] = mapped_column(String(80), nullable=True)
    top_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    warnings: Mapped[list | None] = mapped_column(JSON, nullable=True)
    heatmap_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    heatmap_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    inference_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    image: Mapped[MedicalImage] = relationship(back_populates="analyses")
    reports: Mapped[list["Report"]] = relationship(back_populates="analysis", cascade="all, delete-orphan")
    history: Mapped[list["AnalysisHistory"]] = relationship(back_populates="analysis", cascade="all, delete-orphan")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analysis_results.id", ondelete="CASCADE"), index=True)
    file_path: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    analysis: Mapped[AnalysisResult] = relationship(back_populates="reports")


class AnalysisHistory(Base):
    """Append-only event log for an analysis (audit trail)."""

    __tablename__ = "analysis_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analysis_results.id", ondelete="CASCADE"), index=True)
    event: Mapped[str] = mapped_column(String(40))  # created|started|completed|failed|report_generated
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    analysis: Mapped[AnalysisResult] = relationship(back_populates="history")
