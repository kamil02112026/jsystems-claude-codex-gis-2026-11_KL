"""Image preparation for Jev limits (ADR-003 §3.2, D-003-7; IMG-01, IMG-02, F5.1)."""

from __future__ import annotations

import dataclasses
import hashlib
import io
from pathlib import Path

import pytest
from PIL import Image

from mapqa.models.image_prep import (
    IMAGE_PREP_VERSION,
    ImageOutOfBounds,
    PreparedImage,
    prepare_image,
)


def _save(path: Path, size: tuple[int, int], fmt: str = "PNG", **kwargs: object) -> Path:
    Image.new("RGB", size, color=(120, 60, 30)).save(path, format=fmt, **kwargs)
    return path


def _decode(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


def test_version_constant() -> None:
    assert IMAGE_PREP_VERSION == "image_prep.v2"


def test_small_crop_is_upscaled_so_shorter_side_is_280(tmp_path: Path) -> None:
    # Jev returned HTTP 400 "Invalid image dimensions" for 274×287 (capture 2026-11-13): min side is 280 in practice
    prepared = prepare_image(_save(tmp_path / "crop.png", (120, 200)))
    img = _decode(prepared.data)
    assert img.format == "JPEG"
    assert min(img.size) == 280
    assert max(img.size) <= 1568
    assert 78_400 <= img.size[0] * img.size[1] <= 2_458_624


@pytest.mark.parametrize("size", [(120, 140), (63, 63), (85, 90)])
def test_small_square_crops_are_upscaled_to_pixel_minimum(tmp_path: Path, size: tuple[int, int]) -> None:
    # IMG-01: upscaling only the short side to 256 leaves ~256x256 = 65 536 px < 78 400 px;
    # the rule upscales until both minima hold (ADR-003 §3.2 step 3, corrected 2026-11-12).
    img = _decode(prepare_image(_save(tmp_path / "crop.png", size)).data)
    assert min(img.size) >= 256
    assert img.size[0] * img.size[1] >= 78_400
    assert max(img.size) <= 1568


def test_all_course_crops_are_accepted(data_dir: Path) -> None:
    crops = sorted((data_dir / "signs" / "crops").glob("*.jpg"))
    assert len(crops) == 119
    rejected = []
    for p in crops:
        try:
            prepare_image(p)
        except ImageOutOfBounds:
            rejected.append(p.name)
    assert rejected == []


def test_large_frame_is_downscaled_so_longer_side_is_1568(tmp_path: Path) -> None:
    prepared = prepare_image(_save(tmp_path / "frame.png", (4000, 3000), fmt="JPEG"))
    img = _decode(prepared.data)
    assert max(img.size) == 1568
    assert min(img.size) >= 256
    assert 78_400 <= img.size[0] * img.size[1] <= 2_458_624


def test_exif_orientation_is_applied_and_metadata_removed(tmp_path: Path) -> None:
    src = tmp_path / "rotated.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 degrees clockwise on display
    Image.new("RGB", (300, 200), color=(10, 200, 10)).save(src, format="JPEG", exif=exif.tobytes())
    prepared = prepare_image(src)
    img = _decode(prepared.data)
    assert img.size[1] > img.size[0]  # portrait after transpose
    assert len(img.getexif()) == 0
    assert "exif" not in img.info


def test_gif_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ImageOutOfBounds):
        prepare_image(_save(tmp_path / "sign.gif", (300, 300), fmt="GIF"))


def test_extreme_aspect_ratio_is_out_of_bounds(tmp_path: Path) -> None:
    # 40x400 -> upscaled to 256x2560, longer side > 1568
    with pytest.raises(ImageOutOfBounds):
        prepare_image(_save(tmp_path / "strip.png", (40, 400)))


def test_same_input_gives_identical_bytes(tmp_path: Path) -> None:
    src = _save(tmp_path / "crop.png", (200, 260))
    assert prepare_image(src).data == prepare_image(src).data


def test_source_sha256_is_hash_of_source_file(tmp_path: Path) -> None:
    src = _save(tmp_path / "crop.png", (200, 260))
    prepared = prepare_image(src)
    assert prepared.source_sha256 == hashlib.sha256(src.read_bytes()).hexdigest()
    assert prepared.mime == "image/jpeg"


def test_prepared_image_has_no_filename_or_photo_id_fields() -> None:
    names = {f.name for f in dataclasses.fields(PreparedImage)}
    assert names == {"data", "mime", "source_sha256"}


def test_prepared_image_is_frozen(tmp_path: Path) -> None:
    prepared = prepare_image(_save(tmp_path / "crop.png", (200, 260)))
    with pytest.raises(dataclasses.FrozenInstanceError):
        prepared.mime = "image/png"  # type: ignore[misc]
