"""Test fixtures. Env vars are set BEFORE the backend is imported so tests never touch real data."""
import io
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="medscan_test_"))
# Set TEST_POSTGRES_URL to run the whole API suite against PostgreSQL instead of SQLite
os.environ["DATABASE_URL"] = os.environ.get("TEST_POSTGRES_URL") or f"sqlite:///{_TMP}/test.db"
os.environ["STORAGE_DIR"] = str(_TMP / "storage")
os.environ["MODEL_CACHE_DIR"] = str(Path(__file__).resolve().parent.parent / "storage" / "model_cache")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from backend.main import app  # noqa: E402

SAMPLE = Path(__file__).parent / "data" / "sample_cxr.png"


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def png_bytes(arr: np.ndarray, mode=None) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr, mode).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def sample_bytes() -> bytes:
    return SAMPLE.read_bytes()


@pytest.fixture
def uploader(client):
    def _up(data: bytes, category="chest_xray", name="scan.png", ctype="image/png"):
        return client.post("/api/upload", data={"category": category}, files={"file": (name, data, ctype)})
    return _up
