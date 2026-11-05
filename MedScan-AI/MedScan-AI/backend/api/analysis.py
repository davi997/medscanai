from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from backend.api.schemas import AnalyzeRequest, serialize_analysis
from backend.database import get_db
from backend.models.database_models import AnalysisResult, MedicalImage, Report
from backend.services.inference import AnalysisError, run_analysis

router = APIRouter(prefix="/api", tags=["analysis"])


def _get(db: Session, analysis_id: str) -> AnalysisResult:
    a = db.scalar(select(AnalysisResult).options(joinedload(AnalysisResult.image), joinedload(AnalysisResult.reports))
                  .where(AnalysisResult.id == analysis_id))
    if not a:
        raise HTTPException(404, "Analysis not found.")
    return a


@router.post("/analyze")
def analyze(req: AnalyzeRequest, db: Session = Depends(get_db)):
    """Sync endpoint (runs in FastAPI's threadpool). Returns real inference output or an error, never placeholders."""
    image = db.get(MedicalImage, req.image_id.lower())
    if not image:
        raise HTTPException(404, "Image not found. Upload it first.")
    try:
        analysis = run_analysis(db, image)
    except AnalysisError as e:
        raise HTTPException(e.status_code, e.message)
    return serialize_analysis(_get(db, analysis.id))


@router.get("/analysis/{analysis_id}")
def get_analysis(analysis_id: str, db: Session = Depends(get_db)):
    return serialize_analysis(_get(db, analysis_id))


@router.get("/analysis/{analysis_id}/heatmap")
def heatmap(analysis_id: str, db: Session = Depends(get_db)):
    a = _get(db, analysis_id)
    if not a.heatmap_path:
        raise HTTPException(404, "No Grad-CAM available for this analysis.")
    return FileResponse(a.heatmap_path, media_type="image/png")


@router.get("/analyses")
def list_analyses(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                  category: str | None = None, db: Session = Depends(get_db)):
    q = select(AnalysisResult).options(joinedload(AnalysisResult.image), joinedload(AnalysisResult.reports)) \
        .order_by(AnalysisResult.created_at.desc()).limit(limit).offset(offset)
    cq = select(func.count()).select_from(AnalysisResult)
    if category:
        q, cq = q.where(AnalysisResult.category == category), cq.where(AnalysisResult.category == category)
    rows = db.scalars(q).unique().all()
    return {"total": db.scalar(cq), "items": [serialize_analysis(a) for a in rows]}


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    by_status = dict(db.execute(select(AnalysisResult.status, func.count()).group_by(AnalysisResult.status)).all())
    by_cat = dict(db.execute(select(AnalysisResult.category, func.count())
                             .where(AnalysisResult.status == "completed").group_by(AnalysisResult.category)).all())
    flagged = db.scalar(select(func.count()).where(AnalysisResult.summary == "findings_flagged")) or 0
    avg_ms = db.scalar(select(func.avg(AnalysisResult.inference_ms)).where(AnalysisResult.status == "completed"))
    return {
        "total_images": db.scalar(select(func.count()).select_from(MedicalImage)) or 0,
        "completed": by_status.get("completed", 0),
        "failed": by_status.get("failed", 0),
        "reports": db.scalar(select(func.count()).select_from(Report)) or 0,
        "by_category": by_cat,
        "with_flagged_findings": flagged,
        "avg_inference_ms": int(avg_ms) if avg_ms else None,
    }
