"""Chest X-ray module: TorchXRayVision DenseNet-121 ("densenet121-res224-all").

Verified facts (from the installed package source / project docs):
- Library: https://github.com/mlmed/torchxrayvision (Apache-2.0 per package metadata)
- Weights: GitHub release asset, downloaded automatically on first use.
- Trained on: NIH, PadChest, CheXpert, MIMIC-CXR, Google, OpenI, RSNA (arXiv:2002.02497).
- Output: 18 independent (multi-label) pathology scores. There is no "normal" class.
- Input: single-channel frontal chest radiograph, 224x224, intensities scaled to [-1024, 1024].
"""
from __future__ import annotations

import threading
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F

from backend.config import settings
from backend.models.ai_models.base import Finding, ImagingModel, InferenceOutput, ModelCard

WEIGHTS = "densenet121-res224-all"

CARD = ModelCard(
    id="xrv-densenet121-res224-all",
    category="chest_xray",
    display_name="Chest X-ray pathology screening (TorchXRayVision DenseNet-121)",
    status="operational",
    description="Multi-label DenseNet-121 trained on seven public chest X-ray datasets. "
                "Outputs one score per pathology label; it has no 'normal' class.",
    accepted_formats=["PNG", "JPEG"],
    source="https://github.com/mlmed/torchxrayvision (weights: 'densenet121-res224-all')",
    license="Library: Apache-2.0. Check the licence terms of the underlying datasets before any clinical or commercial use.",
    reference="Cohen JP et al., arXiv:2002.02497; Cohen JP et al., MIDL 2022 (TorchXRayVision).",
    limitations=[
        "Designed for frontal (PA/AP) adult chest radiographs only.",
        "Scores are uncalibrated model outputs, not probabilities of disease.",
        "Cannot verify that the uploaded image really is a chest X-ray; other images still receive scores.",
        "Performance varies across hospitals, devices and populations and was not validated for clinical use here.",
        "'Fracture' in this model refers to findings visible on chest films (e.g. ribs), not limb fracture detection.",
        "Grad-CAM shows where the network looked, not a verified lesion location.",
    ],
)


class ChestXrayModel(ImagingModel):
    card = CARD

    def __init__(self):
        import torchxrayvision as xrv  # imported lazily: heavy

        self._xrv = xrv
        self._lock = threading.Lock()
        self.net = xrv.models.DenseNet(weights=WEIGHTS, cache_dir=str(settings.model_cache_dir))
        self.net.eval()
        self.labels: list[str] = list(self.net.pathologies)
        self.thresholds = [float(t) for t in self.net.op_threshs.tolist()]
        self._tf = __import__("torchvision").transforms.Compose(
            [xrv.datasets.XRayCenterCrop(), xrv.datasets.XRayResizer(224)]
        )

    # ---- preprocessing -------------------------------------------------
    def preprocess(self, image_path: Path) -> tuple[torch.Tensor, np.ndarray, list[str]]:
        warnings: list[str] = []
        gray = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if gray is None:
            raise ValueError("Image could not be decoded.")
        if gray.std() < 5:
            raise ValueError("Image has almost no contrast; it cannot be a usable radiograph.")
        h, w = gray.shape
        if max(h, w) / min(h, w) > 1.6:
            warnings.append("Unusual aspect ratio; the image was centre-cropped to a square, which may remove anatomy.")
        arr = self._xrv.datasets.normalize(gray, 255)[None, ...]   # -> [-1024, 1024], (1, H, W)
        arr = self._tf(arr)                                         # centre-crop + resize to 224
        view = np.clip((arr[0] + 1024) / 2048 * 255, 0, 255).astype(np.uint8)
        return torch.from_numpy(arr).unsqueeze(0).float(), view, warnings

    # ---- inference + Grad-CAM ------------------------------------------
    def _forward(self, x: torch.Tensor):
        feats = self.net.features(x)
        feats.retain_grad()
        pooled = F.adaptive_avg_pool2d(F.relu(feats), (1, 1)).flatten(1)
        logits = self.net.classifier(pooled)
        return feats, logits

    def analyze(self, image_path: Path) -> InferenceOutput:
        x, view, warnings = self.preprocess(image_path)
        with self._lock:  # model object is shared across requests
            x.requires_grad_(False)
            feats, logits = self._forward(x)
            probs = torch.sigmoid(logits)[0].detach().numpy()

            findings = []
            for lbl, p, t in zip(self.labels, probs, self.thresholds):
                if not lbl or np.isnan(t):
                    continue
                findings.append(Finding(label=lbl, score=float(p), threshold=t, flagged=bool(p >= t)))
            findings.sort(key=lambda f: f.score / f.threshold, reverse=True)

            # Grad-CAM for the label whose score is highest relative to its threshold
            top = findings[0]
            idx = self.labels.index(top.label)
            self.net.zero_grad()
            logits[0, idx].backward()
            weights = feats.grad.mean(dim=(2, 3), keepdim=True)
            cam = F.relu((weights * feats).sum(dim=1, keepdim=True))
            cam = F.interpolate(cam, size=view.shape, mode="bilinear", align_corners=False)[0, 0].detach().numpy()

        cam = (cam - cam.min()) / (cam.max() - cam.min() + 1e-8)
        heat = cv2.applyColorMap((cam * 255).astype(np.uint8), cv2.COLORMAP_JET)[:, :, ::-1]
        base = np.repeat(view[:, :, None], 3, axis=2)
        overlay = (0.55 * base + 0.45 * heat).astype(np.uint8)

        any_flag = any(f.flagged for f in findings)
        warnings.append("The system cannot verify that this is a frontal chest radiograph; scores are meaningless otherwise.")
        return InferenceOutput(
            findings=findings,
            summary="findings_flagged" if any_flag else "no_findings_flagged",
            heatmap_label=top.label,
            heatmap_overlay=overlay,
            warnings=warnings,
        )
