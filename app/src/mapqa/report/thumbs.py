"""Thumbnails copied into the run directory (ADR-004 §3.5, D-004-1)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

THUMB_SIZE = 320
JPEG_QUALITY = 80


def make_thumbnail(src: Path, out_dir: Path, photo_sha256: str) -> str | None:
    """Write `<out_dir>/thumbs/<sha>.jpg` (320 px longest side) and return its relative path, or None."""
    rel = f"thumbs/{photo_sha256}.jpg"
    try:
        with Image.open(src) as im:
            im.thumbnail((THUMB_SIZE, THUMB_SIZE))
            rgb = im.convert("RGB")
        target = out_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        rgb.save(target, "JPEG", quality=JPEG_QUALITY)
    except (OSError, ValueError, Image.DecompressionBombError):
        return None
    return rel
