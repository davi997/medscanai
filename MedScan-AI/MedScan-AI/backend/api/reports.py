from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from backend.config import settings
from backend.database import get_db
from backend.models.database_models import AnalysisHistory, AnalysisResult, Report
from backend.services.report_generator import build_report

router = APIRouter(prefix="/api", tags=["reports"])


@router.get("/report/{analysis_id}")
def get_report(analysis_id: str, db: Session = Depends(get_db)):
    a = db.scalar(select(AnalysisResult).options(joinedload(AnalysisResult.image)).where(AnalysisResult.id == analysis_id))
    if not a:
        raise HTTPException(404, "Analysis not found.")
    if a.status != "completed":
        raise HTTPException(409, "A report can only be generated for a completed analysis.")
    settings.ensure_dirs()
    path = settings.report_dir / f"MedScanAI_report_{a.id}.pdf"
    build_report(a, path)
    if not db.scalar(select(Report.id).where(Report.analysis_id == a.id)):
        db.add(Report(analysis_id=a.id, file_path=str(path)))
        db.add(AnalysisHistory(analysis_id=a.id, event="report_generated"))
        db.commit()
    return FileResponse(path, media_type="application/pdf", filename=path.name)
