"""Permanent processing failures; each maps to a version failure reason."""


class ProcessingError(Exception):
    """A file that will never process, whatever the retry."""


class UnreadableImageError(ProcessingError):
    """Corrupt bytes, a type other than the declared one, or a decoder outside the allow-list."""


class ImageTooLargeError(ProcessingError):
    """The header declares more pixels than the worker will decode."""
