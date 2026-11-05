"""Image thumbnails: allow-listed decoders, size check before decoding, metadata stripped."""

import io
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from kiln_worker.constants import (
    DECODERS_BY_MEDIA_TYPE,
    MAX_SOURCE_PIXELS,
    THUMBNAIL_MAX_SIDE,
    THUMBNAIL_QUALITY,
)
from kiln_worker.errors import ImageTooLargeError, UnreadableImageError

THUMBNAIL_MEDIA_TYPE = "image/webp"
_KEEP_ALPHA = {"RGBA", "LA", "PA"}


def make_thumbnail(data: bytes, content_type: str) -> bytes:
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
            with Image.open(io.BytesIO(data), formats=list(decoders)) as source:
                width, height = source.size
                if width * height > MAX_SOURCE_PIXELS:
                    raise ImageTooLargeError
                source.draft("RGB", (THUMBNAIL_MAX_SIDE, THUMBNAIL_MAX_SIDE))
                image = ImageOps.exif_transpose(source)
                image.thumbnail((THUMBNAIL_MAX_SIDE, THUMBNAIL_MAX_SIDE))
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as error:
            raise UnreadableImageError from error
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
            raise ImageTooLargeError from error
    mode = "RGBA" if image.mode in _KEEP_ALPHA or "transparency" in image.info else "RGB"
    clean = image.convert(mode)
    output = io.BytesIO()
    clean.save(output, "WEBP", quality=THUMBNAIL_QUALITY, method=4)
    return output.getvalue()
