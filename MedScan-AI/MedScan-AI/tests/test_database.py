"""ORM relationships and constraints (runs on SQLite; set TEST_POSTGRES_URL to also run on PostgreSQL)."""
import os

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models import database_models as m

_PG = os.environ.get("TEST_POSTGRES_URL")
# ORM tests drop/create tables, so they use a separate database from the API tests: <name>_orm
URLS = ["sqlite://"] + ([_PG.rsplit("/", 1)[0] + "/medscan_test_orm"] if _PG else [])


@pytest.fixture(params=URLS, ids=lambda u: u.split(":")[0])
def db(request):
    eng = create_engine(request.param)
    if eng.dialect.name == "sqlite":
        from sqlalchemy import event
        event.listen(eng, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.drop_all(eng); Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng, expire_on_commit=False)()
    yield s
    s.close(); Base.metadata.drop_all(eng)


def make_image(db):
    img = m.MedicalImage(category="chest_xray", stored_path="x.png", sha256="a" * 64, width=256, height=256, size_bytes=1, source_format="PNG")
    db.add(img); db.commit()
    return img


def test_tables_exist(db):
    assert {"medical_images", "analysis_results", "reports", "analysis_history"} <= set(inspect(db.get_bind()).get_table_names())


def test_relationships_and_cascade(db):
    img = make_image(db)
    a = m.AnalysisResult(image_id=img.id, category="chest_xray", model_id="t")
    db.add(a); db.flush()
    db.add_all([m.Report(analysis_id=a.id, file_path="r.pdf"), m.AnalysisHistory(analysis_id=a.id, event="created")]); db.commit()
    assert db.get(m.AnalysisResult, a.id).image.id == img.id and len(a.reports) == 1 and len(a.history) == 1
    db.delete(img); db.commit()
    assert db.query(m.AnalysisResult).count() == 0 and db.query(m.Report).count() == 0 and db.query(m.AnalysisHistory).count() == 0


def test_json_fields_roundtrip(db):
    img = make_image(db)
    a = m.AnalysisResult(image_id=img.id, category="chest_xray", model_id="t", findings=[{"label": "X", "score": 0.5}], warnings=["w"])
    db.add(a); db.commit(); db.expire_all()
    assert db.get(m.AnalysisResult, a.id).findings[0]["label"] == "X"


def test_foreign_key_enforced(db):
    db.add(m.AnalysisResult(image_id="does-not-exist", category="c", model_id="t"))
    with pytest.raises(Exception):
        db.commit()
