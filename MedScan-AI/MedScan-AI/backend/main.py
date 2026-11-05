"""MedScan AI - FastAPI application. Run: uvicorn backend.main:app"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from backend.api import analysis, reports, upload
from backend.config import ROOT_DIR, settings
from backend.database import SessionLocal, init_db
from backend.models.ai_models.registry import categories

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("medscan")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    init_db()
    yield


app = FastAPI(title="MedScan AI", version="1.0.0", lifespan=lifespan,
              description="AI-assisted medical imaging analysis. Research and educational use only.")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.allowed_origins.split(",")],
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    return resp


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s", request.url.path)
    return JSONResponse({"detail": "Internal server error."}, status_code=500)


@app.get("/api/health", tags=["system"])
def health():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": "up" if db_ok else "down",
            "limits": {"max_upload_mb": settings.max_upload_mb},
            "models": [{"category": c.category, "status": c.status, "name": c.display_name} for c in categories()]}


app.include_router(upload.router)
app.include_router(analysis.router)
app.include_router(reports.router)
app.mount("/", StaticFiles(directory=ROOT_DIR / "frontend", html=True), name="frontend")
