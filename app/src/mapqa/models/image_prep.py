"""Prepare one image per source file so every model receives identical bytes (ADR-003 §3.2, D-003-7)."""

from __future__ import annotations

import hashlib
import io
import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

IMAGE_PREP_VERSION = "image_prep.v2"
# Jev docs say 256 px per side, but a real request with a 274×287 crop returned HTTP 400
# "Invalid image dimensions" (capture 2026-11-13). 78 400 px = 280², so we require 280 px per side.
MIN_SIDE = 280
MAX_SIDE = 1568
MIN_PIXELS = 78_400
MAX_PIXELS = 2_458_624
MAX_BYTES = 16 * 1024 * 1024
JPEG_QUALITY = 92
ALLOWED_FORMATS = ("PNG", "JPEG")


class ImageOutOfBounds(Exception):
    """Image cannot be brought within Jev limits; maps to final_status image_out_of_bounds."""


@dataclass(frozen=True)
class PreparedImage:
    data: bytes
    mime: str
    source_sha256: str


def prepare_image(path: Path) -> PreparedImage:
    try:
        raw = path.read_bytes()
    except OSError as exc:  # deleted/locked/unreadable after loading: per-photo failure, not a run abort
        raise ImageOutOfBounds(f"unreadable file: {type(exc).__name__}") from exc
    source_sha256 = hashlib.sha256(raw).hexdigest()
    try:
        src = Image.open(io.BytesIO(raw))
        fmt = src.format
        src.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageOutOfBounds("unreadable image") from exc
    if fmt not in ALLOWED_FORMATS:
        raise ImageOutOfBounds(f"unsupported format: {fmt}")

    img = ImageOps.exif_transpose(src).convert("RGB")
    target = _target_size(*img.size)
    if target != img.size:
        img = img.resize(target, Image.Resampling.LANCZOS)
    if not _within_limits(*img.size):
        raise ImageOutOfBounds(f"size {img.size[0]}x{img.size[1]} outside Jev limits")

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=JPEG_QUALITY)
    data = buffer.getvalue()
    if len(data) > MAX_BYTES:
        raise ImageOutOfBounds("prepared image exceeds 16 MiB")
    return PreparedImage(data=data, mime="image/jpeg", source_sha256=source_sha256)


def _target_size(width: int, height: int) -> tuple[int, int]:
    """Upscale until BOTH minima hold (short side ≥ 256 and pixels ≥ 78 400), or downscale the long side to 1568.

    Upscaling only the short side to 256 would leave square sign crops at 256×256 = 65 536 px,
    below Jev's pixel minimum (78 400 = 280²); this rejected 105 of 119 course crops.
    """
    short, long = min(width, height), max(width, height)
    if short < MIN_SIDE or width * height < MIN_PIXELS:
        scale = max(MIN_SIDE / short, math.sqrt(MIN_PIXELS / (width * height)))
        new_w, new_h = math.ceil(width * scale), math.ceil(height * scale)
        return new_w, new_h
    if long > MAX_SIDE:
        scale = MAX_SIDE / long
        return min(MAX_SIDE, round(width * scale)), min(MAX_SIDE, round(height * scale))
    return width, height


def _within_limits(width: int, height: int) -> bool:
    sides_ok = MIN_SIDE <= min(width, height) and max(width, height) <= MAX_SIDE
    return sides_ok and MIN_PIXELS <= width * height <= MAX_PIXELS
