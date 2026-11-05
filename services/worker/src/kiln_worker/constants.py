"""Named constants for the worker."""

THUMBNAIL_MAX_SIDE = 512
THUMBNAIL_QUALITY = 82
# Header-declared pixels above this are refused before decoding (decompression bombs).
MAX_SOURCE_PIXELS = 50_000_000
# Only these decoders ever run on uploaded bytes (GD, PCF and others are never reached).
DECODERS_BY_MEDIA_TYPE: dict[str, tuple[str, ...]] = {
    "image/png": ("PNG",),
    "image/jpeg": ("JPEG",),
    "image/webp": ("WEBP",),
}
