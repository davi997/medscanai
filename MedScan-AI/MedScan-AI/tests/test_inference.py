"""Tests of the real AI module (loads the actual TorchXRayVision weights)."""
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from backend.models.ai_models.base import ModelUnavailableError
from backend.models.ai_models.registry import get_model

SAMPLE = Path(__file__).parent / "data" / "sample_cxr.png"


@pytest.fixture(scope="module")
def model():
    return get_model("chest_xray")


@pytest.fixture(scope="module")
def baseline(model):
    return model.analyze(SAMPLE)


def test_model_is_the_documented_one(model):
    assert model.net.weights == "densenet121-res224-all"
    assert len(model.labels) == 18 and "Pneumonia" in model.labels and "Cardiomegaly" in model.labels
    assert len(model.thresholds) == 18 and all(0 < t < 1 for t in model.thresholds)


def test_output_structure_and_ranges(baseline):
    assert len(baseline.findings) == 18
    assert all(0 <= f.score <= 1 and 0 < f.threshold < 1 for f in baseline.findings)
    assert all(f.flagged == (f.score >= f.threshold) for f in baseline.findings)
    assert baseline.summary in ("findings_flagged", "no_findings_flagged")
    assert baseline.heatmap_overlay.shape == (224, 224, 3) and baseline.heatmap_overlay.std() > 5


def test_regression_reference_scores(baseline):
    """Reference values from the first verified run; catches preprocessing/weight regressions."""
    s = {f.label: f.score for f in baseline.findings}
    assert s["Cardiomegaly"] == pytest.approx(0.281, abs=0.01)
    assert s["Fibrosis"] == pytest.approx(0.090, abs=0.01)


def test_deterministic(model, baseline):
    again = model.analyze(SAMPLE)
    assert [f.score for f in again.findings] == [f.score for f in baseline.findings]


def test_outputs_depend_on_the_image_not_constant(model, baseline, tmp_path):
    """Guards against hard-coded / fake predictions."""
    arr = np.asarray(Image.open(SAMPLE).convert("L"))
    for name, mod in {"flip": arr[::-1, :], "dark": (arr * 0.3).astype(np.uint8),
                      "noise": (np.random.default_rng(0).random(arr.shape) * 255).astype(np.uint8)}.items():
        p = tmp_path / f"{name}.png"
        Image.fromarray(mod).save(p)
        other = {f.label: f.score for f in model.analyze(p).findings}
        base = {f.label: f.score for f in baseline.findings}
        assert max(abs(other[k] - base[k]) for k in base) > 0.01, name


def test_blank_image_rejected_instead_of_scored(model, tmp_path):
    p = tmp_path / "blank.png"
    Image.fromarray(np.full((300, 300), 200, np.uint8)).save(p)
    with pytest.raises(ValueError):
        model.analyze(p)


def test_corrupt_file_raises(model, tmp_path):
    p = tmp_path / "bad.png"
    p.write_bytes(b"garbage")
    with pytest.raises(ValueError):
        model.analyze(p)


@pytest.mark.parametrize("cat", ["bone_fracture", "brain_ct"])
def test_unintegrated_models_never_return_results(cat, tmp_path):
    m = get_model(cat)
    assert m.card.status == "not_integrated" and m.card.blocker
    with pytest.raises(ModelUnavailableError):
        m.analyze(tmp_path / "x.png")


def test_evaluation_results_file_has_real_metrics_if_present():
    f = Path(__file__).parent.parent / "docs" / "evaluation_results.json"
    if not f.exists():
        pytest.skip("run `python -m tests.evaluate_model` first")
    r = json.loads(f.read_text())
    for lab in r["labels"].values():
        assert {"accuracy", "precision", "recall_sensitivity", "f1", "auc", "confusion"} <= lab.keys()
    assert r["n"] == r["n_positive_pneumonia"] + r["n_negative_no_finding"]
