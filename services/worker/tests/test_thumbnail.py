import io
import os
import struct
import subprocess
import sys
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from PIL import Image, JpegImagePlugin

from kiln_worker.errors import ImageTooLargeError, UnreadableImageError
from kiln_worker.thumbnail import THUMBNAIL_MEDIA_TYPE, make_thumbnail


def _image(fmt: str, size: tuple[int, int], *, exif_orientation: int | None = None) -> bytes:
    image = Image.new("RGB", size, (200, 120, 40))
    buffer = io.BytesIO()
    if exif_orientation is not None:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation  # Orientation
        exif[0x8825] = {2: (1.0, 2.0, 3.0)}  # GPS block that must not survive
        image.save(buffer, fmt, exif=exif)
    else:
        image.save(buffer, fmt)
    return buffer.getvalue()


def _noise_png() -> bytes:
    image = Image.frombytes("RGB", (64, 64), bytes(range(256)) * 48)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def _png_header_only(width: int, height: int) -> bytes:
    """A PNG whose header declares huge dimensions; pixels are never needed for the check."""

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body))
            + kind
            + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\x00"))


@pytest.mark.parametrize(
    ("fmt", "content_type"), [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")]
)
def test_a_wide_image_becomes_a_512_px_webp_keeping_its_aspect(fmt: str, content_type: str) -> None:
    thumbnail = make_thumbnail(_image(fmt, (2048, 1024)), content_type)

    with Image.open(io.BytesIO(thumbnail)) as result:
        assert result.format == "WEBP"
        assert result.size == (512, 256)
    assert THUMBNAIL_MEDIA_TYPE == "image/webp"


def test_a_small_image_is_not_enlarged() -> None:
    thumbnail = make_thumbnail(_image("PNG", (100, 50)), "image/png")

    with Image.open(io.BytesIO(thumbnail)) as result:
        assert result.size == (100, 50)


def test_exif_orientation_is_applied_and_metadata_is_stripped() -> None:
    rotated = _image("JPEG", (400, 200), exif_orientation=6)  # 6 = rotate 90° clockwise

    thumbnail = make_thumbnail(rotated, "image/jpeg")

    with Image.open(io.BytesIO(thumbnail)) as result:
        assert result.size == (200, 400)
        assert not result.getexif()
        assert "exif" not in result.info


def test_transparency_is_kept_for_png() -> None:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")

    thumbnail = make_thumbnail(buffer.getvalue(), "image/png")

    with Image.open(io.BytesIO(thumbnail)) as result:
        assert result.mode == "RGBA"
        pixel = result.getpixel((0, 0))
        assert isinstance(pixel, tuple)
        assert pixel[3] == 0


def test_a_header_over_50_megapixels_is_refused_without_decoding() -> None:
    with pytest.raises(ImageTooLargeError):
        make_thumbnail(_png_header_only(10_000, 6_000), "image/png")


def test_exactly_50_megapixels_is_allowed_past_the_size_check() -> None:
    # 50 MP passes the size check, then fails only because the pixels are missing.
    with pytest.raises(UnreadableImageError):
        make_thumbnail(_png_header_only(10_000, 5_000), "image/png")


@pytest.mark.parametrize(
    ("data", "content_type"),
    [
        (b"not an image at all", "image/png"),
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * 40, "image/png"),
        (_image("PNG", (10, 10)), "image/jpeg"),  # bytes are not the declared type
        (_image("GIF", (10, 10)), "image/png"),  # a decoder outside the allow-list
        (_noise_png()[: len(_noise_png()) // 2], "image/png"),  # truncated
    ],
)
def test_unreadable_or_mislabelled_files_are_refused(data: bytes, content_type: str) -> None:
    with pytest.raises(UnreadableImageError):
        make_thumbnail(data, content_type)


def test_a_model_file_is_not_an_image_job() -> None:
    with pytest.raises(UnreadableImageError):
        make_thumbnail(b"glTF....", "model/gltf-binary")


def _noise(mode: str, side: int) -> Image.Image:
    return Image.frombytes(mode, (side, side), os.urandom(side * side * len(mode)))


def _encoded(image: Image.Image, fmt: str, **options: object) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, fmt, **options)
    return buffer.getvalue()


def test_a_16_bit_height_map_is_scaled_not_clipped_to_white() -> None:
    gradient = Image.new("I;16", (256, 8))
    gradient.putdata([x * 257 for x in range(256)] * 8)

    thumbnail = make_thumbnail(_encoded(gradient, "PNG"), "image/png")

    with Image.open(io.BytesIO(thumbnail)) as result:
        grey = result.convert("L")
        row = [cast(int, grey.getpixel((x, 4))) for x in range(0, 256, 32)]
    assert row == sorted(row)
    assert row[0] < 20
    assert row[-1] > 200
    assert len(set(row)) == len(row)


@pytest.mark.parametrize("side", [2048, 4096])
def test_large_16_bit_maps_are_thumbnailed(side: int) -> None:
    gradient = Image.new("I;16", (side, side), 1000)
    gradient.paste(60000, (side // 2, 0, side, side))

    thumbnail = make_thumbnail(_encoded(gradient, "PNG"), "image/png")

    with Image.open(io.BytesIO(thumbnail)) as result:
        grey = result.convert("L")
        assert result.size == (512, 512)
        assert cast(int, grey.getpixel((10, 10))) < 10
        assert cast(int, grey.getpixel((500, 10))) > 245


def test_a_16_bit_map_that_does_not_start_at_zero_uses_its_full_range() -> None:
    gradient = Image.new("I;16", (256, 8))
    gradient.putdata([20000 + x * 100 for x in range(256)] * 8)

    thumbnail = make_thumbnail(_encoded(gradient, "PNG"), "image/png")

    with Image.open(io.BytesIO(thumbnail)) as result:
        grey = result.convert("L")
        assert cast(int, grey.getpixel((0, 4))) < 10
        assert cast(int, grey.getpixel((255, 4))) > 245


def test_a_flat_16_bit_map_keeps_its_level() -> None:
    flat = Image.new("I;16", (64, 64), 30000)

    thumbnail = make_thumbnail(_encoded(flat, "PNG"), "image/png")

    with Image.open(io.BytesIO(thumbnail)) as result:
        assert abs(cast(int, result.convert("L").getpixel((5, 5))) - 117) <= 2


def test_palette_transparency_is_kept_as_alpha() -> None:
    palette = Image.new("P", (32, 32), 0)
    palette.putpalette([0, 0, 0, 255, 0, 0] + [0] * 762)
    palette.paste(1, (16, 0, 32, 32))

    thumbnail = make_thumbnail(_encoded(palette, "PNG", transparency=0), "image/png")

    with Image.open(io.BytesIO(thumbnail)) as result:
        assert result.mode == "RGBA"
        assert result.getpixel((0, 0))[3] == 0  # type: ignore[index]
        assert result.getpixel((31, 0))[3] == 255  # type: ignore[index]


def test_jpeg_is_decoded_at_reduced_size(monkeypatch: pytest.MonkeyPatch) -> None:
    requested: list[tuple[str | None, tuple[int, int] | None]] = []
    original = JpegImagePlugin.JpegImageFile.draft

    def spy(
        self: JpegImagePlugin.JpegImageFile, mode: str | None, size: tuple[int, int] | None
    ) -> object:
        requested.append((mode, size))
        return original(self, mode, size)

    monkeypatch.setattr(JpegImagePlugin.JpegImageFile, "draft", spy)

    make_thumbnail(_image("JPEG", (2048, 2048)), "image/jpeg")

    assert requested == [("RGB", (512, 512))]


@pytest.mark.parametrize(("side", "refused"), [(2828, False), (2829, True)])
def test_webp_is_limited_to_8_megapixels(side: int, refused: bool) -> None:
    data = _encoded(Image.new("RGB", (side, side), (5, 5, 5)), "WEBP", quality=10)

    if refused:
        with pytest.raises(ImageTooLargeError):
            make_thumbnail(data, "image/webp")
    else:
        assert make_thumbnail(data, "image/webp")


_PEAK_SCRIPT = """
import resource, sys
from kiln_worker.thumbnail import make_thumbnail
data = open(sys.argv[1], "rb").read()
base = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
make_thumbnail(data, sys.argv[2])
grown = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - base
print(grown if sys.platform == "darwin" else grown * 1024)
"""


@pytest.mark.parametrize(
    ("image", "fmt", "content_type"),
    [
        (lambda: Image.new("RGBA", (2828, 2828), (1, 2, 3, 128)), "WEBP", "image/webp"),
        (lambda: _noise("RGBA", 2828), "WEBP_LOSSLESS", "image/webp"),
        (lambda: Image.new("I;16", (7000, 7000), 4000), "PNG", "image/png"),
        (lambda: Image.new("RGB", (7000, 7000), (1, 2, 3)), "PNG", "image/png"),
        (lambda: Image.new("RGB", (7000, 7000), (1, 2, 3)), "JPEG", "image/jpeg"),
    ],
)
def test_peak_memory_stays_within_the_job_budget_at_each_formats_limit(
    tmp_path: Path, image: Callable[[], Image.Image], fmt: str, content_type: str
) -> None:
    source = tmp_path / f"limit.{fmt.lower()}"
    if fmt == "WEBP_LOSSLESS":
        image().save(source, "WEBP", lossless=True)
    else:
        image().save(source, fmt)
    script = tmp_path / "peak.py"
    script.write_text(_PEAK_SCRIPT)

    result = subprocess.run(  # noqa: S603 - fixed interpreter, script and arguments
        [sys.executable, str(script), str(source), content_type],
        capture_output=True,
        text=True,
        check=True,
    )

    assert int(result.stdout.strip()) < 300 * 1024 * 1024
