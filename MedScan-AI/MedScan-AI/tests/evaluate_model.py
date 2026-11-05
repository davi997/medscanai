"""Independent evaluation of the chest X-ray model on a public labelled dataset.

Data: ieee8023/covid-chestxray-dataset (GitHub). It is NOT among the datasets listed as
training data for the 'densenet121-res224-all' weights (nih, pc, chex, mimic_ch, google, openi, rsna).
Per-image licences vary (mostly CC BY / CC BY-NC-SA): images are downloaded to a git-ignored cache
for evaluation only and are never redistributed with this project.

Task (fixed BEFORE looking at any result):
  positive = metadata 'finding' starts with 'Pneumonia'   negative = 'No Finding'
  frontal PA/AP-erect X-rays only (matches the model's intended input).
  Prediction rule A: the model's 'Pneumonia' score >= its published operating threshold.
  Prediction rule B: the model's 'Lung Opacity' score >= its published operating threshold.
  AUC is computed from the raw scores of the same two labels.
  Sampling: all negatives + up to 3x as many positives, random_state=0.

Usage:  python -m tests.evaluate_model            (writes docs/evaluation_results.json)
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "tests" / "data" / "eval_cache"
BASE = "https://raw.githubusercontent.com/ieee8023/covid-chestxray-dataset/master/"


def fetch(rel: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    try:
        with urllib.request.urlopen(BASE + rel, timeout=40) as r:
            dest.write_bytes(r.read())
        return True
    except Exception as e:  # noqa: BLE001
        print("download failed", rel, e, file=sys.stderr)
        return False


def build_sample() -> pd.DataFrame:
    CACHE.mkdir(parents=True, exist_ok=True)
    meta_path = CACHE / "metadata.csv"
    fetch("metadata.csv", meta_path)
    d = pd.read_csv(meta_path)
    d = d[(d.modality == "X-ray") & d.view.isin(["PA", "AP Erect"])].copy()
    d["label"] = np.where(d.finding.str.startswith("Pneumonia"), 1, np.where(d.finding == "No Finding", 0, -1))
    d = d[d.label >= 0]
    neg, pos = d[d.label == 0], d[d.label == 1]
    pos = pos.sample(n=min(len(pos), 3 * len(neg)), random_state=0)
    return pd.concat([neg, pos]).reset_index(drop=True)


def boot_ci(y, s, fn, n=1000, seed=0):
    rng, vals = np.random.default_rng(seed), []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        if len(set(y[i])) < 2:
            continue
        vals.append(fn(y[i], s[i]))
    return [round(float(np.percentile(vals, 2.5)), 3), round(float(np.percentile(vals, 97.5)), 3)]


def main():
    from backend.models.ai_models.registry import get_model

    sample = build_sample()
    model = get_model("chest_xray")
    idx = {l: i for i, l in enumerate(model.labels)}
    rows, t0 = [], time.time()
    for _, r in sample.iterrows():
        p = CACHE / r.filename
        if not fetch(f"{r.folder}/{r.filename}", p):
            continue
        try:
            x, _, _ = model.preprocess(p)
            import torch
            with torch.no_grad():
                probs = torch.sigmoid(model.net.classifier(torch.nn.functional.adaptive_avg_pool2d(
                    torch.relu(model.net.features(x)), 1).flatten(1)))[0].numpy()
        except Exception as e:  # noqa: BLE001
            print("skip", r.filename, e, file=sys.stderr)
            continue
        rows.append({"file": r.filename, "label": int(r.label), "pneumonia": float(probs[idx["Pneumonia"]]),
                     "lung_opacity": float(probs[idx["Lung Opacity"]])})
    df = pd.DataFrame(rows)
    y = df.label.to_numpy()
    result = {"dataset": "ieee8023/covid-chestxray-dataset (PA / AP Erect X-rays)", "n": int(len(df)),
              "n_positive_pneumonia": int(y.sum()), "n_negative_no_finding": int((1 - y).sum()),
              "seconds": round(time.time() - t0, 1), "labels": {}}
    for key, name in (("pneumonia", "Pneumonia"), ("lung_opacity", "Lung Opacity")):
        s = df[key].to_numpy()
        thr = model.thresholds[idx[name]]
        pred = (s >= thr).astype(int)
        tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
        result["labels"][name] = {
            "operating_threshold": round(thr, 4),
            "accuracy": round(accuracy_score(y, pred), 3),
            "precision": round(precision_score(y, pred, zero_division=0), 3),
            "recall_sensitivity": round(recall_score(y, pred), 3),
            "specificity": round(tn / (tn + fp), 3) if (tn + fp) else None,
            "f1": round(f1_score(y, pred, zero_division=0), 3),
            "auc": round(roc_auc_score(y, s), 3), "auc_95ci_bootstrap": boot_ci(y, s, roc_auc_score),
            "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        }
    result["caveats"] = [
        "Small, class-imbalanced sample; confidence intervals are wide.",
        "Images come from published case reports/papers (selection bias), mixed devices and quality.",
        "'Pneumonia' vs 'No Finding' is a proxy task: the model's labels are not identical to this dataset's labels.",
        "Dataset independence from the training data is based on the weights' documentation, not verified by this project.",
        "This is not a clinical validation.",
    ]
    out = ROOT / "docs" / "evaluation_results.json"
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
