"""Orchestrates an analysis: loads the model for the category, runs it, stores artefacts."""
from __future__ import annotations

import time
from datetime import datetime, timezone

import cv2
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.ai_models.base import ModelUnavailableError
from backend.models.ai_models.registry import get_model
from backend.models.database_models import AnalysisHistory, AnalysisResult, MedicalImage


class AnalysisError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.message, self.status_code = message, status_code


def _log(db: Session, analysis: AnalysisResult, event: str, detail: str | None = None) -> None:
    db.add(AnalysisHistory(analysis_id=analysis.id, event=event, detail=detail))


def run_analysis(db: Session, image: MedicalImage) -> AnalysisResult:
    try:
        model = get_model(image.category)
    except KeyError:
        raise AnalysisError(f"Unknown imaging category '{image.category}'.", 422)
    card = model.card
    if card.status != "operational":
        # No analysis row is created: nothing was analysed, so nothing may be reported.
        raise AnalysisError(f"{card.display_name} is not available: {card.blocker}", 501)

    analysis = AnalysisResult(image_id=image.id, category=image.category, status="pending",
                              model_id=card.id, model_info=card.public())
    db.add(analysis)
    db.flush()
    _log(db, analysis, "created")
    _log(db, analysis, "started")
    db.commit()

    t0 = time.perf_counter()
    try:
        out = model.analyze(settings.upload_dir / f"{image.id}.png")
    except ModelUnavailableError as e:
        return _fail(db, analysis, str(e), 501)
    except ValueError as e:  # unusable input (blank, undecodable...)
        return _fail(db, analysis, str(e), 422)
    except Exception as e:  # noqa: BLE001 - model/weights failures must surface, never be masked
        return _fail(db, analysis, f"Model inference failed: {type(e).__name__}: {e}", 500)

    heat_path = None
    if out.heatmap_overlay is not None:
        heat_path = settings.output_dir / f"{analysis.id}_gradcam.png"
        settings.ensure_dirs()
        big = cv2.resize(out.heatmap_overlay, (512, 512), interpolation=cv2.INTER_CUBIC)  # display size only
        cv2.imwrite(str(heat_path), big[:, :, ::-1])

    top = out.findings[0]
    analysis.status = "completed"
    analysis.findings = [f.__dict__ for f in out.findings]
    analysis.summary = out.summary
    analysis.top_finding, analysis.top_score = top.label, top.score
    analysis.warnings = out.warnings
    analysis.heatmap_path = str(heat_path) if heat_path else None
    analysis.heatmap_label = out.heatmap_label
    analysis.inference_ms = int((time.perf_counter() - t0) * 1000)
    analysis.completed_at = datetime.now(timezone.utc)
    _log(db, analysis, "completed", f"{analysis.inference_ms} ms")
    db.commit()
    return analysis


def _fail(db: Session, analysis: AnalysisResult, message: str, status: int):
    analysis.status = "failed"
    analysis.error_message = message
    analysis.completed_at = datetime.now(timezone.utc)
    _log(db, analysis, "failed", message)
    db.commit()
    raise AnalysisError(message, status)
