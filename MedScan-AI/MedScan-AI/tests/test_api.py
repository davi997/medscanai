"""REST API behaviour: health, analyze, retrieval, listing, report, errors, DB state."""
import numpy as np
from pypdf import PdfReader
import io

from backend.database import SessionLocal
from backend.models.database_models import AnalysisHistory, AnalysisResult, MedicalImage
from tests.conftest import png_bytes


def analyze_sample(uploader, client, sample_bytes):
    iid = uploader(sample_bytes).json()["image_id"]
    return client.post("/api/analyze", json={"image_id": iid})


def test_health_reports_database_and_honest_model_status(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["database"] == "up"
    status = {m["category"]: m["status"] for m in h["models"]}
    assert status == {"chest_xray": "operational", "bone_fracture": "not_integrated", "brain_ct": "not_integrated"}


def test_categories_expose_blockers(client):
    cats = {c["category"]: c for c in client.get("/api/categories").json()}
    assert cats["bone_fracture"]["blocker"] and cats["chest_xray"]["accepted_formats"] == ["PNG", "JPEG"]


def test_full_analysis_flow(uploader, client, sample_bytes):
    r = analyze_sample(uploader, client, sample_bytes)
    assert r.status_code == 200
    a = r.json()
    assert a["status"] == "completed" and a["result_type"] == "model_inference"
    assert len(a["findings"]) == 18
    assert all(0.0 <= f["score"] <= 1.0 for f in a["findings"])
    assert a["heatmap"] and client.get(a["heatmap"]["url"]).headers["content-type"] == "image/png"
    assert "not probabilities" in a["score_note"]
    again = client.get(f"/api/analysis/{a['id']}").json()
    assert again["findings"] == a["findings"]


def test_analysis_history_audit_trail(uploader, client, sample_bytes):
    aid = analyze_sample(uploader, client, sample_bytes).json()["id"]
    with SessionLocal() as db:
        events = [h.event for h in db.query(AnalysisHistory).filter_by(analysis_id=aid).order_by(AnalysisHistory.id)]
    assert events == ["created", "started", "completed"]


def test_analyze_unknown_image_404(client):
    assert client.post("/api/analyze", json={"image_id": "00000000-0000-0000-0000-000000000000"}).status_code == 404


def test_analyze_malformed_id_422(client):
    assert client.post("/api/analyze", json={"image_id": "../../etc/passwd"}).status_code == 422
    assert client.post("/api/analyze", json={}).status_code == 422


def test_blank_image_fails_honestly_and_is_recorded(uploader, client):
    iid = uploader(png_bytes(np.full((256, 256), 128, np.uint8))).json()["image_id"]
    r = client.post("/api/analyze", json={"image_id": iid})
    assert r.status_code == 422 and "contrast" in r.json()["detail"]
    with SessionLocal() as db:
        row = db.query(AnalysisResult).filter_by(image_id=iid).one()
        assert row.status == "failed" and row.findings is None and row.top_score is None  # no fabricated result
    assert client.get("/api/report/" + row.id).status_code == 409


def test_get_unknown_analysis_404(client):
    assert client.get("/api/analysis/nope").status_code == 404
    assert client.get("/api/report/nope").status_code == 404


def test_list_and_pagination(uploader, client, sample_bytes):
    analyze_sample(uploader, client, sample_bytes)
    d = client.get("/api/analyses?limit=1").json()
    assert d["total"] >= 1 and len(d["items"]) == 1
    assert client.get("/api/analyses?limit=0").status_code == 422
    assert client.get("/api/analyses?limit=1000").status_code == 422


def test_stats(client):
    s = client.get("/api/stats").json()
    assert {"total_images", "completed", "failed", "reports", "by_category"} <= s.keys()


def test_pdf_report_contains_required_content(uploader, client, sample_bytes):
    a = analyze_sample(uploader, client, sample_bytes).json()
    r = client.get(f"/api/report/{a['id']}")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    text = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    text = " ".join(text.split())
    assert "MedScan AI" in text and a["id"] in text
    assert ("This AI-generated result is intended for research and educational assistance only. "
            "It is not a definitive medical diagnosis and must be reviewed by a qualified medical professional.") in text
    assert "not calibrated probabilities" in text and "densenet121-res224-all" in a["model"]["source"]
    assert client.get(f"/api/analysis/{a['id']}").json()["has_report"] is True


def test_unhandled_routes_and_methods(client):
    assert client.get("/api/nope").status_code == 404
    assert client.put("/api/upload").status_code in (404, 405)


def test_security_headers(client):
    h = client.get("/api/health").headers
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
