"""Image thumbnails: allow-listed decoders, size check before decoding, metadata stripped."""

import io
import warnings
from typing import IO, cast

from PIL import Image, ImageOps, UnidentifiedImageError

from kiln_worker.constants import (
    DECODERS_BY_MEDIA_TYPE,
    MAX_SOURCE_PIXELS_BY_DECODER,
    THUMBNAIL_MAX_SIDE,
    THUMBNAIL_QUALITY,
)
from kiln_worker.errors import ImageTooLargeError, UnreadableImageError

THUMBNAIL_MEDIA_TYPE = "image/webp"
_KEEP_ALPHA = {"RGBA", "LA", "PA"}
_WIDE_GREY = {"I", "I;16", "I;16B", "I;16L", "I;16N"}
_REDUCING_GAP = 2.0  # Pillow's default for thumbnail()
_SIXTEEN_TO_EIGHT_BIT = 1 / 256


def make_thumbnail(source: bytes | IO[bytes], content_type: str) -> bytes:
    """Return a WebP whose longest side is at most 512 px, EXIF-oriented, without metadata.

    Raises:
        ImageTooLargeError: The header declares more than 50 megapixels.
        UnreadableImageError: Not a readable image of the declared type.
    """
    decoders = DECODERS_BY_MEDIA_TYPE.get(content_type)
    if decoders is None:
        raise UnreadableImageError
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            stream = io.BytesIO(source) if isinstance(source, bytes) else source
            with Image.open(stream, formats=list(decoders)) as opened:
                width, height = opened.size
                if width * height > MAX_SOURCE_PIXELS_BY_DECODER[opened.format or ""]:
                    raise ImageTooLargeError
                opened.draft("RGB", (THUMBNAIL_MAX_SIDE, THUMBNAIL_MAX_SIDE))
                # Shrink first, then orient: rotating the full image would copy every pixel.
                # reduce() rejects 16-bit greyscale; plain resampling handles it.
                gap = None if opened.mode in _WIDE_GREY else _REDUCING_GAP
                opened.thumbnail((THUMBNAIL_MAX_SIDE, THUMBNAIL_MAX_SIDE), reducing_gap=gap)
                image = ImageOps.exif_transpose(opened)
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as error:
            raise UnreadableImageError from error
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
            raise ImageTooLargeError from error
    clean = _to_8_bit(image)
    output = io.BytesIO()
    clean.save(output, "WEBP", quality=THUMBNAIL_QUALITY, method=4)
    return output.getvalue()


def _to_8_bit(image: Image.Image) -> Image.Image:
    """RGB or RGBA for WebP; 16/32-bit greyscale (height maps) is scaled, not clipped."""
    if image.mode in _WIDE_GREY:
        wide = image.convert("I")
        low, high = cast("tuple[int, int]", wide.getextrema())  # mode "I": one (min, max) pair
        if high == low:  # a flat map: keep its level instead of stretching to black
            scaled = wide.point(lambda value: value * _SIXTEEN_TO_EIGHT_BIT)
        else:
            scaled = wide.point(lambda value: (value - low) * 255 / (high - low))
        return scaled.convert("L").convert("RGB")
    keep_alpha = image.mode in _KEEP_ALPHA or "transparency" in image.info
    return image.convert("RGBA" if keep_alpha else "RGB")
