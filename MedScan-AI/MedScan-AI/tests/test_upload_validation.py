"""Image upload + validation + security behaviour."""
import io

import numpy as np
from PIL import Image

from backend.config import settings
from tests.conftest import png_bytes

rng = np.random.default_rng(1)


def gray(h=256, w=256):
    return png_bytes((rng.random((h, w)) * 255).astype(np.uint8))


def test_valid_png_upload_returns_metadata(uploader, sample_bytes):
    r = uploader(sample_bytes)
    assert r.status_code == 201
    body = r.json()
    assert body["width"] == 512 and body["format"] == "PNG" and len(body["sha256"]) == 64


def test_valid_jpeg_upload(uploader):
    buf = io.BytesIO()
    Image.fromarray((rng.random((300, 300)) * 255).astype(np.uint8)).save(buf, format="JPEG")
    assert uploader(buf.getvalue(), name="a.jpg", ctype="image/jpeg").status_code == 201


def test_text_file_with_png_extension_rejected(uploader):
    r = uploader(b"this is not an image", name="evil.png")
    assert r.status_code == 415


def test_real_png_with_wrong_extension_and_mime_is_accepted_by_content(uploader):
    # Decision is made on content, not on the client-supplied name/Content-Type
    assert uploader(gray(), name="x.txt", ctype="text/plain").status_code == 201


def test_unsupported_format_gif_rejected(uploader):
    buf = io.BytesIO()
    Image.fromarray(np.zeros((200, 200), np.uint8)).save(buf, format="GIF")
    assert uploader(buf.getvalue(), name="x.gif").status_code == 415


def test_empty_file_rejected(uploader):
    assert uploader(b"").status_code == 422


def test_truncated_png_rejected(uploader, sample_bytes):
    assert uploader(sample_bytes[: len(sample_bytes) // 2]).status_code == 422


def test_colour_photo_rejected(uploader):
    arr = np.zeros((256, 256, 3), np.uint8)
    arr[..., 0], arr[..., 2] = 220, 30
    r = uploader(png_bytes(arr))
    assert r.status_code == 422 and "colour" in r.json()["detail"].lower()


def test_too_small_rejected(uploader):
    assert uploader(gray(32, 32)).status_code == 422


def test_oversized_file_rejected(uploader, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 0)  # 0 MB limit
    assert uploader(gray()).status_code == 413


def test_unknown_category_rejected(uploader):
    assert uploader(gray(), category="mri_knee").status_code == 422


def test_unintegrated_category_is_not_silently_accepted(uploader):
    for cat in ("bone_fracture", "brain_ct"):
        r = uploader(gray(), category=cat)
        assert r.status_code == 501 and "not available" in r.json()["detail"]


def test_missing_file_field_is_422(client):
    assert client.post("/api/upload", data={"category": "chest_xray"}).status_code == 422


def test_stored_file_is_sanitised_png_without_trailing_payload_or_metadata(uploader, client):
    img = Image.fromarray((rng.random((200, 200)) * 255).astype(np.uint8))
    buf = io.BytesIO()
    img.save(buf, format="PNG", pnginfo=__import__("PIL.PngImagePlugin", fromlist=["x"]).PngInfo())
    payload = buf.getvalue() + b"<?php system($_GET['c']); ?>"   # polyglot: valid PNG + appended code
    iid = uploader(payload).json()["image_id"]
    stored = (settings.upload_dir / f"{iid}.png").read_bytes()
    assert b"<?php" not in stored and stored.startswith(b"\x89PNG")
    assert Image.open(io.BytesIO(stored)).mode == "L"


def test_original_filename_is_not_persisted(uploader, client):
    iid = uploader(gray(), name="JOHN_DOE_1970-01-01.png").json()["image_id"]
    assert "JOHN" not in str(client.get(f"/api/images/{iid}/file").headers)
    from backend.database import SessionLocal
    from backend.models.database_models import MedicalImage
    with SessionLocal() as db:
        row = db.get(MedicalImage, iid)
        assert "JOHN" not in " ".join(str(v) for v in row.__dict__.values())


def test_path_traversal_in_image_id_cannot_read_files(client):
    assert client.get("/api/images/..%2F..%2Fetc%2Fpasswd/file").status_code == 404
