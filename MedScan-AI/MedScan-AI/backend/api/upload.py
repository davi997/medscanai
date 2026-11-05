from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models.ai_models.registry import categories, get_card
from backend.models.database_models import MedicalImage
from backend.services.image_processing import ImageValidationError, validate_and_store

router = APIRouter(prefix="/api", tags=["upload"])


@router.get("/categories")
def list_categories():
    """Imaging tasks with honest status ('operational' vs 'not_integrated')."""
    return [c.public() for c in categories()]


@router.post("/upload", status_code=201)
async def upload(category: str = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db)):
    card = get_card(category)
    if card is None:
        raise HTTPException(422, f"Unknown imaging category '{category}'.")
    if card.status != "operational":
        raise HTTPException(501, f"{card.display_name} is not available yet: {card.blocker}")
    data = await file.read(settings.max_upload_bytes + 1)  # never buffer more than limit + 1 byte
    try:
        stored = validate_and_store(data, card.accepted_formats)
    except ImageValidationError as e:
        raise HTTPException(e.status_code, e.message)
    row = MedicalImage(id=stored.id, category=category, stored_path=stored.path.name, sha256=stored.sha256,
                       width=stored.width, height=stored.height, size_bytes=stored.size_bytes,
                       source_format=stored.source_format)
    db.add(row)
    db.commit()
    return {"image_id": row.id, "category": category, "width": row.width, "height": row.height,
            "format": row.source_format, "sha256": row.sha256, "uploaded_at": row.uploaded_at.isoformat()}


@router.get("/images/{image_id}/file")
def image_file(image_id: str, db: Session = Depends(get_db)):
    img = db.get(MedicalImage, image_id)
    if not img:
        raise HTTPException(404, "Image not found.")
    return FileResponse(settings.upload_dir / img.stored_path, media_type="image/png",
                        headers={"Cache-Control": "private, max-age=3600"})
