"""Common interface for imaging models. Every task (chest X-ray, fracture, brain CT...)
implements ImagingModel; tasks without a verified model use UnavailableModel."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


class ModelUnavailableError(RuntimeError):
    """Raised when a task has no integrated, working model. Never fall back to fake output."""


@dataclass
class ModelCard:
    id: str
    category: str
    display_name: str
    status: str  # "operational" | "not_integrated"
    description: str
    accepted_formats: list[str]
    source: str = ""
    license: str = ""
    reference: str = ""
    limitations: list[str] = field(default_factory=list)
    blocker: str = ""

    def public(self) -> dict:
        return self.__dict__.copy()


@dataclass
class Finding:
    label: str
    score: float          # raw model output in [0, 1]; NOT a calibrated probability
    threshold: float      # operating threshold published with the weights
    flagged: bool


@dataclass
class InferenceOutput:
    findings: list[Finding]
    summary: str          # "findings_flagged" | "no_findings_flagged"
    heatmap_label: str | None = None
    heatmap_overlay: np.ndarray | None = None   # RGB uint8, same view the model saw
    warnings: list[str] = field(default_factory=list)


class ImagingModel(ABC):
    card: ModelCard

    @abstractmethod
    def analyze(self, image_path: Path) -> InferenceOutput: ...


class UnavailableModel(ImagingModel):
    def __init__(self, card: ModelCard):
        self.card = card

    def analyze(self, image_path: Path) -> InferenceOutput:
        raise ModelUnavailableError(f"{self.card.display_name} is not integrated: {self.card.blocker}")
