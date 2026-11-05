"""Model registry: maps an imaging category to a model. Add new tasks here."""
from __future__ import annotations

import threading

from backend.models.ai_models.base import ImagingModel, ModelCard, UnavailableModel

_BLOCKED = {
    "bone_fracture": ModelCard(
        id="bone-fracture-none", category="bone_fracture", display_name="Bone fracture detection",
        status="not_integrated",
        description="Planned module for musculoskeletal radiographs.",
        accepted_formats=[],
        blocker="No pre-trained fracture-detection model has been verified (weights availability, licence, "
                "validation) and integrated in this version. Candidates must be evaluated before use.",
    ),
    "brain_ct": ModelCard(
        id="brain-ct-none", category="brain_ct", display_name="Brain CT analysis",
        status="not_integrated",
        description="Planned module for non-contrast head CT.",
        accepted_formats=[],
        blocker="No pre-trained brain CT model has been verified and integrated. CT also needs DICOM/NIfTI "
                "volume handling and windowing, which this version does not implement.",
    ),
}

_instances: dict[str, ImagingModel] = {}
_lock = threading.Lock()


def categories() -> list[ModelCard]:
    from backend.models.ai_models.chest_xray import CARD

    return [CARD, *_BLOCKED.values()]


def get_card(category: str) -> ModelCard | None:
    return next((c for c in categories() if c.category == category), None)


def get_model(category: str) -> ImagingModel:
    """Return the (lazily loaded, cached) model for a category."""
    with _lock:
        if category in _instances:
            return _instances[category]
        if category == "chest_xray":
            from backend.models.ai_models.chest_xray import ChestXrayModel

            _instances[category] = ChestXrayModel()
        elif category in _BLOCKED:
            _instances[category] = UnavailableModel(_BLOCKED[category])
        else:
            raise KeyError(category)
        return _instances[category]
