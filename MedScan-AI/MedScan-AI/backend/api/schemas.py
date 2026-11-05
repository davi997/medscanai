from datetime import datetime

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    image_id: str = Field(min_length=36, max_length=36, pattern=r"^[0-9a-fA-F-]{36}$")


def serialize_analysis(a) -> dict:
    img = a.image
    return {
        "id": a.id,
        "result_type": "model_inference",  # only real inference is ever stored; see docs/ARCHITECTURE.md
        "status": a.status,
        "category": a.category,
        "image": {"id": img.id, "width": img.width, "height": img.height, "format": img.source_format,
                  "sha256": img.sha256, "uploaded_at": img.uploaded_at.isoformat(),
                  "url": f"/api/images/{img.id}/file"},
        "model": a.model_info,
        "summary": a.summary,
        "top_finding": a.top_finding,
        "findings": a.findings,
        "warnings": a.warnings or [],
        "heatmap": {"label": a.heatmap_label, "url": f"/api/analysis/{a.id}/heatmap"} if a.heatmap_path else None,
        "score_note": "Scores are uncalibrated model outputs (0-1), not probabilities of disease.",
        "error": a.error_message,
        "inference_ms": a.inference_ms,
        "created_at": a.created_at.isoformat(),
        "completed_at": a.completed_at.isoformat() if a.completed_at else None,
        "has_report": len(a.reports) > 0,
    }
