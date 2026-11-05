"""Secure upload handling: validate, sanitise (re-encode) and store images.

Defences: size cap, magic-byte sniffing (extension and Content-Type are ignored),
full decode (rejects truncated/corrupt files), pixel-count cap (decompression bombs),
server-generated filenames (no path traversal), and re-encoding to plain grayscale
PNG which drops EXIF/ICC/text chunks and any appended payloads.
"""
from __future__ import annotations

import hashlib
import io
import uuid
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError

from backend.config import settings

Image.MAX_IMAGE_PIXELS = 64_000_000  # Pillow raises DecompressionBombError above 2x this

_MAGIC = {b"\x89PNG\r\n\x1a\n": "PNG", b"\xff\xd8\xff": "JPEG"}


class ImageValidationError(Exception):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class StoredImage:
    id: str
    path: Path
    sha256: str
    width: int
    height: int
    size_bytes: int
    source_format: str


def sniff_format(data: bytes) -> str | None:
    for magic, name in _MAGIC.items():
        if data.startswith(magic):
            return name
    return None


def _to_gray8(img: Image.Image) -> Image.Image:
    if img.mode in ("I;16", "I;16L", "I;16B", "I"):
        a = np.asarray(img).astype(np.float32)
        lo, hi = float(a.min()), float(a.max())
        a = (a - lo) / (hi - lo + 1e-8) * 255
        return Image.fromarray(a.astype(np.uint8), "L")
    if img.mode in ("L",):
        return img
    if img.mode in ("LA", "P", "PA", "1"):
        img = img.convert("RGBA" if "transparency" in img.info or img.mode in ("LA", "PA") else "RGB")
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (0, 0, 0))
        bg.paste(img, mask=img.split()[3])
        img = bg
    if img.mode == "RGB":
        a = np.asarray(img).astype(np.int16)
        colourfulness = float(np.abs(a[..., 0] - a[..., 1]).mean() + np.abs(a[..., 1] - a[..., 2]).mean())
        if colourfulness > 12:
            raise ImageValidationError(
                "This looks like a colour image. Radiographs are grayscale; upload the original X-ray image, not a photo or screenshot."
            )
        return img.convert("L")
    raise ImageValidationError(f"Unsupported image mode: {img.mode}")


def validate_and_store(data: bytes, allowed_formats: list[str]) -> StoredImage:
    if not data:
        raise ImageValidationError("The uploaded file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise ImageValidationError(f"File is larger than the {settings.max_upload_mb} MB limit.", 413)
    fmt = sniff_format(data)
    if fmt is None:
        raise ImageValidationError("Unsupported file type. Accepted formats: " + ", ".join(allowed_formats) + ".", 415)
    if fmt not in allowed_formats:
        raise ImageValidationError(f"{fmt} is not accepted for this imaging task. Accepted: {', '.join(allowed_formats)}.", 415)
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, ValueError):
        raise ImageValidationError("The file is corrupted or is not a valid image.")
    w, h = img.size
    if min(w, h) < settings.min_image_side_px:
        raise ImageValidationError(f"Image is too small ({w}x{h}). Minimum side is {settings.min_image_side_px}px.")
    if max(w, h) > settings.max_image_side_px:
        raise ImageValidationError(f"Image is too large ({w}x{h}). Maximum side is {settings.max_image_side_px}px.")
    gray = _to_gray8(img)

    settings.ensure_dirs()
    image_id = str(uuid.uuid4())
    path = settings.upload_dir / f"{image_id}.png"
    gray.save(path, format="PNG")  # fresh encode: no metadata carried over
    return StoredImage(image_id, path, hashlib.sha256(data).hexdigest(), w, h, len(data), fmt)
