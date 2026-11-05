import io
import struct
import zlib

import pytest
from PIL import Image

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
