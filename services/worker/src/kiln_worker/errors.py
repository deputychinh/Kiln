"""Permanent processing failures; each maps to a version failure reason."""


class ProcessingError(Exception):
    """A file that will never process, whatever the retry."""


class UnreadableImageError(ProcessingError):
    """Corrupt bytes, a type other than the declared one, or a decoder outside the allow-list."""


class ImageTooLargeError(ProcessingError):
    """The header declares more pixels than the worker will decode."""


class UnreadableModelError(ProcessingError):
    """Not a glTF 2.0 binary the worker can read (broken, external buffers, required extensions)."""


class ModelTooLargeError(ProcessingError):
    """More geometry (or a bigger JSON chunk) than the worker will decode."""


class PreviewCrashedError(Exception):
    """The preview process died for a reason that may not happen again (retried as transient)."""
